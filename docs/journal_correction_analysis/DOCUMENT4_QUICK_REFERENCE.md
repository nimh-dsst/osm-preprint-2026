
         ================================================================================
         QUICK REFERENCE: CORRECTION MACHINERY CODE SNIPPETS
         ================================================================================

         SNIPPET 1: Query Journal Correction Factors
         ────────────────────────────────────────────

         Location: scripts/utils/data_loader.py:268-321

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
             # ... SQL query filters and builds per-journal stats ...
             # Uses: is_open_data_best (PDF ∪ XML) as the ground truth


         SNIPPET 2: Build Journal Correction Table (Add CIs)
         ────────────────────────────────────────────────────

         Location: scripts/utils/correction.py:30-70

         def build_journal_correction_table(
             journal_df: pd.DataFrame,
             global_stats: dict,
         ) -> pd.DataFrame:
             """Add Wilson CI columns to journal correction factors.

             Uses best_od_rate (PDF∪XML) from the head-to-head subset.

             Returns:
                 DataFrame with columns: journal, best_od_rate, ci_lo, ci_hi, h2h_n
             """
             rows = []
             for _, row in journal_df.iterrows():
                 n = int(row["h2h_n"])
                 rate = float(row["best_od_rate"])
                 successes = round(rate * n)
                 lo, hi = wilson_ci(successes, n)  # 95% CI using Wilson score
                 rows.append({
                     "journal": row["journal"],
                     "best_od_rate": rate,
                     "ci_lo": lo,
                     "ci_hi": hi,
                     "h2h_n": n,
                 })
             return pd.DataFrame(rows)


         SNIPPET 3: Apply Funder Correction to XML-Only Articles
         ─────────────────────────────────────────────────────────

         Location: scripts/utils/correction.py:73-146

         def apply_funder_correction(
             funder_journal_xml: pd.DataFrame,
             journal_corrections: pd.DataFrame,
             global_fallback: dict,
             pdf_covered_od: int,
             observed_od: int = 0,
         ) -> dict:
             """Apply journal-level corrections to one funder's XML-only articles.

             For each journal with XML-only articles for this funder, estimate the
             true number of open data articles using the journal's best detection rate.

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

             # Merge journal corrections (split into with/without h2h data)
             merged = funder_journal_xml.merge(
                 journal_corrections[["journal", "best_od_rate", "ci_lo", "ci_hi"]],
                 on="journal",
                 how="left",
             )

             # Apply journal-specific rates where available
             has_correction = merged["best_od_rate"].notna()
             with_corr = merged[has_correction]
             without_corr = merged[~has_correction]

             # Weighted sum of estimates
             est_point = (with_corr["n_xml_only"] * with_corr["best_od_rate"]).sum()
             est_lo = (with_corr["n_xml_only"] * with_corr["ci_lo"]).sum()
             est_hi = (with_corr["n_xml_only"] * with_corr["ci_hi"]).sum()
             n_corrected = int(with_corr["n_xml_only"].sum())

             # Fallback for journals without h2h data
             n_fallback_total = int(without_corr["n_xml_only"].sum()) if not without_corr.empty else 0
             est_point += n_fallback_total * global_fallback["best_rate"]
             est_lo += n_fallback_total * global_fallback["ci_lo"]
             est_hi += n_fallback_total * global_fallback["ci_hi"]

             # Add to PDF-covered OD and floor at observed
             corrected_od = max(pdf_covered_od + est_point, observed_od)
             ci_lo = max(pdf_covered_od + est_lo, observed_od)
             ci_hi = max(pdf_covered_od + est_hi, observed_od)

             return {
                 "corrected_od": corrected_od,
                 "ci_lo": ci_lo,
                 "ci_hi": ci_hi,
                 "n_corrected": n_corrected,
                 "n_fallback": n_fallback_total,
             }


         SNIPPET 4: Wilson Score Confidence Interval (Helper)
         ─────────────────────────────────────────────────────

         Location: scripts/utils/correction.py:13-27

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


         SNIPPET 5: How It's Used in table_funders.py (Workflow)
         ────────────────────────────────────────────────────────

         Location: scripts/table_funders.py (see full file for context)

         # Step 1: Compute journal correction factors
         logger.info("Computing journal correction factors...")
         journal_df, global_stats = query_journal_correction_factors(
             con, min_h2h=args.min_h2h_articles, **filter_kwargs,
         )
         journal_corrections = build_journal_correction_table(journal_df, global_stats)
         logger.info(
             "  %d journals with h2h data; global best OD rate: %.1f%%",
             len(journal_corrections), global_stats["best_rate"] * 100,
         )

         # Step 2: Get XML-only breakdown per funder per journal
         logger.info("Running bulk funder×journal XML-only query...")
         funder_journal_xml_bulk = query_funder_journal_xml_only(
             con, canonical_names=None, **filter_kwargs,
         )

         # Step 3: For each funder, apply correction
         for _, row in bulk_stats.iterrows():
             cname = row["canonical_name"]
             funder_xml = funder_journal_xml_bulk[
                 funder_journal_xml_bulk['canonical_name'] == cname
             ]

             corr = apply_funder_correction(
                 funder_xml,
                 journal_corrections,
                 global_correction,
                 pdf_covered_od=int(row.get("pdf_covered_od", 0)),
                 observed_od=od,
             )

             row_dict["corrected_od"] = corr["corrected_od"]
             row_dict["ci_lo_pct"] = corr["ci_lo"] / total * 100
             row_dict["ci_hi_pct"] = corr["ci_hi"] / total * 100


         SNIPPET 6: Pseudocode for Journal-Level Adaptation
         ────────────────────────────────────────────────────

         # Same three-step pattern, applied per journal instead of per funder

         # Step 1: Get journal correction factors (already done in query)
         journal_df, global_stats = query_journal_correction_factors(con, min_h2h=50)
         journal_corrections = build_journal_correction_table(journal_df, global_stats)

         # Step 2: Get journal stats
         journal_stats = query_journal_open_data_stats(con, min_articles=100)

         # Step 3: Apply correction per journal
         for idx, journal in journal_stats.iterrows():
             j_name = journal['journal']

             # Get correction rate for this journal
             if j_name in journal_corrections['journal'].values:
                 corr_row = journal_corrections[journal_corrections['journal'] == j_name].iloc[0]
                 rate = corr_row['best_od_rate']
                 ci_lo = corr_row['ci_lo']
                 ci_hi = corr_row['ci_hi']
             else:
                 # Fall back to global average
                 rate = global_stats['best_rate']
                 ci_lo = global_stats['ci_lo']
                 ci_hi = global_stats['ci_hi']

             # Estimate true OD for XML-only articles
             xml_only = journal['xml_only']
             est_od = journal['open_data_articles'] + (xml_only * rate)
             est_lo = journal['open_data_articles'] + (xml_only * ci_lo)
             est_hi = journal['open_data_articles'] + (xml_only * ci_hi)

             # Store results
             journal_stats.loc[idx, 'corrected_od'] = est_od
             journal_stats.loc[idx, 'corrected_pct'] = est_od / journal['total_articles'] * 100
             journal_stats.loc[idx, 'ci_lo_pct'] = est_lo / journal['total_articles'] * 100
             journal_stats.loc[idx, 'ci_hi_pct'] = est_hi / journal['total_articles'] * 100


         ================================================================================
         KEY SQL QUERIES (in DuckDB)
         ================================================================================

         Get head-to-head articles for a single journal:

           SELECT
             journal,
             COUNT(*) AS h2h_count,
             SUM(CAST(is_open_data_xml_v7 AS INT)) AS xml_only_od,
             SUM(CAST(is_open_data_pdf_v7 AS INT)) AS pdf_only_od,
             SUM(CAST(is_open_data_best AS INT)) AS best_od,
             SUM(CAST(is_open_data_best AS INT))::DOUBLE / COUNT(*) AS best_od_rate
           FROM pmids
           WHERE journal = 'Nature'
             AND has_oddpub_xml_v7 = true
             AND has_oddpub_pdf_v7 = true
           GROUP BY journal;


         Get XML-only articles per journal for a funder:

           SELECT p.journal, COUNT(DISTINCT af.pmid) AS n_xml_only
           FROM article_funders af
           JOIN pmids p ON af.pmid = p.pmid
           WHERE p.has_oddpub_xml_v7 = true
             AND NOT COALESCE(p.has_oddpub_pdf_v7, false)
             AND af.funder_id = 'F123456'
           GROUP BY p.journal
           ORDER BY COUNT(DISTINCT af.pmid) DESC;


         ================================================================================

