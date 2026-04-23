# CI / CD Setup Guide

This document captures the one-time setup required to make the four workflows
under `.github/workflows/` operational on GitHub. None of the first-run
verification steps can be executed in a local sandbox; after completing the
checklist below, the first `workflow_dispatch` run should be recorded in
`CHANGELOG.md` to formally close CLAUDE.md §9 Task 7 Done-when items.

## Repository secrets

Set these in `Settings → Secrets and variables → Actions → Repository secrets`:

| Secret | Used by | Behaviour if unset |
|---|---|---|
| `ANTHROPIC_API_KEY` | `monthly_fetch.yml` | Classifier falls back to `--mock`; workflow still succeeds and opens a PR (with a `model: mock` provenance in the body). |
| `CLOUDFLARE_API_TOKEN` | `deploy.yml` | Deploy step fails. Build and tests still run on every push. |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy.yml` | Deploy step fails. |

All other tokens (`GITHUB_TOKEN`) are auto-provisioned per run.

## Cloudflare Pages project

1. Log in to the Cloudflare dashboard.
2. Create a Pages project named exactly **`agv-tracker`** (matches the
   `--project-name` in `deploy.yml`).
3. Connect it to *no* Git source — we deploy via `wrangler` from CI.
4. Configure a custom domain later (optional; production URL will be
   `https://agv-tracker.pages.dev/` by default).

## First-run verification checklist (Task 7 Done-when)

Do these in order after merging the Task 7 commit:

1. **monthly_fetch**: Go to `Actions → monthly-fetch → Run workflow`, pick
   `dry_run: true` for the first invocation (only uploads the PR body as an
   artifact — no PR is opened). Inspect the artifact. When the output looks
   sensible, re-run with `dry_run: false` to produce the real PR.
   - Expected: a PR branch `monthly-update/YYYY-MM` with the `monthly-update`
     label and a body matching the §9 Task 6 output format.
2. **deploy**: Push any trivial change into `src/` (or dispatch the workflow
   manually). Verify the Cloudflare Pages deployment URL appears in the
   workflow summary. Record that URL in `CHANGELOG.md`.
3. **validate**: Open a trivial PR. Confirm the three jobs (`python`, `node`,
   `linkcheck`) all run and pass. The Python job's coverage gate
   (`pipelines.diff ≥ 90%`) should turn green automatically.
4. **linkcheck**: Trigger it via `Run workflow`. Confirm that no issue is
   created when all URLs are healthy; then intentionally break a URL in
   `sources/registry.yml` on a branch to observe the issue-creation path.

## Notes on workflow behaviour

- `monthly_fetch.yml` uses `peter-evans/create-pull-request@v7` with
  `add-paths: data/, sources/coverage_matrix.md`. `monthly_pr_body.md` is
  deliberately **not** staged — it lives only as the PR body.
- `validate.yml` enforces `--cov-fail-under=90` on `pipelines.diff`,
  preserving the Task 6 achievement. If the gate fails, the fix is always
  to add tests, never to lower the threshold.
- `linkcheck.yml` uses `--accept 200..=299,429` so that upstream rate
  limiting (HTTP 429) does not create false-positive issues.
- `lycheeverse/lychee-action@v2` reads URLs out of Markdown, YAML, and plain
  text automatically; no explicit config file is required.

## Troubleshooting

- **Playwright install failing**: bump `actions/setup-node` and re-pin
  `playwright` in `pyproject.toml`. For the monthly fetch, the workflow uses
  `uv run playwright install --with-deps chromium` which already installs
  system libraries; if that regresses, switch to `--only-shell` and add the
  apt packages explicitly.
- **PR body too large**: GitHub caps PR bodies at ~65k characters. If a
  monthly run exceeds that, `peter-evans/create-pull-request` will truncate.
  `monthly_update.sh` currently produces ~1000-line bodies for the OECD.AI
  fixture which is well inside the limit, but once more fetchers are added
  (Task 3 gap-fill), revisit this.
- **Cloudflare deploy failing with 401**: the token needs `Account: Cloudflare
  Pages: Edit` AND `Zone: DNS: Edit` if a custom domain is configured.
