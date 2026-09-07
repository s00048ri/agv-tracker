"""Normalizer unit tests (CLAUDE.md §9 Task 6 step 1)."""
from __future__ import annotations

from pipelines.classify import Classifier, mock_llm_call
from pipelines.normalize import (
    Normalizer,
    slugify,
    verification_url_for_entity_type,
)


def _classifier():
    return Classifier(cache_dir=None, llm_call=mock_llm_call, budget_guard=None)


def _registry():
    return [
        {
            "id": "oecd_ai_official",
            "name": "OECD AI official",
            "url": "https://oecd.ai/en/ai-principles",
            "role": "verification",
            "entity_types_covered": ["igo_initiative"],
        },
        {
            "id": "iso_iec_sc42",
            "name": "ISO/IEC SC 42",
            "url": "https://www.iso.org/committee/6794475.html",
            "role": "verification",
            "entity_types_covered": ["standards_body_wg"],
        },
        {
            "id": "oecd_ai_navigator",
            "name": "OECD.AI nav (discovery)",
            "url": "https://oecd.ai/",
            "role": "discovery",
            "entity_types_covered": ["igo_initiative"],
        },
    ]


def test_slugify_basic():
    assert slugify("UK AI Safety Institute") == "uk_ai_safety_institute"
    assert slugify("ISO/IEC JTC 1/SC 42") == "iso_iec_jtc_1_sc_42"
    assert slugify("  ") == "unknown"


def test_verification_lookup_prefers_verification_role():
    reg = _registry()
    assert (
        verification_url_for_entity_type(reg, "igo_initiative")
        == "https://oecd.ai/en/ai-principles"
    )
    assert (
        verification_url_for_entity_type(reg, "standards_body_wg")
        == "https://www.iso.org/committee/6794475.html"
    )
    assert verification_url_for_entity_type(reg, "nonexistent") is None


def test_verification_lookup_ignores_discovery():
    reg = [
        {
            "id": "x", "url": "https://example/discovery/", "role": "discovery",
            "entity_types_covered": ["igo_initiative"],
        }
    ]
    assert verification_url_for_entity_type(reg, "igo_initiative") is None


def test_normalize_emits_candidate_and_evidence():
    rec = {
        "source_id": "oecd.ai:1",
        "source_registry": "oecd_ai_navigator",
        "name": "OECD AI Principles",
        "description": (
            "Non-binding principles adopted by the OECD Council; initiative within "
            "the OECD intergovernmental organization; global scope; OECD secretariat leads."
        ),
        "url": "https://oecd.ai/en/ai-principles",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([rec])
    assert len(out) == 1
    entry = out[0]
    agv_row = entry["agv_row"]
    assert agv_row["agv_id"] == "oecd_ai_principles"
    assert agv_row["entity_type"] == "igo_initiative"
    assert agv_row["primary_reference_url"] == "https://oecd.ai/en/ai-principles"
    # Candidate has explicit candidate-notes flag
    assert "candidate" in agv_row["notes"].lower()
    # Evidence rows: 6 dimensions' classification results
    assert len(entry["evidence_rows"]) == 6
    for ev in entry["evidence_rows"]:
        assert ev["source_type"] == "llm_classification"
        assert ev["source_url"].startswith("internal://classifier-run/")
        # `reviewer` names who answered, `provenance.model` names what
        # was configured. They agree only on a live run — and this
        # fixture's classifier is the mock, so they must not.
        assert entry["provenance"]["model"] == "claude-sonnet-5"
        assert entry["provenance"]["backend"] == "mock"
        assert ev["reviewer"] == "mock (no claude-sonnet-5 call)"


def test_normalize_explicit_verification_url_overrides_registry():
    rec = {
        "name": "Some IGO Initiative",
        "description": (
            "An initiative within the OECD intergovernmental organization. "
            "Global scope."
        ),
        "primary_reference_url": "https://example.invalid/explicit",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([rec])
    assert out[0]["agv_row"]["primary_reference_url"] == "https://example.invalid/explicit"


def test_normalize_skips_records_without_verification_source():
    # Entity type "academic_consortium" has no verification source in our test registry
    rec = {
        "name": "Some Academic Network",
        "description": (
            "A cross-institutional academic network; academic consortium; "
            "peer-reviewed research; global."
        ),
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([rec])
    assert out == []


def test_normalize_skips_records_without_name_or_text():
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([{"source_id": "x"}])  # no name, no text
    assert out == []


def test_normalize_rawvenue_from_fetcher_shape():
    # Matches the JSON shape that pipelines.fetchers.oecd_ai emits
    raw = {
        "source_id": "oecd.ai:1001",
        "source_role": "discovery",
        "source_registry": "oecd_ai_navigator",
        "name": "OECD Working Party on AI Governance",
        "url": "https://oecd.ai/en/dashboards/overview/policy/1001",
        "country": "France",
        "description": (
            "Initiative within the OECD ecosystem; standing working party. "
            "Global scope via OECD; lead actor OECD secretariat."
        ),
        "fetched_at": "2026-04-23T00:00:00+00:00",
        "fetch_strategy": "fixture",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([raw])
    assert len(out) == 1
    prov = out[0]["provenance"]
    assert prov["source_id"] == "oecd.ai:1001"
    assert prov["discovery_url"] == "https://oecd.ai/en/dashboards/overview/policy/1001"


def test_normalize_drops_national_strategy_titles():
    """A national AI strategy is a policy document, not a venue (§3.1).

    OECD.AI's Policy Navigator lists many of them; none should be proposed
    as an AGV candidate.
    """
    raw = {
        "source_id": "oecd.ai:1002",
        "source_registry": "oecd_ai_navigator",
        "name": "France — National AI Strategy",
        "url": "https://oecd.ai/en/dashboards/overview/policy/1002",
        "description": "France national AI strategy, second phase funding.",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    assert norm.normalize([raw]) == []
    assert [s["source_id"] for s in norm.skipped_not_a_venue] == ["oecd.ai:1002"]


def test_normalize_drops_news_headlines_and_unwraps_cdata():
    """Regression: the first live monthly run proposed 17 articles as venues."""
    raws = [
        {
            "source_id": "ai_snake_oil:0001",
            "source_registry": "tech_policy_press",
            "name": "<![CDATA[Could AI slow science?]]>",
            "url": "https://example.invalid/post",
            "description": "A blog post about research productivity.",
        },
        {
            "source_id": "gov_uk:0002",
            "source_registry": "government_pages",
            "name": (
                "New partnership set to see the UK and Ukraine develop battle "
                "winning technology as Britain secures access to Ukraine's AI Labs"
            ),
            "url": "https://example.invalid/news",
            "description": "Press release.",
        },
    ]
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    assert norm.normalize(raws) == []
    assert len(norm.skipped_not_a_venue) == 2
    # CDATA markers must not survive into the reported name.
    assert norm.skipped_not_a_venue[0]["name"] == "Could AI slow science?"


def test_normalize_recovers_venue_named_inside_an_article():
    """A news item earns a candidate only by naming a venue in its text."""
    raw = {
        "source_id": "tech_policy_press:0003",
        "source_registry": "tech_policy_press",
        "name": "Regulators announce sweeping new rules",
        "url": "https://example.invalid/article",
        "description": "The UK AI Safety Institute will run the evaluations.",
        # Explicit so the assertion is about name recovery, not registry lookup.
        "primary_reference_url": "https://www.aisi.gov.uk/",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([raw])
    assert len(out) == 1
    assert out[0]["agv_row"]["name_en"] == "UK AI Safety Institute"
    assert norm.skipped_not_a_venue == []


def test_normalize_flags_placeholder_reference_url():
    """A registry family URL is valid layer-wise but is not this venue's page."""
    raw = {
        "source_id": "oecd.ai:1003",
        "source_registry": "oecd_ai_navigator",
        "name": "OECD AI Policy Observatory",
        "url": "https://oecd.ai/en/dashboards/overview/policy/1003",
        "description": "Initiative within the OECD ecosystem; standing programme.",
    }
    norm = Normalizer(registry=_registry(), classifier=_classifier())
    out = norm.normalize([raw])
    assert len(out) == 1
    assert "placeholder" in out[0]["agv_row"]["notes"]

    explicit = dict(raw, primary_reference_url="https://oecd.ai/en/wonk/")
    out2 = norm.normalize([explicit])
    assert out2[0]["agv_row"]["primary_reference_url"] == "https://oecd.ai/en/wonk/"
    assert "placeholder" not in out2[0]["agv_row"]["notes"]
