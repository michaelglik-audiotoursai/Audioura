"""run_local799_container.py — LOCAL-799 live acceptance (ISOLATED container).

ONE fresh paid tour through the real generation path, proving the tour-467
named-place reconciliation end to end. The exact ClickUp request:

    "Mui Ne sights: Fairy Stream, Red Sand Dunes, White Sand Dunes,
     fishing village (by car)"   (5 stops)

Field defect (tour 467, Subscribed Preview, heard by Michael 2026-10-28): the
tour SHIPPED Red Canyon, Red Sand Dunes, Mui Ne Fishing Village, Mui Ne Market,
Fairy Stream, yet Stop 1's Orientation announced "We could not confirm Fairy
Stream … Red Sand Dunes … White Sand Dunes … fishing village …" — three of the
four are stops; only White Sand Dunes was really missing.

ACCEPTANCE (printed below, asserted after the run):
  * The intro mentions AT MOST White Sand Dunes (or nothing if the map now finds
    it) — never Fairy Stream / Red Sand Dunes / fishing village as "not
    confirmed".
  * At most ONE named-place sentence, and it is NOT inside a stop's Orientation
    line.

Budget: HARD CAP $1.00 for the whole run, enforced by tests/live_run_meter.py
(combined across every provider). No DELETE. The live DB is never written — this
script only generates and inspects the delivered text (DISABLE_TOUR_CACHE /
DISABLE_STOP_POOL on, no INSERT).

Run inside a DISPOSABLE container only (name local799-tg; NEVER an audioura-*
container, never -p audioura):
    docker run --rm --name local799-tg \
        --network local799_default \
        --env-file .env \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.00 -e COST_HARD_LIMIT_USD=1.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local799_container.py
"""
import os as _os
import sys as _sys
import re
import socket
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.00')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.00
HOST = socket.gethostname()

REQUEST = ("Mui Ne sights: Fairy Stream, Red Sand Dunes, White Sand Dunes, "
           "fishing village (by car)")
N_STOPS = 5

# The four places the listener named, and the one that was really missing.
NAMED = ["Fairy Stream", "Red Sand Dunes", "White Sand Dunes", "fishing village"]
SHOULD_NOT_BE_ANNOUNCED = ["Fairy Stream", "Red Sand Dunes", "fishing village"]

print("=== LOCAL-799 isolated live run (tour 467 named-place reconcile) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"request: {REQUEST!r} ({N_STOPS} stops)", flush=True)
print(f"HARD CAP: ${HARD_CAP_USD}  cache_off=1 pool_off=1  STORIED_MODE=true",
      flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-799] live_run_meter unavailable ({_e}) — cannot cap; aborting",
          flush=True)
    _sys.exit(2)


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_ORIENT_LINE_RE = re.compile(r"(?mi)^Orientation:\s*(.+)$")
_CONFIRM_RE = re.compile(
    r"(could not be confirmed|could not confirm|isn't included|aren't included|"
    r"not part of this tour)", re.IGNORECASE)


def _report_stops(text):
    titles = _STOP_HEADER_RE.findall(text)
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        print(f"  STOP {i + 1}: {t.strip()[:80]}", flush=True)
    return titles


def _audit_intro(text):
    """Print the acceptance evidence and return (ok, details).

    The announcement is ONE sentence built by build_named_place_intro_sentence,
    always of the form "... you asked for, <names>, could not be confirmed ...".
    Isolate exactly that sentence (up to its first period) so trailing narrative
    — which legitimately mentions a COVERED place like Fairy Stream — is not
    mistaken for part of the announcement.
    """
    ann = ""
    m = re.search(r"([^.]*?\byou asked for\b[^.]*?could not be confirmed[^.]*?\.)",
                  text, re.IGNORECASE)
    if m:
        ann = m.group(1).strip()
    # Fallback: any legacy per-name "could not confirm … not part of this tour".
    legacy = re.findall(r"(We could not confirm[^.]*?not part of this tour\.)",
                        text, re.IGNORECASE)

    print("  --- NAMED-PLACE ANNOUNCEMENT ---", flush=True)
    if not ann and not legacy:
        print("  (none — every named place is covered by a final stop)", flush=True)
    if ann:
        print(f"  » {ann}", flush=True)
    for l in legacy:
        print(f"  » [legacy per-name] {l}", flush=True)

    scope_text = ann + " " + " ".join(legacy)
    flagged = [n for n in NAMED
               if re.search(r"\b" + re.escape(n) + r"\b", scope_text, re.I)]
    wrongly = [n for n in SHOULD_NOT_BE_ANNOUNCED
               if re.search(r"\b" + re.escape(n) + r"\b", scope_text, re.I)
               and _covered_by_a_stop(n, text)]

    # The announcement must NOT sit inside a stop's Orientation LINE.
    in_orient = False
    for ol in _ORIENT_LINE_RE.findall(text):
        if _CONFIRM_RE.search(ol):
            in_orient = True
            break

    n_sentences = (1 if ann else 0) + len(legacy)
    print(f"  flagged as not-confirmed      : {flagged}", flush=True)
    print(f"  WRONGLY flagged (covered stop): {wrongly}", flush=True)
    print(f"  announcement in Orientation   : {in_orient}", flush=True)
    print(f"  number of announcement lines  : {n_sentences}", flush=True)

    ok = (not wrongly) and (not in_orient) and (n_sentences <= 1)
    return ok, {"flagged": flagged, "wrongly": wrongly,
                "in_orient": in_orient, "n_sentences": n_sentences}


def _covered_by_a_stop(name, text):
    """True when `name` matches a delivered stop title (so flagging it would be
    the bug). Normalized token containment, mirroring the engine's reconciler."""
    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]

    def _norm(s):
        import unicodedata
        s = ''.join(c for c in unicodedata.normalize('NFKD', s)
                    if not unicodedata.combining(c)).lower()
        s = re.sub(r"[^\w\s]", " ", s)
        stop = {"the", "a", "an", "of", "and"}
        return {w for w in s.split() if w not in stop and len(w) > 1}

    nt = _norm(name)
    if not nt:
        return False
    for t in titles:
        st = _norm(t)
        if st and (nt <= st or st <= nt):
            return True
    return False


def main():
    meter = LiveRunMeter('LOCAL-799')
    result_ok = False
    try:
        import generate_tour_text as g
        import traceback as _tb
        t0 = time.time()
        try:
            text, _out, _coords = g.generate_tour_text(REQUEST, '', None, N_STOPS)
            dt = time.time() - t0
            if not text:
                try:
                    _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                except Exception:
                    _ev = {}
                print(f"  [LOCAL-799] generation returned NO text (clean-fail) "
                      f"in {dt:.0f}s; evidence={_ev}", flush=True)
            else:
                titles = _report_stops(text)
                print(f"  delivered {len(titles)} stop(s) in {dt:.0f}s", flush=True)
                result_ok, _details = _audit_intro(text)
                print("\n  --- INTRO (first 900 chars) ---", flush=True)
                print(text[:900], flush=True)
        except Exception as e:
            print(f"  [LOCAL-799] generation raised: {e}", flush=True)
            _tb.print_exc()
        finally:
            try:
                meter.add_generation(g)
            except Exception:
                pass
    finally:
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    print(f"\n=== LOCAL-799 ACCEPTANCE: {'PASS' if result_ok else 'REVIEW'} ===",
          flush=True)


if __name__ == '__main__':
    main()
