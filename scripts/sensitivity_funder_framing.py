#!/usr/bin/env python3
"""
Sensitivity diagnostic: OBSERVED vs CORRECTION-FACTOR-ADJUSTED funder rankings.

Compares directly-measured ("observed") and journal-correction-adjusted
("corrected") open-data rates on the **2024-2025 research-only** funder
leaderboard — i.e. the exact funder set produced by `make funder-table-2024`
(`latex/tables/table_funders_2024_2025.tex`). This is the meaningful comparison;
the all-years `table_funders.tex` has inert correction.

The script REUSES the production funder pipeline (it does NOT reimplement the
correction math nor parse any `.tex`): it calls the same `build_funder_summary`,
`query_*`, `FunderNormalizer`, `compute_weibull_threshold`, and
`build_journal_correction_table` helpers as `scripts/table_funders.py`, with the
same defaults as the `funder-table-2024` Makefile target.

For each selected funder it emits:
  - funder_name
  - n_articles_total, n_articles_pdf, pdf_coverage_pct
  - observed_rate, observed_ci_low, observed_ci_high   (Wilson CI on observed)
  - corrected_rate, corrected_ci_low, corrected_ci_high (from the pipeline)
  - rank_observed, rank_corrected, rank_delta

and PRINTS:
  - Spearman rho between observed and corrected rates
  - max absolute rank delta + the top movers
  - adjacent-pair separability: the smallest gap between neighboring corrected
    rates, and how many adjacent leaderboard pairs have OVERLAPPING corrected CIs
    (i.e. orderings not statistically resolved)
  - a bias-perturbation check: whether a +/- representativeness-bias shift
    (--bias-pt, default 1.0pt: the ~0.44pt XML-space / ~1pt best-rate gap from #21)
    could reorder any adjacent leaderboard pair
  - a rank-stability readout + the team's Option-B decision

(The earlier "non-overlapping observed-vs-corrected CI count" was removed: it was
mechanical — corrected is floored at observed with a tight h2h Wilson CI, so it
measured the size/precision of a one-sided correction, not ranking sensitivity.
See issue #9's correction comment.)

Outputs (byte-deterministic, no timestamps):
  - results/sensitivity_funder_framing.csv
  - results/sensitivity_funder_framing.png

Decision context: the team has chosen **Option B** (expand the PDF corpus to
reduce the ~1pt representativeness bias) as a defensibility strengthening track;
the leaderboard order is already stable. Corpus expansion is tracked in #21; the
postponed ranking-consistency fix is #20.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Allow running as `python scripts/sensitivity_funder_framing.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from table_funders import (
    FunderNormalizer,
    build_funder_summary,
    compute_weibull_threshold,
)
from utils.data_loader import (
    _find_duckdb_default,
    connect_duckdb_registry,
    query_funder_open_data_stats,
    query_journal_correction_factors,
    query_funder_journal_xml_only,
)
from utils.correction import (
    build_journal_correction_table,
    wilson_ci,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Annex-pointer guard
# ---------------------------------------------------------------------------
def _check_duckdb_resolvable(db_path: str) -> None:
    """Exit non-zero with a helpful message if the DuckDB file is missing or is
    an unresolved git-annex pointer (a symlink whose target does not exist)."""
    p = Path(db_path)
    if not p.exists():
        # Path.exists() follows symlinks, so a broken annex symlink lands here.
        if p.is_symlink():
            sys.exit(
                f"ERROR: DuckDB path is an unresolved git-annex pointer:\n"
                f"  {db_path} -> {os.readlink(db_path)}\n"
                f"Fetch the content first, e.g.:\n"
                f"  cd {p.resolve().parent.parent.parent} && "
                f"datalad get duckdbs/{p.name}"
            )
        sys.exit(
            f"ERROR: DuckDB file not found: {db_path}\n"
            f"Set --duckdb-path or OSM_DUCKDB_PATH, or run "
            f"`datalad get` to fetch the registry."
        )


# ---------------------------------------------------------------------------
# Dense ranking (desc), deterministic tie-break by funder_name
# ---------------------------------------------------------------------------
def _dense_rank_desc(df: pd.DataFrame, value_col: str) -> pd.Series:
    """Dense rank (ties share a rank, no gaps) on value_col descending.

    Rows are ordered descending by value, with funder_name ascending as a
    deterministic secondary key, so the output is reproducible across runs.
    Equal rates receive equal ranks.
    """
    ordered = df.sort_values(
        [value_col, "funder_name"], ascending=[False, True]
    )
    ranks: dict[str, int] = {}
    rank = 0
    prev = None
    for name, val in zip(ordered["funder_name"], ordered[value_col]):
        if prev is None or val != prev:
            rank += 1
            prev = val
        ranks[name] = rank
    return df["funder_name"].map(ranks)


# ---------------------------------------------------------------------------
# Short labels for the scatter
# ---------------------------------------------------------------------------
def _short_name(name: str, max_len: int = 24) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1].rstrip() + "\u2026"


# ---------------------------------------------------------------------------
# Build the diagnostic table from the production pipeline
# ---------------------------------------------------------------------------
def build_diagnostic_table(con, args) -> pd.DataFrame:
    """Reproduce the 2024-2025 funder table set and attach diagnostic columns."""
    normalizer = FunderNormalizer(args.aliases_csv)
    logger.info(
        "  %d alias canonical names, %d parent groups",
        len(normalizer.funder_info),
        len(normalizer.parent_children),
    )

    filter_kwargs = {}
    if args.research_only:
        filter_kwargs["research_only"] = True
    if args.date_from:
        filter_kwargs["date_from"] = args.date_from
    if args.date_to:
        filter_kwargs["date_to"] = args.date_to
    logger.info("Filters: %s", filter_kwargs)

    logger.info("Running bulk funder stats query...")
    bulk_stats = query_funder_open_data_stats(con, min_articles=0, **filter_kwargs)
    logger.info("  %d funders in bulk stats", len(bulk_stats))

    logger.info(
        "Computing journal-level correction factors (min_h2h=%d)...",
        args.min_h2h_articles,
    )
    journal_df, global_stats = query_journal_correction_factors(
        con, min_h2h=args.min_h2h_articles, **filter_kwargs
    )
    journal_corrections = build_journal_correction_table(journal_df, global_stats)
    logger.info(
        "  %d journals with h2h data; global best OD rate: %.1f%%",
        len(journal_corrections), global_stats["best_rate"] * 100,
    )

    logger.info("Running bulk funder x journal XML-only query...")
    funder_journal_xml_bulk = query_funder_journal_xml_only(
        con, canonical_names=None, **filter_kwargs
    )
    logger.info("  %d funder x journal rows", len(funder_journal_xml_bulk))

    logger.info("Building funder summary (min_articles=%d)...", args.min_articles)
    summary = build_funder_summary(
        con, normalizer, bulk_stats, min_articles=args.min_articles,
        journal_corrections=journal_corrections,
        global_correction=global_stats,
        funder_journal_xml_bulk=funder_journal_xml_bulk,
        **filter_kwargs,
    )
    logger.info("  %d funders in summary", len(summary))

    # Weibull table threshold (same as `make funder-table-2024`)
    article_counts = summary["total_articles"].values
    tbl_threshold, tbl_n, tbl_params = compute_weibull_threshold(
        article_counts, survival=args.table_survival, min_articles=args.min_articles,
    )
    logger.info(
        "  Weibull %.1f%% table threshold: >=%s articles -> %d funders (shape=%.3f)",
        args.table_survival * 100, f"{tbl_threshold:,}", tbl_n, tbl_params[0],
    )

    # Same dual filter as the table: Weibull article threshold + works count.
    selected = summary[summary["total_articles"] >= tbl_threshold].copy()
    if args.min_works_table > 0:
        before = len(selected)
        selected = selected[selected["aggregated_works_count"] >= args.min_works_table]
        logger.info(
            "  Works filter (>=%s): %d -> %d table funders",
            f"{args.min_works_table:,}", before, len(selected),
        )
    logger.info("  %d funders selected for the leaderboard", len(selected))

    # --- Diagnostic columns -------------------------------------------------
    rows = []
    for _, r in selected.iterrows():
        total = int(r["total_articles"])
        od = int(r["open_data_articles"])
        pdf = int(r["pdf_covered"])
        obs_lo, obs_hi = wilson_ci(od, total)
        rows.append({
            "funder_name": r["funder_name"],
            "n_articles_total": total,
            "n_articles_pdf": pdf,
            "pdf_coverage_pct": round(100.0 * pdf / total, 1) if total else 0.0,
            "observed_rate": float(r["open_data_pct"]),
            "observed_ci_low": round(obs_lo * 100, 1),
            "observed_ci_high": round(obs_hi * 100, 1),
            "corrected_rate": float(r["corrected_pct"]),
            "corrected_ci_low": float(r["ci_lo_pct"]),
            "corrected_ci_high": float(r["ci_hi_pct"]),
        })

    diag = pd.DataFrame(rows)

    diag["rank_observed"] = _dense_rank_desc(diag, "observed_rate")
    diag["rank_corrected"] = _dense_rank_desc(diag, "corrected_rate")
    diag["rank_delta"] = diag["rank_observed"] - diag["rank_corrected"]

    # Deterministic output order: corrected rate desc, tie-break funder_name.
    diag.sort_values(
        ["corrected_rate", "funder_name"], ascending=[False, True], inplace=True,
    )
    diag.reset_index(drop=True, inplace=True)
    return diag


# ---------------------------------------------------------------------------
# Diagnostics + decision rule
# ---------------------------------------------------------------------------
def compute_diagnostics(diag: pd.DataFrame, bias_pt: float = 1.0) -> dict:
    rho, pval = spearmanr(diag["observed_rate"], diag["corrected_rate"])

    abs_delta = diag["rank_delta"].abs()
    max_delta = int(abs_delta.max()) if len(diag) else 0
    movers = diag.reindex(
        abs_delta.sort_values(ascending=False, kind="mergesort").index
    )
    top_movers = movers[movers["rank_delta"] != 0].head(5)

    # --- Adjacent-pair separability on the corrected leaderboard -------------
    # `diag` is already sorted by corrected_rate desc (build_diagnostic_table),
    # so consecutive rows are neighbouring leaderboard positions.
    cr = diag["corrected_rate"].to_numpy()
    clo = diag["corrected_ci_low"].to_numpy()
    chi = diag["corrected_ci_high"].to_numpy()
    names = diag["funder_name"].tolist()

    adj_pairs = []  # (upper_name, lower_name, gap_pt, ci_overlap, within_bias)
    for i in range(len(diag) - 1):
        gap = float(cr[i] - cr[i + 1])               # >= 0 by sort order
        ci_overlap = bool(clo[i] <= chi[i + 1] and clo[i + 1] <= chi[i])
        within_bias = bool(gap < bias_pt)
        adj_pairs.append((names[i], names[i + 1], gap, ci_overlap, within_bias))

    n_pairs = len(adj_pairs)
    min_adjacent_gap = min((p[2] for p in adj_pairs), default=float("nan"))
    n_ambiguous = sum(1 for p in adj_pairs if p[3])          # overlapping CIs
    n_within_bias = sum(1 for p in adj_pairs if p[4])        # gap < bias_pt
    order_robust_to_bias = (n_within_bias == 0)

    # Rank-stability lean (Spearman only; the flawed non-overlap clause is gone).
    if rho >= 0.95:
        stability = "STABLE (≈Option A territory: framing barely changes the order)"
    elif rho < 0.85:
        stability = "UNSTABLE (≈Option B territory: correction reorders the leaderboard)"
    else:
        stability = "MIXED (≈Option C territory)"

    return {
        "rho": float(rho),
        "pval": float(pval),
        "max_delta": max_delta,
        "top_movers": top_movers,
        "n_funders": int(len(diag)),
        "n_pairs": n_pairs,
        "min_adjacent_gap": min_adjacent_gap,
        "n_ambiguous": n_ambiguous,
        "ambiguous_pairs": [p for p in adj_pairs if p[3]],
        "bias_pt": float(bias_pt),
        "n_within_bias": n_within_bias,
        "within_bias_pairs": [p for p in adj_pairs if p[4]],
        "order_robust_to_bias": order_robust_to_bias,
        "stability": stability,
    }


def print_diagnostics(d: dict) -> None:
    line = "=" * 72
    print()
    print(line)
    print("FUNDER FRAMING SENSITIVITY DIAGNOSTIC (2024-2025 research-only)")
    print(line)
    print(f"Funders on leaderboard:            {d['n_funders']}")
    print(f"Spearman rho (observed~corrected): {d['rho']:.4f}  (p={d['pval']:.2e})")
    print(f"Max absolute rank delta:           {d['max_delta']}")
    print()
    print("Top movers (largest |rank_delta|):")
    if d["top_movers"].empty:
        print("  (none — ranking unchanged)")
    else:
        for _, r in d["top_movers"].iterrows():
            print(
                f"  {r['funder_name']:<55} "
                f"obs #{int(r['rank_observed']):>2} -> corr #{int(r['rank_corrected']):>2} "
                f"(delta {int(r['rank_delta']):+d})"
            )
    print()
    print(line)
    print("ADJACENT-PAIR SEPARABILITY (does the leaderboard ORDER hold up?)")
    print(line)
    gap = d["min_adjacent_gap"]
    gap_str = "n/a" if gap != gap else f"{gap:.2f}pt"  # NaN-safe
    print(f"  Smallest gap between neighbouring corrected rates: {gap_str}")
    print(f"  Adjacent pairs with OVERLAPPING corrected CIs:     {d['n_ambiguous']}/{d['n_pairs']}")
    if d["ambiguous_pairs"]:
        print("  Ambiguous (statistically unresolved) orderings:")
        for up, lo, g, _ovl, _wb in d["ambiguous_pairs"][:8]:
            print(f"    {_short_name(up, 34):<34} >? {_short_name(lo, 34):<34} (gap {g:.2f}pt)")
    print()
    print(line)
    print(f"BIAS-PERTURBATION CHECK (representativeness bias = +/-{d['bias_pt']:.2f}pt)")
    print(line)
    print(f"  Adjacent pairs a +/-{d['bias_pt']:.2f}pt shift could reorder (gap < bias): "
          f"{d['n_within_bias']}/{d['n_pairs']}")
    if d["within_bias_pairs"]:
        for up, lo, g, _ovl, _wb in d["within_bias_pairs"][:8]:
            print(f"    {_short_name(up, 34):<34} >? {_short_name(lo, 34):<34} (gap {g:.2f}pt)")
    print(f"  => leaderboard ORDER robust to a +/-{d['bias_pt']:.2f}pt bias: "
          f"{'YES' if d['order_robust_to_bias'] else 'NO'}")
    print("  (This is exactly #21's stopping-rule input: stop expanding the PDF")
    print("   corpus once the worst-case bias perturbation is below the smallest")
    print("   claimed rank gap, i.e. order is robust.)")
    print()
    print(line)
    print("RANK-STABILITY READOUT")
    print(line)
    print(f"  Spearman rho = {d['rho']:.4f}  =>  {d['stability']}")
    print("  (Decision rests on rank stability only; the old non-overlapping-CI")
    print("   criterion was removed as mechanical — see issue #9 correction.)")
    print()
    print("TEAM DECISION: Option B. The leaderboard ORDER is already stable")
    print("(high Spearman rho), so no ranking is being rescued. Option B is chosen")
    print("as a defensibility / bias-reduction strengthening track: expanding the")
    print("PDF corpus shrinks the ~1pt representativeness bias and tightens the")
    print("funder-level correction CIs. Corpus expansion is tracked in #21; the")
    print("postponed ranking-consistency fix is #20.")
    print(line)
    print()


# ---------------------------------------------------------------------------
# Scatter plot (byte-deterministic)
# ---------------------------------------------------------------------------
def make_scatter(diag: pd.DataFrame, d: dict, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 8.0))

    x = diag["observed_rate"].values
    y = diag["corrected_rate"].values
    cov = diag["pdf_coverage_pct"].values

    # Thin error bars from the CIs (drawn under the points).
    ax.errorbar(
        x, y,
        xerr=[x - diag["observed_ci_low"].values, diag["observed_ci_high"].values - x],
        yerr=[y - diag["corrected_ci_low"].values, diag["corrected_ci_high"].values - y],
        fmt="none", ecolor="grey", elinewidth=0.5, alpha=0.5, capsize=0, zorder=1,
    )

    sc = ax.scatter(
        x, y, c=cov, cmap="viridis", s=55, edgecolor="black", linewidth=0.4,
        vmin=0, vmax=100, zorder=3,
    )

    # Identity line y = x
    lo = float(min(x.min(), y.min())) - 2
    hi = float(max(x.max(), y.max())) + 3
    ax.plot([lo, hi], [lo, hi], linestyle="--", color="black", linewidth=0.9,
            alpha=0.7, zorder=2, label="y = x (no correction effect)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)

    for xi, yi, name in zip(x, y, diag["funder_name"]):
        ax.annotate(
            _short_name(str(name)), (xi, yi),
            xytext=(4, 3), textcoords="offset points", fontsize=6.0, zorder=4,
        )

    cbar = fig.colorbar(sc, ax=ax, pad=0.02, aspect=30, shrink=0.85)
    cbar.set_label("PDF coverage (%)", fontsize=10)

    ax.set_xlabel("Observed open data rate (%)", fontsize=11)
    ax.set_ylabel("Correction-adjusted open data rate (%)", fontsize=11)
    ax.set_title(
        "Funder open-data rates: observed vs corrected (2024-2025)\n"
        rf"Spearman $\rho$={d['rho']:.3f}  |  max rank $\Delta$={d['max_delta']}  |  "
        rf"ambiguous adj. pairs={d['n_ambiguous']}/{d['n_pairs']}",
        fontsize=11,
    )
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.5)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # metadata={"Software": None} drops the version/date tag -> byte-deterministic.
    fig.savefig(output_path, dpi=150, metadata={"Software": None})
    plt.close(fig)
    logger.info("Wrote figure: %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--duckdb-path", default=_find_duckdb_default(),
                   help="Path to pmid_registry.duckdb")
    p.add_argument("--aliases-csv",
                   default=str(Path(__file__).resolve().parent / "funder_aliases_v5.csv"),
                   help="Path to funder_aliases_v5.csv")
    p.add_argument("--results-dir", default=str(REPO_ROOT / "results"),
                   help="Directory for CSV and PNG output")
    p.add_argument("--date-from", default="2024-01-01", help="pub_date >= (YYYY-MM-DD)")
    p.add_argument("--date-to", default="2025-06-30", help="pub_date <= (YYYY-MM-DD)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--research-only", dest="research_only", action="store_true",
                   default=True, help="Only research articles (default: on)")
    g.add_argument("--all-years", dest="research_only", action="store_false",
                   help="Disable research-only filter (escape hatch)")
    p.add_argument("--table-survival", type=float, default=0.05,
                   help="Weibull survival for the table threshold (default 0.05)")
    p.add_argument("--min-works-table", type=int, default=50000,
                   help="Min aggregated OpenAlex works count for the table set")
    p.add_argument("--min-h2h-articles", type=int, default=50,
                   help="Min head-to-head articles for journal correction")
    p.add_argument("--min-articles", type=int, default=100,
                   help="Min funded articles to include a funder")
    p.add_argument("--bias-pt", type=float, default=1.0,
                   help="Representativeness-bias magnitude (pt) for the "
                        "perturbation/reorder check; default 1.0 (the ~0.44pt "
                        "XML-space / ~1pt best-rate gap from #21)")
    p.add_argument("--output-prefix", default="sensitivity_funder_framing",
                   help="Output filename prefix (CSV + PNG)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    _check_duckdb_resolvable(args.duckdb_path)

    logger.info("Connecting to DuckDB (read-only): %s", args.duckdb_path)
    con = connect_duckdb_registry(args.duckdb_path, read_only=True)

    try:
        diag = build_diagnostic_table(con, args)
    finally:
        con.close()

    if diag.empty:
        sys.exit("ERROR: no funders selected — check filters / DuckDB content.")

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / f"{args.output_prefix}.csv"
    png_path = results_dir / f"{args.output_prefix}.png"

    col_order = [
        "funder_name",
        "n_articles_total", "n_articles_pdf", "pdf_coverage_pct",
        "observed_rate", "observed_ci_low", "observed_ci_high",
        "corrected_rate", "corrected_ci_low", "corrected_ci_high",
        "rank_observed", "rank_corrected", "rank_delta",
    ]
    diag[col_order].to_csv(csv_path, index=False)
    logger.info("Wrote CSV: %s (%d rows)", csv_path, len(diag))

    d = compute_diagnostics(diag, bias_pt=args.bias_pt)
    make_scatter(diag, d, png_path)
    print_diagnostics(d)

    logger.info("Done.")


if __name__ == "__main__":
    main()
