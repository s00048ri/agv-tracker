# Companion analysis notebooks

This directory holds the Jupyter notebooks that back the SSRN companion
paper. Each notebook is reproducible end-to-end from the CSVs under
`data/`; nothing here depends on the Observable Framework site.

| Notebook | Purpose | Status |
|---|---|---|
| `founding_rate_analysis.ipynb` | Reproduce the dashboard's headline charts; fit a density-dependent Poisson founding-rate model à la Hannan & Freeman (1977, 1989); run sensitivity analyses across the three §6.2 views; emit a publication-ready figure set to `figures/`. | CLAUDE.md §9 Task 13 |

## Running a notebook

```bash
uv sync --extra notebook              # installs pandas, statsmodels, jupyter, etc.
uv run jupyter lab notebooks/         # interactive session
```

or, to execute end-to-end and overwrite the committed outputs in place:

```bash
uv run jupyter nbconvert --to notebook --execute \
    --inplace notebooks/founding_rate_analysis.ipynb
```

## Regenerating a notebook from its source script

The `.ipynb` files are built programmatically from
`scripts/generate_analysis_notebook.py` — treat the Python script as the
canonical source and the notebook as a build artefact. To regenerate:

```bash
uv run python scripts/generate_analysis_notebook.py
```

`scripts/generate_analysis_notebook.py --check` is CI's regression gate
(runs in `.github/workflows/validate.yml`). It exits non-zero if the
committed `.ipynb` is out of sync with the script, so any change to the
analysis is reviewed via an updated script + committed regenerated
notebook.

## Figures

`figures/` is `.gitignore`-d. The notebook writes three PDFs there on
execution:

- `cumulative_active_population.pdf` — Section 3
- `founding_rate_by_view.pdf` — Section 3
- `density_dependence_poisson.pdf` — Section 7 (publication summary)

If you need the figures outside a local run, execute the notebook once
and copy the PDFs out by hand; binary figures are deliberately excluded
from the Git history.

## CI

The `python` job in `.github/workflows/validate.yml` installs the
`[notebook]` extras and executes `tests/test_notebook.py`, which runs
`founding_rate_analysis.ipynb` end-to-end via `nbclient` and asserts:

- parses as a valid `.ipynb`,
- every code cell executes without an `error` output,
- contains the LR-test-inferential cell and the density-dependence
  model-fit cell, so Task 13 Done-when #2 is continuously verified.
