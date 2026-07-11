#!/usr/bin/env python3
"""
Generate journal open-data table, bar chart, CSV, and markdown summary.

Queries pmid_registry.duckdb for per-journal open data rates and produces:
  - latex/tables/table_journals.tex       (longtable, Weibull threshold)
  - latex/figures/journals_open_data.png   (bar chart, Weibull threshold)
  - results/journals_summary.csv          (all journals, min articles)
  - results/journals_summary.md           (ranked table)
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

# Allow running as `python scripts/table_journals.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import (
    _find_duckdb_default,
    connect_duckdb_registry,
    query_journal_open_data_stats,
    query_journal_correction_factors,
    query_baseline_od_rate,
)
from utils.latex_helpers import (
    escape_latex,
    format_number_siunitx,
    get_color_bwr,
)
from utils.correction import (
    build_journal_correction_table,
    apply_journal_correction,
)
from table_funders import compute_weibull_threshold

# OpenAlex source display names that are not real journals: records lacking a
# genuine journal source are sometimes assigned an aggregator/index name. These
# are excluded from the journal analysis. Matched case-insensitively and exactly
# against primary_location.source.display_name. (#33, review #7)
NON_JOURNAL_SOURCES = {
    "pubmed",
    "pubmed central",
    "europe pmc",
    "biorxiv",
    "medrxiv",
    "research square",
    "ssrn",
    "arxiv",
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------
def generate_journal_bar_chart(
    df: pd.DataFrame,
    output_path: Path,
    threshold: int = 0,
    baseline_pct: float | None = None,
) -> None:
    """Horizontal bar chart of journals above the Weibull threshold.

    If corrected_pct is available, draws dual-segment bars:
    - Full bar (lighter shade) = corrected_pct (estimated)
    - Inner bar (full opacity) = open_data_pct (observed)
    - Error whiskers from ci_lo_pct to ci_hi_pct
    """
    top = df[df["total_articles"] >= threshold].copy() if threshold > 0 else df.copy()
    top.sort_values("open_data_pct", ascending=False, inplace=True)

    if top.empty:
        logger.warning("No journals above threshold %d for figure", threshold)
        return

    has_correction = "corrected_pct" in top.columns and top["corrected_pct"].notna().any()

    top = top.iloc[::-1]  # reverse so highest is at top of chart
    n_journals = len(top)

    labels = [
        name[:50] + "..." if len(name) > 50 else name
        for name in top["journal"].values
    ]
    observed = top["open_data_pct"].values
    totals = top["total_articles"].values

    # Color: total articles on log scale using YlOrRd colormap
    norm = mcolors.LogNorm(vmin=max(totals.min(), 1), vmax=totals.max())
    cmap = plt.cm.YlOrRd
    colors = [cmap(norm(t)) for t in totals]
    colors_light = [(*c[:3], 0.35) for c in colors]

    fig, ax = plt.subplots(figsize=(10, 0.45 * n_journals + 2.0))

    if has_correction:
        corrected = top["corrected_pct"].values
        ci_lo = top["ci_lo_pct"].values
        ci_hi = top["ci_hi_pct"].values

        # Background bar: corrected estimate (lighter)
        ax.barh(
            range(n_journals), corrected,
            color=colors_light, edgecolor="grey", linewidth=0.3,
        )
        # Foreground bar: observed (full opacity)
        bars = ax.barh(
            range(n_journals), observed,
            color=colors, edgecolor="grey", linewidth=0.3,
        )
        # Error whiskers
        ax.errorbar(
            corrected, range(n_journals),
            # clamp ≥0: ci_*_pct are full precision while corrected is 1 dp, so
            # rounding can make a difference marginally negative. NaN whiskers
            # (no imputation interval) are skipped by matplotlib. #24
            xerr=[np.clip(corrected - ci_lo, 0, None), np.clip(ci_hi - corrected, 0, None)],
            fmt="none", ecolor="black", elinewidth=0.8, capsize=2, capthick=0.8,
        )

        # ci_hi is NaN where no imputation interval applies; ignore those. #24
        max_val = np.nanmax(np.concatenate([ci_hi, corrected, observed]))

        # Value labels: "observed% (est. corrected%)"
        for i, (obs_v, corr_v) in enumerate(zip(observed, corrected)):
            ax.text(
                max(obs_v, corr_v) + 0.5, i,
                f"{obs_v:.1f}% (est. {corr_v:.1f}%)",
                va="center", fontsize=7,
            )

        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=cmap(0.5), edgecolor="grey", label="Observed"),
            Patch(facecolor=(*cmap(0.5)[:3], 0.35), edgecolor="grey", label="Estimated (corrected)"),
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8, framealpha=0.9)
    else:
        bars = ax.barh(
            range(n_journals), observed,
            color=colors, edgecolor="grey", linewidth=0.3,
        )
        max_val = observed.max()

        for bar, val in zip(bars, observed):
            ax.text(
                bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=8,
            )

    ax.set_yticks(range(n_journals))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("% Articles with Open Data Statement", fontsize=11)
    ax.set_title("Open Data Rates Among Top Journals", fontsize=13, fontweight="bold")

    # Colorbar for total articles
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, aspect=30, shrink=0.8)
    cbar.set_label("Total Articles", fontsize=10)

    # Baseline line
    if baseline_pct is not None:
        ax.axvline(baseline_pct, color="grey", linestyle="--", linewidth=1, alpha=0.7)
        ax.text(
            baseline_pct + 0.3, -0.8,
            f"Overall baseline: {baseline_pct:.1f}%",
            fontsize=8, color="grey", va="top",
        )

    ax.set_xlim(0, max_val * 1.15)
    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote figure: %s (%d journals)", output_path, n_journals)


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------
def generate_journal_latex_table(
    df: pd.DataFrame,
    output_path: Path,
    threshold: int = 0,
    n_total_journals: int = 0,
    survival_pct: float = 1.0,
    label_suffix: str = "",
) -> None:
    """Write a longtable .tex file for journals above the threshold."""
    top = df[df["total_articles"] >= threshold].copy() if threshold > 0 else df.copy()
    top.sort_values("open_data_pct", ascending=False, inplace=True)

    if top.empty:
        logger.warning("No journals above threshold %d for table", threshold)
        return

    has_correction = "corrected_pct" in top.columns and top["corrected_pct"].notna().any()

    min_total = top["total_articles"].min()
    max_total = top["total_articles"].max()
    pct_col = "corrected_pct" if has_correction else "open_data_pct"
    min_pct = top[pct_col].min()
    max_pct = top[pct_col].max()

    lines = []
    lines.append(r"% Auto-generated by scripts/table_journals.py — do not edit manually")
    lines.append(r"\begingroup")
    lines.append(r"\arrayrulecolor{COL5}")
    lines.append(r"\rowcolors{2}{COL5!10}{white}")
    lines.append(r"\small")

    if has_correction:
        col_spec = r"p{5.5cm} S[table-format=6.0] S[table-format=5.0] S[table-format=2.1] S[table-format=2.1]"
        n_cols = 5
    else:
        col_spec = r"p{6cm} S[table-format=6.0] S[table-format=5.0] S[table-format=2.1]"
        n_cols = 4
    lines.append(rf"\begin{{longtable}}{{{col_spec}}}")

    surv_str = f"{survival_pct:g}"
    if has_correction:
        caption = (
            r"Open data rates among top biomedical journals. "
            rf"Journals exceeding the Weibull-derived {surv_str}\% survival threshold "
            rf"for total articles ($\geq${threshold:,} articles with "
            r"oddpub v7 coverage), ranked by observed open data rate. "
            r"\% OD (obs.) shows the directly measured rate; "
            r"\% OD (est.) applies journal-level correction factors from "
            r"head-to-head PDF vs.\ XML comparison to estimate the true rate "
            r"for articles with XML-only coverage. "
            r"Cell shading: Total Pubs uses a blue-to-red gradient on log scale; "
            r"\% OD columns use a linear blue-to-red gradient. "
            rf"Full rankings for all {n_total_journals:,} journals are available "
            r"in the supplementary materials on GitHub."
        )
    else:
        caption = (
            r"Open data rates among top biomedical journals. "
            rf"Journals exceeding the Weibull-derived {surv_str}\% survival threshold "
            rf"for total articles ($\geq${threshold:,} articles with "
            r"oddpub v7 coverage), ranked by open data rate. "
            r"Cell shading: Total Pubs uses a blue-to-red gradient on log scale; "
            r"\% Open Data uses a linear blue-to-red gradient. "
            rf"Full rankings for all {n_total_journals:,} journals are available "
            r"in the supplementary materials on GitHub."
        )
    lines.append(rf"\caption{{{caption}}}")
    lines.append(rf"\label{{tab:journals{label_suffix}}} \\")

    if has_correction:
        header_row = (
            r"\textbf{Journal} & "
            r"{\textbf{Total Pubs}} & {\textbf{Open Data}} & "
            r"{\textbf{\% OD (obs.)}} & {\textbf{\% OD (est.)}} \\"
        )
    else:
        header_row = (
            r"\textbf{Journal} & "
            r"{\textbf{Total Pubs}} & {\textbf{Open Data}} & "
            r"{\textbf{\% Open Data}} \\"
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
        name = escape_latex(str(row["journal"]))
        total = format_number_siunitx(row["total_articles"])
        od = format_number_siunitx(row["open_data_articles"])
        pct = f"{row['open_data_pct']:.1f}"

        color_total = get_color_bwr(row["total_articles"], min_total, max_total, use_log=True)
        color_pct = get_color_bwr(row["open_data_pct"], min_pct, max_pct)

        if has_correction:
            corr_pct = f"{row['corrected_pct']:.1f}"
            color_corr = get_color_bwr(row["corrected_pct"], min_pct, max_pct)
            lines.append(
                f"{name} & "
                f"\\cellcolor{color_total} {total} & "
                f"\\cellcolor{color_pct} {od} & "
                f"\\cellcolor{color_pct} {pct} & "
                f"\\cellcolor{color_corr} {corr_pct} \\\\"
            )
        else:
            lines.append(
                f"{name} & "
                f"\\cellcolor{color_total} {total} & "
                f"\\cellcolor{color_pct} {od} & "
                f"\\cellcolor{color_pct} {pct} \\\\"
            )

    lines.append(r"\end{longtable}")
    lines.append(r"\arrayrulecolor{black}")
    lines.append(r"\endgroup")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote LaTeX table: %s (%d journals)", output_path, len(top))


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------
def save_summary_csv(df: pd.DataFrame, output_path: Path) -> None:
    """Save the full journal summary as CSV."""
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
    baseline_pct: float = 0.0,
) -> None:
    """Save the full journal summary as markdown."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    has_correction = "corrected_pct" in df.columns and df["corrected_pct"].notna().any()

    lines = []
    lines.append("# Journal Open Data Rankings")
    lines.append("")
    lines.append(f"> Generated {date.today().isoformat()} from pmid_registry.duckdb")
    lines.append(f"> {len(df):,} journals with oddpub v7 coverage")
    lines.append(f"> Overall baseline: {baseline_pct:.1f}% open data")
    if has_correction:
        lines.append("> Corrected rates estimated using journal-level PDF vs XML detection factors")
    lines.append("")

    if has_correction:
        lines.append(
            "| Rank | Journal | Total Pubs | Open Data | % OD (obs.) | % OD (est.) | 95% Imp. Interval |"
        )
        lines.append(
            "|---:|---|---:|---:|---:|---:|---|"
        )
    else:
        lines.append(
            "| Rank | Journal | Total Pubs | Open Data | % Open Data |"
        )
        lines.append(
            "|---:|---|---:|---:|---:|"
        )

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        name = str(row["journal"])
        total = f"{int(row['total_articles']):,}"
        od = f"{int(row['open_data_articles']):,}"
        pct = f"{row['open_data_pct']:.1f}%"
        if has_correction:
            corr_pct = f"{row['corrected_pct']:.1f}%"
            # Three display states (#24): None -> correction did nothing;
            # width < 0.1pp -> real interval narrower than display precision
            # (show point); width >= 0.1pp -> normal interval.
            lo_p, hi_p = row["ci_lo_pct"], row["ci_hi_pct"]
            if pd.isna(lo_p) or pd.isna(hi_p):
                ci = "—"
            elif round(lo_p, 1) == round(hi_p, 1):
                ci = f"{row['corrected_pct']:.1f}%"
            else:
                ci = f"{lo_p:.1f}–{hi_p:.1f}%"
            lines.append(f"| {rank} | {name} | {total} | {od} | {pct} | {corr_pct} | {ci} |")
        else:
            lines.append(f"| {rank} | {name} | {total} | {od} | {pct} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote markdown summary: %s (%d rows)", output_path, len(df))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--duckdb-path",
        default=_find_duckdb_default(),
        help="Path to pmid_registry.duckdb",
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
    p.add_argument(
        "--figure-survival", type=float, default=0.005,
        help="Weibull survival for figure threshold (default: 0.005 = 0.5%%)",
    )
    p.add_argument(
        "--table-survival", type=float, default=0.01,
        help="Weibull survival for table threshold (default: 0.01 = 1%%)",
    )
    p.add_argument("--min-articles", type=int, default=100, help="Minimum articles for CSV/markdown")
    p.add_argument("--year-from", type=int, default=None, help="Filter by pub_year >=")
    p.add_argument("--year-to", type=int, default=None, help="Filter by pub_year <=")
    p.add_argument("--date-from", default=None, help="Filter by pub_date >= (YYYY-MM-DD)")
    p.add_argument("--date-to", default=None, help="Filter by pub_date <= (YYYY-MM-DD)")
    p.add_argument("--research-only", action="store_true", help="Only include research articles")
    p.add_argument("--no-correction", action="store_true", help="Skip correction factors")
    p.add_argument("--min-h2h", type=int, default=50, help="Min h2h articles per journal for corrections (default: 50)")
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

    # Date / year / research filters
    filter_kwargs = {}
    parts = []
    if args.date_from:
        filter_kwargs["date_from"] = args.date_from
        parts.append(f"pub_date >= {args.date_from}")
    elif args.year_from:
        filter_kwargs["year_from"] = args.year_from
        parts.append(f"pub_year >= {args.year_from}")
    if args.date_to:
        filter_kwargs["date_to"] = args.date_to
        parts.append(f"pub_date <= {args.date_to}")
    elif args.year_to:
        filter_kwargs["year_to"] = args.year_to
        parts.append(f"pub_year <= {args.year_to}")
    if args.research_only:
        filter_kwargs["research_only"] = True
        parts.append("research only")
    if parts:
        logger.info("Filters: %s", ", ".join(parts))

    # Query per-journal stats
    logger.info("Running journal stats query (min_articles=%d)...", args.min_articles)
    journal_stats = query_journal_open_data_stats(
        con, min_articles=args.min_articles, **filter_kwargs,
    )
    logger.info("  %d journals with >= %d articles", len(journal_stats), args.min_articles)

    # Drop non-journal source artifacts (e.g. the "PubMed" pseudo-journal). #33
    _excl_mask = journal_stats["journal"].astype(str).str.strip().str.lower().isin(NON_JOURNAL_SOURCES)
    if _excl_mask.any():
        dropped = journal_stats.loc[_excl_mask, "journal"].tolist()
        journal_stats = journal_stats[~_excl_mask].reset_index(drop=True)
        logger.info("  Excluded %d non-journal source(s): %s", len(dropped), ", ".join(map(str, dropped)))

    # Compute baseline OD rate
    baseline = query_baseline_od_rate(con, **filter_kwargs)
    baseline_pct = baseline["baseline_pct"]
    logger.info(
        "  Overall baseline: %d / %d = %.1f%%",
        baseline["open_data_articles"], baseline["total_articles"], baseline_pct,
    )

    # Compute percentages
    journal_stats["open_data_pct"] = (
        100.0 * journal_stats["open_data_articles"] / journal_stats["total_articles"]
    ).round(1)
    journal_stats["open_code_pct"] = (
        100.0 * journal_stats["open_code_articles"] / journal_stats["total_articles"]
    ).round(1)

    # Correction factors
    if not args.no_correction:
        logger.info("Computing journal correction factors (min_h2h=%d)...", args.min_h2h)
        j_corr_df, global_stats = query_journal_correction_factors(
            con, min_h2h=args.min_h2h, **filter_kwargs,
        )
        logger.info(
            "  %d journals with >= %d h2h articles; global best_rate=%.3f (n=%d)",
            len(j_corr_df), args.min_h2h, global_stats["best_rate"], global_stats["n"],
        )
        journal_corrections = build_journal_correction_table(j_corr_df, global_stats)

        # Apply per-journal correction
        corrected_rows = []
        for _, row in journal_stats.iterrows():
            result = apply_journal_correction(
                journal_name=row["journal"],
                xml_only_count=int(row["xml_only"]),
                observed_od=int(row["open_data_articles"]),
                pdf_covered_od=int(row["pdf_covered_od"]),
                journal_corrections=journal_corrections,
                global_fallback=global_stats,
            )
            corrected_rows.append(result)

        corr_df = pd.DataFrame(corrected_rows)
        journal_stats["corrected_od"] = corr_df["corrected_od"].values
        journal_stats["ci_lo"] = corr_df["ci_lo"].values
        journal_stats["ci_hi"] = corr_df["ci_hi"].values
        journal_stats["corrected_pct"] = (
            100.0 * journal_stats["corrected_od"] / journal_stats["total_articles"]
        ).round(1)
        # Full precision in the CSV so real-but-narrow imputation intervals
        # stay distinct (display rounds to 1 dp). #24
        journal_stats["ci_lo_pct"] = (
            100.0 * journal_stats["ci_lo"] / journal_stats["total_articles"]
        ).round(6)
        journal_stats["ci_hi_pct"] = (
            100.0 * journal_stats["ci_hi"] / journal_stats["total_articles"]
        ).round(6)

        logger.info("  Correction factors applied to %d journals", len(journal_stats))

    # Sort by OD rate descending
    journal_stats.sort_values("open_data_pct", ascending=False, inplace=True)
    journal_stats.reset_index(drop=True, inplace=True)

    # Weibull thresholds
    article_counts = journal_stats["total_articles"].values

    fig_threshold, fig_n, fig_params = compute_weibull_threshold(
        article_counts, survival=args.figure_survival, min_articles=args.min_articles,
    )
    logger.info(
        "  Weibull %.1f%% figure threshold: >=%s articles → %d journals (shape=%.3f)",
        args.figure_survival * 100, f"{fig_threshold:,}", fig_n, fig_params[0],
    )

    tbl_threshold, tbl_n, tbl_params = compute_weibull_threshold(
        article_counts, survival=args.table_survival, min_articles=args.min_articles,
    )
    logger.info(
        "  Weibull %.1f%% table threshold: >=%s articles → %d journals (shape=%.3f)",
        args.table_survival * 100, f"{tbl_threshold:,}", tbl_n, tbl_params[0],
    )

    # Build filtered subsets
    fig_df = journal_stats[journal_stats["total_articles"] >= fig_threshold].copy()
    tbl_df = journal_stats[journal_stats["total_articles"] >= tbl_threshold].copy()

    # Outputs
    sfx = args.output_suffix
    table_path = Path(args.output_dir) / f"table_journals{sfx}.tex"
    figure_path = Path(args.figures_dir) / f"journals_open_data{sfx}.png"
    csv_path = Path(args.results_dir) / f"journals_summary{sfx}.csv"
    md_path = Path(args.results_dir) / f"journals_summary{sfx}.md"

    generate_journal_latex_table(
        tbl_df, table_path,
        threshold=tbl_threshold,
        n_total_journals=len(journal_stats),
        survival_pct=args.table_survival * 100,
        label_suffix=sfx,
    )
    generate_journal_bar_chart(
        fig_df, figure_path,
        threshold=0,
        baseline_pct=baseline_pct,
    )
    save_summary_csv(journal_stats, csv_path)
    save_summary_markdown(journal_stats, md_path, baseline_pct=baseline_pct)

    con.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
