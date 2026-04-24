"""UNESCO Global AI Ethics and Governance Observatory (GAIGO) fetcher.

Closes the "non-OECD-orbit regional and country-level bodies" gap the
OECD.AI Policy Navigator fetcher (Task 4) leaves open — countries and
regional bodies that are not OECD members, or whose deposit to OECD
lags behind the UNESCO readiness-assessment track, are systematically
under-represented upstream. UNESCO GAIGO specifically indexes:

  - country AI-ethics profiles (all UNESCO member states);
  - Readiness Assessment Methodology (RAM) pilots;
  - regional initiatives and UNESCO-aligned programmes.

Emits one ``RawVenue`` per GAIGO card with ``source_role='discovery'``.
Like ``OECDFetcher`` (Task 4), the live ingestion path of this fetcher
has **not** been exercised in the authoring sandbox; the BaseFetcher
contract tries static HTTP first and falls back to Playwright. When
first run online, record in the module docstring below which strategy
the UNESCO site actually required, and add a sample cached response
under ``tests/fixtures/unesco_gaigo/`` alongside the synthetic
``index.html`` that currently drives the tests.

CLI::

    python -m pipelines.fetchers.unesco_gaigo                 # live → fixture
    python -m pipelines.fetchers.unesco_gaigo --live          # force live
    python -m pipelines.fetchers.unesco_gaigo --from-fixture  # offline
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
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "unesco_gaigo" / "index.html"
)


class UNESCOGaigoFetcher(BaseFetcher):
    source_id = "unesco_gaigo"
    base_url = "https://www.unesco.org/ethics-ai/en"
    required_selectors = ['class="gaigo-entry"']

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
        cards = soup.find_all("article", class_="gaigo-entry")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for card in cards:
            entry_id = (card.get("data-id") or "").strip()
            entry_kind = (card.get("data-kind") or "").strip()
            title_el = card.find(["h2", "h3"])
            name = title_el.get_text(strip=True) if title_el else ""
            link_el = card.find("a", class_="gaigo-link")
            url = (link_el.get("href") if link_el else "") or ""
            country_el = card.find(class_="country")
            country = country_el.get_text(strip=True) if country_el else None
            region_el = card.find(class_="region")
            region = region_el.get_text(strip=True) if region_el else None
            desc_el = card.find(class_="description")
            description = desc_el.get_text(strip=True) if desc_el else None
            if not (name and url):
                self._log.debug("skipping card missing name or url: data-id=%s", entry_id)
                continue
            venues.append(
                RawVenue(
                    source_id=(
                        f"unesco.gaigo:{entry_id}" if entry_id
                        else f"unesco.gaigo:{url}"
                    ),
                    source_role="discovery",
                    source_registry=self.source_id,
                    name=name,
                    url=url,
                    country=country,
                    description=description,
                    fetched_at=ts,
                    fetch_strategy=strategy,
                    raw_blob={
                        "entry_id": entry_id,
                        "entry_kind": entry_kind,
                        "region": region,
                    },
                )
            )
        self._log.info(
            "parsed %d RawVenue records from UNESCO GAIGO (strategy=%s)",
            len(venues), strategy,
        )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.unesco_gaigo",
        description=(
            "UNESCO Global AI Ethics and Governance Observatory discovery "
            "fetcher. Default: try live fetch, fall back to shipped fixture "
            "on failure."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; error out on any failure")
    g.add_argument("--fixture", type=Path,
                   help="use this HTML file instead of fetching")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_PATH.relative_to(REPO_ROOT)}")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path(".cache/unesco_gaigo"),
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
    log = logging.getLogger("fetcher.unesco_gaigo.cli")

    if args.fixture:
        fetcher = UNESCOGaigoFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = UNESCOGaigoFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = UNESCOGaigoFetcher(cache_dir=args.cache_dir)
    else:
        # Default: live with fixture fallback (Task 4 pattern).
        try:
            fetcher = UNESCOGaigoFetcher(cache_dir=args.cache_dir)
            venues = fetcher.fetch()
            _emit_records(venues)
            print(
                f"fetched {len(venues)} records (live, source_role=discovery)",
                file=sys.stderr,
            )
            return 0
        except Exception as e:  # noqa: BLE001 — CLI-level fallback by design
            log.warning(
                "live fetch failed (%s); falling back to shipped fixture", e,
            )
            fetcher = UNESCOGaigoFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

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
