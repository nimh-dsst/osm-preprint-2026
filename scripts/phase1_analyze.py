#!/usr/bin/env python3
"""Phase 1 aggregation (consistent-basis): per-entity genuine-deposit fraction -> corrected
exposure -> re-rank, and the corpus manifest.

Emits:
  results/phase1_corpus_manifest.csv          pmid, entity, entity_kind (sampled article -> displayed entity)
  results/phase1_corrected_{journals,funders}.csv   per-entity corrected exposure/ranks with a `basis` column

`basis` = 'adjudicated' if the entity has >= ADJ_MIN adjudicated repo-DOI negatives (its own genuine
fraction is used); else 'imputed' (the pooled/global genuine fraction is applied). This keeps ALL
entities on one basis so no under-sampled entity keeps its raw (uncorrected) exposure and reads as a
fake mover.

Usage: python phase1_analyze.py <labels_dir> <phase0_scan.parquet> <sample_meta.csv> <out_results_dir>
"""
import json, glob, csv, sys
import duckdb

LABELS_DIR, SCAN, SAMPLE_META, DEST = sys.argv[1:5]
V2 = "/data/adamt/osm/datalad-osm/duckdbs/pmid_registry_v2.duckdb"
W = "p.is_research AND p.pub_date BETWEEN DATE '2024-01-01' AND DATE '2025-06-30'"
JOURNAL_MIN, FUNDER_MIN_ARTICLES, FUNDER_MIN_WORKS = 1815, 1708, 100_000
ADJ_MIN = 10  # >= this many adjudicated repo-DOI negatives -> 'adjudicated', else 'imputed'

labs = [json.load(open(f)) for f in glob.glob(f"{LABELS_DIR}/*.json")]
sample_rows = list(csv.DictReader(open(SAMPLE_META)))
sample_pmids = [r["pmid"] for r in sample_rows]
source_of = {r["pmid"]: r["source"] for r in sample_rows}  # pmid -> text source (md|xml)
G_FN = sum(1 for d in labs if d.get("label") == "false_negative")
G_DEC = sum(1 for d in labs if d.get("label") in ("false_negative", "non_open_data"))
GLOBAL = G_FN / G_DEC
print(f"global genuine fraction = {G_FN}/{G_DEC} = {GLOBAL:.4f}")

con = duckdb.connect()
con.execute(f"ATTACH '{V2}' AS v2 (READ_ONLY)")
con.execute(f"CREATE VIEW rd AS SELECT CAST(pmid AS VARCHAR) pmid FROM read_parquet('{SCAN}') WHERE TRY_CAST(has_repo_doi_anywhere AS INT)=1")
con.execute("CREATE TABLE lab(pmid VARCHAR, label VARCHAR)")
con.executemany("INSERT INTO lab VALUES (?,?)", [(str(d["pmid"]), d.get("label", "unclear")) for d in labs])

# --- corpus manifest: sampled pmid -> displayed entity -> kind ---
inlist = ",".join("'" + p + "'" for p in sample_pmids)
man = con.execute(f"""
  SELECT DISTINCT CAST(p.pmid AS VARCHAR) pmid, p.journal entity, 'journal' kind
  FROM v2.pmids p WHERE CAST(p.pmid AS VARCHAR) IN ({inlist}) AND p.journal IN
    (SELECT journal FROM v2.pmids p WHERE {W} AND journal IS NOT NULL GROUP BY journal HAVING COUNT(*)>={JOURNAL_MIN})
  UNION ALL
  SELECT DISTINCT CAST(p.pmid AS VARCHAR), f.display_name, 'funder'
  FROM v2.pmids p JOIN v2.article_funders af ON af.pmid=p.pmid JOIN v2.funders f ON f.funder_id=af.funder_id
  WHERE CAST(p.pmid AS VARCHAR) IN ({inlist}) AND f.openalex_works_count>={FUNDER_MIN_WORKS} AND f.display_name IN
    (SELECT f2.display_name FROM v2.pmids p2 JOIN v2.article_funders af2 ON af2.pmid=p2.pmid JOIN v2.funders f2 ON f2.funder_id=af2.funder_id
     WHERE {W} AND f2.openalex_works_count>={FUNDER_MIN_WORKS} GROUP BY f2.display_name HAVING COUNT(DISTINCT p2.pmid)>={FUNDER_MIN_ARTICLES})
""").fetchall()
with open(f"{DEST}/phase1_corpus_manifest.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["pmid", "entity", "entity_kind", "text_source"])
    for pmid, entity, kind in man:
        w.writerow([pmid, entity, kind, source_of.get(pmid, "")])
print(f"corpus manifest rows: {len(man)}")

def dump(esql, join, cond, out):
    q = f"""WITH base AS (SELECT {esql} eid, CAST(p.pmid AS VARCHAR) pmid, COALESCE(p.is_open_data_best,FALSE) pos FROM v2.pmids p {join} WHERE {W}),
    ann AS (SELECT b.eid,b.pmid,b.pos,CASE WHEN rd.pmid IS NOT NULL THEN 1 ELSE 0 END repo,l.label FROM base b LEFT JOIN rd USING(pmid) LEFT JOIN lab l USING(pmid)),
    agg AS (SELECT eid,COUNT(*) total,SUM(CASE WHEN pos THEN 1 ELSE 0 END) posv,
      SUM(CASE WHEN NOT pos AND repo=1 THEN 1 ELSE 0 END) neg_repo,
      SUM(CASE WHEN NOT pos AND repo=1 AND label='false_negative' THEN 1 ELSE 0 END) fn,
      SUM(CASE WHEN NOT pos AND repo=1 AND label IN ('false_negative','non_open_data') THEN 1 ELSE 0 END) ndec FROM ann GROUP BY eid)
    SELECT eid,total,posv,neg_repo,fn,ndec FROM agg WHERE {cond} AND eid IS NOT NULL"""
    items = []
    for eid, total, posv, neg_repo, fn, ndec in con.execute(q).fetchall():
        obs = posv / total; raw = neg_repo / total
        if ndec >= ADJ_MIN:
            basis, gf = "adjudicated", fn / ndec
        else:
            basis, gf = "imputed", GLOBAL
        corr = raw * gf
        items.append([eid, total, round(obs*100,2), neg_repo, ndec, basis, round(gf,3), round(raw*100,2), round(corr*100,2)])
    ro = {r[0]: i+1 for i, r in enumerate(sorted(items, key=lambda r: -r[2]))}
    rc = {r[0]: i+1 for i, r in enumerate(sorted(items, key=lambda r: -(r[2] + r[8])))}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity","total","observed_rate","neg_repo","adjudicated_n","basis","genuine_fraction","exposure_raw_pp","exposure_corrected_pp","rank_observed","rank_phase1_corrected","rank_delta","low_confidence_mover"])
        for r in sorted(items, key=lambda r: -r[2]):
            delta = ro[r[0]] - rc[r[0]]
            # imputed (global-fraction) entities that move >=4 places are mixed-basis artifacts, NOT validated movers
            low_conf = int(r[5] == "imputed" and abs(delta) >= 4)
            w.writerow(r + [ro[r[0]], rc[r[0]], delta, low_conf])
    print(f"{out}: {len(items)} entities ({sum(1 for r in items if r[5]=='adjudicated')} adjudicated)")

dump("p.journal", "", f"total>={JOURNAL_MIN}", f"{DEST}/phase1_corrected_journals.csv")
dump("f.display_name",
     f"JOIN v2.article_funders af ON af.pmid=p.pmid JOIN v2.funders f ON f.funder_id=af.funder_id AND f.openalex_works_count>={FUNDER_MIN_WORKS}",
     f"total>={FUNDER_MIN_ARTICLES}", f"{DEST}/phase1_corrected_funders.csv")
