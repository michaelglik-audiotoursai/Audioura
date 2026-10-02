"""LOCAL-563 — per-run generator wrapper (one tour, one run, one process).

Invoked by run_baseline.py as a subprocess:

    python3 run_one.py <slug> <run_label>

Why a subprocess per tour-run:
  * The LOCAL-533 grounded counter in story_leads is a module global that
    generate_tour_text RESETS at the start of every generation, and the LOCAL-562
    cost accumulator is per-tour. Running two tours in one interpreter would let one
    tour's reset/scope clobber the other's measurement. One process per run keeps
    each run's grounded count, cost record and recorded calls cleanly its own.
  * The $14 cap is still process-wide and correct: every run shares the on-disk
    cumulative counter in gemini_recorder (flock-serialised), so three parallel run
    processes increment one running total, and the orchestrator reads that same file
    to decide whether to start the next tour.

What this writes under tests/fixtures/local563/runs/<slug>_<run>.*:
  .txt          the final delivered tour text
  .log          the full generator stdout (the generator log)
  .gemini.jsonl one JSON object per recorded Gemini call (prompt/response/grounding)
  .json         the structured per-run record: cost, extracted measures, grounded
                count, call summary, wall time, status

The structured record is what baseline_summary.json is built from. It is written
even on failure (status != 'ok') so a cap stop or an error still leaves a complete,
inspectable artifact for the pair.
"""
import os
import re
import sys
import json
import time
import io
import contextlib
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RUNS = os.path.join(HERE, "runs")
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

# The 10 tours. (slug -> request, tour_type, stops, is_building_tour)
TOURS = {
    "sail_loft":    ("Boston Sail Loft, Boston, MA", "restaurant", 1, True),
    "buttermilk":   ("Buttermilk & Bourbon - Back Bay, Boston, MA", "restaurant", 1, True),
    "chart_house":  ("Chart House, Boston, MA", "restaurant", 1, True),
    "sycamore":     ("Dinner at Sycamore and Little Big Diner in Newton Centre, MA", "restaurant", 2, True),
    "la_maree":     ("La Marée restaurant, Monaco", "restaurant", 1, True),
    "logan":        ("Boston Logan International Airport, Boston MA", "facility", 4, True),
    "our_lady":     ("Our Lady Help of Christians Catholic Church, Newton MA", "museum", 4, True),
    "lascaris":     ("Palais Lascaris, Nice, France", "museum", 4, True),
    "riviera_bike": ("French Riviera biking tour", "walking", 4, False),
    "faneuil":      ("Faneuil Hall Marketplace, Boston MA", "walking", 4, False),
}


def _load_env():
    """Mirror story_leads' .env loader so keys are present when run from a shell."""
    envfile = os.path.join(REPO, ".env")
    if os.path.exists(envfile):
        for line in open(envfile, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ───────────────────────── measure extraction from the log ──────────────────
_GATE_235 = re.compile(r"\[LOCAL-235\]\s+R10 summary:\s+(\d+)\s+sentences deleted")
_GATE_229 = re.compile(r"\[LOCAL-229\]\s+CONTRADICTED block summary:\s+(\d+)\s+group\(s\) blocked")
_GATE_472_PARA = re.compile(r"\[LOCAL-472\]\s+REMOVED transferable paragraph")
_GATE_472_ENT = re.compile(r"\[LOCAL-472\]\s+UNGROUNDED entity")
_RP_LINE = re.compile(r"\[D538\]\s+'(?P<name>[^']*)'\s+via\s+(?P<provider>\S+):\s+(?P<bits>.*)")
_RP_DROP = re.compile(r"\[D538\]\s+.*DROPPED\s+'(?P<name>[^']*)'\s+—\s+(?P<reason>.*)")


def _gate_removals(log_text):
    """Count sentences/blocks removed by the three deletion gates, from the log.

    235: sum of 'N sentences deleted' across R10 summary lines (the gate can log a
         summary more than once if the chain runs per-stop).
    229: sum of 'N group(s) blocked' across CONTRADICTED summary lines.
    472: occurrences of REMOVED transferable paragraph + UNGROUNDED entity lines
         (each line is one removal), per the task's "count occurrences".
    """
    g235 = sum(int(m) for m in _GATE_235.findall(log_text))
    g229 = sum(int(m) for m in _GATE_229.findall(log_text))
    g472 = len(_GATE_472_PARA.findall(log_text)) + len(_GATE_472_ENT.findall(log_text))
    return {
        "local235_r10_sentences_deleted": g235,
        "local229_contradicted_groups_blocked": g229,
        "local472_specificity_removals": g472,
        "total": g235 + g229 + g472,
    }


def _restaurant_practicals(log_text):
    """What practicals the pipeline actually acquired per restaurant stop, parsed
    from the [D538] log lines: which of hours / reservation / price_band / closed
    were obtained, and any closed-verdict drops."""
    per_stop = []
    for m in _RP_LINE.finditer(log_text):
        bits = m.group("bits")
        fields = {}
        for key in ("hours", "closed_days", "reservation", "price_band"):
            fm = re.search(rf"{key}=([^,]+)", bits)
            if fm:
                fields[key] = fm.group(1).strip()
        per_stop.append({
            "name": m.group("name"),
            "provider": m.group("provider"),
            "nothing_actionable": "nothing actionable" in bits,
            "hours": "hours" in fields,
            "closed_days": "closed_days" in fields,
            "reservation": "reservation" in fields,
            "price_band": "price_band" in fields,
            "raw": bits.strip(),
        })
    drops = [{"name": m.group("name"), "reason": m.group("reason").strip()}
             for m in _RP_DROP.finditer(log_text)]
    return {
        "stops": per_stop,
        "stops_with_any_practical": sum(1 for s in per_stop if not s["nothing_actionable"]),
        "hours_count": sum(1 for s in per_stop if s["hours"]),
        "reservation_count": sum(1 for s in per_stop if s["reservation"]),
        "price_band_count": sum(1 for s in per_stop if s["price_band"]),
        "closed_dropped": drops,
    }


def _measures(text, log_text, tour_type, requested_stops, is_building_tour):
    """All extracted quality measures for one run."""
    import tour_quality as tq
    score = tq.score_tour(text or "", requested_stops=requested_stops,
                          is_building_tour=is_building_tour)
    metrics = score.get("metrics", {})
    defects = score.get("defects", {})
    out = {
        "story_score_clean": bool(score.get("clean")),
        "defects": sorted(defects.keys()),
        "defect_count": len(defects),
        "defect_detail": defects,
        "named_people": metrics.get("named_people"),
        "stops_delivered": metrics.get("stops_delivered"),
        "stops_requested": requested_stops,
        "dates": metrics.get("dates"),
        "chars": len(text) if text else 0,
        "gate_removals": _gate_removals(log_text),
    }
    if tour_type == "restaurant":
        out["restaurant_practicals"] = _restaurant_practicals(log_text)
    return out


def main():
    if len(sys.argv) != 3:
        print("usage: run_one.py <slug> <run_label>", file=sys.stderr)
        return 2
    slug, run_label = sys.argv[1], sys.argv[2]
    if slug not in TOURS:
        print(f"unknown slug {slug!r}", file=sys.stderr)
        return 2

    _load_env()
    os.environ["DISABLE_TOUR_CACHE"] = "1"      # real generation, no cache (D261)
    os.environ["STORIED_MODE"] = "true"
    os.environ.setdefault("DATABASE_URL",
                          "postgresql://admin:password123@localhost:5433/audiotours")

    request, tour_type, stops, is_building = TOURS[slug]
    os.makedirs(RUNS, exist_ok=True)
    base = os.path.join(RUNS, f"{slug}_{run_label}")
    txt_path = base + ".txt"
    log_path = base + ".log"
    jsonl_path = base + ".gemini.jsonl"
    json_path = base + ".json"

    import gemini_recorder as gr

    # Pre-flight: cumulative total BEFORE this run (the orchestrator also checks,
    # but record it so the artifact is self-describing).
    cum_before = gr.cumulative_grounded_requests()

    rec = gr.GeminiRecorder(enforce_cap=True).install()

    import generate_tour_text as gtt

    # Compose the location string passed to the engine. We pass the request as the
    # user's words, with the given tour_type. ONE narrow, transparent adjustment:
    # for a restaurant tour we present it as "restaurant tour of <request>". That
    # exact phrase ("restaurant" + "tour") is what the engine's own guard
    # (_EXPLICIT_NON_MUSEUM_TOUR_RE in generate_tour_text.py) matches to STOP the
    # S15 rule from forcing a named venue into the artwork/museum pipeline, where a
    # restaurant has no catalogued works and clean-fails 'unresolvable' making ZERO
    # Gemini calls. Verified live: a bare "Boston Sail Loft, Boston, MA" and even
    # "... , restaurant" both clean-fail (S15 needs the "<type> tour" phrase); the
    # working historical LOCAL-562 run used "restaurant tour of Chart House". This
    # measures the restaurant GENERATION path (the Gemini questions this baseline
    # exists to record), not the terse-input classifier. Venue + city are intact for
    # step-2 Serper replay; the exact string is recorded in location_passed. No
    # generation code is changed.
    location_passed = request
    signal_appended = False
    if tour_type == "restaurant" and "restaurant tour" not in request.lower():
        location_passed = f"restaurant tour of {request}"
        signal_appended = True

    buf = io.StringIO()
    t0 = time.time()
    status = "ok"
    err = None
    text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out_file, _coords = gtt.generate_tour_text(
                location_passed, tour_type, txt_path, stops,
                job_id=f"local563-{slug}-{run_label}",
            )
    except gr.BudgetExceeded as e:
        status = "budget_exceeded"
        err = f"{type(e).__name__}: {e}"
    except Exception as e:
        status = "error"
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0
    rec.uninstall()

    # A generation that returns None/empty text did not produce a tour. The engine
    # does this on a 'clean fail' (e.g. an artwork-pipeline 'unresolvable') and
    # returns normally rather than raising, so distinguish it from a real tour here
    # — shipping it as 'ok' would poison the baseline with an empty measurement.
    if status == "ok" and not (text and text.strip()):
        status = "clean_fail"
        if not err:
            err = "generator returned empty/None text (clean fail — no tour produced)"

    log_text = buf.getvalue()
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(log_text)

    # The generator writes the .txt itself on success; if it did not (early
    # failure), write whatever text we have so the artifact exists.
    if text and not os.path.exists(txt_path):
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    if not text and not os.path.exists(txt_path):
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("")

    # Dump every recorded Gemini call.
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for r in rec.records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # The per-tour cost record from the LOCAL-562 accumulator.
    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    # Drop the heavy debug snapshot from the slim record (kept in cost.full below).
    cost_slim = {k: v for k, v in cost.items() if k != "cost_accumulator"}

    # Grounded count: prefer the pipeline's own counter (equals ours by construction),
    # fall back to the recorder's tally.
    try:
        from story_leads import get_grounding_requests as _get_gr
        pipeline_grounded = _get_gr()
    except Exception:
        pipeline_grounded = None

    measures = {}
    if text:
        try:
            measures = _measures(text, log_text, tour_type, stops, is_building)
        except Exception as e:
            measures = {"error": f"measure extraction failed: {type(e).__name__}: {e}"}

    cum_after = gr.cumulative_grounded_requests()

    record = {
        "slug": slug,
        "run": run_label,
        "request": request,
        "location_passed": location_passed,
        "restaurant_signal_appended": signal_appended,
        "tour_type": tour_type,
        "stops_requested": stops,
        "is_building_tour": is_building,
        "status": status,
        "error": err,
        "wall_s": round(wall, 1),
        "chars": len(text) if text else 0,
        "gemini_calls": {
            "total": len(rec.records),
            "grounded_this_run": rec.grounded_count,
            "ungrounded_this_run": rec.ungrounded_count,
            "pipeline_grounding_requests": pipeline_grounded,
            "by_site": _by_site(rec.records),
        },
        "budget": {
            "cumulative_grounded_before": cum_before,
            "cumulative_grounded_after": cum_after,
            "cumulative_cost_after_usd": round(cum_after * gr.GROUNDING_COST_PER_REQUEST, 4),
            "hard_cap_usd": gr.HARD_CAP_USD,
        },
        "cost_record": cost_slim,
        "measures": measures,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, default=str)

    print(f"[{slug}_{run_label}] status={status} wall={wall:.0f}s "
          f"grounded_this_run={rec.grounded_count} "
          f"cumulative={cum_after} (${cum_after*gr.GROUNDING_COST_PER_REQUEST:.2f}) "
          f"chars={len(text) if text else 0}")
    if err:
        print(f"[{slug}_{run_label}] ERROR/NOTE: {err.splitlines()[0]}")
    return 0 if status == "ok" else (3 if status == "budget_exceeded" else 1)


def _by_site(records):
    out = {}
    for r in records:
        site = r["site"]
        d = out.setdefault(site, {"grounded": 0, "ungrounded": 0})
        d["grounded" if r["grounded"] else "ungrounded"] += 1
    return out


if __name__ == "__main__":
    sys.exit(main())
