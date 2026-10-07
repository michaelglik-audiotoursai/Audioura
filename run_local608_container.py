#!/usr/bin/env python3
"""run_local608_container.py — LOCAL-608 live acceptance (ISOLATED container).

Runs Harvard Art Museums, Cambridge, MA — museum — 7 stops — through the REAL
generation path with THIS branch mounted over /app, hard cap $1.50. Reports:

  * the BLOCKER 3 content-QA lines (PASS / style-FAIL / FACTUAL-FAIL);
  * any G4 corrective lines (captured from the generation log);
  * a grep over the SPOKEN audio_*.txt text that the modernized parser produces,
    proving no `http` / `www.` / `Sources` reaches the listener (D617);
  * the Tour total cost.

Isolation: STORIED_MODE on, tour-output cache OFF; venue_corpus cache stays ON.
Never touches any audioura-* container — this process runs inside a throwaway
`--rm --name local608-gen` container that only mounts the worktree.

Usage (inside the isolated container):
    python3 run_local608_container.py
"""
import io
import os
import re
import sys
import time
import contextlib

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'   # ticket cap

LOCATION = 'Harvard Art Museums, Cambridge, MA'
STOPS = 7
OUT = '/app/tours/LOCAL608_HARVARD_RUN.txt'

print("=== LOCAL-608 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

# Capture the generation log so we can surface any G4 corrective lines emitted
# by the generate_tour_text pipeline (and, if the service path runs, BLOCKER4c).
_gen_buf = io.StringIO()
t0 = time.time()


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, s):
        for st in self._streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self._streams:
            st.flush()


_real_stdout = sys.stdout
sys.stdout = _Tee(_real_stdout, _gen_buf)
try:
    text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
finally:
    sys.stdout = _real_stdout
elapsed = time.time() - t0
_gen_log = _gen_buf.getvalue()

try:
    from generate_tour_text import _LAST_GENERATION_COST
    _cost = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
    _cache_hit = (_LAST_GENERATION_COST or {}).get('cache_hit', False)
except Exception:
    _cost, _cache_hit = 0.0, False

print("\n================ RESULT ================", flush=True)
if not text:
    print(f"OUTCOME: NO TOUR TEXT (clean-fail or block) after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE, _LAST_TOUR_KIND
        print(f"  tour_kind : {_LAST_TOUR_KIND}", flush=True)
        print(f"  evidence  : {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception as e:
        print(f"  evidence unavailable: {e}", flush=True)
    print(f"\nTour total: ${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
    sys.exit(0)

titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)
for m in titles:
    print(f"   {m.strip()[:120]}", flush=True)

# ---- G4 corrective lines (if the pipeline emitted any) ----
print("\n================ G4 corrective lines ================", flush=True)
_g4_lines = [ln for ln in _gen_log.splitlines()
             if 'G4 corrective' in ln or 'BLOCKER4c] G4' in ln]
if _g4_lines:
    for ln in _g4_lines:
        print(f"   {ln.strip()}", flush=True)
else:
    print("   (none — no ungrounded prolog/epilog sentence needed removing this run)", flush=True)

# ---- BLOCKER 3 content-QA gate (mirror the service wiring) ----
print("\n================ BLOCKER 3 (content-QA factual gate) ================", flush=True)
try:
    import content_qa_runner
    _loc_parts = LOCATION.split(',')
    _venue_name_raw = _loc_parts[0].strip()
    _city_raw = _loc_parts[1].strip() if len(_loc_parts) > 1 else ''
    _region_raw = _loc_parts[2].strip() if len(_loc_parts) > 2 else ''
    _venue_tokens = set(w.lower() for w in re.split(r'[\s\-]+', _venue_name_raw) if len(w) >= 3)
    try:
        from generate_tour_text import _LAST_VERIFICATION_TIER
    except Exception:
        _LAST_VERIFICATION_TIER = ''
    _vctx = {'venue_tokens': _venue_tokens, 'city': _city_raw, 'region': _region_raw,
             'artist': '', 'tier': _LAST_VERIFICATION_TIER or ''}
    content_qa_runner.PASS_COUNT = 0
    content_qa_runner.FAIL_COUNT = 0
    content_qa_runner.FACTUAL_FAIL_COUNT = 0
    try:
        content_qa_runner.run_qa(text, venue_context=_vctx)
    except SystemExit:
        pass
    print(f"  BLOCKER 3 line 1 — PASS checks:          {content_qa_runner.PASS_COUNT}", flush=True)
    print(f"  BLOCKER 3 line 2 — style FAIL checks:    {content_qa_runner.FAIL_COUNT}", flush=True)
    print(f"  BLOCKER 3 line 3 — FACTUAL FAIL checks:  {content_qa_runner.FACTUAL_FAIL_COUNT}", flush=True)
except Exception as _qa_e:
    print(f"  content-QA gate error: {_qa_e}", flush=True)

# ---- D617: no http/www./Sources in the SPOKEN audio_N.txt text ----
print("\n================ D617 spoken-text grep (modernized parse) ================", flush=True)
try:
    import tour_generation_modernized as tgm
    parsed = tgm.parse_tour_content_to_modernized(text)
    _spoken = parsed.get('text_content', [])
    _joined = "\n".join(_spoken)
    # Write the spoken audio_N.txt files to disk so the grep operates on the exact
    # artifacts the listener's TTS would read.
    _audio_dir = '/app/tours/LOCAL608_audio'
    os.makedirs(_audio_dir, exist_ok=True)
    for _i, _st in enumerate(_spoken, 1):
        with open(os.path.join(_audio_dir, f'audio_{_i}.txt'), 'w', encoding='utf-8') as _af:
            _af.write(_st)
    _n_http = len(re.findall(r'https?://', _joined))
    _n_www = len(re.findall(r'www\.', _joined))
    _n_sources = len(re.findall(r'(?i)\bsources?\s*\(?', _joined))
    print(f"  spoken stops written : {len(_spoken)} -> {_audio_dir}/audio_*.txt", flush=True)
    print(f"  grep 'http'   in spoken audio text : {_n_http}", flush=True)
    print(f"  grep 'www.'   in spoken audio text : {_n_www}", flush=True)
    print(f"  grep 'Sources' in spoken audio text: {_n_sources}", flush=True)
    print(f"  D617 CLEAN   : {(_n_http == 0 and _n_www == 0 and _n_sources == 0)}", flush=True)
except Exception as _d617_e:
    print(f"  D617 grep error: {_d617_e}", flush=True)

print(f"\nTour total: ${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
