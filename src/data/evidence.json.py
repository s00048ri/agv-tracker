#!/usr/bin/env python3
"""Data loader: emit agv_evidence.csv as JSON for the site.

Consumers filter by `agv_id` client-side; we ship the full file because it
is only ~100 KB for the 106-AGV seed dataset.
"""
import csv
import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "agv_evidence.csv"

with DATA_PATH.open(newline="") as f:
    records = list(csv.DictReader(f))

json.dump(records, sys.stdout, indent=2, ensure_ascii=False)
