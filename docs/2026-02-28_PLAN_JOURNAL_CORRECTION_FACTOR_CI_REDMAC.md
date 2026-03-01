# Plan: Add Correction Factors & CIs to Journal Figure/Table (MacBook Air Adaptation)

## Context

The plan at `docs/2026-02-26_PLAN_JOURNAL_CORRECTION_FACTOR_CI.md` was written on Curium (NIH physical server) and has **not yet been implemented**. The journal figure and table currently report only observed open data rates. The funder pipeline already applies per-journal h2h correction factors with Wilson score 95% CIs — the same methodology should be applied to the journal outputs for scientific consistency.

This plan adapts the original for execution on Adams-Red-MacBook-Air, addressing path differences, missing Python environment, and LaTeX toolchain gaps.

## Host Adaptation: What Needs to Change

### 1. DuckDB Path
- **Curium:** `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`
- **This Mac:** `/Users/adamt/proj/osm/datalad-osm/duckdbs/pmid_registry.duckdb` (2.6 GB, git-annex, content present)

The `--duckdb-path` default in `scripts/table_journals.py:270` is hardcoded to the Curium path. Must either:
- Pass `--duckdb-path` explicitly on every invocation, **OR**
- Add auto-detection logic (env var → relative path → Curium fallback)

**Recommended:** Add a shared `_find_duckdb_default()` helper in `scripts/utils/data_loader.py` and use it from all 4 scripts (`table_funders.py`, `table_journals.py`, `pdf_priority_list.py`, `load_funder_budgets.py`) plus update the `Makefile` default. This is a prerequisite step before the correction factor work.

### 2. Python Environment
- Shared venv at `~/proj/osm/venv` (Python 3.13.12)
- Has: `duckdb`, `pandas`, `numpy`, `pyarrow`
- **Missing:** `matplotlib`, `seaborn`, `scipy`, `tqdm` (needed by scripts)
- `uv` available at `/opt/homebrew/bin/uv`
- Makefile uses bare `python` (not found on this Mac without activating venv)

**Setup needed before any script runs:**
```bash
source ~/proj/osm/venv/bin/activate
uv pip install matplotlib seaborn scipy tqdm
```

### 3. LaTeX Toolchain
- No `pdflatex`, `biber`, or `tectonic` on this Mac
- `make compile` will fail — not needed for the data pipeline work
- Can install later: `brew install --cask mactex` or `brew install tectonic`

### 4. Makefile
- `DUCKDB_PATH` default needs updating (see #1)
- `python` → should work if venv is activated; alternatively update to `$(PYTHON)` variable

## Implementation Steps

### Step 0: Environment Setup (prerequisite)

1. Install missing deps into shared venv: `source ~/proj/osm/venv/bin/activate && uv pip install matplotlib seaborn scipy tqdm`
2. Add `_find_duckdb_default()` to `scripts/utils/data_loader.py`:
   ```python
   def _find_duckdb_default(db_name="pmid_registry.duckdb"):
       """Auto-detect DuckDB path across hosts."""
       import os
       env = os.environ.get("OSM_DUCKDB_PATH")
       if env and os.path.exists(env):
           return env
       repo_rel = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                               "datalad-osm", "duckdbs", db_name)
       if os.path.exists(repo_rel):
           return os.path.abspath(repo_rel)
       return f"/data/adamt/osm/datalad-osm/duckdbs/{db_name}"
   ```
3. Update default in `scripts/table_journals.py:270`, `scripts/table_funders.py:892`, `scripts/pdf_priority_list.py:34`, `scripts/load_funder_budgets.py:24` to use `_find_duckdb_default()`
4. Update `Makefile:5` DUCKDB_PATH to auto-detect:
   ```makefile
   DUCKDB_PATH ?= $(or $(OSM_DUCKDB_PATH),$(wildcard ../datalad-osm/duckdbs/pmid_registry.duckdb),/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb)
   ```

### Step 1: Add `apply_journal_correction()` to `scripts/utils/correction.py`

New function after `apply_funder_correction()` (after line 146). Simpler than the funder version — each journal corrects itself:

```python
def apply_journal_correction(
    journal_name: str,
    xml_only_count: int,
    observed_od: int,
    pdf_covered_od: int,
    journal_corrections: pd.DataFrame,
    global_fallback: dict,
) -> dict:
```

Logic: look up journal in h2h corrections table → compute corrected OD from `best_od_rate * xml_only_count + pdf_covered_od` → apply Wilson CIs → floor at observed.

### Step 2: Add `pdf_covered_od` to `query_journal_open_data_stats()` in `scripts/utils/data_loader.py`

Add one SUM column to the SQL at line ~448:
```sql
SUM(CASE WHEN p.has_oddpub_pdf_v7 = true AND p.is_open_data_best = true THEN 1 ELSE 0 END) AS pdf_covered_od
```

File: `scripts/utils/data_loader.py:444-460`

### Step 3: Integrate corrections into `scripts/table_journals.py` main workflow

In `main()` (line 307):
1. Add imports: `query_journal_correction_factors` from `data_loader`, `build_journal_correction_table` and `apply_journal_correction` from `correction`
2. Add CLI flags: `--no-correction`, `--min-h2h` (default 50)
3. After querying journal_stats + baseline, compute correction factors and apply per-journal
4. Add correction columns: `corrected_od`, `corrected_pct`, `ci_lo_pct`, `ci_hi_pct`

### Step 4: Update `generate_journal_bar_chart()` (line 45)

Mirror the funder chart pattern from `scripts/table_funders.py:687`:
- Light-opacity background bar = corrected rate
- Full-opacity foreground bar = observed rate
- Error whiskers from `ci_lo_pct` to `ci_hi_pct`
- Label: `"XX.X% (est. YY.Y%)"`
- Legend with "Observed" and "Estimated (corrected)" patches

### Step 5: Update `generate_journal_latex_table()` (line 120)

Add two columns to the longtable:
- **Corrected %** (point estimate)
- **95% CI** (formatted as `[lo, hi]`)

Update column spec, header, data rows, and caption.

### Step 6: Update CSV and Markdown outputs

- `save_summary_csv()`: new columns automatic (just include in DataFrame)
- `save_summary_markdown()`: add corrected % and CI columns to table

### Step 7: Update `latex/article.tex` journal figure caption

Match the funder caption style describing correction methodology and CIs.

### Step 8: Add Makefile target (optional)

Add `journal-table-2024-raw` target with `--no-correction` flag, mirroring `funder-table-2024-raw`.

## Files to Modify

| File | Action | Lines |
|---|---|---|
| `scripts/utils/data_loader.py` | ADD `_find_duckdb_default()`, ADD `pdf_covered_od` column | ~1, ~448 |
| `scripts/utils/correction.py` | ADD `apply_journal_correction()` | after 146 |
| `scripts/table_journals.py` | Integrate correction pipeline, update chart/table/CSV/md, update default path | 27-37, 45-114, 120-211, 228-260, 266-304, 307-411 |
| `scripts/table_funders.py` | Update default duckdb-path | 892 |
| `scripts/pdf_priority_list.py` | Update default duckdb-path | 34 |
| `scripts/load_funder_budgets.py` | Update default duckdb-path | 24 |
| `latex/article.tex` | Update journal figure caption | TBD |
| `Makefile` | Update DUCKDB_PATH, add journal-table-2024-raw target | 5, new |

## Verification

```bash
cd /Users/adamt/proj/osm/brnch_journalFig
source ~/proj/osm/venv/bin/activate

# 1. Test auto-detection works (no --duckdb-path needed)
python scripts/table_journals.py \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 \
    --output-suffix _2024_2025 --verbose

# 2. Test without corrections (compare)
python scripts/table_journals.py \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 --no-correction \
    --output-suffix _2024_2025_raw --verbose

# 3. Verify funder pipeline still works with new auto-detection
python scripts/table_funders.py \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 \
    --min-works-figure 100000 --min-works-table 50000 \
    --output-suffix _2024_2025 --verbose

# 4. Check outputs
ls -la latex/tables/table_journals_2024_2025.tex
ls -la latex/figures/journals_open_data_2024_2025.png
ls -la results/journals_summary_2024_2025.csv

# 5. Spot-checks:
#    - Journals with high PDF coverage → corrected ≈ observed
#    - Journals with 0% PDF coverage → large corrections
#    - All funders: corrected_pct >= open_data_pct
#    - All funders: ci_lo_pct <= corrected_pct <= ci_hi_pct

# 6. LaTeX compilation (skip if no pdflatex/tectonic installed):
#    cd latex && pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex
```
