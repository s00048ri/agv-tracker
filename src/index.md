---
title: AGV Tracker
toc: false
---

```js
const agv = await FileAttachment("data/agv.json").json();
const founding = await FileAttachment("data/founding_rate.json").json();
```

# The proliferation of international AI governance venues

<div class="hero">
<p class="lead">
Since 2015, the population of international organizations, intergovernmental fora, multistakeholder coalitions, and recurring conferences whose mandate addresses the governance of artificial intelligence has grown from a handful to several hundred. This site tracks that population — its founding rates, its institutional types, its topical foci, and its lifecycle dynamics — using a structured ontology and version-controlled data pipeline.
</p>
<p class="lead">
This is a <b>pilot release (v0.1)</b> with a hand-curated seed sample of ${agv.length} venues, intended primarily to validate the AGVO ontology against real-world entities. Future releases will expand the dataset via automated ingestion from OECD.AI, IAPP, UNESCO GAIGO, and direct venue scraping.
</p>
</div>

## Annual founding rate, ${d3.min(founding, d => d.year)}–${d3.max(founding, d => d.year)}

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 360,
  marginLeft: 50,
  x: {label: "Founding year", tickFormat: "d"},
  y: {label: "New venues founded", grid: true},
  marks: [
    Plot.barY(
      founding.filter(d => d.dimension === "total"),
      {x: "year", y: "count", fill: "var(--theme-foreground-focus)", tip: true}
    ),
    Plot.ruleY([0]),
    Plot.text(
      founding.filter(d => d.dimension === "total"),
      {x: "year", y: "count", text: "count", dy: -8, fontSize: 11}
    )
  ]
}))}
</div>

<div class="grid grid-cols-3" style="margin-top: 1.5rem;">
  <div class="card">
    <h2>Active today</h2>
    <span class="big">${agv.filter(d => d.current_state === "active").length}</span>
    <p>of ${agv.length} tracked venues</p>
  </div>
  <div class="card">
    <h2>Founded since 2020</h2>
    <span class="big">${agv.filter(d => d.founded_year >= 2020).length}</span>
    <p>${Math.round(100 * agv.filter(d => d.founded_year >= 2020).length / agv.length)}% of the total</p>
  </div>
  <div class="card">
    <h2>Distinct entity types</h2>
    <span class="big">${new Set(agv.map(d => d.entity_type)).size}</span>
    <p>of 12 defined in AGVO ontology</p>
  </div>
</div>

## By entity type

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 360,
  marginLeft: 200,
  x: {label: "Founded venues (cumulative)"},
  y: {label: null},
  color: {legend: true, scheme: "tableau10"},
  marks: [
    Plot.barX(
      agv,
      Plot.groupY({x: "count"}, {y: "entity_type", fill: "current_state", tip: true, sort: {y: "x", reverse: true}})
    ),
    Plot.ruleX([0])
  ]
}))}
</div>

## By primary topic focus

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 320,
  marginLeft: 180,
  x: {label: "Founded venues"},
  y: {label: null},
  color: {scheme: "blues"},
  marks: [
    Plot.barX(
      agv,
      Plot.groupY({x: "count"}, {y: "topic_focus_primary", fill: "count", tip: true, sort: {y: "x", reverse: true}})
    ),
    Plot.ruleX([0])
  ]
}))}
</div>

---

## About this pilot

The 30 venues in this seed sample were hand-selected to span all twelve `entity_type` values defined in the AGVO ontology, from one-off summits (Asilomar 2017, Bletchley Park 2023) through standing intergovernmental bodies (OECD.AI, UNESCO AI Ethics) to industry consortia (Frontier Model Forum) and academic conferences (FAccT, AIES). The selection is not statistically representative — it is a stress test of the ontology.

See the [methodology](/methodology) for full ontology definitions, inclusion criteria, and data sources. The full venue directory is at [/venues/](/venues/), and raw data downloads are at [/data-download](/data-download).

<style>
.hero { max-width: 720px; margin: 0 0 2rem 0; }
.lead { font-size: 1.05rem; line-height: 1.6; color: var(--theme-foreground-muted); }
.big { font-size: 2.5rem; font-weight: 600; display: block; line-height: 1.2; }
</style>
