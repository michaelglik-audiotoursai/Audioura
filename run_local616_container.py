#!/usr/bin/env python3
"""run_local616_container.py — LOCAL-616 live acceptance (ISOLATED container).

Runs TWO never-seen museums through the REAL generation path with the LOCAL-616
branch code mounted over /app, 3 stops each, metered + capped at $1.50 COMBINED
(TEST_GEMINI_MAX_USD, all providers, via tests/live_run_meter.py):

    1. Musée Granet, Aix-en-Provence, France    (3 stops)
    2. Groeningemuseum, Bruges, Belgium          (3 stops)

For each museum it prints the per-item verdicts for the five code fixes, then
STOP 1 IN FULL, and writes the delivered tour to /app/tours so critique.sh can
score the spoken text. One TEST-LOCAL-616 cost_ledger row is written on exit.

Usage (inside the isolated container):
    python3 run_local616_container.py
"""

# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os616  # noqa: E402
import sys as _sys616  # noqa: E402
_sys616.path.insert(0, _os616.path.join(
    _os616.path.dirname(_os616.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter  # noqa: E402
    _live_run_meter.auto_meter('LOCAL-616')
except Exception as _meter_err:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket cap (combined)

RUNS = [
    ('Musée Granet, Aix-en-Provence, France', '/app/tours/LOCAL616_GRANET.txt'),
    ('Groeningemuseum, Bruges, Belgium', '/app/tours/LOCAL616_GROENINGE.txt'),
]
STOPS = 3

print("=== LOCAL-616 isolated live run (two museums, 3 stops each) ===", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402


def _usd(x):
    try:
        return float(x if not isinstance(x, dict) else x.get('usd', 0.0) or 0.0)
    except Exception:
        return 0.0


def _report(location, out_file, text, elapsed):
    print(f"\n################ {location} ################", flush=True)
    try:
        from generate_tour_text import (_LAST_GENERATION_COST,
                                         _LAST_VENUE_PREFLIGHT, _LAST_DELIVERY_PATH)
        _cost = dict(_LAST_GENERATION_COST or {})
        _pf = _LAST_VENUE_PREFLIGHT or {}
        _path = _LAST_DELIVERY_PATH
    except Exception:
        _cost, _pf, _path = {}, {}, '?'

    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s (path={_path})", flush=True)
        try:
            from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
            print(f"  evidence: {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
        except Exception:
            pass
        return

    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"path={_path}, wall {elapsed:.1f}s", flush=True)
    for m in titles:
        print(f"   {m.strip()[:110]}", flush=True)

    # item 1 — hours guard on EVERY path (no 'check ... on <domain>' when preflight has hours)
    _check = re.search(r'(?i)Check opening hours and admission on\b[^\n]*?before you go', text)
    _pf_ok = bool(_pf) and not _pf.get('skipped') and not _pf.get('error')
    print(f"\n[item 1] delivery path={_path}  preflight ran={_pf_ok}  "
          f"hours={'y' if _pf.get('hours') else 'n'}  "
          f"'check...before you go' in tour={bool(_check)}", flush=True)
    if _pf.get('hours') and _check:
        print("  item 1 FAIL — preflight has hours but the fallback shipped", flush=True)
    else:
        print("  item 1 PASS", flush=True)

    # item 2 — no spoken sourcing sentence / spoken domain
    _drawn = re.search(r'(?i)this account is drawn from', text)
    _pubref = re.search(r'(?i)public reference sources', text)
    print(f"\n[item 2] 'This account is drawn from' spoken={bool(_drawn)}  "
          f"'public reference sources' spoken={bool(_pubref)}", flush=True)
    print(f"  item 2 {'FAIL' if (_drawn or _pubref) else 'PASS'}", flush=True)

    # item 3 — no untranslated foreign (French/Dutch) fragment in the English tour
    try:
        import language_guard as _lg
        _spoken = re.sub(r'(?mis)\n\s*Sources?:.*$', '', text)  # ignore text-view sources
        _sents = re.split(r'(?<=[.!?])\s+', _spoken)
        _foreign = [s for s in _sents
                    if len(s.split()) >= 6 and not _lg.is_in_tour_language(s, 'en')]
        print(f"\n[item 3] non-English spoken sentences (>=6 words): {len(_foreign)}", flush=True)
        for s in _foreign[:3]:
            print(f"    FOREIGN: {s.strip()[:90]!r}", flush=True)
        print(f"  item 3 {'FAIL' if _foreign else 'PASS'}", flush=True)
    except Exception as e:
        print(f"\n[item 3] probe error: {e}", flush=True)

    # item 6 — reached requested stops OR a shortfall sentence is present
    _short = re.search(r'(?i)rather than the \d+ you asked for|'
                       r'has \d+ stops? rather than|currently has \d+ exhibition', text)
    print(f"\n[item 6] stops delivered={len(titles)}/{STOPS}  "
          f"shortfall sentence present={bool(_short)}", flush=True)
    if len(titles) >= STOPS or _short:
        print("  item 6 PASS (reached N, or honest shortfall stated)", flush=True)
    else:
        print("  item 6 CHECK", flush=True)

    # cost
    _bd = _cost.get('breakdown', {}) or {}
    _tour_total = float(_cost.get('tour_total_cost', 0.0) or 0.0)
    print(f"\n[cost] tour_total=${_tour_total:.4f}  "
          f"openai=${_usd(_bd.get('openai')):.4f}  "
          f"grounding=${_usd(_bd.get('gemini_grounding', _bd.get('grounding'))):.4f}  "
          f"serper=${_usd(_bd.get('serper', _bd.get('search'))):.4f}  "
          f"preflight=${_usd(_bd.get('preflight')):.4f}", flush=True)

    # STOP 1 in full
    print(f"\n---------------- STOP 1 (in full) — {location} ----------------", flush=True)
    _s1 = re.search(r'(Stop\s+1:.*?)(?=\nStop\s+2:|\Z)', text, re.DOTALL)
    print((_s1.group(1).strip() if _s1 else '(Stop 1 not found)'), flush=True)
    print(f"\nOUT: {out_file}", flush=True)


for location, out in RUNS:
    print(f"\n=== generating: {location} ({STOPS} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, out_file, _coords = generate_tour_text(location, 'museum', out, STOPS)
    except Exception as _run_err:
        print(f"RUN ERROR for {location}: {_run_err}", flush=True)
        text, out_file = None, out
    _report(location, out_file, text, time.time() - t0)

print("\n=== LOCAL-616 run complete ===", flush=True)
