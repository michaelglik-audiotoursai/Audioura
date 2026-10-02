#!/usr/bin/env python3
"""LOCAL-560 Step 2.2 — generate the 8 required tours on TODAY's models, with the
OpenAI recording harness installed, under DISABLE_TOUR_CACHE=1.

The harness is installed BEFORE generate_tour_text is imported so that the raw
requests.post / openai-client patches are in place for every call site.

For each tour we persist, under tests/fixtures/local560/recordings/:
  <slug>.jsonl   — one JSON record per OpenAI chat call (model, messages,
                   temperature, response, usage, caller site)
  <slug>.log     — the full stdout of the generation (phase/gate/retry lines)
  <slug>.meta.json — cost record (_LAST_GENERATION_COST) + parsed retry/5.17 stats

Run (from repo root):
  python3 tests/fixtures/local560/generate_recordings.py            # all 8
  python3 tests/fixtures/local560/generate_recordings.py 0 1        # a subset by index
"""
import io
import json
import os
import re
import sys
import time
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)   # for openai_recorder
sys.path.insert(0, REPO)   # for generate_tour_text and friends

# --- load .env (OPENAI_API_KEY etc.) ---
_envfile = os.path.join(REPO, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# --- generation environment (today's models; cache off; storied on) ---
os.environ["DISABLE_TOUR_CACHE"] = "1"            # force real generation (D261)
os.environ["STORIED_MODE"] = "true"
os.environ.setdefault("DATABASE_URL",
                      "postgresql://admin:password123@localhost:5433/audiotours")
os.environ.setdefault("SNIPPET_CAP_PER_STOP", "20")
# IMPORTANT: do NOT set TOUR_LLM_MODEL / TOUR_STORY_MODEL — we want TODAY's
# resolved defaults (the env-unset behaviour the task asks us to measure).
for _k in ("TOUR_LLM_MODEL", "TOUR_STORY_MODEL", "CHECK_LLM_MODEL", "WRITE_LLM_MODEL"):
    os.environ.pop(_k, None)

REC_DIR = os.path.join(HERE, "recordings")
os.makedirs(REC_DIR, exist_ok=True)

# The 8 required tours (Michael's cases that make the checkers FIRE).
TOURS = [
    ("boston_sail_loft",        "restaurant tour of Boston Sail Loft, Boston, MA", "restaurant", 4),
    ("buttermilk_bourbon",      "restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, MA", "restaurant", 4),
    ("chart_house_boston",      "restaurant tour of Chart House, Boston, MA", "restaurant", 4),
    ("sycamore_little_big",     "Dinner at Sycamore and Little Big Diner in Newton Centre, MA", "restaurant", 4),
    ("logan_airport",           "Boston Logan International Airport, Boston MA", "facility", 4),
    ("our_lady_help_newton",    "Our Lady Help of Christians Catholic Church, Newton MA", "museum", 4),
    ("palais_lascaris_nice",    "Palais Lascaris, Nice, France", "museum", 4),
    ("french_riviera_biking",   "French Riviera biking tour", "biking", 5),
]

_RETRY_RE = re.compile(r"\[LOCAL-487\]|\[LOCAL-474\]|PHASE 5\.17")


def _parse_phase517(log_text):
    """Count PHASE 5.17 regenerations from the log.

    The retry increments `_retry_stats['retried']`, each one preceded by a
    retry/regeneration log line. We count explicit retry-issued markers.
    """
    retried = len(re.findall(r"will regenerate|retry judged|retrying stop|RETRY issued|regenerat\w* stop", log_text, re.I))
    # also capture the step-7 summary if present
    m = re.search(r"retried['\"]?\s*[:=]\s*(\d+)", log_text)
    summary = int(m.group(1)) if m else None
    return {"retry_markers": retried, "retried_summary": summary}


def generate_one(slug, location, tour_type, stops):
    import openai_recorder
    jsonl = os.path.join(REC_DIR, f"{slug}.jsonl")
    logpath = os.path.join(REC_DIR, f"{slug}.log")
    metapath = os.path.join(REC_DIR, f"{slug}.meta.json")

    # fresh recording file each run
    if os.path.exists(jsonl):
        os.remove(jsonl)
    rec = openai_recorder.install(jsonl)

    import generate_tour_text as gtt

    buf = io.StringIO()
    t0 = time.time()
    err = None
    text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out, _coords = gtt.generate_tour_text(
                location, tour_type, None, stops)
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0

    log_text = buf.getvalue()
    with open(logpath, "w", encoding="utf-8") as f:
        f.write(log_text)

    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    meta = {
        "slug": slug,
        "location": location,
        "tour_type": tour_type,
        "stops": stops,
        "wall_s": round(wall, 1),
        "chars": len(text) if text else 0,
        "ok": bool(text) and err is None,
        "error": err,
        "openai_calls_recorded": rec.count,
        "cost_record": cost,
        "phase517": _parse_phase517(log_text),
        "models_env": {
            "TOUR_LLM_MODEL": os.environ.get("TOUR_LLM_MODEL", "(unset)"),
            "TOUR_STORY_MODEL": os.environ.get("TOUR_STORY_MODEL", "(unset)"),
        },
    }
    rec.uninstall()
    with open(metapath, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"[{slug}] ok={meta['ok']} chars={meta['chars']} "
          f"calls={rec.count} wall={meta['wall_s']}s "
          f"openai_cost=${cost.get('total_cost', 0):.4f} "
          f"retry_markers={meta['phase517']['retry_markers']}"
          + (f"  ERROR: {err.splitlines()[0]}" if err else ""),
          flush=True)
    return meta


def main():
    sel = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else list(range(len(TOURS)))
    results = []
    for i in sel:
        slug, loc, tt, stops = TOURS[i]
        print(f"\n{'='*72}\n[{i}] GENERATING: {loc} ({tt}, {stops} stops)\n{'='*72}", flush=True)
        results.append(generate_one(slug, loc, tt, stops))
    summ = os.path.join(REC_DIR, "_run_summary.json")
    # merge with any existing summary so partial runs accumulate
    prev = {}
    if os.path.exists(summ):
        try:
            prev = {r["slug"]: r for r in json.load(open(summ))}
        except Exception:
            prev = {}
    for r in results:
        prev[r["slug"]] = r
    with open(summ, "w", encoding="utf-8") as f:
        json.dump(list(prev.values()), f, indent=2, default=str)
    print(f"\nSummary written: {summ}", flush=True)


if __name__ == "__main__":
    main()
