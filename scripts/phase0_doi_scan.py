#!/usr/bin/env python3
"""Phase 0 DOI-exposure scanner. Scans a slice of the manifest.
Manifest cols (tab): pmid, source(md|xml), own_doi(lower), path
Emits per-article: pmid, source, has_any_doi, has_repo_doi_anywhere, has_das_doi, has_repo_doi, matched
  has_das_doi   = any non-own DOI near data-availability language (UPPER BOUND / worst-case gate)
  has_repo_doi  = curated repo-DOI prefix near data-availability language (PRECISE)
"""
import sys, csv, re, json

manifest, start, count, out, prefixes_json = sys.argv[1:6]
PREFIXES = tuple(p + "/" for p in json.load(open(prefixes_json)))  # anchor with '/'
# Known journal/publisher DOI prefixes -> a DOI NOT in this set is likely a data/software DOI
PUBLISHER = set(json.load(open(sys.argv[6]))) if len(sys.argv) > 6 else set()
READ_CAP = 500_000  # bytes; guard against pathological large files

DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"\'<>)\]}]+')
DAS_RE = re.compile(
    r'data availab|availability of data|data are available|data is available|'
    r'data can be (?:found|access|download|obtain)|publicly available|freely available|'
    r'openly available|deposited (?:in|at|to)|underlying data|supporting data|raw data|'
    r'data supporting|data generated|data that support|data used|are available (?:in|at|from|via|on)|'
    r'available (?:in|at|from|via|on) (?:the )?(?:repositor|figshare|zenodo|dryad|osf|dataverse|database)|'
    r'available (?:upon|on) request', re.I)
K = 400  # char window around a DAS cue

def clean(d):
    return d.rstrip('.,;)]}')

rows = open(manifest, encoding="utf-8", errors="ignore").read().split("\n")
sl = rows[int(start):int(start) + int(count)]

with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pmid","source","has_any_doi","has_repo_doi_anywhere","has_nonpub_doi","has_das_doi","has_repo_doi","matched"])
    for line in sl:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        pmid, source, own_doi, path = parts
        try:
            text = open(path, encoding="utf-8", errors="ignore").read(READ_CAP).lower()
        except Exception:
            w.writerow([pmid, source, "", "", "", "", "READ_ERR"]); continue
        od = own_doi.strip().lower()
        # all DOIs (with positions)
        hits = [(m.start(), clean(m.group(0))) for m in DOI_RE.finditer(text)]
        dois = set()
        for _, d in hits:
            if od and (d == od or d.startswith(od)):
                continue
            dois.add(d)
        has_any = bool(dois)
        repo_any = any(d.startswith(PREFIXES) for d in dois)
        # non-publisher DOI = prefix (10.xxxx) not in the known-publisher set -> likely data/software
        def prefix_of(d):
            return d.split("/", 1)[0]
        nonpub = any(prefix_of(d) not in PUBLISHER for d in dois) if PUBLISHER else False
        # DAS windows
        spans = [(max(0, m.start() - K), m.end() + K) for m in DAS_RE.finditer(text)]
        das_doi = False
        das_repo_prefixes = set()
        if spans:
            for pos, d in hits:
                if od and (d == od or d.startswith(od)):
                    continue
                if any(s <= pos <= e for s, e in spans):
                    das_doi = True
                    for p in PREFIXES:
                        if d.startswith(p):
                            das_repo_prefixes.add(p[:-1])  # drop trailing '/'
        matched = ";".join(sorted(das_repo_prefixes))
        w.writerow([pmid, source, int(has_any), int(repo_any), int(nonpub), int(das_doi),
                    int(bool(das_repo_prefixes)), matched])
