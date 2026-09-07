"""End-to-end smoke test (CLAUDE.md §9 Task 6 Done-when #1).

Drives the full Task 4 → 5 → 6 chain against shipped fixtures:
    fetcher fixture → Normalizer → Differ → render_pr_body.

No network, no API, no classifier budget calls; everything runs against
the deterministic mock backend.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pipelines.candidates_to_pr import render_pr_body
from pipelines.classify import Classifier, mock_llm_call
from pipelines.diff import Differ
from pipelines.fetchers.oecd_ai import DEFAULT_FIXTURE_DIR, OECDFetcher
from pipelines.normalize import Normalizer

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "data" / "agv.csv"
NAME_HISTORY = REPO_ROOT / "data" / "agv_name_history.csv"
REGISTRY = REPO_ROOT / "sources" / "registry.yml"


def test_fetcher_to_pr_body_end_to_end():
    # 1. Fetch from shipped OECD.AI fixture
    fetcher = OECDFetcher(fixture_dir=DEFAULT_FIXTURE_DIR)
    raw_venues = fetcher.fetch()
    # 10, from the three organisation pages shipped as captures. The old
    # `>= 50` came from a hand-written fixture with 60 invented cards on a
    # URL that returns 404; the number to assert here is "the pipeline
    # carries whatever the fetcher found", not a target.
    assert raw_venues

    # 2. Normalize → v0.3 candidates
    classifier = Classifier(cache_dir=None, llm_call=mock_llm_call, budget_guard=None)
    normalizer = Normalizer(registry_path=REGISTRY, classifier=classifier)
    raw_dicts = [v.as_dict() for v in raw_venues]
    candidates = normalizer.normalize(raw_dicts)
    assert candidates, "normalizer produced zero candidates"

    # 3. Diff against canonical with a fixed 'today'
    differ = Differ.from_paths(CANONICAL, NAME_HISTORY, today=date(2026, 4, 23))
    report = differ.diff(candidates)
    assert report.canonical_size >= 100
    assert report.candidate_size == len(candidates)
    # End-to-end run must surface SOMETHING the reviewer should look at.
    assert (
        report.new_venues
        or report.unverified_updates
        or report.conflicts
        or report.renames
    ), "diff produced an entirely empty actionable set"

    # 4. Render PR body
    body = render_pr_body(report.as_dict())
    assert body.startswith("# AGV Tracker — monthly update proposal")
    assert "| Category | Count |" in body
    # At least one actionable section header must appear
    assert any(
        h in body
        for h in (
            "## New venues",
            "## Updates to unverified fields",
            "## ⚠️ Conflicts with human-verified fields",
            "## Rename detections",
        )
    )


def test_pr_body_empty_report_is_well_formed():
    empty_report = {
        "run_id": "diff-test",
        "today": "2026-04-23",
        "canonical_size": 0,
        "candidate_size": 0,
        "new_venues": [],
        "unverified_updates": [],
        "conflicts": [],
        "stale_candidates": [],
        "renames": [],
        "matches_count": 0,
    }
    body = render_pr_body(empty_report)
    assert "No changes proposed" in body


def test_pr_body_renders_conflict_with_three_checkboxes():
    report = {
        "run_id": "diff-x",
        "today": "2026-04-23",
        "canonical_size": 1,
        "candidate_size": 1,
        "new_venues": [],
        "unverified_updates": [],
        "conflicts": [
            {
                "agv_id": "x",
                "name_en": "X",
                "field_name": "entity_type",
                "existing_value": "igo_initiative",
                "proposed_value": "intergov_forum",
                "rationale": "field locked",
                "existing_verified_at": "2026-01-01",
                "override_policy": "lock_verified_only",
                "source_url": "",
            }
        ],
        "stale_candidates": [],
        "renames": [],
        "matches_count": 0,
    }
    body = render_pr_body(report)
    assert "(a) keep human-verified value" in body
    assert "(b) accept LLM proposal and re-verify" in body
    assert "(c) note venue evolution" in body
    assert "⚠️" in body  # warning header


def test_pr_body_warns_when_conflict_ratio_over_5_percent():
    report = {
        "run_id": "diff-x", "today": "2026-04-23",
        "canonical_size": 10, "candidate_size": 10,
        "new_venues": [], "unverified_updates": [],
        "conflicts": [
            {"agv_id": "c1", "name_en": "C1", "field_name": "entity_type",
             "existing_value": "a", "proposed_value": "b",
             "rationale": "r", "existing_verified_at": "", "override_policy": "",
             "source_url": ""}
        ],
        "stale_candidates": [], "renames": [],
        "matches_count": 1,  # ratio 1/(0+1+1) = 50% > 5%
    }
    body = render_pr_body(report)
    assert "exceeds the 5% target" in body


def test_pr_body_cli_writes_markdown_to_file(tmp_path: Path):
    from pipelines.candidates_to_pr import main as pr_main
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "run_id": "diff-y", "today": "2026-04-23",
        "canonical_size": 0, "candidate_size": 0,
        "new_venues": [], "unverified_updates": [],
        "conflicts": [], "stale_candidates": [], "renames": [],
        "matches_count": 0,
    }), encoding="utf-8")
    output = tmp_path / "pr.md"
    rc = pr_main(["--report", str(report_path), "--output", str(output)])
    assert rc == 0
    body = output.read_text(encoding="utf-8")
    assert "monthly update proposal" in body
