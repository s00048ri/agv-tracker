# `tools/review/` — Local review UI for fetcher candidates

A small Flask app that consumes a `DiffReport` JSON (output of
`python -m pipelines.diff`) and lets the maintainer accept / refine /
reject / defer each candidate row before it gets written to canonical
CSVs. Implements the §4.7 reviewer workflow without requiring GitHub PR
round-trips during interactive review.

## Install

```bash
pip install -e '.[review]'        # adds Flask 3.x
```

## Workflow

```
fetchers → normalize → diff → report.json
                                  ↓
                  python -m tools.review.server report.json
                                  ↓
                       http://127.0.0.1:8765
                       [human review loop]
                                  ↓
                          decisions.json
                                  ↓
        python -m tools.review.apply_decisions decisions.json --report report.json --apply
                                  ↓
              data/agv.csv + agv_evidence.csv + agv_lifecycle.csv
                                  ↓
                       git commit + PR
```

## Running the server

```bash
python -m tools.review.server path/to/report.json \
    --decisions decisions.json \
    --reviewer s00048ri \
    --port 8765
```

Open <http://127.0.0.1:8765/> in the same browser as `npm run dev` so you
can flip between the review form and a live preview of the candidate's
`primary_reference_url`.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `a` | Accept (LLM classification as-is) |
| `e` | Save edits (write your overrides) |
| `r` | Reject |
| `d` | Defer |
| `j` / `↓` | Next candidate |
| `k` / `↑` | Previous candidate |

### Per-category semantics

| Category | Display | Outcomes |
|---|---|---|
| **new_venues** | Full editable row with enum dropdowns | accept / edit / reject / defer |
| **unverified_updates** | Diff: existing → proposed | accept / edit / reject / defer |
| **conflicts** | Diff + 3-way §4.7 choice (`keep_human` / `accept_llm` / `note_evolution`) | accept (with choice) / edit / reject / defer |
| **stale_candidates** | Convening-frequency-aware staleness data | accept (→ dormant) / reject (false positive) / defer |
| **renames** | Existing name vs candidate name | accept (rewrites `agv_name_history.csv`) / reject / defer |

### Decisions are persisted continuously

Every action POSTs to `/api/decision`, which writes `decisions.json`
atomically. You can close the browser, restart the server, and resume
mid-stream — decisions for the current `report_id` are loaded back in.

If the file's `report_id` doesn't match the loaded report, it is
discarded (you can't accidentally apply a stale decision file).

## Applying decisions

```bash
# Dry-run first
python -m tools.review.apply_decisions decisions.json --report report.json

# Then commit
python -m tools.review.apply_decisions decisions.json --report report.json --apply
```

The applier:

- Appends `new_venues` to `data/agv.csv` with `human_verified_fields` set
  to the four `confidence_*` fields, `override_policy=lock_verified_only`,
  and four `human_verification` evidence rows.
- Mutates `data/agv.csv` for `unverified_updates` (and adds the field to
  `human_verified_fields` if it's one of the four tracked).
- Mutates `data/agv.csv` for `conflicts` with `conflict_choice=accept_llm`
  / `note_evolution`; emits an evidence row in all three cases (including
  `keep_human` — the trail records that you reviewed the conflict).
- Transitions `current_state → dormant` and emits a lifecycle row for
  accepted `stale_candidates`.
- Rewrites `data/agv_name_history.csv` for accepted `renames`: closes the
  prior `official_en` with today's `valid_to` and renames it to
  `former_official_en`; appends a new `official_en` row.

Every accept / edit / conflict resolution produces an
`agv_evidence.csv` row with `source_type='human_verification'`.

## After applying

```bash
python3 scripts/generate_venue_pages.py
python3 scripts/generate_coverage_matrix.py
uv run pytest tests/ -q
git add -A
git commit -m "data: monthly review YYYY-MM (NN accepted, M rejected)"
```

## File layout

```
tools/review/
├── __init__.py
├── schema.py              # AGVO enums + decision validation
├── server.py              # Flask app
├── apply_decisions.py     # decisions.json → canonical CSVs
├── templates/
│   └── review.html        # Single-page UI (vanilla JS)
└── README.md
```

## Tests

```bash
uv run pytest tests/test_review_apply.py -q
```

Covers:

- enum parity with `tests/test_schema.py` (drift fails the build)
- decision validation (unknown categories, unknown enums, missing
  conflict choice)
- each (category × action) path produces the correct CSV deltas
- idempotency (double-accept raises)
- `flatten_report` ordering and decision-key shape
