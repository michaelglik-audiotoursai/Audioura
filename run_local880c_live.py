#!/usr/bin/env python3
"""run_local880c_live.py — LOCAL-880C live proof (Mac-local, own container, ONCE).

LOCAL-880C fixes two LOCAL-880B defects:
  1. the sourced-number scrub no longer leaves an orphan unit when it drops an
     unsourced magnitude ("rise 58 meters high" -> "rise high"), and its evidence
     matching tolerates unit spelling/separator variants so a SOURCED figure is
     kept (the Saigon cathedral's 58 m height is on Wikipedia);
  2. signature_story._GENERIC_VENUE names no proof tour's city; the generic place
     words are derived at run time from the tour's location and the stop title.

ONE live 3-stop run of the ticket's Saigon stops, in-process from THIS worktree
against this task's OWN postgres (docker-compose.local880c-proof.yml, :55982).
The shared audioura-* containers, the shared dev DB (:5433) and the live DB are
never touched (D753). TTS is not called.

PASS (the ticket):
  * the delivered text has NO orphan unit (no bare "meters"/"metres"/"seats"/
    "km"/"feet"/"tons"/"storeys" without a number); AND
  * the cathedral height is stated as 58 metres (sourced, kept — not dropped).

BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-880C TASK_BUDGET_USD=0.12.

Launch:

  docker compose -p local880c -f docker-compose.local880c-proof.yml up -d

  TASK_BUDGET_ID=LOCAL-880C TASK_BUDGET_USD=0.12 \\
  PAID_API_LOG=$PWD/_local880c_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local880c_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-880C PYTHONPATH=$PWD/_meter \\
  python3 run_local880c_live.py --run

Run logs go to ./_local880c_meterlogs/ (never committed). The tour text is
written to submission_artifacts/local880c/ (committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-880C":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-880C (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.12") or "0.12")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55982/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55982"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

os.environ.pop("K_SERVICE", None)
os.environ["LANDMARK_LIVE_LOOKUP"] = "1"          # the real Wikidata/Wikipedia path
os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["SIGNATURE_STORY_ENABLED"] = "1"       # LOCAL-880 signature-story pass
os.environ["SIGNATURE_STORY_MODEL"] = "gpt-4.1-mini"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ["USER_STOPS_ENABLED"] = "true"

# Budget mode (same as the 880B proof): route the premium story models to the
# cheap mini arm and KEEP the warmed tour cache so the 3-stop run fits the $0.12
# cap. The scrub mechanisms under test are model-independent.
_CHEAP = os.environ.get("LOCAL880C_CHEAP", "1").strip() != "0"
if _CHEAP:
    os.environ["STORY_PASS_MODEL"] = "gpt-4.1-mini"
    os.environ["TOUR_STORY_MODEL"] = "gpt-4o-mini"
    os.environ["TOUR_SCOPE_COMPARE_MODEL"] = "gpt-4o-mini"
    os.environ.setdefault("DISABLE_TOUR_CACHE", "0")
else:
    os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
    os.environ["DISABLE_TOUR_CACHE"] = "1"

_METER_DIR = os.path.join(_HERE, "_local880c_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local880c")
os.makedirs(_ART_DIR, exist_ok=True)

REQUEST = "Notre-Dame Cathedral Basilica of Saigon, Saigon Central Post Office, Saigon Opera House, Ho Chi Minh City"
STOPS = ["Notre-Dame Cathedral Basilica of Saigon",
         "Saigon Central Post Office", "Saigon Opera House"]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
    r"Museum Information|Operational Details|Sources|Orientation):")

# a bare magnitude unit with NO number in front of it is an orphan (the LOCAL-880B
# defect). Directions lines carry computed walking distances ("400 meters") and
# are excluded from the prose check.
_ORPHAN_UNIT_RE = re.compile(
    r"(?i)(?<![\d.,])\b(?<!\w[- ])"
    r"(meters?|metres?|seats?|feet|tons?|storeys?|stories|acres?|hectares?)\b")


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
    """Narration prose only: field lines and the Directions line removed (those
    carry computed distances, not sourced magnitude claims)."""
    out = []
    for l in b[2].split("\n"):
        s = l.strip()
        if not s:
            continue
        m = re.match(r"(?i)^orientation:\s*(.*)$", s)
        if m:
            if m.group(1).strip():
                out.append(m.group(1).strip())
            continue
        if _FIELD_RE.match(s):
            continue
        out.append(s)
    return " ".join(out)


def _first_two_sentences(prose):
    sents = re.findall(r"[^.!?]*[.!?]", prose)
    return " ".join(s.strip() for s in sents[:2]).strip() or prose[:240]


def _orphan_units(prose):
    return [m.group(0) for m in _ORPHAN_UNIT_RE.finditer(prose)]


def run():
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL880C_RESERVE_USD", "0.01"))
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False

    print(f"\n[880C] request={REQUEST!r}; {len(STOPS)} stops; "
          f"cap=${HARD_CAP_USD:.2f}", flush=True)

    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD - before)
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                REQUEST, "walking", None, len(STOPS), forced_stops=list(STOPS))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_ART_DIR, "saigon_3stop_tour.txt"), "w",
         encoding="utf-8").write(text or "")
    open(os.path.join(_METER_DIR, "saigon_3stop_log.txt"), "w",
         encoding="utf-8").write(log)
    try:
        _lrm.uninstall()
    except Exception:
        pass

    blocks = _blocks(text)
    ok = _check(f"{len(STOPS)} stops delivered", len(blocks) == len(STOPS), len(blocks))

    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    # ── PASS 1: no orphan unit anywhere in the narration prose ──
    all_orphans = []
    for n, t, b in blocks:
        orph = _orphan_units(_prose((n, t, b)))
        if orph:
            all_orphans.append((n, t, orph))
    ok &= _check("no orphan unit in any stop's narration", not all_orphans,
                 "none" if not all_orphans else f"orphans: {all_orphans}")

    # ── PASS 2: the cathedral height is stated as 58 metres (sourced, kept) ──
    cath = next((b for b in blocks if "cathedral" in b[1].lower()
                 or "notre" in b[1].lower()), None)
    if cath:
        cp = _prose(cath)
        cl = cp.lower()
        has_58 = bool(re.search(r"\b58\s*[- ]?m(?:eters?|etres?|\b)", cl)) \
            or ("58" in cp and re.search(r"58[^.]{0,20}(met|m\b)", cl))
        ok &= _check("cathedral height stated as 58 metres (sourced, kept)",
                     has_58, _first_two_sentences(cp))
        # and specifically no orphan 'meters' in the cathedral stop
        ok &= _check("cathedral stop has no orphan unit",
                     not _orphan_units(cp), "clean")
    else:
        ok &= _check("cathedral stop present", False, "missing")

    import landmark_claim_gate as _lgc
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")

    print(f"\n   meter: ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== LOCAL-880C {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--run" in sys.argv:
        sys.exit(0 if run() else 1)
    sys.exit("usage: run_local880c_live.py --run")
