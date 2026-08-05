#!/usr/bin/env python3
"""Phase 0 T0.4: per-entity DOI-repo exposure + worst-case re-rank.

Args: <merged_scan.parquet>   (per-article: pmid, source, has_repo_doi_anywhere, has_nonpub_doi, ...)
Exposure per entity = (oddpub-negative articles with a data-repo DOI) / (total articles)
  measures: repo (curated, precise ~81% recall) and nonpub (loose upper bound).
Decision: add exposure to observed rate, re-rank top-N; does the ordering move?
"""
import sys, duckdb
from scipy.stats import kendalltau

SCAN = sys.argv[1]
V2 = "/data/adamt/osm/datalad-osm/duckdbs/pmid_registry_v2.duckdb"
W = "p.is_research AND p.pub_date BETWEEN DATE '2024-01-01' AND DATE '2025-06-30'"
JOURNAL_MIN = 1815
FUNDER_MIN_ARTICLES = 1708
FUNDER_MIN_WORKS = 100_000

con = duckdb.connect()
con.execute(f"ATTACH '{V2}' AS v2 (READ_ONLY)")
con.execute(f"CREATE VIEW scan AS SELECT CAST(pmid AS VARCHAR) pmid, "
            f"TRY_CAST(has_repo_doi_anywhere AS INT) repo, TRY_CAST(has_nonpub_doi AS INT) nonpub "
            f"FROM read_parquet('{SCAN}')")

def report(entity_sql, label, name_join):
    q = f"""
    WITH base AS (
      SELECT {entity_sql} AS eid, CAST(p.pmid AS VARCHAR) pmid,
             COALESCE(p.is_open_data_best,FALSE) pos
      FROM v2.pmids p {name_join} WHERE {W}
    ),
    j AS (
      SELECT b.eid, b.pmid, b.pos,
             COALESCE(s.repo,0) repo, COALESCE(s.nonpub,0) nonpub
      FROM base b LEFT JOIN scan s USING(pmid)
    ),
    agg AS (
      SELECT eid,
        COUNT(*) total,
        SUM(CASE WHEN pos THEN 1 ELSE 0 END) positives,
        SUM(CASE WHEN NOT pos AND repo=1 THEN 1 ELSE 0 END) neg_repo,
        SUM(CASE WHEN NOT pos AND nonpub=1 THEN 1 ELSE 0 END) neg_nonpub
      FROM j GROUP BY eid
    )
    SELECT eid, total, positives,
      positives*1.0/total AS obs_rate,
      neg_repo*1.0/total AS exp_repo,
      neg_nonpub*1.0/total AS exp_nonpub
    FROM agg WHERE {label}
    ORDER BY obs_rate DESC
    """
    rows = [r for r in con.execute(q).fetchall() if r[0] is not None]
    return rows

def rerank(rows, expo_idx, topn=20):
    # rows: (eid,total,positives,obs_rate,exp_repo,exp_nonpub)
    base = sorted(rows, key=lambda r: -r[3])
    corr = sorted(rows, key=lambda r: -(r[3] + r[expo_idx]))
    base_order = [r[0] for r in base]
    corr_order = [r[0] for r in corr]
    base_rank = {e: i for i, e in enumerate(base_order)}
    corr_rank = {e: i for i, e in enumerate(corr_order)}
    xs = [base_rank[e] for e in base_order]
    ys = [corr_rank[e] for e in base_order]
    tau, _ = kendalltau(xs, ys)
    base_top = set(base_order[:topn]); corr_top = set(corr_order[:topn])
    churn = len(base_top ^ corr_top) // 2
    shifts = {e: abs(base_rank[e] - corr_rank[e]) for e in base_order[:topn]}
    return tau, churn, base_top, corr_top, max(shifts.values()), base_order, corr_order

for kind, esql, lbl, join in [
    ("JOURNAL", "p.journal", f"total>={JOURNAL_MIN}", ""),
    ("FUNDER", "f.display_name",
     f"total>={FUNDER_MIN_ARTICLES}",
     "JOIN v2.article_funders af ON af.pmid=p.pmid JOIN v2.funders f ON f.funder_id=af.funder_id "
     f"AND f.openalex_works_count>={FUNDER_MIN_WORKS}"),
]:
    rows = report(esql, lbl, join)
    print(f"\n{'='*70}\n{kind}S (n={len(rows)})")
    exp_repo_vals = [r[4] for r in rows]
    exp_nonpub_vals = [r[5] for r in rows]
    import statistics as st
    print(f"  exposure_repo (curated): mean={st.mean(exp_repo_vals)*100:.2f}pp "
          f"min={min(exp_repo_vals)*100:.2f} max={max(exp_repo_vals)*100:.2f} "
          f"stdev={st.pstdev(exp_repo_vals)*100:.2f}")
    print(f"  exposure_nonpub (upper): mean={st.mean(exp_nonpub_vals)*100:.2f}pp "
          f"min={min(exp_nonpub_vals)*100:.2f} max={max(exp_nonpub_vals)*100:.2f}")
    for mname, idx in [("repo", 4), ("nonpub(worst)", 5)]:
        tau, churn, bt, ct, maxshift, bo, co = rerank(rows, idx, topn=20)
        print(f"  [{mname}] top-20 re-rank: Kendall_tau={tau:.4f}  top20_churn={churn}  max_rank_shift={maxshift}")
    # show top-10 with exposures
    print(f"  top-10 by observed rate (obs% | exp_repo pp | exp_nonpub pp):")
    for r in sorted(rows, key=lambda r:-r[3])[:10]:
        print(f"    {str(r[0])[:38]:38s} n={r[1]:6d} obs={r[3]*100:5.1f}%  +repo={r[4]*100:4.1f}  +nonpub={r[5]*100:5.1f}")
