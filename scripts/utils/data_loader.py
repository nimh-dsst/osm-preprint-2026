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


def _build_filter_clause(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    research_only: bool = False,
    table_alias: str = "p",
) -> tuple[str, list]:
    """Build WHERE clause fragments and params for date/year/research filters.

    Returns (extra_sql, params) where extra_sql starts with ' AND ...' if non-empty.
    """
    parts = []
    params = []
    if date_from:
        parts.append(f"{table_alias}.pub_date >= ?")
        params.append(date_from)
    elif year_from is not None:
        parts.append(f"{table_alias}.pub_year >= ?")
        params.append(year_from)
    if date_to:
        parts.append(f"{table_alias}.pub_date <= ?")
        params.append(date_to)
    elif year_to is not None:
        parts.append(f"{table_alias}.pub_year <= ?")
        params.append(year_to)
    if research_only:
        parts.append(f"{table_alias}.is_research = true")
    if not parts:
        return "", []
    return " AND " + " AND ".join(parts), params


def query_funder_open_data_stats(
    con: duckdb.DuckDBPyConnection,
    min_articles: int = 0,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    research_only: bool = False,
) -> pd.DataFrame:
    """
    Bulk query: join article_funders + funders + pmids to get per-funder
    open data/code stats with coverage breakdown.

    Returns DataFrame with columns: canonical_name, country_code, funder_id,
    total_articles, open_data_articles, open_code_articles,
    pdf_covered, pdf_covered_od, xml_only, xml_only_od
    """
    extra_sql, params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
    )

    query = f"""
    SELECT
        f.canonical_name,
        f.country_code,
        f.funder_id,
        COUNT(DISTINCT af.pmid) AS total_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_data_best = true THEN af.pmid END) AS open_data_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_code_best = true THEN af.pmid END) AS open_code_articles,
        COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 = true
              THEN af.pmid END) AS pdf_covered,
        COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 = true AND p.is_open_data_best = true
              THEN af.pmid END) AS pdf_covered_od,
        COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
              THEN af.pmid END) AS xml_only,
        COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
              AND p.is_open_data_xml_v7 = true THEN af.pmid END) AS xml_only_od
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true){extra_sql}
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
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    research_only: bool = False,
) -> dict:
    """
    Per-group query for parent-child aggregation with coverage breakdown.

    Returns dict with keys: total_articles, open_data_articles, open_code_articles,
    pdf_covered, pdf_covered_od, xml_only, xml_only_od,
    funder_id (of the member with the most articles)
    """
    placeholders = ", ".join(["?"] * len(canonical_names))
    extra_sql, extra_params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
    )

    query = f"""
    SELECT
        COUNT(DISTINCT af.pmid) AS total_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_data_best = true THEN af.pmid END) AS open_data_articles,
        COUNT(DISTINCT CASE WHEN p.is_open_code_best = true THEN af.pmid END) AS open_code_articles,
        COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 = true
              THEN af.pmid END) AS pdf_covered,
        COUNT(DISTINCT CASE WHEN p.has_oddpub_pdf_v7 = true AND p.is_open_data_best = true
              THEN af.pmid END) AS pdf_covered_od,
        COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
              THEN af.pmid END) AS xml_only,
        COUNT(DISTINCT CASE WHEN NOT COALESCE(p.has_oddpub_pdf_v7, false)
              AND p.is_open_data_xml_v7 = true THEN af.pmid END) AS xml_only_od
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)
      AND f.canonical_name IN ({placeholders}){extra_sql}
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
      AND f.canonical_name IN ({placeholders}){extra_sql}
    GROUP BY f.funder_id
    ORDER BY COUNT(DISTINCT af.pmid) DESC
    LIMIT 1
    """
    fid_row = con.execute(fid_query, params).fetchone()
    return {
        "total_articles": row[0],
        "open_data_articles": row[1],
        "open_code_articles": row[2],
        "pdf_covered": row[3],
        "pdf_covered_od": row[4],
        "xml_only": row[5],
        "xml_only_od": row[6],
        "funder_id": fid_row[0] if fid_row else None,
    }


def query_journal_correction_factors(
    con: duckdb.DuckDBPyConnection,
    min_h2h: int = 50,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    research_only: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """
    Compute per-journal correction factors from head-to-head articles
    (those with both XML and PDF oddpub coverage).

    Returns:
        (journal_df, global_stats) where:
        - journal_df: DataFrame with columns: journal, h2h_n, xml_od_rate,
          pdf_od_rate, best_od_rate  (only journals with h2h_n >= min_h2h)
        - global_stats: dict with keys: rate, n (global PDF OD rate across
          all head-to-head articles regardless of min_h2h)
    """
    extra_sql, params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
        table_alias="pmids",
    )

    # Global stats (no min_h2h filter)
    global_q = f"""
    SELECT
        COUNT(*) AS h2h_n,
        SUM(CAST(is_open_data_pdf_v7 AS INT))::DOUBLE / COUNT(*) AS pdf_od_rate,
        SUM(CAST(is_open_data_best AS INT))::DOUBLE / COUNT(*) AS best_od_rate
    FROM pmids
    WHERE has_oddpub_xml_v7 = true AND has_oddpub_pdf_v7 = true{extra_sql}
    """
    grow = con.execute(global_q, params).fetchone()
    global_stats = {"n": grow[0], "rate": grow[1], "best_rate": grow[2]}

    # Per-journal stats
    journal_q = f"""
    SELECT
        journal,
        COUNT(*) AS h2h_n,
        SUM(CAST(is_open_data_xml_v7 AS INT))::DOUBLE / COUNT(*) AS xml_od_rate,
        SUM(CAST(is_open_data_pdf_v7 AS INT))::DOUBLE / COUNT(*) AS pdf_od_rate,
        SUM(CAST(is_open_data_best AS INT))::DOUBLE / COUNT(*) AS best_od_rate
    FROM pmids
    WHERE has_oddpub_xml_v7 = true AND has_oddpub_pdf_v7 = true
      AND journal IS NOT NULL{extra_sql}
    GROUP BY journal
    HAVING COUNT(*) >= {min_h2h}
    ORDER BY COUNT(*) DESC
    """
    journal_df = con.execute(journal_q, params).fetchdf()
    return journal_df, global_stats


def query_funder_journal_xml_only(
    con: duckdb.DuckDBPyConnection,
    canonical_names: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    research_only: bool = False,
) -> pd.DataFrame:
    """
    Get per-funder (or per-group), per-journal XML-only article counts.

    Args:
        canonical_names: If None, bulk query for all funders returning
            (canonical_name, journal, n_xml_only). If a list, group query
            using DISTINCT pmid across those funders returning
            (journal, n_xml_only).

    Returns:
        DataFrame with per-journal XML-only counts.
    """
    extra_sql, extra_params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
    )

    if canonical_names is not None:
        # Group query: DISTINCT pmid across specified funders
        placeholders = ", ".join(["?"] * len(canonical_names))
        query = f"""
        SELECT p.journal, COUNT(DISTINCT af.pmid) AS n_xml_only
        FROM article_funders af
        JOIN funders f ON af.funder_id = f.funder_id
        JOIN pmids p ON af.pmid = p.pmid
        WHERE p.has_oddpub_xml_v7 = true
          AND NOT COALESCE(p.has_oddpub_pdf_v7, false)
          AND p.journal IS NOT NULL
          AND f.canonical_name IN ({placeholders}){extra_sql}
        GROUP BY p.journal
        """
        params = canonical_names + extra_params
    else:
        # Bulk query: per canonical_name, per journal
        query = f"""
        SELECT f.canonical_name, p.journal, COUNT(DISTINCT af.pmid) AS n_xml_only
        FROM article_funders af
        JOIN funders f ON af.funder_id = f.funder_id
        JOIN pmids p ON af.pmid = p.pmid
        WHERE p.has_oddpub_xml_v7 = true
          AND NOT COALESCE(p.has_oddpub_pdf_v7, false)
          AND p.journal IS NOT NULL{extra_sql}
        GROUP BY f.canonical_name, p.journal
        """
        params = extra_params

    return con.execute(query, params).fetchdf()


def query_funder_works_count(
    con: duckdb.DuckDBPyConnection,
    funder_ids: list[str],
) -> dict[str, int]:
    """Return {funder_id: openalex_works_count} for given IDs.

    Queries the funders table for openalex_works_count. Missing or NULL
    values default to 0.
    """
    if not funder_ids:
        return {}
    placeholders = ", ".join(["?"] * len(funder_ids))
    query = f"""
    SELECT funder_id, COALESCE(openalex_works_count, 0) AS wc
    FROM funders
    WHERE funder_id IN ({placeholders})
    """
    rows = con.execute(query, funder_ids).fetchall()
    return {row[0]: row[1] for row in rows}


def query_funder_works_count_by_name(
    con: duckdb.DuckDBPyConnection,
    canonical_names: list[str],
) -> int:
    """Return sum of openalex_works_count for funders matching canonical_names.

    Useful for aggregating works counts across parent-child funder groups
    where the parent entity (e.g. UKRI) has few direct works but children
    (MRC, EPSRC, etc.) have many.
    """
    if not canonical_names:
        return 0
    placeholders = ", ".join(["?"] * len(canonical_names))
    query = f"""
    SELECT COALESCE(SUM(COALESCE(openalex_works_count, 0)), 0) AS total_wc
    FROM funders
    WHERE canonical_name IN ({placeholders})
    """
    row = con.execute(query, canonical_names).fetchone()
    return int(row[0]) if row else 0


def query_journal_open_data_stats(
    con: duckdb.DuckDBPyConnection,
    min_articles: int = 0,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    research_only: bool = False,
) -> pd.DataFrame:
    """
    Per-journal open data/code stats from the pmids table.

    Returns DataFrame with columns: journal, total_articles,
    open_data_articles, open_code_articles, pdf_covered, xml_only
    """
    extra_sql, params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
        table_alias="p",
    )

    query = f"""
    SELECT
        p.journal,
        COUNT(*) AS total_articles,
        SUM(CASE WHEN p.is_open_data_best = true THEN 1 ELSE 0 END) AS open_data_articles,
        SUM(CASE WHEN p.is_open_code_best = true THEN 1 ELSE 0 END) AS open_code_articles,
        SUM(CASE WHEN p.has_oddpub_pdf_v7 = true THEN 1 ELSE 0 END) AS pdf_covered,
        SUM(CASE WHEN p.has_oddpub_xml_v7 = true
             AND NOT COALESCE(p.has_oddpub_pdf_v7, false) THEN 1 ELSE 0 END) AS xml_only
    FROM pmids p
    WHERE p.journal IS NOT NULL
      AND (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true){extra_sql}
    GROUP BY p.journal
    HAVING COUNT(*) >= {min_articles}
    ORDER BY COUNT(*) DESC
    """
    return con.execute(query, params).fetchdf()


def query_baseline_od_rate(
    con: duckdb.DuckDBPyConnection,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    research_only: bool = False,
) -> dict:
    """
    Compute overall open data rate across all articles matching filters.

    Returns dict with keys: total_articles, open_data_articles, baseline_pct
    """
    extra_sql, params = _build_filter_clause(
        date_from, date_to, year_from, year_to, research_only,
        table_alias="p",
    )

    query = f"""
    SELECT
        COUNT(*) AS total_articles,
        SUM(CASE WHEN p.is_open_data_best = true THEN 1 ELSE 0 END) AS open_data_articles
    FROM pmids p
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true){extra_sql}
    """
    row = con.execute(query, params).fetchone()
    total = row[0]
    od = row[1]
    pct = round(100.0 * od / total, 1) if total > 0 else 0.0
    return {"total_articles": total, "open_data_articles": od, "baseline_pct": pct}


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
