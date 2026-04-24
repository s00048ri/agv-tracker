"""EvalCommunity Global AI Governance Map discovery fetcher.

**Probation status (CLAUDE.md §12.7).** The source is on probation:
its update cadence has been described in the spec as uncertain, and
the §12.7 open decision is whether to keep it in the discovery layer
at all before v0.4. This fetcher is built so that the source's
coverage can be evaluated empirically (quality + freshness of its
monthly output) instead of purely as a design-time question. If the
next three monthly runs show either (a) stale data repeating from
run to run, or (b) consistent duplication with what UNESCO GAIGO /
IAPP tracker already surface, drop this fetcher by setting
``fetcher_module: null`` in ``sources/registry.yml`` and wiring it
out of ``scripts/monthly_update.sh``. The probation outcome will be
recorded in ``CHANGELOG.md`` and reflected in §12.7.

The EvalCommunity Global AI Governance Map lists ~140 institutions
worldwide with role / region / focus metadata. We parse each
``<article class="ecom-institution">`` into a ``RawVenue`` with
``raw_blob`` carrying ``role``, ``region``, and ``focus`` so the
normalizer can map each to an AGVO ``entity_type`` downstream.

**Live strategy TBD.** Not exercised in the authoring sandbox.

CLI::

    python -m pipelines.fetchers.evalcommunity_map                 # live → fixture
    python -m pipelines.fetchers.evalcommunity_map --live          # force live
    python -m pipelines.fetchers.evalcommunity_map --from-fixture  # offline
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
    REPO_ROOT / "tests" / "fixtures" / "evalcommunity_map" / "map.html"
)


class EvalCommunityMapFetcher(BaseFetcher):
    source_id = "evalcommunity_map"
    base_url = (
        "https://academy.evalcommunity.com/"
        "global-ai-governance-map-140-institutions/"
    )
    required_selectors = ['class="ecom-institution"']

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
        cards = soup.find_all("article", class_="ecom-institution")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for card in cards:
            entry_id = (card.get("data-id") or "").strip()
            role = (card.get("data-role") or "").strip()
            region = (card.get("data-region") or "").strip()
            title_el = card.find(["h2", "h3"])
            name = title_el.get_text(strip=True) if title_el else ""
            link_el = card.find("a", class_="ecom-link")
            url = (link_el.get("href") if link_el else "") or ""
            country_el = card.find(class_="country")
            country = country_el.get_text(strip=True) if country_el else None
            focus_el = card.find(class_="focus")
            focus = focus_el.get_text(strip=True) if focus_el else None
            desc_el = card.find(class_="description")
            description = desc_el.get_text(strip=True) if desc_el else None
            if not (name and url):
                continue
            venues.append(
                RawVenue(
                    source_id=(
                        f"evalcommunity:{entry_id}" if entry_id
                        else f"evalcommunity:{url}"
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
                        "role": role,
                        "region": region,
                        "focus": focus,
                    },
                )
            )
        self._log.info(
            "parsed %d RawVenue records from EvalCommunity map (strategy=%s)",
            len(venues), strategy,
        )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.evalcommunity_map",
        description=(
            "EvalCommunity Global AI Governance Map discovery fetcher. "
            "On §12.7 probation; default: live → fixture fallback."
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
                    default=Path(".cache/evalcommunity_map"),
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
    log = logging.getLogger("fetcher.evalcommunity_map.cli")

    if args.fixture:
        fetcher = EvalCommunityMapFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = EvalCommunityMapFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = EvalCommunityMapFetcher(cache_dir=args.cache_dir)
    else:
        try:
            fetcher = EvalCommunityMapFetcher(cache_dir=args.cache_dir)
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
            fetcher = EvalCommunityMapFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

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
