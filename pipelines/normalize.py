"""RawVenue → v0.3 AGV-candidate normalizer (CLAUDE.md §9 Task 6 step 1).

Pipeline position: fetchers (Task 4) emit ``RawVenue`` records flagged
``source_role='discovery'``. ``Normalizer`` pairs each record with a
verification source from ``sources/registry.yml`` (per CLAUDE.md §5.2),
runs the AGVO classifier (Task 5) across the six dimensions, and emits a
v0.3-shaped *candidate* AGV dict plus LLM-classification evidence rows.

Candidates are intentionally *incomplete* (blank ``founded_date``,
``confidence_founded_date='low'``, explicit note in ``notes``). They are
not schema-valid yet; the downstream diff pipeline (``pipelines/diff.py``)
surfaces them to a monthly PR for human review.

CLI::

    python -m pipelines.normalize \\
        --input tests/fixtures/oecd_ai/dashboards.jsonl \\
        --output candidates.json \\
        --registry sources/registry.yml
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .classify import (
    ClassificationResult,
    Classifier,
    anthropic_llm_call,
    mock_llm_call,
    results_to_evidence_rows,
)
from .venue_names import extract_venue_name, looks_like_venue_name, unwrap_cdata

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "sources" / "registry.yml"

log = logging.getLogger("normalizer")

AGV_COLS: list[str] = [
    "agv_id", "name_en", "name_native",
    "entity_type", "governance_modality_primary", "governance_modality_secondary",
    "topic_focus_primary", "topic_focus_secondary_1", "topic_focus_secondary_2",
    "geographic_scope", "region_code",
    "lead_actor_primary", "lead_actor_secondary",
    "legal_character",
    "founded_date", "founded_date_precision", "establishment_basis",
    "announced_date", "first_output_date",
    "current_state", "convening_frequency", "last_observed_activity_date",
    "primary_reference_url", "last_verified_date",
    "confidence_entity_type", "confidence_founded_date",
    "confidence_current_state", "confidence_legal_character",
    "human_verified_at", "human_verified_fields",
    "override_policy", "notes",
]


# ---- helpers ----

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str, maxlen: int = 48) -> str:
    slug = _slug_re.sub("_", text.lower()).strip("_")
    return slug[:maxlen] or "unknown"


def today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def load_registry(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (data or {}).get("sources", [])


def verification_url_for_entity_type(registry: list[dict], entity_type: str) -> str | None:
    """First-matching verification source URL for the given entity_type."""
    for src in registry:
        if src.get("role") != "verification":
            continue
        if entity_type in (src.get("entity_types_covered") or []):
            return src.get("url")
    return None


def extract_name_and_text(record: dict) -> tuple[str, str, str]:
    """Return (agv_id, name_en, classification_text)."""
    name_en = unwrap_cdata(str(record.get("name_en") or record.get("name") or "")).strip()
    text = unwrap_cdata(str(record.get("text") or "")).strip()
    if not text:
        parts = []
        for field in ("name_en", "name", "description", "notes"):
            v = record.get(field)
            if v:
                parts.append(unwrap_cdata(str(v)))
        text = " — ".join(parts)
    agv_id = str(
        record.get("agv_id")
        or record.get("id")
        or slugify(name_en or record.get("source_id") or "candidate")
    )
    return agv_id, name_en, text


# ---- Normalizer ----

class Normalizer:
    def __init__(
        self,
        *,
        registry_path: Path | None = None,
        registry: list[dict] | None = None,
        classifier: Classifier | None = None,
    ):
        if registry is not None:
            self.registry = list(registry)
        else:
            self.registry = load_registry(registry_path or DEFAULT_REGISTRY)
        self.classifier = classifier or Classifier(
            cache_dir=None, llm_call=mock_llm_call, budget_guard=None,
        )
        # Records dropped by the article/venue gate, for run reporting.
        self.skipped_not_a_venue: list[dict] = []

    def normalize(self, records: list[dict]) -> list[dict]:
        """Return list of ``{agv_row, evidence_rows, provenance}`` dicts."""
        outputs: list[dict] = []
        self.skipped_not_a_venue = []
        today = today_utc()
        for rec in records:
            agv_id, name_en, text = extract_name_and_text(rec)
            if not name_en or not text:
                log.warning("skipping record missing name or text: %s", rec.get("source_id") or rec)
                continue

            # A discovery source offers article titles as readily as venue
            # names (CLAUDE.md §3.1: a venue, not coverage of one). Reject the
            # headlines; give an article one chance to name a venue in its text.
            if not looks_like_venue_name(name_en):
                extracted = extract_venue_name(f"{name_en} — {text}")
                if not extracted:
                    log.info(
                        "skipping %s: reads as an article, names no venue (%r)",
                        rec.get("source_id") or agv_id, name_en[:80],
                    )
                    self.skipped_not_a_venue.append({
                        "source_id": str(rec.get("source_id") or ""),
                        "source_registry": str(rec.get("source_registry") or ""),
                        "name": name_en,
                        "url": str(rec.get("url") or ""),
                    })
                    continue
                log.info("record %s: using venue name %r extracted from article %r",
                         rec.get("source_id") or agv_id, extracted, name_en[:60])
                name_en = extracted
                agv_id = slugify(extracted)

            results = self.classifier.classify_all(agv_id, text)
            classified = {r.field_name: r for r in results}

            # Resolve verification URL: explicit > registry lookup by classified entity_type
            explicit_ref = (
                rec.get("primary_reference_url")
                or rec.get("verification_url")
            )
            entity_type_value = classified.get("entity_type", _empty_result()).value
            ref_url = explicit_ref or verification_url_for_entity_type(
                self.registry, entity_type_value,
            )
            if not ref_url:
                log.warning(
                    "no verification URL for %s (entity_type=%s); skipping",
                    agv_id, entity_type_value,
                )
                continue

            agv_row = self._build_agv_row(
                agv_id=agv_id, name_en=name_en, rec=rec,
                classified=classified, ref_url=ref_url, today=today,
                ref_url_is_placeholder=not explicit_ref,
            )
            outputs.append({
                "agv_row": agv_row,
                "evidence_rows": results_to_evidence_rows(results),
                "provenance": {
                    "source_id": rec.get("source_id", ""),
                    "source_registry": rec.get("source_registry", ""),
                    "discovery_url": rec.get("url", ""),
                    "run_id": self.classifier.run_id,
                    "model": self.classifier.model,
                },
            })
        return outputs

    @staticmethod
    def _build_agv_row(
        *,
        ref_url_is_placeholder: bool = False,
        agv_id: str,
        name_en: str,
        rec: dict,
        classified: dict[str, ClassificationResult],
        ref_url: str,
        today: str,
    ) -> dict:
        row = {c: "" for c in AGV_COLS}
        row["agv_id"] = agv_id
        row["name_en"] = name_en
        row["name_native"] = str(rec.get("name_native", ""))

        for field_name in (
            "entity_type", "governance_modality_primary", "topic_focus_primary",
            "geographic_scope", "lead_actor_primary", "legal_character",
        ):
            r = classified.get(field_name)
            if r is not None:
                row[field_name] = r.value

        # Fields not classified but carried through if the record provides them
        row["region_code"] = str(rec.get("region_code", ""))
        row["founded_date"] = str(rec.get("founded_date", ""))
        row["founded_date_precision"] = str(rec.get("founded_date_precision", "day"))
        row["establishment_basis"] = str(rec.get("establishment_basis", "announced"))
        row["announced_date"] = str(rec.get("announced_date", ""))
        row["first_output_date"] = str(rec.get("first_output_date", ""))
        row["current_state"] = str(rec.get("current_state", "active"))
        row["convening_frequency"] = str(rec.get("convening_frequency", "continuous"))
        row["last_observed_activity_date"] = str(rec.get("last_observed_activity_date", today))
        row["primary_reference_url"] = ref_url
        row["last_verified_date"] = today

        # Confidences: from classifier where available, else 'low' placeholder.
        row["confidence_entity_type"] = (
            classified.get("entity_type", _empty_result()).confidence or "low"
        )
        row["confidence_legal_character"] = (
            classified.get("legal_character", _empty_result()).confidence or "low"
        )
        # founded_date / current_state have no classifier dimension; stay 'low' unless
        # the record carried an explicit override.
        row["confidence_founded_date"] = str(rec.get("confidence_founded_date", "low"))
        row["confidence_current_state"] = str(rec.get("confidence_current_state", "low"))

        # Human-verification fields are deliberately empty on candidates.
        row["human_verified_at"] = ""
        row["human_verified_fields"] = ""
        row["override_policy"] = str(rec.get("override_policy", "lock_verified_only"))
        row["notes"] = (
            "normalize candidate — requires human verification of "
            "founded_date, current_state, and convening_frequency before merging."
        )
        if ref_url_is_placeholder:
            # The URL is the entity_type's verification *family* from
            # registry.yml (§5.2), identical for every candidate of that type.
            # It is a valid layer but not evidence for this venue.
            row["notes"] += (
                " | primary_reference_url is the registry verification-family "
                "placeholder for this entity_type, not this venue's own page — "
                "replace it before merging."
            )
        if rec.get("notes"):
            row["notes"] = str(rec["notes"]) + " | " + row["notes"]
        return row


def _empty_result() -> ClassificationResult:
    return ClassificationResult(
        agv_id="", field_name="", value="", confidence="low",
        rationale="", model_version="", run_id="",
    )


# ---- I/O ----

def load_records(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("expected JSON array or JSONL")
        return data
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---- CLI ----

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipelines.normalize",
        description=(
            "Turn RawVenue records (or any records with name/text) into "
            "v0.3-shaped AGV candidate dicts paired with a verification source."
        ),
    )
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    backend = ap.add_mutually_exclusive_group()
    backend.add_argument("--live", action="store_true",
                         help="run the classifier with the live Anthropic backend")
    backend.add_argument("--mock", action="store_true",
                         help="run the classifier with the deterministic mock backend")
    ap.add_argument("--cache-dir", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    records = load_records(args.input)
    llm = mock_llm_call if args.mock or not args.live else anthropic_llm_call
    classifier = Classifier(cache_dir=args.cache_dir, llm_call=llm, budget_guard=None)
    normalizer = Normalizer(registry_path=args.registry, classifier=classifier)
    outputs = normalizer.normalize(records)

    payload = json.dumps(outputs, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    skipped = len(normalizer.skipped_not_a_venue)
    print(
        f"normalized {len(outputs)} candidate(s) "
        f"from {len(records)} input record(s) "
        f"({skipped} dropped as articles, not venues); "
        f"run_id={classifier.run_id}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
