# AGV Tracker — Runtime Changelog

Runtime data/decisions accepted into the repository. Spec revisions are tracked
in `CLAUDE.md §0`.

## 2026-04-23

- **data**: migrated 30-AGV seed from v0.1 → v0.3 schema (Task 2). Split into
  `agv.csv` + `agv_relation.csv` (3) + `agv_evidence.csv` (120) +
  `agv_name_history.csv` (2) + `agv_lifecycle.csv` (35); reclassified FAccT and
  AIES as `standalone_governance_conference`; renamed UK AISI to "UK AI Security
  Institute" with former name preserved; all 30 rows marked
  `human_verified_fields=entity_type,founded_date,current_state,legal_character`
  with `override_policy=lock_verified_only`.
