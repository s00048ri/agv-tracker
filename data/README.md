# `data/` — Schema reference (AGVO v0.3)

Canonical, version-controlled AGV dataset. Five CSV files, one relational model.
Authoritative spec lives in `CLAUDE.md §3, §4`. This file is the operational
summary for people editing the data.

| File | Rows as of migration | Primary key | Purpose |
|---|---:|---|---|
| `agv.csv` | 30 | `agv_id` | Master AGV records |
| `agv_relation.csv` | 3 | (source, target, type, start_date) | Inter-venue relations (canonical direction only) |
| `agv_evidence.csv` | 120 | (agv_id, field_name, source_url, accessed_at) | Per-field source attribution |
| `agv_name_history.csv` | 2 | (agv_id, name, name_type, valid_from) | Renamings and aliases |
| `agv_lifecycle.csv` | 35 | (agv_id, transition_date, to_state) | State transition event log |

Schema invariants are enforced by `tests/test_schema.py` (structural) and
`tests/test_evidence.py` (evidence discipline). Run with `uvx pytest tests/`.

## `agv.csv`

One row per AGV. See CLAUDE.md §4.2 for the full column list. Key v0.3 columns:

- **Dates + precision** — `founded_date` is always stored as ISO 8601; the
  truthful grain is given by `founded_date_precision` (`day` | `month` | `year`).
  Month-only dates are `YYYY-MM-01`; year-only dates are `YYYY-01-01`.
- **`establishment_basis`** — what the date means: `announced` |
  `first_meeting` | `formally_constituted` | `first_output`.
- **`last_observed_activity_date`** — most recent confirmed activity. **Drives
  stale detection (§3.5).** Not the same as `last_verified_date` (which records
  when the maintainer last reviewed the row itself).
- **Four field-level `confidence_*` columns** — `high`/`medium`/`low`. Each must
  have ≥1 corresponding row in `agv_evidence.csv` (§4.8).
- **`human_verified_at` + `human_verified_fields`** — comma-separated field
  names verified by a human. Non-empty `human_verified_fields` requires a
  non-null `human_verified_at` AND a `source_type='human_verification'`
  evidence row per listed field.
- **`override_policy`** — `lock_verified_only` (default) | `lock_all` |
  `allow_llm_update`. Controls what the monthly LLM re-run may touch (§4.7).

Removed since v0.1: `absorbed_into`, `succeeds` (now relations), row-level
`confidence` (replaced by per-field).

## `agv_relation.csv`

Inter-venue relations, **stored in one canonical direction only** per §3.7.
Reverse views (`child_of`, `succeeded_by`, etc.) are computed at display time.

Relation types: `parent_of`, `succeeds`, `absorbed_into`, `coordinates_with`,
`references_principles_of`, `convenes_within`, `member_of`.

Invariant: if `current_state ∈ {absorbed, succeeded}` in `agv.csv`, there must
be ≥1 relation row that references the AGV.

## `agv_evidence.csv`

Per-field source attribution. One row per `(agv_id, field_name, source_url,
accessed_at)`.

- `source_type` values include `official_site`, `founding_document`,
  `press_release`, upstream registries (`oecd_navigator`, `iapp_tracker`,
  `unesco_gaigo`), plus the two migration-relevant ones:
  - `human_verification` — human reviewer confirmed the field. `reviewer` =
    GitHub handle.
  - `llm_classification` — LLM classifier output. `source_url` =
    `internal://classifier-run/{run_id}`, `reviewer` = model version string
    (e.g. `claude-sonnet-4-7`), `evidence_note` = classifier rationale.
- Field-level confidence in `agv.csv` reflects the **highest-confidence**
  evidence row for that field.

## `agv_name_history.csv`

Tracks renamings. The diff pipeline (Task 6) consults this before treating an
apparent new AGV as truly new.

- At most one row per `agv_id` may have `name_type='official_en'` AND
  `valid_to=NULL` (the current name).
- `valid_from < valid_to` when both are set.

## `agv_lifecycle.csv`

Append-only state transition log. Every AGV has an initial
`(NULL → active, founded_date)` row (seeded by v0.3 migration). Subsequent
transitions record movement through §3.5 states: `announced`, `active`,
`dormant`, `absorbed`, `terminated`, `succeeded`.

## Editing discipline (§8.3, §8.6)

1. Edit via pandas or a CSV-aware editor — never hand-type rows containing
   commas/newlines/quotes in plain text.
2. Every data change requires:
   - The change itself in the canonical table.
   - Evidence row(s) for any field with a `confidence_*` column.
   - Name history row if renaming.
   - Lifecycle row if state transition.
   - For human verification: update `human_verified_fields` and
     `human_verified_at` in `agv.csv` AND add a
     `source_type='human_verification'` evidence row.
3. Run `uvx pytest tests/` before committing.
4. One logical change per commit (`data: add 12 industry consortia`, not
   `data: updates`).
