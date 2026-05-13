# AGVO v0.3 Codebook

**Purpose**: complete operational reference for every field and every enum
value in the `data/` tables. Companion to `docs/coding_manual.md` (decision
rules for human coders) and `data/README.md` (table-level summary).

**Authoritative spec**: `CLAUDE.md §3, §4`. If this file disagrees with
`CLAUDE.md`, `CLAUDE.md` wins — open a PR to fix the codebook.

**Conventions in this document**:

- "Field" = a column in a CSV table.
- "Value" = a permitted enum value (always lowercase ASCII with underscores).
- Examples cite real `agv_id`s currently in the dataset.
- "⚠ common confusion" flags pairs of values that get coded inconsistently
  if you don't pause.

---

## 1. The AGV concept

An **AGV (AI Governance Venue)** is any organized forum, body, initiative,
coalition, standards working group, or recurring/one-off convening whose
mandate includes — as a primary or substantial secondary purpose — the
**governance, oversight, coordination, or norm-setting** of AI
technologies.

### Inclusion (positive criteria — ALL of A + B must hold)

- **A. International scope** — at least one of:
  - International participation (≥2 countries' state, civil society, or
    industry representation as voting/working members).
  - Extraterritorial reach (binds or directly affects entities outside
    its host jurisdiction; e.g., EU AI Office reaches non-EU providers).
  - Designation as a node in an international network (e.g., the
    international AISI Network — a national AISI joins by virtue of
    network membership).
- **B. AI-governance mandate** — at least one of:
  - Primary mandate is AI governance, oversight, or norm-setting.
  - Substantial secondary mandate (≥30% of program/output is AI-specific
    governance work).

### Exclusion (negative criteria — ANY of these excludes)

- Pure technical AI conferences with no policy/governance track (NeurIPS
  main conference, ICML main conference). **Their workshops are admissible
  as `conference_policy_track` entities, but the parent conference is not.**
- National-only entities with no international participation. **Exception**:
  national AISIs (members of the international AISI Network are venues by
  virtue of network role).
- Corporate internal AI ethics teams without external coordination.
- Members of a venue are not themselves venues. NIST AI Safety Institute
  Consortium is **one** AGV; its 200+ members are not 200 AGVs.
  Membership is captured in `agv_relation.csv` via `member_of`.
- Press releases and news articles (📌 the fetcher pipeline harvests
  these as discovery signals, but they are not AGVs themselves).

### Edge-case heuristics

- **Members of an international network**: include as AGVs only if (1) the
  member has its own AI mandate (not just generic digital-policy role)
  AND (2) the network role is explicit (not just membership-by-default).
- **Workstreams within a parent venue**: include as a separate AGV only
  when the workstream has its own published output stream and identifiable
  organizing structure. Otherwise it's a `parent_of` relation, not a row.
- **Industry consortia with only a press release**: defer until they
  produce one published output OR enumerate ≥3 named member commitments
  OR hold ≥1 working session. (See `CLAUDE.md §12.1`.)

---

## 2. Tables

| File | Primary key | Purpose |
|---|---|---|
| `agv.csv` | `agv_id` | Master records, one row per AGV |
| `agv_relation.csv` | `(source_agv, target_agv, relation_type, start_date)` | Inter-venue relations (canonical direction only) |
| `agv_evidence.csv` | `(agv_id, field_name, source_url, accessed_at)` | Per-field source attribution |
| `agv_name_history.csv` | `(agv_id, name, name_type, valid_from)` | Renamings + aliases |
| `agv_lifecycle.csv` | `(agv_id, transition_date, to_state)` | State transition event log |

Schema invariants are enforced by `tests/test_schema.py` and
`tests/test_evidence.py`.

---

## 3. `agv.csv` field reference

The full column list is in `CLAUDE.md §4.2`. Below: every column with
definition, type, allowed values, and at least one example.

### 3.1 Identity

#### `agv_id` *(text, primary key)*

Snake_case identifier. Stable for the life of the venue (renamings update
`name_en` and append to `agv_name_history.csv`, but **never** change the
`agv_id`).

- **Convention**: `<short_acronym_or_country>_<topic>` where readable;
  otherwise an abbreviation of the official name.
- **Examples**: `oecd_ai_principles`, `uk_aisi`, `iso_iec_sc42`,
  `bletchley_summit`, `acm_facct`, `germany_bnetza_ai`.
- **Don't**: include version years (`gpai_2020` is OK because it
  represents a historical state, not a renamed venue; `oecd_ai_2024` would
  be wrong if the venue is `oecd_ai_principles` for all time).
- **Don't**: use `_` to mean "any descendant of"; that's `parent_of`.

#### `name_en` *(text, required)*

Current official English name. Spell out acronyms on first occurrence.
Renaming workflow:
1. Update `name_en` in `agv.csv`.
2. Mark the previous name as `name_type=former_official_en` in
   `agv_name_history.csv` with `valid_to=today`.
3. Append a new `name_type=official_en` row with `valid_from=today`.

#### `name_native` *(text, optional)*

Native-language name when the venue is non-Anglophone. Examples:
`Bundesnetzagentur — Koordinierungsstelle für KI`,
`Agencia Española de Supervisión de la Inteligencia Artificial (AESIA)`.

### 3.2 Six classification dimensions

These six dimensions are the **core ontology** (CLAUDE.md §3.3). Coding
rules are in `docs/coding_manual.md §3`. This section defines each value
precisely.

#### `entity_type` *(required, 13 values)*

| Value | Definition | Concrete examples |
|---|---|---|
| `igo_initiative` | Initiative *within* an established intergovernmental organization. Has IGO secretariat support. | `oecd_ai_observatory`, `unesco_ai_ethics`, `un_global_dialogue` |
| `intergov_forum` | State-to-state forum with AI as standing agenda item. Membership = governments. | `g7_hiroshima_process`, `g20_digital_economy_ai`, `quad_critical_tech_ai`, `eu_us_ttc_ai` |
| `treaty_body` | Body operating under a binding international instrument (treaty, regulation, framework convention). | `coe_ai_convention`, `eu_ai_board`, `un_ccw_gge_laws` |
| `multistakeholder_coalition` | Formal cross-sector coalition (governments + industry + civil society + academia). | `partnership_ai`, `gpai_2020`, `singapore_ai_verify` |
| `industry_consortium` | Industry-led standing body. Members = companies (may have observer NGO seats). | `frontier_model_forum`, `mlcommons_ai_safety`, `cosai`, `c2pa` |
| `intl_ngo_thinktank` | International NGO or think tank with AI focus. Civil-society-led. | `fli_2014`, `caidp`, `cais`, `ada_lovelace`, `algorithmwatch` |
| `academic_consortium` | Cross-institutional academic body. Members = universities/labs. | `ellis_network`, `cifar_aistrategy`, `ircai`, `gaiec` |
| `standards_body_wg` | Working group within a recognized standards body (ISO/IEC, IEEE, ITU, ETSI). | `iso_iec_sc42`, `iso_sc42_wg3`, `ieee_p7001`, `itu_fg_ai4h` |
| `national_regulator_intl` | National regulator/agency with international coordination role (network membership OR extraterritorial mandate). | `uk_aisi`, `us_aisi`, `japan_aisi`, `eu_ai_office`, `germany_bnetza_ai` |
| `conference_policy_track` | Track, workshop, or special session within a recurring conference. | `neurips_ml_safety`, `iclr_trustworthy_ml`, `aaai_safe_ai_track`, `acl_trustnlp` |
| `standalone_governance_conference` | Independent recurring conference whose entire scope is AI governance/ethics/safety/accountability. | `acm_facct`, `aies_conference`, `eaamo`, `forc`, `icail` |
| `industry_conference` | Industry-oriented commercial convening with governance content. | `itu_ai_for_good`, `web_summit_ai`, `cogx_london`, `responsible_ai_summit` |
| `one_off_summit` | Named summit producing durable outputs but not recurring as such. (See §3.3 disambiguation rule for when a summit becomes a forum.) | `asilomar_2017`, `bletchley_summit`, `paris_action_summit`, `reaim_hague_2023` |

**⚠ Common confusions**

- `standalone_governance_conference` **vs** `conference_policy_track`:
  Standalone has its own organizing committee, CFP, and proceedings (FAccT
  is FAccT). Track is hosted within a parent's CFP (NeurIPS ML Safety
  Workshop runs under NeurIPS).
- `standalone_governance_conference` **vs** `industry_conference`:
  Standalone is academic/multistakeholder with peer-reviewed proceedings.
  Industry is commercial with sponsorship-driven programming.
- `intergov_forum` **vs** `treaty_body`: forum produces soft-law
  declarations; treaty body operates under a binding instrument.
- `intergov_forum` **vs** `one_off_summit`: if the same named convening
  has been held ≥2 times under one mandate, it's a forum. Individual
  editions stay as historical `one_off_summit` rows with
  `succeeded_by` relations.

#### `governance_modality_primary` *(required, 8 values)* + `governance_modality_secondary` *(optional)*

What the venue **produces or does**.

| Value | Definition | Examples |
|---|---|---|
| `declaration_principles` | Produces principles, declarations, ethics codes. | `oecd_ai_principles`, `bletchley_summit`, `asilomar_2017` |
| `binding_instrument` | Drafts or operates a binding instrument (treaty, regulation, statute). | `coe_ai_convention`, `eu_ai_board` |
| `technical_standards` | Develops technical standards (ISO/IEC, IEEE, ITU, ANSI). | `iso_iec_sc42`, `ieee_p7001`, `c2pa` |
| `evaluation_benchmarking` | Designs and runs evaluations, benchmarks, audits. | `uk_aisi`, `us_aisi`, `mlcommons_ai_safety` |
| `capacity_building` | Training, education, technical assistance. | `unesco_ram_ai`, `ircai`, `smart_africa_ai` |
| `research_monitoring` | Conducts or coordinates research, tracking, monitoring. | `fli_2014`, `eu_ai_scientific_panel`, `pai_incident_db` |
| `dialogue_coordination` | Convenes dialogue, coordinates positions, facilitates cooperation. | `g7_hiroshima_process`, `aisi_network`, `un_global_dialogue` |
| `regulatory_enforcement` | Enforces rules, issues sanctions, conducts market surveillance. | `eu_ai_office`, `china_cac_genai`, `france_cnil_ai` |

**Use secondary** when the venue has a clear second function. E.g., UK
AISI is primary `evaluation_benchmarking`, secondary `research_monitoring`.
Don't list a secondary unless it's at least 30% of the mandate.

#### `topic_focus_primary` *(required, 13 values)* + `topic_focus_secondary_1`, `_secondary_2` *(optional)*

The substantive AI topic the venue addresses.

| Value | Definition / scope | Examples |
|---|---|---|
| `ai_general` | Whole AI / cross-cutting policy. Default for general-purpose bodies. | `oecd_ai_observatory`, `un_global_dialogue` |
| `safety_frontier` | Frontier model safety, dangerous capabilities, model evals. | `uk_aisi`, `frontier_model_forum`, `cais` |
| `ethics_rights` | Ethics, human rights, fairness, accountability. | `unesco_ai_ethics`, `acm_facct`, `caidp` |
| `privacy_data` | Data protection, privacy, ADM (automated decision-making) supervision. | `france_cnil_ai`, `netherlands_ap_ai`, `korea_pipc_ai` |
| `genai_content` | Generative AI, deepfakes, content provenance, watermarking. | `c2pa`, `content_authenticity_initiative`, `china_cac_genai` |
| `agentic_autonomy` | Autonomous agents, agentic systems, autonomy risks. | (rare — emerging area) |
| `domain_health` | AI in health/medical contexts. | `who_ai4h`, `itu_fg_ai4h` |
| `domain_defense` | Military / defense AI (lethal autonomous weapons, etc.). | `un_ccw_gge_laws`, `reaim_hague_2023`, `reaim_seoul_2024` |
| `domain_education` | AI in education. | (sparse) |
| `domain_climate` | AI for climate, environmental sustainability. | `itu_fg_ai4ee` |
| `domain_labor` | AI and labor / employment. | (sparse) |
| `access_inclusion` | Access, inclusion, global south, language diversity. | `smart_africa_ai`, `apru_ai`, `fair_lac_idb` |
| `standards_interop` | Standards and interoperability (when the topic itself is "standards"). | `c2pa` |

**Coding rule**: use the **most specific applicable value** for primary.
A venue addressing "safety + ethics + general policy" picks the dominant
focus and lists the others as secondary.

#### `geographic_scope` *(required, 5 values)* + `region_code` *(required if regional)*

| Value | Definition | Examples |
|---|---|---|
| `global` | Worldwide membership or universal mandate. | `oecd_ai_principles`, `iso_iec_sc42`, UN bodies |
| `transregional` | Spans multiple non-contiguous regions but is not global. | `gpai_integrated` (G7+ + South Korea + others) |
| `regional` | One regional bloc / continent. Requires `region_code`. | `eu_ai_office` (EU), `asean_ai_governance_framework` (ASEAN), `au_ai_continental_strategy` (AU) |
| `plurilateral` | Small named group of states (G7, G20, QUAD, BRICS). | `g7_hiroshima_process`, `g20_digital_economy_ai`, `brics_ai_cooperation` |
| `bilateral_plus` | Bilateral or trilateral. | (rare) |

`region_code` uses UN M49 / common abbreviations: `EU`, `ASEAN`, `AU`,
`LAC`, `MENA`, `Pacific`, `NA`, `SA`, `AS`, `EUR`, `OC`. Required iff
scope is `regional`. Leave blank for global/transregional/plurilateral.

⚠ **A national AISI in the international AISI Network**: code as `global`
(its network role is global) with `region_code` empty. The fact that it's
hosted by one country is captured in `name_en` and `notes`.

#### `lead_actor_primary` *(required, 6 values)* + `lead_actor_secondary` *(optional)*

Who drives the venue.

| Value | Definition | Examples |
|---|---|---|
| `igo_secretariat` | Run by an IGO secretariat (UN, OECD, ITU, UNESCO, CoE). | `oecd_ai_observatory`, `un_global_dialogue` |
| `state_govt` | Run by one or more state governments / national agencies. | `g7_hiroshima_process`, `uk_aisi`, `france_cnil_ai` |
| `industry` | Run by private-sector companies / industry trade group. | `frontier_model_forum`, `ai_alliance`, `cosai` |
| `academia` | Run by universities / research labs / academic associations. | `acm_facct`, `ellis_network`, `cifar_aistrategy` |
| `civil_society` | Run by NGOs / advocacy groups / foundations. | `fli_2014`, `caidp`, `algorithmwatch`, `ada_lovelace` |
| `hybrid_mso` | Genuine multistakeholder: no single sector is the sole driver, governance includes ≥3 sectors with formal seats. | `partnership_ai`, `gpai_2020`, `singapore_ai_verify` |

**⚠ Confusion**: `multistakeholder_coalition` as `entity_type` does NOT
imply `lead_actor=hybrid_mso`. Some multistakeholder coalitions are
secretariat-led (igo_secretariat). Check formal governance, not just
membership composition.

#### `legal_character` *(required, 4 values)*

| Value | Definition | Examples |
|---|---|---|
| `hard_law` | The venue itself enforces or operates a binding instrument with sanctions. | `eu_ai_office`, `china_cac_genai`, `france_cnil_ai` |
| `soft_law` | Produces non-binding norms (declarations, recommendations, guidelines, codes). | `oecd_ai_principles`, `bletchley_summit`, `partnership_ai` |
| `mixed` | Produces both binding and non-binding instruments. | `eu_ai_board` (mixes binding AI Act implementation with non-binding guidance) |
| `n/a` | Legal character doesn't apply (research org, conference, evaluation venue). | `acm_facct`, `uk_aisi`, `ellis_network` |

**⚠ Confusion**: Standards bodies. A `standards_body_wg` that produces
ISO standards is often coded `soft_law` because ISO standards themselves
are voluntary unless adopted into regulation. Mark `hard_law` only when
the standard is *directly* binding (rare).

### 3.3 Date and establishment fields

These together encode the real-world ambiguity around "when did this start".

#### `founded_date` *(required, ISO 8601 date)*

The canonical date. **Storage rule**: even when only the year is known,
store as `YYYY-01-01`; precision is conveyed by `founded_date_precision`.

#### `founded_date_precision` *(required, 3 values)*

| Value | Meaning | Example |
|---|---|---|
| `day` | Day-precise (most common, e.g., from a founding press release). | `2023-07-26` (Frontier Model Forum announcement) |
| `month` | Month known, day not. Store as `YYYY-MM-01`. | `2024-04-01` (Brazil ANPD AI guidance) |
| `year` | Only year known. Store as `YYYY-01-01`. | `2020-01-01` |

#### `establishment_basis` *(required, 4 values)*

What event the `founded_date` records.

| Value | Definition | Pick when |
|---|---|---|
| `announced` | Public announcement, before operationalization. | Press conference, white paper publication. Used when the venue's "birth" is the announcement (Asilomar). |
| `first_meeting` | First convening or organizing meeting. | Initial workshop or convening day. Used for conferences (FAccT 2018-02-23). |
| `formally_constituted` | Formal founding instrument signed (treaty entered into force, agency established by statute, MOU signed). | Royal Decree (Spain AESIA), CoE convention opened for signature. |
| `first_output` | First published output (when announcement/meeting predates anything substantive). | Used when the official "founding" predates the venue actually doing anything; the first output is the meaningful start. |

**Pick exactly one**. If multiple bases would all be valid, prefer the one
the venue itself claims on its "about" page. If still ambiguous, prefer
`formally_constituted` > `first_meeting` > `announced` > `first_output`.

#### `announced_date`, `first_output_date` *(optional, ISO date)*

When announce-date and operationalization-date diverge, both can be
recorded. `first_output_date` is the organizational-ecology "birth"
proxy.

#### `last_observed_activity_date` *(date, optional)*

**Drives stale detection (§3.5).** The most recent date you have evidence
the venue actually did something (held a meeting, published a document,
issued a statement, updated its main page).

⚠ Distinct from `last_verified_date` (when you last reviewed the row).
Stale detection thresholds are in `coding_manual.md §6`.

### 3.4 Lifecycle and rhythm

#### `current_state` *(required, 6 values)*

| Value | Definition |
|---|---|
| `announced` | Publicly announced but not yet operational (no first meeting, no first output). |
| `active` | Currently operating. (Default for nearly all rows.) |
| `dormant` | Apparently inactive but not formally terminated. Surfaced via stale detection. |
| `absorbed` | Merged into another AGV. Requires `absorbed_into` relation in `agv_relation.csv`. |
| `terminated` | Formally ended (mandate completed or revoked). |
| `succeeded` | Replaced by a successor venue with a distinct identity. Requires `succeeds` relation. |

**Transitions are append-only** to `agv_lifecycle.csv`. Don't backfill —
record the date you confirmed the transition.

#### `convening_frequency` *(required, 5 values)*

Both descriptive and operational — drives stale-detection thresholds.

| Value | Definition | Stale threshold (months since LOA) |
|---|---|---:|
| `continuous` | Standing body operating year-round. | 6 |
| `annual` | Meets once a year. | 18 |
| `biennial` | Meets every two years. | 30 |
| `ad_hoc` | Convened as needed, no fixed cadence. | 24 |
| `one_off` | Single event (a summit, a one-time convening). | **excluded** from stale detection |

### 3.5 Reference and verification

#### `primary_reference_url` *(required, URL)*

The single authoritative URL for the venue. Must be a **verification
source** per `CLAUDE.md §5.2` (the venue's own official site, founding
document, or canonical first-party page). Never a discovery source
(OECD.AI Navigator entry, IAPP tracker entry, news article).

#### `last_verified_date` *(date)*

When the maintainer last confirmed the row's data is current.

### 3.6 Field-level confidence (4 columns)

`confidence_entity_type`, `confidence_founded_date`,
`confidence_current_state`, `confidence_legal_character`.

| Value | Meaning |
|---|---|
| `high` | Multiple independent sources agree; the value is uncontroversial. |
| `medium` | Single source confirms, OR multiple sources but with minor inconsistency, OR plausible inference from indirect evidence. |
| `low` | Ambiguous or weakly supported; flagged for re-review. |

Each `confidence_*` column requires ≥1 row in `agv_evidence.csv` for
that `(agv_id, field_name)` pair (CLAUDE.md §4.8). The column reflects
the **highest-confidence** evidence row for that field.

### 3.7 Human verification

#### `human_verified_at` *(date, optional)*

ISO date of most recent human review. NULL = never human-reviewed.

#### `human_verified_fields` *(text, comma-separated)*

Field names verified by a human. Conventionally the four
confidence-tracked fields: `entity_type,founded_date,current_state,legal_character`.

For each field listed, an `agv_evidence.csv` row must exist with
`source_type='human_verification'` and the reviewer's GitHub handle.

#### `override_policy` *(required, 3 values)*

Controls what the monthly LLM re-run may do.

| Value | Behavior |
|---|---|
| `lock_verified_only` *(default)* | LLM may propose updates to fields **not** in `human_verified_fields`. Verified-field disagreements surface as **conflicts** (§4.7), never silent overwrites. |
| `lock_all` | LLM may not propose any update; row is fully frozen. Reserved for high-stakes / contested rows. |
| `allow_llm_update` | LLM may overwrite any field. Used sparingly for high-churn metadata (e.g., a rapidly-changing membership count). |

### 3.8 Free text

#### `notes` *(text, optional)*

Free-text annotation. Conventions:

- Cite migrations: `"Reclassified in v0.3 as ..."`.
- Record provenance of unusual codings.
- Annotate evolution: `"[2026-05-13] entity_type changed industry_consortium → multistakeholder_coalition after adding civil society seats."`
- Avoid duplicating evidence; that belongs in `agv_evidence.csv`.

---

## 4. `agv_relation.csv` field reference

| Field | Type | Notes |
|---|---|---|
| `source_agv` | text | The agv_id at the canonical "from" end. |
| `target_agv` | text | The agv_id at the canonical "to" end. |
| `relation_type` | enum | See table below. |
| `start_date` | ISO date | When the relation became effective. |
| `end_date` | ISO date / NULL | NULL = ongoing. |
| `source_url` | text | Verification URL for the relation itself. |
| `notes` | text | Free text. |

### `relation_type` values (7)

Stored in **canonical direction only**; reverse is computed at display time.

| Value | Canonical direction | Reverse (display only) | Example |
|---|---|---|---|
| `parent_of` | parent → child | `child_of` | `iso_iec_sc42` parent_of `iso_sc42_wg3` |
| `succeeds` | successor → predecessor | `succeeded_by` | `gpai_integrated` succeeds `gpai_2020` |
| `absorbed_into` | absorbed → absorber | `absorbed` | `cahai` absorbed_into `coe_ai_convention` |
| `coordinates_with` | symmetric (pick lexicographic source) | (same) | `uk_aisi` coordinates_with `us_aisi` |
| `references_principles_of` | adopter → original | `principles_referenced_by` | `bletchley_summit` references_principles_of `oecd_ai_principles` |
| `convenes_within` | track → parent conference | `convenes` | `neurips_ml_safety` convenes_within (NeurIPS — but NeurIPS itself is not an AGV; this is a notional example) |
| `member_of` | member → coalition | `has_member` | `uk_aisi` member_of `aisi_network` |

⚠ A common bug is duplicating a relation in both directions. Don't —
store once, in canonical direction.

---

## 5. `agv_evidence.csv` field reference

One row per `(agv_id, field_name, source_url, accessed_at)`.

| Field | Type | Notes |
|---|---|---|
| `agv_id` | text | FK to `agv.csv`. |
| `field_name` | text | Which column in `agv.csv` this row evidences. |
| `source_url` | text | URL of the source. |
| `source_type` | enum | See table below. |
| `accessed_at` | ISO date | When you saw this source. |
| `evidence_note` | text | Quote, paraphrase, or classifier rationale. |
| `reviewer` | text | GitHub handle (for human) or model version (for LLM). |
| `confidence` | `high`/`medium`/`low` | How confident this **source** makes you in the field's value. |

### `source_type` values (11)

| Value | Use when |
|---|---|
| `official_site` | The venue's own website. |
| `founding_document` | Treaty, charter, MOU, executive order, royal decree. |
| `press_release` | Official press release, even if hosted on a third-party platform. |
| `oecd_navigator` | OECD.AI Policy Navigator entry. |
| `iapp_tracker` | IAPP Global AI Law and Policy Tracker entry. |
| `unesco_gaigo` | UNESCO Global AI Ethics & Governance Observatory. |
| `news` | Reputable news outlet (Tech Policy Press, MIT Tech Review, etc.). |
| `academic_paper` | Peer-reviewed paper documenting the venue. |
| `human_verification` | Human reviewer confirmation. `reviewer` = GitHub handle. |
| `llm_classification` | LLM classifier output. `source_url = "internal://classifier-run/{run_id}"`, `reviewer` = model version. |
| `other` | Anything else (rare; explain in `evidence_note`). |

### Rules

- **Every** field listed in a `confidence_*` column on `agv.csv` must
  have ≥1 evidence row.
- A field marked in `human_verified_fields` must have a
  `source_type='human_verification'` row.
- LLM classification rows are **preserved** even after human verification
  — they form the provenance trail.

---

## 6. `agv_name_history.csv` field reference

| Field | Type | Notes |
|---|---|---|
| `agv_id` | text | FK. |
| `name` | text | The name itself. |
| `name_type` | enum | See below. |
| `valid_from` | ISO date | Optional; blank = "from venue's founding". |
| `valid_to` | ISO date | NULL = current. Required for `former_*` types. |
| `source_url` | text | Where the rename was announced. |

### `name_type` values (5)

| Value | Use when |
|---|---|
| `official_en` | The current official English name. Only one row per `agv_id` may have `valid_to=NULL`. |
| `official_native` | The current official native-language name. |
| `alias` | An alternative name (project name vs. organizational name). |
| `former_official_en` | A previous official English name. `valid_to` required. |
| `abbreviation` | Acronym or short form. |

### Rename procedure

1. Add `valid_to=today` and change `name_type` from `official_en` to
   `former_official_en` on the existing current-name row.
2. Append a new row with `name_type=official_en`, `valid_from=today`,
   `valid_to=` (blank).
3. Update `agv.csv` `name_en`.

---

## 7. `agv_lifecycle.csv` field reference

Append-only state-transition log.

| Field | Type | Notes |
|---|---|---|
| `agv_id` | text | FK. |
| `from_state` | enum / "" | Empty for the initial `(NULL → active)` row. |
| `to_state` | enum (`current_state` values) | The state being entered. |
| `transition_date` | ISO date | When the transition occurred (not when you observed it). |
| `source_url` | text | Verification URL for the transition. |
| `notes` | text | Free text (often: who recorded it and why). |

### Standard transition patterns

| Pattern | Recorded as |
|---|---|
| Initial state | `(from_state="", to_state="active", transition_date=founded_date)` |
| Becomes dormant after stale review | `(active → dormant, today)` |
| Merger | `(active → absorbed, transition_date)` plus an `absorbed_into` relation |
| Mandate ends | `(active → terminated, transition_date)` |
| Replaced by successor | `(active → succeeded, transition_date)` plus a `succeeds` relation on the successor |

---

## 8. Quick lookups

### Which fields go in which CSV?

```
identity, classification, dates, state, confidence, verification → agv.csv
relations between two AGVs                                       → agv_relation.csv
"source X confirms field Y of AGV Z"                             → agv_evidence.csv
"AGV X used to be called Y"                                      → agv_name_history.csv
"AGV X transitioned to state S on date D"                        → agv_lifecycle.csv
```

### Which `entity_type` for ...?

| Situation | Pick |
|---|---|
| Standing UN/OECD/UNESCO program | `igo_initiative` |
| G7/G20/QUAD AI item | `intergov_forum` |
| Body under EU AI Act / CoE Convention | `treaty_body` |
| Partnership on AI / GPAI 2020 | `multistakeholder_coalition` |
| Frontier Model Forum / MLCommons | `industry_consortium` |
| Future of Life / CAIDP / CAIS | `intl_ngo_thinktank` |
| ELLIS / CIFAR / UNESCO Chairs Network | `academic_consortium` |
| ISO SC 42 / IEEE P7000 series / ITU FG | `standards_body_wg` |
| UK AISI / US AISI / EU AI Office | `national_regulator_intl` |
| NeurIPS ML Safety Workshop | `conference_policy_track` |
| FAccT / AIES | `standalone_governance_conference` |
| World Summit AI / CogX | `industry_conference` |
| Asilomar 2017 / Bletchley 2023 | `one_off_summit` |

### Which `geographic_scope` for ...?

| Situation | Pick |
|---|---|
| UN, OECD, ISO body | `global` |
| GPAI (G7+Korea+others) | `transregional` |
| EU AI Office, ASEAN AI WG | `regional` (set `region_code`) |
| G7, G20, QUAD | `plurilateral` |
| US-EU TTC, US-Japan AI dialogue | `bilateral_plus` |

---

## 9. Migration checklist (when adding a new AGV)

1. Choose `agv_id`. Snake_case, stable for life.
2. Fill in 32 columns of `agv.csv`. Use defaults: `override_policy=lock_verified_only`.
3. Add ≥1 `agv_evidence.csv` row per `confidence_*` field.
4. Add the initial `(NULL → active)` row in `agv_lifecycle.csv`.
5. If renamed historically, populate `agv_name_history.csv`.
6. If absorbed into / succeeds another venue, add a relation in `agv_relation.csv`.
7. Run `uv run pytest tests/test_schema.py tests/test_evidence.py -q`.
8. Regenerate `src/venues/{agv_id}.md` via `python3 scripts/generate_venue_pages.py`.
9. Append a one-line entry to `CHANGELOG.md`.
10. Commit with Conventional Commits message (`data: add new venue ...`).

---

## 10. See also

- `docs/coding_manual.md` — decision rules and edge cases for the human coder.
- `CLAUDE.md §3, §4` — the authoritative spec.
- `data/README.md` — table-level summary.
- `sources/README.md` — three-layer source architecture.
- `tools/review/README.md` — review UI workflow.
