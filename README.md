# OSM Preprint 2026

LaTeX preprint manuscript analyzing open data sharing trends across ~326,000 biomedical research articles from PubMed (2024-2025).

## Key Findings

- Major funders (NIH, Wellcome Trust, UKRI) achieve 30-82% open data rates vs 8.7% overall baseline
- Top journals (Nature Structural & Molecular Biology, Nature Genetics) exceed 70% observed, 90%+ estimated after correction
- Journal-level correction factors account for differential PDF vs XML coverage using Wilson 95% CIs
- PDF-based detection (MinerU + oddpub v7.2.3) finds ~52% more open data statements than XML-based methods

## Quick Start

```bash
# Activate shared venv (has tectonic, biber, and Python deps)
source ~/proj/osm/venv/bin/activate

# Regenerate all tables/figures
make tables

# Compile PDF
make compile

# See all targets
make help
```

## Structure

- `latex/` — LaTeX manuscript (compile with `make compile`)
- `scripts/` — Python data pipelines (DuckDB queries, correction factors, chart/table generation)
- `results/` — CSV and markdown summaries for reproducibility
- `docs/` — Session summaries, implementation plans

## Links

- **Interactive Dashboard:** https://www.opensciencemetrics.org
- **Repository:** https://github.com/nimh-dsst/osm-preprint-2026 (private)
- **Meta-Repo:** https://github.com/nimh-dsst/open-science-metrics

See [CLAUDE.md](CLAUDE.md) for detailed documentation.
