# AGV Tracker

A static web tracker for **AI Governance Venues** — international organizations, intergovernmental fora, multistakeholder coalitions, and recurring conferences whose mandate addresses the governance of AI.

This is a **v0.1 pilot** with 30 hand-curated seed venues, intended primarily to validate the AGVO ontology against real-world entities.

## Quickstart

```bash
npm install
npm run dev    # local preview at http://localhost:3000
npm run build  # static build to ./dist
```

## Repository layout

```
agv-tracker/
├── src/                # Observable Framework source
│   ├── index.md        # Landing page
│   ├── dashboard.md    # Analytical dashboard
│   ├── venues/         # Searchable directory
│   ├── methodology.md  # AGVO ontology
│   ├── data-download.md
│   └── data/           # Data loaders (.py scripts run at build time)
├── data/               # Canonical CSV — version-controlled source of truth
├── pipelines/          # ETL scripts (monthly fetch → diff → PR)
├── scripts/
│   └── monthly_update.sh
├── tests/              # Schema validation
└── .github/workflows/  # CI/CD
```

## Data model

See `src/methodology.md` and the AGVO ontology specification.

## Monthly update workflow

1. GitHub Actions runs `pipelines/` on the 1st of each month.
2. Diff against `data/agv.csv` is computed; new candidates are listed in an auto-opened PR.
3. Maintainer reviews each candidate (~30–60 min), assigns ontology values, merges.
4. CI rebuilds the site and Cloudflare Pages auto-deploys.

## License

- Code: MIT
- Data: CC-BY 4.0

## Contributing

Issues and PRs welcome. For data corrections, see the "Edit on GitHub" link on each venue's detail page (planned for v0.2).
