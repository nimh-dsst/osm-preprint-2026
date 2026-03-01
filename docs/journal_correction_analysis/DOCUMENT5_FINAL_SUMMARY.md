Excellent! Now let me create a final summary document to display to you:

       ---
       Summary

       I've completed a thorough analysis of the PDF vs XML coverage distribution across journals in the OSM preprint DuckDB database and fully
        documented the correction machinery. Here are the key findings:

       1. Global PDF/XML Coverage Distribution

       - Total articles: 784,262 across 1,389 journals
       - PDF-covered: 256,660 (32.7%)
       - XML-only: 527,602 (67.3%)

       The journals show distinct clustering patterns:
       - 677 journals (261k articles): 0-10% PDF coverage (pure XML)
       - 197 journals (172k articles): 10-30% PDF coverage (mostly XML)
       - 195 journals (176k articles): 30-70% PDF coverage (balanced)
       - 261 journals (162k articles): 70-90% PDF coverage (mostly PDF)
       - 59 journals (13k articles): 90-100% PDF coverage (pure PDF)

       Variance among large journals (≥200 articles):
       - Mean PDF coverage: 28.4%
       - Median PDF coverage: 13.5%
       - Stdev: 31.7% (HIGH variance indicates journal-specific patterns matter)

       2. Existing Correction Machinery (Three-Part System)

       A. Query Layer: query_journal_correction_factors() in data_loader.py:268-321
       - Computes per-journal OD detection rates from "head-to-head" articles (those with both XML and PDF coverage)
       - Minimum threshold: ≥50 h2h articles per journal (configurable)
       - Output columns: journal, h2h_n, xml_od_rate, pdf_od_rate, best_od_rate (PDF∪XML, the "ground truth")

       B. Build Layer: build_journal_correction_table() in correction.py:30-70
       - Adds Wilson score confidence intervals (95%, z=1.96)
       - Propagates uncertainty through the correction process
       - Output: journal, best_od_rate, ci_lo, ci_hi, h2h_n

       C. Apply Layer: apply_funder_correction() in correction.py:73-146
       - Applies journal-specific correction rates to XML-only articles
       - Splits journals into two groups: those with h2h data vs. those using global fallback
       - Weighted sum: sum(n_xml_only[j] × rate[j]) for each journal j
       - Floors result at observed OD to be conservative

       3. Funder-Level Correction Impact (Proof of Concept)

       Across 816 funders with ≥100 articles and XML-only coverage:

       ┌──────────────────────────────┬──────────────────┐
       │            Metric            │      Value       │
       ├──────────────────────────────┼──────────────────┤
       │ Observed OD                  │ 72,969 articles  │
       ├──────────────────────────────┼──────────────────┤
       │ Corrected OD                 │ 88,009 articles  │
       ├──────────────────────────────┼──────────────────┤
       │ Total correction             │ +15,040 articles │
       ├──────────────────────────────┼──────────────────┤
       │ Overall increase             │ +20.6%           │
       ├──────────────────────────────┼──────────────────┤
       │ Mean per-funder correction   │ +33.7%           │
       ├──────────────────────────────┼──────────────────┤
       │ Median per-funder correction │ +21.9%           │
       ├──────────────────────────────┼──────────────────┤
       │ Range                        │ 0% to +526%      │
       └──────────────────────────────┴──────────────────┘

       Example: NIH has 5,940 observed OD articles but 6,582 corrected articles (+642, +10.8%).

       4. Journal-Level Correction Potential

       The same machinery could be directly adapted for journals because:

       1. Head-to-head correction factors are already computed (query_journal_correction_factors exists)
       2. High variance in PDF coverage (stdev 31.7%) means journal-specific rates matter significantly
       3. 67.3% of articles are XML-only, providing a large pool for correction to impact
       4. Expected impact: +15-30% for journals with low PDF coverage; minimal for >90% PDF coverage

       Journals most affected:
       - Heliyon: 16,600 articles, 0% PDF, 7.4% OD observed → could be 40%+ if h2h data shows high OD rate
       - ACS Omega: 5,973 articles, 0% PDF, 2.6% OD observed
       - Cureus: 28,751 articles, 49.4% PDF, 0.1% OD observed

       Journals least affected:
       - Nature Biotechnology: 120 articles, 97.5% PDF → correction ~1-2%

       5. How the Correction Works (Step-by-Step)

       Step 1: Query head-to-head rates
       journal_df, global_stats = query_journal_correction_factors(con, min_h2h=50)
       Output: Per-journal best_od_rate (e.g., Nature: 0.85, meaning 85% of h2h articles have OD statements)

       Step 2: Add confidence intervals
       journal_corrections = build_journal_correction_table(journal_df, global_stats)
       Output: journal, best_od_rate, ci_lo, ci_hi, h2h_n

       Step 3: Apply to XML-only articles
       For each journal with n_xml_only articles:
       estimated_od = n_xml_only × journal_best_od_rate
       ci_bounds = [n_xml_only × ci_lo, n_xml_only × ci_hi]

       Plus PDF-covered OD (ground truth), floored at observed OD.

       6. Key Files & Code Locations

       ┌────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────┬─────────────────
       ───────┐
       │                                      File                                      │              Function              │        Purpose
              │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/scripts/utils/data_loader.py:268-321   │ query_journal_correction_factors() │ Compute h2h
       rates per  │
       │                                                                                │                                    │ journal
              │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/scripts/utils/correction.py:30-70      │ build_journal_correction_table()   │ Add Wilson CIs
              │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/scripts/utils/correction.py:73-146     │ apply_funder_correction()          │ Apply correction
        to    │
       │                                                                                │                                    │ XML-only
       articles      │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/scripts/table_funders.py               │ Full workflow                      │ Example of how
              │
       │                                                                                │                                    │ correction is
       used     │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/results/journals_summary_2024_2025.csv │ Journal stats                      │ Current data (NO
              │
       │                                                                                │                                    │ correction
       applied)    │
       ├────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────┼─────────────────
       ───────┤
       │ /home/adamt/claude/osm/brnch_journalFig/results/funders_summary_2024_2025.csv  │ Funder stats                       │ WITH correction
              │
       │                                                                                │                                    │ applied
              │
       └────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────┴─────────────────
       ───────┘

       7. Key Assumptions & Limitations

       - Core assumption: XML-only articles have the same OD distribution as PDF articles (reasonable if availability is random)
       - Sample size: Varies by journal (50 to 50,000+ h2h articles); affects CI width
       - Global fallback: 68% best OD rate used for journals lacking h2h data
       - Conservative floor: Corrected OD ≥ observed OD (never corrects downward)

       8. Bottom Line

       The correction machinery is sophisticated, well-tested, and reusable. It's currently applied at the funder level (adding ~20.6% to OD
       estimates) and could be directly adapted for journals using the same three functions. The high variance in PDF coverage across journals
       (stdev 31.7%) and the large pool of XML-only articles (67.3%) suggest that journal-level correction would meaningfully improve rankings
       and reported OD rates, particularly for major journals with low PDF coverage like Heliyon, ACS Omega, and BMJ Open.
  ⎿  Done (31 tool uses · 82.7k tokens · 37m 53s)

                                                                                                                    03:22 PM claude-opus-4-6
● This is an important methodological point. Here's what the data shows:

  The Problem

  Across 1,389 journals, only 32.7% of articles have PDF coverage — the rest are XML-only. And the distribution is wildly uneven:

  ┌──────────────┬──────────┬──────────┐
  │ PDF Coverage │ Journals │ Articles │
  ├──────────────┼──────────┼──────────┤
  │ 0–10%        │ 677      │ 261k     │
  ├──────────────┼──────────┼──────────┤
  │ 10–30%       │ 197      │ 172k     │
  ├──────────────┼──────────┼──────────┤
  │ 30–70%       │ 195      │ 176k     │
  ├──────────────┼──────────┼──────────┤
  │ 70–90%       │ 261      │ 162k     │
  ├──────────────┼──────────┼──────────┤
  │ 90–100%      │ 59       │ 13k      │
  └──────────────┴──────────┴──────────┘

  Standard deviation of PDF coverage across large journals is 31.7%. So when we report that, say, Heliyon has 7.4% OD rate based on 16,600 articles
  with 0% PDF coverage, that rate is systematically depressed relative to Nature Biotechnology's rate measured at 97.5% PDF coverage. The observed
  rates aren't comparable on an apples-to-apples basis.

  What a correction would actually do

  The plan dismissed journal correction as "trivially the journal's own h2h best_od_rate," but that's not quite right. The correction doesn't
  replace the observed rate with the h2h rate — it reweights the two detection populations:

  corrected_od = pdf_covered_od + (n_xml_only × journal_h2h_best_od_rate)

  For a journal with 50% PDF / 50% XML-only, this meaningfully adjusts the estimate. The existing build_journal_correction_table() and
  apply_funder_correction() already do exactly this with Wilson score CIs — the funder pipeline shows a +20.6% median correction across funders,
  driven entirely by XML-only article reweighting.

  Two things we can quantify

  1. Corrected OD rate — same machinery as funders, using each journal's own h2h factor (or global fallback for journals without enough h2h data)
  2. 95% Wilson CI — already propagated through the correction pipeline, width determined by h2h sample size and XML-only fraction

  Journals with high PDF coverage get narrow CIs (corrected ≈ observed). Journals with high XML-only fractions get wider CIs and potentially larger
  upward corrections.

  My recommendation

  We should apply the correction. The infrastructure already exists, and journals with 0% PDF coverage (Heliyon, ACS Omega, many MDPI titles) are
  currently being unfairly penalized in the rankings. The correction + CI would make the figure and table more scientifically honest, and it follows
   the same methodology already validated in the funder pipeline.

  Want me to implement the journal-level correction with CIs?
