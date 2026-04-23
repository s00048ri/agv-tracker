---
title: Data download
---

# Data download

The canonical dataset is version-controlled in Git; downloads here are snapshots from the latest build.

```js
const agvFile = FileAttachment("./data/agv.json");
const agv = await agvFile.json();
const citation = await FileAttachment("./data/citation.json").json();
```

## Files

**AGV master table** — ${agv.length} venues, all six AGVO classification dimensions plus lifecycle and source metadata.

```js
display(html`<a href="${agvFile.href}" download="agv.json">Download as JSON</a> · <a href="https://github.com/s00048ri/agv-tracker/blob/main/data/agv.csv" target="_blank" rel="noreferrer">View on GitHub</a>`);
```

## Schema

See the [methodology page](/methodology) for the full ontology definition. Core fields in the AGV master table:

| Field | Description |
|---|---|
| `agv_id` | Stable short identifier |
| `name_en` | English name |
| `entity_type` | One of 12 AGVO entity types |
| `governance_modality_primary` | Primary output type |
| `topic_focus_primary` | Primary AI topic |
| `geographic_scope` | Global / transregional / regional / plurilateral / bilateral-plus |
| `lead_actor_primary` | Driving actor type |
| `legal_character` | Soft law / hard law / mixed / n/a |
| `founded_date` | ISO date of founding |
| `current_state` | Active / dormant / absorbed / terminated / succeeded |
| `primary_reference_url` | Authoritative source URL |
| `confidence` | High / medium / low |

## License

Data is released under **CC-BY 4.0**; code under **MIT**. Attribution
should use the citation block below.

## Cite this release

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

The DOI strings above resolve via <https://doi.org/>. When this release
is still pre-Zenodo, the values carry a `PLACEHOLDER` suffix — see
`.github/CI_SETUP.md` §7 for the bootstrap procedure.

## Reuse

If you build on this dataset, please cite the release above and consider
opening a GitHub issue to share what you used it for — it helps
prioritize future additions.
