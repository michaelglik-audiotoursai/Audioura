#!/usr/bin/env python3
"""LOCAL-569 step 4 — measure the story-retry flags on three museums x three arms.

Arms (one run each, D261 host env):
  A  both flags off          (today / ship-last)
  B  STORY_RETRY_KEEP_BEST=1
  C  STORY_RETRY_KEEP_BEST=1 + STORY_RETRY_EARLY_STOP=1

Museums:
  Palais Lascaris, Nice, France      — story-poor (LOCAL-566: 39 writer calls/4 stops,
                                        most stops stuck at story_count 1-2 through 5/5)
  Museum of Fine Arts, Boston, MA    — the standing storied reference venue
  The Metropolitan Museum of Art, New York, NY
                                     — NON story-poor control. The Met resolves
                                        offline (dense Wikidata/Wikipedia corpus) even
                                        with Gemini off, and its signature works carry
                                        rich named-person provenance (artists, donors,
                                        acquisitions), so stops reach story_count>=3
                                        readily. Here the flags should barely change the
                                        outcome and early-stop should ship as soon as
                                        >=3 is hit — the guard that the flags don't harm
                                        a storied museum. (Isabella Stewart Gardner was
                                        tried first but is unresolvable offline with
                                        Gemini off — 0 corpus pages — so it produced an
                                        empty tour and could not exercise the retry.)

Host env: DISABLE_TOUR_CACHE=1, STORIED_MODE=true, DATABASE_URL -> localhost:5433.
Gemini OFF (as LOCAL-566): GEMINI_API_KEY removed from the run env so the grounding
channel issues no requests. OpenAI cap: a cumulative $6 budget across all cells, with
a per-tour COST_HARD_LIMIT_USD guard; the harness stops before the next cell would
risk the cap and persists after every cell so a partial run is still an artifact.

NO audio_tours writes: generate_tour_text() (the in-process path used here) does not
call store_audio_tour. The harness records audio_tours row counts before and after to
prove it, and never DELETEs.

Run:
    python3 run_local569_measure.py            # all remaining cells
    python3 run_local569_measure.py A Palais   # (optional) a single cell by arm+museum
"""
import contextlib
import io
import json
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

# --- D261 host env -----------------------------------------------------------
_envfile = os.path.join(HERE, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ["STORIED_MODE"] = "true"
os.environ.setdefault("DATABASE_URL",
                      "postgresql://admin:password123@localhost:5433/audiotours")
# Gemini off (LOCAL-566): set the keys to empty BEFORE anything can read .env.
# Popping is not enough — story_leads.py re-reads .env with setdefault at import,
# which would restore a popped key. An empty (but present) value is falsy for the
# `os.environ.get('GEMINI_API_KEY') or ...` guard AND blocks setdefault from
# refilling it, so the grounding channel issues zero requests.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
# Per-tour safety guard; the cumulative $6 cap is enforced in the loop below.
os.environ.setdefault("COST_HARD_LIMIT_USD", "2.00")

OUTDIR = os.path.join(HERE, "LOCAL569_measure")
os.makedirs(OUTDIR, exist_ok=True)
SUMMARY = os.path.join(OUTDIR, "summary.json")

OPENAI_BUDGET_USD = 6.0

MUSEUMS = [
    ("Palais", "Palais Lascaris, Nice, France"),
    ("MFA", "Museum of Fine Arts, Boston, MA"),
    ("Met", "The Metropolitan Museum of Art, New York, NY"),
]
ARMS = {
    "A": {},
    "B": {"STORY_RETRY_KEEP_BEST": "1"},
    "C": {"STORY_RETRY_KEEP_BEST": "1", "STORY_RETRY_EARLY_STOP": "1"},
}
TOUR_TYPE = "museum"
# 3 stops (not 4): with Gemini off the OpenAI writer is ~$0.6-0.9 per 3-4 stop
# tour; 9 cells (3 museums x 3 arms) must fit the $6 OpenAI cap, so 3 stops keeps
# the whole matrix inside budget. All arms use the same stop count, so the A/B/C
# comparison is unaffected.
STOPS = 3

_ATTEMPT_RE = re.compile(
    r"\[LOCAL-569\] Stop (\d+) attempt (\d+)/(\d+) story_count=(\d+) words=(\d+)")
_EARLYSTOP_RE = re.compile(r"\[LOCAL-569\] Stop (\d+): EARLY STOP")
_KEEPBEST_RE = re.compile(r"\[LOCAL-569\] Stop (\d+): KEEP-BEST ship")
_STORYRETRY_RE = re.compile(r"\[LOCAL-432\] Stop (\d+): STORY RETRY")


def _audio_tours_count():
    try:
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
        real = cur.fetchone()[0]
        conn.close()
        return {"total": total, "non_test": real}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _parse_log(log_text):
    """Extract per-attempt story lines, per-stop shipped story_count, early-stop /
    keep-best / story-retry events from a run's stdout."""
    attempts = {}  # stop -> list of {attempt,total,story_count,words}
    for m in _ATTEMPT_RE.finditer(log_text):
        stop = int(m.group(1))
        attempts.setdefault(stop, []).append({
            "attempt": int(m.group(2)), "of": int(m.group(3)),
            "story_count": int(m.group(4)), "words": int(m.group(5)),
        })
    # shipped story_count per stop = the LAST attempt line logged for that stop
    shipped = {}
    for stop, lst in attempts.items():
        lst_sorted = sorted(lst, key=lambda d: d["attempt"])
        shipped[stop] = lst_sorted[-1]["story_count"] if lst_sorted else None
    writer_attempts = sum(len(v) for v in attempts.values())
    return {
        "attempts_by_stop": {str(k): v for k, v in sorted(attempts.items())},
        "shipped_story_count_by_stop": {str(k): v for k, v in sorted(shipped.items())},
        "writer_attempts_logged": writer_attempts,
        "early_stops": sorted({int(m.group(1)) for m in _EARLYSTOP_RE.finditer(log_text)}),
        "keep_best_ships": sorted({int(m.group(1)) for m in _KEEPBEST_RE.finditer(log_text)}),
        "story_retries": len(_STORYRETRY_RE.findall(log_text)),
    }


def run_cell(arm, mkey, location, cumulative_cost):
    cell_id = f"{mkey}_{arm}"
    cell_env = ARMS[arm]
    # set/clear arm flags
    for k in ("STORY_RETRY_KEEP_BEST", "STORY_RETRY_EARLY_STOP"):
        os.environ.pop(k, None)
    for k, v in cell_env.items():
        os.environ[k] = v

    # Reimport fresh so the cost record starts clean per cell.
    import importlib
    import generate_tour_text as gtt
    importlib.reload(gtt)

    text_path = os.path.join(OUTDIR, f"{cell_id}.txt")
    buf = io.StringIO()
    t0 = time.time()
    err = None
    text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out, _coords = gtt.generate_tour_text(
                location, TOUR_TYPE, text_path, STOPS,
                job_id=f"local569-{cell_id}")
    except Exception as e:
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0
    log_text = buf.getvalue()
    with open(os.path.join(OUTDIR, f"{cell_id}.log"), "w", encoding="utf-8") as fh:
        fh.write(log_text)

    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    acc = cost.get("cost_accumulator") or {}
    llm = (acc.get("llm") or {}) if isinstance(acc, dict) else {}
    breakdown = cost.get("breakdown") or {}
    parsed = _parse_log(log_text)

    # score the tour
    score = {}
    try:
        import tour_quality as tq
        scored = tq.score_tour(text or "", STOPS, is_building_tour=False)
        score = {
            "defects": list(scored.get("defects", {}).keys()),
            "defect_detail": scored.get("defects", {}),
            "metrics": scored.get("metrics", {}),
            "clean": scored.get("clean"),
        }
    except Exception as e:
        score = {"error": f"{type(e).__name__}: {e}"}

    rec = {
        "cell": cell_id, "arm": arm, "museum": mkey, "location": location,
        "flags": cell_env, "ok": bool(text) and err is None,
        "error": err, "wall_s": round(wall, 1), "chars": len(text or ""),
        "writer_llm_calls": llm.get("calls"),
        "writer_attempts_logged": parsed["writer_attempts_logged"],
        "breakdown_llm_usd": round(breakdown.get("llm", 0.0), 6),
        "search_usd": round(breakdown.get("search", 0.0), 6),
        "grounding_usd": round(breakdown.get("grounding", 0.0), 6),
        "tour_total_cost_usd": round(cost.get("tour_total_cost", 0.0), 6),
        "total_cost_llm_usd": round(cost.get("total_cost", 0.0), 6),
        "shipped_story_count_by_stop": parsed["shipped_story_count_by_stop"],
        "attempts_by_stop": parsed["attempts_by_stop"],
        "early_stops": parsed["early_stops"],
        "keep_best_ships": parsed["keep_best_ships"],
        "story_retries": parsed["story_retries"],
        "score_tour": score,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return rec


def main():
    argv = sys.argv[1:]
    only_arm = argv[0] if len(argv) >= 1 else None
    only_museum = argv[1] if len(argv) >= 2 else None

    summary = {"arms": ARMS, "museums": dict(MUSEUMS), "tour_type": TOUR_TYPE,
               "stops": STOPS, "openai_budget_usd": OPENAI_BUDGET_USD,
               "gemini": "off (GEMINI_API_KEY removed)", "cells": {}}
    if os.path.exists(SUMMARY):
        try:
            summary = json.load(open(SUMMARY))
        except Exception:
            pass
    summary.setdefault("cells", {})

    at_before = _audio_tours_count()
    summary["audio_tours_before"] = at_before
    print(f"[audio_tours BEFORE] {at_before}")

    cumulative = sum(c.get("tour_total_cost_usd", 0.0)
                     for c in summary["cells"].values() if isinstance(c, dict))
    print(f"[cumulative cost so far] ${cumulative:.4f}")

    # Order: arm A for all museums, then B, then C, so a partial run still has a
    # complete baseline.
    for arm in ("A", "B", "C"):
        if only_arm and arm != only_arm:
            continue
        for mkey, location in MUSEUMS:
            if only_museum and mkey != only_museum:
                continue
            cell_id = f"{mkey}_{arm}"
            if cell_id in summary["cells"] and summary["cells"][cell_id].get("ok"):
                print(f"[skip] {cell_id} already done "
                      f"(${summary['cells'][cell_id].get('tour_total_cost_usd', 0):.4f})")
                continue
            if cumulative + 1.2 > OPENAI_BUDGET_USD:
                print(f"[CAP] cumulative ${cumulative:.4f} + ~$1.2 would risk "
                      f"${OPENAI_BUDGET_USD} cap — stopping before {cell_id}.")
                summary["stopped_at_cap"] = {"before": cell_id, "cumulative": cumulative}
                json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
                _finish(summary)
                return
            print(f"\n{'='*72}\n[RUN] {cell_id}: {location}  flags={ARMS[arm]}\n{'='*72}",
                  flush=True)
            rec = run_cell(arm, mkey, location, cumulative)
            summary["cells"][cell_id] = rec
            cumulative += rec.get("tour_total_cost_usd", 0.0) or 0.0
            json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
            print(f"[done] {cell_id}: ok={rec['ok']} wall={rec['wall_s']}s "
                  f"writer_calls={rec['writer_llm_calls']} "
                  f"attempts_logged={rec['writer_attempts_logged']} "
                  f"cost=${rec['tour_total_cost_usd']:.4f} "
                  f"shipped_story={rec['shipped_story_count_by_stop']} "
                  f"defects={rec['score_tour'].get('defects')}  "
                  f"cumulative=${cumulative:.4f}", flush=True)

    _finish(summary)


def _finish(summary):
    at_after = _audio_tours_count()
    summary["audio_tours_after"] = at_after
    json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
    print(f"\n[audio_tours AFTER] {at_after}")
    print(f"[summary] {SUMMARY}")


if __name__ == "__main__":
    main()
