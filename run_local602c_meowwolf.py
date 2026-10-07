"""run_local602c_meowwolf.py — LOCAL-602C r3 live acceptance (ISOLATED container).

Runs `Meow Wolf, Santa Fe, NM`, 5 stops, cap $1.50, through the REAL generation
path with VENUE_PREFLIGHT enabled. Meow Wolf Santa Fe is the open chain/SPA venue
whose r2 live run shipped two non-exhibit pages a block-list let through:

    Stop 1: Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out   (event)
    Stop 2: Santa Fe City Guide: Top Attractions & Restaurants …  (blog/guide)

r3 replaced the block-list with an ALLOW-LIST (a stop must be POSITIVELY an
exhibit). This run captures the acceptance evidence: the stop titles each with
its source URL, and the Tour total under the $1.50 cap. The stop pool uses the
DISPOSABLE Postgres passed via DATABASE_URL; no audioura-* container is touched.

Usage (inside the isolated container local602c-gen):
    python3 run_local602c_meowwolf.py
"""
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # r3 ticket cap $1.50
os.environ['LOCAL603_PREFLIGHT'] = '1'            # VENUE_PREFLIGHT enabled

LOCATION = os.environ.get('LOCAL602C_LOCATION', 'Meow Wolf, Santa Fe, NM')
STOPS = int(os.environ.get('LOCAL602C_STOPS', '5'))
OUT = os.environ.get('LOCAL602C_OUT', '/app/tours/LOCAL602C_MEOWWOLF_RUN.txt')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

GIT_SHA = (open('/app/.git_sha').read().strip()
           if os.path.exists('/app/.git_sha') else '?')

print("=== LOCAL-602C r3 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)
print(f"preflight: ENABLED (LOCAL603_PREFLIGHT=1)", flush=True)
print(f"git_sha  : {GIT_SHA}", flush=True)

# ---- Measure the preflight in isolation first (fresh), for the evidence line ----
try:
    import venue_preflight as _vpf
    import story_leads
    _city = ','.join(p.strip() for p in LOCATION.split(',')[1:]).strip()
    _venue = LOCATION.split(',')[0].strip()
    try:
        story_leads.reset_grounding_requests()
    except Exception:
        pass
    _pf = _vpf.safe_preflight(_venue, _city, use_cache=False)
    print("\n--- PREFLIGHT (measured, isolated) ---", flush=True)
    print(f"  status     : {_pf.get('status')}", flush=True)
    print(f"  hours      : {_pf.get('hours') or '(none)'}", flush=True)
    print(f"  admission  : {_pf.get('admission') or '(none)'}", flush=True)
    print(f"  highlights : {len(_pf.get('current_exhibitions_or_highlights') or [])}", flush=True)
    _gate = _vpf.gate(_venue, _city, _pf)
    if _gate:
        print(f"  GATE: {_gate['error_code']} — {_gate['message']}", flush=True)
        print("  (venue reported closed — pick another open venue and rerun)", flush=True)
except Exception as _pf_e:
    print(f"  preflight probe error (non-fatal): {_pf_e}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

try:
    from generate_tour_text import _LAST_GENERATION_COST
    _cost = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
    _tour_total = (_LAST_GENERATION_COST or {}).get('tour_total_cost', _cost)
    _cache_hit = (_LAST_GENERATION_COST or {}).get('cache_hit', False)
except Exception:
    _cost = _tour_total = 0.0
    _cache_hit = False

for _attr in ('_LAST_VERIFICATION_TIER', '_LAST_TOUR_KIND', '_LAST_SITE_FIRST_SOURCES'):
    try:
        globals()[_attr] = getattr(__import__('generate_tour_text'), _attr)
    except Exception:
        globals()[_attr] = '' if _attr != '_LAST_SITE_FIRST_SOURCES' else []

print("\n================ RESULT ================", flush=True)
print(f"TIER: {_LAST_VERIFICATION_TIER}   TOUR_KIND: {_LAST_TOUR_KIND}", flush=True)

if not text:
    print(f"OUTCOME: NO TOUR TEXT (clean-fail or block) after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"  evidence  : {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception as e:
        print(f"  evidence unavailable: {e}", flush=True)
else:
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)

    # ---- Stop titles, each with its source URL (the r3 allow-list evidence) ----
    print("\nSTOP TITLES + SOURCE URLS:", flush=True)
    _src_by_name = {s['name'].strip().lower(): s for s in (_LAST_SITE_FIRST_SOURCES or [])}
    for _t in titles:
        _t = _t.strip()
        _name = re.sub(r'(?i)^\s*stop\s+\d+\s*[:\-]\s*', '', _t).strip()
        _rec = _src_by_name.get(_name.lower())
        print(f"   {_t[:110]}", flush=True)
        if _rec:
            print(f"        source: {_rec['source_url']}  [{_rec.get('kind','')}/{_rec.get('status','')}]", flush=True)

    if _LAST_SITE_FIRST_SOURCES:
        print("\nSITE-FIRST SOURCES (recorded during generation):", flush=True)
        for s in _LAST_SITE_FIRST_SOURCES:
            print(f"   - {s['name']}  →  {s['source_url']}  [{s.get('kind','')}/{s.get('status','')}]", flush=True)

    # ---- Address vs coordinates ----
    print("\n================ ADDRESS vs COORDINATES ================", flush=True)
    for _lbl, _rx in (("Address", r'(?mi)^Address:\s*(.+?)\s*$'),
                      ("Coordinates", r'(?mi)^Coordinates:\s*(.+?)\s*$')):
        for _v in re.findall(_rx, text):
            print(f"  {_lbl}: {_v}", flush=True)

    # ---- Stop 1 opening section ----
    print("\n================ STOP 1 (opening section, full) ================", flush=True)
    _m1 = re.search(r'(?ms)^\s*Stop\s+1\s*[:\-].*?(?=^\s*Stop\s+2\s*[:\-]|\Z)', text)
    print(_m1.group(0).strip() if _m1 else "(Stop 1 not found)", flush=True)

print(f"\nTour total: ${_tour_total:.4f}  (OpenAI=${_cost:.4f})  cache_hit={_cache_hit}  wall={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
