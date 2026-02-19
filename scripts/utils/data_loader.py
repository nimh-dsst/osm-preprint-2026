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


def connect_duckdb_registry(db_path: str, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Open a DuckDB registry database file.

    Args:
        db_path: Path to the .duckdb file
        read_only: Open in read-only mode (default True)

    Returns:
        DuckDB connection
    """
    db_path = str(db_path)
    return duckdb.connect(db_path, read_only=read_only)


def query_funder_open_data_stats(
    con: duckdb.DuckDBPyConnection,
    min_articles: int = 0,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> pd.DataFrame:
    """
    Bulk query: join article_funders + funders + pmids to get per-funder
    open data/code stats. Uses best-available oddpub scores (PDF v7 preferred over XML v7).

    Args:
        con: DuckDB connection to pmid_registry.duckdb
        min_articles: Minimum total articles for a funder to be included
        year_from: Include articles published in or after this year
        year_to: Include articles published in or before this year

    Returns:
        DataFrame with columns: canonical_name, country_code, funder_id,
        total_articles, open_data_articles, open_code_articles
    """
    filters = ["(p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)"]
    params = []
    if year_from is not None:
        filters.append("p.pub_year >= ?")
        params.append(year_from)
    if year_to is not None:
        filters.append("p.pub_year <= ?")
        params.append(year_to)
    where_clause = " AND ".join(filters)

    query = f"""
    SELECT
        f.canonical_name,
        f.country_code,
        f.funder_id,
        COUNT(DISTINCT af.pmid) AS total_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_data_best = true THEN af.pmid END) AS open_data_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_code_best = true THEN af.pmid END) AS open_code_articles
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE {where_clause}
    GROUP BY f.canonical_name, f.country_code, f.funder_id
    HAVING COUNT(DISTINCT af.pmid) >= {min_articles}
    ORDER BY COUNT(DISTINCT af.pmid) DESC
    """
    return con.execute(query, params).fetchdf()


def query_funder_open_data_for_group(
    con: duckdb.DuckDBPyConnection,
    canonical_names: List[str],
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> dict:
    """
    Per-group query for parent-child aggregation. Takes a list of canonical
    names and returns DISTINCT counts across all of them, avoiding
    double-counting articles funded by multiple child funders.

    Args:
        con: DuckDB connection to pmid_registry.duckdb
        canonical_names: List of funder canonical_names to aggregate
        year_from: Include articles published in or after this year
        year_to: Include articles published in or before this year

    Returns:
        Dict with keys: total_articles, open_data_articles, open_code_articles,
        funder_id (of the member with the most articles)
    """
    placeholders = ", ".join(["?"] * len(canonical_names))
    extra_filters = ""
    extra_params = []
    if year_from is not None:
        extra_filters += " AND p.pub_year >= ?"
        extra_params.append(year_from)
    if year_to is not None:
        extra_filters += " AND p.pub_year <= ?"
        extra_params.append(year_to)

    query = f"""
    SELECT
        COUNT(DISTINCT af.pmid) AS total_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_data_best = true THEN af.pmid END) AS open_data_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_code_best = true THEN af.pmid END) AS open_code_articles
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)
      AND f.canonical_name IN ({placeholders}){extra_filters}
    """
    params = canonical_names + extra_params
    row = con.execute(query, params).fetchone()
    # Get funder_id of the largest member in the group
    fid_query = f"""
    SELECT f.funder_id
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)
      AND f.canonical_name IN ({placeholders}){extra_filters}
    GROUP BY f.funder_id
    ORDER BY COUNT(DISTINCT af.pmid) DESC
    LIMIT 1
    """
    fid_row = con.execute(fid_query, params).fetchone()
    return {
        "total_articles": row[0],
        "open_data_articles": row[1],
        "open_code_articles": row[2],
        "funder_id": fid_row[0] if fid_row else None,
    }


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
