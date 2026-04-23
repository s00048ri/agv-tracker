"""Analysis notebook tests (CLAUDE.md §9 Task 13).

The heavy test here is an end-to-end execution of
`notebooks/founding_rate_analysis.ipynb` via `nbclient`. It validates
both Done-when items:

  #1  runs end-to-end from CSV    → execute the notebook, expect zero
                                    error outputs;
  #2  contains ≥1 inferential test → assert an LR-test cell is present.

Notebook extras are optional; if the `[notebook]` deps are not
installed locally, the heavy test is `importorskip`-ed and the
remaining structural tests still run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = REPO_ROOT / "notebooks" / "founding_rate_analysis.ipynb"
GENERATOR = REPO_ROOT / "scripts" / "generate_analysis_notebook.py"
NOTEBOOKS_README = REPO_ROOT / "notebooks" / "README.md"


# ---- structural (no [notebook] extras required) ----

def test_notebook_file_exists():
    assert NOTEBOOK.exists(), f"missing {NOTEBOOK}"


def test_notebook_parses_as_valid_json():
    data = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert data["nbformat"] == 4
    assert "cells" in data


def test_notebook_has_code_and_markdown_cells():
    data = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    kinds = {c["cell_type"] for c in data["cells"]}
    assert {"code", "markdown"}.issubset(kinds)


def test_notebook_mentions_csv_data_loading():
    body = NOTEBOOK.read_text(encoding="utf-8")
    assert "data/agv.csv" in body or "'agv.csv'" in body
    assert "read_csv" in body


def test_notebook_contains_density_dependent_model():
    body = NOTEBOOK.read_text(encoding="utf-8")
    # Poisson GLM on density_prev + density_prev_sq is the core fit.
    assert "density_prev_sq" in body
    assert "Poisson()" in body
    assert "smf.glm" in body or "statsmodels.formula" in body


def test_notebook_contains_inferential_test():
    """CLAUDE.md §9 Task 13 Done-when #2: ≥1 inferential test."""
    body = NOTEBOOK.read_text(encoding="utf-8")
    # Either the LR test explicitly or compare_lr_test; the generator
    # uses scipy.stats.chi2.sf of 2·Δℓ against df.
    assert "Likelihood-ratio" in body or "compare_lr_test" in body
    assert "chi2" in body or "LR" in body


def test_notebook_covers_all_three_views():
    body = NOTEBOOK.read_text(encoding="utf-8")
    for v in ("continuous", "recurring", "one_off_included"):
        assert v in body, v


def test_notebook_produces_figures():
    body = NOTEBOOK.read_text(encoding="utf-8")
    assert ".pdf" in body
    assert "plt.savefig" in body
    assert "FIGURES" in body or "figures" in body


def test_generator_check_passes_on_committed_tree():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"generator --check failed:\n{result.stderr}"
    )


def test_generator_is_deterministic():
    before = NOTEBOOK.read_bytes()
    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    after = NOTEBOOK.read_bytes()
    assert before == after


def test_notebooks_readme_exists():
    assert NOTEBOOKS_README.exists()
    body = NOTEBOOKS_README.read_text(encoding="utf-8")
    for phrase in (
        "founding_rate_analysis.ipynb",
        "uv sync --extra notebook",
        "generate_analysis_notebook.py",
        "CSV",
    ):
        assert phrase in body, phrase


# ---- end-to-end execution (requires [notebook] extras) ----

def test_notebook_executes_end_to_end(tmp_path):
    """The Done-when #1 contract: notebook runs end-to-end from CSV."""
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("pandas")
    pytest.importorskip("statsmodels")
    pytest.importorskip("scipy")

    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = nbclient.NotebookClient(
        nb,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(REPO_ROOT / "notebooks")}},
    )
    client.execute()

    # No cell produced an error output.
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.outputs:
            assert output.output_type != "error", (
                f"cell produced error:\n"
                f"  source head: {cell.source.splitlines()[0] if cell.source else ''!r}\n"
                f"  ename: {output.get('ename')}\n"
                f"  evalue: {output.get('evalue')}"
            )


def test_notebook_execution_fits_the_poisson_model(tmp_path):
    """Confirm the fit cell emits a meaningful GLM summary on execution."""
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("pandas")
    pytest.importorskip("statsmodels")
    pytest.importorskip("scipy")

    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = nbclient.NotebookClient(
        nb,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(REPO_ROOT / "notebooks")}},
    )
    client.execute()

    # Find the Poisson fit output — must mention the `Link Function: Log`
    # header that statsmodels prints for GLM(Poisson).
    found_poisson = False
    found_lr_test = False
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.outputs:
            text = output.get("text", "") if output.output_type == "stream" else ""
            data = output.get("data", {}) if output.output_type in {"execute_result", "display_data"} else {}
            text += str(data.get("text/plain", ""))
            if "Poisson" in text and "Link Function" in text:
                found_poisson = True
            if "Likelihood-ratio" in text and "p-value" in text:
                found_lr_test = True
    assert found_poisson, "expected a GLM(Poisson) summary output in the notebook"
    assert found_lr_test, "expected an explicit LR-test output in the notebook"
