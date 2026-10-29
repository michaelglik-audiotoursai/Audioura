#!/usr/bin/env python3
"""proof_local813_offline.py — LOCAL-813 OFFLINE pin proof, before/after.

Reads the STORED stops (titles + shipped pins) of the 6 failing tours
(854/855/857/860/861/862) from the Mac dev Postgres (READ-ONLY, one SELECT per
tour via `docker exec`, no writes), then:

  BEFORE  — distance from each stored SHIPPED pin to the stop's authority
            (Wikidata P625 for a place; the museum building P625 for a museum
            tour's artwork stops).
  AFTER   — applies the LOCAL-813 snap (pin_snap.snap_poi_coordinates, live
            Wikidata landmark lookup, museum building venue-fallback) and measures
            the SNAPPED pin to the SAME authority.

No generation, no Serper, no paid API, no DB writes. Live Wikidata reads only.
Prints a per-stop before/after table and the worst-pin summary per tour (the
≤150 m catalog bar). Ground-truth QIDs are the ones confirmed in
SUBMISSION_LOCAL-813.md; the authority coordinate is fetched live from Wikidata
P625 so the numbers are not hand-copied.

Usage:  python3 proof_local813_offline.py
"""
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LANDMARK_LIVE_LOOKUP"] = "1"
os.environ.pop("SERPER_API_KEY", None)  # free run: no Serper

import pin_snap
import wikidata_landmark_lookup as wll
from stop_existence_gate import _geocode_scope_bbox

CONTAINER = os.environ.get("CATALOG_DB_CONTAINER", "development-postgres-2-1")
DB = os.environ.get("CATALOG_DB_NAME", "audiotours")
DBUSER = os.environ.get("CATALOG_DB_USER", "admin")

# Authority QID per stop title (confirmed live Wikidata P625 during diagnosis).
# Stops whose authority is the museum BUILDING (artwork stops) use key "*building".
GROUND_TRUTH_QID = {
    854: {"Nanzen-ji": "Q1089767", "Ryozen Kannon": "Q7385349",
          "Eikan-do Zenrin-ji": "Q2380134", "Kodai-ji": "Q2702064",
          "Shoren-in": "Q377386"},
    855: {"Nakamise Street": "Q107583845", "Asakusa Shrine": "Q670049"},
    857: {"Miradouro de Santa Luzia": "Q6837314",
          "Castelo de São Jorge": "Q636780",
          "Igreja de Santo António de Lisboa": "Q2976487",
          "Panteão Nacional": "Q1601019", "Museu de Fado": "Q1954395"},
    860: {"Campanile di San Marco": "Q754194", "Palazzo Ducale": "Q189883",
          "Basilica di San Marco": "Q172988", "Teatro La Fenice": "Q223942",
          "Museo Correr": "Q1470912"},
    861: {"*building": "Q87193291"},  # Upper Belvedere (painting galleries)
    862: {"Bach Ma Temple": "Q10841667", "Dong Xuan Market": "Q1094375",
          "Ngoc Son Temple": "Q3517494", "Hoan Kiem Lake": "Q1151254"},
}

TOURS = {
    854: ("Higashiyama, Kyoto, Japan", (35.0030, 135.7820), False),
    855: ("Asakusa, Tokyo, Japan", (35.7148, 139.7967), False),
    857: ("Alfama, Lisbon, Portugal", (38.7120, -9.1300), False),
    860: ("San Marco, Venice, Italy", (45.4340, 12.3390), False),
    861: ("Belvedere Museum, Vienna, Austria", (48.1914, 16.3808), True),
    862: ("Old Quarter, Hanoi, Vietnam", (21.0333, 105.8500), False),
}

_WD_API = "https://www.wikidata.org/w/api.php"
_UA = {"User-Agent": "audioura-local813-proof/1.0 (dev)"}


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def psql(sql):
    cmd = ["docker", "exec", CONTAINER, "psql", "-U", DBUSER, "-d", DB, "-Atc", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"DB read failed: {r.stderr.strip()}")
    return r.stdout


def parse_stops(content):
    import re
    out = []
    headers = list(re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", content))
    for i, h in enumerate(headers):
        s = h.end()
        e = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        block = content[s:e]
        cm = re.search(r"(?mi)^\s*Coordinates:\s*(.+)$", block)
        coord = None
        if cm:
            mm = re.search(r"(-?\d+(?:\.\d+)?)\s*[,/ ]\s*(-?\d+(?:\.\d+)?)",
                           cm.group(1))
            if mm:
                coord = (float(mm.group(1)), float(mm.group(2)))
        out.append({"name": h.group(1).strip(), "coordinate": coord})
    return out


_P625_CACHE = {}


def p625(qid):
    if qid in _P625_CACHE:
        return _P625_CACHE[qid]
    import urllib.request
    url = (f"{_WD_API}?action=wbgetentities&ids={qid}&props=claims"
           f"&format=json")
    for _ in range(4):
        try:
            d = json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=_UA), timeout=20))
            cl = d["entities"][qid].get("claims", {})
            pt = None
            for c in cl.get("P625", []):
                v = c["mainsnak"].get("datavalue", {}).get("value", {})
                pt = (round(v.get("latitude"), 6), round(v.get("longitude"), 6))
            _P625_CACHE[qid] = pt
            time.sleep(3)
            return pt
        except Exception:
            time.sleep(10)
    _P625_CACHE[qid] = None
    return None


def main():
    print("LOCAL-813 OFFLINE pin proof — before/after vs Wikidata P625 authority")
    print("(read-only DB, live Wikidata reads, NO generation, NO Serper, NO writes)\n")
    grand_before_fail = grand_after_fail = grand_total = 0
    for tid, (scope, center, is_museum) in TOURS.items():
        content = psql(f"select tour_content from audio_tours where id={tid}")
        stops = parse_stops(content)
        bbox = None
        try:
            bbox = _geocode_scope_bbox(scope)
        except Exception:
            bbox = None

        # Resolve the museum building pin once, as generation does.
        vf = None
        if is_museum:
            mb = wll.lookup("Belvedere Museum", scope=scope, scope_center=center,
                            scope_bbox=bbox, tour_language="en", use_cache=False)
            if mb:
                vf = (float(mb[0]), float(mb[1]))

        # BEFORE distances (shipped pins).
        qids = GROUND_TRUTH_QID.get(tid, {})

        def authority_for(name):
            if is_museum:
                return p625(qids.get("*building"))
            q = qids.get(name)
            return p625(q) if q else None

        before = []
        for st in stops:
            auth = authority_for(st["name"])
            d = _hav_m(st["coordinate"], auth) if (st["coordinate"] and auth) else None
            before.append(d)

        # APPLY the LOCAL-813 snap.
        poi_list = [{"name": st["name"],
                     "coordinates": (f"{st['coordinate'][0]},{st['coordinate'][1]}"
                                     if st["coordinate"] else "")}
                    for st in stops]
        pin_snap.snap_poi_coordinates(
            poi_list, scope=scope, scope_center=center, scope_bbox=bbox,
            tour_language="en", venue_fallback_coordinate=vf,
            log=lambda m: None)

        # AFTER distances (snapped pins) vs the SAME authority.
        print("=" * 100)
        print(f"TOUR {tid} — {scope}  (museum={is_museum})")
        print("=" * 100)
        print(f"  {'stop':38s} {'before':>9s} {'after':>9s}  authority")
        n_bf = n_af = 0
        for i, st in enumerate(stops):
            auth = authority_for(st["name"])
            newc = pin_snap._parse_coord(poi_list[i]["coordinates"])
            af = _hav_m(newc, auth) if (newc and auth) else None
            bf = before[i]
            if auth is None:
                authnote = "(no P625 authority — e.g. gate/street)"
            else:
                authnote = f"{auth[0]:.5f},{auth[1]:.5f}"
            bfs = f"{bf:7.0f}m" if bf is not None else "   —  "
            afs = f"{af:7.0f}m" if af is not None else "   —  "
            bffail = (bf is not None and bf > 150)
            affail = (af is not None and af > 150)
            if bf is not None:
                n_bf += 1 if bffail else 0
            if af is not None:
                n_af += 1 if affail else 0
            flag = ""
            if bffail and not affail:
                flag = "  FIXED"
            elif affail:
                flag = "  STILL>150"
            print(f"  {st['name']:38s} {bfs:>9s} {afs:>9s}  {authnote}{flag}")
        measured = sum(1 for b in before if b is not None)
        print(f"  -> before: {n_bf}/{measured} stops >150m ; "
              f"after: {n_af}/{measured} stops >150m\n")
        grand_before_fail += n_bf
        grand_after_fail += n_af
        grand_total += measured
    print("=" * 100)
    print(f"GRAND TOTAL (measured stops with a P625 authority): {grand_total}")
    print(f"  pins >150m BEFORE snap: {grand_before_fail}")
    print(f"  pins >150m AFTER  snap: {grand_after_fail}")


if __name__ == "__main__":
    main()
