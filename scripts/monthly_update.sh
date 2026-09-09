#!/usr/bin/env bash
# Monthly update driver (CLAUDE.md §9 Task 7).
#
# Chains:
#   1a. pipelines.fetchers.oecd_ai           — discovery fetch (OECD Policy Navigator)
#   1b. pipelines.fetchers.unesco_gaigo      — discovery fetch (UNESCO GAIGO)
#   1c. pipelines.fetchers.government_pages  — discovery fetch (config-driven government pages)
#   1d. pipelines.fetchers.tech_policy_press  — discovery fetch (news monitor)
#   1e. pipelines.fetchers.iapp               — discovery fetch (IAPP law/policy tracker)
#   1f. pipelines.fetchers.ai_deadlines       — discovery fetch (aideadlin.es, governance workshops)
#   1g. pipelines.fetchers.evalcommunity_map  — discovery fetch (§12.7 probation)
#       → RawVenue JSONL from all fetchers concatenated as the normalizer input
#   2. pipelines.normalize          — RawVenue → v0.3 candidates + classifier
#   3. pipelines.diff               — lock-aware diff vs. data/agv.csv
#   4. pipelines.candidates_to_pr   — Markdown body for the PR
#
# Output (relative to repo root):
#   monthly_pr_body.md            — consumed by peter-evans/create-pull-request
#   monthly_report.json           — raw DiffReport, scratch (gitignored)
#   pipelines/reports/YYYY-MM.json — the same report, committed. This is what
#                         gives the monthly PR a diff, and what the review UI
#                         reads: python -m tools.review.server that path.
#
# Fallback behaviour:
#   - If ANTHROPIC_API_KEY is unset, the classifier silently switches to
#     --mock. The PR body will say `model: mock` via provenance.
#   - If Playwright/Chromium is not installed, the OECD.AI fetcher falls
#     back to its shipped fixture (Task 4 contract).
#   - Either way, this script should exit 0 and produce a well-formed PR body.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WORK="${RUNNER_TEMP:-$(mktemp -d)}/monthly-update"
mkdir -p "$WORK"

TODAY="$(date -u +%Y-%m-%d)"
echo "::group::monthly_update — workspace"
echo "  REPO_ROOT = $REPO_ROOT"
echo "  WORK      = $WORK"
echo "  TODAY     = $TODAY"
echo "::endgroup::"

echo "::group::1a/4 fetch (OECD.AI)"
uv run python -m pipelines.fetchers.oecd_ai \
    --cache-dir "$WORK/oecd-cache" \
    --quiet \
    > "$WORK/raw-oecd.jsonl"
echo "  OECD.AI: $(wc -l < "$WORK/raw-oecd.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1b/4 fetch (UNESCO GAIGO)"
uv run python -m pipelines.fetchers.unesco_gaigo \
    --cache-dir "$WORK/unesco-cache" \
    --quiet \
    > "$WORK/raw-unesco.jsonl"
echo "  UNESCO GAIGO: $(wc -l < "$WORK/raw-unesco.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1c/4 fetch (government pages)"
uv run python -m pipelines.fetchers.government_pages \
    --cache-dir "$WORK/gov-cache" \
    --quiet \
    > "$WORK/raw-gov.jsonl"
echo "  government pages: $(wc -l < "$WORK/raw-gov.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1d/4 fetch (Tech Policy Press RSS)"
uv run python -m pipelines.fetchers.tech_policy_press \
    --cache-dir "$WORK/tpp-cache" \
    --quiet \
    > "$WORK/raw-tpp.jsonl"
echo "  Tech Policy Press: $(wc -l < "$WORK/raw-tpp.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1e/4 fetch (IAPP AI Law Tracker)"
uv run python -m pipelines.fetchers.iapp \
    --cache-dir "$WORK/iapp-cache" \
    --quiet \
    > "$WORK/raw-iapp.jsonl"
echo "  IAPP tracker: $(wc -l < "$WORK/raw-iapp.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1f/4 fetch (AI conference deadlines)"
uv run python -m pipelines.fetchers.ai_deadlines \
    --cache-dir "$WORK/aidl-cache" \
    --quiet \
    > "$WORK/raw-aidl.jsonl"
echo "  aideadlin.es: $(wc -l < "$WORK/raw-aidl.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

echo "::group::1g/4 fetch (EvalCommunity map — §12.7 probation)"
uv run python -m pipelines.fetchers.evalcommunity_map \
    --cache-dir "$WORK/ecom-cache" \
    --quiet \
    > "$WORK/raw-ecom.jsonl"
echo "  EvalCommunity: $(wc -l < "$WORK/raw-ecom.jsonl" | tr -d ' ') RawVenue record(s)"
echo "::endgroup::"

# Concatenate per-source RawVenue streams for the normalizer.
cat "$WORK/raw-oecd.jsonl" "$WORK/raw-unesco.jsonl" "$WORK/raw-gov.jsonl" \
    "$WORK/raw-tpp.jsonl" "$WORK/raw-iapp.jsonl" "$WORK/raw-aidl.jsonl" \
    "$WORK/raw-ecom.jsonl" > "$WORK/raw.jsonl"
echo "  combined: $(wc -l < "$WORK/raw.jsonl" | tr -d ' ') RawVenue record(s)"

CLASSIFY_FLAG="--live"
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "::warning::ANTHROPIC_API_KEY is unset; classifier will run in --mock mode"
    CLASSIFY_FLAG="--mock"
elif [[ -n "${ANTHROPIC_WORKSPACE_ID:-}" ]]; then
    # An org-scoped key is refused with a 400 unless the request names a
    # workspace; the classifier sends this as `anthropic-workspace-id`.
    echo "  classifier: live, workspace ${ANTHROPIC_WORKSPACE_ID}"
else
    echo "  classifier: live, key's own workspace"
fi

echo "::group::2/4 normalize"
uv run python -m pipelines.normalize \
    --input "$WORK/raw.jsonl" \
    --output "$WORK/candidates.json" \
    --registry "$REPO_ROOT/sources/registry.yml" \
    --cache-dir "$WORK/classifier-cache" \
    $CLASSIFY_FLAG \
    --quiet
echo "  normalized $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$WORK/candidates.json") candidate(s)"
echo "::endgroup::"

echo "::group::3/4 diff"
uv run python -m pipelines.diff \
    --candidates "$WORK/candidates.json" \
    --canonical  "$REPO_ROOT/data/agv.csv" \
    --name-history "$REPO_ROOT/data/agv_name_history.csv" \
    --output "$REPO_ROOT/monthly_report.json" \
    --today "$TODAY" \
    --quiet
echo "  report saved to monthly_report.json"
echo "::endgroup::"

# The monthly proposal is the run's only durable output: the pipeline does
# not edit data/ (a human does, after review). Commit the report under a
# dated path so the PR carries a diff at all — without this,
# peter-evans/create-pull-request finds nothing staged and opens no PR —
# and so the review UI can be pointed straight at the PR branch:
#   python -m tools.review.server pipelines/reports/YYYY-MM.json
REPORT_MONTH="$(date -u +%Y-%m)"
mkdir -p "$REPO_ROOT/pipelines/reports"
cp "$REPO_ROOT/monthly_report.json" "$REPO_ROOT/pipelines/reports/$REPORT_MONTH.json"
echo "  archived report to pipelines/reports/$REPORT_MONTH.json"

echo "::group::4/4 render PR body"
uv run python -m pipelines.candidates_to_pr \
    --report "$REPO_ROOT/monthly_report.json" \
    --output "$REPO_ROOT/monthly_pr_body.md"
echo "  body: $(wc -l < "$REPO_ROOT/monthly_pr_body.md" | tr -d ' ') line(s)"
echo "::endgroup::"

# The monthly PR doesn't edit data/ directly (data edits happen via human
# review on the PR), so per-venue pages rarely need regenerating here.
# We still run the generator defensively — it's a no-op when the committed
# pages are already in sync with data/.
echo "::group::5/5 regenerate venue pages (no-op if in sync)"
uv run python scripts/generate_venue_pages.py
echo "::endgroup::"

echo "monthly_update: OK"
