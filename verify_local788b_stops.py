"""verify_local788b_stops.py — verify each LOCAL-788B delivered stop against
Serper Places (name, address, km from scope centre). Read-only; metered.

Confirms the delivered stops are REAL map places in scope and that the two field
fakes (Sultan's Kebab, Cafe Jaffa) are NOT on the map in West Roxbury. Uses the
same places_search the generator uses. Budget-safe: one Serper query per stop
($0.001 each), ~11 queries total (<$0.02), well inside the task headroom.
"""
import math
import os

import places_search as ps
from stop_existence_gate import _geocode_scope_center, _geocode_scope_bbox

os.environ.setdefault("SERP_PROVIDER", "serper")


def km(a, b):
    if not a or not b:
        return float("nan")
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0]); dl = math.radians(b[1] - a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


CASES = [
    ("West Roxbury, MA",
     ["Stardust", "Bread Thyme", "Al Wadi"],
     ["Sultan's Kebab", "Cafe Jaffa"]),
    ("Jamaica Plain, Boston",
     ["Jamaica Plain Coffee", "Ula Cafe", "Tres Gatos"], []),
    ("Mui Ne, Vietnam",
     ["Vietnam Kiteboarding School", "Surfpoint Kiteboarding School",
      "C2Sky Kite Center"], []),
]

nq = 0
for scope, present, absent in CASES:
    print(f"\n=== SCOPE: {scope} ===", flush=True)
    center = _geocode_scope_center(scope)
    bbox = _geocode_scope_bbox(scope)
    print(f"  scope centre: {center}", flush=True)
    for name in present:
        recs = ps.places_search(name, scope=scope, scope_center=center,
                                scope_bbox=bbox, limit=5)
        nq += 1
        hit = None
        nl = name.lower()
        toks = [t for t in nl.replace("'", " ").split() if len(t) >= 3]
        for r in recs:
            rn = (r.get("name") or r.get("display_name") or "").lower()
            if sum(1 for t in toks if t in rn) >= max(1, len(toks)//2):
                hit = r; break
        if hit:
            try:
                c = (float(hit["lat"]), float(hit["lon"]))
            except Exception:
                c = None
            d = km(center, c) if (center and c) else float("nan")
            print(f"  [ON MAP] {name!r} -> {hit.get('name')!r} | "
                  f"{hit.get('display_name','')[:70]} | {d:.2f} km from centre",
                  flush=True)
        else:
            print(f"  [NOT FOUND in first {len(recs)} recs] {name!r} "
                  f"(recs: {[x.get('name') for x in recs][:5]})", flush=True)
    for name in absent:
        recs = ps.places_search(name, scope=scope, scope_center=center,
                                scope_bbox=bbox, limit=5)
        nq += 1
        nl = name.lower()
        toks = [t for t in nl.replace("'", " ").split() if len(t) >= 3]
        found = False
        for r in recs:
            rn = (r.get("name") or r.get("display_name") or "").lower()
            if sum(1 for t in toks if t in rn) >= max(1, len(toks)//2):
                found = True; break
        tag = "STILL ON MAP (BAD)" if found else "correctly NOT on map"
        print(f"  [FAKE] {name!r} -> {tag} (recs: {[x.get('name') for x in recs][:5]})",
              flush=True)

print(f"\n[verify] Serper queries issued: {nq}  (~${nq*0.001:.3f})", flush=True)
