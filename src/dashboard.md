---
title: Dashboard
toc: true
---

```js
import {
  filterByView,
  VIEW_VALUES,
  VIEW_LABELS,
  VIEW_DESCRIPTIONS,
  renderInlineMarkdown,
} from "./components/viewToggle.js";
import {networkGraph} from "./components/networkGraph.js";
const agv = await FileAttachment("./data/agv.json").json();
const network = await FileAttachment("./data/network.json").json();
```

# Analytical dashboard

Three default views filter the AGV population around different analytical
questions (CLAUDE.md §6.2):
**continuous bodies only** (institution-building signal),
**recurring convenings only** (annual/biennial conferences and summits),
and **one-off included** (full dataset).
Switching the toggle re-renders every chart below; the **explanatory
paragraph directly under the toggle tells you what you should and should
not read into the current view**.

```js
const selectedView = view(Inputs.radio(VIEW_VALUES, {
  label: "View",
  value: "one_off_included",
  format: (v) => VIEW_LABELS[v],
}));
```

```js
const agvFiltered = filterByView(agv, selectedView);
```

<div class="note" style="
  padding: 0.75rem 1rem;
  margin: 0.75rem 0 1.25rem;
  border-left: 4px solid var(--theme-foreground-focus, #3b82f6);
  background: var(--theme-background-alt, #f6f8fa);
  border-radius: 4px;
">
${renderInlineMarkdown(VIEW_DESCRIPTIONS[selectedView])}<br><br>
<small><strong>Current view contains ${agvFiltered.length} venue${agvFiltered.length === 1 ? "" : "s"}</strong> out of ${agv.length} in the full dataset.</small>
</div>

## 1. Cumulative active population over time

How the live stock of AGVs in the current view has grown.
A venue is "alive at year Y" if it was founded on or before Y AND is not
`current_state = terminated`. `absorbed` and `succeeded` venues are
counted as alive because their work continues inside their successor.

```js
const cumulative = (() => {
  const minY = d3.min(agvFiltered, (d) => d.founded_year);
  const maxY = Math.max(new Date().getUTCFullYear(), d3.max(agvFiltered, (d) => d.founded_year) ?? 2015);
  if (minY == null) return [];
  const rows = [];
  for (let year = minY; year <= maxY; year++) {
    const alive = agvFiltered.filter(
      (d) => d.founded_year != null
        && d.founded_year <= year
        && d.current_state !== "terminated",
    ).length;
    rows.push({year, alive});
  }
  return rows;
})();
```

<div class="card">
${cumulative.length
  ? resize((width) => Plot.plot({
      width,
      height: 320,
      marginLeft: 55,
      x: {label: "Year", tickFormat: "d"},
      y: {label: "Venues alive", grid: true},
      marks: [
        Plot.areaY(cumulative, {x: "year", y: "alive", fillOpacity: 0.18, fill: "var(--theme-foreground-focus)"}),
        Plot.lineY(cumulative, {x: "year", y: "alive", stroke: "var(--theme-foreground-focus)", strokeWidth: 2}),
        Plot.dot(cumulative, {x: "year", y: "alive", r: 3, fill: "var(--theme-foreground-focus)", tip: true}),
        Plot.ruleY([0]),
      ],
    }))
  : html`<p><em>No venues in this view.</em></p>`}
</div>

## 2. Founding rate by entity type (small multiples)

Annual foundings, faceted by `entity_type`. Empty facets indicate a type
that is filtered out under the current view (e.g. `one_off_summit` is
absent from the `continuous` view).

```js
const foundingByType = (() => {
  const m = new Map();
  for (const d of agvFiltered) {
    if (d.founded_year == null) continue;
    const key = `${d.entity_type}::${d.founded_year}`;
    m.set(key, (m.get(key) ?? 0) + 1);
  }
  const out = [];
  for (const [key, count] of m) {
    const [entity_type, yr] = key.split("::");
    out.push({entity_type, year: +yr, count});
  }
  return out;
})();
```

<div class="card">
${foundingByType.length
  ? resize((width) => Plot.plot({
      width,
      height: Math.max(320, 38 * new Set(foundingByType.map((d) => d.entity_type)).size),
      marginLeft: 55,
      x: {label: "Year", tickFormat: "d"},
      y: {label: "New venues", grid: true, ticks: 3},
      fy: {label: null},
      marks: [
        Plot.barY(foundingByType, {x: "year", y: "count", fy: "entity_type", fill: "var(--theme-foreground-focus)", tip: true}),
        Plot.ruleY([0]),
      ],
    }))
  : html`<p><em>No foundings in this view.</em></p>`}
</div>

## 3. Founding rate by topic focus (small multiples)

Annual foundings, faceted by `topic_focus_primary`. Inflection points on
specific topical rows often correspond to discrete external triggers
(ChatGPT launch for `genai_content`, Bletchley Park for `safety_frontier`).

```js
const foundingByTopic = (() => {
  const m = new Map();
  for (const d of agvFiltered) {
    if (d.founded_year == null) continue;
    const key = `${d.topic_focus_primary}::${d.founded_year}`;
    m.set(key, (m.get(key) ?? 0) + 1);
  }
  const out = [];
  for (const [key, count] of m) {
    const [topic_focus_primary, yr] = key.split("::");
    out.push({topic_focus_primary, year: +yr, count});
  }
  return out;
})();
```

<div class="card">
${foundingByTopic.length
  ? resize((width) => Plot.plot({
      width,
      height: Math.max(320, 38 * new Set(foundingByTopic.map((d) => d.topic_focus_primary)).size),
      marginLeft: 55,
      x: {label: "Year", tickFormat: "d"},
      y: {label: "New venues", grid: true, ticks: 3},
      fy: {label: null},
      marks: [
        Plot.barY(foundingByTopic, {x: "year", y: "count", fy: "topic_focus_primary", fill: "var(--theme-foreground-focus)", tip: true}),
        Plot.ruleY([0]),
      ],
    }))
  : html`<p><em>No foundings in this view.</em></p>`}
</div>

## 4. Lifecycle state distribution

Distribution of `current_state` across the venues in the current view.
The presence of `terminated` / `succeeded` / `absorbed` buckets at the
bottom is the population-ecology signature the dataset is built to
capture.

<div class="card">
${agvFiltered.length
  ? resize((width) => Plot.plot({
      width,
      height: 240,
      marginLeft: 110,
      x: {label: "Number of venues", grid: true},
      y: {label: null},
      color: {scheme: "set2"},
      marks: [
        Plot.barX(
          agvFiltered,
          Plot.groupY({x: "count"}, {y: "current_state", fill: "current_state", tip: true, sort: {y: "x", reverse: true}}),
        ),
        Plot.ruleX([0]),
      ],
    }))
  : html`<p><em>No venues in this view.</em></p>`}
</div>

## 5. Topic × entity-type heatmap

Where the governance effort concentrates. Clusters of cells pick out the
current hot corners of the landscape; empty rows/columns show the
structural gaps worth filling (CLAUDE.md §5.4 coverage matrix is the
complementary metadata view).

<div class="card">
${agvFiltered.length
  ? resize((width) => Plot.plot({
      width,
      height: 420,
      marginLeft: 220,
      marginBottom: 90,
      x: {label: null, tickRotate: -30},
      y: {label: null},
      color: {scheme: "blues", legend: true, label: "Venues"},
      marks: [
        Plot.cell(
          agvFiltered,
          Plot.group({fill: "count"}, {x: "topic_focus_primary", y: "entity_type", tip: true}),
        ),
      ],
    }))
  : html`<p><em>No venues in this view.</em></p>`}
</div>

## 6. Geographic scope and lead actor

Two complementary breakdowns of *who* and *where*: the jurisdictional
reach (left) and the driving institutional actor (right).

<div class="grid grid-cols-2">
  <div class="card">

### By geographic scope

${agvFiltered.length
  ? resize((width) => Plot.plot({
      width,
      height: 260,
      marginLeft: 100,
      x: {label: "Venues"},
      y: {label: null},
      marks: [
        Plot.barX(
          agvFiltered,
          Plot.groupY({x: "count"}, {y: "geographic_scope", fill: "var(--theme-foreground-focus)", tip: true, sort: {y: "x", reverse: true}}),
        ),
        Plot.ruleX([0]),
      ],
    }))
  : html`<p><em>No venues in this view.</em></p>`}

  </div>
  <div class="card">

### By lead actor

${agvFiltered.length
  ? resize((width) => Plot.plot({
      width,
      height: 260,
      marginLeft: 115,
      x: {label: "Venues"},
      y: {label: null},
      marks: [
        Plot.barX(
          agvFiltered,
          Plot.groupY({x: "count"}, {y: "lead_actor_primary", fill: "var(--theme-foreground-focus)", tip: true, sort: {y: "x", reverse: true}}),
        ),
        Plot.ruleX([0]),
      ],
    }))
  : html`<p><em>No venues in this view.</em></p>`}

  </div>
</div>

## 7. Relations network

Force-directed graph of the `agv_relation.csv` edges (succeeds,
absorbed_into, parent_of, coordinates_with, convenes_within, member_of,
references_principles_of). Node colour encodes `entity_type`; edge
stroke width encodes relation strength (hierarchy and succession are
drawn thicker than referencing relations). Terminated venues are drawn
semi-transparent.

The graph respects the current view toggle: nodes are restricted to the
filtered set, and edges are kept only when **both** endpoints are visible.

**Interactions.** Drag a node to reposition it (release to let the force
re-settle). Scroll / pinch to zoom (0.3× … 4×); drag empty canvas to pan.
Hover a node or edge for a native tooltip.

**Edge density note.** The v0.3 seed ships only ${network.links.length}
relations across ${network.nodes.length} venues; most nodes are therefore
isolated dots. This is expected — relation data will densify as
v0.4 backfills `member_of` / `parent_of` / `coordinates_with` edges
(CLAUDE.md §3.7).

```js
const filteredNodeIds = new Set(agvFiltered.map((d) => d.agv_id));
const filteredNetwork = {
  nodes: network.nodes.filter((n) => filteredNodeIds.has(n.id)),
  links: network.links.filter((l) => {
    const s = typeof l.source === "string" ? l.source : l.source.id;
    const t = typeof l.target === "string" ? l.target : l.target.id;
    return filteredNodeIds.has(s) && filteredNodeIds.has(t);
  }),
};
```

<div class="card">
${resize((width) => networkGraph(filteredNetwork, {
  width,
  height: Math.min(620, Math.max(360, width * 0.62)),
  invalidation,
}))}
</div>

<small><strong>${filteredNetwork.nodes.length}</strong> nodes · <strong>${filteredNetwork.links.length}</strong> edges in current view.</small>

---

*All charts above re-render on toggle change.* For a row-level inventory,
see the [Venues directory](./venues/). For the per-AGV evidence trail,
open any venue's detail page from that listing.
