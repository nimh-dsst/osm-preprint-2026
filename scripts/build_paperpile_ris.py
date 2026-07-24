#!/usr/bin/env python3
"""
Build a RIS file for PaperPile-driven PDF retrieval of hard-blocked journals.

Targets journals that sit on the global 16.0% correction fallback because
automated PDF download has never succeeded for them (~0 PDFs in the pipeline
backlog), yet appear in Figure 2. For each such journal, draw a deterministic
random sample of XML-only articles (has oddpub XML coverage, no PDF coverage)
inside the analysis window. Downloading + processing these PDFs converts each
into a head-to-head PDF/XML pair; ~50 pairs earns the journal its own
journal-specific correction factor (min_h2h) and retires the fallback bar.

Random (not cherry-picked) sampling is deliberate: the resulting best_od_rate
must be an unbiased estimate of the journal's true sharing rate. See issue #40.

Outputs (to --output-dir, date-stamped; --label sets the batch name):
  paperpile_<label>_<DATE>.ris  -- import into PaperPile, then fetch PDFs
  paperpile_<label>_<DATE>.csv  -- manifest (pmid, doi, journal, year),
                                   the authoritative pmid<->doi map for ingestion

Emit ONE RIS per hand-off. Pass every target journal as a --journal arg in a
single run so the user imports a single file; running with no --journal args
uses DEFAULT_JOURNALS only (Medicine, BMJ Open) and will silently omit any other
journal you meant to include (this is how the case-report titles were missed in
the first round -- they were never generated, never fetched, never ingested).

PaperPile round-trip (how a .ris becomes ingested PDFs):
  1. User imports this .ris into PaperPile and runs "auto-update" -- PaperPile
     fills full bibliographic metadata (title, authors, year) from each DOI.
  2. User fetches PDFs (manual, solves captchas for bot-blocked publishers).
     PaperPile names each downloaded PDF by <title>-<author>-<year>, NOT by
     PMID/DOI -- so the filenames alone cannot be mapped back to a PMID.
  3. User exports the UPDATED .ris (now carrying titles/authors/years that match
     the PDF filenames) and hands it + the PDF zip to the osm-pipeline agent.
  4. Pipeline maps each PDF filename -> updated-.ris record -> PMID, stages the
     PDFs, and runs MinerU -> oddpub. The AN/ID (PMID) and DO (DOI) fields we
     write survive the round-trip; the manifest CSV above is the fallback
     pmid<->doi map if filename matching is ambiguous.
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import _find_duckdb_default, connect_duckdb_registry

logger = logging.getLogger(__name__)

# Figure-2 journals on the fallback that the backlog cannot reach (issue #40).
DEFAULT_JOURNALS = ["Medicine", "BMJ Open"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--duckdb-path", default=_find_duckdb_default())
    p.add_argument(
        "--journal", action="append", dest="journals",
        help="Exact journal display name to target (repeatable). "
             f"Default: {DEFAULT_JOURNALS}",
    )
    p.add_argument(
        "--per-journal", type=int, default=75,
        help="Articles to sample per journal (default: 75 = 50 h2h target + "
             "~50%% headroom for retrieval/processing loss)",
    )
    p.add_argument("--date-from", default="2024-01-01", help="pub_date >= (YYYY-MM-DD)")
    p.add_argument("--date-to", default="2025-06-30", help="pub_date <= (YYYY-MM-DD)")
    p.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "results"),
    )
    p.add_argument(
        "--label", default="hardblock_pdfs",
        help="Batch label in output filename: paperpile_<label>_<DATE>.{ris,csv}. "
             "Use a distinct label per batch so same-day runs don't collide.",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def sample_journal(con, journal, n, date_from, date_to, seed):
    """Deterministic random sample of XML-only research articles with a DOI.

    Ordering is by hash(pmid, seed) so the sample is reproducible across
    machines and independent of DuckDB's RNG state.
    """
    q = """
    SELECT pmid, doi, pmcid, journal, pub_year
    FROM pmids
    WHERE journal = ?
      AND is_research = true
      AND pub_date >= CAST(? AS DATE)
      AND pub_date <= CAST(? AS DATE)
      AND has_oddpub_xml_v7 = true
      AND NOT COALESCE(has_oddpub_pdf_v7, false)
      AND doi IS NOT NULL
    ORDER BY hash(CAST(pmid AS VARCHAR) || '-' || CAST(? AS VARCHAR))
    LIMIT ?
    """
    return con.execute(q, [journal, date_from, date_to, seed, n]).fetchdf()


def ris_records(df):
    """Yield RIS records. DOI (DO) is PaperPile's retrieval key; PMID is
    included as an accession so PaperPile can cross-check against PubMed."""
    for _, r in df.iterrows():
        yield "\n".join([
            "TY  - JOUR",
            f"JO  - {r['journal']}",
            f"T2  - {r['journal']}",
            f"PY  - {int(r['pub_year'])}" if r["pub_year"] else "PY  - ",
            f"DO  - {r['doi']}",
            f"AN  - {int(r['pmid'])}",
            "DB  - PubMed",
            f"ID  - {int(r['pmid'])}",
            "ER  - ",
            "",
        ])


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    journals = args.journals or DEFAULT_JOURNALS
    con = connect_duckdb_registry(args.duckdb_path)

    frames = []
    for j in journals:
        df = sample_journal(con, j, args.per_journal, args.date_from, args.date_to, args.seed)
        logger.info("%s: sampled %d / requested %d XML-only articles", j, len(df), args.per_journal)
        if len(df) < args.per_journal:
            logger.warning("  only %d available for %s (fewer than requested)", len(df), j)
        frames.append(df)
    con.close()

    import pandas as pd
    manifest = pd.concat(frames, ignore_index=True)
    if manifest.empty:
        logger.error("No articles sampled; nothing written.")
        return 1

    stamp = date.today().isoformat()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ris_path = out_dir / f"paperpile_{args.label}_{stamp}.ris"
    csv_path = out_dir / f"paperpile_{args.label}_{stamp}.csv"

    ris_path.write_text("".join(ris_records(manifest)), encoding="utf-8")
    manifest.to_csv(csv_path, index=False)

    logger.info("Wrote %d RIS records -> %s", len(manifest), ris_path)
    logger.info("Wrote manifest              -> %s", csv_path)
    for j in journals:
        logger.info("  %-12s %d records", j, int((manifest["journal"] == j).sum()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
