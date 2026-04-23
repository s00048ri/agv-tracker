// Sensitivity-view toggle for the analytical dashboard (CLAUDE.md §6.2).
//
// Three defensible "shapes" of the AGV population, each emphasising a
// different analytical question:
//
//   continuous      — institution-building view; only venues that are
//                     expected to exist continuously between meetings.
//   recurring       — recurring-convening view; only annual/biennial
//                     conferences, workshops, and summits.
//   one_off_included — full dataset, including one-off summits.
//
// This module exports the filter constants + a `filterByView` helper +
// `VIEW_VALUES`, `VIEW_LABELS`, and `VIEW_DESCRIPTIONS` tables so that
// `dashboard.md` can drive its `Inputs.radio` from a single source of truth.

// AGVO §3.3 entity_types that denote continuous institutional bodies.
// Source: CLAUDE.md §6.2 view 1.
export const CONTINUOUS_ENTITY_TYPES = new Set([
  "igo_initiative",
  "treaty_body",
  "multistakeholder_coalition",
  "industry_consortium",
  "intl_ngo_thinktank",
  "academic_consortium",
  "standards_body_wg",
  "national_regulator_intl",
]);

// Convening frequencies that qualify a venue as a "recurring convening".
// Source: CLAUDE.md §6.2 view 2.
export const RECURRING_FREQUENCIES = new Set(["annual", "biennial"]);

export const VIEW_VALUES = ["continuous", "recurring", "one_off_included"];

export const VIEW_LABELS = {
  continuous: "Continuous bodies only",
  recurring: "Recurring convenings only",
  one_off_included: "One-off summits included (full dataset)",
};

// One paragraph per view explaining the analytical purpose. Rendered
// verbatim above the chart set via `${VIEW_DESCRIPTIONS[view]}`.
export const VIEW_DESCRIPTIONS = {
  continuous: (
    "**Institution-building view.** Restricts the population to venues " +
    "that exist between meetings — intergovernmental initiatives, treaty " +
    "bodies, multistakeholder coalitions, industry consortia, think tanks, " +
    "academic consortia, standards working groups, and national safety " +
    "institutes. This is the cleanest signal of the AI-governance ecosystem " +
    "as an *organizational* population; it strips out the conference + summit " +
    "cadence that can otherwise dominate annual counts."
  ),
  recurring: (
    "**Recurring-convening view.** Keeps only venues whose `convening_frequency` " +
    "is annual or biennial — standalone governance conferences (FAccT, AIES, " +
    "EAAMO, ICAIL …), policy tracks inside larger conferences, industry " +
    "conferences, and repeating summit series. This reveals the cadence of " +
    "peer-reviewed and industry-driven deliberation, which evolves differently " +
    "from the institutional baseline."
  ),
  one_off_included: (
    "**Full dataset.** Everything, including one-off summits (Asilomar 2017, " +
    "Bletchley 2023, REAIM 2023…). One-off summits often *produce* the " +
    "institutions and recurring series shown in the other two views, so " +
    "including them here makes catalytic events visible — at the cost of " +
    "spikes on the annual founding curve that are not sustained populations."
  ),
};

// Pure filter. Tests import this directly.
export function filterByView(agvs, view) {
  if (view === "continuous") {
    return agvs.filter((a) => CONTINUOUS_ENTITY_TYPES.has(a.entity_type));
  }
  if (view === "recurring") {
    return agvs.filter((a) => RECURRING_FREQUENCIES.has(a.convening_frequency));
  }
  // "one_off_included" — return everything, callers highlight one_off separately.
  return agvs.slice();
}

// Convenience: filter the pre-computed founding_rate.json records that
// carry a `value` = entity_type (for view=continuous filter) or
// `value` = topic_focus_primary. For the recurring / one_off_included
// views we cannot easily re-aggregate from founding_rate.json because it
// lacks convening_frequency; callers should re-aggregate from `agv` instead.
export function filterFoundingRateByEntityType(records, view) {
  if (view !== "continuous") return records;
  return records.filter(
    (r) => r.dimension !== "entity_type" || CONTINUOUS_ENTITY_TYPES.has(r.value),
  );
}
