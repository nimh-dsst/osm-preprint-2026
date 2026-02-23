# Session Summary — 2026-02-22 (Session 2)

## Objective

Filter small/niche funders from the funder figure and table using an objective
dual-threshold approach: Weibull article count AND OpenAlex `openalex_works_count`
as a proxy for funder scale. Separately, curate annual budget data for the 24
figure-level funders.

Plan: `docs/2026-02-22_PLAN_FILTER_FUNDER_SIZE_BUDGET.md`

## What Was Done

### Part 1: Dual-Threshold Filter (works_count + article count)

#### 1. New query functions (`scripts/utils/data_loader.py`)

- `query_funder_works_count(con, funder_ids)` — returns `{funder_id: works_count}`
  for a list of funder IDs
- `query_funder_works_count_by_name(con, canonical_names)` — sums
  `openalex_works_count` across all funders matching the given canonical names;
  critical for parent-child groups where the parent entity (e.g. UKRI: 26K
  individual) has few direct works but children aggregate to ~1.04M

#### 2. Aggregated works count in `build_funder_summary()` (`scripts/table_funders.py`)

- Every funder row now includes `aggregated_works_count` — the sum of
  `openalex_works_count` for all member funders in the group
- For alias groups (NIH, UKRI, European Commission), this aggregates across all
  child funder IDs
- For standalone funders, it's the individual funder's works count

#### 3. Dual filter in `main()` (`scripts/table_funders.py`)

- New CLI args: `--min-works-figure` (default 0), `--min-works-table` (default 0),
  `--no-works-filter`
- After Weibull threshold computation, applies second filter: funder must have
  `aggregated_works_count >= min_works` to appear in figure/table
- Pre-filtered DataFrames passed to `generate_funder_latex_table()` and
  `generate_funder_bar_chart()` with `threshold=0` (already filtered)
- Full unfiltered summary still saved to CSV/markdown for supplementary materials
- Logs filter effect with names of removed funders

#### 4. Makefile updates

- `funder-table-2024` target now includes `--min-works-figure 100000
  --min-works-table 50000`

### Part 2: Funder Budget Data Curation

#### 5. Budget seed CSV (`scripts/funder_budgets_seed.csv`)

24 funders with manually curated annual budget data:
- Columns: `funder_name`, `funder_id`, `country_code`, `budget_amount`,
  `budget_currency`, `budget_usd`, `budget_year`, `budget_type`, `confidence`,
  `source_url`, `source_description`, `notes`
- Sources: official annual reports, government budget pages, Nature News
- Confidence levels: `confirmed` (14 funders), `estimated` (9), `unknown` (1)
- Range: $1.2M (NSF Sri Lanka) to $48.6B (NIH)

#### 6. Budget loader script (`scripts/load_funder_budgets.py`)

- Reads seed CSV, creates `funder_budgets` table in `funder_extract.duckdb`
- CLI args: `--duckdb-path`, `--seed-csv`, `--verbose`
- Prints formatted budget summary on completion
- Requires `datalad unlock` before writing to the managed DuckDB file

#### 7. Makefile `load-budgets` target

```bash
make load-budgets
```

## Key Results

### Works-count filter effect (2024-2025 research, survival 3%/5%)

```
Figure: 24 → 23 funders (removed: National Science Foundation of Sri Lanka)
Table:  42 → 34 funders (removed: NSF Sri Lanka, Japan Agency for Medical Research
        and Development, Bill and Melinda Gates Foundation, HORIZON EUROPE European
        Research Council, National Science Centre, Italian Ministry, Basic and Applied
        Basic Research Foundation of Guangdong Province, National Science and
        Technology Council)
```

### Validation of key funders

| Funder | aggregated_works_count | Status |
|---|---|---|
| UKRI | 1,038,191 | Included (5 children aggregated) |
| NIH | 1,434,393 | Included |
| NSF (USA) | 1,483,056 | Included |
| NSF Sri Lanka | 15,789 | Excluded from figure + table |

### Budget data summary (top 10 by USD)

| Funder | Budget (USD) | Year | Confidence |
|---|---|---|---|
| NIH | $48.6B | 2024 | confirmed |
| European Commission | $13.9B | 2024 | confirmed |
| UKRI | $11.1B | 2024 | confirmed |
| BMBF | $10.8B | 2024 | estimated |
| NSF (USA) | $9.1B | 2024 | confirmed |
| NRF Korea | $7.5B | 2024 | estimated |
| National Key R&D Program | $7.0B | 2024 | estimated |
| NSFC | $5.1B | 2024 | confirmed |
| DFG | $4.2B | 2024 | confirmed |
| Wellcome Trust | $2.4B | 2024 | confirmed |

## Files Modified/Created

| File | Action | Description |
|---|---|---|
| `scripts/utils/data_loader.py` | Modified | +2 functions: `query_funder_works_count`, `query_funder_works_count_by_name` |
| `scripts/table_funders.py` | Modified | `aggregated_works_count` column; `--min-works-*` CLI args; dual filter logic |
| `Makefile` | Modified | Added `--min-works-*` to `funder-table-2024`; added `load-budgets` target |
| `scripts/funder_budgets_seed.csv` | Created | 24-row budget data CSV with sources |
| `scripts/load_funder_budgets.py` | Created | ~100 lines; loads CSV into DuckDB `funder_budgets` table |

## Output Files (regenerated)

| Output | Path | Details |
|---|---|---|
| LaTeX table | `latex/tables/table_funders_2024_2025.tex` | 34 funders (was 42, works-filtered) |
| Bar chart | `latex/figures/funders_open_data_2024_2025.png` | 23 funders (was 24, NSF Sri Lanka removed) |
| CSV | `results/funders_summary_2024_2025.csv` | 816 funders, includes `aggregated_works_count` column |
| Markdown | `results/funders_summary_2024_2025.md` | 816 funders, unfiltered |

## Datalad Workflow for Budget Loading

```bash
cd /data/adamt/osm/datalad-osm
datalad unlock duckdbs/funder_extract.duckdb
python ~/claude/osm/brnch_funderFig/scripts/load_funder_budgets.py --verbose
datalad save -m "Add funder_budgets table with annual budget data" duckdbs/funder_extract.duckdb
```

## Next Steps

1. **Commit** all changes on `funder_fig` branch
2. **Load budgets** into DuckDB via datalad workflow above
3. **Verify Overleaf** — 34-funder table compiles cleanly
4. **Consider** adding budget column to the funder bar chart (e.g. annotated
   with "$48.6B" next to NIH) or a separate budget vs. open data scatter plot
5. **Review** the 8 funders removed from the table by the 50K works filter —
   some (e.g. Gates Foundation) may warrant manual inclusion despite low works count
