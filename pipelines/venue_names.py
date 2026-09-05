"""Telling venue names apart from news headlines (CLAUDE.md §3.1, §5.1).

Discovery fetchers surface whatever a listing page or RSS feed offers, and
for news-shaped sources (Tech Policy Press, AI Snake Oil, gov.uk press
releases) that is an *article title*, not a venue name. CLAUDE.md §3.1
admits venues, not coverage of venues: "記事 ≠ venue" was applied by hand
during the batch-2 curation, and this module makes the same judgement
mechanical so `pipelines/normalize.py` can apply it before a candidate row
is ever proposed.

The first live monthly-fetch run (2026-09-05) proposed 17 new venues, all
17 of which were articles — the calibration set for the heuristics below.

Two questions, asked in this order:

1. ``is_headline(name)`` — does this read as a sentence about the world?
   Asked *first*, because a headline may well contain an organisational
   noun ("...access to Ukraine's Avengers AI Labs") and would otherwise
   pass step 2 on that accident.
2. ``looks_like_venue_name(name)`` — does what remains name an organisation?
   Either an organisational noun ("... Institute", "... Working Group"),
   a bare acronym (FAccT, IASEAI), or a known named venue.

When a record fails both, ``extract_venue_name`` gets one more chance to
pull a *named* venue out of the article's own text, which is the only
legitimate contribution a news item can make to the dataset.
"""
from __future__ import annotations

import re

# Named venues the fetchers already watch for by name (mirrors the
# INCLUDE_REGEX token list in pipelines/fetchers/tech_policy_press.py).
# These have no organisational noun in their name, so they need an
# explicit accept-list.
NAMED_VENUE_TOKENS = (
    "IASEAI",
    "AI Safety Connect",
    "AI Safety Asia",
    "AISA",
    "FAccT",
    "AIES",
    "EAAMO",
    "FORC",
)

# Nouns that name an organised body rather than an event in the news.
ORG_NOUNS = (
    "Institute", "Institutes",
    "Forum", "Fora", "Forums",
    "Council", "Committee", "Subcommittee",
    "Coalition", "Alliance", "Partnership", "Network", "Consortium",
    "Working Group", "Task Force", "Taskforce", "Expert Group",
    "Observatory", "Summit", "Conference", "Workshop", "Symposium",
    "Association", "Society", "Assembly", "Roundtable", "Dialogue",
    "Initiative", "Programme", "Program", "Process",
    "Board", "Panel", "Commission", "Secretariat", "Bureau",
    "Centre", "Center", "Agency", "Authority", "Office",
    "Organisation", "Organization", "Foundation",
    "Body", "Commissioner", "Administration", "Directorate",
    "Ministry", "Department",
)

_ORG_NOUN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in ORG_NOUNS) + r")\b",
)
_NAMED_TOKEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in NAMED_VENUE_TOKENS) + r")\b",
)
# A bare acronym: 3+ capitals, optionally mixed like FAccT or ISO/IEC.
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Za-z]*[A-Z][A-Za-z]*[A-Z][A-Za-z0-9/]*\b")

# Auxiliary and reporting verbs that mark a sentence rather than a name.
_HEADLINE_VERB_RE = re.compile(
    r"(?i)\b(?:is|are|was|were|has|have|had|does|do|did|will|shall|can|could|"
    r"should|would|may|might|announces?|announced|launches?|launched|unveils?|"
    r"unveiled|publishes?|published|says?|said|warns?|warned|urges?|urged|"
    r"calls? for|set to|agrees?|agreed|signs?|signed|backs?|backed|"
    r"replaced|requires?|require)\b",
)
# Interrogative or auxiliary lead-in: "Why AI hasn't...", "Could AI slow science?"
# Case-insensitive but never against an all-caps token, so the WHO in
# "WHO Global Initiative on AI for Health" is read as the agency, not "who".
_QUESTION_LEAD_RE = re.compile(
    r"(?i)^(?:how|why|what|when|where|who|whose|which|is|are|do|does|did|can|"
    r"could|should|would|will|has|have|was|were)\b",
)
_ALLCAPS_LEAD_RE = re.compile(r"^[A-Z]{2,}\b")
# Verb contractions ("can't", "won't"), but not the possessive "AI's".
_CONTRACTION_RE = re.compile(r"(?i)\w['’](?:t|ll|ve|re|d)\b")
# A sentence boundary inside the string: ". " followed by a capital.
_MULTI_SENTENCE_RE = re.compile(r"[.!?]\s+[A-Z0-9]")

# Real venue names run long ("ITU-T Focus Group on Environmental Efficiency
# for AI and other Emerging Technologies (FG-AI4EE)" is 13 words), so the cap
# sits above them rather than at a typical headline length.
MAX_VENUE_NAME_WORDS = 16

_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)


def unwrap_cdata(text: str) -> str:
    """Replace ``<![CDATA[x]]>`` with ``x``.

    BeautifulSoup's html.parser keeps the CDATA markers as literal text, so
    an RSS ``<title><![CDATA[...]]></title>`` reaches the normalizer with the
    markers embedded in the venue name (and hence in the slugged agv_id).
    """
    return _CDATA_RE.sub(r"\1", text)


def is_headline(name: str) -> bool:
    """True when `name` reads as a sentence about events, not as a name."""
    s = name.strip()
    if not s:
        return False
    if len(s.split()) > MAX_VENUE_NAME_WORDS:
        return True
    if s.endswith(("?", "!")):
        return True
    if _MULTI_SENTENCE_RE.search(s):
        return True
    if _CONTRACTION_RE.search(s):
        return True
    if _QUESTION_LEAD_RE.match(s) and not _ALLCAPS_LEAD_RE.match(s):
        return True
    return bool(_HEADLINE_VERB_RE.search(s))


def looks_like_venue_name(name: str) -> bool:
    """True when `name` plausibly names an organised body.

    Headlines are rejected before the organisational-noun test, so a
    headline that happens to mention a lab or an office does not pass.
    """
    s = name.strip()
    if not s or is_headline(s):
        return False
    if _NAMED_TOKEN_RE.search(s):
        return True
    if _ORG_NOUN_RE.search(s):
        return True
    return bool(_ACRONYM_RE.search(s))


def extract_venue_name(text: str) -> str | None:
    """Pull a named venue out of free text, or None.

    Requires a run of capitalised words ending in an organisational noun —
    "the UK AI Safety Institute" yields "UK AI Safety Institute". A bare
    organisational noun with no proper-noun run ("a national consultation")
    yields nothing, which is the intended outcome: an article that names no
    venue contributes no candidate.
    """
    if not text:
        return None

    named = _NAMED_TOKEN_RE.search(text)
    if named:
        return named.group(0)

    pattern = re.compile(
        r"\b((?:[A-Z][\w&.\-]*\s+(?:for\s+|of\s+|on\s+|and\s+|the\s+)?){1,5}"
        r"(?:" + "|".join(re.escape(n) for n in ORG_NOUNS) + r"))\b",
    )
    m = pattern.search(text)
    if not m:
        return None
    candidate = " ".join(m.group(1).split())
    # "The UK AI Safety Institute" -> "UK AI Safety Institute": the article is
    # part of the sentence, not of the name.
    candidate = re.sub(r"^(?:The|A|An)\s+", "", candidate)
    # Guard against swallowing a leading sentence word ("The Institute").
    if len(candidate.split()) < 2:
        return None
    return candidate
