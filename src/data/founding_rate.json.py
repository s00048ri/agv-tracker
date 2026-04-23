#!/usr/bin/env python3
"""Data loader: pre-compute annual founding counts, total and by entity_type."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "agv.csv"

annual_total = Counter()
annual_by_type = defaultdict(Counter)
annual_by_topic = defaultdict(Counter)

with DATA_PATH.open() as f:
    for row in csv.DictReader(f):
        if not row["founded_date"]:
            continue
        year = int(row["founded_date"][:4])
        annual_total[year] += 1
        annual_by_type[row["entity_type"]][year] += 1
        annual_by_topic[row["topic_focus_primary"]][year] += 1

# emit a long-format dataset: {year, count, dimension, value}
records = []
all_years = sorted(annual_total.keys())
for year in all_years:
    records.append({
        "year": year,
        "dimension": "total",
        "value": "all",
        "count": annual_total[year]
    })
for entity_type, by_year in annual_by_type.items():
    for year, count in by_year.items():
        records.append({
            "year": year,
            "dimension": "entity_type",
            "value": entity_type,
            "count": count
        })
for topic, by_year in annual_by_topic.items():
    for year, count in by_year.items():
        records.append({
            "year": year,
            "dimension": "topic_focus",
            "value": topic,
            "count": count
        })

json.dump(records, sys.stdout, indent=2)
