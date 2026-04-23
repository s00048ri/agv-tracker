"""Evidence-layer invariants per CLAUDE.md §4.4, §4.8, §8.6."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"

CONFIDENCE_FIELDS = ("entity_type", "founded_date", "current_state", "legal_character")

SOURCE_TYPES = {
    "official_site", "founding_document", "press_release",
    "oecd_navigator", "iapp_tracker", "unesco_gaigo",
    "news", "academic_paper",
    "human_verification", "llm_classification", "other",
}
CONFIDENCE_VALUES = {"high", "medium", "low"}

URL_RE = re.compile(r"^(https?|internal)://")
INTERNAL_CLASSIFIER_RE = re.compile(r"^internal://classifier-run/")


def _load(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def agvs() -> list[dict]:
    return _load("agv.csv")


@pytest.fixture(scope="module")
def evidence() -> list[dict]:
    return _load("agv_evidence.csv")


def test_evidence_required_fields(evidence):
    for r in evidence:
        for f in ("agv_id", "field_name", "source_url",
                  "source_type", "accessed_at", "confidence"):
            assert (r.get(f) or "").strip(), (
                f"evidence row missing '{f}': {r}"
            )


def test_evidence_source_type_enum(evidence):
    for r in evidence:
        assert r["source_type"] in SOURCE_TYPES, (
            f"bad source_type '{r['source_type']}'"
        )


def test_evidence_confidence_enum(evidence):
    for r in evidence:
        assert r["confidence"] in CONFIDENCE_VALUES


def test_evidence_agv_ids_resolve(evidence, agvs):
    ids = {r["agv_id"] for r in agvs}
    for r in evidence:
        assert r["agv_id"] in ids, (
            f"evidence row references unknown agv_id '{r['agv_id']}'"
        )


def test_evidence_source_url_wellformed(evidence):
    for r in evidence:
        assert URL_RE.match(r["source_url"]), (
            f"evidence source_url '{r['source_url']}' not well-formed"
        )


def test_every_confidence_field_has_evidence_row(agvs, evidence):
    """§4.8: every field in agv.csv with a confidence_* column has ≥1 evidence row."""
    by_key = defaultdict(list)
    for r in evidence:
        by_key[(r["agv_id"], r["field_name"])].append(r)
    for a in agvs:
        for f in CONFIDENCE_FIELDS:
            rows = by_key.get((a["agv_id"], f))
            assert rows, (
                f"{a['agv_id']}: no agv_evidence row for field '{f}' "
                "(required because confidence_" + f + " is set)"
            )


def test_human_verified_field_has_human_evidence(agvs, evidence):
    """§4.8: each field in human_verified_fields must have ≥1 evidence row with
    source_type='human_verification' for that (agv_id, field_name)."""
    by_key = defaultdict(list)
    for r in evidence:
        by_key[(r["agv_id"], r["field_name"], r["source_type"])].append(r)
    for a in agvs:
        hvf = (a.get("human_verified_fields") or "").strip()
        if not hvf:
            continue
        for f in [x.strip() for x in hvf.split(",") if x.strip()]:
            rows = by_key.get((a["agv_id"], f, "human_verification"))
            assert rows, (
                f"{a['agv_id']}: human_verified_fields lists '{f}' "
                "but no human_verification evidence row exists"
            )


def test_human_verification_rows_have_reviewer(evidence):
    for r in evidence:
        if r["source_type"] == "human_verification":
            assert (r.get("reviewer") or "").strip(), (
                f"{r['agv_id']}/{r['field_name']}: "
                "human_verification row missing 'reviewer' (GitHub handle)"
            )


def test_llm_classification_rows_use_internal_url(evidence):
    """§4.4: LLM-classified rows must use source_url='internal://classifier-run/...'."""
    for r in evidence:
        if r["source_type"] == "llm_classification":
            assert INTERNAL_CLASSIFIER_RE.match(r["source_url"]), (
                f"{r['agv_id']}/{r['field_name']}: llm_classification row "
                f"must use internal://classifier-run/... URL, got '{r['source_url']}'"
            )
            assert (r.get("reviewer") or "").strip(), (
                f"{r['agv_id']}/{r['field_name']}: "
                "llm_classification row missing 'reviewer' (model version)"
            )


def test_agv_field_confidence_matches_highest_evidence_row(agvs, evidence):
    """§4.4: field-level confidence in agv.csv reflects the highest-confidence
    evidence row for that field."""
    order = {"low": 0, "medium": 1, "high": 2}
    best: dict[tuple[str, str], str] = {}
    for r in evidence:
        key = (r["agv_id"], r["field_name"])
        cur = best.get(key)
        if cur is None or order[r["confidence"]] > order[cur]:
            best[key] = r["confidence"]
    for a in agvs:
        for f in CONFIDENCE_FIELDS:
            declared = a[f"confidence_{f}"]
            observed = best.get((a["agv_id"], f))
            assert observed is not None, (
                f"{a['agv_id']}: confidence_{f}={declared} "
                "but no evidence rows"
            )
            assert declared == observed, (
                f"{a['agv_id']}: confidence_{f}={declared} "
                f"does not match highest evidence confidence '{observed}'"
            )
