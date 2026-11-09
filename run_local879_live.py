#!/usr/bin/env python3
"""run_local879_live.py — LOCAL-879 live proof (Mac-local, own container, ONCE).

ONE live 10-stop run of Michael's Saigon-centre list, in-process from THIS
worktree against this task's OWN postgres (docker-compose.local879-proof.yml,
:55979). The shared audioura-* containers, the shared dev DB (:5433) and the
live DB are never touched (D753). TTS is not called.

PASS criteria (the ticket):
  * none of the defect strings §1–§6 appears;
  * no "tháng" / "năm" in the English text;
  * the Palace says Diệm was killed outside the palace, or does not place the
    death at all (never "within the walls");
  * the War Remnants Museum says the Information Agency (never "intelligence HQ");
  * no unsourced "established … 19th century";
  * no /wiki/Saigon_Centre in the log;
  * every stop has >= 4 content sentences;
  * the earlier PASS criteria still hold (Opera House = Saigon; Post Office not
    empty; no Sydney/Utzon/Bennelong; the request string is never a place).

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-879 TASK_BUDGET_USD=0.35 \\
  PAID_API_LOG=$PWD/_local879_meterlogs/paid_api_calls.jsonl \\
  AUDIOURA_TASK_BUDGET_DIR=$PWD/_local879_meterlogs METER_MOUNT_GUARD=0 \\
  METER_SERVICE=LOCAL-879 PYTHONPATH=$PWD/_meter \\
  python3 run_local879_live.py --saigon

Run logs go to ./_local879_meterlogs/ (never committed).
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

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-879":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-879 (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.35") or "0.35")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

_OWN_DB = "postgresql://admin:password123@localhost:55979/audiotours"
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
               ("DB_HOST", "localhost"), ("DB_PORT", "55979"),
               ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
               ("DB_PASSWORD", "password123")):
    os.environ[_k] = _v

os.environ.pop("K_SERVICE", None)
os.environ["LANDMARK_LIVE_LOOKUP"] = "1"          # the real Wikidata/Wikipedia path
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

_METER_DIR = os.path.join(_HERE, "_local879_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
PREVIEW_JSON = os.path.join(_HERE, "submission_artifacts", "local867", "preview_michael_hcmc.json")

# The exact tour-547 request string.
REQUEST_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"

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


def phase_saigon():
    before = _meter_total()
    reserve = float(os.environ.get("LOCAL879_RESERVE_USD", "0.05"))
    if before + reserve > HARD_CAP_USD:
        print(f"refusing: meter ${before:.4f} + reserve ${reserve:.2f} > cap ${HARD_CAP_USD:.2f}")
        return False
    d = json.load(open(PREVIEW_JSON))
    forced = [s["resolved_name"] for s in d["stops"]]
    print(f"\n[SAIGON] request={REQUEST_547!r}; {len(forced)} stops", flush=True)

    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{HARD_CAP_USD - before:.4f}"
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD - before)
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                REQUEST_547, "walking", None, len(forced), forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_METER_DIR, "saigon_tour.txt"), "w", encoding="utf-8").write(text or "")
    open(os.path.join(_METER_DIR, "saigon_log.txt"), "w", encoding="utf-8").write(log)
    try:
        _lrm.uninstall()
    except Exception:
        pass

    blocks = _blocks(text)
    low = (text or "").lower()
    ok = _check(f"{len(forced)}/{len(forced)} stops delivered", len(blocks) == len(forced), len(blocks))

    print("\n--- first two sentences per stop ---", flush=True)
    for n, t, _b in blocks:
        print(f"Stop {n} [{t}]: {_first_two_sentences(_prose((n, t, _b)))}", flush=True)
    print("------------------------------------\n", flush=True)

    # ---- §1 cross-stop business line ----
    ok &= _check("§1 Thi Bar hours not under the Cathedral",
                 "opens every day at 7pm" not in low or _bar_line_only_in_bar(blocks),
                 "no cross-stop bar line")

    # ---- §2 truncated U.S. preview ----
    ok &= _check("§2 no '…served as the U.S. Your first stop' truncation",
                 "served as the u.s. your first stop" not in low
                 and not re.search(r"as the u\.s\.\s*$", low, re.M),
                 "no U.S. stub")

    # ---- §3 Vietnamese dates ----
    ok &= _check("§3 no 'tháng' in the English text", "tháng" not in low, "absent")
    ok &= _check("§3 no 'năm' in the English text", "năm" not in low, "absent")

    # ---- §4 false facts ----
    ok &= _check("§4 Palace: no 'within the walls' death placement",
                 "within the walls" not in low, "absent")
    ok &= _check("§4 War Remnants: Information Agency, not 'intelligence' HQ",
                 ("information agency" in low) and ("intelligence" not in low),
                 "info-agency / no 'intelligence'")
    ok &= _check("§4 Pier: no unsourced 'established … 19th century'",
                 not re.search(r"establish\w+[^.]{0,60}19th century", low),
                 "absent")
    ok &= _check("§4 no 'it is sometimes said' hedge on the sourced bombing",
                 "sometimes said" not in low, "absent")

    # ---- §5 Saigon_Centre fetch ----
    ok &= _check("§5 no /wiki/Saigon_Centre in the log",
                 "saigon_centre" not in log.lower(), "absent in log")
    ok &= _check("§5 request string never a place ('saigon centre landmarks' absent)",
                 "saigon centre landmarks" not in low, "absent")

    # ---- §6 marketing + closing ----
    for bad in ("diamond-valued", "distinctive cultural brand", "the notting hill of",
                "one of the only"):
        ok &= _check(f"§6 promo phrase '{bad}' absent", bad not in low, "absent")
    ok &= _check("§6 no circular 'one thread runs through: the places you chose on this route'",
                 "one thread runs through: the places you chose on this route" not in low,
                 "absent")

    # ---- earlier PASS criteria ----
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

    # ---- every stop >= 4 content sentences ----
    short = [(n, t, _content_sentence_count(_prose((n, t, b))))
             for n, t, b in blocks if _content_sentence_count(_prose((n, t, b))) < 4]
    ok &= _check("every stop has >= 4 content sentences", not short,
                 "all >=4" if not short else f"short: {short}")

    empties = [t for _, t, b in blocks if not _lgc._has_real_sentence(b)]
    ok &= _check("no stop has an empty body", not empties, empties or "all non-empty")

    print(f"\n   meter (saigon): ${_meter_total() - before:.4f}; task total "
          f"${_meter_total():.4f} of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== SAIGON {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def _bar_line_only_in_bar(blocks):
    """§1: the 'the bar opens every day at 7pm' line, if present, appears ONLY in
    a bar-kind stop block (Thi Bar), never under the Cathedral or any other stop."""
    for n, t, b in blocks:
        if "opens every day at 7pm" in b.lower():
            tl = t.lower()
            if "bar" not in tl:
                return False
    return True


if __name__ == "__main__":
    if "--saigon" in sys.argv:
        sys.exit(0 if phase_saigon() else 1)
    sys.exit("usage: run_local879_live.py --saigon")
