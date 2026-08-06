#!/usr/bin/env python3
"""#56 funder re-run on the paper's CANONICAL funder set (fixes two bugs).

Bug 1 (fan-out): `article_funders` is one row per GRANT; the earlier analysis used COUNT(*)
over the joined relation, inflating totals ~1.7-1.9x and admitting sub-threshold funders.
=> every count here is COUNT(DISTINCT pmid).

Bug 2 (entity resolution): the earlier analysis used raw OpenAlex funder entities; the paper
reports funders AFTER alias aggregation + ROR sub-agency rollup (NASA absent, NERC->UKRI,
NCI/NIGMS->NIH). => canonical grouping comes from the production `FunderNormalizer`.

Also matches the paper's denominator: coverage gate (has_oddpub_xml_v7 OR has_oddpub_pdf_v7),
research-only, 2024-01-01..2025-06-30; displayed set = >=1708 articles AND >=50,000 aggregated
OpenAlex works (supplementary table).

Label pooling is SHARE-REWEIGHTED: a canonical funder's genuine fraction is the weighted mean of
its sub-entities' fractions, each weighted by that sub-entity's share of the canonical funder's
repo-DOI negatives (a naive pool would inherit the sampling mix, not the population mix).

Usage: python phase1_canonical_funders.py <labels_dir> <phase0_scan.parquet> <out_results_dir>
"""
import sys, json, glob, csv
from pathlib import Path
import duckdb
import pandas as pd
from scipy.stats import kendalltau

LABELS_DIR, SCAN, DEST = sys.argv[1], sys.argv[2], sys.argv[3]
REPO = "/mnt_homes/home4T3/adamt/claude/osm/osm-preprint-2026"
DB = "/data/adamt/osm/datalad-osm/duckdbs/pmid_registry_v2.duckdb"
sys.path.insert(0, f"{REPO}/scripts")
from table_funders import FunderNormalizer, _resolve_english_name  # noqa: E402

ART_MIN, WORKS_MIN = 1708, 50_000       # supplementary displayed set (paper's frozen cuts)
ADJ_MIN = 10                            # >= this many adjudications -> 'adjudicated' basis

# ---------------- canonical grouping (production pipeline) ----------------
norm = FunderNormalizer(f"{REPO}/scripts/funder_aliases_v5.csv")
groups = norm.get_aggregation_groups()
db_to_paper = {db: g["display_name"] for g in groups for db in g["db_names"]}
def paper_canonical(db_name):
    return db_to_paper.get(db_name, _resolve_english_name(db_name))

con = duckdb.connect(DB, read_only=True)
GATE = "(p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)"
WIN = "p.is_research AND p.pub_date BETWEEN DATE '2024-01-01' AND DATE '2025-06-30'"

# pmid -> canonical funder (DISTINCT: an article counts once per canonical funder even if it
# credits several member sub-agencies through several grants)
pf = con.execute(f"""
    SELECT DISTINCT CAST(af.pmid AS VARCHAR) pmid, f.canonical_name db_name,
           COALESCE(p.is_open_data_best, FALSE) pos
    FROM article_funders af
    JOIN funders f USING (funder_id)
    JOIN pmids p ON p.pmid = af.pmid
    WHERE {WIN} AND {GATE}
""").fetchdf()
pf["funder"] = pf["db_name"].map(paper_canonical)

# aggregated OpenAlex works per canonical funder (sum over member db canonical_names)
works_df = con.execute("SELECT canonical_name db_name, COALESCE(openalex_works_count,0) w FROM funders").fetchdf()
works_df["funder"] = works_df["db_name"].map(paper_canonical)
works = works_df.groupby("funder")["w"].sum()

# ---------------- per-article signals ----------------
scan = con.execute(f"SELECT CAST(pmid AS VARCHAR) pmid, TRY_CAST(has_repo_doi_anywhere AS INT) repo FROM read_parquet('{SCAN}')").fetchdf()
labs = {}
for f in glob.glob(f"{LABELS_DIR}/*.json"):
    try:
        d = json.load(open(f)); labs[str(d["pmid"])] = d.get("label", "unclear")
    except Exception:
        pass
lab_df = pd.DataFrame({"pmid": list(labs), "label": list(labs.values())})

df = (pf.merge(scan, on="pmid", how="left")
        .merge(lab_df, on="pmid", how="left"))
df["repo"] = df["repo"].fillna(0).astype(int)

# ---------------- per-canonical-funder aggregation (all DISTINCT pmid) ----------------
rows = []
for funder, g in df.groupby("funder"):
    total = g["pmid"].nunique()
    if total < 100:
        continue
    pos = g.loc[g["pos"], "pmid"].nunique()
    negrepo_df = g[(~g["pos"]) & (g["repo"] == 1)]
    neg_repo = negrepo_df["pmid"].nunique()

    # --- share-reweighted genuine fraction across member sub-entities ---
    # weight each sub-entity (db_name) by its share of THIS funder's repo-DOI negatives
    num = den = 0.0
    adj_n = 0
    subs_with_labels = 0
    for db_name, sg in negrepo_df.groupby("db_name"):
        share = sg["pmid"].nunique()
        dec = sg[sg["label"].isin(["false_negative", "non_open_data"])]
        n_dec = dec["pmid"].nunique()
        if n_dec == 0:
            continue
        fn = dec[dec["label"] == "false_negative"]["pmid"].nunique()
        num += share * (fn / n_dec)
        den += share
        adj_n += n_dec
        subs_with_labels += 1
    gf = (num / den) if den > 0 else None

    rows.append(dict(funder=funder, total=total, positives=pos, neg_repo=neg_repo,
                     adjudicated_n=adj_n, subs_with_labels=subs_with_labels,
                     gf_weighted=gf, works=int(works.get(funder, 0))))

summary = pd.DataFrame(rows)
displayed = summary[(summary["total"] >= ART_MIN) & (summary["works"] >= WORKS_MIN)].copy()
print(f"canonical funders: {len(summary)} with >=100 articles; displayed set (>= {ART_MIN} & >= {WORKS_MIN:,} works): {len(displayed)}")

# global genuine fraction (pooled) for imputation
allfn = sum(1 for v in labs.values() if v == "false_negative")
alldec = sum(1 for v in labs.values() if v in ("false_negative", "non_open_data"))
GLOBAL = allfn / alldec
print(f"global genuine fraction (imputation fallback) = {GLOBAL:.4f}")

displayed["obs_rate"] = displayed["positives"] / displayed["total"] * 100
displayed["exposure_raw_pp"] = displayed["neg_repo"] / displayed["total"] * 100
def basis_row(r):
    # 'adjudicated' needs enough labels AND >1 contributing sub-entity when the funder is an umbrella
    return "adjudicated" if (r["adjudicated_n"] >= ADJ_MIN and pd.notna(r["gf_weighted"])) else "imputed"
displayed["basis"] = displayed.apply(basis_row, axis=1)
displayed["genuine_fraction"] = displayed.apply(
    lambda r: r["gf_weighted"] if r["basis"] == "adjudicated" else GLOBAL, axis=1)
displayed["exposure_corrected_pp"] = displayed["exposure_raw_pp"] * displayed["genuine_fraction"]

displayed = displayed.sort_values("obs_rate", ascending=False).reset_index(drop=True)
displayed["rank_observed"] = displayed["obs_rate"].rank(ascending=False, method="first").astype(int)
corr_order = (displayed["obs_rate"] + displayed["exposure_corrected_pp"]).rank(ascending=False, method="first").astype(int)
displayed["rank_corrected"] = corr_order
displayed["rank_delta"] = displayed["rank_observed"] - displayed["rank_corrected"]
displayed["single_subagency"] = (displayed["subs_with_labels"] <= 1).astype(int)
displayed["low_confidence_mover"] = (((displayed["basis"] == "imputed") | (displayed["single_subagency"] == 1))
                                     & (displayed["rank_delta"].abs() >= 4)).astype(int)

out = f"{DEST}/phase1_corrected_funders_canonical.csv"
cols = ["funder","total","positives","obs_rate","neg_repo","adjudicated_n","subs_with_labels",
        "basis","genuine_fraction","exposure_raw_pp","exposure_corrected_pp",
        "rank_observed","rank_corrected","rank_delta","single_subagency","low_confidence_mover"]
displayed[cols].round(4).to_csv(out, index=False)
# phase0 (raw exposure) view for the same canonical set
displayed[["funder","total","positives","obs_rate","neg_repo","exposure_raw_pp","rank_observed"]].round(4)\
    .to_csv(f"{DEST}/phase0_exposure_funders_canonical.csv", index=False)

tau, _ = kendalltau(displayed["rank_observed"], displayed["rank_corrected"])
solid = displayed[displayed["low_confidence_mover"] == 0]
tau_solid, _ = kendalltau(solid["rank_observed"], solid["rank_corrected"])
print(f"\nKendall tau (observed vs corrected), displayed set: {tau:.4f}")
print(f"max |rank_delta| all: {displayed['rank_delta'].abs().max()} | excluding low-confidence: {solid['rank_delta'].abs().max()}")
print(f"adjudicated: {(displayed['basis']=='adjudicated').sum()} / imputed: {(displayed['basis']=='imputed').sum()} | single-subagency: {displayed['single_subagency'].sum()}")
print("\ntop |moves| (excluding low-confidence):")
for _, r in solid.reindex(solid["rank_delta"].abs().sort_values(ascending=False).index).head(10).iterrows():
    print(f"  {r['funder'][:38]:38s} n={int(r['total']):6d} obs#{int(r['rank_observed']):2d}->#{int(r['rank_corrected']):2d} "
          f"d={int(r['rank_delta']):+3d} gf={r['genuine_fraction']:.2f} exp {r['exposure_raw_pp']:.2f}->{r['exposure_corrected_pp']:.2f}pp basis={r['basis']}")
print("\nwrote:", out)
