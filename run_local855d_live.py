#!/usr/bin/env python3
"""run_local855d_live.py — LOCAL-855D live, budget-enforced proof (Mac-local).

The second bounce of LOCAL-855. Re-runs Sophia's 7-stop CYCLING tour of Ho Chi
Minh City and a 3-stop regression whose first stop is a famous, documented place
(Notre-Dame Cathedral Basilica of Saigon), then checks the delivered text for the
855D PASS criteria.

INPUTS (Item 4). The field request (orch ef0cee57 / tour 525/523) pasted each
user stop as "Name + Google share link". Those exact cloud links are not
reachable from this Mac-local worktree (and we must never read/write the live
DB). The ticket's stated alternative is used: REAL Google Maps place URLs for the
District-1/3 venues, resolved through the LOCAL-852 resolver (user_stop_input).
Each URL carries `/maps/place/<Name>/@<lat>,<lng>` so it resolves OFFLINE to a
real name + coordinate with no paid API — which is the whole point: the prior run
used munged placeholder links ("https___share.google_z20B") that did not resolve,
so "Longan" geocoded by name to a Fruit Cafe and "Rambutan" to a Boutique Hotel.
The coordinates are the District-1/3 pins for the actual venues (Thi Bar at
Bùi Viện/Đề Thám, Acoustic Bar on Ngô Thời Nhiệm in Quận 3, etc.).

PASS (run A) = 7/7 delivered AND:
  * none of the eight quoted fabrications, or a paraphrase class of them, appears
    (checked literally AND by re-running the user_stop_narration scrub + the
    fact-sheet verifier's own judgement is exercised live during generation);
  * no "Đ." address stub ("Address: 15 Đ." etc. — item 1);
  * no walking words anywhere in the cycling tour (item 2);
  * each stop is about its venue (every stop body names its venue or kind).
PASS (run B) = Notre-Dame keeps a sourced date in 1863–1880.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-855D TASK_BUDGET_USD=0.40 (both runs share
the cap), meter contract, OWN meter dir ./_local855d_meterlogs (D753 Mac-local
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
os.environ["TASK_BUDGET_ID"] = "LOCAL-855D"
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

_METER_DIR = os.path.join(_HERE, "_local855d_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-855D"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# [LOCAL-855D item 4] REAL Google Maps place URLs for the District-1/3 venues,
# resolved offline by the LOCAL-852 resolver (name + @lat,lng in the URL). These
# replace the munged placeholder share links of the prior run.
G = "https://www.google.com/maps/place"
USER_STOPS = [
    f"Rambutan {G}/Rambutan/@10.7761,106.6962,18z",
    f"Longan {G}/Longan/@10.7791,106.6996,18z",
    f"The Crazy street {G}/Bui+Vien+Walking+Street/@10.7672,106.6930,18z",
    f"Thi Bar Saigon {G}/Thi+Bar+Saigon/@10.76766,106.69396,18z",
    f"A Star is Born {G}/A+Star+is+Born/@10.7760,106.6968,18z",
    f"Acoustic Bar {G}/Acoustic+Bar+Ngo+Thoi+Nhiem/@10.781195,106.68992,18z",
    f"An Spa {G}/An+Spa+Tran+Quoc+Thao/@10.7820,106.6935,18z",
]

# Run B: a 3-stop user-stops tour whose FIRST stop is a FAMOUS, documented place —
# its sourced dates (1863–1880) must survive (item: Notre-Dame keeps 1863–1880).
USER_STOPS_B = [
    "Notre-Dame Cathedral Basilica of Saigon",
    "Independence Palace",
    "Bến Thành Market",
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_ADDR_RE = re.compile(r"(?mi)^Address:\s*(.*)$")


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
        print(f"  [LOCAL-855D] raised: {e}", flush=True)
        traceback.print_exc()
    return text


def _split_blocks(text):
    out = []
    titles = _STOP_HEADER_RE.findall(text or "")
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    for (n, title), body in zip(titles, blocks[1:]):
        out.append((int(n), title.strip(), body))
    return out


# The EIGHT quoted fabrications from the ticket (item 3), plus their paraphrase
# roots. A PASS forbids any of these, or a paraphrase of them.
_BANNED = {
    # Longan
    "quiet homage to that mythic past": "Longan mythic-past fabrication",
    "mythic past": "Longan mythic-past (paraphrase root)",
    "Hagimex": "Longan Hagimex canned-longan fabrication",
    "not directly tied to this": "Longan 'not directly tied' hedge",
    # Crazy street
    "tumultuous weeks when the city": "Crazy-street war fabrication",
    "city's fate was being decided": "Crazy-street war fabrication (paraphrase)",
    # Thi Bar
    "opened doors for acceptance": "Thi Bar pioneering fabrication",
    "set a precedent for other venues": "Thi Bar precedent fabrication",
    # A Star is Born
    "story passed down through the neighborhood": "Star passed-down fabrication",
    "passed down through the neighborhood": "Star passed-down (paraphrase)",
    # Acoustic Bar
    "played a critical role for many local artists": "Acoustic critical-role fabrication",
    "critical role for many local artists": "Acoustic critical-role (paraphrase)",
}

_WALK_RE = re.compile(r"(?i)\b(walk|walking|walked|walks|stroll|strolling|on foot)\b")
_DUONG_STUB_RE = re.compile(r"Address:\s*\d*\s*Đ\.\s*$", re.M)
_DUONG_STUB_INLINE_RE = re.compile(r"\bĐ\.\s*$", re.M)


def _semantic_defect_scan(blocks):
    """Re-run the user_stop_narration scrub over each user-stop body; any sentence
    it would still drop is a residual fabrication the delivered text must not
    carry — catches a NEW paraphrase, not only the literal banned strings."""
    try:
        import user_stop_narration as _usn
    except Exception as _e:
        return [f"scan unavailable: {_e}"]
    findings = []
    for n, title, body in blocks:
        poi = {"name": title, "title": title, "user_explicit": True}
        tm = re.search(r"(?mi)^Type/Specialty:\s*(.+?)\s*$", body)
        if tm:
            poi["type_specialty"] = tm.group(1).strip()
        cm = _COORD_RE.search(body)
        if cm:
            poi["coordinates"] = f"{cm.group(1)}, {cm.group(2)}"
        for para in body.split("\n"):
            s = para.strip()
            if not s:
                continue
            m = re.match(r"(?i)^Orientation:\s*(.*)$", s)
            if m:
                val = m.group(1)
            elif re.match(r"(?i)^(Address|Coordinates|Type/Specialty|"
                          r"Specific Examples|Directions):", s):
                continue
            else:
                val = s
            _, dropped = _usn.scrub_user_stop_body(val, poi, LOCATION,
                                                   source_gated=True)
            for d in dropped:
                findings.append(f"Stop {n} ({title[:22]}): "
                                f"{' '.join(d.split()[:10])}…")
    return findings


def _stop_is_about_venue(n, title, body):
    """True when the stop body mentions its venue name or kind at least once."""
    import unicodedata
    def fold(t):
        nf = unicodedata.normalize("NFKD", t or "")
        nf = "".join(c for c in nf if not unicodedata.combining(c)).lower()
        return re.sub(r"[^\w\s]", " ", nf)
    name_toks = {w for w in fold(title).split()
                 if len(w) >= 3 and w not in {"the", "bar", "spa", "street"}}
    # strip field lines; look at prose only
    prose = "\n".join(
        ln for ln in body.split("\n")
        if not re.match(r"(?i)^(Address|Coordinates|Type/Specialty|"
                        r"Specific Examples|Directions):", ln.strip()))
    pf = fold(prose)
    if not name_toks:
        return True
    return any(tok in pf for tok in name_toks)


def _check_run_a(text):
    checks = []
    blocks = _split_blocks(text)
    titles = [(n, t) for n, t, _ in blocks]

    checks.append(("7/7 delivered", len(blocks) == len(USER_STOPS),
                   f"{len(blocks)}/{len(USER_STOPS)}"))

    header = (text or "").split("\n", 1)[0]
    checks.append(("title is a Cycling tour (not Museum)",
                   "museum tour" not in header.lower()
                   and "cycl" in header.lower(), header.strip()[:90]))

    low = (text or "")
    present = [desc for marker, desc in _BANNED.items() if marker.lower() in low.lower()]
    checks.append(("none of the 8 quoted fabrications (or paraphrase) present",
                   not present, ", ".join(present) if present else "none"))

    sem = _semantic_defect_scan(blocks)
    checks.append(("semantic fabrication scan clean",
                   not sem,
                   "clean" if not sem else f"{len(sem)}: " + " | ".join(sem[:4])))

    stub = _DUONG_STUB_RE.search(text or "") or re.search(
        r"(?m)\bĐ\.\s*$", text or "")
    checks.append(('no "Đ." address stub (item 1)', not stub,
                   "none" if not stub else f"found: {stub.group(0)!r}"))

    walks = _WALK_RE.findall(text or "")
    checks.append(("no walking words in the cycling tour (item 2)",
                   not walks, "none" if not walks else f"{len(walks)}: {walks[:6]}"))

    off_venue = [f"Stop {n} ({t[:20]})" for n, t, b in blocks
                 if not _stop_is_about_venue(n, t, b)]
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
    print("=== LOCAL-855D live — Sophia 7-stop cycling + Notre-Dame 3-stop ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print("  inputs: REAL Google Maps place URLs (item 4), resolved offline by "
          "the LOCAL-852 resolver", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-855D] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    meter = LiveRunMeter("LOCAL-855D")
    t0 = time.time()

    print("\n[RUN A] Sophia's biking tour — 7 user stops", flush=True)
    text_a = _generate(LOCATION, TOUR_TYPE, USER_STOPS)

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

    art = os.path.join(_HERE, "submission_artifacts", "local855d")
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
        json.dump({"task_budget_id": "LOCAL-855D", "hard_cap_usd": HARD_CAP_USD,
                   "metered_total_usd": round(total, 6), "rows": len(rows)},
                  f, indent=2)

    checks_a, titles_a = _check_run_a(text_a or "")
    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-855D SUMMARY ===", flush=True)
    print("  Run A delivered stops:", flush=True)
    for n, t in titles_a:
        print(f"    Stop {n}: {t[:70]}", flush=True)
    ok_a = _print_checks("RUN A (7-stop Sophia cycling)", checks_a)

    checks_b, _ = _check_run_b(text_b or "")
    ok_b = _print_checks("RUN B (Notre-Dame 1863–1880)", checks_b)

    budget_ok = total <= HARD_CAP_USD
    print(f"\n  metered total: ${total:.4f} / cap ${HARD_CAP_USD:.2f} "
          f"({'OK' if budget_ok else 'OVER'})", flush=True)

    verdict = ok_a and ok_b and budget_ok
    print(f"\n=== LOCAL-855D OVERALL: {'PASS' if verdict else 'CHECK'} ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
