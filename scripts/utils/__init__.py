"""
Utility modules for OSM Preprint 2026 data processing and table generation.
"""

from .latex_helpers import (
    escape_latex,
    format_number_siunitx,
    format_number_with_comma,
    get_color_bwr,
    generate_longtable_header,
    generate_longtable_footer
)

from .data_loader import (
    load_oddpub_results,
    load_openalex_metadata,
    join_oddpub_openalex,
    aggregate_by_group,
    connect_duckdb_registry,
    query_funder_open_data_stats,
    query_funder_open_data_for_group
)

__all__ = [
    'escape_latex',
    'format_number_siunitx',
    'format_number_with_comma',
    'get_color_bwr',
    'generate_longtable_header',
    'generate_longtable_footer',
    'load_oddpub_results',
    'load_openalex_metadata',
    'join_oddpub_openalex',
    'aggregate_by_group',
    'connect_duckdb_registry',
    'query_funder_open_data_stats',
    'query_funder_open_data_for_group'
]
