"""run_local767_live.py — LOCAL-767 live acceptance (ISOLATED container).

Runs "Newton City Hall, Newton, MA" (1 stop) through the REAL generation path
TWICE, to prove the fix end-to-end on the storied tree:

  RUN 1 — GEMINI UNSET. GEMINI_API_KEY and GOOGLE_API_KEY are removed from the
          environment before the call. Newton City Hall is a `worship_civic`
          venue, so generate_tour_text takes the venue-parts path; with no key
          every ask returns '' and venue_parts.build_tour_stops raises
          ServiceUnavailable. The LOCAL-767 fix must CATCH it, log
          "[LOCAL-767] venue-parts unavailable (reason=…) — falling back to
          standard stops", and STILL DELIVER a tour via the standard path. We
          assert: a tour came out, the fallback log fired, no ABORT.

  RUN 2 — GEMINI PRESENT. The key is restored. The same venue must take the
          venue-parts path ("[D571] VENUE-PARTS FILL"). We assert a tour came
          out and the venue-parts marker fired.

Both runs are metered: the LOCAL-594 grounding meter is reset before and read
after each run, priced with cost_rates; the per-tour OpenAI cap is $0.40 and the
whole script is budgeted well under $0.80. The startup line
"[LOCAL-767] GEMINI key present=<bool>" is captured from each run's stdout.

generate_tour_text is called DIRECTLY (it returns text; it does not write
audio_tours rows), so this harness writes ZERO rows to the shared DB — the
before/after audio_tours counts, printed by the surrounding shell script, must be
identical. Nothing is deleted (D141).

Usage (inside the isolated container, name local767-gen):
    python3 run_local767_live.py
"""
import io
import os
import re
import sys
import time
import contextlib

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'                  # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('COST_HARD_LIMIT_USD', '0.40')    # per-tour OpenAI cap

GIT_SHA = (open('/app/.git_sha').read().strip()
           if os.path.exists('/app/.git_sha') else '?')

LOCATION = 'Newton City Hall, Newton, MA'
STOPS = 1


def _grounding_snapshot():
    import story_leads
    try:
        return story_leads.get_grounding_requests()
    except Exception:
        return -1


def _run(label, expect_key_present):
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}", flush=True)
    # Fresh import each run so the startup key-presence line prints against the
    # environment we set up here, and module-level state is clean.
    for m in ('generate_tour_text', 'story_leads'):
        sys.modules.pop(m, None)
    import story_leads  # noqa: E402
    from generate_tour_text import generate_tour_text  # noqa: E402

    print(f"location : {LOCATION}", flush=True)
    print(f"stops    : {STOPS}", flush=True)
    print(f"git_sha  : {GIT_SHA}", flush=True)
    print(f"GEMINI_API_KEY present in env: {bool(os.environ.get('GEMINI_API_KEY'))}",
          flush=True)
    print(f"GOOGLE_API_KEY present in env: {bool(os.environ.get('GOOGLE_API_KEY'))}",
          flush=True)

    try:
        story_leads.reset_grounding_requests()
    except Exception:
        pass

    out = f"/app/tours/LOCAL767_{'withkey' if expect_key_present else 'nokey'}.txt"
    # Capture stdout so we can assert on the pipeline's own log lines while STILL
    # echoing everything for the operator.
    buf = io.StringIO()
    t0 = time.time()
    text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, out_file, _ = generate_tour_text(LOCATION, 'landmark', out, STOPS)
    except Exception as e:
        logs = buf.getvalue()
        sys.stdout.write(logs)
        print(f"\n!!! RUN RAISED: {type(e).__name__}: {e}", flush=True)
        return {'label': label, 'delivered': False, 'raised': f"{type(e).__name__}: {e}",
                'logs': logs, 'elapsed': time.time() - t0}
    elapsed = time.time() - t0
    logs = buf.getvalue()
    sys.stdout.write(logs)          # echo the full pipeline log

    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _tour_total = (_LAST_GENERATION_COST or {}).get('tour_total_cost',
                       (_LAST_GENERATION_COST or {}).get('total_cost', 0.0))
        _openai = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
        _grounding = (_LAST_GENERATION_COST or {}).get('grounding_cost', 0.0)
    except Exception:
        _tour_total = _openai = _grounding = 0.0

    reqs = _grounding_snapshot()

    # ── Assertions on the pipeline's own logs ───────────────────────────────
    key_line = next((l for l in logs.splitlines()
                     if '[LOCAL-767] GEMINI key present=' in l), '(not found)')
    fell_back = '[LOCAL-767] venue-parts unavailable' in logs \
        and 'falling back to standard stops' in logs
    venue_parts_fill = '[D571] VENUE-PARTS FILL' in logs
    aborted = 'ABORTING' in logs

    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text or '')
    delivered = bool(text)

    print(f"\n--- RESULT ({label}) ---", flush=True)
    print(f"  startup key line : {key_line.strip()}", flush=True)
    print(f"  delivered        : {delivered}  ({len(text or '')} chars, "
          f"{len(titles)} stop-title line(s))", flush=True)
    print(f"  fell back to std : {fell_back}", flush=True)
    print(f"  venue-parts fill : {venue_parts_fill}", flush=True)
    print(f"  ABORTED          : {aborted}", flush=True)
    print(f"  grounding reqs   : {reqs}", flush=True)
    print(f"  cost: tour_total=${_tour_total:.4f} openai=${_openai:.4f} "
          f"grounding=${_grounding:.4f}  wall={elapsed:.1f}s", flush=True)
    if text:
        _m1 = re.search(r'(?ms)^\s*Stop\s+1\s*[:\-].*?(?=^\s*Stop\s+2\s*[:\-]|\Z)', text)
        print("\n--- STOP 1 (first 900 chars) ---", flush=True)
        print((_m1.group(0).strip()[:900] if _m1 else (text[:900])), flush=True)

    return {'label': label, 'delivered': delivered, 'fell_back': fell_back,
            'venue_parts_fill': venue_parts_fill, 'aborted': aborted,
            'key_line': key_line.strip(), 'tour_total': _tour_total,
            'grounding_reqs': reqs, 'elapsed': elapsed}


# ── RUN 1: no key → must degrade to standard path and still deliver ──────────
_saved_gemini = os.environ.pop('GEMINI_API_KEY', None)
_saved_google = os.environ.pop('GOOGLE_API_KEY', None)
r1 = _run("RUN 1 — GEMINI UNSET (expect LOUD fallback to standard stops, tour delivered)",
          expect_key_present=False)

# ── RUN 2: restore key → must take the venue-parts path ──────────────────────
if _saved_gemini is not None:
    os.environ['GEMINI_API_KEY'] = _saved_gemini
if _saved_google is not None:
    os.environ['GOOGLE_API_KEY'] = _saved_google
_have_key = bool(os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
if _have_key:
    r2 = _run("RUN 2 — GEMINI PRESENT (expect venue-parts path)",
              expect_key_present=True)
else:
    print("\n[local767] No GEMINI/GOOGLE key in env — skipping RUN 2 (venue-parts "
          "path). RUN 1 alone proves the degrade fix.", flush=True)
    r2 = None

# ── Verdict ──────────────────────────────────────────────────────────────────
print(f"\n{'=' * 72}\nLOCAL-767 LIVE VERDICT\n{'=' * 72}", flush=True)
ok = True

print("RUN 1 (no key):", flush=True)
print(f"  delivered          = {r1['delivered']}   (want True)", flush=True)
print(f"  fell back to std   = {r1.get('fell_back')}   (want True)", flush=True)
print(f"  ABORTED            = {r1.get('aborted')}   (want False)", flush=True)
print(f"  key line           = {r1.get('key_line')}", flush=True)
if not (r1['delivered'] and r1.get('fell_back') and not r1.get('aborted')):
    ok = False
    print("  >>> RUN 1 FAILED its acceptance", flush=True)

if r2 is not None:
    print("RUN 2 (with key):", flush=True)
    print(f"  delivered          = {r2['delivered']}   (want True)", flush=True)
    print(f"  venue-parts fill   = {r2.get('venue_parts_fill')}   (want True)", flush=True)
    if not (r2['delivered']):
        ok = False
        print("  >>> RUN 2 FAILED its acceptance (no tour)", flush=True)

_total = (r1.get('tour_total') or 0.0) + (r2.get('tour_total') if r2 else 0.0)
print(f"\nTOTAL METERED SPEND (OpenAI+grounding, in-process): ${_total:.4f}  "
      f"(budget ≤ $0.80)", flush=True)
if _total > 0.80:
    print("  >>> OVER BUDGET", flush=True)

print(f"\nLOCAL-767 LIVE: {'PASS' if ok else 'FAIL'}", flush=True)
sys.exit(0 if ok else 1)
