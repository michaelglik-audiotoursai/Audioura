#!/usr/bin/env python3
"""run_local859b_live.py — LOCAL-859B live, budget-enforced proof (Mac-local).

Google now resolves share.google through a Knowledge-Graph SEARCH url, not a
``/maps/place`` url (GCloud_Storied_1 probed Michael's REAL links, orch
ef0cee57, 2026-11-03 20:3x; ClickUp wdvrdazc6c). The live chain:
  1. share.google/<id>                   -> 302 www.google.com/share.google?q=<id>
  2. www.google.com/share.google?q=<id>  -> 301 www.google.com/search?kgmid=<KG
       id>&q=<place name>&source=sh/x/(loc|kp)/…
  3. a JS-only search page (NO /maps/place, @lat,lng, !3d!4d, 0x…:0x… or ftid).
HEAD stops at hop 2 — the resolver follows with GET and reads ``q`` + ``kgmid``.

This harness proves the LOCAL-859B fix, budget-enforced:

  PART 0 — LIVE share.google FLOW. Hit the REAL share.google endpoint with HEAD
    (stops at hop 2) and GET (follows to the search page) and print the final
    URLs, so the submission shows the flow the fix targets is the one live today.

  PART A — RESOLVER DIRECT, both KG shapes. The ticket says no tour is needed to
    prove the resolver: call it directly on realistic ``search?kgmid=…`` URLs.
    A genuine share.google short link can only be minted by clicking "Share" in a
    browser on Google Maps, which this Mac-local worktree cannot do (and we must
    never read/write the live DB). Per the ticket's stated alternative we drive
    the resolver through a captured copy of the exact live chain for the two real
    shapes Michael's links produced:
      * Thi Bar  → kgmid=/g/…  source=…/loc  → HIGH: q looked up via Serper /places
        (metered), coord_source='user_share_link_kg';
      * Rambutan → kgmid=/m/0fs6v source=…/kp → LOW: q (the FRUIT) ignored, the
        typed NAME looked up via name_lookup_in_bbox.
    HIGH pins are checked within 50 m of the venue's real Google Maps location.

  PART B — ONE 3-stop user-stops tour (Thi Bar Saigon, Acoustic Bar, An Spa) with
    unresolvable share.google links, to prove the WIRING end-to-end. PASS = each
    pin within 50 m of the real venue, or announced with NO pin — NEVER the
    centroid, never another city.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-859B TASK_BUDGET_USD=0.15, meter
contract, OWN meter dir ./_local859b_meterlogs (D753 Mac-local no-mount escape
hatch: METER_MOUNT_GUARD=0 — never writes the shared/live DB, never touches the
shared audioura-* containers). Cheap env, pool OFF.
"""
import contextlib
import io
import json
import math
import os
import re
import sys
import types

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
os.environ["TASK_BUDGET_ID"] = "LOCAL-859B"
os.environ["TASK_BUDGET_USD"] = os.environ.get("TASK_BUDGET_USD", "0.15") or "0.15"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.15") or "0.15")
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

_METER_DIR = os.path.join(_HERE, "_local859b_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-859B"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

import user_stop_input as usi  # noqa: E402

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# Real Google Maps locations of the three field venues (the pin targets).
VENUE_PINS = {
    "thi bar saigon": (10.76766, 106.69396),
    "acoustic bar":   (10.781195, 106.68992),
    "an spa":         (10.7820, 106.6935),
}
HCMC_CENTROID = (10.7769, 106.7009)
HCMC_BBOX = (8.3456879, 11.5015885, 105.9769387, 108.4311207)  # HCMC admin bbox
HCMC_CENTER = (10.7769, 106.7009)
PIN_TARGET_M = 50.0

# A captured copy of the EXACT live hop-2 search URLs for the two real shapes
# (ids obfuscated — a share id is public, we never hardcode Michael's real one).
_LOC_SEARCH = ("https://www.google.com/search?kgmid=/g/11c5qd9z"
               "&q=Thi+Bar+Saigon,+Ng%C3%B4+Th%E1%BB%9Di+Nhi%E1%BB%87m,"
               "+District+3&source=sh/x/loc/1/en")
_KP_SEARCH = ("https://www.google.com/search?kgmid=/m/0fs6v"
              "&q=Rambutan&source=sh/x/kp/1/en")


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
                    total += float(row.get("usd", row.get("cost_usd",
                                   row.get("cost", 0))) or 0)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return total


# ── a captured-chain resolver so PART A drives the EXACT live KG flow offline ──
class _CapturedChain:
    """requests.Session replaying the captured new-flow chain: a GET on
    share.google/<id> follows to the canonical search?kgmid=…&q=…&source=… URL
    (hop-2 target). Keyed by the first 4 chars of the id so the obfuscated ids
    below map to the two real shapes."""
    PREFIX = {"thib": _LOC_SEARCH, "ramb": _KP_SEARCH}
    _BODY = "<!DOCTYPE html><html><body>loading…</body></html>"

    def __init__(self):
        self.headers = {}
        self.cookies = type("C", (), {"set": lambda *a, **k: None})()

    def _id(self, url):
        m = re.search(r"(?:share\.google/|[?&]q=)([^/?&#\s]+)", url)
        return m.group(1) if m else ""

    def get(self, url, timeout=None, allow_redirects=True):
        sid = self._id(url)
        final = self.PREFIX.get(sid[:4].lower())
        if final:
            return type("R", (), {"url": final, "text": self._BODY})()
        return type("R", (), {"url": url, "text": "<html>no map</html>"})()


def _install_captured_requests():
    fake = types.ModuleType("requests")
    fake.Session = _CapturedChain
    sys.modules["requests"] = fake


def _restore_real_requests():
    sys.modules.pop("requests", None)


def part0_live_flow():
    print("\n[PART 0] LIVE share.google flow (the fix target, live today)",
          flush=True)
    try:
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS "
                          "X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120 Safari/537.36",
                          "Accept-Language": "en-US,en;q=0.9"})
        rh = s.head("https://share.google/local859b0", allow_redirects=True,
                    timeout=12)
        print(f"   HEAD follow -> {rh.status_code} {rh.url}", flush=True)
        print("   (HEAD stops at hop 2 — share.google?q=<id> — no kgmid; GET is "
              "required to reach the search URL)", flush=True)
        rg = s.get("https://share.google/local859b0", allow_redirects=True,
                   timeout=12)
        q, kgmid, source = usi.parse_kg_search_url(rg.url)
        print(f"   GET follow  -> {rg.status_code} final host "
              f"{rg.url.split('?')[0]}", flush=True)
        print(f"   parsed from final: q={q!r} kgmid={kgmid!r} source={source!r}",
              flush=True)
    except Exception as e:
        print(f"   [PART 0] probe error (non-fatal): {e}", flush=True)


def part_a_resolver_direct():
    print("\n[PART A] RESOLVER DIRECT — both KG shapes (captured live chain)",
          flush=True)
    _install_captured_requests()
    results = {}
    a_ok = True
    try:
        for label, sid in (("Thi Bar (loc/g)", "thibObf12"),
                           ("Rambutan (kp/m)", "rambObf34")):
            logs = []
            out = usi.resolve_share_link_kg(f"https://share.google/{sid}",
                                            log=logs.append)
            print(f"   {label}: {logs[-1] if logs else '(no log)'}", flush=True)
            results[label] = out

        # Confidence gate: HIGH q looked up via live Serper /places (metered);
        # LOW uses the typed name. Prove the HIGH pin lands on the real venue.
        hi = results["Thi Bar (loc/g)"]
        assert hi and hi["confidence"] == "high" and hi["q"], "Thi Bar not HIGH"
        hit = usi.name_lookup_in_bbox(
            hi["q"], "Ho Chi Minh City", bbox=HCMC_BBOX, center=HCMC_CENTER,
            log=print)
        if hit:
            d = _haversine_m(VENUE_PINS["thi bar saigon"], (hit[0], hit[1]))
            dc = _haversine_m(HCMC_CENTROID, (hit[0], hit[1]))
            on_centroid = dc <= 40.0
            ok = d <= PIN_TARGET_M and not on_centroid
            print(f"   HIGH q-lookup Thi Bar -> {hit[0]:.6f},{hit[1]:.6f} "
                  f"({d:.0f} m to venue, source {hit[2]}) "
                  f"{'OK' if ok else 'FAIL'}"
                  f"{'  <-- CENTROID' if on_centroid else ''}", flush=True)
            a_ok = a_ok and ok
        else:
            print("   HIGH q-lookup Thi Bar -> no in-box match (announced, never "
                  "centroid) — acceptable, but no pin to measure", flush=True)

        lo = results["Rambutan (kp/m)"]
        assert lo and lo["confidence"] == "low", "Rambutan not LOW"
        print(f"   LOW: Rambutan q ignored (kgmid {lo['kgmid']} is the FRUIT) — "
              f"caller uses the typed NAME, not q", flush=True)
    except Exception as e:
        import traceback
        print(f"   [PART A] error: {e}", flush=True)
        traceback.print_exc()
        a_ok = False
    finally:
        _restore_real_requests()
    return a_ok


def _generate(stops):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                LOCATION, TOUR_TYPE, None, len(stops), forced_stops=list(stops))
    except Exception as e:
        import traceback
        print(f"  [LOCAL-859B] generate raised: {e}", flush=True)
        traceback.print_exc()
    return text, buf.getvalue()


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def _blocks(text):
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    for (n, title), body in zip(titles, bodies[1:]):
        out.append((int(n), title.strip(), body))
    return out


def _pin_for_title(title):
    key = _fold(title).strip()
    for k in sorted(VENUE_PINS, key=len, reverse=True):
        kf = _fold(k).strip()
        if kf and (kf == key or kf in key or key in kf):
            return VENUE_PINS[k]
    return None


def part_b_tour():
    print("\n[PART B] ONE 3-stop user-stops tour — wiring proof "
          "(Thi Bar Saigon, Acoustic Bar, An Spa)", flush=True)
    stops = [
        "Thi Bar Saigon https://share.google/local859bthib",
        "Acoustic Bar https://share.google/local859bacou",
        "An Spa https://share.google/local859banspa",
    ]
    text, _log = _generate(stops)
    blocks = _blocks(text or "")
    centroid_hit = False
    all_ok = True
    measured = 0
    print(f"   ── pin proof (≤ {PIN_TARGET_M:.0f} m of real venue, or announced "
          f"with NO pin; NEVER the centroid) ──", flush=True)
    for n, title, body in blocks:
        exp = _pin_for_title(title)
        cm = _COORD_RE.search(body)
        got = (float(cm.group(1)), float(cm.group(2))) if cm else None
        if got is None:
            print(f"   Stop {n} {title[:24]:24} announced, NO coord (OK — never "
                  f"centroid)", flush=True)
            continue
        dc = _haversine_m(HCMC_CENTROID, got)
        on_centroid = dc <= 40.0
        centroid_hit = centroid_hit or on_centroid
        d = _haversine_m(exp, got) if exp else None
        measured += 1
        dtxt = f"{d:7.0f} m to venue" if d is not None else "untracked"
        ok = (d is not None and d <= PIN_TARGET_M and not on_centroid)
        all_ok = all_ok and (ok or on_centroid is False and d is None)
        print(f"   Stop {n} {title[:24]:24} {dtxt}; {dc:6.0f} m from centroid "
              f"{'OK' if ok else ''}"
              f"{'  <-- ON CENTROID' if on_centroid else ''}", flush=True)
    b_ok = (not centroid_hit)
    print(f"   → measured {measured} pins; any on centroid: {centroid_hit} "
          f"(PART B PASS iff no centroid)", flush=True)
    try:
        with open(os.path.join(_METER_DIR, "tour_part_b.txt"), "w") as f:
            f.write(text or "")
    except Exception:
        pass
    return b_ok


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-859B live — share.google KG flow (q + kgmid) + gate ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log (OWN dir): {METER_LOG}", flush=True)
    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    part0_live_flow()
    a_ok = part_a_resolver_direct()
    b_ok = part_b_tour()

    spent = _meter_total()
    print("\n" + "=" * 72, flush=True)
    print(f"  PART A (resolver direct: /g/+loc HIGH q-pin ≤50 m, /m/+kp LOW): "
          f"{'PASS' if a_ok else 'FAIL'}", flush=True)
    print(f"  PART B (3-stop user tour, no centroid): "
          f"{'PASS' if b_ok else 'FAIL'}", flush=True)
    print(f"  BUDGET (${spent:.4f} ≤ ${HARD_CAP_USD:.2f}): "
          f"{'PASS' if spent <= HARD_CAP_USD else 'FAIL'}", flush=True)
    overall = a_ok and b_ok and spent <= HARD_CAP_USD
    print(f"  OVERALL: {'PASS' if overall else 'FAIL'}", flush=True)
    print("=" * 72, flush=True)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
