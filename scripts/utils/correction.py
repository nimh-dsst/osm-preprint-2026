"""
Journal-level correction factors for XML-only open data underestimation.

Uses head-to-head best (PDF∪XML) detection rates to estimate true open data
rates for articles that only have XML coverage. Wilson score confidence
intervals are propagated through the weighted correction.
"""

import math
import pandas as pd


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    Returns (lo, hi) as proportions in [0, 1].
    Returns (0.0, 0.0) if n == 0.
    """
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return lo, hi


def build_journal_correction_table(
    journal_df: pd.DataFrame,
    global_stats: dict,
) -> pd.DataFrame:
    """Add Wilson CI columns to journal correction factors.

    Uses best_od_rate (PDF∪XML) from the head-to-head subset, since that
    matches what is_open_data_best would give if both coverages existed.

    Args:
        journal_df: DataFrame from query_journal_correction_factors() with
            columns: journal, h2h_n, xml_od_rate, pdf_od_rate, best_od_rate
        global_stats: dict with keys: rate, n

    Returns:
        DataFrame with columns: journal, best_od_rate, ci_lo, ci_hi, h2h_n
    """
    rows = []
    for _, row in journal_df.iterrows():
        n = int(row["h2h_n"])
        rate = float(row["best_od_rate"])
        successes = round(rate * n)
        lo, hi = wilson_ci(successes, n)
        rows.append({
            "journal": row["journal"],
            "best_od_rate": rate,
            "ci_lo": lo,
            "ci_hi": hi,
            "h2h_n": n,
        })
    result = pd.DataFrame(rows)

    # Compute global fallback CI using best rate
    gn = global_stats["n"]
    grate = global_stats["best_rate"]
    g_successes = round(grate * gn)
    g_lo, g_hi = wilson_ci(g_successes, gn)
    global_stats["ci_lo"] = g_lo
    global_stats["ci_hi"] = g_hi

    return result


def apply_funder_correction(
    funder_journal_xml: pd.DataFrame,
    journal_corrections: pd.DataFrame,
    global_fallback: dict,
    pdf_covered_od: int,
    observed_od: int = 0,
) -> dict:
    """Apply journal-level corrections to one funder's XML-only articles.

    For each journal with XML-only articles for this funder, estimate the
    true number of open data articles using the journal's best detection rate
    from the head-to-head subset. For journals without sufficient h2h data,
    use the global average. Result is floored at the observed OD count.

    Args:
        funder_journal_xml: DataFrame with columns: journal, n_xml_only
        journal_corrections: DataFrame with columns: journal, best_od_rate, ci_lo, ci_hi
        global_fallback: dict with keys: best_rate, ci_lo, ci_hi
        pdf_covered_od: accurate OD count from PDF-covered articles
        observed_od: total observed OD (for flooring)

    Returns:
        dict with keys: corrected_od, ci_lo, ci_hi, n_corrected, n_fallback
    """
    if funder_journal_xml.empty:
        corrected = max(pdf_covered_od, observed_od)
        return {
            "corrected_od": corrected,
            "ci_lo": corrected,
            "ci_hi": corrected,
            "n_corrected": 0,
            "n_fallback": 0,
        }

    # Merge journal corrections
    merged = funder_journal_xml.merge(
        journal_corrections[["journal", "best_od_rate", "ci_lo", "ci_hi"]],
        on="journal",
        how="left",
    )

    # Split into journals with and without correction factors
    has_correction = merged["best_od_rate"].notna()
    with_corr = merged[has_correction]
    without_corr = merged[~has_correction]

    # Corrected estimates from journal-specific rates
    est_point = (with_corr["n_xml_only"] * with_corr["best_od_rate"]).sum()
    est_lo = (with_corr["n_xml_only"] * with_corr["ci_lo"]).sum()
    est_hi = (with_corr["n_xml_only"] * with_corr["ci_hi"]).sum()
    n_corrected = int(with_corr["n_xml_only"].sum())

    # Fallback for journals without enough h2h data
    n_fallback_total = int(without_corr["n_xml_only"].sum()) if not without_corr.empty else 0
    est_point += n_fallback_total * global_fallback["best_rate"]
    est_lo += n_fallback_total * global_fallback["ci_lo"]
    est_hi += n_fallback_total * global_fallback["ci_hi"]

    corrected_od = pdf_covered_od + est_point
    ci_lo = pdf_covered_od + est_lo
    ci_hi = pdf_covered_od + est_hi

    # Floor at observed: corrected estimate should never be below what we actually observed
    corrected_od = max(corrected_od, observed_od)
    ci_lo = max(ci_lo, observed_od)
    ci_hi = max(ci_hi, observed_od)

    return {
        "corrected_od": corrected_od,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_corrected": n_corrected,
        "n_fallback": n_fallback_total,
    }
