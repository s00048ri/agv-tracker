"""Render a ``DiffReport`` as a monthly-update PR body (CLAUDE.md §9 Task 6 step 5).

Sections (emitted in order, each skipped if empty):

  1. Summary header + counts + §4.7 conflict-ratio gauge.
  2. ``## New venues`` — candidates whose ``agv_id`` was not seen in canonical.
  3. ``## Updates to unverified fields`` — cases A (greenfield) and B
     (unverified update) from §4.7.
  4. ``## ⚠️ Conflicts with human-verified fields`` — case C, each with the
     three labelled checkboxes (a)/(b)/(c) prescribed by §4.7.
  5. ``## Stale candidates for review`` — §3.5 dynamic thresholds.
  6. ``## Rename detections`` — matched via ``agv_name_history.csv``.

The PR body is designed so a reviewer can process one row in well under
30 seconds (CLAUDE.md §9 Task 6 Done-when #1): each item shows the exact
``(agv_id, field, current, proposed, rationale)`` tuple inline.

CLI::

    python -m pipelines.candidates_to_pr \\
        --report report.json --output pr_body.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reviewers are human, so a printable limit keeps the table readable.
_CELL_MAX = 120


def _truncate(s: str, n: int = _CELL_MAX) -> str:
    s = (s or "").replace("\n", " ").replace("|", "\\|")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _classifier_backends(report: dict) -> set[str]:
    """Backends that actually answered across this report's proposals."""
    backends: set[str] = set()
    for nv in (report.get("new_venues") or []):
        backend = (nv.get("provenance") or {}).get("backend")
        if backend:
            backends.add(str(backend))
    return backends


def render_pr_body(report: dict) -> str:
    """Render the (dict form of) a ``DiffReport`` as Markdown."""
    lines: list[str] = []

    lines.append("# AGV Tracker — monthly update proposal")
    lines.append("")
    lines.append(f"- Run: `{report.get('run_id', '?')}`")
    lines.append(f"- Date: `{report.get('today', '?')}`")
    lines.append(f"- Canonical rows: **{report.get('canonical_size', 0)}**")
    lines.append(f"- Candidate rows: **{report.get('candidate_size', 0)}**")
    lines.append("")

    # A run whose classifications came from the mock backend must say so at
    # the top. The 2026-09-07 run did not, and read as a fully classified
    # proposal set; a reviewer accepting those values would have merged
    # keyword guesses recorded as model output.
    backends = _classifier_backends(report)
    if backends and backends != {"anthropic"}:
        listed = ", ".join(f"`{b}`" for b in sorted(backends))
        lines.append(
            f"> ⚠️ **Classifications are not from a live model** (backend: {listed}). "
            "The mock backend keyword-matches; its values are plumbing output, not "
            "judgements. Treat every ontology field below as unset, and re-run with "
            "`ANTHROPIC_API_KEY` set before reviewing them on their merits."
        )
        lines.append("")

    n_new = len(report.get("new_venues") or [])
    n_upd = len(report.get("unverified_updates") or [])
    n_conf = len(report.get("conflicts") or [])
    n_stale = len(report.get("stale_candidates") or [])
    n_ren = len(report.get("renames") or [])
    n_namematch = len(report.get("name_matches") or [])
    n_match = int(report.get("matches_count", 0))

    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    lines.append(f"| New venues | {n_new} |")
    lines.append(f"| Updates to unverified fields | {n_upd} |")
    lines.append(f"| ⚠️ Conflicts (locked fields) | {n_conf} |")
    lines.append(f"| Stale candidates | {n_stale} |")
    lines.append(f"| Rename detections | {n_ren} |")
    lines.append(f"| Matched to an existing row by name | {n_namematch} |")
    lines.append(f"| Matches (no action) | {n_match} |")
    lines.append("")

    # Conflict-ratio gauge (§4.7: target ≤5%)
    reviewed = n_upd + n_conf + n_match
    if reviewed > 0:
        ratio = n_conf / reviewed
        lines.append(f"**Conflict ratio**: {ratio:.1%} ({n_conf}/{reviewed}).")
        if ratio > 0.05:
            lines.append(
                "> ⚠️ Conflict ratio exceeds the 5% target from §4.7. "
                "Consider classifier drift, re-evaluate prompts, or flag "
                "this as a genuine venue-evolution cluster."
            )
        lines.append("")

    # ---- New venues ----
    if n_new:
        lines.append("## New venues")
        lines.append("")
        for nv in report["new_venues"]:
            row = nv.get("agv_row", {})
            aid = row.get("agv_id", "?")
            name = row.get("name_en", "?")
            lines.append(f"### `{aid}` — {name}")
            lines.append("")
            lines.append(f"- entity_type: `{row.get('entity_type', '')}`")
            lines.append(
                f"- governance_modality_primary: `{row.get('governance_modality_primary', '')}`"
            )
            lines.append(f"- topic_focus_primary: `{row.get('topic_focus_primary', '')}`")
            lines.append(f"- geographic_scope: `{row.get('geographic_scope', '')}`")
            lines.append(f"- lead_actor_primary: `{row.get('lead_actor_primary', '')}`")
            lines.append(f"- legal_character: `{row.get('legal_character', '')}`")
            prov = nv.get("provenance") or {}
            disc = prov.get("discovery_url") or row.get("primary_reference_url", "")
            lines.append(f"- primary_reference_url: {row.get('primary_reference_url', '')}")
            if disc and disc != row.get("primary_reference_url", ""):
                lines.append(f"- discovery_url: {disc}")
            if row.get("notes"):
                lines.append(f"- notes: {_truncate(row['notes'])}")
            dupes = nv.get("possible_duplicates") or []
            if dupes:
                listed = ", ".join(
                    f"`{d.get('agv_id','?')}` ({d.get('name_en','')})" for d in dupes
                )
                lines.append(
                    f"- ⚠️ **may already exist**: {listed} — the names overlap but "
                    "do not match exactly, so this was left as a new-venue "
                    "proposal. Check before accepting."
                )
            lines.append("")
            lines.append("- [ ] accept new venue (merge as-is)")
            lines.append("- [ ] needs edits before merge (list in PR comments)")
            lines.append("- [ ] reject (out of scope)")
            lines.append("")

    # ---- Matched by name ----
    if n_namematch:
        lines.append("## Matched to an existing row by name")
        lines.append("")
        lines.append(
            "These candidates carried a different `agv_id` — ids are derived "
            "from whatever wording a source printed — but name an existing "
            "row exactly. They were diffed against that row rather than "
            "proposed as new."
        )
        lines.append("")
        for m in report.get("name_matches") or []:
            lines.append(
                f"- `{m.get('candidate_agv_id','?')}` "
                f"({m.get('candidate_name','')}) → `{m.get('matched_agv_id','?')}` "
                f"({m.get('matched_name','')})"
            )
        lines.append("")

    # ---- Unverified updates ----
    if n_upd:
        lines.append("## Updates to unverified fields")
        lines.append("")
        lines.append(
            "_Covers §4.7 case A (greenfield: canonical field was empty) and "
            "case B (LLM-classified field, not human-verified, differs from "
            "canonical)._"
        )
        lines.append("")
        lines.append("| agv_id | name | field | current | proposed | rationale |")
        lines.append("|---|---|---|---|---|---|")
        for u in report["unverified_updates"]:
            existing = u.get("existing_value") or "_(empty)_"
            lines.append(
                "| `{aid}` | {name} | `{f}` | `{cur}` | `{prop}` | {why} |".format(
                    aid=u.get("agv_id", ""),
                    name=_truncate(u.get("name_en", ""), 48),
                    f=u.get("field_name", ""),
                    cur=_truncate(existing, 40),
                    prop=_truncate(u.get("proposed_value", ""), 40),
                    why=_truncate(u.get("rationale", ""), 80),
                )
            )
        lines.append("")

    # ---- Conflicts (§4.7 three-checkbox format) ----
    if n_conf:
        lines.append("## ⚠️ Conflicts with human-verified fields")
        lines.append("")
        lines.append(
            "> Each conflict requires an explicit choice (§4.7). Tick ONE of "
            "(a) keep human-verified, (b) accept LLM proposal and re-verify, "
            "(c) note venue evolution."
        )
        lines.append("")
        for c in report["conflicts"]:
            aid = c.get("agv_id", "?")
            name = c.get("name_en", "?")
            fname = c.get("field_name", "?")
            lines.append(f"### `{aid}` — {name} / `{fname}`")
            lines.append("")
            lines.append(
                f"- **Human-verified value**: `{c.get('existing_value', '')}` "
                f"(verified {c.get('existing_verified_at') or '?'})"
            )
            lines.append(f"- **LLM-proposed value**: `{c.get('proposed_value', '')}`")
            lines.append(f"- **Override policy**: `{c.get('override_policy', '')}`")
            lines.append(f"- **Rationale**: {_truncate(c.get('rationale', ''), 200)}")
            if c.get("source_url"):
                lines.append(f"- **Discovery source**: {c['source_url']}")
            lines.append("")
            lines.append("- [ ] (a) keep human-verified value")
            lines.append("- [ ] (b) accept LLM proposal and re-verify")
            lines.append("- [ ] (c) note venue evolution (real change in the world)")
            lines.append("")

    # ---- Stale candidates ----
    if n_stale:
        lines.append("## Stale candidates for review")
        lines.append("")
        lines.append(
            "_§3.5 dynamic thresholds applied. `one_off` venues are excluded "
            "from this list by design._"
        )
        lines.append("")
        lines.append(
            "| agv_id | name | frequency | last observed | months since | threshold |"
        )
        lines.append("|---|---|---|---|---:|---:|")
        for s in report["stale_candidates"]:
            lines.append(
                "| `{aid}` | {name} | `{freq}` | {loa} | {m:.1f} | {t} |".format(
                    aid=s.get("agv_id", ""),
                    name=_truncate(s.get("name_en", ""), 48),
                    freq=s.get("convening_frequency", ""),
                    loa=s.get("last_observed_activity_date", ""),
                    m=float(s.get("months_since_loa", 0.0)),
                    t=s.get("threshold_months", 0),
                )
            )
        lines.append("")

    # ---- Rename detections ----
    if n_ren:
        lines.append("## Rename detections")
        lines.append("")
        lines.append(
            "_Candidates whose `name_en` matches a `former_official_en` entry "
            "in `agv_name_history.csv` are treated as updates to the matched "
            "existing AGV, not as brand-new venues._"
        )
        lines.append("")
        for r in report["renames"]:
            lines.append(
                f"- Candidate `{r.get('candidate_agv_id', '?')}` "
                f"(**{r.get('candidate_name', '?')}**) matches the former name "
                f"of `{r.get('matched_agv_id', '?')}` "
                f"(renamed on or before {r.get('name_history_valid_to') or '?'})."
            )
        lines.append("")

    if not any([n_new, n_upd, n_conf, n_stale, n_ren]):
        lines.append("_No changes proposed in this run._")
        lines.append("")

    return "\n".join(lines)


# ---- CLI ----

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.candidates_to_pr",
        description="Render a DiffReport JSON file as a Markdown PR body.",
    )
    ap.add_argument("--report", type=Path, required=True,
                    help="JSON DiffReport produced by pipelines.diff")
    ap.add_argument("--output", type=Path,
                    help="Markdown output path (default: stdout)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    body = render_pr_body(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
