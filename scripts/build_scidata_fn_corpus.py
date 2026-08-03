#!/usr/bin/env python3
"""
Build the full-text corpus for the Scientific Data false-negative validation (#50).

Selects the Scientific Data articles that oddpub v7.2.3 scored `is_open_data_best
= false` in the v2 registry (research, 2024-01-01..2025-06-30) -- the "negatives"
whose true data-sharing status the LLM harness then judges -- and assembles the
full text for each.

Text source, per article (recorded in `text_source`):
  1. MinerU markdown (`minerU_out/<pfx3>/<pmid>/{auto,hybrid_auto}/<pmid>.md`):
     preferred, because it is the exact text oddpub consumed. A "false negative"
     against this text means oddpub had the statement in hand and still missed it.
  2. `pdftotext` of the local PDF (`pdfs/<pfx3>/<pmid>.pdf`): fallback for
     articles whose MinerU markdown is not staged locally (the 2025 slice). This
     conflates a MinerU-extraction miss with an oddpub-algorithm miss; the
     downstream report breaks results out by `text_source` so the fallback's
     influence is visible.

Outputs:
  - <out-jsonl> (default: scratchpad): one JSON object per line with keys
    pmid, pmcid, doi, oddpub_category, text_source, char_len, text. Full text
    is kept OUT of git (large); this file feeds the workflow harness.
  - results/scidata_fn_corpus_manifest.csv: pmid, pmcid, doi, oddpub_category,
    text_source, char_len (NO text) -- committable provenance.

Deterministic: articles ordered by pmid; text whitespace-normalized; long texts
truncated head+tail to `--max-chars` (keeps the data-availability section, which
sits near the end, ahead of references).
"""

import argparse
import csv as _csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb

DATE_FROM = "2024-01-01"
DATE_TO = "2025-06-30"
DATALAD = "/data/adamt/osm/datalad-osm"
MINERU = f"{DATALAD}/minerU_out"
PDFS = f"{DATALAD}/pdfs"


def md_path(pmid: str, extra: dict | None = None):
    # Explicit override map wins (e.g. markdown staged from HPC batch-output
    # dirs that live outside the datalad minerU_out tree -- the 2025 slice).
    if extra and pmid in extra and os.path.getsize(extra[pmid]) > 0:
        return extra[pmid]
    for sub in ("auto", "hybrid_auto"):
        f = f"{MINERU}/{pmid[:3]}/{pmid}/{sub}/{pmid}.md"
        if os.path.exists(f) and os.path.getsize(f) > 0:
            return f
    return None


def pdf_path(pmid: str):
    f = f"{PDFS}/{pmid[:3]}/{pmid}.pdf"
    return f if os.path.exists(f) else None


def pdftotext(path: str) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-q", "-nopgbrk", path, "-"],
            capture_output=True, timeout=120,
        )
        return out.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head
    return text[:head] + "\n\n[...truncated...]\n\n" + text[-tail:]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--v2-duckdb",
                    default=f"{DATALAD}/duckdbs/pmid_registry_v2.duckdb")
    ap.add_argument("--out-jsonl", default=None,
                    help="corpus JSONL path (default: scratchpad or ./scidata_fn_corpus.jsonl)")
    ap.add_argument("--text-dir", default=None,
                    help="also write one <pmid>.txt per article here (for the "
                         "per-article LLM harness); default: <out-jsonl dir>/scidata_texts")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--extra-md-map", default=None,
                    help="CSV (pmid,md_path) of markdown staged from outside the "
                         "datalad minerU_out tree; these paths take precedence")
    ap.add_argument("--max-chars", type=int, default=80000)
    args = ap.parse_args()

    extra_md = {}
    if args.extra_md_map and os.path.exists(args.extra_md_map):
        with open(args.extra_md_map, newline="") as fh:
            for r in _csv.DictReader(fh):
                extra_md[str(r["pmid"])] = r["md_path"]
        print(f"extra md-map entries: {len(extra_md)}")

    if not os.path.exists(args.v2_duckdb):
        print(f"v2 registry not found: {args.v2_duckdb}", file=sys.stderr)
        return 2

    con = duckdb.connect()
    con.execute(f"ATTACH '{args.v2_duckdb}' AS v2 (READ_ONLY)")
    rows = con.execute(
        "SELECT CAST(pmid AS VARCHAR) pmid, pmcid, doi, open_data_category_pdf_v7 "
        "FROM v2.pmids WHERE journal='Scientific Data' AND is_research "
        f"AND pub_date BETWEEN DATE '{DATE_FROM}' AND DATE '{DATE_TO}' "
        "AND NOT is_open_data_best ORDER BY pmid"
    ).fetchall()
    con.close()
    print(f"Scientific Data oddpub-negatives: {len(rows)}")

    out_jsonl = args.out_jsonl
    if out_jsonl is None:
        scratch = os.environ.get("CLAUDE_SCRATCHPAD") or ""
        out_jsonl = (str(Path(scratch) / "scidata_fn_corpus.jsonl")
                     if scratch else "scidata_fn_corpus.jsonl")
    Path(out_jsonl).parent.mkdir(parents=True, exist_ok=True)

    text_dir = Path(args.text_dir) if args.text_dir else (
        Path(out_jsonl).parent / "scidata_texts")
    text_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    n_md = n_pdf = n_none = 0
    with open(out_jsonl, "w", encoding="utf-8") as fh:
        for pmid, pmcid, doi, cat in rows:
            mp = md_path(pmid, extra_md)
            if mp:
                text = open(mp, encoding="utf-8", errors="replace").read()
                source = "mineru_md"
                n_md += 1
            else:
                pp = pdf_path(pmid)
                text = pdftotext(pp) if pp else ""
                source = "pdftotext" if text else "none"
                n_pdf += 1 if text else 0
                n_none += 0 if text else 1
            text = truncate(normalize(text), args.max_chars)
            (text_dir / f"{pmid}.txt").write_text(text, encoding="utf-8")
            rec = dict(pmid=pmid, pmcid=pmcid, doi=doi,
                       oddpub_category=cat, text_source=source,
                       char_len=len(text), text=text)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            manifest.append({k: rec[k] for k in
                             ("pmid", "pmcid", "doi", "oddpub_category",
                              "text_source", "char_len")})

    import csv
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    man_path = results_dir / "scidata_fn_corpus_manifest.csv"
    with open(man_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)

    print(f"text sources: mineru_md={n_md}  pdftotext={n_pdf}  none={n_none}")
    print(f"wrote corpus -> {out_jsonl}")
    print(f"wrote manifest -> {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
