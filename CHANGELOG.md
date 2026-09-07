# AGV Tracker — Runtime Changelog

Runtime data/decisions accepted into the repository. Spec revisions are tracked
in `CLAUDE.md §0`.

## 2026-09-07

- **ci**: **`validate.yml` had never passed, on two defects that predate every
  change in it.** It runs only on pull requests, and this repo had none until
  2026-09-07, so the gate went unexercised from the day it was written.
  (1) `ruff check pipelines scripts tests` reported 31 findings — mostly
  `UP017` (`datetime.UTC`), import ordering, unused imports, six over-length
  lines. All mechanical; all fixed. `pyproject.toml` gains
  `[tool.ruff.lint.isort] combine-as-imports = true`, without which isort
  splits each aliased import onto its own `from X import (...)` statement and
  `tests/test_fetchers.py`'s import block goes from 12 lines to 60 against the
  file's existing style. (2) Both link-check jobs passed `--exclude-mail`,
  which lychee v2 removed; lychee rejects the invocation with a usage error
  (exit 2) before fetching a single URL. In `validate.yml` that failed the
  job on every PR; in `linkcheck.yml`, where `fail: false` masks the exit
  status, it would have filed a "broken URLs detected" issue every week off
  no broken link at all. Excluding `mailto:` is v2's default. A regression
  test now rejects the flag in either workflow. pytest: 401 green; ruff clean;
  `pipelines.diff` coverage 99%.
- **ci**: `pages_config.yml` added — a `workflow_dispatch` one-shot that sets
  the Cloudflare Pages project's `production_branch` through the REST API
  using the secrets `deploy.yml` already holds. The production branch is a
  property of the Pages project, not the repo, and `wrangler` has no
  `pages project update`, so the alternative was an undocumented click-path.
  Idempotent, and it reads back the value it set rather than trusting the
  write.
- **site**: **two runtime errors were visible on the deployed dashboard** and
  are fixed. (1) `src/dashboard.md` declared `const view = view(Inputs.radio(…))`
  — `view` is Framework's own builtin for wiring an Input as a reactive value,
  so binding the result to a `const` of the same name shadows it for the whole
  block and the call reads the not-yet-initialised binding:
  `ReferenceError: Cannot access 'view' before initialization`, which took the
  view toggle out with it. Renamed to `selectedView`. (2) `md` is an Observable
  *notebook* builtin and does not exist in Framework, so
  `${md`…`}` threw `RuntimeError: md is not defined` in `dashboard.md` (the
  per-view explanatory paragraph) and in `methodology.md` (the Zenodo citation
  note). `methodology.md` now uses `html`; `dashboard.md` renders its
  description strings through a new `renderInlineMarkdown` export in
  `viewToggle.js` (escape-then-substitute, supporting only the `**strong**`,
  `*em*` and `` `code` `` the descriptions use).
  Both errors build cleanly and only fail in the browser, and
  `tests/test_dashboard.py` had asserted the broken form
  (``"${md`${VIEW_DESCRIPTIONS[view]}`}" in body``) — a test written against
  what the file said rather than what Framework provides. The tests now reject
  `const view = view(` and scan every `src/**/*.md` for the `md` tagged
  template. pytest: 400 green (397 + 3).
- **infra**: `deploy` run 34069569021 (`workflow_dispatch` on `main`) went
  green end to end after `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`
  were provisioned and the `agv-tracker` Pages project was created: 182
  files uploaded, `✨ Deployment complete!` at
  <https://d709cd24.agv-tracker.pages.dev>, branch alias
  <https://main.agv-tracker.pages.dev>. **Task 7 Done-when #2 closed** — CI
  builds and ships to Cloudflare Pages.
- **infra**: **but the production alias <https://agv-tracker.pages.dev> serves
  Cloudflare's "Nothing is here yet" placeholder**, which is what Pages shows
  for a project with no *production* deployment. `deploy.yml` deploys with
  `--branch=main`, and `wrangler pages project create` defaults the project's
  production branch to `production` unless `--production-branch` is passed —
  so a green deploy lands as a preview and the production hostname stays
  empty. Fix is on the Pages project (Settings → production branch → `main`),
  not in the workflow. **Task 11 Done-when #1 stays open** until the
  production hostname serves the site and `scripts/verify_deployment.sh`
  passes against it; that check also still needs a normal network, since the
  sandbox this session runs in gets 403 on CONNECT to `pages.dev`.
  Recorded because the earlier version of this entry called the site live on
  the strength of the workflow log alone — "Deployment complete" names a
  deployment, not the hostname a reader will visit.
- **ci**: **the monthly pipeline opens PRs.** After the repository setting in
  `.github/CI_SETUP.md` §0.1 was enabled and saved, `monthly-fetch` run
  34070189628 completed green and opened
  <https://github.com/s00048ri/agv-tracker/pull/1> from
  `monthly-update/2026-09`. **Task 7 Done-when #1 closed** — every Task 7
  Done-when item is now met. (Run 34069575107, before the setting was saved,
  had failed on the same refusal as run #5; the setting is per-repository
  only — there is no account-level equivalent for a personal account, the
  org-level one applies to organizations.)
- **data**: that first real PR carries **0 new venues, 0 updates, 0 conflicts,
  67 stale candidates** over a canonical 118, from a candidate set of size 0.
  The automation is now proven end to end while proposing nothing, which is
  exactly what the 2026-09-05 fetcher finding predicts: five of seven
  discovery fetchers match nothing on their live targets, so there is no
  input for the classifier or the differ to work on. Rebuilding the fetchers
  against real DOM is the gate on the monthly cycle producing substance
  rather than an empty-but-valid PR. The 67 is the differ's own count under
  §3.5 thresholds and supersedes the coarser month-arithmetic estimate used
  in session notes.

## 2026-09-06

- **ci**: first `deploy` run (33993566147, push to `main`) **failed at the
  wrangler step** — `CLOUDFLARE_API_TOKEN` is not provisioned. Everything
  before it passed: venue-page regeneration, `npm ci`, and `npm run build`.
  So the Observable Framework build is green on CI, and Task 11 Done-when #1
  is blocked only on (a) the two Cloudflare repository secrets and (b) the
  `agv-tracker` Pages project existing (`.github/CI_SETUP.md` §1–§2).
- **ci**: `monthly-fetch` run #5 (33993926637) is the first run to reach PR
  creation, and it **failed there**: `GitHub Actions is not permitted to
  create or approve pull requests`. The pipeline itself succeeded and
  `monthly-update/2026-09` was pushed with `pipelines/reports/2026-09.json`,
  so no work was lost — the blocker is the repository setting
  `Settings → Actions → General → Workflow permissions`, which cannot be set
  from inside a workflow. Documented as `.github/CI_SETUP.md` §0.1 with the
  UI path, the `gh api` equivalent, and the org-level override caveat; the
  §1 secrets table no longer claims the monthly workflow "opens a PR"
  regardless of that setting. Task 7 Done-when #1 remains open.

## 2026-09-05

- **infra**: repository published at <https://github.com/s00048ri/agv-tracker>
  (public; code MIT, data CC-BY 4.0) and `main` pushed. Four workflows
  registered. Repository secrets are **not** yet provisioned, so
  `monthly-fetch` ran with the classifier in `--mock` mode and `deploy`
  has not run.
- **pipeline**: first live `monthly-fetch` on GitHub Actions
  (run 33961283592) **timed out at 30 min and was killed**.
  `BaseFetcher._can_fetch` called `urllib.robotparser.RobotFileParser.read()`,
  which calls `urllib.request.urlopen()` with no timeout; `au_disr_ai`
  accepted the connection and never responded, so the run hung for ~29.5 min.
  `government_pages`' per-target `except` could not isolate it because the
  call never returned. Fixed by fetching robots.txt through httpx under the
  fetcher's own timeout budget; Playwright launch and page defaults are now
  bounded too. Re-run 33962767018 completed in ~3 min.
- **pipeline**: the same run proposed **17 new venues, all 17 of which were
  articles** — 15 AI Snake Oil posts, a gov.uk press release, a consultation
  notice. `pipelines/venue_names.py` now rejects headlines before they become
  candidates, unwraps CDATA (which had been reaching `name_en` and `agv_id`
  as literal `<![CDATA[...]]>`), and flags the registry verification-family
  `primary_reference_url` as a placeholder for the reviewer to replace.
  Calibrated on real data in both directions: 0 of the 17 articles survive,
  112 of the 118 curated names in `data/agv.csv` pass. pytest: 397 green.
- **sources**: **the discovery layer is largely non-functional and the docs
  said otherwise.** Five of seven fetchers match nothing on their live pages,
  because their fixtures were authored to fit the selectors rather than
  captured from the sites: `initiative-card` appears 60× in
  `tests/fixtures/oecd_ai/dashboards.html` and 0× on the live OECD.AI
  dashboard; `gaigo-entry` 60 vs 0; `iapp-law-entry` 40 vs 0. A green fetcher
  test proves the parser handles its own fixture, not that the source is
  covered. `sources/registry.yml` gains `fetcher_status` /
  `fetcher_status_checked` / `fetcher_status_note` recording what each
  fetcher does against live targets, and `pipelines/README.md` no longer
  claims seven sources are online. Rebuilding them needs live DOM
  inspection, tracked as a separate task; `ai_deadlines` is the one easy fix
  (upstream `conferences.yml`) and is also the lowest-yield (~1 governance
  venue).
- **data**: stale detection flagged 67 of 118 AGVs, correctly —
  `last_observed_activity_date` sits around 2026-03/04 and the `continuous`
  threshold is 6 months (§3.5). The dataset needs a refresh pass, not a
  threshold change.

## 2026-05-13

- **docs**: `docs/codebook.md` + `docs/coding_manual.md` published.
  Codebook (589 lines): operational reference for every field and every
  enum value in the v0.3 schema, with concrete examples from current 118
  AGVs and explicit "common confusion" flags for the ambiguous pairs
  (standalone_governance_conference vs conference_policy_track, etc.).
  Coding manual (569 lines): how-to guide for the human reviewer —
  decision trees per dimension, §4.7 conflict-resolution decision tree,
  §3.5 stale-detection decision tree, edge cases (AISI Network geography,
  summit series, workshop-name drift, member-vs-venue), audit-trail rules,
  and a printable quick-reference card. Together they aim for 80%
  inter-coder agreement within 5 min/row.
- **tools**: local review UI (`tools/review/`) online. Flask app + single-page
  vanilla-JS frontend that consumes a `pipelines.diff` `DiffReport` and lets
  the maintainer Accept / Edit / Reject / Defer each candidate row before it
  gets written to canonical CSVs. Implements all five DiffReport categories
  (new_venues / unverified_updates / conflicts / stale_candidates / renames)
  with the three §4.7 conflict choices (keep_human / accept_llm /
  note_evolution) surfaced as radio buttons. Side-by-side iframe preview of
  the candidate's `primary_reference_url`, keyboard shortcuts (a/e/r/d +
  j/k), continuous persistence to `decisions.json`, resumable mid-stream.
  Companion `apply_decisions.py` writes decisions back to `data/agv.csv`,
  `agv_evidence.csv`, `agv_lifecycle.csv`, `agv_name_history.csv` with proper
  `human_verification` evidence rows and `human_verified_fields` /
  `human_verified_at` stamping; `--dry-run` by default, `--apply` to commit.
  Enum validation against AGVO v0.3; schema parity with
  `tests/test_schema.py` is itself tested. pyproject.toml adds `[review]`
  extras = flask>=3.0. pytest: 380/380 green (+20 new tests covering each
  category × action × dry-run/apply path).

## 2026-04-23

- **data**: curated batch 2 — promoted 12 AGVs from discovery-fetcher output
  into canonical data (106 → 118 AGVs). Three buckets:
  (a) 5 national AI Act competent / supervisory authorities surfaced by IAPP
  (Germany BNetzA, Italy ACN, Netherlands AP, Brazil ANPD, Korea PIPC);
  (b) 3 regional / IGO coordination bodies surfaced by UNESCO GAIGO
  (Smart Africa AI Blueprint WG, ECOWAS AI Strategy WG, UNESCO Chairs &
  UNITWIN AI Ethics Network); (c) 4 conference policy tracks surfaced by
  ai_deadlines (NeurIPS Responsible GenAI, IJCAI AI Safety Track, UAI Causal
  Safety Workshop, KDD Responsible AI Workshop). News articles (TPP /
  government_pages press releases) intentionally skipped — 記事 ≠ venue.
  Each row carries one `llm_classification` evidence row attributed to the
  fetcher pipeline plus four `human_verification` rows
  (entity_type/founded_date/current_state/legal_character) with
  reviewer=s00048ri; `override_policy=lock_verified_only`.
  +12 AGVs / +60 evidence rows / +12 lifecycle rows. Coverage matrix and
  118 venue pages regenerated. pytest: 360/360 green.
- **data**: migrated 30-AGV seed from v0.1 → v0.3 schema (Task 2). Split into
  `agv.csv` + `agv_relation.csv` (3) + `agv_evidence.csv` (120) +
  `agv_name_history.csv` (2) + `agv_lifecycle.csv` (35); reclassified FAccT and
  AIES as `standalone_governance_conference`; renamed UK AISI to "UK AI Security
  Institute" with former name preserved; all 30 rows marked
  `human_verified_fields=entity_type,founded_date,current_state,legal_character`
  with `override_policy=lock_verified_only`.
- **pipelines**: multi-feed wave for `tech_policy_press` —
  refactored from a single-feed Tech Policy Press fetcher into a
  config-driven multi-feed news monitor (same shape as
  `government_pages`). Backed by new `sources/news_feeds.yml`
  carrying 4 feeds: Tech Policy Press AI category (existing), CAIS
  AI Safety Newsletter, Import AI (Jack Clark), AI Snake Oil
  (Narayanan & Kapoor). The module name `tech_policy_press` is
  preserved for registry / monthly_update.sh compatibility despite
  becoming a generic news monitor; the historical naming is
  documented in the module + YAML headers.
  Each feed gets its own per-target BaseFetcher subclass (own
  throttle clock + robots cache + .cache/<feed_id>/ bucket); per-
  feed failures are isolated. Source_id namespace changed from
  `techpolicypress:<idx>` to `<feed_id>:<idx>` (e.g.
  `tech_policy_press:0001`, `cais_newsletter:0002`,
  `import_ai:0003`); raw_blob carries `feed_id` + `feed_name`.
  INCLUDE_REGEX gained four named-venue tokens that were previously
  filtered out: `IASEAI`, `AI Safety Connect`, `AI Safety Asia`,
  `AISA`, plus the standalone-conference acronyms FAccT / AIES /
  EAAMO / FORC. Fixtures: existing `feed.xml` renamed to
  `tech_policy_press.xml`; three new RSS fixtures (cais_newsletter,
  import_ai, ai_snake_oil) added under
  `tests/fixtures/tech_policy_press/`. CLI gains `--only` and
  `--fixture-dir` flags matching the government_pages pattern.
  fetcher output: 26 → 39 records. 7-fetcher monthly E2E: 305 → 318
  RawVenue per run. pytest: 360/360 green (349 + 11 new multi-feed
  tests; 1 existing test updated for the new source_id namespace).
- **pipelines**: multi-language wave for `government_pages` —
  6 non-English targets added to `sources/government_pages.yml`:
  Japan MOFA OECD policy hub, Japan METI AI policy + AI事業者
  ガイドライン, Korea MSIT (K-AISI announcements + AI Basic Act),
  France Élysée (AI Action Summit follow-ups + national strategy),
  Germany BMWK (BNetzA designation + KI-Strategie), China CAC
  (GenAI Interim Measures enforcement + algorithm-recommendation
  rules). Per-language `include_if_regex` covers each target's
  native AI lexicon (人工知能 / 生成AI / AISI; 인공지능 / AI안전
  연구소 / AI기본법; IA / intelligence artificielle / sommet IA;
  KI / Künstliche Intelligenz / KI-Verordnung / KI-Aufsichtsbehörde;
  人工智能 / 生成式人工智能 / 人工智能法 / 算法推荐) plus a
  word-bounded ASCII fallback for "AI" / "IA" / "KI". Each fixture
  carries one off-topic control entry to prove the regex handles
  CJK + accented Latin without leaking — care needed because
  `\bIA\b` / `\bKI\b` will match self-referential phrases like
  "kein KI-Bezug", so noise descriptions avoid the keyword.
  government_pages now drives 12 targets total; fixture-mode E2E
  yields 40 records (was 23 with 6 English-only targets).
  Combined 7-fetcher E2E rises to 305 RawVenue candidates.
  pytest: 349/349 green (345 + 4 new multilingual tests).
  **Live classifier prerequisite**: the mock classifier is
  English-only and will mislabel non-English content; the new
  YAML targets are gated behind switching to live Claude
  (--live in pipelines/classify or scripts/monthly_update.sh
  with ANTHROPIC_API_KEY set) before they go into a real PR.
- **pipelines**: **all 7 discovery fetchers online** — `ai_deadlines`
  (aideadlin.es, governance workshops filtered via
  safety/ethics/fairness/trustworthy/alignment/responsible/
  accountability/governance/policy/privacy/interpretability/
  explainability/bias regex plus named conference list FAccT/AIES/
  EAAMO/FORC/ICAIL) and `evalcommunity_map` (Global AI Governance
  Map; on §12.7 probation, kept in the chain so update cadence +
  dedup overlap can be evaluated empirically over the next ~3 runs)
  completed. `scripts/monthly_update.sh` now chains 7 fetchers
  (1a-1g); fixture-mode monthly dry-run surfaces 287 RawVenue
  records (60 OECD + 60 UNESCO + 23 gov + 26 TPP + 40 IAPP +
  25 aideadlines + 53 EvalCommunity) → 287 candidates → 277 new /
  19 updated / **9 conflict** / 17 stale / 0 rename → 4614-line PR
  body. The 9 conflicts all hit `legal_character` on research-only
  AGVs (METR / Apollo Research / ELLIS / AlgorithmWatch / Spain
  AESIA / EU AI Office) where the mock classifier over-classifies
  as `soft_law`; canonical values are human-verified (`n/a` or
  `hard_law`) so §4.7 pinpoints them as reviewer-decision items
  instead of silently overwriting. Registry entries for
  `ai_deadlines` and `evalcommunity_map` wired up; coverage matrix
  unchanged (36 sources). pytest: 345/345 green (325 + 20 new —
  10 AIDeadlines tests + 8 EvalCommunity tests + 2 regex tests).
- **pipelines**: IAPP Global AI Law and Policy Tracker fetcher online
  (follow-on to Task 4). `pipelines/fetchers/iapp.py` parses the
  tracker into three entry kinds — `statute`, `regulation`, `agency` —
  landing in `RawVenue.raw_blob.entry_kind`. The `agency` rows are
  where new `national_regulator_intl` / `treaty_body` AGV candidates
  live (EU AI Office, AESIA, CNIL AI, K-PIPC AI division, India
  AISI, Japan AISI, CAI, UN CCW GGE, International AISI Network).
  Synthetic 40-entry fixture covers 22 jurisdictions spanning
  OECD + Global South + treaty bodies. Fixture E2E: 40 records;
  raw_blob carries status, date, and authority alongside entry_kind.
  5-fetcher monthly dry-run (first time this pipeline has hit
  non-zero §4.7 conflict + update signals): 209 RawVenue (60 OECD +
  60 UNESCO + 23 gov + 26 TPP + 40 IAPP) → 209 candidates → 208 new /
  2 updated / **1 conflict** / 17 stale / 0 rename → 3397-line PR
  body. The conflict (EU AI Office `legal_character`, canonical
  `hard_law` vs classifier-proposed `soft_law`) is exactly the case
  §4.7 was built to surface — human-verified field locked,
  classifier proposal pinned to the PR for reviewer decision, not
  silently overwritten. pytest: 325/325 green (314 + 11 new IAPP
  tests). Registry: IAPP entry updated (update_frequency monthly,
  entity_types_covered adds intergov_forum, notes rewritten to
  explain the three-kind parsing).
- **pipelines**: Tech Policy Press RSS discovery fetcher online
  (follow-on to Task 4). `pipelines/fetchers/tech_policy_press.py`
  reads the site's AI-category RSS feed, preprocesses `<link>` tags
  so html.parser keeps their URL content (no lxml dependency), then
  filters items by an AI-governance relevance regex covering AI /
  AISI / AI Office / AI Act / frontier model / generative AI /
  content provenance / C2PA / watermark. Emits one RawVenue per
  qualifying article; the article-vs-venue caveat (each record is an
  article, reviewer filters which articles correspond to a new AGV)
  is documented in the module docstring. Synthetic 30-item RSS
  fixture at `tests/fixtures/tech_policy_press/feed.xml` includes
  IASEAI / AI Safety Connect / CAISI / K-AISI / CoSAI / REAIM-3
  announcement items plus 4 deliberate off-topic control items the
  regex must reject. Fixture E2E: 26 records through the filter.
  4-fetcher monthly dry-run: 169 RawVenue (60 OECD + 60 UNESCO +
  23 gov + 26 TPP) → 169 candidates → 2745-line PR body. pytest:
  314/314 green (301 + 13 new TPP tests). Registry entry updated
  (fetcher_module wired; entity_types_covered broadened to include
  intl_ngo_thinktank + industry_consortium).
- **pipelines**: government-pages discovery fetcher online (follow-on
  to Task 4). One Python module (`pipelines/fetchers/government_pages.py`)
  + one YAML config (`sources/government_pages.yml`) covers N
  government AI pages without a per-country fetcher. Initial MVP ships
  6 English-native targets: UK DSIT (Atom), US NIST news, EU AI Office,
  Singapore IMDA, Canada ISED, Australia DISR. Per-target schema:
  `id / country / language / url / list_selector / title_selector /
  link_selector / description_selector / include_if_regex / priority`.
  Extend by appending ~10 YAML lines; no Python change required.
  Per-target failures are isolated (other targets keep going). Atom
  feeds parse via BS4 html.parser fallback (no lxml dependency).
  Synthetic per-target fixtures under `tests/fixtures/government_pages/`
  (one `<target_id>.html` each) drive the offline tests.
  `scripts/monthly_update.sh` chains all 3 fetchers now; fixture-mode
  E2E: 143 RawVenue records (60 OECD + 60 UNESCO + 23 gov) → 143
  candidates → 2329-line PR body. `sources/registry.yml` gains a
  `government_pages` discovery entry; coverage matrix regenerated
  (36 sources). pytest: 301/301 green (289 + 12 new government-pages
  tests).
- **pipelines**: UNESCO GAIGO discovery fetcher online (follow-on to
  Task 4). `pipelines/fetchers/unesco_gaigo.py` (`UNESCOGaigoFetcher`)
  targets the Global AI Ethics & Governance Observatory and extracts
  three entry kinds (country profiles, RAM pilots, regional
  initiatives) into `RawVenue` records. Reuses the Task-4
  `BaseFetcher` contract verbatim: static HTTP → Playwright fallback,
  robots.txt honouring, throttle, SHA-256-keyed cache. CLI mirrors
  `oecd_ai`'s flags (`--live` / `--fixture` / `--from-fixture` /
  `--cache-dir` / `--quiet`) with live-first-fallback-to-fixture as
  default. Shipped synthetic fixture at
  `tests/fixtures/unesco_gaigo/index.html` (60 entries skewed to
  AF/MENA/LAC/Asia/Pacific — the OECD.AI blind spot). Live strategy
  (static vs Playwright) TBD on first online run — the module
  docstring instructs the first runner to update it.
  `scripts/monthly_update.sh` now chains both fetchers (step 1a + 1b),
  concatenating per-source RawVenue streams into the normalizer input.
  Local dry-run: 120 RawVenue records (60 OECD + 60 UNESCO) → 120
  normalized candidates → 1961-line PR body. `pipelines/README.md`
  roadmap updated; 2/6 discovery sources now online. pytest: 289/289
  green (280 + 9 new UNESCO tests).
- **analysis**: companion notebook online (Task 13).
  `notebooks/founding_rate_analysis.ipynb` is a deterministic
  `.ipynb` built from `scripts/generate_analysis_notebook.py` (same
  generator pattern as `generate_venue_pages.py`). It loads the v0.3
  CSVs, reproduces the dashboard's cumulative-active-population and
  annual founding-rate charts, fits a Hannan-&-Freeman-style
  density-dependent Poisson GLM
  (`foundings ~ density_prev + density_prev²`), runs the same fit
  under each of the three §6.2 views, and runs an explicit
  likelihood-ratio test against an intercept-only null model —
  χ² = 115.48, df = 2, p < 0.0001 on the v0.3 seed. Publication-
  ready PDFs (cumulative_active_population.pdf,
  founding_rate_by_view.pdf, density_dependence_poisson.pdf) are
  written to `notebooks/figures/` (git-ignored). New `[notebook]`
  extras in pyproject.toml (pandas, numpy, matplotlib, statsmodels,
  scipy, jupyter, nbformat, nbclient, ipykernel); validate.yml's
  python job now installs them, so `tests/test_notebook.py` executes
  the notebook end-to-end on CI. pytest: 280/280 green (267 + 13
  new notebook tests). Notebook contents locked by the generator's
  `--check` gate (regenerate + commit to change the analysis).
- **meta**: Zenodo DOI integration ready (Task 12). `.zenodo.json` +
  `CITATION.cff` at the repo root supply Zenodo deposit metadata and
  the GitHub "Cite this repository" widget; `data/citation.json` is the
  canonical DOI + citation text + BibTeX consumed by the site via
  `src/data/citation.json.py`. "Cite this release" blocks added to
  `src/methodology.md` and `src/data-download.md` render version DOI,
  concept DOI, preferred citation, and BibTeX with graceful
  pre-release placeholder messaging. `scripts/update_citation.sh
  VERSION VERSION_DOI CONCEPT_DOI` atomically rewrites the three
  citation-carrying files after Zenodo mints a DOI; validated against
  a 10.5281/… pattern. `.github/CI_SETUP.md §7` documents the end-to-
  end first-release flow (GitHub↔Zenodo toggle, tag + push, update
  script, commit to surface the DOI on-site). `npm run build` green
  (methodology 10 kB → 12 kB with the citation renderer). pytest:
  267/267 green (238 + 29 new citation/Zenodo tests). First DOI minting
  happens at the first `v0.3.0` tag push and will be recorded here.
- **ci**: Cloudflare Pages deployment configuration complete (Task 11).
  New `src/_headers` ships security headers (CSP tuned for Observable's
  runtime JS eval, X-Frame-Options DENY, Referrer-Policy, Permissions-
  Policy, nosniff) and long-cache rules for `/_file/* /_import/*
  /_observablehq/* /_npm/*` hashed assets. New `src/robots.txt`
  (allow-all + sitemap hint), `wrangler.toml` (name=`agv-tracker`,
  `pages_build_output_dir="dist"`), `scripts/verify_deployment.sh`
  (curl smoke over 7 routes with non-zero exit on any failure), and
  `scripts/post_build.sh` (copies `_headers`/`robots.txt` into `dist/`
  since Observable Framework does not emit them). `npm run build` now
  chains `observable build && bash scripts/post_build.sh`.
  `.github/CI_SETUP.md` rewritten into a task-by-task runbook covering
  secrets, first-deploy, custom domain + DNS + HTTPS, recurring
  workflow verification, and troubleshooting. README gains a "Live
  site" section. pytest: 238/238 green (216 + 22 new deployment-config
  tests). Production URL + custom domain verification deferred to
  first online deploy and recorded here at that point.
- **site**: force-directed relations network on the dashboard (Task 10).
  New `src/data/network.json.py` loader emits deterministic
  `{nodes, links}` from `agv.csv` (106 nodes) + `agv_relation.csv`
  (5 links). New `src/components/networkGraph.js` implements a D3
  force-directed graph with `forceSimulation` (link/manyBody/center/
  collide), drag via `d3.drag()` with simulation re-warm, pan/zoom
  via `d3.zoom()` (0.3× … 4×) on an inner `<g>`, native `<title>`
  hover tooltips on nodes and edges, a 13-colour `entity_type` palette
  (Tableau10 + 3 extras), relation-weighted edge widths
  (parent_of 2.5 → references_principles_of 0.9), inline legend,
  and `invalidation`-driven simulation teardown for Observable's
  cell re-eval. §7 section added to `dashboard.md` respecting the
  Task 9 view toggle: both endpoints must be in the filtered node
  set for an edge to survive. Interactivity (drag/zoom/hover) is
  verified only in a browser — tests enforce the D3 wiring and
  dashboard integration. `npm run build` green; dashboard.html
  22 kB → 26 kB. pytest: 216/216 green (192 + 24 new).
- **site**: sensitivity-view dashboard online (Task 9). New
  `src/components/viewToggle.js` exposes `CONTINUOUS_ENTITY_TYPES`
  (the 8 §6.2 view-1 entity_types), `RECURRING_FREQUENCIES`
  (annual/biennial), `VIEW_VALUES` / `VIEW_LABELS` / `VIEW_DESCRIPTIONS`
  tables, and the pure `filterByView(agvs, view)` function.
  `src/dashboard.md` rewritten around `Inputs.radio` reactive toggle
  driving all six analytical sections: cumulative active population,
  founding rate by entity_type (small multiples), founding rate by
  topic_focus_primary (small multiples, previously absent), lifecycle
  state distribution, topic × entity_type heatmap, and geographic_scope
  + lead_actor breakdowns. View-specific explanatory paragraph renders
  above every chart. `npm run build` green (dashboard: 22 kB). pytest:
  192/192 green (177 + 15 new dashboard/toggle structural tests).
- **site**: per-venue detail pages + evidence + verification components
  online (Task 8). `scripts/generate_venue_pages.py` emits 106
  deterministic `src/venues/{agv_id}.md` files from the CSVs (sorted,
  byte-stable, `--check` mode for CI). Pages render the prominent
  `verificationBadge` (§6.4: "Human-verified … by @reviewer" vs.
  "Awaiting human review") and `evidencePanel` (grouped by `field_name`,
  with source-type icons distinguishing `human_verification` /
  `llm_classification` / upstream registries and confidence colour
  badges). Three new JSON loaders (`evidence.json.py`, `lifecycle.json.py`,
  `name_history.json.py`) power the pages. Observable Framework
  `npm run build` now green end-to-end (0 warnings), producing 107
  venue pages + the existing top-level pages. `validate.yml` gates on
  `generate_venue_pages.py --check`; `deploy.yml` regenerates before
  build. Pre-existing scaffold blockers fixed: `src/venues/index.md`
  relative-path FileAttachment; `src/data-download.md` download link
  via `FileAttachment.href`; `package-lock.json` now committed.
  pytest: 177/177 green (155 + 22 new venue-page tests).
- **ci**: four GitHub Actions workflows online (Task 7). `monthly_fetch.yml`
  (cron `0 9 1 * *` UTC + `workflow_dispatch`; runs `scripts/monthly_update.sh`
  and opens a PR via `peter-evans/create-pull-request@v7`), `deploy.yml`
  (push to main → Observable Framework build → Cloudflare Pages via
  `wrangler-action@v3`), `validate.yml` (PR: pytest + ruff +
  `--cov-fail-under=90` on `pipelines.diff` + npm build + lychee on changed
  files), `linkcheck.yml` (weekly full-dataset lychee with issue creation
  on breakage). Setup guide at `.github/CI_SETUP.md` covers required
  secrets (`ANTHROPIC_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`)
  and Cloudflare Pages project bootstrap. `monthly_update.sh` driver
  chains fetcher → normalize → diff → candidates_to_pr with a mock
  fallback when `ANTHROPIC_API_KEY` is unset; local dry-run produces
  a 1001-line PR body. First-run PR URL + Cloudflare preview URL to be
  recorded here after `workflow_dispatch`. pytest: 155/155 green
  (131 + 24 new workflow structural tests).
- **pipelines**: normalize → diff → PR pipeline online (Task 6). `Normalizer`
  (RawVenue → v0.3 candidate + classifier-backed evidence + registry
  verification-source pairing), `Differ` (§4.7 four-case logic with
  `human_verified_fields` / `override_policy` respect, §3.5 dynamic stale
  detection excluding `one_off`, rename detection via
  `agv_name_history.csv`), and `candidates_to_pr.render_pr_body`
  (Markdown with three-checkbox conflict sections per §4.7 and
  conflict-ratio 5% gauge). Three CLIs chained as
  `oecd_ai → normalize → diff → candidates_to_pr` produce a full PR body
  from the shipped OECD.AI fixture (60 new, 17 stale). pytest: 131/131
  green; `diff.py` coverage 99%.
- **pipelines**: LLM-assisted AGVO classifier online (Task 5). Six per-dimension
  prompt templates; `Classifier` with content-hash cache, monthly budget
  guard, and pluggable backends (Anthropic live / deterministic mock);
  evidence emission (`source_type=llm_classification`,
  `source_url=internal://classifier-run/{run_id}`, reviewer=model version);
  CLI `python -m pipelines.classify` with `--input/--output/--evidence-out`
  and `--eval` subcommand. Against the 10 shipped gold examples the mock
  backend achieves 100% on all six dimensions (deterministic plumbing
  check); live Claude accuracy (≥80% entity_type, ≥70% others) TBD on first
  online run. pyproject.toml adds `[classifier]` extras = anthropic.
  pytest: 78/78 green (54 + 24 new).
- **pipelines**: OECD.AI Policy Navigator discovery fetcher online (Task 4).
  `BaseFetcher` ABC + `RawVenue` dataclass + `fetch_html_with_fallback`
  (static HTTP → Playwright) + throttle + robots.txt + disk cache;
  `OECDFetcher` CLI returns 60 records from the shipped 60-card fixture
  (`source_role=discovery`). Live strategy (static vs Playwright) TBD on
  first online run — see `pipelines/fetchers/oecd_ai.py` docstring.
  pyproject.toml adds deps (httpx, bs4, pyyaml) + `[scraping]` / `[dev]`
  extras. pytest: 54/54 green (41 existing + 13 new fetcher tests).
- **data**: expanded seed dataset to 106 AGVs (Task 3). +76 new rows across
  all 13 entity_types — every type now has ≥4 (min industry_conference=4;
  academic_consortium 0→5; treaty_body 1→5; standards_body_wg 1→11;
  national_regulator_intl 3→13). Regional coverage added: AF (AU Continental
  AI Strategy), LAC (IDB fAIr LAC), ASEAN (ASEAN AI Guide), Pacific (APRU AI).
  +304 evidence rows (all `human_verification` / reviewer=s00048ri),
  +81 lifecycle rows (76 initial + 5 later transitions: CAHAI→succeeded,
  UN HLP→terminated, REAIM Hague→succeeded, ITU FG-AI4H/AI4EE→terminated),
  +2 relations (coe_ai_convention succeeds cahai; reaim_seoul_2024 succeeds
  reaim_hague_2023). Release gate PASS.
