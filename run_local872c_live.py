#!/usr/bin/env python3
"""run_local872c_live.py: LOCAL-872C live (wiki evidence -> narrator), budget-enforced proof (Mac-local).

Runs IN-PROCESS from this worktree against this task's OWN postgres
(docker-compose.local872c-proof.yml, :55973). The shared audioura-* containers,
the shared dev DB (:5433) and the live DB are never touched. TTS is NOT called:
requests.post to the polly URL is replaced by a capture, so the payload that WOULD
go to Beta's polly-tts is inspected.

  --import10 Michael's 10-stop HCMC list (saved LOCAL-867 preview): zero undisclosed
             UNSOURCED claims, no Miss Saigon, Opera House >= 5 sentences + sourced facts
  --hanoi    ordinary walking tour "Old Quarter walk, Hanoi" (4 stops)

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-872 TASK_BUDGET_USD=0.40 \\
  PAID_API_LOG=$PWD/_local872_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local872_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-872 PYTHONPATH=$PWD/_meter \\
  python3 run_local872_live.py --sophia      # then --import10

Run logs go to ./_local872_meterlogs/ (never committed).
"""
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import zipfile

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

if os.environ.get("TASK_BUDGET_ID") not in ("LOCAL-872C",):
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-872B (see docstring)")
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

os.environ.pop("K_SERVICE", None)       # setting it disarms the meter's whole-task cap
os.environ["LANDMARK_LIVE_LOOKUP"] = ""
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

_METER_DIR = os.path.join(_HERE, "_local872c_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

SOPHIA_REQUEST = "Sophia's biking tour in Ho Chi Minh City, Vietnam"
SOPHIA_STOPS = [
    "Longan", "Rambutan", "Crazy street", "An Spa",
    "The LGBT bar \U0001F308Thi Bar Saigon", "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm",
]
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
MODEL_STAR = (10.7762, 106.6956)


def _hav_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


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


def _generate(location, tour_type, stops, n, tag):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                location, tour_type, None, n, forced_stops=list(stops))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_METER_DIR, f"{tag}_tour.txt"), "w").write(text or "")
    open(os.path.join(_METER_DIR, f"{tag}_log.txt"), "w").write(log)
    return text or "", log


def _through_modernized(text, tag):
    """Run the REAL modernized service function with TTS replaced by a capture.
    Returns (zip audio_N.txt dict, captured TTS payload texts, stdout log)."""
    import tour_generation_modernized as tgm
    import requests
    payloads = []

    class _R:
        status_code = 200
        content = b"ID3fake"

    def _fake_post(url, headers=None, json=None, timeout=None, **kw):
        payloads.append((json or {}).get("text", ""))
        return _R()

    tmp = tempfile.mkdtemp(prefix="l872_")
    old_dir, old_post = tgm.TOURS_DIR, requests.post
    tgm.TOURS_DIR = tmp
    requests.post = _fake_post
    try:
        import geocode_stops
        geocode_stops.correct_stops = lambda texts, hint, tour_anchor=None: (texts, [])
        geocode_stops.geocode = lambda *a, **k: None
    except Exception:
        pass
    src = os.path.join(tmp, "tour.txt")
    open(src, "w", encoding="utf-8").write(text)
    job = "l872" + tag
    tgm.ACTIVE_JOBS[job] = {"status": "queued"}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            tgm.generate_modernized_tour_async(job, src)
        info = tgm.ACTIVE_JOBS.get(job)
        zname = (info or {}).get("output_zip")
        files = {}
        if zname:
            with zipfile.ZipFile(os.path.join(tmp, zname)) as z:
                for n in z.namelist():
                    if re.fullmatch(r"audio_\d+\.txt", n):
                        files[n] = z.read(n).decode("utf-8")
        return files, payloads, buf.getvalue()
    finally:
        tgm.TOURS_DIR = old_dir
        requests.post = old_post


def _install_evidence_tap(tag):
    """Record, without changing behaviour, the text the LOCAL-872 gate was handed
    and the research evidence it checked against (the 'research log')."""
    import landmark_claim_gate as lg
    orig = lg.filter_tour_text
    calls = []

    def tap(tour_text, **kw):
        if not calls:
            open(os.path.join(_METER_DIR, f"{tag}_pregate_tour.txt"), "w").write(tour_text or "")
            json.dump({str(k): v for k, v in (kw.get("stop_evidence") or {}).items()},
                      open(os.path.join(_METER_DIR, f"{tag}_evidence.json"), "w"), indent=1)
            json.dump({str(k): v for k, v in (kw.get("stop_titles") or {}).items()},
                      open(os.path.join(_METER_DIR, f"{tag}_titles.json"), "w"), indent=1)
            json.dump({"known": {str(k): v for k, v in (kw.get("stop_known") or {}).items()},
                       "skip": list(kw.get("skip_stops") or [])},
                      open(os.path.join(_METER_DIR, f"{tag}_known.json"), "w"), indent=1)
        calls.append(1)
        return orig(tour_text, **kw)
    lg.filter_tour_text = tap


def _unsourced_check(tag):
    """Log vs delivered text, with the LOCAL-864 checker."""
    import subprocess
    log = os.path.join(_METER_DIR, f"{tag}_log.txt")
    txt = os.path.join(_METER_DIR, f"{tag}_tour.txt")
    r = subprocess.run([sys.executable, "submission_artifacts/local864/check_unsourced_vs_text.py", log, txt],
                       capture_output=True, text=True, cwd=_HERE)
    print(r.stdout, flush=True)
    m = re.search(r"undisclosed in delivered text: (\d+)", r.stdout)
    return (int(m.group(1)) if m else -1), r.stdout


def _recheck(tag, text, location):
    """Independent pass: re-run the gate over the DELIVERED text against the saved
    research evidence; a correct delivery has nothing left to drop."""
    import landmark_claim_gate as lg
    ev = json.load(open(os.path.join(_METER_DIR, f"{tag}_evidence.json")))
    ti = json.load(open(os.path.join(_METER_DIR, f"{tag}_titles.json")))
    kn = json.load(open(os.path.join(_METER_DIR, f"{tag}_known.json")))
    _o, rep = lg.filter_tour_text(
        text, stop_evidence={int(k): v for k, v in ev.items()},
        stop_titles={int(k): v for k, v in ti.items()},
        stop_known={int(k): v for k, v in kn["known"].items()},
        skip_stops=kn["skip"], location=location)
    for r in rep["removed"]:
        print(f"     LEFT: stop {r['stop']} {r['reason']}: {r['sentence'][:140]}", flush=True)
    return _check("delivered text re-checked against the evidence: nothing left to drop",
                  rep["dropped"] == 0, f"{rep['dropped']} (business user stops are 855D's; counted here for visibility)")


def _gate_log_lines(log):
    return [l.rstrip()[:230] for l in log.splitlines() if "LOCAL-872" in l or l.strip().startswith("UNSOURCED: '")]


def phase_import10(only=None):
    d = json.load(open(PREVIEW_JSON))
    stops = d["stops"]
    if only:   # budget-limited re-proof of ONE stop of the list
        stops = [x for x in stops if only.lower() in json.dumps(x, ensure_ascii=False).lower()]
        print(f"[ONLY {only!r}] {len(stops)} stop(s)", flush=True)
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL872_IMPORT_RESERVE_USD", "0.24" if not only else "0.05"))
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    print(f"\n[IMPORT10] {len(stops)} stops from the saved LOCAL-867 preview", flush=True)
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD - before)
    import importlib
    import tour_orchestrator_service as orch
    importlib.reload(orch)
    import entitlements
    allow = lambda *a, **k: {"allowed": True, "error_code": None, "level": "L1",  # noqa
                             "clamped_stops": k.get("requested_stops") or 10, "mode": None}
    entitlements.check_operation = allow
    orch.check_operation = allow
    orch.check_tour_quota = lambda uid, stops=10: {"allowed": True, "clamped_stops": stops,
                                                   "used": 0, "remaining": 100}
    orch.track_user_tour = lambda *a, **k: None
    orch.log_job_update = lambda *a, **k: None
    cap = {}

    def _thread(job_id, location, tour_type, total_stops, user_id=None, request_string=None,
                language='en', persona=None, is_test=None, stops=None, mode=None):
        cap["stops"], cap["total"] = stops, total_stops
    orch.orchestrate_tour_async = _thread
    orch.app.testing = True
    with contextlib.redirect_stdout(io.StringIO()):
        orch.app.test_client().post(
            "/generate-complete-tour", content_type="application/json",
            data=json.dumps({"location": "Ho Chi Minh City, Vietnam", "tour_type": "walking",
                             "user_id": "local872",
                             "request_string": "a walking tour of my Ho Chi Minh City itinerary",
                             "user_stops": stops}))
    import generate_tour_text_service as svc
    forced, err = svc.validate_stops(cap.get("stops") or [])
    _tag = (os.environ.get("RUN_TAG") or "import10") if not only else re.sub(r"\W+", "", only.lower())
    _install_evidence_tap(_tag)
    text, log = _generate("Ho Chi Minh City, Vietnam", "walking", forced, len(forced), _tag)
    blocks = _blocks(text)
    ok = _check(f"{len(forced)}/{len(forced)} delivered", len(blocks) == len(forced), len(blocks))
    for l in _gate_log_lines(log):
        print("     " + l, flush=True)

    ok &= _check("no 'Miss Saigon' in the delivered text", "miss saigon" not in text.lower(),
                 "clean" if "miss saigon" not in text.lower() else "PRESENT")
    n_bad, _out = _unsourced_check(_tag)
    ok &= _check("zero undisclosed UNSOURCED claims (log vs text)", n_bad == 0, n_bad)
    ok &= _recheck(_tag, text, "Ho Chi Minh City, Vietnam")

    # 872B: the famous true facts must survive (sourced from Wikipedia, or disclosed)
    for key, facts in (("notre", ("1863", "1880")), ("independence", ("Thụ", "Thu"))):
        b = next((b for b in blocks if key in b[1].lower()), None)
        if b is None:
            print(f"   (no '{key}' stop in this run)", flush=True)
            continue
        low = b[2]
        got = [f for f in facts if f in low]
        pre = open(os.path.join(_METER_DIR, f"{_tag}_pregate_tour.txt"), encoding="utf-8").read()
        pb = next((x for x in _blocks(pre) if key in x[1].lower()), None)
        was = [f for f in facts if pb and f in pb[2]]
        if was:     # the gate's job: a fact the narrator wrote must survive
            ok &= _check(f"{key}: famous fact written by the narrator survives the gate ({'/'.join(facts)})",
                         bool(got), got or "DROPPED")
        else:
            print(f"   [INFO] {key}: the narrator did not write {'/'.join(facts)} this run "
                  f"(pre-gate text lacks it; the gate dropped nothing)", flush=True)
        for m in re.finditer(r"[^.\n]*(?:%s)[^.\n]*\." % "|".join(facts), low):
            print("       " + m.group(0).strip()[:220], flush=True)
    # ---- 872C acceptance (every run) ----
    def _prose(b):
        return " ".join(l for l in b[2].split("\n") if l.strip() and not re.match(
            r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address):", l.strip()))
    _fold = lambda x: "".join(c for c in __import__("unicodedata").normalize("NFD", x) if not __import__("unicodedata").combining(c)).replace("\u0111", "d").lower()
    _op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if _op:
        pr = _fold(_prose(_op))
        ok &= _check("Opera House names Olivier/Guichard/Ferret and 1900",
                     any(n in pr for n in ("olivier", "guichard", "ferret")) and "1900" in pr,
                     [n for n in ("olivier", "guichard", "ferret", "1900") if n in pr])
    _ip = next((b for b in blocks if "independence" in b[1].lower()), None)
    if _ip:
        pr = _fold(_prose(_ip))
        ok &= _check("Independence Palace names Ngo Viet Thu + 1960s dates, no 1885",
                     "ngo viet thu" in pr and re.search(r"196[2-6]", pr) and "1885" not in pr,
                     [x for x in ("ngo viet thu", "1962", "1966", "1885") if x in pr])
        print("       " + _prose(_ip)[:700], flush=True)
    _nd = next((b for b in blocks if "notre" in b[1].lower()), None)
    if _nd:
        pr = _prose(_nd)
        ok &= _check("Notre-Dame states 1863-1880", "1863" in pr and "1880" in pr,
                     [x for x in ("1863", "1880") if x in pr])
    import landmark_claim_gate as _lgc
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")
    open(os.path.join(_METER_DIR, f"{_tag}_delivered.txt"), "w", encoding="utf-8").write(text)
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op is None:
        ok &= _check("Saigon Opera House delivered", False, "missing")
    else:
        prose = " ".join(l for l in op[2].split("\n")
                         if l.strip() and not re.match(r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address):", l.strip()))
        n_sent = len(re.findall(r"[.!?](?:\s|$)", prose))
        print(f"   Opera House prose ({n_sent} sentences):\n     {prose[:900]}", flush=True)
        ok &= _check("Opera House >= 5 sentences", n_sent >= 5, n_sent)
        ev = json.load(open(os.path.join(_METER_DIR, f"{_tag}_evidence.json")))
        titles = json.load(open(os.path.join(_METER_DIR, f"{_tag}_titles.json")))
        k = next((k for k, t in titles.items() if "opera" in t.lower()), None)
        evtxt = " ".join(ev.get(k, [])).lower() if k else ""
        _pre = open(os.path.join(_METER_DIR, f"{_tag}_pregate_tour.txt"), encoding="utf-8").read()
        _pb = next((x for x in _blocks(_pre) if "opera" in x[1].lower()), None)
        for fact in ("1900", "ferret"):
            if _pb and fact in _pb[2].lower():
                ok &= _check(f"sourced fact '{fact}' written by the narrator survives the gate",
                             fact in prose.lower(), "in text" if fact in prose.lower() else "DROPPED")
            elif fact in evtxt:
                print(f"   [INFO] '{fact}' is in the evidence but the narrator did not write it", flush=True)
            else:
                print(f"   (fact '{fact}' is not in this run's Opera House research; not required)", flush=True)
    try:
        _lrm.uninstall()
    except Exception:
        pass
    print(f"\n   meter (import10): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== IMPORT10 {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def phase_hanoi():
    before = _meter_total()
    if before + 0.10 > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + $0.10 reserve > cap ${HARD_CAP_USD:.2f}")
        return False
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD - before)
    _install_evidence_tap("hanoi")
    text, log = _generate("Old Quarter walk, Hanoi", "walking", [], 4, "hanoi")
    blocks = _blocks(text)
    ok = _check("4 stops delivered", len(blocks) == 4, [t for _, t, _ in blocks])
    for l in _gate_log_lines(log):
        print("     " + l, flush=True)
    n_bad, _out = _unsourced_check("hanoi")
    ok &= _check("zero undisclosed UNSOURCED claims (log vs text)", n_bad == 0, n_bad)
    ok &= _recheck("hanoi", text, "Old Quarter walk, Hanoi")
    for n, t, b in blocks:
        _ns = len(re.findall(r"[.!?](?:\s|$)", b))
        print(f"   Stop {n} {t}: {_ns} sentences", flush=True)
    try:
        _lrm.uninstall()
    except Exception:
        pass
    print(f"\n   meter (hanoi): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== HANOI {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--only" in sys.argv:
        sys.exit(0 if phase_import10(only=sys.argv[sys.argv.index("--only") + 1]) else 1)
    if "--opera" in sys.argv:
        sys.exit(0 if phase_import10(only="opera") else 1)
    if "--import10" in sys.argv:
        sys.exit(0 if phase_import10() else 1)
    if "--hanoi" in sys.argv:
        sys.exit(0 if phase_hanoi() else 1)
    sys.exit("usage: run_local872c_live.py --import10 | --hanoi")
