// Per-field evidence rendering (CLAUDE.md §6.4).
//
// Groups agv_evidence.csv rows by `field_name` and shows each with a
// source_type icon, a confidence badge, and any `reviewer` / `evidence_note`.
// Source-type icons distinguish human-verification, LLM-classification, and
// upstream-registry sources.

const SOURCE_TYPE_META = {
  human_verification: { icon: "👤", label: "human verification" },
  llm_classification: { icon: "🤖", label: "LLM classification" },
  official_site: { icon: "🔗", label: "official site" },
  founding_document: { icon: "📄", label: "founding document" },
  press_release: { icon: "📰", label: "press release" },
  oecd_navigator: { icon: "📚", label: "OECD Policy Navigator" },
  iapp_tracker: { icon: "📚", label: "IAPP tracker" },
  unesco_gaigo: { icon: "📚", label: "UNESCO GAIGO" },
  news: { icon: "📰", label: "news" },
  academic_paper: { icon: "📖", label: "academic paper" },
  other: { icon: "🔸", label: "other" },
};

const CONFIDENCE_COLOR = {
  high: "#1a7f37",
  medium: "#9a6700",
  low: "#cf222e",
};

function sourceMeta(source_type) {
  return SOURCE_TYPE_META[source_type] || { icon: "🔸", label: source_type };
}

function renderSourceLink(url) {
  if (!url) return "";
  if (url.startsWith("internal://")) {
    return html` <code title="classifier-run reference">${url}</code>`;
  }
  if (url.startsWith("http")) {
    return html` <a href="${url}" target="_blank" rel="noreferrer">${url}</a>`;
  }
  return html` <code>${url}</code>`;
}

export function evidencePanel(evidence) {
  const rows = evidence || [];
  if (!rows.length) {
    return html`<p><em>No evidence rows for this venue yet.</em></p>`;
  }

  const byField = new Map();
  for (const e of rows) {
    if (!byField.has(e.field_name)) byField.set(e.field_name, []);
    byField.get(e.field_name).push(e);
  }
  const fields = [...byField.keys()].sort();

  return html`<div class="evidence-panel">
    ${fields.map((f) => {
      const fieldRows = byField.get(f).slice().sort((a, b) => {
        // human_verification first, then llm_classification, then others
        const order = (t) =>
          t === "human_verification" ? 0 : t === "llm_classification" ? 1 : 2;
        return order(a.source_type) - order(b.source_type);
      });
      return html`<div class="evidence-field" style="margin: 0.5rem 0 1rem;">
        <h4 style="margin-bottom: 0.25rem;"><code>${f}</code></h4>
        <ul style="margin: 0; padding-left: 1.25rem;">
          ${fieldRows.map((e) => {
            const m = sourceMeta(e.source_type);
            const color = CONFIDENCE_COLOR[e.confidence] || "#6e7781";
            return html`<li style="margin: 0.35rem 0;">
              <span title="${m.label}">${m.icon}</span>
              <span style="color: ${color}; font-weight: 600; font-size: 0.85em;">
                [${e.confidence}]
              </span>
              <span style="font-size: 0.9em; color: var(--theme-foreground-muted);">
                ${m.label}
              </span>
              ${e.reviewer
                ? html` · <em>${e.reviewer}</em>`
                : ""}
              ${e.accessed_at
                ? html` · <small>${e.accessed_at}</small>`
                : ""}
              ${renderSourceLink(e.source_url)}
              ${e.evidence_note
                ? html`<br><small style="color: var(--theme-foreground-muted);">
                    ${e.evidence_note}
                  </small>`
                : ""}
            </li>`;
          })}
        </ul>
      </div>`;
    })}
  </div>`;
}
