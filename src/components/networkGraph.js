// Force-directed AGV relation graph (CLAUDE.md §6.2 section 7 + §9 Task 10).
//
// Nodes: AGVs (from data/network.json #nodes); colour encodes `entity_type`.
// Edges: inter-venue relations from agv_relation.csv; stroke width encodes
// the "strength" of the relation type.
//
// Interactions:
//   drag  — grab a node (pins it via fx/fy during drag, releases on drop)
//   zoom  — wheel / pinch to scale 0.3×…4×; drag empty space to pan
//   hover — native <title> tooltip per node shows name + entity_type + state
//
// Performance: tested with 106 nodes in the v0.3 seed. D3's force layout is
// O(n log n) per tick via the Barnes-Hut quadtree inside forceManyBody, so
// 200+ nodes (§9 Task 10 Done-when #2) runs comfortably on a laptop. Above
// ~500 nodes, tune by capping `forceManyBody().distanceMax(...)` and raising
// `forceCollide(...)` radius to reduce overlap resolution passes.

import * as d3 from "npm:d3";

// 13 AGVO entity_type categories need more than d3.schemeCategory10. Tableau
// palette extended with three additional hues so every type is distinct.
const ENTITY_TYPE_PALETTE = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
  "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
  "#9d174d", "#4d7c0f", "#6b21a8",
];

const ENTITY_TYPES = [
  "igo_initiative",
  "intergov_forum",
  "treaty_body",
  "multistakeholder_coalition",
  "industry_consortium",
  "intl_ngo_thinktank",
  "academic_consortium",
  "standards_body_wg",
  "national_regulator_intl",
  "conference_policy_track",
  "standalone_governance_conference",
  "industry_conference",
  "one_off_summit",
];

// Semantic weighting of relation_type (§3.7). parent_of is strongest; alias-
// like references at the bottom. Values map directly to stroke-width px.
const RELATION_WEIGHTS = {
  parent_of: 2.5,
  succeeds: 2.0,
  absorbed_into: 2.0,
  coordinates_with: 1.2,
  convenes_within: 1.2,
  member_of: 0.9,
  references_principles_of: 0.9,
};

function linkWidth(relationType) {
  return RELATION_WEIGHTS[relationType] ?? 1.0;
}

function linkColor(relationType) {
  // Solid grey for structural relations, a distinct hue for successions.
  if (relationType === "succeeds" || relationType === "absorbed_into") {
    return "#c44e52";
  }
  return "#8e8e8e";
}

// Drag behaviour — standard D3 v7 pattern with simulation re-warm on start.
function drag(simulation) {
  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
  return d3
    .drag()
    .on("start", dragstarted)
    .on("drag", dragged)
    .on("end", dragended);
}

export function networkGraph(
  data,
  {
    width = 800,
    height = 600,
    nodeRadius = 6,
    invalidation,
  } = {},
) {
  const rawNodes = data?.nodes ?? [];
  const rawLinks = data?.links ?? [];

  if (!rawNodes.length) {
    const empty = document.createElement("p");
    empty.innerHTML = "<em>No venues in this view — nothing to graph.</em>";
    return empty;
  }

  // Clone because d3-force mutates x/y/fx/fy and replaces string endpoints
  // with node references.
  const nodes = rawNodes.map((n) => ({ ...n }));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const links = rawLinks
    .filter((l) => nodeById.has(l.source) && nodeById.has(l.target))
    .map((l) => ({ ...l }));

  const color = d3.scaleOrdinal().domain(ENTITY_TYPES).range(ENTITY_TYPE_PALETTE);

  const simulation = d3
    .forceSimulation(nodes)
    .force(
      "link",
      d3
        .forceLink(links)
        .id((d) => d.id)
        .distance(90)
        .strength(0.7),
    )
    .force("charge", d3.forceManyBody().strength(-140).distanceMax(350))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide(nodeRadius + 3));

  const svg = d3
    .create("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", [0, 0, width, height])
    .attr("style", "max-width: 100%; height: auto; font: 12px sans-serif;");

  // Root group that receives the zoom transform.
  const container = svg.append("g");

  // Edges.
  const link = container
    .append("g")
    .attr("stroke-opacity", 0.6)
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("stroke", (d) => linkColor(d.relation_type))
    .attr("stroke-width", (d) => linkWidth(d.relation_type));

  link.append("title").text(
    (d) => `${d.source.id ?? d.source} —[${d.relation_type}]→ ${d.target.id ?? d.target}`,
  );

  // Nodes.
  const node = container
    .append("g")
    .attr("stroke", "#fff")
    .attr("stroke-width", 1.25)
    .selectAll("circle")
    .data(nodes)
    .join("circle")
    .attr("r", nodeRadius)
    .attr("fill", (d) => color(d.entity_type))
    .attr("opacity", (d) => (d.current_state === "terminated" ? 0.35 : 0.9))
    .call(drag(simulation));

  node.append("title").text(
    (d) =>
      `${d.name}\n${d.entity_type} · ${d.current_state}${
        d.convening_frequency ? " · " + d.convening_frequency : ""
      }`,
  );

  // Zoom / pan on the container group.
  svg.call(
    d3
      .zoom()
      .scaleExtent([0.3, 4])
      .on("zoom", (event) => {
        container.attr("transform", event.transform);
      }),
  );

  // Legend (top-left overlay, not inside the zoom group).
  const entityTypesPresent = [
    ...new Set(nodes.map((n) => n.entity_type)),
  ].sort();
  const legend = svg
    .append("g")
    .attr("class", "network-legend")
    .attr("transform", "translate(10, 14)");
  legend
    .append("text")
    .attr("y", 0)
    .attr("font-weight", "bold")
    .text("entity_type");
  entityTypesPresent.forEach((et, i) => {
    const g = legend.append("g").attr("transform", `translate(0, ${14 + i * 14})`);
    g.append("circle").attr("r", 5).attr("fill", color(et));
    g.append("text").attr("x", 10).attr("dy", "0.35em").text(et);
  });

  simulation.on("tick", () => {
    link
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);
    node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
  });

  // Clean up the simulation when the cell is re-evaluated. Observable
  // Framework passes `invalidation` as a Promise in the top-level scope;
  // callers should thread it through this component so we don't leak
  // ticking simulations across hot reloads.
  if (invalidation && typeof invalidation.then === "function") {
    invalidation.then(() => simulation.stop());
  }

  return svg.node();
}
