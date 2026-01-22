# Implementation Plan: OSM Preprint 2026 - LaTeX Skeleton

## Overview

Create a complete LaTeX preprint skeleton with Git/GitHub/Overleaf integration for the Open Science Metrics project. The preprint will document open data sharing trends across ~326k biomedical articles (growing to ~618k), focusing on PDF-based detection improvements over XML (~13.5% vs 6.8% open data rates).

**Primary Goals:**
1. Initialize osm-preprint-2026 as a git repository with GitHub (private) and Overleaf integration
2. Create modular LaTeX document structure (single-column article format)
3. Implement Python scripts to auto-generate 4 tables/figures from parquet data
4. Integrate into meta-repository documentation
5. Design for easy data updates as corpus grows

**Timeline:** Skeleton ready for one-week sprint to near-complete draft

---

## Directory Structure

```
/home/adamt/claude/osm/osm-preprint-2026/
├── .git/                           # Git repository
├── .gitignore                      # Standard LaTeX + Python ignores
├── README.md                       # Minimal description (5-10 lines)
├── CLAUDE.md                       # Comprehensive guide (200-400 lines)
├── LICENSE                         # CC0 1.0 Universal or similar
│
├── docs/                           # Documentation
│   └── IMPLEMENTATION_PLAN.md      # This plan document
│
├── latex/                          # LaTeX source files
│   ├── main.tex                    # Main document entry point
│   ├── preamble.tex                # Packages, formatting, colors
│   ├── metadata.tex                # Title, authors, affiliations
│   ├── article.tex                 # Main content (abstract, intro, methods, results, discussion)
│   ├── references.bib              # BibTeX bibliography
│   ├── tables/                     # Generated LaTeX tables (committed to git)
│   │   ├── table_funders.tex
│   │   ├── table_journals.tex
│   │   ├── table_institutions.tex
│   │   └── table_repositories.tex
│   └── figures/                    # Generated PNG graphs (committed to git)
│       ├── funders_open_data.png
│       ├── journals_open_data.png
│       ├── institutions_open_data.png
│       └── repositories_mentions.png
│
├── scripts/                        # Python data processing scripts
│   ├── requirements.txt            # pandas, duckdb, matplotlib, seaborn
│   ├── generate_all_tables.py      # Master script - regenerate all 4 tables
│   ├── table_funders.py            # Funder table generation (PRIMARY)
│   ├── table_journals.py           # Journal table generation
│   ├── table_institutions.py       # Institution table generation (basic extraction)
│   ├── table_repositories.py       # Repository table generation (basic extraction)
│   ├── utils/                      # Shared utilities
│   │   ├── latex_helpers.py        # escape_latex, get_color_bwr, format_number
│   │   └── data_loader.py          # DuckDB parquet queries
│   └── funder_aliases_v4.csv       # Copy from osm-2025-12-poster-incf
│
├── results/                        # CSV summaries for reproducibility
│   ├── funders_summary.csv
│   ├── journals_summary.csv
│   ├── institutions_summary.csv
│   └── repositories_summary.csv
│
└── Makefile                        # Build automation (tables, compile, clean)
```

**Key Design Decision:** Generated tables and figures are committed to git and pushed to both GitHub and Overleaf (simpler workflow than selective pushing).

---

## LaTeX Architecture

### Document Class: Single-Column Article

```latex
\documentclass[11pt,letterpaper]{article}
```

**Rationale:** Standard arXiv/bioRxiv format, easier to read on screen, simpler layout than two-column.

### Package Structure (preamble.tex)

Reuse poster design elements with adaptations for article format:

```latex
% Fonts & Encoding
\usepackage[T1]{fontenc}
\usepackage[sfdefault]{roboto}          % Reuse poster font

% Layout
\usepackage[margin=1in]{geometry}
\usepackage{fancyhdr}
\usepackage{parskip}                     % Spacing between paragraphs

% Colors (reuse poster palette)
\usepackage[table]{xcolor}
\definecolor{COLprimary}{HTML}{38761d}   % Forest green
\definecolor{COL5}{HTML}{4472C4}         % Blue for tables
\rowcolors{2}{COL5!10}{white}            % Alternating table rows

% Tables & Numbers
\usepackage{booktabs}                    % Professional table rules
\usepackage{longtable}                   % Multi-page tables
\usepackage{pdflscape}                   # Landscape orientation if needed
\usepackage{siunitx}                     % Numeric alignment
\sisetup{
    group-separator={,},
    group-minimum-digits=4
}

% Graphics
\usepackage{graphicx}
\usepackage{caption}
\usepackage{subcaption}

% Bibliography (PaperPile integration)
\usepackage[
    backend=biber,
    style=science,
    maxcitenames=2,
    maxbibnames=99,
    sorting=none,
    doi=true,
    url=false
]{biblatex}
\addbibresource{references.bib}  % PaperPile dynamic export

% Hyperlinks
\usepackage{hyperref}
\hypersetup{
    colorlinks=true,
    linkcolor=COLprimary,
    citecolor=COLprimary,
    urlcolor=COLprimary
}
```

### Main Document Structure (main.tex)

```latex
\documentclass[11pt,letterpaper]{article}
\input{preamble.tex}
\input{metadata.tex}

\begin{document}

\maketitle

% Main article content (abstract, introduction, methods, results, discussion)
\input{article.tex}

\printbibliography

\appendix
\section{Supplementary Tables}
\input{tables/table_funders.tex}
\input{tables/table_journals.tex}
\input{tables/table_institutions.tex}
\input{tables/table_repositories.tex}

\end{document}
```

### Article Content Structure (article.tex)

The `article.tex` file contains all main content in a single file:

```latex
\begin{abstract}
[Abstract text: 150-250 words summarizing key findings...]
\end{abstract}

\section{Introduction}
[Introduction content: 2-3 pages of context and motivation...]

\section{Methods}
[Methods content: 2-3 pages describing pipeline, oddpub, PDF vs XML...]

\section{Results}
[Results content: 4-5 pages with narrative for all 4 figures/tables...]

\begin{quote}
\textbf{Interactive Exploration:} Readers can explore these results dynamically through our web dashboard at \url{https://www.opensciencemetrics.org}, which provides real-time filtering and visualization across multiple dimensions.
\end{quote}

\section{Discussion}
[Discussion content: 2-3 pages interpreting findings and limitations...]
```

**Note:** Tables in appendix using `longtable` for multi-page spanning if needed.

### Bibliography Management with PaperPile

The preprint uses PaperPile for reference management, integrated with Overleaf:

**PaperPile Dynamic BibTeX URL:**
```
https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib
```

**Overleaf Integration Steps:**
1. In Overleaf project, upload the dynamic BibTeX file from PaperPile
2. Set up automatic sync (Overleaf → Upload → From External URL)
3. References will auto-update when modified in PaperPile
4. Local compilation: Download `references.bib` from PaperPile URL periodically

**Local Workflow:**
```bash
# Download latest references from PaperPile
curl -o latex/references.bib https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib

# Compile with updated references
make compile
```

**Note:** The `references.bib` file should be committed to git for reproducibility, but can be updated from PaperPile as needed.

---

## Python Scripts: Table/Figure Generation

### Pattern: Adapt funder_table_latex.py

All scripts follow the pattern from `/home/adamt/claude/osm/osm-2025-12-poster-incf/analysis/funder_table_latex.py`:

1. Load data from parquet using DuckDB (memory-efficient)
2. Process/aggregate data with pandas
3. Generate LaTeX table with:
   - `\begingroup...\endgroup` scoping
   - `booktabs` styling (toprule, midrule, bottomrule)
   - `siunitx` S columns for numeric alignment
   - Conditional formatting with `get_color_bwr()` (blue-white-red gradient)
4. Output both LaTeX (.tex) and CSV summary

### Table 1: Top Funders (PRIMARY FINDING)

**Script:** `scripts/table_funders.py`

**Data Source:**
- oddpub results: `/data/adamt/osm/datafiles/oddpub_output/*.parquet`
- Funder metadata from OpenAlex or rtransparent
- Funder aliases: `scripts/funder_aliases_v4.csv` (copy from poster repo)

**Key Features:**
- Parent-child funder aggregation (e.g., NIH institutes → NIH)
- Top 50 funders by % open data or total publications
- Columns: Funder Name, Country, Total Pubs (2024-2026), Open Data Pubs, % Open Data
- Conditional formatting on % column (blue=low, red=high)

**Template:** `/home/adamt/claude/osm/osm-2025-12-poster-incf/analysis/funder_table_latex.py`

### Table 2: Top Journals

**Script:** `scripts/table_journals.py`

**Data Source:**
- oddpub results joined with OpenAlex metadata
- Field: `openalex.primary_location.source.display_name` (journal name)

**Key Features:**
- Top 50 journals by open data publications
- Columns: Journal Name, Publisher, Total Pubs, Open Data Pubs, % Open Data
- Conditional formatting on % column

**Reference Data:** `/home/adamt/claude/osm/brnch_oddpubv7minerU/results/xml_vs_mineru_journals/xml_vs_mineru_journals.csv`

### Table 3: Top Institutions (Basic Extraction)

**Script:** `scripts/table_institutions.py`

**Data Source:**
- OpenAlex metadata: `authorships[].institutions[].display_name`
- oddpub results for open data detection

**Key Features:**
- Basic extraction of top-level institution names
- Top 50 institutions by open data publications
- Columns: Institution Name, Country (if available), Total Pubs, Open Data Pubs, % Open Data
- **Note:** May need refinement later for institution name normalization

### Table 4: Top Repositories (Basic Extraction)

**Script:** `scripts/table_repositories.py`

**Data Source:**
- oddpub results: `open_data_category` field or raw text parsing
- Extract repository mentions (GenBank, Dryad, Zenodo, Figshare, etc.)

**Key Features:**
- Regex pattern matching for common repositories
- Top 30 repositories by unique article mentions
- Columns: Repository Name, Type (domain-specific/general), Unique Articles, % of All Data-Sharing Articles
- **Note:** May need refinement for URL normalization

### Interactive Dashboard Reference

In addition to the four static figure/table pairs, the preprint will direct readers to the interactive dashboard for dynamic exploration of the results:

**Dashboard URL:** https://www.opensciencemetrics.org

**Dashboard Features:**
- Real-time exploration of open data trends across funders, journals, institutions
- Interactive filtering by time period, country, research domain
- Powered by osm-dashboard repository (Streamlit + FastAPI + MongoDB)

**Integration in Results Section:**
The Results section (latex/sections/results.tex) should include a prominent callout/box directing readers to the dashboard:
```latex
\begin{quote}
\textbf{Interactive Exploration:} Readers can explore these results dynamically through our web dashboard at \url{https://www.opensciencemetrics.org}, which provides real-time filtering and visualization across multiple dimensions.
\end{quote}
```

### Utility Functions (scripts/utils/latex_helpers.py)

Copy from poster repo and adapt:

```python
def escape_latex(text: str) -> str:
    """Escape special LaTeX characters (&, %, $, #, _, {, }, ~, ^)."""

def get_color_bwr(value: float, min_val: float, max_val: float,
                  use_log: bool = False) -> str:
    """Generate blue-white-red color gradient for cellcolor."""

def format_number_siunitx(n: int) -> str:
    """Format integer for siunitx S column (no commas)."""

def generate_longtable_header(columns: list) -> str:
    """Generate longtable header with column specs."""
```

### Master Script (scripts/generate_all_tables.py)

```bash
python scripts/generate_all_tables.py \
    --data-dir /data/adamt/osm/datafiles/ \
    --output-dir latex/tables/ \
    --figures-dir latex/figures/ \
    --results-dir results/ \
    --force
```

Orchestrates all 4 table/figure generation scripts, handles paths, logging, and error reporting.

---

## Git/GitHub/Overleaf Integration

### Step 1: Initialize Git Repository

```bash
cd /home/adamt/claude/osm
mkdir -p osm-preprint-2026
cd osm-preprint-2026

# Create initial structure
mkdir -p latex/tables latex/figures scripts/utils results docs

# Initialize git
git init
git add README.md CLAUDE.md LICENSE .gitignore
git add latex/ scripts/ Makefile
git commit -m "Initial commit: LaTeX skeleton structure

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### Step 2: Create GitHub Repository (Private)

```bash
gh repo create nimh-dsst/osm-preprint-2026 \
    --private \
    --description "LaTeX preprint analyzing open data sharing trends in biomedical research (2024-2026)" \
    --source=. \
    --remote=origin \
    --push
```

### Step 3: Overleaf Integration

**Create Overleaf Project:**
1. Go to https://www.overleaf.com
2. Create new project: "OSM Preprint 2026"
3. Menu → Sync → Git
4. Copy Git URL: `https://git.overleaf.com/<project-id>`

**Add Overleaf Remote:**
```bash
git remote add overleaf https://git.overleaf.com/<project-id>
git push overleaf main

# Configure Overleaf compiler settings
# - Main document: latex/main.tex
# - Compiler: pdfLaTeX
# - LaTeX engine: 2023 or later
```

**Verify Remotes:**
```bash
git remote -v
# origin    git@github.com:nimh-dsst/osm-preprint-2026.git (fetch/push)
# overleaf  https://git.overleaf.com/<project-id> (fetch/push)
```

### Step 4: Standard Workflow (Simple - No Selective Pushing)

```bash
# Regenerate tables from updated data
make tables

# Review changes
git diff latex/tables/ latex/figures/

# Commit and push to both remotes
git add latex/ scripts/ results/
git commit -m "Update tables with latest dataset (326k → 618k articles)"
git push origin main
git push overleaf main
```

**Note:** Generated tables/figures are committed to git (unlike original complex plan). This is simpler but increases repo size. Consider `.gitattributes` for LFS if PNGs become too large.

### .gitignore

```gitignore
# LaTeX auxiliary files
*.aux
*.log
*.out
*.bbl
*.blg
*.bcf
*.run.xml
*.synctex.gz
*.fls
*.fdb_latexmk

# Python cache
__pycache__/
*.pyc
.venv/

# Large raw data (regenerate from /data/adamt/osm/)
*.parquet
*.duckdb

# OS files
.DS_Store
```

---

## Meta-Repository Integration

### Update /home/adamt/claude/osm/open-science-metrics/README.md

Add to "Related" section:

```markdown
| Repository | Description |
|------------|-------------|
| [osm-2025-12-poster-incf](https://github.com/nimh-dsst/osm-2025-12-poster-incf) | Analysis and visualizations for INCF 2025 conference poster on open science trends across 6.5M articles. |
| [osm-preprint-2026](https://github.com/nimh-dsst/osm-preprint-2026) | LaTeX preprint manuscript analyzing PDF-based vs XML-based open data detection across 326k-618k biomedical articles (2024-2026). |
```

### Update /home/adamt/claude/osm/open-science-metrics/CLAUDE.md

Add new section after osm-2025-12-poster-incf:

```markdown
### 5. osm-preprint-2026

**Purpose:** LaTeX preprint manuscript documenting open data sharing trends using PDF-based detection (MinerU + oddpub v7.2.3). Primary finding: 13.5% open data rate with PDF-based detection vs 6.8% with XML-based detection (+52% relative improvement).

**Tech Stack:**
- LaTeX (single-column article, biblatex science style)
- Python 3.11+ (pandas, duckdb, matplotlib)
- Git + GitHub (private) + Overleaf integration

**Key Directories:**
- `latex/` - Modular LaTeX source (main.tex, sections/, tables/, figures/)
- `scripts/` - Python table/figure generation (4 tables: funders, journals, institutions, repositories)
- `results/` - CSV summaries for reproducibility

**Data Sources:**
- oddpub results: `/data/adamt/osm/datafiles/oddpub_output/*.parquet` (~326k articles, growing to ~618k)
- OpenAlex metadata: `/data/adamt/osm/datafiles/pubmed_metadata/openalex_2024_2025.parquet`
- Funder aliases: `scripts/funder_aliases_v4.csv` (from osm-2025-12-poster-incf)

**Workflow:**
```bash
cd ~/claude/osm/osm-preprint-2026

# Regenerate tables from updated data
make tables

# Compile PDF locally
make compile

# Push to GitHub and Overleaf
git add latex/ scripts/ results/
git commit -m "Update with latest data"
git push origin main
git push overleaf main
```

**Primary Findings:**
- Top funders by open data percentage (NIH, Wellcome Trust, UKRI, etc.)
- Top journals (Nature Communications, eLife, PLOS, etc.)
- Top institutions (to be analyzed)
- Top repositories (GenBank, Zenodo, Dryad, etc.)

**Time Frame:** Jan 2024 - June 2026 (extensible)
```

---

## Data Update Workflow

### Scenario: Updating from 326k to 618k Articles

When new oddpub results are available:

```bash
# Step 1: Update data pipeline (in osm-pipeline)
cd ~/claude/osm/osm-pipeline
python hpc_scripts/merge_oddpub_results.py \
    --input-dir /data/adamt/osm/datafiles/oddpub_output/ \
    --output oddpub_v7.2.3_2026_full.parquet

# Step 2: Regenerate preprint tables (in osm-preprint-2026)
cd ~/claude/osm/osm-preprint-2026
make tables

# Step 3: Update LaTeX metadata
# Edit latex/metadata.tex:
# - Update article count: "analyzing 618,000 articles"
# - Update date range if needed: "January 2024 - June 2026"

# Step 4: Compile and verify
make compile
evince latex/main.pdf

# Step 5: Commit and push
git add latex/tables/ latex/figures/ results/ latex/metadata.tex
git commit -m "Update tables with full 618k article dataset"
git push origin main
git push overleaf main
```

### Makefile for Automation

```makefile
# Makefile for osm-preprint-2026

.PHONY: all clean tables compile help

all: tables compile

tables:
	python scripts/generate_all_tables.py \
		--data-dir /data/adamt/osm/datafiles/ \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--force

compile:
	cd latex && pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex

clean:
	cd latex && rm -f *.aux *.log *.out *.bbl *.blg *.bcf *.run.xml *.synctex.gz

help:
	@echo "make all      - Generate tables and compile PDF"
	@echo "make tables   - Regenerate all LaTeX tables and figures"
	@echo "make compile  - Compile LaTeX to PDF (requires tables)"
	@echo "make clean    - Remove LaTeX auxiliary files"
```

---

## Critical Files (Priority Order)

### Phase 1: Repository Structure
1. `.gitignore` - Standard LaTeX + Python ignores
2. `README.md` - Minimal project description (5-10 lines)
3. `LICENSE` - CC0 1.0 Universal or similar
4. `CLAUDE.md` - Comprehensive documentation (200-400 lines)
5. `docs/IMPLEMENTATION_PLAN.md` - Copy of this plan document

### Phase 2: LaTeX Skeleton
6. `latex/preamble.tex` - Package imports, colors, formatting
7. `latex/metadata.tex` - Title, authors, affiliations
8. `latex/main.tex` - Document structure
9. `latex/article.tex` - Main content (abstract, introduction, methods, results, discussion with dashboard callout)
10. `latex/references.bib` - Initial bibliography (download from PaperPile URL)

### Phase 3: Python Infrastructure
11. `scripts/requirements.txt` - pandas, duckdb, matplotlib, seaborn
12. `scripts/utils/latex_helpers.py` - Shared utility functions
13. `scripts/utils/data_loader.py` - DuckDB parquet queries
14. `scripts/funder_aliases_v4.csv` - Copy from poster repo

### Phase 4: Table Generation Scripts (in order of priority)
15. `scripts/table_funders.py` - PRIMARY FINDING table
16. `scripts/table_journals.py` - Journal analysis
17. `scripts/table_institutions.py` - Basic institution extraction
18. `scripts/table_repositories.py` - Basic repository extraction
19. `scripts/generate_all_tables.py` - Master orchestration script

### Phase 5: Build Automation
20. `Makefile` - Build automation targets

---

## Verification Strategy

### Phase 1: Repository Setup
```bash
# Verify git initialization
git status
git remote -v

# Verify GitHub repo created
gh repo view nimh-dsst/osm-preprint-2026

# Verify Overleaf remote
git ls-remote overleaf
```

### Phase 2: LaTeX Compilation
```bash
cd latex/
pdflatex main.tex
# Should complete without errors (even with placeholder sections)

# Check for errors
grep -i error main.log

# Clean build
make clean && make compile
evince main.pdf
```

### Phase 3: Python Scripts
```bash
# Test utility functions
python -c "from scripts.utils.latex_helpers import escape_latex; print(escape_latex('Test & 50%'))"

# Test funder table (with limit)
python scripts/table_funders.py --limit 10 --output test.tex
cat test.tex | grep "begin{tabular}"

# Test all tables
make tables
ls -lh latex/tables/ latex/figures/ results/
```

### Phase 4: End-to-End Workflow
```bash
# Full workflow
make clean
make all
evince latex/main.pdf

# Verify tables appear in PDF
# Verify figures render
# Verify bibliography compiles
```

### Phase 5: Git Sync
```bash
# Test push to both remotes
git add latex/tables/table_funders.tex
git commit -m "Test: Add generated funder table"
git push origin main
git push overleaf main

# Check Overleaf web UI
# Verify table appears in Overleaf compilation
```

---

## Success Criteria

**Minimal Viable Skeleton (ready for one-week sprint):**
- ✓ Git repo initialized with GitHub (private) and Overleaf remotes
- ✓ LaTeX compiles without errors
- ✓ All 4 table generation scripts work (even if data needs refinement)
- ✓ Makefile automates table regeneration and compilation
- ✓ Meta-repo documentation updated (README.md + CLAUDE.md)
- ✓ Sections have placeholder text indicating what content is needed
- ✓ Bibliography compiles (even if minimal entries)

**Near-Complete Draft (one-week goal):**
- ✓ Abstract written (150-250 words)
- ✓ Introduction (2-3 pages context + motivation)
- ✓ Methods (2-3 pages describing pipeline, oddpub, PDF vs XML)
- ✓ Results (4-5 pages with all 4 figures/tables + narrative)
- ✓ Discussion (2-3 pages interpreting findings + limitations)
- ✓ Bibliography (20-30 key references)
- ✓ All tables generated from current ~326k dataset
- ✓ All figures rendered as publication-quality PNGs

---

## Key Design Decisions Summary

1. **Single-column article format** - Simpler than two-column, standard for arXiv/bioRxiv
2. **Generated tables committed to git** - Simpler workflow than selective pushing
3. **Basic extraction for institutions/repositories** - Will refine later when analysis is complete
4. **Regenerate all graphs from scratch** - Use current ~326k dataset, not preliminary 100k graphs
5. **Reuse poster design elements** - Roboto font, forest green colors, biblatex science style
6. **DuckDB for data loading** - Memory-efficient parquet queries (100x faster than pandas)
7. **longtable for large tables** - Multi-page spanning in appendix
8. **Makefile automation** - One command to regenerate all tables and compile PDF

---

## Post-Implementation Next Steps

1. **Skeleton validation** - Verify all files compile and git workflow works
2. **Content sprint** - Fill in section placeholders with actual narrative
3. **Data refinement** - Improve institution name normalization, repository URL parsing
4. **Figure design** - Create publication-quality graphs (consider using seaborn/matplotlib)
5. **Bibliography expansion** - Add key references for open science, data sharing, oddpub
6. **Peer review** - Internal review before preprint submission
7. **Preprint submission** - Upload to bioRxiv or arXiv
