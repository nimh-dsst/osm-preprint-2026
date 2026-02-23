#!/usr/bin/env python3
"""
Cross-iteration funder comparison.

Compares open data rates across three analysis iterations:
  - Iter 1 (INCF Poster, Dec 2025): XML oddpub, NER funders, v4 aliases
  - Iter 2 (Pipeline Prelim, Feb 2026): PDF oddpub (MinerU), NER funders, v4 aliases
  - Iter 3 (Expanded + Corrections, Feb 2026): Best(XML+PDF), OpenAlex, v5 aliases

Produces:
  - results/iteration_comparison.csv
  - results/iteration_comparison.md
  - latex/figures/iteration_comparison.png  (optional, --chart)
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import weibull_min

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

DEFAULT_ITER1_CSV = Path.home() / "claude/osm/osm-2025-12-poster-incf/results/funder_data_sharing_summary_v3_all.csv"
DEFAULT_ITER2_CSV = Path.home() / "claude/osm/osm-pipeline/results/open_data_by_funder/open_data_by_funder.csv"
DEFAULT_ITER3_CSV = REPO_ROOT / "results/funders_summary_2024_2025.csv"
DEFAULT_NAME_MAP = SCRIPT_DIR / "funder_name_mapping.csv"

ITER_META = {
    "iter1": {
        "label": "INCF Poster (Dec 2025)",
        "period": "2010–2024",
        "detection": "XML oddpub v7",
        "funder_source": "NER on PMC XML",
        "aliases": "v4 (47 funders)",
    },
    "iter2": {
        "label": "Pipeline Prelim (Feb 2026)",
        "period": "MinerU+rtrans overlap",
        "detection": "PDF oddpub (MinerU)",
        "funder_source": "NER on rtransparent",
        "aliases": "v4 (47 funders)",
    },
    "iter3": {
        "label": "Expanded + Corrections (Feb 2026)",
        "period": "2024-01 to 2025-06",
        "detection": "Best(XML+PDF) + correction",
        "funder_source": "OpenAlex grants",
        "aliases": "v5 (816 funders)",
    },
}


# ── Loaders ───────────────────────────────────────────────────────────────
def load_iter1(path: Path) -> pd.DataFrame:
    """Load INCF poster CSV: funder, total_pubs, data_sharing_pubs, data_sharing_pct."""
    df = pd.read_csv(path)
    df = df.rename(columns={
        "funder": "name",
        "total_pubs": "total",
        "data_sharing_pubs": "od",
        "data_sharing_pct": "pct",
    })
    df["in_figure"] = True
    df["rank"] = range(1, len(df) + 1)
    logger.info("Iter 1: %d funders from %s", len(df), path)
    return df


def load_iter2(path: Path) -> pd.DataFrame:
    """Load pipeline CSV: funder, total, open_data, percentage."""
    df = pd.read_csv(path)
    df = df.rename(columns={
        "funder": "name",
        "open_data": "od",
        "percentage": "pct",
    })
    df["in_figure"] = True
    # Already sorted by percentage desc in the file
    df["rank"] = range(1, len(df) + 1)
    logger.info("Iter 2: %d funders from %s", len(df), path)
    return df


def _compute_weibull_threshold(
    article_counts: np.ndarray,
    survival: float = 0.03,
    min_articles: int = 100,
) -> int:
    """Fit Weibull to log(article_counts) and return threshold at survival probability."""
    counts = article_counts[article_counts >= min_articles]
    log_counts = np.log(counts)
    shape, loc, scale = weibull_min.fit(log_counts)
    threshold_log = weibull_min.isf(survival, shape, loc=loc, scale=scale)
    return int(np.exp(threshold_log))


def load_iter3(path: Path, fig_threshold: int = -1, fig_survival: float = 0.03) -> pd.DataFrame:
    """Load expanded CSV with correction columns.

    fig_threshold: minimum articles for figure membership.
      -1 (default) = auto-compute via Weibull at fig_survival.
       0 = all funders in figure.
    """
    df = pd.read_csv(path)
    df = df.rename(columns={
        "funder_name": "name",
        "total_articles": "total",
        "open_data_articles": "od",
        "open_data_pct": "pct",
    })
    # Keep correction columns if present
    for col in ("corrected_pct", "ci_lo_pct", "ci_hi_pct", "corrected_od"):
        if col not in df.columns:
            df[col] = np.nan

    # Sort by pct desc and assign ranks
    df = df.sort_values("pct", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    if fig_threshold == -1:
        fig_threshold = _compute_weibull_threshold(
            df["total"].values, survival=fig_survival,
        )
        logger.info("  Iter 3 auto Weibull %.1f%% threshold: %s articles",
                     fig_survival * 100, f"{fig_threshold:,}")

    if fig_threshold > 0:
        df["in_figure"] = df["total"] >= fig_threshold
    else:
        df["in_figure"] = True

    logger.info("Iter 3: %d funders from %s (%d in figure)", len(df), path, df["in_figure"].sum())
    return df


# ── Name mapping ──────────────────────────────────────────────────────────
def build_name_mapping(
    iter1: pd.DataFrame,
    iter2: pd.DataFrame,
    iter3: pd.DataFrame,
    manual_csv: Path | None = None,
) -> pd.DataFrame:
    """Build unified name mapping across iterations.

    Strategy:
      1. Exact name matches across any pair of iterations
      2. Manual overrides from CSV for names that don't match
    Returns DataFrame: unified_name, iter1_name, iter2_name, iter3_name
    """
    names1 = set(iter1["name"].unique())
    names2 = set(iter2["name"].unique())
    names3 = set(iter3["name"].unique())
    all_names = names1 | names2 | names3

    rows = []
    matched = set()

    # Auto-match: for each unique name, check which iterations have it
    for name in sorted(all_names):
        in1 = name in names1
        in2 = name in names2
        in3 = name in names3
        if in1 or in2 or in3:
            rows.append({
                "unified_name": name,
                "iter1_name": name if in1 else np.nan,
                "iter2_name": name if in2 else np.nan,
                "iter3_name": name if in3 else np.nan,
            })
            matched.add(name)

    mapping = pd.DataFrame(rows)

    # Apply manual overrides
    if manual_csv and manual_csv.exists():
        manual = pd.read_csv(manual_csv)
        for _, mrow in manual.iterrows():
            unified = mrow["unified_name"]
            # Remove any auto-generated rows that this override supersedes
            names_to_remove = set()
            for col in ("iter1_name", "iter2_name", "iter3_name"):
                val = mrow.get(col)
                if pd.notna(val) and val != "":
                    names_to_remove.add(val)
            # Also remove the unified_name itself if it's different
            names_to_remove.add(unified)

            mapping = mapping[~mapping["unified_name"].isin(names_to_remove)]

            mapping = pd.concat([mapping, pd.DataFrame([{
                "unified_name": unified,
                "iter1_name": mrow.get("iter1_name") if pd.notna(mrow.get("iter1_name", np.nan)) and mrow.get("iter1_name", "") != "" else np.nan,
                "iter2_name": mrow.get("iter2_name") if pd.notna(mrow.get("iter2_name", np.nan)) and mrow.get("iter2_name", "") != "" else np.nan,
                "iter3_name": mrow.get("iter3_name") if pd.notna(mrow.get("iter3_name", np.nan)) and mrow.get("iter3_name", "") != "" else np.nan,
            }])], ignore_index=True)

    n_in_all = mapping.dropna(subset=["iter1_name", "iter2_name", "iter3_name"]).shape[0]
    n_in_any2 = mapping.apply(
        lambda r: sum(pd.notna(r[c]) for c in ("iter1_name", "iter2_name", "iter3_name")) >= 2,
        axis=1,
    ).sum()
    logger.info(
        "Name mapping: %d unified names (%d in all 3, %d in ≥2)",
        len(mapping), n_in_all, n_in_any2,
    )

    return mapping.sort_values("unified_name").reset_index(drop=True)


# ── Merge iterations ──────────────────────────────────────────────────────
def _lookup(df: pd.DataFrame, name, cols: list[str]) -> dict:
    """Look up a funder by name and return requested columns."""
    if pd.isna(name):
        return {c: np.nan for c in cols}
    match = df[df["name"] == name]
    if match.empty:
        return {c: np.nan for c in cols}
    row = match.iloc[0]
    return {c: row.get(c, np.nan) for c in cols}


def merge_iterations(
    iter1: pd.DataFrame,
    iter2: pd.DataFrame,
    iter3: pd.DataFrame,
    name_map: pd.DataFrame,
    figure_only: bool = True,
) -> pd.DataFrame:
    """Merge all iterations into a wide comparison DataFrame."""
    rows = []
    for _, m in name_map.iterrows():
        unified = m["unified_name"]

        v1 = _lookup(iter1, m["iter1_name"], ["total", "od", "pct", "rank", "in_figure"])
        v2 = _lookup(iter2, m["iter2_name"], ["total", "od", "pct", "rank", "in_figure"])
        v3 = _lookup(iter3, m["iter3_name"], ["total", "od", "pct", "rank", "in_figure",
                                                "corrected_pct", "ci_lo_pct", "ci_hi_pct"])

        # Filter: require in figure in at least one iteration
        if figure_only:
            in_any_fig = any(
                v.get("in_figure", False) is True or v.get("in_figure", False) == 1
                for v in (v1, v2, v3)
                if not (isinstance(v.get("in_figure"), float) and np.isnan(v.get("in_figure")))
            )
            if not in_any_fig:
                continue

        rows.append({
            "unified_name": unified,
            "iter1_total": v1["total"],
            "iter1_od": v1["od"],
            "iter1_pct": v1["pct"],
            "iter1_rank": v1["rank"],
            "iter1_in_fig": v1["in_figure"],
            "iter2_total": v2["total"],
            "iter2_od": v2["od"],
            "iter2_pct": v2["pct"],
            "iter2_rank": v2["rank"],
            "iter2_in_fig": v2["in_figure"],
            "iter3_total": v3["total"],
            "iter3_od": v3["od"],
            "iter3_pct": v3["pct"],
            "iter3_corrected_pct": v3["corrected_pct"],
            "iter3_ci_lo": v3["ci_lo_pct"],
            "iter3_ci_hi": v3["ci_hi_pct"],
            "iter3_rank": v3["rank"],
            "iter3_in_fig": v3["in_figure"],
        })

    merged = pd.DataFrame(rows)
    logger.info("Merged: %d funders (figure_only=%s)", len(merged), figure_only)
    return merged


# ── Derived columns ───────────────────────────────────────────────────────
def add_derived_columns(merged: pd.DataFrame) -> pd.DataFrame:
    """Add delta and ratio columns."""
    df = merged.copy()

    # Percentage-point changes (observed)
    df["delta_pct_1to3"] = df["iter3_pct"] - df["iter1_pct"]
    df["delta_pct_2to3"] = df["iter3_pct"] - df["iter2_pct"]

    # Percentage-point changes (corrected)
    df["delta_pct_1to3_corr"] = df["iter3_corrected_pct"] - df["iter1_pct"]
    df["delta_pct_2to3_corr"] = df["iter3_corrected_pct"] - df["iter2_pct"]

    # Article count ratios
    df["ratio_total_3to1"] = df["iter3_total"] / df["iter1_total"]
    df["ratio_total_3to2"] = df["iter3_total"] / df["iter2_total"]

    return df


# ── CSV output ────────────────────────────────────────────────────────────
def save_comparison_csv(merged: pd.DataFrame, path: Path) -> None:
    """Save full comparison as CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False, float_format="%.1f")
    logger.info("Wrote CSV: %s (%d rows)", path, len(merged))


# ── Markdown output ───────────────────────────────────────────────────────
def save_comparison_markdown(merged: pd.DataFrame, path: Path) -> None:
    """Save formatted markdown comparison table."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("# Cross-Iteration Funder Comparison")
    lines.append("")
    lines.append(f"> Generated {date.today().isoformat()}")
    lines.append("")

    # Iteration metadata table
    lines.append("## Iteration Details")
    lines.append("")
    lines.append("| | Iter 1 | Iter 2 | Iter 3 |")
    lines.append("|---|---|---|---|")
    for key in ("label", "period", "detection", "funder_source", "aliases"):
        lines.append(
            f"| **{key.replace('_', ' ').title()}** "
            f"| {ITER_META['iter1'][key]} "
            f"| {ITER_META['iter2'][key]} "
            f"| {ITER_META['iter3'][key]} |"
        )
    lines.append("")

    # Count funders per iteration
    n1 = merged["iter1_pct"].notna().sum()
    n2 = merged["iter2_pct"].notna().sum()
    n3 = merged["iter3_pct"].notna().sum()
    n_all = merged.dropna(subset=["iter1_pct", "iter2_pct", "iter3_pct"]).shape[0]
    lines.append(f"**Funders in comparison:** {len(merged)} total "
                 f"({n1} in iter1, {n2} in iter2, {n3} in iter3, {n_all} in all 3)")
    lines.append("")

    # Sort by iter3 corrected desc, NaN last
    sort_col = "iter3_corrected_pct" if merged["iter3_corrected_pct"].notna().any() else "iter3_pct"
    df = merged.sort_values(sort_col, ascending=False, na_position="last")

    # Table
    lines.append("## Comparison Table")
    lines.append("")
    lines.append(
        "| Funder | I1 Total | I1 %OD | I2 Total | I2 %OD | I3 Total | I3 %OD (obs) | I3 %OD (est) | Δ1→3 | Δ2→3 |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    for _, row in df.iterrows():
        name = row["unified_name"]

        def _fmt_int(v):
            return f"{int(v):,}" if pd.notna(v) else "—"

        def _fmt_pct(v):
            return f"{v:.1f}%" if pd.notna(v) else "—"

        def _fmt_delta(v):
            if pd.isna(v):
                return "—"
            sign = "+" if v > 0 else ""
            return f"{sign}{v:.1f}pp"

        lines.append(
            f"| {name} "
            f"| {_fmt_int(row['iter1_total'])} "
            f"| {_fmt_pct(row['iter1_pct'])} "
            f"| {_fmt_int(row['iter2_total'])} "
            f"| {_fmt_pct(row['iter2_pct'])} "
            f"| {_fmt_int(row['iter3_total'])} "
            f"| {_fmt_pct(row['iter3_pct'])} "
            f"| {_fmt_pct(row['iter3_corrected_pct'])} "
            f"| {_fmt_delta(row['delta_pct_1to3_corr'])} "
            f"| {_fmt_delta(row['delta_pct_2to3_corr'])} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote markdown: %s (%d rows)", path, len(df))


# ── Chart ─────────────────────────────────────────────────────────────────
def generate_comparison_chart(merged: pd.DataFrame, path: Path) -> None:
    """Grouped horizontal bar chart comparing iterations."""
    # Only funders present in ≥2 iterations
    df = merged.copy()
    df["n_iters"] = df[["iter1_pct", "iter2_pct", "iter3_pct"]].notna().sum(axis=1)
    df = df[df["n_iters"] >= 2].copy()

    if df.empty:
        logger.warning("No funders in ≥2 iterations for chart")
        return

    # Sort by iter3 corrected pct desc (NaN last, then by iter1 pct)
    sort_col = "iter3_corrected_pct" if df["iter3_corrected_pct"].notna().any() else "iter3_pct"
    df = df.sort_values(
        [sort_col, "iter1_pct"], ascending=[True, True], na_position="first",
    )

    n = len(df)
    bar_height = 0.2
    y = np.arange(n)

    fig, ax = plt.subplots(figsize=(12, 0.6 * n + 2.5))

    colors = {
        "iter1": "#2196F3",      # blue
        "iter2": "#FF9800",      # orange
        "iter3_obs": "#4CAF50",  # green
        "iter3_corr": "#81C784", # light green
    }

    has_corr = df["iter3_corrected_pct"].notna().any()

    # Draw bars (bottom to top for correct visual ordering)
    if has_corr:
        offsets = [-1.5, -0.5, 0.5, 1.5]
        ax.barh(y + offsets[0] * bar_height, df["iter1_pct"].fillna(0),
                height=bar_height, color=colors["iter1"], alpha=0.85,
                label=f"Iter 1: {ITER_META['iter1']['label']}")
        ax.barh(y + offsets[1] * bar_height, df["iter2_pct"].fillna(0),
                height=bar_height, color=colors["iter2"], alpha=0.85,
                label=f"Iter 2: {ITER_META['iter2']['label']}")
        ax.barh(y + offsets[2] * bar_height, df["iter3_pct"].fillna(0),
                height=bar_height, color=colors["iter3_obs"], alpha=0.85,
                label=f"Iter 3 observed: {ITER_META['iter3']['label']}")
        ax.barh(y + offsets[3] * bar_height, df["iter3_corrected_pct"].fillna(0),
                height=bar_height, color=colors["iter3_corr"], alpha=0.85,
                label="Iter 3 corrected (est.)")
    else:
        offsets = [-1, 0, 1]
        ax.barh(y + offsets[0] * bar_height, df["iter1_pct"].fillna(0),
                height=bar_height, color=colors["iter1"], alpha=0.85,
                label=f"Iter 1: {ITER_META['iter1']['label']}")
        ax.barh(y + offsets[1] * bar_height, df["iter2_pct"].fillna(0),
                height=bar_height, color=colors["iter2"], alpha=0.85,
                label=f"Iter 2: {ITER_META['iter2']['label']}")
        ax.barh(y + offsets[2] * bar_height, df["iter3_pct"].fillna(0),
                height=bar_height, color=colors["iter3_obs"], alpha=0.85,
                label=f"Iter 3: {ITER_META['iter3']['label']}")

    ax.set_yticks(y)
    ax.set_yticklabels(df["unified_name"], fontsize=8)
    ax.set_xlabel("% Articles with Open Data Statement", fontsize=11)
    ax.set_title("Funder Open Data Rates: Cross-Iteration Comparison",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax.set_xlim(0, max(
        df["iter1_pct"].max(),
        df["iter2_pct"].max(),
        df["iter3_pct"].max(),
        df["iter3_corrected_pct"].max() if has_corr else 0,
    ) * 1.12)

    plt.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote chart: %s (%d funders)", path, n)


# ── Summary report ────────────────────────────────────────────────────────
def print_summary(merged: pd.DataFrame) -> None:
    """Print summary statistics to stdout."""
    n_total = len(merged)
    n1 = merged["iter1_pct"].notna().sum()
    n2 = merged["iter2_pct"].notna().sum()
    n3 = merged["iter3_pct"].notna().sum()
    n_all3 = merged.dropna(subset=["iter1_pct", "iter2_pct", "iter3_pct"]).shape[0]

    print("\n" + "=" * 70)
    print("CROSS-ITERATION FUNDER COMPARISON SUMMARY")
    print("=" * 70)
    print(f"\nFunders in comparison: {n_total}")
    print(f"  In iter 1 (Poster):     {n1}")
    print(f"  In iter 2 (Pipeline):   {n2}")
    print(f"  In iter 3 (Expanded):   {n3}")
    print(f"  In all 3 iterations:    {n_all3}")

    # Deltas for funders in both iter1 and iter3
    both_1_3 = merged.dropna(subset=["iter1_pct", "iter3_pct"])
    if len(both_1_3) > 0:
        has_corr = both_1_3["delta_pct_1to3_corr"].notna().any()
        delta_col = "delta_pct_1to3_corr" if has_corr else "delta_pct_1to3"
        label = "corrected" if has_corr else "observed"
        print(f"\n--- Iter 1 → Iter 3 ({label}) ---")
        print(f"  Median Δ: {both_1_3[delta_col].median():+.1f} pp")
        print(f"  Mean Δ:   {both_1_3[delta_col].mean():+.1f} pp")
        top_gains = both_1_3.nlargest(5, delta_col)
        print("  Top 5 gains:")
        for _, r in top_gains.iterrows():
            print(f"    {r['unified_name']}: {r['iter1_pct']:.1f}% → {r['iter3_pct']:.1f}%"
                  f" ({r[delta_col]:+.1f} pp)")
        top_drops = both_1_3.nsmallest(5, delta_col)
        print("  Top 5 drops:")
        for _, r in top_drops.iterrows():
            print(f"    {r['unified_name']}: {r['iter1_pct']:.1f}% → {r['iter3_pct']:.1f}%"
                  f" ({r[delta_col]:+.1f} pp)")

    # Deltas for funders in both iter2 and iter3
    both_2_3 = merged.dropna(subset=["iter2_pct", "iter3_pct"])
    if len(both_2_3) > 0:
        has_corr = both_2_3["delta_pct_2to3_corr"].notna().any()
        delta_col = "delta_pct_2to3_corr" if has_corr else "delta_pct_2to3"
        label = "corrected" if has_corr else "observed"
        print(f"\n--- Iter 2 → Iter 3 ({label}) ---")
        print(f"  Median Δ: {both_2_3[delta_col].median():+.1f} pp")
        print(f"  Mean Δ:   {both_2_3[delta_col].mean():+.1f} pp")

    # Article count ratios
    has_ratio = merged["ratio_total_3to1"].notna()
    if has_ratio.any():
        ratios_1 = merged.loc[has_ratio, "ratio_total_3to1"]
        print(f"\n--- Article Count Ratios ---")
        print(f"  Iter3/Iter1: median {ratios_1.median():.1f}x, "
              f"mean {ratios_1.mean():.1f}x")
    has_ratio2 = merged["ratio_total_3to2"].notna()
    if has_ratio2.any():
        ratios_2 = merged.loc[has_ratio2, "ratio_total_3to2"]
        print(f"  Iter3/Iter2: median {ratios_2.median():.1f}x, "
              f"mean {ratios_2.mean():.1f}x")

    # Funders entering/leaving figure subsets
    in_fig_1 = set(merged.loc[merged["iter1_in_fig"] == True, "unified_name"])
    in_fig_2 = set(merged.loc[merged["iter2_in_fig"] == True, "unified_name"])
    in_fig_3 = set(merged.loc[merged["iter3_in_fig"] == True, "unified_name"])

    entered_3 = in_fig_3 - (in_fig_1 | in_fig_2)
    left_3 = (in_fig_1 | in_fig_2) - in_fig_3
    if entered_3:
        print(f"\n--- New in iter3 figure ({len(entered_3)}) ---")
        for name in sorted(entered_3):
            print(f"    {name}")
    if left_3:
        print(f"\n--- Left iter3 figure ({len(left_3)}) ---")
        for name in sorted(left_3):
            print(f"    {name}")

    print("\n" + "=" * 70)


# ── CLI ───────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iter1-csv", default=str(DEFAULT_ITER1_CSV),
                   help="Iter 1 CSV (poster)")
    p.add_argument("--iter2-csv", default=str(DEFAULT_ITER2_CSV),
                   help="Iter 2 CSV (pipeline)")
    p.add_argument("--iter3-csv", default=str(DEFAULT_ITER3_CSV),
                   help="Iter 3 CSV (expanded)")
    p.add_argument("--name-map", default=str(DEFAULT_NAME_MAP),
                   help="Manual name overrides CSV")
    p.add_argument("--output-dir", default=str(REPO_ROOT / "results"),
                   help="Directory for CSV and markdown output")
    p.add_argument("--figures-dir", default=str(REPO_ROOT / "latex" / "figures"),
                   help="Directory for chart output")
    p.add_argument("--chart", action="store_true",
                   help="Generate grouped bar chart")
    p.add_argument("--iter3-fig-threshold", type=int, default=-1,
                   help="Min articles for iter3 figure (default: auto Weibull 3%%); 0=all")
    p.add_argument("--all-funders", action="store_true",
                   help="Include non-figure funders (default: figure funders only)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Load iterations
    iter1 = load_iter1(Path(args.iter1_csv))
    iter2 = load_iter2(Path(args.iter2_csv))
    iter3 = load_iter3(Path(args.iter3_csv), fig_threshold=args.iter3_fig_threshold)

    # Build name mapping
    manual_csv = Path(args.name_map) if args.name_map else None
    name_map = build_name_mapping(iter1, iter2, iter3, manual_csv)

    # Merge
    figure_only = not args.all_funders
    merged = merge_iterations(iter1, iter2, iter3, name_map, figure_only=figure_only)

    # Add derived columns
    merged = add_derived_columns(merged)

    # Save outputs
    output_dir = Path(args.output_dir)
    save_comparison_csv(merged, output_dir / "iteration_comparison.csv")
    save_comparison_markdown(merged, output_dir / "iteration_comparison.md")

    if args.chart:
        figures_dir = Path(args.figures_dir)
        generate_comparison_chart(merged, figures_dir / "iteration_comparison.png")

    # Print summary
    print_summary(merged)


if __name__ == "__main__":
    main()
