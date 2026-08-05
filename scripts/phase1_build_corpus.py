#!/usr/bin/env python3
"""Build focused adjudication excerpts for the Phase 1 sample.
Excerpt = title/abstract head + windows around each repo-DOI + data-availability cues.
Keeps the deposit-vs-reuse context while fitting many articles per agent context.
"""
import csv, re, os, sys, json
from pathlib import Path

SCR = sys.argv[1]
XMLDIR = Path(SCR) / "phase1_xml"
OUT = Path(SCR) / "phase1_texts"; OUT.mkdir(exist_ok=True)
PREFIXES = tuple(p + "/" for p in json.load(open(f"{SCR}/repo_doi_prefixes.json")))

DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"\'<>)\]}]+')
DAS_RE = re.compile(r'data availab|availability of data|data are available|data record|data citation|'
                    r'deposited|repository|figshare|zenodo|dryad|dataverse|osf\b|dryad|accession|'
                    r'underlying data|supporting data|openly available|publicly available|archived at|'
                    r'available (?:at|from|in|via)|code availab', re.I)

def strip_xml(raw):
    raw = re.sub(r'<(ref-list|back)\b.*?</\1>', ' ', raw, flags=re.S | re.I)  # drop bibliography
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = re.sub(r'&[a-z#0-9]+;', ' ', raw)
    return raw

def excerpt(text):
    text = re.sub(r'[ \t]+', ' ', text)
    n = len(text)
    keep = []
    keep.append((0, min(1800, n)))  # head: title/abstract
    for m in DOI_RE.finditer(text):
        if m.group(0).startswith(PREFIXES):
            keep.append((max(0, m.start() - 1500), min(n, m.end() + 800)))
    for m in DAS_RE.finditer(text):
        keep.append((max(0, m.start() - 500), min(n, m.start() + 1200)))
    # merge overlapping spans, cap total ~8000 chars
    keep.sort()
    merged = []
    for s, e in keep:
        if merged and s <= merged[-1][1] + 100:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out = []
    total = 0
    for s, e in merged:
        if total > 8000:
            break
        chunk = text[s:e]
        out.append(chunk); total += len(chunk)
    return "\n[...]\n".join(out)

rows = list(csv.DictReader(open(f"{SCR}/phase1_meta.csv")))
n_ok = 0
for r in rows:
    pmid, source, path = r["pmid"], r["source"], r["path"]
    try:
        if source == "md":
            raw = open(path, encoding="utf-8", errors="ignore").read()
        else:
            xp = XMLDIR / re.sub(r'.*baseline\.2025-06-26/', '', path)
            raw = strip_xml(open(xp, encoding="utf-8", errors="ignore").read())
        ex = excerpt(raw)
        (OUT / f"{pmid}.txt").write_text(ex, encoding="utf-8")
        n_ok += 1
    except Exception as e:
        (OUT / f"{pmid}.txt").write_text(f"[ERROR reading text: {e}]", encoding="utf-8")
print(f"excerpts written: {n_ok}/{len(rows)}")
# sanity: avg excerpt size
sizes = [len((OUT / f"{r['pmid']}.txt").read_text()) for r in rows]
print(f"excerpt chars: mean={sum(sizes)//len(sizes)} max={max(sizes)}")
