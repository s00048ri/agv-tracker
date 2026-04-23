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
