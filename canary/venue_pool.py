#!/usr/bin/env python3
"""canary/venue_pool.py — Wikidata venue pool for the LOCAL-611 canary.

Michael (2026-10-07): "how would it help when there is a new tour? You should
try a new tour all the time as part of your check. Europe alone has 34,000 to
nearly 190,000 museums."

This module builds and caches, WEEKLY, a large venue list drawn from Wikidata
so the canary can try a never-seen venue on every run. It covers the venue
*types* that have broken in the field:

    * museums (Q33506) and their subclasses
    * art galleries (Q1007870)
    * historic house museums (Q2087181)
    * churches (Q16970) and cathedrals (Q2977)
    * parks (Q22698)
    * city landmark streets / pedestrian streets (Q79007 street, Q21000333
      pedestrian street) — the walking-tour material

Each cached row has:
    qid        — Wikidata Q-id (e.g. "Q160236")
    label      — English (or best available) label
    city       — city/admin label when available, else ""
    country    — country label (English)
    country_qid— country Q-id (used for stratifying / coverage counting)
    lat, lng   — coordinates (floats) when present, else None
    sitelinks  — number of Wikipedia/Wikimedia sitelinks (fame proxy)
    has_site   — True iff the item has an official website (P856)
    kind       — one of: museum, gallery, historic_house, church, cathedral,
                 park, street  (what we queried it as)

The pool is stored as JSON Lines at canary/venue_pool.jsonl. A sidecar
canary/venue_pool.meta.json records when it was built and the row/country
counts, so build() is a no-op within CACHE_MAX_AGE_DAYS unless force=True.

Design notes
------------
* WDQS (query.wikidata.org) enforces a ~60s per-query timeout. A single global
  "all museums on Earth" query times out, so we iterate PER COUNTRY and, within
  a country, page with LIMIT/OFFSET. Countries are discovered first (one small
  query), then each (country, kind) slice is pulled in pages. This keeps every
  individual query small and well under the timeout, and it guarantees breadth
  across countries rather than 20k rows from one country.
* The network layer is isolated behind _sparql(). Tests monkeypatch
  _sparql / build-time collaborators, so importing this module never touches
  the network and the picker/report tests run offline.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
POOL_PATH = os.path.join(HERE, "venue_pool.jsonl")
META_PATH = os.path.join(HERE, "venue_pool.meta.json")

WDQS_ENDPOINT = os.environ.get(
    "WDQS_ENDPOINT", "https://query.wikidata.org/sparql"
)
# A descriptive UA is required by the WDQS etiquette policy.
USER_AGENT = os.environ.get(
    "CANARY_WDQS_UA",
    "AudiouraCanary/1.0 (LOCAL-611 venue pool; contact: dev@audioura.local)",
)

CACHE_MAX_AGE_DAYS = int(os.environ.get("CANARY_POOL_MAX_AGE_DAYS", "7"))

# Minimum acceptance thresholds the deliverable requires.
MIN_ROWS = int(os.environ.get("CANARY_POOL_MIN_ROWS", "20000"))
MIN_COUNTRIES = int(os.environ.get("CANARY_POOL_MIN_COUNTRIES", "60"))

# WDQS paging. Keep LIMIT modest so each query stays far under the 60s ceiling.
PAGE_LIMIT = int(os.environ.get("CANARY_POOL_PAGE_LIMIT", "1500"))
MAX_PAGES_PER_SLICE = int(os.environ.get("CANARY_POOL_MAX_PAGES", "20"))
# Politeness delay between queries (seconds).
QUERY_DELAY_S = float(os.environ.get("CANARY_POOL_QUERY_DELAY", "1.0"))

# Venue kinds → the Wikidata class used in the query. For museums we include
# subclasses (wdt:P31/wdt:P279*) because the long tail of museum subtypes is
# exactly where the field defects came from. Others are matched directly, which
# is both faster and sufficient for breadth.
KIND_CLASSES: Dict[str, Dict[str, object]] = {
    "museum": {"qid": "Q33506", "subclasses": True},
    "gallery": {"qid": "Q1007870", "subclasses": True},
    "historic_house": {"qid": "Q2087181", "subclasses": True},
    "church": {"qid": "Q16970", "subclasses": True},
    "cathedral": {"qid": "Q2977", "subclasses": True},
    "park": {"qid": "Q22698", "subclasses": False},
    "street": {"qid": "Q79007", "subclasses": False},
}


# --------------------------------------------------------------------------- #
# Network layer (isolated for testability)
# --------------------------------------------------------------------------- #
def _sparql(query: str, *, timeout: int = 60) -> dict:
    """Run a SPARQL query against WDQS and return the parsed JSON.

    Isolated so tests can monkeypatch it. Raises on HTTP error.
    """
    import requests  # local import: keeps module import network-free

    resp = requests.get(
        WDQS_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------- #
# SPARQL builders
# --------------------------------------------------------------------------- #
def _countries_query() -> str:
    """Countries (Q6256) that are current sovereign states, with English labels."""
    return (
        "SELECT ?country ?countryLabel WHERE {\n"
        "  ?country wdt:P31 wd:Q6256 .\n"
        "  FILTER NOT EXISTS { ?country wdt:P576 ?dissolved. }\n"
        '  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }\n'
        "}\n"
    )


def _venue_slice_query(country_qid: str, kind: str, offset: int, limit: int) -> str:
    """One page of venues of a given kind located in a given country.

    Uses wdt:P17 (country) to bind the venue to the country, which is the
    broadest and most reliable location predicate across venue types.
    """
    spec = KIND_CLASSES[kind]
    cls = spec["qid"]
    if spec["subclasses"]:
        type_clause = f"?item wdt:P31/wdt:P279* wd:{cls} ."
    else:
        type_clause = f"?item wdt:P31 wd:{cls} ."
    # ?sitelinks via wikibase:sitelinks on the item. P856 presence → ?site.
    return (
        "SELECT ?item ?itemLabel ?countryLabel ?locLabel ?coord ?sitelinks ?site WHERE {\n"
        f"  ?item wdt:P17 wd:{country_qid} .\n"
        f"  {type_clause}\n"
        "  ?item wikibase:sitelinks ?sitelinks .\n"
        "  OPTIONAL { ?item wdt:P625 ?coord. }\n"
        "  OPTIONAL { ?item wdt:P856 ?site. }\n"
        f"  BIND(wd:{country_qid} AS ?country)\n"
        "  OPTIONAL { ?item wdt:P131 ?loc. }\n"
        '  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }\n'
        "}\n"
        f"ORDER BY DESC(?sitelinks) ?item\n"
        f"LIMIT {limit} OFFSET {offset}\n"
    )


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1] if uri else ""


def _parse_coord(wkt: Optional[str]):
    """Parse a WKT 'Point(lng lat)' into (lat, lng) floats, or (None, None)."""
    if not wkt or not wkt.startswith("Point("):
        return None, None
    try:
        inner = wkt[len("Point("):].rstrip(")")
        lng_s, lat_s = inner.split()
        return float(lat_s), float(lng_s)
    except Exception:
        return None, None


def _rows_from_bindings(bindings: Iterable[dict], kind: str) -> List[dict]:
    rows = []
    for b in bindings:
        item_uri = b.get("item", {}).get("value", "")
        qid = _qid_from_uri(item_uri)
        if not qid:
            continue
        label = b.get("itemLabel", {}).get("value", "") or ""
        # WDQS returns the Q-id as the label when no label exists; drop those.
        if label == qid:
            label = ""
        country = b.get("countryLabel", {}).get("value", "") or ""
        city = b.get("locLabel", {}).get("value", "") or ""
        if city == country:
            city = ""
        lat, lng = _parse_coord(b.get("coord", {}).get("value"))
        try:
            sitelinks = int(b.get("sitelinks", {}).get("value", "0") or "0")
        except (TypeError, ValueError):
            sitelinks = 0
        has_site = bool(b.get("site", {}).get("value"))
        rows.append(
            {
                "qid": qid,
                "label": label,
                "city": city,
                "country": country,
                "lat": lat,
                "lng": lng,
                "sitelinks": sitelinks,
                "has_site": has_site,
                "kind": kind,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def fetch_countries(sparql: Callable[[str], dict] = _sparql) -> List[Dict[str, str]]:
    """Return [{qid,label}] for sovereign states, label-sorted for determinism."""
    data = sparql(_countries_query())
    out = []
    for b in data.get("results", {}).get("bindings", []):
        qid = _qid_from_uri(b.get("country", {}).get("value", ""))
        label = b.get("countryLabel", {}).get("value", "") or ""
        if qid and label and label != qid:
            out.append({"qid": qid, "label": label})
    out.sort(key=lambda c: c["label"])
    return out


def _iter_slice(country_qid, kind, sparql, delay):
    """Yield rows for one (country, kind) slice, paging until exhausted/capped."""
    for page in range(MAX_PAGES_PER_SLICE):
        offset = page * PAGE_LIMIT
        q = _venue_slice_query(country_qid, kind, offset, PAGE_LIMIT)
        try:
            data = sparql(q)
        except Exception as e:  # transient WDQS error: skip this page
            print(f"[venue_pool] slice {kind}@{country_qid} p{page} error: {e}")
            break
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            break
        yield from _rows_from_bindings(bindings, kind)
        if len(bindings) < PAGE_LIMIT:
            break
        if delay:
            time.sleep(delay)


def build(
    *,
    force: bool = False,
    sparql: Callable[[str], dict] = _sparql,
    pool_path: str = POOL_PATH,
    meta_path: str = META_PATH,
    min_rows: int = MIN_ROWS,
    min_countries: int = MIN_COUNTRIES,
    delay: float = QUERY_DELAY_S,
    progress: bool = True,
) -> dict:
    """Build the venue pool and write JSONL + meta. Weekly-cached.

    Returns the meta dict {built_at, rows, countries, path}. If a fresh cache
    exists (younger than CACHE_MAX_AGE_DAYS) and force is False, returns the
    existing meta without hitting the network.
    """
    if not force and is_cache_fresh(meta_path):
        return load_meta(meta_path)

    countries = fetch_countries(sparql)
    if progress:
        print(f"[venue_pool] {len(countries)} countries discovered")

    seen_qids = set()
    rows_written = 0
    countries_with_rows = set()

    tmp_path = pool_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        # Pull the big-tail kinds first so breadth accrues early; museums last
        # because they are the largest and we want wide country coverage before
        # we exhaust the per-slice page cap in any single country.
        kind_order = ["museum", "gallery", "historic_house", "church",
                      "cathedral", "park", "street"]
        for ci, country in enumerate(countries):
            cqid = country["qid"]
            for kind in kind_order:
                for row in _iter_slice(cqid, kind, sparql, delay):
                    if row["qid"] in seen_qids:
                        continue
                    seen_qids.add(row["qid"])
                    # Prefer the country label from the query; fall back to the
                    # discovered country label when WDQS omitted it.
                    if not row["country"]:
                        row["country"] = country["label"]
                    row["country_qid"] = cqid
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows_written += 1
                    countries_with_rows.add(cqid)
            if progress and (ci + 1) % 10 == 0:
                print(f"[venue_pool]   {ci + 1}/{len(countries)} countries, "
                      f"{rows_written} rows, {len(countries_with_rows)} countries w/ rows")

    os.replace(tmp_path, pool_path)

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows_written,
        "countries": len(countries_with_rows),
        "path": pool_path,
        "min_rows": min_rows,
        "min_countries": min_countries,
        "meets_min": rows_written >= min_rows and len(countries_with_rows) >= min_countries,
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    if progress:
        print(f"[venue_pool] DONE rows={rows_written} countries={len(countries_with_rows)} "
              f"meets_min={meta['meets_min']}")
    return meta


# --------------------------------------------------------------------------- #
# Cache helpers / loading
# --------------------------------------------------------------------------- #
def is_cache_fresh(meta_path: str = META_PATH, max_age_days: int = CACHE_MAX_AGE_DAYS) -> bool:
    """True iff a meta file exists, is younger than max_age_days, and the pool
    file it points to exists."""
    meta = load_meta(meta_path)
    if not meta:
        return False
    pool = meta.get("path", POOL_PATH)
    if not os.path.exists(pool):
        return False
    try:
        built = datetime.fromisoformat(meta["built_at"])
    except Exception:
        return False
    if built.tzinfo is None:
        built = built.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - built).total_seconds() / 86400.0
    return age_days < max_age_days


def load_meta(meta_path: str = META_PATH) -> dict:
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def load_pool(pool_path: str = POOL_PATH) -> List[dict]:
    """Read the JSONL pool into a list of dicts. Empty list if absent."""
    if not os.path.exists(pool_path):
        return []
    out = []
    with open(pool_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def pool_stats(pool_path: str = POOL_PATH) -> dict:
    """Row count and distinct-country count for the pool on disk."""
    rows = 0
    countries = set()
    if not os.path.exists(pool_path):
        return {"rows": 0, "countries": 0}
    with open(pool_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            c = r.get("country_qid") or r.get("country")
            if c:
                countries.add(c)
    return {"rows": rows, "countries": len(countries)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build/refresh the canary Wikidata venue pool.")
    ap.add_argument("--force", action="store_true", help="Rebuild even if cache is fresh.")
    ap.add_argument("--stats", action="store_true", help="Print stats for the pool on disk and exit.")
    args = ap.parse_args()

    if args.stats:
        print(json.dumps({"meta": load_meta(), "disk": pool_stats()}, indent=2))
    else:
        build(force=args.force)
