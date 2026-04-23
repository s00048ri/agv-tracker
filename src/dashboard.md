---
title: Dashboard
---

```js
const agv = await FileAttachment("data/agv.json").json();
const founding = await FileAttachment("data/founding_rate.json").json();
```

# Analytical dashboard

## Cumulative active population

```js
const cumulative = (() => {
  const years = d3.range(d3.min(agv, d => d.founded_year), 2027);
  return years.map(year => ({
    year,
    cumulative: agv.filter(d => d.founded_year <= year).length
  }));
})();
```

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 320,
  marginLeft: 50,
  x: {label: "Year", tickFormat: "d"},
  y: {label: "Cumulative venues founded", grid: true},
  marks: [
    Plot.areaY(cumulative, {x: "year", y: "cumulative", fillOpacity: 0.2, fill: "var(--theme-foreground-focus)"}),
    Plot.lineY(cumulative, {x: "year", y: "cumulative", stroke: "var(--theme-foreground-focus)", strokeWidth: 2}),
    Plot.dot(cumulative, {x: "year", y: "cumulative", r: 3, fill: "var(--theme-foreground-focus)"}),
    Plot.ruleY([0])
  ]
}))}
</div>

## Founding rate by entity type (small multiples)

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 360,
  marginLeft: 50,
  x: {label: "Year", tickFormat: "d"},
  y: {label: "New venues", grid: true, ticks: 3},
  fy: {label: null},
  marks: [
    Plot.barY(
      founding.filter(d => d.dimension === "entity_type"),
      {x: "year", y: "count", fy: "value", fill: "var(--theme-foreground-focus)", tip: true}
    ),
    Plot.ruleY([0])
  ]
}))}
</div>

## Lifecycle state of all tracked venues

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 220,
  marginLeft: 100,
  x: {label: "Number of venues", grid: true},
  y: {label: null},
  color: {scheme: "set2"},
  marks: [
    Plot.barX(
      agv,
      Plot.groupY({x: "count"}, {y: "current_state", fill: "current_state", tip: true, sort: {y: "x", reverse: true}})
    ),
    Plot.ruleX([0])
  ]
}))}
</div>

## Topic focus × entity type heatmap

<div class="card">
${resize((width) => Plot.plot({
  width,
  height: 380,
  marginLeft: 200,
  marginBottom: 80,
  x: {label: null, tickRotate: -30},
  y: {label: null},
  color: {scheme: "blues", legend: true, label: "Count"},
  marks: [
    Plot.cell(
      agv,
      Plot.group({fill: "count"}, {x: "topic_focus_primary", y: "entity_type", tip: true})
    )
  ]
}))}
</div>

## Geographic scope distribution

<div class="grid grid-cols-2">
  <div class="card">

### By scope

${resize((width) => Plot.plot({
  width,
  height: 240,
  marginLeft: 100,
  x: {label: "Venues"},
  y: {label: null},
  marks: [
    Plot.barX(
      agv,
      Plot.groupY({x: "count"}, {y: "geographic_scope", fill: "var(--theme-foreground-focus)", tip: true, sort: {y: "x", reverse: true}})
    ),
    Plot.ruleX([0])
  ]
}))}

  </div>
  <div class="card">

### By lead actor type

${resize((width) => Plot.plot({
  width,
  height: 240,
  marginLeft: 110,
  x: {label: "Venues"},
  y: {label: null},
  marks: [
    Plot.barX(
      agv,
      Plot.groupY({x: "count"}, {y: "lead_actor_primary", fill: "var(--theme-foreground-focus)", tip: true, sort: {y: "x", reverse: true}})
    ),
    Plot.ruleX([0])
  ]
}))}

  </div>
</div>
