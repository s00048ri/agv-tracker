#!/usr/bin/env bash
# Update the three citation-carrying files after a Zenodo DOI is minted
# (CLAUDE.md §9 Task 12).
#
# Usage:
#   scripts/update_citation.sh VERSION VERSION_DOI CONCEPT_DOI [RELEASED_AT]
#
# Where:
#   VERSION       e.g. 0.3.0
#   VERSION_DOI   e.g. 10.5281/zenodo.12345678       (this tag's DOI)
#   CONCEPT_DOI   e.g. 10.5281/zenodo.12345677       (version-agnostic DOI)
#   RELEASED_AT   optional ISO date; defaults to $(date -u +%Y-%m-%d)
#
# Rewrites:
#   data/citation.json    — authoritative copy, consumed by the site
#   CITATION.cff          — GitHub "Cite this repository" widget
#   .zenodo.json          — Zenodo deposit metadata
#
# Uses python3 for safe JSON/YAML editing (no fragile sed rewrites).

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: $0 VERSION VERSION_DOI CONCEPT_DOI [RELEASED_AT]" >&2
    exit 2
fi

VERSION="$1"
VERSION_DOI="$2"
CONCEPT_DOI="$3"
RELEASED_AT="${4:-$(date -u +%Y-%m-%d)}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# DOI sanity check: must be of the form ^10\.\d+/.+$ .
if ! [[ "$VERSION_DOI" =~ ^10\.[0-9]+/.+$ ]]; then
    echo "error: VERSION_DOI '$VERSION_DOI' is not a DOI" >&2
    exit 2
fi
if ! [[ "$CONCEPT_DOI" =~ ^10\.[0-9]+/.+$ ]]; then
    echo "error: CONCEPT_DOI '$CONCEPT_DOI' is not a DOI" >&2
    exit 2
fi

# --- data/citation.json -----------------------------------------------------
python3 - <<PY
import json, re
from pathlib import Path

p = Path("data/citation.json")
d = json.loads(p.read_text(encoding="utf-8"))
version = "$VERSION"
doi = "$VERSION_DOI"
concept = "$CONCEPT_DOI"
released = "$RELEASED_AT"
year = released[:4]

d["version"] = version
d["released_at"] = released
d["doi"] = doi
d["doi_url"] = f"https://doi.org/{doi}"
d["concept_doi"] = concept
d["concept_doi_url"] = f"https://doi.org/{concept}"
d["citation_text"] = (
    f"Iida, R. ({year}). AGV Tracker: AI Governance Venues "
    f"(v{version}) [Data set]. Zenodo. https://doi.org/{doi}"
)
d["bibtex"] = (
    "@dataset{iida_" + year + "_agv_tracker,\n"
    "  author    = {Iida, Ren},\n"
    "  title     = {AGV Tracker: AI Governance Venues},\n"
    f"  year      = {{{year}}},\n"
    f"  version   = {{{version}}},\n"
    f"  publisher = {{Zenodo}},\n"
    f"  doi       = {{{doi}}},\n"
    f"  url       = {{https://doi.org/{doi}}}\n"
    "}"
)
# Drop the placeholder note once a real DOI is wired in.
if "PLACEHOLDER" not in doi and "note" in d:
    del d["note"]

p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"updated {p} -> v{version} / {doi}")
PY

# --- CITATION.cff -----------------------------------------------------------
python3 - <<PY
import re
from pathlib import Path

p = Path("CITATION.cff")
body = p.read_text(encoding="utf-8")

body = re.sub(r'(?m)^version:\s*".*"$', f'version: "$VERSION"', body)
body = re.sub(
    r'(?m)^date-released:\s*".*"$', f'date-released: "$RELEASED_AT"', body,
)

# Replace the two DOI identifier values (version DOI first, concept DOI second).
doi_line = re.compile(r'(\n  - description: "Zenodo DOI for this version"\n    type: doi\n    value: )"[^"]+"')
body = doi_line.sub(lambda m: m.group(1) + '"$VERSION_DOI"', body, count=1)
concept_line = re.compile(r'(\n  - description: "Zenodo concept DOI \(always resolves to the latest version\)"\n    type: doi\n    value: )"[^"]+"')
body = concept_line.sub(lambda m: m.group(1) + '"$CONCEPT_DOI"', body, count=1)

p.write_text(body, encoding="utf-8")
print(f"updated {p} -> v$VERSION")
PY

# --- .zenodo.json -----------------------------------------------------------
# Zenodo's own metadata does not carry its own DOI; but if we ever add a
# `related_identifiers` row pointing at the concept DOI, we'd bump it here.
# For now this file is version-stable except for authors / title updates,
# so leave it alone.
echo "update_citation: done."
