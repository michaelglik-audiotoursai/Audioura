#!/usr/bin/env python3
"""run_local855e_live.py — LOCAL-855E live, budget-enforced proof (Mac-local).

The third bounce of LOCAL-855. Re-runs Sophia's 7-stop CYCLING tour of Ho Chi
Minh City TWICE (the output varies run to run) and a 3-stop Notre-Dame regression,
then checks the delivered text against the LOCAL-855E PASS criteria:

  * 7/7 stops delivered;
  * every delivered pin is within 30 m of its INPUT @lat,lng (item 1 — the
    listener's own coordinate is authoritative and was NOT moved);
  * no "Đ." address stub (item 2 — "Address: 15 Đ." never ships);
  * no sea / coast / harp / altar / film-poster invention (item 3 / D759 — the
    SENSORY loophole is closed);
  * each stop is about its venue.
Run B: Notre-Dame keeps a sourced date in 1863–1880.

INPUTS (item 4). The field request (orch ef0cee57 / tour 525/523) pasted each
user stop as "Name + Google share link". Those exact cloud links are not
reachable from this Mac-local worktree (and we must never read/write the live
DB). The ticket's stated alternative is used: REAL Google Maps place URLs for the
District-1/3 venues whose /maps/place/<Name>/@<lat>,<lng> resolves OFFLINE to a
real name + coordinate with no paid API. These are the SAME inputs as
run_local855d_live.py (shared with LEAD's re-run).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-855E TASK_BUDGET_USD=0.40 (both runs share
the cap), meter contract, OWN meter dir ./_local855e_meterlogs (D753 Mac-local
no-mount escape hatch: METER_MOUNT_GUARD=0 — never writes the shared/live DB,
never touches the shared audioura-* containers). Cheap env + STORY_PASS_MODEL=
gpt-4.1, pool OFF.
"""
import io
import json
import math
import os
import re
import sys
import time
import contextlib

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

# ── budget + cheap env ───────────────────────────────────────────────────────
os.environ["TASK_BUDGET_ID"] = "LOCAL-855E"
os.environ["TASK_BUDGET_USD"] = os.environ.get("TASK_BUDGET_USD", "0.40") or "0.40"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.40") or "0.40")
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

_METER_DIR = os.path.join(_HERE, "_local855e_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-855E"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# [LOCAL-855E item 4] REAL Google Maps place URLs for the District-1/3 venues,
# resolved offline by the LOCAL-852 resolver (name + @lat,lng in the URL). SAME
# inputs as run_local855d_live.py. The input @lat,lng is the authoritative pin
# each delivered stop must land within 30 m of.
G = "https://www.google.com/maps/place"
USER_STOPS = [
    (f"Rambutan {G}/Rambutan/@10.7761,106.6962,18z", (10.7761, 106.6962)),
    (f"Longan {G}/Longan/@10.7791,106.6996,18z", (10.7791, 106.6996)),
    (f"The Crazy street {G}/Bui+Vien+Walking+Street/@10.7672,106.6930,18z", (10.7672, 106.6930)),
    (f"Thi Bar Saigon {G}/Thi+Bar+Saigon/@10.76766,106.69396,18z", (10.76766, 106.69396)),
    (f"A Star is Born {G}/A+Star+is+Born/@10.7760,106.6968,18z", (10.7760, 106.6968)),
    (f"Acoustic Bar {G}/Acoustic+Bar+Ngo+Thoi+Nhiem/@10.781195,106.68992,18z", (10.781195, 106.68992)),
    (f"An Spa {G}/An+Spa+Tran+Quoc+Thao/@10.7820,106.6935,18z", (10.7820, 106.6935)),
]
USER_STOP_INPUTS = [u for u, _ in USER_STOPS]
EXPECTED_PINS = {
    "rambutan": (10.7761, 106.6962),
    "longan": (10.7791, 106.6996),
    "the crazy street": (10.7672, 106.6930),
    "thi bar saigon": (10.76766, 106.69396),
    "a star is born": (10.7760, 106.6968),
    "acoustic bar": (10.781195, 106.68992),
    "an spa": (10.7820, 106.6935),
}

USER_STOPS_B = [
    "Notre-Dame Cathedral Basilica of Saigon",
    "Independence Palace",
    "Bến Thành Market",
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_ADDR_RE = re.compile(r"(?mi)^Address:\s*(.*)$")


def _haversine_m(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return rows


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


def _generate(location, tour_type, stops):
    import generate_tour_text as g
    buf = io.StringIO()
    text = None
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _out, _coords = g.generate_tour_text(
                location, tour_type, None, len(stops),
                forced_stops=list(stops))
    except Exception as e:
        import traceback
        print(f"  [LOCAL-855E] raised: {e}", flush=True)
        traceback.print_exc()
    return text


def _split_blocks(text):
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    for (n, title), body in zip(titles, blocks[1:]):
        out.append((int(n), title.strip(), body))
    return out


# [LOCAL-855E item 3] The invented physical detail the SENSORY loophole shipped —
# a sea/coast/harbour, a harp, an altar, a film poster. None may appear in the
# delivered text.
_INVENTION_RE = re.compile(
    r"(?i)\b("
    r"sea|south\s+china\s+sea|coast|coastal|ocean|harbou?r|maritime|beach|"
    r"harp|altar|film\s+poster|film\s+posters|movie\s+poster|vintage\s+(?:film|movie)"
    r")\b")

_DUONG_STUB_RE = re.compile(r"(?m)\bĐ\.\s*$")


def _fold(t):
    import unicodedata
    nf = unicodedata.normalize("NFKD", t or "")
    nf = "".join(c for c in nf if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w\s]", " ", nf)


def _stop_is_about_venue(title, body):
    name_toks = {w for w in _fold(title).split()
                 if len(w) >= 3 and w not in {"the", "bar", "spa", "street"}}
    prose = "\n".join(
        ln for ln in body.split("\n")
        if not re.match(r"(?i)^(Address|Coordinates|Type/Specialty|"
                        r"Specific Examples|Directions):", ln.strip()))
    pf = _fold(prose)
    if not name_toks:
        return True
    return any(tok in pf for tok in name_toks)


def _check_run_a(text, run_label):
    checks = []
    blocks = _split_blocks(text)
    titles = [(n, t) for n, t, _ in blocks]

    checks.append(("7/7 delivered", len(blocks) == len(USER_STOPS),
                   f"{len(blocks)}/{len(USER_STOPS)}"))

    header = (text or "").split("\n", 1)[0]
    checks.append(("title is a Cycling tour (not Museum)",
                   "museum tour" not in header.lower()
                   and "cycl" in header.lower(), header.strip()[:90]))

    # [item 1] every delivered pin within 30 m of its INPUT @lat,lng
    pin_detail = []
    pin_ok = True
    for n, title, body in blocks:
        key = _fold(title).strip()
        exp = None
        for k, v in EXPECTED_PINS.items():
            if k in key or key in k:
                exp = v
                break
        cm = _COORD_RE.search(body)
        if exp is None:
            continue
        if not cm:
            pin_ok = False
            pin_detail.append(f"{title[:16]}: NO COORD")
            continue
        got = (float(cm.group(1)), float(cm.group(2)))
        d = _haversine_m(exp, got)
        if d > 30.0:
            pin_ok = False
            pin_detail.append(f"{title[:16]}: {d:.0f} m")
        else:
            pin_detail.append(f"{title[:16]}: {d:.0f} m OK")
    checks.append(("every pin within 30 m of input @lat,lng (item 1)",
                   pin_ok, "; ".join(pin_detail)))

    stub = _DUONG_STUB_RE.search(text or "")
    checks.append(('no "Đ." address stub (item 2)', not stub,
                   "none" if not stub else f"found: {stub.group(0)!r}"))

    inv = _INVENTION_RE.findall(text or "")
    checks.append(("no sea/coast/harp/altar/film-poster invention (item 3)",
                   not inv, "none" if not inv else f"{sorted(set(inv))}"))

    off_venue = [f"Stop {n} ({t[:20]})" for n, t, b in blocks
                 if not _stop_is_about_venue(t, b)]
    checks.append(("each stop is about its venue",
                   not off_venue, "all on-venue" if not off_venue
                   else ", ".join(off_venue)))

    return checks, titles


def _check_run_b(text):
    blocks = _split_blocks(text)
    nd = next((b for b in blocks if "notre" in b[1].lower()
               or "notre" in b[2].lower()), None)
    kept = False
    detail = "Notre-Dame stop not found"
    if nd:
        yrs = [int(y) for y in re.findall(r"\b(1[6-9]\d{2})\b", nd[2])]
        in_range = [y for y in yrs if 1863 <= y <= 1880]
        kept = bool(in_range)
        detail = (f"dates in 1863–1880 kept: {sorted(set(in_range))}"
                  if in_range else f"no 1863–1880 date (found {sorted(set(yrs))})")
    return [("Notre-Dame keeps a 1863–1880 date", kept, detail)], blocks


def _print_checks(label, checks):
    print(f"\n  ── {label} ──", flush=True)
    allok = True
    for name, ok, detail in checks:
        allok = allok and ok
        print(f"   [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return allok


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-855E live — Sophia 7-stop cycling x2 + Notre-Dame 3-stop ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-855E] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    meter = LiveRunMeter("LOCAL-855E")
    t0 = time.time()

    print("\n[RUN A1] Sophia's biking tour — 7 user stops (first run)", flush=True)
    text_a1 = _generate(LOCATION, TOUR_TYPE, USER_STOP_INPUTS)

    print("\n[RUN A2] Sophia's biking tour — 7 user stops (second run)", flush=True)
    text_a2 = _generate(LOCATION, TOUR_TYPE, USER_STOP_INPUTS)

    print("\n[RUN B] user stops incl. Notre-Dame Cathedral Basilica of Saigon",
          flush=True)
    text_b = _generate(LOCATION, "user stops walking tour", USER_STOPS_B)

    dt = time.time() - t0
    print(f"\n  all runs generated in {dt:.0f}s", flush=True)

    for fn in ("add_generation", "record"):
        try:
            (meter.add_generation(g) if fn == "add_generation"
             else meter.record())
        except Exception:
            pass
    try:
        print("  " + meter.summary().replace("\n", "\n  "), flush=True)
    except Exception:
        pass
    try:
        meter.uninstall()
    except Exception:
        pass

    art = os.path.join(_HERE, "submission_artifacts", "local855e")
    os.makedirs(art, exist_ok=True)
    if text_a1:
        with open(os.path.join(art, "live_tour_7stops_run1.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text_a1)
    if text_a2:
        with open(os.path.join(art, "live_tour_7stops_run2.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text_a2)
    if text_b:
        with open(os.path.join(art, "live_tour_notredame_3stops.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text_b)

    rows = _meter_rows()
    total = sum(float(r.get("usd") or 0.0) for r in rows
                if r.get("status") in (200, "200"))
    with open(os.path.join(art, "meter_ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"task_budget_id": "LOCAL-855E", "hard_cap_usd": HARD_CAP_USD,
                   "metered_total_usd": round(total, 6), "rows": len(rows)},
                  f, indent=2)

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-855E SUMMARY ===", flush=True)

    checks_a1, titles_a1 = _check_run_a(text_a1 or "", "A1")
    print("\n  Run A1 delivered stops:", flush=True)
    for n, t in titles_a1:
        print(f"    Stop {n}: {t[:70]}", flush=True)
    ok_a1 = _print_checks("RUN A1 (7-stop Sophia cycling, first)", checks_a1)

    checks_a2, titles_a2 = _check_run_a(text_a2 or "", "A2")
    print("\n  Run A2 delivered stops:", flush=True)
    for n, t in titles_a2:
        print(f"    Stop {n}: {t[:70]}", flush=True)
    ok_a2 = _print_checks("RUN A2 (7-stop Sophia cycling, second)", checks_a2)

    checks_b, _ = _check_run_b(text_b or "")
    ok_b = _print_checks("RUN B (Notre-Dame 1863–1880)", checks_b)

    budget_ok = total <= HARD_CAP_USD
    print(f"\n  metered total: ${total:.4f} / cap ${HARD_CAP_USD:.2f} "
          f"({'OK' if budget_ok else 'OVER'})", flush=True)

    verdict = ok_a1 and ok_a2 and ok_b and budget_ok
    print(f"\n=== LOCAL-855E OVERALL: {'PASS' if verdict else 'CHECK'} ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
