#!/usr/bin/env python3
"""run_local860_live.py — LOCAL-860 live, budget-enforced proof (Mac-local).

  Run A: "Boston Common and Old North Church walk, Boston" (2 stops).
         PASS = both named places are stops, with real pins.
  Run B: user-stops tour "Sophia's biking tour in Ho Chi Minh City", 3 user stops,
         one carrying a rainbow emoji. PASS = apostrophe kept, tour_name ends
         "Cycling Tour", no emoji in the TTS-bound text, Serper queries carry the
         city (not the tour title).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-860 TASK_BUDGET_USD=0.35, meter contract,
OWN meter dir ./_local860_meterlogs (D753 Mac-local no-mount escape hatch:
METER_MOUNT_GUARD=0 — never writes the shared/live DB, never touches the shared
audioura-* containers).
"""
import io
import json
import math
import os
import re
import sys
import time
import contextlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))


def _load_dotenv():
    path = os.path.join(_HERE, ".env")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

# ── budget + cheap env ───────────────────────────────────────────────────────
os.environ["TASK_BUDGET_ID"] = "LOCAL-860"
os.environ["TASK_BUDGET_USD"] = os.environ.get("TASK_BUDGET_USD", "0.35") or "0.35"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.35") or "0.35")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("USER_STOPS_ENABLED", "true")

_METER_DIR = os.path.join(_HERE, "_local860_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-860"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)


BOSTON_REQUEST = "Boston Common and Old North Church walk, Boston"
SOPHIA_TITLE = "Sophia's biking tour in Ho Chi Minh City"
G = "https://www.google.com/maps/place"
RAINBOW = "\U0001F308"
USER_STOPS = [
    f"Rambutan {G}/Rambutan/@10.7761,106.6962,18z",
    f"Longan {G}/Longan/@10.7791,106.6996,18z",
    f"{RAINBOW}Thi Bar Saigon {G}/Thi+Bar+Saigon/@10.76766,106.69396,18z",
]
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return rows


def _spent():
    return sum(float(r.get("usd") or 0.0) for r in _meter_rows()
               if r.get("status") in (200, "200"))


class _Tee:
    def __init__(self, *s):
        self._s = s

    def write(self, d):
        for s in self._s:
            s.write(d)
        return len(d)

    def flush(self):
        for s in self._s:
            try:
                s.flush()
            except Exception:
                pass


def _generate(location, tour_type, n, forced=None):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                location, tour_type, None, n, forced_stops=forced)
    except Exception as e:
        import traceback
        print(f"  [LOCAL-860] raised: {e}", flush=True)
        traceback.print_exc()
    return text, buf.getvalue()


def _blocks(text):
    titles = _STOP_HEADER_RE.findall(text or "")
    parts = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    return [(int(n), t.strip(), b) for (n, t), b in zip(titles, parts[1:])]


def _show(label, checks):
    ok = True
    print(f"\n  -- {label} --", flush=True)
    for name, good, detail in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}: {detail}", flush=True)
    return ok


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-860 live: Boston 2-stop walk + Sophia 3-stop cycling ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} cap=${HARD_CAP_USD:.2f}", flush=True)
    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass
    from live_run_meter import LiveRunMeter
    meter = LiveRunMeter("LOCAL-860")
    which = (sys.argv[1] if len(sys.argv) > 1 else "both").lower()
    art = os.path.join(_HERE, "submission_artifacts", "local860")
    os.makedirs(art, exist_ok=True)
    ok_all = True

    if which in ("both", "boston"):
        print("\n[RUN A] " + BOSTON_REQUEST, flush=True)
        text_a, log_a = _generate(BOSTON_REQUEST, "walking", 2)
        open(os.path.join(art, "live_boston.txt"), "w", encoding="utf-8").write(text_a or "")
        blocks = _blocks(text_a)
        print("  delivered stops: " + "; ".join(t for _, t, _ in blocks), flush=True)
        low = [t.lower() for _, t, _ in blocks]
        def has(word):
            return next((b for _, t, b in blocks if word in t.lower()), None)
        common, onc = has("boston common"), has("old north")
        def pin(b):
            m = _COORD_RE.search(b or "")
            return (float(m.group(1)), float(m.group(2))) if m else None
        pc, po = pin(common), pin(onc)
        # Real pins: inside the Boston bbox and not the city-centre default.
        def real(p):
            return bool(p) and 42.30 < p[0] < 42.42 and -71.20 < p[1] < -70.95
        checks = [
            ("2 stops delivered", len(blocks) == 2, str(len(blocks))),
            ("Boston Common is a stop", common is not None, str(low)),
            ("Old North Church is a stop", onc is not None, str(low)),
            ("Boston Common has a real pin", real(pc), str(pc)),
            ("Old North Church has a real pin", real(po), str(po)),
            ("pins differ (not one collapsed point)", bool(pc and po and pc != po), ""),
        ]
        ok_all = _show("RUN A (Boston)", checks) and ok_all

    if which in ("both", "sophia"):
        import tour_orchestrator_service as orch
        from text_polish import derive_tour_name
        loc = orch.sanitize_input(SOPHIA_TITLE)
        clean_stops = []
        for s in USER_STOPS:
            clean_stops.append(orch.sanitize_input(s))
        print("\n[RUN B] " + loc, flush=True)
        text_b, log_b = _generate(loc, "biking", len(clean_stops), forced=clean_stops)
        open(os.path.join(art, "live_sophia.txt"), "w", encoding="utf-8").write(text_b or "")
        first = (text_b or "").split("\n", 1)[0]
        tour_name = derive_tour_name(loc, "biking", first)
        import tour_generation_modernized as tgm
        tts_text = "\n".join(tgm._strip_nav_fields_for_tts(b) for b in [text_b or ""])
        # What polly_tts_service would send (second, independent choke point):
        from text_polish import strip_emoji_for_tts
        tts_text = strip_emoji_for_tts(tts_text)
        queries = re.findall(r"q='([^']*)'", log_b) or re.findall(r'queries=\[(.*?)\]', log_b)
        qtxt = " | ".join(queries) if isinstance(queries, list) else str(queries)
        blocks = _blocks(text_b)
        checks = [
            ("3 stops delivered", len(blocks) == 3, str(len(blocks))),
            ("sanitised title keeps the apostrophe", "Sophia's" in loc, loc),
            ("no 'Sophias' (stripped apostrophe) in the delivered text",
             "Sophias" not in (text_b or ""), "absent" if "Sophias" not in (text_b or "") else "FOUND"),
            ("tour_name ends 'Cycling Tour'", tour_name.endswith("Cycling Tour")
             and "biking Tour" not in tour_name, tour_name),
            ("header is not 'biking Tour'", "biking Tour" not in first, first[:100]),
            ("emoji kept in the DISPLAY text (stop title)", bool(_EMOJI_RE.search(text_b or "")),
             "present" if _EMOJI_RE.search(text_b or "") else "absent (user title lost it earlier)"),
            ("NO emoji in the TTS-bound text", not _EMOJI_RE.search(tts_text),
             "clean" if not _EMOJI_RE.search(tts_text) else repr(_EMOJI_RE.findall(tts_text))),
            ("Serper queries carry the city, not the title",
             "Sophia" not in qtxt and "biking" not in qtxt.lower(), qtxt[:200] or "(no queries logged)"),
        ]
        ok_all = _show("RUN B (Sophia cycling)", checks) and ok_all

    for fn in ("add_generation", "record"):
        try:
            import generate_tour_text as g
            (meter.add_generation(g) if fn == "add_generation" else meter.record())
        except Exception:
            pass
    try:
        meter.uninstall()
    except Exception:
        pass
    # The whole-task ledger (task_budget) is the authority the cap is enforced on;
    # the per-call meter rows alone under-count (LiveRunMeter adds estimated LLM
    # spend), so report the ledger.
    try:
        import task_budget as _tb
        total = float(_tb.spent_so_far("LOCAL-860"))
    except Exception:
        total = _spent()
    with open(os.path.join(art, "meter_ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"task_budget_id": "LOCAL-860", "hard_cap_usd": HARD_CAP_USD,
                   "metered_total_usd": round(total, 6), "rows": len(_meter_rows())}, f, indent=2)
    print(f"\n  metered total: ${total:.4f} / cap ${HARD_CAP_USD:.2f}", flush=True)
    ok_all = ok_all and total <= HARD_CAP_USD
    print(f"\n=== LOCAL-860 OVERALL: {'PASS' if ok_all else 'CHECK'} ===", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
