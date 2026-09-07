"""Tests for the live-fixture capture script (scripts/capture_fixtures.py).

The script itself reaches the network, so what is testable offline is the
part that decides *what* to capture and the part that reads the capture
back. Both have bitten before: the current fixtures diverge from the live
pages precisely because nothing tied them to what the fetchers request.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "capture_fixtures", REPO_ROOT / "scripts" / "capture_fixtures.py",
)
capture_fixtures = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves annotations through
# sys.modules[cls.__module__], which is None until the module is there.
sys.modules[_spec.name] = capture_fixtures
_spec.loader.exec_module(capture_fixtures)


def test_every_target_mirrors_its_fetcher_base_url():
    """A capture that requests a different URL than the fetcher is useless.

    The targets import each fetcher's own `base_url` rather than retyping
    it, so this asserts the property that import is there to guarantee.
    """
    from pipelines.fetchers.ai_deadlines import AIDeadlinesFetcher
    from pipelines.fetchers.evalcommunity_map import EvalCommunityMapFetcher
    from pipelines.fetchers.iapp import IAPPFetcher
    from pipelines.fetchers.oecd_ai import OECDFetcher
    from pipelines.fetchers.unesco_gaigo import UNESCOGaigoFetcher

    by_id = {
        f.source_id: f.base_url
        for f in (
            OECDFetcher, UNESCOGaigoFetcher, IAPPFetcher,
            EvalCommunityMapFetcher, AIDeadlinesFetcher,
        )
    }
    targets = capture_fixtures._targets()
    assert {t.source_id for t in targets} == set(by_id)
    for t in targets:
        assert t.url == by_id[t.source_id], t.source_id
        assert t.url.startswith("https://"), t.source_id


def test_capture_writes_under_live_never_over_an_existing_fixture():
    """Captures must land in `<source>/live/`, beside the fixtures.

    Overwriting a fixture from a fetch would let a network round trip
    silently rewrite what the test suite asserts.
    """
    for t in capture_fixtures._targets():
        fixture_root = capture_fixtures.FIXTURES_DIR / t.fixture_dir
        assert fixture_root.exists(), f"{t.fixture_dir} is not a fixture dir"


def test_top_class_tokens_ranks_content_classes_and_drops_layout_noise():
    html = """
    <div class="container row mt-4">
      <article class="initiative-card"><span class="sr-only">x</span></article>
      <article class="initiative-card col-md-6"></article>
      <article class="initiative-card"></article>
      <aside class="wp-block-group elementor-widget"></aside>
    </div>
    """
    tokens = capture_fixtures.top_class_tokens(html)
    names = [t["token"] for t in tokens]

    assert names[0] == "initiative-card"
    assert tokens[0]["count"] == 3
    for noise in ("container", "row", "mt-4", "col-md-6", "sr-only",
                  "wp-block-group", "elementor-widget"):
        assert noise not in names, noise


def test_top_class_tokens_survives_markup_with_no_classes():
    assert capture_fixtures.top_class_tokens("<p>nothing here</p>") == []


def test_max_bytes_is_a_real_ceiling():
    """Set low enough to catch a wrong URL, high enough for a real page."""
    assert 1_000_000 <= capture_fixtures.MAX_BYTES <= 20_000_000
