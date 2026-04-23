# AGV Tracker — Runtime Changelog

Runtime data/decisions accepted into the repository. Spec revisions are tracked
in `CLAUDE.md §0`.

## 2026-04-23

- **data**: migrated 30-AGV seed from v0.1 → v0.3 schema (Task 2). Split into
  `agv.csv` + `agv_relation.csv` (3) + `agv_evidence.csv` (120) +
  `agv_name_history.csv` (2) + `agv_lifecycle.csv` (35); reclassified FAccT and
  AIES as `standalone_governance_conference`; renamed UK AISI to "UK AI Security
  Institute" with former name preserved; all 30 rows marked
  `human_verified_fields=entity_type,founded_date,current_state,legal_character`
  with `override_policy=lock_verified_only`.
- **pipelines**: OECD.AI Policy Navigator discovery fetcher online (Task 4).
  `BaseFetcher` ABC + `RawVenue` dataclass + `fetch_html_with_fallback`
  (static HTTP → Playwright) + throttle + robots.txt + disk cache;
  `OECDFetcher` CLI returns 60 records from the shipped 60-card fixture
  (`source_role=discovery`). Live strategy (static vs Playwright) TBD on
  first online run — see `pipelines/fetchers/oecd_ai.py` docstring.
  pyproject.toml adds deps (httpx, bs4, pyyaml) + `[scraping]` / `[dev]`
  extras. pytest: 54/54 green (41 existing + 13 new fetcher tests).
- **data**: expanded seed dataset to 106 AGVs (Task 3). +76 new rows across
  all 13 entity_types — every type now has ≥4 (min industry_conference=4;
  academic_consortium 0→5; treaty_body 1→5; standards_body_wg 1→11;
  national_regulator_intl 3→13). Regional coverage added: AF (AU Continental
  AI Strategy), LAC (IDB fAIr LAC), ASEAN (ASEAN AI Guide), Pacific (APRU AI).
  +304 evidence rows (all `human_verification` / reviewer=s00048ri),
  +81 lifecycle rows (76 initial + 5 later transitions: CAHAI→succeeded,
  UN HLP→terminated, REAIM Hague→succeeded, ITU FG-AI4H/AI4EE→terminated),
  +2 relations (coe_ai_convention succeeds cahai; reaim_seoul_2024 succeeds
  reaim_hague_2023). Release gate PASS.
