export const meta = {
  name: 'scidata-fn-validation',
  description: 'LLM adjudication of Scientific Data oddpub-negatives (#50): false-negative vs legitimate non-open-data',
  phases: [{ title: 'Classify', detail: 'one pinned-model agent per article, structured label' }],
}

// Issue #50 / #14. Reads args = { textDir, pmids: [...] }. Each article's full
// text (MinerU markdown, the exact text oddpub consumed) sits at
// `${textDir}/${pmid}.txt`; the agent Reads it and returns a structured label.
// Model pinned to sonnet; prompt is the source of truth mirrored in
// results/scidata_fn_prompt_v1.md. Returns the array of per-article labels.

const PROMPT = `You are validating an automated open-data detector (oddpub v7.2.3).

Read the full article text at the path given below. It is a paper from the journal Scientific Data, a data-descriptor journal. The automated detector scored this article as NOT sharing open data. Decide whether the article in fact openly shares NEWLY GENERATED data, using the same definition the detector targets.

OPEN DATA — what counts (all three must hold):
1. The authors deposited data they generated/produced in a data repository — e.g. GEO, SRA, ENA, ArrayExpress, PRIDE, MetaboLights, GenBank, NCBI BioProject, PDB, EMPIAR, Figshare, Zenodo, Dryad, OSF, Mendeley Data, or an institutional/domain repository; AND
2. they give an accession number, DOI, or persistent URL to it; AND
3. the data are openly accessible (not gated).

What does NOT count as open data (these are legitimate detector negatives):
- Data only REUSED from pre-existing or third-party sources, with no new deposit.
- Data available only "upon request", by application, or under controlled/restricted access or a data-use agreement.
- Only supplementary files attached to the article itself, with no repository deposit + accession.
- Only CODE/software shared (e.g., a GitHub repository), with no open data deposit.
- No data shared at all, or editorial/commentary/correction content.

Classify into exactly one label:
- "false_negative" — the article DOES openly share newly generated data per the definition above; the detector missed it.
- "non_open_data" — the article legitimately does NOT share open data per the definition (reuse-only, upon-request/restricted, supplement-only, code-only, or none).
- "unclear" — the text is insufficient or too garbled to decide.

Count the ARTICLE, not statements: one article with three accession numbers is still one article. Base your decision only on the article text; do not assume that because it is Scientific Data it must share data.`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['label', 'data_location', 'accession_or_link', 'access', 'evidence_quote', 'rationale'],
  properties: {
    label: { type: 'string', enum: ['false_negative', 'non_open_data', 'unclear'] },
    data_location: { type: 'string', description: 'repository/platform if a deposit is described, else ""' },
    accession_or_link: { type: 'string', description: 'accession number, DOI, or URL if present, else ""' },
    access: { type: 'string', enum: ['open', 'upon_request_or_restricted', 'reuse_only', 'supplement_only', 'code_only', 'none', 'unclear'] },
    evidence_quote: { type: 'string', description: 'short verbatim quote from the data-availability/data-records text' },
    rationale: { type: 'string', description: 'one sentence' },
  },
}

const A = typeof args === 'string' ? JSON.parse(args) : args
const textDir = A.textDir

// PMIDs come either inline (A.pmids) or, to avoid transcribing hundreds by hand,
// are read from the corpus manifest CSV (A.manifestPath) by a lister agent.
let pmids = A.pmids
if (!Array.isArray(pmids)) {
  if (!A.manifestPath) throw new Error('provide args.pmids (array) or args.manifestPath (CSV)')
  phase('List')
  const listing = await agent(
    `Read the CSV file at this exact path: ${A.manifestPath}\nIt has a header row and a "pmid" column. Return every pmid value, in file order, as an array of strings. Do not skip, dedupe, or reorder.`,
    { label: 'list-pmids', phase: 'List', agentType: 'general-purpose',
      schema: { type: 'object', additionalProperties: false, required: ['pmids'],
        properties: { pmids: { type: 'array', items: { type: 'string' } } } } }
  )
  pmids = listing.pmids
  log(`manifest yielded ${pmids.length} pmids`)
}
if (!Array.isArray(pmids) || pmids.length === 0) throw new Error('no pmids resolved')

phase('Classify')
const results = await pipeline(
  pmids,
  (pmid) =>
    agent(
      `${PROMPT}\n\nPMID: ${pmid}\nRead the article full text at this exact path and classify it:\n${textDir}/${pmid}.txt`,
      { label: `classify:${pmid}`, phase: 'Classify', agentType: 'general-purpose', model: 'sonnet', schema: SCHEMA }
    ).then((r) => (r ? { pmid, ...r } : { pmid, label: 'ERROR', access: 'unclear', data_location: '', accession_or_link: '', evidence_quote: '', rationale: 'agent returned null' }))
)

return results
