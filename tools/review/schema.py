"""AGVO v0.3 enums + decisions.json shape (single source of truth for the review UI).

Enum values intentionally duplicate ``tests/test_schema.py`` rather than
importing from it: the review UI must work even when test deps are not
installed, and pinning the two independently means an enum change in
CLAUDE.md must be reflected in both places — which surfaces drift via
``tests/test_review_schema_parity.py``.
"""
from __future__ import annotations

# ---- AGVO enums (CLAUDE.md §3) ----

ENTITY_TYPES: list[str] = [
    "igo_initiative", "intergov_forum", "treaty_body", "multistakeholder_coalition",
    "industry_consortium", "intl_ngo_thinktank", "academic_consortium",
    "standards_body_wg", "national_regulator_intl", "conference_policy_track",
    "standalone_governance_conference", "industry_conference", "one_off_summit",
]
GOVERNANCE_MODALITIES: list[str] = [
    "declaration_principles", "binding_instrument", "technical_standards",
    "evaluation_benchmarking", "capacity_building", "research_monitoring",
    "dialogue_coordination", "regulatory_enforcement",
]
TOPIC_FOCI: list[str] = [
    "ai_general", "safety_frontier", "ethics_rights", "privacy_data",
    "genai_content", "agentic_autonomy", "domain_health", "domain_defense",
    "domain_education", "domain_climate", "domain_labor", "access_inclusion",
    "standards_interop",
]
GEO_SCOPES: list[str] = [
    "global", "transregional", "regional", "plurilateral", "bilateral_plus",
]
REGION_CODES: list[str] = [
    "EU", "ASEAN", "AU", "LAC", "MENA", "Pacific", "NA", "SA", "AS", "EUR", "OC",
]
LEAD_ACTORS: list[str] = [
    "igo_secretariat", "state_govt", "industry", "academia",
    "civil_society", "hybrid_mso",
]
LEGAL_CHARACTERS: list[str] = ["soft_law", "hard_law", "mixed", "n/a"]
STATES: list[str] = [
    "announced", "active", "dormant", "absorbed", "terminated", "succeeded",
]
CONVENING_FREQUENCIES: list[str] = [
    "continuous", "annual", "biennial", "ad_hoc", "one_off",
]
DATE_PRECISIONS: list[str] = ["day", "month", "year"]
ESTABLISHMENT_BASES: list[str] = [
    "announced", "first_meeting", "formally_constituted", "first_output",
]
OVERRIDE_POLICIES: list[str] = [
    "lock_verified_only", "lock_all", "allow_llm_update",
]
CONFIDENCE_VALUES: list[str] = ["high", "medium", "low"]


# Per-field dropdown source for the review UI.
ENUM_BY_FIELD: dict[str, list[str]] = {
    "entity_type": ENTITY_TYPES,
    "governance_modality_primary": GOVERNANCE_MODALITIES,
    "governance_modality_secondary": [""] + GOVERNANCE_MODALITIES,
    "topic_focus_primary": TOPIC_FOCI,
    "topic_focus_secondary_1": [""] + TOPIC_FOCI,
    "topic_focus_secondary_2": [""] + TOPIC_FOCI,
    "geographic_scope": GEO_SCOPES,
    "region_code": [""] + REGION_CODES,
    "lead_actor_primary": LEAD_ACTORS,
    "lead_actor_secondary": [""] + LEAD_ACTORS,
    "legal_character": LEGAL_CHARACTERS,
    "current_state": STATES,
    "convening_frequency": CONVENING_FREQUENCIES,
    "founded_date_precision": DATE_PRECISIONS,
    "establishment_basis": ESTABLISHMENT_BASES,
    "override_policy": OVERRIDE_POLICIES,
    "confidence_entity_type": CONFIDENCE_VALUES,
    "confidence_founded_date": CONFIDENCE_VALUES,
    "confidence_current_state": CONFIDENCE_VALUES,
    "confidence_legal_character": CONFIDENCE_VALUES,
}

# Fields the reviewer is allowed to edit on a candidate row, in display order.
# We omit agv_id (immutable identifier) and last_verified_date / human_verified_*
# (filled by apply_decisions automatically).
EDITABLE_FIELDS: list[str] = [
    "name_en", "name_native",
    "entity_type",
    "governance_modality_primary", "governance_modality_secondary",
    "topic_focus_primary", "topic_focus_secondary_1", "topic_focus_secondary_2",
    "geographic_scope", "region_code",
    "lead_actor_primary", "lead_actor_secondary",
    "legal_character",
    "founded_date", "founded_date_precision", "establishment_basis",
    "announced_date", "first_output_date",
    "current_state", "convening_frequency",
    "last_observed_activity_date",
    "primary_reference_url",
    "confidence_entity_type", "confidence_founded_date",
    "confidence_current_state", "confidence_legal_character",
    "override_policy",
    "notes",
]


# ---- decisions.json shape -------------------------------------------------
#
# {
#   "report_id":   "diff-20260513T..-...",   # echoes DiffReport.run_id
#   "reviewer":    "s00048ri",
#   "started_at":  "2026-05-13T10:00:00Z",
#   "decisions":   {                          # keyed by candidate ref
#     "new_venues:germany_bnetza_ai": {
#       "category":  "new_venues",
#       "ref":       "germany_bnetza_ai",
#       "action":    "accept" | "edit" | "reject" | "defer",
#       "edits":     { "entity_type": "...", ... },   # only when action=edit
#       "comment":   "free text rationale",
#       "decided_at":"2026-05-13T10:15:00Z"
#     },
#     ...
#   }
# }
#
# Categories: new_venues | unverified_updates | conflicts | stale_candidates | renames
#
# `ref` interpretation per category:
#   new_venues       -> agv_id (candidate's)
#   unverified_updates -> "{agv_id}:{field_name}"
#   conflicts        -> "{agv_id}:{field_name}"
#   stale_candidates -> agv_id
#   renames          -> "{candidate_agv_id}->{matched_agv_id}"
#
# Conflicts get an extra `conflict_choice` ∈ {keep_human, accept_llm, note_evolution}
# from §4.7 in addition to `action`.

VALID_ACTIONS: set[str] = {"accept", "edit", "reject", "defer"}
VALID_CATEGORIES: set[str] = {
    "new_venues", "unverified_updates", "conflicts",
    "stale_candidates", "renames",
}
VALID_CONFLICT_CHOICES: set[str] = {
    "keep_human", "accept_llm", "note_evolution",
}


def decision_key(category: str, ref: str) -> str:
    """Compose the dict key used in decisions.json."""
    return f"{category}:{ref}"


def validate_decision(d: dict) -> list[str]:
    """Return a list of human-readable errors; empty list means valid."""
    errors: list[str] = []
    cat = d.get("category")
    if cat not in VALID_CATEGORIES:
        errors.append(f"unknown category: {cat!r}")
    action = d.get("action")
    if action not in VALID_ACTIONS:
        errors.append(f"unknown action: {action!r}")
    if not d.get("ref"):
        errors.append("missing ref")
    if action == "edit":
        edits = d.get("edits") or {}
        if not isinstance(edits, dict):
            errors.append("edits must be an object")
        else:
            for field, val in edits.items():
                if field in ENUM_BY_FIELD and val not in ENUM_BY_FIELD[field]:
                    errors.append(
                        f"invalid value for {field!r}: {val!r}"
                    )
    if cat == "conflicts":
        choice = d.get("conflict_choice")
        if action != "defer" and choice not in VALID_CONFLICT_CHOICES:
            errors.append(
                f"conflict requires conflict_choice ∈ {sorted(VALID_CONFLICT_CHOICES)}"
            )
    return errors
