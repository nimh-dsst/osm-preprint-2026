# Session Summary — 2026-02-26

## Objective

Create the journal open data figure and table pipeline (`table_journals.py`),
paralleling the existing funder pipeline. Then investigate whether journal-level
correction factors and confidence intervals should be added (given that 67.3% of
articles are XML-only with uneven coverage across journals).

Plan: `docs/2026-02-26-PLAN_JOURNAL_FIGURE.md`

## What Was Done

### Part 1: Journal Pipeline — Initial Implementation

#### 1. New query functions (`scripts/utils/data_loader.py`)

- `query_journal_open_data_stats(con, ...)` — per-journal stats from the
  `pmids` table: total_articles, open_data_articles, open_code_articles,
  pdf_covered, xml_only. Accepts same date/research filter kwargs as funder
  queries.
- `query_baseline_od_rate(con, ...)` — overall OD rate across all articles
  matching filters. Returns dict with total_articles, open_data_articles,
  baseline_pct.

#### 2. New script (`scripts/table_journals.py`)

Full pipeline following the funder pattern but simpler (no alias normalization,
no correction in this initial version):

- Queries DuckDB for per-journal stats
- Computes baseline OD rate (8.7% for 2024-2025 research articles)
- Applies Weibull thresholds (imported `compute_weibull_threshold` from
  `table_funders`)
- Generates four outputs:
  - `latex/tables/table_journals_2024_2025.tex` — longtable (63 journals at 5%
    survival, ≥1,832 articles)
  - `latex/figures/journals_open_data_2024_2025.png` — horizontal bar chart (38
    journals at 3% survival, ≥2,957 articles), 300 DPI
  - `results/journals_summary_2024_2025.csv` — 1,389 journals with ≥100 articles
  - `results/journals_summary_2024_2025.md` — ranked markdown table

Weibull note: The default survival parameters (0.5%/1%) were too strict for the
journal distribution, yielding only 4/8 journals. The Makefile target uses
`--table-survival 0.05 --figure-survival 0.03` for reasonable counts.

#### 3. LaTeX integration

- `latex/article.tex`: Added `\begin{figure}...\end{figure}` block in the
  "Variation by Journal" subsection with `\label{fig:journals}`. Updated
  table ref to `\ref{tab:journals_2024_2025}`.
- `latex/main.tex`: Updated `\input` to reference
  `tables/table_journals_2024_2025.tex`.

#### 4. Makefile

- Added `journal-table-2024` target with date/research/survival flags
- Added to `tables` phony target and help text

### Part 2: Correction Factor Analysis

After reviewing the initial (uncorrected) outputs, we investigated whether
journal OD rates should be corrected for differential PDF/XML coverage.

#### Key finding: PDF coverage varies enormously across journals

- Overall: 32.7% PDF-covered, 67.3% XML-only
- Distribution is bimodal: 677 journals at 0-10% PDF, 261 at 70-90% PDF
- Standard deviation of PDF coverage: 31.7% across large journals
- Examples: Heliyon has 0% PDF coverage (7.4% OD observed), Nature
  Biotechnology has 97.5% PDF (69.2% OD observed)

#### Rationale for adding correction

The observed `is_open_data_best` rate is a mixture of PDF-based and XML-based
detection. Since PDF finds ~52% more OD than XML, journals with low PDF coverage
have systematically depressed observed rates. The correction reweights:

```
corrected_od = pdf_covered_od + (n_xml_only × journal_h2h_best_od_rate)
```

The existing correction infrastructure (`correction.py`) already handles:
- Per-journal h2h correction factor computation
- Wilson score 95% CIs with uncertainty propagation
- Global fallback for journals without enough h2h data (≥50 articles)

The funder pipeline shows +20.6% median correction across funders — the journal
correction should have a similar or larger effect given the 67.3% XML-only rate.

#### Analysis documents

Five detailed analysis documents were saved to
`docs/journal_correction_analysis/`:
1. `DOCUMENT_1_JOURNAL_CORRECTION_ANALYSIS.md` — PDF coverage distribution
2. `DOCUMENT_2_CORRECTION_WORKFLOW.txt` — Existing correction code walkthrough
3. `DOCUMENT3_COMPREHENSIVE_SUMMARY_PDF_v_XML.md` — Full statistical summary
4. `DOCUMENT4_QUICK_REFERENCE.md` — Quick reference for correction pipeline
5. `DOCUMENT5_FINAL_SUMMARY.md` — Final synthesis and recommendation

#### Next steps plan

A plan for adding correction factors and CIs to the journal pipeline was written
to `docs/2026-02-26_PLAN_JOURNAL_CORRECTION_FACTOR_CI.md`. This covers:
- Adding `apply_journal_correction()` to `correction.py`
- Modifying `table_journals.py` to integrate the correction pipeline
- Updating the bar chart with dual bars + error whiskers
- Updating the LaTeX table with corrected % and CI columns

## Key Numbers

| Metric | Value |
|---|---|
| Total journals (≥100 articles) | 1,389 |
| Overall baseline OD rate | 8.7% |
| Weibull table threshold (5%) | ≥1,832 articles → 63 journals |
| Weibull figure threshold (3%) | ≥2,957 articles → 38 journals |
| Top journal by OD rate | Nature Structural & Molecular Biology (86.1%) |
| Nature Communications | 45.2% OD, 15,129 articles |
| Cureus (bottom) | 0.1% OD, 28,751 articles |

## Files Changed

| File | Action |
|---|---|
| `scripts/utils/data_loader.py` | Added `query_journal_open_data_stats()`, `query_baseline_od_rate()` |
| `scripts/table_journals.py` | **New** — full journal pipeline |
| `latex/article.tex` | Added figure block, updated table ref |
| `latex/main.tex` | Updated `\input` to `table_journals_2024_2025.tex` |
| `Makefile` | Added `journal-table-2024` target |
| `latex/tables/table_journals_2024_2025.tex` | **Generated** — 63-journal longtable |
| `latex/figures/journals_open_data_2024_2025.png` | **Generated** — 38-journal bar chart |
| `results/journals_summary_2024_2025.csv` | **Generated** — 1,389-journal CSV |
| `results/journals_summary_2024_2025.md` | **Generated** — ranked markdown |
| `docs/journal_correction_analysis/` | **New** — 5 analysis documents |
| `docs/2026-02-26-PLAN_JOURNAL_FIGURE.md` | **New** — initial implementation plan |
| `docs/2026-02-26_PLAN_JOURNAL_CORRECTION_FACTOR_CI.md` | **New** — correction factor plan |
