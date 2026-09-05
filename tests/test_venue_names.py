"""Venue-name vs news-headline heuristics (pipelines/venue_names.py).

The calibration corpus below is real: ARTICLES are the 17 "new venues" the
first live monthly-fetch run proposed on 2026-09-05 (all 17 were articles),
and VENUES is a sample of hand-curated names from data/agv.csv.

The gate is deliberately asymmetric. A false positive puts an article into
the monthly PR as a venue candidate, which is what we are fixing; a false
negative only means the pipeline does not *propose* a venue that a
maintainer can still add by hand. So ARTICLES is asserted exhaustively and
VENUES is asserted as a rate.
"""
from __future__ import annotations

import csv
from pathlib import Path

from pipelines.venue_names import (
    extract_venue_name,
    is_headline,
    looks_like_venue_name,
    unwrap_cdata,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTICLES = [
    "New partnership set to see the UK and Ukraine develop battle winning "
    "technology as Britain secures access to Ukraine's Avengers AI Labs",
    "Growing up in the online world: a national consultation",
    "AI agents can't yet do open-ended AI research",
    "Up the Stack: How AI's Escape From the Commodity Trap Risks Enterprise Lock-in",
    "Why AI hasn't replaced software engineers, and won't",
    "Did Google's AI agents really build an operating system for $916?",
    "Do AI Risks Require Extraordinary Government Intervention?",
    "Open-world evaluations for measuring frontier AI capabilities",
    "New Paper: Towards a science of AI agent reliability",
    "AI Won't Automatically Make Legal Services Cheaper",
    "A guide to understanding AI as normal technology",
    "Could AI slow science?",
    "AI as Normal Technology",
    "Is AI progress slowing down?",
    "We Looked at 78 Election Deepfakes. Political Misinformation is not an AI Problem.",
    "Can AI automate computational reproducibility?",
    "Start reading the AI Snake Oil book online",
]

VENUES = [
    "Frontier Model Forum",
    "Partnership on AI",
    "ISO/IEC JTC 1/SC 42",
    "UK AI Security Institute",
    "Council of Europe Committee on Artificial Intelligence",
    "WHO Global Initiative on AI for Health",
    "ITU-T Focus Group on Environmental Efficiency for AI and other "
    "Emerging Technologies (FG-AI4EE)",
    "UN High-Level Advisory Body on AI",
    "ACM Conference on Fairness, Accountability, and Transparency",
]


def test_no_article_from_the_first_live_run_reads_as_a_venue():
    leaked = [
        a for a in ARTICLES
        if looks_like_venue_name(a) or extract_venue_name(a)
    ]
    assert leaked == []


def test_curated_venue_names_pass_the_gate():
    rejected = [v for v in VENUES if not looks_like_venue_name(v)]
    assert rejected == []


def test_gate_keeps_most_of_the_real_dataset():
    """Guards against a heuristic tightening that would blind the pipeline."""
    path = REPO_ROOT / "data" / "agv.csv"
    names = [r["name_en"] for r in csv.DictReader(path.open(encoding="utf-8"))]
    passing = [n for n in names if looks_like_venue_name(n)]
    assert len(passing) / len(names) >= 0.90


def test_headline_test_runs_before_the_org_noun_test():
    """A headline mentioning a lab or an office is still a headline."""
    headline = (
        "New partnership set to see the UK secure access to Ukraine's Avengers AI Labs"
    )
    assert is_headline(headline)
    assert not looks_like_venue_name(headline)


def test_all_caps_lead_is_not_an_interrogative():
    assert not is_headline("WHO Global Initiative on AI for Health")
    assert is_headline("Who governs AI?")


def test_possessive_is_not_a_contraction():
    assert not is_headline("AI's Governance Forum")
    assert is_headline("AI can't govern itself")


def test_extract_prefers_a_named_venue_token():
    assert extract_venue_name("A report from IASEAI on frontier risk") == "IASEAI"


def test_extract_requires_a_proper_noun_run():
    assert extract_venue_name("a national consultation") is None
    assert extract_venue_name("The Institute said") is None
    assert (
        extract_venue_name("The UK AI Safety Institute will lead evaluations.")
        == "UK AI Safety Institute"
    )


def test_unwrap_cdata():
    assert unwrap_cdata("<![CDATA[Could AI slow science?]]>") == "Could AI slow science?"
    assert unwrap_cdata("plain text") == "plain text"
    assert unwrap_cdata("<![CDATA[a]]> and <![CDATA[b]]>") == "a and b"
