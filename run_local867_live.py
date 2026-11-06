#!/usr/bin/env python3
"""run_local867_live.py: LOCAL-867 live, budget-enforced proof (Mac-local).

Two phases, run separately so a preview problem never costs a generation:

  --preview   POST /preview-stops on Michael's EXACT string, city "Ho Chi Minh City"
              (the real endpoint via the Flask test client, live resolvers, no LLM,
              no DB). PASS: 10 stops in order; "Cathedral" -> Notre-Dame Cathedral
              Saigon; "Post Office" -> Saigon Central Post Office; "Book Street" ->
              Nguyen Van Binh; every pin within 150 m of the real place; cost reported.
              Writes _local867_meterlogs/preview.json.

  --generate  Feed THAT saved preview to the REAL orchestrator intake
              (/generate-complete-tour: user_stops objects -> user-stops strings,
              logs "[LOCAL-867] imported N stops"), then the generator's own
              validate_stops, then generate_tour_text(forced_stops=...) for a walking
              tour. PASS: 10/10 delivered in the given order, every pin kept, D760
              layers (disclosed legends, stops about their venue, no thin stops).

Generator runs IN-PROCESS from this worktree (the 859B/863R pattern) against this
task's OWN postgres (docker-compose.local867-proof.yml, :55967). The shared
audioura-* containers, the shared dev DB (:5433) and the live DB are never touched.

Launch (the meter's sitecustomize reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-867 TASK_BUDGET_USD=0.50 \\
  PAID_API_LOG=$PWD/_local867_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local867_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-867 PYTHONPATH=$PWD/_meter \\
  python3 run_local867_live.py --preview     # then --generate

Run logs go to ./_local867_meterlogs/ (never committed).
"""
import contextlib
import io
import json
import math
import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))


def _load_dotenv():
    """API keys only. DB_* from .env (if any) are overridden below."""
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-867":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-867 (see docstring)")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# ── OWN database (D753) ──────────────────────────────────────────────────────
_OWN_DB = "postgresql://admin:password123@localhost:55967/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55967"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

# K_SERVICE is deliberately NOT set (863R set it for a "cloud-like" env). Nothing
# in the generator reads it, and setting it DISARMS the LOCAL-827 meter-log
# whole-task cap (paid_api_meter._meter_log_cap_armed), which is the only cap
# that stops an in-progress run on non-grounded (OpenAI/Serper) calls.
os.environ.pop("K_SERVICE", None)
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

_METER_DIR = os.path.join(_HERE, "_local867_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_METER_DIR, "preview.json")

MICHAEL = ("Cathedral → Post Office → Book Street → Independence Palace → "
           "War Remnants Museum → Opera House/Đồng Khởi → City Hall & Nguyễn Huệ → "
           "Café Apartments 42 → Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar")
CITY = "Ho Chi Minh City"
LIMIT_M = 150.0

# Reference location of the REAL place, with provenance (none of these is the
# resolver's own output for that stop):
#   OSM  = Nominatim reverse/search polygon centroid for the real object
#   GGL  = Google Places (Serper /places), a separate query from the resolver's
#   863R/859B = the pins earlier tasks verified against the venue
TRUTH = [
    ("cathedral",        (10.779769, 106.699043), "OSM Nhà thờ Đức Bà Sài Gòn"),
    ("post office",      (10.779955, 106.699992), "OSM Bưu điện Trung tâm Sài Gòn"),
    ("book street",      (10.780963, 106.700070), "GGL 'Ho Chi Minh City Book Street'"),
    ("independence",     (10.777034, 106.695488), "OSM Dinh Độc Lập"),
    ("war remnants",     (10.779364, 106.692280), "OSM Bảo tàng Chứng tích Chiến tranh"),
    ("opera",            (10.776500, 106.703100), "863R-verified Saigon Opera House"),
    ("city hall",        (10.776587, 106.700918), "OSM Trụ sở UBND TP.HCM, 86 Lê Thánh Tôn"),
    ("cafe apartments",  (10.774133, 106.704212), "OSM chung cư 42 Nguyễn Huệ"),
    ("bach dang",        (10.775263, 106.706880), "GGL 'Saigon Waterbus Bạch Đằng'"),
    ("thi bar",          (10.767660, 106.693960), "859B-verified Thi Bar Saigon"),
]


def _hav_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _fold(t):
    raw = (t or "").lower().replace("đ", "d")
    nf = unicodedata.normalize("NFKD", raw)
    nf = "".join(c for c in nf if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", nf).split())


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return rows


def _meter_total():
    return sum(float(r.get("usd", r.get("cost_usd", 0)) or 0) for r in _meter_rows())


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


def _check(label, ok, detail):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}: {detail}", flush=True)
    return ok


# ═════════════════════════════════════════════════════════════════════════════
def phase_preview():
    import generate_tour_text_service as svc
    print("\n[PREVIEW] POST /preview-stops, Michael's exact string, city "
          f"{CITY!r}", flush=True)
    before = _meter_total()
    c = svc.app.test_client()
    r = c.post("/preview-stops", json={"text": MICHAEL, "city": CITY})
    d = r.get_json()
    json.dump(d, open(PREVIEW_JSON, "w"), ensure_ascii=False, indent=1)
    print(f"   HTTP {r.status_code}  city={d.get('city')}", flush=True)
    stops = d.get("stops", [])
    allok = True

    allok &= _check("10 stops", len(stops) == 10, f"{len(stops)}")
    exp = ["cathedral", "post office", "book street", "independence palace",
           "war remnants museum", "opera house", "city hall", "cafe apartments 42",
           "bach dang pier", "thi bar"]
    got = [_fold(s["name"]) for s in stops]
    allok &= _check("in the order given", got == exp, f"{[s['name'] for s in stops]}")
    allok &= _check("alt_names kept", stops[5]["alt_names"] == ["Đồng Khởi"]
                    and stops[6]["alt_names"] == ["Nguyễn Huệ"],
                    f"{stops[5]['alt_names']} {stops[6]['alt_names']}")
    allok &= _check("note kept", stops[8]["note"] == "tour-bus + waterbus", repr(stops[8]["note"]))
    allok &= _check("'Cathedral' -> Notre-Dame Cathedral Saigon",
                    "notre" in _fold(stops[0]["resolved_name"]) and "saigon" in _fold(stops[0]["resolved_name"]),
                    stops[0]["resolved_name"])
    allok &= _check("'Post Office' -> Saigon Central Post Office",
                    "saigon central post office" in _fold(stops[1]["resolved_name"]),
                    stops[1]["resolved_name"])
    allok &= _check("'Book Street' -> Nguyễn Văn Bình",
                    "nguyen van binh" in _fold(stops[2]["resolved_name"]),
                    stops[2]["resolved_name"])

    print("   ── pin vs the real place (limit 150 m) ──", flush=True)
    pins_ok = True
    for s, (k, ref, prov) in zip(stops, TRUTH):
        if s["unresolved"]:
            pins_ok = False
            print(f"   {s['index'] + 1:2d} {s['name']:22s} UNRESOLVED FAIL", flush=True)
            continue
        dm = _hav_m((s["lat"], s["lng"]), ref)
        ok = dm <= LIMIT_M
        pins_ok &= ok
        print(f"   {s['index'] + 1:2d} {s['name']:22s} {dm:6.0f} m  "
              f"{s['source']:15s}{s['confidence']:7s} ref={prov} {'OK' if ok else 'FAIL'}",
              flush=True)
    allok &= _check("every pin within 150 m", pins_ok, "see table")

    cost = d.get("cost", {})
    spent = _meter_total() - before
    print(f"   cost (reported by the endpoint): {cost}", flush=True)
    print(f"   cost (network meter, this call): ${spent:.4f}  "
          f"[target <= $0.01 for 10 items]", flush=True)
    allok &= _check("cost reported and <= $0.01", cost.get("usd", 1) <= 0.01
                    and cost.get("llm_calls") == 0 and spent <= 0.01,
                    f"${cost.get('usd')} / meter ${spent:.4f}, llm_calls={cost.get('llm_calls')}")
    print(f"\n=== PREVIEW {'PASS' if allok else 'FAIL'} ===  meter total so far "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    return allok


# ═════════════════════════════════════════════════════════════════════════════
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def _blocks(text):
    titles = _STOP_HEADER_RE.findall(text)
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text)
    return [(int(n), t.strip(), b) for (n, t), b in zip(titles, bodies[1:])]


def _prose(body):
    out = []
    for ln in body.split("\n"):
        s = ln.strip()
        if not s or re.match(r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
                             r"Address|Sources?|Tour-Category):", s):
            continue
        if re.match(r"(?i)^(across these stops|if you would like to eat|that'?s \d+ stops)", s):
            continue
        out.append(re.sub(r"(?i)^Orientation:\s*", "", s))
    return " ".join(out)


def phase_generate():
    d = json.load(open(PREVIEW_JSON))
    stops = d["stops"]
    print(f"\n[GENERATE] {len(stops)} stops from the saved preview, walking tour", flush=True)
    before = _meter_total()
    _reserve = float(os.environ.get("LOCAL867_GEN_RESERVE_USD", "0.24"))
    if before + _reserve > HARD_CAP_USD:
        print(f"   refusing to start: meter ${before:.4f} + reserve ${_reserve:.2f} > "
              f"cap ${HARD_CAP_USD:.2f}", flush=True)
        return False
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter("LOCAL-867", cap_usd=HARD_CAP_USD - before)
    allok = True

    # 1. the REAL orchestrator intake (user_stops objects -> strings; logs the line)
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

    def _thread(job_id, location, tour_type, total_stops, user_id=None,
                request_string=None, language='en', persona=None, is_test=None,
                stops=None, mode=None):
        cap["stops"], cap["total"] = stops, total_stops
    orch.orchestrate_tour_async = _thread
    orch.app.testing = True
    buf = io.StringIO()
    with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
        resp = orch.app.test_client().post(
            "/generate-complete-tour", content_type="application/json",
            data=json.dumps({"location": "Ho Chi Minh City, Vietnam",
                             "tour_type": "walking", "user_id": "local867",
                             "request_string": "a walking tour of my Ho Chi Minh City itinerary",
                             "user_stops": stops}))
    intake_log = buf.getvalue()
    allok &= _check("orchestrator accepted user_stops", resp.status_code in (200, 202),
                    f"HTTP {resp.status_code}")
    allok &= _check("log '[LOCAL-867] imported 10 stops'",
                    "[LOCAL-867] imported 10 stops" in intake_log,
                    [l for l in intake_log.splitlines() if "LOCAL-867" in l][:1])
    fwd = cap.get("stops") or []
    allok &= _check("10 stops forwarded, total_stops=10",
                    len(fwd) == 10 and cap.get("total") == 10, f"{len(fwd)} / {cap.get('total')}")

    # 2. the generator service's own validation of the forwarded list
    import generate_tour_text_service as svc
    forced, err = svc.validate_stops(fwd)
    allok &= _check("generator validate_stops", err is None and forced == fwd, err or "ok")

    # 3. generate (walking)
    import generate_tour_text as g
    gbuf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, gbuf)):
            text, _o, _c = g.generate_tour_text(
                "Ho Chi Minh City, Vietnam", "walking", None, 10, forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = gbuf.getvalue()
    open(os.path.join(_METER_DIR, "tour.txt"), "w").write(text or "")
    open(os.path.join(_METER_DIR, "gen_log.txt"), "w").write(log)

    blocks = _blocks(text or "")
    exp_titles = [s["stop_name"] for s in stops]
    print(f"\n   delivered titles: {[t for _, t, _ in blocks]}", flush=True)
    allok &= _check("10/10 delivered", len(blocks) == 10, f"{len(blocks)}/10")

    order_ok = len(blocks) == 10
    for (n, t, _b), want in zip(blocks, exp_titles):
        a, b = _fold(t), _fold(want)
        if not (a == b or a in b or b in a):
            order_ok = False
            print(f"     order mismatch: Stop {n} {t!r} vs expected {want!r}", flush=True)
    allok &= _check("in the order given", order_ok, "titles match the preview order")

    print("   ── delivered pin vs preview pin vs real place (matched by TITLE) ──", flush=True)
    kept_ok = len(blocks) == 10
    by_title = {}
    for s, tr in zip(stops, TRUTH):
        by_title[_fold(s["stop_name"])] = (s, tr)
    for n, t, b in blocks:
        hit = by_title.get(_fold(t))
        if hit is None:
            kept_ok = False
            print(f"   Stop {n} {t[:28]:28s} not a preview stop FAIL", flush=True)
            continue
        s, (k, ref, prov) = hit
        cm = _COORD_RE.search(b)
        if not cm:
            kept_ok = False
            print(f"   Stop {n} {t[:28]:28s} NO COORDINATE FAIL", flush=True)
            continue
        got = (float(cm.group(1)), float(cm.group(2)))
        d_prev = _hav_m(got, (s["lat"], s["lng"]))
        d_real = _hav_m(got, ref)
        ok = d_prev <= 30.0 and d_real <= LIMIT_M
        kept_ok &= ok
        print(f"   Stop {n:2d} {t[:28]:28s} {d_prev:5.0f} m from preview pin, "
              f"{d_real:5.0f} m from real place {'OK' if ok else 'FAIL'}", flush=True)
    allok &= _check("pins kept (<=30 m of preview pin, <=150 m of real place)", kept_ok, "see table")

    # 4. D760 layers (LOCAL-862B): legends disclosed, stops about their venue, not thin
    try:
        from user_stop_context import DISCLOSURE_RE, _LEGEND_VOCAB_RE as LV
        from user_stop_narration import _split_sentences
    except Exception as e:
        DISCLOSURE_RE = LV = None
        print(f"   (layer helpers unavailable: {e})", flush=True)
    thin, undisclosed, off_venue = [], [], []
    for n, t, b in blocks:
        ss = _split_sentences(_prose(b)) if LV else []
        if len(ss) < 4:
            thin.append((n, t, len(ss)))
        if LV:
            for s_ in ss:
                if LV.search(s_) and not DISCLOSURE_RE.search(s_):
                    undisclosed.append((n, s_[:90]))
        toks = {w for w in _fold(t).split() if len(w) >= 3
                and w not in {"the", "bar", "street", "house", "saigon", "pier", "hall", "city"}}
        pf = _fold(_prose(b))
        if toks and not any(w in pf for w in toks):
            off_venue.append((n, t))
    # A stop with nothing sourced is SHORT by design (D760 short form, LOCAL-863
    # item 3): it is reported, not failed. A thin stop that is NOT the short form
    # (a few unsourced sentences) is a failure.
    short_form = [x for x in thin if "one of the places you chose" in
                  _fold(next(b for nn, tt, b in blocks if nn == x[0]))]
    other_thin = [x for x in thin if x not in short_form]
    print(f"   D760 short-form stops (nothing sourced): {short_form or 'none'}", flush=True)
    allok &= _check("no thin stop other than the D760 short form", not other_thin,
                    other_thin or "ok")
    allok &= _check("every legend-style sentence carries its disclosure marker",
                    not undisclosed, undisclosed or "ok")
    allok &= _check("each stop is about its venue", not off_venue, off_venue or "ok")
    disc = [l for l in log.splitlines() if "LOCAL-862" in l and "layer" in l.lower()]
    print(f"   layer log lines: {len(disc)}", flush=True)
    for l in disc[:8]:
        print("     " + l.strip()[:170], flush=True)

    # 5. never the centroid
    cent = [l for l in log.splitlines() if "centroid" in l.lower() and "user stop" in l.lower()]
    print(f"   centroid mentions for user stops: {len(cent)}", flush=True)

    try:
        _lrm.uninstall()
    except Exception:
        pass
    spent = _meter_total() - before
    print(f"\n   paid-API meter (generation): ${spent:.4f}; task total ${_meter_total():.4f} "
          f"of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"\n=== GENERATE {'PASS' if allok else 'FAIL'} ===", flush=True)
    return allok


if __name__ == "__main__":
    if "--preview" in sys.argv:
        sys.exit(0 if phase_preview() else 1)
    if "--generate" in sys.argv:
        sys.exit(0 if phase_generate() else 1)
    sys.exit("usage: run_local867_live.py --preview | --generate")
