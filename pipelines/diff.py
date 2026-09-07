"""Lock-aware diff + dynamic stale detection (CLAUDE.md §9 Task 6 steps 2-4).

Consumes the ``list[{agv_row, evidence_rows, provenance}]`` output of
``pipelines.normalize`` and diffs it against the canonical ``data/agv.csv``,
applying the four-case logic of CLAUDE.md §4.7:

  - **Case A (greenfield)**: canonical field is empty → `unverified_updates`.
  - **Case B (unverified update)**: canonical field has an LLM-classified
    value not listed in ``human_verified_fields`` and the candidate differs →
    `unverified_updates`.
  - **Case C (locked field)**: candidate differs from a ``human_verified_fields``
    entry under ``override_policy='lock_verified_only'``, OR any field under
    ``'lock_all'`` → `conflicts`.
  - **Case D (match)**: candidate agrees with canonical → no entry.

Also:

  - **Rename detection** (§9 Task 6 step 4): candidate ``name_en`` matching an
    ``agv_name_history.csv`` ``former_official_en`` row is treated as an
    update to the matched existing AGV, not as a brand-new venue.
  - **Dynamic stale detection** (§3.5): any canonical AGV not appearing in
    the candidate set is flagged as ``stale_candidate`` iff
    ``(today - last_observed_activity_date) ≥ threshold`` for its
    ``convening_frequency``. ``one_off`` venues are excluded.

CLI::

    python -m pipelines.diff --candidates candidates.json --output report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL = REPO_ROOT / "data" / "agv.csv"
DEFAULT_NAME_HISTORY = REPO_ROOT / "data" / "agv_name_history.csv"

log = logging.getLogger("differ")

# Stale-detection thresholds in months (CLAUDE.md §3.5).
STALE_THRESHOLDS_MONTHS: dict[str, int] = {
    "continuous": 6,
    "annual": 18,
    "biennial": 30,
    "ad_hoc": 24,
    # 'one_off' is EXPLICITLY excluded from stale detection.
}
STALE_EXCLUDED_FREQUENCIES: set[str] = {"one_off"}

# Fields we consider when diffing. founded_date is intentionally excluded:
# once set correctly for a seed row it rarely changes, and false-positive
# diffs on it (e.g., precision-only changes) would be noisy.
DIFFED_FIELDS: list[str] = [
    "entity_type",
    "governance_modality_primary",
    "topic_focus_primary",
    "geographic_scope",
    "lead_actor_primary",
    "legal_character",
    "current_state",
    "convening_frequency",
]


# ---- DiffReport data classes ----

@dataclass
class NewVenue:
    agv_row: dict
    evidence_rows: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


@dataclass
class FieldChange:
    agv_id: str
    name_en: str
    field_name: str
    existing_value: str
    proposed_value: str
    rationale: str
    source_url: str = ""


@dataclass
class Conflict:
    agv_id: str
    name_en: str
    field_name: str
    existing_value: str
    proposed_value: str
    rationale: str
    existing_verified_at: str
    override_policy: str
    source_url: str = ""


@dataclass
class Rename:
    candidate_agv_id: str
    candidate_name: str
    matched_agv_id: str
    former_name: str
    name_history_valid_to: str


@dataclass
class StaleCandidate:
    agv_id: str
    name_en: str
    convening_frequency: str
    last_observed_activity_date: str
    months_since_loa: float
    threshold_months: int


@dataclass
class DiffReport:
    run_id: str
    today: str
    canonical_size: int
    candidate_size: int
    new_venues: list[NewVenue] = field(default_factory=list)
    unverified_updates: list[FieldChange] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    stale_candidates: list[StaleCandidate] = field(default_factory=list)
    renames: list[Rename] = field(default_factory=list)
    matches_count: int = 0

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "today": self.today,
            "canonical_size": self.canonical_size,
            "candidate_size": self.candidate_size,
            "new_venues": [
                {
                    "agv_row": nv.agv_row,
                    "evidence_rows": nv.evidence_rows,
                    "provenance": nv.provenance,
                }
                for nv in self.new_venues
            ],
            "unverified_updates": [asdict(u) for u in self.unverified_updates],
            "conflicts": [asdict(c) for c in self.conflicts],
            "stale_candidates": [asdict(s) for s in self.stale_candidates],
            "renames": [asdict(r) for r in self.renames],
            "matches_count": self.matches_count,
        }


# ---- CSV loaders ----

def load_csv(path: Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---- Differ ----

class Differ:
    def __init__(
        self,
        *,
        canonical_rows: list[dict] | None = None,
        name_history_rows: list[dict] | None = None,
        today: date | None = None,
    ):
        self.canonical_rows = list(canonical_rows or [])
        self.name_history_rows = list(name_history_rows or [])
        self.today = today or datetime.now(UTC).date()

    @classmethod
    def from_paths(
        cls,
        canonical_path: Path = DEFAULT_CANONICAL,
        name_history_path: Path = DEFAULT_NAME_HISTORY,
        today: date | None = None,
    ) -> Differ:
        return cls(
            canonical_rows=load_csv(canonical_path),
            name_history_rows=load_csv(name_history_path),
            today=today,
        )

    def diff(self, candidates: list[dict]) -> DiffReport:
        run_id = (
            "diff-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8]
        )
        report = DiffReport(
            run_id=run_id,
            today=self.today.isoformat(),
            canonical_size=len(self.canonical_rows),
            candidate_size=len(candidates),
        )

        canonical_by_id: dict[str, dict] = {
            r["agv_id"]: r for r in self.canonical_rows if r.get("agv_id")
        }
        rename_map = self._build_rename_map()

        seen_canonical_ids: set[str] = set()

        for cand in candidates:
            cand_row = cand.get("agv_row", {}) or {}
            cand_id = (cand_row.get("agv_id") or "").strip()
            cand_name = (cand_row.get("name_en") or "").strip()

            matched_via_rename: str | None = None
            if cand_name and cand_id not in canonical_by_id:
                rename_hit = rename_map.get(cand_name.lower())
                if rename_hit is not None:
                    matched_agv_id, former_name, valid_to = rename_hit
                    matched_via_rename = matched_agv_id
                    report.renames.append(Rename(
                        candidate_agv_id=cand_id,
                        candidate_name=cand_name,
                        matched_agv_id=matched_agv_id,
                        former_name=former_name,
                        name_history_valid_to=valid_to,
                    ))

            effective_id = matched_via_rename or cand_id
            if effective_id in canonical_by_id:
                seen_canonical_ids.add(effective_id)
                canonical = canonical_by_id[effective_id]
                self._diff_fields(
                    cand_row=cand_row,
                    canonical=canonical,
                    provenance=cand.get("provenance") or {},
                    report=report,
                )
            else:
                report.new_venues.append(NewVenue(
                    agv_row=cand_row,
                    evidence_rows=list(cand.get("evidence_rows") or []),
                    provenance=dict(cand.get("provenance") or {}),
                ))

        # Stale detection over canonical rows not seen in candidate set
        for canonical_id, canonical in canonical_by_id.items():
            if canonical_id in seen_canonical_ids:
                continue
            stale = self._check_stale(canonical)
            if stale is not None:
                report.stale_candidates.append(stale)

        return report

    # ---- internals ----

    def _build_rename_map(self) -> dict[str, tuple[str, str, str]]:
        """Lowercase-name → (agv_id, name, valid_to) for former_official_en rows."""
        out: dict[str, tuple[str, str, str]] = {}
        for row in self.name_history_rows:
            if (row.get("name_type") or "").strip() != "former_official_en":
                continue
            name = (row.get("name") or "").strip()
            aid = (row.get("agv_id") or "").strip()
            if not name or not aid:
                continue
            # Ignore rows with valid_to blank (still-current name, shouldn't happen for former_)
            out[name.lower()] = (aid, name, (row.get("valid_to") or "").strip())
        return out

    def _diff_fields(
        self,
        *,
        cand_row: dict,
        canonical: dict,
        provenance: dict,
        report: DiffReport,
    ) -> None:
        hv_fields = {
            f.strip()
            for f in (canonical.get("human_verified_fields") or "").split(",")
            if f.strip()
        }
        override_policy = (canonical.get("override_policy") or "lock_verified_only").strip()
        verified_at = (canonical.get("human_verified_at") or "").strip()
        source_url = provenance.get("discovery_url") or cand_row.get("primary_reference_url", "")
        agv_id = canonical["agv_id"]
        name_en = canonical.get("name_en", "")

        for f in DIFFED_FIELDS:
            existing = (canonical.get(f) or "").strip()
            proposed = (cand_row.get(f) or "").strip()

            if not proposed:
                continue
            if proposed == existing:
                report.matches_count += 1
                continue

            # Determine lock status
            if override_policy == "lock_all":
                is_locked = True
            elif override_policy == "allow_llm_update":
                is_locked = False
            else:  # lock_verified_only (default)
                is_locked = f in hv_fields

            if not existing:
                # Case A — greenfield. Treated as an unverified update.
                report.unverified_updates.append(FieldChange(
                    agv_id=agv_id, name_en=name_en, field_name=f,
                    existing_value="", proposed_value=proposed,
                    rationale="greenfield: canonical field was empty",
                    source_url=source_url,
                ))
            elif is_locked:
                # Case C — conflict.
                report.conflicts.append(Conflict(
                    agv_id=agv_id, name_en=name_en, field_name=f,
                    existing_value=existing, proposed_value=proposed,
                    rationale=(
                        f"field locked by override_policy='{override_policy}'"
                        + (" and listed in human_verified_fields" if f in hv_fields else "")
                    ),
                    existing_verified_at=verified_at,
                    override_policy=override_policy,
                    source_url=source_url,
                ))
            else:
                # Case B — unverified update.
                report.unverified_updates.append(FieldChange(
                    agv_id=agv_id, name_en=name_en, field_name=f,
                    existing_value=existing, proposed_value=proposed,
                    rationale="unverified field; LLM proposed replacement",
                    source_url=source_url,
                ))

    def _check_stale(self, canonical: dict) -> StaleCandidate | None:
        freq = (canonical.get("convening_frequency") or "").strip()
        if freq in STALE_EXCLUDED_FREQUENCIES:
            return None
        threshold = STALE_THRESHOLDS_MONTHS.get(freq)
        if threshold is None:
            # Unknown / missing frequency: be conservative, skip.
            return None
        loa_s = (canonical.get("last_observed_activity_date") or "").strip()
        if not loa_s:
            return None
        try:
            loa = date.fromisoformat(loa_s)
        except ValueError:
            return None
        months_since = (self.today - loa).days / 30.44
        if months_since < threshold:
            return None
        return StaleCandidate(
            agv_id=canonical["agv_id"],
            name_en=canonical.get("name_en", ""),
            convening_frequency=freq,
            last_observed_activity_date=loa_s,
            months_since_loa=round(months_since, 1),
            threshold_months=threshold,
        )


# ---- CLI ----

def _load_candidates(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.diff",
        description=(
            "Diff normalize-output candidates against canonical data/agv.csv "
            "applying §4.7 lock-aware rules and §3.5 stale detection."
        ),
    )
    ap.add_argument("--candidates", type=Path, required=True,
                    help="JSON (array) or JSONL output from pipelines.normalize")
    ap.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    ap.add_argument("--name-history", type=Path, default=DEFAULT_NAME_HISTORY)
    ap.add_argument("--output", type=Path, help="JSON DiffReport (default: stdout)")
    ap.add_argument("--today", type=str,
                    help="override the 'today' reference date (YYYY-MM-DD)")
    ap.add_argument("--quiet", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    today = date.fromisoformat(args.today) if args.today else None
    differ = Differ.from_paths(args.canonical, args.name_history, today=today)
    candidates = _load_candidates(args.candidates)
    report = differ.diff(candidates)

    payload = json.dumps(report.as_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    print(
        f"diffed {report.candidate_size} candidate(s) against "
        f"{report.canonical_size} canonical row(s) — "
        f"{len(report.new_venues)} new / "
        f"{len(report.unverified_updates)} updated / "
        f"{len(report.conflicts)} conflict / "
        f"{len(report.stale_candidates)} stale / "
        f"{len(report.renames)} rename",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
