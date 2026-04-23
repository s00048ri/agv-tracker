#!/usr/bin/env bash
# Production smoke check for a deployed AGV Tracker site (CLAUDE.md §9 Task 11).
#
# Visits the major routes plus a representative hashed asset and asserts an
# HTTP 200 on each. Usage:
#
#   scripts/verify_deployment.sh [BASE_URL]
#
# Default BASE_URL is https://agv-tracker.pages.dev . Override to hit a
# preview URL (e.g. the PR-preview URL Cloudflare prints during deploy):
#
#   scripts/verify_deployment.sh https://main.agv-tracker.pages.dev
#
# Exit codes:
#   0 — every path responded 200.
#   1 — at least one path did not respond 200, or curl failed.

set -euo pipefail

BASE_URL="${1:-https://agv-tracker.pages.dev}"
BASE_URL="${BASE_URL%/}"  # trim trailing slash

PATHS=(
    "/"
    "/dashboard"
    "/venues/"
    "/venues/uk_aisi"
    "/venues/oecd_ai_principles"
    "/methodology"
    "/data-download"
    "/robots.txt"
)

echo "verify_deployment: checking ${#PATHS[@]} path(s) at ${BASE_URL}"
echo ""

fails=0
for path in "${PATHS[@]}"; do
    url="${BASE_URL}${path}"
    code=$(curl -fsS -o /dev/null -w "%{http_code}" --max-time 20 "$url" || echo "000")
    if [[ "$code" == "200" ]]; then
        printf "  OK   %s  ->  %s\n" "$code" "$url"
    else
        printf "  FAIL %s  ->  %s\n" "$code" "$url"
        fails=$((fails + 1))
    fi
done

echo ""
if [[ "$fails" -gt 0 ]]; then
    echo "verify_deployment: $fails path(s) failed." >&2
    exit 1
fi

echo "verify_deployment: all paths OK."
