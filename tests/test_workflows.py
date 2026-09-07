"""Structural validation of the GitHub Actions workflows and the driver shell
script (CLAUDE.md §9 Task 7).

We cannot actually execute workflows from the local sandbox. These tests
enforce the parts we CAN check offline:

  - The YAML parses.
  - The file shape matches GitHub Actions conventions (``on`` / ``jobs``).
  - The specific triggers, permissions, and actions required by §9 Task 7
    step 1-4 are present (cron strings, ``peter-evans/create-pull-request``,
    ``cloudflare/wrangler-action``, ``lycheeverse/lychee-action``, etc.).
  - ``scripts/monthly_update.sh`` passes ``bash -n`` syntax check.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
DRIVER_SCRIPT = REPO_ROOT / "scripts" / "monthly_update.sh"

EXPECTED_WORKFLOWS = {
    "monthly_fetch.yml",
    "deploy.yml",
    "validate.yml",
    "linkcheck.yml",
}


def _load(path: Path) -> dict:
    # PyYAML turns the bare ``on`` key into Python True; use a safe loader
    # that preserves it as the string "on".
    class _PreserveOnLoader(yaml.SafeLoader):
        pass

    def _str_bool(loader, node):
        value = node.value
        if value in ("on", "On", "ON"):
            return "on"
        if value in ("off", "Off", "OFF"):
            return "off"
        return yaml.SafeLoader.construct_yaml_bool(loader, node)

    _PreserveOnLoader.add_constructor("tag:yaml.org,2002:bool", _str_bool)
    return yaml.load(path.read_text(encoding="utf-8"), _PreserveOnLoader)


def _action_uses(jobs: dict) -> set[str]:
    """Return the set of ``uses:`` action references anywhere in ``jobs``."""
    out: set[str] = set()
    for job in (jobs or {}).values():
        for step in job.get("steps", []) or []:
            if isinstance(step, dict) and "uses" in step:
                out.add(step["uses"].split("@")[0])
    return out


# ---- file presence ----

def test_all_four_workflows_present():
    present = {p.name for p in WORKFLOWS_DIR.glob("*.yml")}
    assert EXPECTED_WORKFLOWS.issubset(present), present


# ---- monthly_fetch.yml (step 1) ----

def test_monthly_fetch_has_cron_and_dispatch():
    data = _load(WORKFLOWS_DIR / "monthly_fetch.yml")
    triggers = data["on"]
    assert "workflow_dispatch" in triggers
    schedules = triggers["schedule"]
    assert any(s["cron"] == "0 9 1 * *" for s in schedules), schedules


def test_monthly_fetch_uses_required_actions():
    data = _load(WORKFLOWS_DIR / "monthly_fetch.yml")
    actions = _action_uses(data["jobs"])
    assert "peter-evans/create-pull-request" in actions
    assert "astral-sh/setup-uv" in actions
    assert "actions/checkout" in actions


def test_monthly_fetch_runs_driver_script():
    data = _load(WORKFLOWS_DIR / "monthly_fetch.yml")
    steps = data["jobs"]["monthly-update"]["steps"]
    run_cmds = [s.get("run", "") for s in steps if "run" in s]
    assert any("scripts/monthly_update.sh" in cmd for cmd in run_cmds)


def test_monthly_fetch_has_write_permissions():
    data = _load(WORKFLOWS_DIR / "monthly_fetch.yml")
    perms = data["permissions"]
    assert perms["contents"] == "write"
    assert perms["pull-requests"] == "write"


def test_monthly_fetch_sets_anthropic_key_env():
    data = _load(WORKFLOWS_DIR / "monthly_fetch.yml")
    steps = data["jobs"]["monthly-update"]["steps"]
    env_steps = [s for s in steps if isinstance(s.get("env"), dict)]
    assert any("ANTHROPIC_API_KEY" in s["env"] for s in env_steps), env_steps


# ---- deploy.yml (step 2) ----

def test_deploy_triggers_on_push_to_main():
    data = _load(WORKFLOWS_DIR / "deploy.yml")
    push = data["on"]["push"]
    assert "main" in push["branches"]
    # The deploy should be scoped, not run on every trivial README edit.
    assert "paths" in push and any("src" in p for p in push["paths"])


def test_deploy_uses_cloudflare_wrangler_action():
    data = _load(WORKFLOWS_DIR / "deploy.yml")
    actions = _action_uses(data["jobs"])
    assert "cloudflare/wrangler-action" in actions
    assert "actions/setup-node" in actions


def test_deploy_builds_observable_framework():
    data = _load(WORKFLOWS_DIR / "deploy.yml")
    steps = data["jobs"]["deploy"]["steps"]
    run_cmds = [s.get("run", "") for s in steps if "run" in s]
    assert any("npm run build" in cmd for cmd in run_cmds)


def test_deploy_cloudflare_step_references_secrets_and_project():
    data = _load(WORKFLOWS_DIR / "deploy.yml")
    steps = data["jobs"]["deploy"]["steps"]
    cf = next(
        s for s in steps
        if "uses" in s and s["uses"].startswith("cloudflare/wrangler-action")
    )
    with_block = cf["with"]
    assert "CLOUDFLARE_API_TOKEN" in str(with_block["apiToken"])
    assert "CLOUDFLARE_ACCOUNT_ID" in str(with_block["accountId"])
    assert "agv-tracker" in with_block["command"]


# ---- validate.yml (step 3) ----

def test_validate_triggers_on_pull_request():
    data = _load(WORKFLOWS_DIR / "validate.yml")
    assert "pull_request" in data["on"]


def test_validate_has_python_and_node_and_linkcheck_jobs():
    data = _load(WORKFLOWS_DIR / "validate.yml")
    jobs = data["jobs"]
    assert {"python", "node", "linkcheck"}.issubset(jobs.keys())


def test_validate_python_enforces_coverage_threshold():
    data = _load(WORKFLOWS_DIR / "validate.yml")
    steps = data["jobs"]["python"]["steps"]
    run_cmds = [s.get("run", "") for s in steps if "run" in s]
    assert any("--cov-fail-under=90" in cmd for cmd in run_cmds), run_cmds
    assert any("pipelines.diff" in cmd for cmd in run_cmds)


def test_validate_node_builds_site():
    data = _load(WORKFLOWS_DIR / "validate.yml")
    steps = data["jobs"]["node"]["steps"]
    run_cmds = [s.get("run", "") for s in steps if "run" in s]
    assert any("npm run build" in cmd for cmd in run_cmds)


def test_validate_linkcheck_uses_lychee_and_is_scoped_to_changed_files():
    data = _load(WORKFLOWS_DIR / "validate.yml")
    actions = _action_uses(data["jobs"])
    assert "lycheeverse/lychee-action" in actions
    # tj-actions/changed-files drives the "changed URLs only" contract
    assert "tj-actions/changed-files" in actions


# ---- linkcheck.yml (step 4) ----

def test_linkcheck_is_weekly():
    data = _load(WORKFLOWS_DIR / "linkcheck.yml")
    schedules = data["on"]["schedule"]
    assert any(re.fullmatch(r"\d+\s+\d+\s+\*\s+\*\s+\d+", s["cron"])
               for s in schedules), schedules


def test_linkcheck_opens_issue_on_failure():
    data = _load(WORKFLOWS_DIR / "linkcheck.yml")
    steps = data["jobs"]["lychee"]["steps"]
    issue_step = next(
        s for s in steps
        if "uses" in s and "create-issue-from-file" in s["uses"]
    )
    assert "if" in issue_step  # guarded on lychee failure
    assert "exit_code" in issue_step["if"]


def test_linkcheck_covers_registry_and_dataset():
    data = _load(WORKFLOWS_DIR / "linkcheck.yml")
    steps = data["jobs"]["lychee"]["steps"]
    lychee = next(
        s for s in steps
        if "uses" in s and s["uses"].startswith("lycheeverse/lychee-action")
    )
    args = lychee["with"]["args"]
    assert "sources/registry.yml" in args
    assert "data/agv.csv" in args
    # internal://... URLs from llm_classification evidence must be excluded.
    # The exclusion may live in `args` or in .lycheeignore, which lychee
    # reads automatically; what matters is that it is excluded somewhere.
    ignore = (REPO_ROOT / ".lycheeignore")
    ignore_body = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    assert "internal://" in args or "internal://" in ignore_body


# ---- monthly_update.sh ----

def test_driver_script_passes_bash_syntax_check():
    assert DRIVER_SCRIPT.exists()
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")
    result = subprocess.run(
        [bash, "-n", str(DRIVER_SCRIPT)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_driver_script_is_executable():
    import stat
    mode = DRIVER_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "monthly_update.sh should be executable"


def test_driver_script_uses_strict_mode():
    body = DRIVER_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in body


def test_driver_script_chains_four_pipeline_stages():
    body = DRIVER_SCRIPT.read_text(encoding="utf-8")
    for mod in (
        "pipelines.fetchers.oecd_ai",
        "pipelines.normalize",
        "pipelines.diff",
        "pipelines.candidates_to_pr",
    ):
        assert mod in body, f"driver script must invoke {mod}"


def test_driver_script_has_mock_fallback_for_missing_api_key():
    body = DRIVER_SCRIPT.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in body
    assert "--mock" in body


def test_ci_setup_doc_present():
    doc = REPO_ROOT / ".github" / "CI_SETUP.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for secret in ("ANTHROPIC_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        assert secret in text, f"{secret} not documented"


def test_lychee_args_use_only_flags_that_exist_in_v2():
    """`--exclude-mail` was removed in lychee v2.

    lychee rejects the whole invocation with a usage error (exit 2) rather
    than ignoring the unknown flag, so no URL is ever fetched. In
    `validate.yml` that failed the linkcheck job on every pull request; in
    `linkcheck.yml`, where `fail: false` masks the exit status, it would
    have filed a "broken URLs detected" issue every week off a usage error
    rather than off any real link. Excluding `mailto:` is v2's default —
    `--include-mail` opts back in.
    """
    for name in ("validate.yml", "linkcheck.yml"):
        body = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        offenders = [
            line for line in body.splitlines()
            if "--exclude-mail" in line and not line.strip().startswith("#")
        ]
        assert not offenders, f"{name}: {offenders}"


# ---- .lycheeignore ----

LYCHEEIGNORE = REPO_ROOT / ".lycheeignore"


def test_lycheeignore_exists_and_both_jobs_can_use_it():
    """lychee reads .lycheeignore from the working directory automatically.

    Keeping the exclusions there rather than in `args` is what stops the
    PR-scoped job and the weekly job from drifting apart.
    """
    assert LYCHEEIGNORE.exists()
    for name in ("validate.yml", "linkcheck.yml"):
        body = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        assert "--exclude " not in body, (
            f"{name}: per-URL exclusions belong in .lycheeignore"
        )


def test_every_lycheeignore_entry_states_a_reason():
    """An exclusion without a reason cannot be told from a hidden break.

    These are the URLs behind `primary_reference_url` values, so each
    pattern must be preceded by a comment line explaining it.
    """
    lines = LYCHEEIGNORE.read_text(encoding="utf-8").splitlines()
    undocumented = []
    for i, line in enumerate(lines):
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        # Walk back over the contiguous comment block above the pattern.
        j = i - 1
        comment = []
        while j >= 0 and lines[j].strip().startswith("#"):
            comment.append(lines[j].strip("# ").strip())
            j -= 1
        if not any(comment):
            undocumented.append(pattern)
    assert not undocumented, f"undocumented exclusions: {undocumented}"

