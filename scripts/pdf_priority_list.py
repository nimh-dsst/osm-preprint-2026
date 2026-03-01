#!/usr/bin/env python3
"""
Generate a prioritized list of XML-only PMIDs/DOIs for PDF download.

Ranks articles by expected impact on the funder table's correction error
bars: articles in high-miss-rate journals funded by table-visible funders
are prioritized highest.

Output: CSV with pmid, doi, pmcid, journal, funder_name, pdf_od_rate,
priority_score, rank.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import (
    _find_duckdb_default,
    connect_duckdb_registry,
    query_journal_correction_factors,
)
from utils.correction import build_journal_correction_table

logger = logging.getLogger(__name__)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--duckdb-path",
        default=_find_duckdb_default(),
    )
    p.add_argument("--date-from", default=None, help="pub_date >= (YYYY-MM-DD)")
    p.add_argument("--date-to", default=None, help="pub_date <= (YYYY-MM-DD)")
    p.add_argument("--research-only", action="store_true")
    p.add_argument("--top-n", type=int, default=5000, help="Number of top-priority PMIDs to output")
    p.add_argument("--min-h2h", type=int, default=50, help="Min h2h articles per journal")
    p.add_argument(
        "--aliases-csv",
        default=str(Path(__file__).resolve().parent / "funder_aliases_v5.csv"),
        help="Path to funder_aliases_v5.csv (for funder_weight)",
    )
    p.add_argument("--output", default="results/pdf_priority_list.csv")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def _load_table_funder_names(aliases_csv: str) -> set[str]:
    """Load canonical names from aliases CSV for funder_weight=2.0."""
    try:
        import csv
        names = set()
        with open(aliases_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                oa_name = row.get("openalex_name", "")
                if oa_name and oa_name != "nan":
                    names.add(oa_name)
                cname = row.get("canonical_name", "")
                if cname:
                    names.add(cname)
        return names
    except Exception:
        return set()


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    con = connect_duckdb_registry(args.duckdb_path)

    # Build filter kwargs
    filter_kwargs = {}
    if args.date_from:
        filter_kwargs["date_from"] = args.date_from
    if args.date_to:
        filter_kwargs["date_to"] = args.date_to
    if args.research_only:
        filter_kwargs["research_only"] = True

    # Get journal correction factors
    logger.info("Computing journal correction factors...")
    journal_df, global_stats = query_journal_correction_factors(
        con, min_h2h=args.min_h2h, **filter_kwargs,
    )
    journal_corrections = build_journal_correction_table(journal_df, global_stats)
    logger.info(
        "  %d journals with h2h data; global PDF OD rate: %.1f%%",
        len(journal_corrections), global_stats["rate"] * 100,
    )

    # Load table funder names for weighting
    table_funders = _load_table_funder_names(args.aliases_csv)
    logger.info("  %d funder names from aliases CSV for weighting", len(table_funders))

    # Build extra filter SQL
    extra_sql = ""
    params = []
    if args.date_from:
        extra_sql += " AND p.pub_date >= ?"
        params.append(args.date_from)
    if args.date_to:
        extra_sql += " AND p.pub_date <= ?"
        params.append(args.date_to)
    if args.research_only:
        extra_sql += " AND p.is_research = true"

    # Main query: XML-only funded articles where XML didn't detect OD
    logger.info("Querying XML-only funded articles (XML OD=false)...")
    query = f"""
    SELECT DISTINCT
        p.pmid,
        p.doi,
        p.pmcid,
        p.journal,
        f.canonical_name AS funder_name
    FROM pmids p
    JOIN article_funders af ON p.pmid = af.pmid
    JOIN funders f ON af.funder_id = f.funder_id
    WHERE p.has_oddpub_xml_v7 = true
      AND NOT COALESCE(p.has_oddpub_pdf_v7, false)
      AND NOT COALESCE(p.is_open_data_xml_v7, false)
      AND p.journal IS NOT NULL{extra_sql}
    """
    candidates = con.execute(query, params).fetchdf()
    logger.info("  %d candidate rows (before dedup)", len(candidates))

    if candidates.empty:
        logger.warning("No candidates found")
        con.close()
        return

    # Merge with journal correction rates
    candidates = candidates.merge(
        journal_corrections[["journal", "pdf_od_rate"]],
        on="journal",
        how="inner",
    )
    logger.info("  %d rows after journal merge", len(candidates))

    # Compute priority score
    candidates["funder_weight"] = candidates["funder_name"].apply(
        lambda n: 2.0 if n in table_funders else 1.0
    )
    candidates["priority_score"] = candidates["pdf_od_rate"] * candidates["funder_weight"]

    # Deduplicate on PMID keeping highest score
    candidates.sort_values("priority_score", ascending=False, inplace=True)
    deduped = candidates.drop_duplicates(subset="pmid", keep="first").copy()
    logger.info("  %d unique PMIDs after dedup", len(deduped))

    # Take top N
    top = deduped.head(args.top_n).copy()
    top["rank"] = range(1, len(top) + 1)

    # Select output columns
    out_cols = ["pmid", "doi", "pmcid", "journal", "funder_name", "pdf_od_rate", "priority_score", "rank"]
    top = top[out_cols]

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(output_path, index=False)
    logger.info("Wrote %d rows to %s", len(top), output_path)

    # Summary stats
    if not top.empty:
        top_journals = top["journal"].value_counts().head(10)
        logger.info("Top journals in priority list:")
        for j, n in top_journals.items():
            logger.info("  %s: %d articles", j, n)

    con.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
