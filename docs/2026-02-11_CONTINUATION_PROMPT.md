## Context: Funder Table Generation — Update to Use DuckDB

### What Just Happened (osm-pipeline repo, `add_funders2duckdb` branch — now merged to develop)

We built a funder extraction pipeline that populated `pmid_registry.duckdb` with comprehensive funder data from OpenAlex + PMC XML. The old NER-based approach (133 funders, 3.3M relationships) has been replaced.

### Current Data in pmid_registry.duckdb

**Location:** `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`

**Tables relevant to funder figure/table:**

```sql
-- funders (27,465 rows)
-- Columns: funder_id (PK, VARCHAR, e.g. 'F4320321001'), canonical_name, display_name,
--          country_code, ror_id, parent_funder_id, funder_type, openalex_works_count,
--          source, created_at, updated_at

-- article_funders (10,504,701 rows)
-- Columns: pmid (INTEGER), funder_id (VARCHAR), source (VARCHAR), confidence (FLOAT),
--          grant_id (VARCHAR), created_at
-- PK: (pmid, funder_id, source)
-- source values: 'openalex_funders' (6.2M), 'openalex_grants' (2.6M), 'xml_funding_group' (1.7M)

-- pmids (6,744,945 rows) — main article table
-- Has: pmid, pmcid, pub_year, openalex_id, journal_name, etc.

-- funder_stats (27,464 rows) — precomputed: canonical_name, funder_id, country_code, article_count
-- funder_coverage_by_year — precomputed: pub_year, total_articles, articles_with_funder, coverage_pct
```

**Key stats:** 2,759,417 articles with funders (40.9% of 6.7M), coverage peaks ~52% for 2018.

**Top funders:** NSFC (403K), NIH (271K), NSF (104K), MRC (100K), DFG (89K), European Commission (77K).

### What Needs to Change in This Repo

The current `docs/IMPLEMENTATION_PLAN.md` and `CLAUDE.md` assume funder data comes from:
- `oddpub_output/*.parquet` files joined with `openalex_*.parquet`
- `funder_aliases_v4.csv` for normalization (133 funders)

This is obsolete. All funder data is now in `pmid_registry.duckdb` with 27,465 funders already normalized via OpenAlex IDs.

**Files to update:**

1. **`scripts/utils/data_loader.py`** — Add functions to query pmid_registry.duckdb directly. The existing parquet-loading functions are still useful for oddpub results, but funder queries should go to DuckDB.

2. **`scripts/table_funders.py`** (needs to be created) — Query pmid_registry.duckdb to generate the funder table/figure. Should join `article_funders` with `funders` and oddpub results. Key columns: Funder Name, Country, Total Pubs, Open Data Pubs, % Open Data. Top 50 funders, conditional formatting (blue-white-red gradient). Use `scripts/utils/latex_helpers.py` for formatting.

3. **`docs/IMPLEMENTATION_PLAN.md`** — Update the "Table 1: Top Funders" section and data sources to reflect DuckDB instead of parquet+CSV.

4. **`CLAUDE.md`** — Update the "Data Sources" section: funder data now comes from `pmid_registry.duckdb`, not parquet files. Remove references to `funder_aliases_v4.csv` for funder normalization (keep the file for backward compatibility but note it's superseded).

### Oddpub Data (Still From Parquet)

The oddpub open_data/open_code detection results are NOT in the DuckDB yet. They're still in parquet files or in `pmcid_registry.duckdb`. For the funder table, you'll need to join:
- Funder relationships: `pmid_registry.duckdb` → `article_funders` + `funders`
- Oddpub results: `pmcid_registry.duckdb` → `pmcids` table (has `oddpub_v7_open_data`, `oddpub_v7_open_code` columns)
- Link via PMID: `pmid_registry.duckdb.pmids` has both `pmid` and `pmcid`

### Reference Implementation

The poster repo has a working funder table script: `/home/adamt/claude/osm/osm-2025-12-poster-incf/analysis/funder_table_latex.py` — use as a pattern for LaTeX output formatting, but the data loading approach is completely different now.

### Don't Forget

- `scripts/utils/latex_helpers.py` already exists with `escape_latex()`, `get_color_bwr()`, etc.
- The `Makefile` exists and has `make tables` target
- This branch (`funderFig`) is off `develop` in `osm-preprint-2026` repo
- Python venv: `source ~/claude/osm/venv/bin/activate`
