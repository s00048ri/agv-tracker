---
title: Data download
---

# Data download

The canonical dataset is version-controlled in Git; downloads here are snapshots from the latest build.

```js
const agv = await FileAttachment("data/agv.json").json();
```

## Files

- **AGV master table** — ${agv.length} venues, all six AGVO classification dimensions plus lifecycle and source metadata.

  [Download as JSON](data/agv.json) · [View on GitHub](https://github.com/your-handle/agv-tracker/blob/main/data/agv.csv)

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

Data is released under CC-BY 4.0; code under MIT.

## Reuse

If you build on this dataset, please cite (see [methodology](/methodology)) and consider opening a GitHub issue to share what you used it for — it helps prioritize future additions.
