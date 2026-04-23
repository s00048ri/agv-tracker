// observablehq.config.js
export default {
  title: "AGV Tracker",
  pages: [
    {name: "Dashboard", path: "/dashboard"},
    {name: "Venues", path: "/venues/"},
    {name: "Methodology", path: "/methodology"},
    {name: "Data", path: "/data-download"}
  ],
  theme: ["air", "alt"],
  header: `<div style="display: flex; align-items: baseline; justify-content: space-between;">
    <span><b>AGV Tracker</b> — AI Governance Venues, 2015–present</span>
    <span style="font-size: 0.85em; color: var(--theme-foreground-muted);">v0.1 · pilot</span>
  </div>`,
  footer: `Data version-controlled at <a href="https://github.com/your-handle/agv-tracker">github.com/your-handle/agv-tracker</a>. Last build: ${new Date().toISOString().slice(0,10)}.`,
  root: "src",
  output: "dist",
  search: true
};
