# CLAUDE.md

## Repository Overview

LaTeX preprint manuscript analyzing open data sharing trends across ~326,000 biomedical research articles from PubMed (2024-2025). Demonstrates that major funders, journals, and institutions achieve dramatically higher open data rates (up to 82%) compared to baseline (13.5%).

## Current Status (2026-03-01)

**✅ Data Pipelines Complete:**
- Funder pipeline: table, figure, CSV, markdown with correction factors + 95% CIs
- Journal pipeline: table, figure, CSV, markdown with correction factors + 95% CIs
- DuckDB auto-detection works across Curium and MacBook Air
- LaTeX compiles via tectonic (`make compile`)

**🔧 Next Steps:**
1. Institution and repository table pipelines
2. Write manuscript content (abstract, intro, methods, results, discussion)
3. Internal review and revisions

**📊 Branch Strategy:**
- `main` — Default development branch
- `journal_fig` — Journal figure/correction factor work (active)

## Path Variables

**DuckDB auto-detection** (`_find_duckdb_default()` in `scripts/utils/data_loader.py`):
1. `OSM_DUCKDB_PATH` env var
2. Sibling repo: `../datalad-osm/duckdbs/pmid_registry.duckdb`
3. Curium fallback: `/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb`

**Development Machine (Curium/EC2):**
```bash
REPO_ROOT="/home/adamt/claude/osm/osm-preprint-2026"
DATA_DIR="/data/adamt/osm/datafiles"
```

**MacBook Air:**
```bash
REPO_ROOT="/Users/adamt/proj/osm/brnch_journalFig"
VENV="~/proj/osm/venv"  # shared venv with tectonic + biber in bin/
```

## Directory Structure

```
osm-preprint-2026/
├── docs/
│   └── IMPLEMENTATION_PLAN.md      # Detailed implementation plan
│
├── latex/
│   ├── main.tex                    # Main document entry point
│   ├── preamble.tex                # Package imports, colors, formatting
│   ├── metadata.tex                # Title, authors, affiliations
│   ├── article.tex                 # Main content (all sections)
│   ├── references.bib              # BibTeX (from PaperPile)
│   ├── tables/                     # Generated LaTeX tables
│   │   ├── table_funders.tex
│   │   ├── table_journals.tex
│   │   ├── table_institutions.tex
│   │   └── table_repositories.tex
│   └── figures/                    # Generated PNG graphs
│       ├── funders_open_data.png
│       ├── journals_open_data.png
│       ├── institutions_open_data.png
│       └── repositories_mentions.png
│
├── scripts/
│   ├── table_funders.py            # Funder table pipeline (with correction factors)
│   ├── table_journals.py           # Journal table pipeline (with correction factors)
│   ├── sensitivity_funder_framing.py # Observed vs corrected funder-ranking diagnostic
│   ├── pdf_priority_list.py        # Prioritized XML-only PMIDs for PDF download
│   ├── load_funder_budgets.py      # Load funder budget data into DuckDB
│   ├── compare_iterations.py       # Cross-iteration funder comparison
│   ├── utils/
│   │   ├── data_loader.py          # DuckDB queries + _find_duckdb_default()
│   │   ├── latex_helpers.py        # LaTeX formatting utilities
│   │   └── correction.py           # Wilson CIs, journal/funder correction factors
│   ├── funder_aliases_v5.csv       # Funder normalization (from osm-pipeline)
│   └── requirements.txt            # Python dependencies
│
└── results/                        # CSV summaries for reproducibility
    ├── funders_summary.csv
    ├── journals_summary.csv
    ├── institutions_summary.csv
    └── repositories_summary.csv
```

## Key Scripts & Commands

### Regenerate All Tables

```bash
cd ~/claude/osm/osm-preprint-2026

# Regenerate all 4 tables and figures
make tables

# Or run directly
python scripts/generate_all_tables.py \
    --data-dir /data/adamt/osm/datafiles/ \
    --output-dir latex/tables/ \
    --figures-dir latex/figures/ \
    --results-dir results/ \
    --force
```

### Funder Framing Sensitivity Diagnostic

```bash
# Compare observed vs correction-adjusted funder rankings (2024-2025 research-only)
~/proj/osm/venv/bin/python scripts/sensitivity_funder_framing.py --verbose
```

`scripts/sensitivity_funder_framing.py` is a read-only diagnostic for the T5
funder-framing decision (GitHub #9). It **reuses** the production funder pipeline
(`FunderNormalizer`, `build_funder_summary`, the DuckDB `query_*` helpers, and
`build_journal_correction_table`) with the same defaults as `make
funder-table-2024`, so it reconstructs the exact ~34-funder 2024-2025 leaderboard
in `latex/tables/table_funders_2024_2025.tex` (it does **not** parse `.tex`).

- **Inputs:** the 2024-2025 funder pipeline output (DuckDB registry; date range
  2024-01-01..2025-06-30, research-only, Weibull survival 0.05, min works 50000,
  min h2h 50). Requires the DuckDB content — if the annex pointer is unresolved,
  run `cd ../datalad-osm && datalad get duckdbs/pmid_registry.duckdb` first (the
  script exits non-zero with this hint).
- **Outputs:** `results/sensitivity_funder_framing.csv` (per-funder observed vs
  corrected rates, Wilson CIs, dense ranks, rank delta) and
  `results/sensitivity_funder_framing.png` (observed-vs-corrected scatter, colored
  by PDF coverage, with y=x identity line). Both are byte-deterministic.
- **What it measures:** Spearman ρ between observed and corrected rates, the max
  absolute rank delta and top movers, **adjacent-pair separability** (smallest gap
  between neighbouring corrected rates; how many adjacent pairs have overlapping
  corrected CIs), and a **±bias-perturbation reorder check** (`--bias-pt`, default
  1.0pt) — i.e. whether the leaderboard order is robust to the ~1pt
  representativeness bias, which is #21's stopping-rule input. (The earlier
  non-overlapping observed-vs-corrected CI count was removed as mechanical — it
  measured the size of a one-sided floored correction, not ranking sensitivity;
  see the correction comment on #9.)
- **Decision:** the team chose **Option B** (expand the PDF corpus to reduce the
  ~1pt representativeness bias; leaderboard order is already stable). Corpus
  expansion is tracked in #21; the deferred ranking-consistency fix is #20.

### Compile LaTeX

```bash
# Requires venv activated (tectonic + biber 2.17 in ~/proj/osm/venv/bin/)
source ~/proj/osm/venv/bin/activate
make compile   # uses tectonic (handles biber internally)

# Clean auxiliary files
make clean
```

### Update References from PaperPile

```bash
# Download latest references from PaperPile
curl -o latex/references.bib https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib

# Compile with updated references
make compile
```

### Git Workflow

```bash
# Standard workflow (push to GitHub and Overleaf)
git add latex/ scripts/ results/
git commit -m "Update with latest data"
git push origin main
git push overleaf main
```

## Data Sources

### oddpub Results
- **Location:** `/data/adamt/osm/datafiles/oddpub_output/*.parquet`
- **Records:** ~326k articles (growing to ~618k)
- **Time Frame:** January 2024 - June 2026
- **Fields Used:** `is_open_data`, `is_open_code`, `data_text`, `pmid`

### OpenAlex Metadata
- **Location:** `/data/adamt/osm/datafiles/pubmed_metadata/openalex_*.parquet`
- **Fields Used:**
  - `primary_location.source.display_name` (journal name)
  - `authorships[].institutions[].display_name` (institutions)
  - `grants[].funder_display_name` (funder names)

### Funder Aliases
- **Location:** `scripts/funder_aliases_v5.csv`
- **Source:** Copied from osm-pipeline/funder_analysis/
- **Purpose:** Parent-child funder aggregation (e.g., NIH institutes → NIH)
- **Key columns:** `openalex_name` (DuckDB canonical_name), `openalex_id` (funder_id), `canonical_name` (English display name)

## Python Dependencies

Key packages (see `scripts/requirements.txt`):
- `pandas` - Data manipulation
- `duckdb` - Memory-efficient parquet queries
- `matplotlib` - Figure generation
- `seaborn` - Statistical visualization
- `numpy` - Numerical operations

Install dependencies:
```bash
source ~/proj/osm/venv/bin/activate
uv pip install -r scripts/requirements.txt
```

## LaTeX Architecture

### Document Class
- Single-column article format (arXiv/bioRxiv standard)
- 11pt, letterpaper
- Roboto font (reused from poster)

### Key Packages
- `biblatex` with science style
- `booktabs` for professional tables
- `longtable` for multi-page tables
- `siunitx` for numeric alignment
- `xcolor` with table support for colored rows

### Color Scheme
- Primary: Forest green (#38761d)
- Table rows: Blue (#4472C4) alternating with white

## Table Generation Details

### Table 1: Top Funders (PRIMARY FINDING)

**Columns:** Funder Name, Country, Total Pubs, Open Data, % OD (obs.), % OD (est.)

**Features:**
- Parent-child aggregation using funder_aliases_v5.csv
- Weibull threshold + OpenAlex works-count filter
- Journal-level correction factors with Wilson 95% CIs
- Dual-bar chart (observed + corrected) with error whiskers

**Key Finding:** Major funders like NIH, Wellcome Trust, UKRI show 30-82% open data rates vs 16.6% funded baseline

### Table 2: Top Journals

**Columns:** Journal, Total Pubs, Open Data, % OD (obs.), % OD (est.)

**Features:**
- Journal-level correction factors with Wilson 95% CIs
- Weibull threshold (5% table / 2% figure)
- Dual-bar chart matching funder pattern
- 676 journals with h2h correction data (min 50 articles)

### Table 3: Top Institutions

**Columns:** Institution Name, Country, Total Pubs, Open Data Pubs, % Open Data

**Features:**
- Basic extraction from OpenAlex affiliations
- Top 50 institutions by open data publications
- May need refinement for name normalization

### Table 4: Top Repositories

**Columns:** Repository Name, Type, Unique Articles, % of Data-Sharing Articles

**Features:**
- Regex pattern matching for repository URLs
- Top 30 repositories (GenBank, Zenodo, Dryad, etc.)
- Domain-specific vs general-purpose classification

## Data Update Workflow

When new oddpub results are available (e.g., 326k → 618k articles):

```bash
# 1. Update data pipeline (in osm-pipeline repo)
cd ~/claude/osm/osm-pipeline
python hpc_scripts/merge_oddpub_results.py \
    --input-dir /data/adamt/osm/datafiles/oddpub_output/ \
    --output oddpub_v7.2.3_2026_full.parquet

# 2. Regenerate preprint tables
cd ~/claude/osm/osm-preprint-2026
make tables

# 3. Update LaTeX metadata
# Edit latex/metadata.tex: Update article count, date range

# 4. Compile and verify
make compile
evince latex/who-funds-open-science-2026.pdf

# 5. Commit and push
git add latex/tables/ latex/figures/ results/ latex/metadata.tex
git commit -m "Update tables with full 618k article dataset"
git push origin main
git push overleaf main
```

## Git Remotes

This repository has two remotes:

1. **GitHub (origin):** Private repository at nimh-dsst/osm-preprint-2026
   - Source control and collaboration
   - All files committed (including generated tables/figures)

2. **Overleaf (overleaf):** Git integration for real-time PDF preview
   - URL: `https://git.overleaf.com/<project-id>`
   - Compiler: pdfLaTeX
   - Main document: `latex/main.tex`

## Bibliography Management

**PaperPile Integration:**
- Dynamic BibTeX URL: `https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib`
- Overleaf configured to sync automatically from PaperPile
- Local compilation: Download references.bib periodically with curl

## Interactive Dashboard

**URL:** https://www.opensciencemetrics.org

**Repository:** osm-dashboard (Streamlit + FastAPI + MongoDB)

**Integration:** The Results section includes a prominent callout directing readers to explore the data interactively through the dashboard.

## Primary Findings

1. **Top Funders:** Major public funders (NIH, Wellcome Trust, UKRI) show 30-82% open data rates (16.6% funded baseline)
2. **Top Journals:** Nature Structural & Molecular Biology (86.1% obs., 91.7% est.), Nature Genetics (70.5% obs., 92.9% est.)
3. **Top Institutions:** Leading research institutions demonstrate higher compliance
4. **Top Repositories:** GenBank, Zenodo, Dryad dominate data sharing statements

**Baselines:** 8.7% overall (all articles), 16.6% funded-article baseline (2024-2025 research)

**Methodology:** PDF-based detection (MinerU + oddpub v7.2.3) finds ~52% more open data statements than XML-based methods. Journal-level correction factors with Wilson 95% CIs adjust for differential PDF/XML coverage.

## Development Guidelines

### LaTeX Best Practices
- Keep `article.tex` as single content file (not split by section)
- Use `\input{}` for modularity (preamble, metadata, tables)
- Test compilation after every significant change
- Use `make clean` before `make compile` to clear auxiliary files

### Python Best Practices
- Use DuckDB for parquet queries (100x faster than pandas for large files)
- Cache intermediate results in `data/cache/` as parquet
- All table scripts should output both LaTeX (.tex) and CSV summary
- Follow the pattern from `table_funders.py` for consistency

### Git Best Practices
- Commit generated tables/figures (they're small and aid reproducibility)
- Write descriptive commit messages
- Push to both remotes (GitHub and Overleaf)
- Use `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` for AI-assisted commits

## Cross-Repo Dependencies

### osm-pipeline
- **Purpose:** HPC processing, oddpub analysis, DuckDB registries
- **Used For:** Generating oddpub results (input to this repo)
- **Location:** `/home/adamt/claude/osm/osm-pipeline`

### osm-2025-12-poster-incf
- **Purpose:** Previous INCF 2025 poster (FROZEN)
- **Used For:** Funder aliases, table generation patterns, color scheme
- **Location:** `/home/adamt/claude/osm/osm-2025-12-poster-incf`

### osm-dashboard
- **Purpose:** Interactive web dashboard (Streamlit)
- **Used For:** Referenced in preprint for dynamic exploration
- **URL:** https://www.opensciencemetrics.org

### open-science-metrics (meta-repo)
- **Purpose:** Top-level documentation and architecture
- **Used For:** Project overview, component relationships
- **Location:** `/home/adamt/claude/osm/open-science-metrics`

## Timeline

- **Target Submission:** bioRxiv or arXiv preprint server

## Technical Notes

1. **Memory Efficiency:** Use DuckDB for querying large parquet files instead of loading entire datasets into pandas
2. **Reproducibility:** All generated tables/figures committed to git with corresponding CSV summaries in `results/`
3. **Overleaf Sync:** Bi-directional - changes in Overleaf can be pulled with `git pull overleaf main`
4. **LaTeX Compilation:** Uses tectonic (handles biber internally). Both binaries in `~/proj/osm/venv/bin/`
5. **Font Availability:** Roboto font bundled by tectonic

## Troubleshooting

### LaTeX Compilation Errors
```bash
# Clean and rebuild
make clean && make compile

# Verbose tectonic output
cd latex && tectonic --print main.tex
```

### Python Script Errors
```bash
# Test utility functions
python -c "from scripts.utils.latex_helpers import escape_latex; print(escape_latex('Test & 50%'))"

# Run with verbose logging
python scripts/table_funders.py --verbose --limit 10
```

### Git Sync Issues
```bash
# Check remotes
git remote -v

# Pull latest from Overleaf
git pull overleaf main

# Force push if needed (use with caution)
git push overleaf main --force
```

## Contact & Collaboration

**Repository:** https://github.com/nimh-dsst/osm-preprint-2026 (private)

**Dashboard:** https://www.opensciencemetrics.org

**Meta-Repo:** https://github.com/nimh-dsst/open-science-metrics
