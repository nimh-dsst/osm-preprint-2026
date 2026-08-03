# Who Funds Open Data Sharing?

LaTeX manuscript and analysis code for a population-scale study of open data sharing across **951,949 open access biomedical research articles** (PubMed Central, January 2024 – June 2025).

## Preprint

**Who Funds Open Data Sharing? Analysis of data availability statements in biomedical publications**
Lawrimore J, Li C, Moraczewski D, Poline J-B, Thomas A. *bioRxiv* (2026).

📄 **[https://www.biorxiv.org/content/10.64898/2026.07.17.739022v1](https://www.biorxiv.org/content/10.64898/2026.07.17.739022v1)** — doi:10.64898/2026.07.17.739022

## Key Findings

- Overall open data rate of **8.7%**, rising to **11.7%** among funder-linked articles.
- Leading major funders reach observed rates of **20–24%**; smaller, mission-focused research organizations (e.g., EMBL) reach far higher.
- Top journals reach observed rates of **70–86%** (Nature Structural & Molecular Biology, Nature Genetics).
- Rates vary more than tenfold across funders and journals.
- PDF-first detection (MinerU + oddpub v7.2.3) finds substantially more data sharing statements than XML-based methods; journal-level correction factors adjust for differential PDF vs XML coverage.

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

- **Preprint (bioRxiv):** https://www.biorxiv.org/content/10.64898/2026.07.17.739022v1
- **Interactive Dashboard:** https://www.opensciencemetrics.org
- **Meta-Repo:** https://github.com/nimh-dsst/open-science-metrics

See [CLAUDE.md](CLAUDE.md) for detailed documentation.
