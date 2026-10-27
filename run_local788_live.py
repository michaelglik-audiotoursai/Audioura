#!/usr/bin/env python3
"""run_local788_live.py — LOCAL-788 live proof (Overpass forced 502).

Exercises the LOCAL-788 code against the REAL paid APIs (Serper Places via the
metered serper_meter door), with Overpass forced to a dead URL so the mirror +
Serper fallback must engage. No full stack, no DB write required, and it NEVER
touches the shared audioura-* containers — it drives the changed code paths
in-process so the live run measures THIS worktree.

Proves, live:
  * item 3 — Overpass 502 → mirror tried → Serper fallback; candidate list
    non-empty (overpass_fallback.query_pois_with_fallback).
  * item 4 — the dining replenish escalation ladder (Serper Places + ll + the
    LOCAL-786 bbox) returns the real West Roxbury Middle-Eastern places; none in
    Norwood (stop_existence_gate.replenish_with_escalation).
  * item 1 — a pool containing Byblos (Norwood) + Stardust for a West Roxbury
    request: Byblos rejected, Stardust kept (places_search.row_in_scope using the
    live scope geocode).

Spend cap: TEST_GEMINI_MAX_USD (set to 1.50 for the WHOLE task). The Serper
Places calls here are a handful at ~$0.002 each — a few cents total.

Run (own env, shared containers untouched):
    SERP_API_KEY=… SERP_PROVIDER=serper \
    OVERPASS_URL=http://127.0.0.1:1/dead \
    OVERPASS_MIRRORS=http://127.0.0.1:1/dead2 \
    TEST_GEMINI_MAX_USD=1.50 \
    python3 run_local788_live.py
"""
import os
import sys

# Force Overpass to a dead URL BEFORE importing the Overpass client, so the
# module-level _OVERPASS_URL/_OVERPASS_MIRRORS pick it up (item 3 outage proof).
os.environ.setdefault("OVERPASS_URL", "http://127.0.0.1:1/dead-primary")
os.environ.setdefault("OVERPASS_MIRRORS",
                      "http://127.0.0.1:1/dead-mirror-1,http://127.0.0.1:1/dead-mirror-2")
os.environ.setdefault("TEST_GEMINI_MAX_USD", "1.50")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

WR = "West Roxbury, MA"
_NORWOOD_FORBIDDEN = ("norwood",)


def _fail(msg):
    print(f"  ✗ FAIL: {msg}")
    return False


def main():
    if not (os.environ.get("SERP_API_KEY") and
            os.environ.get("SERP_PROVIDER", "").lower() == "serper"):
        print("SERP_API_KEY / SERP_PROVIDER=serper not set — cannot run the live "
              "Serper proof. Set them and re-run.")
        return 2

    import places_search as ps
    import stop_existence_gate as gate
    import overpass_fallback as ofb
    import osm_venue_facts as ovf

    print("LOCAL-788 LIVE PROOF — Overpass forced 502/dead")
    print(f"  OVERPASS_URL     = {ovf._OVERPASS_URL}")
    print(f"  OVERPASS_MIRRORS = {ovf._OVERPASS_MIRRORS}")
    print(f"  cap TEST_GEMINI_MAX_USD = ${os.environ['TEST_GEMINI_MAX_USD']}")

    # Install the combined-provider spend cap (hard stop at the grounding counter).
    meter = None
    try:
        from live_run_meter import LiveRunMeter
        meter = LiveRunMeter("LOCAL-788")
    except Exception as e:
        print(f"  (meter unavailable, continuing without ledger row: {e})")

    ps.clear_cache()
    ok = True

    # The scope geocode the new-lookup path uses (live Nominatim via the gate).
    try:
        center = gate._geocode_scope_center(WR)
        bbox = gate._geocode_scope_bbox(WR)
    except Exception as e:
        center, bbox = None, None
        print(f"  scope geocode failed ({e}); continuing with query-text binding")
    print(f"  scope centre = {center}  bbox = {bbox}")

    # ── item 4 — dining replenish via the escalation ladder (Serper real) ─────
    print("\n[item 4] replenish_with_escalation('dining', 'middle eastern "
          "restaurants', 'West Roxbury, MA') — Overpass is dead, Serper must rescue")
    cands = gate.replenish_with_escalation(
        "dining", "middle eastern restaurants", WR, 2,
        cuisine="middle eastern",
        request_text="middle eastern restaurants near me, West Roxbury, MA")
    names = [c.get("name", "") for c in cands]
    print(f"  ladder returned {len(cands)}: {names}")
    for c in cands:
        print(f"    - {c.get('name')} @ {c.get('coordinates')} "
              f"[{c.get('evidence','')[:60]}]")
    if not cands:
        ok = _fail("ladder returned NO candidates — the candidate list shrank")
    if any(any(f in (c.get("name", "") + " " + str(c.get("address", ""))).lower()
               for f in _NORWOOD_FORBIDDEN) for c in cands):
        ok = _fail("a Norwood place was returned for a West Roxbury request")

    # ── item 3 — Overpass→Serper fallback keeps the candidate list ────────────
    print("\n[item 3] overpass_fallback.query_pois_with_fallback — Overpass dead "
          "→ Serper fallback")
    serper_q = "middle eastern restaurants West Roxbury MA"
    overpass_q = ('[out:json][timeout:15];node["amenity"="restaurant"]'
                  '(around:2500,42.2843,-71.1627);out tags;')
    pois = ofb.query_pois_with_fallback(
        overpass_query=overpass_q, serper_query=serper_q, scope=WR,
        scope_center=center, scope_bbox=bbox, limit=10,
        context="local788-live")
    print(f"  fallback returned {len(pois)} ({[p['name'] for p in pois]})")
    if not pois:
        ok = _fail("Overpass-down fallback returned an empty candidate list")
    elif not all(p.get("source") == "serper" for p in pois):
        print("  (note: some candidates came from a live mirror, not Serper — "
              "still a non-empty list, which is the contract)")

    # ── item 1 — pool re-validation drops Byblos Norwood, keeps Stardust ──────
    print("\n[item 1] row_in_scope on a pool of {Stardust (WR), Byblos (Norwood)} "
          "for a West Roxbury request")
    pool = [
        {"title": "Stardust", "coordinates": "42.28744, -71.15047",
         "address": "1753 Centre St, West Roxbury, MA"},
        {"title": "Byblos Restaurant", "coordinates": "42.1945, -71.1997",
         "address": "678 Washington St, Norwood, MA 02062"},
    ]
    kept = []
    for r in pool:
        keep, reason, dist = ps.row_in_scope(
            r["coordinates"], r["address"], WR,
            scope_center=center, scope_bbox=bbox)
        _d = "?" if dist == float("inf") else f"{dist:.1f}km"
        print(f"    {r['title']:<18} keep={keep!s:<5} {_d} {reason}")
        if keep:
            kept.append(r["title"])
    if "Byblos Restaurant" in kept:
        ok = _fail("Byblos (Norwood) was NOT rejected for a West Roxbury request")
    if "Stardust" not in kept:
        ok = _fail("Stardust (West Roxbury) was wrongly rejected")

    # ── spend report ──────────────────────────────────────────────────────────
    if meter is not None:
        try:
            meter.add_generation(ps) if hasattr(meter, "add_generation") else None
        except Exception:
            pass
        try:
            print("\n" + meter.summary())
            meter.record()
        except Exception as e:
            print(f"  (meter record skipped: {e})")
        finally:
            try:
                meter.uninstall()
            except Exception:
                pass

    print("\n" + ("ALL LIVE CHECKS PASSED" if ok else "LIVE CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
