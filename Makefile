# Makefile for OSM Preprint 2026

.PHONY: all clean tables funder-table funder-table-2024 funder-table-2024-raw journal-table-2024 journal-table-2024-raw pdf-priority compare-iterations compile preview-table load-budgets push-overleaf push-all help

DUCKDB_PATH ?= $(or $(OSM_DUCKDB_PATH),$(wildcard ../datalad-osm/duckdbs/pmid_registry.duckdb),/data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb)

# Default target
all: tables compile

# Regenerate all LaTeX tables and figures
tables: funder-table funder-table-2024 journal-table-2024

# Funder table, figure, and CSV
funder-table:
	@echo "Generating funder table..."
	python scripts/table_funders.py \
		--duckdb-path $(DUCKDB_PATH) \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--verbose

# Funder table filtered to 2024-2025 research articles
funder-table-2024:
	@echo "Generating funder table (2024-01 to 2025-06, research only)..."
	python scripts/table_funders.py \
		--duckdb-path $(DUCKDB_PATH) \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--date-from 2024-01-01 --date-to 2025-06-30 \
		--research-only \
		--table-survival 0.05 --figure-survival 0.03 \
		--min-works-figure 100000 --min-works-table 50000 \
		--output-suffix _2024_2025 \
		--verbose

# Journal table filtered to 2024-2025 research articles
journal-table-2024:
	@echo "Generating journal table (2024-01 to 2025-06, research only)..."
	python scripts/table_journals.py \
		--duckdb-path $(DUCKDB_PATH) \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--date-from 2024-01-01 --date-to 2025-06-30 \
		--research-only \
		--table-survival 0.05 --figure-survival 0.02 \
		--output-suffix _2024_2025 \
		--verbose

# Journal table (2024-2025) WITHOUT correction factors for comparison
journal-table-2024-raw:
	@echo "Generating journal table (2024-2025, no correction)..."
	python scripts/table_journals.py \
		--duckdb-path $(DUCKDB_PATH) \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--date-from 2024-01-01 --date-to 2025-06-30 \
		--research-only \
		--table-survival 0.05 --figure-survival 0.02 \
		--no-correction \
		--output-suffix _2024_2025_raw \
		--verbose

# Funder table (2024-2025) WITHOUT correction factors for comparison
funder-table-2024-raw:
	@echo "Generating funder table (2024-2025, no correction)..."
	python scripts/table_funders.py \
		--duckdb-path $(DUCKDB_PATH) \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--date-from 2024-01-01 --date-to 2025-06-30 \
		--research-only \
		--table-survival 0.05 --figure-survival 0.03 \
		--no-correction \
		--output-suffix _2024_2025_raw \
		--verbose

# Generate prioritized PDF download list
pdf-priority:
	python scripts/pdf_priority_list.py \
		--duckdb-path $(DUCKDB_PATH) \
		--date-from 2024-01-01 --date-to 2025-06-30 --research-only \
		--top-n 5000 --output results/pdf_priority_list.csv --verbose

# Cross-iteration funder comparison
compare-iterations:
	python scripts/compare_iterations.py --chart --verbose

# Load funder budget data into DuckDB
load-budgets:
	@echo "Loading funder budget data into DuckDB..."
	python scripts/load_funder_budgets.py --verbose

# Compile LaTeX to PDF using tectonic + biber 2.17.
# Both binaries were manually downloaded and installed into ~/proj/osm/venv/bin/:
#   tectonic 0.15.0+20251006 (aarch64-apple-darwin) — from GitHub continuous release
#   biber 2.17 (darwin_universal) — from SourceForge, matches tectonic's bundled biblatex 3.17
# Brew versions of tectonic and biber have been uninstalled.
# Requires venv activated (or venv/bin first in PATH) so tectonic finds the matching biber.
compile:
	@echo "Compiling LaTeX to PDF (tectonic)..."
	cd latex && tectonic main.tex
	@echo "PDF generated: latex/main.pdf"

# Local preview: generate tables then compile
preview-table: funder-table
	@echo "Rendering table preview with tectonic..."
	cd latex && tectonic main.tex
	@echo "Preview: latex/main.pdf"

# Clean LaTeX auxiliary files
clean:
	@echo "Cleaning LaTeX auxiliary files..."
	cd latex && rm -f *.aux *.log *.out *.bbl *.blg *.bcf *.run.xml *.synctex.gz *.fls *.fdb_latexmk *.toc *.lof *.lot *.xdv

# Update references from PaperPile
update-refs:
	@echo "Downloading latest references from PaperPile..."
	curl -o latex/references.bib https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib
	@echo "References updated: latex/references.bib"

# Push flat LaTeX tree to Overleaf (overleaf-publish branch -> overleaf/master)
push-overleaf:
	@chmod +x scripts/push_overleaf.sh
	@./scripts/push_overleaf.sh

# Push current branch to GitHub, then publish LaTeX to Overleaf
push-all: push-overleaf
	@echo "Pushing to GitHub (current branch)..."
	git push origin HEAD
	@echo "Pushed to GitHub and Overleaf"

# Help target
help:
	@echo "OSM Preprint 2026 Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make all          - Generate tables and compile PDF (default)"
	@echo "  make tables       - Regenerate all tables (currently: funder-table)"
	@echo "  make funder-table - Generate funder table, figure, CSV, and markdown (all years)"
	@echo "  make funder-table-2024 - Same but filtered to 2024-2025 publications (with correction)"
	@echo "  make journal-table-2024 - Generate journal table, figure, CSV (2024-2025)"
	@echo "  make journal-table-2024-raw - Journal 2024-2025 without correction factors (comparison)"
	@echo "  make funder-table-2024-raw - Funder 2024-2025 without correction factors (comparison)"
	@echo "  make pdf-priority - Generate prioritized PDF download list"
	@echo "  make compare-iterations - Cross-iteration funder comparison (CSV, markdown, chart)"
	@echo "  make preview-table- Generate tables and render PDF locally (tectonic)"
	@echo "  make compile      - Compile LaTeX to PDF (tectonic + biber 2.17 from venv)"
	@echo "  make clean        - Remove LaTeX auxiliary files"
	@echo "  make update-refs  - Download latest references from PaperPile"
	@echo "  make push-overleaf - Sync latex/ to flat overleaf-publish branch and push to Overleaf"
	@echo "  make push-all     - Push to GitHub (HEAD) and Overleaf (via push-overleaf)"
	@echo "  make help         - Show this help message"
