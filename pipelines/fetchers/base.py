"""BaseFetcher ABC and the RawVenue intermediate record.

CLAUDE.md §5 splits sources into discovery/verification/background layers.
Fetchers in this package target **discovery** sources: they surface candidate
AGVs that the normalizer (Task 6) later pairs with a verification source.

Contract (CLAUDE.md §9 Task 4, step 1):
  * `fetch_html_with_fallback(url, required_selectors)`:
    1. Try `httpx.get(url)` with a reasonable timeout.
    2. Check the response for the caller-supplied `required_selectors`.
    3. If missing, fall back to Playwright (lazy-imported).
    4. Log which strategy succeeded.

The RawVenue dataclass is intentionally schema-loose: it captures the upstream
payload verbatim. Conversion into the AGV schema happens in pipelines/normalize.py.
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

USER_AGENT = "agv-tracker/0.3 (+https://github.com/rentaroiida/agv-tracker)"
FETCH_STRATEGY_STATIC = "http_static"
FETCH_STRATEGY_PLAYWRIGHT = "playwright"
FETCH_STRATEGY_CACHE = "http_static_cache"
FETCH_STRATEGY_FIXTURE = "fixture"


@dataclass
class RawVenue:
    """Intermediate record emitted by a fetcher, pre-normalization.

    `source_role` is always 'discovery' for fetcher output in v0.3 — verification
    sources are curated into registry.yml, not fetched.
    """
    source_id: str            # upstream-stable id (e.g., "oecd.ai:1001")
    source_role: str          # 'discovery' (may widen later)
    source_registry: str      # sources/registry.yml `id` field
    name: str                 # upstream-reported venue name
    url: str                  # upstream-reported canonical URL
    country: str | None = None
    description: str | None = None
    fetched_at: str = ""      # ISO 8601 UTC
    fetch_strategy: str = ""  # one of FETCH_STRATEGY_* constants
    raw_blob: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_role": self.source_role,
            "source_registry": self.source_registry,
            "name": self.name,
            "url": self.url,
            "country": self.country,
            "description": self.description,
            "fetched_at": self.fetched_at,
            "fetch_strategy": self.fetch_strategy,
            "raw_blob": self.raw_blob,
        }


class BaseFetcher(ABC):
    """ABC for discovery-layer fetchers.

    Subclasses set class-level `source_id` and `base_url`, and implement
    `fetch()`. Shared machinery — throttling, robots.txt, on-disk cache, and
    the static→Playwright fallback — lives here.
    """

    source_id: str = ""          # matches registry.yml id
    base_url: str = ""
    required_selectors: list[str] = []
    respect_robots: bool = True
    throttle_seconds: float = 1.0
    timeout_seconds: float = 10.0

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._last_request_time = 0.0
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._log = logging.getLogger(f"fetcher.{self.source_id or self.__class__.__name__}")

    # ---- contract ----

    @abstractmethod
    def fetch(self) -> list[RawVenue]:
        """Return list of RawVenue records."""

    # ---- helpers ----

    def fetch_html_with_fallback(
        self,
        url: str,
        *,
        required_selectors: list[str] | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        """Fetch HTML: static HTTP first, Playwright fallback.

        Returns `(html, strategy)` where strategy ∈ {http_static, http_static_cache,
        playwright}. If `required_selectors` is given, each substring must appear
        in the response HTML for the static path to be considered successful.
        """
        timeout = timeout or self.timeout_seconds
        selectors = required_selectors or self.required_selectors

        cached = self._read_cache(url)
        if cached is not None and self._selectors_present(cached, selectors):
            self._log.info("cache hit for %s", url)
            return cached, FETCH_STRATEGY_CACHE

        if self.respect_robots and not self._can_fetch(url):
            raise PermissionError(f"robots.txt disallows {url}")

        self._throttle()
        static_err: Exception | None = None
        try:
            import httpx
            resp = httpx.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            html = resp.text
            if self._selectors_present(html, selectors):
                self._log.info("http_static succeeded for %s", url)
                self._write_cache(url, html)
                return html, FETCH_STRATEGY_STATIC
            self._log.info(
                "http_static returned HTML without required selectors for %s; "
                "falling back to Playwright",
                url,
            )
        except Exception as e:  # noqa: BLE001 — we want to fall back on anything
            static_err = e
            self._log.warning("http_static failed for %s: %s", url, e)

        html = self._fetch_with_playwright(url, timeout=timeout)
        if selectors and not self._selectors_present(html, selectors):
            self._log.warning(
                "Playwright also returned HTML without required selectors for %s", url,
            )
        self._write_cache(url, html)
        if static_err:
            self._log.info("Playwright recovered from static-HTTP failure: %s", static_err)
        return html, FETCH_STRATEGY_PLAYWRIGHT

    # ---- implementation details ----

    @staticmethod
    def _selectors_present(html: str, selectors: list[str]) -> bool:
        if not selectors:
            return True
        return all(s in html for s in selectors)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.throttle_seconds:
            time.sleep(self.throttle_seconds - elapsed)
        self._last_request_time = time.monotonic()

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if self._robots is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                # NOT RobotFileParser.read(): it calls urllib.request.urlopen()
                # with no timeout, so a host that accepts the connection but
                # never responds blocks the whole run forever (observed on the
                # first live monthly-fetch: ~30 min hang, job killed). Fetch it
                # ourselves so the same timeout budget as page fetches applies.
                import httpx
                resp = httpx.get(
                    robots_url,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                rp.parse(resp.text.splitlines())
            except Exception as e:  # noqa: BLE001
                self._log.info("robots.txt unreachable at %s: %s (defaulting to allow)",
                               robots_url, e)
                self._robots = "_permissive_"  # type: ignore[assignment]
                return True
            self._robots = rp
        if self._robots == "_permissive_":
            return True
        return self._robots.can_fetch(USER_AGENT, url)

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{h}.html"

    def _read_cache(self, url: str) -> str | None:
        p = self._cache_path(url)
        if p is None or not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def _write_cache(self, url: str, html: str) -> None:
        p = self._cache_path(url)
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")

    def _fetch_with_playwright(self, url: str, *, timeout: float) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ImportError(
                "Playwright is not installed. Run:\n"
                "  uv sync --extra scraping\n"
                "  playwright install chromium"
            ) from e
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, timeout=timeout * 1000)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                # Bounds page.content() and any other implicit wait, not just goto().
                page.set_default_timeout(timeout * 1000)
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                html = page.content()
            finally:
                browser.close()
        return html

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
