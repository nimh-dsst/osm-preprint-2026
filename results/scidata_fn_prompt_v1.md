# Scientific Data false-negative validation — classification prompt (v1)

**Issue:** nimh-dsst/osm-preprint-2026#50 (related #14, #35)
**Pinned model:** claude-sonnet-5 (workflow `model: 'sonnet'`)
**Task:** Adjudicate whether each *Scientific Data* article that oddpub v7.2.3
scored `is_open_data_best = false` in fact openly shares newly generated data,
using the same definition the detector targets. One label per article.

This is the exact instruction text embedded in `scripts/scidata_fn_workflow.mjs`
(source of truth). Saved here for the reproducibility record (#14). The per-article
runtime prompt appends only the PMID and the path to the article's full text; the
detector's own category tag is deliberately withheld so the judgment is independent.

---

You are validating an automated open-data detector (oddpub v7.2.3).

Read the full article text at the path given below. It is a paper from the journal
*Scientific Data*, a data-descriptor journal. The automated detector scored this
article as NOT sharing open data. Decide whether the article in fact openly shares
NEWLY GENERATED data, using the same definition the detector targets.

OPEN DATA — what counts (all three must hold):
1. The authors deposited data they generated/produced in a data repository — e.g.
   GEO, SRA, ENA, ArrayExpress, PRIDE, MetaboLights, GenBank, NCBI BioProject, PDB,
   EMPIAR, Figshare, Zenodo, Dryad, OSF, Mendeley Data, or an institutional/domain
   repository; AND
2. they give an accession number, DOI, or persistent URL to it; AND
3. the data are openly accessible (not gated).

What does NOT count as open data (these are legitimate detector negatives):
- Data only REUSED from pre-existing or third-party sources, with no new deposit.
- Data available only "upon request", by application, or under controlled/restricted
  access or a data-use agreement.
- Only supplementary files attached to the article itself, with no repository
  deposit + accession.
- Only CODE/software shared (e.g., a GitHub repository), with no open data deposit.
- No data shared at all, or editorial/commentary/correction content.

Classify into exactly one label:
- "false_negative" — the article DOES openly share newly generated data per the
  definition above; the detector missed it.
- "non_open_data" — the article legitimately does NOT share open data per the
  definition (reuse-only, upon-request/restricted, supplement-only, code-only, or
  none).
- "unclear" — the text is insufficient or too garbled to decide.

Count the ARTICLE, not statements: one article with three accession numbers is
still one article. Base your decision only on the article text; do not assume that
because it is Scientific Data it must share data.

Return the structured object:
- label
- data_location: the repository/platform if a deposit is described, else ""
- accession_or_link: the accession number, DOI, or URL if present, else ""
- access: one of open | upon_request_or_restricted | reuse_only | supplement_only |
  code_only | none | unclear
- evidence_quote: a short verbatim quote from the data-availability / data-records
  text that justifies the label
- rationale: one sentence
