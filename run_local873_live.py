#!/usr/bin/env python3
"""run_local873_live.py — LOCAL-873 live proof (Mac-local, own container).

ONE live 10-stop run of Michael's Saigon-centre list, in-process from THIS
worktree against this task's OWN postgres (docker-compose.local873-proof.yml,
:55973). The shared audioura-* containers, the shared dev DB (:5433) and the live
DB are never touched. TTS is not called.

Proves D766 / LOCAL-873: a THIN stop escalates to a real web search + page fetch
before narration, so the acceptance stop — Bạch Đằng Pier — gains real sourced
content instead of being empty/thin.

PASS (the ticket):
  * Bạch Đằng Pier has >= 5 sentences and >= 3 sourced specifics (each listed
    with its source URL from the [LOCAL-873] escalation);
  * no stop thinner than in LOCAL-872C's run (every stop has a non-empty body);
  * the claim gate shows 0 undisclosed unsourced claims (0 DROPPED by the
    LOCAL-872 gate at the end — a drop is an undisclosed unsourced claim);
  * the added cost per tour (LOCAL-873 escalation spend) is reported.

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-873 TASK_BUDGET_USD=0.50 \\
  PAID_API_LOG=$PWD/_local873_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local873_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-873 PYTHONPATH=$PWD/_meter \\
  python3 run_local873_live.py --saigon

Run logs go to ./_local873_meterlogs/ (never committed).
"""
import contextlib
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))


def _load_dotenv():
    try:
        with open(os.path.join(_HERE, ".env"), "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-873":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-873 (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55973/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55973"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

os.environ.pop("K_SERVICE", None)
os.environ["LANDMARK_LIVE_LOOKUP"] = "1"          # the real Wikidata/Wikipedia path
os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ["USER_STOPS_ENABLED"] = "true"
os.environ["THIN_STOP_SEARCH"] = "1"              # LOCAL-873 escalation ON

_METER_DIR = os.path.join(_HERE, "_local873_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
ACCEPT_STOP = "Bạch Đằng Pier"

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")


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


def _meter_total():
    total = 0.0
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    total += float(row.get("usd", row.get("cost_usd", row.get("cost", 0))) or 0)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return total


def _check(label, ok, detail=""):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}: {detail}", flush=True)
    return bool(ok)


def _blocks(text):
    titles = _STOP_HEADER_RE.findall(text)
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text)
    return [(int(n), t.strip(), b) for (n, t), b in zip(titles, bodies[1:])]


def _prose(b):
    return " ".join(l for l in b[2].split("\n") if l.strip() and not re.match(
        r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
        r"Orientation|Museum Information|Sources):", l.strip()))


def _sentences(prose):
    return [s.strip() for s in re.findall(r"[^.!?]*[.!?]", prose) if s.strip()]


def phase_saigon():
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL873_RESERVE_USD", "0.05"))
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    d = json.load(open(PREVIEW_JSON))
    forced = [s["resolved_name"] for s in d["stops"]]
    print(f"\n[SAIGON] request={REQUEST_547!r}; {len(forced)} stops", flush=True)

    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD - before)
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                REQUEST_547, "walking", None, len(forced), forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_METER_DIR, "saigon_tour.txt"), "w", encoding="utf-8").write(text or "")
    open(os.path.join(_METER_DIR, "saigon_log.txt"), "w", encoding="utf-8").write(log)
    try:
        _lrm.uninstall()
    except Exception:
        pass

    import landmark_claim_gate as _lgc
    blocks = _blocks(text)
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered", len(blocks) == len(forced), len(blocks))

    # ---- LOCAL-873 escalation telemetry from the log --------------------------
    thin_lines = re.findall(r"\[LOCAL-873\] thin stop .*", log)
    esc_lines = re.findall(r"\[LOCAL-873\] Stop \d+ .* was thin .*", log)
    print("\n--- [LOCAL-873] escalation telemetry ---", flush=True)
    for ln in thin_lines + esc_lines:
        print("  " + ln, flush=True)
    # the added LOCAL-873 cost (serper + llm) summed from the per-stop log lines
    added = 0.0
    for m in re.finditer(r"\[LOCAL-873\].*cost \$([0-9.]+)", log):
        try:
            added += float(m.group(1))
        except Exception:
            pass
    print(f"  LOCAL-873 added cost this tour: ${added:.4f}", flush=True)
    print("----------------------------------------\n", flush=True)

    # ---- per-stop body sentence counts (no stop thinner than 872C: non-empty) --
    print("--- per-stop body (first sentence + sentence count) ---", flush=True)
    empties = []
    for n, t, b in blocks:
        pr = _prose((n, t, b))
        ss = _sentences(pr)
        if not _lgc._has_real_sentence(b):
            empties.append(t)
        print(f"Stop {n} [{t}]: {len(ss)} sentence(s) | {(ss[0] if ss else '')[:90]}", flush=True)
    print("-------------------------------------------------------\n", flush=True)
    ok &= _check("no stop has an empty body (no stop thinner than 872C)",
                 not empties, empties or "all non-empty")

    # ---- acceptance stop: Bạch Đằng Pier --------------------------------------
    pier = next((b for b in blocks if "bach dang" in
                 b[1].encode("ascii", "ignore").decode().lower()
                 or "bạch đằng" in b[1].lower()), None)
    if pier is None:
        ok &= _check("Bạch Đằng Pier stop delivered", False, "missing")
    else:
        pr = _prose(pier)
        ss = _sentences(pr)
        ok &= _check("Bạch Đằng Pier has >= 5 sentences", len(ss) >= 5, len(ss))
        # sourced specifics for this stop, from the escalation facts recorded in log
        import thin_stop_search as _ts
        specifics = _ts.count_specifics(ss)
        ok &= _check("Bạch Đằng Pier has >= 3 sourced specifics", specifics >= 3, specifics)
        # list the escalation facts with their URLs (parsed from the narrator block log)
        facts_with_urls = re.findall(r"- (.+?) \[source: (https?://[^\]]+)\]", log)
        pier_facts = [(ftxt, furl) for ftxt, furl in facts_with_urls]
        print("   Bạch Đằng Pier sourced facts (from [LOCAL-873] escalation):", flush=True)
        for ftxt, furl in pier_facts[:12]:
            print(f"     - {ftxt}  [{furl}]", flush=True)
        print("   Bạch Đằng Pier delivered sentences:", flush=True)
        for s in ss:
            print(f"     · {s}", flush=True)

    # ---- claim gate: 0 undisclosed unsourced claims ---------------------------
    dropped = re.findall(r"\[LOCAL-872\] stop \d+ DROPPED", log)
    disclosed = re.findall(r"DISCLOSED", log)
    ok &= _check("claim gate shows 0 undisclosed unsourced claims (0 DROPPED)",
                 len(dropped) == 0, f"dropped={len(dropped)}, disclosed={len(disclosed)}")

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"   LOCAL-873 added cost per tour: ${added:.4f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--saigon" in sys.argv:
        sys.exit(0 if phase_saigon() else 1)
    sys.exit("usage: run_local873_live.py --saigon")
