"""Classifier unit tests (CLAUDE.md §9 Task 5).

No live network: the tests exercise the mock backend, fixture I/O, cache and
budget machinery, and the CLI in --mock mode. Real-API accuracy is verified
out of band via ``python -m pipelines.classify --eval … --live``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipelines.classify import (
    DEFAULT_MODEL,
    DIMENSIONS,
    ENTITY_TYPES,
    GEO_SCOPES,
    GOVERNANCE_MODALITIES,
    LEAD_ACTORS,
    LEGAL_CHARACTERS,
    PRICING,
    PROMPTS_DIR,
    TOPIC_FOCI,
    BudgetExceededError,
    BudgetGuard,
    ClassificationResult,
    Classifier,
    anthropic_llm_call,
    compute_cost,
    extract_json,
    load_records,
    main as classify_main,
    mock_llm_call,
    record_id_and_text,
    results_to_evidence_rows,
    write_evidence_csv,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD = REPO_ROOT / "tests" / "fixtures" / "classify" / "gold_examples.jsonl"
SAMPLE_INPUT = REPO_ROOT / "tests" / "fixtures" / "classify" / "sample_input.json"


# ---- prompts ----

def test_all_six_prompt_files_present():
    for _fn, filename, _vals in DIMENSIONS:
        p = PROMPTS_DIR / filename
        assert p.exists(), f"missing prompt: {p}"
        assert "{text}" in p.read_text(encoding="utf-8"), (
            f"prompt {filename} is missing the {{text}} placeholder"
        )


def test_every_enum_value_appears_in_its_prompt():
    for _field_name, filename, values in DIMENSIONS:
        body = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        for v in values:
            assert v in body, (
                f"prompt {filename}: enum value {v!r} missing"
            )


# ---- helpers ----

def test_extract_json_handles_plain_and_fenced():
    plain = '{"value": "igo_initiative", "confidence": "high", "rationale": "x"}'
    assert extract_json(plain)["value"] == "igo_initiative"
    fenced = "```json\n" + plain + "\n```"
    assert extract_json(fenced)["confidence"] == "high"
    with_prefix = (
        "Here is my classification:\n\n"
        + plain
        + "\n\nThat's my answer."
    )
    assert extract_json(with_prefix)["value"] == "igo_initiative"


def test_extract_json_raises_on_garbage():
    with pytest.raises(ValueError):
        extract_json("no json here at all — just prose")


def test_compute_cost_sonnet():
    # 1000 in @ $2 + 500 out @ $10 per MTok = 0.002 + 0.005 = 0.007
    assert compute_cost("claude-sonnet-5", 1000, 500) == pytest.approx(0.007)


def test_compute_cost_falls_back_to_the_default_models_rate():
    """An unknown id must not silently disable the budget guard.

    A typo in `--model` would otherwise price every call at zero and let
    a run spend past the monthly cap unchallenged.
    """
    assert compute_cost("claude-typo-9", 1000, 500) == compute_cost(
        DEFAULT_MODEL, 1000, 500,
    )
    assert compute_cost("claude-typo-9", 1000, 500) > 0


def test_priced_models_include_the_default():
    """The fallback dereferences PRICING[DEFAULT_MODEL] — it must exist."""
    assert DEFAULT_MODEL in PRICING


def test_record_id_and_text_variants():
    rid, text = record_id_and_text({"agv_id": "x", "text": "hello"})
    assert (rid, text) == ("x", "hello")
    rid, text = record_id_and_text(
        {"source_id": "oecd.ai:1", "name": "Foo", "description": "Bar"}
    )
    assert rid == "oecd.ai:1" and "Foo" in text and "Bar" in text


# ---- mock backend ----

@pytest.mark.parametrize("field_name,filename,values", DIMENSIONS)
def test_mock_returns_valid_enum_for_each_dimension(field_name, filename, values):
    prompt = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    prompt = prompt.replace("{text}", "A generic AI governance body with global reach.")
    resp = mock_llm_call("claude-sonnet-5", prompt)
    assert resp["value"] in values


# ---- Classifier ----

def test_classifier_happy_path_mock():
    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=mock_llm_call)
    text = (
        "OECD AI Principles — non-binding principles adopted by the "
        "OECD secretariat; global scope."
    )
    results = c.classify_all("oecd_ai_principles", text)
    assert len(results) == 6
    field_names = [r.field_name for r in results]
    assert field_names == [d[0] for d in DIMENSIONS]
    for r in results:
        assert isinstance(r, ClassificationResult)
        assert r.value  # non-empty
        assert r.confidence in {"high", "medium", "low"}


def test_invalid_enum_downgrades_confidence(tmp_path: Path):
    def bad_call(_model, _prompt, _max_tokens=600):
        return {
            "value": "not_a_real_enum",
            "confidence": "high",
            "rationale": "this is nonsense",
            "_tokens_in": 100,
            "_tokens_out": 50,
        }

    c = Classifier(model="claude-sonnet-5", cache_dir=tmp_path, llm_call=bad_call,
                   budget_guard=None)
    results = c.classify_all("x", "some text")
    assert all(r.confidence == "low" for r in results)
    assert all("invalid-enum fallback" in r.rationale for r in results)


def test_cache_hit_skips_llm_call(tmp_path: Path):
    calls = {"n": 0}

    def counting(_model, _prompt, _max_tokens=600):
        calls["n"] += 1
        return {
            "value": "igo_initiative", "confidence": "high", "rationale": "r",
            "_tokens_in": 50, "_tokens_out": 20,
        }

    c = Classifier(model="claude-sonnet-5", cache_dir=tmp_path, llm_call=counting)
    c._classify_one("x", "entity_type", "text", ENTITY_TYPES)
    first = calls["n"]
    c._classify_one("x", "entity_type", "text", ENTITY_TYPES)
    assert calls["n"] == first, "second call with same text should be served from cache"

    fresh = Classifier(model="claude-sonnet-5", cache_dir=tmp_path, llm_call=counting)
    r = fresh._classify_one("x", "entity_type", "text", ENTITY_TYPES)
    assert r.cached is True


# ---- Budget ----

def test_budget_under_limit_allows(tmp_path: Path):
    bg = BudgetGuard(tmp_path / "b.json", monthly_budget_usd=10.0)
    bg.check(0.01)  # no exception
    bg.record(0.01, "run-test")
    assert bg.current_spend() == pytest.approx(0.01)


def test_budget_over_limit_raises(tmp_path: Path):
    bg = BudgetGuard(tmp_path / "b.json", monthly_budget_usd=0.001)
    bg.record(0.002, "run-preexisting")
    with pytest.raises(BudgetExceededError):
        bg.check(0.01)


def test_classifier_respects_budget_guard(tmp_path: Path):
    budget_file = tmp_path / "b.json"
    bg = BudgetGuard(budget_file, monthly_budget_usd=0.0001)
    bg.record(0.0002, "preexisting")

    def costly(_model, _prompt, _max_tokens=600):
        return {"value": "igo_initiative", "confidence": "high", "rationale": "r",
                "_tokens_in": 1000, "_tokens_out": 500}

    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=costly,
                   budget_guard=bg)
    with pytest.raises(BudgetExceededError):
        c.classify_all("x", "some text")


# ---- Evidence rows ----

def test_evidence_row_shape_matches_agvschema(tmp_path: Path):
    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=mock_llm_call)
    results = c.classify_all("sample", "OECD AI Principles: non-binding principles; global.")
    rows = results_to_evidence_rows(results)
    assert len(rows) == 6
    for row in rows:
        assert row["source_type"] == "llm_classification"
        assert re.match(r"^internal://classifier-run/run-\d{8}T", row["source_url"])
        # The mock backend must not sign its work with the model's name.
        assert row["reviewer"] == "mock (no claude-sonnet-5 call)"
        assert row["confidence"] in {"high", "medium", "low"}
        assert row["evidence_note"]
        assert row["accessed_at"]

    out = tmp_path / "evidence.csv"
    write_evidence_csv(out, rows)
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith(
        "agv_id,field_name,source_url,source_type,accessed_at,"
        "evidence_note,reviewer,confidence\n"
    )
    assert body.count("\n") == 7  # header + 6 rows


def test_evidence_csv_append_does_not_duplicate_header(tmp_path: Path):
    out = tmp_path / "evidence.csv"
    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=mock_llm_call)
    rows1 = results_to_evidence_rows(
        c.classify_all("a", "Foo research institute, research-only, global.")
    )
    rows2 = results_to_evidence_rows(
        c.classify_all("b", "Bar standards organization, ISO secretariat, global.")
    )
    write_evidence_csv(out, rows1)
    write_evidence_csv(out, rows2)
    body = out.read_text(encoding="utf-8")
    assert body.count("agv_id,field_name,source_url") == 1
    assert body.count("\n") == 1 + 12  # header + 2 × 6


# ---- CLI ----

def test_cli_mock_end_to_end(tmp_path: Path):
    output = tmp_path / "classified.json"
    evidence = tmp_path / "evidence.csv"
    rc = classify_main([
        "--mock", "--quiet",
        "--input", str(SAMPLE_INPUT),
        "--output", str(output),
        "--evidence-out", str(evidence),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 2
    for entry in data:
        assert len(entry["classifications"]) == 6
        for c in entry["classifications"]:
            assert c["field_name"] in {d[0] for d in DIMENSIONS}
    # Evidence file header + 2 records × 6 dimensions
    assert evidence.read_text(encoding="utf-8").count("\n") == 1 + 12


def test_cli_eval_reports_gold_accuracy(tmp_path: Path, capsys):
    report_out = tmp_path / "eval.json"
    rc = classify_main([
        "--mock", "--quiet",
        "--eval", str(GOLD),
        "--output", str(report_out),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0, capsys.readouterr().err
    report = json.loads(report_out.read_text(encoding="utf-8"))
    # With carefully-crafted gold texts and the deterministic mock, accuracy
    # should be 100% on all six dimensions — this also validates that the
    # evaluation plumbing computes per-dimension scores correctly.
    for dim in report["per_dimension"]:
        assert dim["pass"] is True, dim
        assert dim["accuracy"] >= dim["threshold"]
        assert dim["hits"] == dim["total"] == 10


def test_gold_file_shape():
    records = load_records(GOLD)
    assert len(records) == 10
    for rec in records:
        assert rec["id"]
        assert rec["text"]
        exp = rec["expected"]
        assert exp["entity_type"] in ENTITY_TYPES
        assert exp["governance_modality_primary"] in GOVERNANCE_MODALITIES
        assert exp["topic_focus_primary"] in TOPIC_FOCI
        assert exp["geographic_scope"] in GEO_SCOPES
        assert exp["lead_actor_primary"] in LEAD_ACTORS
        assert exp["legal_character"] in LEGAL_CHARACTERS


def test_anthropic_llm_call_raises_clear_error_without_sdk(monkeypatch):
    """If the anthropic SDK is missing, the call should raise an ImportError
    with actionable guidance — tested by pretending the import fails."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "anthropic":
            raise ImportError("mocked missing SDK")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError) as ei:
        anthropic_llm_call("claude-sonnet-5", "irrelevant prompt")
    assert "uv sync --extra classifier" in str(ei.value)


# ---- Backend attribution ----

def test_mock_results_do_not_claim_a_model_call():
    """`agv_evidence.reviewer` is provenance, and provenance must be true.

    Recording "claude-sonnet-5" for a classification the mock produced
    puts a false attribution into the dataset's own audit trail
    (CLAUDE.md §4.4) and makes a plumbing run indistinguishable from a
    real one — which is exactly what happened to the 2026-09-07 monthly
    run before this was fixed.
    """
    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=mock_llm_call)
    for r in c.classify_all("sample", "OECD AI Principles: non-binding; global."):
        assert r.backend == "mock"
        assert "claude-sonnet-5" not in r.reviewer.split("(")[0]
        assert r.reviewer.startswith("mock")


def test_a_live_backend_signs_with_the_model_name():
    def fake_live(model, prompt, max_tokens=600):
        out = mock_llm_call(model, prompt, max_tokens)
        out["_backend"] = "anthropic"
        return out

    c = Classifier(model="claude-sonnet-5", cache_dir=None, llm_call=fake_live)
    for r in c.classify_all("sample", "OECD AI Principles: non-binding; global."):
        assert r.backend == "anthropic"
        assert r.reviewer == "claude-sonnet-5"


def test_cached_mock_answers_stay_labelled_mock(tmp_path: Path):
    """A cache hit must not launder a mock answer into a live one.

    `_cache_write` strips underscore-prefixed keys, so the backend has to
    be persisted deliberately or a replayed answer comes back wearing the
    model's name months later.
    """
    cache = tmp_path / "cache"
    first = Classifier(model="claude-sonnet-5", cache_dir=cache, llm_call=mock_llm_call)
    first.classify_all("sample", "OECD AI Principles: non-binding; global.")

    def explode(model, prompt, max_tokens=600):  # pragma: no cover - must not run
        raise AssertionError("cache miss: the second run should not call a backend")

    second = Classifier(model="claude-sonnet-5", cache_dir=cache, llm_call=explode)
    results = second.classify_all("sample", "OECD AI Principles: non-binding; global.")
    assert results and all(r.cached for r in results)
    for r in results:
        assert r.backend == "mock"
        assert r.reviewer.startswith("mock")

