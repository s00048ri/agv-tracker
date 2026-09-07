"""Fetcher unit tests (CLAUDE.md §9 Task 4).

No live network: all tests run against the shipped fixture at
tests/fixtures/oecd_ai/dashboards.html or use monkeypatching to confirm
no httpx call fires.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pipelines.fetchers import BaseFetcher, RawVenue
from pipelines.fetchers.ai_deadlines import (
    DEFAULT_FIXTURE_PATH as AIDL_FIXTURE_PATH,
    INCLUDE_REGEX as AIDL_INCLUDE_REGEX,
    AIDeadlinesFetcher,
    main as aidl_main,
)
from pipelines.fetchers.base import (
    FETCH_STRATEGY_CACHE,
    FETCH_STRATEGY_FIXTURE,
    FETCH_STRATEGY_STATIC,
)
from pipelines.fetchers.evalcommunity_map import (
    DEFAULT_FIXTURE_PATH as ECOM_FIXTURE_PATH,
    EvalCommunityMapFetcher,
    main as ecom_main,
)
from pipelines.fetchers.government_pages import (
    DEFAULT_CONFIG_PATH as GOV_CONFIG_PATH,
    DEFAULT_FIXTURE_DIR as GOV_FIXTURE_DIR,
    GovernmentPagesFetcher,
    load_targets,
    main as gov_main,
)
from pipelines.fetchers.iapp import (
    DEFAULT_FIXTURE_PATH as IAPP_FIXTURE_PATH,
    IAPPFetcher,
    main as iapp_main,
)
from pipelines.fetchers.oecd_ai import DEFAULT_FIXTURE_PATH, OECDFetcher, main as oecd_main
from pipelines.fetchers.tech_policy_press import (
    DEFAULT_CONFIG_PATH as NEWS_CONFIG_PATH,
    DEFAULT_FIXTURE_DIR as NEWS_FIXTURE_DIR,
    DEFAULT_FIXTURE_PATH as TPP_FIXTURE_PATH,
    INCLUDE_REGEX as TPP_INCLUDE_REGEX,
    TechPolicyPressFetcher,
    load_feeds,
    main as tpp_main,
)
from pipelines.fetchers.unesco_gaigo import (
    DEFAULT_FIXTURE_PATH as UNESCO_FIXTURE_PATH,
    UNESCOGaigoFetcher,
    main as unesco_main,
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


# ---- robots.txt fetching must be bounded (regression: first live monthly-fetch) ----

class _FakeRobotsResp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def test_robots_fetch_never_uses_unbounded_robotparser_read(monkeypatch):
    """RobotFileParser.read() calls urlopen() with no timeout and can hang forever.

    The first live monthly-fetch run stalled ~30 min inside it and the job was
    killed, so _can_fetch must fetch robots.txt itself with a timeout.
    """
    import urllib.robotparser

    def boom(self):
        raise AssertionError("RobotFileParser.read() must not be used (unbounded)")

    monkeypatch.setattr(urllib.robotparser.RobotFileParser, "read", boom)

    seen: list[dict] = []

    def fake_get(url, **kw):
        seen.append({"url": url, **kw})
        return _FakeRobotsResp("User-agent: *\nAllow: /\n")

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    f = _DummyFetcher()
    assert f._can_fetch("https://example.invalid/page") is True
    assert len(seen) == 1
    assert seen[0]["url"] == "https://example.invalid/robots.txt"
    assert seen[0]["timeout"] == f.timeout_seconds


def test_robots_unreachable_defaults_to_permissive(monkeypatch):
    def hang(*a, **kw):
        raise TimeoutError("read timed out")

    import httpx
    monkeypatch.setattr(httpx, "get", hang)

    f = _DummyFetcher()
    assert f._can_fetch("https://example.invalid/page") is True


def test_robots_disallow_is_respected(monkeypatch):
    import httpx
    monkeypatch.setattr(
        httpx, "get",
        lambda url, **kw: _FakeRobotsResp("User-agent: *\nDisallow: /\n"),
    )

    f = _DummyFetcher()
    assert f._can_fetch("https://example.invalid/page") is False


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


def test_gov_fetcher_multilingual_country_coverage():
    """Non-English wave: JP/KR/FR/DE/CN must each emit at least one
    record from their fixture."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    countries = {v.country for v in fetcher.fetch()}
    for c in ("JP", "KR", "FR", "DE", "CN"):
        assert c in countries, f"missing non-English country: {c}"


def test_gov_fetcher_multilingual_regex_filters_noise():
    """Each non-English target's fixture has one off-topic control entry
    that the include_if_regex must drop. Together they prove the regex
    works against CJK + accented Latin scripts."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    names = {v.name for v in fetcher.fetch()}
    # One known-noise title per non-English fixture.
    for noise in (
        "日米首脳会談",                         # JP MOFA
        "工作機械輸出統計",                     # JP METI
        "5G 망 투자 동향",                      # KR MSIT
        "Vœux du Président",                    # FR Élysée
        "Energiepreis-Bericht Januar",          # DE BMWK
        "网络信息内容生态治理",                  # CN CAC
    ):
        for n in names:
            assert noise not in n, (
                f"non-English regex leaked off-topic entry: {n!r}"
            )


def test_gov_fetcher_emits_records_in_target_languages():
    """Confirm we are actually getting CJK / accented-Latin content out
    the other side, not silently degraded to empty strings."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    venues = fetcher.fetch()
    # Pick one known-keyword fragment per language and assert it
    # appears in at least one record's name.
    expectations = [
        ("jp_mofa_oecd_ai", "AI"),                 # ASCII inside JP content
        ("jp_meti_ai", "AI"),
        ("kr_msit_ai", "AI"),                       # ASCII inside KR content
        ("fr_elysee_ai", "IA"),                     # IA in FR
        ("de_bmwk_ai", "KI"),                       # KI in DE
        ("cn_cac_ai", "人工智能"),                  # CJK in CN
    ]
    for target_id, fragment in expectations:
        per_target_names = [
            v.name for v in venues
            if v.raw_blob["target_id"] == target_id
        ]
        assert any(fragment in n for n in per_target_names), (
            f"{target_id}: no record with '{fragment}' in name; "
            f"got {per_target_names!r}"
        )


def test_gov_fetcher_url_resolution_handles_relative_links_in_multilingual_fixtures():
    """Per-target hrefs may be absolute (most fixtures) or relative; either
    way, the fetcher must produce https:// URLs in RawVenue.url."""
    fetcher = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    )
    for v in fetcher.fetch():
        assert v.url.startswith("https://"), v


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


# ---- TechPolicyPressFetcher ----

def test_tpp_default_fixture_exists():
    assert TPP_FIXTURE_PATH.exists(), (
        f"default Tech Policy Press fixture missing at {TPP_FIXTURE_PATH}"
    )


def test_tpp_fetcher_fixture_returns_records():
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert len(venues) >= 20
    for v in venues:
        assert v.source_role == "discovery"
        assert v.source_registry == "tech_policy_press"
        # New multi-feed namespace: source_id is "<feed_id>:<idx>".
        # The legacy single-fixture path bind us to the tech_policy_press
        # feed only.
        assert v.source_id.startswith("tech_policy_press:")
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_tpp_fetcher_record_shape():
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    for v in venues:
        assert v.name, v
        assert v.url.startswith("https://"), v
        assert v.fetched_at, v
        # raw_blob carries RSS metadata
        assert "pubdate" in v.raw_blob
        assert "categories" in v.raw_blob


def test_tpp_fetcher_catches_iaseai_announcement():
    """The fixture includes an IASEAI announcement (the flagship example
    the user pointed to as currently uncovered)."""
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    names = [v.name for v in venues]
    assert any("IASEAI" in n for n in names), (
        "expected IASEAI announcement to pass the include regex"
    )


def test_tpp_fetcher_catches_ai_safety_connect():
    """Paris AI Action Summit side-event (AI Safety Connect)."""
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    names = [v.name for v in fetcher.fetch()]
    assert any("AI Safety Connect" in n for n in names)


def test_tpp_fetcher_filters_off_topic_noise():
    """Control items that are clearly non-AI must be dropped."""
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    names = {v.name for v in fetcher.fetch()}
    for noise in (
        "Broadband policy roundup",
        "Content moderation reform",
        "Privacy rights in the post-Schrems era",
        "Tech antitrust: the Google case",
    ):
        for n in names:
            assert noise not in n, f"noise leaked: {n}"


def test_tpp_include_regex_matches_expected_keywords():
    for kw in (
        "artificial intelligence", "AI governance", "AI safety",
        "AI Act", "frontier model", "generative AI", "AISI",
        "content provenance", "C2PA",
    ):
        assert TPP_INCLUDE_REGEX.search(f"Story about {kw} today"), kw


def test_tpp_include_regex_rejects_clearly_off_topic():
    for text in (
        "Broadband roundup, the quarter's cases",
        "Content moderation reform: lessons from Europe",
        "Tech antitrust: the Google case three years on",
    ):
        assert not TPP_INCLUDE_REGEX.search(text), text


def test_tpp_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.xml"
    empty.write_text(
        '<?xml version="1.0"?><rss><channel></channel></rss>',
        encoding="utf-8",
    )
    fetcher = TechPolicyPressFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_tpp_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == []


def test_tpp_rss_link_preprocessing_recovers_urls():
    """html.parser drops <link>...</link> text; the fetcher's
    preprocessing must restore it."""
    fetcher = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    for v in venues:
        assert v.url.startswith("https://www.techpolicy.press/"), v


def test_tpp_cli_from_fixture_outputs_jsonl(capsys):
    rc = tpp_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 20
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_registry"] == "tech_policy_press"
    assert "source_role=discovery" in captured.err


def test_tpp_source_ids_distinct_from_other_fetchers():
    tpp = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    gov = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    ).fetch()
    all_others = (
        {v.source_id for v in oecd}
        | {v.source_id for v in unesco}
        | {v.source_id for v in gov}
    )
    for v in tpp:
        assert v.source_id not in all_others, v


# ---- TechPolicyPressFetcher multi-feed wave ----


def test_news_feeds_config_loads_and_has_required_fields():
    feeds = load_feeds(NEWS_CONFIG_PATH)
    assert len(feeds) >= 4
    for f in feeds:
        for k in ("id", "name", "url"):
            assert k in f, (f.get("id"), k)


def test_news_feeds_config_target_ids_unique():
    from collections import Counter
    ids = [f["id"] for f in load_feeds(NEWS_CONFIG_PATH)]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    assert not dupes


def test_news_fixture_dir_has_one_xml_per_feed():
    feed_ids = {f["id"] for f in load_feeds(NEWS_CONFIG_PATH)}
    fixture_files = {p.stem for p in NEWS_FIXTURE_DIR.glob("*.xml")}
    missing = feed_ids - fixture_files
    assert not missing, (
        f"fixture XMLs missing for feeds: {sorted(missing)}"
    )


def test_news_multi_feed_fetch_emits_records_from_each_feed():
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    venues = fetcher.fetch()
    assert len(venues) >= 30  # all feeds combined
    feed_ids_hit = {v.raw_blob["feed_id"] for v in venues}
    config_ids = {f["id"] for f in load_feeds(NEWS_CONFIG_PATH)}
    assert feed_ids_hit == config_ids


def test_news_multi_feed_source_ids_namespaced_per_feed():
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    for v in fetcher.fetch():
        feed_id = v.raw_blob["feed_id"]
        assert v.source_id.startswith(f"{feed_id}:"), v


def test_news_multi_feed_only_flag_scopes_feeds():
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    venues = fetcher.fetch(only_ids={"cais_newsletter"})
    assert venues
    assert all(v.raw_blob["feed_id"] == "cais_newsletter" for v in venues)


def test_news_multi_feed_iaseai_caught():
    """IASEAI was the user-flagged blind spot; the AI Snake Oil feed
    article 'The IASEAI moment' must pass the include regex."""
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    names = [v.name for v in fetcher.fetch()]
    assert any("IASEAI" in n for n in names)


def test_news_multi_feed_ai_safety_connect_caught():
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    names = [v.name for v in fetcher.fetch()]
    assert any("AI Safety Connect" in n for n in names)


def test_news_multi_feed_filters_off_topic_substack_items():
    """Each non-TPP feed has at least one off-topic 'reading list' /
    'round-up' item that should be filtered."""
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=NEWS_FIXTURE_DIR,
    )
    names = [v.name for v in fetcher.fetch()]
    for noise in (
        "Reading list: Q1 2026",  # ai_snake_oil control
    ):
        for n in names:
            assert noise not in n, n


def test_news_multi_feed_cli_from_fixture(capsys):
    """The CLI's --from-fixture mode should drive all feeds, not just TPP."""
    rc = tpp_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 30
    feed_ids = {json.loads(ln)["raw_blob"]["feed_id"] for ln in lines}
    # Should span at least the tech_policy_press + cais + import_ai + snake_oil.
    assert "tech_policy_press" in feed_ids
    assert "cais_newsletter" in feed_ids
    assert "import_ai" in feed_ids
    assert "ai_snake_oil" in feed_ids


def test_news_multi_feed_per_feed_failure_isolated(monkeypatch, tmp_path):
    """If one feed's fixture is missing in fixture-dir mode, the run
    continues with the remaining feeds (same isolation contract as
    government_pages)."""
    fdir = tmp_path / "fixtures"
    fdir.mkdir()
    # Only ship one of four expected fixtures.
    (NEWS_FIXTURE_DIR / "tech_policy_press.xml").read_bytes()  # sanity
    (fdir / "tech_policy_press.xml").write_bytes(
        (NEWS_FIXTURE_DIR / "tech_policy_press.xml").read_bytes()
    )
    fetcher = TechPolicyPressFetcher(
        config_path=NEWS_CONFIG_PATH, fixture_dir=fdir,
    )
    venues = fetcher.fetch()
    assert venues  # tech_policy_press feed still produced records
    # Other feeds were skipped, not crashed.
    feed_ids = {v.raw_blob["feed_id"] for v in venues}
    assert feed_ids == {"tech_policy_press"}


# ---- IAPPFetcher ----

def test_iapp_default_fixture_exists():
    assert IAPP_FIXTURE_PATH.exists(), (
        f"default IAPP fixture missing at {IAPP_FIXTURE_PATH}"
    )


def test_iapp_fetcher_fixture_returns_records():
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert len(venues) >= 30  # 40 entries × some filtering latitude
    for v in venues:
        assert v.source_role == "discovery"
        assert v.source_registry == "iapp_ai_law_tracker"
        assert v.source_id.startswith("iapp:")
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_iapp_record_shape_has_regulatory_metadata():
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    venues = fetcher.fetch()
    for v in venues:
        assert v.name, v
        assert v.url.startswith("https://"), v
        rb = v.raw_blob
        # IAPP-specific raw_blob carries entry_kind, status, date, authority.
        assert "entry_kind" in rb
        assert "status" in rb
        assert "authority" in rb
        assert rb["entry_kind"] in ("statute", "regulation", "agency")


def test_iapp_fetcher_covers_expected_jurisdictions():
    """Regression: jurisdictions that the other four fetchers underserve."""
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    countries = {v.country for v in fetcher.fetch()}
    # Must span EU-level + global + a mix of non-OECD enforcement hubs.
    for c in ("EU", "International", "China", "Korea", "Brazil", "India",
              "Israel", "Saudi Arabia", "South Africa"):
        assert c in countries, f"{c} missing from IAPP fixture coverage"


def test_iapp_fetcher_covers_three_entry_kinds():
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    kinds = {v.raw_blob["entry_kind"] for v in fetcher.fetch()}
    assert kinds == {"statute", "regulation", "agency"}


def test_iapp_fetcher_catches_flagship_statutes():
    """Regression: the obvious anchor statutes must be present."""
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    names = {v.name for v in fetcher.fetch()}
    for flagship in (
        "EU Artificial Intelligence Act",
        "Council of Europe Framework Convention on AI",
        "China Interim Measures for Generative AI Services",
        "Korea AI Basic Act",
    ):
        assert any(flagship in n for n in names), flagship


def test_iapp_fetcher_surfaces_regulators_agencies():
    """The 'agency' kind is what promotes IAPP beyond a mere legislation
    index — it's where the tracker names new AGVs (national_regulator_intl
    candidates)."""
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    agencies = [v for v in fetcher.fetch()
                if v.raw_blob["entry_kind"] == "agency"]
    assert len(agencies) >= 10
    # A handful we know must be present.
    names = {v.name for v in agencies}
    for expected in (
        "EU AI Office",
        "UK AI Security Institute",
        "US AI Safety Institute",
        "Japan AI Safety Institute",
    ):
        assert any(expected in n for n in names), expected


def test_iapp_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body>no entries</body></html>", encoding="utf-8")
    fetcher = IAPPFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_iapp_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == []


def test_iapp_cli_from_fixture_outputs_jsonl(capsys):
    rc = iapp_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 30
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_registry"] == "iapp_ai_law_tracker"
    assert "source_role=discovery" in captured.err


def test_iapp_source_ids_distinct_from_other_fetchers():
    iapp = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    gov = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    ).fetch()
    tpp = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH).fetch()
    all_others = (
        {v.source_id for v in oecd}
        | {v.source_id for v in unesco}
        | {v.source_id for v in gov}
        | {v.source_id for v in tpp}
    )
    for v in iapp:
        assert v.source_id not in all_others, v


# ---- AIDeadlinesFetcher ----
#
# These run against `tests/fixtures/ai_deadlines/live/static.html`, which is
# the page aideadlin.es actually served on 2026-09-07. The fixture they used
# to run against was written by hand to fit the selectors, and asserted eight
# flagship governance workshops — FAccT, AIES, EAAMO, TrustNLP, "AI Safety",
# "Trustworthy", "Bias", "Accountability" — that the real listing does not
# carry. It listed 192 conferences, of which exactly one passes the filter.

def test_aidl_default_fixture_exists():
    assert AIDL_FIXTURE_PATH.exists()


def test_aidl_fixture_is_the_captured_live_page():
    """Guard against quietly reverting to a hand-written fixture."""
    assert AIDL_FIXTURE_PATH.parent.name == "live"


def test_aidl_selector_matches_every_entry_on_the_real_page():
    """The selector, not the filter: does the parser see the listing at all?

    192 `div.ConfItem` nodes is what the live page carries. The old
    selector, `article.conf-entry`, matched zero of them — which is the
    whole reason the discovery layer produced nothing.
    """
    from bs4 import BeautifulSoup

    html = AIDL_FIXTURE_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.find_all("div", class_="ConfItem")) == 192
    assert soup.find_all("article", class_="conf-entry") == []


def test_aidl_fetcher_fixture_returns_records():
    fetcher = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert venues, "the filter should still admit FAccT"
    for v in venues:
        assert v.source_role == "discovery"
        assert v.source_registry == "ai_deadlines"
        assert v.source_id.startswith("aideadlines:")
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_aidl_yield_on_the_real_page_is_one_governance_venue():
    """Record the real yield rather than an aspirational one.

    A drop to zero means the filter or the selectors broke; a jump means
    aideadlin.es started carrying governance venues, which is worth
    noticing rather than absorbing silently.
    """
    venues = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH).fetch()
    assert [v.name for v in venues] == ["FAccT 2022"]


def test_aidl_links_to_the_conference_not_to_aideadlines():
    """`url` must point at the venue's own site.

    aideadlin.es is a discovery source, and a discovery URL is never
    acceptable as a primary_reference_url (CLAUDE.md §5.2). The entry's
    own detail page would be exactly that.
    """
    for v in AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH).fetch():
        assert "aideadlin.es" not in v.url, v.url
        assert v.url.startswith("https://"), v.url


def test_aidl_raw_blob_carries_tags_and_dates():
    fetcher = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH)
    for v in fetcher.fetch():
        assert "tags" in v.raw_blob
        assert isinstance(v.raw_blob["tags"], list)
        assert "deadline" in v.raw_blob
        assert "event_date" in v.raw_blob
        # The subject tag lives in the ConfItem's own class list
        # (`ML-conf`), not in child `.tag` nodes.
        assert v.raw_blob["tags"] == ["ML"]
        assert v.raw_blob["event_date"] == "June 21-24, 2022."
        assert v.raw_blob["venue"].startswith("Seoul")


def test_aidl_filters_off_topic_technical_tracks():
    """Control: the 191 technical conferences must not pass the filter."""
    names = {v.name for v in AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH).fetch()}
    for noise in ("AISTATS", "NeurIPS", "CVPR", "ICRA", "ICASSP", "KDD"):
        for n in names:
            assert noise not in n, f"noise leaked: {n}"


def test_aidl_include_regex_matches_expected_keywords():
    for kw in (
        "safety", "ethics", "fairness", "trustworthy", "alignment",
        "responsible", "accountability", "governance", "policy",
        "privacy", "interpretability", "explainability", "bias",
        "FAccT", "AIES", "EAAMO", "FORC", "ICAIL",
    ):
        assert AIDL_INCLUDE_REGEX.search(f"ICML 2026 Workshop on {kw}"), kw


def test_aidl_include_regex_rejects_pure_technical():
    for text in (
        "Workshop on Reinforcement Learning Theory",
        "Workshop on Graph Neural Networks",
        "Competition on 3D scene reconstruction",
    ):
        assert not AIDL_INCLUDE_REGEX.search(text), text


def test_aidl_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body></body></html>", encoding="utf-8")
    fetcher = AIDeadlinesFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_aidl_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == []


def test_aidl_cli_from_fixture_outputs_jsonl(capsys):
    rc = aidl_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert lines
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_registry"] == "ai_deadlines"
    assert "source_role=discovery" in captured.err


def test_aidl_source_ids_distinct_from_other_fetchers():
    aidl = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    gov = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    ).fetch()
    tpp = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH).fetch()
    iapp = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH).fetch()
    all_others = (
        {v.source_id for v in oecd}
        | {v.source_id for v in unesco}
        | {v.source_id for v in gov}
        | {v.source_id for v in tpp}
        | {v.source_id for v in iapp}
    )
    for v in aidl:
        assert v.source_id not in all_others, v


# ---- EvalCommunityMapFetcher ----

def test_ecom_default_fixture_exists():
    assert ECOM_FIXTURE_PATH.exists()


def test_ecom_fetcher_fixture_returns_records():
    fetcher = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH)
    venues = fetcher.fetch()
    assert len(venues) >= 40
    for v in venues:
        assert v.source_role == "discovery"
        assert v.source_registry == "evalcommunity_map"
        assert v.source_id.startswith("evalcommunity:")
        assert v.fetch_strategy == FETCH_STRATEGY_FIXTURE


def test_ecom_raw_blob_carries_role_region_focus():
    fetcher = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH)
    for v in fetcher.fetch():
        assert "role" in v.raw_blob
        assert "region" in v.raw_blob
        assert "focus" in v.raw_blob


def test_ecom_fetcher_spans_all_regions():
    fetcher = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH)
    regions = {v.raw_blob["region"] for v in fetcher.fetch()}
    for r in ("NA", "EU", "LAC", "AF", "MENA", "Asia", "Pacific", "International"):
        assert r in regions, f"region {r} missing from fixture coverage"


def test_ecom_fetcher_role_taxonomy_diverse():
    fetcher = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH)
    roles = {v.raw_blob["role"] for v in fetcher.fetch()}
    # Expect at least regulator + thinktank + multistakeholder + industry
    for r in ("regulator", "thinktank", "multistakeholder", "industry_consortium",
              "academic", "ngo"):
        assert r in roles, f"role {r} missing from fixture"


def test_ecom_fetcher_fixture_mode_does_not_hit_network(monkeypatch):
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append((a, kw)))
    fetcher = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH)
    fetcher.fetch()
    assert calls == []


def test_ecom_fetcher_empty_fixture(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body></body></html>", encoding="utf-8")
    fetcher = EvalCommunityMapFetcher(fixture_path=empty)
    assert fetcher.fetch() == []


def test_ecom_cli_from_fixture_outputs_jsonl(capsys):
    rc = ecom_main(["--from-fixture", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    import json
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) >= 40
    for ln in lines:
        obj = json.loads(ln)
        assert obj["source_registry"] == "evalcommunity_map"
    assert "source_role=discovery" in captured.err


def test_ecom_source_ids_distinct_from_other_fetchers():
    ecom = EvalCommunityMapFetcher(fixture_path=ECOM_FIXTURE_PATH).fetch()
    oecd = OECDFetcher(fixture_path=DEFAULT_FIXTURE_PATH).fetch()
    unesco = UNESCOGaigoFetcher(fixture_path=UNESCO_FIXTURE_PATH).fetch()
    gov = GovernmentPagesFetcher(
        config_path=GOV_CONFIG_PATH, fixture_dir=GOV_FIXTURE_DIR,
    ).fetch()
    tpp = TechPolicyPressFetcher(fixture_path=TPP_FIXTURE_PATH).fetch()
    iapp = IAPPFetcher(fixture_path=IAPP_FIXTURE_PATH).fetch()
    aidl = AIDeadlinesFetcher(fixture_path=AIDL_FIXTURE_PATH).fetch()
    all_others = (
        {v.source_id for v in oecd}
        | {v.source_id for v in unesco}
        | {v.source_id for v in gov}
        | {v.source_id for v in tpp}
        | {v.source_id for v in iapp}
        | {v.source_id for v in aidl}
    )
    for v in ecom:
        assert v.source_id not in all_others, v


# ---- CDATA unwrapping (regression: AI Snake Oil titles) ----

def test_rss_preprocess_unwraps_cdata():
    from pipelines.fetchers.tech_policy_press import _parse_feed

    xml = (
        "<rss><channel>"
        "<item><title><![CDATA[Global AI Safety Forum launches]]></title>"
        "<link>https://example.invalid/post</link>"
        "<description><![CDATA[About AI governance]]></description></item>"
        "</channel></rss>"
    )
    out = _parse_feed(xml, "http_static", {"id": "ai_snake_oil", "name": "AI Snake Oil"})
    assert len(out) == 1
    assert out[0].name == "Global AI Safety Forum launches"
    assert "CDATA" not in out[0].name
    assert out[0].url == "https://example.invalid/post"
