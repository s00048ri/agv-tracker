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
        assert ev["reviewer"] == entry["provenance"]["model"]


def test_normalize_explicit_verification_url_overrides_registry():
    rec = {
        "name": "Some IGO Initiative",
        "description": "An initiative within the OECD intergovernmental organization. Global scope.",
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
        "name": "France — National AI Strategy",
        "url": "https://oecd.ai/en/dashboards/overview/policy/1001",
        "country": "France",
        "description": (
            "Initiative within the OECD ecosystem; France national AI strategy. "
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
