"""Config-driven government AI-page discovery fetcher.

One Python module driving N government pages via
``sources/government_pages.yml`` (Task-4 follow-on). Each YAML entry
specifies a URL, CSS selectors for the per-item title / link /
description, and a keep-if regex that narrows broad government news
indexes to their AI subset. Catches venues that live first on host-
government pages and only later (if ever) land on the OECD.AI Policy
Navigator:

  - national AISI / AI Office announcements (UK DSIT, US NIST,
    EU Commission, Korea MSIT, Japan MOFA, …);
  - ministerial AI event / summit pages;
  - national AI-strategy working-group updates.

Multiple governments share a single fetcher so that adding a new
country is ~10 lines of YAML, not a new Python module. Each target is
fetched independently through the standard ``BaseFetcher`` contract
(static HTTP → Playwright fallback + robots.txt + 1 req/sec throttle +
on-disk cache).

**Live strategy.** Not yet exercised in the authoring sandbox; the
CLI default (live-first, fixture-fallback) ensures it produces output
regardless. The first online runner should inspect the per-target
``INFO fetcher.…: http_static`` / ``playwright`` log lines and, if any
target systematically needs Playwright, either mark that in the target
entry's ``notes:`` or consider a site-specific fetcher.

CLI::

    python -m pipelines.fetchers.government_pages                 # live → fixture
    python -m pipelines.fetchers.government_pages --live          # force live
    python -m pipelines.fetchers.government_pages --from-fixture  # offline
    python -m pipelines.fetchers.government_pages --only uk_dsit_ai_news,us_nist_ai_news
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup

from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "sources" / "government_pages.yml"
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "government_pages"

log = logging.getLogger("fetcher.government_pages")


def load_targets(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return list(data.get("targets", []))


class _PerTargetFetcher(BaseFetcher):
    """BaseFetcher subclass that carries a single YAML-target config.

    We re-instantiate one per YAML entry so each target gets its own
    throttle clock, robots cache, and on-disk cache bucket.
    """

    def __init__(
        self,
        *,
        target: dict,
        cache_dir: Path | None = None,
    ):
        self.source_id = target["id"]
        self.base_url = target["url"]
        # Having the required_selectors empty means static HTTP always
        # wins from the BaseFetcher perspective; we gate quality by the
        # actual parse output below.
        self.required_selectors = []
        super().__init__(cache_dir=cache_dir)
        self.target = target

    def fetch(self) -> list[RawVenue]:
        html, strategy = self.fetch_html_with_fallback(self.base_url)
        return _parse_target(html, strategy, self.target)


def _parse_target(html: str, strategy: str, target: dict) -> list[RawVenue]:
    """Apply the per-target selectors + regex filter to a fetched page."""
    # Atom feeds are common for .gov sites; try the XML tree builder
    # when available (requires lxml), fall back to html.parser which
    # handles Atom well enough for our selector-based extraction.
    if target["url"].endswith((".atom", ".xml")):
        try:
            soup = BeautifulSoup(html, "xml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
    else:
        soup = BeautifulSoup(html, "html.parser")

    list_els = soup.select(target["list_selector"])
    title_sel = target["title_selector"]
    link_sel = target.get("link_selector") or title_sel
    desc_sel = target.get("description_selector")
    regex = target.get("include_if_regex")
    pattern = re.compile(regex) if regex else None

    ts = BaseFetcher.now_iso()
    out: list[RawVenue] = []
    for idx, el in enumerate(list_els):
        title_el = el.select_one(title_sel)
        title = title_el.get_text(strip=True) if title_el else ""
        link_el = el.select_one(link_sel)
        href = None
        if link_el is not None:
            # Atom entries use <link href="...">; HTML anchors use href.
            href = link_el.get("href") or link_el.get_text(strip=True)
        url = urljoin(target["url"], href) if href else ""
        description = None
        if desc_sel:
            desc_el = el.select_one(desc_sel)
            description = desc_el.get_text(strip=True) if desc_el else None
        if not (title and url):
            continue
        if pattern is not None:
            haystack = title + " " + (description or "")
            if not pattern.search(haystack):
                continue
        out.append(
            RawVenue(
                source_id=f"gov.{target['id']}:{idx:04d}",
                source_role="discovery",
                source_registry="government_pages",
                name=title,
                url=url,
                country=target.get("country"),
                description=description,
                fetched_at=ts,
                fetch_strategy=strategy,
                raw_blob={
                    "target_id": target["id"],
                    "language": target.get("language"),
                    "priority": target.get("priority"),
                },
            )
        )
    return out


class GovernmentPagesFetcher:
    """Thin orchestrator around N per-target BaseFetchers."""

    source_id = "government_pages"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        targets: list[dict] | None = None,
        fixture_dir: Path | None = None,
        cache_dir: Path | None = None,
    ):
        if targets is not None:
            self.targets = list(targets)
        else:
            self.targets = load_targets(config_path or DEFAULT_CONFIG_PATH)
        self.fixture_dir = Path(fixture_dir) if fixture_dir else None
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def select(self, only_ids: set[str] | None) -> list[dict]:
        if not only_ids:
            return list(self.targets)
        return [t for t in self.targets if t["id"] in only_ids]

    def fetch(self, *, only_ids: set[str] | None = None) -> list[RawVenue]:
        out: list[RawVenue] = []
        for target in self.select(only_ids):
            # Fixture mode: look for tests/fixtures/government_pages/<id>.html
            if self.fixture_dir is not None:
                fixture = self.fixture_dir / f"{target['id']}.html"
                if not fixture.exists():
                    log.warning(
                        "fixture missing for %s (%s); skipping in fixture mode",
                        target["id"], fixture,
                    )
                    continue
                html = fixture.read_text(encoding="utf-8")
                out.extend(_parse_target(html, FETCH_STRATEGY_FIXTURE, target))
                continue

            sub = _PerTargetFetcher(
                target=target,
                cache_dir=(
                    self.cache_dir / target["id"] if self.cache_dir else None
                ),
            )
            try:
                out.extend(sub.fetch())
            except Exception as e:  # noqa: BLE001 — keep other targets going
                log.warning(
                    "target %s failed: %s; continuing with remaining targets",
                    target["id"], e,
                )
        return out


# ---- CLI ----

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.government_pages",
        description=(
            "Config-driven discovery fetcher for major-government AI pages. "
            "Reads sources/government_pages.yml and scrapes each target. "
            "Default: live with fixture fallback."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; individual target failures are "
                        "logged but do not abort the run")
    g.add_argument("--fixture-dir", type=Path,
                   help="use fixture HTML files from this directory "
                        "(one <target_id>.html per target)")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_DIR.relative_to(REPO_ROOT)}")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    ap.add_argument("--cache-dir", type=Path,
                    default=Path(".cache/government_pages"))
    ap.add_argument("--only", type=str,
                    help="comma-separated target ids to run (defaults to all)")
    ap.add_argument("--quiet", action="store_true")
    return ap


def _emit_records(venues: list[RawVenue]) -> None:
    for v in venues:
        sys.stdout.write(json.dumps(v.as_dict(), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    only_ids = (
        {t.strip() for t in args.only.split(",") if t.strip()}
        if args.only else None
    )

    if args.fixture_dir:
        fetcher = GovernmentPagesFetcher(
            config_path=args.config, fixture_dir=args.fixture_dir,
        )
    elif args.from_fixture:
        fetcher = GovernmentPagesFetcher(
            config_path=args.config, fixture_dir=DEFAULT_FIXTURE_DIR,
        )
    elif args.live:
        fetcher = GovernmentPagesFetcher(
            config_path=args.config, cache_dir=args.cache_dir,
        )
    else:
        # Default: live; if it produces zero records (e.g. offline sandbox),
        # fall back to the shipped fixtures so the CLI is always useful.
        try:
            fetcher = GovernmentPagesFetcher(
                config_path=args.config, cache_dir=args.cache_dir,
            )
            venues = fetcher.fetch(only_ids=only_ids)
            if venues:
                _emit_records(venues)
                print(
                    f"fetched {len(venues)} records (live, source_role=discovery)",
                    file=sys.stderr,
                )
                return 0
            log.warning("live fetch returned 0 records; falling back to fixtures")
        except Exception as e:  # noqa: BLE001
            log.warning("live fetch failed (%s); falling back to fixtures", e)
        fetcher = GovernmentPagesFetcher(
            config_path=args.config, fixture_dir=DEFAULT_FIXTURE_DIR,
        )

    venues = fetcher.fetch(only_ids=only_ids)
    _emit_records(venues)
    print(
        f"fetched {len(venues)} records "
        f"(strategy={venues[0].fetch_strategy if venues else '(none)'}, "
        "source_role=discovery)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
