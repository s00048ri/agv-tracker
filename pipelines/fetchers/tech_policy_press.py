"""Multi-feed AI-policy news monitor.

Originally Tech Policy Press only; extended to a config-driven
multi-feed fetcher that drives N RSS sources from
``sources/news_feeds.yml``. The module name is kept for backwards
compatibility with ``sources/registry.yml`` (the Task-1 entry
pre-dated the multi-feed wave).

Design parallels ``pipelines/fetchers/government_pages.py``: one
generic module + one YAML config of targets. Adding a feed is a
YAML edit; no Python change. Each RSS feed is fetched independently
through the ``BaseFetcher`` contract (static HTTP → Playwright
fallback + robots.txt + 1 req/sec throttle + on-disk cache).

Filter: each item passes when its title or description matches the
module-level ``INCLUDE_REGEX`` (AI / AISI / AI Office / AI Act /
frontier model / generative AI / content provenance / C2PA /
watermark / coalition / consortium / alliance / summit /
declaration). Per-feed override available via the YAML's
``include_regex`` field.

**Article-level vs venue-level caveat.** Each RSS item is one
article, not one AGV. The fetcher emits one ``RawVenue`` per
AI-relevant article; the monthly PR reviewer decides which
articles correspond to a new AGV. The module docstring spells
this out, and cross-references the roadmap in
``pipelines/README.md`` for future downstream entity extraction.

CLI::

    python -m pipelines.fetchers.tech_policy_press                 # live → fixture
    python -m pipelines.fetchers.tech_policy_press --live          # force live
    python -m pipelines.fetchers.tech_policy_press --from-fixture  # offline
    python -m pipelines.fetchers.tech_policy_press --only tech_policy_press,cais_newsletter
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import warnings
from pathlib import Path

import yaml
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..venue_names import unwrap_cdata
from .base import FETCH_STRATEGY_FIXTURE, BaseFetcher, RawVenue

# We deliberately use html.parser on XML; see _preprocess_rss().
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "sources" / "news_feeds.yml"
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "tech_policy_press"

log = logging.getLogger("fetcher.tech_policy_press")

# Default relevance filter; per-feed YAML may override via `include_regex`.
INCLUDE_REGEX = re.compile(
    r"(?i)\b("
    r"AI|artificial intelligence|AI governance|AI safety|AI ethics|"
    r"AI policy|safety institute|AISI|AI Office|AI Act|"
    r"frontier model|foundation model|generative AI|GenAI|"
    r"AI summit|AI declaration|AI code of conduct|AI coalition|"
    r"AI alliance|AI consortium|"
    r"IASEAI|AI Safety Connect|"           # named venues from §roadmap
    r"AI Safety Asia|AISA|"
    r"FAccT|AIES|EAAMO|FORC|"               # standalone-conference acronyms
    r"content provenance|C2PA|content credentials|watermark"
    r")\b"
)


def load_feeds(path: Path | None = None) -> list[dict]:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return list(data.get("feeds", []))


class _PerFeedFetcher(BaseFetcher):
    """One BaseFetcher subclass per YAML feed entry."""

    required_selectors: list[str] = []

    def __init__(self, *, feed: dict, cache_dir: Path | None = None):
        self.source_id = feed["id"]
        self.base_url = feed["url"]
        super().__init__(cache_dir=cache_dir)
        self.feed = feed

    def fetch(self) -> list[RawVenue]:
        xml, strategy = self.fetch_html_with_fallback(self.base_url)
        return _parse_feed(xml, strategy, self.feed)


def _preprocess_rss(xml: str) -> str:
    """html.parser drops <link>...</link> text; rename to <rsslink> so the
    URL survives (no lxml dependency). Self-closing <link/> is left alone.

    Also unwraps CDATA sections: html.parser keeps their markers as literal
    text, so a feed that wraps its titles (AI Snake Oil does) would otherwise
    yield names like "<![CDATA[Could AI slow science?]]>".
    """
    xml = unwrap_cdata(xml)
    return re.sub(r"<link>([^<]+)</link>", r"<rsslink>\1</rsslink>", xml)


def _parse_feed(xml: str, strategy: str, feed: dict) -> list[RawVenue]:
    """Apply per-feed selectors + relevance regex to fetched RSS body."""
    soup = BeautifulSoup(_preprocess_rss(xml), "html.parser")
    items = soup.find_all("item")

    custom = feed.get("include_regex")
    if custom:
        try:
            pattern = re.compile(custom, re.IGNORECASE)
        except re.error:
            log.warning(
                "feed %s: invalid include_regex %r; using default",
                feed["id"], custom,
            )
            pattern = INCLUDE_REGEX
    else:
        pattern = INCLUDE_REGEX

    feed_id = feed["id"]
    ts = BaseFetcher.now_iso()
    out: list[RawVenue] = []
    for idx, item in enumerate(items):
        title_el = item.find("title")
        link_el = item.find("rsslink")
        desc_el = item.find("description")
        pubdate_el = item.find("pubdate") or item.find("pubDate")
        category_els = item.find_all("category")

        title = title_el.get_text(strip=True) if title_el else ""
        url = link_el.get_text(strip=True) if link_el else ""
        description = desc_el.get_text(strip=True) if desc_el else None
        pubdate = pubdate_el.get_text(strip=True) if pubdate_el else None
        categories = [c.get_text(strip=True) for c in category_els]

        if not (title and url):
            continue

        haystack = title + " " + (description or "")
        if not pattern.search(haystack):
            continue

        out.append(
            RawVenue(
                source_id=f"{feed_id}:{idx:04d}",
                source_role="discovery",
                source_registry="tech_policy_press",
                name=title,
                url=url,
                description=description,
                fetched_at=ts,
                fetch_strategy=strategy,
                raw_blob={
                    "feed_id": feed_id,
                    "feed_name": feed.get("name", ""),
                    "pubdate": pubdate,
                    "categories": categories,
                },
            )
        )
    return out


class TechPolicyPressFetcher:
    """Orchestrator over N RSS feeds.

    Name kept historical (matches sources/registry.yml id); function is
    a generic news monitor.
    """

    source_id = "tech_policy_press"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        feeds: list[dict] | None = None,
        fixture_dir: Path | None = None,
        cache_dir: Path | None = None,
        # Backwards-compat: callers in tests may still pass a single
        # `fixture_path` pointing at the original feed.xml. We treat
        # that as the tech_policy_press feed only.
        fixture_path: Path | None = None,
    ):
        if feeds is not None:
            self.feeds = list(feeds)
        else:
            self.feeds = load_feeds(config_path)
        if fixture_path is not None and fixture_dir is None:
            self._legacy_fixture_path = fixture_path
            self.fixture_dir = None
        else:
            self._legacy_fixture_path = None
            self.fixture_dir = Path(fixture_dir) if fixture_dir else None
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def select(self, only_ids: set[str] | None) -> list[dict]:
        if not only_ids:
            return list(self.feeds)
        return [f for f in self.feeds if f["id"] in only_ids]

    def fetch(self, *, only_ids: set[str] | None = None) -> list[RawVenue]:
        out: list[RawVenue] = []
        feeds = self.select(only_ids)

        # Backwards-compat path: if a caller passed a single fixture_path,
        # bind it to the tech_policy_press feed and ignore the rest.
        if self._legacy_fixture_path is not None:
            tpp_feed = next(
                (f for f in feeds if f["id"] == "tech_policy_press"), None,
            )
            if tpp_feed is None:
                return out
            xml = self._legacy_fixture_path.read_text(encoding="utf-8")
            return _parse_feed(xml, FETCH_STRATEGY_FIXTURE, tpp_feed)

        for feed in feeds:
            if self.fixture_dir is not None:
                fixture = self.fixture_dir / f"{feed['id']}.xml"
                if not fixture.exists():
                    log.warning(
                        "feed %s: fixture missing at %s; skipping in fixture mode",
                        feed["id"], fixture,
                    )
                    continue
                xml = fixture.read_text(encoding="utf-8")
                out.extend(_parse_feed(xml, FETCH_STRATEGY_FIXTURE, feed))
                continue

            sub = _PerFeedFetcher(
                feed=feed,
                cache_dir=(
                    self.cache_dir / feed["id"] if self.cache_dir else None
                ),
            )
            try:
                out.extend(sub.fetch())
            except Exception as e:  # noqa: BLE001 — keep other feeds going
                log.warning(
                    "feed %s failed: %s; continuing with remaining feeds",
                    feed["id"], e,
                )
        return out


# ---- CLI ----

# Backwards-compat alias used by older tests / docs.
DEFAULT_FIXTURE_PATH = DEFAULT_FIXTURE_DIR / "tech_policy_press.xml"


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.fetchers.tech_policy_press",
        description=(
            "Multi-feed AI-policy news monitor. "
            "Default: try live fetch, fall back to shipped fixture on failure."
        ),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true",
                   help="force live fetch; per-feed failures are isolated, the run continues")
    g.add_argument("--fixture-dir", type=Path,
                   help="use fixture XML files from this directory")
    g.add_argument("--from-fixture", action="store_true",
                   help=f"shortcut: use {DEFAULT_FIXTURE_DIR.relative_to(REPO_ROOT)}")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    ap.add_argument("--cache-dir", type=Path,
                    default=Path(".cache/tech_policy_press"))
    ap.add_argument("--only", type=str,
                    help="comma-separated feed ids to run (defaults to all)")
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
        {f.strip() for f in args.only.split(",") if f.strip()}
        if args.only else None
    )

    if args.fixture_dir:
        fetcher = TechPolicyPressFetcher(
            config_path=args.config, fixture_dir=args.fixture_dir,
        )
    elif args.from_fixture:
        fetcher = TechPolicyPressFetcher(
            config_path=args.config, fixture_dir=DEFAULT_FIXTURE_DIR,
        )
    elif args.live:
        fetcher = TechPolicyPressFetcher(
            config_path=args.config, cache_dir=args.cache_dir,
        )
    else:
        try:
            fetcher = TechPolicyPressFetcher(
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
            log.warning(
                "live fetch returned 0 records; falling back to shipped fixtures",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("live fetch failed (%s); falling back to fixtures", e)
        fetcher = TechPolicyPressFetcher(
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
