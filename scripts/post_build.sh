#!/usr/bin/env bash
# Post-build: copy static assets that Observable Framework does not emit
# into the dist/ output tree so Cloudflare Pages picks them up at its
# expected root paths (CLAUDE.md §9 Task 11).
#
# Invoked by `npm run build` after `observable build`.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d "dist" ]]; then
    echo "post_build: dist/ not found — did observable build succeed?" >&2
    exit 1
fi

# Static passthrough files.
for f in _headers robots.txt; do
    src_path="src/$f"
    if [[ -f "$src_path" ]]; then
        cp "$src_path" "dist/$f"
        echo "post_build: copied $src_path -> dist/$f"
    fi
done
