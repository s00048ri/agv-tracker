"""Dashboard + view toggle tests (CLAUDE.md §9 Task 9).

Structural validation of the JS component and the Markdown page. We do
not run a JS runtime here; Observable Framework's own `npm run build`
is the integration check. These tests catch drift in the two files that
the Task 9 Done-when depends on.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "src" / "components" / "viewToggle.js"
DASHBOARD = REPO_ROOT / "src" / "dashboard.md"


# ---- viewToggle component ----

def test_component_file_present():
    assert COMPONENT.exists()


def test_component_exports_required_symbols():
    body = COMPONENT.read_text(encoding="utf-8")
    for sym in (
        "CONTINUOUS_ENTITY_TYPES",
        "RECURRING_FREQUENCIES",
        "VIEW_VALUES",
        "VIEW_LABELS",
        "VIEW_DESCRIPTIONS",
        "filterByView",
        "renderInlineMarkdown",
    ):
        assert re.search(rf"export\s+(?:const|function)\s+{sym}\b", body), sym


def test_render_inline_markdown_escapes_before_substituting():
    """The renderer sets innerHTML, so escaping has to come first."""
    body = COMPONENT.read_text(encoding="utf-8")
    fn = body[body.index("export function renderInlineMarkdown") :]
    fn = fn[: fn.index("\n}\n")]
    escape_at = fn.index("&amp;")
    strong_at = fn.index("<strong>")
    assert escape_at < strong_at, "HTML escaping must precede markup substitution"
    assert "innerHTML" in fn


def test_continuous_entity_types_matches_agvo_62():
    """§6.2 view 1 enumerates the 8 continuous entity_type values."""
    body = COMPONENT.read_text(encoding="utf-8")
    for et in (
        "igo_initiative",
        "treaty_body",
        "multistakeholder_coalition",
        "industry_consortium",
        "intl_ngo_thinktank",
        "academic_consortium",
        "standards_body_wg",
        "national_regulator_intl",
    ):
        assert f'"{et}"' in body, f"{et} missing from CONTINUOUS_ENTITY_TYPES"


def test_recurring_frequencies_matches_agvo_62():
    """§6.2 view 2 specifies annual + biennial."""
    body = COMPONENT.read_text(encoding="utf-8")
    # We look at the RECURRING_FREQUENCIES line specifically to avoid
    # false positives if the words appear in comments elsewhere.
    m = re.search(r"RECURRING_FREQUENCIES\s*=\s*new Set\(\[([^\]]+)\]\)", body)
    assert m, "RECURRING_FREQUENCIES not declared as Set literal"
    listed = m.group(1)
    assert '"annual"' in listed
    assert '"biennial"' in listed


def test_view_values_are_the_three_sec_6_2_views():
    body = COMPONENT.read_text(encoding="utf-8")
    m = re.search(r"VIEW_VALUES\s*=\s*\[([^\]]+)\]", body)
    assert m, "VIEW_VALUES not declared as array"
    listed = m.group(1)
    for v in ("continuous", "recurring", "one_off_included"):
        assert f'"{v}"' in listed, v


def test_view_descriptions_cover_all_three_views():
    body = COMPONENT.read_text(encoding="utf-8")
    # The explanation map must include all three keys
    for v in ("continuous", "recurring", "one_off_included"):
        assert re.search(rf"\b{v}\s*:\s*\(", body) or re.search(
            rf"\b{v}\s*:\s*[\"']", body
        ), f"VIEW_DESCRIPTIONS[{v}] missing"


def test_view_descriptions_mention_analytical_purpose_keywords():
    body = COMPONENT.read_text(encoding="utf-8")
    assert "institution-building" in body.lower()
    assert "recurring-convening" in body.lower()
    # Catalytic / one-off language — §6.2 "one-off included"
    assert "one-off" in body.lower() or "one_off" in body.lower()


def test_filter_by_view_is_pure_function():
    body = COMPONENT.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+function\s+filterByView\s*\(([^)]*)\)\s*{([\s\S]*?)^}",
        body,
        re.MULTILINE,
    )
    assert m, "filterByView not found with expected signature"
    params = m.group(1)
    assert "agvs" in params and "view" in params
    fn_body = m.group(2)
    # All three view branches must be handled
    assert "continuous" in fn_body
    assert "recurring" in fn_body
    # Default branch returns the full list (one_off_included)
    assert "return agvs" in fn_body


# ---- dashboard.md ----

def test_dashboard_imports_viewToggle():
    body = DASHBOARD.read_text(encoding="utf-8")
    assert 'from "./components/viewToggle.js"' in body
    for sym in ("filterByView", "VIEW_VALUES", "VIEW_LABELS", "VIEW_DESCRIPTIONS"):
        assert sym in body, sym


def test_dashboard_has_radio_toggle():
    body = DASHBOARD.read_text(encoding="utf-8")
    # view(Inputs.radio(...)) pattern must be present so Observable Framework
    # wires it as a reactive value.
    assert "Inputs.radio(VIEW_VALUES" in body
    assert "view(Inputs.radio" in body


def test_dashboard_declares_all_six_sections():
    body = DASHBOARD.read_text(encoding="utf-8")
    # §6.2 requires all six analytical sections.
    for header in (
        "## 1. Cumulative active population over time",
        "## 2. Founding rate by entity type",
        "## 3. Founding rate by topic focus",
        "## 4. Lifecycle state distribution",
        "## 5. Topic × entity-type heatmap",
        "## 6. Geographic scope and lead actor",
    ):
        assert header in body, header


def test_dashboard_interpolates_view_description():
    body = DASHBOARD.read_text(encoding="utf-8")
    assert "VIEW_DESCRIPTIONS[selectedView]" in body


def test_dashboard_does_not_shadow_the_view_builtin():
    """`const view = view(...)` is a temporal-dead-zone self-reference.

    `view` is Observable Framework's own builtin for wiring an Input as a
    reactive value. Binding the result to a `const` of the same name shadows
    it for the whole block, so the call reads the not-yet-initialised
    binding and the page dies with "Cannot access 'view' before
    initialization" — which shipped to production on 2026-09-07.
    """
    body = DASHBOARD.read_text(encoding="utf-8")
    assert not re.search(r"\bconst\s+view\s*=\s*view\s*\(", body)


def test_pages_do_not_use_the_md_tagged_template():
    """`md` is an Observable *notebook* builtin, absent from Framework.

    A page using it builds fine and then throws "md is not defined" in the
    browser, so this can only be caught by reading the source (or the live
    page). Use `html` or `renderInlineMarkdown` instead.
    """
    offenders = []
    for page in sorted((REPO_ROOT / "src").rglob("*.md")):
        for i, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            # A tagged template call: `md` immediately followed by a backtick.
            if re.search(r"(?<![\w.`])md`", line):
                offenders.append(f"{page.relative_to(REPO_ROOT)}:{i}")
    assert not offenders, f"`md` tagged template used in: {offenders}"


def test_dashboard_uses_agvFiltered_for_all_charts():
    """Every Plot.* call should use the filtered dataset, not raw agv."""
    body = DASHBOARD.read_text(encoding="utf-8")
    # Loosen: there must be many `agvFiltered` references and no `Plot.*(agv,`.
    assert "agvFiltered" in body
    # Catch the common regression: Plot.barX(agv, ...) instead of agvFiltered.
    raw_plot_refs = re.findall(r"Plot\.\w+\(\s*agv\s*,", body)
    assert not raw_plot_refs, (
        f"Plot mark(s) bound to unfiltered `agv` instead of `agvFiltered`: "
        f"{raw_plot_refs}"
    )


def test_dashboard_references_all_three_view_values_via_component():
    """View values come from VIEW_VALUES; we require the import, not literals."""
    body = DASHBOARD.read_text(encoding="utf-8")
    assert "VIEW_VALUES" in body
    # And the top-level paragraph names all three views in prose
    for phrase in (
        "continuous",
        "recurring",
        "one-off",  # hyphenated form in the intro paragraph
    ):
        assert phrase in body.lower(), phrase


def test_dashboard_notes_toggle_rerenders_charts():
    body = DASHBOARD.read_text(encoding="utf-8")
    assert "re-renders" in body.lower()
