# Plan: Journal Open Data Figure & Table (`table_journals.py`)

## Context

The manuscript already has a working funder table/figure pipeline (`scripts/table_funders.py`, ~1,100 lines). The "Variation by Journal" subsection in `latex/article.tex` (lines 72-78) references `Figure~\ref{fig:journals}` and `Table~\ref{tab:journals}`, but these don't exist yet — only a placeholder `table_journals.tex` is present. This task creates the journal equivalent of the funder pipeline.

## Design Decisions

1. **Observed rates only** (no correction) — For journals, the correction factor is trivially the journal's own h2h best_od_rate, which doesn't add insight the way cross-journal corrections do for funders. Keeps the script simpler.

2. **No publisher grouping** — No publisher column exists in DuckDB. Adding one would require an external mapping CSV or OpenAlex API calls. Skip for now; rank journals individually.

3. **Rank by OD rate** (not volume) — With a minimum article threshold from Weibull, rank journals by `open_data_pct` descending. This surfaces the interesting story (Nature Communications at 45%, eLife, PLOS Genetics) rather than mega-journals with near-zero OD rates (Cureus 0.1%, MDPI titles).

4. **Weibull thresholds** — Reuse the same `compute_weibull_threshold()` approach from funders. The shape will differ for journals but the statistical framework is sound. No works-count dual filter (no equivalent for journals).

5. **Baseline** — Compute overall OD rate across all articles matching the date/research filters (not just "funded" baseline). Show as dashed vertical line on figure.

## Deliverables

| Output | Path |
|--------|------|
| Script | `scripts/table_journals.py` |
| LaTeX table | `latex/tables/table_journals_2024_2025.tex` |
| Bar chart | `latex/figures/journals_open_data_2024_2025.png` |
| CSV | `results/journals_summary_2024_2025.csv` |
| Markdown | `results/journals_summary_2024_2025.md` |
| Makefile target | `journal-table-2024` added to `Makefile` |
| Article figure | `\begin{figure}...\end{figure}` block added to `latex/article.tex` |

## Implementation Steps

### Step 1: Add `query_journal_open_data_stats()` to `scripts/utils/data_loader.py`

New function (parallel to `query_funder_open_data_stats()`):
```sql
SELECT journal,
       COUNT(*) AS total_articles,
       SUM(CASE WHEN is_open_data_best THEN 1 ELSE 0 END) AS open_data_articles,
       SUM(CASE WHEN is_open_code_best THEN 1 ELSE 0 END) AS open_code_articles,
       SUM(CASE WHEN has_oddpub_pdf_v7 THEN 1 ELSE 0 END) AS pdf_covered,
       SUM(CASE WHEN has_oddpub_xml_v7 AND NOT has_oddpub_pdf_v7 THEN 1 ELSE 0 END) AS xml_only
FROM pmids
WHERE journal IS NOT NULL
  AND (has_oddpub_xml_v7 OR has_oddpub_pdf_v7)
  {filter_clause}
GROUP BY journal
```
- Accepts same date/research filter kwargs as funder version
- Returns DataFrame with per-journal stats

Also add a small helper `query_baseline_od_rate()` that returns the overall OD rate across all matching articles.

### Step 2: Create `scripts/table_journals.py`

Structure (following `table_funders.py` pattern but simpler — no alias normalization, no correction):

**CLI arguments:**
- `--duckdb-path` (default: standard path)
- `--date-from`, `--date-to`, `--year-from`, `--year-to`
- `--research-only`
- `--output-dir`, `--figures-dir`, `--results-dir`
- `--output-suffix`
- `--figure-survival` (default 0.005)
- `--table-survival` (default 0.01)
- `--min-articles` (default 100)
- `--verbose`

**Main flow:**
1. Connect to DuckDB, query journal stats via `query_journal_open_data_stats()`
2. Compute baseline OD rate via `query_baseline_od_rate()`
3. Compute `open_data_pct` = `open_data_articles / total_articles * 100`
4. Sort by `open_data_pct` descending
5. Apply Weibull thresholds (reuse `compute_weibull_threshold()` from funders — extract to shared utility or import)
6. Generate outputs: LaTeX table, bar chart, CSV, markdown

**`generate_journal_bar_chart()`:**
- Horizontal bars, sorted highest OD % at top
- Color = total articles on LogNorm scale (YlOrRd colormap)
- Dashed baseline line with "Overall baseline: X.X%" label
- Labels: journal name (truncated if >50 chars)
- Value labels: "XX.X%" at bar end
- Figure sizing: `(10, 0.45 * n_journals + 2.0)`
- Save as PNG at 300 DPI

**`generate_journal_latex_table()`:**
- Longtable with columns: Journal Name | Total Pubs | Open Data | % Open Data
  - `p{6cm}` for journal name (wider than funder's 5.5cm — journal names can be long)
  - `S[table-format=6.0]` for Total Pubs
  - `S[table-format=5.0]` for Open Data
  - `S[table-format=2.1]` for % Open Data
- Cell coloring via `get_color_bwr()` (log scale for totals, linear for %)
- Alternating row colors, `\rowcolors{2}{COL5!10}{white}`
- Caption with Weibull threshold info and article count
- `\label{tab:journals_2024_2025}`

**CSV columns:** `journal, total_articles, open_data_articles, open_code_articles, open_data_pct, open_code_pct, pdf_covered, xml_only`

**Markdown:** Ranked table with `| Rank | Journal | Total Pubs | Open Data | % Open Data |`

### Step 3: Extract `compute_weibull_threshold()` for reuse

Currently defined inside `table_funders.py`. Either:
- (a) Import it from `table_funders` into `table_journals` — simple but creates a dependency
- (b) Move it to `scripts/utils/stats.py` — cleaner but touches `table_funders.py`

**Recommendation:** Option (a) — import from `table_funders.py`. It's a clean module-level function at line 312 with no funder-specific dependencies (takes a numpy array, returns threshold). Import as `from table_funders import compute_weibull_threshold`.

### Step 4: Update `latex/article.tex`

Add figure block in the "Variation by Journal" subsection (after line ~72), following the funder figure pattern:

```latex
\begin{figure}[htbp]
    \centering
    \includegraphics[width=\textwidth]{figures/journals_open_data_2024_2025.png}
    \caption{Open data rates among top journals...}
    \label{fig:journals}
\end{figure}
```

### Step 5: Update `Makefile`

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

Update `tables` target to include `journal-table-2024`.

## Key Files to Modify

| File | Action |
|------|--------|
| `scripts/utils/data_loader.py` | Add `query_journal_open_data_stats()`, `query_baseline_od_rate()` |
| `scripts/table_journals.py` | **New file** — main script |
| `latex/article.tex` | Add figure block in journal subsection |
| `Makefile` | Add `journal-table-2024` target, update `tables` |

## Existing Functions to Reuse

- `scripts/utils/data_loader.py`: `connect_duckdb_registry()`, `_build_filter_clause()`
- `scripts/utils/latex_helpers.py`: `escape_latex()`, `format_number_siunitx()`, `get_color_bwr()`
- `scripts/table_funders.py`: `compute_weibull_threshold()` (import)

## Verification

1. Run: `source ~/claude/osm/venv/bin/activate && cd ~/claude/osm/brnch_journalFig`
2. Run: `python scripts/table_journals.py --duckdb-path /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb --date-from 2024-01-01 --date-to 2025-06-30 --research-only --output-suffix _2024_2025 --verbose`
3. Check Nature Communications appears near top (~45% OD, ~15K articles)
4. Check Cureus/MDPI titles are low-ranked or below threshold
5. Verify figure has readable labels and dashed baseline
6. Compile LaTeX: `tectonic latex/main.tex` — confirm no errors
7. Verify CSV contains all journals with ≥100 articles
8. Verify markdown has correct ranks
