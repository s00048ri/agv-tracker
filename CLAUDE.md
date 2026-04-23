# CLAUDE.md — AGV Tracker

**Project**: A static web tracker for **AI Governance Venues (AGVs)** — international organizations, intergovernmental fora, multistakeholder coalitions, standards bodies, recurring conferences, and one-off summits whose mandate addresses AI governance.

**Goal**: Empirically document the quantitative proliferation of the AI governance ecosystem since 2015, present it as a public web dashboard with full source attribution, and update it monthly.

**Owner**: Ren Iida (GPAI Tokyo Centre / NICT)
**Stage**: v0.3 spec — supersedes v0.2 after second-round external review.
**Stack**: Observable Framework (static site) + Python ETL + GitHub Actions + Cloudflare Pages

---

## 0. Changelog

### v0.3 changes (this revision) — operational hardening
Incorporates a second-round external review focused on operational and implementation risks. Key changes:

1. **Human-in-the-Loop is now a first-class concept** (§3.6, §4.2): `agv.csv` gains `human_verified_at`, `human_verified_fields`, `override_policy` columns. The `diff.py` pipeline must respect these flags so that monthly LLM re-runs cannot silently overwrite human-verified values.
2. **Conflict resolution rules** (§4.7, NEW section): when LLM re-classification disagrees with a human-verified value, the diff pipeline must surface a `conflict` (not silently skip, not silently overwrite) so that genuine venue evolution is not missed.
3. **Stale detection is now `convening_frequency`-aware** (§3.5): a uniform 6-month threshold mass-produces false positives for annual conferences and treaty bodies. The threshold table makes this explicit; `one_off` venues are excluded from stale detection entirely.
4. **Fetcher robustness — Playwright fallback** (§9 Task 4): the spec now mandates that fetchers must first attempt static HTTP, then fall back to a headless browser (Playwright) when the target is a SPA. `playwright` is added as an optional Python dependency.
5. **Inclusivity metrics deferred to v0.4+** (§12 Open Decisions): a future axis for measuring linguistic and Global South participation diversity, captured as a candidate but explicitly out of scope for v0.3 to protect the v1.0 launch timeline.
6. **CHANGELOG file separation**: `CHANGELOG.md` is now reserved for runtime data/decisions; this `CLAUDE.md §0` records spec versions only.

### v0.2 changes (previous revision) — architectural overhaul
1. Source architecture stratified into three layers (`discovery` / `verification` / `background`) with binding rules (§5).
2. Source coverage matrix as mandatory deliverable (§5.4).
3. Ontology — entity_type revised: `standalone_governance_conference` added (FAccT, AIES); `conference_policy_track` reserved for genuine within-conference tracks (§3.3).
4. Date precision and establishment basis added (§3.2).
5. Schema — new `agv_evidence.csv` table for per-field source attribution (§4.4).
6. Schema — new `agv_name_history.csv` for renamings (§4.5).
7. Schema — `absorbed_into` and `succeeds` removed from `agv.csv` (relation table is canonical) (§3.5).
8. Field-level confidence ratings (§4.2).
9. Dashboard — three sensitivity views (§6.2).
10. Launch criteria revised to entity-class coverage (§10).

---

## 1. How to use this document

This `CLAUDE.md` is the entry point for any Claude Code session on this project.

Before starting any task:
1. Read this file in full.
2. Read `data/README.md` (data schema reference) if touching data.
3. Read `pipelines/README.md` (ETL conventions) if touching pipelines.
4. Read `sources/README.md` (source registry) if touching sources or fetchers.
5. Check `CHANGELOG.md` for recent runtime decisions and accepted PRs.
6. Pick the lowest-numbered open task from §9 and follow its completion criteria.

Hard rules:
- Do **not** bypass the AGVO ontology by adding ad-hoc fields to `agv.csv`. If a new dimension is needed, propose an ontology extension in a GitHub issue first; do not edit the schema unilaterally.
- Do **not** auto-classify new venues without recording (a) the prompt used, (b) the model version, (c) the rationale, and (d) a per-field confidence rating in `agv_evidence.csv`.
- Do **not** treat a discovery source as a primary reference. `primary_reference_url` must point to a verification source (§5.2).
- Do **not** overwrite `human_verified_fields` values via LLM re-runs (§4.7); surface conflicts to a PR instead.
- Do **not** commit secrets; use GitHub repository secrets for API keys.

---

## 2. Project context

### 2.1 Why this exists
The AI governance landscape has grown from a handful of venues in 2015 to several hundred today, but no consolidated, version-controlled dataset of these venues exists. Existing partial trackers — OECD.AI Policy Navigator (national policies), IAPP (laws), UNESCO GAIGO (country profiles), Stanford AI Index (legislation counts) — each cover slices but none focuses on the **population dynamics of the venues themselves**.

This project fills that gap with:
- A structured ontology (AGVO v0.3) that handles the heterogeneity of venue types.
- A version-controlled CSV dataset under Git, with full evidence trail and human-verification audit log.
- A static web frontend with charts, search, per-venue pages, and source links.
- A monthly automated update cycle that opens Pull Requests for human review, never overwriting human-verified values silently.

### 2.2 Theoretical framing
Informed by:
- **Organizational ecology** (Hannan & Freeman 1977, 1989): population-level birth/death rates, density dependence, legitimation effects.
- **Regime complex theory** (Keohane & Victor 2011): governance via loosely-coupled overlapping institutional clusters.
- **Issue evolution** (Carmines & Stimson 1989): emergence → politicization → entrenchment.

These frames make the venue population itself a measurable, theoretically meaningful object — not just a directory.

### 2.3 Audience
- Primary: AI governance researchers, policymakers, GPAI / OECD / UN community.
- Secondary: data journalists, civil society analysts.
- Output target: public web dashboard + SSRN companion paper *"Mapping the Proliferation of International AI Governance Venues, 2015–2026."*

---

## 3. The AGVO Ontology v0.3

### 3.1 Core entity definition

An **AGV (AI Governance Venue)** is any organized forum, body, initiative, coalition, standards working group, or recurring/one-off convening whose mandate includes — as a primary or substantial secondary purpose — the governance, oversight, coordination, or norm-setting of AI technologies.

The term **venue** deliberately spans:
- continuous organizations (OECD.AI, UK AI Security Institute),
- recurring fora with no standing secretariat (G7 Hiroshima Process working sessions),
- standalone recurring governance conferences (FAccT, AIES),
- standards working groups (ISO/IEC JTC 1/SC 42, IEEE P7000 series),
- one-off convenings producing durable outputs (Asilomar 2017, Bletchley Park 2023),
- workstreams within larger orgs with distinct AI mandates (UN Scientific Panel on AI).

**Inclusion**:
- International participation or extraterritorial reach.
- National AISIs (because of explicit role in international AISI network — flag for sensitivity analysis).

**Exclusion**:
- Pure technical AI conferences without any policy/governance track. Workshops within them are admissible as separate entities (§3.3 → `conference_policy_track`).
- National-only entities with no international participation.
- Corporate internal AI ethics teams without external coordination.
- **Member organizations participating in a venue**: a member is not itself a venue. NIST AI Safety Institute Consortium is one AGV; its 200+ members are not 200 AGVs. Membership is captured in `agv_relation.csv` via `member_of`.

### 3.2 Date and establishment fields

To handle real-world ambiguity:
- `founded_date` (DATE, ISO 8601) — the canonical date.
- `founded_date_precision` (enum) — `day` | `month` | `year`.
- `establishment_basis` (enum) — what the date represents:
  - `announced` — public announcement, before operationalization
  - `first_meeting` — first convening
  - `formally_constituted` — formal founding instrument signed
  - `first_output` — first published output
- `announced_date` (optional) — for venues where announcement and operationalization differ.
- `first_output_date` (optional) — proxy for "birth" in organizational ecology.

When `founded_date_precision = year`, store as `YYYY-01-01` and document in evidence.

### 3.3 Six classification dimensions

Every AGV is classified across six orthogonal dimensions. Use only the listed enum values.

#### Dimension 1: `entity_type` (13 values)

| Value | Description | Example |
|---|---|---|
| `igo_initiative` | Initiative within an established intergovernmental organization | OECD.AI, UNESCO AI Ethics |
| `intergov_forum` | State-to-state forum with AI as standing item | G7 Hiroshima AI Process, G20 AI WG |
| `treaty_body` | Body under a binding international instrument | CoE Framework Convention on AI Committee |
| `multistakeholder_coalition` | Formal cross-sector coalition | Partnership on AI |
| `industry_consortium` | Industry-led standing body | Frontier Model Forum, MLCommons AI Safety |
| `intl_ngo_thinktank` | International NGO or think tank | Future of Life Institute, CAIDP, CAIS |
| `academic_consortium` | Cross-institutional academic body | MILA-led initiatives |
| `standards_body_wg` | Working group within a standards body | ISO/IEC JTC 1/SC 42, IEEE P7000 series |
| `national_regulator_intl` | National regulator with international coordination role | UK AISI, US AISI, Japan AISI |
| `conference_policy_track` | Policy/governance track or workshop within a recurring conference | NeurIPS ML Safety Workshop |
| `standalone_governance_conference` | Independent recurring conference whose entire scope is AI governance/ethics/safety | FAccT, AIES |
| `industry_conference` | Industry-oriented convening with governance content | World Summit AI |
| `one_off_summit` | Named summit producing durable outputs but not recurring as such | Asilomar 2017, Bletchley Park 2023 |

**Disambiguation rules (binding)**:
- **`standalone_governance_conference` vs `conference_policy_track`**: If the conference's *entire* scope is AI governance / ethics / safety / accountability and it has its own organizing committee and CFP independent of a parent venue, it is `standalone_governance_conference`. If it is a track or workshop that exists *within* a broader conference (e.g., a NeurIPS workshop), it is `conference_policy_track`.
- **`standalone_governance_conference` vs `industry_conference`**: Standalone governance conferences are primarily academic/multistakeholder with peer-reviewed proceedings. Industry conferences are commercial events with sponsorship-driven programming.
- **`one_off_summit` vs `intergov_forum`**: A summit becomes part of a recurring `intergov_forum` only when it has been held ≥ 2 times under the same mandate (e.g., Bletchley → Seoul → Paris summit series is now an `intergov_forum`). Individual editions remain in dataset as historical `one_off_summit` records, with `succeeded_by` relations.

#### Dimension 2: `governance_modality_primary` (+ optional `_secondary`)
- `declaration_principles` | `binding_instrument` | `technical_standards` | `evaluation_benchmarking` | `capacity_building` | `research_monitoring` | `dialogue_coordination` | `regulatory_enforcement`

#### Dimension 3: `topic_focus_primary` (+ up to 2 `_secondary`)
- `ai_general` | `safety_frontier` | `ethics_rights` | `privacy_data` | `genai_content` | `agentic_autonomy` | `domain_health` | `domain_defense` | `domain_education` | `domain_climate` | `domain_labor` | `access_inclusion` | `standards_interop`

#### Dimension 4: `geographic_scope` (+ `region_code` if regional)
- `global` | `transregional` | `regional` | `plurilateral` | `bilateral_plus`
- `region_code`: UN M49 (EU, ASEAN, AU, LAC, MENA, Pacific, etc.)

#### Dimension 5: `lead_actor_primary` (+ optional `_secondary`)
- `igo_secretariat` | `state_govt` | `industry` | `academia` | `civil_society` | `hybrid_mso`

#### Dimension 6: `legal_character`
- `soft_law` | `hard_law` | `mixed` | `n/a`

### 3.4 Convening frequency

`convening_frequency` (enum) — `one_off` | `annual` | `biennial` | `continuous` | `ad_hoc`

This field has dual purpose: descriptive (how often the venue meets) and operational (it drives stale detection thresholds in §3.5).

### 3.5 Lifecycle states and stale detection

States: `announced` | `active` | `dormant` | `absorbed` | `terminated` | `succeeded`

State transitions stored as event log in `agv_lifecycle.csv` (§4.6).

**Stale detection thresholds (NEW in v0.3)**: A uniform threshold (as proposed in v0.2) produces excessive false positives for venues that meet annually or less frequently. The diff pipeline (§9 Task 6) must apply thresholds based on `convening_frequency`:

| `convening_frequency` | Months since last observed activity to flag as `stale` candidate |
|---|---|
| `continuous` | 6 |
| `annual` | 18 |
| `biennial` | 30 |
| `ad_hoc` | 24 |
| `one_off` | **n/a — excluded from stale detection** |

`one_off` venues are excluded entirely from stale detection because their lack of ongoing activity is the default expected state. An Asilomar 2017 or Bletchley Park 2023 record remains `current_state = active` as long as its outputs retain influence; transitions to `terminated` or `succeeded` are made manually based on substantive evidence, not absence.

A "stale candidate" is **never** auto-transitioned to `dormant`. The diff pipeline surfaces it in the monthly PR for human review.

### 3.6 Human verification (NEW in v0.3)

Human verification is a first-class concept, not an afterthought. The schema must distinguish:
- **LLM-classified, unreviewed**: produced by `pipelines/classify.py`, low/medium confidence.
- **Human-verified**: explicitly reviewed and confirmed by a maintainer; LLM may not silently overwrite.

This distinction is recorded per-field via `human_verified_fields` in `agv.csv` (§4.2) and enforced by `diff.py` (§4.7 conflict resolution).

The act of human verification is recorded as a `reviewer` entry in `agv_evidence.csv` (§4.4) with `source_type = 'human_verification'`.

### 3.7 Relations (canonical: `agv_relation.csv`)

All inter-venue relationships live in the relation table — never duplicated in `agv.csv`.

Relation types (`relation_type` enum):
- `parent_of` — hierarchical containment (stored canonical direction only; reverse derived at display time)
- `succeeds` — formal succession (e.g., GPAI Integrated `succeeds` GPAI 2020)
- `absorbed_into` — merger
- `coordinates_with` — formal MOU or joint program
- `references_principles_of` — adopts another's principles
- `convenes_within` — policy track within a parent conference
- `member_of` — venue is a member/participant of another venue (e.g., a national AISI `member_of` the international AISI Network)

**Direction convention**: Relations are stored in one canonical direction only. The reverse (`child_of`, `succeeded_by`, etc.) is computed at query/display time. This eliminates the relation duplication problem from v0.1.

---

## 4. Data Schema

### 4.1 Files in `data/`

| File | Purpose |
|---|---|
| `agv.csv` | AGV master records — one row per venue |
| `agv_relation.csv` | Inter-venue relations (canonical) |
| `agv_evidence.csv` | Per-field source attribution |
| `agv_name_history.csv` | Renamings, aliases, valid date ranges |
| `agv_lifecycle.csv` | State transition event log |
| `agv_timeseries.csv` | Sparse time-series metrics |
| `README.md` | Schema reference (this section, in human-readable form) |

### 4.2 `agv.csv` — master AGV table (v0.3)

```
agv_id                          TEXT PRIMARY KEY
name_en                         TEXT NOT NULL          -- current English name
name_native                     TEXT                   -- current native-language name
entity_type                     TEXT NOT NULL          -- §3.3 D1 (13 values)
governance_modality_primary     TEXT NOT NULL          -- §3.3 D2
governance_modality_secondary   TEXT
topic_focus_primary             TEXT NOT NULL          -- §3.3 D3
topic_focus_secondary_1         TEXT
topic_focus_secondary_2         TEXT
geographic_scope                TEXT NOT NULL          -- §3.3 D4
region_code                     TEXT                   -- if scope='regional'
lead_actor_primary              TEXT NOT NULL          -- §3.3 D5
lead_actor_secondary            TEXT
legal_character                 TEXT NOT NULL          -- §3.3 D6
founded_date                    DATE NOT NULL
founded_date_precision          TEXT NOT NULL          -- §3.2
establishment_basis             TEXT NOT NULL          -- §3.2
announced_date                  DATE
first_output_date               DATE
current_state                   TEXT NOT NULL          -- §3.5
convening_frequency             TEXT NOT NULL          -- §3.4 (now NOT NULL because it drives stale detection)
last_observed_activity_date     DATE                   -- NEW v0.3: most recent confirmed activity, used for stale detection
primary_reference_url           TEXT NOT NULL          -- must be verification source (§5.2)
last_verified_date              DATE                   -- last time the maintainer confirmed all data is current
confidence_entity_type          TEXT NOT NULL          -- 'high'|'medium'|'low'
confidence_founded_date         TEXT NOT NULL
confidence_current_state        TEXT NOT NULL
confidence_legal_character      TEXT NOT NULL
human_verified_at               DATE                   -- NEW v0.3: date of most recent human verification (NULL = never reviewed by human)
human_verified_fields           TEXT                   -- NEW v0.3: comma-separated field names verified by human (e.g., "entity_type,founded_date,legal_character")
override_policy                 TEXT NOT NULL          -- NEW v0.3: 'lock_verified_only' (default) | 'lock_all' | 'allow_llm_update'
notes                           TEXT
```

**Notes on the new v0.3 fields**:

- `last_observed_activity_date`: separate from `last_verified_date`. The former records the most recent date on which the venue itself was observed to do something (publish a document, hold a meeting, update its site); the latter records when the maintainer last confirmed the row's data correctness. Stale detection uses `last_observed_activity_date`.

- `human_verified_at` and `human_verified_fields`: capture the maintainer's explicit verification. A row that has never been reviewed has `human_verified_at = NULL` and an empty `human_verified_fields`. After review, both are populated.

- `override_policy`:
  - `lock_verified_only` (default): LLM may update only fields not listed in `human_verified_fields`.
  - `lock_all`: LLM may not update any field on this row; only manual edits accepted.
  - `allow_llm_update`: explicit opt-in for LLM to update any field (use sparingly, e.g., for high-churn metadata).

Removed from v0.1: `absorbed_into`, `succeeds` (now in `agv_relation.csv` only).
Removed from v0.1: row-level `confidence` (replaced by per-field).

### 4.3 `agv_relation.csv`

```
source_agv     TEXT NOT NULL
target_agv     TEXT NOT NULL
relation_type  TEXT NOT NULL          -- §3.7
start_date     DATE
end_date       DATE                   -- NULL = ongoing
source_url     TEXT NOT NULL          -- verification source for the relation itself
notes          TEXT
PRIMARY KEY (source_agv, target_agv, relation_type, start_date)
```

### 4.4 `agv_evidence.csv`

Per-field source attribution. One row per (AGV, field, source) tuple.

```
agv_id          TEXT NOT NULL
field_name      TEXT NOT NULL          -- which field in agv.csv this evidences
source_url      TEXT NOT NULL
source_type     TEXT NOT NULL          -- 'official_site' | 'founding_document' | 'press_release' | 'oecd_navigator' | 'iapp_tracker' | 'unesco_gaigo' | 'news' | 'academic_paper' | 'human_verification' | 'llm_classification' | 'other'
accessed_at     DATE NOT NULL
evidence_note   TEXT                   -- short quote, paraphrase, or LLM rationale
reviewer        TEXT                   -- GitHub handle (for human_verification) or model version (for llm_classification)
confidence      TEXT NOT NULL          -- 'high' | 'medium' | 'low'
PRIMARY KEY (agv_id, field_name, source_url, accessed_at)
```

**Rules**:
- Every value in `agv.csv` flagged with field-level confidence (§4.2) must have ≥1 corresponding row.
- For LLM-classified fields, `source_type='llm_classification'`, `source_url='internal://classifier-run/{run_id}'`, `evidence_note` contains the classifier rationale, `reviewer` is the model version string (e.g., `claude-sonnet-4-7`).
- Before merging an LLM-classified field as `human_verified`, a second evidence row with `source_type='human_verification'` must be added by the human reviewer.
- Field-level confidence in `agv.csv` reflects the **highest-confidence** evidence row for that field.

### 4.5 `agv_name_history.csv`

Tracks renamings and aliases.

```
agv_id          TEXT NOT NULL
name            TEXT NOT NULL
name_type       TEXT NOT NULL          -- 'official_en' | 'official_native' | 'alias' | 'former_official_en' | 'abbreviation'
valid_from      DATE
valid_to        DATE                   -- NULL = current
source_url      TEXT
PRIMARY KEY (agv_id, name, name_type, valid_from)
```

The diff pipeline (§4.7) must consult this table before flagging any apparent name change as a new entity.

### 4.6 `agv_lifecycle.csv`

State transition event log.

```
agv_id          TEXT NOT NULL
from_state      TEXT                   -- NULL for initial
to_state        TEXT NOT NULL          -- §3.5
transition_date DATE NOT NULL
source_url      TEXT
notes           TEXT
PRIMARY KEY (agv_id, transition_date, to_state)
```

### 4.7 Conflict resolution rules (NEW in v0.3)

When the monthly LLM re-classification produces a value that disagrees with an existing `agv.csv` row, the diff pipeline (§9 Task 6) categorizes the situation as one of four cases and acts accordingly:

| Case | Existing row state | LLM proposed value | Action |
|---|---|---|---|
| **A. Greenfield** | Field has no value | Any | Add as `new` proposal in PR |
| **B. Unverified update** | Field has LLM-classified value, not in `human_verified_fields` | Differs | Add as `updated` proposal in PR; replace permitted on merge |
| **C. Locked field** | Field listed in `human_verified_fields`, `override_policy = 'lock_verified_only'` or `'lock_all'` | Differs | Add as **`conflict`** in PR with both old and new values, classifier rationale, and source URL diff. **Do not propose replacement.** Reviewer must explicitly choose: (a) keep human value, (b) accept LLM proposal and re-verify, (c) note venue evolution. |
| **D. Match** | Any | Same as existing | No action |

**Why case C requires explicit conflict surfacing rather than silent skipping**: A venue's true classification can legitimately change over time (e.g., an `industry_consortium` formally restructures into a `multistakeholder_coalition` by adding civil society seats). Silently skipping locked fields would cause the dataset to miss real evolution. Surfacing as a conflict gives the reviewer the chance to recognize this, while the default action remains preserving the human verification.

The `conflict` category in PR bodies must include:
- The existing human-verified value with its `human_verified_at` date and reviewer.
- The new LLM-proposed value with rationale.
- A diff of the source content (if the underlying source URL has changed since `human_verified_at`).
- Three labeled checkboxes (a/b/c above) for the reviewer to choose.

Ratio target: Conflicts should be rare. If the monthly PR contains >5% conflicts among reviewed rows, that signals either classifier drift (re-evaluate prompts) or genuine venue churn warranting investigation.

### 4.8 Schema invariants (enforced by `tests/test_schema.py`)

- All required fields non-null.
- All enum values valid per §3.
- All `agv_id` references resolve.
- All URLs well-formed.
- `founded_date` parseable; year ≥ 2000.
- If `current_state` ∈ {`absorbed`, `succeeded`}, a corresponding relation exists in `agv_relation.csv`.
- Every field in `agv.csv` with a `confidence_*` column has ≥1 evidence row.
- `agv_name_history`: `valid_from < valid_to` when both set; only one row per `agv_id` may have `name_type='official_en'` and `valid_to=NULL`.
- If `human_verified_fields` non-empty, `human_verified_at` is non-null.
- For each field listed in `human_verified_fields`, at least one `agv_evidence.csv` row exists with `source_type='human_verification'` for that `(agv_id, field_name)`.
- `override_policy` ∈ {`lock_verified_only`, `lock_all`, `allow_llm_update`}.

---

## 5. Source Architecture

### 5.1 The three-layer model

Every external source is assigned one of three roles. A source may serve multiple roles only if explicitly listed in both layers in `sources/registry.yml`.

| Layer | Role | Allowed use |
|---|---|---|
| **discovery** | Helps find candidate AGVs | May seed candidate rows in monthly diff PRs; **never** acceptable as `primary_reference_url` |
| **verification** | Authoritative source for an AGV's existence and properties | Must be the `primary_reference_url`; must be cited in `agv_evidence.csv` for each verified field |
| **background** | Conceptual/contextual literature | Cited in `methodology.md`; **never** populated into `agv.csv` or `agv_evidence.csv` |

### 5.2 Source assignments

#### Discovery layer
- **OECD.AI Policy Navigator** — best general-purpose discovery for international initiatives and IGO programs
- **UNESCO Global AI Ethics & Governance Observatory** — discovery for country-level entities and emerging regional bodies
- **IAPP Global AI Law and Policy Tracker** — discovery for regulatory authorities and laws
- **EvalCommunity Global AI Governance Map** — supplementary discovery; on probation in v0.2 (re-evaluate before v0.4 based on update cadence)
- **Direct news monitoring** (Tech Policy Press, EuroNews AI, MIT Tech Review policy desk) — discovery for emerging venues not yet in registries
- **AI Safety Newsletter (CAIS)**, **Import AI**, **AI Snake Oil** — discovery via expert curation
- **Conference deadline aggregators** (aideadlin.es) — discovery for academic conference policy tracks

#### Verification layer
Verification sources are the **canonical first-party sources** for each `entity_type`. Every AGV's `primary_reference_url` must come from the appropriate verification source family.

| `entity_type` | Verification source family |
|---|---|
| `igo_initiative` | The IGO's official AI page (oecd.ai, unesco.org/ethics-ai, etc.) + founding mandate document |
| `intergov_forum` | Forum's official communique repository (g7.gc.ca, mofa.go.jp/G7, g20.org) + summit declarations |
| `treaty_body` | The treaty text + the body's official secretariat page (e.g., coe.int/cai) |
| `multistakeholder_coalition` | The coalition's official site + bylaws/founding charter |
| `industry_consortium` | The consortium's official site + founding press release |
| `intl_ngo_thinktank` | The org's official site + 990/charity registration where available |
| `academic_consortium` | Host institution announcement + program page |
| `standards_body_wg` | The standards body's WG page (iso.org, ieee.org, itu.int) + WG charter/scope document |
| `national_regulator_intl` | The regulator's official site + establishing legislation/regulation |
| `conference_policy_track` | The track's CFP page + conference proceedings |
| `standalone_governance_conference` | The conference's official site + first-edition proceedings |
| `industry_conference` | The conference's official site + agenda |
| `one_off_summit` | The host government's summit page + declaration text |

#### Background layer
- **Stanford AI Index Report** (annual) — context for legislation/policy trends, not entity-level data
- **Berkman Klein "Principled AI"** (2020) — historical mapping of AI principles documents
- **Lawfare three-layer framework** — conceptual organization of governance layers
- **Springer *AI and Ethics* mapping article** (Schmitt 2021) — early academic mapping
- **Cihon, Maas & Kemp** (AAAI/ACM AIES 2020) — centralization debate

These are cited in `methodology.md` and the SSRN companion paper, never in `agv.csv` data fields.

### 5.3 Source registry

All sources are declared in `sources/registry.yml`:

```yaml
sources:
  - id: oecd_ai
    name: "OECD.AI Policy Observatory"
    url: "https://oecd.ai/"
    role: discovery
    entity_types_covered: [igo_initiative, intergov_forum, multistakeholder_coalition, national_regulator_intl]
    fetcher_module: pipelines.fetchers.oecd_ai
    fetch_strategy: http_with_playwright_fallback
    update_frequency: monthly
    last_verified_alive: 2026-04-23

  - id: coe_cai
    name: "Council of Europe Committee on AI"
    url: "https://www.coe.int/en/web/artificial-intelligence/cai"
    role: verification
    entity_types_covered: [treaty_body]
    fetcher_module: null
    update_frequency: quarterly
    last_verified_alive: 2026-04-23
```

`sources/registry.yml` is the single source of truth for which fetcher exists, what it covers, and when each was last confirmed alive.

### 5.4 Source coverage matrix (mandatory deliverable)

`sources/coverage_matrix.md` must contain a table cross-tabulating `entity_type × geographic_scope × source_family`, showing for each cell: (a) which discovery sources can find such venues, (b) which verification source family is canonical, (c) current count of populated AGVs in that cell, (d) gaps.

The matrix is regenerated at each release (`scripts/generate_coverage_matrix.py`) and committed to Git so its evolution is visible. **No release is allowed if any cell has count > 0 but lacks a designated verification source.**

### 5.5 Why this matters

The v0.1 spec listed three fetchers (OECD.AI, IAPP, UNESCO GAIGO) and treated them as sufficient. External review correctly identified that these three together cannot cover the full ontology — they are largely silent on standards bodies, industry consortia, treaty bodies, and one-off summits. The 3-layer architecture and coverage matrix make the gap visible and force it to be filled, rather than papered over.

---

## 6. Site Structure

### 6.1 `/` (landing)
- Hero chart: annual founding rate, full timeline, with annotated layer for inflection points (Asilomar 2017, OECD AI Principles 2019, ChatGPT 2022, Bletchley 2023, EU AI Act enforcement 2025).
- Three "headline numbers" cards: total active AGVs, new in past 12 months, distinct entity types covered.
- Two secondary charts: by entity type, by topic focus.
- 200–300 word narrative intro pointing to dashboard and methodology.

### 6.2 `/dashboard` — sensitivity views

Three default views, selectable via toggle:
1. **`continuous bodies only`** — filters to `entity_type` ∈ {igo_initiative, treaty_body, multistakeholder_coalition, industry_consortium, intl_ngo_thinktank, academic_consortium, standards_body_wg, national_regulator_intl}. The "institution-building" view.
2. **`recurring convenings only`** — filters to entities with `convening_frequency` ∈ {annual, biennial} (covers `standalone_governance_conference`, `conference_policy_track`, `industry_conference`, recurring summits).
3. **`one-off included`** — full dataset, with one-off summits explicitly highlighted.

Each view renders the six analytical sections:
1. Cumulative active population over time.
2. Founding rate by `entity_type` (small multiples).
3. Founding rate by `topic_focus_primary` (small multiples).
4. Lifecycle state distribution.
5. Topic × entity-type heatmap.
6. Geographic scope and lead-actor distributions.

Future v0.4 additions:
- Network graph of relations (force-directed D3).
- Lifecycle Sankey: founded → state transitions.
- Concentration index (Herfindahl) over time.
- Density-dependence model fit (organizational ecology).
- Inclusivity dashboard (if v0.4 adopts the inclusivity metrics extension; see §12).

### 6.3 `/venues/`
Searchable, sortable, filterable table. Filters: entity type, topic, region, founded year range, current state, lead actor. Source URL link in every row.

### 6.4 `/venues/[agv_id]`
Auto-generated from each AGV record:
- Header: current name + former names from `agv_name_history` + founding year + current state badge.
- Ontology classification badges (six dimensions) with per-field confidence indicators.
- **Verification status badge** (NEW v0.3): "Human-verified on [date] by [reviewer]" or "Awaiting human review".
- Timeline of state transitions (from `agv_lifecycle.csv`).
- Time series charts where available.
- Local network graph (related AGVs from `agv_relation.csv`).
- **All evidence sources** (from `agv_evidence.csv`), grouped by field, with source_type icons (human vs LLM vs upstream registry).
- "Edit on GitHub" link to the canonical CSV row.

### 6.5 `/methodology`
- Human-readable AGVO ontology v0.3.
- Three-layer source architecture explained.
- Source registry with last-verified dates.
- Inclusion/exclusion rules.
- Stale detection thresholds (§3.5 table).
- Conflict resolution policy (§4.7).
- Known limitations and biases.
- **Background literature** (separate from data sources).

### 6.6 `/sources`
- Live view of `sources/registry.yml` and the coverage matrix.
- Per-source pages showing which AGVs were sourced from each.

### 6.7 `/data-download`
- Direct downloads of all CSV files; JSON exports.
- Schema reference.
- License (CC-BY 4.0 data, MIT code).
- Citation block including current Zenodo DOI.

---

## 7. Repository Layout

```
agv-tracker/
├── CLAUDE.md                       # This file (v0.3)
├── README.md                       # Public-facing
├── CHANGELOG.md                    # Runtime decisions log; append-only
├── observablehq.config.js
├── package.json
├── pyproject.toml
├── src/                            # Observable Framework source
│   ├── index.md
│   ├── dashboard.md
│   ├── venues/
│   │   ├── index.md
│   │   └── [agv_id].md             # Auto-generated
│   ├── methodology.md
│   ├── sources.md
│   ├── data-download.md
│   ├── data/                       # Data loaders
│   │   ├── agv.json.py
│   │   ├── founding_rate.json.py
│   │   ├── lifecycle.json.py
│   │   ├── network.json.py
│   │   ├── evidence.json.py
│   │   └── coverage_matrix.json.py
│   └── components/
│       ├── foundingRateChart.js
│       ├── topicHeatmap.js
│       ├── networkGraph.js
│       ├── venueCard.js
│       ├── evidencePanel.js
│       ├── verificationBadge.js    # NEW v0.3
│       └── viewToggle.js
├── data/                           # Canonical CSV
│   ├── agv.csv
│   ├── agv_relation.csv
│   ├── agv_evidence.csv
│   ├── agv_name_history.csv
│   ├── agv_lifecycle.csv
│   ├── agv_timeseries.csv
│   └── README.md
├── sources/
│   ├── registry.yml
│   ├── coverage_matrix.md          # auto-generated
│   └── README.md
├── pipelines/
│   ├── README.md
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseFetcher with playwright fallback
│   │   ├── oecd_ai.py
│   │   ├── iapp.py
│   │   ├── unesco_gaigo.py
│   │   ├── coe_cai.py
│   │   ├── iso_iec_sc42.py
│   │   ├── ieee_p7000.py
│   │   ├── itu_focus_groups.py
│   │   ├── aisi_network.py
│   │   ├── frontier_model_forum.py
│   │   ├── partnership_on_ai.py
│   │   └── ...
│   ├── normalize.py
│   ├── classify.py
│   ├── diff.py                     # NOW lock-aware + dynamic stale (v0.3)
│   ├── candidates_to_pr.py         # NOW emits 'conflict' category (v0.3)
│   └── prompts/
│       ├── classify_entity_type.txt
│       ├── classify_governance_modality.txt
│       ├── classify_topic_focus.txt
│       └── classify_lead_actor.txt
├── scripts/
│   ├── monthly_update.sh
│   ├── generate_venue_pages.py
│   └── generate_coverage_matrix.py
├── tests/
│   ├── test_schema.py
│   ├── test_normalize.py
│   ├── test_classify.py
│   ├── test_evidence.py
│   ├── test_diff_lock_logic.py     # NEW v0.3
│   ├── test_stale_detection.py     # NEW v0.3
│   └── fixtures/
└── .github/workflows/
    ├── deploy.yml
    ├── monthly_fetch.yml
    ├── validate.yml
    └── linkcheck.yml
```

---

## 8. Conventions

### 8.1 Python
- Python 3.12+, managed via `uv`.
- Type hints mandatory on public functions.
- `ruff` for lint/format; configured in `pyproject.toml`.
- Tests with `pytest`.
- `playwright` listed as optional dependency (extras `[scraping]`); `pip install -e ".[scraping]"` installs it.

### 8.2 JavaScript / Markdown (Observable)
- Prefer Observable Plot for standard charts; D3 only for custom (network graph, Sankey).
- Avoid `import * as d3 from "npm:d3"` for trivial uses; use plain JS for `Math.min`, range loops, etc. — keeps build dependencies minimal and reduces CDN load.
- Component files in `src/components/` are plain ESM modules.

### 8.3 CSV editing
- Edit `data/*.csv` via `pandas` or a CSV-aware editor — never hand-typing in plain text editor for rows with commas/newlines/quotes in `notes` or `evidence_note`.
- After every edit, run `python tests/test_schema.py` before committing.
- Commit one logical change per commit (e.g., "add 5 standards body WGs", not "data updates").
- **When marking a field as human-verified**: add the field name to `human_verified_fields`, set `human_verified_at` to today, and add a corresponding `agv_evidence.csv` row with `source_type='human_verification'` and your GitHub handle as `reviewer`. CI enforces this triple.

### 8.4 Commit messages — Conventional Commits
- `data: add 12 industry consortia to seed sample`
- `data: human-verify entity_type for 30 AGVs`
- `pipeline: implement OECD.AI fetcher with playwright fallback`
- `site: add network graph to dashboard`
- `docs: revise methodology page`
- `fix: handle missing founded_date in normalizer`
- `sources: register CoE CAI as verification source for treaty_body`
- `ontology: add standalone_governance_conference entity_type` (only via formal proposal)

### 8.5 Branch strategy
- `main` is always deployable.
- Feature branches for non-trivial work.
- Monthly update PRs from `monthly-update/YYYY-MM` branches (auto-named by Action).

### 8.6 Evidence and verification discipline
Every data change requires:
1. The change itself in `agv.csv` (or other canonical table).
2. Corresponding row(s) in `agv_evidence.csv` for any field with a `confidence_*` column.
3. If the change is a renaming, a new row in `agv_name_history.csv`.
4. If the change is a state transition, a new row in `agv_lifecycle.csv`.
5. If the change marks a field as human-verified, the `agv.csv` `human_verified_fields` and `human_verified_at` must reflect it, AND a `source_type='human_verification'` row must exist in `agv_evidence.csv`.

CI enforces these via `tests/test_evidence.py` and `tests/test_schema.py`.

---

## 9. Task Backlog

Tasks ordered by dependency. Pick lowest open.

### Task 1 — Build source registry and coverage matrix scaffolding
**Goal**: Stand up the source architecture infrastructure before doing any data work.
**Files**: `sources/registry.yml`, `sources/coverage_matrix.md`, `sources/README.md`, `scripts/generate_coverage_matrix.py`
**Steps**:
1. Create `sources/registry.yml` populated with all sources listed in §5.2, with `entity_types_covered` and `last_verified_alive` for each. Include `fetch_strategy` field where applicable: `http_static` | `http_with_playwright_fallback` | `manual`.
2. Implement `scripts/generate_coverage_matrix.py` reading `registry.yml` and `data/agv.csv`, emitting `sources/coverage_matrix.md`.
3. Run once with the empty/minimal dataset to confirm.
4. Document conventions in `sources/README.md`.
**Done when**:
- `registry.yml` lists ≥15 sources across all three layers.
- `generate_coverage_matrix.py` produces a valid Markdown matrix.
- All `entity_type` values from §3.3 have ≥1 verification source assigned.

### Task 2 — Migrate seed data from v0.1 → v0.3 schema
**Goal**: Upgrade existing 30-AGV seed to the v0.3 schema (skipping v0.2 since it was never realized).
**Files**: `data/agv.csv`, `data/agv_relation.csv`, `data/agv_evidence.csv`, `data/agv_name_history.csv`, `data/agv_lifecycle.csv`
**Steps**:
1. Re-emit `data/agv.csv` with v0.3 columns (add `founded_date_precision`, `establishment_basis`, four `confidence_*`, `last_observed_activity_date`, `human_verified_at`, `human_verified_fields`, `override_policy`; remove `absorbed_into`, `succeeds`, row-level `confidence`).
2. Move `absorbed_into`/`succeeds` data to `agv_relation.csv`.
3. Reclassify FAccT and AIES as `standalone_governance_conference`.
4. For each existing AGV, populate `agv_evidence.csv` with ≥1 row per `confidence_*` field, citing the existing `primary_reference_url`. Mark these initial rows with `source_type='human_verification'` (since you, the maintainer, are confirming them) and your GitHub handle as `reviewer`.
5. Set `human_verified_at = today` and `human_verified_fields = "entity_type,founded_date,current_state,legal_character"` for all 30 seed rows.
6. Set `override_policy = "lock_verified_only"` (default).
7. For UK AISI, populate `agv_name_history.csv` with both former and current names.
8. Populate `agv_lifecycle.csv` with `(NULL → active, founded_date)` for currently-active AGVs; `(active → absorbed, ...)` for GPAI 2020.
9. Populate `last_observed_activity_date` from the most recent verifiable activity for each venue.
**Done when**:
- All v0.3 schema invariants (§4.8) pass.
- `tests/test_schema.py` passes.
- `tests/test_evidence.py` passes.

### Task 3 — Expand seed dataset to 100 AGVs using coverage matrix
**Goal**: Use the coverage matrix from Task 1 to systematically fill gaps.
**Files**: `data/*.csv`
**Steps**:
1. Run `generate_coverage_matrix.py`; identify `(entity_type × region)` cells with zero AGVs.
2. For each gap, manually add 3–5 AGVs from the appropriate verification source family.
3. Priority gaps:
   - `standards_body_wg`: ISO/IEC SC 42 sub-WGs, IEEE P7000 series (P7001–P7014), ITU FG-AI4H, FG-AI4EE
   - `industry_consortium` post-2023: Coalition for Secure AI (CoSAI), AI Alliance, ML Safety Network
   - `multistakeholder_coalition`: Partnership on AI workstreams, GPAI Working Groups
   - `treaty_body`: CoE Committee on AI (CAI) and its drafting groups
   - `national_regulator_intl`: AISI Network, EU AI Office, Singapore IMDA AI Verify, Korea AISI
   - `standalone_governance_conference`: confirm FAccT/AIES reclassified; add ICAIL
   - `conference_policy_track`: NeurIPS workshops on safety/governance, ICML workshops, AAAI safety tracks
   - Regional: AU AI Continental Strategy, ASEAN AI Working Group, LAC fAIr LAC initiative
4. For each new AGV: full evidence rows + appropriate `human_verified_*` fields.
5. Re-run coverage matrix to verify gaps closed.
**Done when**:
- ≥100 rows in `data/agv.csv`.
- All 13 `entity_type` values appear ≥3 times.
- Coverage matrix shows no entity_type with zero coverage.
- All schema and evidence tests pass.
- Append summary to `CHANGELOG.md`.

### Task 4 — Build OECD.AI Navigator fetcher with Playwright fallback
**Goal**: First automated discovery source.
**Files**: `pipelines/fetchers/oecd_ai.py`, `pipelines/fetchers/base.py`, `tests/test_fetchers.py`, `tests/fixtures/oecd_ai/`, `pyproject.toml`
**Steps**:
1. Define `BaseFetcher` ABC in `base.py` with `fetch() -> list[RawVenue]`. Provide a helper `fetch_html_with_fallback(url)` that:
   - First tries `httpx.get(url)` with reasonable timeout.
   - If response HTML lacks expected content selectors (passed in by caller), falls back to Playwright headless browser.
   - Logs which strategy succeeded.
2. Implement `OECDFetcher`. Strategy: target `https://oecd.ai/dashboards` initiative listing endpoints; respect `robots.txt`; cache responses to disk; throttle 1 req/sec.
3. **Important**: Try static HTTP first. Many OECD.AI listing pages may serve initial HTML with content; Playwright is fallback only. Document which approach was needed in module docstring.
4. Map raw fields to `RawVenue` dataclass.
5. Output records flagged `source_role=discovery`; the normalizer (Task 6) will require pairing with a verification source before promoting to AGV candidate.
6. Unit tests with cached fixtures (no live network in CI).
7. Add `playwright` to `pyproject.toml` as optional dependency in `[scraping]` extras: `pip install -e ".[scraping]"`.
**Done when**:
- `python -m pipelines.fetchers.oecd_ai` returns ≥50 raw records flagged `source_role=discovery`.
- Tests pass with fixtures.
- Module docstring documents whether static HTTP or Playwright was needed.
- `playwright install chromium` is documented in `pipelines/README.md` setup steps.

### Task 5 — Build LLM-assisted classifier with evidence emission
**Goal**: Map free-text mandate descriptions to AGVO enum values, with full provenance.
**Files**: `pipelines/classify.py`, `pipelines/prompts/*.txt`, `tests/test_classify.py`
**Steps**:
1. For each of the six dimensions, write a prompt template including AGVO enum definitions and asking for `(value, confidence, rationale)` JSON output.
2. Use Anthropic Claude API; key from `ANTHROPIC_API_KEY`.
3. Parse and store `value`, `confidence`, `rationale`.
4. **Emit evidence rows**: each classification creates a row in `agv_evidence.csv` with `source_type='llm_classification'`, `source_url='internal://classifier-run/{run_id}'`, `evidence_note={rationale}`, `reviewer={model_version}`, e.g., `claude-sonnet-4-7`.
5. Cache by content hash to avoid re-classifying unchanged text.
6. Cost guardrail: log spend per run, fail if monthly budget exceeded.
**Done when**:
- `python -m pipelines.classify --input raw.json --output classified.json` works.
- 10 manually-verified gold examples; classifier accuracy ≥80% on entity_type, ≥70% on each other dimension.
- Evidence rows correctly emitted with proper `source_type` and `reviewer`.

### Task 6 — Build normalize → diff → PR pipeline (lock-aware + dynamic stale)
**Goal**: End-to-end automation with v0.3 conflict resolution and stale detection.
**Files**: `pipelines/normalize.py`, `pipelines/diff.py`, `pipelines/candidates_to_pr.py`, `tests/test_diff_lock_logic.py`, `tests/test_stale_detection.py`
**Steps**:
1. `normalize.py`: take raw venues from fetchers (discovery), require pairing with verification source before promoting to AGV candidate, run through classifier, emit candidate `agv.csv`-shaped DataFrame + evidence rows.
2. `diff.py`: compare candidate vs canonical; categorize using §4.7 four-case logic:
   - For each row × field, determine case A/B/C/D and emit appropriate diff entry.
   - **Crucially**: respect `human_verified_fields` and `override_policy` per §4.7. Conflicts (case C) are surfaced, never silently dropped.
3. `diff.py`: also implement **dynamic stale detection** per §3.5 table. For each existing AGV not seen in this fetch run, check `convening_frequency` and threshold; emit `stale_candidate` only if threshold exceeded. `one_off` venues skipped entirely.
4. `diff.py`: consult `agv_name_history.csv` to detect renames vs new entities (an apparent new AGV with name matching a former_official_en of an existing AGV is a rename, not a new entity).
5. `candidates_to_pr.py`: emit Markdown PR body with sections per change type:
   - `## New venues` (case A)
   - `## Updates to unverified fields` (case B)
   - `## ⚠️ Conflicts with human-verified fields` (case C, with three labeled checkboxes per §4.7)
   - `## Stale candidates for review` (dynamic threshold)
   - `## Rename detections` (matched against name history)
6. Tests: `test_diff_lock_logic.py` covers all four cases × `override_policy` variations; `test_stale_detection.py` covers each `convening_frequency` × edge dates.
**Done when**:
- Running on Task 4 output produces a PR body actionable in <30 sec/row.
- Renames correctly identified, not flagged as new.
- Conflicts surfaced (not silently dropped or auto-overwritten).
- Stale detection respects `convening_frequency`; `one_off` venues never flagged stale.
- Test coverage ≥90% on `diff.py`.

### Task 7 — Wire up GitHub Actions
**Files**: `.github/workflows/{monthly_fetch,deploy,validate,linkcheck}.yml`
**Steps**:
1. `monthly_fetch.yml`: cron `0 9 1 * *` UTC; runs all registered fetchers; opens PR via `peter-evans/create-pull-request`.
2. `deploy.yml`: on push to `main`, runs `npm run build` then deploys to Cloudflare Pages.
3. `validate.yml`: on every PR, runs `pytest tests/`, `npm run build`, link check on changed source URLs.
4. `linkcheck.yml`: weekly check of all source URLs; opens issue for broken links.
**Done when**:
- Manual `workflow_dispatch` of `monthly_fetch.yml` produces a real PR.
- `deploy.yml` deploys to a Cloudflare Pages preview URL.

### Task 8 — Per-venue detail pages with evidence and verification panels
**Files**: `scripts/generate_venue_pages.py`, `src/venues/[agv_id].md` template, `src/components/evidencePanel.js`, `src/components/verificationBadge.js`
**Steps**:
1. Auto-generate `src/venues/{agv_id}.md` from `data/agv.csv`.
2. Each page renders all evidence rows from `agv_evidence.csv` grouped by field, with confidence badges and source_type icons distinguishing human-verification, LLM-classification, and upstream-registry sources.
3. **Verification badge**: prominent display per §6.4: "Human-verified [date] by [reviewer]" or "Awaiting human review".
4. Render `agv_name_history` as a renaming timeline.
5. Render `agv_lifecycle` as state transition timeline.
**Done when**:
- Every AGV has a detail page with full evidence panel and verification badge.
- Build is reproducible from CSV alone.

### Task 9 — Sensitivity-view dashboard
**Files**: `src/dashboard.md`, `src/components/viewToggle.js`
**Steps**:
1. Implement view toggle: continuous / recurring / one-off-included.
2. Each chart re-renders when toggle changes.
3. Add explanatory text for each view.
**Done when**:
- All three views render correctly with the same chart set.
- Explanatory text makes the analytical purpose of each view clear.

### Task 10 — Network graph visualization
**Files**: `src/components/networkGraph.js`, `src/data/network.json.py`, dashboard section
**Steps**:
1. Pre-compute graph (nodes = AGVs, edges = `agv_relation.csv`) in `network.json.py`.
2. Force-directed D3 graph; nodes colored by `entity_type`; edges weighted by relation type.
3. Add to dashboard.
**Done when**:
- Graph loads and is interactive (drag, zoom, hover).
- Performs acceptably with 200+ nodes.

### Task 11 — Cloudflare Pages + custom domain
**Steps**:
1. Connect GitHub repo to Cloudflare Pages.
2. Configure build: `npm run build`, output `dist/`.
3. Register `agv-tracker.org` (or chosen domain).
4. DNS, HTTPS.
**Done when**:
- Production URL accessible publicly.
- Auto-deploys on merge to `main`.

### Task 12 — Zenodo DOI integration
**Steps**:
1. Connect repo to Zenodo via GitHub integration.
2. Tag `v0.3.0` release; verify DOI minted.
3. Update `methodology.md` and `data-download.md` with DOI citation.
**Done when**:
- Tagged releases auto-mint Zenodo DOIs.
- Site shows "Cite this release" with current DOI.

### Task 13 — Companion analysis notebook
**Files**: `notebooks/founding_rate_analysis.ipynb`
**Goal**: Foundation for SSRN paper.
**Steps**:
1. Reproduce headline charts from CSV.
2. Run organizational ecology models: density-dependent founding rates.
3. Sensitivity analyses across the three views (§6.2).
4. Output publication-ready figure set.
**Done when**:
- Notebook runs end-to-end from CSV.
- Includes ≥1 inferential test.

---

## 10. Success Criteria for v1.0 Public Launch

When all of the following are true, the project is ready for public announcement:

- [ ] **Coverage**: All 13 `entity_type` values populated with ≥10 AGVs each.
- [ ] **Source coverage**: Every `entity_type` has at least one operational verification source (manual or automated) listed in `sources/registry.yml`.
- [ ] **Automation**: At least 3 automated discovery fetchers operational (OECD.AI mandatory).
- [ ] **Recurring update**: Monthly cron has run successfully for 3 consecutive months with human review, producing ≤5% case-C conflicts on average (signal of classifier stability).
- [ ] **Deployment**: Site deployed at custom domain with HTTPS.
- [ ] **Citability**: First Zenodo DOI minted.
- [ ] **Evidence**: Every AGV has ≥1 evidence row per `confidence_*` field; <10% of fields at `low` confidence; **≥80% of AGVs have at least one `human_verified` field**.
- [ ] **Methodology**: Documents every choice including known biases, source coverage matrix, stale detection thresholds, and conflict resolution policy.
- [ ] **External use**: ≥1 external researcher has used the data (cited issue, PR, or downstream use).
- [ ] **Companion paper**: Analysis notebook produces publication-quality figures.

---

## 11. Out of Scope (deferred)

- Multilingual UI (English-only for v0.x).
- User accounts or comment system (use GitHub issues).
- Real-time updates (monthly cadence is intentional).
- Predictive modeling of future venue formation (descriptive first).
- Full national-only entity coverage (out of scope; OECD.AI's remit).
- Member organization registry as separate entities (members captured via `member_of` relations only).
- Inclusivity metrics (`working_languages_count`, `global_south_member_share`, etc.) — deferred to v0.4+; see §12 #6.

---

## 12. Open Decisions

Log decisions in `CHANGELOG.md` as resolved.

1. **Industry consortium minimum-substance threshold**: Some 2024–2025 consortia exist mainly as press releases. Proposal: require at least one published output OR ≥3 named member commitments OR ≥1 working session held.
2. **Bodies within bodies**: When does a working group merit its own AGV row vs being a child of its parent? Proposal: only when it has an independently published output stream. Otherwise, captured as `parent_of` relation.
3. **Private foundation programs** (e.g., Open Phil AI program): Include as `intl_ngo_thinktank`, or exclude as internal grantmaking? Lean toward exclude unless the program is itself a coordination venue.
4. **AISI Network**: Should the international AISI Network be its own AGV, with each national AISI as `member_of`? Lean yes.
5. **Conference policy track granularity**: One row per workshop, or one row per conference's safety/governance program? Lean: one row per recurring named workshop with stable organizing committee.
6. **Inclusivity metrics extension** (deferred to v0.4+): External review identified that the current ontology measures topical inclusion (`access_inclusion`) but not the venue's own diversity practices. A future extension could add to `agv_timeseries.csv`:
   - `working_languages_count` — number of official working languages
   - `global_south_member_share` — proportion of member orgs based in Global South
   - `civil_society_seat_share` — proportion of civil society representatives (multistakeholder venues only)
   These are intentionally deferred because (a) v0.3 should stabilize core schema first, (b) inclusivity data is high-cost to gather (often not in official sources), and (c) committing prematurely risks under-defined fields. Re-evaluate after v1.0 launch.
7. **EvalCommunity probation**: Re-evaluate before v0.4 based on observed update cadence.
8. **Conflict ratio target tuning**: §4.7 sets a 5% conflict-ratio target as "healthy". Revisit after first 3 monthly runs; may need adjustment based on actual classifier behavior.

---

## Appendix A — Source URLs (organized by layer)

### Discovery layer
- OECD.AI Policy Observatory: <https://oecd.ai/>
- UNESCO Global AI Ethics & Governance Observatory: <https://www.unesco.org/ethics-ai/en>
- IAPP Global AI Law and Policy Tracker: <https://iapp.org/resources/article/global-ai-legislation-tracker>
- EvalCommunity Global AI Governance Map (probation): <https://academy.evalcommunity.com/global-ai-governance-map-140-institutions/>
- AI conference deadlines: <https://aideadlin.es/>

### Verification layer (representative — full list in `sources/registry.yml`)
- OECD.AI: <https://oecd.ai/>
- UNESCO AI Ethics Recommendation: <https://www.unesco.org/en/artificial-intelligence/recommendation-ethics>
- Council of Europe Committee on AI (CAI): <https://www.coe.int/en/web/artificial-intelligence/cai>
- ISO/IEC JTC 1/SC 42: <https://www.iso.org/committee/6794475.html>
- IEEE Standards Association — AI: <https://standards.ieee.org/practices/intelligent-systems/>
- ITU AI for Good: <https://aiforgood.itu.int/>
- UN Global Dialogue on AI Governance: <https://www.un.org/global-dialogue-ai-governance/en>
- Frontier Model Forum: <https://www.frontiermodelforum.org/>
- Partnership on AI: <https://partnershiponai.org/>
- UK AI Security Institute (formerly AI Safety Institute): <https://www.aisi.gov.uk/>
- US AI Safety Institute (NIST): <https://www.nist.gov/aisi>
- Japan AI Safety Institute: <https://aisi.go.jp/>
- ACM FAccT: <https://facctconference.org/>
- AIES Conference: <https://www.aies-conference.com/>

### Background literature (cited in methodology + companion paper, never in data)
- Stanford AI Index Report (annual): <https://hai.stanford.edu/ai-index/>
- Berkman Klein Principled AI (2020): <https://cyber.harvard.edu/publication/2020/principled-ai>
- Lawfare three-layer framework (2026): <https://www.lawfaremedia.org/article/understanding-global-ai-governance-through-a-three-layer-framework>
- Hannan, M. T. & Freeman, J. (1989). *Organizational Ecology*. Harvard UP.
- Keohane, R. O. & Victor, D. G. (2011). The Regime Complex for Climate Change. *Perspectives on Politics* 9(1).
- Carmines, E. G. & Stimson, J. A. (1989). *Issue Evolution*. Princeton UP.
- Cihon, P., Maas, M. M., & Kemp, L. (2020). Should AI Governance be Centralised? *AAAI/ACM AIES 2020*.
- Schmitt, L. (2021). Mapping global AI governance. *AI and Ethics* 2.
