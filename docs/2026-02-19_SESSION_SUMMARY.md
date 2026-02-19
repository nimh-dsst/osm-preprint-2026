# Session Summary — 2026-02-19

## Objective

Implement the funder table generation pipeline from the plan approved earlier
today, then run end-to-end and compare with the preliminary funder ranking
analysis from `osm-pipeline`.

## What Was Done

### 1. Verified existing code and ran `table_funders.py`

All files specified in the plan had already been scaffolded during the planning
phase:

- `scripts/utils/data_loader.py` — 3 DuckDB query functions
  (`connect_duckdb_registry`, `query_funder_open_data_stats`,
  `query_funder_open_data_for_group`)
- `scripts/utils/__init__.py` — exports for the new functions
- `scripts/table_funders.py` — ~808-line main script with `FunderNormalizer`,
  Weibull thresholding, LaTeX longtable, bar chart, CSV, and markdown outputs
- `Makefile` — `funder-table` target pointing at DuckDB

Verified column names against the live DuckDB schema (the `pmids` table has
`is_open_data_best` and `is_open_code_best` composite columns, plus separate
`has_oddpub_xml_v7` / `has_oddpub_pdf_v7` flags — all used correctly in the
queries).

### 2. Successful end-to-end run

```
INFO: 27,304 funders in bulk stats
INFO: Funded-article baseline: 701,472 / 6,332,868 = 11.1%
INFO: 5,394 funders in summary (min 100 articles)
INFO: Weibull 0.5% figure threshold: >=30,845 → 14 funders
INFO: Weibull 1.0% table threshold:  >=15,702 → 40 funders
```

Four outputs generated:

| Output | Path | Details |
|---|---|---|
| LaTeX longtable | `latex/tables/table_funders.tex` | 40 funders, conditional cell shading |
| Bar chart (PNG) | `latex/figures/funders_open_data.png` | 14 funders, YlOrRd colormap |
| CSV | `results/funders_summary.csv` | 5,394 funders |
| Markdown | `results/funders_summary.md` | 5,394 funders with OpenAlex links |

### 3. Comparison with preliminary funder ranking

Compared the current DuckDB-based results against the earlier
`osm-pipeline/results/open_data_by_funder/open_data_by_funder.csv` (produced
2026-01-10 by `analysis/open_data_by_funder.py`). See analysis below.

## Preliminary vs Current Analysis — Key Differences

Every funder shows a **large drop in open data percentage** (median -20.7
percentage points). The five major factors driving this:

### Factor 1: Dataset size (98K → 6.3M articles)

The preliminary analysis used only the **MinerU + rtransparent overlap cohort**
of 98,382 PMIDs — articles that had both PDF-based oddpub processing and
XML-based rtransparent funder extraction. The current analysis queries all 6.3M
articles in `pmid_registry.duckdb` that have any oddpub v7 coverage (XML or
PDF). This is a **~64x increase** in the denominator.

### Factor 2: Funder source (NER text matching → OpenAlex grants)

The preliminary analysis extracted funders by running regex/NER matching on
rtransparent's `fund_text`, `fund_pmc_institute`, and `fund_pmc_source` columns
from PMC XML. This captured funders mentioned in the full text of a small number
of articles.

The current analysis uses OpenAlex's `grants[].funder` metadata joined via the
`article_funders` table (10.5M rows, 27K unique funders). OpenAlex has much
broader coverage — for example, NIH went from 19,037 to 353,324 matched articles
(18.6x), while some funders like the Russian Science Foundation grew 101x. The
broader matching means many articles are now attributed to funders that the
NER-based method missed — and these additional articles have lower open data
rates on average.

### Factor 3: Selection bias in the overlap cohort

The 98K overlap cohort was inherently biased toward **PMC Open Access articles
with both high-quality PDFs and XML full text**. These tend to come from
well-funded, high-impact journals with stronger data sharing mandates. The
current analysis includes the full spectrum of articles — many from journals and
regions with lower open data compliance — diluting the rates.

### Factor 4: Open data detection column

The preliminary analysis used `is_open_data` from `oddpub_mineru_merged.parquet`
(MinerU PDF-based oddpub only). The current analysis uses `is_open_data_best`,
a composite column that takes the best result between XML v7 and PDF v7 oddpub
processing. While `_best` should be at least as sensitive as PDF-only, the
different column provenance and processing pipeline versions may contribute
marginal differences.

### Factor 5: Alias version (v4 → v5)

The preliminary analysis used `funder_aliases_v4.csv` (134 rows, from the INCF
poster). The current analysis uses `funder_aliases_v5.csv` (279 rows, with
OpenAlex IDs). The expanded alias set affects parent-child aggregation boundaries
(e.g., more NIH institutes are now captured under the NIH umbrella), though this
factor is minor compared to the dataset size and funder source changes.

### Quantitative comparison (all 47 matched funders)

| Metric | Preliminary | Current |
|---|---|---|
| Total articles analyzed | 98,382 | 6,332,868 |
| Funder source | rtransparent NER | OpenAlex grants |
| Open data column | `is_open_data` (MinerU) | `is_open_data_best` (XML+PDF v7) |
| Overall baseline | 17.4% | 11.1% |
| NIH articles / % OD | 19,037 / 32.9% | 353,324 / 12.2% |
| Wellcome articles / % OD | 1,059 / 43.4% | 66,492 / 14.4% |
| HHMI articles / % OD | 251 / 64.9% | 9,771 / 24.6% |
| Median % OD change | — | -20.7 pp |
| Article count ratio (median) | — | 47x |

### Conclusion

The dominant factor is the **64x larger article denominator** combined with
**broader funder attribution via OpenAlex**. The preliminary analysis captured a
small, high-quality slice of the literature where both PDF processing and XML
funder text were available — articles disproportionately from top-tier OA
journals with strong data mandates. The current pipeline captures the full
breadth of funded biomedical research, revealing that open data rates among
funded articles (~11%) are closer to the overall population baseline (~8.7% for
all articles with funders) than the preliminary analysis suggested.

The relative rankings remain broadly consistent — funders like USDA, Dept of
Energy, and HHMI still rank near the top, while NNSFC and NRF Korea remain
near the bottom — validating the directional findings while correcting the
absolute magnitudes.
