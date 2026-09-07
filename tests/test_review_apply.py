"""Tests for tools.review.apply_decisions.

Each test builds a tiny synthetic data/ tree in a tmp_path and verifies the
applier emits the right CSV deltas for each (category × action) combination.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tools.review.apply_decisions import Applier
from tools.review.schema import validate_decision

AGV_HEADER = [
    "agv_id", "name_en", "name_native", "entity_type",
    "governance_modality_primary", "governance_modality_secondary",
    "topic_focus_primary", "topic_focus_secondary_1", "topic_focus_secondary_2",
    "geographic_scope", "region_code",
    "lead_actor_primary", "lead_actor_secondary",
    "legal_character",
    "founded_date", "founded_date_precision", "establishment_basis",
    "announced_date", "first_output_date",
    "current_state", "convening_frequency", "last_observed_activity_date",
    "primary_reference_url", "last_verified_date",
    "confidence_entity_type", "confidence_founded_date",
    "confidence_current_state", "confidence_legal_character",
    "human_verified_at", "human_verified_fields", "override_policy", "notes",
]

EVIDENCE_HEADER = [
    "agv_id", "field_name", "source_url", "source_type",
    "accessed_at", "evidence_note", "reviewer", "confidence",
]

LIFECYCLE_HEADER = [
    "agv_id", "from_state", "to_state", "transition_date", "source_url", "notes",
]


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    # Seed one existing AGV used by update/conflict/stale/rename paths.
    seed = {
        "agv_id": "existing_agv", "name_en": "Existing AGV", "entity_type": "igo_initiative",
        "governance_modality_primary": "dialogue_coordination",
        "topic_focus_primary": "ai_general", "geographic_scope": "global",
        "lead_actor_primary": "igo_secretariat", "legal_character": "soft_law",
        "founded_date": "2020-01-01", "founded_date_precision": "year",
        "establishment_basis": "formally_constituted",
        "current_state": "active", "convening_frequency": "continuous",
        "last_observed_activity_date": "2026-04-01",
        "primary_reference_url": "https://example.org/",
        "last_verified_date": "2026-04-23",
        "confidence_entity_type": "high", "confidence_founded_date": "high",
        "confidence_current_state": "high", "confidence_legal_character": "high",
        "human_verified_at": "2026-04-23",
        "human_verified_fields": "entity_type,founded_date,current_state,legal_character",
        "override_policy": "lock_verified_only",
    }
    _write_csv(d / "agv.csv", AGV_HEADER, [seed])
    _write_csv(d / "agv_evidence.csv", EVIDENCE_HEADER, [])
    _write_csv(d / "agv_lifecycle.csv", LIFECYCLE_HEADER, [])
    return d


def _new_venue_payload() -> dict:
    return {
        "agv_row": {
            "agv_id": "candidate_new", "name_en": "Candidate New",
            "entity_type": "industry_consortium",
            "governance_modality_primary": "dialogue_coordination",
            "topic_focus_primary": "safety_frontier",
            "geographic_scope": "global", "lead_actor_primary": "industry",
            "legal_character": "soft_law",
            "founded_date": "2024-09-01", "founded_date_precision": "month",
            "establishment_basis": "announced",
            "current_state": "active", "convening_frequency": "continuous",
            "primary_reference_url": "https://example.org/candidate",
            "confidence_entity_type": "high", "confidence_founded_date": "medium",
            "confidence_current_state": "high", "confidence_legal_character": "high",
        },
        "evidence_rows": [{
            "agv_id": "candidate_new", "field_name": "entity_type",
            "source_url": "internal://classifier-run/test",
            "source_type": "llm_classification",
            "accessed_at": "2026-05-13", "evidence_note": "auto-classified",
            "reviewer": "claude-test", "confidence": "medium",
        }],
        "provenance": {"discovery_source": "test_fetcher"},
    }


def _base_report(extra: dict | None = None) -> dict:
    rep = {
        "run_id": "test-run", "today": "2026-05-13",
        "canonical_size": 1, "candidate_size": 0,
        "new_venues": [], "unverified_updates": [], "conflicts": [],
        "stale_candidates": [], "renames": [], "matches_count": 0,
    }
    rep.update(extra or {})
    return rep


def _decisions(reviewer: str, items: dict) -> dict:
    return {
        "report_id": "test-run", "reviewer": reviewer,
        "started_at": "2026-05-13T00:00:00Z",
        "decisions": items,
    }


# ---------------------------------------------------------------------------
# Sanity: schema validator
# ---------------------------------------------------------------------------


def test_validate_decision_rejects_unknown_category():
    errs = validate_decision({"category": "bogus", "action": "accept", "ref": "x"})
    assert any("unknown category" in e for e in errs)


def test_validate_decision_rejects_unknown_enum_value():
    errs = validate_decision({
        "category": "new_venues", "action": "edit", "ref": "x",
        "edits": {"entity_type": "not_a_real_type"},
    })
    assert any("invalid value for 'entity_type'" in e for e in errs)


def test_validate_decision_accept_is_clean():
    errs = validate_decision({
        "category": "new_venues", "action": "accept", "ref": "x",
    })
    assert errs == []


def test_validate_conflict_requires_choice():
    errs = validate_decision({
        "category": "conflicts", "action": "accept",
        "ref": "x:field",
    })
    assert any("conflict_choice" in e for e in errs)


# ---------------------------------------------------------------------------
# Applier: empty decisions = no-op
# ---------------------------------------------------------------------------


def test_apply_empty_decisions_changes_nothing(data_dir):
    rep = _base_report()
    dec = _decisions("s00048ri", {})
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    counts = a.apply_all()
    a.flush()
    assert counts["new_venues_accepted"] == 0
    assert _read_csv(data_dir / "agv.csv")[0]["agv_id"] == "existing_agv"
    assert _read_csv(data_dir / "agv_evidence.csv") == []
    assert _read_csv(data_dir / "agv_lifecycle.csv") == []


def test_apply_requires_reviewer(data_dir):
    rep = _base_report()
    dec = _decisions("", {})
    with pytest.raises(ValueError, match="reviewer"):
        Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")


# ---------------------------------------------------------------------------
# new_venues
# ---------------------------------------------------------------------------


def test_new_venue_accept_appends_row_with_human_verification(data_dir):
    payload = _new_venue_payload()
    rep = _base_report({"new_venues": [payload]})
    dec = _decisions("s00048ri", {
        "new_venues:candidate_new": {
            "category": "new_venues", "ref": "candidate_new",
            "action": "accept", "comment": "ok",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    counts = a.apply_all()
    a.flush()
    assert counts["new_venues_accepted"] == 1

    agvs = _read_csv(data_dir / "agv.csv")
    assert len(agvs) == 2
    new_row = next(r for r in agvs if r["agv_id"] == "candidate_new")
    assert new_row["human_verified_at"] == "2026-05-13"
    assert "entity_type" in new_row["human_verified_fields"]
    assert new_row["override_policy"] == "lock_verified_only"

    ev = _read_csv(data_dir / "agv_evidence.csv")
    human_rows = [r for r in ev if r["reviewer"] == "s00048ri"
                  and r["agv_id"] == "candidate_new"]
    fields = {r["field_name"] for r in human_rows}
    assert fields == {"entity_type", "founded_date", "current_state", "legal_character"}
    # llm_classification row is preserved
    assert any(r["source_type"] == "llm_classification" for r in ev)

    lc = _read_csv(data_dir / "agv_lifecycle.csv")
    assert lc and lc[0]["agv_id"] == "candidate_new"
    assert lc[0]["from_state"] == ""
    assert lc[0]["to_state"] == "active"


def test_new_venue_edit_overrides_classification(data_dir):
    payload = _new_venue_payload()
    rep = _base_report({"new_venues": [payload]})
    dec = _decisions("s00048ri", {
        "new_venues:candidate_new": {
            "category": "new_venues", "ref": "candidate_new",
            "action": "edit",
            "edits": {"entity_type": "multistakeholder_coalition",
                      "legal_character": "mixed"},
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    new_row = next(r for r in _read_csv(data_dir / "agv.csv")
                   if r["agv_id"] == "candidate_new")
    assert new_row["entity_type"] == "multistakeholder_coalition"
    assert new_row["legal_character"] == "mixed"


def test_new_venue_edit_rejects_unknown_enum(data_dir):
    payload = _new_venue_payload()
    rep = _base_report({"new_venues": [payload]})
    dec = _decisions("s00048ri", {
        "new_venues:candidate_new": {
            "category": "new_venues", "ref": "candidate_new",
            "action": "edit",
            "edits": {"entity_type": "made_up_type"},
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    counts = a.apply_all()
    # Validation errors at decision level are caught by validate_decision,
    # tracked as "errors". Decision is skipped, no row added.
    assert counts["errors"] == 1
    assert counts["new_venues_accepted"] == 0
    assert len(_read_csv(data_dir / "agv.csv")) == 1


def test_new_venue_reject_is_noop(data_dir):
    payload = _new_venue_payload()
    rep = _base_report({"new_venues": [payload]})
    dec = _decisions("s00048ri", {
        "new_venues:candidate_new": {
            "category": "new_venues", "ref": "candidate_new",
            "action": "reject",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    counts = a.apply_all()
    a.flush()
    assert counts["rejected"] == 1
    assert len(_read_csv(data_dir / "agv.csv")) == 1


# ---------------------------------------------------------------------------
# unverified_updates
# ---------------------------------------------------------------------------


def test_unverified_update_accept_writes_proposed(data_dir):
    rep = _base_report({"unverified_updates": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "field_name": "convening_frequency",
        "existing_value": "continuous", "proposed_value": "annual",
        "rationale": "site reorganized", "source_url": "https://example.org/x",
    }]})
    dec = _decisions("s00048ri", {
        "unverified_updates:existing_agv:convening_frequency": {
            "category": "unverified_updates",
            "ref": "existing_agv:convening_frequency",
            "action": "accept",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["convening_frequency"] == "annual"


def test_unverified_update_edit_writes_user_value(data_dir):
    rep = _base_report({"unverified_updates": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "field_name": "convening_frequency",
        "existing_value": "continuous", "proposed_value": "annual",
        "rationale": "site reorganized", "source_url": "https://example.org/x",
    }]})
    dec = _decisions("s00048ri", {
        "unverified_updates:existing_agv:convening_frequency": {
            "category": "unverified_updates",
            "ref": "existing_agv:convening_frequency",
            "action": "edit",
            "edits": {"convening_frequency": "biennial"},
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["convening_frequency"] == "biennial"


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------


def test_conflict_keep_human_records_evidence(data_dir):
    rep = _base_report({"conflicts": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "field_name": "legal_character",
        "existing_value": "soft_law", "proposed_value": "hard_law",
        "rationale": "classifier confused", "source_url": "https://example.org/x",
        "existing_verified_at": "2026-04-23", "override_policy": "lock_verified_only",
    }]})
    dec = _decisions("s00048ri", {
        "conflicts:existing_agv:legal_character": {
            "category": "conflicts", "ref": "existing_agv:legal_character",
            "action": "accept", "conflict_choice": "keep_human",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["legal_character"] == "soft_law"
    ev_rows = _read_csv(data_dir / "agv_evidence.csv")
    assert any("keep_human" in r["evidence_note"] or "kept human" in r["evidence_note"]
               for r in ev_rows)


def test_conflict_accept_llm_overwrites_canonical(data_dir):
    rep = _base_report({"conflicts": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "field_name": "legal_character",
        "existing_value": "soft_law", "proposed_value": "hard_law",
        "rationale": "venue evolved", "source_url": "https://example.org/x",
        "existing_verified_at": "2026-04-23", "override_policy": "lock_verified_only",
    }]})
    dec = _decisions("s00048ri", {
        "conflicts:existing_agv:legal_character": {
            "category": "conflicts", "ref": "existing_agv:legal_character",
            "action": "accept", "conflict_choice": "accept_llm",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["legal_character"] == "hard_law"
    assert row["human_verified_at"] == "2026-05-13"


def test_conflict_note_evolution_appends_note(data_dir):
    rep = _base_report({"conflicts": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "field_name": "entity_type",
        "existing_value": "igo_initiative",
        "proposed_value": "multistakeholder_coalition",
        "rationale": "restructured 2026", "source_url": "https://example.org/x",
        "existing_verified_at": "2026-04-23", "override_policy": "lock_verified_only",
    }]})
    dec = _decisions("s00048ri", {
        "conflicts:existing_agv:entity_type": {
            "category": "conflicts", "ref": "existing_agv:entity_type",
            "action": "accept", "conflict_choice": "note_evolution",
            "comment": "added civil society seats",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["entity_type"] == "multistakeholder_coalition"
    assert "Venue evolution noted" in row["notes"]


# ---------------------------------------------------------------------------
# stale + renames
# ---------------------------------------------------------------------------


def test_stale_accept_marks_dormant(data_dir):
    rep = _base_report({"stale_candidates": [{
        "agv_id": "existing_agv", "name_en": "Existing AGV",
        "convening_frequency": "continuous",
        "last_observed_activity_date": "2024-01-01",
        "months_since_loa": 28.0, "threshold_months": 6,
    }]})
    dec = _decisions("s00048ri", {
        "stale_candidates:existing_agv": {
            "category": "stale_candidates", "ref": "existing_agv",
            "action": "accept",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["current_state"] == "dormant"
    lc = _read_csv(data_dir / "agv_lifecycle.csv")
    assert lc[-1]["to_state"] == "dormant"
    assert lc[-1]["from_state"] == "active"


def test_rename_accept_swaps_name_and_writes_history(data_dir):
    # Pre-seed name_history with the existing official_en row.
    nh = data_dir / "agv_name_history.csv"
    _write_csv(nh, [
        "agv_id", "name", "name_type", "valid_from", "valid_to", "source_url",
    ], [{
        "agv_id": "existing_agv", "name": "Existing AGV",
        "name_type": "official_en", "valid_from": "2020-01-01",
        "valid_to": "", "source_url": "",
    }])
    rep = _base_report({"renames": [{
        "candidate_agv_id": "existing_agv_renamed",
        "candidate_name": "Existing AGV (Renamed 2026)",
        "matched_agv_id": "existing_agv",
        "former_name": "Existing AGV",
        "name_history_valid_to": "",
    }]})
    dec = _decisions("s00048ri", {
        "renames:existing_agv_renamed->existing_agv": {
            "category": "renames",
            "ref": "existing_agv_renamed->existing_agv",
            "action": "accept",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    row = _read_csv(data_dir / "agv.csv")[0]
    assert row["name_en"] == "Existing AGV (Renamed 2026)"
    hist = _read_csv(nh)
    assert len(hist) == 2
    old = [r for r in hist if r["valid_to"] == "2026-05-13"][0]
    new = [r for r in hist if r["valid_from"] == "2026-05-13"][0]
    assert old["name_type"] == "former_official_en"
    assert new["name_type"] == "official_en"


# ---------------------------------------------------------------------------
# Idempotency: applying same decisions twice via flush+reload is rejected
# ---------------------------------------------------------------------------


def test_applying_new_venue_twice_raises(data_dir):
    payload = _new_venue_payload()
    rep = _base_report({"new_venues": [payload]})
    dec = _decisions("s00048ri", {
        "new_venues:candidate_new": {
            "category": "new_venues", "ref": "candidate_new",
            "action": "accept",
        },
    })
    a = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    a.apply_all()
    a.flush()
    # Second pass should now see candidate_new already in canonical and
    # complain.
    a2 = Applier(report=rep, decisions=dec, data_dir=data_dir, today="2026-05-13")
    counts = a2.apply_all()
    assert counts["errors"] == 1
    assert counts["new_venues_accepted"] == 0


# ---------------------------------------------------------------------------
# Server smoke test: flatten_report + decision validation
# ---------------------------------------------------------------------------


def test_flatten_report_orders_by_category():
    from tools.review.server import flatten_report
    rep = _base_report({
        "new_venues": [_new_venue_payload()],
        "stale_candidates": [{
            "agv_id": "existing_agv", "name_en": "x",
            "convening_frequency": "continuous",
            "last_observed_activity_date": "2024-01-01",
            "months_since_loa": 28, "threshold_months": 6,
        }],
    })
    flat = flatten_report(rep)
    cats = [c["category"] for c in flat]
    # new_venues come before stale_candidates in display order
    assert cats.index("new_venues") < cats.index("stale_candidates")
    assert flat[0]["key"] == "new_venues:candidate_new"


# ---------------------------------------------------------------------------
# Schema parity: tools.review.schema enums match tests/test_schema.py
# ---------------------------------------------------------------------------


def test_review_schema_parity_with_test_schema():
    """The duplicated enums must agree with the canonical set in tests/test_schema.py."""
    from tests import test_schema as canonical
    from tools.review import schema as ui

    assert set(ui.ENTITY_TYPES) == canonical.ENTITY_TYPES
    assert set(ui.GOVERNANCE_MODALITIES) == canonical.GOVERNANCE_MODALITIES
    assert set(ui.TOPIC_FOCI) == canonical.TOPIC_FOCI
    assert set(ui.GEO_SCOPES) == canonical.GEO_SCOPES
    assert set(ui.LEAD_ACTORS) == canonical.LEAD_ACTORS
    assert set(ui.LEGAL_CHARACTERS) == canonical.LEGAL_CHARACTERS
    assert set(ui.STATES) == canonical.STATES
    assert set(ui.CONVENING_FREQUENCIES) == canonical.CONVENING_FREQUENCIES
    assert set(ui.DATE_PRECISIONS) == canonical.DATE_PRECISIONS
    assert set(ui.ESTABLISHMENT_BASES) == canonical.ESTABLISHMENT_BASES
    assert set(ui.OVERRIDE_POLICIES) == canonical.OVERRIDE_POLICIES
    assert set(ui.CONFIDENCE_VALUES) == canonical.CONFIDENCE_VALUES
