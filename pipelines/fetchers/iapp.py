"""IAPP Global AI Law and Policy Tracker discovery fetcher.

Closes the regulatory / enforcement blind spot left by the other four
fetchers. OECD.AI tracks government-announced *initiatives*, UNESCO
GAIGO tracks *readiness*, `government_pages` tracks *news*, and
`tech_policy_press` tracks *commentary* — none consistently surfaces
the **enacted AI laws + the regulators created to enforce them**.
IAPP's tracker fills exactly that cell:

  - national AI statutes + regulations (enacted / proposed / draft);
  - regulators / supervisory agencies named in those statutes
    (e.g. EU AI Office under AI Act; Spain AESIA under Royal Decree
    729/2023; Korean PIPC AI provisions; India DPDP Act AI clauses);
  - cross-jurisdictional coordination bodies (e.g. CoE Framework
    Convention CAI drafting groups).

Emitted ``RawVenue`` records are discovery-layer; the monthly
reviewer is responsible for deciding which rows correspond to new
AGVs (`national_regulator_intl` / `treaty_body`) versus standalone
laws that don't create a new venue.

**Live strategy TBD.** Not exercised in the authoring sandbox. IAPP's
tracker page mixes a static HTML summary with a JS-driven filter
widget; the BaseFetcher contract tries static first and falls back
to Playwright if the expected row selectors are missing. The first
online runner should record which path succeeded in this docstring.

CLI::

    python -m pipelines.fetchers.iapp                 # live → fixture
    python -m pipelines.fetchers.iapp --live          # force live
    python -m pipelines.fetchers.iapp --from-fixture  # offline
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
DEFAULT_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "iapp" / "tracker.html"


class IAPPFetcher(BaseFetcher):
    source_id = "iapp_ai_law_tracker"
    base_url = "https://iapp.org/resources/article/global-ai-legislation-tracker"
    # Our synthetic fixture uses class="iapp-law-entry"; the live
    # IAPP markup may differ. Adjust on first online run if needed.
    required_selectors = ['class="iapp-law-entry"']

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
        rows = soup.find_all("article", class_="iapp-law-entry")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for row in rows:
            entry_id = (row.get("data-id") or "").strip()
            status = (row.get("data-status") or "").strip()
            entry_kind = (row.get("data-kind") or "").strip()
            title_el = row.find(["h2", "h3"])
            name = title_el.get_text(strip=True) if title_el else ""
            link_el = row.find("a", class_="iapp-link")
            url = (link_el.get("href") if link_el else "") or ""
            country_el = row.find(class_="country")
            country = country_el.get_text(strip=True) if country_el else None
            date_el = row.find(class_="date")
            date_text = date_el.get_text(strip=True) if date_el else None
            authority_el = row.find(class_="authority")
            authority = authority_el.get_text(strip=True) if authority_el else None
            desc_el = row.find(class_="description")
            description = desc_el.get_text(strip=True) if desc_el else None
            if not (name and url):
                self._log.debug("skipping row missing name or url: data-id=%s", entry_id)
                continue
            venues.append(
                RawVenue(
                    source_id=(
                        f"iapp:{entry_id}" if entry_id
                        else f"iapp:{url}"
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
                        "status": status,
                        "date": date_text,
                        "authority": authority,
                    },
                )
            )
        self._log.info(
            "parsed %d RawVenue records from IAPP tracker (strategy=%s)",
            len(venues), strategy,
        )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.iapp",
        description=(
            "IAPP Global AI Law and Policy Tracker discovery fetcher. "
            "Default: try live fetch, fall back to shipped fixture on failure."
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
                    default=Path(".cache/iapp"),
                    help="on-disk response cache directory (live mode only)")
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
    log = logging.getLogger("fetcher.iapp.cli")

    if args.fixture:
        fetcher = IAPPFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = IAPPFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = IAPPFetcher(cache_dir=args.cache_dir)
    else:
        try:
            fetcher = IAPPFetcher(cache_dir=args.cache_dir)
            venues = fetcher.fetch()
            _emit_records(venues)
            print(
                f"fetched {len(venues)} records (live, source_role=discovery)",
                file=sys.stderr,
            )
            return 0
        except Exception as e:  # noqa: BLE001
            log.warning(
                "live fetch failed (%s); falling back to shipped fixture", e,
            )
            fetcher = IAPPFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

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
