#!/usr/bin/env python3
"""run_local873c_live.py — LOCAL-873C live proof (Mac-local, own container).

ONE live 10-stop run of Michael's Saigon-centre list, in-process from THIS
worktree against this task's OWN postgres (docker-compose.local873c-proof.yml,
:55975). The shared audioura-* containers, the shared dev DB (:5433) and the
live DB are never touched. TTS is not called.

Proves the LOCAL-873C fix on the DELIVERED text — the thin-stop rebuild is now
NARRATED, not pasted web copy:
  * Book Street carries >= 5 SPOKEN sentences, no Orientation repeat, and no
    raw-copy fragment ("Known as", list run-ons);
  * the 873B criteria still hold: Pier and City Hall each >= 3 sourced specifics,
    every stop >= 4 content sentences, and no banned place/figure
    (Thủ Dầu Một, Bình Mỹ, Sydney, Utzon, "Saigon centre landmarks").

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-873C TASK_BUDGET_USD=0.25 \\
  PAID_API_LOG=$PWD/_local873c_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local873c_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-873C PYTHONPATH=$PWD/_meter \\
  python3 run_local873c_live.py --saigon

Run logs go to ./_local873c_meterlogs/ (never committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-873C":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-873C (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.25") or "0.25")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55975/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55975"),
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

_METER_DIR = os.path.join(_HERE, "_local873c_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
BANNED = ["Thủ Dầu Một", "Bình Mỹ", "Sydney", "Utzon", "Saigon centre landmarks"]
# Raw-copy fragments the narrated rebuild must never ship on Book Street.
RAW_FRAGMENTS = ["Known as", "newspapers area", "magazine area",
                 "old book exchange, book exhibition area"]

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


def _orientation(b):
    for l in b[2].split("\n"):
        s = l.strip()
        if s.lower().startswith("orientation:"):
            return s.partition(":")[2].strip()
    return ""


def _prose(b):
    """Delivered CONTENT prose of a stop: narration paragraphs only — NOT the
    Orientation line, field lines, Directions or Sources."""
    return " ".join(l for l in b[2].split("\n") if l.strip() and not re.match(
        r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
        r"Orientation|Museum Information|Operational Details|Sources):", l.strip()))


def _sentences(prose):
    return [s.strip() for s in re.findall(r"[^.!?]*[.!?]", prose) if s.strip()]


def _find(blocks, *needles):
    for b in blocks:
        tl = b[1].lower()
        asc = b[1].encode("ascii", "ignore").decode().lower()
        if any(n.lower() in tl or n.lower() in asc for n in needles):
            return b
    return None


def _norm(s):
    import unicodedata
    pre = str(s).replace("đ", "d").replace("Đ", "D")
    nf = unicodedata.normalize("NFKD", pre)
    nf = "".join(c for c in nf if not unicodedata.combining(c))
    nf = re.sub(r"[^\w\s]", " ", nf.lower())
    return " ".join(nf.split())


def _orientation_dup(prose, orientation):
    or_norms = [_norm(s) for s in _sentences(orientation) if len(_norm(s)) >= 12]
    for s in _sentences(prose):
        n = _norm(s)
        if not n:
            continue
        for on in or_norms:
            if n == on or (len(n) >= 12 and (n in on or on in n)):
                return s
    return ""


def phase_saigon():
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL873C_RESERVE_USD", "0.05"))
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

    import thin_stop_search as _ts
    blocks = _blocks(text)
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered", len(blocks) == len(forced), len(blocks))

    # ---- escalation + post-narration telemetry --------------------------------
    print("\n--- [LOCAL-873 / 873B / 873C] escalation + rebuild telemetry ---", flush=True)
    for ln in (re.findall(r"\[LOCAL-873\].*thin.*", log)
               + re.findall(r"\[LOCAL-873B\].*", log)
               + re.findall(r"\[LOCAL-873C\].*", log)):
        print("  " + ln, flush=True)
    print("----------------------------------------------------------------\n", flush=True)

    # ---- per-stop content sentence counts; no stop under 4 content sentences --
    print("--- per-stop content body (sentence count) ---", flush=True)
    thin4 = []
    for n, t, b in blocks:
        ss = _sentences(_prose((n, t, b)))
        if len(ss) < 4:
            thin4.append(f"{t}({len(ss)})")
        print(f"Stop {n} [{t}]: {len(ss)} content sentence(s) | {(ss[0] if ss else '')[:80]}", flush=True)
    print("-----------------------------------------------\n", flush=True)
    ok &= _check("no stop has fewer than 4 content sentences", not thin4, thin4 or "all >= 4")

    # ---- Book Street: >= 5 SPOKEN sentences, no Orientation repeat, no raw copy
    bs = _find(blocks, "Nguyễn Văn Bình Book Street", "Nguyen Van Binh Book Street", "Book Street")
    if bs is None:
        ok &= _check("Book Street delivered", False, "missing")
    else:
        bprose = _prose(bs)
        bss = _sentences(bprose)
        ok &= _check("Book Street has >= 5 spoken sentences", len(bss) >= 5, len(bss))
        dup = _orientation_dup(bprose, _orientation(bs))
        ok &= _check("Book Street body does not repeat the Orientation",
                     not dup, dup[:80] if dup else "no repeat")
        frags = [f for f in RAW_FRAGMENTS if f.lower() in bprose.lower()]
        ok &= _check("Book Street has no raw-copy fragment", not frags, frags or "none")
        print("   Book Street content sentences:", flush=True)
        for s in bss:
            print(f"     · {s}", flush=True)

    # ---- Pier + City Hall: >= 3 sourced specifics in the delivered body -------
    for label, needles in (("Bạch Đằng Pier", ("Bạch Đằng", "Bach Dang")),
                           ("Ho Chi Minh City Hall",
                            ("Ho Chi Minh City Hall", "People's Committee"))):
        blk = _find(blocks, *needles)
        if blk is None:
            ok &= _check(f"{label} delivered", False, "missing")
            continue
        ss = _sentences(_prose(blk))
        spec = _ts.count_specifics(ss)
        ok &= _check(f"{label} has >= 3 sourced specifics in the delivered body",
                     spec >= 3, spec)

    # ---- no banned name anywhere in the delivered text ------------------------
    hits = sorted({w for w in BANNED if w.lower() in (text or "").lower()})
    ok &= _check("no stop text names a banned place/figure", not hits, hits or "none")

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--saigon" in sys.argv:
        sys.exit(0 if phase_saigon() else 1)
    sys.exit("usage: run_local873c_live.py --saigon")
