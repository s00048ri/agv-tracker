# AGV Hand-Coding Manual

**Purpose**: how-to guide for the human reviewer classifying AGV candidates.
Use alongside the field reference in `docs/codebook.md`.

**Audience**:
- The maintainer (Ren) doing monthly reviews.
- Future collaborators who haven't read CLAUDE.md cover-to-cover.

**Promise**: After reading this manual + the codebook, a coder should
reach the same classification as the maintainer on ≥80% of candidates
within 5 minutes per row.

---

## 1. Workflow at a glance

```
1. Monthly fetcher run produces report.json (308 new / 19 update /
   9 conflict / 22 stale candidates is typical).
2. Launch the review UI:
       python -m tools.review.server report.json --reviewer <your-handle>
3. For each candidate (1 row ≈ 1 minute target):
       (a) Read the candidate card.
       (b) Open primary_reference_url in the iframe.
       (c) Decide: Accept / Edit / Reject / Defer.
       (d) For conflicts: pick one of three §4.7 resolutions.
4. When done, apply:
       python -m tools.review.apply_decisions decisions.json \\
           --report report.json --apply
5. Regenerate site artifacts:
       python3 scripts/generate_venue_pages.py
       python3 scripts/generate_coverage_matrix.py
6. Run tests, commit, push.
```

Aim for **≤30 s/row average** on routine `accept`s; spend more time on
edits, conflicts, and gray-zone classifications.

---

## 2. Before you start: orient yourself

### What's in front of you

Each candidate falls into one of five categories. The UI color-codes them:

| Category | UI color | What you're deciding |
|---|---|---|
| **new_venues** (green) | green | Should this become a new row in `agv.csv`? With what classification? |
| **unverified_updates** (blue) | blue | Has the value of this field changed for an existing AGV? |
| **conflicts** (red) | red | The LLM disagrees with a *human-verified* value. Who's right? |
| **stale_candidates** (yellow) | yellow | This AGV hasn't shown activity in N months. Still active? |
| **renames** (purple) | purple | This candidate seems to be an existing AGV under a new name. |

### Ground rules

- **Read the primary_reference_url before deciding** for `new_venues` and
  `conflicts`. The iframe loads it side-by-side; one mouse-over typically
  resolves the call.
- **When uncertain, defer.** A deferred row re-surfaces in the next monthly
  cycle, so deferring is cheap. A wrong `accept` enters canonical data.
- **Comment when you edit or resolve a conflict.** Future-you will thank
  present-you when looking at the evidence trail.
- **Never invent**. If the primary_reference_url doesn't say it, don't
  claim it. Lower confidence instead.

---

## 3. Deciding the six classification dimensions

The full list of values for each dimension is in `docs/codebook.md §3.2`.
This section gives **decision rules** for the cases that recur.

### 3.1 `entity_type` — the big one

This is the highest-stakes classification because nearly every other field
flows from it. Use this decision tree:

```
Q1. Is the venue a SINGLE EVENT (not recurring under one mandate)?
    YES → one_off_summit              (Asilomar 2017, Bletchley 2023)
    NO  → continue.

Q2. Is the venue a RECURRING CONFERENCE?
    YES, entire scope is AI governance/ethics/safety/accountability with
         its own organizing committee → standalone_governance_conference (FAccT)
    YES, but it's a track WITHIN a broader conference → conference_policy_track
                                                       (NeurIPS ML Safety)
    YES, commercial / sponsorship-driven → industry_conference (CogX)
    NO  → continue.

Q3. Does it operate under a BINDING international instrument?
    YES → treaty_body                 (CoE AI Convention Committee, EU AI Board)
    NO  → continue.

Q4. Is it a WORKING GROUP within a recognized standards body?
    YES → standards_body_wg           (ISO SC 42, IEEE P7001, ITU FG-AI4H)
    NO  → continue.

Q5. Is it a state-to-state forum (members are GOVERNMENTS)?
    YES → intergov_forum              (G7 Hiroshima Process, QUAD)
    NO  → continue.

Q6. Is it run by an IGO SECRETARIAT (UN/OECD/UNESCO/ITU/CoE/etc.)?
    YES → igo_initiative              (OECD.AI, UNESCO AI Ethics)
    NO  → continue.

Q7. Is it a NATIONAL agency with international coordination role?
    YES → national_regulator_intl     (UK AISI, EU AI Office, France CNIL AI)
    NO  → continue.

Q8. Genuine multistakeholder (≥3 sectors with formal seats)?
    YES → multistakeholder_coalition  (Partnership on AI, GPAI)
    NO  → continue.

Q9. Industry-led standing body?
    YES → industry_consortium         (Frontier Model Forum, MLCommons)
    NO  → continue.

Q10. Cross-institutional ACADEMIC body?
    YES → academic_consortium         (ELLIS, CIFAR AI Strategy)
    NO  → intl_ngo_thinktank          (Future of Life, CAIDP, Ada Lovelace)
```

**Tie-breakers** when two values both seem to fit:

- `igo_initiative` vs `treaty_body`: does the venue operate a **binding**
  instrument? Treaty body. Otherwise IGO initiative.
- `industry_consortium` vs `multistakeholder_coalition`: are there formal
  civil-society or government seats? If yes (and ≥3 sectors), coalition.
- `intl_ngo_thinktank` vs `academic_consortium`: is membership composed
  of universities/labs (academic) or 501(c)(3)-style NGOs (think tank)?
- `national_regulator_intl` vs `igo_initiative`: who's the legal entity
  behind it? A national government → regulator. An IGO → initiative.

### 3.2 `governance_modality_primary`

What does the venue **actually produce**? Read the venue's "about" page
or charter and ask: what's the output?

- Publications, principles, declarations → `declaration_principles`
- Regulations, statutes, binding rules → `binding_instrument`
- ISO/IEEE-style standards → `technical_standards`
- Benchmarks, evals, audits → `evaluation_benchmarking`
- Training programs, technical assistance → `capacity_building`
- Research outputs, reports, datasets → `research_monitoring`
- Convening, dialogue, coordination meetings → `dialogue_coordination`
- Enforcement actions, fines, market surveillance → `regulatory_enforcement`

**When a venue does several things**: pick the one its founding mandate
emphasizes. If that's still ambiguous, pick the one its most recent year of
outputs is dominated by. Use `governance_modality_secondary` only when the
secondary is ≥30% of activity.

### 3.3 `topic_focus_primary`

Use the **most specific applicable** value, not the broadest. A frontier-AI
safety institute is `safety_frontier`, not `ai_general`, even though it
arguably covers all AI.

Default escalation: specific domain (`domain_health`) → topic
(`safety_frontier`) → `ai_general`. Drop to `ai_general` only for genuinely
cross-cutting bodies.

### 3.4 `geographic_scope`

Decision rule:

```
Members from ≥4 contiguous-region clusters or universal mandate → global
Members spanning multiple non-adjacent regions, but not universal → transregional
Members within ONE regional bloc                                  → regional (set region_code)
Named plurilateral group (G7/G20/QUAD/BRICS)                      → plurilateral
2-3 named countries                                                → bilateral_plus
```

**Edge cases**:

- A "global" venue with predominantly North-Atlantic membership is still
  `global` *if* its mandate is universal. Code geographic scope by mandate
  + open membership, not by current participant geography.
- National AISI in the international AISI Network: `global` (network role
  is global), `region_code` blank.

### 3.5 `lead_actor_primary`

Look at:
1. **Who holds the secretariat / hosts the staff?**
2. **Who chairs?**
3. **Who funds the core operations?**

If 2 of 3 are the same sector, that's the lead actor.

**Multistakeholder gotcha**: a venue *typed* as `multistakeholder_coalition`
isn't automatically `lead_actor=hybrid_mso`. Check formal governance:

- Secretariat at an IGO → `igo_secretariat`
- Secretariat at a national agency → `state_govt`
- Genuine balanced board with no single sector having veto → `hybrid_mso`

### 3.6 `legal_character`

Three quick tests:

1. **Can the venue impose sanctions or penalties on non-compliance?** Yes →
   `hard_law`. No → continue.
2. **Does it produce a mix of binding and non-binding instruments?** Yes →
   `mixed`. No → continue.
3. **Does it produce normative output at all (declarations, codes, standards)?**
   Yes → `soft_law`. No → `n/a`.

⚠ **Standards body trap**: an ISO/IEEE standard is *voluntary* unless
incorporated into law somewhere. Standards bodies default to `soft_law`.
Mark `hard_law` only when the standard is itself a binding instrument
(rare — most are incorporated by reference into regulation, not by their
own force).

⚠ **Research org / conference / think tank**: usually `n/a`. They produce
research outputs, not normative instruments.

---

## 4. Confidence ratings

Each of the four confidence-tracked fields gets one of three values.

| Rating | Use when | Example |
|---|---|---|
| `high` | Multiple independent sources agree; no plausible alternative. | UK AISI's founding date (Nov 2023, announced + multiple news outlets + official site) |
| `medium` | One source confirms, OR multiple sources with minor inconsistency, OR plausible inference from indirect evidence. | A venue's `legal_character` when the official site doesn't say but mandate implies it. |
| `low` | Ambiguous, weakly supported, or surfaced from a discovery source only. | An ECOWAS WG's `founded_date` when only press mentions exist. |

**Rule of thumb**: if you'd accept a `low`-confidence row into the dataset
right now, you should be willing to defend it under a 30-second
challenge. If not, defer.

Field-level confidence sets the **maximum** confidence of any
human_verification evidence row you emit. Don't claim `high` confidence
in `agv.csv` if your evidence rows are `medium`.

---

## 5. §4.7 Conflict resolution

When the LLM proposes a value that disagrees with a **human-verified**
value, the UI surfaces it as a **conflict** and asks you to pick one of
three resolutions.

### The three choices

| Choice | UI label | What it does | When to use |
|---|---|---|---|
| (a) | `keep_human` | Preserves the existing human value. Logs an evidence row noting that you reviewed the conflict. | The LLM is wrong / mistaken. Classifier drift or misinterpretation of a recent press release. |
| (b) | `accept_llm` | Overwrites canonical with the LLM's proposal. Updates `human_verified_at` to today. | You agree the value has changed and the LLM's reading is correct. |
| (c) | `note_evolution` | Same as (b), plus appends a timestamped note to `agv.csv.notes` explaining the evolution. | The venue genuinely evolved (e.g., a coalition restructured). You want a trail. |

### Decision tree

```
Q1. Does the LLM-proposed source actually say what the LLM claims?
    NO  → keep_human. Comment: "LLM misread source."
    YES → continue.

Q2. Has the underlying venue actually changed since the human-verified date?
    NO  → keep_human. Comment: "Source updated but venue itself unchanged."
    YES → continue.

Q3. Is the change a normal evolution worth recording?
    YES → note_evolution. Comment: brief description of the change.
    NO  → accept_llm. Comment: "LLM proposal validates updated reality."
```

**Watch for**: more than 5% of reviewed rows being conflicts (the §4.7
target). If you're routinely hitting >5%, either the classifier has drifted
(re-prompt) or the venue population is genuinely churning (note it for the
companion paper).

---

## 6. Stale candidates

The diff pipeline applies dynamic thresholds by `convening_frequency`:

| Frequency | Stale if `today - last_observed_activity_date` ≥ |
|---|---|
| `continuous` | 6 months |
| `annual` | 18 months |
| `biennial` | 30 months |
| `ad_hoc` | 24 months |
| `one_off` | **never flagged** |

### What "accept" means here

Accepting a stale candidate **transitions** `current_state` from
`active` → `dormant` and appends a lifecycle row. It does **not** mean
"yes, this is stale and we should drop the venue." Dormancy is a
recoverable state.

### Decision tree

```
Q1. Is the venue clearly dead or permanently disbanded?
    YES → accept (→ dormant) + add a follow-up note to consider transitioning
          to `terminated` in a future cycle once the death is confirmed.
    NO  → continue.

Q2. Did the venue meet recently in a way the LOA date missed?
    YES → reject (false positive). Update last_observed_activity_date in a
          subsequent edit pass.
    NO  → continue.

Q3. Genuine slow cadence or genuine inactivity?
    Slow but real    → reject (false positive).
    Apparently inactive → accept (→ dormant).
    Unsure           → defer.
```

**Defer is the safe default** for ambiguous staleness.

---

## 7. Renames

A rename is detected when a candidate's `name_en` matches a
`former_official_en` entry in `agv_name_history.csv`. The UI shows both
the candidate name and the matched existing AGV.

### What "accept" means here

Accept rewrites `agv_name_history.csv`:

1. The existing `official_en` row gets `valid_to=today` and is reclassified
   as `former_official_en`.
2. A new `official_en` row is appended with the candidate's name and
   `valid_from=today`.
3. `agv.csv.name_en` is updated.

### Decision rules

- Confirm via the candidate's `primary_reference_url` that the venue
  itself uses the new name on its official site.
- If the new name is only an informal nickname (the "AI Safety Institute"
  for "UK AISI"), prefer `alias` over a rename. Reject the candidate as a
  rename and add an `alias` row manually instead.
- If the venue itself uses both names (transitional period), defer.

---

## 8. Edge cases and recurring traps

### 8.1 "Is this even an AGV?"

When the fetcher surfaces a candidate that looks tangential:

```
Q1. Is there a clear AI-governance mandate (primary or substantial 30%+ secondary)?
    NO  → reject. Comment: "out of scope: <reason>".
    YES → continue.

Q2. International scope OR network-membership AI role?
    NO  → reject. Comment: "national-only with no international role".
    YES → continue.

Q3. Is the candidate a member of an existing AGV (should be in agv_relation, not agv.csv)?
    YES → reject. Open an issue to add a `member_of` relation instead.
    NO  → continue.

Q4. Is the candidate a press release / news article about a venue?
    YES → reject. The fetcher uses these as discovery signals; the venue
          itself (if not already in dataset) belongs as a separate candidate.
    NO  → accept / edit.
```

### 8.2 National AISIs and the AISI Network

Each national AISI has its own row (`uk_aisi`, `us_aisi`, `japan_aisi`,
`korea_aisi`, etc.) AND there's a separate row for the network itself
(`aisi_network`). Each national AISI has a `member_of` relation to
`aisi_network`.

⚠ Geographic scope: code each national AISI as `global` (their network
role is global), not `regional`.

### 8.3 Working groups within standards bodies

For ISO/IEC SC 42: we have both the SC itself (`iso_iec_sc42`) and
named sub-WGs (`iso_sc42_wg1`, ..., `iso_sc42_wg5`). Each sub-WG has a
`parent_of` relation from the SC.

Don't add every ad hoc working group. Add named sub-WGs that publish
their own output stream.

### 8.4 Summit series

```
Edition 1 (Bletchley 2023)     → one_off_summit row
Edition 2 (Seoul 2024)         → one_off_summit row
Edition 3 (Paris 2025)         → one_off_summit row
```

Once the series has held ≥2 editions under one mandate, you may **also**
create an `intergov_forum` row for the umbrella series (e.g., "AI Action
Summit series"). Don't merge editions — each summit retains its
historical row.

### 8.5 Workshops with shifting names

NeurIPS holds different safety workshops each year (sometimes ML Safety
Workshop, sometimes Responsible AI). When the fetcher catches yearly
variants:

- If there's an **organizing-committee continuity** across editions, treat
  them as one AGV (current `neurips_ml_safety` covers this).
- If they're genuinely independent workshops, code each as its own
  `conference_policy_track` row.

In the `notes` field of any such row, write: `"Workshop name varies year
to year; same organizing committee."`

### 8.6 Industry consortia with minimal substance

A consortium that has only a press release and no further activity is
borderline. Apply the §12.1 threshold: **at least one of**

- Published output (white paper, technical report, benchmark)
- ≥3 named member commitments with detail
- ≥1 working session held

If none of these, **defer** (not reject — they may operationalize within
the next cycle).

### 8.7 Workstreams of a parent venue

When a venue announces a "working group on X" within a larger venue:

- If the WG has its own output stream and identifiable structure → its own
  row with `parent_of` relation from the parent venue. (See
  `gpai_data_gov_wg`, `gpai_rai_wg`.)
- If it's just a name on an org chart → no separate row. Capture in the
  parent venue's `notes` if relevant.

### 8.8 "We made a typo"

The `agv_id` is immutable. If you typo'd an `agv_id` and committed it,
do **not** try to "rename" it in-place. Add a new row with the correct
ID and mark the old as `current_state=terminated` with a lifecycle row.
Move evidence/lifecycle rows manually.

(In practice, this happens during initial seeding; in normal operation,
the review UI uses IDs from the candidate stream, not free-text.)

---

## 9. Reviewer signature and audit trail

Every action you take in the UI produces audit evidence:

- An entry in `decisions.json` with action, comment, timestamp,
  reviewer handle.
- After `apply_decisions.py --apply`, an `agv_evidence.csv` row with
  `source_type='human_verification'` and your GitHub handle as
  `reviewer`.

This means:

- **Your handle goes on every cell you touched.** Future you / future
  collaborators can see exactly who verified what.
- **Don't share a handle.** If multiple people review, each uses their
  own GitHub handle.
- **Don't impersonate the LLM.** `source_type='llm_classification'` is
  reserved for automated runs. Your edits are always `human_verification`.

---

## 10. After the review

Once you've worked through the queue:

```bash
# Dry-run first — sanity check what's about to happen
uv run python -m tools.review.apply_decisions decisions.json \\
    --report report.json

# Apply for real
uv run python -m tools.review.apply_decisions decisions.json \\
    --report report.json --apply

# Regenerate site artifacts
python3 scripts/generate_venue_pages.py
python3 scripts/generate_coverage_matrix.py

# Verify invariants
uv run pytest tests/ -q

# Commit
git add data/ src/venues/ sources/coverage_matrix.md CHANGELOG.md
git commit -m "data: monthly review YYYY-MM (N accepted, M rejected, K conflicts resolved)"
```

Then append a line to `CHANGELOG.md` summarizing the run. The line should
include: number accepted, rejected, deferred; any noteworthy conflicts;
unusual stale-detection outcomes.

---

## 11. Tooling glossary

| Tool | What it does |
|---|---|
| `pipelines/diff.py` | Produces `report.json` from candidate JSON. Implements §4.7 + §3.5 logic. |
| `tools/review/server.py` | Flask UI; `python -m tools.review.server report.json` |
| `tools/review/apply_decisions.py` | Writes decisions back to canonical CSVs. |
| `scripts/generate_venue_pages.py` | Per-AGV detail page generator (regenerate after data edits). |
| `scripts/generate_coverage_matrix.py` | Recomputes `sources/coverage_matrix.md`. |
| `tests/test_schema.py`, `tests/test_evidence.py` | Invariant tests. **Must pass before commit.** |

---

## 12. Quick reference card

Print this and keep it next to the keyboard.

```
KEYBOARD SHORTCUTS
  a  Accept    e  Save edits    r  Reject    d  Defer
  j / ↓  Next     k / ↑  Previous

WHEN TO DEFER (vs reject):
  - You don't yet have time to verify.
  - The primary_reference_url is down right now.
  - The venue might exist but you can't tell.

WHEN TO REJECT (vs defer):
  - Confirmed out of scope.
  - Confirmed not a venue (member, press release, news article).
  - Confirmed false positive.

CONFLICT (red) RESOLUTIONS:
  (a) keep_human       LLM is wrong.
  (b) accept_llm       Venue changed; LLM is right.
  (c) note_evolution   Venue evolved; record the transition.

STALE (yellow) RESOLUTIONS:
  Accept  →  current_state becomes 'dormant'.
  Reject  →  False positive; venue is actually still active.
  Defer   →  Re-evaluate next cycle.

CONFIDENCE THRESHOLDS:
  high    Multiple independent sources agree.
  medium  Single source, OR minor inconsistency, OR inference.
  low     Weakly supported; flagged for re-review.

NEVER:
  - Invent a value the source doesn't say.
  - Overwrite a human-verified field silently (the UI won't let you anyway).
  - Skip evidence rows.
  - Commit if tests are red.
```

---

## See also

- `docs/codebook.md` — field reference with all enum values.
- `tools/review/README.md` — UI installation and full workflow.
- `CLAUDE.md §3, §4` — authoritative spec.
- `sources/coverage_matrix.md` — current coverage gaps; informs what
  to prioritize when reviewing new candidates.
