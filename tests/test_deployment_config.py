"""Deployment configuration tests (CLAUDE.md §9 Task 11).

Validates the offline artefacts that Cloudflare Pages consumes:

  - `src/_headers`  — security + cache headers.
  - `src/robots.txt` — crawler policy.
  - `wrangler.toml` — Pages project config.
  - `scripts/verify_deployment.sh` — smoke check script.

Live-deploy verification (Done-when #1 + #2) happens on Cloudflare and is
tracked in `CHANGELOG.md`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS = REPO_ROOT / "src" / "_headers"
ROBOTS = REPO_ROOT / "src" / "robots.txt"
WRANGLER = REPO_ROOT / "wrangler.toml"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_deployment.sh"
CI_SETUP = REPO_ROOT / ".github" / "CI_SETUP.md"
README = REPO_ROOT / "README.md"


# ---- _headers ----

def test_headers_file_exists():
    assert HEADERS.exists()


def test_headers_has_global_rule():
    body = HEADERS.read_text(encoding="utf-8")
    # /* on its own line == global rule in Cloudflare _headers format
    assert re.search(r"^/\*\s*$", body, re.MULTILINE)


def test_headers_applies_security_headers_globally():
    body = HEADERS.read_text(encoding="utf-8")
    for h in (
        "X-Content-Type-Options: nosniff",
        "X-Frame-Options: DENY",
        "Referrer-Policy:",
        "Permissions-Policy:",
        "Content-Security-Policy:",
    ):
        assert h in body, h


def test_headers_csp_keeps_observable_reactivity_working():
    body = HEADERS.read_text(encoding="utf-8")
    # Observable Framework needs new Function(...) and inline style blocks;
    # a CSP that disables these would brick the dashboard.
    assert "'unsafe-eval'" in body
    assert "'unsafe-inline'" in body
    assert "frame-ancestors 'none'" in body


def test_headers_long_cache_for_hashed_assets():
    body = HEADERS.read_text(encoding="utf-8")
    # Hashed Observable Framework paths deserve immutable long cache.
    for path in ("/_file/*", "/_import/*", "/_observablehq/*", "/_npm/*"):
        assert path in body, path
    # Any long cache rule should carry `immutable` so browsers don't revalidate.
    assert re.search(r"max-age=31536000,\s*immutable", body)


# ---- robots.txt ----

def test_robots_file_exists():
    assert ROBOTS.exists()


def test_robots_allows_crawling_by_default():
    body = ROBOTS.read_text(encoding="utf-8")
    assert re.search(r"^User-agent:\s*\*", body, re.MULTILINE)
    assert re.search(r"^Allow:\s*/", body, re.MULTILINE)
    # A naive "Disallow: /" would block everything; guard against that.
    assert not re.search(r"^Disallow:\s*/\s*$", body, re.MULTILINE)


def test_robots_sitemap_hint_present():
    body = ROBOTS.read_text(encoding="utf-8")
    assert re.search(r"^Sitemap:\s+https?://", body, re.MULTILINE)


# ---- wrangler.toml ----

def test_wrangler_toml_exists():
    assert WRANGLER.exists()


def test_wrangler_toml_targets_agv_tracker_project():
    body = WRANGLER.read_text(encoding="utf-8")
    assert re.search(r'^\s*name\s*=\s*"agv-tracker"\s*$', body, re.MULTILINE)


def test_wrangler_toml_output_dir_is_dist():
    body = WRANGLER.read_text(encoding="utf-8")
    assert re.search(
        r'^\s*pages_build_output_dir\s*=\s*"dist"\s*$', body, re.MULTILINE,
    )


def test_wrangler_toml_has_compatibility_date():
    body = WRANGLER.read_text(encoding="utf-8")
    assert re.search(
        r'^\s*compatibility_date\s*=\s*"\d{4}-\d{2}-\d{2}"\s*$',
        body,
        re.MULTILINE,
    )


# ---- verify_deployment.sh ----

def test_verify_script_is_executable():
    import stat
    assert VERIFY_SCRIPT.exists()
    assert VERIFY_SCRIPT.stat().st_mode & stat.S_IXUSR


def test_verify_script_uses_strict_mode():
    body = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in body


def test_verify_script_passes_bash_syntax_check():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")
    result = subprocess.run(
        [bash, "-n", str(VERIFY_SCRIPT)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_verify_script_covers_major_routes():
    body = VERIFY_SCRIPT.read_text(encoding="utf-8")
    # At minimum the four top-level pages plus a venue detail page and robots.
    for path in ('"/"', '"/dashboard"', '"/venues/"', '"/methodology"',
                 '"/data-download"', '"/robots.txt"'):
        assert path in body, path
    # At least one venue detail page (any agv_id will do).
    assert re.search(r'"/venues/[a-z0-9_]+"', body)


def test_verify_script_fails_on_non_200():
    body = VERIFY_SCRIPT.read_text(encoding="utf-8")
    # Any bash idiom for "code equals 200" is acceptable.
    assert re.search(r'"\$?\{?code\}?"?\s*==\s*"?200"?', body), body[:200]
    assert re.search(r"exit\s+1", body)


def test_verify_script_has_sensible_default_base_url():
    body = VERIFY_SCRIPT.read_text(encoding="utf-8")
    # Default placeholder must be a plausible https URL, not empty.
    assert re.search(
        r'BASE_URL="\$\{1:-https://[a-z0-9.-]+}"',
        body,
    ), "default BASE_URL should be an https:// URL"


# ---- docs ----

def test_ci_setup_documents_cloudflare_bootstrap():
    body = CI_SETUP.read_text(encoding="utf-8")
    # Task 11 bootstrap steps must be spelled out.
    for phrase in (
        "Cloudflare Pages",
        "agv-tracker",
        "Custom domain",
        "HTTPS",
        "DNS",
        "verify_deployment.sh",
    ):
        assert phrase in body, phrase


def test_readme_mentions_live_site():
    body = README.read_text(encoding="utf-8")
    assert "Live site" in body
    assert "agv-tracker.pages.dev" in body or "pages.dev" in body
    assert "verify_deployment.sh" in body


# ---- post-build passthrough ----

def test_post_build_script_exists_and_is_strict():
    script = REPO_ROOT / "scripts" / "post_build.sh"
    assert script.exists()
    body = script.read_text(encoding="utf-8")
    assert "set -euo pipefail" in body
    assert "_headers" in body
    assert "robots.txt" in body


def test_package_json_build_invokes_post_build():
    import json
    pkg = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    build = pkg["scripts"]["build"]
    assert "observable build" in build
    assert "post_build.sh" in build
