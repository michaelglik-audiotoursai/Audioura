"""run_local609_gardner.py — LOCAL-609 isolated live acceptance (DISPOSABLE container).

Generates ONE fresh 3-stop museum tour of `Isabella Stewart Gardner Museum,
Boston, MA` through the REAL generation path, records the tour_generate row into
the cost_ledger exactly as generate_tour_text_service does (reading
_LAST_GENERATION_COST, our_cost_usd=tour_total_cost, breakdown=the 7-key provider
breakdown), then runs tour_cost_report.build_report against that job and prints
the table — the ticket's deliverable (5).

Cap $1.50 (COST_HARD_LIMIT_USD). Stop pool + tour cache use the DISPOSABLE
Postgres passed via DATABASE_URL; no audioura-* container is touched.

Usage (inside the isolated container local609-gen):
    python3 run_local609_gardner.py
"""
import os
import time
import uuid

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'              # fresh generation, not a cache hit
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('COST_HARD_LIMIT_USD', '1.50')  # ticket cap $1.50
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')    # exercise the preflight line

LOCATION = os.environ.get('LOCAL609_LOCATION', 'Isabella Stewart Gardner Museum, Boston, MA')
STOPS = int(os.environ.get('LOCAL609_STOPS', '3'))
OUT = os.environ.get('LOCAL609_OUT', '/app/tours/LOCAL609_GARDNER_RUN.txt')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

JOB_ID = os.environ.get('LOCAL609_JOB_ID', f"local609-{uuid.uuid4().hex[:12]}")
GIT_SHA = (open('/app/.git_sha').read().strip()
           if os.path.exists('/app/.git_sha') else '?')

print("=== LOCAL-609 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)
print(f"job_id   : {JOB_ID}", flush=True)
print(f"git_sha  : {GIT_SHA}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS, job_id=JOB_ID)
elapsed = time.time() - t0

# ---- Record the ledger row EXACTLY as generate_tour_text_service does ----
# (the service is the production writer; this driver calls generate_tour_text
# directly, so we replicate its record step so the row lands in the disposable
# cost_ledger for the report to read.)
from generate_tour_text import _LAST_GENERATION_COST  # noqa: E402
_cost_info = _LAST_GENERATION_COST or {}
_is_cache_hit = _cost_info.get("cache_hit", False)
_op_type = "tour_cache_hit" if _is_cache_hit else "tour_generate"
_llm_cost = _cost_info.get("total_cost", 0.0)
_grounding = _cost_info.get("grounding_cost", 0.0) or 0.0
_our_cost = _cost_info.get("tour_total_cost", _llm_cost + _grounding)
_breakdown = dict(_cost_info.get("breakdown", {}) or {})
if "research_cost_reused" in _cost_info:
    _breakdown["research_cost_reused"] = _cost_info.get("research_cost_reused", 0.0) or 0.0
for _k in ("pool_reuse", "by_reference", "reused_stops", "new_stops"):
    if _k in _cost_info:
        _breakdown[_k] = _cost_info[_k]

try:
    from cost_meter import record_operation
    _row_id = record_operation(
        operation_type=_op_type,
        our_cost_usd=_our_cost,
        cache_hit=_is_cache_hit,
        user_id=None,
        job_id=JOB_ID,
        breakdown=_breakdown,
        description=f"Tour: {LOCATION}",
    )
    print(f"\n[LOCAL-609] ledger row recorded: {_row_id} ({_op_type}, ${_our_cost:.6f})", flush=True)
except Exception as _e:
    print(f"[LOCAL-609] ledger record FAILED: {_e}", flush=True)

print("\n================ RESULT ================", flush=True)
if not text:
    print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"  evidence: {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception:
        pass
else:
    import re
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops, wall={elapsed:.1f}s", flush=True)
    for _t in titles:
        print(f"   {_t.strip()[:100]}", flush=True)

# ---- Print the tour_cost_report.py table for this job ----
print("\n" + "#" * 64, flush=True)
print("# tour_cost_report.py  — LOCAL-609 deliverable table", flush=True)
print("#" * 64, flush=True)
try:
    import tour_cost_report as _rep
    conn = _rep._connect()
    try:
        rows = _rep._rows_for_job(conn, JOB_ID)
        print(_rep.build_report(rows, {"tour_name": LOCATION}), flush=True)
    finally:
        conn.close()
except Exception as _re_err:
    print(f"[LOCAL-609] report error: {_re_err}", flush=True)

print(f"\nOUT: {out_file}", flush=True)
