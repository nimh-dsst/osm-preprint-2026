# Plan: Add Correction Factors and Confidence Intervals to Journal Figure & Table

## Context

The journal figure and table currently report **observed** open data rates only, which are systematically biased downward for journals with low PDF coverage (67.3% of all articles are XML-only). The funder pipeline already applies per-journal head-to-head (h2h) correction factors with Wilson score 95% CIs — the same methodology should be applied at the journal level so the figure and table are scientifically comparable to the funder outputs.

**Key insight**: For journals, the correction is simpler than for funders. Each journal corrects *itself* using its own h2h rate (or the global fallback if it has <50 h2h articles). There's no cross-entity breakdown needed.

## Files to Modify

| File | Change |
|---|---|
| `scripts/utils/correction.py` | Add `apply_journal_correction()` function |
| `scripts/table_journals.py` | Integrate correction pipeline, update bar chart & table |
| `latex/article.tex` | Update journal figure caption to describe correction |
| `Makefile` | Add `--no-correction` variant for journals (optional) |

## Step 1: Add `apply_journal_correction()` to `correction.py`

New function after `apply_funder_correction()` (~line 147):

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

**Logic**:
1. Look up `journal_name` in `journal_corrections` DataFrame
2. If found: use that journal's `best_od_rate`, `ci_lo`, `ci_hi`
3. If not found: use `global_fallback` rates
4. `corrected_od = pdf_covered_od + (xml_only_count * rate)`
5. `ci_lo = pdf_covered_od + (xml_only_count * ci_lo_rate)`
6. `ci_hi = pdf_covered_od + (xml_only_count * ci_hi_rate)`
7. Floor all three at `observed_od`
8. Return dict: `corrected_od`, `ci_lo`, `ci_hi`, `used_journal_specific` (bool)

**Reuses**: `build_journal_correction_table()` (already exists), `wilson_ci()` (already exists)

## Step 2: Modify `table_journals.py` main workflow

In `main()`, after querying `journal_stats` and `baseline`:

1. **Import** `query_journal_correction_factors` from `data_loader` and `build_journal_correction_table`, `apply_journal_correction` from `correction`
2. **Add CLI flags**: `--no-correction` (skip correction), `--min-h2h` (default 50)
3. **Compute correction factors**:
   ```python
   journal_df, global_stats = query_journal_correction_factors(con, min_h2h=args.min_h2h, **filter_kwargs)
   journal_corrections = build_journal_correction_table(journal_df, global_stats)
   ```
4. **Apply per-journal correction** in a loop over `journal_stats`, adding columns:
   - `corrected_od`, `corrected_pct`, `ci_lo_pct`, `ci_hi_pct`
   - `pdf_covered_od` (need to add to query — see note below)

**Note**: `query_journal_open_data_stats()` already returns `pdf_covered` and `xml_only` but not `pdf_covered_od` (OD count among PDF-covered articles). Need to add that column to the SQL query in `data_loader.py:query_journal_open_data_stats()`.

### Step 2a: Update `query_journal_open_data_stats()` in `data_loader.py`

Add one more `SUM(CASE ...)` column:
```sql
SUM(CASE WHEN p.has_oddpub_pdf_v7 = true AND p.is_open_data_best = true THEN 1 ELSE 0 END) AS pdf_covered_od
```

This mirrors the funder query pattern (lines 184-185 in `data_loader.py`).

## Step 3: Update bar chart — `generate_journal_bar_chart()`

Mirror the funder chart pattern from `generate_funder_bar_chart()` (line 687 of `table_funders.py`):

1. Detect if `corrected_pct` column exists and has data
2. If correction available:
   - Light-opacity background bar = corrected rate
   - Full-opacity foreground bar = observed rate
   - Error whiskers from `ci_lo_pct` to `ci_hi_pct`
   - Label: `"XX.X% (est. YY.Y%)"`
   - Legend with "Observed" and "Estimated (corrected)" patches
3. If no correction: current behavior (single bar)

## Step 4: Update LaTeX table — `generate_journal_latex_table()`

Add two new columns to the longtable:
- **Corrected %** (point estimate)
- **95% CI** (formatted as `[lo, hi]`)

Update column spec, header row, and data rows. Update caption to describe the correction methodology.

## Step 5: Update CSV and Markdown outputs

- **CSV**: Add `corrected_od`, `corrected_pct`, `ci_lo_pct`, `ci_hi_pct`, `pdf_covered_od` columns
- **Markdown**: Add corrected % and CI columns to the table

## Step 6: Update `latex/article.tex` journal figure caption

Change from:
> "Bar length shows the observed open data rate."

To (matching funder caption style):
> "Bar length shows the observed open data rate (full opacity) and the estimated corrected rate (lighter shade) after applying journal-level PDF vs. XML correction factors. Error bars indicate 95% Wilson score confidence intervals on the corrected estimate."

## Step 7: Add Makefile target (optional)

Add `journal-table-2024-raw` target mirroring `funder-table-2024-raw` with `--no-correction` flag.

## Verification

1. Run: `make journal-table-2024` (regenerates all journal outputs)
2. Check `results/journals_summary_2024_2025.csv` has new correction columns
3. Check `latex/figures/journals_open_data_2024_2025.png` shows dual bars + whiskers
4. Check `latex/tables/table_journals_2024_2025.tex` has corrected % and CI columns
5. Spot-check: journals with high PDF coverage (e.g., Nature Biotechnology at 97.5% PDF) should show corrected ≈ observed; journals with 0% PDF (e.g., Heliyon) should show large corrections
6. Run `make compile` to verify LaTeX compiles cleanly
