"""LLM-assisted classifier for the AGVO v0.3 ontology (CLAUDE.md §9 Task 5).

Classifies free-text mandate descriptions across the six AGVO dimensions:
entity_type, governance_modality_primary, topic_focus_primary,
geographic_scope, lead_actor_primary, legal_character.

For each (venue, dimension) pair the classifier emits a `ClassificationResult`
with `(value, confidence, rationale)` plus bookkeeping fields (run_id, model
version, token counts, cost). When an `agv_evidence.csv`-formatted output is
requested, each result becomes a row with ``source_type='llm_classification'``,
``source_url='internal://classifier-run/{run_id}'``,
``evidence_note={rationale}``, ``reviewer={model_version}`` per §4.4.

Strategy note (Task 5 analogue of Task 4's step-3 contract):
    Live accuracy against the 10 gold examples has NOT yet been exercised in
    this sandboxed environment. The classifier machinery and the deterministic
    ``mock_llm_call`` backend are validated by tests/test_classify.py, but the
    entity_type ≥80% / other-dimension ≥70% thresholds will be verified on the
    first online run via the ``--eval`` subcommand. When first run live,
    update this docstring and ``CHANGELOG.md`` with the per-dimension accuracy.

Default backend: Anthropic Claude API (lazy-imported from the optional
``[classifier]`` extras). If the ``anthropic`` SDK is not installed or the
``ANTHROPIC_API_KEY`` environment variable is unset, the default CLI path
falls back to ``mock_llm_call`` so that ``python -m pipelines.classify …``
always produces output. Use ``--live`` to disable the fallback and
``--mock`` to force the mock.

CLI examples::

    # Classify discovery records against all six dimensions
    python -m pipelines.classify \\
        --input raw.json --output classified.json \\
        --evidence-out data/agv_evidence_candidates.csv

    # Evaluate against the shipped 10 gold examples (prints pass/fail per dim)
    python -m pipelines.classify \\
        --eval tests/fixtures/classify/gold_examples.jsonl --mock
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_CACHE_DIR = Path(".cache/classifier")
DEFAULT_BUDGET_FILE = DEFAULT_CACHE_DIR / "budget.json"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MONTHLY_BUDGET_USD = 50.0
DEFAULT_MAX_TOKENS = 600

log = logging.getLogger("classifier")

# ---- AGVO enum values (duplicate of tests/test_schema.py's tables, kept local
# to keep this module self-contained for downstream consumers). ----

ENTITY_TYPES = [
    "igo_initiative", "intergov_forum", "treaty_body", "multistakeholder_coalition",
    "industry_consortium", "intl_ngo_thinktank", "academic_consortium",
    "standards_body_wg", "national_regulator_intl", "conference_policy_track",
    "standalone_governance_conference", "industry_conference", "one_off_summit",
]
GOVERNANCE_MODALITIES = [
    "declaration_principles", "binding_instrument", "technical_standards",
    "evaluation_benchmarking", "capacity_building", "research_monitoring",
    "dialogue_coordination", "regulatory_enforcement",
]
TOPIC_FOCI = [
    "ai_general", "safety_frontier", "ethics_rights", "privacy_data",
    "genai_content", "agentic_autonomy", "domain_health", "domain_defense",
    "domain_education", "domain_climate", "domain_labor", "access_inclusion",
    "standards_interop",
]
GEO_SCOPES = ["global", "transregional", "regional", "plurilateral", "bilateral_plus"]
LEAD_ACTORS = [
    "igo_secretariat", "state_govt", "industry", "academia",
    "civil_society", "hybrid_mso",
]
LEGAL_CHARACTERS = ["soft_law", "hard_law", "mixed", "n/a"]

CONFIDENCE_VALUES = {"high", "medium", "low"}

# Dimension specs: (field_name, prompt_filename, allowed_values)
DIMENSIONS: list[tuple[str, str, list[str]]] = [
    ("entity_type", "classify_entity_type.txt", ENTITY_TYPES),
    ("governance_modality_primary", "classify_governance_modality.txt", GOVERNANCE_MODALITIES),
    ("topic_focus_primary", "classify_topic_focus.txt", TOPIC_FOCI),
    ("geographic_scope", "classify_geographic_scope.txt", GEO_SCOPES),
    ("lead_actor_primary", "classify_lead_actor.txt", LEAD_ACTORS),
    ("legal_character", "classify_legal_character.txt", LEGAL_CHARACTERS),
]

# Anthropic list prices (USD per million tokens), input then output.
# Checked 2026-09-07. Prices move: `compute_cost` is a budget guard, not an
# invoice, and an unknown model falls back to the default model's rate —
# deliberately, so a typo in a model id cannot silently disable the guard.
PRICING: dict[str, tuple[float, float]] = {
    # Current generation
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # Previous generation, still priced here for older cached runs
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}


# Backend identifiers. Every backend tags its reply with `_backend`, and the
# evidence trail records *who actually answered* rather than which model was
# configured: writing the model name into `agv_evidence.reviewer` for a
# classification no Claude ever saw is a false attribution in the dataset's
# own provenance (CLAUDE.md §4.4), and it makes a plumbing run look exactly
# like a real one.
BACKEND_ANTHROPIC = "anthropic"
BACKEND_MOCK = "mock"


# ---- Data classes ----

@dataclass
class ClassificationResult:
    agv_id: str
    field_name: str
    value: str
    confidence: str
    rationale: str
    model_version: str
    run_id: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    backend: str = BACKEND_MOCK

    @property
    def reviewer(self) -> str:
        """What to record as `agv_evidence.reviewer` for this field.

        The configured model name only when that model was actually
        called. A mock classification says so, so a reader of the
        evidence trail can tell a real run from a plumbing exercise.
        """
        if self.backend == BACKEND_ANTHROPIC:
            return self.model_version
        return f"{BACKEND_MOCK} (no {self.model_version} call)"


# ---- Helpers ----

def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:24]


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response body."""
    body = text.strip()
    body = re.sub(r"^```(?:json)?\s*", "", body)
    body = re.sub(r"\s*```$", "", body)
    depth = 0
    start = -1
    for i, ch in enumerate(body):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = body[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        start = -1
                        continue
    raise ValueError(f"no parseable JSON object in LLM response: {text[:200]!r}")


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000


# ---- LLM backends ----

def anthropic_llm_call(model: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> dict:
    """Live Anthropic API call. Lazy-imports the SDK."""
    try:
        import anthropic
    except ImportError as e:
        raise ImportError(
            "anthropic SDK not installed. Install with:\n"
            "  uv sync --extra classifier\n"
            "or re-run with --mock."
        ) from e
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text if msg.content else ""
    parsed = extract_json(text)
    parsed["_tokens_in"] = msg.usage.input_tokens
    parsed["_tokens_out"] = msg.usage.output_tokens
    parsed["_backend"] = BACKEND_ANTHROPIC
    return parsed


# ---- Mock backend ----

_KW_ENTITY_TYPE: list[tuple[tuple[str, ...], str]] = [
    # Very specific acronyms / named venues go first so that later, more
    # generic keywords (e.g. "oecd", "think tank") cannot shadow them.
    (("iso/iec", "ieee p7", "itu-t fg", "standards working group",
      "sc 42", "jtc 1"), "standards_body_wg"),
    (("aisi", "ai safety institute", "ai office", "ai security institute",
      "national ai regulator"), "national_regulator_intl"),
    (("ccw", "gge on laws", "lethal autonomous weapons",
      "framework convention", "ad hoc committee", "cahai",
      "eu ai board", "ai scientific panel"), "treaty_body"),
    (("frontier model forum", "mlcommons", "c2pa ", "coalition for secure",
      "ai alliance", "itic ai", "bsa ai", "industry consortium",
      "industry-led consortium"), "industry_consortium"),
    (("partnership on ai", "wef ai governance", "multistakeholder coalition",
      "responsible ai institute", "ai verify foundation", "gpai working group"),
     "multistakeholder_coalition"),
    (("faact", "faccT", "aies", "eaamo", "forc conference", "icail",
      "conference on fairness", "conference on ai ethics",
      "standalone annual academic conference"),
     "standalone_governance_conference"),
    (("workshop", "special track", "policy track"), "conference_policy_track"),
    (("ellis ", "cifar", "ircai", "academic consortium", "cross-institutional",
      "network of universities", "apru"), "academic_consortium"),
    (("web summit", "cogx", "world summit ai", "industry conference",
      "commercial summit", "sponsored conference"), "industry_conference"),
    (("summit 2023", "summit 2024", "summit 2025", "asilomar", "bletchley",
      "seoul summit", "paris action summit", "reaim 20",
      "one-off summit", "ministerial council meeting"),
     "one_off_summit"),
    (("g7 hiroshima", "g7 ai", "g20 digital", "quad critical",
      "brics ai", "asean guide", "trade and technology council",
      "intergovernmental forum"), "intergov_forum"),
    (("think tank", "non-profit", "civil-society think", "future of life institute",
      "caidp", "ada lovelace", "ai now", "cltr", "apollo research",
      "metr ", "access now"), "intl_ngo_thinktank"),
    (("oecd", "unesco", "wipo", "who ", "itu ", "un high-level",
      "un global dialogue", "au continental", "fair lac", "igo initiative",
      "initiative within"), "igo_initiative"),
]

_KW_MODALITY: list[tuple[tuple[str, ...], str]] = [
    (("regulation 2024", "regulatory enforcement", "enforces", "enforcement body",
      "supervises"), "regulatory_enforcement"),
    (("binding instrument", "binding treaty", "binding convention",
      "treaty-drafting", "statute"), "binding_instrument"),
    (("technical standards", "standards organization", "voluntary standards",
      "specification", "interoperab", "terminology"), "technical_standards"),
    (("evaluation", "benchmark", "audit", "red team", "red-team",
      "capability evaluation", "testing"), "evaluation_benchmarking"),
    (("capacity building", "readiness assessment", "readiness methodology",
      "training programme", "tooling for adoption"), "capacity_building"),
    (("principles", "code of conduct", "declaration", "guidelines",
      "ethical framework"), "declaration_principles"),
    (("research", "monitoring", "observatory", "maps the landscape",
      "incident database", "publishes research"), "research_monitoring"),
    (("dialogue", "convenes", "convening", "forum for", "coordination",
      "alliance"), "dialogue_coordination"),
]

_KW_TOPIC: list[tuple[tuple[str, ...], str]] = [
    (("frontier", "catastrophic", "existential", "safety", "dangerous capabilities",
      "ai safety"), "safety_frontier"),
    (("ethics", "human rights", "fairness", "accountability", "non-discrimination",
      "bias"), "ethics_rights"),
    (("privacy", "data protection", "gdpr", "data governance"), "privacy_data"),
    (("generative", "content provenance", "synthetic media", "deepfake", "watermark"),
     "genai_content"),
    (("autonomous agent", "multi-agent", "agentic", "agentic risk"),
     "agentic_autonomy"),
    (("health", "medicine", "clinical"), "domain_health"),
    (("military", "defence", "defense", "lethal", "weapons", "autonomous weapons"),
     "domain_defense"),
    (("education", "schools"), "domain_education"),
    (("climate", "environment", "energy efficiency", "green ai"), "domain_climate"),
    (("labour", "labor", "employment", "workforce", "productivity", "skills"),
     "domain_labor"),
    (("inclusion", "global south", "access ", "digital inclusion", "equity and access"),
     "access_inclusion"),
    (("interoperability", "interoperable standards", "terminology standards"),
     "standards_interop"),
]

_KW_GEO: list[tuple[tuple[str, ...], str]] = [
    (("bilateral", "eu-us", "us-uk bilateral"), "bilateral_plus"),
    (("g7", "g20", "quad", "brics", "plurilateral", "gpai member states"),
     "plurilateral"),
    (("european union", " eu ", "council of europe", "african union",
      "asean", "latin america", "regional ", "mercosur", "africa continental"),
     "regional"),
    (("transregional", "oecd member states", "oecd + "), "transregional"),
    (("global", "worldwide", "open membership", "all un member states", "193 member states"),
     "global"),
]

_KW_LEAD: list[tuple[tuple[str, ...], str]] = [
    # Civil society first — "civil-society think tank" should NOT fall through
    # to "academic" via "research institute" etc.
    (("civil society", "civil-society", "non-profit", "think tank", "advocacy",
      " ngo "), "civil_society"),
    (("oecd secretariat", "oecd ", "unesco", "un agenc", "un secretariat",
      "itu ", "who ", "european commission", "council of europe secretariat",
      "wipo", "igo secretariat"), "igo_secretariat"),
    (("national government", "state government", "state govt", "state-to-state",
      "national regulator", "aisi", "ai safety institute", "g7 states",
      "g7 hiroshima", "g20 states", "cabinet-approved", "ministry"),
     "state_govt"),
    (("industry-led", "corporate members", "industry consortium",
      "industry trade association"), "industry"),
    (("academic", "university", "faculty", "peer-reviewed", "acm ", "ieee "),
     "academia"),
    (("multistakeholder leadership", "balanced cross-sector",
      "cross-sector balance",
      "partnership of government, industry, academia"), "hybrid_mso"),
]

_KW_LEGAL: list[tuple[tuple[str, ...], str]] = [
    (("regulation 2024/1689", "statute", "enforces domestic law",
      "binding instrument", "hard-law", "interim measures effective",
      "royal decree"), "hard_law"),
    (("research-only", "research institute", "think tank", "academic conference",
      "benchmarks", "no normative output", "conference-only"), "n/a"),
    (("mixed", "both binding and non-binding", "hybrid hard/soft", "issues guidance and enforces"),
     "mixed"),
    (("soft-law", "non-binding", "principles", "code of conduct", "declaration",
      "voluntary standards", "guidelines", "recommendation"),
     "soft_law"),
]


def _keyword_match(haystack: str, table: list[tuple[tuple[str, ...], str]]) -> str | None:
    for keywords, value in table:
        for kw in keywords:
            if kw in haystack:
                return value
    return None


def mock_llm_call(model: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> dict:
    """Deterministic mock — detects dimension from prompt preamble, then uses
    keyword heuristics on the ``{text}`` payload to produce a plausible reply.

    Not accurate enough to be used in production but covers the gold examples
    deterministically and exercises the full classifier plumbing in tests.
    """
    m = re.search(r"Text to classify:\s*(.+?)$", prompt, re.DOTALL)
    text_part = (m.group(1) if m else prompt).lower()

    if "`entity_type`" in prompt:
        value = _keyword_match(text_part, _KW_ENTITY_TYPE) or "igo_initiative"
    elif "`governance_modality_primary`" in prompt:
        value = _keyword_match(text_part, _KW_MODALITY) or "dialogue_coordination"
    elif "`topic_focus_primary`" in prompt:
        value = _keyword_match(text_part, _KW_TOPIC) or "ai_general"
    elif "`geographic_scope`" in prompt:
        value = _keyword_match(text_part, _KW_GEO) or "global"
    elif "`lead_actor_primary`" in prompt:
        value = _keyword_match(text_part, _KW_LEAD) or "igo_secretariat"
    elif "`legal_character`" in prompt:
        value = _keyword_match(text_part, _KW_LEGAL) or "soft_law"
    else:
        raise ValueError("mock_llm_call: could not detect dimension from prompt header")

    return {
        "value": value,
        "confidence": "medium",
        "rationale": f"[mock backend] keyword-matched to {value!r}",
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_backend": BACKEND_MOCK,
    }


# ---- Budget guard ----

class BudgetExceededError(RuntimeError):
    pass


class BudgetGuard:
    def __init__(self, path: Path, monthly_budget_usd: float):
        self.path = Path(path)
        self.monthly_budget_usd = float(monthly_budget_usd)

    @staticmethod
    def _now_month() -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def current_spend(self) -> float:
        return float(self._load().get(self._now_month(), {}).get("spend_usd", 0.0))

    def check(self, additional_usd: float) -> None:
        spent = self.current_spend()
        if spent + additional_usd > self.monthly_budget_usd:
            raise BudgetExceededError(
                f"monthly budget ${self.monthly_budget_usd:.2f} would be "
                f"exceeded: spent ${spent:.4f}, additional ${additional_usd:.4f}"
            )

    def record(self, usd: float, run_id: str) -> None:
        if usd <= 0:
            return
        data = self._load()
        month = self._now_month()
        bucket = data.setdefault(month, {"spend_usd": 0.0, "runs": []})
        bucket["spend_usd"] = float(bucket.get("spend_usd", 0.0)) + usd
        bucket.setdefault("runs", []).append({"run_id": run_id, "usd": usd})
        self._save(data)


# ---- Classifier ----

class Classifier:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        llm_call=anthropic_llm_call,
        budget_guard: BudgetGuard | None = None,
        run_id: str | None = None,
    ):
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.llm_call = llm_call
        self.budget_guard = budget_guard
        self.run_id = run_id or (
            "run-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8]
        )
        self._cumulative_cost = 0.0
        self._prompts: dict[str, str] = {}
        for field_name, filename, _ in DIMENSIONS:
            self._prompts[field_name] = (PROMPTS_DIR / filename).read_text(encoding="utf-8")

    @property
    def cumulative_cost(self) -> float:
        return self._cumulative_cost

    def classify_all(self, agv_id: str, text: str) -> list[ClassificationResult]:
        return [
            self._classify_one(agv_id, field_name, text, allowed)
            for field_name, _filename, allowed in DIMENSIONS
        ]

    def _classify_one(
        self,
        agv_id: str,
        field_name: str,
        text: str,
        allowed: list[str],
    ) -> ClassificationResult:
        prompt = self._prompts[field_name].replace("{text}", text)
        cache_key = _hash_key(self.model, field_name, text)

        cached_response = self._cache_read(cache_key)
        if cached_response is not None:
            value, confidence, rationale = self._extract_triple(cached_response, allowed)
            return ClassificationResult(
                agv_id=agv_id, field_name=field_name, value=value,
                confidence=confidence, rationale=rationale,
                model_version=self.model, run_id=self.run_id,
                cached=True,
                # A cache hit inherits the backend that produced the entry;
                # absent that, assume mock rather than claim a live call.
                backend=str(cached_response.get("backend") or BACKEND_MOCK),
            )

        if self.budget_guard:
            est = compute_cost(self.model, 1500, 200)
            self.budget_guard.check(self._cumulative_cost + est)

        response = self.llm_call(self.model, prompt)
        tokens_in = int(response.pop("_tokens_in", 0))
        tokens_out = int(response.pop("_tokens_out", 0))
        cost = compute_cost(self.model, tokens_in, tokens_out)
        self._cumulative_cost += cost
        self._cache_write(cache_key, response)

        value, confidence, rationale = self._extract_triple(response, allowed)
        return ClassificationResult(
            agv_id=agv_id, field_name=field_name, value=value,
            confidence=confidence, rationale=rationale,
            model_version=self.model, run_id=self.run_id,
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
            backend=str(response.get("_backend") or BACKEND_MOCK),
        )

    def _extract_triple(
        self, response: dict, allowed: list[str],
    ) -> tuple[str, str, str]:
        value = str(response.get("value", "")).strip()
        confidence = str(response.get("confidence", "low")).strip().lower()
        rationale = str(response.get("rationale", "")).strip()
        if confidence not in CONFIDENCE_VALUES:
            confidence = "low"
        if value not in allowed:
            log.warning(
                "%s: invalid enum value %r from model; downgrading to low confidence",
                self.run_id, value,
            )
            rationale = (
                f"[invalid-enum fallback] model returned '{value}'. "
                f"Original rationale: {rationale}"
            )
            confidence = "low"
        return value, confidence, rationale

    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{key}.json"

    def _cache_read(self, key: str) -> dict | None:
        p = self._cache_path(key)
        if p is None or not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _cache_write(self, key: str, response: dict) -> None:
        p = self._cache_path(key)
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in response.items() if not k.startswith("_")}
        # `_backend` is stripped with the other underscore keys, but it has
        # to survive: a cached mock answer replayed months later must not
        # come back wearing the model's name.
        clean["backend"] = response.get("_backend", BACKEND_MOCK)
        p.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    def finalize(self) -> None:
        if self.budget_guard and self._cumulative_cost > 0:
            self.budget_guard.record(self._cumulative_cost, self.run_id)


# ---- Evidence emission ----

def results_to_evidence_rows(results: list[ClassificationResult]) -> list[dict]:
    today = datetime.now(UTC).date().isoformat()
    return [
        {
            "agv_id": r.agv_id,
            "field_name": r.field_name,
            "source_url": f"internal://classifier-run/{r.run_id}",
            "source_type": "llm_classification",
            "accessed_at": today,
            "evidence_note": r.rationale,
            "reviewer": r.reviewer,
            "confidence": r.confidence,
        }
        for r in results
    ]


EVIDENCE_COLS = [
    "agv_id", "field_name", "source_url", "source_type",
    "accessed_at", "evidence_note", "reviewer", "confidence",
]


def write_evidence_csv(path: Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not path.exists() or path.stat().st_size == 0
    mode = "w" if header_needed else "a"
    with path.open(mode, newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=EVIDENCE_COLS)
        if header_needed:
            w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in EVIDENCE_COLS})


# ---- I/O ----

def load_records(path: Path) -> list[dict]:
    """Accept JSON array or JSON Lines."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"expected top-level list, got {type(data).__name__}")
        return data
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def record_id_and_text(rec: dict) -> tuple[str, str]:
    rid = (
        rec.get("agv_id")
        or rec.get("source_id")
        or rec.get("id")
        or ""
    )
    if "text" in rec and rec["text"]:
        return rid, str(rec["text"])
    parts = []
    for field in ("name", "description", "notes"):
        v = rec.get(field)
        if v:
            parts.append(str(v))
    return rid, " — ".join(parts)


# ---- CLI ----

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.classify",
        description=(
            "LLM-assisted AGVO classifier. "
            "Default: try Anthropic API, fall back to --mock on failure."
        ),
    )
    backend = ap.add_mutually_exclusive_group()
    backend.add_argument("--live", action="store_true",
                         help="force live Anthropic API; error on failure")
    backend.add_argument("--mock", action="store_true",
                         help="force deterministic mock backend; no API calls")
    ap.add_argument("--input", type=Path,
                    help="JSON array or JSONL of records with agv_id+text or name+description")
    ap.add_argument("--output", type=Path,
                    help="JSON output path (default: stdout)")
    ap.add_argument("--evidence-out", type=Path,
                    help="additionally write agv_evidence.csv-format rows here")
    ap.add_argument("--eval", dest="eval_path", type=Path,
                    help="evaluation mode against a gold JSONL; ignores --input")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--budget-file", type=Path, default=DEFAULT_BUDGET_FILE)
    ap.add_argument("--monthly-budget-usd", type=float, default=DEFAULT_MONTHLY_BUDGET_USD)
    ap.add_argument("--no-cache", action="store_true",
                    help="disable on-disk response cache")
    ap.add_argument("--no-budget", action="store_true",
                    help="disable monthly budget guard")
    ap.add_argument("--quiet", action="store_true")
    return ap


def _resolve_llm_call(args):
    """Return the llm_call function per CLI flags."""
    if args.mock:
        return mock_llm_call
    if args.live:
        return anthropic_llm_call
    # Default: live if credentials available and SDK importable, else mock
    try:
        import anthropic  # noqa: F401
        if os.environ.get("ANTHROPIC_API_KEY"):
            def _live_with_fallback(model, prompt, max_tokens=DEFAULT_MAX_TOKENS):
                try:
                    return anthropic_llm_call(model, prompt, max_tokens)
                except Exception as e:  # noqa: BLE001
                    log.warning("live call failed (%s); falling back to mock", e)
                    return mock_llm_call(model, prompt, max_tokens)
            return _live_with_fallback
    except ImportError:
        pass
    log.info("anthropic SDK not available or no ANTHROPIC_API_KEY; using mock backend")
    return mock_llm_call


def _make_classifier(args) -> Classifier:
    cache_dir = None if args.no_cache else args.cache_dir
    budget_guard = None
    if not args.no_budget and not args.mock:
        budget_guard = BudgetGuard(args.budget_file, args.monthly_budget_usd)
    return Classifier(
        model=args.model,
        cache_dir=cache_dir,
        llm_call=_resolve_llm_call(args),
        budget_guard=budget_guard,
    )


def _run_classify(args) -> int:
    if not args.input:
        log.error("--input is required (or use --eval)")
        return 2
    records = load_records(args.input)
    classifier = _make_classifier(args)

    out: list[dict] = []
    all_results: list[ClassificationResult] = []
    for rec in records:
        rid, text = record_id_and_text(rec)
        if not rid or not text:
            log.warning("skipping record without id/text: %s", rec)
            continue
        results = classifier.classify_all(rid, text)
        all_results.extend(results)
        out.append({
            "agv_id": rid,
            "run_id": classifier.run_id,
            "model": classifier.model,
            "classifications": [
                {
                    "field_name": r.field_name, "value": r.value,
                    "confidence": r.confidence, "rationale": r.rationale,
                    "cached": r.cached,
                }
                for r in results
            ],
        })

    classifier.finalize()

    payload = json.dumps(out, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")

    if args.evidence_out:
        write_evidence_csv(args.evidence_out, results_to_evidence_rows(all_results))

    print(
        f"classified {len(out)} record(s); run_id={classifier.run_id}; "
        f"cost=${classifier.cumulative_cost:.4f}",
        file=sys.stderr,
    )
    return 0


THRESHOLDS: dict[str, float] = {
    "entity_type": 0.80,
    "governance_modality_primary": 0.70,
    "topic_focus_primary": 0.70,
    "geographic_scope": 0.70,
    "lead_actor_primary": 0.70,
    "legal_character": 0.70,
}


def _run_eval(args) -> int:
    gold = load_records(args.eval_path)
    classifier = _make_classifier(args)

    totals = {f: 0 for f in THRESHOLDS}
    hits = {f: 0 for f in THRESHOLDS}
    misses: list[dict] = []

    for rec in gold:
        rid, text = record_id_and_text(rec)
        expected = rec.get("expected", {})
        results = classifier.classify_all(rid, text)
        for r in results:
            if r.field_name not in expected:
                continue
            totals[r.field_name] += 1
            if r.value == expected[r.field_name]:
                hits[r.field_name] += 1
            else:
                misses.append({
                    "agv_id": rid, "field": r.field_name,
                    "expected": expected[r.field_name], "got": r.value,
                    "rationale": r.rationale,
                })

    classifier.finalize()

    any_fail = False
    per_dim = []
    print(
        f"Gold evaluation run_id={classifier.run_id} model={classifier.model}",
        file=sys.stderr,
    )
    for f, threshold in THRESHOLDS.items():
        tot = totals[f]
        h = hits[f]
        acc = h / tot if tot else 0.0
        passed = acc >= threshold
        if not passed:
            any_fail = True
        per_dim.append({
            "field": f, "hits": h, "total": tot, "accuracy": acc,
            "threshold": threshold, "pass": passed,
        })
        marker = "PASS" if passed else "FAIL"
        print(
            f"  {marker:4s} {f:30s} {h}/{tot} = {acc:.1%} (threshold {threshold:.0%})",
            file=sys.stderr,
        )
    print(f"  cost=${classifier.cumulative_cost:.4f}", file=sys.stderr)

    report = {
        "run_id": classifier.run_id,
        "model": classifier.model,
        "cost_usd": classifier.cumulative_cost,
        "per_dimension": per_dim,
        "misses": misses,
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")

    return 0 if not any_fail else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.eval_path:
        return _run_eval(args)
    return _run_classify(args)


if __name__ == "__main__":
    raise SystemExit(main())
