#!/usr/bin/env python3
"""LOCAL-566 Step 2 — before/after measurement of the writer prompt-cache prefix.

Runs ONE tour live with the LOCAL-560 OpenAI recorder installed, so every
chat-completion call (site, model, messages, usage incl. cached_tokens) is
captured. Gemini grounding is DISABLED (GEMINI/GOOGLE keys unset) so the run
incurs NO Gemini cost — the task's "Gemini: none" rule — and isolates the
OpenAI writer cost, which is what this change touches.

The SAME tour is run twice:
  * arm="before"  WRITER_CACHE_PREFIX=0  (production default; original messages)
  * arm="after"   WRITER_CACHE_PREFIX=1  (universal rules relocated to system)

For each arm we report, for the WRITER call site (generate_tour_text.py writer):
  * writer OpenAI cost (cost_rates.llm_cost, undiscounted and cache-discounted)
  * input / output / cached tokens
  * cold vs warm writer calls
and the tour-level quality signals (tour_quality.score_tour on the saved text):
  * story defect count, named_people, stops delivered.

Usage:
  python3 tests/fixtures/local566/measure_prefix.py palais before
  python3 tests/fixtures/local566/measure_prefix.py palais after
  python3 tests/fixtures/local566/measure_prefix.py logan  before
  python3 tests/fixtures/local566/measure_prefix.py logan  after
"""
import os, sys, io, json, time, re, contextlib, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
# the LOCAL-560 recorder lives on another branch; we vendored a copy under local566/
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

# --- load .env for OPENAI_API_KEY (and DB), then STRIP Gemini keys ---
_envfile = os.path.join(REPO, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# Gemini: none. Unset so story_leads._gemini() returns '' (no grounded request).
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ["STORIED_MODE"] = "true"
os.environ.setdefault("DATABASE_URL",
                      "postgresql://admin:password123@localhost:5433/audiotours")
os.environ.setdefault("SNIPPET_CAP_PER_STOP", "20")
for _k in ("TOUR_LLM_MODEL", "TOUR_STORY_MODEL", "CHECK_LLM_MODEL", "WRITE_LLM_MODEL"):
    os.environ.pop(_k, None)

TOURS = {
    "palais": ("Palais Lascaris, Nice, France", "museum", 4),
    "logan":  ("Boston Logan International Airport, Boston MA", "facility", 4),
}

from cost_rates import llm_cost


def writer_site_matches(site):
    # The writer call site line can drift; match by file + the known function region.
    return bool(site) and site.startswith("generate_tour_text.py:")


def analyse(jsonl_path):
    """Return per-site aggregates and the writer breakdown from a recording."""
    by_site = collections.defaultdict(lambda: {"calls": 0, "pt": 0, "ct": 0,
                                               "cached": 0, "cost": 0.0,
                                               "models": collections.Counter()})
    writer_seq = []
    with open(jsonl_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            u = r.get("usage") or {}
            site = r.get("site") or r.get("caller") or "?"
            model = r.get("model") or "gpt-3.5-turbo"
            pt = u.get("prompt_tokens", 0); ct = u.get("completion_tokens", 0)
            cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            a = by_site[site]
            a["calls"] += 1; a["pt"] += pt; a["ct"] += ct; a["cached"] += cached
            a["cost"] += llm_cost(input_tokens=pt, output_tokens=ct, model=model)
            a["models"][model] += 1
            # the writer is the single highest-token gpt-4o description site; capture
            # all generate_tour_text.py sites that use gpt-4o with large prompts
            if model == "gpt-4o" and pt > 1500:
                writer_seq.append((site, pt, ct, cached))
    return by_site, writer_seq


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "palais"
    arm = sys.argv[2] if len(sys.argv) > 2 else "before"
    location, tour_type, stops = TOURS[which]
    os.environ["WRITER_CACHE_PREFIX"] = "1" if arm == "after" else "0"

    outdir = os.path.join(HERE, "measure")
    os.makedirs(outdir, exist_ok=True)
    jsonl = os.path.join(outdir, f"{which}_{arm}.jsonl")
    logpath = os.path.join(outdir, f"{which}_{arm}.log")
    txtpath = os.path.join(outdir, f"{which}_{arm}.txt")
    if os.path.exists(jsonl):
        os.remove(jsonl)

    import openai_recorder
    rec = openai_recorder.install(jsonl)
    import generate_tour_text as gtt

    print(f"[{which}/{arm}] WRITER_CACHE_PREFIX={os.environ['WRITER_CACHE_PREFIX']} "
          f"gemini_key={'set' if os.environ.get('GEMINI_API_KEY') else 'UNSET(no grounding)'}",
          flush=True)

    buf = io.StringIO(); t0 = time.time(); err = None; text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out, _coords = gtt.generate_tour_text(location, tour_type, None, stops)
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0
    rec.uninstall()

    log_text = buf.getvalue()
    open(logpath, "w", encoding="utf-8").write(log_text)
    if text:
        open(txtpath, "w", encoding="utf-8").write(text)

    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    by_site, writer_seq = analyse(jsonl)

    # writer aggregates
    w_calls = len(writer_seq)
    w_in = sum(x[1] for x in writer_seq)
    w_out = sum(x[2] for x in writer_seq)
    w_cached = sum(x[3] for x in writer_seq)
    w_cost_full = llm_cost(input_tokens=w_in, output_tokens=w_out, model="gpt-4o")
    # OpenAI bills cached input at 50%:
    w_cost_cachedisc = (llm_cost(input_tokens=w_in - w_cached, output_tokens=0, model="gpt-4o")
                        + llm_cost(input_tokens=w_cached, output_tokens=0, model="gpt-4o") * 0.5
                        + llm_cost(input_tokens=0, output_tokens=w_out, model="gpt-4o"))
    cold = sum(1 for x in writer_seq if x[3] == 0)
    warm = w_calls - cold

    # quality — use tour_quality.score_tour exactly as LOCAL-563 did (offline:
    # no provenance/geocoder), parsing its {'defects','metrics','clean'} shape.
    story = {"error": "no text"}
    named_people = None
    story_defect_count = None
    stops_delivered = None
    if text:
        try:
            from tour_quality import score_tour
            sc = score_tour(text, requested_stops=stops)
            defects = sc.get("defects", {}) if isinstance(sc, dict) else {}
            metrics = sc.get("metrics", {}) if isinstance(sc, dict) else {}
            story = {"clean": sc.get("clean"), "defects": list(defects.keys()),
                     "defect_detail": defects, "metrics": metrics}
            named_people = metrics.get("named_people")
            story_defect_count = len(defects)
            stops_delivered = metrics.get("stops_delivered")
        except Exception as e:
            import traceback
            story = {"error": f"score_tour failed: {e}", "tb": traceback.format_exc()}

    result = {
        "tour": which, "arm": arm,
        "writer_cache_prefix": os.environ["WRITER_CACHE_PREFIX"],
        "ok": bool(text) and err is None, "error": err,
        "wall_s": round(wall, 1), "chars": len(text) if text else 0,
        "openai_calls_recorded": rec.count,
        "writer": {
            "calls": w_calls, "cold": cold, "warm": warm,
            "input_tok": w_in, "output_tok": w_out, "cached_tok": w_cached,
            "cached_pct": round(100 * w_cached / w_in, 1) if w_in else 0,
            "cost_full_usd": round(w_cost_full, 4),
            "cost_cache_discounted_usd": round(w_cost_cachedisc, 4),
        },
        "tour_total_openai_cost": cost.get("total_cost"),
        "grounding_requests": cost.get("grounding_requests"),
        "named_people": named_people,
        "story_defect_count": story_defect_count,
        "stops_delivered": stops_delivered,
        "story_score": story,
    }
    outjson = os.path.join(outdir, f"{which}_{arm}.result.json")
    json.dump(result, open(outjson, "w"), indent=2, default=str)
    print(json.dumps(result, indent=2, default=str)[:2500], flush=True)
    print(f"\nwrote {outjson}", flush=True)



if __name__ == "__main__":
    main()
