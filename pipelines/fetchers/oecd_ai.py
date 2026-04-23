"""OECD.AI Policy Navigator discovery fetcher.

Targets the OECD.AI Policy Observatory's initiative listing at
``https://oecd.ai/en/dashboards/overview/policy`` and emits one
``RawVenue`` per listed policy initiative, flagged ``source_role='discovery'``.

**Strategy note** (CLAUDE.md §9 Task 4, step 3).

At Task 4 authoring time the live OECD.AI endpoint was **not** exercised
(the sandboxed environment had no committed outbound network path). The
fetcher therefore was validated entirely against the shipped synthetic
fixture at ``tests/fixtures/oecd_ai/dashboards.html``. The BaseFetcher
contract tries static HTTP first and falls back to Playwright when the
caller-supplied selectors are absent in the static response. The first
time this module is run online, whoever executes it should:

1. Run ``python -m pipelines.fetchers.oecd_ai --live --quiet`` and inspect
   the stderr log line that reports the succeeding strategy.
2. Update this docstring and the ``sources/registry.yml`` entry for
   ``oecd_ai_navigator`` to reflect which strategy (``http_static`` vs
   ``playwright``) the OECD.AI dashboard actually required.

CLI (``python -m pipelines.fetchers.oecd_ai``):
    default: try live, fall back to shipped fixture on any failure.
    --live:     force live; error out on failure.
    --fixture PATH: use a custom HTML fixture instead of the default.
    --from-fixture: shortcut for ``--fixture tests/fixtures/oecd_ai/dashboards.html``.
    --cache-dir PATH: on-disk response cache (ignored in fixture mode).
    --quiet:   suppress INFO logs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "oecd_ai" / "dashboards.html"


class OECDFetcher(BaseFetcher):
    source_id = "oecd_ai_navigator"
    base_url = "https://oecd.ai/en/dashboards/overview/policy"
    required_selectors = ['class="initiative-card"']

    def __init__(
        self,
        fixture_path: Path | None = None,
        cache_dir: Path | None = None,
    ):
        super().__init__(cache_dir=cache_dir)
        self.fixture_path = fixture_path

    def fetch(self) -> list[RawVenue]:
        if self.fixture_path is not None:
            html = self.fixture_path.read_text(encoding="utf-8")
            strategy = FETCH_STRATEGY_FIXTURE
            self._log.info("fixture mode: %s", self.fixture_path)
        else:
            html, strategy = self.fetch_html_with_fallback(self.base_url)
        return self._parse(html, strategy)

    def _parse(self, html: str, strategy: str) -> list[RawVenue]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("article", class_="initiative-card")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for card in cards:
            data_id = (card.get("data-id") or "").strip()
            title_el = card.find(["h2", "h3"])
            name = title_el.get_text(strip=True) if title_el else ""
            link_el = card.find("a", class_="initiative-link")
            url = (link_el.get("href") if link_el else "") or ""
            country_el = card.find(class_="country")
            country = country_el.get_text(strip=True) if country_el else None
            desc_el = card.find(class_="description")
            description = desc_el.get_text(strip=True) if desc_el else None
            if not (name and url):
                self._log.debug("skipping card missing name or url: data-id=%s", data_id)
                continue
            venues.append(
                RawVenue(
                    source_id=f"oecd.ai:{data_id}" if data_id else f"oecd.ai:{url}",
                    source_role="discovery",
                    source_registry=self.source_id,
                    name=name,
                    url=url,
                    country=country,
                    description=description,
                    fetched_at=ts,
                    fetch_strategy=strategy,
                    raw_blob={"data_id": data_id},
                )
            )
        self._log.info("parsed %d RawVenue records (strategy=%s)", len(venues), strategy)
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.oecd_ai",
        description=(
            "OECD.AI Policy Navigator discovery fetcher. "
            "Default: try live fetch, fall back to shipped fixture on failure."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; error out on any failure (no fixture fallback)")
    g.add_argument("--fixture", type=Path,
                   help="use this HTML file instead of fetching")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_PATH.relative_to(REPO_ROOT)}")
    ap.add_argument("--cache-dir", type=Path, default=Path(".cache/oecd_ai"),
                    help="on-disk response cache directory (live mode only)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress INFO log messages")
    return ap


def _configure_logging(quiet: bool) -> None:
    logging.basicConfig(
        level=logging.WARNING if quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _emit_records(venues: list[RawVenue]) -> None:
    for v in venues:
        sys.stdout.write(json.dumps(v.as_dict(), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.quiet)
    log = logging.getLogger("fetcher.oecd_ai.cli")

    # Resolve mode
    if args.fixture:
        fetcher = OECDFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = OECDFetcher(cache_dir=args.cache_dir)
    else:
        # Default: live with fixture fallback.
        try:
            fetcher = OECDFetcher(cache_dir=args.cache_dir)
            venues = fetcher.fetch()
            _emit_records(venues)
            print(
                f"fetched {len(venues)} records (live, source_role=discovery)",
                file=sys.stderr,
            )
            return 0
        except Exception as e:  # noqa: BLE001 — CLI-level fallback by design
            log.warning("live fetch failed (%s); falling back to shipped fixture", e)
            fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

    venues = fetcher.fetch()
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
