"""Zenodo / citation plumbing tests (CLAUDE.md §9 Task 12).

First-release DOI minting and the Zenodo side of the integration can
only be verified after a real tagged release lands on Zenodo; these
tests lock down the offline artefacts and the update-script contract
so the first release works predictably.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ZENODO_JSON = REPO_ROOT / ".zenodo.json"
CITATION_CFF = REPO_ROOT / "CITATION.cff"
CITATION_JSON = REPO_ROOT / "data" / "citation.json"
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "update_citation.sh"
METHODOLOGY = REPO_ROOT / "src" / "methodology.md"
DATA_DOWNLOAD = REPO_ROOT / "src" / "data-download.md"
CI_SETUP = REPO_ROOT / ".github" / "CI_SETUP.md"
README = REPO_ROOT / "README.md"

DOI_RE = re.compile(r"^10\.\d+/[A-Za-z0-9._/\-]+$")


# ---- .zenodo.json ----

def test_zenodo_json_parses():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    assert isinstance(d, dict)


def test_zenodo_json_has_required_fields():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    for key in ("title", "description", "creators",
                "upload_type", "access_right", "license", "keywords"):
        assert key in d, key


def test_zenodo_json_upload_type_is_dataset():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    assert d["upload_type"] == "dataset"


def test_zenodo_json_license_is_cc_by_40():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    # Zenodo schema uses the lowercased ID form.
    assert d["license"].lower().replace(" ", "-") == "cc-by-4.0"


def test_zenodo_json_access_right_is_open():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    assert d["access_right"] == "open"


def test_zenodo_json_has_creator_with_name():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    assert isinstance(d["creators"], list) and d["creators"]
    for c in d["creators"]:
        assert "name" in c and c["name"].strip()


def test_zenodo_json_related_identifiers_point_at_repo_and_site():
    d = json.loads(ZENODO_JSON.read_text(encoding="utf-8"))
    rels = d.get("related_identifiers", [])
    joined = " ".join(str(r) for r in rels)
    assert "github.com" in joined
    assert "pages.dev" in joined or "agv-tracker.org" in joined


# ---- CITATION.cff ----

def test_citation_cff_parses_as_yaml():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    assert isinstance(d, dict)


def test_citation_cff_version_is_1_2_0():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    assert d["cff-version"] == "1.2.0"


def test_citation_cff_type_is_dataset():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    assert d["type"] == "dataset"


def test_citation_cff_has_authors_with_names():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    assert d.get("authors")
    for a in d["authors"]:
        assert "family-names" in a and "given-names" in a


def test_citation_cff_has_two_doi_identifiers():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    ids = d.get("identifiers", [])
    dois = [i for i in ids if i.get("type") == "doi"]
    assert len(dois) >= 2, "expected both version and concept DOI identifiers"
    for i in dois:
        val = i.get("value", "")
        assert DOI_RE.match(val) or "PLACEHOLDER" in val


def test_citation_cff_license_is_cc_by_40():
    d = yaml.safe_load(CITATION_CFF.read_text(encoding="utf-8"))
    assert d["license"].replace(" ", "").replace("-", "").lower() == "ccby4.0"


# ---- data/citation.json ----

def test_citation_json_parses():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    assert isinstance(d, dict)


def test_citation_json_has_required_fields():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    for key in ("version", "released_at", "doi", "doi_url",
                "concept_doi", "concept_doi_url",
                "citation_text", "bibtex"):
        assert key in d, key


def test_citation_json_doi_url_matches_doi():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    assert d["doi_url"].endswith(d["doi"])
    assert d["concept_doi_url"].endswith(d["concept_doi"])


def test_citation_json_doi_format_or_placeholder():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    for key in ("doi", "concept_doi"):
        v = d[key]
        assert DOI_RE.match(v) or "PLACEHOLDER" in v, f"{key}={v!r}"


def test_citation_json_bibtex_references_doi():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    assert d["doi"] in d["bibtex"]


def test_citation_json_citation_text_references_doi_url():
    d = json.loads(CITATION_JSON.read_text(encoding="utf-8"))
    assert d["doi_url"] in d["citation_text"]


# ---- update_citation.sh ----

def test_update_script_exists_and_executable():
    import stat
    assert UPDATE_SCRIPT.exists()
    assert UPDATE_SCRIPT.stat().st_mode & stat.S_IXUSR


def test_update_script_uses_strict_mode():
    body = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in body


def test_update_script_passes_bash_syntax():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")
    result = subprocess.run(
        [bash, "-n", str(UPDATE_SCRIPT)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_update_script_requires_three_positional_args():
    body = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert "VERSION" in body
    assert "VERSION_DOI" in body
    assert "CONCEPT_DOI" in body
    # Require at least 3 positional arguments.
    assert re.search(r"\$#\s*-lt\s*3", body)


def test_update_script_validates_doi_format():
    body = UPDATE_SCRIPT.read_text(encoding="utf-8")
    # Some form of a regex gate on DOI arguments.
    assert re.search(r"10\\\.\[0-9\]\+", body)


def test_update_script_touches_all_three_artifacts():
    body = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert "data/citation.json" in body
    assert "CITATION.cff" in body
    # .zenodo.json is version-stable in v0.3 but the script comments on it,
    # so an explicit mention is required to avoid accidental drift.
    assert ".zenodo.json" in body


# ---- site content ----

def test_methodology_has_cite_this_release_section():
    body = METHODOLOGY.read_text(encoding="utf-8")
    assert "## Cite this release" in body
    assert 'FileAttachment("./data/citation.json")' in body
    assert "citation.doi_url" in body
    assert "citation.bibtex" in body


def test_data_download_has_cite_this_release_section():
    body = DATA_DOWNLOAD.read_text(encoding="utf-8")
    assert "## Cite this release" in body
    assert 'FileAttachment("./data/citation.json")' in body
    assert "citation.citation_text" in body


# ---- docs ----

def test_ci_setup_has_zenodo_section():
    body = CI_SETUP.read_text(encoding="utf-8")
    assert "Zenodo" in body
    assert ".zenodo.json" in body
    assert "CITATION.cff" in body
    assert "update_citation.sh" in body


def test_readme_or_ci_setup_documents_first_release_flow():
    # Either README or CI_SETUP must explain how to mint the first DOI.
    bodies = " ".join(p.read_text(encoding="utf-8")
                      for p in (README, CI_SETUP))
    # Acceptable evidence: the tag command + update_citation.sh + DOI.
    assert re.search(r"git\s+tag[^\n]*v\d+\.\d+\.\d+", bodies)
    assert "update_citation.sh" in bodies
    assert "DOI" in bodies
