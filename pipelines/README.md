# `pipelines/` — ETL for the AGV Tracker

Python 3.12+ pipeline that turns upstream AI-governance-venue directories into
candidate AGV records. CLAUDE.md §5 splits the source landscape into
discovery / verification / background layers; this package hosts the
**discovery** fetchers plus the normalize / classify / diff stages that feed
monthly PRs.

| Subpackage | Purpose | Status |
|---|---|---|
| `fetchers/` | Per-source discovery fetchers (§5.2) | §9 Task 4 — OECD.AI online |
| `normalize.py` | RawVenue → AGV candidate rows | §9 Task 6 (pending) |
| `classify.py` | LLM-assisted AGVO classification | §9 Task 5 (pending) |
| `diff.py`     | Lock-aware diff + stale detection | §9 Task 6 (pending) |
| `candidates_to_pr.py` | Emits Markdown PR body | §9 Task 6 (pending) |

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

## Testing

```bash
uvx pytest tests/ -q            # all tests, offline (no playwright needed)
uvx pytest tests/test_fetchers.py -q   # fetcher suite only
```

Fixture tests must not hit the network. If you add a test that exercises
live fetch, gate it with `@pytest.mark.skipif(offline, …)` or move it to
a separate `tests/test_fetchers_live.py` that CI runs out of band.
