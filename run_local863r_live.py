#!/usr/bin/env python3
"""run_local863r_live.py: LOCAL-863R live, budget-enforced proof (Mac-local).

Runs the wave-27 Sophia request EXACTLY as worded, with 7 user stops, then the
Ben Thanh walk regression, IN-PROCESS from this worktree. That is the 859B
pattern, except that EVERY DB variable points at this task's OWN postgres
(docker-compose.local863r-proof.yml, port 55963). The shared audioura-*
containers, the shared dev postgres (:5433) and the live DB are never touched.

Cloud-like env: K_SERVICE set, LANDMARK_LIVE_LOOKUP empty.

Launch (the meter's sitecustomize reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-863R TASK_BUDGET_USD=0.45 \
  PAID_API_LOG=$PWD/_local863r_meterlogs/paid_api_calls.jsonl \
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local863r_meterlogs METER_MOUNT_GUARD=0 \
  METER_SERVICE=LOCAL-863R PYTHONPATH=$PWD/_meter \
  python3 run_local863r_live.py

PASS (Sophia):
  * city centre within 10 km of 10.776,106.700;
  * 7/7 stops delivered;
  * every pin is within 50 m of the venue, or announced with no pin;
  * zero "user pin kept" for a model coordinate;
  * no 🌈 in any TTS payload (the real egress function, applied to every stop).
Then the Ben Thanh walk must keep its pins (no regression).

Run logs go to ./_local863r_meterlogs/ (never committed).
"""
import contextlib
import io
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))


def _load_dotenv():
    """API keys only. DB_* from .env (if any) are overridden below."""
    path = os.path.join(_HERE, ".env")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
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

# ── budget: must already be in the env (set on the command line) ─────────────
if os.environ.get("TASK_BUDGET_ID") != "LOCAL-863R":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-863R (see docstring)")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.45") or "0.45")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# ── OWN database (D753): never the shared :5433 dev DB, never the live DB ───
_OWN_DB = "postgresql://admin:password123@localhost:55963/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55963"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

# ── cloud-like env ───────────────────────────────────────────────────────────
os.environ["K_SERVICE"] = "tour-generator-subscribed-local863r"
os.environ["LANDMARK_LIVE_LOOKUP"] = ""

# ── cheap arm, pool/cache off (same as the 859B/860 proofs) ──────────────────
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

_METER_DIR = os.path.join(_HERE, "_local863r_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")

SOPHIA_REQUEST = "Sophia's biking tour in Ho Chi Minh City, Vietnam"
HCMC_REF = (10.776, 106.700)
PIN_TARGET_M = 50.0

# 7 user stops: share.google-style links (minted ids cannot be resolved from a
# Mac-local worktree, so they exercise the fallback), Google Maps URLs, and TWO
# plain names. 🌈 is in Thi Bar's typed name, as in Michael's real share title.
SOPHIA_STOPS = [
    "🌈 Thi Bar Saigon https://share.google/l863rThiBar1",
    "Acoustic Bar https://share.google/l863rAcoustic2",
    "An Spa https://www.google.com/maps/place/An+Spa/@10.7820,106.6935,17z",
    "Ben Thanh Market https://www.google.com/maps/search/?api=1&query=Ben+Thanh+Market",
    "Saigon Opera House https://maps.app.goo.gl/l863rOpera5",
    "Crazy street",
    "Saigon Central Post Office",
]
# Truth = the venue's Google Maps location. Thi Bar / Acoustic Bar / An Spa are
# the LOCAL-859B-verified pins. Crazy street is Bui Vien (a STREET: a 50 m
# point test is approximate, so it is judged against a 300 m street tolerance
# and reported separately).
TRUTH = {
    "thi bar saigon": ((10.76766, 106.69396), PIN_TARGET_M),
    "acoustic bar": ((10.781195, 106.68992), PIN_TARGET_M),
    "an spa": ((10.7820, 106.6935), PIN_TARGET_M),
    "ben thanh market": ((10.77250, 106.69800), 150.0),   # a large building
    "saigon opera house": ((10.77650, 106.70310), PIN_TARGET_M),
    "central post office": ((10.77990, 106.69990), PIN_TARGET_M),
    "crazy street": ((10.76730, 106.69290), 300.0),
    "bui vien": ((10.76730, 106.69290), 300.0),
}

BEN_THANH_REQUEST = "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"
BEN_THANH_TRUTH = {
    "ben thanh market": ((10.77250, 106.69800), 150.0),
    "saigon opera house": ((10.77650, 106.70310), 150.0),
}

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_CENTER_RE = re.compile(r"\[LOCAL-791C\] pin snap: scope=(.*?) center=\(([-\d.]+), ([-\d.]+)\)")


def _hav_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _fold(t):
    import unicodedata
    nf = unicodedata.normalize("NFKD", t or "")
    nf = "".join(c for c in nf if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", nf).split())


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


def _generate(location, tour_type, stops, n, tag):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                location, tour_type, None, n, forced_stops=list(stops) if stops else None)
    except Exception as e:
        import traceback
        print(f"  [LOCAL-863R] {tag} generate raised: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    with open(os.path.join(_METER_DIR, f"{tag}_tour.txt"), "w") as f:
        f.write(text or "")
    with open(os.path.join(_METER_DIR, f"{tag}_log.txt"), "w") as f:
        f.write(log)
    return text or "", log


def _blocks(text):
    titles = _STOP_HEADER_RE.findall(text)
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text)
    return [(int(n), t.strip(), b) for (n, t), b in zip(titles, bodies[1:])]


def _truth_for(title, table):
    key = _fold(title)
    for k in sorted(table, key=len, reverse=True):
        if k in key:
            return k, table[k]
    return None, None


def _pin_report(blocks, table, label):
    ok_all = True
    rows = []
    for n, title, body in blocks:
        cm = _COORD_RE.search(body)
        got = (float(cm.group(1)), float(cm.group(2))) if cm else None
        k, tr = _truth_for(title, table)
        if got is None:
            rows.append((n, title, "announced, NO pin", True))
            continue
        if not tr:
            rows.append((n, title, f"pin {got} (no truth to measure)", True))
            continue
        d = _hav_m(got, tr[0])
        ok = d <= tr[1]
        ok_all = ok_all and ok
        rows.append((n, title, f"{d:7.0f} m to venue (limit {tr[1]:.0f} m)", ok))
    print(f"   ── {label} pin proof ──", flush=True)
    for n, title, msg, ok in rows:
        print(f"   Stop {n} {title[:30]:30} {msg} {'OK' if ok else 'FAIL'}", flush=True)
    return ok_all


def _no_rainbow_in_tts(blocks, log):
    import tour_generation_modernized as tgm
    bad = []
    for n, title, body in blocks:
        payload = tgm._strip_nav_fields_for_tts(f"Stop {n}: {title}\n{body}")
        if "🌈" in payload:
            bad.append(n)
    strip_lines = [l for l in log.splitlines() if "TTS emoji strip" in l]
    return not bad, bad


def sophia():
    print("\n[SOPHIA] " + SOPHIA_REQUEST + f"  ({len(SOPHIA_STOPS)} user stops)", flush=True)
    text, log = _generate(SOPHIA_REQUEST, "", SOPHIA_STOPS, len(SOPHIA_STOPS), "sophia")
    blocks = _blocks(text)
    res = {}

    m = _CENTER_RE.search(log)
    if m and m.group(2) != "None":
        c = (float(m.group(2)), float(m.group(3)))
        d = _hav_m(c, HCMC_REF) / 1000.0
        res["city"] = d <= 10.0
        print(f"   city centre {c} = {d:.2f} km from {HCMC_REF} "
              f"{'OK' if res['city'] else 'FAIL'}", flush=True)
    else:
        res["city"] = False
        print("   city centre: pin-snap centre line not found / None  FAIL", flush=True)
    bbox_country = [l for l in log.splitlines()
                    if "enclosing segment 'Vietnam'" in l]
    print(f"   whole-country bbox fallbacks: {len(bbox_country)}", flush=True)
    res["city"] = res["city"] and not bbox_country

    res["count"] = len(blocks) == 7
    print(f"   delivered {len(blocks)}/7 {'OK' if res['count'] else 'FAIL'}: "
          f"{[t for _, t, _ in blocks]}", flush=True)
    removed = [l for l in log.splitlines() if "REMOVED:" in l]
    if removed:
        print(f"   removal lines: {removed}", flush=True)

    res["pins"] = _pin_report(blocks, TRUTH, "Sophia")

    # Zero "user pin kept" for a MODEL coordinate: every kept pin must be a
    # real user source, so its delivered coordinate must be within the limit.
    kept = [l for l in log.splitlines() if "user pin kept" in l]
    model_flags = [l for l in log.splitlines() if "has a MODEL coordinate" in l]
    bad_kept = []
    for l in kept:
        mm = re.search(r"user pin kept '([^']+)'", l) or re.search(r'user pin kept "([^"]+)"', l)
        if not mm:
            continue
        nm = mm.group(1)
        blk = next((b for b in blocks if _fold(nm) in _fold(b[1]) or _fold(b[1]) in _fold(nm)), None)
        k, tr = _truth_for(nm, TRUTH)
        if blk and tr:
            cm = _COORD_RE.search(blk[2])
            if cm and _hav_m((float(cm.group(1)), float(cm.group(2))), tr[0]) > tr[1]:
                bad_kept.append(l)
    res["no_model_kept"] = not bad_kept
    print(f"   'user pin kept' lines: {len(kept)}; model-coordinate user stops "
          f"flagged: {len(model_flags)}; kept-but-off-venue: {len(bad_kept)} "
          f"{'OK' if res['no_model_kept'] else 'FAIL'}", flush=True)
    for l in kept:
        print(f"     {l.strip()}", flush=True)

    ok, bad = _no_rainbow_in_tts(blocks, log)
    res["no_rainbow"] = ok
    print(f"   🌈 in TTS payload: {'none OK' if ok else f'stops {bad} FAIL'}", flush=True)
    return res


def ben_thanh():
    print("\n[BEN THANH] " + BEN_THANH_REQUEST, flush=True)
    text, log = _generate(BEN_THANH_REQUEST, "walking", None, 4, "benthanh")
    blocks = _blocks(text)
    ok = _pin_report(blocks, BEN_THANH_TRUTH, "Ben Thanh")
    have = {k for k in BEN_THANH_TRUTH
            if any(k in _fold(t) for _, t, _ in blocks)}
    print(f"   anchors delivered: {sorted(have)}", flush=True)
    return ok and len(blocks) >= 2


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-863R live: Sophia (7 user stops) + Ben Thanh regression ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} CAP=${HARD_CAP_USD:.2f} "
          f"K_SERVICE={os.environ.get('K_SERVICE')!r} "
          f"LANDMARK_LIVE_LOOKUP={os.environ.get('LANDMARK_LIVE_LOOKUP')!r}", flush=True)
    print(f"  own DB: {_OWN_DB.replace('password123', '***')}", flush=True)
    s = sophia()
    spent1 = _meter_total()
    print(f"\n  spent after Sophia: ${spent1:.4f}", flush=True)
    bt = None
    if spent1 < HARD_CAP_USD * 0.8:
        bt = ben_thanh()
    else:
        print("  Ben Thanh SKIPPED: too little budget left", flush=True)
    spent = _meter_total()
    print("\n" + "=" * 72, flush=True)
    for k, v in s.items():
        print(f"  SOPHIA {k:14}: {'PASS' if v else 'FAIL'}", flush=True)
    print(f"  BEN THANH     : {'PASS' if bt else ('SKIPPED' if bt is None else 'FAIL')}", flush=True)
    print(f"  BUDGET (${spent:.4f} ≤ ${HARD_CAP_USD:.2f}): "
          f"{'PASS' if spent <= HARD_CAP_USD else 'FAIL'}", flush=True)
    overall = all(s.values()) and bool(bt) and spent <= HARD_CAP_USD
    print(f"  OVERALL: {'PASS' if overall else 'FAIL'}", flush=True)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
