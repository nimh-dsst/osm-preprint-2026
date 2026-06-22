#!/usr/bin/env python3
"""
Generate funder open-data table, bar chart, CSV, and markdown summary.

Queries pmid_registry.duckdb for per-funder open data rates, applies
parent-child aggregation from funder_aliases_v5.csv, and produces:
  - latex/tables/table_funders.tex      (longtable, Weibull 1% threshold)
  - latex/figures/funders_open_data.png  (bar chart, Weibull 0.5% threshold)
  - results/funders_summary.csv         (all funders, min 100 articles)
  - results/funders_summary.md          (all funders with OpenAlex links)
"""

import argparse
import csv
import logging
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from scipy.stats import weibull_min

# Allow running as `python scripts/table_funders.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.data_loader import (
    _find_duckdb_default,
    connect_duckdb_registry,
    query_funder_open_data_stats,
    query_funder_open_data_for_group,
    query_journal_correction_factors,
    query_funder_journal_xml_only,
    query_funder_works_count_by_name,
)
from utils.latex_helpers import (
    escape_latex,
    format_number_siunitx,
    get_color_bwr,
)
from utils.correction import (
    build_journal_correction_table,
    apply_funder_correction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DuckDB canonical_name overrides for v5 entries without openalex_name
# (v5 has openalex_name for 102/133 funders; these 15 need manual mapping)
# ---------------------------------------------------------------------------
_DB_NAME_OVERRIDES: dict[str, list[str]] = {
    # --- Entries with no openalex match in v5 (openalex_name is NaN) ---
    "Bundesministerium fur Bildung und Forschung": [
        "Bundesministerium für Bildung und Forschung",
    ],
    "Coordenacao de Aperfeicoamento de Pessoal de Nivel Superior": [
        "Coordenação de Aperfeiçoamento de Pessoal de Nível Superior",
    ],
    "Czech Science Foundation": [
        "Grantová Agentura České Republiky",
    ],
    "Department of Biotechnology": [
        "Department of Biotechnology, Ministry of Science and Technology, India",
    ],
    "Fundacao de Amparo a Pesquisa do Estado de Sao Paulo": [
        "Fundação de Amparo à Pesquisa do Estado de São Paulo",
    ],
    "Fundacao para a Ciencia e a Tecnologia": [
        "Fundação para a Ciência e a Tecnologia",
    ],
    "Italian Ministry": [
        "Ministero dell'Istruzione, dell'Università e della Ricerca",
        "Ministero della Salute",
        "Ministero dell'Università e della Ricerca",
    ],
    "Max Planck Society": [
        "Max-Planck-Gesellschaft",
    ],
    "Ministerio de Economia y Competitividad": [
        "Ministerio de Economía y Competitividad",
    ],
    "National Science Centre": [
        "Narodowe Centrum Nauki",
    ],
    "Netherlands Organisation for Scientific Research": [
        "Nederlandse Organisatie voor Wetenschappelijk Onderzoek",
    ],
    "Research Foundation Flanders": [
        "Fonds Wetenschappelijk Onderzoek",
    ],
    "Swedish Research Council": [
        "Vetenskapsrådet",
    ],
    "Swiss National Science Foundation": [
        "Schweizerischer Nationalfonds zur Förderung der Wissenschaftlichen Forschung",
    ],
    # --- Multi-name DuckDB aggregation (has openalex_name but needs extra) ---
    "Wellcome Trust": [
        "Wellcome Trust",
        "Wellcome",
    ],
}

# ---------------------------------------------------------------------------
# English display names for non-English DuckDB canonical_names
# (for unaliased funders that appear in results)
# ---------------------------------------------------------------------------
ENGLISH_DISPLAY_NAMES: dict[str, str] = {
    # Brazil
    "Conselho Nacional de Desenvolvimento Científico e Tecnológico":
        "National Council for Scientific and Technological Development (CNPq)",
    "Fundação Carlos Chagas Filho de Amparo à Pesquisa do Estado do Rio de Janeiro":
        "Rio de Janeiro Research Foundation (FAPERJ)",
    "Fundação de Amparo à Pesquisa do Estado de Minas Gerais":
        "Minas Gerais Research Foundation (FAPEMIG)",
    # Spain
    "Ministerio de Ciencia e Innovación":
        "Ministry of Science and Innovation (Spain)",
    "Agencia Estatal de Investigación":
        "State Research Agency (Spain)",
    "Ministerio de Ciencia, Innovación y Universidades":
        "Ministry of Science, Innovation and Universities (Spain)",
    # France
    "Institut National de la Santé et de la Recherche Médicale":
        "National Institute of Health and Medical Research (INSERM)",
    "Fondation pour la Recherche Médicale":
        "Foundation for Medical Research (France)",
    # Norway
    "Norges Forskningsråd": "Research Council of Norway",
    # Sweden
    "Forskningsrådet om Hälsa, Arbetsliv och Välfärd":
        "Swedish Research Council for Health, Working Life and Welfare (Forte)",
    "Forskningsrådet för Miljö, Areella Näringar och Samhällsbyggande":
        "Swedish Research Council for Environment, Agricultural Sciences and Spatial Planning (Formas)",
    "Stiftelsen för Strategisk Forskning":
        "Swedish Foundation for Strategic Research (SSF)",
    # Mexico
    "Consejo Nacional de Ciencia y Tecnología":
        "National Council of Science and Technology (CONACYT, Mexico)",
    # Turkey
    "Türkiye Bilimsel ve Teknolojik Araştırma Kurumu":
        "Scientific and Technological Research Council of Turkey (TUBITAK)",
    # Chile
    "Comisión Nacional de Investigación Científica y Tecnológica":
        "National Commission for Scientific and Technological Research (CONICYT, Chile)",
    "Agencia Nacional de Investigación y Desarrollo":
        "National Agency for Research and Development (ANID, Chile)",
    "Fondo Nacional de Desarrollo Científico y Tecnológico":
        "National Fund for Scientific and Technological Development (FONDECYT, Chile)",
    # Argentina
    "Consejo Nacional de Investigaciones Científicas y Técnicas":
        "National Scientific and Technical Research Council (CONICET, Argentina)",
    "Agencia Nacional de Promoción Científica y Tecnológica":
        "National Agency for Scientific and Technological Promotion (ANPCyT, Argentina)",
    # Hungary
    "Nemzeti Kutatási Fejlesztési és Innovációs Hivatal":
        "National Research, Development and Innovation Office (Hungary)",
    "Magyar Tudományos Akadémia":
        "Hungarian Academy of Sciences",
    # Czech Republic
    "Ministerstvo Školství, Mládeže a Tělovýchovy":
        "Ministry of Education, Youth and Sports (Czech Republic)",
    # Italy
    "Ministero dell'Istruzione, dell'Università e della Ricerca":
        "Ministry of Education, University and Research (MIUR, Italy)",
    "Ministero della Salute": "Ministry of Health (Italy)",
    "Ministero dell'Università e della Ricerca":
        "Ministry of University and Research (MUR, Italy)",
    # Portugal
    "Centro de Ciências do Mar": "Center for Marine Sciences (Portugal)",
    # Colombia
    "Departamento Administrativo de Ciencia, Tecnología e Innovación":
        "Administrative Department of Science, Technology and Innovation (COLCIENCIAS, Colombia)",
    # Canada (French)
    "Fonds de recherche du Québec - Santé":
        "Quebec Health Research Fund (FRQS)",
    # Finland
    "Sigrid Juséliuksen Säätiö": "Sigrid Juselius Foundation (Finland)",
    # Slovakia
    "Agentúra na Podporu Výskumu a Vývoja":
        "Slovak Research and Development Agency (APVV)",
}


# ---------------------------------------------------------------------------
# FunderNormalizer — reads aliases CSV, builds parent-child groups
# ---------------------------------------------------------------------------
class FunderNormalizer:
    """Load funder_aliases_v5.csv and build aggregation groups.

    v5 columns used:
      - canonical_name: English display name
      - openalex_name: exact DuckDB canonical_name (NaN for 16 entries)
      - openalex_id: DuckDB funder_id for OpenAlex links
      - openalex_country: DuckDB country_code
      - parent_funder: parent group name (NIH, UKRI, European Commission)
      - country: alias CSV country (fallback)
      - funder_type: government, private, etc.
    """

    def __init__(self, aliases_csv: Path):
        self.aliases_csv = Path(aliases_csv)
        # canonical_name → {country, parent_funder, funder_type, openalex_id, openalex_name, openalex_country}
        self.funder_info: dict[str, dict] = {}
        # parent display_name → set of child canonical_names
        self.parent_children: dict[str, set[str]] = {}
        self._load()

    def _load(self):
        with open(self.aliases_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cname = row["canonical_name"]
                if cname not in self.funder_info:
                    oa_name = row.get("openalex_name", "")
                    oa_id = row.get("openalex_id", "")
                    oa_country = row.get("openalex_country", "")
                    self.funder_info[cname] = {
                        "country": row.get("country", ""),
                        "parent_funder": row.get("parent_funder", ""),
                        "funder_type": row.get("funder_type", ""),
                        "openalex_id": oa_id if oa_id and oa_id != "nan" else "",
                        "openalex_name": oa_name if oa_name and oa_name != "nan" else "",
                        "openalex_country": oa_country if oa_country and oa_country != "nan" else "",
                    }
                parent = row.get("parent_funder", "").strip()
                if parent:
                    self.parent_children.setdefault(parent, set()).add(cname)

    def _resolve_db_names(self, alias_name: str) -> list[str]:
        """Map an alias canonical_name to a list of DuckDB canonical_names.

        Priority:
          1. _DB_NAME_OVERRIDES (for multi-name aggregation and no-openalex entries)
          2. openalex_name from v5 CSV (exact DuckDB canonical_name)
          3. canonical_name itself (last resort)
        """
        if alias_name in _DB_NAME_OVERRIDES:
            return _DB_NAME_OVERRIDES[alias_name]
        info = self.funder_info.get(alias_name, {})
        oa_name = info.get("openalex_name", "")
        if oa_name:
            return [oa_name]
        return [alias_name]

    def get_openalex_id(self, canonical_name: str) -> str:
        """Get openalex_id for a canonical_name from v5 CSV."""
        info = self.funder_info.get(canonical_name, {})
        return info.get("openalex_id", "")

    def get_aggregation_groups(self) -> list[dict]:
        """
        Return aggregation groups. Each group is:
          {display_name, db_names: [str], country, funder_type, is_parent, openalex_id}

        Parent funders (e.g. NIH, UKRI, European Commission) aggregate all
        children plus their own direct entry. Standalone funders become
        single-entry groups.
        """
        groups = []
        children_consumed: set[str] = set()

        # 1) Parent groups
        for parent_display, children in self.parent_children.items():
            db_names: list[str] = []
            for child in children:
                db_names.extend(self._resolve_db_names(child))
            # Also include the parent itself (it may appear as its own funder)
            if parent_display in self.funder_info:
                db_names.extend(self._resolve_db_names(parent_display))

            # Country + openalex_id: use parent's own info if available
            info = self.funder_info.get(parent_display, {})
            if not info:
                first_child = next(iter(children))
                info = self.funder_info.get(first_child, {})

            groups.append({
                "display_name": parent_display,
                "db_names": list(set(db_names)),
                "country": info.get("country", ""),
                "funder_type": info.get("funder_type", ""),
                "openalex_id": info.get("openalex_id", ""),
                "is_parent": True,
            })
            children_consumed.update(children)
            if parent_display in self.funder_info:
                children_consumed.add(parent_display)

        # 2) Standalone funders (not consumed as children)
        for cname, info in self.funder_info.items():
            if cname in children_consumed:
                continue
            groups.append({
                "display_name": cname,
                "db_names": self._resolve_db_names(cname),
                "country": info.get("country", ""),
                "funder_type": info.get("funder_type", ""),
                "openalex_id": info.get("openalex_id", ""),
                "is_parent": False,
            })

        return groups


# ---------------------------------------------------------------------------
# Weibull threshold
# ---------------------------------------------------------------------------
def compute_weibull_threshold(
    article_counts: np.ndarray,
    survival: float = 0.01,
    min_articles: int = 100,
) -> tuple[int, int, tuple]:
    """
    Fit Weibull to log(article_counts) and return the threshold
    at the given survival probability.

    Args:
        article_counts: array of total_articles per funder
        survival: survival probability (e.g. 0.01 = top 1%)
        min_articles: minimum articles to include in fit

    Returns:
        (threshold, n_above, (shape, loc, scale)) tuple
    """
    counts = article_counts[article_counts >= min_articles]
    log_counts = np.log(counts)
    shape, loc, scale = weibull_min.fit(log_counts)
    threshold_log = weibull_min.isf(survival, shape, loc=loc, scale=scale)
    threshold = int(np.exp(threshold_log))
    n_above = int((counts >= threshold).sum())
    return threshold, n_above, (shape, loc, scale)


# ---------------------------------------------------------------------------
# English name resolution
# ---------------------------------------------------------------------------
def _resolve_english_name(name: str) -> str:
    """Return English display name if available, else original."""
    return ENGLISH_DISPLAY_NAMES.get(name, name)


# ---------------------------------------------------------------------------
# build_funder_summary
# ---------------------------------------------------------------------------
def build_funder_summary(
    con,
    normalizer: FunderNormalizer,
    bulk_stats: pd.DataFrame,
    min_articles: int = 100,
    journal_corrections: pd.DataFrame | None = None,
    global_correction: dict | None = None,
    funder_journal_xml_bulk: pd.DataFrame | None = None,
    **filter_kwargs,
) -> pd.DataFrame:
    """
    Build the full funder summary DataFrame.

    For alias groups (parent-child), queries DuckDB with DISTINCT counts.
    For unaliased funders, uses the bulk_stats DataFrame.

    If journal_corrections is provided, computes corrected open data rates
    and 95% imputation intervals for each funder based on journal-level PDF
    detection rates. The interval reflects uncertainty in the XML-only
    correction only; observed rates are census-exact and carry no interval.
    """
    apply_correction = journal_corrections is not None
    rows = []

    # --- Alias groups (parent + standalone from aliases CSV) ---
    alias_db_names_used: set[str] = set()
    groups = normalizer.get_aggregation_groups()

    for group in groups:
        db_names = group["db_names"]
        if not db_names:
            continue
        alias_db_names_used.update(db_names)

        stats = query_funder_open_data_for_group(
            con, db_names, **filter_kwargs,
        )
        total = stats["total_articles"]
        if total < min_articles:
            continue

        od = stats["open_data_articles"]
        oc = stats["open_code_articles"]

        # Prefer openalex_id from v5 CSV; fall back to DuckDB query result
        funder_id = group.get("openalex_id", "") or stats.get("funder_id", "") or ""

        # Country: prefer DuckDB country_code from the largest child
        country = _country_from_bulk(bulk_stats, db_names) or group["country"]

        # Aggregated OpenAlex works count across all member funders
        agg_works = query_funder_works_count_by_name(con, db_names)

        row_dict = {
            "funder_name": group["display_name"],
            "country": country,
            "total_articles": total,
            "open_data_articles": od,
            "open_code_articles": oc,
            "open_data_pct": round(100.0 * od / total, 1) if total else 0.0,
            "open_code_pct": round(100.0 * oc / total, 1) if total else 0.0,
            "funder_type": group["funder_type"],
            "funder_id": funder_id,
            "is_alias_group": True,
            "pdf_covered": stats.get("pdf_covered", 0),
            "xml_only": stats.get("xml_only", 0),
            "aggregated_works_count": agg_works,
        }

        if apply_correction:
            # Query per-journal XML-only for this group
            group_xml = query_funder_journal_xml_only(
                con, db_names, **filter_kwargs,
            )
            corr = apply_funder_correction(
                group_xml, journal_corrections, global_correction,
                pdf_covered_od=stats.get("pdf_covered_od", 0),
                observed_od=od,
            )
            row_dict.update(_correction_fields(corr, total))

        rows.append(row_dict)

    # --- Unaliased funders from bulk stats ---
    # Pre-index bulk XML-only data by canonical_name for fast lookup
    bulk_xml_by_name = {}
    if apply_correction and funder_journal_xml_bulk is not None:
        for cname, grp in funder_journal_xml_bulk.groupby("canonical_name"):
            bulk_xml_by_name[cname] = grp[["journal", "n_xml_only"]].copy()

    for _, row in bulk_stats.iterrows():
        cname = row["canonical_name"]
        if cname in alias_db_names_used:
            continue
        total = int(row["total_articles"])
        if total < min_articles:
            continue
        od = int(row["open_data_articles"])
        oc = int(row["open_code_articles"])
        cc = row["country_code"] if pd.notna(row["country_code"]) else ""
        funder_id = row["funder_id"] if pd.notna(row.get("funder_id", None)) else ""
        # Single funder works count
        agg_works = query_funder_works_count_by_name(con, [cname])

        row_dict = {
            "funder_name": _resolve_english_name(cname),
            "country": _country_code_to_name(cc),
            "total_articles": total,
            "open_data_articles": od,
            "open_code_articles": oc,
            "open_data_pct": round(100.0 * od / total, 1) if total else 0.0,
            "open_code_pct": round(100.0 * oc / total, 1) if total else 0.0,
            "funder_type": "",
            "funder_id": str(funder_id),
            "is_alias_group": False,
            "pdf_covered": int(row.get("pdf_covered", 0)),
            "xml_only": int(row.get("xml_only", 0)),
            "aggregated_works_count": agg_works,
        }

        if apply_correction:
            funder_xml = bulk_xml_by_name.get(cname, pd.DataFrame(columns=["journal", "n_xml_only"]))
            corr = apply_funder_correction(
                funder_xml, journal_corrections, global_correction,
                pdf_covered_od=int(row.get("pdf_covered_od", 0)),
                observed_od=od,
            )
            row_dict.update(_correction_fields(corr, total))

        rows.append(row_dict)

    if not rows:
        cols = [
            "funder_name", "country", "total_articles", "open_data_articles",
            "open_code_articles", "open_data_pct", "open_code_pct",
            "funder_type", "funder_id", "is_alias_group",
            "pdf_covered", "xml_only", "aggregated_works_count",
        ]
        if apply_correction:
            cols += ["corrected_od", "corrected_pct", "ci_lo_pct", "ci_hi_pct"]
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows)
    df.sort_values("open_data_pct", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _correction_fields(corr: dict, total: int) -> dict:
    """Convert correction dict to row fields with percentages."""
    if total == 0:
        return {"corrected_od": 0, "corrected_pct": 0.0, "ci_lo_pct": None, "ci_hi_pct": None}
    # ci_lo/ci_hi are None when no imputation interval applies (no XML-only
    # articles, or the band floored to a point); carry that through as None. #24
    ci_lo, ci_hi = corr["ci_lo"], corr["ci_hi"]
    # CI percentages kept at full precision in the CSV so real-but-narrow
    # imputation intervals stay distinct (display rounds to 1 dp). #24
    return {
        "corrected_od": corr["corrected_od"],
        "corrected_pct": round(100.0 * corr["corrected_od"] / total, 1),
        "ci_lo_pct": None if ci_lo is None else round(100.0 * ci_lo / total, 6),
        "ci_hi_pct": None if ci_hi is None else round(100.0 * ci_hi / total, 6),
    }


def _country_from_bulk(bulk_stats: pd.DataFrame, db_names: list[str]) -> str:
    """Get country from bulk stats for the largest child funder."""
    subset = bulk_stats[bulk_stats["canonical_name"].isin(db_names)]
    if subset.empty:
        return ""
    largest = subset.sort_values("total_articles", ascending=False).iloc[0]
    cc = largest["country_code"]
    if pd.isna(cc) or cc == "":
        return ""
    return _country_code_to_name(str(cc))


# Compact ISO-3166 alpha-2 → short display name
_COUNTRY_MAP = {
    "AU": "Australia", "AT": "Austria", "BE": "Belgium", "BR": "Brazil",
    "CA": "Canada", "CN": "China", "CZ": "Czech Republic", "DK": "Denmark",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HK": "Hong Kong", "IN": "India", "IR": "Iran", "IE": "Ireland",
    "IL": "Israel", "IT": "Italy", "JP": "Japan", "KR": "Korea",
    "MY": "Malaysia", "MX": "Mexico", "NL": "Netherlands", "NZ": "New Zealand",
    "NO": "Norway", "PK": "Pakistan", "PL": "Poland", "PT": "Portugal",
    "RU": "Russia", "SA": "Saudi Arabia", "SG": "Singapore", "ZA": "South Africa",
    "ES": "Spain", "SE": "Sweden", "CH": "Switzerland", "TW": "Taiwan",
    "TH": "Thailand", "TR": "Turkey", "GB": "UK", "US": "USA",
}


def _country_code_to_name(code: str) -> str:
    """Convert ISO-3166 alpha-2 to short display name."""
    return _COUNTRY_MAP.get(code.upper().strip(), code)


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------
def generate_funder_latex_table(
    df: pd.DataFrame,
    output_path: Path,
    threshold: int = 0,
    n_total_funders: int = 0,
    survival_pct: float = 1.0,
    label_suffix: str = "",
) -> None:
    """Write a longtable .tex file for funders above the threshold."""
    top = df[df["total_articles"] >= threshold].copy() if threshold > 0 else df.copy()
    top.sort_values("open_data_pct", ascending=False, inplace=True)

    if top.empty:
        logger.warning("No funders above threshold %d for table", threshold)
        return

    has_correction = "corrected_pct" in top.columns and top["corrected_pct"].notna().any()

    min_total = top["total_articles"].min()
    max_total = top["total_articles"].max()
    pct_col = "corrected_pct" if has_correction else "open_data_pct"
    min_pct = top[pct_col].min()
    max_pct = top[pct_col].max()

    lines = []
    lines.append(r"% Auto-generated by scripts/table_funders.py — do not edit manually")
    lines.append(r"\begingroup")
    lines.append(r"\arrayrulecolor{COL5}")
    lines.append(r"\rowcolors{2}{COL5!10}{white}")
    lines.append(r"\small")

    if has_correction:
        col_spec = r"p{5.5cm} l S[table-format=6.0] S[table-format=5.0] S[table-format=2.1] S[table-format=2.1]"
        n_cols = 6
    else:
        col_spec = r"p{5.5cm} l S[table-format=6.0] S[table-format=5.0] S[table-format=2.1]"
        n_cols = 5
    lines.append(rf"\begin{{longtable}}{{{col_spec}}}")

    # Caption with methodology note
    surv_str = f"{survival_pct:g}"
    if has_correction:
        caption = (
            r"Open data rates among major biomedical research funders. "
            rf"Funders exceeding the Weibull-derived {surv_str}\% survival threshold "
            rf"for total funded articles ($\geq${threshold:,} articles with "
            r"oddpub v7 coverage), ranked by observed open data rate. "
            r"Parent funders (e.g., NIH, UKRI) aggregate all child institutes "
            r"with deduplicated article counts. "
            r"\% OD (obs.) shows the directly measured rate; "
            r"\% OD (est.) applies journal-level correction factors from "
            r"head-to-head PDF vs.\ XML comparison to estimate the true rate "
            r"for articles with XML-only coverage. "
            r"Cell shading: Total Pubs uses a blue-to-red gradient on log scale; "
            r"\% OD columns use a linear blue-to-red gradient. "
            rf"Full rankings for all {n_total_funders:,} funders are available "
            r"in the supplementary materials on GitHub."
        )
    else:
        caption = (
            r"Open data rates among major biomedical research funders. "
            rf"Funders exceeding the Weibull-derived {surv_str}\% survival threshold "
            rf"for total funded articles ($\geq${threshold:,} articles with "
            r"oddpub v7 coverage), ranked by open data rate. "
            r"Parent funders (e.g., NIH, UKRI) aggregate all child institutes "
            r"with deduplicated article counts. "
            r"Cell shading: Total Pubs uses a blue-to-red gradient on log scale; "
            r"\% Open Data uses a linear blue-to-red gradient. "
            rf"Full rankings for all {n_total_funders:,} funders are available "
            r"in the supplementary materials on GitHub."
        )
    lines.append(rf"\caption{{{caption}}}")
    lines.append(rf"\label{{tab:funders{label_suffix}}} \\")

    # Header
    if has_correction:
        header_row = (
            r"\textbf{Funder} & \textbf{Country} & "
            r"{\textbf{Total Pubs}} & {\textbf{Open Data}} & "
            r"{\textbf{\% OD (obs.)}} & {\textbf{\% OD (est.)}} \\"
        )
    else:
        header_row = (
            r"\textbf{Funder} & \textbf{Country} & "
            r"{\textbf{Total Pubs}} & {\textbf{Open Data}} & "
            r"{\textbf{\% Open Data}} \\"
        )
    lines.append(r"\toprule")
    lines.append(header_row)
    lines.append(r"\midrule")
    lines.append(r"\endfirsthead")
    lines.append(r"\toprule")
    lines.append(header_row)
    lines.append(r"\midrule")
    lines.append(r"\endhead")
    lines.append(r"\midrule")
    lines.append(
        rf"\multicolumn{{{n_cols}}}{{r}}{{\textit{{Continued on next page\ldots}}}} \\"
    )
    lines.append(r"\endfoot")
    lines.append(r"\bottomrule")
    lines.append(r"\endlastfoot")

    # Data rows
    for _, row in top.iterrows():
        name = escape_latex(str(row["funder_name"]))
        country = escape_latex(str(row["country"]))
        total = format_number_siunitx(row["total_articles"])
        od = format_number_siunitx(row["open_data_articles"])
        pct = f"{row['open_data_pct']:.1f}"

        color_total = get_color_bwr(row["total_articles"], min_total, max_total, use_log=True)
        color_pct = get_color_bwr(row["open_data_pct"], min_pct, max_pct)

        if has_correction:
            corr_pct = f"{row['corrected_pct']:.1f}"
            color_corr = get_color_bwr(row["corrected_pct"], min_pct, max_pct)
            lines.append(
                f"{name} & {country} & "
                f"\\cellcolor{color_total} {total} & "
                f"\\cellcolor{color_pct} {od} & "
                f"\\cellcolor{color_pct} {pct} & "
                f"\\cellcolor{color_corr} {corr_pct} \\\\"
            )
        else:
            lines.append(
                f"{name} & {country} & "
                f"\\cellcolor{color_total} {total} & "
                f"\\cellcolor{color_pct} {od} & "
                f"\\cellcolor{color_pct} {pct} \\\\"
            )

    lines.append(r"\end{longtable}")
    lines.append(r"\arrayrulecolor{black}")
    lines.append(r"\endgroup")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote LaTeX table: %s (%d funders)", output_path, len(top))


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------
def generate_funder_bar_chart(
    df: pd.DataFrame,
    output_path: Path,
    threshold: int = 0,
    baseline_pct: float | None = None,
) -> None:
    """
    Horizontal bar chart of funders above the Weibull threshold.

    If corrected_pct is available, draws dual-segment bars:
    - Full bar (lighter shade) = corrected_pct (estimated)
    - Inner bar (full opacity) = open_data_pct (observed)
    - Error whiskers from ci_lo_pct to ci_hi_pct
    """
    top = df[df["total_articles"] >= threshold].copy() if threshold > 0 else df.copy()
    top.sort_values("open_data_pct", ascending=False, inplace=True)

    if top.empty:
        logger.warning("No funders above threshold %d for figure", threshold)
        return

    has_correction = "corrected_pct" in top.columns and top["corrected_pct"].notna().any()

    top = top.iloc[::-1]  # reverse so highest is at top of chart
    n_funders = len(top)

    labels = [
        f"{row['funder_name']} ({row['country']})" if row["country"] else row["funder_name"]
        for _, row in top.iterrows()
    ]
    observed = top["open_data_pct"].values
    totals = top["total_articles"].values

    # Color: total articles on log scale using YlOrRd colormap
    norm = mcolors.LogNorm(vmin=totals.min(), vmax=totals.max())
    cmap = plt.cm.YlOrRd
    colors = [cmap(norm(t)) for t in totals]
    colors_light = [(*c[:3], 0.35) for c in colors]  # lighter shade for estimated

    fig, ax = plt.subplots(figsize=(10, 0.45 * n_funders + 2.0))

    if has_correction:
        corrected = top["corrected_pct"].values
        ci_lo = top["ci_lo_pct"].values
        ci_hi = top["ci_hi_pct"].values

        # Background bar: corrected estimate (lighter)
        ax.barh(
            range(n_funders), corrected,
            color=colors_light, edgecolor="grey", linewidth=0.3,
        )
        # Foreground bar: observed (full opacity)
        bars = ax.barh(
            range(n_funders), observed,
            color=colors, edgecolor="grey", linewidth=0.3,
        )
        # Error whiskers
        ax.errorbar(
            corrected, range(n_funders),
            # clamp ≥0: ci_*_pct are full precision while corrected is 1 dp, so
            # rounding can make a difference marginally negative. NaN whiskers
            # (no imputation interval) are skipped by matplotlib. #24
            xerr=[np.clip(corrected - ci_lo, 0, None), np.clip(ci_hi - corrected, 0, None)],
            fmt="none", ecolor="black", elinewidth=0.8, capsize=2, capthick=0.8,
        )

        # ci_hi is NaN where no imputation interval applies; ignore those when
        # sizing the axis. #24
        max_val = np.nanmax(np.concatenate([ci_hi, corrected, observed]))

        # Value labels: "observed% (est. corrected%)"
        for i, (obs_v, corr_v) in enumerate(zip(observed, corrected)):
            ax.text(
                max(obs_v, corr_v) + 0.5, i,
                f"{obs_v:.1f}% (est. {corr_v:.1f}%)",
                va="center", fontsize=7,
            )

        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=cmap(0.5), edgecolor="grey", label="Observed"),
            Patch(facecolor=(*cmap(0.5)[:3], 0.35), edgecolor="grey", label="Estimated (corrected)"),
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8, framealpha=0.9)
    else:
        bars = ax.barh(
            range(n_funders), observed,
            color=colors, edgecolor="grey", linewidth=0.3,
        )
        max_val = observed.max()

        for bar, val in zip(bars, observed):
            ax.text(
                bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=8,
            )

    ax.set_yticks(range(n_funders))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("% Articles with Open Data Statement", fontsize=11)
    ax.set_title("Open Data Rates Among Major Funders", fontsize=13, fontweight="bold")

    # Colorbar for total articles
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, aspect=30, shrink=0.8)
    cbar.set_label("Total Funded Articles", fontsize=10)

    # Baseline line
    if baseline_pct is not None:
        ax.axvline(baseline_pct, color="grey", linestyle="--", linewidth=1, alpha=0.7)
        ax.text(
            baseline_pct + 0.3, -0.8,
            f"Funded baseline: {baseline_pct:.1f}%",
            fontsize=8, color="grey", va="top",
        )

    ax.set_xlim(0, max_val * 1.15)
    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote figure: %s (%d funders)", output_path, n_funders)


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------
def save_summary_csv(df: pd.DataFrame, output_path: Path) -> None:
    """Save the full funder summary as CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Wrote CSV summary: %s (%d rows)", output_path, len(df))


# ---------------------------------------------------------------------------
# Markdown output with OpenAlex links
# ---------------------------------------------------------------------------
def save_summary_markdown(
    df: pd.DataFrame,
    output_path: Path,
    baseline_pct: float = 0.0,
) -> None:
    """Save the full funder summary as markdown with OpenAlex links."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    has_correction = "corrected_pct" in df.columns and df["corrected_pct"].notna().any()

    lines = []
    lines.append("# Funder Open Data Rankings")
    lines.append("")
    lines.append(f"> Generated {date.today().isoformat()} from pmid_registry.duckdb")
    lines.append(f"> {len(df):,} funders with ≥100 funded articles and oddpub v7 coverage")
    lines.append(f"> Funded-article baseline: {baseline_pct:.1f}% open data")
    if has_correction:
        lines.append("> Corrected rates estimated using journal-level PDF vs XML detection factors")
    lines.append("")

    if has_correction:
        lines.append(
            "| Rank | Funder | Country | Total Pubs | Open Data | % OD (obs.) | % OD (est.) | 95% Imp. Interval | OpenAlex |"
        )
        lines.append(
            "|---:|---|---|---:|---:|---:|---:|---|---|"
        )
    else:
        lines.append(
            "| Rank | Funder | Country | Total Pubs | Open Data | % Open Data | OpenAlex |"
        )
        lines.append(
            "|---:|---|---|---:|---:|---:|---|"
        )

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        name = str(row["funder_name"])
        country = str(row["country"])
        total = f"{int(row['total_articles']):,}"
        od = f"{int(row['open_data_articles']):,}"
        pct = f"{row['open_data_pct']:.1f}%"

        funder_id = str(row.get("funder_id", ""))
        if funder_id and funder_id != "nan" and funder_id != "":
            openalex = f"[{funder_id}](https://openalex.org/funders/{funder_id})"
        else:
            openalex = ""

        if has_correction:
            corr_pct = f"{row['corrected_pct']:.1f}%"
            # Three display states (#24):
            #   None            -> correction did nothing (no XML-only / floored)
            #   width < 0.1pp    -> real interval narrower than display precision
            #   width >= 0.1pp   -> normal interval
            lo_p, hi_p = row["ci_lo_pct"], row["ci_hi_pct"]
            if pd.isna(lo_p) or pd.isna(hi_p):
                ci = "—"
            elif round(lo_p, 1) == round(hi_p, 1):
                ci = f"{row['corrected_pct']:.1f}%"
            else:
                ci = f"{lo_p:.1f}–{hi_p:.1f}%"
            lines.append(
                f"| {rank} | {name} | {country} | {total} | {od} | {pct} | {corr_pct} | {ci} | {openalex} |"
            )
        else:
            lines.append(f"| {rank} | {name} | {country} | {total} | {od} | {pct} | {openalex} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote markdown summary: %s (%d rows)", output_path, len(df))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--duckdb-path",
        default=_find_duckdb_default(),
        help="Path to pmid_registry.duckdb",
    )
    p.add_argument(
        "--aliases-csv",
        default=str(Path(__file__).resolve().parent / "funder_aliases_v5.csv"),
        help="Path to funder_aliases_v5.csv",
    )
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "latex" / "tables"),
        help="Directory for LaTeX table output",
    )
    p.add_argument(
        "--figures-dir",
        default=str(Path(__file__).resolve().parent.parent / "latex" / "figures"),
        help="Directory for figure output",
    )
    p.add_argument(
        "--results-dir",
        default=str(Path(__file__).resolve().parent.parent / "results"),
        help="Directory for CSV and markdown output",
    )
    p.add_argument(
        "--figure-survival", type=float, default=0.005,
        help="Weibull survival for figure threshold (default: 0.005 = 0.5%%)",
    )
    p.add_argument(
        "--table-survival", type=float, default=0.01,
        help="Weibull survival for table threshold (default: 0.01 = 1%%)",
    )
    p.add_argument("--min-articles", type=int, default=100, help="Minimum articles for CSV/markdown")
    p.add_argument("--year-from", type=int, default=None, help="Filter by pub_year >= (fallback if --date-from not set)")
    p.add_argument("--year-to", type=int, default=None, help="Filter by pub_year <= (fallback if --date-to not set)")
    p.add_argument("--date-from", default=None, help="Filter by pub_date >= (YYYY-MM-DD)")
    p.add_argument("--date-to", default=None, help="Filter by pub_date <= (YYYY-MM-DD)")
    p.add_argument("--research-only", action="store_true", help="Only include research articles (is_research=true)")
    p.add_argument("--output-suffix", default="", help="Suffix for output filenames (e.g. '_2024' → table_funders_2024.tex)")
    p.add_argument("--no-correction", action="store_true", help="Disable journal-level XML→PDF correction factors")
    p.add_argument("--min-h2h-articles", type=int, default=50, help="Min head-to-head articles for journal correction (default: 50)")
    p.add_argument(
        "--min-works-figure", type=int, default=0,
        help="Min aggregated OpenAlex works count for figure (0 = no filter)",
    )
    p.add_argument(
        "--min-works-table", type=int, default=0,
        help="Min aggregated OpenAlex works count for table (0 = no filter)",
    )
    p.add_argument("--no-works-filter", action="store_true", help="Disable works-count filter entirely")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger.info("Connecting to DuckDB: %s", args.duckdb_path)
    con = connect_duckdb_registry(args.duckdb_path)

    logger.info("Loading funder aliases: %s", args.aliases_csv)
    normalizer = FunderNormalizer(args.aliases_csv)
    logger.info(
        "  %d alias canonical names, %d parent groups",
        len(normalizer.funder_info),
        len(normalizer.parent_children),
    )

    # Date / year / research filters
    filter_kwargs = {}
    parts = []
    if args.date_from:
        filter_kwargs["date_from"] = args.date_from
        parts.append(f"pub_date >= {args.date_from}")
    elif args.year_from:
        filter_kwargs["year_from"] = args.year_from
        parts.append(f"pub_year >= {args.year_from}")
    if args.date_to:
        filter_kwargs["date_to"] = args.date_to
        parts.append(f"pub_date <= {args.date_to}")
    elif args.year_to:
        filter_kwargs["year_to"] = args.year_to
        parts.append(f"pub_year <= {args.year_to}")
    if args.research_only:
        filter_kwargs["research_only"] = True
        parts.append("research only")
    if parts:
        logger.info("Filters: %s", ", ".join(parts))

    logger.info("Running bulk funder stats query...")
    bulk_stats = query_funder_open_data_stats(
        con, min_articles=0, **filter_kwargs,
    )
    logger.info("  %d funders in bulk stats", len(bulk_stats))

    # Compute funded-article baseline
    total_funded = int(bulk_stats["total_articles"].sum())
    total_od_funded = int(bulk_stats["open_data_articles"].sum())
    baseline_pct = round(100.0 * total_od_funded / total_funded, 1) if total_funded > 0 else 0.0
    logger.info(
        "  Funded-article baseline: %d / %d = %.1f%%",
        total_od_funded, total_funded, baseline_pct,
    )

    # Journal-level correction factors
    journal_corrections = None
    global_correction = None
    funder_journal_xml_bulk = None

    if not args.no_correction:
        logger.info("Computing journal-level correction factors (min_h2h=%d)...", args.min_h2h_articles)
        journal_df, global_stats = query_journal_correction_factors(
            con, min_h2h=args.min_h2h_articles, **filter_kwargs,
        )
        journal_corrections = build_journal_correction_table(journal_df, global_stats)
        global_correction = global_stats
        logger.info(
            "  %d journals with h2h data; global best OD rate: %.1f%% (PDF: %.1f%%, n=%d)",
            len(journal_corrections), global_stats["best_rate"] * 100,
            global_stats["rate"] * 100, global_stats["n"],
        )

        logger.info("Running bulk funder×journal XML-only query...")
        funder_journal_xml_bulk = query_funder_journal_xml_only(
            con, canonical_names=None, **filter_kwargs,
        )
        logger.info("  %d funder×journal rows", len(funder_journal_xml_bulk))

    # Build summary
    logger.info("Building funder summary (min_articles=%d)...", args.min_articles)
    summary = build_funder_summary(
        con, normalizer, bulk_stats, min_articles=args.min_articles,
        journal_corrections=journal_corrections,
        global_correction=global_correction,
        funder_journal_xml_bulk=funder_journal_xml_bulk,
        **filter_kwargs,
    )
    logger.info("  %d funders in summary", len(summary))

    article_counts = summary["total_articles"].values

    fig_threshold, fig_n, fig_params = compute_weibull_threshold(
        article_counts, survival=args.figure_survival, min_articles=args.min_articles,
    )
    logger.info(
        "  Weibull %.1f%% figure threshold: >=%s articles → %d funders (shape=%.3f)",
        args.figure_survival * 100, f"{fig_threshold:,}", fig_n, fig_params[0],
    )

    tbl_threshold, tbl_n, tbl_params = compute_weibull_threshold(
        article_counts, survival=args.table_survival, min_articles=args.min_articles,
    )
    logger.info(
        "  Weibull %.1f%% table threshold: >=%s articles → %d funders (shape=%.3f)",
        args.table_survival * 100, f"{tbl_threshold:,}", tbl_n, tbl_params[0],
    )

    # Works-count filter (dual threshold: Weibull article count + OpenAlex works)
    min_works_fig = 0 if args.no_works_filter else args.min_works_figure
    min_works_tbl = 0 if args.no_works_filter else args.min_works_table

    if min_works_fig > 0 or min_works_tbl > 0:
        wc_col = summary["aggregated_works_count"]

        if min_works_fig > 0:
            fig_before = int((summary["total_articles"] >= fig_threshold).sum())
            fig_mask = (summary["total_articles"] >= fig_threshold) & (wc_col >= min_works_fig)
            fig_after = int(fig_mask.sum())
            removed_fig = summary[
                (summary["total_articles"] >= fig_threshold) & (wc_col < min_works_fig)
            ]["funder_name"].tolist()
            logger.info(
                "  Works filter (>=%s): %d → %d figure funders (removed: %s)",
                f"{min_works_fig:,}", fig_before, fig_after,
                ", ".join(removed_fig) if removed_fig else "none",
            )

        if min_works_tbl > 0:
            tbl_before = int((summary["total_articles"] >= tbl_threshold).sum())
            tbl_mask = (summary["total_articles"] >= tbl_threshold) & (wc_col >= min_works_tbl)
            tbl_after = int(tbl_mask.sum())
            removed_tbl = summary[
                (summary["total_articles"] >= tbl_threshold) & (wc_col < min_works_tbl)
            ]["funder_name"].tolist()
            logger.info(
                "  Works filter (>=%s): %d → %d table funders (removed: %s)",
                f"{min_works_tbl:,}", tbl_before, tbl_after,
                ", ".join(removed_tbl) if removed_tbl else "none",
            )

    # Build filtered subsets for figure and table
    fig_df = summary[summary["total_articles"] >= fig_threshold].copy()
    if min_works_fig > 0:
        fig_df = fig_df[fig_df["aggregated_works_count"] >= min_works_fig]

    tbl_df = summary[summary["total_articles"] >= tbl_threshold].copy()
    if min_works_tbl > 0:
        tbl_df = tbl_df[tbl_df["aggregated_works_count"] >= min_works_tbl]

    # Outputs
    sfx = args.output_suffix
    table_path = Path(args.output_dir) / f"table_funders{sfx}.tex"
    figure_path = Path(args.figures_dir) / f"funders_open_data{sfx}.png"
    csv_path = Path(args.results_dir) / f"funders_summary{sfx}.csv"
    md_path = Path(args.results_dir) / f"funders_summary{sfx}.md"

    generate_funder_latex_table(
        tbl_df, table_path,
        threshold=0,
        n_total_funders=len(summary),
        survival_pct=args.table_survival * 100,
        label_suffix=sfx,
    )
    generate_funder_bar_chart(
        fig_df, figure_path,
        threshold=0,
        baseline_pct=baseline_pct,
    )
    save_summary_csv(summary, csv_path)
    save_summary_markdown(summary, md_path, baseline_pct=baseline_pct)

    con.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
