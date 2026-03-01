#!/usr/bin/env python3
"""
Load funder budget seed CSV into DuckDB funder_budgets table.

Reads scripts/funder_budgets_seed.csv and creates/replaces the funder_budgets
table in funder_extract.duckdb. The DuckDB file must be unlocked with
`datalad unlock` before running.

Usage:
    python scripts/load_funder_budgets.py --verbose
    python scripts/load_funder_budgets.py --duckdb-path /path/to/db --seed-csv /path/to/csv
"""

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import _find_duckdb_default

logger = logging.getLogger(__name__)

DEFAULT_DUCKDB = _find_duckdb_default("funder_extract.duckdb")
DEFAULT_SEED = str(Path(__file__).resolve().parent / "funder_budgets_seed.csv")


def load_budgets(duckdb_path: str, seed_csv: str) -> int:
    """Load budget seed CSV into DuckDB.

    Returns number of rows inserted.
    """
    logger.info("Reading seed CSV: %s", seed_csv)
    df = pd.read_csv(seed_csv, dtype=str)

    # Convert numeric columns
    for col in ("budget_amount", "budget_usd"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["budget_year"] = pd.to_numeric(df["budget_year"], errors="coerce").astype("Int64")

    # Replace NaN strings
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].where(df[col].notna(), None)

    logger.info("  %d rows loaded from CSV", len(df))

    logger.info("Connecting to DuckDB: %s", duckdb_path)
    con = duckdb.connect(duckdb_path, read_only=False)

    con.execute("DROP TABLE IF EXISTS funder_budgets")
    con.execute("""
    CREATE TABLE funder_budgets (
        funder_name VARCHAR NOT NULL,
        funder_id VARCHAR,
        country_code VARCHAR,
        budget_amount DOUBLE,
        budget_currency VARCHAR,
        budget_usd DOUBLE,
        budget_year INTEGER,
        budget_type VARCHAR,
        confidence VARCHAR,
        source_url VARCHAR,
        source_description VARCHAR,
        notes VARCHAR,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    con.register("budget_df", df)
    con.execute("""
    INSERT INTO funder_budgets (
        funder_name, funder_id, country_code,
        budget_amount, budget_currency, budget_usd,
        budget_year, budget_type, confidence,
        source_url, source_description, notes
    )
    SELECT
        funder_name, funder_id, country_code,
        budget_amount, budget_currency, budget_usd,
        budget_year, budget_type, confidence,
        source_url, source_description, notes
    FROM budget_df
    """)

    n_rows = con.execute("SELECT COUNT(*) FROM funder_budgets").fetchone()[0]
    logger.info("  Inserted %d rows into funder_budgets", n_rows)

    # Print summary
    summary = con.execute("""
    SELECT funder_name, budget_usd, budget_year, confidence
    FROM funder_budgets
    WHERE budget_usd IS NOT NULL
    ORDER BY budget_usd DESC
    """).fetchdf()
    if not summary.empty:
        logger.info("Budget summary (USD):")
        for _, row in summary.iterrows():
            usd = row["budget_usd"]
            if usd >= 1e9:
                usd_str = f"${usd / 1e9:.1f}B"
            elif usd >= 1e6:
                usd_str = f"${usd / 1e6:.0f}M"
            else:
                usd_str = f"${usd:,.0f}"
            logger.info(
                "  %-55s %10s  %d  %s",
                row["funder_name"], usd_str, row["budget_year"], row["confidence"],
            )

    con.close()
    return n_rows


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--duckdb-path", default=DEFAULT_DUCKDB, help="Path to funder_extract.duckdb")
    p.add_argument("--seed-csv", default=DEFAULT_SEED, help="Path to funder_budgets_seed.csv")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    load_budgets(args.duckdb_path, args.seed_csv)
    logger.info("Done.")


if __name__ == "__main__":
    main()
