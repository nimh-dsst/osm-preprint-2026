# Makefile for OSM Preprint 2026

.PHONY: all clean tables funder-table funder-table-2024 compile preview-table help

DUCKDB_PATH ?= /data/adamt/osm/datalad-osm/duckdbs/pmid_registry.duckdb

# Default target
all: tables compile

# Regenerate all LaTeX tables and figures
tables: funder-table funder-table-2024

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
		--output-suffix _2024_2025 \
		--verbose

# Compile LaTeX to PDF
compile:
	@echo "Compiling LaTeX to PDF..."
	cd latex && pdflatex main.tex
	cd latex && biber main
	cd latex && pdflatex main.tex
	cd latex && pdflatex main.tex
	@echo "PDF generated: latex/main.pdf"

# Local preview using tectonic (auto-downloads LaTeX packages)
preview-table: funder-table
	@echo "Rendering table preview with tectonic..."
	tectonic latex/main.tex
	@echo "Preview: latex/main.pdf"

# Clean LaTeX auxiliary files
clean:
	@echo "Cleaning LaTeX auxiliary files..."
	cd latex && rm -f *.aux *.log *.out *.bbl *.blg *.bcf *.run.xml *.synctex.gz *.fls *.fdb_latexmk *.toc *.lof *.lot

# Update references from PaperPile
update-refs:
	@echo "Downloading latest references from PaperPile..."
	curl -o latex/references.bib https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib
	@echo "References updated: latex/references.bib"

# Push to both GitHub and Overleaf
push-all:
	@echo "Pushing to GitHub and Overleaf..."
	git push origin main
	git push overleaf main
	@echo "Pushed to both remotes"

# Help target
help:
	@echo "OSM Preprint 2026 Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make all          - Generate tables and compile PDF (default)"
	@echo "  make tables       - Regenerate all tables (currently: funder-table)"
	@echo "  make funder-table - Generate funder table, figure, CSV, and markdown (all years)"
	@echo "  make funder-table-2024 - Same but filtered to 2024-2025 publications"
	@echo "  make preview-table- Generate tables and render PDF locally (tectonic)"
	@echo "  make compile      - Compile LaTeX to PDF (requires tables)"
	@echo "  make clean        - Remove LaTeX auxiliary files"
	@echo "  make update-refs  - Download latest references from PaperPile"
	@echo "  make push-all     - Push to both GitHub and Overleaf"
	@echo "  make help         - Show this help message"
