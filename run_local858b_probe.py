"""run_local858b_probe.py — LOCAL-858B cheap second-authority probe.

The full 2-pass tour run proved PASS 1 (Wikidata reachable: Ben Thanh 0 m, Opera
0 m). This probe proves the BLOCKED pass cheaply (≈ 2 Serper /places calls,
≈ $0.004) WITHOUT a full tour generation: with Wikidata blocked, the SECOND
authority (Serper /places → Nominatim) must resolve BOTH requested landmarks,
name-matched and in-scope, within 150 m of the real pin.

Metered + budget-capped by the harness (TASK_BUDGET_ID=LOCAL-858B). No tour text,
no DB write.
"""
import math
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

# Cloud-like: Wikidata blocked, live lookup on (so the second authority's live
# Serper path fires).
_os.environ['LANDMARK_LIVE_LOOKUP'] = '1'
_os.environ['LANDMARK_WIKIDATA_BLOCKED'] = '1'
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')

REAL = {
    'Ben Thanh Market': (10.772521, 106.698019),
    'Saigon Opera House': (10.776390, 106.702780),
}
HCMC_CENTER = (10.7769, 106.7009)
HCMC_BBOX = [10.70, 10.85, 106.60, 106.75]  # rough HCMC District-1 box


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def main():
    print("=== LOCAL-858B second-authority probe (Wikidata BLOCKED) ===", flush=True)
    print(f"serper key present: "
          f"{bool(_os.environ.get('SERP_API_KEY') or _os.environ.get('SERPER_API_KEY'))}",
          flush=True)
    # Confirm Wikidata really is blocked on this path.
    import wikidata_landmark_lookup as wl
    wd = wl.lookup('Ben Thanh Market', scope='Ho Chi Minh City',
                   scope_center=HCMC_CENTER, scope_bbox=HCMC_BBOX,
                   tour_language='en', use_cache=False)
    print(f"  Wikidata lookup (should be None when blocked): {wd}", flush=True)

    from landmark_second_authority import lookup_second_authority as _2nd
    all_ok = True
    for name, real in REAL.items():
        hit = _2nd(name, scope='Ho Chi Minh City', scope_center=HCMC_CENTER,
                   scope_bbox=HCMC_BBOX, use_cache=False)
        if not hit:
            print(f"  [{name}] second authority: NO HIT -> FAIL", flush=True)
            all_ok = False
            continue
        d = _hav_m((hit[0], hit[1]), real)
        ok = d <= 150.0
        all_ok = all_ok and ok
        print(f"  [{name}] second authority: ({hit[0]:.6f},{hit[1]:.6f}) "
              f"src={hit[2]}  {d:.0f} m from real -> {'PASS' if ok else 'FAIL'}",
              flush=True)
    print(f"=== LOCAL-858B PROBE OVERALL: {'PASS' if all_ok else 'FAIL'} ===",
          flush=True)


if __name__ == '__main__':
    main()
