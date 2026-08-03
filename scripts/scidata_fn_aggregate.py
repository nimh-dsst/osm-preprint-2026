#!/usr/bin/env python3
"""
Aggregate the LLM adjudications of Scientific Data oddpub-negatives (#50).

Input: the per-article label JSONL produced from the `scidata-fn-validation`
workflow output (keys: pmid, label, data_location, accession_or_link, access,
evidence_quote, rationale), joined to the corpus manifest for oddpub_category
and text_source.

Computes and reports:
  - the label breakdown over the 533 oddpub-negatives,
  - oddpub false-negative rate = false_negative / 533,
  - implied true Scientific Data open-data rate = observed 78.0% + FN/2421,
  - breakdown by the detector's original category tag and by text_source,
  - the `access` distribution (why the legitimate negatives are negative).

Outputs:
  - results/scidata_fn_labels.csv   (per-article, committable — no full text)
  - results/scidata_fn_summary.csv  (aggregate counts/rates)
Deterministic; totals are fixed inputs from the v2 registry.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Map a free-text data_location to a repository family, for the mechanism table
# (what kind of deposit oddpub's accession dictionary is missing). Order matters.
REPO_FAMILIES = [
    ("Figshare", r"figshare"),
    ("Zenodo", r"zenodo"),
    ("Dryad", r"dryad"),
    ("OSF", r"\bosf\b|open science framework"),
    ("Mendeley Data", r"mendeley"),
    ("Dataverse/Recherche Data Gouv", r"dataverse|recherche data gouv|data\.gouv|data inrae"),
    ("OpenNeuro/DANDI/EBRAINS", r"openneuro|dandi|ebrains|brainlife"),
    ("NCBI (GEO/SRA/BioProject/GenBank)", r"\bgeo\b|gene expression omnibus|\bsra\b|bioproject|genbank|ncbi"),
    ("ENA/EBI (ENA/PRIDE/ArrayExpress/BioStudies)", r"\bena\b|ebi|pride|arrayexpress|biostudies|metabolights"),
    ("Protein/structure (PDB/EMPIAR)", r"\bpdb\b|protein data bank|empiar|emdb"),
    ("Institutional / national / domain repository",
     r"csiro|jrc|gfz|wdcc|pangaea|dataone|aodn|seanoe|zenodo|nps datastore|imas|oedi|"
     r"repository|data portal|data centre|data center|data archive|data catalog"),
    ("Generic DOI (repository unclear)", r"doi\.org|https?://"),
]


def repo_family(loc: str, acc: str) -> str:
    s = f"{loc} {acc}".lower()
    for name, pat in REPO_FAMILIES:
        if re.search(pat, s):
            return name
    return "Other / unspecified"

# Fixed v2 census inputs (see scripts/build_scidata_fn_corpus.py / #50).
N_TOTAL = 2421          # Scientific Data research articles, 2024-01..2025-06
N_OBSERVED_POS = 1888   # oddpub is_open_data_best = true
N_NEG = 533             # oddpub-negatives (the set validated here)
OBSERVED_RATE = N_OBSERVED_POS / N_TOTAL  # 0.7799...


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels-jsonl", required=True,
                    help="per-article labels JSONL (workflow output, persisted)")
    ap.add_argument("--manifest", default="results/scidata_fn_corpus_manifest.csv")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args()

    man = {r["pmid"]: r for r in csv.DictReader(open(args.manifest))}
    labels = [json.loads(l) for l in open(args.labels_jsonl) if l.strip()]
    by_pmid = {str(r["pmid"]): r for r in labels}

    rows = []
    for pmid, m in man.items():
        r = by_pmid.get(pmid, {})
        rows.append({
            "pmid": pmid,
            "oddpub_category": m.get("oddpub_category", ""),
            "text_source": m.get("text_source", ""),
            "label": r.get("label", "MISSING"),
            "access": r.get("access", ""),
            "data_location": r.get("data_location", ""),
            "accession_or_link": r.get("accession_or_link", ""),
            "evidence_quote": (r.get("evidence_quote", "") or "").replace("\n", " ")[:500],
            "rationale": (r.get("rationale", "") or "").replace("\n", " ")[:500],
        })

    rd = Path(args.results_dir)
    rd.mkdir(parents=True, exist_ok=True)
    with open(rd / "scidata_fn_labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lab = Counter(r["label"] for r in rows)
    n_fn = lab.get("false_negative", 0)
    n_non = lab.get("non_open_data", 0)
    n_unclear = lab.get("unclear", 0)
    n_missing = lab.get("MISSING", 0) + lab.get("ERROR", 0)
    n = len(rows)

    fn_rate = n_fn / n
    # Implied true rate: treat confirmed FNs as true positives oddpub missed.
    implied_true = (N_OBSERVED_POS + n_fn) / N_TOTAL
    # Bounds: lower = FN only; upper = FN + unclear all true.
    implied_true_hi = (N_OBSERVED_POS + n_fn + n_unclear) / N_TOTAL
    # oddpub sensitivity on this near-fully-true set = TP / (TP + FN).
    sensitivity = N_OBSERVED_POS / (N_OBSERVED_POS + n_fn)

    print(f"\n=== Scientific Data oddpub-negative adjudication (n={n}) ===")
    for k in ("false_negative", "non_open_data", "unclear", "MISSING", "ERROR"):
        if lab.get(k):
            print(f"  {k:14s} {lab[k]:4d}  ({lab[k]/n*100:.1f}%)")
    print(f"\noddpub false-negative rate on this set = {n_fn}/{n} = {fn_rate*100:.1f}%")
    print(f"observed Scientific Data open-data rate  = {N_OBSERVED_POS}/{N_TOTAL} = {OBSERVED_RATE*100:.1f}%")
    print(f"implied TRUE open-data rate (obs + FN)   = {implied_true*100:.1f}%"
          f"  (upper, +unclear: {implied_true_hi*100:.1f}%)")
    print(f"implied detector miss on Scientific Data = {n_fn}/{N_TOTAL} = {n_fn/N_TOTAL*100:.1f}% of all its articles")
    print(f"oddpub sensitivity on this set (TP/(TP+FN)) = {N_OBSERVED_POS}/{N_OBSERVED_POS+n_fn} = {sensitivity*100:.1f}%")

    print("\n=== where the missed data actually live (repository family of the 476 FNs) ===")
    fam = Counter(repo_family(r["data_location"], r["accession_or_link"])
                  for r in rows if r["label"] == "false_negative")
    for k, v in fam.most_common():
        print(f"  {v:4d}  {k}")

    print("\n=== access distribution among non_open_data (why they are legit negatives) ===")
    acc = Counter(r["access"] for r in rows if r["label"] == "non_open_data")
    for k, v in acc.most_common():
        print(f"  {k:26s} {v}")

    print("\n=== label x oddpub_category ===")
    cats = sorted({r["oddpub_category"] or "(null)" for r in rows})
    for c in cats:
        sub = [r for r in rows if (r["oddpub_category"] or "(null)") == c]
        cc = Counter(r["label"] for r in sub)
        print(f"  {c:36s} n={len(sub):4d}  FN={cc.get('false_negative',0):3d}  non={cc.get('non_open_data',0):3d}  unclear={cc.get('unclear',0):2d}")

    print("\n=== label x text_source ===")
    for s in sorted({r["text_source"] for r in rows}):
        sub = [r for r in rows if r["text_source"] == s]
        cc = Counter(r["label"] for r in sub)
        print(f"  {s:12s} n={len(sub):4d}  FN={cc.get('false_negative',0):3d}  non={cc.get('non_open_data',0):3d}  unclear={cc.get('unclear',0):2d}")

    with open(rd / "scidata_fn_summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["n_negatives", n])
        w.writerow(["false_negative", n_fn])
        w.writerow(["non_open_data", n_non])
        w.writerow(["unclear", n_unclear])
        w.writerow(["missing_or_error", n_missing])
        w.writerow(["fn_rate_pct", round(fn_rate * 100, 2)])
        w.writerow(["observed_rate_pct", round(OBSERVED_RATE * 100, 2)])
        w.writerow(["implied_true_rate_pct", round(implied_true * 100, 2)])
        w.writerow(["implied_true_rate_hi_pct", round(implied_true_hi * 100, 2)])
        w.writerow(["sensitivity_pct", round(sensitivity * 100, 2)])
        w.writerow(["n_total_scidata", N_TOTAL])

    # Figure: observed vs implied-true rate, and where the missed data live.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                   gridspec_kw={"width_ratios": [1, 1.4]})
    ax1.bar(["observed\n(oddpub)", "implied true\n(+ LLM-confirmed\nmisses)"],
            [OBSERVED_RATE * 100, implied_true * 100],
            color=["#4472C4", "#38761d"])
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("Open-data rate (%)")
    ax1.set_title(f"Scientific Data open-data rate\nsensitivity = {sensitivity*100:.0f}%")
    for i, v in enumerate([OBSERVED_RATE * 100, implied_true * 100]):
        ax1.text(i, v + 1.5, f"{v:.1f}%", ha="center", fontweight="bold")

    fam = Counter(repo_family(r["data_location"], r["accession_or_link"])
                  for r in rows if r["label"] == "false_negative")
    items = fam.most_common()[::-1]
    ax2.barh([k for k, _ in items], [v for _, v in items], color="#38761d")
    ax2.set_xlabel("False-negative articles")
    ax2.set_title(f"Where the {n_fn} missed datasets live\n(repository family)")
    for i, (_, v) in enumerate(items):
        ax2.text(v + 2, i, str(v), va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(rd / "scidata_fn_summary.png", dpi=150)
    plt.close(fig)

    print(f"\nwrote {rd/'scidata_fn_labels.csv'}, {rd/'scidata_fn_summary.csv'}, "
          f"{rd/'scidata_fn_summary.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
