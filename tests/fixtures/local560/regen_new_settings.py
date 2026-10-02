#!/usr/bin/env python3
"""LOCAL-560 Step 6 — regenerate Chart House + Palais Lascaris with the NEW
central model settings and report OpenAI cost per tour before/after.

Uses the SAME recording harness as step 2 so every OpenAI call's on-wire model
and token usage is captured — now with the LOCAL-560 switch live. We leave
CHECK_LLM_MODEL / WRITE_LLM_MODEL UNSET so the committed defaults apply exactly
as production would see them (checkers -> gpt-4o-mini, writers unchanged).

Writes under tests/fixtures/local560/recordings_new/:
  <slug>.jsonl / <slug>.log / <slug>.meta.json

Run from repo root (local stack + DISABLE_TOUR_CACHE=1 required):
  python3 tests/fixtures/local560/regen_new_settings.py
"""
import io, json, os, sys, time, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

_envfile = os.path.join(REPO, ".env")
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
os.environ.setdefault("SNIPPET_CAP_PER_STOP", "20")
# NEW settings: leave the central knobs UNSET so the committed defaults apply
# (check_model -> gpt-4o-mini, write_model -> gpt-3.5-turbo site default, held
# scope gates -> gpt-3.5-turbo). Also keep TOUR_* unset so we measure the
# post-switch default, not a manual override.
for _k in ("TOUR_LLM_MODEL", "TOUR_STORY_MODEL", "CHECK_LLM_MODEL", "WRITE_LLM_MODEL",
           "IS_RESTAURANT_MODEL", "GEO_SCOPE_MODEL", "VENUE_SCOPE_MODEL"):
    os.environ.pop(_k, None)

REC_DIR = os.path.join(HERE, "recordings_new")
os.makedirs(REC_DIR, exist_ok=True)

RATES = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60), "gpt-3.5-turbo": (0.50, 1.50)}
def _wire_cost(model, pin, pout):
    for k, (i, o) in RATES.items():
        if k in (model or ""):
            return pin * i / 1e6 + pout * o / 1e6
    return 0.0

TOURS = [
    ("chart_house_boston",   "restaurant tour of Chart House, Boston, MA", "restaurant", 4),
    ("palais_lascaris_nice", "Palais Lascaris, Nice, France", "museum", 4),
]


def generate_one(slug, location, tour_type, stops):
    import openai_recorder
    jsonl = os.path.join(REC_DIR, f"{slug}.jsonl")
    logpath = os.path.join(REC_DIR, f"{slug}.log")
    metapath = os.path.join(REC_DIR, f"{slug}.meta.json")
    if os.path.exists(jsonl):
        os.remove(jsonl)
    rec = openai_recorder.install(jsonl)
    import generate_tour_text as gtt

    buf = io.StringIO()
    t0 = time.time(); err = None; text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out, _coords = gtt.generate_tour_text(location, tour_type, None, stops)
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0

    log_text = buf.getvalue()
    open(logpath, "w", encoding="utf-8").write(log_text)
    rec.uninstall()

    # recompute wire cost + per-model call breakdown from the fresh recording
    models = {}
    wire_cost = 0.0
    for line in open(jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        m = r.get("model")
        u = r.get("usage") or {}
        models[m] = models.get(m, 0) + 1
        wire_cost += _wire_cost(m, u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0)

    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    meta = {
        "slug": slug, "location": location, "tour_type": tour_type, "stops": stops,
        "wall_s": round(wall, 1), "chars": len(text) if text else 0,
        "ok": bool(text) and err is None, "error": err,
        "openai_calls_recorded": rec.count,
        "models_on_wire": models,
        "wire_cost_recomputed": round(wire_cost, 4),
        "cost_record": cost,
    }
    json.dump(meta, open(metapath, "w", encoding="utf-8"), indent=2, default=str)
    print(f"[{slug}] ok={meta['ok']} calls={rec.count} chars={meta['chars']} "
          f"wire_cost=${wire_cost:.4f} models={models}"
          + (f"  ERROR: {err.splitlines()[0]}" if err else ""), flush=True)
    return meta


def main():
    results = []
    for slug, loc, tt, stops in TOURS:
        print(f"\n{'='*70}\nGENERATING (new settings): {loc}\n{'='*70}", flush=True)
        results.append(generate_one(slug, loc, tt, stops))
    json.dump(results, open(os.path.join(REC_DIR, "_new_summary.json"), "w"), indent=2, default=str)
    print("\nwrote _new_summary.json", flush=True)


if __name__ == "__main__":
    main()
