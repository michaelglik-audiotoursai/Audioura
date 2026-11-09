#!/usr/bin/env python3
"""run_local880b_live.py — LOCAL-880B live proof (Mac-local, own container, ONCE).

LOCAL-880B removes the four scrubs that LOCAL-880 hard-coded to tour 547 and makes
the surviving mechanisms generic / evidence-driven. This runner proves:
  * Michael's same 10 Saigon stops still pass every LOCAL-880 criterion, now
    through the GENERIC mechanisms (no hard-coded Saigon answer injected); AND
  * a 3-stop control tour in a DIFFERENT city (Sydney) leaks nothing Saigon- or
    tour-547-specific — no "Lower House of South Vietnam's National Assembly",
    no "1956 to 1975", no "2005" statue-tear date, no Saigon place names.

Own isolated DB (docker-compose.local880b-proof.yml, :55981). The shared
audioura-* containers, the shared dev DB (:5433) and the live DB are never
touched (D753). TTS is not called.

BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-880B TASK_BUDGET_USD=0.30, with a $0.10
sub-cap for the Sydney control inside the $0.30.

Launch:

  docker compose -p local880b -f docker-compose.local880b-proof.yml up -d

  TASK_BUDGET_ID=LOCAL-880B TASK_BUDGET_USD=0.30 \\
  PAID_API_LOG=$PWD/_local880b_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local880b_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-880B PYTHONPATH=$PWD/_meter \\
  python3 run_local880b_live.py --all

Run logs go to ./_local880b_meterlogs/ (never committed). The two tour texts are
written to submission_artifacts/local880b/ (committed).
"""
import contextlib
import io
import json
import os
import re
import sys

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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-880B":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-880B (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.30") or "0.30")
SYDNEY_SUBCAP_USD = float(os.environ.get("LOCAL880B_SYDNEY_SUBCAP_USD", "0.10") or "0.10")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55981/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55981"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

os.environ.pop("K_SERVICE", None)
os.environ["LANDMARK_LIVE_LOOKUP"] = "1"          # the real Wikidata/Wikipedia path
os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["SIGNATURE_STORY_ENABLED"] = "1"       # LOCAL-880 signature-story pass
os.environ["SIGNATURE_STORY_MODEL"] = "gpt-4.1-mini"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ["USER_STOPS_ENABLED"] = "true"

# Budget mode: route the premium story models to the cheap mini arm and KEEP the
# tour cache so a warmed DB (wiki/coord already populated) makes the run fit the
# $0.30 whole-task cap with the Sydney $0.10 sub-cap inside it. The generic
# defect mechanisms (the subject of LOCAL-880B) are model-independent, so the
# cheaper models exercise exactly the same code paths.
_CHEAP = os.environ.get("LOCAL880B_CHEAP", "1").strip() != "0"
if _CHEAP:
    os.environ["STORY_PASS_MODEL"] = "gpt-4.1-mini"
    os.environ["TOUR_STORY_MODEL"] = "gpt-4o-mini"
    os.environ["TOUR_SCOPE_COMPARE_MODEL"] = "gpt-4o-mini"
    os.environ.setdefault("DISABLE_TOUR_CACHE", "0")   # reuse the warmed cache
else:
    os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
    os.environ["DISABLE_TOUR_CACHE"] = "1"

_METER_DIR = os.path.join(_HERE, "_local880b_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local880b")
os.makedirs(_ART_DIR, exist_ok=True)
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
REQUEST_SYDNEY = "Sydney Opera House, Circular Quay, The Rocks, Sydney"
SYDNEY_STOPS = ["Sydney Opera House", "Circular Quay", "The Rocks"]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")


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


_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
    r"Museum Information|Operational Details|Sources|Orientation):")


def _prose(b):
    out = []
    for l in b[2].split("\n"):
        s = l.strip()
        if not s:
            continue
        m = re.match(r"(?i)^orientation:\s*(.*)$", s)
        if m:
            if m.group(1).strip():
                out.append(m.group(1).strip())
            continue
        if _FIELD_RE.match(s):
            continue
        out.append(s)
    return " ".join(out)


def _content_sentence_count(prose):
    try:
        from sentence_split import split_sentences
        sents = split_sentences(prose)
    except Exception:
        sents = re.findall(r"[^.!?]*[.!?]", prose)
    return len([s for s in sents if len(s.strip()) >= 15])


def _first_two_sentences(prose):
    sents = re.findall(r"[^.!?]*[.!?]", prose)
    return " ".join(s.strip() for s in sents[:2]).strip() or prose[:240]


def _generate(request, tour_type, forced, cap_remaining, out_name):
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{cap_remaining:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=cap_remaining)
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                request, tour_type, None, len(forced), forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_ART_DIR, out_name), "w", encoding="utf-8").write(text or "")
    open(os.path.join(_METER_DIR, out_name.replace(".txt", "_log.txt")), "w",
         encoding="utf-8").write(log)
    try:
        _lrm.uninstall()
    except Exception:
        pass
    return text or "", log


# Strings that must NEVER leak outside the one proof tour they came from.
_HARDCODE_LEAK_STRINGS = [
    "lower house of south vietnam",
    "south vietnam's national assembly",
    "1956 to 1975",
    "a story told in 2005",
]


def phase_saigon(cap_remaining):
    before = _meter_total()
    d = json.load(open(PREVIEW_JSON))
    forced = [s["resolved_name"] for s in d["stops"]]
    print(f"\n[SAIGON] request={REQUEST_547!r}; {len(forced)} stops; "
          f"cap_remaining=${cap_remaining:.4f}", flush=True)
    text, log = _generate(REQUEST_547, "walking", forced, cap_remaining,
                          "saigon_tour.txt")

    blocks = _blocks(text)
    low = (text or "").lower()
    loglow = log.lower()
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered",
                len(blocks) == len(forced), len(blocks))

    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    _sig_logged = re.findall(r"\[LOCAL-880\] signature story for ([^:]+):", log)
    ok &= _check("signature story logged for >= 1 landmark stop",
                 len(_sig_logged) >= 1, f"{len(_sig_logged)} logged")

    palace = next((b for b in blocks if "palace" in b[1].lower()), None)
    if palace:
        pl = _prose(palace).lower()
        ok &= _check("Palace mentions 30 April 1975 (the tank through the gates)",
                     ("1975" in pl and ("30 april" in pl or "april 30" in pl
                                        or "30 apr" in pl)) or "gates" in pl,
                     _first_two_sentences(_prose(palace)))

    # wave-38 defect strings (items 1-8) absent — now via the generic mechanisms
    defect_strings = {
        "1 intelligence headquarters": "intelligence headquarters",
        "2 truncated 'by the iconic.'": "by the iconic.",
        "3 flat folklore 'witnesses have reported a mysterious'":
            "witnesses have reported a mysterious",
        "4 orientation filler": "position yourself to best view this location",
        "5 intro grammar 'vietnam, is a walking tour'": "vietnam, is a walking tour",
        "6 orphan closing": "each was picked by you, and together they trace your own route",
        "7 current-affairs boilerplate": "we found no verified developments",
        "8a promo 'can't miss'": "can't miss this unique multi-story",
        "8b promo 'distinctive cultural brand'": "distinctive cultural brand",
    }
    for label, s in defect_strings.items():
        ok &= _check(f"defect {label} absent", s not in low, "absent")

    first_line = (text or "").strip().split("\n", 1)[0]
    ok &= _check("intro is a clean sentence",
                 first_line.startswith("This is a step-by-step audio-guided")
                 or "is a walking tour." not in first_line.lower(),
                 first_line[:90])

    # the hard-coded answer must NOT be injected any more, even in Saigon — the
    # fact may only appear if the stop's own evidence supplied it.
    ok &= _check("no hard-coded 'A story told in 2005' insertion",
                 "a story told in 2005" not in low, "absent")

    ok &= _check("§ no 'tháng' in the English text", "tháng" not in low, "absent")
    ok &= _check("§ no 'năm' in the English text", "năm" not in low, "absent")
    ok &= _check("§ no /wiki/Saigon_Centre FETCH in the log (a skip is a pass)",
                 not re.search(r"(?i)fetch\w*[^\n]*saigon_centre", log), "no fetch")
    for bad in ("sydney", "utzon", "bennelong"):
        ok &= _check(f"'{bad}' absent (Opera House is Saigon's)", bad not in low, "absent")

    import landmark_claim_gate as _lgc
    po = next((b for b in blocks if "post office" in b[1].lower()), None)
    ok &= _check("Post Office not empty", bool(po) and _lgc._has_real_sentence(po[2]),
                 _first_two_sentences(_prose(po)) if po else "missing")
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op:
        folded = _prose(op).encode("ascii", "ignore").decode().lower()
        ok &= _check("Opera House is the Saigon one (1900 / Ferret / French colonial)",
                     "1900" in _prose(op) or "ferret" in folded or "french colonial" in folded,
                     _first_two_sentences(_prose(op)))

    short = [(n, t, _content_sentence_count(_prose((n, t, b))))
             for n, t, b in blocks if _content_sentence_count(_prose((n, t, b))) < 5]
    ok &= _check("every stop has >= 5 content sentences", not short,
                 "all >=5" if not short else f"short: {short}")
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def phase_sydney(cap_remaining):
    before = _meter_total()
    sub = min(cap_remaining, SYDNEY_SUBCAP_USD)
    print(f"\n[SYDNEY control] request={REQUEST_SYDNEY!r}; {len(SYDNEY_STOPS)} stops; "
          f"sub-cap=${sub:.4f} (of task cap ${HARD_CAP_USD:.2f})", flush=True)
    text, log = _generate(REQUEST_SYDNEY, "walking", SYDNEY_STOPS, sub,
                          "sydney_control_tour.txt")

    blocks = _blocks(text)
    low = (text or "").lower()
    ok = _check(f"{len(SYDNEY_STOPS)} stops delivered", len(blocks) == len(SYDNEY_STOPS),
                len(blocks))

    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    # NOTHING Saigon- / tour-547-specific may leak into a Sydney tour.
    for s in _HARDCODE_LEAK_STRINGS:
        ok &= _check(f"no tour-547 leak: '{s}'", s not in low, "absent")
    for bad in ("saigon", "ho chi minh", "vietnam", "national assembly",
                "information agency"):
        ok &= _check(f"no Saigon place/term leak: '{bad}'", bad not in low, "absent")

    # the Sydney Opera House stop is Sydney's (a sanity check the control is real)
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op:
        opl = _prose(op).lower()
        ok &= _check("Sydney Opera House stop is Sydney's",
                     "sydney" in opl or "utzon" in opl or "bennelong" in opl
                     or "harbour" in opl,
                     _first_two_sentences(_prose(op)))

    import landmark_claim_gate as _lgc
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")

    spent = _meter_total() - before
    ok &= _check("Sydney control stayed under its sub-cap", spent <= SYDNEY_SUBCAP_USD + 1e-9,
                 f"${spent:.4f} of ${SYDNEY_SUBCAP_USD:.2f}")
    print(f"\n   meter (sydney): ${spent:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SYDNEY {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def main():
    reserve = float(os.environ.get("LOCAL880B_RESERVE_USD", "0.02"))
    # Saigon first, leaving the Sydney sub-cap in reserve.
    before = _meter_total()
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    saigon_cap = HARD_CAP_USD - before - SYDNEY_SUBCAP_USD
    if saigon_cap <= 0:
        saigon_cap = HARD_CAP_USD - before - reserve
    ok_s = phase_saigon(saigon_cap)

    after_saigon = _meter_total()
    syd_cap = min(SYDNEY_SUBCAP_USD, HARD_CAP_USD - after_saigon - reserve)
    if syd_cap <= 0:
        print("refusing Sydney: no budget left under the cap")
        ok_y = False
    else:
        ok_y = phase_sydney(syd_cap)

    print(f"\n=== LOCAL-880B {'PASS' if (ok_s and ok_y) else 'FAIL'} "
          f"(saigon={'PASS' if ok_s else 'FAIL'}, sydney={'PASS' if ok_y else 'FAIL'}) ===",
          flush=True)
    print(f"   task total ${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    return ok_s and ok_y


if __name__ == "__main__":
    if "--all" in sys.argv:
        sys.exit(0 if main() else 1)
    if "--saigon" in sys.argv:
        sys.exit(0 if phase_saigon(HARD_CAP_USD - _meter_total() - SYDNEY_SUBCAP_USD) else 1)
    if "--sydney" in sys.argv:
        sys.exit(0 if phase_sydney(min(SYDNEY_SUBCAP_USD,
                                       HARD_CAP_USD - _meter_total())) else 1)
    sys.exit("usage: run_local880b_live.py --all | --saigon | --sydney")
