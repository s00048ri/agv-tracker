// Prominent human-verification status banner for a per-venue page.
// Renders one of two states per CLAUDE.md §6.4:
//   "Human-verified <date> by @<reviewer>"       — human_verified_at non-null
//   "Awaiting human review"                      — otherwise
//
// Inputs:
//   agv       — single row from data/agv.json
//   evidence  — agv_evidence.csv rows already filtered to this agv_id
export function verificationBadge(agv, evidence) {
  const verifiedFields = (agv.human_verified_fields || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const verifiedAt = (agv.human_verified_at || "").trim();

  // Most recent human_verification evidence row, preferring higher accessed_at.
  const hv = (evidence || [])
    .filter((e) => e.source_type === "human_verification")
    .sort((a, b) => (b.accessed_at || "").localeCompare(a.accessed_at || ""));
  const reviewer = hv.length ? hv[0].reviewer : "";

  if (verifiedFields.length && verifiedAt) {
    return html`<div class="verification-badge verified" style="
      padding: 0.75rem 1rem;
      margin: 0.75rem 0 1.25rem;
      border-left: 4px solid var(--theme-green, #1a7f37);
      background: var(--theme-background-alt, #f6f8fa);
      border-radius: 4px;
    ">
      <strong style="color: var(--theme-green, #1a7f37);">✓ Human-verified</strong>
      on <code>${verifiedAt}</code>${reviewer
        ? html` by <a href="https://github.com/${reviewer}" target="_blank" rel="noreferrer">@${reviewer}</a>`
        : ""}.<br>
      <small>Verified fields: ${verifiedFields.map((f) => html`<code>${f}</code>`).reduce(
        (acc, el, i) => (i === 0 ? [el] : [...acc, ", ", el]),
        []
      )}.</small>
      <br><small>Override policy: <code>${agv.override_policy || "lock_verified_only"}</code>.</small>
    </div>`;
  }

  return html`<div class="verification-badge awaiting" style="
    padding: 0.75rem 1rem;
    margin: 0.75rem 0 1.25rem;
    border-left: 4px solid var(--theme-orange, #9a6700);
    background: var(--theme-background-alt, #fff8e1);
    border-radius: 4px;
  ">
    <strong style="color: var(--theme-orange, #9a6700);">⏳ Awaiting human review</strong><br>
    <small>This record has not yet been confirmed by a maintainer. Its
    classifications are LLM-proposed and subject to change on review.</small>
  </div>`;
}
