"""
LaTeX formatting utilities for table generation.

Adapted from osm-2025-12-poster-incf/analysis/funder_table_latex.py
"""

import math


def escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters.

    Args:
        text: String to escape

    Returns:
        Escaped string safe for LaTeX
    """
    replacements = [
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def format_number_siunitx(n: int) -> str:
    """
    Format integer for siunitx S column (no comma separators).

    Args:
        n: Integer to format

    Returns:
        String representation without commas (siunitx handles formatting)
    """
    return str(int(n))


def format_number_with_comma(n: int) -> str:
    """
    Format number with comma separators for display.

    Args:
        n: Integer to format

    Returns:
        Formatted string with comma separators
    """
    return f"{int(n):,}"


def get_color_bwr(value: float, min_val: float, max_val: float,
                  use_log: bool = False) -> str:
    """
    Get blue-white-red color for conditional formatting.

    Returns LaTeX color definition for cellcolor.
    - Low values: Blue (light blue)
    - Mid values: White
    - High values: Red/Pink (salmon)

    Args:
        value: Value to map to color
        min_val: Minimum value in range
        max_val: Maximum value in range
        use_log: If True, use log scale for mapping

    Returns:
        LaTeX color specification string for \\cellcolor
    """
    if use_log:
        # Log scale
        if value <= 0:
            value = 1
        value = math.log10(value)
        min_val = math.log10(max(min_val, 1))
        max_val = math.log10(max(max_val, 1))

    # Normalize to 0-1 range
    if max_val == min_val:
        normalized = 0.5
    else:
        normalized = (value - min_val) / (max_val - min_val)
    # Clamp: callers may anchor the range on one column (e.g. observed rates)
    # while shading values from another column (corrected) that can fall
    # outside [min_val, max_val]. Without this, an out-of-range value produces
    # a negative rgb channel and breaks LaTeX compilation. (#20)
    normalized = min(1.0, max(0.0, normalized))

    # Map to color: 0 = blue, 0.5 = white, 1 = red
    if normalized < 0.5:
        # Blue to white (low to mid)
        # Blue component stays high, red/green increase
        t = normalized * 2  # 0 to 1
        r = 0.7 + 0.3 * t  # 0.7 to 1.0
        g = 0.7 + 0.3 * t  # 0.7 to 1.0
        b = 1.0
    else:
        # White to red (mid to high)
        # Red component stays high, green/blue decrease
        t = (normalized - 0.5) * 2  # 0 to 1
        r = 1.0
        g = 1.0 - 0.4 * t  # 1.0 to 0.6
        b = 1.0 - 0.6 * t  # 1.0 to 0.4

    # Convert to 0-255 range for xcolor
    r_int = int(r * 255)
    g_int = int(g * 255)
    b_int = int(b * 255)

    return f"{{rgb,255:red,{r_int};green,{g_int};blue,{b_int}}}"


def generate_longtable_header(columns: list, column_format: str = None) -> str:
    """
    Generate longtable header with column specifications.

    Args:
        columns: List of column header strings
        column_format: LaTeX column format string (e.g., 'llccc')
                      If None, defaults to 'l' for each column

    Returns:
        LaTeX string for longtable header
    """
    if column_format is None:
        column_format = 'l' * len(columns)

    lines = []
    lines.append(r"\begingroup")
    lines.append(r"\arrayrulecolor{COL5}")
    lines.append(r"\rowcolors{2}{COL5!10}{white}")
    lines.append(f"\\begin{{longtable}}{{{column_format}}}")
    lines.append(r"\toprule")
    lines.append(" & ".join(columns) + r" \\")
    lines.append(r"\midrule")
    lines.append(r"\endfirsthead")
    lines.append(r"\toprule")
    lines.append(" & ".join(columns) + r" \\")
    lines.append(r"\midrule")
    lines.append(r"\endhead")
    lines.append(r"\midrule")
    lines.append(r"\multicolumn{" + str(len(columns)) + r"}{r}{\textit{Continued on next page...}} \\")
    lines.append(r"\endfoot")
    lines.append(r"\bottomrule")
    lines.append(r"\endlastfoot")

    return "\n".join(lines)


def generate_longtable_footer() -> str:
    """
    Generate longtable footer.

    Returns:
        LaTeX string for longtable footer
    """
    lines = []
    lines.append(r"\end{longtable}")
    lines.append(r"\arrayrulecolor{black}")
    lines.append(r"\endgroup")

    return "\n".join(lines)
