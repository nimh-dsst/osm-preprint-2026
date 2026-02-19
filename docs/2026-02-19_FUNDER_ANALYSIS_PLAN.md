# Plan: Funder Table & Figure Generation (v2026-02-19.1)

> Supersedes `2026-02-13_IMPLEMENTATION_PLAN_USING_DUCKDB.md` (v2).

## What Changed

| Area | v2 (2026-02-13) | v2026-02-19.1 |
|---|---|---|
| **Open data scoring** | `is_open_data_v7` (oddpub v7 on XML only, 5.6% rate) | `is_open_data_best` (PDF preferred, XML fallback, ~12% funded rate) |
| **Column names** | Ambiguous (`is_open_data_v7`) | Clarified: `is_open_data_xml_v7`, `is_open_data_pdf_v7`, `is_open_data_best` |
| **Article scope** | All years, 6.4M articles | Jan 2024 – Jun 2025 only (~322K funded articles with oddpub scores) |
| **DuckDB schema** | MinerU results in separate DB | Merged into `pmid_registry.duckdb` with `is_open_data_best = COALESCE(pdf_v7, xml_v7)` |
| **data_loader.py** | Used `is_open_data_v7`, `has_oddpub_v7` | Already updated to use `is_open_data_best`, `has_oddpub_pdf_v7 OR has_oddpub_xml_v7` |
| **Funder aliases** | v4 → v5 migration | v5 (already done) |

## Why Restrict to Jan 2024 – Jun 2025

1. **PDF coverage:** 326K articles have MinerU+oddpub PDF scores, almost all from 2024-2025. For articles outside this window, only XML scores exist (which undercount by ~60%).
2. **Consistent methodology:** Within 2024-2025, 35% of funded articles have PDF scoring. Using `is_open_data_best` gives the most accurate available score for each article.
3. **Contemporary snapshot:** Current funder policies, not 2010-era practices.
4. **Preprint scope:** The PDF pivot is the core methodological contribution.

## Data Architecture

### Single DuckDB: `pmid_registry.duckdb`

**Location:** `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`

All scoring is now in one database. Key oddpub columns in `pmids` table:

| Column | Source | Articles Scored | Open Data Rate |
|---|---|---|---|
| `is_open_data_xml_v5` | oddpub v5 on PMC XML | 6.1M | 11.8% |
| `is_open_data_xml_v7` | oddpub v7 on PMC XML | 6.4M | 5.6% |
| `is_open_data_pdf_v7` | oddpub v7 on MinerU PDF | 326K | 15.8% |
| **`is_open_data_best`** | **COALESCE(pdf_v7, xml_v7)** | **6.4M** | **varies** |

**`is_open_data_best`** is the column to use. It prefers the more accurate PDF score when available, falls back to XML. On the 281K articles with both scores, PDF finds 29,600 open_data that XML misses while XML only finds 954 that PDF misses.

### Current Stats for Funded Articles (2024–2025)

| Metric | Count |
|---|---|
| Funded articles with any oddpub score | 322,432 |
| Open data (best) | 39,309 (12.2%) |
| Have PDF scoring | 113,507 (35.2%) |

## Implementation

### Already Done

These changes were completed in prior sessions:
- `data_loader.py`: queries use `is_open_data_best` and `has_oddpub_pdf_v7 OR has_oddpub_xml_v7`
- `funder_aliases_v5.csv`: migrated, `FunderNormalizer` rewritten
- `_DB_NAME_OVERRIDES`: reduced from 21 to 15 entries
- Weibull threshold, bar chart with color=volume, markdown output

### Changes Needed

#### 1. Add date range filtering to queries

**`scripts/utils/data_loader.py`:**

Add `min_year`/`max_year` parameters to both query functions:

```python
def query_funder_open_data_stats(
    con, min_articles=0, min_year=None, max_year=None,
) -> pd.DataFrame:
    # Add WHERE clause: p.pub_year >= {min_year} AND p.pub_year <= {max_year}
```

```python
def query_funder_open_data_for_group(
    con, canonical_names, min_year=None, max_year=None,
) -> dict:
    # Same date filter
```

#### 2. Add CLI date range and update captions

**`scripts/table_funders.py`:**

```python
p.add_argument("--min-year", type=int, default=2024,
    help="Start year for article selection (default: 2024)")
p.add_argument("--max-year", type=int, default=2025,
    help="End year for article selection (default: 2025)")
```

Pass `min_year`/`max_year` through `build_funder_summary()` to both query functions.

**Update captions** to specify:
- Time range: "Jan 2024 – Jun 2025"
- Detection method: "oddpub v7 best-available (MinerU PDF preferred, PMC XML fallback)"

#### 3. Recalibrate Weibull thresholds

With ~322K funded articles (vs 2.6M in v2), per-funder article counts will be smaller. Run with `--verbose` first to check the Weibull fit. May need to:
- Lower `--min-articles` from 100 to 50
- Adjust survival levels if the distribution is too narrow
- Or keep current levels and accept fewer funders in table/figure

#### 4. Update Makefile

No new DuckDB path needed (still `pmid_registry.duckdb`). Just pass date range:

```makefile
funder-table:
	python scripts/table_funders.py \
		--duckdb-path $(DUCKDB_PATH) \
		--min-year 2024 --max-year 2025 \
		--output-dir latex/tables/ --figures-dir latex/figures/ \
		--results-dir results/ --verbose
```

#### 5. Update logging for clarity

In `main()`, add explicit logging about data source:

```python
logger.info("Scoring: is_open_data_best (PDF v7 preferred, XML v7 fallback)")
logger.info("Date range: %d–%d", args.min_year, args.max_year)
```

## Files to Modify

| File | Change |
|---|---|
| `scripts/utils/data_loader.py` | Add `min_year`/`max_year` params to both query functions |
| `scripts/utils/__init__.py` | No change (exports unchanged) |
| `scripts/table_funders.py` | Add `--min-year`/`--max-year` CLI args, update captions, pass date range through |
| `Makefile` | Add date range to funder-table target |

## Expected Results

| Metric | v2 (all years, XML only) | v2026-02-19.1 (2024-2025, best) |
|---|---|---|
| Funded articles | 2.6M | ~322K |
| Funded open data baseline | ~10% | ~12% |
| Funders with ≥100 articles | ~5,400 | TBD (est. 500-1,000) |
| Top funder open data rate | ~22% | TBD (est. 25-40%) |
| Detection method | XML only (underestimates) | PDF preferred (most accurate) |

## Verification

```bash
source ~/claude/osm/venv/bin/activate

# Run with verbose to check Weibull fit and date range
python scripts/table_funders.py --min-year 2024 --max-year 2025 --verbose

# Verify baseline is ~12% (not ~10% like XML-only or ~5% like old v7)
python -c "
import pandas as pd
df = pd.read_csv('results/funders_summary.csv')
print(f'Funders: {len(df)}')
print(f'Median open data rate: {df[\"open_data_pct\"].median():.1f}%')
# Should be meaningfully higher than v2's ~10% baseline
"

# Check top funders have reasonable rates (15-30% range)
head -20 results/funders_summary.csv
```

## Preventing Confusion: Column Naming Summary

The renamed columns in `pmid_registry.duckdb` now encode both **text source** and **oddpub version**:

```
is_open_data_{source}_{version}
                │         │
                │         └── v5 or v7 (oddpub version)
                └── xml or pdf (text extraction method)

is_open_data_best = COALESCE(pdf_v7, xml_v7)
```

This convention should be followed for any future scoring iterations (e.g., `is_open_data_pdf_v8`).

See `osm-pipeline/docs/PLAN_2026-02-19_Clarify_and_Clean_Up_OddPub_Scoring_pmid_registry.md` for full migration details.
