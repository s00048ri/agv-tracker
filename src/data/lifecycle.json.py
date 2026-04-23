#!/usr/bin/env python3
"""Data loader: emit agv_lifecycle.csv as JSON for the site."""
import csv
import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "agv_lifecycle.csv"

with DATA_PATH.open(newline="") as f:
    records = list(csv.DictReader(f))

json.dump(records, sys.stdout, indent=2, ensure_ascii=False)
