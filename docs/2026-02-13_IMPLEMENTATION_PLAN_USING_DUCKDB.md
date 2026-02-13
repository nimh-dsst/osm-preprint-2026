# Plan: Funder Table & Figure Generation from DuckDB (v2)

> Revised 2026-02-13. Supersedes `2026-02-11_IMPLEMENTATION_PLAN_USING_DUCKDB.md`.

## What Changed from v1

| Area | v1 | v2 |
|---|---|---|
| Funder names | Native-language names from DuckDB | English display names via aliases CSV + new mapping |
| Figure funder selection | Arbitrary min 100 articles → top 20 by % | Weibull 0.5% survival threshold (~15 largest funders) |
| Table funder selection | Arbitrary top 50 by % | Weibull 1% survival threshold (~40 largest funders) |
| Figure bar colors | Redundant gradient mapping % (same as bar width) | Color encodes total articles (log scale) with colorbar legend |
| Figure/table legends | None | Proper captions with methodology notes |
| Local LaTeX preview | Assumed system texlive (missing `siunitx`) | Reproducible env via `tectonic` (uv-managed) |
| Output formats | LaTeX + PNG + CSV | LaTeX + PNG + CSV + Markdown (with OpenAlex links) |

## Context

The funder data pipeline populates `pmid_registry.duckdb` with 27,465 funders and 10.5M article-funder relationships. The v1 implementation (completed 2026-02-11) successfully generates a table, figure, and CSV, but needs refinement in four areas: English display names, statistically-motivated funder selection, meaningful use of visual channels, and a markdown output with OpenAlex links.

### Key Data Facts

- **pmid_registry.duckdb**: 6.7M articles, 10.5M article-funder links, 27K funders
- **Coverage**: 2.6M funded articles with oddpub v7 results; ~228K with open data (10.3% funded baseline)
- **`display_name` = `canonical_name`** in DuckDB — OpenAlex stores native-language names, so English names must come from our own mapping
- **`parent_funder_id`**: ALL NULL — parent-child aggregation uses `funder_aliases_v4.csv`
- **Funder article distribution**: highly skewed (median 268, 99th pctl 14,489, max 386K)
- **Funder IDs**: format `F4320321001` → OpenAlex URL `https://openalex.org/funders/F4320321001`

## Files to Modify

| File | Action | Description |
|---|---|---|
| `scripts/table_funders.py` | MODIFY | All changes below |
| `scripts/utils/data_loader.py` | MODIFY | Add funder_id to queries |
| `Makefile` | MODIFY | Add `preview-table` target for local rendering |

Generated outputs (by running the script):
- `latex/tables/table_funders.tex` — longtable (~40 funders, Weibull 1% threshold)
- `latex/figures/funders_open_data.png` — horizontal bar chart (~15 funders, Weibull 0.5% threshold)
- `results/funders_summary.csv` — **all** funders ranked by open_data_pct (no size filter beyond min 100)
- `results/funders_summary.md` — **all** funders with clickable OpenAlex links (NEW)

## Implementation Details

### 1. English Display Names

**Problem:** OpenAlex `display_name` == `canonical_name` for all 27,465 funders. Non-English funders appear in their native language (e.g., "Schweizerischer Nationalfonds zur Förderung der Wissenschaftlichen Forschung").

**Solution:** Two-tier name resolution:

1. **Aliases CSV (already available):** The `canonical_name` column in `funder_aliases_v4.csv` already uses English names for most funders (e.g., "Swiss National Science Foundation"). For any funder that appears in the aliases CSV, use the aliases CSV `canonical_name` as the display name. This covers the 75 aliased funders. **This already works in v1** — aliased groups use the aliases CSV name as `display_name`.

2. **`ENGLISH_DISPLAY_NAMES` dict (new):** For unaliased funders that appear in the DuckDB with non-English names and end up in the top results, add a manual English mapping. Populate on first run by reviewing the top ~100 funders in the CSV output and adding translations for any non-English names that appear.

**Implementation in `build_funder_summary()`:**
- Aliased funders: no change needed (already use English aliases CSV name)
- Unaliased funders: look up in `ENGLISH_DISPLAY_NAMES`; if not found, use the DuckDB `canonical_name` as-is
- Add a `--warn-non-english` flag that logs any top-N funder names containing non-ASCII characters, to prompt the developer to add translations

### 2. Weibull-Based Threshold for Figure and Table

**Problem:** Showing top funders by % open data with a low arbitrary threshold (100 articles) surfaces tiny niche funders ("Michigan Technology Tri-Corridor", 133 articles) that large funders don't view as peers. The preprint aims to incentivize competition between major funders.

**Solution:** Fit a Weibull distribution to the log of funder article counts and use survival-function thresholds to select funders at two levels.

**Weibull fit results (from v1 data):**
- Distribution: `log(total_articles)` for 5,411 funders with ≥100 articles
- Weibull parameters: shape=1.109, loc=4.604, scale=1.306

| Output | Survival Level | Threshold | Funders Above |
|---|---|---|---|
| **Figure** | 0.5% | ~35,440 | ~15 |
| **Table** | 1% | ~17,646 | ~40 |
| **CSV/Markdown** | none (min 100) | 100 | ~5,400 |

The 0.5% survival threshold directly yields ~15 funders — no secondary cull needed. These are shown sorted by `open_data_pct` in the figure. The 1% threshold yields ~40 funders for the more detailed LaTeX table.

**Implementation:**

```python
def compute_weibull_threshold(article_counts, survival=0.01, min_articles=100):
    """
    Fit Weibull to log(article_counts) and return the threshold
    at the given survival probability.

    Returns:
        (threshold, n_above, weibull_params) tuple
    """
    from scipy.stats import weibull_min
    counts = article_counts[article_counts >= min_articles]
    log_counts = np.log(counts)
    shape, loc, scale = weibull_min.fit(log_counts)
    threshold_log = weibull_min.isf(survival, shape, loc=loc, scale=scale)
    threshold = int(np.exp(threshold_log))
    n_above = (counts >= threshold).sum()
    return threshold, n_above, (shape, loc, scale)
```

### 3. Figure Redesign: Meaningful Color + Legend

**Problem:** In v1, bar color is a blue-white-red gradient of `open_data_pct` — identical information to bar width. The color channel is wasted.

**Redesign:**
- **Bar width (x-axis):** % open data (the primary metric)
- **Bar color:** Total articles funded (log scale), using a sequential colormap (e.g., `viridis` or `YlOrRd`). This lets readers instantly see both the rate AND the volume for each funder.
- **Colorbar legend:** Vertical colorbar on the right labeled "Total Funded Articles" with log-scale tick labels (e.g., 1K, 10K, 100K)
- **Baseline line:** Dashed vertical line at the funded-article baseline (~10.3%) with annotation

**Figure caption (draft):**

> **Figure 1. Open data rates among the largest biomedical research funders.** Funders included are those exceeding the Weibull-derived 0.5% survival threshold for total funded article count (≥{threshold:,} articles with oddpub v7 coverage), ranked by percentage of articles containing an open data sharing statement. Bar color indicates the total number of funded articles (log scale; see colorbar). The dashed line marks the overall funded-article baseline ({baseline}%). Parent funders (e.g., NIH, UKRI) aggregate all child institutes with deduplicated article counts. Country codes in parentheses. Data source: PubMed articles (2000–2025) with OpenAlex funder metadata and oddpub v7.2.3 open data detection.

### 4. Table Legend (LaTeX)

**Table caption (draft):**

> **Table 1. Open data rates among major biomedical research funders.** Funders exceeding the Weibull-derived 1% survival threshold for total funded articles (≥{threshold:,} articles with oddpub v7 coverage), ranked by open data rate. Parent funders (e.g., NIH, UKRI) aggregate all child institutes with deduplicated article counts. Cell shading: Total Pubs uses a blue-to-red gradient on log scale; % Open Data uses a linear blue-to-red gradient. Full rankings for all {n_total:,} funders are available in the supplementary materials on GitHub.

### 5. Markdown Output with OpenAlex Links

**New output:** `results/funders_summary.md`

**Format:**

```markdown
# Funder Open Data Rankings

> Generated {date} from pmid_registry.duckdb
> {n_funders} funders with ≥100 funded articles and oddpub v7 coverage
> Funded-article baseline: {baseline}% open data

| Rank | Funder | Country | Total Pubs | Open Data | % Open Data | OpenAlex |
|---:|---|---|---:|---:|---:|---|
| 1 | Fondation Méditerranée Infection | France | 266 | 195 | 73.3% | [link](https://openalex.org/funders/F4320337199) |
| 2 | ... | ... | ... | ... | ... | ... |
```

**Implementation:**
- Add `funder_id` to the data pipeline (see data_loader changes below)
- For aliased parent groups (NIH, UKRI, European Commission): link to the parent's own funder_id if it exists in DuckDB, otherwise to the largest child's funder_id
- For unaliased funders: use the funder_id directly from the bulk stats query

### 6. Local LaTeX Preview

**Problem:** System texlive lacks `siunitx` and other packages. User doesn't want system package installs.

**Solution:** Use `tectonic`, a self-contained LaTeX engine that automatically downloads needed packages on first use. Install via `uv tool install` or download pre-built binary.

**Makefile addition:**

```makefile
# Local preview using tectonic (auto-downloads LaTeX packages)
preview-table: funder-table
	@echo "Rendering table preview..."
	tectonic latex/main.tex
	@echo "Preview: latex/main.pdf"
```

**Setup (one-time):**

```bash
# Option A: via uv
uv tool install tectonic

# Option B: pre-built binary
curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
```

`tectonic` handles multi-pass compilation (pdflatex → biber → pdflatex) in a single invocation and caches packages in `~/.cache/Tectonic/`. Sufficient for local review; Overleaf remains the canonical compilation platform.

## Summary of Code Changes

### `scripts/table_funders.py`

| Function / Constant | Change |
|---|---|
| `ENGLISH_DISPLAY_NAMES` | NEW dict: non-English DuckDB names → English for unaliased funders in top results |
| `compute_weibull_threshold()` | NEW: fits Weibull to log(article counts), returns threshold |
| `build_funder_summary()` | Add `funder_id` to output; apply English name resolution for unaliased funders |
| `generate_funder_bar_chart()` | Redesign: color = total articles (log scale, sequential colormap), add colorbar legend, use Weibull 0.5% threshold for selection, add figure caption |
| `generate_funder_latex_table()` | Use Weibull 1% threshold, update caption with methodology note |
| `save_summary_markdown()` | NEW: write markdown table with OpenAlex links for all funders |
| `main()` | Compute Weibull thresholds (0.5% for figure, 1% for table), pass to generators, call markdown output |

### `scripts/utils/data_loader.py`

| Function | Change |
|---|---|
| `query_funder_open_data_stats()` | Add `f.funder_id` to SELECT (one per canonical_name) |
| `query_funder_open_data_for_group()` | Return `funder_id` of the parent funder or largest child in the group |

### `Makefile`

| Target | Change |
|---|---|
| `preview-table` | NEW: render LaTeX locally via `tectonic` |

### Dependencies

Add `scipy` to `scripts/requirements.txt` for the Weibull fit.

---

## Next: Migrate from funder_aliases_v4.csv to v5

> Status: **PLANNED** — implement after context reset

### Why

The repo currently uses `scripts/funder_aliases_v4.csv` (134 rows, 10 columns), copied from the older `osm-2025-12-poster-incf` repo. The pipeline repo has `funder_aliases_v5.csv` (279 rows, 15 columns) which was built for the DuckDB pipeline and includes:

| Feature | v4 | v5 |
|---|---|---|
| Rows | 134 | 279 |
| Columns | 10 | 15 |
| `openalex_id` | No | Yes — DuckDB funder_id directly in CSV |
| `openalex_name` | No | Yes — exact DuckDB canonical_name |
| `openalex_country` | No | Yes — DuckDB country_code |
| `validation_status` | No | Yes — explicit_alias, fuzzy, etc. |
| Fuzzy matches | No | Yes — additional variants via fuzzy matching |

### What this enables

1. **Eliminate `ALIAS_TO_DB_NAME_OVERRIDES` dict** — v5 has `openalex_name` which IS the DuckDB canonical_name. No more accent/language mismatches.
2. **Eliminate `ENGLISH_DISPLAY_NAMES` dict** — v5 `canonical_name` is English, `openalex_name` is the DuckDB name. Use `canonical_name` for display, `openalex_name` for queries.
3. **Direct `openalex_id`** — No need to query DuckDB for funder_id; it's in the CSV.
4. **Fix NRF South Africa** — v5 likely has the South African NRF as a separate entry (v4 incorrectly aliases it as Korean NRF variant).
5. **More aliases** — 279 vs 134 rows means better coverage.

### Implementation plan

1. **Copy v5 to repo**: `cp ~/claude/osm/osm-pipeline/funder_analysis/funder_aliases_v5.csv scripts/funder_aliases_v5.csv`
2. **Rewrite `FunderNormalizer`** to use v5 columns:
   - Use `openalex_name` for DuckDB queries (replaces `_resolve_db_names` + overrides)
   - Use `canonical_name` for display (English names)
   - Use `openalex_id` for OpenAlex links (replaces funder_id queries)
   - Use `openalex_country` as fallback country
3. **Remove** `ALIAS_TO_DB_NAME_OVERRIDES` and `ENGLISH_DISPLAY_NAMES` dicts (or reduce to edge cases)
4. **Update** `query_funder_open_data_for_group()` — may no longer need the funder_id subquery
5. **Remove** `funder_aliases_v4.csv` from repo
6. **Test** and verify counts match or improve

### Known issues to verify in v5

- Does v5 have South African NRF as separate entry? (v4 bug)
- Does v5 include "Wellcome" as variant of "Wellcome Trust"? (v4 had it but DuckDB also has separate entry)
- Are there new parent-child relationships in v5?
- Verify `openalex_name` matches DuckDB `canonical_name` exactly for all rows

## Verification

```bash
source ~/claude/osm/venv/bin/activate

# Quick test
python scripts/table_funders.py --top-n-figure 10 --verbose

# Verify outputs
ls -la latex/tables/table_funders.tex latex/figures/funders_open_data.png \
      results/funders_summary.csv results/funders_summary.md

# Check figure shows only large funders
python -c "
import pandas as pd
df = pd.read_csv('results/funders_summary.csv')
print(f'Total funders in CSV: {len(df)}')
# Verify Weibull threshold was applied to table
"

# Check markdown has OpenAlex links
head -20 results/funders_summary.md

# Local LaTeX preview (requires tectonic)
make preview-table

# Full run
python scripts/table_funders.py --verbose
```
