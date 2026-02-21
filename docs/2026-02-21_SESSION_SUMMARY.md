# Session Summary — 2026-02-21

## Objective

Regenerate 2024-2025 filtered funder table/figure using newly-populated
`pub_date` and `is_research` columns in DuckDB, then compare with the
preliminary funder ranking analysis from the pipeline repo.

## What Was Done

### 1. Added date-precise and research-only filtering

Extended `data_loader.py` query functions with `date_from`, `date_to`, and
`research_only` parameters (in addition to existing `year_from`/`year_to`).
Updated `table_funders.py` CLI with `--date-from`, `--date-to`,
`--research-only` flags. Updated Makefile `funder-table-2024` target.

### 2. Regenerated 2024-2025 outputs

```
Filters: pub_date >= 2024-01-01, pub_date <= 2025-06-30, research only
638,256 funded research articles, 18,767 funders in bulk stats
Funded-article baseline: 105,963 / 638,256 = 16.6%
816 funders in summary (min 100 articles)
42 funders in table (Weibull 5%), 24 in figure (Weibull 3%)
```

### 3. Comparison with preliminary analysis

Compared the current 2024-2025 results against the preliminary
`osm-pipeline/results/open_data_by_funder/open_data_by_funder.csv`.

## Preliminary vs Current — Comparison Analysis

### Overview

| | Preliminary | Current (2024-2025) |
|---|---|---|
| Article pool | 98,382 overlap PMIDs | 951,949 research articles |
| Funded articles | 62,537 article-funder pairs | 638,256 funded research |
| Funder source | NER regex on rtransparent `fund_text` | OpenAlex `grants[]` metadata |
| Open data column | `is_open_data` (MinerU PDF oddpub) | `is_open_data_best` (best of XML + PDF v7) |
| Alias file | v4 (134 rows, 46 canonical funders) | v5 (279 rows, 133 canonical funders) |
| Min articles | 50 | 100 |
| Output funders | 47 | 816 |
| Baseline open data | ~30% (overlap cohort) | 16.6% |

All 47 matched funders show lower open data rates in the current analysis.
**Median change: -13.4pp**, range -30.0pp (HHMI) to -5.6pp (NHMRC).

### Factor 1: Selection bias in overlap cohort

The preliminary 98K articles required both MinerU-extracted PDFs AND
rtransparent PMC XML — a strict intersection biased toward PMC OA articles
from high-impact journals with strong data sharing mandates. The current
analysis covers all research articles with any oddpub v7 coverage.

### Factor 2: Funder attribution breadth (NER vs OpenAlex)

The preliminary used regex/NER matching on rtransparent `fund_text` from PMC
XML, capturing only funders mentioned in article text. OpenAlex's structured
`grants[]` metadata attributes ~3-13x more articles per funder (median 5x),
and these newly-attributed articles have lower open data rates on average.

### Factor 3: PDF vs XML detection sensitivity (REVISION NEEDED)

**This is a major confounding factor not yet quantified in the funder
analysis.** The preliminary analysis used PDF-based oddpub exclusively
(MinerU-extracted text), while the current analysis uses `is_open_data_best`
— which for 69% of articles (657,777 / 951,949) falls back to XML-only
oddpub detection.

Head-to-head comparison on 268,512 articles with BOTH XML and PDF processing
(2024-01 to 2025-06, research only):

| Detection method | Open data rate | Articles detected |
|---|---|---|
| XML oddpub v7 | 5.8% | 15,663 |
| PDF oddpub v7 | 16.0% | 42,935 |
| Best (union) | 16.0% | 42,935 |

- **PDF detects 2.74x more open data than XML** in head-to-head
- PDF finds 27,956 statements XML misses (10.4% of articles)
- XML finds only 684 statements PDF misses (0.3% of articles)
- The asymmetry is extreme: PDF captures nearly all XML detections plus 2x more

**Coverage breakdown** (951,949 research articles, 2024-01 to 2025-06):

| Coverage | Articles | % of total | OD rate (best) |
|---|---|---|---|
| XML only | 657,777 | 69.1% | 5.6% |
| Both XML + PDF | 268,512 | 28.2% | 16.0% |
| PDF only | 25,660 | 2.7% | 10.3% |

The 657K XML-only articles report 5.6% open data — but based on the 2.74x
head-to-head ratio, their true open data rate is likely ~15-16%, meaning we
are **missing ~65,000 open data statements** across the dataset.

This detection gap differentially affects funders: journals with high data
sharing mandates (Nature Communications, Scientific Reports, PLOS ONE) have
XML miss rates of 70-84%, meaning funders whose articles concentrate in these
journals are disproportionately undercounted.

### Factor 4: Date range and article type

No explicit date/type filter in preliminary; current filters to Jan 2024 -
Jun 2025 research articles. This should increase rates (open data is trending
up) but is overwhelmed by factors 1-3.

### Factor 5: Alias version (v4 → v5)

Minor: 134 → 279 alias entries, more NIH institutes captured. Affects
parent-child boundaries but negligible impact on rates.

## Revision Needed

The current comparison analysis in the session summary and the funder
table/figure have a significant methodological limitation: the `is_open_data_best`
column for 69% of articles relies on XML-only detection, which systematically
underestimates open data rates by ~2.74x compared to PDF-based detection.

### Next steps for the next agent session:

1. **Quantify each factor's contribution** to the preliminary-vs-current gap.
   For the 268K articles with both XML and PDF, compute funder-level rates
   using XML-only vs PDF-only vs best, to isolate the detection method effect
   from the selection bias and attribution breadth effects.

2. **Estimate missing open data statements.** For the 657K XML-only articles,
   apply journal-level correction factors derived from the 268K head-to-head
   set (see `~/claude/osm/osm-pipeline/docs/STRATEGIC_PDF_PRIORITIZATION_PLAN.md`
   — top 20 journals account for 61.4% of XML misses, with journal-specific
   miss rates from 30% to 84%).

3. **Add confidence intervals / error bars.** For each funder in the table and
   figure, compute an estimated range:
   - **Lower bound**: current `is_open_data_best` rate (conservative, XML-biased)
   - **Upper bound**: corrected rate assuming XML-only articles have the same
     PDF/XML ratio as the head-to-head set for articles in the same journals
   - This could be displayed as error bars on the bar chart and a range column
     in the table.

4. **Strategic PDF prioritization** is underway in `osm-pipeline` to
   selectively download PDFs for journals with highest XML miss rates. Once
   more PDFs are processed, the gap will narrow. Until then, the correction
   factors provide the best estimate.

### Key reference files

- Preliminary analysis script: `~/claude/osm/osm-pipeline/analysis/open_data_by_funder.py`
- Preliminary output: `~/claude/osm/osm-pipeline/results/open_data_by_funder/open_data_by_funder.csv`
- PDF prioritization plan: `~/claude/osm/osm-pipeline/docs/STRATEGIC_PDF_PRIORITIZATION_PLAN.md`
- Current funder script: `scripts/table_funders.py`
- Current DuckDB: `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`
- Detection gap data: 268K head-to-head articles, 2.74x PDF/XML ratio
