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

## Cite this release

```js
const citation = await FileAttachment("./data/citation.json").json();
const isPlaceholder = citation.doi.includes("PLACEHOLDER");
```

${isPlaceholder
  ? html`<em>A Zenodo DOI has not yet been minted for this release. The block
below shows the citation layout that will be populated once the first
tagged release lands on Zenodo (see <code>.github/CI_SETUP.md</code> §7).</em>`
  : html`This release carries a citable Zenodo DOI. Please cite as below.`}

```js
display(html`
  <div class="cite-release" style="
    padding: 0.9rem 1.1rem;
    margin: 0.75rem 0 1.25rem;
    border-left: 4px solid var(--theme-foreground-focus, #3b82f6);
    background: var(--theme-background-alt, #f6f8fa);
    border-radius: 4px;
  ">
    <div><strong>Version ${citation.version}</strong> · released ${citation.released_at}</div>
    <div>Version DOI:
      <a href="${citation.doi_url}" target="_blank" rel="noreferrer"><code>${citation.doi}</code></a>
    </div>
    <div>Concept DOI (always latest):
      <a href="${citation.concept_doi_url}" target="_blank" rel="noreferrer"><code>${citation.concept_doi}</code></a>
    </div>
    <hr>
    <div><strong>Preferred citation</strong></div>
    <div style="margin: 0.35rem 0 0.75rem; font-family: serif;">${citation.citation_text}</div>
    <div><strong>BibTeX</strong></div>
    <pre style="white-space: pre-wrap; font-size: 0.88em;">${citation.bibtex}</pre>
  </div>
`);
```

## Source code

Repository: <https://github.com/s00048ri/agv-tracker>. See `CITATION.cff`
at the repo root for the GitHub-native citation widget, and `.zenodo.json`
for the Zenodo deposit metadata.
