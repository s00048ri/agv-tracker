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

**Live strategy: static HTTP.** Confirmed 2026-09-07 against a real
capture (`tests/fixtures/ai_deadlines/live/`): `div.ConfItem` occurs
195 times in the static response and 195 times in the rendered DOM,
so the page needs no browser. The Playwright fallback stays as a
safety net but is not on the expected path.

**Yield is low and that is the honest number.** The live listing
carries 192 conferences, of which exactly one — FAccT — passes the
governance filter. aideadlin.es indexes submission deadlines for
technical ML venues; the governance workshops this fetcher was
written for are largely not on it. It is kept because the cost is a
single request and FAccT-class venues do appear, not because it is
a productive discovery source.

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
# The captured live page, not a hand-written stand-in. The previous
# fixture was authored to fit the selectors below and asserted eight
# flagship governance workshops that aideadlin.es does not list.
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "ai_deadlines" / "live" / "static.html"
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


def _class_text(card, class_name: str) -> str | None:
    """Text of the first descendant carrying `class_name`, or None."""
    el = card.find(class_=class_name)
    return el.get_text(" ", strip=True) if el else None


class AIDeadlinesFetcher(BaseFetcher):
    source_id = "ai_deadlines"
    base_url = "https://aideadlin.es/"
    required_selectors = ["ConfItem"]

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
        """Parse the live aideadlin.es DOM.

        Structure (captured 2026-09-07):

            div#<id>.ConfItem.<TAG>-conf[.past]
              .conf-title       > a[href="/conference?id=<id>"]  title
              .conf-title-icon  > a[href=...]                    homepage
              .deadline-time                                     deadline
              .conf-date                                         event dates
              .conf-place                                        location
              .note                                              free text

        The subject tag lives in the element's own class list as
        `ML-conf`, `NLP-conf` and so on, not in child `.tag` nodes.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_="ConfItem")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for card in cards:
            entry_id = (card.get("id") or "").strip()
            classes = card.get("class") or []
            tags = [c[: -len("-conf")] for c in classes if c.endswith("-conf")]

            title_el = card.find(class_="conf-title")
            name = title_el.get_text(" ", strip=True) if title_el else ""

            # Prefer the conference's own site; the detail page is the
            # fallback, and is aideadlin.es itself — a discovery source,
            # never acceptable as a primary_reference_url (CLAUDE.md §5.2).
            url = ""
            icon_el = card.find(class_="conf-title-icon")
            if icon_el:
                link = icon_el.find("a", href=True)
                if link:
                    url = link["href"].strip()
            if not url and title_el:
                link = title_el.find("a", href=True)
                if link:
                    href = link["href"].strip()
                    url = href if href.startswith("http") else f"{self.base_url.rstrip('/')}{href}"

            deadline = _class_text(card, "deadline-time")
            event_date = _class_text(card, "conf-date")
            venue_place = _class_text(card, "conf-place")
            description = _class_text(card, "note")

            if not (name and url):
                continue

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
                        "venue": venue_place,
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
