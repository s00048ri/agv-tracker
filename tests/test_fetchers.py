"""Fetcher unit tests (CLAUDE.md §9 Task 4).

No live network: all tests run against the shipped fixture at
tests/fixtures/oecd_ai/dashboards.html or use monkeypatching to confirm
no httpx call fires.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from pipelines.fetchers import BaseFetcher, RawVenue
from pipelines.fetchers.base import (
    FETCH_STRATEGY_CACHE,
    FETCH_STRATEGY_FIXTURE,
    FETCH_STRATEGY_STATIC,
)
from pipelines.fetchers.oecd_ai import DEFAULT_FIXTURE_PATH, OECDFetcher, main as oecd_main
from pipelines.fetchers.unesco_gaigo import (
    DEFAULT_FIXTURE_PATH as UNESCO_FIXTURE_PATH,
    UNESCOGaigoFetcher,
    main as unesco_main,
)
from pipelines.fetchers.government_pages import (
    DEFAULT_CONFIG_PATH as GOV_CONFIG_PATH,
    DEFAULT_FIXTURE_DIR as GOV_FIXTURE_DIR,
    GovernmentPagesFetcher,
    load_targets,
    main as gov_main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- RawVenue ----

def test_rawvenue_defaults_and_as_dict():
    v = RawVenue(
        source_id="oecd.ai:1",
        source_role="discovery",
        source_registry="oecd_ai_navigator",
        name="Test",
        url="https://example/test",
    )
    assert v.country is None
    assert v.description is None
    assert v.raw_blob == {}
    d = v.as_dict()
    assert d["source_role"] == "discovery"
    assert d["raw_blob"] == {}


# ---- BaseFetcher helpers ----

class _DummyFetcher(BaseFetcher):
    source_id = "dummy"
    base_url = "https://example.invalid/"

    def fetch(self):
        return []


def test_selectors_present_helper():
    f = _DummyFetcher()
    assert f._selectors_present("<html>foo bar</html>", ["foo", "bar"])
    assert not f._selectors_present("<html>foo</html>", ["foo", "baz"])
    assert f._selectors_present("<html>anything</html>", [])


def test_throttle_enforces_minimum_interval(monkeypatch):
    f = _DummyFetcher()
    f.throttle_seconds = 0.05
    current = [1000.0]
    slept: list[float] = []

    def fake_monotonic():
        return current[0]

    def fake_sleep(s):
        slept.append(s)
        current[0] += s

    monkeypatch.setattr("pipelines.fetchers.base.time.monotonic", fake_monotonic)
    monkeypatch.setattr("pipelines.fetchers.base.time.sleep", fake_sleep)

    f._throttle()            # first call: no prior timestamp, no sleep
    current[0] += 0.01       # 10ms pass
    f._throttle()            # second call: should sleep 40ms
    assert slept and slept[0] == pytest.approx(0.04, rel=0.01)


def test_cache_roundtrip(tmp_path: Path):
    f = _DummyFetcher(cache_dir=tmp_path)
    url = "https://example.invalid/page"
    assert f._read_cache(url) is None
    f._write_cache(url, "<html>cached</html>")
    assert f._read_cache(url) == "<html>cached</html>"
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].suffix == ".html"


def test_cache_hit_skips_http(monkeypatch, tmp_path: Path):
    f = _DummyFetcher(cache_dir=tmp_path)
    f.respect_robots = False
    url = "https://example.invalid/listing"
    f._write_cache(url, '<html>class="initiative-card" present</html>')

    def boom(*a, **kw):
        raise AssertionError("httpx.get should not be called on cache hit")

    import httpx
    monkeypatch.setattr(httpx, "get", boom)

    html, strategy = f.fetch_html_with_fallback(
        url, required_selectors=['class="initiative-card"'],
    )
    assert strategy == FETCH_STRATEGY_CACHE
    assert "initiative-card" in html


def test_static_http_success(monkeypatch, tmp_path: Path):
    """When httpx returns HTML with all required selectors, no Playwright path."""
    f = _DummyFetcher(cache_dir=tmp_path)
    f.respect_robots = False

    class FakeResp:
        text = '<article class="initiative-card" data-id="1">x</article>'

        def raise_for_status(self):
            pass

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: FakeResp())

    def pw_called(*a, **kw):
        raise AssertionError("Playwright must not be invoked when static succeeds")

    monkeypatch.setattr(
        _DummyFetcher, "_fetch_with_playwright", pw_called,
    )

    html, strategy = f.fetch_html_with_fallback(
        "https://example.invalid/x",
        required_selectors=['class="initiative-card"'],
    )
    assert strategy == FETCH_STRATEGY_STATIC
    assert "initiative-card" in html


# ---- OECDFetcher ----

def test_default_fixture_exists():
    assert DEFAULT_FIXTURE_PATH.exists(), (
        f"default fixture missing at {DEFAULT_FIXTURE_PATH}"
    )


def test_oecd_fetcher_fixture_returns_at_least_50():
    fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert len(venues) >= 50, f"expected >=50 records, got {len(venues)}"


def test_oecd_fetcher_all_records_are_discovery():
    fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert venues, "no records parsed"
    for v in venues:
        assert v.source_role == "discovery", v
        assert v.source_registry == "oecd_ai_navigator"
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_oecd_fetcher_record_shape():
    fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    venues = fetcher.fetch()
    for v in venues:
        assert v.name, v
        assert v.url.startswith("https://"), v
        assert v.source_id.startswith("oecd.ai:"), v
        assert v.fetched_at, v


def test_oecd_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == [], "fixture-mode fetcher must not call httpx.get"


def test_oecd_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body>no cards</body></html>", encoding="utf-8")
    fetcher = OECDFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_oecd_cli_from_fixture_outputs_jsonl(capsys):
    rc = oecd_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 50
    # every line parses as JSON and carries source_role=discovery
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_role"] == "discovery"
    assert "source_role=discovery" in captured.err


# ---- UNESCOGaigoFetcher ----

def test_unesco_default_fixture_exists():
    assert UNESCO_FIXTURE_PATH.exists(), (
        f"default UNESCO fixture missing at {UNESCO_FIXTURE_PATH}"
    )


def test_unesco_fetcher_fixture_returns_at_least_50():
    fetcher = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert len(venues) >= 50, f"expected >=50 records, got {len(venues)}"


def test_unesco_fetcher_all_records_are_discovery():
    fetcher = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert venues
    for v in venues:
        assert v.source_role == "discovery", v
        assert v.source_registry == "unesco_gaigo"
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_unesco_fetcher_record_shape():
    fetcher = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH)
    venues = fetcher.fetch()
    for v in venues:
        assert v.name, v
        assert v.url.startswith("https://"), v
        assert v.source_id.startswith("unesco.gaigo:"), v
        assert v.fetched_at, v
        # raw_blob carries the UNESCO-specific entry_kind classification
        assert v.raw_blob.get("entry_kind") in (
            "country_profile", "ram_pilot", "regional_initiative",
        )


def test_unesco_fetcher_covers_non_oecd_regions():
    """Sanity check that the fixture (and therefore the fetcher) skews
    toward the global-south / non-OECD regions the Task 4 fetcher misses."""
    fetcher = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH)
    venues = fetcher.fetch()
    regions = {v.raw_blob.get("region") for v in venues}
    # At minimum AF, MENA, LAC, Asia, Pacific should all show up.
    for r in ("AF", "MENA", "LAC", "Asia", "Pacific"):
        assert r in regions, f"fixture missing region '{r}': {regions}"


def test_unesco_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == []


def test_unesco_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body>no cards</body></html>", encoding="utf-8")
    fetcher = UNESCOGaigoFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_unesco_cli_from_fixture_outputs_jsonl(capsys):
    rc = unesco_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 50
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_role"] == "discovery"
        assert obj["source_registry"] == "unesco_gaigo"
    assert "source_role=discovery" in captured.err


def test_unesco_fetcher_source_id_distinct_from_oecd():
    """Guard against the two fetchers' source_id namespaces colliding."""
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    u_ids = {v.source_id for v in unesco}
    o_ids = {v.source_id for v in oecd}
    assert not (u_ids & o_ids), "source_id collision between fetchers"


# ---- GovernmentPagesFetcher ----

def test_gov_config_loads_and_has_targets():
    targets = load_targets(GOV_CONFIG_PATH)
    assert len(targets) >= 5
    # Required schema fields per target.
    for t in targets:
        for k in ("id", "country", "language", "url",
                  "list_selector", "title_selector"):
            assert k in t, (t["id"], k)


def test_gov_config_target_ids_unique():
    from collections import Counter
    ids = [t["id"] for t in load_targets(GOV_CONFIG_PATH)]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    assert not dupes, dupes


def test_gov_fixture_dir_has_one_file_per_target():
    target_ids = {t["id"] for t in load_targets(GOV_CONFIG_PATH)}
    fixture_files = {p.stem for p in GOV_FIXTURE_DIR.glob("*.html")}
    missing = target_ids - fixture_files
    assert not missing, (
        f"fixture files missing for targets: {sorted(missing)}"
    )


def test_gov_fetcher_from_fixture_returns_records():
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch()
    assert len(venues) >= 20  # 6 targets × ~4 records average
    for v in venues:
        assert v.source_role == "discovery"
        assert v.source_registry == "government_pages"
        assert v.source_id.startswith("gov.")
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_gov_fetcher_covers_all_configured_targets():
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch()
    targets_hit = {v.raw_blob["target_id"] for v in venues}
    config_ids = {t["id"] for t in load_targets(GOV_CONFIG_PATH)}
    assert targets_hit == config_ids, (
        f"expected records from all {len(config_ids)} targets; got {len(targets_hit)}"
    )


def test_gov_fetcher_regex_filter_drops_non_ai_entries():
    """A UK entry with 'Health policy update' must NOT be emitted;
    the include_if_regex gates it out."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch()
    names = {v.name for v in venues}
    for v in venues:
        assert "Health policy update" not in v.name, v
    # Positive: a confidently-AI entry is present.
    assert any("AI Security Institute" in n for n in names)


def test_gov_fetcher_only_flag_scopes_targets():
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch(only_ids={"uk_dsit_ai_news"})
    assert venues
    target_ids = {v.raw_blob["target_id"] for v in venues}
    assert target_ids == {"uk_dsit_ai_news"}


def test_gov_fetcher_multi_country_coverage():
    """The fixture should cover GB/US/EU/SG/CA/AU — the six MVP countries."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    countries = {v.country for v in fetcher.fetch()}
    for c in ("GB", "US", "EU", "SG", "CA", "AU"):
        assert c in countries, f"missing country in fixture coverage: {c}"


def test_gov_fetcher_atom_feed_target_parses():
    """The UK target is an Atom feed; make sure it comes out non-empty."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch(only_ids={"uk_dsit_ai_news"})
    assert len(venues) >= 3, (
        f"expected multiple UK DSIT records, got {len(venues)}"
    )
    # Atom <link href="..."/> was parsed into the url field.
    for v in venues:
        assert v.url.startswith("https://"), v


def test_gov_cli_from_fixture_outputs_jsonl(capsys):
    rc = gov_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 20
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_registry"] == "government_pages"
    assert "source_role=discovery" in captured.err


def test_gov_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    fetcher.fetch()
    assert calls == [], "fixture-mode fetcher must not call httpx.get"


def test_gov_fetcher_source_ids_distinct_from_other_fetchers():
    gov = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    ).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    all_others = {v.source_id for v in oecd} | {v.source_id for v in unesco}
    for v in gov:
        assert v.source_id not in all_others, v
