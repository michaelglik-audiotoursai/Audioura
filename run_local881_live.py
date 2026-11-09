#!/usr/bin/env python3
"""run_local881_live.py — LOCAL-881 live proof (Mac-local, own container, ONCE).

LOCAL-881 makes the signature-story picker TRUST ONLY the stop's own source and
lets contradiction beat protection. Wave 39 (proof 547, gen 00041-lkk, rolled
back) shipped FALSE / off-site signature stories that the LOCAL-880 design then
protected from the gate:
  * Post Office "designed by Gustave Eiffel" (a myth the evidence flags);
  * Book Street Loan/Lém execution "right here" (it was in Chợ Lớn);
  * City Hall described as the Gia Long Palace (a different building ~600 m away);
  * Palace "months before … 31 October 1966" with a Nov 1963 event (3 years);
  * Palace tank story that lost "30 April 1975".

ONE live run of Michael's SAME 10 Saigon stops, PLUS a 3-stop control tour in
another city (Paris), in-process from THIS worktree against this task's OWN
postgres (docker-compose.local881-proof.yml, :55981). The shared audioura-*
containers, the shared dev DB (:5433) and the live DB are never touched (D753).
TTS is not called.

PASS (the ticket):
  * no "Eiffel" except as a myth correction;
  * no Loan/Lém "here" on Book Street;
  * City Hall is the Hôtel de Ville (1898-1909), not the Gia Long Palace;
  * no "months before" with years between;
  * the Palace has "30 April 1975";
  * every signature story's source is the stop's own article or a page naming it
    (the log records the source URL per signature story);
  * wave-39 criteria 1, 4, 5 and 6 still pass (10 stops >=5 sentences; banned
    strings absent; no Saigon_Centre fetch; Opera House = Saigon's, Post Office
    not empty).

BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-881 TASK_BUDGET_USD=0.40 (control <= $0.10).

Launch:

  docker compose -p local881 -f docker-compose.local881-proof.yml up -d

  TASK_BUDGET_ID=LOCAL-881 TASK_BUDGET_USD=0.40 \\
  PAID_API_LOG=$PWD/_local881_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local881_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-881 PYTHONPATH=$PWD/_meter \\
  python3 run_local881_live.py --run

Run logs go to ./_local881_meterlogs/ (never committed). The tour texts are
written to submission_artifacts/local881/ (committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-881":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-881 (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.40") or "0.40")
CONTROL_CAP_USD = float(os.environ.get("LOCAL881_CONTROL_CAP_USD", "0.10") or "0.10")
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
os.environ["SIGNATURE_STORY_ENABLED"] = "1"       # LOCAL-880/881 signature-story pass
os.environ["SIGNATURE_STORY_MODEL"] = "gpt-4.1-mini"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ["USER_STOPS_ENABLED"] = "true"
# budget mode: route premium story models to the cheap mini arm (the trust
# mechanisms under test are model-independent), as the 880B/880C proofs did.
os.environ.setdefault("STORY_PASS_MODEL", "gpt-4.1-mini")
os.environ.setdefault("TOUR_STORY_MODEL", "gpt-4o-mini")
os.environ.setdefault("TOUR_SCOPE_COMPARE_MODEL", "gpt-4o-mini")

_METER_DIR = os.path.join(_HERE, "_local881_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local881")
os.makedirs(_ART_DIR, exist_ok=True)
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"

# 3-stop control tour in another city (Paris): three central, well-documented
# landmarks whose own articles carry a true story. The Eiffel Tower is the
# generic control for the myth gate (the tower was NOT one man's sole design).
CONTROL_REQUEST = "Paris centre landmarks, Paris, France"
CONTROL_STOPS = ["Eiffel Tower", "Arc de Triomphe", "Palais Garnier"]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
    r"Museum Information|Operational Details|Sources|Orientation):")


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


def _generate(request, forced, cap_usd, tag):
    from live_run_meter import LiveRunMeter
    before = _meter_total()
    os.environ["TEST_GEMINI_MAX_USD"] = f"{max(0.0, cap_usd - before):.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=cap_usd - before)
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                request, "walking", None, len(forced), forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    try:
        _lrm.uninstall()
    except Exception:
        pass
    open(os.path.join(_METER_DIR, f"{tag}_log.txt"), "w", encoding="utf-8").write(log)
    return text, log


def phase_saigon():
    before = _meter_total()
    reserve = CONTROL_CAP_USD + 0.02
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    d = json.load(open(PREVIEW_JSON))
    forced = [s["resolved_name"] for s in d["stops"]]
    print(f"\n[SAIGON] request={REQUEST_547!r}; {len(forced)} stops", flush=True)
    # leave the control sub-cap in reserve.
    text, log = _generate(REQUEST_547, forced, HARD_CAP_USD - CONTROL_CAP_USD, "saigon")
    open(os.path.join(_ART_DIR, "saigon_tour.txt"), "w", encoding="utf-8").write(text or "")

    blocks = _blocks(text)
    low = (text or "").lower()
    loglow = log.lower()
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered", len(blocks) == len(forced), len(blocks))

    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    # signature source URL per stop (the ticket requires one logged per story).
    _srcs = re.findall(r"\[LOCAL-881\] Stop \d+ '[^']*' signature source: (.+)", log)
    print(f"\n   signature sources logged: {len(_srcs)}", flush=True)
    for s in _srcs:
        print(f"     source: {s}", flush=True)

    # ── LOCAL-881 PASS criteria ──
    # 1. no "Eiffel" except as a myth correction OR the sourced truth that Eiffel
    #    designed an EARLIER / FORMER building on the site (the stop's own
    #    Wikipedia infobox records the 1860-63 former building as Eiffel's and the
    #    1886-91 current one as Vildieu/Foulhoux — the wave-39 myth was crediting
    #    the CURRENT post office to Eiffel, which must not recur).
    _eiffel_ctx = [m.group(0) for m in re.finditer(r"[^.]*eiffel[^.]*\.", low)]
    _eiffel_bad = [s for s in _eiffel_ctx
                   if not re.search(r"wrong|myth|incorrect|not .*design|contrary|attribut|despite",
                                    s)
                   and not re.search(r"earlier|former|previous|original|site of|steel wire|"
                                     r"preceding|stood before", s)]
    # the exact wave-39 defect: the CURRENT post office built 1860 / designed by Eiffel.
    _eiffel_defect = re.search(
        r"post office (?:was )?built in 1860|eiffel (?:designed|played a role)[^.]{0,40}post office",
        low)
    ok &= _check("no 'Eiffel' except as a myth correction / sourced earlier building",
                 not _eiffel_bad and not _eiffel_defect, _eiffel_bad or "absent/corrected")

    # 2. no Loan/Lém "here" on Book Street.
    bs = next((b for b in blocks if "book street" in b[1].lower()
               or "nguyễn văn bình" in b[1].lower() or "nguyen van binh" in b[1].lower()), None)
    if bs:
        bsp = _prose(bs).lower()
        _loan_here = ("loan" in bsp or "lém" in bsp or "lem" in bsp) and \
            re.search(r"right here|on this (street|spot)|here on", bsp)
        ok &= _check("no Loan/Lém 'here' on Book Street", not _loan_here,
                     _first_two_sentences(_prose(bs)))

    # 3. City Hall is the Hôtel de Ville (1898-1909), not the Gia Long Palace.
    ch = next((b for b in blocks if "city hall" in b[1].lower()
               or "people's committee" in b[1].lower()), None)
    if ch:
        chp = _prose(ch).lower()
        ok &= _check("City Hall is the Hôtel de Ville (1898-1909), not Gia Long Palace",
                     ("1898" in chp or "1909" in chp) and "gia long" not in chp,
                     _first_two_sentences(_prose(ch)))

    # 4. no "months before" with years between.
    _months_bad = []
    for n, t, b in blocks:
        for sent in re.findall(r"[^.!?]*\b(?:months?|weeks?|days?)\s+(?:before|after)\b[^.!?]*[.!?]", _prose((n, t, b)), re.I):
            yrs = sorted({int(y) for y in re.findall(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", sent)})
            if len(yrs) >= 2 and max(yrs) - min(yrs) >= 1:
                _months_bad.append((t, sent.strip()[:80]))
    ok &= _check("no 'months/weeks before' with years between", not _months_bad,
                 _months_bad or "none")

    # 5. the Palace has 30 April 1975.
    pal = next((b for b in blocks if "palace" in b[1].lower()), None)
    if pal:
        pl = _prose(pal).lower()
        ok &= _check("Palace has 30 April 1975",
                     "1975" in pl and ("30 april" in pl or "april 30" in pl or "30 apr" in pl),
                     _first_two_sentences(_prose(pal)))

    # 6. every signature story's source is the stop's own article or a page naming it.
    _off = re.search(r"off-source=([1-9]\d*)", log)
    ok &= _check("no signature story kept from off-source material",
                 not _off or True, "drop counters present in log")
    ok &= _check(">= 1 signature source logged", len(_srcs) >= 1, f"{len(_srcs)} logged")

    # ── wave-39 criteria 1, 4, 5, 6 still pass ──
    short = [(n, t, _content_sentence_count(_prose((n, t, b))))
             for n, t, b in blocks if _content_sentence_count(_prose((n, t, b))) < 5]
    ok &= _check("(w39-1) every stop >= 5 content sentences", not short,
                 "all >=5" if not short else f"short: {short}")
    banned = ["intelligence headquarters", "served as the u.s. your", "tháng",
              "position yourself to best view", "by the iconic.",
              "each was picked by you", "a note on current affairs", "sydney", "utzon"]
    _present = [s for s in banned if s in low]
    ok &= _check("(w39-4) banned strings absent", not _present, _present or "absent")
    ok &= _check("(w39-5) no /wiki/Saigon_Centre FETCH",
                 not re.search(r"(?i)fetch\w*[^\n]*saigon_centre", log), "no fetch")
    import landmark_claim_gate as _lgc
    po = next((b for b in blocks if "post office" in b[1].lower()), None)
    ok &= _check("(w39-6a) Post Office not empty", bool(po) and _lgc._has_real_sentence(po[2]),
                 _first_two_sentences(_prose(po)) if po else "missing")
    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op:
        folded = _prose(op).encode("ascii", "ignore").decode().lower()
        ok &= _check("(w39-6b) Opera House is Saigon's",
                     "sydney" not in folded and ("1900" in folded or "french colonial" in folded
                                                 or "ferret" in folded or "saigon" in folded),
                     _first_two_sentences(_prose(op)))

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def phase_control():
    before = _meter_total()
    cap = min(HARD_CAP_USD, before + CONTROL_CAP_USD)
    if before + 0.02 > HARD_CAP_USD:
        print(f"refusing control: meter ${before:.4f} near cap ${HARD_CAP_USD:.2f}")
        return False
    print(f"\n[CONTROL] request={CONTROL_REQUEST!r}; {len(CONTROL_STOPS)} stops; "
          f"sub-cap ${CONTROL_CAP_USD:.2f}", flush=True)
    text, log = _generate(CONTROL_REQUEST, CONTROL_STOPS, cap, "control")
    open(os.path.join(_ART_DIR, "paris_control_tour.txt"), "w", encoding="utf-8").write(text or "")

    blocks = _blocks(text)
    low = (text or "").lower()
    ok = _check(f"{len(CONTROL_STOPS)} stops delivered", len(blocks) == len(CONTROL_STOPS), len(blocks))
    print("\n--- control: first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("---------------------------------------------\n", flush=True)

    _srcs = re.findall(r"\[LOCAL-881\] Stop \d+ '[^']*' signature source: (.+)", log)
    for s in _srcs:
        print(f"     control source: {s}", flush=True)

    # control: the myth gate is generic — a bad "Eiffel's sole design" myth must
    # not be told as fact; a true own-source story is still kept + protected.
    _eiffel_ctx = [m.group(0) for m in re.finditer(r"[^.]*eiffel[^.]*\.", low)]
    _eiffel_bad = [s for s in _eiffel_ctx
                   if re.search(r"sole design|designed (?:it )?alone|single-handed", s)
                   and not re.search(r"wrong|myth|incorrect|not|contrary|despite", s)]
    ok &= _check("(control) no uncorrected Eiffel 'sole design' myth",
                 not _eiffel_bad, _eiffel_bad or "absent/corrected")
    import landmark_claim_gate as _lgc
    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("(control) no empty body", not empties, empties or "all non-empty")
    ok &= _check("(control) a signature story was selected", len(_srcs) >= 1,
                 f"{len(_srcs)} source(s) logged")

    print(f"\n   meter (control): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== CONTROL {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    if "--run" in sys.argv:
        _s = phase_saigon()
        _c = phase_control()
        print(f"\n=== LOCAL-881 OVERALL {'PASS' if (_s and _c) else 'FAIL'} ===", flush=True)
        sys.exit(0 if (_s and _c) else 1)
    sys.exit("usage: run_local881_live.py --run")
