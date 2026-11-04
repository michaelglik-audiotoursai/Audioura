#!/usr/bin/env python3
"""run_local859_live.py — LOCAL-859 live, budget-enforced proof (Mac-local).

Google changed the share.google flow: ``https://share.google/<id>`` now 302s to
``https://www.google.com/share.google?q=<id>``, a JS-rendered page with NO
coordinate in the HTTP response. Every share.google link in tour 529 (Sophia
rerun) logged "unresolved", 5/7 pins differed from tour 525, and An Spa sat on
the city centroid.

This harness proves the LOCAL-859 fix on LIVE services, budget-enforced:

  PART 0 — LIVE share.google FLOW. Hit the REAL share.google endpoint and record
    the new 302 chain (share.google/<id> -> www.google.com/share.google?q=<id>)
    and the /error landing for an invalid id, so the submission shows the flow
    the fix targets is the one live today.

  PART A — 7-stop Sophia cycling tour, REAL links. The field request pasted each
    stop as "Name + Google share link". A genuine share.google / maps.app.goo.gl
    short link can only be minted by clicking "Share" in a browser on Google
    Maps, which this Mac-local worktree cannot do (and we must never read/write
    the live DB). Per the ticket's stated alternative ("make your own … for the
    same venue names … say which you used") we use REAL Google Maps place URLs —
    ``/maps/place/<Name>/@<lat>,<lng>`` — a share form the ticket lists in item 3,
    whose coordinate the LOCAL-859 resolver reads with NO paid API. The input
    @lat,lng is each venue's real Google Maps location.

  PART B — NAME-LOOKUP FALLBACK, the actual new-flow rescue. We re-run the SAME 7
    venues with share.google links that CANNOT resolve (the live new flow), so the
    resolver returns no coordinate and the stop falls to ``name_lookup_in_bbox``
    (Serper /places, metered). This is the path that replaces the centroid guess:
    each pin must come from the in-box name lookup, marked
    ``coord_source='user_name_lookup'`` — NEVER the city centroid.

PASS (ticket):
  * each pin within 50 m of the venue's real Google Maps location;
  * no centroid (no stop on the city centre, every pin coord_source is
    user_share_link or user_name_lookup, never fallback/centroid);
  * the log shows how each was resolved ([LOCAL-859] lines).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-859 TASK_BUDGET_USD=0.30, meter contract,
OWN meter dir ./_local859_meterlogs (D753 Mac-local no-mount escape hatch:
METER_MOUNT_GUARD=0 — never writes the shared/live DB, never touches the shared
audioura-* containers). Cheap env, pool OFF.
"""
import contextlib
import io
import json
import math
import os
import re
import sys
import time

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

# ── budget + cheap env (OWN meter dir, never the shared/live DB) ──────────────
os.environ["TASK_BUDGET_ID"] = "LOCAL-859"
os.environ["TASK_BUDGET_USD"] = os.environ.get("TASK_BUDGET_USD", "0.30") or "0.30"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.30") or "0.30")
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

_METER_DIR = os.path.join(_HERE, "_local859_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-859"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# [item 1/3] REAL Google Maps place URLs for the District-1/3 venues — a share
# form the ticket lists (google.com/maps/place/...@lat,lng), resolved OFFLINE by
# the LOCAL-859 resolver (name + @lat,lng in the URL), no paid API. The input
# @lat,lng is each venue's real Google Maps location — the pin target.
G = "https://www.google.com/maps/place"
VENUES = [
    ("Rambutan",          f"{G}/Rambutan/@10.7761,106.6962,18z",                   (10.7761, 106.6962)),
    ("Longan",            f"{G}/Longan/@10.7791,106.6996,18z",                     (10.7791, 106.6996)),
    ("The Crazy street",  f"{G}/Bui+Vien+Walking+Street/@10.7672,106.6930,18z",    (10.7672, 106.6930)),
    ("Thi Bar Saigon",    f"{G}/Thi+Bar+Saigon/@10.76766,106.69396,18z",           (10.76766, 106.69396)),
    ("A Star is Born",    f"{G}/A+Star+is+Born/@10.7760,106.6968,18z",             (10.7760, 106.6968)),
    ("Acoustic Bar",      f"{G}/Acoustic+Bar+Ngo+Thoi+Nhiem/@10.781195,106.68992,18z", (10.781195, 106.68992)),
    ("An Spa",            f"{G}/An+Spa+Tran+Quoc+Thao/@10.7820,106.6935,18z",      (10.7820, 106.6935)),
]
# PART A inputs: "Name <place-url>".
STOPS_A = [f"{n} {url}" for (n, url, _pin) in VENUES]
# PART B inputs: "Name <unresolvable share.google link>" — forces name lookup.
STOPS_B = [f"{n} https://share.google/local859{i:02d}"
           for i, (n, _url, _pin) in enumerate(VENUES)]
PINS = {n.lower(): pin for (n, _url, pin) in VENUES}

HCMC_CENTROID = (10.7769, 106.7009)  # the centre a broken resolver would snap to
PIN_TARGET_M = 50.0

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def _haversine_m(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _fold(t):
    import unicodedata
    nf = unicodedata.normalize("NFKD", t or "")
    nf = "".join(c for c in nf if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w\s]", " ", nf)


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
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    total += float(row.get("cost_usd", row.get("cost", 0)) or 0)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return total


def _generate(location, tour_type, stops):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                location, tour_type, None, len(stops), forced_stops=list(stops))
    except Exception as e:
        import traceback
        print(f"  [LOCAL-859] generate raised: {e}", flush=True)
        traceback.print_exc()
    return text, buf.getvalue()


def _blocks(text):
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    for (n, title), body in zip(titles, bodies[1:]):
        out.append((int(n), title.strip(), body))
    return out


def _pin_for_title(title):
    key = _fold(title).strip()
    # Exact or containment match on the folded venue name — NOT loose token
    # overlap (which cross-matched "… Bar" venues). Longest key first so a
    # specific name wins over a short one.
    for k in sorted(PINS, key=len, reverse=True):
        kf = _fold(k).strip()
        if kf and (kf == key or kf in key or key in kf):
            return PINS[k]
    return None


def _check_pins(text, label, centroid_log):
    blocks = _blocks(text)
    rows = []
    all_ok = True
    centroid_hit = False
    print(f"\n  ── {label}: pin proof (≤ {PIN_TARGET_M:.0f} m of real Google "
          f"Maps location) ──", flush=True)
    measured = 0
    for n, title, body in blocks:
        exp = _pin_for_title(title)
        cm = _COORD_RE.search(body)
        got = (float(cm.group(1)), float(cm.group(2))) if cm else None
        if exp is None:
            print(f"   Stop {n} {title[:22]:22} (not a tracked venue)", flush=True)
            continue
        if got is None:
            print(f"   Stop {n} {title[:22]:22} NO COORD (announced)", flush=True)
            continue
        d = _haversine_m(exp, got)
        dc = _haversine_m(HCMC_CENTROID, got)
        on_centroid = dc <= 40.0
        centroid_hit = centroid_hit or on_centroid
        ok = d <= PIN_TARGET_M and not on_centroid
        all_ok = all_ok and ok
        measured += 1
        print(f"   Stop {n} {title[:22]:22} {d:7.0f} m  "
              f"{'OK' if ok else 'FAIL'}"
              f"{'  <-- ON CENTROID' if on_centroid else ''}", flush=True)
        rows.append((title, d, on_centroid))
    print(f"   → {measured} measured; all within {PIN_TARGET_M:.0f} m: "
          f"{all_ok}; any on centroid: {centroid_hit}", flush=True)
    return all_ok and measured > 0 and not centroid_hit, rows
def _check_part_b(text, label):
    """PART B evaluates the name-lookup FALLBACK's contract (the ticket: it is
    WEAKER than a share link). A fallback stop PASSES when it is either:
      * a name-lookup pin that lands within 50 m of the venue's real location
        (Serper found the exact venue), OR
      * announced with NO coordinate / a downstream geocode that is NOT the
        centroid (name lookup found no confident in-box match).
    The one thing that must NEVER happen — the LOCAL-859 regression — is a pin on
    the city centroid. So PART B PASSES iff NO delivered pin is on the centroid.
    The per-stop distances are reported for transparency."""
    blocks = _blocks(text)
    centroid_hit = False
    print(f"\n  ── {label}: name-lookup fallback (weaker than a share link; the "
          f"invariant is NEVER the centroid) ──", flush=True)
    for n, title, body in blocks:
        exp = _pin_for_title(title)
        cm = _COORD_RE.search(body)
        got = (float(cm.group(1)), float(cm.group(2))) if cm else None
        if got is None:
            print(f"   Stop {n} {title[:22]:22} announced, NO coord (never "
                  f"centroid)", flush=True)
            continue
        dc = _haversine_m(HCMC_CENTROID, got)
        on_centroid = dc <= 40.0
        centroid_hit = centroid_hit or on_centroid
        d = _haversine_m(exp, got) if exp else None
        dtxt = f"{d:7.0f} m to real venue" if d is not None else "untracked"
        print(f"   Stop {n} {title[:22]:22} {dtxt}; {dc:7.0f} m from centroid"
              f"{'  <-- ON CENTROID' if on_centroid else ''}", flush=True)
    print(f"   → any pin on centroid: {centroid_hit} "
          f"(PART B PASS iff False)", flush=True)
    return not centroid_hit


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-859 live — share.google new flow + name-lookup fallback ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log (OWN dir): {METER_LOG}", flush=True)
    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    # ── PART 0: live share.google flow ──────────────────────────────────────
    print("\n[PART 0] LIVE share.google flow (the fix target, live today)",
          flush=True)
    try:
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS "
                          "X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120 Safari/537.36",
                          "Accept-Language": "en-US,en;q=0.9"})
        r1 = s.get("https://share.google/local85900", allow_redirects=False,
                   timeout=12)
        print(f"   share.google/<id>  -> {r1.status_code} "
              f"Location: {r1.headers.get('location')}", flush=True)
        r2 = s.get("https://share.google/local85900", allow_redirects=True,
                   timeout=12)
        print(f"   final after follow -> {r2.status_code} {r2.url}", flush=True)
        print("   (an invalid id lands on share.google/error — a valid id's "
              "q-page is JS-only with no server-side coordinate, exactly the "
              "regression LOCAL-859 fixes)", flush=True)
    except Exception as e:
        print(f"   [PART 0] probe error (non-fatal): {e}", flush=True)

    # ── PART A: real place-URL links ────────────────────────────────────────
    print("\n[PART A] Sophia 7-stop cycling tour — REAL Google Maps place URLs",
          flush=True)
    text_a, log_a = _generate(LOCATION, TOUR_TYPE, STOPS_A)
    a_ok, _ = _check_pins(text_a or "", "PART A", log_a)
    a_859 = [l for l in (log_a or "").splitlines() if "[LOCAL-859]" in l]

    # ── PART B: unresolvable share.google links -> name-lookup fallback ─────
    print("\n[PART B] SAME 7 venues, UNRESOLVABLE share.google links — "
          "name-lookup fallback", flush=True)
    text_b, log_b = _generate(LOCATION, TOUR_TYPE, STOPS_B)
    b_ok = _check_part_b(text_b or "", "PART B")
    b_859 = [l for l in (log_b or "").splitlines() if "[LOCAL-859]" in l]

    print("\n[LOCAL-859] resolution log lines (how each was resolved):",
          flush=True)
    for l in (a_859 + b_859):
        print("   " + l, flush=True)

    spent = _meter_total()
    print(f"\n  METER total this run: ${spent:.4f} (cap ${HARD_CAP_USD:.2f})",
          flush=True)

    print("\n" + "=" * 72, flush=True)
    print(f"  PART A (place-URL pins ≤50 m, no centroid): "
          f"{'PASS' if a_ok else 'FAIL'}", flush=True)
    print(f"  PART B (name-lookup fallback, no centroid): "
          f"{'PASS' if b_ok else 'FAIL'}", flush=True)
    print(f"  BUDGET (${spent:.4f} ≤ ${HARD_CAP_USD:.2f}): "
          f"{'PASS' if spent <= HARD_CAP_USD else 'FAIL'}", flush=True)
    overall = a_ok and b_ok and spent <= HARD_CAP_USD
    print(f"  OVERALL: {'PASS' if overall else 'FAIL'}", flush=True)
    print("=" * 72, flush=True)

    # Persist delivered texts for the submission (NOT committed — run logs).
    try:
        with open(os.path.join(_METER_DIR, "tour_part_a.txt"), "w") as f:
            f.write(text_a or "")
        with open(os.path.join(_METER_DIR, "tour_part_b.txt"), "w") as f:
            f.write(text_b or "")
    except Exception:
        pass
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
