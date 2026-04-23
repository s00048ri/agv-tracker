# CI / CD Setup Guide

This document captures the one-time setup required to make the four workflows
under `.github/workflows/` operational on GitHub and to take the site live on
Cloudflare Pages (CLAUDE.md §9 Tasks 7 + 11). None of the first-run
verification steps can be executed in a local sandbox; record every
first-run outcome in `CHANGELOG.md` so that the corresponding Done-when
items are formally closed.

---

## 1. Repository secrets

Set these in `Settings → Secrets and variables → Actions → Repository secrets`:

| Secret | Used by | Behaviour if unset |
|---|---|---|
| `ANTHROPIC_API_KEY` | `monthly_fetch.yml` | Classifier falls back to `--mock`; workflow still succeeds and opens a PR. |
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
2. Alternative: run `wrangler pages project create agv-tracker` locally
   after `wrangler login`.
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
- **Cloudflare deploy failing with 401**: the token needs
  `Account: Cloudflare Pages: Edit` and, for custom domain moves,
  `Zone: DNS: Edit` on the target zone.
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

## 6. File map (what lives where)

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
