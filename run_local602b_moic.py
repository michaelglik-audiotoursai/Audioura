"""run_local602b_moic.py — LOCAL-602B r2 live acceptance (ISOLATED container).

Runs `Museum of Ice Cream, New York, NY`, 5 stops, cap $2, through the REAL
generation path with VENUE_PREFLIGHT enabled. Museum of Ice Cream is an open
chain/SPA venue — the next open case after WNDR (closed) that the r1 defects
would hit. Captures the r2 acceptance evidence:

  * the preflight status/hours/admission;
  * the stop titles, each with its source URL (junk-stop filter proven);
  * the coordinates vs the address (300 m address-verification proven);
  * Stop 1's opening section (About describes the MUSEUM; <=1 'check the website');
  * the spoken text's last 15 lines (no URL / no Sources — item 9);
  * no 'From X to X' recap on a short tour (item 12);
  * Tour total (< $2 cap).

The stop pool uses the DISPOSABLE Postgres passed via DATABASE_URL; no audioura-*
container is touched. Usage (inside the isolated container local602b-gen):
    python3 run_local602b_moic.py
"""
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '2.00'        # ticket cap $2
os.environ['LOCAL603_PREFLIGHT'] = '1'            # VENUE_PREFLIGHT enabled

LOCATION = os.environ.get('LOCAL602B_LOCATION', 'Museum of Ice Cream, New York, NY')
STOPS = int(os.environ.get('LOCAL602B_STOPS', '5'))
OUT = os.environ.get('LOCAL602B_OUT', '/app/tours/LOCAL602B_MOIC_RUN.txt')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

GIT_SHA = (open('/app/.git_sha').read().strip()
           if os.path.exists('/app/.git_sha') else '?')

print("=== LOCAL-602B r2 isolated live run ===", flush=True)
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

    # ---- Stop titles, each with its source URL ----
    print("\nSTOP TITLES + SOURCE URLS:", flush=True)
    _src_by_name = {s['name'].strip().lower(): s for s in (_LAST_SITE_FIRST_SOURCES or [])}
    for _t in titles:
        _t = _t.strip()
        _name = re.sub(r'(?i)^\s*stop\s+\d+\s*[:\-]\s*', '', _t).strip()
        _rec = _src_by_name.get(_name.lower())
        print(f"   {_t[:100]}", flush=True)
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

    # ---- 'check the website' count + From-X-to-X recap check ----
    print("\n================ D617 item 10 / 12 CHECKS ================", flush=True)
    _ptr = re.findall(r'(?i)(check[^?!]*?before you (?:go|visit)'
                      r'|opening hours? (?:are|were) (?:listed|not listed)'
                      r'|admission prices? (?:are|were) (?:listed|not listed))', text)
    print(f"  'check the website' pointer sentences: {len(_ptr)} (must be <= 1)", flush=True)
    _ft = re.findall(r'(?i)From\s+(.+?)\s+to\s+(.+?),\s*you have followed', text)
    _degenerate = [(a, b) for a, b in _ft
                   if re.sub(r'\s+', ' ', a).strip().lower() == re.sub(r'\s+', ' ', b).strip().lower()]
    print(f"  'From X to X' degenerate recap sentences: {len(_degenerate)} (must be 0)", flush=True)

    # ---- Spoken text (packer output) — scan every audio_*.txt for http/www ----
    print("\n================ SPOKEN TEXT (packer) — URL/Sources scan ================", flush=True)
    try:
        import break_text_to_pois as _pack
        _pack.process_tour_file(out_file)
        # The packer writes the output dir NEXT TO its own module (script_dir),
        # named from the tour file's base name — not under the tour file's dir.
        _pack_script_dir = os.path.dirname(os.path.abspath(_pack.__file__))
        _base = os.path.splitext(os.path.basename(out_file))[0]
        _dir = os.path.join(_pack_script_dir, _base)
        if not os.path.isdir(_dir):
            # Fallback: alongside the tour file.
            _dir = os.path.splitext(out_file)[0]
        _audio = sorted(fn for fn in os.listdir(_dir)
                        if fn.startswith('audio_') and fn.endswith('.txt'))
        _url_hits = 0
        _src_hits = 0
        _last_lines = []
        for fn in _audio:
            with open(os.path.join(_dir, fn), encoding='utf-8') as fh:
                body = fh.read()
            if re.search(r'(?i)(https?://|www\.)', body):
                _url_hits += 1
            if 'Sources' in body:
                _src_hits += 1
        print(f"  audio_*.txt files: {len(_audio)}", flush=True)
        print(f"  files containing http/www : {_url_hits} (must be 0)", flush=True)
        print(f"  files containing 'Sources' : {_src_hits} (must be 0)", flush=True)
        # Last spoken file's last 15 lines (the tour's final spoken text).
        if _audio:
            with open(os.path.join(_dir, _audio[-1]), encoding='utf-8') as fh:
                _lines = [ln for ln in fh.read().splitlines()]
            print("\n  --- last spoken file's last 15 lines ---", flush=True)
            for ln in _lines[-15:]:
                print(f"    {ln}", flush=True)
    except Exception as _pe:
        print(f"  packer scan error: {_pe}", flush=True)

print(f"\nTour total: ${_tour_total:.4f}  (OpenAI=${_cost:.4f})  cache_hit={_cache_hit}  wall={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
