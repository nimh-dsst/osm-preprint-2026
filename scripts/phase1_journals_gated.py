#!/usr/bin/env python3
"""#56 journal re-run with the paper's coverage gate (matches what the funder re-run does).

Fixes: the journal dump() used the ungated window, so denominators were inflated
(deflating observed_rate AND exposure_pp), the >=1815 threshold was applied to ungated
counts (admitting e.g. Nature at 2,038 ungated / 1,722 gated), and the `PubMed`
pseudo-journal (a registry data-quality artifact) was never excluded.

Now: coverage gate (has_oddpub_xml_v7 OR has_oddpub_pdf_v7), research-only,
2024-01-01..2025-06-30; threshold re-applied to GATED counts; PubMed excluded.
No join on this path, so no fan-out; the label/adjudication layer is unchanged.

Also reports the LLM-free ceiling bound (gf = 1.0: assume EVERY repo-DOI negative is a
genuine missed deposit) alongside the adjudicated estimate.

Usage: python phase1_journals_gated.py <labels_dir> <phase0_scan.parquet> <out_results_dir>
"""
import sys, json, glob
import duckdb
import pandas as pd
from scipy.stats import kendalltau

LABELS_DIR, SCAN, DEST = sys.argv[1], sys.argv[2], sys.argv[3]
DB = "/data/adamt/osm/datalad-osm/duckdbs/pmid_registry_v2.duckdb"
JOURNAL_MIN = 1815
ADJ_MIN = 10
EXCLUDE = {"PubMed"}          # registry data-quality artifact, not a journal

con = duckdb.connect(DB, read_only=True)
GATE = "(p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)"
WIN = "p.is_research AND p.pub_date BETWEEN DATE '2024-01-01' AND DATE '2025-06-30'"

labs = {}
for f in glob.glob(f"{LABELS_DIR}/*.json"):
    try:
        d = json.load(open(f)); labs[str(d["pmid"])] = d.get("label", "unclear")
    except Exception:
        pass
lab_df = pd.DataFrame({"pmid": list(labs), "label": list(labs.values())})

art = con.execute(f"""
    SELECT CAST(p.pmid AS VARCHAR) pmid, p.journal,
           COALESCE(p.is_open_data_best, FALSE) pos
    FROM pmids p WHERE {WIN} AND {GATE} AND p.journal IS NOT NULL
""").fetchdf()
scan = con.execute(f"SELECT CAST(pmid AS VARCHAR) pmid, TRY_CAST(has_repo_doi_anywhere AS INT) repo FROM read_parquet('{SCAN}')").fetchdf()
df = art.merge(scan, on="pmid", how="left").merge(lab_df, on="pmid", how="left")
df["repo"] = df["repo"].fillna(0).astype(int)
df = df[~df["journal"].isin(EXCLUDE)]

GLOBAL_FN = sum(1 for v in labs.values() if v == "false_negative")
GLOBAL_DEC = sum(1 for v in labs.values() if v in ("false_negative", "non_open_data"))
GLOBAL = GLOBAL_FN / GLOBAL_DEC

rows = []
for j, g in df.groupby("journal"):
    total = len(g)
    if total < JOURNAL_MIN:
        continue
    pos = int(g["pos"].sum())
    negrepo = g[(~g["pos"]) & (g["repo"] == 1)]
    neg_repo = len(negrepo)
    dec = negrepo[negrepo["label"].isin(["false_negative", "non_open_data"])]
    ndec = len(dec)
    fn = int((dec["label"] == "false_negative").sum())
    gf = (fn / ndec) if ndec >= ADJ_MIN else None
    rows.append(dict(journal=j, total=total, positives=pos, neg_repo=neg_repo,
                     adjudicated_n=ndec, gf_own=gf))

d = pd.DataFrame(rows)
d["obs_rate"] = d["positives"] / d["total"] * 100
d["exposure_raw_pp"] = d["neg_repo"] / d["total"] * 100
d["basis"] = d["gf_own"].apply(lambda x: "adjudicated" if pd.notna(x) else "imputed")
d["genuine_fraction"] = d["gf_own"].fillna(GLOBAL)
d["exposure_corrected_pp"] = d["exposure_raw_pp"] * d["genuine_fraction"]
d["exposure_ceiling_pp"] = d["exposure_raw_pp"]          # gf = 1.0 ceiling (LLM-free bound)

d = d.sort_values("obs_rate", ascending=False).reset_index(drop=True)
d["rank_observed"] = d["obs_rate"].rank(ascending=False, method="first").astype(int)
d["rank_corrected"] = (d["obs_rate"] + d["exposure_corrected_pp"]).rank(ascending=False, method="first").astype(int)
d["rank_ceiling"] = (d["obs_rate"] + d["exposure_ceiling_pp"]).rank(ascending=False, method="first").astype(int)
d["rank_delta"] = d["rank_observed"] - d["rank_corrected"]
d["rank_delta_ceiling"] = d["rank_observed"] - d["rank_ceiling"]
d["low_confidence_mover"] = ((d["basis"] == "imputed") & (d["rank_delta"].abs() >= 4)).astype(int)

cols = ["journal","total","positives","obs_rate","neg_repo","adjudicated_n","basis",
        "genuine_fraction","exposure_raw_pp","exposure_corrected_pp",
        "rank_observed","rank_corrected","rank_delta","rank_ceiling","rank_delta_ceiling",
        "low_confidence_mover"]
out = f"{DEST}/phase1_corrected_journals_gated.csv"
d[cols].round(4).to_csv(out, index=False)
d[["journal","total","positives","obs_rate","neg_repo","exposure_raw_pp","rank_observed"]].round(4)\
    .to_csv(f"{DEST}/phase0_exposure_journals_gated.csv", index=False)

tau, _ = kendalltau(d["rank_observed"], d["rank_corrected"])
tau_c, _ = kendalltau(d["rank_observed"], d["rank_ceiling"])
print(f"gated displayed journals: {len(d)} (threshold >= {JOURNAL_MIN} on GATED counts, PubMed excluded)")
print(f"global gf (imputation) = {GLOBAL:.4f}")
print(f"Kendall tau  adjudicated={tau:.4f}   ceiling(gf=1.0)={tau_c:.4f}")
print(f"max |rank_delta| adjudicated={d['rank_delta'].abs().max()}  ceiling={d['rank_delta_ceiling'].abs().max()}")
print(f"basis: {(d['basis']=='adjudicated').sum()} adjudicated / {(d['basis']=='imputed').sum()} imputed; low_confidence flagged {int(d['low_confidence_mover'].sum())}")
print("\ntop moves (adjudicated correction):")
for _, r in d.reindex(d["rank_delta"].abs().sort_values(ascending=False).index).head(12).iterrows():
    print(f"  {r['journal'][:40]:40s} n={int(r['total']):6d} obs#{int(r['rank_observed']):2d}->#{int(r['rank_corrected']):2d} "
          f"d={int(r['rank_delta']):+3d} (ceil#{int(r['rank_ceiling']):2d}) gf={r['genuine_fraction']:.2f} "
          f"exp {r['exposure_raw_pp']:.1f}->{r['exposure_corrected_pp']:.1f}pp {r['basis']}")
print("\nwrote:", out)
