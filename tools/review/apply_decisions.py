"""Apply a ``decisions.json`` from the review UI to canonical CSVs.

Reads:
  - decisions.json   (review UI output)
  - the original DiffReport (whose path is recorded in decisions.json's
    parent context, but the script also accepts --report explicitly)

Writes:
  - data/agv.csv             (append new venues, mutate existing rows)
  - data/agv_evidence.csv    (append human_verification rows)
  - data/agv_lifecycle.csv   (append initial transitions for new venues)

Decision-action semantics
-------------------------

new_venues:
  accept  -> use candidate's agv_row as-is; add lifecycle row;
             emit human_verification evidence for all four confidence_* fields.
  edit    -> same as accept but apply the user's `edits` first; validate enums.
  reject  -> no-op.
  defer   -> no-op (re-emitted on next monthly run).

unverified_updates:
  accept  -> write proposed_value into agv.csv; emit human_verification row.
  edit    -> write the user-provided value (from edits[field_name]) instead;
             emit human_verification row.
  reject  -> no-op (existing value preserved).
  defer   -> no-op.

conflicts:
  conflict_choice = "keep_human"     -> no-op.
  conflict_choice = "accept_llm"     -> replace canonical value with proposed;
                                        emit a new human_verification row;
                                        update human_verified_at.
  conflict_choice = "note_evolution" -> same as accept_llm but also append a note.

stale_candidates:
  accept  -> transition lifecycle to 'dormant' (active → dormant); annotate.
  reject  -> no-op.  (false positive — venue is actually still active)
  defer   -> no-op.

renames:
  accept  -> append a new official_en row to agv_name_history.csv valid_from=today;
             update agv.csv name_en.
  reject/defer -> no-op.

Run
---
    python -m tools.review.apply_decisions decisions.json --report report.json --apply

Without --apply, runs as a dry-run and prints what would happen.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.review.schema import ENUM_BY_FIELD, validate_decision

log = logging.getLogger("review.apply")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"

AGV_CSV = DATA / "agv.csv"
EVIDENCE_CSV = DATA / "agv_evidence.csv"
LIFECYCLE_CSV = DATA / "agv_lifecycle.csv"
NAME_HISTORY_CSV = DATA / "agv_name_history.csv"

CONFIDENCE_FIELDS = (
    "entity_type", "founded_date", "current_state", "legal_character",
)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# CSV helpers — minimal, deterministic
# ---------------------------------------------------------------------------


def read_csv_dicts(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return header, rows


def write_csv_dicts(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in header})


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class Applier:
    """Stateful applier that batches mutations to canonical CSVs."""

    def __init__(
        self,
        *,
        report: dict,
        decisions: dict,
        data_dir: Path = DATA,
        today: str | None = None,
    ):
        self.report = report
        self.decisions = decisions
        self.reviewer = decisions.get("reviewer") or ""
        if not self.reviewer:
            raise ValueError(
                "decisions.json has no reviewer handle — set one in the UI first."
            )
        self.data_dir = Path(data_dir)
        self.today = today or _today()

        self.agv_header, self.agv_rows = read_csv_dicts(self.data_dir / "agv.csv")
        self.evidence_header, self.evidence_rows = read_csv_dicts(
            self.data_dir / "agv_evidence.csv")
        self.lifecycle_header, self.lifecycle_rows = read_csv_dicts(
            self.data_dir / "agv_lifecycle.csv")
        self.namehist_path = self.data_dir / "agv_name_history.csv"
        if self.namehist_path.exists():
            self.namehist_header, self.namehist_rows = read_csv_dicts(self.namehist_path)
        else:
            self.namehist_header, self.namehist_rows = [], []

        self._by_id = {r["agv_id"]: r for r in self.agv_rows if r.get("agv_id")}

        # Index report sections for cross-reference (new_venues need agv_row,
        # conflicts need source_url, etc.)
        self._new_venue_idx = {
            (nv.get("agv_row") or {}).get("agv_id"): nv
            for nv in (report.get("new_venues") or [])
        }
        self._update_idx = {
            f"{u['agv_id']}:{u['field_name']}": u
            for u in (report.get("unverified_updates") or [])
        }
        self._conflict_idx = {
            f"{c['agv_id']}:{c['field_name']}": c
            for c in (report.get("conflicts") or [])
        }
        self._stale_idx = {
            s["agv_id"]: s for s in (report.get("stale_candidates") or [])
        }
        self._rename_idx = {
            f"{r['candidate_agv_id']}->{r['matched_agv_id']}": r
            for r in (report.get("renames") or [])
        }

        self.log_entries: list[str] = []

    # ---- decision dispatch ---------------------------------------------

    def apply_all(self) -> dict:
        counts = {
            "new_venues_accepted": 0,
            "updates_accepted": 0,
            "conflicts_resolved": 0,
            "stale_marked_dormant": 0,
            "renames_applied": 0,
            "rejected": 0,
            "deferred": 0,
            "errors": 0,
        }
        for key, decision in (self.decisions.get("decisions") or {}).items():
            errors = validate_decision(decision)
            if errors:
                self.log_entries.append(f"SKIP {key}: validation errors: {errors}")
                counts["errors"] += 1
                continue
            cat = decision["category"]
            action = decision["action"]
            if action == "defer":
                counts["deferred"] += 1
                continue
            if action == "reject":
                counts["rejected"] += 1
                self.log_entries.append(f"REJECT {key}")
                continue
            try:
                if cat == "new_venues":
                    self._apply_new_venue(decision)
                    counts["new_venues_accepted"] += 1
                elif cat == "unverified_updates":
                    self._apply_update(decision)
                    counts["updates_accepted"] += 1
                elif cat == "conflicts":
                    self._apply_conflict(decision)
                    counts["conflicts_resolved"] += 1
                elif cat == "stale_candidates":
                    self._apply_stale(decision)
                    counts["stale_marked_dormant"] += 1
                elif cat == "renames":
                    self._apply_rename(decision)
                    counts["renames_applied"] += 1
            except Exception as e:  # noqa: BLE001
                self.log_entries.append(f"ERROR {key}: {e!r}")
                counts["errors"] += 1
        return counts

    # ---- per-category appliers ----------------------------------------

    def _apply_new_venue(self, d: dict) -> None:
        nv = self._new_venue_idx.get(d["ref"])
        if not nv:
            raise KeyError(f"new_venues ref {d['ref']!r} not in report")
        agv_row = dict(nv.get("agv_row") or {})
        # Apply user edits (validated against enums)
        for f, v in (d.get("edits") or {}).items():
            if f in ENUM_BY_FIELD and v not in ENUM_BY_FIELD[f]:
                raise ValueError(f"invalid value for {f}: {v!r}")
            agv_row[f] = v
        # Stamp human verification metadata
        agv_row["human_verified_at"] = self.today
        agv_row["human_verified_fields"] = ",".join(CONFIDENCE_FIELDS)
        agv_row.setdefault("override_policy", "lock_verified_only")
        agv_row["last_verified_date"] = self.today
        # Append AGV row (refuse on collision)
        aid = agv_row.get("agv_id")
        if not aid:
            raise ValueError("new venue has no agv_id")
        if aid in self._by_id:
            raise ValueError(f"agv_id already exists: {aid}")
        self.agv_rows.append(agv_row)
        self._by_id[aid] = agv_row
        # Emit human_verification evidence rows for each confidence_* field
        for field in CONFIDENCE_FIELDS:
            self.evidence_rows.append({
                "agv_id": aid,
                "field_name": field,
                "source_url": agv_row.get("primary_reference_url", ""),
                "source_type": "human_verification",
                "accessed_at": self.today,
                "evidence_note": (
                    f"Verified during review by {self.reviewer}. "
                    f"Comment: {d.get('comment','').strip() or '-'}"
                ),
                "reviewer": self.reviewer,
                "confidence": agv_row.get(f"confidence_{field}") or "medium",
            })
        # Also keep the original llm_classification rows the fetcher emitted,
        # to preserve provenance trail.
        for er in nv.get("evidence_rows") or []:
            self.evidence_rows.append(dict(er))
        # Lifecycle (NULL → active at founded_date)
        self.lifecycle_rows.append({
            "agv_id": aid,
            "from_state": "",
            "to_state": agv_row.get("current_state") or "active",
            "transition_date": agv_row.get("founded_date") or self.today,
            "source_url": agv_row.get("primary_reference_url", ""),
            "notes": f"Initial state recorded during review by {self.reviewer}.",
        })
        self.log_entries.append(f"NEW {aid}")

    def _apply_update(self, d: dict) -> None:
        u = self._update_idx.get(d["ref"])
        if not u:
            raise KeyError(f"unverified_updates ref {d['ref']!r} not in report")
        aid = u["agv_id"]
        field = u["field_name"]
        row = self._by_id.get(aid)
        if not row:
            raise KeyError(f"agv {aid} missing from canonical")
        # action ∈ {accept, edit} (reject/defer handled upstream)
        if d["action"] == "edit":
            edits = d.get("edits") or {}
            new_val = edits.get(field, u["proposed_value"])
        else:
            new_val = u["proposed_value"]
        if field in ENUM_BY_FIELD and new_val not in ENUM_BY_FIELD[field]:
            raise ValueError(f"invalid value for {field}: {new_val!r}")
        row[field] = new_val
        # If this field is one of the confidence-tracked four, mark it human-verified.
        if field in CONFIDENCE_FIELDS:
            verified = (row.get("human_verified_fields") or "").split(",")
            verified = [v for v in (v.strip() for v in verified) if v]
            if field not in verified:
                verified.append(field)
            row["human_verified_fields"] = ",".join(verified)
            row["human_verified_at"] = self.today
        row["last_verified_date"] = self.today
        # Evidence row
        self.evidence_rows.append({
            "agv_id": aid,
            "field_name": field,
            "source_url": u.get("source_url") or row.get("primary_reference_url", ""),
            "source_type": "human_verification",
            "accessed_at": self.today,
            "evidence_note": (
                f"Updated {field} to {new_val!r} during review by {self.reviewer}. "
                f"Comment: {d.get('comment','').strip() or '-'}"
            ),
            "reviewer": self.reviewer,
            "confidence": "high",
        })
        self.log_entries.append(f"UPDATE {aid}.{field} = {new_val!r}")

    def _apply_conflict(self, d: dict) -> None:
        c = self._conflict_idx.get(d["ref"])
        if not c:
            raise KeyError(f"conflicts ref {d['ref']!r} not in report")
        choice = d.get("conflict_choice")
        if choice == "keep_human":
            # No data change; just emit a re-verification evidence row so the
            # trail records that this conflict was reviewed.
            self.evidence_rows.append({
                "agv_id": c["agv_id"],
                "field_name": c["field_name"],
                "source_url": (
                    self._by_id.get(c["agv_id"], {}).get("primary_reference_url", "")
                ),
                "source_type": "human_verification",
                "accessed_at": self.today,
                "evidence_note": (
                    f"§4.7 conflict reviewed by {self.reviewer}: kept human value "
                    f"{c['existing_value']!r} over LLM proposal {c['proposed_value']!r}. "
                    f"Comment: {d.get('comment','').strip() or '-'}"
                ),
                "reviewer": self.reviewer,
                "confidence": "high",
            })
            self.log_entries.append(
                f"CONFLICT keep_human {c['agv_id']}.{c['field_name']}")
            return
        # accept_llm or note_evolution → write proposal
        row = self._by_id.get(c["agv_id"])
        if not row:
            raise KeyError(f"agv {c['agv_id']} missing from canonical")
        field = c["field_name"]
        new_val = c["proposed_value"]
        if d["action"] == "edit":
            new_val = (d.get("edits") or {}).get(field, new_val)
        if field in ENUM_BY_FIELD and new_val not in ENUM_BY_FIELD[field]:
            raise ValueError(f"invalid value for {field}: {new_val!r}")
        row[field] = new_val
        row["human_verified_at"] = self.today
        row["last_verified_date"] = self.today
        # Build note
        note_extra = ""
        if choice == "note_evolution":
            note_extra = (
                f"Venue evolution noted: {field} changed from "
                f"{c['existing_value']!r} (verified {c['existing_verified_at']}) "
                f"to {new_val!r}. "
            )
            existing_notes = row.get("notes") or ""
            stamp = f"[{self.today}] {note_extra.strip()}"
            row["notes"] = (existing_notes + (" | " if existing_notes else "") + stamp)
        self.evidence_rows.append({
            "agv_id": c["agv_id"],
            "field_name": field,
            "source_url": (
                c.get("source_url") or row.get("primary_reference_url", "")
            ),
            "source_type": "human_verification",
            "accessed_at": self.today,
            "evidence_note": (
                f"§4.7 conflict resolved by {self.reviewer} via choice={choice!r}: "
                f"{c['existing_value']!r} → {new_val!r}. {note_extra}"
                f"Comment: {d.get('comment','').strip() or '-'}"
            ),
            "reviewer": self.reviewer,
            "confidence": "high",
        })
        self.log_entries.append(
            f"CONFLICT {choice} {c['agv_id']}.{field} {c['existing_value']!r} -> {new_val!r}")

    def _apply_stale(self, d: dict) -> None:
        s = self._stale_idx.get(d["ref"])
        if not s:
            raise KeyError(f"stale_candidates ref {d['ref']!r} not in report")
        aid = s["agv_id"]
        row = self._by_id.get(aid)
        if not row:
            raise KeyError(f"agv {aid} missing from canonical")
        # action=accept → transition active → dormant
        row["current_state"] = "dormant"
        row["last_verified_date"] = self.today
        self.lifecycle_rows.append({
            "agv_id": aid,
            "from_state": "active",
            "to_state": "dormant",
            "transition_date": self.today,
            "source_url": row.get("primary_reference_url", ""),
            "notes": (
                f"Marked dormant during review by {self.reviewer} (stale {s['months_since_loa']}mo > "
                f"threshold {s['threshold_months']}mo). "
                f"Comment: {d.get('comment','').strip() or '-'}"
            ),
        })
        self.log_entries.append(f"STALE→dormant {aid}")

    def _apply_rename(self, d: dict) -> None:
        r = self._rename_idx.get(d["ref"])
        if not r:
            raise KeyError(f"renames ref {d['ref']!r} not in report")
        if not self.namehist_header:
            # Initialize with conventional columns from CLAUDE.md §4.5
            self.namehist_header = [
                "agv_id", "name", "name_type", "valid_from", "valid_to", "source_url",
            ]
        # Close out the existing official_en row (set valid_to=today)
        for row in self.namehist_rows:
            if (
                row.get("agv_id") == r["matched_agv_id"]
                and row.get("name_type") == "official_en"
                and not row.get("valid_to")
            ):
                row["valid_to"] = self.today
                row["name_type"] = "former_official_en"
                break
        # Append new official_en row
        self.namehist_rows.append({
            "agv_id": r["matched_agv_id"],
            "name": r["candidate_name"],
            "name_type": "official_en",
            "valid_from": self.today,
            "valid_to": "",
            "source_url": "",
        })
        # Update the canonical name_en
        canonical = self._by_id.get(r["matched_agv_id"])
        if canonical:
            canonical["name_en"] = r["candidate_name"]
            canonical["last_verified_date"] = self.today
        self.log_entries.append(
            f"RENAME {r['matched_agv_id']} -> {r['candidate_name']!r}")

    # ---- flush ---------------------------------------------------------

    def flush(self) -> None:
        write_csv_dicts(self.data_dir / "agv.csv", self.agv_header, self.agv_rows)
        write_csv_dicts(
            self.data_dir / "agv_evidence.csv",
            self.evidence_header, self.evidence_rows,
        )
        write_csv_dicts(
            self.data_dir / "agv_lifecycle.csv",
            self.lifecycle_header, self.lifecycle_rows,
        )
        if self.namehist_header:
            write_csv_dicts(
                self.namehist_path,
                self.namehist_header, self.namehist_rows,
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m tools.review.apply_decisions",
        description="Apply review-UI decisions to canonical CSVs.",
    )
    ap.add_argument("decisions", type=Path, help="Path to decisions.json")
    ap.add_argument("--report", type=Path, required=True, help="Path to DiffReport JSON")
    ap.add_argument("--data-dir", type=Path, default=DATA)
    ap.add_argument("--apply", action="store_true",
                    help="Actually write to disk; without this flag, runs dry.")
    ap.add_argument("--today", type=str, default="",
                    help="Override today's date (ISO yyyy-mm-dd) for deterministic tests.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with args.decisions.open(encoding="utf-8") as fh:
        decisions = json.load(fh)
    with args.report.open(encoding="utf-8") as fh:
        report = json.load(fh)

    if decisions.get("report_id") and decisions["report_id"] != report.get("run_id"):
        log.warning(
            "decisions.report_id (%s) != report.run_id (%s); proceeding anyway",
            decisions["report_id"], report.get("run_id"),
        )

    applier = Applier(
        report=report, decisions=decisions, data_dir=args.data_dir,
        today=args.today or None,
    )
    counts = applier.apply_all()
    for line in applier.log_entries:
        print(line)
    print()
    print("Summary:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()

    if args.apply:
        applier.flush()
        print(f"WROTE changes to {args.data_dir}")
        return 0 if counts["errors"] == 0 else 1
    print("DRY RUN — no files written. Re-run with --apply to commit changes.")
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
