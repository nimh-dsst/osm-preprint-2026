#!/usr/bin/env python3
"""
Generate repository adoption table, bar chart, CSV, and markdown summary.

Queries oddpub_v7_registry.duckdb for repository mentions in open data
statements, classifies by type, and produces:
  - latex/tables/table_repositories.tex      (longtable)
  - latex/figures/repositories_mentions.png   (bar chart by type)
  - results/repositories_summary.csv         (all repositories)
  - results/repositories_summary.md          (ranked table)
"""

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Allow running as `python scripts/table_repositories.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import (
    _find_duckdb_default,
    connect_duckdb_registry,
)
from utils.latex_helpers import (
    escape_latex,
    format_number_siunitx,
    get_color_bwr,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository definitions: name → {pattern, type, priority}
# Priority controls match order for NCBI deduplication: lower = matched first.
# Specific NCBI sub-resources have higher priority (lower number) than the
# NCBI catch-all so that "NCBI GenBank" counts under GenBank, not NCBI (other).
# ---------------------------------------------------------------------------
REPOSITORIES: dict[str, dict] = {
    # --- NCBI sub-resources (match first, priority < NCBI catch-all) ---
    "GenBank": {
        "pattern": r"genbank",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "GEO": {
        "pattern": r"gene expression omnibus|geo[\s\-]?(?:dataset|series|accession)|(?<!\w)geo(?:\s*accession|\s*database)|gse\d{3,}",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "SRA": {
        "pattern": r"sequence read archive|(?<!\w)sra(?:\s*accession|\s*database|\s*repository)|srr\d{4,}|srp\d{4,}",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "dbGaP": {
        "pattern": r"dbgap|database of genotypes and phenotypes|phs\d{6}",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "RefSeq": {
        "pattern": r"refseq|reference sequence database",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "PubChem": {
        "pattern": r"pubchem",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "dbSNP": {
        "pattern": r"dbsnp",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "ClinVar": {
        "pattern": r"clinvar",
        "type": "Domain-Specific",
        "priority": 10,
    },
    "NCBI (other)": {
        "pattern": r"(?<!\w)ncbi(?!\w)|national center for biotechnology information",
        "type": "Domain-Specific",
        "priority": 90,  # Match last among NCBI sub-resources
    },
    # --- Other domain-specific repositories ---
    "Protein Data Bank": {
        "pattern": r"protein data bank|(?<!\w)pdb(?:\s*accession|\s*database|\s*entry|\s*id|\s*code|\s*structure)|rcsb|wwpdb",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "UniProt": {
        "pattern": r"uniprot|swissprot|swiss-prot|trembl",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "EMBL-EBI": {
        "pattern": r"embl[\s\-]ebi|european bioinformatics institute|embl[\s\-](?:bank|nucleotide)|european nucleotide archive|(?<!\w)ena(?:\s*accession|\s*database)|ebi\.ac\.uk",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "ArrayExpress": {
        "pattern": r"arrayexpress|array express",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "DDBJ": {
        "pattern": r"ddbj|dna data bank of japan",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "MetaboLights": {
        "pattern": r"metabolights",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "PRIDE": {
        "pattern": r"pride(?:\s*archive|\s*database|\s*repository|\s*proteomics)|proteomexchange",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "FlowRepository": {
        "pattern": r"flowrepository",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "KEGG": {
        "pattern": r"(?<!\w)kegg(?!\w)",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "Ensembl": {
        "pattern": r"ensembl",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "TCGA": {
        "pattern": r"cancer genome atlas|(?<!\w)tcga(?!\w)",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "GDC": {
        "pattern": r"genomic data commons|(?<!\w)gdc(?:\s*portal|\s*data)",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "CCDC": {
        "pattern": r"cambridge crystallographic data centre|(?<!\w)ccdc(?:\s*\d+|\s*deposit)",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "ImmPort": {
        "pattern": r"immport",
        "type": "Domain-Specific",
        "priority": 20,
    },
    "MGnify": {
        "pattern": r"mgnify|ebi metagenomics",
        "type": "Domain-Specific",
        "priority": 20,
    },
    # --- General-purpose repositories ---
    "Zenodo": {
        "pattern": r"zenodo",
        "type": "General-Purpose",
        "priority": 30,
    },
    "Dryad": {
        "pattern": r"dryad",
        "type": "General-Purpose",
        "priority": 30,
    },
    "figshare": {
        "pattern": r"figshare",
        "type": "General-Purpose",
        "priority": 30,
    },
    "OSF": {
        "pattern": r"osf\.io|open science framework",
        "type": "General-Purpose",
        "priority": 30,
    },
    "Mendeley Data": {
        "pattern": r"mendeley data|data\.mendeley",
        "type": "General-Purpose",
        "priority": 30,
    },
    "Dataverse": {
        "pattern": r"dataverse",
        "type": "General-Purpose",
        "priority": 30,
    },
    "Kaggle": {
        "pattern": r"kaggle\.com|kaggle(?:\s*dataset)",
        "type": "General-Purpose",
        "priority": 30,
    },
    # --- Code repositories ---
    "GitHub": {
        "pattern": r"github\.com|github(?:\s*repository)",
        "type": "Code",
        "priority": 40,
    },
    "GitLab": {
        "pattern": r"gitlab\.com|gitlab(?:\s*repository)",
        "type": "Code",
        "priority": 40,
    },
    "Bitbucket": {
        "pattern": r"bitbucket",
        "type": "Code",
        "priority": 40,
    },
}

# Pre-compile all patterns
_COMPILED_PATTERNS: dict[str, re.Pattern] = {
    name: re.compile(info["pattern"], re.IGNORECASE)
    for name, info in REPOSITORIES.items()
}


# ---------------------------------------------------------------------------
# Query and count repository mentions
# ---------------------------------------------------------------------------
def count_repository_mentions(con) -> pd.DataFrame:
    """
    Count distinct articles mentioning each repository in open data statements.

    Uses NCBI deduplication: if an article mentions both "NCBI" and a specific
    NCBI sub-resource (GenBank, GEO, SRA, etc.), it counts only under the
    specific sub-resource, not under "NCBI (other)".

    Returns DataFrame with columns: repository, type, unique_articles
    """
    # Fetch all statements
    logger.info("Fetching XML statements...")
    xml_stmts = con.execute(
        "SELECT pmcid AS article_id, open_data_statements FROM statements_xml "
        "WHERE open_data_statements IS NOT NULL"
    ).fetchdf()
    logger.info("  %d XML statements", len(xml_stmts))

    logger.info("Fetching PDF statements...")
    pdf_stmts = con.execute(
        "SELECT pmid AS article_id, open_data_statements FROM statements_pdf "
        "WHERE open_data_statements IS NOT NULL"
    ).fetchdf()
    logger.info("  %d PDF statements", len(pdf_stmts))

    # Get total open data articles for percentage calculation
    total_od_xml = con.execute(
        "SELECT COUNT(*) FROM articles_xml WHERE is_open_data = true"
    ).fetchone()[0]
    total_od_pdf = con.execute(
        "SELECT COUNT(*) FROM articles_pdf WHERE is_open_data = true"
    ).fetchone()[0]
    total_od = total_od_xml + total_od_pdf
    logger.info("Total open data articles: %d (XML: %d, PDF: %d)", total_od, total_od_xml, total_od_pdf)

    # Sort repositories by priority for NCBI deduplication
    sorted_repos = sorted(REPOSITORIES.items(), key=lambda x: x[1]["priority"])

    # For each article, track which repos matched
    # article_id → set of repo names
    article_repos: dict[str, set] = {}

    # Process all statements (XML + PDF combined)
    all_stmts = pd.concat([xml_stmts, pdf_stmts], ignore_index=True)
    logger.info("Processing %d total statements...", len(all_stmts))

    for _, row in all_stmts.iterrows():
        aid = row["article_id"]
        text = str(row["open_data_statements"]).lower()
        if aid not in article_repos:
            article_repos[aid] = set()

        for repo_name, repo_info in sorted_repos:
            pattern = _COMPILED_PATTERNS[repo_name]
            if pattern.search(text):
                article_repos[aid].add(repo_name)

    # NCBI deduplication: remove "NCBI (other)" if any specific NCBI sub-resource matched
    ncbi_subs = {
        name for name, info in REPOSITORIES.items()
        if info["type"] == "Domain-Specific" and info["priority"] == 10
        and name != "NCBI (other)"
    }

    for aid, repos in article_repos.items():
        if "NCBI (other)" in repos and repos & ncbi_subs:
            repos.discard("NCBI (other)")

    # Count unique articles per repository
    repo_counts: dict[str, int] = {}
    for repos in article_repos.values():
        for repo in repos:
            repo_counts[repo] = repo_counts.get(repo, 0) + 1

    # Build result DataFrame
    rows = []
    for repo_name, repo_info in REPOSITORIES.items():
        count = repo_counts.get(repo_name, 0)
        if count > 0:
            rows.append({
                "repository": repo_name,
                "type": repo_info["type"],
                "unique_articles": count,
                "pct_of_od_articles": round(100.0 * count / total_od, 2) if total_od else 0.0,
            })

    df = pd.DataFrame(rows)
    df.sort_values("unique_articles", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger.info("Found %d repositories with mentions", len(df))
    return df, total_od


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------
def generate_repository_latex_table(
    df: pd.DataFrame,
    output_path: Path,
    top_n: int = 25,
    total_od: int = 0,
) -> None:
    """Write a longtable .tex file for top repositories."""
    top = df.head(top_n).copy()
    if top.empty:
        logger.warning("No repositories to write")
        return

    min_articles = top["unique_articles"].min()
    max_articles = top["unique_articles"].max()
    min_pct = top["pct_of_od_articles"].min()
    max_pct = top["pct_of_od_articles"].max()

    lines = []
    lines.append(r"% Auto-generated by scripts/table_repositories.py — do not edit manually")
    lines.append(r"\begingroup")
    lines.append(r"\arrayrulecolor{COL5}")
    lines.append(r"\rowcolors{2}{COL5!10}{white}")
    lines.append(r"\small")

    col_spec = r"p{5.0cm} l S[table-format=6.0] S[table-format=2.2]"
    n_cols = 4
    lines.append(rf"\begin{{longtable}}{{{col_spec}}}")

    caption = (
        r"Repository adoption in biomedical open data statements. "
        rf"Top {top_n} repositories ranked by unique article count, "
        r"identified by regex matching against open data statement text "
        r"from oddpub v7.2.3 analysis of PubMed Central articles. "
        r"Type indicates domain-specific (e.g., GenBank, GEO), "
        r"general-purpose (e.g., Zenodo, Dryad), or code repositories "
        r"(e.g., GitHub). "
        rf"Percentages are relative to {total_od:,} articles flagged as sharing open data. "
        r"NCBI sub-resources (GenBank, GEO, SRA, dbGaP) are counted individually; "
        r"``NCBI (other)'' captures remaining NCBI mentions not attributable to a specific database. "
        r"Cell shading: Unique Articles uses a blue-to-red gradient on log scale; "
        r"\% of OD Articles uses a linear blue-to-red gradient."
    )
    lines.append(rf"\caption{{{caption}}}")
    lines.append(r"\label{tab:repositories} \\")

    header_row = (
        r"\textbf{Repository} & \textbf{Type} & "
        r"{\textbf{Unique Articles}} & {\textbf{\% of OD Articles}} \\"
    )
    lines.append(r"\toprule")
    lines.append(header_row)
    lines.append(r"\midrule")
    lines.append(r"\endfirsthead")
    lines.append(r"\toprule")
    lines.append(header_row)
    lines.append(r"\midrule")
    lines.append(r"\endhead")
    lines.append(r"\midrule")
    lines.append(
        rf"\multicolumn{{{n_cols}}}{{r}}{{\textit{{Continued on next page\ldots}}}} \\"
    )
    lines.append(r"\endfoot")
    lines.append(r"\bottomrule")
    lines.append(r"\endlastfoot")

    # Data rows
    for _, row in top.iterrows():
        name = escape_latex(str(row["repository"]))
        rtype = escape_latex(str(row["type"]))
        articles = format_number_siunitx(row["unique_articles"])
        pct = f"{row['pct_of_od_articles']:.2f}"

        color_articles = get_color_bwr(row["unique_articles"], min_articles, max_articles, use_log=True)
        color_pct = get_color_bwr(row["pct_of_od_articles"], min_pct, max_pct)

        lines.append(
            f"{name} & {rtype} & "
            f"\\cellcolor{color_articles} {articles} & "
            f"\\cellcolor{color_pct} {pct} \\\\"
        )

    lines.append(r"\end{longtable}")
    lines.append(r"\arrayrulecolor{black}")
    lines.append(r"\endgroup")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote LaTeX table: %s (%d repositories)", output_path, len(top))


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------
TYPE_COLORS = {
    "Domain-Specific": "#4472C4",   # Blue (matches table row color)
    "General-Purpose": "#70AD47",   # Green
    "Code": "#FFC000",              # Gold
}


def generate_repository_bar_chart(
    df: pd.DataFrame,
    output_path: Path,
    top_n: int = 25,
    total_od: int = 0,
) -> None:
    """Horizontal bar chart of top repositories colored by type."""
    top = df.head(top_n).copy()
    if top.empty:
        logger.warning("No repositories for figure")
        return

    top = top.iloc[::-1]  # reverse so highest is at top
    n_repos = len(top)

    labels = top["repository"].values
    values = top["pct_of_od_articles"].values
    colors = [TYPE_COLORS.get(t, "#999999") for t in top["type"].values]

    fig, ax = plt.subplots(figsize=(10, 0.45 * n_repos + 2.0))

    bars = ax.barh(
        range(n_repos), values,
        color=colors, edgecolor="grey", linewidth=0.3,
    )

    # Value labels
    for bar, val, articles in zip(bars, values, top["unique_articles"].values):
        ax.text(
            bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}% ({articles:,})",
            va="center", fontsize=8,
        )

    ax.set_yticks(range(n_repos))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("% of Open Data Articles Mentioning Repository", fontsize=11)
    ax.set_title("Repository Adoption in Biomedical Open Data Statements", fontsize=13, fontweight="bold")

    # Legend for types
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=TYPE_COLORS["Domain-Specific"], edgecolor="grey", label="Domain-Specific"),
        Patch(facecolor=TYPE_COLORS["General-Purpose"], edgecolor="grey", label="General-Purpose"),
        Patch(facecolor=TYPE_COLORS["Code"], edgecolor="grey", label="Code"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9, framealpha=0.9)

    ax.set_xlim(0, values.max() * 1.20)
    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote figure: %s (%d repositories)", output_path, n_repos)


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------
def save_summary_csv(df: pd.DataFrame, output_path: Path) -> None:
    """Save the full repository summary as CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Wrote CSV summary: %s (%d rows)", output_path, len(df))


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------
def save_summary_markdown(
    df: pd.DataFrame,
    output_path: Path,
    total_od: int = 0,
) -> None:
    """Save the full repository summary as markdown."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("# Repository Adoption Rankings")
    lines.append("")
    lines.append(f"> Generated {date.today().isoformat()} from oddpub_v7_registry.duckdb")
    lines.append(f"> {len(df):,} repositories identified in open data statements")
    lines.append(f"> {total_od:,} total articles with open data flag")
    lines.append("")

    lines.append(
        "| Rank | Repository | Type | Unique Articles | % of OD Articles |"
    )
    lines.append(
        "|---:|---|---|---:|---:|"
    )

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        name = str(row["repository"])
        rtype = str(row["type"])
        articles = f"{int(row['unique_articles']):,}"
        pct = f"{row['pct_of_od_articles']:.2f}%"
        lines.append(f"| {rank} | {name} | {rtype} | {articles} | {pct} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote markdown summary: %s (%d rows)", output_path, len(df))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--duckdb-path",
        default=_find_duckdb_default("oddpub_v7_registry.duckdb"),
        help="Path to oddpub_v7_registry.duckdb",
    )
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "latex" / "tables"),
        help="Directory for LaTeX table output",
    )
    p.add_argument(
        "--figures-dir",
        default=str(Path(__file__).resolve().parent.parent / "latex" / "figures"),
        help="Directory for figure output",
    )
    p.add_argument(
        "--results-dir",
        default=str(Path(__file__).resolve().parent.parent / "results"),
        help="Directory for CSV and markdown output",
    )
    p.add_argument("--top-n", type=int, default=25, help="Number of repositories in table/figure (default: 25)")
    p.add_argument("--output-suffix", default="", help="Suffix for output filenames")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger.info("Connecting to DuckDB: %s", args.duckdb_path)
    con = connect_duckdb_registry(args.duckdb_path)

    # Count repository mentions
    logger.info("Counting repository mentions in open data statements...")
    repo_df, total_od = count_repository_mentions(con)
    logger.info("  %d repositories found", len(repo_df))

    if repo_df.empty:
        logger.error("No repository mentions found — aborting")
        sys.exit(1)

    # Print top results
    logger.info("Top 10 repositories:")
    for _, row in repo_df.head(10).iterrows():
        logger.info(
            "  %-25s  %7d articles  (%5.2f%%)  [%s]",
            row["repository"], row["unique_articles"],
            row["pct_of_od_articles"], row["type"],
        )

    suffix = args.output_suffix

    # Generate LaTeX table
    tex_path = Path(args.output_dir) / f"table_repositories{suffix}.tex"
    logger.info("Generating LaTeX table: %s", tex_path)
    generate_repository_latex_table(repo_df, tex_path, top_n=args.top_n, total_od=total_od)

    # Generate bar chart
    fig_path = Path(args.figures_dir) / f"repositories_mentions{suffix}.png"
    logger.info("Generating bar chart: %s", fig_path)
    generate_repository_bar_chart(repo_df, fig_path, top_n=args.top_n, total_od=total_od)

    # Save CSV
    csv_path = Path(args.results_dir) / f"repositories_summary{suffix}.csv"
    logger.info("Saving CSV summary: %s", csv_path)
    save_summary_csv(repo_df, csv_path)

    # Save markdown
    md_path = Path(args.results_dir) / f"repositories_summary{suffix}.md"
    logger.info("Saving markdown summary: %s", md_path)
    save_summary_markdown(repo_df, md_path, total_od=total_od)

    logger.info("Done! %d repositories processed.", len(repo_df))
    con.close()


if __name__ == "__main__":
    main()
