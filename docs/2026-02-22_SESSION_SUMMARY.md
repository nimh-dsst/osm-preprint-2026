# Session Summary — 2026-02-22

## Objective

Implement journal-level correction factors and confidence intervals for the
funder table and figure, addressing the systematic underestimation of open data
rates caused by 69% of articles having XML-only oddpub coverage (which detects
2.74x less open data than PDF-based detection).

Plan: `docs/PLAN_2026-02-21_FUNDER_FIG_CORRECTION_FACTOR.md`

## What Was Done

### 1. Extended DuckDB query functions (`scripts/utils/data_loader.py`)

- Added `_build_filter_clause()` helper to DRY up date/year/research filter SQL
- Extended `query_funder_open_data_stats()` with coverage breakdown columns:
  `pdf_covered`, `pdf_covered_od`, `xml_only`, `xml_only_od`
- Extended `query_funder_open_data_for_group()` with same coverage columns
- Added `query_journal_correction_factors()` — returns per-journal head-to-head
  stats (h2h_n, xml_od_rate, pdf_od_rate, best_od_rate) and global stats
- Added `query_funder_journal_xml_only()` — returns per-funder, per-journal
  XML-only article counts (bulk or group mode)

### 2. Created correction module (`scripts/utils/correction.py`)

- `wilson_ci()` — Wilson score confidence interval for binomial proportions
- `build_journal_correction_table()` — adds Wilson CI columns to journal
  correction factors using `best_od_rate` (PDF∪XML union rate)
- `apply_funder_correction()` — applies journal-level corrections to one
  funder's XML-only articles, with observed-value flooring

### 3. Integrated corrections into `scripts/table_funders.py`

- `build_funder_summary()` now accepts `journal_corrections`, `global_correction`,
  and `funder_journal_xml_bulk` for correction computation
- `generate_funder_latex_table()` adds 6th column (`% OD (est.)`) when
  corrections available; caption explains methodology
- `generate_funder_bar_chart()` draws dual-segment bars (observed + estimated)
  with error whiskers and legend
- `save_summary_markdown()` adds corrected rate and CI columns
- New CLI flags: `--no-correction`, `--min-h2h-articles`

### 4. Created PDF priority list script (`scripts/pdf_priority_list.py`)

Standalone script generating a prioritized CSV of XML-only PMIDs/DOIs ranked by
expected impact on funder table error bars. Priority score:
`pdf_od_rate × funder_weight` (2x for table-visible funders).

### 5. Updated Makefile

- `funder-table-2024-raw` — runs with `--no-correction` for comparison
- `pdf-priority` — generates top 5,000 priority PMIDs

### 6. Updated exports (`scripts/utils/__init__.py`)

Added all new functions to module exports.

## Deviation from Plan: `best_od_rate` instead of `pdf_od_rate`

The original plan specified using `pdf_od_rate` for journal corrections. During
testing, 59 funders showed `corrected_pct < open_data_pct` — a logical
impossibility (correction should only increase estimates). Root cause: the plan's
formula `corrected_od = pdf_covered_od + Σ(n_xml_only_j × pdf_rate_j)` replaces
XML-detected OD entirely with PDF estimates, but some funders have anomalously
high XML detection in specific journals.

**Fix applied:**
1. Switched from `pdf_od_rate` to `best_od_rate` (PDF∪XML union), which matches
   what `is_open_data_best` would yield with full coverage
2. Added flooring: `corrected_od = max(corrected_od, observed_od)` to guarantee
   the monotonicity invariant

After fix: zero violations across all 816 funders.

## Key Results

### Correction factor statistics

```
676 journals with head-to-head data (min 50 articles each)
Global best OD rate: 16.0% (PDF: 16.0%, n=268,512)
174,303 funder×journal XML-only rows
```

### Impact on major funders (table-level, ≥1,593 articles)

| Funder | Observed | Estimated | 95% CI |
|---|---|---|---|
| National Science Foundation (Sri Lanka) | 27.7% | 31.3% | 30.7–31.8% |
| National Science Foundation (USA) | 24.7% | 27.3% | 26.7–28.0% |
| Wellcome Trust | 24.1% | 26.1% | 25.6–26.7% |
| Deutsche Forschungsgemeinschaft | 21.6% | 24.5% | 23.9–25.3% |
| National Institutes of Health | 20.5% | 22.7% | 22.1–23.4% |
| UK Research and Innovation | 19.4% | 23.2% | 22.7–23.8% |
| European Commission | 19.3% | 21.1% | 20.5–21.8% |

Typical correction: +2 to +4 percentage points. Largest corrections for funders
concentrated in journals with high XML miss rates.

### PDF priority list

```
319,711 candidate rows → 81,332 unique PMIDs → top 5,000 output
Top journals: Nature Communications (816), Ecology and Evolution (678),
eLife (416), PLoS Pathogens (321), PLoS Computational Biology (313)
```

## Verification

All invariants passed:
- `corrected_pct >= open_data_pct` for all 816 funders (0 violations)
- `ci_lo_pct <= corrected_pct <= ci_hi_pct` for all funders (0 violations)
- `--no-correction` produces backward-compatible output (5-column table, no CIs)
- Bar chart shows dual segments and error whiskers visually
- PDF priority list top entries are from high-miss-rate journals (Nature Genetics,
  Nature Structural & Molecular Biology)

## Output Files

| Output | Path | Details |
|---|---|---|
| LaTeX table (corrected) | `latex/tables/table_funders_2024_2025.tex` | 42 funders, 6 columns |
| Bar chart (corrected) | `latex/figures/funders_open_data_2024_2025.png` | 24 funders, dual bars + whiskers |
| CSV (corrected) | `results/funders_summary_2024_2025.csv` | 816 funders, with corrected cols |
| Markdown (corrected) | `results/funders_summary_2024_2025.md` | 816 funders, with CIs |
| LaTeX table (raw) | `latex/tables/table_funders_2024_2025_raw.tex` | 42 funders, 5 columns |
| Bar chart (raw) | `latex/figures/funders_open_data_2024_2025_raw.png` | 24 funders, single bars |
| CSV (raw) | `results/funders_summary_2024_2025_raw.csv` | 816 funders, no correction |
| PDF priority list | `results/pdf_priority_list.csv` | 5,000 PMIDs ranked by impact |

## Files Modified/Created

| File | Action | Lines changed |
|---|---|---|
| `scripts/utils/data_loader.py` | Modified | +~140 lines (new queries, helper) |
| `scripts/utils/correction.py` | Created | ~130 lines |
| `scripts/utils/__init__.py` | Modified | +12 lines (new exports) |
| `scripts/table_funders.py` | Modified | +~200 lines (correction integration) |
| `scripts/pdf_priority_list.py` | Created | ~150 lines |
| `Makefile` | Modified | +20 lines (new targets) |

## Next Steps

1. **Commit** all changes on `funder_fig` branch
2. **LaTeX compilation** — verify the 6-column table compiles on Overleaf
3. **Manuscript text** — update methods/results sections to describe the
   correction methodology
4. **Strategic PDF download** — use `results/pdf_priority_list.csv` to batch
   download top 5K PDFs via PaperPile, re-run oddpub on them, and regenerate
   tables to narrow the correction gap
5. **Consider** whether to sort the table by corrected rate instead of observed
