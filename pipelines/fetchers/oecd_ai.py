"""OECD.AI Policy Observatory discovery fetcher — international dashboard.

What it reads, and why that page
--------------------------------
``https://oecd.ai/en/dashboards/international`` indexes 14 intergovernmental
organisations — African Union, ASEAN, Council of Europe, EU, G7,
Inter-American Development Bank, OECD/GPAI, UN, UNESCO, OAS, Arab League,
APEC, IEEE, ISO — each linking to a page of that organisation's AI
initiatives. Council of Europe lists HUDERIA and the Framework Convention;
OECD/GPAI lists the Hiroshima AI Process reporting framework; ISO lists
ISO/IEC 42001 and 23894.

The fetcher walks that two-level structure: index → per-organisation page →
initiative.

It deliberately does **not** read ``/en/dashboards/policy-initiatives``, the
site's full database. Probing it on 2026-09-07 found it dominated by
national policy instruments — Zimbabwe's national strategy, Sweden's AI
strategy, Egypt's guidelines — which AGVO excludes as national-only
entities (CLAUDE.md §3.1). Pointing discovery there would bury the
reviewer in out-of-scope proposals, the failure this pipeline already hit
in September when all 17 proposals turned out to be news articles.

What a record here is, and is not
---------------------------------
OECD.AI catalogues **policy instruments**; AGVO catalogues **venues**. The
two do not correspond one to one: "ISO/IEC 42001" is a standard, and the
AGV is the working group that maintains it; the "Framework Convention on
AI" is a treaty, and the AGV is the committee under it. So a record from
this fetcher is a *pointer* to a venue, not a venue — which is what a
discovery source is for (§5.1), and why the normalizer requires pairing
with a verification source before anything is promoted. Do not expect the
proposal count to be a venue count.

Live strategy: static HTTP
--------------------------
Confirmed 2026-09-07 against captures under ``tests/fixtures/oecd_ai/``:
``intergovernmental-card`` appears 14 times in both the static response
and the rendered DOM, and the per-organisation pages carry their
initiative links in the static HTML too. The Playwright fallback stays as
a safety net but is not on the expected path.

The previous target, ``/en/dashboards/overview/policy``, returns HTTP 404;
the fixture that made this fetcher's tests pass had been written to match
its selectors rather than captured from it.

CLI (``python -m pipelines.fetchers.oecd_ai``):
    default: try live, fall back to shipped fixtures on any failure.
    --live:            force live; error out on failure.
    --fixture-dir PATH: read captures from this directory instead.
    --from-fixture:    shortcut for the shipped captures.
    --cache-dir PATH:  on-disk response cache (ignored in fixture mode).
    --quiet:           suppress INFO logs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "oecd_ai"

SITE_ROOT = "https://oecd.ai"

# Initiative links are recognised by their path, not by a class name. The
# site is an Angular build whose component classes carry generated
# `_ngcontent-*` attributes; a path is the stable thing on the page.
INITIATIVE_PATH = "/policy-initiatives/"


@dataclass(frozen=True)
class Organisation:
    """One intergovernmental organisation on the international dashboard."""

    slug: str
    name: str
    url: str


class OECDFetcher(BaseFetcher):
    source_id = "oecd_ai_navigator"
    base_url = "https://oecd.ai/en/dashboards/international"
    required_selectors = ["intergovernmental-card"]

    def __init__(
        self,
        fixture_dir: Path | None = None,
        cache_dir: Path | None = None,
    ):
        super().__init__(cache_dir=cache_dir)
        self.fixture_dir = fixture_dir

    # ---- fixture layout ----------------------------------------------

    def _index_fixture(self) -> Path:
        return self.fixture_dir / "international" / "live" / "static.html"

    def _organisation_fixture(self, slug: str) -> Path:
        return self.fixture_dir / f"international-{slug}" / "live" / "static.html"

    # ---- fetching -----------------------------------------------------

    def fetch(self) -> list[RawVenue]:
        if self.fixture_dir is not None:
            index_html = self._index_fixture().read_text(encoding="utf-8")
            strategy = FETCH_STRATEGY_FIXTURE
            self._log.info("fixture mode: %s", self._index_fixture())
        else:
            index_html, strategy = self.fetch_html_with_fallback(self.base_url)

        organisations = self.parse_organisations(index_html)
        self._log.info("index lists %d organisations", len(organisations))

        ts = self.now_iso()
        venues: list[RawVenue] = []
        for org in organisations:
            html = self._organisation_html(org)
            if html is None:
                continue
            found = self.parse_initiatives(html, org, ts, strategy)
            self._log.info("%s: %d initiatives", org.slug, len(found))
            venues.extend(found)

        self._log.info(
            "parsed %d RawVenue records from %d organisations (strategy=%s)",
            len(venues), len(organisations), strategy,
        )
        return venues

    def _organisation_html(self, org: Organisation) -> str | None:
        """Page for one organisation, or None when it cannot be read.

        A missing fixture is normal: the shipped captures cover a few
        organisations, not all 14, and a fixture-mode run should exercise
        what is there rather than fail on what is not. A live fetch that
        fails for one organisation should not lose the other thirteen
        either — this is discovery, and a partial answer beats none.
        """
        if self.fixture_dir is not None:
            path = self._organisation_fixture(org.slug)
            if not path.exists():
                self._log.debug("no fixture for %s (%s)", org.slug, path)
                return None
            return path.read_text(encoding="utf-8")
        try:
            html, _ = self.fetch_html_with_fallback(org.url, required_selectors=[])
            return html
        except Exception as e:  # noqa: BLE001 — one dead org page is not fatal
            self._log.warning("failed to fetch %s (%s): %s", org.slug, org.url, e)
            return None

    # ---- parsing ------------------------------------------------------

    @staticmethod
    def parse_organisations(html: str) -> list[Organisation]:
        """The organisations indexed on the international dashboard."""
        soup = BeautifulSoup(html, "html.parser")
        organisations: list[Organisation] = []
        seen: set[str] = set()
        for card in soup.find_all(class_="intergovernmental-card"):
            href = (card.get("href") or "").strip()
            if not href:
                continue
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in seen:
                continue
            label = card.find("span")
            name = label.get_text(" ", strip=True) if label else slug
            seen.add(slug)
            organisations.append(
                Organisation(slug=slug, name=name, url=urljoin(SITE_ROOT, href)),
            )
        return organisations

    @staticmethod
    def parse_initiatives(
        html: str, org: Organisation, fetched_at: str, strategy: str,
    ) -> list[RawVenue]:
        """Initiatives listed on one organisation's page.

        Each initiative is rendered as two anchors to the same href — the
        title, then the description — so the anchors are grouped by href
        and read in document order.
        """
        soup = BeautifulSoup(html, "html.parser")
        by_href: dict[str, list[str]] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if INITIATIVE_PATH not in href:
                continue
            text = a.get_text(" ", strip=True)
            if text:
                by_href.setdefault(href, []).append(text)

        venues: list[RawVenue] = []
        for href, texts in by_href.items():
            name = texts[0]
            description = texts[1] if len(texts) > 1 else None
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            venues.append(
                RawVenue(
                    source_id=f"oecd.ai:{slug}",
                    source_role="discovery",
                    source_registry=OECDFetcher.source_id,
                    name=name,
                    url=urljoin(SITE_ROOT, href),
                    country=None,  # intergovernmental by construction
                    description=description,
                    fetched_at=fetched_at,
                    fetch_strategy=strategy,
                    raw_blob={
                        "initiative_slug": slug,
                        "organisation": org.name,
                        "organisation_slug": org.slug,
                        "organisation_url": org.url,
                    },
                )
            )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.oecd_ai",
        description=(
            "OECD.AI international-dashboard discovery fetcher. "
            "Default: try live fetch, fall back to shipped captures on failure."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; error out on any failure (no fixture fallback)")
    g.add_argument("--fixture-dir", type=Path,
                   help="read captures from this directory instead of fetching")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_DIR.relative_to(REPO_ROOT)}")
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

    if args.fixture_dir:
        fetcher = OECDFetcher(fixture_dir=args.fixture_dir)
    elif args.from_fixture:
        fetcher = OECDFetcher(fixture_dir=DEFAULT_FIXTURE_DIR)
    elif args.live:
        fetcher = OECDFetcher(cache_dir=args.cache_dir)
    else:
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
            log.warning("live fetch failed (%s); falling back to shipped captures", e)
            fetcher = OECDFetcher(fixture_dir=DEFAULT_FIXTURE_DIR)

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
