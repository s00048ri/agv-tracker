# `pipelines/` — ETL for the AGV Tracker

Python 3.12+ pipeline that turns upstream AI-governance-venue directories into
candidate AGV records. CLAUDE.md §5 splits the source landscape into
discovery / verification / background layers; this package hosts the
**discovery** fetchers plus the normalize / classify / diff stages that feed
monthly PRs.

| Subpackage | Purpose | Status |
|---|---|---|
| `fetchers/` | Per-source discovery fetchers (§5.2) | §9 Task 4 — **all 7 discovery sources online** (OECD.AI, UNESCO GAIGO, government_pages, Tech Policy Press, IAPP, ai_deadlines, EvalCommunity map). EvalCommunity remains on §12.7 probation; see [Discovery fetcher roadmap](#discovery-fetcher-roadmap) |
| `normalize.py` | RawVenue → AGV candidate rows | §9 Task 6 — online |
| `classify.py` | LLM-assisted AGVO classification | §9 Task 5 — online |
| `diff.py`     | Lock-aware diff + stale detection | §9 Task 6 — online |
| `candidates_to_pr.py` | Emits Markdown PR body | §9 Task 6 — online |

## Setup

```bash
# Runtime deps (httpx, beautifulsoup4, pyyaml) from pyproject.toml
uv sync

# Developer deps (pytest + ruff) for tests/lint
uv sync --extra dev

# Optional scraping deps for fetchers that need a headless browser
uv sync --extra scraping
playwright install chromium
```

`playwright install chromium` downloads the browser binary used by the
static-HTTP → Playwright fallback in `pipelines/fetchers/base.py`. Do it
**once per developer machine / CI runner**; it's not covered by `uv sync`.

## Running the OECD.AI fetcher

```bash
# Default: live with fixture fallback (always produces output)
python -m pipelines.fetchers.oecd_ai > raw.jsonl

# Force live (error out on failure)
python -m pipelines.fetchers.oecd_ai --live

# Offline-friendly: use the shipped fixture
python -m pipelines.fetchers.oecd_ai --from-fixture

# Use your own HTML fixture
python -m pipelines.fetchers.oecd_ai --fixture path/to/dashboards.html
```

Output is JSON Lines on stdout (one `RawVenue` per line); a short summary
goes to stderr. Live-mode responses are cached under `.cache/oecd_ai/` by
default — delete that directory to force a refetch.

## Fetcher conventions (CLAUDE.md §9 Task 4)

Every fetcher inherits from `pipelines.fetchers.base.BaseFetcher`:

1. **Respect `robots.txt`.** `BaseFetcher` fetches and caches `/robots.txt`
   on the first call, then honours allow/deny per the project User-Agent.
   If `robots.txt` is unreachable the fetcher defaults to *allow* (fail-open);
   tighten this if you target sources with explicit disallow rules.
2. **Throttle 1 req/sec.** `BaseFetcher._throttle()` sleeps to maintain the
   minimum inter-request interval. Override `throttle_seconds` if a source
   requires slower pacing.
3. **Static HTTP first, Playwright fallback.** Call
   `fetch_html_with_fallback(url, required_selectors=…)`. If the static
   response contains all `required_selectors` the static path wins; if not
   (or on network error) Playwright is lazy-imported and used.
4. **Cache to disk.** Pass `cache_dir=Path(".cache/<source>")` to skip
   network on repeat runs. Cache keys are SHA-256(url).
5. **Emit `RawVenue` only.** Fetchers never write into `data/*.csv`
   directly — they produce the intermediate `RawVenue` dataclass which
   `normalize.py` (Task 6) converts into AGV candidate rows with paired
   verification sources.
6. **`source_role='discovery'`.** All fetcher output is discovery-layer.
   Verification sources are curated into `sources/registry.yml` by hand.

## Adding a new fetcher

1. Register the source in `sources/registry.yml` (set `fetcher_module` to
   the Python dotted path you are about to create).
2. Create `pipelines/fetchers/<source>.py` with a class inheriting from
   `BaseFetcher`. Set `source_id`, `base_url`, `required_selectors`, and
   implement `fetch() -> list[RawVenue]`.
3. Ship a fixture under `tests/fixtures/<source>/` so CI can run without
   network.
4. Add a `tests/test_fetchers_<source>.py` (or extend `test_fetchers.py`).
5. Update the first paragraph of your module docstring to record which
   strategy the live source actually required (`http_static` vs
   `playwright`). This is a CLAUDE.md §9 Task 4 step-3 contract.
6. Regenerate `sources/coverage_matrix.md` if the source's
   `entity_types_covered` changed.

## Discovery fetcher roadmap

All seven discovery sources declared in `sources/registry.yml` now
have a fetcher (`oecd_ai_navigator`, `unesco_gaigo`, the config-driven
`government_pages`, `tech_policy_press`, `iapp_ai_law_tracker`,
`ai_deadlines`, `evalcommunity_map`). The last one is on §12.7
probation — kept in the chain so we can evaluate update cadence +
deduplication empirically over the next ~3 monthly runs and decide
whether to drop it before v0.4. The monthly pipeline therefore currently surfaces only
what OECD.AI's Policy Navigator catches — roughly *national AI
strategies* and *major intergovernmental initiatives*. Non-OECD-orbit
venues are systematically invisible to the fetcher until the
corresponding module exists.

### What the current pipeline misses (worked examples)

| Venue | Type | Would be caught by | Reason it's missed today |
|---|---|---|---|
| **IASEAI** — International Association for Safe and Ethical AI | `multistakeholder_coalition` / `intl_ngo_thinktank` | `tech_policy_press` (news) or a dedicated association tracker | Not an OECD.AI Policy Observatory entry |
| **AI Safety Connect** (Paris AI Action Summit side event) | `conference_policy_track` or `one_off_summit` | `tech_policy_press`, a host-government summit fetcher, or `ai_deadlines` | Summit-adjacent events not registered in Policy Navigator |
| **AI Safety Asia (AISA)** | `intl_ngo_thinktank`, regional (Asia) | `unesco_gaigo` (regional bodies) or `tech_policy_press` | Asian regional bodies outside OECD's core focus |
| MOFA OECD-related conference page | `one_off_summit` or `intergov_forum` | Direct MOFA / host-government fetcher, or OECD.AI when the deposit lands | OECD.AI may lag the host-government announcement |

These are *representative* — the dataset's v0.3 seed of 106 venues is a
deliberate sample, not a census (CLAUDE.md §10 targets ≥10 per
`entity_type` for v1.0). Covering gaps like the above requires adding
fetchers, not hand-seeding each new venue.

### Priority order for new fetchers

Each bullet names a `sources/registry.yml` entry that already exists
and what gap its fetcher would close.

1. ~~**`unesco_gaigo`** — UNESCO Global AI Ethics and Governance
   Observatory.~~ **DONE.** Closed the "Asian / African / LAC regional
   bodies" blind spot — RAM pilot reports + country profiles +
   regional initiatives (AU / ASEAN / fAIr LAC / MENA / Pacific).
   Live strategy TBD on first online run; see
   `pipelines/fetchers/unesco_gaigo.py` docstring.
2. ~~**`government_pages`** — config-driven major-government AI pages.~~
   **DONE.** `pipelines/fetchers/government_pages.py` is one module
   driving N target pages listed in `sources/government_pages.yml`.
   Initial MVP config ships UK DSIT / US NIST / EU AI Office /
   Singapore IMDA / Canada ISED / Australia DISR. Extend to a new
   country by appending ~10 YAML lines; no Python change required.
   Live strategy TBD per target on first online run; see the module
   docstring.
3. ~~**`tech_policy_press`** — news monitoring for newly-formed
   associations, alliances, and side events.~~ **DONE.**
   `pipelines/fetchers/tech_policy_press.py` reads the site's AI-
   category RSS feed and filters to AI-governance relevance via
   `INCLUDE_REGEX` (AI / AISI / AI Office / frontier model / content
   provenance / C2PA / watermark / …). IASEAI and AI Safety Connect —
   the two user-raised examples of pipeline blind spots — are now
   caught at the first run. Article-vs-venue caveat: the fetcher
   emits one RawVenue per article; a reviewer decides which of those
   correspond to a new AGV. Live strategy TBD on first online run.
4. ~~**`iapp_ai_law_tracker`** — Global AI Law & Policy Tracker.~~
   **DONE.** `pipelines/fetchers/iapp.py` parses the tracker into
   three entry kinds (`statute` / `regulation` / `agency`); the
   `agency` rows are exactly where regulator AGVs live (EU AI Office,
   Spain AESIA, Korea PIPC AI division, India AISI, …). Extends to
   `treaty_body` coverage via CoE CAI, UN CCW GGE on LAWS, and the
   International AISI Network. Live strategy TBD on first online run;
   see the module docstring.
5. ~~**`ai_deadlines`** — academic conference deadlines aggregator.~~
   **DONE.** `pipelines/fetchers/ai_deadlines.py` filters the feed
   via INCLUDE_REGEX to governance/ethics/safety/fairness-layered
   workshops and tracks (safety / ethics / fairness / trustworthy /
   alignment / responsible / accountability / governance / policy /
   privacy / interpretability / explainability / bias + named
   conferences FAccT/AIES/EAAMO/FORC/ICAIL). Pure technical tracks
   (RL theory / GNN / distributed training / 3D vision) are rejected.
6. ~~**`evalcommunity_map`** — on probation per §12.7.~~ **DONE,
   probation preserved.** `pipelines/fetchers/evalcommunity_map.py`
   ships so the source can be evaluated empirically. Drop by setting
   `fetcher_module: null` in `sources/registry.yml` and unlinking
   from `scripts/monthly_update.sh` if the next 3 runs show stale or
   duplicated output vs UNESCO GAIGO / IAPP.

Each new fetcher is a single-file module under
`pipelines/fetchers/<source>.py` following the §Fetcher conventions
pattern (see "Adding a new fetcher" below). None of them reshape
`BaseFetcher`; the Task 4 plumbing was intentionally built to scale
to N sources.

### Pipeline-level implication

With all seven fetchers live (one on probation) the monthly
discovery surface spans:

  - OECD-member national AI strategies + policy initiatives
    (`oecd_ai_navigator`, 60 fixture records);
  - Global-South / UNESCO-aligned RAM pilots + regional bodies
    (`unesco_gaigo`, 60);
  - English-native government news for UK / US / EU / SG / CA / AU
    (`government_pages`, 23 — extend via YAML);
  - newly-formed organization and summit-side-event announcements in
    AI-policy media (`tech_policy_press`, 26);
  - enacted statutes + regulations + supervisory agencies by
    jurisdiction (`iapp_ai_law_tracker`, 40);
  - AI-governance-layered conference workshops + tracks
    (`ai_deadlines`, 25);
  - ~140 institutions aggregated by EvalCommunity (on probation,
    53).

Fixture-mode E2E now surfaces **287 candidate venues** per run. The
overlap between sources is intentional: it is how the §4.7 diff
pipeline discovers genuine conflicts (human-verified canonical value
vs. classifier proposal under a different source) and counts
matches. Live cross-source triangulation is the point — no single
source is authoritative.

## Testing

```bash
uvx pytest tests/ -q            # all tests, offline (no playwright needed)
uvx pytest tests/test_fetchers.py -q   # fetcher suite only
```

Fixture tests must not hit the network. If you add a test that exercises
live fetch, gate it with `@pytest.mark.skipif(offline, …)` or move it to
a separate `tests/test_fetchers_live.py` that CI runs out of band.
