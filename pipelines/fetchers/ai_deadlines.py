"""AI conference deadlines discovery fetcher (aideadlin.es).

Closes the "academic conference policy track" gap. Safety, ethics,
fairness, and trustworthy-ML workshops at NeurIPS / ICML / ICLR /
AAAI / ACL / IJCAI usually live first as an aideadlin.es entry
months before anyone builds a standalone governance conference
`standalone_governance_conference` or notes them in the Policy
Navigator. This fetcher converts each AI-governance-relevant
conference / workshop entry in aideadlin.es into a `RawVenue` that
the normalizer can promote to a `conference_policy_track` candidate.

Filter: a conference / workshop passes when its title **or**
tag list **or** description mentions at least one governance-layer
keyword (safety / ethics / fairness / trustworthy / alignment /
responsible / accountability / governance / policy). Purely
technical tracks without a policy layer (e.g. "Optimization",
"Reinforcement Learning Theory") are filtered out.

**Live strategy TBD.** aideadlin.es is a mostly-static Jekyll site
built from a YAML data file (the project is open source on GitHub);
static HTML is likely sufficient, but the BaseFetcher contract
falls back to Playwright automatically if the expected selectors
are missing.

CLI::

    python -m pipelines.fetchers.ai_deadlines                 # live → fixture
    python -m pipelines.fetchers.ai_deadlines --live          # force live
    python -m pipelines.fetchers.ai_deadlines --from-fixture  # offline
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "ai_deadlines" / "conferences.html"
)

# Governance-layer keywords. A conference/workshop passes the filter when
# the title, any tag, or the description hits this regex.
INCLUDE_REGEX = re.compile(
    r"(?i)\b("
    r"safety|ethics|fairness|trustworthy|alignment|"
    r"responsible|accountability|governance|policy|"
    r"privacy|interpretabilit\w*|interpretable|"
    r"explainabilit\w*|explainable|bias|"
    r"trustnlp|FAccT|AIES|EAAMO|FORC|ICAIL"
    r")\b"
)


class AIDeadlinesFetcher(BaseFetcher):
    source_id = "ai_deadlines"
    base_url = "https://aideadlin.es/"
    required_selectors = ['class="conf-entry"']

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
        cards = soup.find_all("article", class_="conf-entry")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for card in cards:
            entry_id = (card.get("data-id") or "").strip()
            title_el = card.find(["h2", "h3"])
            name = title_el.get_text(strip=True) if title_el else ""
            link_el = card.find("a", class_="conf-link")
            url = (link_el.get("href") if link_el else "") or ""
            deadline_el = card.find(class_="deadline")
            deadline = deadline_el.get_text(strip=True) if deadline_el else None
            date_el = card.find(class_="event-date")
            event_date = date_el.get_text(strip=True) if date_el else None
            desc_el = card.find(class_="description")
            description = desc_el.get_text(strip=True) if desc_el else None
            tag_els = card.find_all(class_="tag")
            tags = [t.get_text(strip=True) for t in tag_els]
            venue_el = card.find(class_="venue")
            venue = venue_el.get_text(strip=True) if venue_el else None

            if not (name and url):
                continue

            # Filter on title + tags + description.
            haystack = " ".join([name, *tags, description or ""])
            if not INCLUDE_REGEX.search(haystack):
                continue

            venues.append(
                RawVenue(
                    source_id=(
                        f"aideadlines:{entry_id}" if entry_id
                        else f"aideadlines:{url}"
                    ),
                    source_role="discovery",
                    source_registry=self.source_id,
                    name=name,
                    url=url,
                    description=description,
                    fetched_at=ts,
                    fetch_strategy=strategy,
                    raw_blob={
                        "entry_id": entry_id,
                        "tags": tags,
                        "deadline": deadline,
                        "event_date": event_date,
                        "venue": venue,
                    },
                )
            )
        self._log.info(
            "parsed %d RawVenue records from aideadlin.es (strategy=%s)",
            len(venues), strategy,
        )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.ai_deadlines",
        description=(
            "AI conference deadlines discovery fetcher. "
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
                    default=Path(".cache/ai_deadlines"),
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
    log = logging.getLogger("fetcher.ai_deadlines.cli")

    if args.fixture:
        fetcher = AIDeadlinesFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = AIDeadlinesFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = AIDeadlinesFetcher(cache_dir=args.cache_dir)
    else:
        try:
            fetcher = AIDeadlinesFetcher(cache_dir=args.cache_dir)
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
            fetcher = AIDeadlinesFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

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
