"""Schema invariants for data/*.csv per CLAUDE.md §4.8.

Runs with any Python 3.9+ and pytest; no pandas dependency.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"

# ---- AGVO enums (CLAUDE.md §3) ----

ENTITY_TYPES = {
    "igo_initiative", "intergov_forum", "treaty_body", "multistakeholder_coalition",
    "industry_consortium", "intl_ngo_thinktank", "academic_consortium",
    "standards_body_wg", "national_regulator_intl", "conference_policy_track",
    "standalone_governance_conference", "industry_conference", "one_off_summit",
}
GOVERNANCE_MODALITIES = {
    "declaration_principles", "binding_instrument", "technical_standards",
    "evaluation_benchmarking", "capacity_building", "research_monitoring",
    "dialogue_coordination", "regulatory_enforcement",
}
TOPIC_FOCI = {
    "ai_general", "safety_frontier", "ethics_rights", "privacy_data",
    "genai_content", "agentic_autonomy", "domain_health", "domain_defense",
    "domain_education", "domain_climate", "domain_labor", "access_inclusion",
    "standards_interop",
}
GEO_SCOPES = {"global", "transregional", "regional", "plurilateral", "bilateral_plus"}
LEAD_ACTORS = {
    "igo_secretariat", "state_govt", "industry", "academia",
    "civil_society", "hybrid_mso",
}
LEGAL_CHARACTERS = {"soft_law", "hard_law", "mixed", "n/a"}
STATES = {"announced", "active", "dormant", "absorbed", "terminated", "succeeded"}
CONVENING_FREQUENCIES = {"one_off", "annual", "biennial", "continuous", "ad_hoc"}
DATE_PRECISIONS = {"day", "month", "year"}
ESTABLISHMENT_BASES = {
    "announced", "first_meeting", "formally_constituted", "first_output",
}
OVERRIDE_POLICIES = {"lock_verified_only", "lock_all", "allow_llm_update"}
RELATION_TYPES = {
    "parent_of", "succeeds", "absorbed_into", "coordinates_with",
    "references_principles_of", "convenes_within", "member_of",
}
NAME_TYPES = {
    "official_en", "official_native", "alias",
    "former_official_en", "abbreviation",
}
CONFIDENCE_VALUES = {"high", "medium", "low"}

REQUIRED_AGV_FIELDS = [
    "agv_id", "name_en", "entity_type",
    "governance_modality_primary", "topic_focus_primary",
    "geographic_scope", "lead_actor_primary", "legal_character",
    "founded_date", "founded_date_precision", "establishment_basis",
    "current_state", "convening_frequency", "primary_reference_url",
    "confidence_entity_type", "confidence_founded_date",
    "confidence_current_state", "confidence_legal_character",
    "override_policy",
]

URL_RE = re.compile(r"^(https?|internal)://")


def _load(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def agvs() -> list[dict]:
    return _load("agv.csv")


@pytest.fixture(scope="module")
def relations() -> list[dict]:
    return _load("agv_relation.csv")


@pytest.fixture(scope="module")
def name_history() -> list[dict]:
    return _load("agv_name_history.csv")


@pytest.fixture(scope="module")
def lifecycle() -> list[dict]:
    return _load("agv_lifecycle.csv")


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


# ------------------------------------------------------------------
# agv.csv
# ------------------------------------------------------------------

def test_agv_required_fields_nonnull(agvs):
    for row in agvs:
        for field in REQUIRED_AGV_FIELDS:
            assert (row.get(field) or "").strip(), (
                f"{row.get('agv_id')}: required field '{field}' is empty"
            )


def test_agv_id_unique(agvs):
    ids = [r["agv_id"] for r in agvs]
    dupes = [x for x, c in Counter(ids).items() if c > 1]
    assert not dupes, f"duplicate agv_id(s): {dupes}"


def test_entity_type_enum(agvs):
    for r in agvs:
        assert r["entity_type"] in ENTITY_TYPES, (
            f"{r['agv_id']}: bad entity_type '{r['entity_type']}'"
        )


def test_governance_modality_enum(agvs):
    for r in agvs:
        assert r["governance_modality_primary"] in GOVERNANCE_MODALITIES
        sec = (r.get("governance_modality_secondary") or "").strip()
        if sec:
            assert sec in GOVERNANCE_MODALITIES


def test_topic_focus_enum(agvs):
    for r in agvs:
        assert r["topic_focus_primary"] in TOPIC_FOCI
        for col in ("topic_focus_secondary_1", "topic_focus_secondary_2"):
            v = (r.get(col) or "").strip()
            if v:
                assert v in TOPIC_FOCI


def test_geographic_scope_enum(agvs):
    for r in agvs:
        assert r["geographic_scope"] in GEO_SCOPES


def test_lead_actor_enum(agvs):
    for r in agvs:
        assert r["lead_actor_primary"] in LEAD_ACTORS
        sec = (r.get("lead_actor_secondary") or "").strip()
        if sec:
            assert sec in LEAD_ACTORS


def test_legal_character_enum(agvs):
    for r in agvs:
        assert r["legal_character"] in LEGAL_CHARACTERS


def test_current_state_enum(agvs):
    for r in agvs:
        assert r["current_state"] in STATES


def test_convening_frequency_enum(agvs):
    for r in agvs:
        assert r["convening_frequency"] in CONVENING_FREQUENCIES


def test_date_precision_enum(agvs):
    for r in agvs:
        assert r["founded_date_precision"] in DATE_PRECISIONS


def test_establishment_basis_enum(agvs):
    for r in agvs:
        assert r["establishment_basis"] in ESTABLISHMENT_BASES


def test_override_policy_enum(agvs):
    for r in agvs:
        assert r["override_policy"] in OVERRIDE_POLICIES


def test_confidence_values(agvs):
    for r in agvs:
        for k in (
            "confidence_entity_type", "confidence_founded_date",
            "confidence_current_state", "confidence_legal_character",
        ):
            assert r[k] in CONFIDENCE_VALUES, f"{r['agv_id']}: {k}={r[k]!r}"


def test_founded_date_parseable_and_post_2000(agvs):
    for r in agvs:
        d = _parse_date(r["founded_date"])
        assert d.year >= 2000, (
            f"{r['agv_id']}: founded_date {r['founded_date']} before 2000"
        )


def test_primary_reference_url_wellformed(agvs):
    for r in agvs:
        assert URL_RE.match(r["primary_reference_url"]), (
            f"{r['agv_id']}: primary_reference_url "
            f"'{r['primary_reference_url']}' not well-formed"
        )


def test_region_code_when_regional(agvs):
    for r in agvs:
        if r["geographic_scope"] == "regional":
            assert (r.get("region_code") or "").strip(), (
                f"{r['agv_id']}: region_code required when scope=regional"
            )


def test_state_absorbed_or_succeeded_has_relation(agvs, relations):
    referenced = set()
    for r in relations:
        referenced.add(r["source_agv"])
        referenced.add(r["target_agv"])
    for r in agvs:
        if r["current_state"] in {"absorbed", "succeeded"}:
            assert r["agv_id"] in referenced, (
                f"{r['agv_id']}: current_state={r['current_state']} "
                "but no relation references this AGV"
            )


def test_human_verified_requires_verified_at(agvs):
    for r in agvs:
        hvf = (r.get("human_verified_fields") or "").strip()
        hva = (r.get("human_verified_at") or "").strip()
        if hvf:
            assert hva, (
                f"{r['agv_id']}: human_verified_fields set "
                "but human_verified_at empty"
            )


def test_last_observed_activity_parseable(agvs):
    for r in agvs:
        v = (r.get("last_observed_activity_date") or "").strip()
        if v:
            _parse_date(v)


# ------------------------------------------------------------------
# agv_relation.csv
# ------------------------------------------------------------------

def test_relation_type_enum(relations):
    for r in relations:
        assert r["relation_type"] in RELATION_TYPES


def test_relation_agv_ids_resolve(relations, agvs):
    ids = {r["agv_id"] for r in agvs}
    for r in relations:
        assert r["source_agv"] in ids, (
            f"relation source '{r['source_agv']}' not in agv.csv"
        )
        assert r["target_agv"] in ids, (
            f"relation target '{r['target_agv']}' not in agv.csv"
        )


def test_relation_source_url_wellformed(relations):
    for r in relations:
        assert URL_RE.match(r["source_url"]), (
            f"relation source_url '{r['source_url']}' not well-formed"
        )


def test_relation_start_date_parseable(relations):
    for r in relations:
        v = (r.get("start_date") or "").strip()
        if v:
            _parse_date(v)


# ------------------------------------------------------------------
# agv_name_history.csv
# ------------------------------------------------------------------

def test_name_history_name_type_enum(name_history):
    for r in name_history:
        assert r["name_type"] in NAME_TYPES


def test_name_history_valid_from_lt_valid_to(name_history):
    for r in name_history:
        vf = (r.get("valid_from") or "").strip()
        vt = (r.get("valid_to") or "").strip()
        if vf and vt:
            assert _parse_date(vf) < _parse_date(vt), (
                f"{r['agv_id']} '{r['name']}': valid_from >= valid_to"
            )


def test_name_history_unique_current_official_en(name_history):
    counts = Counter(
        r["agv_id"] for r in name_history
        if r["name_type"] == "official_en"
        and not (r.get("valid_to") or "").strip()
    )
    offenders = [aid for aid, n in counts.items() if n > 1]
    assert not offenders, (
        f"AGVs with >1 current official_en row: {offenders}"
    )


def test_name_history_agv_ids_resolve(name_history, agvs):
    ids = {r["agv_id"] for r in agvs}
    for r in name_history:
        assert r["agv_id"] in ids


# ------------------------------------------------------------------
# agv_lifecycle.csv
# ------------------------------------------------------------------

def test_lifecycle_to_state_enum(lifecycle):
    for r in lifecycle:
        assert r["to_state"] in STATES
        frm = (r.get("from_state") or "").strip()
        if frm:
            assert frm in STATES


def test_lifecycle_agv_ids_resolve(lifecycle, agvs):
    ids = {r["agv_id"] for r in agvs}
    for r in lifecycle:
        assert r["agv_id"] in ids


def test_lifecycle_transition_date_parseable(lifecycle):
    for r in lifecycle:
        _parse_date(r["transition_date"])
