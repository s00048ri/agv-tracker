---
title: Methodology
---

# Methodology

## What is an AI Governance Venue (AGV)?

An **AGV** is any organized forum, body, initiative, coalition, or recurring convening whose mandate includes — as a primary or substantial secondary purpose — the governance, oversight, coordination, or norm-setting of AI technologies, their development, deployment, or societal impact.

The term *venue* deliberately covers continuous organizations (e.g., OECD.AI), recurring fora (e.g., AI Action Summits), one-off convenings that produced durable outputs (e.g., Asilomar 2017, Bletchley Park 2023), and workstreams within larger organizations that have a distinct AI mandate.

## Inclusion and exclusion

Excluded from the dataset:
- Purely technical AI conferences without any policy or governance track.
- National-only entities with no international participation or extraterritorial reach (with the exception of national AISIs, included for their explicit role in the international AISI network).
- Corporate internal AI ethics teams without external coordination function.

## Classification dimensions

Each venue is classified across six orthogonal dimensions defined in the AGVO ontology v0.1:

1. **Entity type** — twelve values from `igo_initiative` to `one_off_summit`.
2. **Governance modality** — what the venue produces: declarations, binding instruments, technical standards, evaluations, capacity-building, research, dialogue, regulation.
3. **Topic focus** — what aspect of AI: general, safety/frontier, ethics/rights, privacy/data, generative AI, agentic AI, or domain-specific.
4. **Geographic scope** — global, transregional, regional, plurilateral, or bilateral-plus.
5. **Lead actor type** — who drives it: IGO secretariat, state government, industry, academia, civil society, or hybrid multistakeholder.
6. **Legal character** — soft law, hard law, mixed, or n/a.

A separate **lifecycle model** tracks state transitions: `announced` → `active` → optionally `dormant`, `absorbed`, `terminated`, or `succeeded`.

## Data sources

Current sources for the seed sample:
- Direct venue homepages and founding documents.
- OECD.AI Policy Navigator.
- UNESCO Global AI Ethics and Governance Observatory.
- IAPP Global AI Law and Policy Tracker.
- Berkman Klein "Principled AI" mapping (historical).

Future automated ingestion is planned via dedicated fetchers per source.

## Update cadence

Monthly. The pipeline runs on the first of each month, fetches changes from upstream sources, and opens a Pull Request listing candidate additions and updates. Each change is human-reviewed before being merged into the canonical dataset.

## Limitations

This is a **v0.1 pilot release** with a hand-curated seed sample of 30 venues. The selection is not statistically representative; it is a stress test of the ontology. Coverage gaps that will be addressed in future releases include:

- Industry consortia formed in 2024–2025 (only the most prominent are included here).
- Regional bodies in Africa, Latin America, ASEAN beyond their largest convenings.
- Standards bodies beyond ISO/IEC SC 42 (IEEE working groups, ITU AI focus groups).
- Many academic conference policy tracks.

## Citation

Until a stable release with a Zenodo DOI is published, please cite this site as: *AGV Tracker v0.1 (pilot), accessed [date], [URL]*.

## Source code

Repository: <https://github.com/your-handle/agv-tracker> (replace with actual URL on deployment).
