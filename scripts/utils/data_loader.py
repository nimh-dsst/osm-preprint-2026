"""
Data loading utilities using DuckDB for memory-efficient parquet queries.
"""

import duckdb
from pathlib import Path
from typing import Optional, List
import pandas as pd


def load_oddpub_results(oddpub_dir: Path, duckdb_con: Optional[duckdb.DuckDBPyConnection] = None) -> pd.DataFrame:
    """
    Load oddpub results from parquet files using DuckDB.

    Args:
        oddpub_dir: Directory containing oddpub parquet files
        duckdb_con: Optional DuckDB connection (creates new if None)

    Returns:
        DataFrame with oddpub results
    """
    if duckdb_con is None:
        duckdb_con = duckdb.connect()

    # Find all parquet files
    parquet_files = list(Path(oddpub_dir).glob("*.parquet"))

    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {oddpub_dir}")

    # Use DuckDB to efficiently query parquet files
    file_pattern = str(Path(oddpub_dir) / "*.parquet")

    query = f"""
    SELECT *
    FROM read_parquet('{file_pattern}')
    """

    return duckdb_con.execute(query).fetchdf()


def load_openalex_metadata(openalex_file: Path,
                          duckdb_con: Optional[duckdb.DuckDBPyConnection] = None,
                          columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Load OpenAlex metadata from parquet file using DuckDB.

    Args:
        openalex_file: Path to OpenAlex parquet file
        duckdb_con: Optional DuckDB connection (creates new if None)
        columns: Optional list of columns to select (selects all if None)

    Returns:
        DataFrame with OpenAlex metadata
    """
    if duckdb_con is None:
        duckdb_con = duckdb.connect()

    if columns:
        col_str = ", ".join(columns)
    else:
        col_str = "*"

    query = f"""
    SELECT {col_str}
    FROM read_parquet('{openalex_file}')
    """

    return duckdb_con.execute(query).fetchdf()


def join_oddpub_openalex(oddpub_df: pd.DataFrame,
                        openalex_df: pd.DataFrame,
                        on: str = 'pmid',
                        duckdb_con: Optional[duckdb.DuckDBPyConnection] = None) -> pd.DataFrame:
    """
    Join oddpub results with OpenAlex metadata using DuckDB.

    Args:
        oddpub_df: DataFrame with oddpub results
        openalex_df: DataFrame with OpenAlex metadata
        on: Column name to join on (default: 'pmid')
        duckdb_con: Optional DuckDB connection (creates new if None)

    Returns:
        Joined DataFrame
    """
    if duckdb_con is None:
        duckdb_con = duckdb.connect()

    # Register DataFrames as DuckDB views
    duckdb_con.register('oddpub', oddpub_df)
    duckdb_con.register('openalex', openalex_df)

    query = f"""
    SELECT *
    FROM oddpub
    INNER JOIN openalex
    ON oddpub.{on} = openalex.{on}
    """

    return duckdb_con.execute(query).fetchdf()


def aggregate_by_group(df: pd.DataFrame,
                      group_col: str,
                      agg_dict: dict,
                      duckdb_con: Optional[duckdb.DuckDBPyConnection] = None) -> pd.DataFrame:
    """
    Aggregate DataFrame by group using DuckDB for efficiency.

    Args:
        df: DataFrame to aggregate
        group_col: Column to group by
        agg_dict: Dictionary mapping columns to aggregation functions
                 (e.g., {'total_pubs': 'COUNT(*)', 'open_data_pubs': 'SUM(is_open_data)'})
        duckdb_con: Optional DuckDB connection (creates new if None)

    Returns:
        Aggregated DataFrame
    """
    if duckdb_con is None:
        duckdb_con = duckdb.connect()

    # Register DataFrame as DuckDB view
    duckdb_con.register('data', df)

    # Build aggregation expressions
    agg_exprs = [f"{func} AS {col}" for col, func in agg_dict.items()]
    agg_str = ", ".join(agg_exprs)

    query = f"""
    SELECT {group_col}, {agg_str}
    FROM data
    GROUP BY {group_col}
    """

    return duckdb_con.execute(query).fetchdf()
