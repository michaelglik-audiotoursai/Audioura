#!/usr/bin/env python3
"""run_local870_live.py: LOCAL-870 live, budget-enforced proof (Mac-local).

Runs IN-PROCESS from this worktree against this task's OWN postgres
(docker-compose.local870-proof.yml, :55970). The shared audioura-* containers,
the shared dev DB (:5433) and the live DB are never touched. TTS is NOT called:
requests.post to the polly URL is replaced by a capture, so the payload that WOULD
go to Beta's polly-tts is inspected.

  --sophia   wave-28 Sophia request (7 user stops) + content rating of the result
             + modernized ZIP / TTS payload (emoji) + "A Star is Born" pin
  --import10 the LOCAL-867 10-stop import (saved preview) -> Opera House, name bridges

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-870 TASK_BUDGET_USD=0.70 \\
  PAID_API_LOG=$PWD/_local870_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local870_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-870 PYTHONPATH=$PWD/_meter \\
  python3 run_local870_live.py --sophia      # then --import10

Run logs go to ./_local870_meterlogs/ (never committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-870":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-870 (see docstring)")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.70") or "0.70")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55970/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55970"),
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

_METER_DIR = os.path.join(_HERE, "_local870_meterlogs")
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

    tmp = tempfile.mkdtemp(prefix="l870_")
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
    job = "l870" + tag
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


def phase_sophia():
    print("\n[SOPHIA] " + SOPHIA_REQUEST + f"  ({len(SOPHIA_STOPS)} user stops)", flush=True)
    before = _meter_total()
    text, log = _generate(SOPHIA_REQUEST, "", SOPHIA_STOPS, len(SOPHIA_STOPS), "sophia")
    blocks = _blocks(text)
    ok = True
    ok &= _check("7/7 delivered", len(blocks) == 7, [t for _, t, _ in blocks])

    # item 3: A Star is Born: a user-source pin or no pin, never the MODEL coordinate
    star = next((b for b in blocks if "star is born" in b[1].lower()), None)
    if star is None:
        ok &= _check("A Star is Born delivered", False, "missing")
    else:
        cm = _COORD_RE.search(star[2])
        if not cm:
            ok &= _check("A Star is Born: announced with no pin", True, "no Coordinates line")
        else:
            got = (float(cm.group(1)), float(cm.group(2)))
            near_model = _hav_m(got, MODEL_STAR) <= 5.0
            ok &= _check("A Star is Born: not the model coordinate", not near_model,
                         f"pin {got}, {_hav_m(got, MODEL_STAR):.0f} m from the model's {MODEL_STAR}")
    for l in log.splitlines():
        if "LOCAL-870" in l or "A Star is Born" in l and ("pin" in l.lower() or "coordinate" in l.lower()):
            print("     " + l.strip()[:200], flush=True)

    # item 2: emoji
    print("   -- emoji: the real modernized function, TTS captured --", flush=True)
    files, payloads, mlog = _through_modernized(text, "sophia")
    raw_has = bool(EMOJI_RE.search(text))
    print(f"   emoji present in the generator text (display): {raw_has}", flush=True)
    ok &= _check("audio_N.txt files produced", len(files) == 7, sorted(files))
    bad_txt = [n for n, t in files.items() if EMOJI_RE.search(t)]
    ok &= _check("no emoji in any audio_N.txt", not bad_txt, bad_txt or "clean")
    bad_tts = [i + 1 for i, t in enumerate(payloads) if EMOJI_RE.search(t)]
    ok &= _check("no emoji in any TTS payload", payloads and not bad_tts,
                 f"{len(payloads)} payloads; bad={bad_tts}")
    strip_lines = [l for l in mlog.splitlines() if "TTS emoji strip" in l]
    ok &= _check("log line '[LOCAL-863] TTS emoji strip' present",
                 bool(strip_lines) or not raw_has, strip_lines[:2] or "no emoji to strip")

    # item 1: the rater, for real
    print("   -- content rating (real gpt-4.1-mini) --", flush=True)
    import tour_content_rating as tcr
    rating, detail = tcr.rate_text("Sophia's biking tour in Ho Chi Minh City", text, 7)
    print(f"   rating={rating}  reason={detail.get('reason')}", flush=True)
    ok &= _check("rater gives General", rating == "general", rating)

    spent = _meter_total() - before
    print(f"\n   meter (Sophia): ${spent:.4f}; task total ${_meter_total():.4f} of "
          f"${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SOPHIA {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def phase_import10():
    d = json.load(open(PREVIEW_JSON))
    stops = d["stops"]
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL870_IMPORT_RESERVE_USD", "0.26"))
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    print(f"\n[IMPORT10] {len(stops)} stops from the saved LOCAL-867 preview", flush=True)
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter("LOCAL-870", cap_usd=HARD_CAP_USD - before)
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
                             "user_id": "local870",
                             "request_string": "a walking tour of my Ho Chi Minh City itinerary",
                             "user_stops": stops}))
    import generate_tour_text_service as svc
    forced, err = svc.validate_stops(cap.get("stops") or [])
    text, log = _generate("Ho Chi Minh City, Vietnam", "walking", forced, 10, "import10")
    blocks = _blocks(text)
    ok = _check("10/10 delivered", len(blocks) == 10, len(blocks))

    # item 4: Opera House
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op is None:
        ok &= _check("Saigon Opera House delivered", False, "missing")
    else:
        prose = " ".join(l for l in op[2].split("\n")
                         if l.strip() and not re.match(r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address):", l.strip()))
        n_sent = len(re.findall(r"[.!?](?:\s|$)", prose))
        thin = "before you go in" in prose.lower() or "architectural beauty" in prose.lower()
        print(f"   Opera House prose ({n_sent} sentences, {len(prose.split())} words):\n     {prose[:700]}", flush=True)
        ok &= _check("Opera House is not the 3-sentence thin form", n_sent >= 5 and not thin,
                     f"{n_sent} sentences, thin_markers={thin}")
    kind_lines = [l.strip()[:160] for l in log.splitlines()
                  if "opera" in l.lower() and "LOCAL-862" in l]
    for l in kind_lines[:4]:
        print("     " + l, flush=True)

    # item 5: name bridges
    bad = [(n, t) for n, t, b in blocks
           if re.search(r"(?i)(?:takes its name|comes) from the word .{0,3}nguyen", b)]
    ok &= _check("no 'name from the word Nguyen' bridge", not bad, bad or "clean")
    for n, t, b in blocks:
        if re.search(r"(?i)book|nguy[eễ]n|caf[eé] apart", t):
            m = re.search(r"(?i)[^.]*\b(?:takes its name|named after)[^.]*\.", b)
            print(f"   Stop {n} {t}: bridge = {m.group(0).strip() if m else '(none)'}", flush=True)

    # emoji / rainbow regression (Thi Bar is a stop here too)
    try:
        _lrm.uninstall()
    except Exception:
        pass
    print(f"\n   meter (import10): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== IMPORT10 {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--sophia" in sys.argv:
        sys.exit(0 if phase_sophia() else 1)
    if "--import10" in sys.argv:
        sys.exit(0 if phase_import10() else 1)
    sys.exit("usage: run_local870_live.py --sophia | --import10")
