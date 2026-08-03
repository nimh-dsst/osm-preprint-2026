# Handoff: PaperPile hard-block corpus additions → v2 refresh

**Date:** 2026-07-27
**From:** the #40 / PaperPile-retrieval workstream (branch `claude/v2a-defect-fixes`)
**To:** the v2-refresh agent (paper-wide regeneration from `pmid_registry_v2.duckdb`)
**Issue:** nimh-dsst/osm-preprint-2026#40

---

## TL;DR

**The PaperPile PDFs are already in v2. No data action is needed — this is a
provenance/documentation handoff, not a data transfer.** Curium ingested both
PaperPile batches into `pmid_registry_v2.duckdb` alongside the 210k backlog, so
the seven affected journals already sit at h2h ≥ 50 in v2. Just:

1. Use the **correct** v2 registry (key below) — not an earlier snapshot.
2. **Attribute** these journals' coverage to the PaperPile retrieval in Methods.
3. **Do not** implement the old #40 "suppress <5% PDF-coverage bars" plan — corpus
   expansion resolved it (0 displayed journals remain on the fallback).

### Use exactly this registry
```
duckdbs/pmid_registry_v2.duckdb
key: MD5E-s2467573760--9df14d6ac4dd090f4fa91d7bc82ab340
```
This is the version with **1,034 journals ≥ 50 h2h** and global fallback
best_rate **15.8%**. If your v2 shows only ~676 journals ≥ 50 h2h, you have a
pre-PaperPile/pre-cleanup snapshot — get the current one (`git annex get --from
sandisk duckdbs/pmid_registry_v2.duckdb`; it's on the sandisk, s3, and curium).

---

## What PaperPile added (and why it matters)

Seven journals were on the **16% global correction fallback** because automated PDF
download never succeeded for them (~0 PDFs in the 210k backlog — hard-blocked by
publisher bot-detection). We retrieved PDFs manually via PaperPile; they are now
h2h-covered in v2 and earn their own correction factors:

| journal | h2h in v2 | v2 best_od_rate | was (fallback) |
|---|--:|--:|--:|
| Medicine | 75 | 4.0% | 16.0% |
| BMJ Open | 76 | 5.3% | 16.0% |
| JAMA Network Open | 91 | 0.0% | 16.0% |
| International Journal of Surgery Case Reports | 74 | 6.8% | 16.0% |
| Radiology Case Reports | 74 | 1.4% | 16.0% |
| PeerJ | 74 | 31.1% | 16.0% |
| Poultry Science | 74 | 17.6% | 16.0% |

These crossed the min_h2h=50 bar **because of PaperPile, not the backlog** — the
backlog gave each of them ~0 usable PDFs. Most land far below the old 16%
imputation (the case-report/clinical titles were being over-estimated); PeerJ and
Poultry Science land above it. This is the concrete resolution of #40.

**iScience is NOT a PaperPile journal** — the 210k backlog alone took it from 13 to
459 h2h (v2 rate 51.9%). Don't attribute it to PaperPile.

---

## Reproducibility (for the Methods section)

- **Sampling:** deterministic random sample, **seed 42**, **75 articles/journal**,
  drawn from XML-only research articles in the window 2024-01-01..2025-06-30. Random
  (not cherry-picked) so `best_od_rate` is unbiased.
- **Retrieval:** manual PaperPile fetch (solves publisher captchas), then MinerU +
  oddpub v7.2.3 — the same detection pipeline as the rest of the corpus.
- **Two batches:**
  - Batch 1 — 150 PDFs (Medicine, BMJ Open). Commit `3d1e5ba`,
    `results/paperpile_hardblock_pdfs_2026-07-23.{ris,csv}`.
  - Final batch — 375 PDFs (JAMA Network Open, Int. J. Surgery Case Reports,
    Radiology Case Reports, PeerJ, Poultry Science). Commit `98c50a9`,
    `results/paperpile_hardblock_final_2026-07-24.{ris,csv}`.
- **Generator:** `scripts/build_paperpile_ris.py` (docstring documents the full
  PaperPile round-trip). Both commits on branch `claude/v2a-defect-fixes`.
- **Correction factors from v2:** `results/journal_correction_factors_v2_2026-07-25.csv`
  on branch `claude/journal-h2h-coverage` (commit `5550ca0`).

Suggested Methods addition: one or two sentences noting that journals hard-blocked
from automated PDF retrieval were supplemented with a manually-retrieved,
randomly-sampled PDF set (≥50 head-to-head pairs) so they receive journal-specific
correction factors rather than the global fallback.

---

## Journal table/figure — handed over as INPUT; you own the regen

Per the ownership decision, **the v2-refresh agent owns all table/figure
generation** (journals + funders) so the whole paper regenerates consistently from
one dataset. I have reverted my working-tree journal regen so you start clean.
Reproduce it with:

```bash
python scripts/table_journals.py \
  --duckdb-path ../datalad-osm/duckdbs/pmid_registry_v2.duckdb \
  --output-dir latex/tables/ --figures-dir latex/figures/ --results-dir results/ \
  --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
  --table-survival 0.05 --figure-survival 0.02 \
  --output-suffix _2024_2025 --verbose
```

**Expected results (sanity-check your run against these):**
- 1,034 journals ≥ 50 h2h; global fallback best_rate 15.8%.
- Figure threshold ≥ 4,262 articles → 24 journals; table threshold ≥ 1,815 → 64.
- **Zero** Table 2 / Figure 2 journals on the fallback.
- Figure-2 before→after (committed → v2), a few checks:
  - Nature Communications: obs 45.2→**57.1%**, est 55.9→**57.1%**
  - PLoS ONE: obs 14.2→**24.1%**, est 23.8→**24.1%**
  - Heliyon: est **16.0→7.8%**; Medicine est **16.0→4.0%**; ACS Omega est
    **16.0→6.5%**; BMJ Open est **16.0→5.3%**

---

## ⚠️ Paper-wide ripples I found (your scope, flagging for consistency)

Adopting v2 is bigger than the fallback fix — the backlog PDF coverage + the
OR-logic `is_open_data_best` fix raise rates across the board:

- **Corpus-wide baseline: 8.7% → 10.9%.** Cited in `article.tex` at lines ~4, ~51,
  ~74 (`8.7\%`). Must be updated.
- **Funder-linked baseline 11.7%** (article.tex lines ~4, 51, 74, 78, 83, 87, 91)
  will also change — **regenerate the funder tables/figure from v2** or the paper is
  internally inconsistent (journals on v2, funders on pre-backlog data).
- **Journal rates quoted in Results prose** (Nature Communications, PLoS ONE,
  iScience, Communications Biology, etc.) need updating to their v2 values.
- Consider a light revisit of the correction-methodology framing: most journals are
  now directly PDF-covered, so the paper shifts from "observed + large imputation"
  toward "mostly direct measurement, small correction."

---

## #40 status

The corpus-expansion route (backlog + PaperPile) **resolves the substance of #40**:
no Table 2 / Figure 2 journal rests on the 16% fallback, and the falsely-narrow
imputation intervals are gone. **Do not implement the "<5% PDF-coverage bar
suppression"** for displayed journals — it's moot. The only residual is small
supplementary-only journals still under min_h2h=50; if you want, note that residual
(they use the 15.8% global fallback) in Limitations rather than suppressing.
