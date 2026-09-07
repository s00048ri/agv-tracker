"""CLAUDE.md §3.5 stale-detection thresholds exercised at boundary dates."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from pipelines.diff import STALE_THRESHOLDS_MONTHS, Differ

TODAY = date(2026, 4, 23)


def _canonical(*, freq: str, loa: date | str | None,
               agv_id: str = "x") -> dict:
    loa_s = loa.isoformat() if isinstance(loa, date) else (loa or "")
    return {
        "agv_id": agv_id,
        "name_en": "X",
        "entity_type": "igo_initiative",
        "governance_modality_primary": "dialogue_coordination",
        "topic_focus_primary": "ai_general",
        "geographic_scope": "global",
        "lead_actor_primary": "igo_secretariat",
        "legal_character": "soft_law",
        "current_state": "active",
        "convening_frequency": freq,
        "last_observed_activity_date": loa_s,
        "override_policy": "lock_verified_only",
        "human_verified_fields": "",
    }


def _months_ago(n: float) -> date:
    """Return a date whose computed months-since is just *>* n.

    Uses ceil() on the day conversion so the diff's `months_since >= threshold`
    check fires reliably at boundary values.
    """
    return TODAY - timedelta(days=math.ceil(n * 30.44))


# ---- parametrized threshold edges ----

@pytest.mark.parametrize(
    "freq,threshold",
    list(STALE_THRESHOLDS_MONTHS.items()),
)
def test_under_threshold_not_flagged(freq, threshold):
    # 2 months under the threshold — clearly inside the fresh window.
    canon = _canonical(freq=freq, loa=_months_ago(threshold - 2))
    differ = Differ(canonical_rows=[canon], today=TODAY)
    report = differ.diff([])  # no candidates; canonical not 'seen'
    assert report.stale_candidates == [], (
        f"{freq}: AGV {threshold-2}mo old should NOT be stale"
    )


@pytest.mark.parametrize(
    "freq,threshold",
    list(STALE_THRESHOLDS_MONTHS.items()),
)
def test_over_threshold_flagged(freq, threshold):
    # 2 months past the threshold — clearly stale.
    canon = _canonical(freq=freq, loa=_months_ago(threshold + 2))
    differ = Differ(canonical_rows=[canon], today=TODAY)
    report = differ.diff([])
    assert len(report.stale_candidates) == 1
    s = report.stale_candidates[0]
    assert s.convening_frequency == freq
    assert s.threshold_months == threshold
    assert s.months_since_loa >= threshold


@pytest.mark.parametrize(
    "freq,threshold",
    list(STALE_THRESHOLDS_MONTHS.items()),
)
def test_at_threshold_flagged(freq, threshold):
    # Exactly at the threshold — conservative: flag (reviewer will decide).
    canon = _canonical(freq=freq, loa=_months_ago(threshold))
    differ = Differ(canonical_rows=[canon], today=TODAY)
    report = differ.diff([])
    assert len(report.stale_candidates) == 1


# ---- one_off exclusion (binding rule from §3.5) ----

def test_one_off_excluded_regardless_of_loa_age():
    for years_ago in (1, 3, 10):
        canon = _canonical(
            freq="one_off",
            loa=date(TODAY.year - years_ago, TODAY.month, TODAY.day),
        )
        differ = Differ(canonical_rows=[canon], today=TODAY)
        report = differ.diff([])
        assert report.stale_candidates == [], (
            f"one_off with LOA {years_ago} years old must NEVER be flagged"
        )


# ---- edge cases ----

def test_missing_loa_not_flagged():
    canon = _canonical(freq="continuous", loa="")
    report = Differ(canonical_rows=[canon], today=TODAY).diff([])
    assert report.stale_candidates == []


def test_malformed_loa_not_flagged():
    canon = _canonical(freq="continuous", loa="not-a-date")
    report = Differ(canonical_rows=[canon], today=TODAY).diff([])
    assert report.stale_candidates == []


def test_unknown_frequency_not_flagged():
    """Unknown convening_frequency values are skipped conservatively."""
    canon = _canonical(freq="decadal", loa=_months_ago(120))
    report = Differ(canonical_rows=[canon], today=TODAY).diff([])
    assert report.stale_candidates == []


def test_present_in_candidate_set_not_flagged():
    """If a fetcher surfaces the AGV this run it is 'seen', not stale."""
    canon = _canonical(freq="continuous", loa=_months_ago(24))  # well past 6mo
    candidate = {
        "agv_row": {"agv_id": canon["agv_id"], "name_en": "X"},
        "evidence_rows": [],
        "provenance": {},
    }
    report = Differ(canonical_rows=[canon], today=TODAY).diff([candidate])
    assert report.stale_candidates == []


def test_stale_reports_months_since_and_threshold():
    canon = _canonical(freq="annual", loa=_months_ago(20))  # threshold 18
    report = Differ(canonical_rows=[canon], today=TODAY).diff([])
    assert len(report.stale_candidates) == 1
    s = report.stale_candidates[0]
    assert s.threshold_months == 18
    assert 19 < s.months_since_loa < 21


def test_biennial_threshold_30_months():
    # Just under 30 months → not stale
    canon = _canonical(freq="biennial", loa=_months_ago(29), agv_id="b1")
    # Just over 30 months → stale
    canon2 = _canonical(freq="biennial", loa=_months_ago(31), agv_id="b2")
    report = Differ(canonical_rows=[canon, canon2], today=TODAY).diff([])
    staleness = {s.agv_id for s in report.stale_candidates}
    assert staleness == {"b2"}


def test_multiple_frequencies_coexist_correctly():
    rows = [
        _canonical(freq="continuous", loa=_months_ago(8), agv_id="c1"),  # stale (>6)
        _canonical(freq="continuous", loa=_months_ago(3), agv_id="c2"),  # fresh
        _canonical(freq="annual", loa=_months_ago(20), agv_id="a1"),      # stale (>18)
        _canonical(freq="annual", loa=_months_ago(10), agv_id="a2"),      # fresh
        _canonical(freq="ad_hoc", loa=_months_ago(26), agv_id="h1"),      # stale (>24)
        _canonical(freq="one_off", loa=_months_ago(120), agv_id="o1"),    # excluded
    ]
    report = Differ(canonical_rows=rows, today=TODAY).diff([])
    flagged = {s.agv_id for s in report.stale_candidates}
    assert flagged == {"c1", "a1", "h1"}
