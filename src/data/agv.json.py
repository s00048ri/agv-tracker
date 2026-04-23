#!/usr/bin/env python3
"""Data loader: emit canonical AGV records as JSON for the site."""
import csv
import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "agv.csv"

records = []
with DATA_PATH.open() as f:
    reader = csv.DictReader(f)
    for row in reader:
        # parse founded year for time-series convenience
        row["founded_year"] = int(row["founded_date"][:4]) if row["founded_date"] else None
        records.append(row)

json.dump(records, sys.stdout, indent=2, ensure_ascii=False)
