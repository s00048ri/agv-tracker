"""Flask server for the AGV review UI.

Serves a single page at ``/`` driven by ``review.html`` + vanilla JS,
backed by a JSON API that reads a ``DiffReport`` and persists decisions
to ``decisions.json``.

Endpoints
---------
GET  /                       — review.html
GET  /api/state              — full state: report metadata + candidates + decisions
GET  /api/enums              — ENUM_BY_FIELD + EDITABLE_FIELDS (for dropdowns)
POST /api/decision           — upsert a single decision; persists to disk
POST /api/reviewer           — set the reviewer handle
GET  /healthz                — liveness

Run
---
    python -m tools.review.server path/to/report.json \\
        --decisions decisions.json --port 8765
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.review.schema import (
    EDITABLE_FIELDS,
    ENUM_BY_FIELD,
    decision_key,
    validate_decision,
)

# Flask is loaded lazily so flatten_report() and DecisionsStore remain importable
# without the optional [review] extras installed (handy for tests).

log = logging.getLogger("review.server")

# ---------------------------------------------------------------------------
# Candidate flattening — turn a DiffReport into a flat list the UI iterates
# ---------------------------------------------------------------------------


def flatten_report(report: dict) -> list[dict]:
    """Return a flat candidate list ordered as the UI displays them.

    Each entry has shape::

        {
            "category":   "new_venues" | "unverified_updates" | ... ,
            "ref":        unique-within-category key,
            "key":        "{category}:{ref}",   # global key
            "data":       category-specific payload (subset of DiffReport item)
        }
    """
    out: list[dict] = []

    for nv in report.get("new_venues") or []:
        agv_row = nv.get("agv_row") or {}
        aid = agv_row.get("agv_id") or "(unnamed)"
        out.append({
            "category": "new_venues",
            "ref": aid,
            "key": decision_key("new_venues", aid),
            "data": {
                "agv_row": agv_row,
                "evidence_rows": nv.get("evidence_rows") or [],
                "provenance": nv.get("provenance") or {},
            },
        })

    for u in report.get("unverified_updates") or []:
        ref = f"{u.get('agv_id')}:{u.get('field_name')}"
        out.append({
            "category": "unverified_updates",
            "ref": ref,
            "key": decision_key("unverified_updates", ref),
            "data": u,
        })

    for c in report.get("conflicts") or []:
        ref = f"{c.get('agv_id')}:{c.get('field_name')}"
        out.append({
            "category": "conflicts",
            "ref": ref,
            "key": decision_key("conflicts", ref),
            "data": c,
        })

    for s in report.get("stale_candidates") or []:
        aid = s.get("agv_id") or "(unknown)"
        out.append({
            "category": "stale_candidates",
            "ref": aid,
            "key": decision_key("stale_candidates", aid),
            "data": s,
        })

    for r in report.get("renames") or []:
        ref = f"{r.get('candidate_agv_id')}->{r.get('matched_agv_id')}"
        out.append({
            "category": "renames",
            "ref": ref,
            "key": decision_key("renames", ref),
            "data": r,
        })

    return out


# ---------------------------------------------------------------------------
# Decisions store (file-backed; single writer = this server, locked)
# ---------------------------------------------------------------------------


class DecisionsStore:
    def __init__(self, path: Path, report: dict, reviewer: str = ""):
        self.path = Path(path)
        self.report = report
        self._lock = threading.Lock()
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log.warning("decisions file is corrupt (%s); starting fresh", e)
                self.state = self._empty_state(reviewer)
        else:
            self.state = self._empty_state(reviewer)
        # Always re-bind to current report id (so a fresh report ignores
        # a stale decisions file).
        if self.state.get("report_id") != self.report.get("run_id"):
            log.warning(
                "decisions file is for report %s but server loaded %s; resetting",
                self.state.get("report_id"), self.report.get("run_id"),
            )
            self.state = self._empty_state(reviewer)
        if reviewer and not self.state.get("reviewer"):
            self.state["reviewer"] = reviewer
        self._flush_locked()

    def _empty_state(self, reviewer: str) -> dict:
        return {
            "report_id": self.report.get("run_id", ""),
            "reviewer": reviewer,
            "started_at": _now_iso(),
            "decisions": {},
        }

    def _flush_locked(self) -> None:
        self.path.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.state))  # deep copy

    def set_reviewer(self, handle: str) -> None:
        with self._lock:
            self.state["reviewer"] = handle.strip()
            self._flush_locked()

    def upsert(self, decision: dict) -> dict:
        key = decision_key(decision["category"], decision["ref"])
        decision["decided_at"] = _now_iso()
        with self._lock:
            self.state["decisions"][key] = decision
            self._flush_locked()
        return decision


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------


def build_app(report: dict, store: "DecisionsStore"):
    try:
        from flask import Flask, abort, jsonify, render_template, request
    except ImportError:  # pragma: no cover
        sys.stderr.write(
            "tools.review.server requires Flask. Install with:\n"
            "    pip install -e '.[review]'\n"
        )
        raise

    candidates = flatten_report(report)
    app = Flask(__name__, template_folder="templates")

    @app.get("/")
    def index() -> Any:
        return render_template("review.html")

    @app.get("/api/state")
    def state() -> Any:
        return jsonify({
            "report": {
                "run_id": report.get("run_id", ""),
                "today": report.get("today", ""),
                "canonical_size": report.get("canonical_size", 0),
                "candidate_size": report.get("candidate_size", 0),
            },
            "candidates": candidates,
            "decisions": store.snapshot(),
            "editable_fields": EDITABLE_FIELDS,
        })

    @app.get("/api/enums")
    def enums() -> Any:
        return jsonify({"enums": ENUM_BY_FIELD, "editable_fields": EDITABLE_FIELDS})

    @app.post("/api/decision")
    def decision() -> Any:
        body = request.get_json(force=True, silent=True) or {}
        errors = validate_decision(body)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400
        saved = store.upsert(body)
        return jsonify({"ok": True, "decision": saved})

    @app.post("/api/reviewer")
    def reviewer() -> Any:
        body = request.get_json(force=True, silent=True) or {}
        handle = (body.get("reviewer") or "").strip()
        if not handle:
            abort(400, "missing reviewer handle")
        store.set_reviewer(handle)
        return jsonify({"ok": True, "reviewer": handle})

    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"ok": True, "report_id": report.get("run_id", "")})

    return app


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m tools.review.server",
        description="Local Flask review UI for fetcher candidates (CLAUDE.md §4.7).",
    )
    ap.add_argument("report", type=Path, help="Path to DiffReport JSON")
    ap.add_argument("--decisions", type=Path, default=Path("decisions.json"))
    ap.add_argument("--reviewer", type=str, default="",
                    help="GitHub handle of the reviewer (saved into decisions.json)")
    ap.add_argument("--host", type=str, default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--debug", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.report.exists():
        sys.stderr.write(f"report not found: {args.report}\n")
        return 2

    report = _load_report(args.report)
    store = DecisionsStore(args.decisions, report=report, reviewer=args.reviewer)
    app = build_app(report, store)

    n = len(flatten_report(report))
    print(
        f"AGV review UI: {n} candidates from {args.report} "
        f"(decisions: {args.decisions})",
        file=sys.stderr,
    )
    print(f"  open http://{args.host}:{args.port}/", file=sys.stderr)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
