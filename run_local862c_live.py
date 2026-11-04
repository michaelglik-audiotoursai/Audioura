#!/usr/bin/env python3
"""run_local862c_live.py — LOCAL-862C live, budget-enforced proof (Mac-local).

Sophia's 7-stop CYCLING tour of Ho Chi Minh City (same inputs as run_local855e_live)
with the user-stop ENRICHMENT path (Places record + customer_voice + venue site +
one story search -> narrate from that material only -> verify against it), plus a
3-stop Notre-Dame landmark regression. TASK_BUDGET_ID=LOCAL-862C
TASK_BUDGET_USD=0.35, meter contract, OWN meter dir (D753 Mac-local escape hatch:
never the shared/live DB, never the shared audioura-* containers).
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
os.environ["TASK_BUDGET_ID"] = "LOCAL-862C"
os.environ["TASK_BUDGET_USD"] = "0.35"
HARD_CAP_USD = 0.35
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

_METER_DIR = os.path.join(_HERE, "_local862c_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-862C"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# [LOCAL-862C item 4] REAL Google Maps place URLs for the District-1/3 venues,
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
        print(f"  [LOCAL-862C] raised: {e}", flush=True)
        traceback.print_exc()
    return text


def _split_blocks(text):
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    for (n, title), body in zip(titles, blocks[1:]):
        out.append((int(n), title.strip(), body))
    return out


# [LOCAL-862C item 3] The invented physical detail the SENSORY loophole shipped —
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


def _sentences(t):
    from user_stop_narration import _split_sentences
    return _split_sentences(t)


def _stop_prose(body):
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


def _check_862c(blocks, rep):
    """LOCAL-862C: one disclosed legend block, a bridge on name-based stops, no
    duplicated list items.  A sentence whose words are carried by the stop's own
    layer-2 facts (a name-meaning sentence) is context, not a legend."""
    from user_stop_context import DISCLOSURE_RE, _LEGEND_VOCAB_RE as _LV, dedupe_names, _content_tokens
    l2 = {}
    for st in (rep or {}).get("stops", []):
        l2[st.get("stop")] = " ".join(f[2] for f in st.get("facts", []) if f[4] == 2)
    legend_bad, bridge_bad, dup_bad = [], [], []
    print("\n  -- 862C: legend blocks / bridges / duplicates --", flush=True)
    for n, t, b in blocks:
        ss = _sentences(_stop_prose(b))
        l2t = _content_tokens(l2.get(t, ""))
        marks = [i for i, s_ in enumerate(ss) if DISCLOSURE_RE.search(s_)
                 and re.search(r"(?i)folk\s*tale|legend|stor(?:y|ies)\s+(?:tells|goes)", s_)]
        legendish = [i for i, s_ in enumerate(ss) if _LV.search(s_) and not _is_meaning(s_, t)
                     and len(_content_tokens(s_) & l2t) < 0.7 * max(1, len(_content_tokens(s_)))]
        if marks:
            if len(marks) > 1:
                legend_bad.append((t, f"marker repeated {len(marks)}x"))
            elif len(ss) - marks[0] < 2:
                legend_bad.append((t, "legend is a single-sentence fragment"))
        elif legendish:
            legend_bad.append((t, "legend vocabulary without a disclosed block"))
        for s_ in ss:
            if dedupe_names(s_) != s_:
                dup_bad.append((t, s_))
        prose = " ".join(ss)
        name_based = bool(re.search(r"(?i)\bthe name\b|title of a|literally mean", prose))
        has_bridge = bool(re.search(r"(?i)probably\s+(?:takes\s+its\s+name|comes\s+from)|"
                                    r"takes\s+its\s+name\s+from|name\s+comes\s+from", prose))
        if name_based and not has_bridge:
            bridge_bad.append(t)
        print(f"   Stop {n} {t[:20]:20s} name_based={name_based} bridge={has_bridge} "
              f"legend_marks={len(marks)}", flush=True)
    print(f"  [{'PASS' if not legend_bad else 'FAIL'}] every legend one coherent disclosed block: {legend_bad or 'ok (none told, or one block)'}", flush=True)
    print(f"  [{'PASS' if not bridge_bad else 'FAIL'}] each name-based stop has a bridge: {bridge_bad or 'ok'}", flush=True)
    print(f"  [{'PASS' if not dup_bad else 'FAIL'}] no duplicated list items: {dup_bad or 'ok'}", flush=True)
    return legend_bad, bridge_bad, dup_bad


def main():
    if "--check-only" in sys.argv:       # re-check saved output; no network, no spend
        art = os.path.join(_HERE, "submission_artifacts", "local862c")
        text = open(os.path.join(art, "live_tour_7stops.txt"), encoding="utf-8").read()
        rep = json.load(open(os.path.join(art, "enrichment_report.json"), encoding="utf-8"))
        blocks = _split_blocks(text)
        under = [t for n, t, b in blocks if len(_sentences(_stop_prose(b))) < 4]
        print(f"  sentences<4: {under or 'none'}")
        lb, bb, db = _check_862c(blocks, rep)
        return 0 if not (under or lb or bb or db) else 1
    print("=" * 72, flush=True)
    print("=== LOCAL-862C live - Sophia 7-stop cycling tour (D760 layers) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    rows0 = _meter_rows()
    prior = sum(float(r.get("usd") or 0.0) for r in rows0 if r.get("status") in (200, "200"))
    if prior >= HARD_CAP_USD:
        print(f"[LOCAL-862C] budget exhausted (${prior:.4f})", flush=True)
        return 2
    from live_run_meter import LiveRunMeter
    import generate_tour_text as g
    meter = LiveRunMeter("LOCAL-862C")
    t0 = time.time()
    text = _generate(LOCATION, TOUR_TYPE, USER_STOP_INPUTS)
    import user_stop_enrichment as _use
    rep = getattr(_use, "LAST_REPORT", None)
    print(f"\n  generated in {time.time()-t0:.0f}s", flush=True)
    for fn in ("add_generation", "record"):
        try:
            (meter.add_generation(g) if fn == "add_generation" else meter.record())
        except Exception:
            pass
    try:
        print("  " + meter.summary().replace("\n", "\n  "), flush=True)
        meter.uninstall()
    except Exception:
        pass
    art = os.path.join(_HERE, "submission_artifacts", "local862c")
    os.makedirs(art, exist_ok=True)
    if text:
        open(os.path.join(art, "live_tour_7stops.txt"), "w", encoding="utf-8").write(text)
    if rep:
        json.dump(rep, open(os.path.join(art, "enrichment_report.json"), "w"),
                  indent=2, ensure_ascii=False, default=str)
    rows = _meter_rows()
    total = sum(float(r.get("usd") or 0.0) for r in rows if r.get("status") in (200, "200"))
    json.dump({"task_budget_id": "LOCAL-862C", "hard_cap_usd": HARD_CAP_USD,
               "metered_total_usd": round(total, 6), "rows": len(rows)},
              open(os.path.join(art, "meter_ledger.json"), "w"), indent=2)

    checks, titles = _check_run_a(text or "", "A")
    ok = _print_checks("structural (pins, no invention words)", checks)
    blocks = _split_blocks(text or "")
    print("\n  ── sentences per stop ──", flush=True)
    under = []
    for n, t, b in blocks:
        k = len(_sentences(_stop_prose(b)))
        print(f"   Stop {n} {t[:24]:24s} {k} sentence(s)", flush=True)
        if k < 4:
            under.append(t)
    print(f"  [{'PASS' if not under else 'FAIL'}] no stop under 4 sentences: {under or 'none'}", flush=True)

    from user_stop_context import has_disclosure, _LEGEND_VOCAB_RE
    print("\n  ── layer-3 sentences (legend / unconfirmed) with their marker ──", flush=True)
    bad = []
    for n, t, b in blocks:
        for s in _sentences(_stop_prose(b)):
            d = has_disclosure(s)
            if d or _LEGEND_VOCAB_RE.search(s):
                m = None
                from user_stop_context import DISCLOSURE_RE
                mm = DISCLOSURE_RE.search(s)
                m = mm.group(0) if mm else None
                print(f"   Stop {n} {t[:18]}: marker={m!r}\n      {s}", flush=True)
                if not d and not _is_meaning(s, t):
                    bad.append((t, s))
    print(f"  [{'PASS' if not bad else 'FAIL'}] every legend sentence carries a disclosure: "
          f"{len(bad)} undisclosed", flush=True)
    for t, s in bad:
        print(f"     UNDISCLOSED {t}: {s}", flush=True)
    legend_bad, bridge_bad, dup_bad = _check_862c(blocks, rep)
    print(f"\n  metered total: ${total:.4f} / cap ${HARD_CAP_USD:.2f}", flush=True)
    verdict = (ok and not under and not bad and not legend_bad and not bridge_bad
               and not dup_bad and total <= HARD_CAP_USD)
    print(f"=== LOCAL-862C OVERALL: {'PASS' if verdict else 'CHECK'} (truth checks beyond "
          f"this script: read every sentence) ===", flush=True)
    return 0 if verdict else 1


def _is_meaning(s, title):
    from user_stop_context import is_name_meaning_sentence
    return is_name_meaning_sentence(s, title)


if __name__ == "__main__":
    raise SystemExit(main())
