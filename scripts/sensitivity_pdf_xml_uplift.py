#!/usr/bin/env python3
"""
Sensitivity diagnostic: PDF-vs-XML open-data detection uplift on the
head-to-head subset (GitHub #49).

Background
----------
The manuscript claims that PDF-based detection (MinerU + oddpub v7.2.3) finds
more open-data statements than XML-based detection on the *same* articles. v1
prose quoted "approximately 52% more"; a v2 recompute produced ~+172%, a 3.3x
jump that #49 asked us to explain before trusting it. The hypothesis under test
was that the ~210k gold-OA backlog added in v2 (MDPI/Frontiers etc., whose PMC
XML plausibly omits the data-availability section) *composition-drives* the
number up.

What this script establishes
----------------------------
1. REPRODUCE the head-to-head uplift under the manuscript's stated definition
   (is_open_data_pdf_v7 vs is_open_data_xml_v7; research; 2024-01-01..2025-06-30;
   both oddpub v7 arms scored) on v2 -- and, if a v1 registry is supplied, on v1.
   Finding: BOTH registries give ~+170%. The "52%" was never this quantity; it
   is a stale, incomparable placeholder inherited from the poster-era skeleton
   (docs/IMPLEMENTATION_PLAN.md's "13.5% vs 6.8%"), never recomputed against the
   head-to-head definition the sentence claims. So the +172% is not a v1->v2
   data change: the head-to-head uplift was ~+170% all along.

2. DECOMPOSE the v2 head-to-head set into (a) the articles that were already
   head-to-head in v1 and (b) the newly-added backlog, and separately by OA
   status. Finding: the uplift is ~+170% *everywhere* -- (a) +174%, (b) +168%,
   and every OA type in the 130-210% band. It is NOT composition-driven.

3. AGREEMENT (2x2): PDF is nearly a strict superset of XML -- ~94% of XML
   positives are also PDF positives, and PDF catches ~30x as many that the
   other misses. The uplift is a genuine, asymmetric detection difference.

Recommendation for the manuscript: replace the placeholder "substantially more"
with the robust head-to-head figure (~170% more, i.e. roughly 2.7x as many
articles with a detected data-sharing statement). The existing mechanistic
explanation (MinerU extracts DAS text from formatted data-availability
statements, supplementary sections, and figure captions that PMC XML markup
omits) holds unchanged; no gold-OA composition caveat is warranted.

Outputs (byte-deterministic, no timestamps):
  - results/sensitivity_pdf_xml_uplift.csv
  - results/sensitivity_pdf_xml_uplift.png

Read-only: opens the DuckDB registries READ_ONLY and never edits the manuscript.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Make scripts/utils importable whether run from repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import _find_duckdb_default  # noqa: E402

log = logging.getLogger("pdf_xml_uplift")

# Manuscript's stated head-to-head definition.
DATE_FROM = "2024-01-01"
DATE_TO = "2025-06-30"
# NB: is_open_data_pdf_v7 / is_open_data_xml_v7 are article-level flags
# (article has >=1 detected open-data statement in that arm), matching how the
# manuscript sentence is computed.


def _base_predicate() -> str:
    return (
        "is_research "
        f"AND pub_date >= DATE '{DATE_FROM}' AND pub_date <= DATE '{DATE_TO}' "
        "AND has_oddpub_pdf_v7 AND has_oddpub_xml_v7"
    )


def _uplift(pdf: int, xml: int) -> float:
    return (pdf - xml) / xml * 100.0 if xml else float("nan")


def _row(con: duckdb.DuckDBPyConnection, stratum: str, subset: str, where: str) -> dict:
    n, pdf, xml = con.execute(
        f"SELECT COUNT(*), SUM(is_open_data_pdf_v7::INT), SUM(is_open_data_xml_v7::INT) "
        f"FROM pmids WHERE {where}"
    ).fetchone()
    n = n or 0
    pdf = pdf or 0
    xml = xml or 0
    return {
        "stratum": stratum,
        "subset": subset,
        "n_headtohead": n,
        "pdf_open_data": pdf,
        "xml_open_data": xml,
        "pdf_rate_pct": round(pdf / n * 100, 4) if n else float("nan"),
        "xml_rate_pct": round(xml / n * 100, 4) if n else float("nan"),
        "uplift_pct": round(_uplift(pdf, xml), 2),
        "pdf_over_xml_ratio": round(pdf / xml, 4) if xml else float("nan"),
    }


def analyze(v2_path: str, v1_path: str | None) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute(f"ATTACH '{v2_path}' AS v2 (READ_ONLY)")
    base = _base_predicate()

    # Build the working head-to-head table from v2, tagged with v1 membership
    # if a v1 registry was supplied (for the original-vs-backlog decomposition).
    if v1_path:
        con.execute(f"ATTACH '{v1_path}' AS v1 (READ_ONLY)")
        con.execute(
            f"CREATE TEMP TABLE v1h2h AS SELECT pmid FROM v1.pmids WHERE {base}"
        )
        con.execute(
            "CREATE TEMP TABLE pmids AS "
            "SELECT p.pmid, p.is_open_data_pdf_v7, p.is_open_data_xml_v7, p.is_research, "
            "       p.pub_date, p.has_oddpub_pdf_v7, p.has_oddpub_xml_v7, "
            "       COALESCE(p.oa_status,'(null)') AS oa_status, p.journal, "
            "       (v.pmid IS NOT NULL) AS in_v1 "
            f"FROM v2.pmids p LEFT JOIN v1h2h v USING(pmid) WHERE p.{base}"
        )
        has_v1 = True
    else:
        con.execute(
            "CREATE TEMP TABLE pmids AS "
            "SELECT pmid, is_open_data_pdf_v7, is_open_data_xml_v7, is_research, "
            "       pub_date, has_oddpub_pdf_v7, has_oddpub_xml_v7, "
            "       COALESCE(oa_status,'(null)') AS oa_status, journal, "
            "       FALSE AS in_v1 "
            f"FROM v2.pmids WHERE {base}"
        )
        has_v1 = False

    # From here the temp `pmids` already encodes the base predicate, so downstream
    # WHERE clauses only add strata.
    rows = []
    rows.append(_row(con, "headline", "all_v2_headtohead", "TRUE"))

    if has_v1:
        rows.append(_row(con, "decomposition", "also_headtohead_in_v1", "in_v1"))
        rows.append(_row(con, "decomposition", "newly_added_backlog", "NOT in_v1"))

    for (oa,) in con.execute(
        "SELECT DISTINCT oa_status FROM pmids ORDER BY oa_status"
    ).fetchall():
        rows.append(_row(con, "oa_status", oa, f"oa_status = '{oa}'"))

    df = pd.DataFrame(rows)

    # 2x2 agreement matrix (printed; also stashed on the frame's attrs).
    both, pdf_only, xml_only, neither, n = con.execute(
        "SELECT "
        "SUM((is_open_data_pdf_v7 AND is_open_data_xml_v7)::INT), "
        "SUM((is_open_data_pdf_v7 AND NOT is_open_data_xml_v7)::INT), "
        "SUM((NOT is_open_data_pdf_v7 AND is_open_data_xml_v7)::INT), "
        "SUM((NOT is_open_data_pdf_v7 AND NOT is_open_data_xml_v7)::INT), "
        "COUNT(*) FROM pmids"
    ).fetchone()
    df.attrs["agreement"] = dict(
        both=both, pdf_only=pdf_only, xml_only=xml_only, neither=neither, n=n
    )

    # Top journals by PDF-only detections (for the mechanism narrative).
    top = con.execute(
        "SELECT journal, COUNT(*) n, "
        "SUM((is_open_data_pdf_v7 AND NOT is_open_data_xml_v7)::INT) pdf_only "
        "FROM pmids WHERE journal IS NOT NULL "
        "GROUP BY journal ORDER BY pdf_only DESC LIMIT 15"
    ).fetchdf()
    df.attrs["top_journals"] = top

    con.close()
    return df


def make_figure(df: pd.DataFrame, out_png: Path) -> None:
    """Bar chart of PDF vs XML open-data rate across strata, annotated with uplift."""
    plot = df[df["stratum"].isin(["headline", "decomposition", "oa_status"])].copy()
    # Stable, readable order: headline, decomposition, then OA by descending n.
    order = {"headline": 0, "decomposition": 1, "oa_status": 2}
    plot["__k"] = plot["stratum"].map(order)
    plot = plot.sort_values(
        ["__k", "n_headtohead"], ascending=[True, False]
    ).reset_index(drop=True)

    labels = plot["subset"].str.replace("_", " ")
    x = np.arange(len(plot))
    w = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - w / 2, plot["pdf_rate_pct"], w, label="PDF (oddpub v7)", color="#38761d")
    ax.bar(x + w / 2, plot["xml_rate_pct"], w, label="XML (oddpub v7)", color="#4472C4")
    for xi, up, pr in zip(x, plot["uplift_pct"], plot["pdf_rate_pct"]):
        if np.isfinite(up):
            ax.text(xi, pr + 0.5, f"+{up:.0f}%", ha="center", va="bottom",
                    fontsize=8, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Open-data detection rate (%)")
    ax.set_title(
        "PDF vs XML open-data detection on the head-to-head subset\n"
        f"(research, {DATE_FROM}..{DATE_TO}; both oddpub v7 arms scored)"
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--v2-duckdb", default=None,
                    help="v2 registry (default: auto-detect pmid_registry_v2.duckdb)")
    ap.add_argument("--v1-duckdb", default=None,
                    help="v1 registry for the original-vs-backlog decomposition "
                         "(default: auto-detect pmid_registry.duckdb; pass '' to skip)")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--figures-dir", default=None,
                    help="if set, also write the PNG here (e.g. latex/figures)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    v2 = args.v2_duckdb or _find_duckdb_default("pmid_registry_v2.duckdb")
    if not os.path.exists(v2):
        log.error("v2 registry not found: %s", v2)
        log.error("Resolve the annex pointer first: "
                  "cd ../datalad-osm && git annex get duckdbs/pmid_registry_v2.duckdb")
        return 2

    if args.v1_duckdb is None:
        v1 = _find_duckdb_default("pmid_registry.duckdb")
        v1 = v1 if os.path.exists(v1) else None
    elif args.v1_duckdb == "":
        v1 = None
    else:
        v1 = args.v1_duckdb
    if v1 is None:
        log.warning("No v1 registry: skipping the original-vs-backlog decomposition.")

    log.info("v2 registry: %s", v2)
    if v1:
        log.info("v1 registry: %s", v1)

    df = analyze(v2, v1)

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "sensitivity_pdf_xml_uplift.csv"
    df.to_csv(csv_path, index=False)

    png_path = results_dir / "sensitivity_pdf_xml_uplift.png"
    make_figure(df, png_path)
    if args.figures_dir:
        fig_dir = Path(args.figures_dir)
        fig_dir.mkdir(parents=True, exist_ok=True)
        make_figure(df, fig_dir / "sensitivity_pdf_xml_uplift.png")

    # ---- Console report ----
    def show(sub):
        r = df[df["subset"] == sub].iloc[0]
        print(f"  {sub:28s} n={int(r.n_headtohead):>8,}  "
              f"PDF={r.pdf_rate_pct:5.2f}%  XML={r.xml_rate_pct:5.2f}%  "
              f"uplift=+{r.uplift_pct:6.1f}%  ({r.pdf_over_xml_ratio:.2f}x)")

    print("\n=== Head-to-head PDF vs XML open-data uplift (v2) ===")
    show("all_v2_headtohead")
    if v1:
        print("\n  decomposition (v1 membership):")
        show("also_headtohead_in_v1")
        show("newly_added_backlog")
    print("\n  by OA status:")
    for sub in df[df.stratum == "oa_status"].sort_values(
        "n_headtohead", ascending=False
    )["subset"]:
        show(sub)

    a = df.attrs["agreement"]
    print("\n=== PDF vs XML agreement (2x2, v2 head-to-head) ===")
    print(f"  both positive : {a['both']:>8,}")
    print(f"  PDF-only pos  : {a['pdf_only']:>8,}   (PDF catches, XML misses)")
    print(f"  XML-only pos  : {a['xml_only']:>8,}   (XML catches, PDF misses)")
    print(f"  neither       : {a['neither']:>8,}")
    print(f"  total         : {a['n']:>8,}")
    if a["xml_only"]:
        print(f"  -> PDF catches {a['pdf_only']/a['xml_only']:.1f}x as many that the other misses")
    if (a["both"] + a["xml_only"]):
        print(f"  -> {a['both']/(a['both']+a['xml_only'])*100:.1f}% of XML positives are also PDF positives")

    print("\n=== Top journals by PDF-only detections ===")
    for _, r in df.attrs["top_journals"].iterrows():
        print(f"  {int(r.pdf_only):>5,}  (h2h n={int(r.n):>6,})  {r.journal}")

    print(f"\nWrote {csv_path}")
    print(f"Wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
