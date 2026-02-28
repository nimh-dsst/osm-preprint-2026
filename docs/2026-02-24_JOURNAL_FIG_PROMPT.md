# Continuation Prompt: Journal Open Data Figure & Table

## Task

Plan and implement `table_journals.py` — the journal equivalent of `table_funders.py`. This script should produce:

1. `latex/tables/table_journals_2024_2025.tex` — LaTeX longtable of top journals by open data rate
2. `latex/figures/journals_open_data_2024_2025.png` — horizontal bar chart of top journals
3. `results/journals_summary_2024_2025.csv` — full CSV of all journals (≥100 articles)
4. `results/journals_summary_2024_2025.md` — markdown with ranks

Add the figure to `latex/article.tex` in the "Variation by Journal" subsection (which already references `Figure~\ref{fig:journals}` and `Table~\ref{tab:journals}`).

## Data Source

All data lives in `pmid_registry.duckdb` at `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`. The `pmids` table has:

- `journal` (VARCHAR) — 7,684 distinct journals across 968K articles with oddpub coverage
- `is_open_data_best`, `is_open_code_best` — combined PDF∪XML detection flags
- `has_oddpub_xml_v7`, `has_oddpub_pdf_v7` — coverage flags
- `is_open_data_xml_v7`, `is_open_data_pdf_v7` — per-method detection
- `pub_date` (DATE), `is_research` (BOOLEAN) — for filtering

There is **no publisher column** in DuckDB. Publisher grouping would require an external mapping or OpenAlex lookup. Consider whether this is worth the complexity.

## Existing Infrastructure to Reuse

### From `scripts/table_funders.py` (pattern to follow):
- CLI args: `--duckdb-path`, `--date-from`, `--date-to`, `--research-only`, `--output-suffix`, `--verbose`
- Weibull threshold for figure/table cutoffs (`--figure-survival`, `--table-survival`)
- Journal-level correction factors already computed by `utils/data_loader.py:query_journal_correction_factors()` — for journals, correction is trivially the journal's own h2h rate
- `utils/latex_helpers.py` — `escape_latex()`, `format_number_siunitx()`, `get_color_bwr()`
- `utils/correction.py` — Wilson CI functions

### From `utils/data_loader.py` (already available):
- `connect_duckdb_registry()`
- `query_journal_correction_factors()` — returns per-journal h2h stats (h2h_n, xml_od_rate, pdf_od_rate, best_od_rate)
- `_build_filter_clause()` — date/year/research filter SQL builder

## Key Design Decisions to Plan

1. **What to show**: Observed rate only, or observed + corrected (like funders)? For journals, the correction is the journal's own best_od_rate from h2h data — so journals with both XML+PDF coverage get their true rate directly, while XML-only journals get a global correction. This is less interesting than for funders since journals don't aggregate across multiple detection methods.

2. **Publisher grouping**: The CLAUDE.md mentions grouping by publisher. Without a publisher column, options are:
   - Skip publisher grouping (simplest, just rank journals individually)
   - Add a manual publisher mapping CSV for top ~50 publishers
   - Query OpenAlex API for publisher info (adds network dependency)
   - Recommend: Start with individual journals, add publisher column from a small mapping CSV if time permits

3. **Filtering thresholds**: The funder table uses Weibull survival thresholds. Journals have a very different distribution (some mega-journals with 50K+ articles, long tail of small journals). Consider:
   - Weibull may still work but the shape will differ
   - Works-count dual filter doesn't apply (no equivalent for journals)
   - Simple article-count cutoffs may be more interpretable

4. **Which journals are interesting**: The top journals by article count include many MDPI journals (Sensors, Materials, Molecules) with very low OD rates (0.2–3.6%). The interesting story is the contrast between:
   - High-OD journals: Nature Communications (45.2%), eLife, PLOS Genetics
   - High-volume low-OD journals: Cureus (0.1%), MDPI titles
   - Consider showing top N by OD rate (with min articles) rather than top N by volume

5. **Figure design**: Follow the funder figure style (horizontal bars, color = total articles on log scale, dashed baseline). But with more journals (~30-50 may pass threshold), the chart may need to be taller.

## Sample Data (2024-2025 research articles)

Top journals by article count (with OD rates):
```
Scientific Reports        49,520 articles   11.7% OD
Cureus                    28,751            0.1%
PLoS ONE                  24,182            14.2%
Heliyon                   16,600            7.4%
Nature Communications     15,129            45.2%
Int J Molecular Sciences  14,269            7.1%
Sensors                   10,333            0.4%
J Clinical Medicine       8,679             0.3%
```

## Makefile Integration

Add targets:
```makefile
journal-table-2024:
    python scripts/table_journals.py \
        --duckdb-path $(DUCKDB_PATH) \
        --date-from 2024-01-01 --date-to 2025-06-30 \
        --research-only \
        --output-suffix _2024_2025 \
        --verbose
```

## Verification Checklist

- [ ] Nature Communications appears near the top (45.2% OD, 15K articles)
- [ ] Cureus/MDPI titles appear low or are filtered by OD rate ranking
- [ ] Figure renders with readable labels (journal names can be long)
- [ ] LaTeX table compiles with tectonic
- [ ] CSV contains all journals ≥100 articles
- [ ] Figure is included in `article.tex` with caption and `\label{fig:journals}`

## Environment

```bash
# Activate venv
source ~/claude/osm/venv/bin/activate

# Working directory
cd ~/claude/osm/brnch_journalFig

# DuckDB (read-only)
/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb

# Compile LaTeX locally
tectonic latex/main.tex

# Branch: journal_fig (branched from develop)
```

## Prior Art

- Funder figure/table: `scripts/table_funders.py` (1,100 lines, fully working)
- Poster journal comparison: `~/claude/osm/brnch_oddpubv7minerU/results/xml_vs_mineru_journals/`
- CLAUDE.md Table 2 spec: "Top 50 journals by open data publications, grouped by publisher"
