# AGV Tracker

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22571203.svg)](https://doi.org/10.5281/zenodo.22571203)

A static web tracker for **AI Governance Venues** — international organizations, intergovernmental fora, multistakeholder coalitions, and recurring conferences whose mandate addresses the governance of AI.

This is a **v0.3 working dataset** with 118 human-verified venues produced
under the AGVO v0.3 ontology (see `CLAUDE.md` for the spec and `CHANGELOG.md`
for the dataset history).

## Live site

- **Production**: <https://agv-tracker.pages.dev/> — auto-deployed from
  `main` by `.github/workflows/deploy.yml`. First public URL + custom
  domain TBD; recorded in `CHANGELOG.md` on first successful deploy.
- **Smoke-check the deploy** (any URL):
  ```bash
  scripts/verify_deployment.sh https://agv-tracker.pages.dev/
  ```

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

## Citing this dataset

Iida, R. (2026). *AGV Tracker: AI Governance Venues* (v0.3.0) [Data set].
Zenodo. <https://doi.org/10.5281/zenodo.22571204>

The badge above carries the **concept DOI**
(`10.5281/zenodo.22571203`), which always resolves to the newest release —
cite that when you mean the dataset rather than one edition of it. The
version DOI above pins v0.3.0, and is what a reproducible analysis should
reference. `/data-download` on the site carries a ready-made BibTeX block,
generated from `data/citation.json` so it cannot drift from this file.

## License

- Code: MIT
- Data: CC-BY 4.0

## Contributing

Issues and PRs welcome. For data corrections, use the "Edit on GitHub" link on each
venue's detail page — it opens `data/agv.csv` directly. Any data change must carry
the evidence rows described in `CLAUDE.md` §8.6; CI enforces this.
