# Plan: Add Journal-Level Correction Factors and Confidence Intervals to Funder Table/Figure

## Context

The funder table and figure (`table_funders_2024_2025.tex`, `funders_open_data_2024_2025.png`) currently report open data rates using `is_open_data_best`, which combines XML and PDF oddpub detection. However, 69% of the 951K research articles (2024-2025) only have XML coverage, and head-to-head comparison on the 268K articles with both shows PDF detects **2.74x more open data** (16.0% vs 5.8%). This means we're systematically underestimating open data rates, especially for funders whose articles concentrate in journals with high XML miss rates (Nature Communications: 82%, Scientific Reports: 69%).

**Goal:** Apply journal-level correction factors from the head-to-head subset to estimate each funder's true open data rate, and display corrected rates with confidence intervals in the table and figure.

## Files to Modify/Create

| File | Action | Description |
|---|---|---|
| `scripts/utils/data_loader.py` | MODIFY | Add 3 new DuckDB query functions |
| `scripts/utils/correction.py` | CREATE | Correction logic + Wilson CI (~100 lines) |
| `scripts/utils/__init__.py` | MODIFY | Export new functions |
| `scripts/table_funders.py` | MODIFY | Integrate corrections into summary, table, and chart |
| `scripts/pdf_priority_list.py` | CREATE | Generate prioritized PMID/DOI list for PDF download (~150 lines) |
| `Makefile` | MODIFY | Add `--no-correction` comparison target + `pdf-priority` target |

## Correction Methodology

For each funder, split articles into two pools:
1. **PDF-covered** (`has_oddpub_pdf_v7 = true`): `is_open_data_best` is accurate
2. **XML-only** (`has_oddpub_xml_v7 = true AND has_oddpub_pdf_v7 != true`): underestimated

For XML-only articles, estimate true OD using journal-level PDF OD rates from the head-to-head subset:

```
corrected_od = od_from_pdf_covered + Σ_j (n_xml_only_j × pdf_rate_j)
```

Where `pdf_rate_j` is the PDF open data rate for journal `j` from the head-to-head articles. For journals without enough head-to-head data (< 50 articles), use the global average PDF OD rate.

**Confidence intervals** use Wilson score binomial CIs on each journal's `pdf_rate_j`, propagated through the weighted sum.

**Result:** Each funder gets:
- `open_data_pct` (observed, current value — lower bound)
- `corrected_pct` (estimated true rate — point estimate)
- `ci_lo_pct` / `ci_hi_pct` (95% CI on the corrected estimate)

## Implementation Details

### 1. `scripts/utils/data_loader.py` — Add 2 functions

**`query_journal_correction_factors(con, min_h2h=50, **filter_kwargs)`**
Returns (DataFrame, dict):
- DataFrame: per-journal stats from head-to-head articles (both XML+PDF processed)
  - Columns: `journal, h2h_n, xml_od_rate, pdf_od_rate, best_od_rate`
- Dict: global stats `{rate, n}` across all head-to-head articles

SQL (journal-level):
```sql
SELECT journal,
    COUNT(*) AS h2h_n,
    SUM(is_open_data_xml_v7::INT)::DOUBLE / COUNT(*) AS xml_od_rate,
    SUM(is_open_data_pdf_v7::INT)::DOUBLE / COUNT(*) AS pdf_od_rate,
    SUM(is_open_data_best::INT)::DOUBLE / COUNT(*) AS best_od_rate
FROM pmids
WHERE has_oddpub_xml_v7 = true AND has_oddpub_pdf_v7 = true
  AND journal IS NOT NULL {extra_filters}
GROUP BY journal
HAVING COUNT(*) >= {min_h2h}
```

**`query_funder_journal_xml_only(con, canonical_names=None, **filter_kwargs)`**
Returns DataFrame: per-funder (or per-group), per-journal XML-only article counts.
- If `canonical_names` is None: bulk query for all funders, columns `canonical_name, journal, n_xml_only`
- If `canonical_names` is a list: group query (DISTINCT pmid), columns `journal, n_xml_only`

### 2. `scripts/utils/correction.py` — New module (~80 lines)

```python
def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score CI for a binomial proportion."""

def build_journal_correction_table(
    journal_df: pd.DataFrame, global_stats: dict
) -> pd.DataFrame:
    """Add Wilson CI columns (ci_lo, ci_hi) to journal corrections.
    Returns DataFrame with: journal, pdf_od_rate, ci_lo, ci_hi"""

def apply_funder_correction(
    funder_journal_xml: pd.DataFrame,  # journal, n_xml_only
    journal_corrections: pd.DataFrame, # journal, pdf_od_rate, ci_lo, ci_hi
    global_fallback: dict,             # rate, ci_lo, ci_hi
    pdf_covered_od: int,               # accurate OD from PDF-covered articles
) -> dict:
    """Apply journal-level corrections to one funder's XML-only articles.
    Returns: {corrected_od, ci_lo, ci_hi, n_corrected, n_fallback}"""
```

### 3. `scripts/table_funders.py` — Integrate corrections

**Modified `build_funder_summary()` signature:**
```python
def build_funder_summary(
    con, normalizer, bulk_stats, min_articles=100,
    journal_corrections=None,    # NEW
    global_correction=None,      # NEW
    funder_journal_xml=None,     # NEW (bulk XML-only counts)
    **filter_kwargs,
) -> pd.DataFrame:
```

Changes inside:
- For **alias groups**: also call `query_funder_journal_xml_only(con, db_names, ...)` and `apply_funder_correction()` to get corrected values. Need a new `_with_coverage` variant of the group query to get `pdf_covered_od`.
- For **unaliased funders**: merge with pre-computed bulk corrections
- Each row dict gains: `corrected_od, corrected_pct, ci_lo_pct, ci_hi_pct, pdf_covered_pct, xml_only_pct`
- If `journal_corrections` is None, corrected columns = observed (backward compatible)

**Modified `generate_funder_latex_table()`:**
- Add 6th column: `% OD (obs.)` showing the raw `open_data_pct`
- Primary `% Open Data` column shows `corrected_pct`
- Caption updated to explain correction methodology
- Column spec: `{p{5.5cm} l S[table-format=6.0] S[table-format=5.0] S[table-format=2.1] S[table-format=2.1]}`

**Modified `generate_funder_bar_chart()`:**
- Two-segment bars: full bar = `corrected_pct` (lighter shade), inner bar = `open_data_pct` (full opacity)
- Error whiskers from `ci_lo_pct` to `ci_hi_pct`
- Legend: "Observed", "Estimated (corrected)", "95% CI"
- Baseline line remains at observed funded baseline

**Modified `main()`:**
- New CLI args: `--apply-correction` (default True), `--no-correction`, `--min-h2h-articles` (default 50)
- Before `build_funder_summary`: compute journal corrections if enabled
- Also need to call `query_funder_open_data_stats` with coverage columns for the bulk path (extend existing query to also return `pdf_covered, pdf_covered_od, xml_only, xml_only_od`)

**Modified `save_summary_markdown()`:**
- Add columns for corrected rate and CI bounds

### 4. `Makefile`

Add `funder-table-2024-raw` target with `--no-correction` for comparison. Add `pdf-priority` target:

```makefile
pdf-priority:
	python scripts/pdf_priority_list.py \
		--duckdb-path $(DUCKDB_PATH) \
		--date-from 2024-01-01 --date-to 2025-06-30 --research-only \
		--top-n 5000 --output results/pdf_priority_list.csv --verbose
```

## Data Flow

```
DuckDB ──────────────────────────────────────────────────────────
  │
  ├─ query_journal_correction_factors()
  │    → journal_corrections (DataFrame, ~600 journals)
  │    → global_correction (dict: rate, n)
  │
  ├─ query_funder_open_data_stats() [existing, + coverage cols]
  │    → bulk_stats (DataFrame, ~18K funders)
  │
  ├─ query_funder_journal_xml_only(canonical_names=None)
  │    → funder_journal_xml (DataFrame, ~200K rows)
  │
  └─ per alias group:
       query_funder_open_data_for_group() [existing]
       query_funder_journal_xml_only(canonical_names=[...])
       apply_funder_correction()

build_funder_summary() → summary DataFrame
  ├─ generate_funder_latex_table()  → .tex (6 columns)
  ├─ generate_funder_bar_chart()    → .png (dual bars + whiskers)
  ├─ save_summary_csv()             → .csv (with corrected cols)
  └─ save_summary_markdown()        → .md  (with corrected cols)
```

## Key Query: Coverage-Aware Bulk Stats

Extend `query_funder_open_data_stats` to also return PDF vs XML-only breakdown per funder:

```sql
SELECT
    f.canonical_name, f.country_code, f.funder_id,
    COUNT(DISTINCT af.pmid) AS total_articles,
    COUNT(DISTINCT CASE WHEN p.is_open_data_best THEN af.pmid END) AS open_data_articles,
    COUNT(DISTINCT CASE WHEN p.is_open_code_best THEN af.pmid END) AS open_code_articles,
    -- Coverage breakdown:
    COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 THEN af.pmid END) AS pdf_covered,
    COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 AND p.is_open_data_best
          THEN af.pmid END) AS pdf_covered_od,
    COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
          THEN af.pmid END) AS xml_only,
    COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
          AND p.is_open_data_xml_v7 THEN af.pmid END) AS xml_only_od
FROM article_funders af
JOIN funders f ON af.funder_id = f.funder_id
JOIN pmids p ON af.pmid = p.pmid
WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)
  {extra_filters}
GROUP BY f.canonical_name, f.country_code, f.funder_id
```

## Implementation Sequence

1. Add `query_journal_correction_factors()`, `query_funder_journal_xml_only()`, and coverage-aware bulk stats to `data_loader.py`
2. Create `scripts/utils/correction.py` with Wilson CI and correction logic
3. Update `scripts/utils/__init__.py` exports
4. Modify `build_funder_summary()` to compute corrected rates
5. Modify `generate_funder_latex_table()` for 6-column layout
6. Modify `generate_funder_bar_chart()` for dual-segment bars with error whiskers
7. Modify `save_summary_markdown()` for new columns
8. Add CLI args and wire up in `main()`
9. Create `scripts/pdf_priority_list.py`
10. Update Makefile
11. Run and verify all outputs

## 5. `scripts/pdf_priority_list.py` — Prioritized PDF Download List

Standalone script that outputs a CSV of XML-only PMIDs/DOIs ranked by expected impact on the funder table's error bars. Intended for manual batch download via PaperPile (1K–10K articles per batch).

**Prioritization logic:**

For each XML-only funded article, compute a priority score:

```
priority = pdf_od_rate_j × funder_weight
```

Where:
- `pdf_od_rate_j` = the journal's PDF open data rate from head-to-head (higher = more likely to find OD the XML missed)
- `funder_weight` = 2.0 if funder is in the table/figure, 1.0 otherwise (directly improves visible results)
- Only include articles where `is_open_data_xml_v7 = false` (XML didn't detect OD — PDF might flip it)

**Output:** `results/pdf_priority_list.csv` with columns:
- `pmid, doi, pmcid, journal, funder_name, pdf_od_rate, priority_score, rank`

Sorted by `priority_score` descending. The top N articles (configurable, default 5000) are the highest-value downloads.

**CLI:**
```bash
python scripts/pdf_priority_list.py \
    --duckdb-path /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --top-n 5000 --output results/pdf_priority_list.csv --verbose
```

**Key query** (single DuckDB query):
```sql
SELECT p.pmid, p.doi, p.pmcid, p.journal,
       f.canonical_name AS funder_name,
       jc.pdf_od_rate
FROM pmids p
JOIN article_funders af ON p.pmid = af.pmid
JOIN funders f ON af.funder_id = f.funder_id
JOIN (journal_corrections_cte) jc ON p.journal = jc.journal
WHERE p.has_oddpub_xml_v7 = true
  AND NOT COALESCE(p.has_oddpub_pdf_v7, false)
  AND NOT COALESCE(p.is_open_data_xml_v7, false)
  AND p.is_research = true
  AND p.pub_date >= '2024-01-01' AND p.pub_date <= '2025-06-30'
ORDER BY jc.pdf_od_rate DESC
```

The script imports `query_journal_correction_factors()` from `data_loader.py` and reuses the journal corrections table. After scoring, deduplicates on PMID (an article may have multiple funders) keeping the highest score.

**Expected output size:** ~50K–100K candidate rows before top-N filtering. The top 5K should cover the highest-impact journals (Nature Communications, Scientific Reports, PLOS ONE, Communications Biology) where XML miss rates are 69–84%.

## Verification

```bash
source ~/claude/osm/venv/bin/activate

# 1. Test with corrections (default)
python scripts/table_funders.py \
    --duckdb-path /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 \
    --output-suffix _2024_2025 --verbose

# 2. Test without corrections (compare)
python scripts/table_funders.py \
    --duckdb-path /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 --no-correction \
    --output-suffix _2024_2025_raw --verbose

# 3. Generate PDF priority list
python scripts/pdf_priority_list.py \
    --duckdb-path /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --top-n 5000 --output results/pdf_priority_list.csv --verbose

# Checks:
# - For every funder: corrected_pct >= open_data_pct
# - For every funder: ci_lo_pct <= corrected_pct <= ci_hi_pct
# - --no-correction output matches previous output (backward compat)
# - LaTeX compiles: tectonic latex/main.tex
# - Bar chart visually shows dual segments and whiskers
# - PDF priority list has ~5K rows, top entries are from high-miss-rate journals
# - Spot-check: top DOIs are from Nature Comms, Sci Reports, etc.
```
