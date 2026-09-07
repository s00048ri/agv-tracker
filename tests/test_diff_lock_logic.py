"""Four-case §4.7 logic × override_policy variations + rename detection.

Tests build canonical and candidate rows as plain dicts in-memory; no CSV
I/O so the fixtures are fully explicit.
"""
from __future__ import annotations

from datetime import date

from pipelines.diff import (
    DIFFED_FIELDS,
    Differ,
)

TODAY = date(2026, 4, 23)


# ---- fixture helpers ----

def _canonical(**overrides) -> dict:
    base = {
        "agv_id": "test_agv",
        "name_en": "Test AGV",
        "entity_type": "igo_initiative",
        "governance_modality_primary": "dialogue_coordination",
        "topic_focus_primary": "ai_general",
        "geographic_scope": "global",
        "lead_actor_primary": "igo_secretariat",
        "legal_character": "soft_law",
        "current_state": "active",
        "convening_frequency": "continuous",
        "last_observed_activity_date": TODAY.isoformat(),
        "human_verified_at": "2026-04-23",
        "human_verified_fields": "entity_type,founded_date,current_state,legal_character",
        "override_policy": "lock_verified_only",
    }
    base.update(overrides)
    return base


def _candidate(**overrides) -> dict:
    agv_row = {
        "agv_id": "test_agv",
        "name_en": "Test AGV",
        "entity_type": "igo_initiative",
        "governance_modality_primary": "dialogue_coordination",
        "topic_focus_primary": "ai_general",
        "geographic_scope": "global",
        "lead_actor_primary": "igo_secretariat",
        "legal_character": "soft_law",
        "current_state": "active",
        "convening_frequency": "continuous",
    }
    agv_row.update(overrides)
    return {"agv_row": agv_row, "evidence_rows": [], "provenance": {}}


def _differ(canonical=(), history=(), today=TODAY) -> Differ:
    return Differ(
        canonical_rows=list(canonical),
        name_history_rows=list(history),
        today=today,
    )


# ---- case D: match ----

def test_case_d_match_produces_no_entry():
    d = _differ(canonical=[_canonical()])
    report = d.diff([_candidate()])
    assert report.unverified_updates == []
    assert report.conflicts == []
    assert report.matches_count == len(DIFFED_FIELDS)


# ---- case A: greenfield ----

def test_case_a_greenfield_treated_as_unverified_update():
    canon = _canonical(entity_type="")
    cand = _candidate(entity_type="standards_body_wg")
    report = _differ(canonical=[canon]).diff([cand])
    assert len(report.unverified_updates) == 1
    u = report.unverified_updates[0]
    assert u.field_name == "entity_type"
    assert u.existing_value == ""
    assert u.proposed_value == "standards_body_wg"
    assert "greenfield" in u.rationale
    assert report.conflicts == []


# ---- case B: unverified update ----

def test_case_b_unverified_field_accepts_update():
    canon = _canonical(
        governance_modality_primary="dialogue_coordination",
        human_verified_fields="entity_type,founded_date,current_state,legal_character",
    )
    cand = _candidate(governance_modality_primary="research_monitoring")
    report = _differ(canonical=[canon]).diff([cand])
    assert len(report.unverified_updates) == 1
    u = report.unverified_updates[0]
    assert u.field_name == "governance_modality_primary"
    assert u.existing_value == "dialogue_coordination"
    assert u.proposed_value == "research_monitoring"
    assert "unverified" in u.rationale.lower()
    assert report.conflicts == []


# ---- case C: locked fields ----

def test_case_c_verified_field_surfaces_conflict():
    canon = _canonical(entity_type="igo_initiative")
    cand = _candidate(entity_type="intergov_forum")
    report = _differ(canonical=[canon]).diff([cand])
    assert len(report.conflicts) == 1
    assert report.unverified_updates == []
    c = report.conflicts[0]
    assert c.field_name == "entity_type"
    assert c.existing_value == "igo_initiative"
    assert c.proposed_value == "intergov_forum"
    assert c.override_policy == "lock_verified_only"
    assert c.existing_verified_at == "2026-04-23"


def test_case_c_lock_all_blocks_any_field():
    canon = _canonical(
        override_policy="lock_all",
        # human_verified_fields has only the default four — but lock_all means
        # the non-listed governance_modality_primary must STILL conflict.
    )
    cand = _candidate(governance_modality_primary="regulatory_enforcement")
    report = _differ(canonical=[canon]).diff([cand])
    assert len(report.conflicts) == 1
    assert report.unverified_updates == []
    assert report.conflicts[0].override_policy == "lock_all"


def test_case_c_allow_llm_update_bypasses_lock():
    canon = _canonical(override_policy="allow_llm_update")
    # Even for a human_verified field, allow_llm_update lets LLM update it.
    cand = _candidate(entity_type="standards_body_wg")
    report = _differ(canonical=[canon]).diff([cand])
    assert report.conflicts == []
    assert len(report.unverified_updates) == 1
    assert report.unverified_updates[0].field_name == "entity_type"


def test_lock_verified_only_default_permits_non_verified_changes():
    canon = _canonical(
        human_verified_fields="entity_type",
        override_policy="lock_verified_only",
    )
    # Changing a non-verified field must be accepted as an update.
    cand = _candidate(governance_modality_primary="technical_standards")
    report = _differ(canonical=[canon]).diff([cand])
    assert report.conflicts == []
    assert any(
        u.field_name == "governance_modality_primary"
        for u in report.unverified_updates
    )


# ---- new venues ----

def test_new_agv_emits_new_venue_entry():
    canon = _canonical(agv_id="existing_agv", name_en="Existing")
    cand = _candidate(agv_id="brand_new", name_en="Brand New")
    report = _differ(canonical=[canon]).diff([cand])
    assert len(report.new_venues) == 1
    assert report.new_venues[0].agv_row["agv_id"] == "brand_new"
    assert report.conflicts == []
    assert report.unverified_updates == []


# ---- rename detection ----

def test_rename_detected_and_not_flagged_as_new():
    canon = _canonical(agv_id="uk_aisi", name_en="UK AI Security Institute")
    name_history = [
        {
            "agv_id": "uk_aisi",
            "name": "UK AI Safety Institute",
            "name_type": "former_official_en",
            "valid_from": "2023-11-02",
            "valid_to": "2025-02-14",
        }
    ]
    # Candidate found under the former name with a different agv_id slug
    cand = _candidate(
        agv_id="uk_ai_safety_institute",
        name_en="UK AI Safety Institute",
        # Propose unchanged fields; we're only testing the rename match.
    )
    report = _differ(canonical=[canon], history=name_history).diff([cand])
    assert len(report.renames) == 1
    r = report.renames[0]
    assert r.matched_agv_id == "uk_aisi"
    assert r.former_name == "UK AI Safety Institute"
    assert len(report.new_venues) == 0, (
        "rename must NOT be flagged as a new venue"
    )


def test_rename_remaps_field_diffs_to_matched_agv():
    canon = _canonical(
        agv_id="uk_aisi",
        name_en="UK AI Security Institute",
        entity_type="national_regulator_intl",
        human_verified_fields="entity_type",
    )
    name_history = [
        {
            "agv_id": "uk_aisi", "name": "UK AI Safety Institute",
            "name_type": "former_official_en",
            "valid_from": "2023-11-02", "valid_to": "2025-02-14",
        }
    ]
    # Candidate uses old name and proposes a different (verified) entity_type
    cand = _candidate(
        agv_id="uk_ai_safety_institute",
        name_en="UK AI Safety Institute",
        entity_type="treaty_body",  # differs from verified canonical value
    )
    report = _differ(canonical=[canon], history=name_history).diff([cand])
    assert len(report.renames) == 1
    # And the conflicting proposal should land as a conflict on uk_aisi
    assert any(c.agv_id == "uk_aisi" and c.field_name == "entity_type"
               for c in report.conflicts)


def test_unmatched_former_name_ignored():
    canon = _canonical(agv_id="other", name_en="Other")
    name_history = [
        {
            "agv_id": "other", "name": "Previous Name",
            "name_type": "former_official_en",
            "valid_from": "2020-01-01", "valid_to": "2022-01-01",
        }
    ]
    cand = _candidate(agv_id="completely_new", name_en="Completely New")
    report = _differ(canonical=[canon], history=name_history).diff([cand])
    assert report.renames == []
    assert len(report.new_venues) == 1


def test_current_official_name_does_not_trigger_rename():
    """Only `former_official_en` rows participate in rename detection.

    It is still the same venue, though, so it must not be proposed as new —
    it matches by name instead. This test previously asserted the opposite,
    which is how the 2026-09-07 run came to propose the ASEAN guide, the UN
    scientific panel and the UN global dialogue as new venues alongside the
    rows they already are.
    """
    canon = _canonical(agv_id="existing", name_en="Existing Venue")
    name_history = [
        {
            "agv_id": "existing", "name": "Existing Venue",
            "name_type": "official_en",
            "valid_from": "2020-01-01", "valid_to": "",
        }
    ]
    cand = _candidate(agv_id="different_id_same_name", name_en="Existing Venue")
    report = _differ(canonical=[canon], history=name_history).diff([cand])
    assert report.renames == []
    assert report.new_venues == []
    assert [m.matched_agv_id for m in report.name_matches] == ["existing"]


# ---- candidate omits a field ----

def test_empty_candidate_field_does_not_produce_diff():
    canon = _canonical(entity_type="igo_initiative")
    cand = _candidate(entity_type="")  # empty proposal
    report = _differ(canonical=[canon]).diff([cand])
    # No update proposed, no conflict either — empty candidate values skipped.
    assert not any(u.field_name == "entity_type" for u in report.unverified_updates)
    assert not any(c.field_name == "entity_type" for c in report.conflicts)


# ---- DiffReport serialization ----

def test_report_round_trips_to_dict():
    canon = _canonical()
    cand = _candidate(governance_modality_primary="research_monitoring")
    report = _differ(canonical=[canon]).diff([cand])
    d = report.as_dict()
    assert d["canonical_size"] == 1
    assert d["candidate_size"] == 1
    assert d["unverified_updates"][0]["field_name"] == "governance_modality_primary"
    # Ensure JSON-serializable
    import json
    json.dumps(d)


# ---- load_csv / rename-map edge cases ----

def test_load_csv_missing_file_returns_empty(tmp_path):
    from pipelines.diff import load_csv
    assert load_csv(tmp_path / "does_not_exist.csv") == []


def test_rename_map_skips_incomplete_rows():
    d = _differ(
        canonical=[_canonical(agv_id="x", name_en="X")],
        history=[
            # Missing name
            {"agv_id": "x", "name": "", "name_type": "former_official_en",
             "valid_from": "2020-01-01", "valid_to": "2022-01-01"},
            # Missing agv_id
            {"agv_id": "", "name": "Ghost", "name_type": "former_official_en",
             "valid_from": "2020-01-01", "valid_to": "2022-01-01"},
            # Not a former_official_en
            {"agv_id": "x", "name": "X Alias", "name_type": "alias",
             "valid_from": "", "valid_to": ""},
        ],
    )
    report = d.diff([_candidate(agv_id="ghost_id", name_en="Ghost")])
    # "Ghost" was skipped from rename_map due to missing agv_id → this is a new venue
    assert len(report.new_venues) == 1
    assert report.renames == []


def test_differ_from_paths_loads_csvs(tmp_path):
    from pipelines.diff import Differ
    canonical = tmp_path / "agv.csv"
    canonical.write_text(
        "agv_id,name_en,entity_type,governance_modality_primary,"
        "topic_focus_primary,geographic_scope,lead_actor_primary,"
        "legal_character,current_state,convening_frequency,"
        "last_observed_activity_date,human_verified_fields,override_policy\n"
        "t1,T1,igo_initiative,dialogue_coordination,ai_general,global,"
        "igo_secretariat,soft_law,active,continuous,"
        "2026-04-20,entity_type,lock_verified_only\n",
        encoding="utf-8",
    )
    history = tmp_path / "name_history.csv"
    history.write_text(
        "agv_id,name,name_type,valid_from,valid_to,source_url\n",
        encoding="utf-8",
    )
    d = Differ.from_paths(canonical, history, today=TODAY)
    assert d.canonical_rows[0]["agv_id"] == "t1"
    report = d.diff([])
    assert report.canonical_size == 1


# ---- CLI end-to-end ----

def test_diff_cli_produces_report_json(tmp_path, capsys):
    from pipelines.diff import main as diff_main
    canonical = tmp_path / "agv.csv"
    canonical.write_text(
        "agv_id,name_en,entity_type,governance_modality_primary,"
        "topic_focus_primary,geographic_scope,lead_actor_primary,"
        "legal_character,current_state,convening_frequency,"
        "last_observed_activity_date,human_verified_fields,override_policy\n"
        "t1,T1,igo_initiative,dialogue_coordination,ai_general,global,"
        "igo_secretariat,soft_law,active,continuous,"
        "2026-04-20,entity_type,lock_verified_only\n",
        encoding="utf-8",
    )
    history = tmp_path / "name_history.csv"
    history.write_text(
        "agv_id,name,name_type,valid_from,valid_to,source_url\n",
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        '[{"agv_row": {"agv_id": "t1", "name_en": "T1", '
        '"governance_modality_primary": "research_monitoring"}, '
        '"evidence_rows": [], "provenance": {}}]',
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    rc = diff_main([
        "--candidates", str(candidates),
        "--canonical", str(canonical),
        "--name-history", str(history),
        "--output", str(output),
        "--today", "2026-04-23",
        "--quiet",
    ])
    assert rc == 0
    import json
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["today"] == "2026-04-23"
    assert len(report["unverified_updates"]) == 1


def test_diff_cli_handles_jsonl_candidates(tmp_path):
    from pipelines.diff import main as diff_main
    canonical = tmp_path / "agv.csv"
    canonical.write_text(
        "agv_id,name_en,entity_type,convening_frequency,last_observed_activity_date,"
        "human_verified_fields,override_policy\n"
        "t1,T1,igo_initiative,continuous,2026-04-20,,lock_verified_only\n",
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        '{"agv_row": {"agv_id": "new_one", "name_en": "New One"}, '
        '"evidence_rows": [], "provenance": {}}\n',
        encoding="utf-8",
    )
    rc = diff_main([
        "--candidates", str(candidates),
        "--canonical", str(canonical),
        "--name-history", str(tmp_path / "does_not_exist.csv"),
        "--output", str(tmp_path / "r.json"),
        "--quiet",
    ])
    assert rc == 0
    import json
    r = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert len(r["new_venues"]) == 1


def test_diff_cli_empty_candidates_file(tmp_path):
    from pipelines.diff import main as diff_main
    canonical = tmp_path / "agv.csv"
    canonical.write_text(
        "agv_id,name_en,convening_frequency,last_observed_activity_date,"
        "human_verified_fields,override_policy\n",
        encoding="utf-8",
    )
    empty = tmp_path / "c.json"
    empty.write_text("", encoding="utf-8")
    rc = diff_main([
        "--candidates", str(empty),
        "--canonical", str(canonical),
        "--name-history", str(tmp_path / "nh.csv"),
        "--output", str(tmp_path / "r.json"),
        "--quiet",
    ])
    assert rc == 0


# ---- name matching (the same venue under a different id) ----

def test_name_match_survives_punctuation_and_case():
    """`agv_id` comes from whatever wording a source printed."""
    canon = _canonical(agv_id="iso_42001", name_en="ISO/IEC 42001")
    cand = _candidate(agv_id="iso_iec_42001", name_en="iso iec  42001")
    report = _differ(canonical=[canon]).diff([cand])
    assert report.new_venues == []
    assert [m.matched_agv_id for m in report.name_matches] == ["iso_42001"]


def test_an_alias_in_name_history_also_identifies_the_venue():
    canon = _canonical(agv_id="uk_aisi", name_en="UK AI Security Institute")
    history = [
        {
            "agv_id": "uk_aisi", "name": "AI Security Institute",
            "name_type": "alias", "valid_from": "2025-02-14", "valid_to": "",
        }
    ]
    cand = _candidate(agv_id="ai_security_institute", name_en="AI Security Institute")
    report = _differ(canonical=[canon], history=history).diff([cand])
    assert report.new_venues == []
    assert [m.matched_agv_id for m in report.name_matches] == ["uk_aisi"]


def test_a_name_two_rows_share_matches_neither():
    """Guessing between them would attach the proposal to the wrong venue."""
    a = _canonical(agv_id="venue_a", name_en="AI Advisory Body")
    b = _canonical(agv_id="venue_b", name_en="AI Advisory Body")
    cand = _candidate(agv_id="third_thing", name_en="AI Advisory Body")
    report = _differ(canonical=[a, b]).diff([cand])
    assert report.name_matches == []
    assert len(report.new_venues) == 1


def test_a_near_name_is_flagged_for_review_not_merged():
    """"Global Dialogue on AI Governance" vs "UN Global Dialogue on AI Governance".

    Close enough that a reviewer must look; not close enough for the differ
    to decide. It stays a new-venue proposal, carrying the pointer.
    """
    canon = _canonical(
        agv_id="un_global_dialogue", name_en="UN Global Dialogue on AI Governance",
    )
    cand = _candidate(
        agv_id="global_dialogue_on_ai_governance",
        name_en="Global Dialogue on AI Governance",
    )
    report = _differ(canonical=[canon]).diff([cand])
    assert report.name_matches == []
    assert len(report.new_venues) == 1
    assert [d["agv_id"] for d in report.new_venues[0].possible_duplicates] == [
        "un_global_dialogue"
    ]


def test_short_names_do_not_trigger_duplicate_warnings():
    """Two- and three-word names overlap far too easily to be a signal."""
    from pipelines.diff import looks_like_same_venue

    assert not looks_like_same_venue("AI Office", "EU AI Office")
    assert not looks_like_same_venue("G7", "G7 Hiroshima AI Process")
    assert looks_like_same_venue(
        "Global Dialogue on AI Governance", "UN Global Dialogue on AI Governance",
    )


def test_an_unrelated_venue_is_not_flagged_as_a_duplicate():
    canon = _canonical(agv_id="facct", name_en="ACM Conference on Fairness")
    cand = _candidate(agv_id="iso_42001", name_en="ISO IEC 42001 Management System")
    report = _differ(canonical=[canon]).diff([cand])
    assert report.new_venues[0].possible_duplicates == []
