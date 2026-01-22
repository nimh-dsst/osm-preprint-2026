# CLAUDE.md

## Repository Overview

LaTeX preprint manuscript analyzing open data sharing trends across ~326,000 biomedical research articles from PubMed (2024-2026). Demonstrates that major funders, journals, and institutions achieve dramatically higher open data rates (up to 82%) compared to baseline (13.5%).

## Path Variables

**Development Machine (Curium/EC2):**
```bash
REPO_ROOT="/home/adamt/claude/osm/osm-preprint-2026"
DATA_DIR="/data/adamt/osm/datafiles"
ODDPUB_OUTPUT="$DATA_DIR/oddpub_output"
OPENALEX_DATA="$DATA_DIR/pubmed_metadata"
```

**HPC (Biowulf) - Currently Offline:**
```bash
# HPC offline for maintenance until Jan 26, 2026
# Data processing happens on HPC, preprint work on local machine
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
│   ├── generate_all_tables.py      # Master script - regenerate all tables
│   ├── table_funders.py            # Funder table (PRIMARY FINDING)
│   ├── table_journals.py           # Journal table
│   ├── table_institutions.py       # Institution table
│   ├── table_repositories.py       # Repository table
│   ├── utils/
│   │   ├── latex_helpers.py        # LaTeX formatting utilities
│   │   └── data_loader.py          # DuckDB parquet queries
│   ├── funder_aliases_v4.csv       # Funder normalization
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

### Compile LaTeX

```bash
cd ~/claude/osm/osm-preprint-2026

# Full compilation
make compile

# Or manually
cd latex && pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex

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
- **Location:** `scripts/funder_aliases_v4.csv`
- **Source:** Copied from osm-2025-12-poster-incf repo
- **Purpose:** Parent-child funder aggregation (e.g., NIH institutes → NIH)

## Python Dependencies

Key packages (see `scripts/requirements.txt`):
- `pandas` - Data manipulation
- `duckdb` - Memory-efficient parquet queries
- `matplotlib` - Figure generation
- `seaborn` - Statistical visualization
- `numpy` - Numerical operations

Install dependencies:
```bash
python -m venv venv
source venv/bin/activate
pip install -r scripts/requirements.txt
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

**Columns:** Funder Name, Country, Total Pubs, Open Data Pubs, % Open Data

**Features:**
- Parent-child aggregation using FunderNormalizer
- Top 50 funders by % open data
- Conditional formatting (blue-white-red gradient)
- Multi-page longtable

**Key Finding:** Major funders like NIH, Wellcome Trust, UKRI show 30-82% open data rates vs 13.5% baseline

### Table 2: Top Journals

**Columns:** Journal Name, Publisher, Total Pubs, Open Data Pubs, % Open Data

**Features:**
- Top 50 journals by open data publications
- Grouped by publisher
- Conditional formatting on % column

**Reference:** Preliminary results in `osm/brnch_oddpubv7minerU/results/xml_vs_mineru_journals/`

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
evince latex/main.pdf

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

1. **Top Funders:** Major public funders (NIH, Wellcome Trust, UKRI) show 30-82% open data rates
2. **Top Journals:** Open access journals (Nature Communications, eLife, PLOS) lead in open data
3. **Top Institutions:** Leading research institutions demonstrate higher compliance
4. **Top Repositories:** GenBank, Zenodo, Dryad dominate data sharing statements

**Baseline:** 13.5% open data rate across all recent open access PubMed articles (2024-2026)

**Methodology:** PDF-based detection (MinerU + oddpub v7.2.3) finds ~52% more open data statements than XML-based methods

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
- Use `Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>` for AI-assisted commits

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

- **Week 1 (Jan 20-26):** Skeleton implementation and initial draft
- **Week 2-3:** Content refinement, data updates (618k articles)
- **Week 4:** Internal review and revisions
- **Target Submission:** bioRxiv or arXiv preprint server

## Technical Notes

1. **Memory Efficiency:** Use DuckDB for querying large parquet files instead of loading entire datasets into pandas
2. **Reproducibility:** All generated tables/figures committed to git with corresponding CSV summaries in `results/`
3. **Overleaf Sync:** Bi-directional - changes in Overleaf can be pulled with `git pull overleaf main`
4. **LaTeX Compilation:** Requires 3 passes for references: pdflatex → biber → pdflatex → pdflatex
5. **Font Availability:** Roboto font must be installed system-wide for local compilation

## Troubleshooting

### LaTeX Compilation Errors
```bash
# Check log for errors
grep -i error latex/main.log

# Clean and rebuild
make clean && make compile

# Test individual components
cd latex && pdflatex preamble.tex
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
