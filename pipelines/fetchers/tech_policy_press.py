"""Tech Policy Press discovery fetcher (RSS / AI coverage).

News monitoring layer. Tech Policy Press publishes frequent reporting on
newly-formed AI governance bodies, associations, summit side events,
and national AI policy moves that neither OECD.AI Policy Navigator
nor UNESCO GAIGO consistently surface until much later. Concretely,
fetcher output includes article-level candidates such as "IASEAI
launches" or "AI Safety Connect opens at Paris AI Action Summit" —
the kind of venues that otherwise live only in news for months
before landing on an official registry.

**Article-level vs venue-level caveat.** Each RSS item is one article,
not one AGV. A reporter's article can mention a venue, cover a
summit, or be pure commentary. The fetcher emits one ``RawVenue`` per
AI-relevant article; the monthly PR reviewer is responsible for
deciding which ones become AGV rows and which are discarded (the
normalizer's mock classifier cannot distinguish "article announcing
a new venue" from "opinion piece mentioning an existing venue"). When
the classifier is switched to live Claude, a downstream entity-
extraction step could parse the article body to propose a specific
AGV name; that is a post-MVP refinement tracked in
``pipelines/README.md``.

Live strategy TBD (sandbox has no live test); the BaseFetcher
contract falls back to Playwright if the RSS feed response drops the
expected `<item>` structure.

CLI::

    python -m pipelines.fetchers.tech_policy_press                 # live → fixture
    python -m pipelines.fetchers.tech_policy_press --live          # force live
    python -m pipelines.fetchers.tech_policy_press --from-fixture  # offline
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# We deliberately use html.parser on XML; see _preprocess_rss().
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "tech_policy_press" / "feed.xml"
)

# Keep items whose title OR description mentions at least one AI-governance
# keyword. The regex is intentionally broad so that the tracker catches
# adjacent material (summits, declarations, safety institutes, evaluations)
# — the reviewer applies the narrower AGVO judgement on the monthly PR.
INCLUDE_REGEX = re.compile(
    r"(?i)\b("
    r"AI|artificial intelligence|AI governance|AI safety|AI ethics|"
    r"AI policy|safety institute|AISI|AI Office|AI Act|"
    r"frontier model|foundation model|generative AI|GenAI|"
    r"AI summit|AI declaration|AI code of conduct|AI coalition|"
    r"AI alliance|AI consortium|"
    r"content provenance|C2PA|content credentials|watermark"
    r")\b"
)


class TechPolicyPressFetcher(BaseFetcher):
    source_id = "tech_policy_press"
    base_url = "https://www.techpolicy.press/category/artificial-intelligence/feed/"
    # RSS feeds don't use CSS selectors the same way HTML does; the base
    # fetcher's selector check is a safety net that's unused here.
    required_selectors: list[str] = []

    def __init__(
        self,
        fixture_path: Path | None = None,
        cache_dir: Path | None = None,
    ):
        super().__init__(cache_dir=cache_dir)
        self.fixture_path = fixture_path

    def fetch(self) -> list[RawVenue]:
        if self.fixture_path is not None:
            xml = self.fixture_path.read_text(encoding="utf-8")
            strategy = FETCH_STRATEGY_FIXTURE
            self._log.info("fixture mode: %s", self.fixture_path)
        else:
            xml, strategy = self.fetch_html_with_fallback(self.base_url)
        return self._parse(xml, strategy)

    @staticmethod
    def _preprocess_rss(xml: str) -> str:
        """html.parser treats <link>…</link> as a void HTML element and
        drops its URL text content; RSS depends on that text. Rename
        occurrences of ``<link>text</link>`` to ``<rsslink>text</rsslink>``
        before parsing so we can read the URL via get_text() without
        needing an lxml dependency. The self-closing ``<link/>`` form
        is left untouched (it doesn't carry the URL we care about)."""
        import re as _re
        return _re.sub(r"<link>([^<]+)</link>", r"<rsslink>\1</rsslink>", xml)

    def _parse(self, xml: str, strategy: str) -> list[RawVenue]:
        # BS4's html.parser handles RSS with our <link>-rename
        # preprocessing, so no lxml dependency is needed.
        soup = BeautifulSoup(self._preprocess_rss(xml), "html.parser")
        items = soup.find_all("item")
        ts = self.now_iso()
        venues: list[RawVenue] = []
        for idx, item in enumerate(items):
            title_el = item.find("title")
            link_el = item.find("rsslink")
            desc_el = item.find("description")
            pubdate_el = item.find("pubdate") or item.find("pubDate")
            category_els = item.find_all("category")

            title = title_el.get_text(strip=True) if title_el else ""
            # Renamed RSS link tag; text content is the URL.
            url = link_el.get_text(strip=True) if link_el else ""
            description = desc_el.get_text(strip=True) if desc_el else None
            pubdate = pubdate_el.get_text(strip=True) if pubdate_el else None
            categories = [c.get_text(strip=True) for c in category_els]

            if not (title and url):
                continue

            # Relevance filter: title + description combined.
            haystack = title + " " + (description or "")
            if not INCLUDE_REGEX.search(haystack):
                continue

            venues.append(
                RawVenue(
                    source_id=f"techpolicypress:{idx:04d}",
                    source_role="discovery",
                    source_registry=self.source_id,
                    name=title,
                    url=url,
                    description=description,
                    fetched_at=ts,
                    fetch_strategy=strategy,
                    raw_blob={
                        "pubdate": pubdate,
                        "categories": categories,
                    },
                )
            )
        self._log.info(
            "parsed %d RawVenue records from Tech Policy Press (strategy=%s)",
            len(venues), strategy,
        )
        return venues


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.tech_policy_press",
        description=(
            "Tech Policy Press AI coverage discovery fetcher. "
            "Default: try live fetch, fall back to shipped fixture on failure."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; error out on any failure")
    g.add_argument("--fixture", type=Path,
                   help="use this RSS file instead of fetching")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_PATH.relative_to(REPO_ROOT)}")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path(".cache/tech_policy_press"),
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
    log = logging.getLogger("fetcher.tech_policy_press.cli")

    if args.fixture:
        fetcher = TechPolicyPressFetcher(fixture_path=args.fixture)
    elif args.from_fixture:
        fetcher = TechPolicyPressFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    elif args.live:
        fetcher = TechPolicyPressFetcher(cache_dir=args.cache_dir)
    else:
        try:
            fetcher = TechPolicyPressFetcher(cache_dir=args.cache_dir)
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
            fetcher = TechPolicyPressFetcher(fixture_path=DEFAULT_FIXTURE_PATH)

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
