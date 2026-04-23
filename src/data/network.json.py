#!/usr/bin/env python3
"""Data loader: emit the AGV relation network as ``{nodes, links}`` JSON.

Used by ``src/dashboard.md`` §7 through ``src/components/networkGraph.js``.
Deterministic: nodes and links are sorted so the loader output is stable
under unchanged inputs (enables content-hashed FileAttachment URLs).
"""
import csv
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def main() -> None:
    nodes: list[dict] = []
    with (DATA_DIR / "agv.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            nodes.append({
                "id": row["agv_id"],
                "name": row["name_en"],
                "entity_type": row.get("entity_type", ""),
                "current_state": row.get("current_state", ""),
                "convening_frequency": row.get("convening_frequency", ""),
                "geographic_scope": row.get("geographic_scope", ""),
            })
    nodes.sort(key=lambda n: n["id"])

    links: list[dict] = []
    rel_path = DATA_DIR / "agv_relation.csv"
    if rel_path.exists():
        with rel_path.open(newline="") as f:
            for row in csv.DictReader(f):
                links.append({
                    "source": row["source_agv"],
                    "target": row["target_agv"],
                    "relation_type": row["relation_type"],
                    "start_date": (row.get("start_date") or "").strip(),
                })
    links.sort(key=lambda l: (l["source"], l["target"], l["relation_type"]))

    json.dump({"nodes": nodes, "links": links}, sys.stdout,
              indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
