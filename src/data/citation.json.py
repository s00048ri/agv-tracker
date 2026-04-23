#!/usr/bin/env python3
"""Data loader: pass data/citation.json through to the site.

The site reads this via FileAttachment on the methodology + data-download
pages and renders the "Cite this release" block. Updating the canonical
`data/citation.json` (typically via `scripts/update_citation.sh` after a
Zenodo DOI is minted) propagates to the site on the next build.
"""
import json
import sys
from pathlib import Path

CITATION = Path(__file__).parent.parent.parent / "data" / "citation.json"

with CITATION.open(encoding="utf-8") as f:
    json.dump(json.load(f), sys.stdout, indent=2, ensure_ascii=False)
