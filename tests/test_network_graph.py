"""Network graph tests (CLAUDE.md §9 Task 10).

Drag / zoom / hover behaviour can only be verified in a browser; these
tests enforce structural contracts that Observable Framework's build
validates end-to-end. Complements the browser-level verification
tracked in CHANGELOG.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOADER = REPO_ROOT / "src" / "data" / "network.json.py"
COMPONENT = REPO_ROOT / "src" / "components" / "networkGraph.js"
DASHBOARD = REPO_ROOT / "src" / "dashboard.md"
AGV_CSV = REPO_ROOT / "data" / "agv.csv"
RELATION_CSV = REPO_ROOT / "data" / "agv_relation.csv"


# ---- loader ----

def _run_loader() -> dict:
    result = subprocess.run(
        [sys.executable, str(LOADER)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_loader_emits_nodes_and_links():
    data = _run_loader()
    assert set(data.keys()) >= {"nodes", "links"}
    assert isinstance(data["nodes"], list)
    assert isinstance(data["links"], list)


def test_nodes_count_matches_agv_csv():
    import csv
    with AGV_CSV.open(newline="") as f:
        agv_count = sum(1 for _ in csv.DictReader(f))
    data = _run_loader()
    assert len(data["nodes"]) == agv_count


def test_links_count_matches_relation_csv():
    import csv
    with RELATION_CSV.open(newline="") as f:
        rel_count = sum(1 for _ in csv.DictReader(f))
    data = _run_loader()
    assert len(data["links"]) == rel_count


def test_every_link_endpoint_resolves_to_a_node():
    data = _run_loader()
    node_ids = {n["id"] for n in data["nodes"]}
    for link in data["links"]:
        assert link["source"] in node_ids, link
        assert link["target"] in node_ids, link


def test_node_shape_has_expected_fields():
    data = _run_loader()
    required = {"id", "name", "entity_type", "current_state", "convening_frequency"}
    for node in data["nodes"]:
        assert required.issubset(node.keys()), node


def test_link_shape_has_expected_fields():
    data = _run_loader()
    for link in data["links"]:
        for f in ("source", "target", "relation_type"):
            assert f in link, link


def test_loader_output_is_deterministic():
    first = _run_loader()
    second = _run_loader()
    assert first == second


def test_nodes_sorted_by_id():
    data = _run_loader()
    ids = [n["id"] for n in data["nodes"]]
    assert ids == sorted(ids)


# ---- component: structural / interaction wiring ----

def test_component_file_present():
    assert COMPONENT.exists()


def test_component_exports_networkGraph():
    body = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"export\s+function\s+networkGraph\s*\(", body)


def test_component_imports_d3():
    body = COMPONENT.read_text(encoding="utf-8")
    assert 'from "npm:d3"' in body


def _d3_call_pattern(method: str) -> re.Pattern:
    # Matches d3.method( or d3\n  .method( (D3's chained style)
    return re.compile(rf"d3\s*\.\s*{re.escape(method)}\s*\(", re.DOTALL)


def test_component_uses_force_simulation():
    body = COMPONENT.read_text(encoding="utf-8")
    for method in (
        "forceSimulation", "forceLink", "forceManyBody",
        "forceCenter", "forceCollide",
    ):
        assert _d3_call_pattern(method).search(body), method


def test_component_wires_drag_interaction():
    body = COMPONENT.read_text(encoding="utf-8")
    assert _d3_call_pattern("drag").search(body)
    # Standard D3 drag handler pattern
    for handler in ("dragstarted", "dragged", "dragended"):
        assert handler in body, handler
    assert "alphaTarget" in body, "simulation must be re-warmed on drag start"


def test_component_wires_zoom_interaction():
    body = COMPONENT.read_text(encoding="utf-8")
    assert _d3_call_pattern("zoom").search(body)
    assert "scaleExtent" in body
    assert 'on("zoom"' in body
    # Zoom target is the container group, not the whole svg
    assert 'container.attr("transform"' in body


def test_component_has_hover_title_tooltips():
    body = COMPONENT.read_text(encoding="utf-8")
    # <title> is the native SVG hover tooltip mechanism
    assert 'append("title")' in body
    # Both nodes and links get a title
    title_count = len(re.findall(r'append\("title"\)', body))
    assert title_count >= 2, title_count


def test_component_covers_all_thirteen_entity_types():
    body = COMPONENT.read_text(encoding="utf-8")
    entity_types = [
        "igo_initiative", "intergov_forum", "treaty_body",
        "multistakeholder_coalition", "industry_consortium",
        "intl_ngo_thinktank", "academic_consortium", "standards_body_wg",
        "national_regulator_intl", "conference_policy_track",
        "standalone_governance_conference", "industry_conference",
        "one_off_summit",
    ]
    for et in entity_types:
        assert f'"{et}"' in body, et


def test_component_handles_all_relation_types():
    body = COMPONENT.read_text(encoding="utf-8")
    relation_types = [
        "parent_of", "succeeds", "absorbed_into",
        "coordinates_with", "convenes_within", "member_of",
        "references_principles_of",
    ]
    for rt in relation_types:
        assert rt in body, rt


def test_component_stops_simulation_on_invalidation():
    body = COMPONENT.read_text(encoding="utf-8")
    assert "invalidation" in body
    assert "simulation.stop()" in body


def test_component_handles_empty_nodes_gracefully():
    body = COMPONENT.read_text(encoding="utf-8")
    # Either an early return, a helpful placeholder, or a guarded tick
    assert "No venues" in body or "rawNodes.length" in body


# ---- dashboard integration ----

def test_dashboard_imports_networkGraph():
    body = DASHBOARD.read_text(encoding="utf-8")
    assert 'from "./components/networkGraph.js"' in body


def test_dashboard_has_section_7():
    body = DASHBOARD.read_text(encoding="utf-8")
    assert "## 7. Relations network" in body


def test_dashboard_passes_invalidation_to_component():
    body = DASHBOARD.read_text(encoding="utf-8")
    # §7 component call must thread invalidation through so the simulation
    # is torn down on cell re-eval.
    section = body.split("## 7. Relations network", 1)[1]
    assert "invalidation" in section


def test_dashboard_filters_network_by_view():
    body = DASHBOARD.read_text(encoding="utf-8")
    section = body.split("## 7. Relations network", 1)[1]
    # filteredNetwork.nodes derived from agvFiltered
    assert "filteredNetwork" in section
    assert "agvFiltered" in section
    # Edge filter keeps only edges whose both endpoints are visible
    assert "filteredNodeIds.has(s)" in section
    assert "filteredNodeIds.has(t)" in section


def test_dashboard_mentions_drag_zoom_hover_controls():
    body = DASHBOARD.read_text(encoding="utf-8")
    section = body.split("## 7. Relations network", 1)[1].lower()
    assert "drag" in section
    assert "zoom" in section
    assert "hover" in section
