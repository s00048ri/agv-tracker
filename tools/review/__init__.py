"""Local review UI for fetcher candidate output (CLAUDE.md §4.7).

A small Flask app that consumes the JSON ``DiffReport`` emitted by
``pipelines.diff`` and lets the maintainer accept / refine / reject /
defer each candidate row before it gets written to canonical CSVs.

Run with::

    python -m tools.review.server path/to/report.json

When the reviewer is done, decisions persist to ``decisions.json`` and
are applied via::

    python -m tools.review.apply_decisions decisions.json [--apply]
"""
