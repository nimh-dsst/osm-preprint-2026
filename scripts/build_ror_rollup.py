#!/usr/bin/env python3
"""Build the ROR-derived sub-agency rollup map used by table_funders.py.

WHY THIS EXISTS
---------------
Our funder design aggregates constituent funders into their parent agency (NIH
institutes -> NIH, EU framework programmes -> European Commission). OpenAlex,
however, surfaces many sub-agency programmes as *separate* funder entities whose
parent agency is also in our corpus (e.g. the NSF Directorate for Biological
Sciences, DOE's Office of Science, USDA's NIFA). Left alone they both (a) rank
alongside their own parent, contradicting the aggregation design, and (b) leave
the parent agency's totals undercounted.

Neither available metadata source encodes the hierarchy for us:
  * ``funders.parent_funder_id`` is NULL for every row in the registry, and
  * the OpenAlex funder API returns ``parent_organization: null`` for these.
Both do carry a ROR id, and ROR models parent/child relationships explicitly, so
ROR is the authority we roll up against. This script resolves each sub-unit to
its root agency and writes the mapping to a CSV that ``table_funders.py``
consumes. The CSV is committed so the table pipeline needs no network access;
re-run this script when the corpus or ROR data changes.

BOUNDARY RULE (agreed 2026-07-16, GitHub #33)
---------------------------------------------
Within a vetted allow-list of *root agencies* (``_ROOT_AGENCIES``), fold every
corpus funder entity that ROR places beneath that agency, at any depth, into the
agency. ROR decides *which* entities fold, so the set is complete and auditable
rather than hand-picked -- if ROR says the NSF Division of Chemistry sits under
NSF, it folds, and we do not have to argue each programme office individually.

The allow-list exists because ROR encodes administrative *containment*, not
"funder of record". Applied without one, the rule folds away the funders this
paper is about: JSPS (20.6k articles) into MEXT, NHMRC and the ARC into
"Australian Government", CNPq/CAPES into Brazilian ministries, NIH's ~84k
articles into HHS, and -- via a ROR quirk -- the China Scholarship Council into
the People's Government of Jilin Province. The agencies below are the ones where
a sub-unit actually competes with its own parent in our table; every other funder
keeps its own row.

De-duplication and nesting are handled downstream for free: the group query in
``data_loader.query_funder_open_data_for_group`` counts ``COUNT(DISTINCT pmid)``
over the union of member names, so an article crediting both a child and its
parent counts once, and folding DOE BER straight to DOE (rather than through the
Office of Science) cannot double-count.

Usage:
    python scripts/build_ror_rollup.py --duckdb-path <db> --verbose
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import requests

logger = logging.getLogger(__name__)

ROR_API = "https://api.ror.org/v2/organizations"
DEFAULT_OUTPUT = Path(__file__).parent / "funder_ror_rollup.csv"
DEFAULT_CACHE = Path(__file__).parent / ".ror_cache.json"

# ---------------------------------------------------------------------------
# Root agencies: keys are DuckDB canonical_names.
# ---------------------------------------------------------------------------
# Each is a funder of record whose own sub-units OpenAlex surfaces separately.
# Cabinet departments appear here where grantees cite the department itself
# (USDA, DOE, DoD) and their sub-units are programme offices. HHS is deliberately
# absent for the mirror-image reason: for biomedical research the funder of record
# is the operating division (NIH, CDC), not the department, so NIH and CDC are
# roots in their own right and nothing folds into HHS.
_ROOT_AGENCIES: dict[str, dict] = {
    "National Science Foundation": {},
    "U.S. Department of Energy": {},
    "U.S. Department of Agriculture": {},
    "National Institutes of Health": {},
    "U.S. Department of Defense": {},
    "Centers for Disease Control and Prevention": {},
    "U.S. Department of Veterans Affairs": {},
    "Helmholtz Association": {
        # This corpus entity carries no ror_id, so the ROR descent is seeded from
        # the Helmholtz-Gemeinschaft id instead -- the same real organisation,
        # which OpenAlex happens to also carry as a second funder entity. That
        # duplicate folds in here like any other member centre.
        "ror": "0281dp749",
    },
}

# ROR organization types never folded into a funder. Degree-granting bodies are
# independent legal entities even where ROR places them under an agency (e.g. the
# Naval Postgraduate School under DoD).
_EXCLUDED_TYPES: set[str] = {"education"}

# Individual entities that survive the rules above but still should not fold.
_EXCLUDED_CHILDREN: dict[str, str] = {}


def _norm_ror(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1]


class RorClient:
    """Small cached ROR v2 client (cache is on-disk so re-runs are cheap)."""

    def __init__(self, cache_path: Path, mailto: str):
        self.cache_path = cache_path
        self.cache: dict[str, dict | None] = (
            json.loads(cache_path.read_text()) if cache_path.exists() else {}
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"osm-preprint-2026 ({mailto})"

    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache))

    def get(self, ror_id: str) -> dict | None:
        ror_id = _norm_ror(ror_id)
        if ror_id in self.cache:
            return self.cache[ror_id]
        for attempt in range(4):
            try:
                resp = self.session.get(f"{ROR_API}/{ror_id}", timeout=30)
                if resp.status_code == 404:
                    self.cache[ror_id] = None  # genuine "no such record"
                    return None
                resp.raise_for_status()
                payload = resp.json()
                names = [
                    n["value"] for n in payload.get("names", [])
                    if "ror_display" in n.get("types", [])
                ]
                rec = {
                    "id": ror_id,
                    "name": names[0] if names else "",
                    "types": payload.get("types", []),
                    "parents": [
                        _norm_ror(r["id"]) for r in payload.get("relationships", [])
                        if r["type"] == "parent"
                    ],
                    "children": [
                        _norm_ror(r["id"]) for r in payload.get("relationships", [])
                        if r["type"] == "child"
                    ],
                }
                self.cache[ror_id] = rec
                return rec
            except Exception as exc:
                if attempt == 3:
                    # Deliberately NOT cached as None: a transient failure cached
                    # as a permanent negative silently orphans everything beneath
                    # the node (this dropped the whole DOE Office of Science
                    # subtree on an earlier run). Fail loudly instead.
                    raise RuntimeError(f"ROR fetch failed for {ror_id}: {exc}") from exc
                time.sleep(1 + 2 * attempt)
        return None

    def get_many(self, ror_ids: list[str], workers: int = 8) -> None:
        todo = [r for r in ror_ids if _norm_ror(r) not in self.cache]
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(self.get, todo))
        self.save()


def load_corpus_funders(con, date_from, date_to, research_only) -> list[dict]:
    clauses, params = [], []
    if date_from:
        clauses.append("AND p.pub_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("AND p.pub_date <= ?")
        params.append(date_to)
    if research_only:
        clauses.append("AND p.is_research = true")
    sql = f"""
    SELECT f.funder_id, f.canonical_name, f.ror_id, COUNT(DISTINCT af.pmid) AS n
    FROM article_funders af
    JOIN funders f ON af.funder_id = f.funder_id
    JOIN pmids p ON af.pmid = p.pmid
    WHERE (p.has_oddpub_xml_v7 = true OR p.has_oddpub_pdf_v7 = true)
      {' '.join(clauses)}
    GROUP BY 1, 2, 3
    """
    return [
        {"funder_id": r[0], "canonical_name": r[1], "ror": _norm_ror(r[2]), "n": r[3]}
        for r in con.execute(sql, params).fetchall()
    ]


def build_rollup(con, client: RorClient, date_from, date_to, research_only) -> list[dict]:
    corpus = load_corpus_funders(con, date_from, date_to, research_only)
    logger.info("corpus funder entities: %d", len(corpus))

    by_ror: dict[str, list[dict]] = {}
    by_name: dict[str, dict] = {}
    for ent in corpus:
        if ent["ror"]:
            by_ror.setdefault(ent["ror"], []).append(ent)
        by_name[ent["canonical_name"]] = ent

    # Resolve each root agency to the ROR id its descent starts from.
    root_ror_to_name: dict[str, str] = {}
    for name, cfg in _ROOT_AGENCIES.items():
        ent = by_name.get(name)
        if not ent:
            logger.warning("root agency %r absent from corpus -- skipped", name)
            continue
        ror = cfg.get("ror") or ent["ror"]
        if not ror:
            logger.warning("root agency %r has no ROR id and no override -- skipped", name)
            continue
        root_ror_to_name[ror] = name
    logger.info("root agencies resolved: %d", len(root_ror_to_name))

    # Walk DOWN from each root, recording which root every node descends from.
    owner: dict[str, str] = {}  # ror -> root canonical_name
    for root_ror, root_name in root_ror_to_name.items():
        frontier, seen = [root_ror], {root_ror}
        owner[root_ror] = root_name
        while frontier:
            client.get_many(frontier)
            nxt = []
            for rid in frontier:
                rec = client.get(rid)
                if not rec:
                    continue
                for child in rec["children"]:
                    if child in seen:
                        continue
                    seen.add(child)
                    if child in owner and owner[child] != root_name:
                        logger.warning("ROR node %s reachable from both %r and %r; "
                                       "keeping %r", child, owner[child], root_name,
                                       owner[child])
                        continue
                    owner[child] = root_name
                    nxt.append(child)
            frontier = nxt
        logger.info("  %-44s subtree: %d ROR nodes", root_name[:44], len(seen))
    client.save()

    rows = []
    for rid, root_name in sorted(owner.items()):
        if rid not in by_ror:
            continue
        rec = client.get(rid)
        if not rec:
            continue
        if set(rec["types"]) & _EXCLUDED_TYPES:
            logger.info("  skip %-44s (ROR type %s)", rec["name"][:44], rec["types"])
            continue
        root = by_name[root_name]
        for child in by_ror[rid]:
            # The root itself, and any name-variant entity that IS the root.
            if child["canonical_name"] == root_name:
                continue
            if child["canonical_name"] in _EXCLUDED_CHILDREN:
                logger.info("  exception: not folding %s (%s)", child["canonical_name"],
                            _EXCLUDED_CHILDREN[child["canonical_name"]])
                continue
            rows.append({
                "child_canonical_name": child["canonical_name"],
                "child_funder_id": child["funder_id"],
                "child_ror": rid,
                "child_types": "|".join(rec["types"]),
                "child_articles": child["n"],
                "parent_canonical_name": root_name,
                "parent_funder_id": root["funder_id"],
                "parent_ror": next((r for r, n in root_ror_to_name.items()
                                    if n == root_name), ""),
            })
    rows.sort(key=lambda r: (r["parent_canonical_name"], -r["child_articles"],
                             r["child_canonical_name"]))
    return rows


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duckdb-path", required=True)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--mailto", default="claude@adamthomas.io")
    ap.add_argument("--date-from", default="2024-01-01")
    ap.add_argument("--date-to", default="2025-06-30")
    ap.add_argument("--research-only", action="store_true", default=True)
    ap.add_argument("--verbose", "-v", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")
    db = Path(args.duckdb_path)
    if not db.exists() or db.stat().st_size < 1024:
        logger.error("DuckDB registry not available at %s. If the datalad annex "
                     "pointer is unresolved run:\n"
                     "  cd ../datalad-osm && datalad get duckdbs/pmid_registry.duckdb", db)
        return 1
    con = duckdb.connect(str(db), read_only=True)
    client = RorClient(args.cache, args.mailto)
    rows = build_rollup(con, client, args.date_from, args.date_to, args.research_only)
    con.close()

    fields = ["child_canonical_name", "child_funder_id", "child_ror", "child_types",
              "child_articles", "parent_canonical_name", "parent_funder_id", "parent_ror"]
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    parents = {r["parent_canonical_name"] for r in rows}
    logger.info("\nwrote %s: %d child entities -> %d root agencies",
                args.output, len(rows), len(parents))
    for p in sorted(parents):
        kids = [r for r in rows if r["parent_canonical_name"] == p]
        logger.info("  %-46s %3d children, %6d child credits",
                    p[:46], len(kids), sum(k["child_articles"] for k in kids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
