#!/usr/bin/env python3
"""run_local855b_live.py — LOCAL-855B live, budget-enforced proof (Mac-local).

The bounce of LOCAL-855. Re-runs the EXACT field request ("Sophia's biking tour
in Ho Chi Minh City", seven user-chosen stops) and checks the NARRATION for the
TEN defects LEAD found in the delivered text, plus a second short run proving a
FAMOUS user stop (Notre-Dame Cathedral Basilica of Saigon) KEEPS its sourced
dates (defect 8 must not over-scrub).

PASS (run A) = 7/7 stops delivered AND every one of the ten defects absent:
  1  title is not "… - Museum Tour" (a user-stops tour is not a museum);
  2  no city-specific transit ("T station") in directions;
  3  no folk-tale/legend narration (dragon/village/robber/stolen eye);
  4  no fabricated anecdote/firsts ("one pivotal night", "that evening changed",
     "credits … first record deal", "recording contract", "launched her career");
  5  no "no direct tie/link" hedge + national-figure biography;
  6  no District-1 landmark (Đồng Khởi / Lam Sơn Square / Saigon Municipal
     Theatre / Rue N°6) in the District-3 An Spa stop;
  7  The Crazy street pinned near Bùi Viện (~10.767,106.693), not next to Rambutan;
  8  no unsourced dated fabrication from the LOCAL-852 run (VietPride 2018, Bức
     Tường, airport, Cần Thơ merger, 1975 offensive);
  9  (unit-tested — per-job title store; not observable in one tour's text);
  10 no generic "<stop> is one you might carry with you." closer.

PASS (run B) = the 3-stop tour with Notre-Dame keeps at least one sourced date
  (e.g. "1863", "1877", "1880").

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-855B TASK_BUDGET_USD=0.50 (both runs share
the cap), meter contract, own meter log under ./_local855b_meterlogs, cheap env +
STORY_PASS_MODEL=gpt-4.1, pool OFF. Mac-LOCAL diagnostic (the documented no-mount
escape hatch, D753): METER_MOUNT_GUARD=0. It never writes the shared/live DB and
never touches the shared audioura-* containers.
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
os.environ["TASK_BUDGET_ID"] = "LOCAL-855B"
os.environ["TASK_BUDGET_USD"] = os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
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

_METER_DIR = os.path.join(_HERE, "_local855b_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-855B"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

USER_STOPS = [
    "Rambutan https___share.google_1v4x",
    "Longan https___share.google_z20B",
    "The Crazy street",
    "The LGBT bar 🌈Thi Bar Saigon",
    "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3",
    "An Spa at https___an-spa.vn_en",
]

# Run B: a 3-stop user-stops tour whose FIRST stop is a FAMOUS, well-documented
# place — its sourced dates must survive the scrub (defect 8).
USER_STOPS_B = [
    "Notre-Dame Cathedral Basilica of Saigon",
    "Independence Palace",
    "Bến Thành Market",
]

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
        print(f"  [LOCAL-855B] raised: {e}", flush=True)
        traceback.print_exc()
    return text


def _split_blocks(text):
    """Return list of (n, title, body) per stop."""
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    # blocks[0] is the preamble; blocks[1:] align with titles
    for (n, title), body in zip(titles, blocks[1:]):
        out.append((int(n), title.strip(), body))
    return out


# Markers that must be ABSENT from the delivered text (defects 2,3,4,5,8).
# [LOCAL-855B bounce] Strengthened: the first 855B run rephrased every defect
# past the old literal markers (Caillebotte/canvas for the Chicago painting,
# "one account … springboard" for the record-deal anecdote, "turning point /
# opened a door" for the firsts claim, "Hồ Tràm / a hundred kilometers southeast"
# for the off-pin placement, "fruit market / longan fruit" for the wrong subject,
# "history of the twenty-first century" for the closer). Each is now banned so a
# rephrased defect can no longer slip past the runner.
_BANNED = {
    # 2 — city-specific transit
    "T station": "T station (Boston transit leak)",
    "MBTA": "Boston MBTA leak",
    # 3 — the dragon legend
    "hatched a dragon": "dragon legend",
    "stolen eye": "dragon legend (stolen eye)",
    "the village survive": "dragon legend (village)",
    "dragon's eye": "dragon legend (dragon's eye)",
    # 3b — the Caillebotte / art-provenance digression (rephrased)
    "Caillebotte": "art digression (Caillebotte)",
    "the canvas": "art digression (the canvas)",
    "Art Institute of Chicago": "cross-tour callback / art provenance",
    "oil painting": "art digression (oil painting)",
    # NOTE (resolution, not narration): "longan fruit" / "Fruit Market" is NOT
    # banned here. In this offline reproduction the listener's Google share links
    # are munged placeholders ("https___share.google_z20B") that do not resolve,
    # so "Longan" geocodes BY NAME to a real HCMC fruit market and its Type comes
    # back "Fruit Market". Narrating a fruit market is then FAITHFUL to what
    # resolved — not a narration fabrication the scrub can fix. The field request
    # had working links that resolved to the bar; that resolution is out of scope
    # for a link-less reproduction. The narration DEFECT for this stop (defect 3,
    # the dragon LEGEND) is banned above and is gone.
    # 4 — fabricated anecdotes / firsts (original + rephrased)
    "one pivotal night": "fabricated anecdote (pivotal night)",
    "that evening changed": "fabricated anecdote (that evening changed)",
    "first record deal": "fabricated anecdote (first record deal)",
    "recording contract": "fabricated anecdote (recording contract)",
    "launched her career": "fabricated anecdote (launched career)",
    "one account that lingers": "fabricated anecdote (one account)",
    "opened doors to professional": "fabricated anecdote (opened doors)",
    "springboard": "fabricated anecdote (springboard)",
    "local obscurity": "fabricated anecdote (local obscurity)",
    "turning point": "fabricated firsts (turning point)",
    "opened a door for": "fabricated firsts (opened a door)",
    "on its opening evening": "fabricated firsts (opening evening)",
    "step into public view": "fabricated firsts (public view)",
    # 5 — off-topic hedge
    "no direct tie": "off-topic hedge (no direct tie)",
    "no direct link": "off-topic hedge (no direct link)",
    "Nguyễn Sinh Cung": "off-topic biography (Hồ Chí Minh)",
    # 6 — District-1 landmarks in the An Spa (District-3) stop + Hồ Tràm beach
    "Lam Sơn Square": "off-pin landmark (Lam Sơn Square)",
    "Đồng Khởi": "off-pin landmark (Đồng Khởi)",
    "Saigon Municipal Theatre": "off-pin landmark (Municipal Theatre)",
    "Rue N°6": "off-pin landmark (Rue N°6)",
    "Hồ Tràm": "off-pin placement (Hồ Tràm beach ~100km)",
    "Ho Tram": "off-pin placement (Ho Tram beach ~100km)",
    "coastal commune": "off-pin placement (coastal commune)",
    "kilometers southeast": "off-pin placement (distance from city)",
    "Xuyên Mộc": "off-pin placement (Xuyên Mộc district)",
    "Bà Rịa": "off-pin placement (Bà Rịa–Vũng Tàu province)",
    # 8 — known LOCAL-852 dated fabrications
    "VietPride 2018": "dated fabrication (VietPride 2018)",
    "VietPride 2019": "dated fabrication (VietPride 2019)",
    "Bức Tường": "dated fabrication (Bức Tường)",
    "Long Thanh International Airport": "airport filler",
    "Resolution No. 202/2025": "Cần Thơ merger filler",
    "1975 spring offensive": "war filler",
    "Le Van Sy Street": "invented street",
    # 10 — generic / nonsensical closer
    "is one you might carry with you": "generic closer",
    "history of the twenty-first century": "false/generic closer (century thread)",
}

# [LOCAL-855B bounce] A semantic scan over each USER-STOP body, mirroring the
# user_stop_narration scrub detectors. The literal _BANNED list catches known
# phrasings; this catches the CLASS (legend / anecdote / hedge / off-pin / art)
# so a NEW rephrasing on a future run still fails the runner rather than passing.
def _semantic_defect_scan(blocks):
    try:
        import user_stop_narration as _usn
    except Exception as _e:
        return [("semantic scan unavailable", False, str(_e))]
    try:
        import cross_stop_reference_guard as _csrg
    except Exception:
        _csrg = None
    findings = []
    for n, title, body in blocks:
        poi = {"name": title, "title": title, "user_explicit": True}
        tm = re.search(r"(?mi)^Type/Specialty:\s*(.+?)\s*$", body)
        if tm:
            poi["type_specialty"] = tm.group(1).strip()
        cm = _COORD_RE.search(body)
        if cm:
            poi["coordinates"] = f"{cm.group(1)}, {cm.group(2)}"
        # Scrub every narration paragraph (not field/structure lines).
        for para in body.split("\n"):
            s = para.strip()
            if not s or re.match(r"(?i)^(Address|Coordinates|Type/Specialty|"
                                 r"Specific Examples|Directions|Orientation):?$", s):
                continue
            val = s
            m = re.match(r"(?i)^Orientation:\s*(.*)$", s)
            if m:
                val = m.group(1)
            elif re.match(r"(?i)^(Address|Coordinates|Type/Specialty|"
                          r"Specific Examples|Directions):", s):
                continue
            _, dropped = _usn.scrub_user_stop_body(
                val, poi, LOCATION, source_gated=True)
            for d in dropped:
                findings.append(f"Stop {n} ({title[:24]}): {' '.join(d.split()[:10])}…")
    # Cross-stop callback residue (the 'sackbut you paused beside earlier' class):
    # a user-stops tour must carry none. Re-run the zero-budget stripper over the
    # whole delivered text — any drop is a residual callback defect.
    if _csrg is not None:
        full = "\n\n".join(f"Stop {n}: {t}\n\n{b}" for n, t, b in blocks)
        try:
            _, n_cb = _csrg.strip_all_cross_stop_callbacks_in_text(full)
            if n_cb:
                findings.append(f"{n_cb} cross-stop callback sentence(s) (no "
                                f"shared thread on a user-stops tour)")
        except Exception:
            pass
    return findings


def main_defect_scan(text):
    return _semantic_defect_scan(_split_blocks(text))


def _check_run_a(text):
    checks = []
    blocks = _split_blocks(text)
    titles = [(n, t) for n, t, _ in blocks]

    # 7/7 delivered
    checks.append(("7/7 delivered", len(blocks) == len(USER_STOPS),
                   f"{len(blocks)}/{len(USER_STOPS)}"))

    # 1 — title not "Museum Tour"
    header = (text or "").split("\n", 1)[0]
    checks.append(("1 title not Museum",
                   "museum tour" not in header.lower(), header.strip()[:90]))

    # 2..6,8,10 — banned markers absent
    low = (text or "")
    present = [desc for marker, desc in _BANNED.items() if marker in low]
    checks.append(("2/3/4/5/6/8/10 banned markers absent",
                   not present, (", ".join(present) if present else "none")))

    # 7 — The Crazy street pin near Bùi Viện (~10.767,106.693)
    crazy = next((b for b in blocks if "crazy" in b[1].lower()), None)
    crazy_ok, crazy_detail = False, "stop not found"
    if crazy:
        cm = _COORD_RE.search(crazy[2])
        if cm:
            lat, lng = float(cm.group(1)), float(cm.group(2))
            d = _haversine_m((lat, lng), (10.7672, 106.6930))
            crazy_ok = d <= 350.0
            crazy_detail = f"pin ({lat},{lng}) is {d:.0f} m from Bùi Viện"
        else:
            crazy_detail = "no coordinate line parsed"
    checks.append(("7 Crazy-street pin near Bùi Viện", crazy_ok, crazy_detail))

    # [LOCAL-855B bounce] Semantic class scan: any user-stop body sentence the
    # user_stop_narration scrub would still drop is a residual defect, EVEN IF it
    # uses a phrasing not in the literal _BANNED list. This is what keeps the
    # runner honest against future rephrasings.
    sem = _semantic_defect_scan(blocks)
    checks.append(("semantic defect scan (legend/anecdote/hedge/off-pin/art)",
                   not sem,
                   "clean" if not sem else f"{len(sem)} residual: " + " | ".join(sem[:4])))

    return checks, titles


def _check_run_b(text):
    """Run B: Notre-Dame stop keeps at least one sourced date."""
    blocks = _split_blocks(text)
    nd = next((b for b in blocks if "notre" in b[1].lower()
               or "notre" in b[2].lower()), None)
    kept = False
    detail = "Notre-Dame stop not found"
    if nd:
        body = nd[2]
        yrs = re.findall(r"\b(1[6-9]\d{2})\b", body)
        kept = bool(yrs)
        detail = (f"dates kept: {sorted(set(yrs))}" if yrs
                  else "NO date survived (over-scrubbed)")
    return [("B Notre-Dame keeps a sourced date", kept, detail)], blocks


def _print_checks(label, checks):
    print(f"\n  ── {label} ──", flush=True)
    allok = True
    for name, ok, detail in checks:
        allok = allok and ok
        print(f"   [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return allok


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-855B live — Sophia 7-stop + Notre-Dame 3-stop, HCMC ===",
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
        print(f"[LOCAL-855B] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    meter = LiveRunMeter("LOCAL-855B")
    t0 = time.time()

    # ── Run A: the 7-stop Sophia biking tour ──
    print("\n[RUN A] Sophia's biking tour — 7 user stops", flush=True)
    text_a = _generate(LOCATION, TOUR_TYPE, USER_STOPS)

    # ── Run B: the 3-stop user-stops tour with a famous first stop ──
    print("\n[RUN B] user stops incl. Notre-Dame Cathedral Basilica of Saigon",
          flush=True)
    text_b = _generate(LOCATION, "user stops walking tour", USER_STOPS_B)

    dt = time.time() - t0
    print(f"\n  both runs generated in {dt:.0f}s", flush=True)

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

    # Save artifacts.
    art = os.path.join(_HERE, "submission_artifacts", "local855b")
    os.makedirs(art, exist_ok=True)
    if text_a:
        with open(os.path.join(art, "live_tour_7stops.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text_a)
    if text_b:
        with open(os.path.join(art, "live_tour_notredame_3stops.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text_b)

    rows = _meter_rows()
    total = sum(float(r.get("usd") or 0.0) for r in rows
                if r.get("status") in (200, "200"))
    with open(os.path.join(art, "meter_ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"task_budget_id": "LOCAL-855B", "hard_cap_usd": HARD_CAP_USD,
                   "metered_total_usd": round(total, 6), "rows": len(rows)},
                  f, indent=2)

    # ── PASS checks ──
    checks_a, titles_a = _check_run_a(text_a or "")
    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-855B SUMMARY ===", flush=True)
    print("  Run A delivered stops:", flush=True)
    for n, t in titles_a:
        print(f"    Stop {n}: {t[:70]}", flush=True)
    ok_a = _print_checks("RUN A (7-stop Sophia)", checks_a)

    checks_b, _ = _check_run_b(text_b or "")
    ok_b = _print_checks("RUN B (Notre-Dame sourced dates)", checks_b)

    budget_ok = total <= HARD_CAP_USD
    print(f"\n  metered total: ${total:.4f} / cap ${HARD_CAP_USD:.2f} "
          f"({'OK' if budget_ok else 'OVER'})", flush=True)

    verdict = ok_a and ok_b and budget_ok
    print(f"\n=== LOCAL-855B OVERALL: {'PASS' if verdict else 'CHECK'} ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
