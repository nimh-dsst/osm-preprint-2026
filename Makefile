# Makefile for OSM Preprint 2026

.PHONY: all clean tables compile help

# Default target
all: tables compile

# Regenerate all LaTeX tables and figures
tables:
	@echo "Regenerating all tables and figures..."
	python scripts/generate_all_tables.py \
		--data-dir /data/adamt/osm/datafiles/ \
		--output-dir latex/tables/ \
		--figures-dir latex/figures/ \
		--results-dir results/ \
		--force

# Compile LaTeX to PDF
compile:
	@echo "Compiling LaTeX to PDF..."
	cd latex && pdflatex main.tex
	cd latex && biber main
	cd latex && pdflatex main.tex
	cd latex && pdflatex main.tex
	@echo "PDF generated: latex/main.pdf"

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
	@echo "  make tables       - Regenerate all LaTeX tables and figures"
	@echo "  make compile      - Compile LaTeX to PDF (requires tables)"
	@echo "  make clean        - Remove LaTeX auxiliary files"
	@echo "  make update-refs  - Download latest references from PaperPile"
	@echo "  make push-all     - Push to both GitHub and Overleaf"
	@echo "  make help         - Show this help message"
