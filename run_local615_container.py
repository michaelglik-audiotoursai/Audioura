#!/usr/bin/env python3
"""run_local615_container.py — LOCAL-615 live acceptance (ISOLATED container).

Runs ONE never-seen museum — Museo Nacional de Escultura, Valladolid, Spain —
through the REAL generation path with the LOCAL-615 branch code mounted over /app,
3 stops, metered + capped at $1.00 (TEST_GEMINI_MAX_USD, all providers combined,
via tests/live_run_meter.py).

It prints, for the four LOCAL-615 fixes:
  item 1 — the "No duplicated paragraph" QA check result + a direct dedupe probe;
  item 2 — whether Stop 1 still says "Check opening hours and admission on <domain>"
           and whether the preflight reported hours;
  item 3 — _LAST_GENERATION_COST['tour_total_cost'] vs the OpenAI-only total_cost,
           and the per-provider breakdown;
  item 4 — the preflight line in the breakdown (calls/queries/$), proving it is
           metered rather than calls:0.
It then prints STOP 1 IN FULL, the BLOCKER-3 content-QA lines, and the cost/time.
The TEST-* cost_ledger row is written on exit by live_run_meter.auto_meter.

Usage (inside the isolated container):
    python3 run_local615_container.py
"""

# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os613  # noqa: E402
import sys as _sys613  # noqa: E402
_sys613.path.insert(0, _os613.path.join(
    _os613.path.dirname(_os613.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter  # noqa: E402
    _live_run_meter.auto_meter('LOCAL-615')
except Exception as _meter_err:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force a FRESH tour (item 1/2/3/4)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket cap

LOCATION = 'Museo Nacional de Escultura, Valladolid, Spain'
STOPS = 3
OUT = '/app/tours/LOCAL615_VALLADOLID_RUN.txt'

print("=== LOCAL-615 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

# ── cost record ──────────────────────────────────────────────────────────────
try:
    from generate_tour_text import _LAST_GENERATION_COST, _LAST_VENUE_PREFLIGHT
    _cost = dict(_LAST_GENERATION_COST or {})
except Exception:
    _cost, _LAST_VENUE_PREFLIGHT = {}, {}

print("\n================ RESULT ================", flush=True)
if not text:
    print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"  evidence  : {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception as e:
        print(f"  evidence unavailable: {e}", flush=True)
    raise SystemExit(0)

titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)
for m in titles:
    print(f"   {m.strip()[:120]}", flush=True)

# ── item 1: duplicated-paragraph check ─────────────────────────────────────────
print("\n================ LOCAL-615 item 1 — No duplicated paragraph ================", flush=True)
try:
    from paragraph_dedupe import find_duplicate_paragraphs
    _dupes = find_duplicate_paragraphs(text)
    print(f"  duplicate paragraphs (>=80 chars) in delivered text: {len(_dupes)}", flush=True)
    for d in _dupes[:2]:
        print(f"    DUP: {d[:90]!r}", flush=True)
    print(f"  item 1 {'PASS (none)' if not _dupes else 'FAIL'}", flush=True)
except Exception as e:
    print(f"  item 1 probe error: {e}", flush=True)

# ── item 2: preflight hours folded, no 'check ... on <domain>' ─────────────────
print("\n================ LOCAL-615 item 2 — preflight hours on the fresh path ================", flush=True)
_check_hours = re.search(r'(?i)Check opening hours and admission on\b[^\n]*?before you go', text)
_pf = _LAST_VENUE_PREFLIGHT or {}
print(f"  preflight ran: {bool(_pf) and not _pf.get('skipped') and not _pf.get('error')}", flush=True)
print(f"  preflight hours present: {'y' if _pf.get('hours') else 'n'}  "
      f"admission: {'y' if _pf.get('admission') else 'n'}", flush=True)
print(f"  'Check opening hours ... on <domain>' still in tour: {bool(_check_hours)}", flush=True)
if _pf.get('hours') and _check_hours:
    print("  item 2 FAIL — preflight has hours but the fallback shipped", flush=True)
else:
    print("  item 2 PASS", flush=True)

# ── item 3 + 4: cost total sums all providers; preflight metered ───────────────
print("\n================ LOCAL-615 item 3 — our_cost_usd sums all providers ================", flush=True)
_bd = _cost.get('breakdown', {}) or {}
def _usd(x):
    try:
        return float(x if not isinstance(x, dict) else x.get('usd', 0.0) or 0.0)
    except Exception:
        return 0.0
_openai = _usd(_bd.get('openai', _bd.get('llm', 0.0)))
_grounding = _usd(_bd.get('gemini_grounding', _bd.get('grounding', 0.0)))
_gtok = _usd(_bd.get('gemini_tokens', 0.0))
_serper = _usd(_bd.get('serper', _bd.get('search', 0.0)))
_tts = _usd(_bd.get('tts', 0.0))
_pf_usd = _usd(_bd.get('preflight', 0.0))
_tour_total = float(_cost.get('tour_total_cost', 0.0) or 0.0)
print(f"  total_cost (OpenAI only)   : ${_openai:.4f}", flush=True)
print(f"  gemini_grounding           : ${_grounding:.4f}", flush=True)
print(f"  gemini_tokens              : ${_gtok:.4f}", flush=True)
print(f"  serper                     : ${_serper:.4f}", flush=True)
print(f"  tts                        : ${_tts:.4f}", flush=True)
print(f"  preflight                  : ${_pf_usd:.4f}", flush=True)
print(f"  tour_total_cost (our_cost) : ${_tour_total:.4f}", flush=True)
_sum = _openai + _grounding + _gtok + _serper + _tts + _pf_usd
print(f"  sum of provider lines      : ${_sum:.4f}", flush=True)
print(f"  item 3 {'PASS' if _tour_total >= _openai and abs(_tour_total - _sum) < 0.02 else 'CHECK'} "
      f"(tour_total >= OpenAI-only and ~= provider sum)", flush=True)

print("\n================ LOCAL-615 item 4 — preflight metered ================", flush=True)
_pf_line = _bd.get('preflight', {}) if isinstance(_bd.get('preflight'), dict) else {}
print(f"  breakdown.preflight = {_pf_line}", flush=True)
print(f"  item 4 {'PASS (line present)' if 'preflight' in _bd else 'CHECK'}", flush=True)

# ── STOP 1 IN FULL ─────────────────────────────────────────────────────────────
print("\n================ STOP 1 (in full) ================", flush=True)
_s1 = re.search(r'(Stop\s+1:.*?)(?=\nStop\s+2:|\Z)', text, re.DOTALL)
print((_s1.group(1).strip() if _s1 else '(Stop 1 not found)'), flush=True)

# ── BLOCKER 3 content-QA gate (mirror the service wiring) ──────────────────────
print("\n================ BLOCKER 3 (content-QA factual gate) ================", flush=True)
try:
    import content_qa_runner
    _loc_parts = LOCATION.split(',')
    _venue_name_raw = _loc_parts[0].strip()
    _city_raw = _loc_parts[1].strip() if len(_loc_parts) > 1 else ''
    _region_raw = _loc_parts[2].strip() if len(_loc_parts) > 2 else ''
    _venue_tokens = set(w.lower() for w in re.split(r'[\s\-]+', _venue_name_raw) if len(w) >= 3)
    _vctx = {'venue_tokens': _venue_tokens, 'city': _city_raw,
             'region': _region_raw, 'artist': ''}
    content_qa_runner.PASS_COUNT = 0
    content_qa_runner.FAIL_COUNT = 0
    content_qa_runner.FACTUAL_FAIL_COUNT = 0
    try:
        content_qa_runner.run_qa(text, venue_context=_vctx)
    except SystemExit:
        pass
    print(f"  PASS checks         : {content_qa_runner.PASS_COUNT}", flush=True)
    print(f"  style FAIL checks   : {content_qa_runner.FAIL_COUNT}", flush=True)
    print(f"  FACTUAL FAIL checks : {content_qa_runner.FACTUAL_FAIL_COUNT}", flush=True)
except Exception as _qa_e:
    print(f"  content-QA gate error: {_qa_e}", flush=True)

print(f"\nCOST/TIME: tour_total_cost=${_tour_total:.4f}  "
      f"cache_hit={_cost.get('cache_hit', False)}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
