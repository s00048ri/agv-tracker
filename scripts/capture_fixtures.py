#!/usr/bin/env python3
"""Capture real HTML from the discovery sources into tests/fixtures/.

Why this exists
---------------
On 2026-09-05 the discovery layer was found to be non-functional: five of
seven fetchers match nothing on their live targets. The cause was not
selector rot. The fixtures had been *authored to fit the selectors* rather
than captured from the sources — ``class="initiative-card"`` occurs 60
times in ``tests/fixtures/oecd_ai/dashboards.html`` and zero times on the
live OECD.AI dashboard. A green fetcher test therefore proved that a
parser handles its own invention, not that a source is covered.

Rebuilding the selectors needs the real markup, and the real markup needs
network access that neither the test suite (deliberately) nor a sandboxed
authoring session (structurally) has. So this script runs in CI, captures
what the sources actually serve, and commits it — after which selectors
can be written offline against bytes nobody made up.

What it captures
----------------
For each target, both halves of the story:

* ``static.html``   — exactly what ``httpx.get`` returns.
* ``rendered.html`` — the DOM after a headless browser runs the page's
  JavaScript.

The pair is the diagnosis. If a listing appears only in ``rendered.html``,
the source is a SPA and the fetcher must keep its Playwright path; if both
carry it, the static path is enough and the browser is dead weight.

``capture.json`` records url, timestamp, HTTP status, byte counts, SHA-256
of each artefact, and the most frequent ``class`` tokens in the rendered
DOM. That last field is the practical one: it is a first look at the real
selector vocabulary, and it is short enough to read in a CI log before the
captured pages have landed anywhere.

Probing for a URL that no longer exists
---------------------------------------
A capture answers "what does this page contain". When the page is gone —
oecd.ai's dashboard target returns 404 — the question is instead "where
did it move to", and guessing URLs one CI run at a time is slow and
mostly wrong. So `--probe` fetches candidates *and* prints the internal
links each one offers, which lets the site's own navigation answer the
question rather than a list of guesses. Nothing is written to disk: the
report goes to stdout, where a CI log can carry it back.

Usage
-----
    python scripts/capture_fixtures.py                 # every target
    python scripts/capture_fixtures.py --only oecd_ai_navigator
    python scripts/capture_fixtures.py --list
    python scripts/capture_fixtures.py --probe https://oecd.ai/
    python scripts/capture_fixtures.py --probe https://oecd.ai/ \
        --link-filter "dashboard|initiative"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipelines.fetchers.base import BaseFetcher  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# A page larger than this is refused rather than committed. Nothing in the
# discovery layer should be near it; hitting the cap means the target URL
# is wrong (a download, a media page) and the capture is worth failing on.
MAX_BYTES = 5 * 1024 * 1024

# Class tokens that describe layout or a CSS framework rather than the
# content, and so tell us nothing about where the listing lives.
BORING_CLASS_RE = re.compile(
    r"^(?:"
    r"[a-z]{1,3}|"                       # u, sm, md …
    r"(?:col|row|grid|flex|container|wrapper|inner|outer|clearfix)[-_a-z0-9]*|"
    r"(?:mt|mb|ml|mr|pt|pb|pl|pr|px|py|mx|my|p|m|w|h|text|bg|border)-[-_a-z0-9]+|"
    r"(?:sr-only|hidden|visually-hidden|screen-reader-text)|"
    r"(?:elementor|wp-|jetpack|has-|is-|js-)[-_a-z0-9]*"
    r")$"
)


@dataclass(frozen=True)
class Target:
    """One page to capture, named by the fetcher that consumes it."""

    source_id: str
    url: str
    fixture_dir: str  # under tests/fixtures/
    note: str = ""


# Targets mirror each fetcher's own `base_url`, imported rather than
# retyped so the capture cannot drift from what the fetcher requests.
def _targets() -> list[Target]:
    from pipelines.fetchers.ai_deadlines import AIDeadlinesFetcher
    from pipelines.fetchers.evalcommunity_map import EvalCommunityMapFetcher
    from pipelines.fetchers.iapp import IAPPFetcher
    from pipelines.fetchers.oecd_ai import OECDFetcher
    from pipelines.fetchers.unesco_gaigo import UNESCOGaigoFetcher

    return [
        Target(
            OECDFetcher.source_id, OECDFetcher.base_url, "oecd_ai",
            "policy-initiative listing; 60 invented initiative-card nodes today",
        ),
        Target(
            UNESCOGaigoFetcher.source_id, UNESCOGaigoFetcher.base_url, "unesco_gaigo",
            "GAIGO landing page; gaigo-entry appears 0 times live",
        ),
        Target(
            IAPPFetcher.source_id, IAPPFetcher.base_url, "iapp",
            "global AI legislation tracker; iapp-law-entry appears 0 times live",
        ),
        Target(
            EvalCommunityMapFetcher.source_id, EvalCommunityMapFetcher.base_url,
            "evalcommunity_map", "140-institution map; source is on probation (§12 #7)",
        ),
        Target(
            AIDeadlinesFetcher.source_id, AIDeadlinesFetcher.base_url, "ai_deadlines",
            "conference deadlines; upstream also publishes a machine-readable feed",
        ),
    ]


def parse_capture_url(spec: str) -> Target:
    """Turn `subdir/under/fixtures=https://...` into a Target.

    A probe says which URL is worth capturing; this captures it without
    first rewriting a fetcher's `base_url` to point somewhere nobody has
    inspected yet. The destination is confined to tests/fixtures/ — a
    capture spec is an argument, and arguments should not be able to
    write outside the tree they name.
    """
    directory, sep, url = spec.partition("=")
    if not sep or not directory.strip() or not url.strip():
        raise ValueError(f"expected DIR=URL, got {spec!r}")
    directory, url = directory.strip(), url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"not an http(s) URL: {url!r}")

    resolved = (FIXTURES_DIR / directory).resolve()
    if not resolved.is_relative_to(FIXTURES_DIR.resolve()):
        raise ValueError(f"destination escapes tests/fixtures/: {directory!r}")

    return Target(
        source_id=f"ad-hoc:{directory}",
        url=url,
        fixture_dir=directory,
        note="ad-hoc capture (--capture-url)",
    )


class _Capture(BaseFetcher):
    """Concrete BaseFetcher used only for its fetch helpers.

    `required_selectors` stays empty on purpose: we are capturing a page
    precisely because we do not yet know what to look for in it, and a
    non-empty list would make the static path "fail" into Playwright on
    markup that is in fact complete.
    """

    required_selectors: list[str] = []

    def __init__(self, source_id: str, base_url: str) -> None:
        self.source_id = source_id
        self.base_url = base_url
        super().__init__(cache_dir=None)

    def fetch(self):  # pragma: no cover - never called
        raise NotImplementedError("capture-only fetcher")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def top_class_tokens(html: str, limit: int = 25) -> list[dict]:
    """Most frequent content-bearing `class` tokens, commonest first.

    A first read of the real selector vocabulary. Layout and framework
    classes are filtered out (see BORING_CLASS_RE) because they are the
    same on every site and drown out the handful of tokens that actually
    name the listing.
    """
    tokens: Counter[str] = Counter()
    for attr in re.findall(r'class=["\']([^"\']+)["\']', html):
        for token in attr.split():
            token = token.strip()
            if len(token) < 3 or BORING_CLASS_RE.match(token.lower()):
                continue
            tokens[token] += 1
    return [{"token": t, "count": n} for t, n in tokens.most_common(limit)]


def capture(target: Target) -> dict:
    """Capture one target. Returns the manifest entry; never raises."""
    out_dir = FIXTURES_DIR / target.fixture_dir / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = _Capture(target.source_id, target.url)

    entry: dict = {
        "source_id": target.source_id,
        "url": target.url,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": target.note,
    }

    # --- static ---
    try:
        import httpx

        resp = httpx.get(
            target.url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "agv-tracker-fixture-capture"},
        )
        entry["static_status"] = resp.status_code
        html = resp.text
        if len(html.encode("utf-8")) > MAX_BYTES:
            entry["static_error"] = f"exceeds MAX_BYTES ({len(html)} chars)"
        else:
            (out_dir / "static.html").write_text(html, encoding="utf-8")
            entry["static_bytes"] = len(html.encode("utf-8"))
            entry["static_sha256"] = _sha256(html)
    except Exception as e:  # noqa: BLE001 — a dead source is a result, not a crash
        entry["static_error"] = f"{type(e).__name__}: {e}"

    # --- rendered ---
    try:
        html = fetcher._fetch_with_playwright(target.url, timeout=45)
        if len(html.encode("utf-8")) > MAX_BYTES:
            entry["rendered_error"] = f"exceeds MAX_BYTES ({len(html)} chars)"
        else:
            (out_dir / "rendered.html").write_text(html, encoding="utf-8")
            entry["rendered_bytes"] = len(html.encode("utf-8"))
            entry["rendered_sha256"] = _sha256(html)
            entry["top_class_tokens"] = top_class_tokens(html)
    except Exception as e:  # noqa: BLE001
        entry["rendered_error"] = f"{type(e).__name__}: {e}"

    # The comparison this whole script exists to make.
    if "static_sha256" in entry and "rendered_sha256" in entry:
        entry["javascript_changes_dom"] = (
            entry["static_sha256"] != entry["rendered_sha256"]
        )

    (out_dir / "capture.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return entry


# Default interest filter for --probe: the vocabulary a listing of policy
# initiatives is likely to use somewhere in its path or link text.
DEFAULT_LINK_FILTER = r"dashboard|initiativ|polic|database|observator|search|catalog"


def internal_links(html: str, base_url: str, pattern: str) -> list[dict]:
    """Same-site links whose href or anchor text matches `pattern`.

    Deduplicated by href and capped, because a site's chrome repeats the
    same nav on every page and the useful signal is the set of distinct
    destinations, not their frequency.
    """
    from urllib.parse import urljoin, urlparse

    host = urlparse(base_url).netloc
    rx = re.compile(pattern, re.I)
    seen: dict[str, str] = {}
    for href, text in re.findall(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S,
    ):
        label = re.sub(r"<[^>]+>", " ", text)
        label = re.sub(r"\s+", " ", label).strip()
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != host:
            continue
        if not (rx.search(absolute) or rx.search(label)):
            continue
        seen.setdefault(absolute.split("#")[0], label)
    return [{"url": u, "text": t} for u, t in sorted(seen.items())]


def probe(url: str, link_filter: str) -> dict:
    """Fetch one candidate URL and describe what came back."""
    import httpx

    result: dict = {"url": url}
    try:
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "agv-tracker-fixture-capture"},
        )
    except Exception as e:  # noqa: BLE001 — an unreachable candidate is an answer
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    html = resp.text
    result["status"] = resp.status_code
    result["final_url"] = str(resp.url)
    result["bytes"] = len(html.encode("utf-8"))
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    result["title"] = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
    result["top_class_tokens"] = top_class_tokens(html, limit=12)
    result["links"] = internal_links(html, str(resp.url), link_filter)
    return result


def _report_probe(result: dict) -> None:
    print(f"\n=== {result['url']} ===")
    if "error" in result:
        print(f"  FAILED — {result['error']}")
        return
    print(f"  status     {result['status']}  ({result['bytes']:,} bytes)")
    if result["final_url"] != result["url"]:
        print(f"  redirected {result['final_url']}")
    print(f"  title      {result['title'][:100]!r}")
    tokens = result.get("top_class_tokens") or []
    if tokens:
        print("  classes    " + ", ".join(
            f"{t['token']}x{t['count']}" for t in tokens[:10]))
    links = result.get("links") or []
    print(f"  matching internal links: {len(links)}")
    for link in links[:40]:
        print(f"    {link['url']}\n        {link['text'][:80]!r}")


def _report(entry: dict) -> None:
    print(f"\n=== {entry['source_id']} ===")
    print(f"  url        {entry['url']}")
    for half in ("static", "rendered"):
        if f"{half}_error" in entry:
            print(f"  {half:<10} FAILED — {entry[f'{half}_error']}")
        else:
            size = entry.get(f"{half}_bytes", 0)
            status = entry.get("static_status", "-") if half == "static" else "-"
            print(f"  {half:<10} {size:>9,} bytes  (http {status})")
    if "javascript_changes_dom" in entry:
        print(f"  js alters DOM: {entry['javascript_changes_dom']}")
    tokens = entry.get("top_class_tokens") or []
    if tokens:
        joined = ", ".join(f"{t['token']}×{t['count']}" for t in tokens[:12])
        print(f"  top classes: {joined}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", help="capture just this source_id")
    ap.add_argument("--list", action="store_true", help="list targets and exit")
    ap.add_argument(
        "--probe", action="append",
        help="fetch this URL and report status, title and internal links "
             "instead of capturing (repeatable; writes nothing to disk)",
    )
    ap.add_argument(
        "--capture-url", action="append", metavar="DIR=URL",
        help="capture an arbitrary URL into tests/fixtures/DIR/live/ "
             "(repeatable; for pages a probe has just identified)",
    )
    ap.add_argument(
        "--link-filter", default=DEFAULT_LINK_FILTER,
        help="regex a link's href or text must match to be reported",
    )
    args = ap.parse_args(argv)

    if args.probe:
        results = [probe(u, args.link_filter) for u in args.probe]
        for result in results:
            _report_probe(result)
        reached = sum(1 for r in results if "error" not in r)
        print(f"\nprobed {reached}/{len(results)} URLs")
        return 0 if reached else 1

    if args.capture_url:
        try:
            targets = [parse_capture_url(spec) for spec in args.capture_url]
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        entries = [capture(t) for t in targets]
        for entry in entries:
            _report(entry)
        captured = sum(
            1 for e in entries if "static_sha256" in e or "rendered_sha256" in e
        )
        print(f"\ncaptured {captured}/{len(entries)} URLs")
        return 0 if captured else 1

    targets = _targets()
    if args.list:
        for t in targets:
            print(f"{t.source_id:<24} {t.url}")
        return 0
    if args.only:
        wanted = set(args.only)
        targets = [t for t in targets if t.source_id in wanted]
        if not targets:
            print(f"no target matches {sorted(wanted)}", file=sys.stderr)
            return 2

    entries = [capture(t) for t in targets]
    for entry in entries:
        _report(entry)

    captured = sum(
        1 for e in entries
        if "static_sha256" in e or "rendered_sha256" in e
    )
    print(f"\ncaptured {captured}/{len(entries)} targets")
    # A total failure is worth a nonzero exit; partial success is normal,
    # since any one source can be down or blocking the runner.
    return 0 if captured else 1


if __name__ == "__main__":
    raise SystemExit(main())
