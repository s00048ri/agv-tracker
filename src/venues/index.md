---
title: Venues
---

```js
const agv = await FileAttachment("data/agv.json").json();
```

# Venues directory

${agv.length} venues in the current dataset. Click any column header to sort.

```js
const search = view(Inputs.search(agv, {placeholder: "Search by name, type, topic, or notes…"}));
```

```js
view(Inputs.table(search, {
  columns: [
    "name_en",
    "entity_type",
    "topic_focus_primary",
    "geographic_scope",
    "founded_year",
    "current_state",
    "primary_reference_url"
  ],
  header: {
    name_en: "Name",
    entity_type: "Type",
    topic_focus_primary: "Topic",
    geographic_scope: "Scope",
    founded_year: "Founded",
    current_state: "State",
    primary_reference_url: "Source"
  },
  format: {
    primary_reference_url: (url) => htl.html`<a href="${url}" target="_blank" rel="noreferrer">link</a>`,
    founded_year: (y) => y
  },
  sort: "founded_year",
  reverse: true,
  width: {
    name_en: 280,
    entity_type: 180,
    topic_focus_primary: 160
  }
}))
```
