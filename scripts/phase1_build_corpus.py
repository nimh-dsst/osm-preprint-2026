#!/usr/bin/env python3
"""Build the Phase 1 adjudication text corpus ({pmid}.txt) for the sampled articles.

Markdown articles (PDF-covered): read the MinerU markdown as-is.
XML-only articles: strip ONLY the <ref-list> (bibliography = citation noise); KEEP the rest of
JATS <back> (data-availability sections, notes, footnotes) — the Data Availability Statement
frequently lives there. (An earlier version stripped all of <back>, which removed the DAS for
~60% of XML articles and mislabeled genuine deposits as non_open_data/unclear — see #56.)

Full text is truncated to 80k chars (head 48k + tail 32k) to keep both front-matter and the
back-matter data statements. Usage: python phase1_build_corpus.py <meta.csv> <xml_dir> <out_dir>
"""
import csv, re, sys
from pathlib import Path

META, XMLDIR, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)

def strip_xml(raw):
    raw = re.sub(r'<ref-list\b.*?</ref-list>', ' ', raw, flags=re.S | re.I)  # drop ONLY bibliography
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = re.sub(r'&[a-z#0-9]+;', ' ', raw)
    return raw

def trunc(t, cap=80000):
    t = re.sub(r'[ \t]+', ' ', t); t = re.sub(r'\n{3,}', '\n\n', t)
    return t if len(t) <= cap else t[:48000] + "\n\n[... middle truncated ...]\n\n" + t[-32000:]

ok = 0
rows = list(csv.DictReader(open(META)))
for r in rows:
    pmid, source, path = r["pmid"], r["source"], r["path"]
    try:
        if source == "md":
            raw = open(path, encoding="utf-8", errors="ignore").read()
        else:
            xp = XMLDIR / re.sub(r'.*baseline\.2025-06-26/', '', path)
            raw = strip_xml(open(xp, encoding="utf-8", errors="ignore").read())
        (OUT / f"{pmid}.txt").write_text(trunc(raw), encoding="utf-8"); ok += 1
    except Exception as e:
        (OUT / f"{pmid}.txt").write_text(f"[ERROR: {e}]", encoding="utf-8")
print(f"corpus written: {ok}/{len(rows)}")
