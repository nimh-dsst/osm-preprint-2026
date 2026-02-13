# Plan: Funder Table Generation from DuckDB

## Context

The funder data pipeline was recently rebuilt in the `osm-pipeline` repo, populating `pmid_registry.duckdb` with 27,465 funders and 10.5M article-funder relationships. Country codes are now 99.4% populated in the DuckDB. The preprint repo still has placeholder tables and data-loading code that assumes parquet files. This task creates `scripts/table_funders.py` to query the DuckDB and generate the funder table, figure, and CSV.

## Files to Modify/Create

| File | Action | Description |
|---|---|---|
| `scripts/utils/data_loader.py` | MODIFY | Add 3 DuckDB query functions |
| `scripts/utils/__init__.py` | MODIFY | Export new functions |
| `scripts/table_funders.py` | CREATE | Main script (~300 lines) |
| `Makefile` | MODIFY | Update `tables` target for DuckDB path |

Generated outputs (by running the script):
- `latex/tables/table_funders.tex` — longtable with top 50 funders
- `latex/figures/funders_open_data.png` — horizontal bar chart (top 20)
- `results/funders_summary.csv` — full summary

## Implementation Details

### 1. `scripts/utils/data_loader.py` — Add 3 functions

Append after existing functions (leave existing parquet functions untouched):

- **`connect_duckdb_registry(db_path, read_only=True)`** — Opens a `.duckdb` file, returns connection
- **`query_funder_open_data_stats(con, min_articles=0)`** — Bulk query: joins `article_funders` + `funders` + `pmids` (where `has_oddpub_v7=true`), groups by `canonical_name`, returns DataFrame with `total_articles`, `open_data_articles`, `open_code_articles`, `country_code`
- **`query_funder_open_data_for_group(con, canonical_names)`** — Per-group query for parent-child aggregation. Takes a list of canonical names and returns `COUNT(DISTINCT pmid)` across all of them. Avoids double-counting articles funded by multiple child funders (e.g., an article funded by both NCI and NIMH counts once for "NIH")

### 2. `scripts/utils/__init__.py` — Export new functions

Add the 3 new imports.

### 3. `scripts/table_funders.py` — Main script

**Architecture:**

```
CLI (argparse) → connect DuckDB → FunderNormalizer(aliases CSV)
  → build_funder_summary()     # queries DuckDB per alias group + unaliased bulk
  → generate_funder_latex_table()  # longtable with conditional formatting
  → generate_funder_bar_chart()    # matplotlib horizontal bar chart
  → save_summary_csv()            # full CSV to results/
```

**Key components:**

**A. `ALIAS_TO_DB_NAME_OVERRIDES` dict** — Maps 20 alias canonical names that don't exactly match DuckDB names (accent differences, name changes). Verified mappings:

| Alias Name | DuckDB Name |
|---|---|
| Swiss National Science Foundation | Schweizerischer Nationalfonds zur Förderung der Wissenschaftlichen Forschung |
| Bundesministerium fur Bildung und Forschung | Bundesministerium für Bildung und Forschung |
| Swedish Research Council | Vetenskapsrådet |
| Netherlands Organisation for Scientific Research | Nederlandse Organisatie voor Wetenschappelijk Onderzoek |
| Research Foundation Flanders | Fonds Wetenschappelijk Onderzoek |
| National Science Centre | Narodowe Centrum Nauki |
| Max Planck Society | Max-Planck-Gesellschaft |
| Czech Science Foundation | Grantová Agentura České Republiky |
| (+ 12 more accent/prefix differences) | |

**B. `FunderNormalizer` class** — Loads `funder_aliases_v4.csv`, builds:
- `child_to_parent`: maps NIH institutes → "NIH", UKRI councils → "UKRI", ERC → "European Commission"
- `get_aggregation_groups()`: returns list of groups, each with display_name and list of DuckDB canonical_names to aggregate
- **Country**: Uses DuckDB `country_code` directly (99.4% coverage), NOT aliases CSV. The aliases CSV is only used for parent-child relationships and display name preferences.

**C. `build_funder_summary()`** — For each alias group, calls `query_funder_open_data_for_group()` with deduplicated DISTINCT counts. Then adds unaliased funders from bulk query (min 100 articles). Country codes come from DuckDB's `funders.country_code`. Returns DataFrame sorted by `open_data_pct` descending.

**D. `generate_funder_latex_table()`** — longtable (not table float) with:
- Columns: Funder Name | Country | Total Pubs (S col) | Open Data (S col) | % Open Data (S col)
- `\caption` and `\label{tab:funders}` inside longtable
- Conditional formatting: blue-white-red via `get_color_bwr()` (log scale for pubs, linear for %)
- COL5 alternating rows, multi-page headers/footers

**E. `generate_funder_bar_chart()`** — Horizontal bar chart (top 20), blue-white-red color gradient, baseline line at ~8.7% (funded article open data rate), country in label parentheses.

### 4. `Makefile` — Update `tables` target

Replace the nonexistent `generate_all_tables.py` call with a `funder-table` target:
```makefile
DUCKDB_PATH ?= /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb

funder-table:
    python scripts/table_funders.py --duckdb-path $(DUCKDB_PATH) ...

tables: funder-table
```

## Key Data Facts

- **pmid_registry.duckdb**: 6.7M articles, 10.5M article-funder links, 27K funders
- **Coverage**: 2.6M articles have funders + oddpub_v7 results; 228K have open data (8.7%)
- **`country_code`**: 99.4% populated in DuckDB — use directly (no aliases needed for country)
- **`parent_funder_id`**: ALL NULL in DuckDB — parent-child aggregation uses `funder_aliases_v4.csv`
- **55 of 75** alias names match DuckDB exactly; 20 need override mapping

## Verification

```bash
source ~/claude/osm/venv/bin/activate

# Quick test (10 funders)
python scripts/table_funders.py --top-n-table 10 --top-n-figure 10 --verbose

# Verify outputs
ls -la latex/tables/table_funders.tex latex/figures/funders_open_data.png results/funders_summary.csv

# Compile LaTeX
cd latex && pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex

# Full run
python scripts/table_funders.py --verbose
```
