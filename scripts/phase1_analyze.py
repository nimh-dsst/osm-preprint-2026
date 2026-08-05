#!/usr/bin/env python3
"""Phase 1 aggregation: per-entity genuine-deposit fraction -> corrected exposure -> re-rank.

The cheap Phase 0 `repo` exposure assumed every repo-DOI negative is a genuine miss.
Phase 1 adjudicates a stratified sample: false_negative = genuine new deposit oddpub missed;
non_open_data = legit (reuse/code/restricted). The per-entity genuine fraction rescales exposure.
Question: do the Phase 0 rank-movers survive once reuse/code is excluded?
"""
import json, glob, csv, os, sys
import duckdb
from scipy.stats import kendalltau

SCR = sys.argv[1]
V2 = "/data/adamt/osm/datalad-osm/duckdbs/pmid_registry_v2.duckdb"
SCAN = "/mnt_homes/home4T3/adamt/claude/osm/osm-preprint-2026/results/phase0_doi_scan.parquet"
W = "p.is_research AND p.pub_date BETWEEN DATE '2024-01-01' AND DATE '2025-06-30'"

# 1. load labels
labels = {}
for f in glob.glob(f"{SCR}/phase1_labels/*.json"):
    try:
        d = json.load(open(f)); labels[str(d["pmid"])] = d.get("label", "unclear")
    except Exception:
        labels[os.path.basename(f)[:-5]] = "PARSE_ERR"
print(f"labels loaded: {len(labels)}")
from collections import Counter
print("label distribution:", dict(Counter(labels.values())))

con = duckdb.connect()
con.execute(f"ATTACH '{V2}' AS v2 (READ_ONLY)")
con.execute(f"CREATE VIEW rd AS SELECT CAST(pmid AS VARCHAR) pmid FROM read_parquet('{SCAN}') WHERE TRY_CAST(has_repo_doi_anywhere AS INT)=1")
# register labels as a temp table
con.execute("CREATE TABLE lab(pmid VARCHAR, label VARCHAR)")
con.executemany("INSERT INTO lab VALUES (?,?)", list(labels.items()))

def analyze(esql, join, cond, kind):
    q = f"""
    WITH base AS (
      SELECT {esql} eid, CAST(p.pmid AS VARCHAR) pmid, COALESCE(p.is_open_data_best,FALSE) pos
      FROM v2.pmids p {join} WHERE {W}
    ),
    ann AS (
      SELECT b.eid, b.pmid, b.pos,
        CASE WHEN rd.pmid IS NOT NULL THEN 1 ELSE 0 END repo,
        l.label
      FROM base b LEFT JOIN rd USING(pmid) LEFT JOIN lab l USING(pmid)
    ),
    agg AS (
      SELECT eid,
        COUNT(*) total,
        SUM(CASE WHEN pos THEN 1 ELSE 0 END) positives,
        SUM(CASE WHEN NOT pos AND repo=1 THEN 1 ELSE 0 END) neg_repo,
        SUM(CASE WHEN NOT pos AND repo=1 AND label='false_negative' THEN 1 ELSE 0 END) samp_fn,
        SUM(CASE WHEN NOT pos AND repo=1 AND label='non_open_data' THEN 1 ELSE 0 END) samp_non,
        SUM(CASE WHEN NOT pos AND repo=1 AND label IN ('false_negative','non_open_data') THEN 1 ELSE 0 END) samp_dec
      FROM ann GROUP BY eid
    )
    SELECT eid,total,positives,neg_repo,samp_fn,samp_non,samp_dec FROM agg WHERE {cond} AND eid IS NOT NULL
    """
    rows = con.execute(q).fetchall()
    out = []
    for eid, total, pos, neg_repo, fn, non, dec in rows:
        obs = pos / total
        gfrac = (fn / dec) if dec >= 5 else None  # need >=5 adjudicated to estimate
        raw_exp = neg_repo / total
        corr_exp = raw_exp * gfrac if gfrac is not None else raw_exp  # fallback: uncorrected
        out.append(dict(eid=eid, total=total, obs=obs, neg_repo=neg_repo, samp_dec=dec,
                        gfrac=gfrac, raw_exp=raw_exp, corr_exp=corr_exp))
    return out

def ranks(items, key):
    order = sorted(items, key=lambda r: -key(r))
    return {r["eid"]: i + 1 for i, r in enumerate(order)}, [r["eid"] for r in order]

for kind, esql, cond, join in [
    ("JOURNAL", "p.journal", "total>=1815", ""),
    ("FUNDER", "f.display_name", "total>=1708",
     "JOIN v2.article_funders af ON af.pmid=p.pmid JOIN v2.funders f ON f.funder_id=af.funder_id AND f.openalex_works_count>=100000"),
]:
    items = analyze(esql, join, cond, kind)
    r_obs, _ = ranks(items, lambda r: r["obs"])
    r_raw, _ = ranks(items, lambda r: r["obs"] + r["raw_exp"])         # Phase 0 (all repo-DOI = miss)
    r_corr, corr_order = ranks(items, lambda r: r["obs"] + r["corr_exp"])  # Phase 1 (genuine only)
    print(f"\n{'='*76}\n{kind}S (n={len(items)})")
    # genuine fraction spread (uniform-bias check)
    gf = [r["gfrac"] for r in items if r["gfrac"] is not None]
    import statistics as st
    if gf:
        print(f"  genuine-deposit fraction (sampled, >=5 adj): n={len(gf)} mean={st.mean(gf):.2f} min={min(gf):.2f} max={max(gf):.2f} stdev={st.pstdev(gf):.2f}")
    # concordance: observed vs Phase0-raw-corrected vs Phase1-genuine-corrected
    eids = [r["eid"] for r in items]
    tau_raw, _ = kendalltau([r_obs[e] for e in eids], [r_raw[e] for e in eids])
    tau_corr, _ = kendalltau([r_obs[e] for e in eids], [r_corr[e] for e in eids])
    print(f"  Kendall tau vs observed:  raw(Phase0)={tau_raw:.3f}   genuine-corrected(Phase1)={tau_corr:.3f}")
    # movers: show entities with a sampled fraction and notable rank change under corrected
    print(f"  key entities (obs rank -> Phase0-raw rank -> Phase1-corrected rank | gfrac | raw_exp->corr_exp pp):")
    movers = sorted([r for r in items if r["gfrac"] is not None], key=lambda r: (r_obs[r["eid"]] - r_corr[r["eid"]]), reverse=True)
    for r in movers[:14]:
        e = r["eid"]
        print(f"    {str(e)[:34]:34s} {r_obs[e]:3d}->{r_raw[e]:3d}->{r_corr[e]:3d}  gf={r['gfrac']:.2f}  {r['raw_exp']*100:4.1f}->{r['corr_exp']*100:4.1f}  (adj n={r['samp_dec']})")
