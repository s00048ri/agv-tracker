# CI / CD Setup Guide

This document captures the one-time setup required to make the four workflows
under `.github/workflows/` operational on GitHub and to take the site live on
Cloudflare Pages (CLAUDE.md §9 Tasks 7 + 11). None of the first-run
verification steps can be executed in a local sandbox; record every
first-run outcome in `CHANGELOG.md` so that the corresponding Done-when
items are formally closed.

---

## 0. Repository settings

### 0.1 Allow Actions to open pull requests (required by `monthly_fetch.yml`)

`Settings → Actions → General → Workflow permissions` →
tick **"Allow GitHub Actions to create and approve pull requests"** → **Save**.

Without it the monthly run does everything except the last step: the
`monthly-update/YYYY-MM` branch is pushed and then PR creation fails with

```
GitHub Actions is not permitted to create or approve pull requests.
```

and the job is marked failed (observed on run 33993926637, 2026-09-05). The
pushed branch survives, so after enabling the setting either re-run
`monthly-fetch` or open the PR by hand from the existing branch — no
pipeline work is lost.

The setting is per-repository and cannot be set from inside a workflow.
Equivalent via API (needs an admin-scoped token, not `GITHUB_TOKEN`):

```bash
gh api -X PUT repos/s00048ri/agv-tracker/actions/permissions/workflow \
  -F default_workflow_permissions=write \
  -F can_approve_pull_request_reviews=true
```

Note that the org/enterprise-level equivalent of this setting, where one
exists, overrides the repository one — if the checkbox is greyed out, it
has to be enabled at the owner level first.

---

## 1. Repository secrets

Set these in `Settings → Secrets and variables → Actions → Repository secrets`:

| Secret | Used by | Behaviour if unset |
|---|---|---|
| `ANTHROPIC_API_KEY` | `monthly_fetch.yml` | Classifier falls back to `--mock`; the pipeline still runs and proposes candidates from the fetchers, with mock classifications. Not a substitute for a real run — the proposals carry no live classifier rationale. |
| `CLOUDFLARE_API_TOKEN` | `deploy.yml` | Deploy step fails. Build and tests still run on every push. |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy.yml` | Deploy step fails. |

All other tokens (`GITHUB_TOKEN`) are auto-provisioned per run.

### Creating the Cloudflare API token

1. Cloudflare dashboard → **My Profile** → **API Tokens** → **Create Token**.
2. Use the **Edit Cloudflare Workers** template or create a custom token with:
   - `Account` → `Cloudflare Pages` → `Edit`
   - `User` → `User Details` → `Read`
   - (Optional, for custom domain) `Zone` → `DNS` → `Edit` on the target zone
3. Constrain to the intended account; copy the generated secret into
   `CLOUDFLARE_API_TOKEN`.
4. Grab your account ID from **Workers & Pages** → **Overview** → sidebar
   → "Account ID". Paste into `CLOUDFLARE_ACCOUNT_ID`.

---

## 2. First deploy — Cloudflare Pages (Task 11 steps 1–2)

**Before the first main-branch push that should deploy.**

1. In the Cloudflare dashboard → **Workers & Pages** → **Create** →
   **Pages** → **Upload assets**. Name the project exactly
   **`agv-tracker`** (matches `wrangler.toml` and `deploy.yml`'s
   `--project-name`). Upload any placeholder HTML to complete project
   creation — it will be overwritten on the first CI deploy.
2. Alternative: run
   `wrangler pages project create agv-tracker --production-branch main`
   locally after `wrangler login`. **Pass `--production-branch main`** — it
   defaults to `production`, and `deploy.yml` deploys with `--branch=main`,
   so a mismatch makes every green deploy a *preview*: the commit and
   `main.agv-tracker.pages.dev` aliases serve the site while
   `agv-tracker.pages.dev` keeps showing "Nothing is here yet" (observed
   2026-09-07). On an existing project the branch is changed in the Pages
   project settings; the next deploy then populates the production
   hostname.
3. Do NOT connect a Git source in the dashboard — deployments are driven
   from GitHub Actions via `cloudflare/wrangler-action@v3`.
4. Verify the project appears at
   `https://dash.cloudflare.com/<account>/workers/pages/view/agv-tracker`
   and has no deployments yet.
5. Merge a no-op change to `main` (touching `src/`) or run
   `Actions → deploy → Run workflow` to trigger the first deploy.
6. Inspect the workflow summary for the generated preview URL
   (`https://<sha>.agv-tracker.pages.dev` for the commit, plus the
   production alias `https://agv-tracker.pages.dev`).
7. Run the smoke check locally:
   ```bash
   scripts/verify_deployment.sh https://agv-tracker.pages.dev
   ```
   Every path must return `200 OK`.
8. **Record the preview URL + smoke-check pass in `CHANGELOG.md`** —
   this closes Task 11 Done-when #1.

---

## 3. Custom domain (Task 11 steps 3–4)

### 3.1 Register the domain

1. Register `agv-tracker.org` (or an alternative) through any registrar;
   Cloudflare Registrar keeps the full flow inside one vendor if preferred.
2. If using an external registrar, set name servers to the two Cloudflare
   ones shown in the CF dashboard for the zone.

### 3.2 Attach the domain to the Pages project

1. CF dashboard → **Pages** → `agv-tracker` → **Custom domains** →
   **Set up a custom domain**.
2. Enter `agv-tracker.org` (and a `www.agv-tracker.org` alias if desired).
3. Cloudflare auto-provisions a DNS record and an SSL certificate. Expect
   the record to look like:
   ```
   agv-tracker.org   CNAME   agv-tracker.pages.dev   (proxied)
   ```
   (A/AAAA is used if the root record can't be a CNAME; Cloudflare
   handles this under the hood when the zone is on CF DNS.)
4. Wait for the certificate to become **Active** (usually < 5 minutes).
5. From the terminal:
   ```bash
   scripts/verify_deployment.sh https://agv-tracker.org
   ```
   All paths must return `200 OK` *via HTTPS*; Cloudflare also auto-
   redirects HTTP → HTTPS.

### 3.3 Update references

After the domain is live, update these files and CHANGELOG:

- `src/robots.txt` — change the `Sitemap:` host to the new domain.
- `observablehq.config.js` — update `footer:` URL.
- `README.md` — update the "Live site" section with the new URL.
- `CHANGELOG.md` — **record the production URL here** — this closes
  Task 11 Done-when #2.

---

## 4. Recurring verification after any change

Each of the four workflows carries its own Done-when item from Tasks 7 /
11. Walk through these once end-to-end after the first successful deploy:

1. **monthly_fetch** (Task 7 Done-when #1): `Actions → monthly-fetch →
   Run workflow`, `dry_run: true` first to check the artifact, then
   `dry_run: false` to produce the real PR. Record the PR URL in
   `CHANGELOG.md`.
2. **deploy** (Task 7 Done-when #2, Task 11 Done-when #1): any
   main-branch push that touches `src/` / `data/` / `sources/` /
   `observablehq.config.js` / `package.json` triggers it. First run
   was recorded in §2 above.
3. **validate**: open a trivial PR (e.g. README typo fix); the
   `python` / `node` / `linkcheck` jobs must all go green. The Python
   coverage gate (`pipelines.diff ≥ 90%`) and the
   `generate_venue_pages.py --check` gate are both part of the python
   job.
4. **linkcheck**: trigger via `Run workflow`. Should finish clean while
   all data URLs resolve. When intentional breakage occurs in
   `sources/registry.yml`, confirm an issue is opened with label
   `linkcheck`.

---

## 5. Troubleshooting

- **Playwright install failing**: bump `actions/setup-node` and re-pin
  `playwright` in `pyproject.toml`. For `monthly_fetch.yml`, the workflow
  uses `uv run playwright install --with-deps chromium`; if that regresses,
  switch to `--only-shell` and add apt packages explicitly.
- **PR body too large**: GitHub caps PR bodies at ~65k characters. Split
  `candidates_to_pr.py` output into multiple PRs or attach long sections
  as artifacts once the monthly diff exceeds this limit.
- **`GitHub Actions is not permitted to create or approve pull requests`**:
  the repository setting in §0.1 is off. Enable it, then re-run
  `monthly-fetch`; the already-pushed `monthly-update/YYYY-MM` branch is
  reused rather than recreated.
- **Cloudflare deploy failing with 401**: the token needs
  `Account: Cloudflare Pages: Edit` and, for custom domain moves,
  `Zone: DNS: Edit` on the target zone.
- **Deploy is green but `agv-tracker.pages.dev` shows "Nothing is here
  yet"**: the project has no production deployment because its production
  branch is not `main` (§2 step 2). Change it in the Pages project settings
  and re-run `deploy`; the commit-specific and `main.` aliases work
  throughout, so the build itself is not at fault.
- **Cloudflare deploy failing with 404 "project not found"**: the Pages
  project does not exist yet. Create it in the dashboard or via
  `wrangler pages project create agv-tracker` (§2 step 2) before the next
  deploy run.
- **HTTPS certificate stuck pending**: the CAA record on the parent zone
  may be blocking Cloudflare's issuer. Either remove the CAA records or
  add `0 issue "letsencrypt.org"` / `"pki.goog"`.
- **Venue detail page 404 on first deploy**: `deploy.yml` regenerates
  pages before `npm run build`, so this should self-heal. If it
  persists, check that the `generate_venue_pages.py` step succeeded in
  the workflow logs.

---

## 7. Zenodo integration + first DOI (Task 12)

Goal: every tagged `v*.*.*` GitHub release auto-mints a Zenodo DOI, and
the site's "Cite this release" blocks on `/methodology` and
`/data-download` show the minted DOI after a short manual sync step.

### 7.1 One-time Zenodo ↔ GitHub link

1. Sign in to <https://zenodo.org/> using the GitHub login (same account
   that owns the repo).
2. **Menu → GitHub**. The page lists the account's repos. Flip the
   toggle next to `s00048ri/agv-tracker` to **on**.
3. Zenodo now watches that repo for releases. `.zenodo.json` at the
   repo root controls the deposit metadata; do not remove it.

### 7.2 First release

1. Write the release notes as `docs/release-notes/vX.Y.Z.md` and merge
   them — notes worth reading are worth reviewing in a PR. Without that
   file the release falls back to GitHub's generated notes.
2. Check that `pyproject.toml` and `data/citation.json` both carry the
   version you are about to release. The workflow refuses to run
   otherwise: a Zenodo deposit whose metadata contradicts the archived
   files cannot be corrected the way a git tag can.
3. `Actions → release → Run workflow`, entering the version **without**
   the leading `v` (e.g. `0.3.0`). `gh release create` makes the tag and
   publishes the release in one step; Zenodo's webhook fires on the
   publish event.

   The workflow exists because tagging by hand is easy to get wrong and
   because some environments cannot push tags at all — a sandboxed agent
   session, for one, is typically restricted to its own branch.
4. Wait ~30 seconds. Zenodo's GitHub page will show the new deposit
   and both DOIs (version + concept).
5. Copy both DOIs.

### 7.3 Sync the DOIs into the repo

```bash
scripts/update_citation.sh 0.3.0 10.5281/zenodo.<version> 10.5281/zenodo.<concept>
```

The script rewrites `data/citation.json` and `CITATION.cff`. Commit,
push to `main`, and the next `deploy.yml` run will publish the updated
"Cite this release" blocks. At that point **record the DOI in
`CHANGELOG.md`** — this closes Task 12 Done-when #1 and #2.

### 7.4 Recurring releases

Every subsequent release repeats §7.2 + §7.3 for that version. The
concept DOI stays stable (only the version DOI changes), and the site's
BibTeX automatically points at the latest version DOI once
`scripts/update_citation.sh` runs.

---

## 8. File map (what lives where)

| File | Purpose |
|---|---|
| `.github/workflows/monthly_fetch.yml` | Monthly cron + manual dispatch; runs `scripts/monthly_update.sh` and opens a PR. |
| `.github/workflows/deploy.yml` | Main-branch push → build → Cloudflare Pages. |
| `.github/workflows/validate.yml` | PR gate: pytest + ruff + npm build + lychee on changed files. |
| `.github/workflows/linkcheck.yml` | Weekly full-dataset link check; opens issue on failure. |
| `scripts/monthly_update.sh` | Bash chain: fetch → normalize → diff → PR body. |
| `scripts/verify_deployment.sh` | Production smoke check (HTTP 200 over key routes). |
| `wrangler.toml` | Cloudflare Pages project config (`name = "agv-tracker"`, `pages_build_output_dir = "dist"`). |
| `src/_headers` | Security + cache headers applied by Cloudflare Pages. |
| `src/robots.txt` | Allow-all crawl policy + sitemap hint. |
| `.zenodo.json` | Zenodo deposit metadata (title, creators, license, keywords). |
| `CITATION.cff` | GitHub-native "Cite this repository" widget metadata. |
| `data/citation.json` | Canonical DOI + citation text + BibTeX (consumed by the site). |
| `scripts/update_citation.sh` | Post-release syncer: `VERSION VERSION_DOI CONCEPT_DOI → citation.json + CITATION.cff`. |
