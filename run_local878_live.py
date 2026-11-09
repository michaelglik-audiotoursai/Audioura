#!/usr/bin/env python3
"""run_local878_live.py — LOCAL-878 live proof (Mac-local, own container).

ONE live 10-stop run of Michael's Saigon-centre list, in-process from THIS worktree
against this task's OWN postgres (docker-compose.local878-proof.yml, :55978). The
shared audioura-* containers, the shared dev DB (:5433) and the live DB are never
touched. TTS is not called.

Proves the three LOCAL-878 fixes on the exact tour-547 inputs:
  1. Opera House is the SAIGON opera house (French colonial / 1900 / Ferret) or says it
     has no source — NEVER the Sydney one (no "Sydney"/"Utzon"/"Bennelong").
  2. Post Office is not empty.
  3. The request string "Saigon centre landmarks, …" is never treated as a place — the
     text never says "Saigon centre landmarks".

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-878 TASK_BUDGET_USD=0.35 \\
  PAID_API_LOG=$PWD/_local878_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local878_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-878 PYTHONPATH=$PWD/_meter \\
  python3 run_local878_live.py --saigon

Run logs go to ./_local878_meterlogs/ (never committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-878":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-878 (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.35") or "0.35")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55978/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55978"),
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

_METER_DIR = os.path.join(_HERE, "_local878_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

# The exact tour-547 request string (Bug 3 must never treat it as a place).
REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"

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
        r"Museum Information|Sources):", l.strip()))


def _first_two_sentences(prose):
    sents = re.findall(r"[^.!?]*[.!?]", prose)
    return " ".join(s.strip() for s in sents[:2]).strip() or prose[:240]


def phase_saigon():
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL878_RESERVE_USD", "0.05"))
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

    blocks = _blocks(text)
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered", len(blocks) == len(forced), len(blocks))

    # First two sentences of every stop (the ticket's report).
    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    low = (text or "").lower()
    # Bug 1: never the Sydney opera house.
    for bad in ("sydney", "utzon", "bennelong"):
        ok &= _check(f"'{bad}' absent from the delivered text", bad not in low, "absent" if bad not in low else "PRESENT")
    # Bug 3: the request string is never a place.
    ok &= _check("'saigon centre landmarks' absent from the delivered text",
                 "saigon centre landmarks" not in low,
                 "absent" if "saigon centre landmarks" not in low else "PRESENT")

    # Opera House: the Saigon one (French colonial / 1900 / Ferret) OR an explicit
    # no-source stop. Never Sydney (already asserted tour-wide above).
    import landmark_claim_gate as _lgc
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op is None:
        ok &= _check("Opera House stop delivered", False, "missing")
    else:
        pr = _prose(op)
        fold = (pr.encode("ascii", "ignore").decode()).lower()
        saigon_ok = ("1900" in pr) or ("ferret" in fold) or ("french colonial" in fold) \
            or ("municipal theatre" in fold)
        no_source = not _lgc._has_real_sentence(op[2]) or "no " in fold and "source" in fold
        ok &= _check("Opera House is the Saigon one (1900 / Ferret / French colonial) or has no source",
                     saigon_ok or no_source, _first_two_sentences(pr))

    # Bug 2: Post Office not empty.
    po = next((b for b in blocks if "post office" in b[1].lower()), None)
    if po is None:
        ok &= _check("Post Office stop delivered", False, "missing")
    else:
        ok &= _check("Post Office is not empty", _lgc._has_real_sentence(po[2]),
                     _first_two_sentences(_prose(po)))

    # No stop empty at all.
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--saigon" in sys.argv:
        sys.exit(0 if phase_saigon() else 1)
    sys.exit("usage: run_local878_live.py --saigon")
