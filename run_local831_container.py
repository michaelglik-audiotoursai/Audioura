"""
run_local831_container.py — LOCAL-831 live, budget-enforced proof.

LOCAL-831: the repeated-fact remover (D533) deleted a WHOLE stop and the delivery
check shipped the gap (Rijks Museum shipped four stops numbered [1, 2, 4, 5]).
The fix hardens strip_repeated_facts (never removes a "Stop N:" header or empties
a body) and makes a gap-closing renumber + delivery check the LAST text transform
before write/store on every path.

ONE TOUR, cheap museum arm, DISABLE_STOP_POOL=1:
    * "Rijks Museum, Amsterdam, Netherlands"   (5 stops)

PASS = well-formed, SEQUENTIAL stops (check_stop_delivery returns []) each with
>= 2 complete sentences, AND the delivered count is HONEST: either the requested
5, or fewer with the honest shortfall sentence present in the text. A numbering
gap [1, 2, 4, 5] is a FAIL.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-831 TASK_BUDGET_USD=0.50. LiveRunMeter
records the run to the task ledger; a reserve gate refuses to START once the
ledger spend is at/over the cap.

METER CONTRACT (LOCAL-819/820): the container bind-mounts the shared meterlog
dir, writes the canonical PAID_API_LOG, installs the meter via
PYTHONPATH=/opt/meter and tags rows METER_SERVICE=LOCAL-831.

DB: the isolated throwaway postgres only, seeded by the wrapper; never the
shared/live DB.
"""
import io
import json
import os
import re
import sys
import time
import contextlib

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("DISABLE_STOP_POOL", "1")
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

TOURS = [
    ("Rijks Museum, Amsterdam, Netherlands", "museum", 5),
]

_D1V2_RE = re.compile(r"\[D1v2\]\s+(VERIFIED|DROPPED)\b.*")
_F3_RE = re.compile(r"\[F3\].*")
_DELIVERY_RE = re.compile(r"\[LOCAL-82[16][BC]?\].*|\[LOCAL-831\].*")
_D533_RE = re.compile(r"\[D533\].*|removed: Stop\s+\d+:.*")
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
# A sentence-ending mark (same shape as tour_conclusion._DELIVERY_SENTENCE_END).
_SENTENCE_END = re.compile(r"[.!?][\'\"\u2019\u201d)]*(?:\s|$)")


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return rows


def _by_model(rows):
    out = {}
    for r in rows:
        if r.get("status") not in (200, "200"):
            continue
        key = (r.get("kind") or "?", r.get("model") or "?")
        slot = out.setdefault(key, {"calls": 0, "usd": 0.0})
        slot["calls"] += 1
        try:
            slot["usd"] += float(r.get("usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return out


def _stop_bodies(text):
    """Return [(num, title, body)] for each delivered stop (body up to Sources)."""
    import re as _re
    end = len(text)
    m = _re.search(r"(?ms)^\s*Sources:\s.*\Z", text)
    if m:
        end = m.start()
    heads = list(_STOP_HEADER_RE.finditer(text[:end]))
    out = []
    for i, h in enumerate(heads):
        start = h.end()
        stop_end = heads[i + 1].start() if i + 1 < len(heads) else end
        body = text[start:stop_end]
        # Drop house field lines for the sentence count.
        narration = []
        for ln in body.splitlines():
            s = ln.strip()
            if not s:
                continue
            fm = _re.match(r"(?i)^(?:Orientation|Type/Specialty|Specific Examples|"
                           r"Operational Details|Museum Information):\s*(.*)$", s)
            if fm:
                if fm.group(1).strip():
                    narration.append(fm.group(1).strip())
                continue
            if _re.match(r"(?i)^(?:Address|Coordinates|Directions):", s):
                continue
            narration.append(s)
        out.append((int(h.group(1)), h.group(2).strip(), " ".join(narration)))
    return out


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-831 live run — D533 whole-stop deletion + gap renumber "
          "(cheap arm, DISABLE_STOP_POOL=1) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}   meter log: {METER_LOG}", flush=True)

    try:
        from venue_resolver import CORPUS_VERSION, cache_get, venue_works_cache_get
        print(f"  CORPUS_VERSION={CORPUS_VERSION}", flush=True)
        for qid, lang in (("Q190804", "nl"), ("Q190804", "en")):
            wc = venue_works_cache_get(qid, lang)
            print(f"  seeded venue_works_cache {qid}/{lang}: "
                  f"{len(wc) if wc else 0} works", flush=True)
        ch = cache_get("Q190804")
        print(f"  venue_corpus cache_get(Q190804) at v{CORPUS_VERSION}: "
              f"{'HIT' if ch else 'MISS (stale -> rebuild)'}", flush=True)
    except Exception as e:
        print(f"  [LOCAL-831] seed check failed ({e})", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-831] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    from tour_conclusion import check_stop_delivery, count_delivered_stops
    import traceback as _tb

    results = []
    n_before_all = len(_meter_rows())

    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-831")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-831] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
        delivery_lines, d533_lines, titles = [], [], []
        text = None
        buf = io.StringIO()

        class _Tee:
            def __init__(self, *streams):
                self._s = streams

            def write(self, data):
                for s in self._s:
                    s.write(data)
                return len(data)

            def flush(self):
                for s in self._s:
                    try:
                        s.flush()
                    except Exception:
                        pass

        _tee = _Tee(sys.stdout, buf)
        try:
            with contextlib.redirect_stdout(_tee):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            captured = buf.getvalue()
            delivery_lines = [m.group(0).strip()
                              for m in _DELIVERY_RE.finditer(captured)]
            d533_lines = [m.group(0).strip() for m in _D533_RE.finditer(captured)]
            if text:
                titles = [(int(a), b.strip())
                          for a, b in _STOP_HEADER_RE.findall(text)]
                print(f"  generated in {dt:.0f}s — {len(titles)} stops", flush=True)
            else:
                print(f"  [LOCAL-831] NO text in {dt:.0f}s", flush=True)
        except Exception as e:
            print(f"  [LOCAL-831] raised: {e}", flush=True)
            _tb.print_exc()
        finally:
            try:
                meter.add_generation(g)
            except Exception:
                pass
            try:
                meter.record()
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

        viol = check_stop_delivery(text or "")
        bodies = _stop_bodies(text or "")
        nums = [n for n, _, _ in bodies]
        sentence_counts = {
            n: len(_SENTENCE_END.findall(body)) for n, _t, body in bodies}
        # Honest count: either requested 5, or fewer WITH a shortfall sentence.
        delivered = count_delivered_stops(text or "")
        shortfall_present = bool(text and re.search(
            r"(?i)rather than the \d+ you asked for|we could confirm \d+ "
            r"stops?", text))
        results.append({
            "location": location,
            "requested": n_stops,
            "delivered": delivered,
            "nums": nums,
            "titles": titles,
            "sentence_counts": sentence_counts,
            "delivery_log": delivery_lines,
            "d533_log": d533_lines,
            "delivery_violations": viol,
            "shortfall_present": shortfall_present,
            "text": text or "",
        })

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-831 SUMMARY ===", flush=True)
    all_pass = True
    for r in results:
        sequential = (r["nums"] == list(range(1, len(r["nums"]) + 1))
                      and len(r["nums"]) > 0)
        two_sentences = all(c >= 2 for c in r["sentence_counts"].values()) \
            and bool(r["sentence_counts"])
        honest_count = (r["delivered"] == r["requested"]
                        or (r["delivered"] < r["requested"]
                            and r["shortfall_present"]))
        well_formed = (not r["delivery_violations"]) and sequential \
            and two_sentences and honest_count
        all_pass = all_pass and well_formed

        print(f"\n  {r['location']}: requested {r['requested']}, "
              f"delivered {r['delivered']}", flush=True)
        print("    --- [D533] de-repetition / role-guard log ---", flush=True)
        for ln in r["d533_log"] or ["(none fired)"]:
            print(f"      {ln[:140]}", flush=True)
        print("    --- delivered Stop headers (as numbered) ---", flush=True)
        for n, t in r["titles"]:
            print(f"      Stop {n}: {t[:80]}  "
                  f"[{r['sentence_counts'].get(n, 0)} sentence(s)]", flush=True)
        print("    --- [LOCAL-826B/C / LOCAL-831] delivery log ---", flush=True)
        for ln in r["delivery_log"] or ["(none)"]:
            print(f"      {ln}", flush=True)
        print(f"    sequential={sequential}  >=2 sentences each={two_sentences}  "
              f"honest_count={honest_count}  "
              f"shortfall_present={r['shortfall_present']}", flush=True)
        verdict = ("PASS — well-formed, sequential, >=2 sentences, honest count"
                   if well_formed else
                   f"FAIL — nums={r['nums']} viol={r['delivery_violations']} "
                   f"sentences={r['sentence_counts']}")
        print(f"    --- VERDICT: {verdict}", flush=True)

    rows_all = _meter_rows()
    new_all = rows_all[n_before_all:] if len(rows_all) >= n_before_all else rows_all
    bm_all = _by_model(new_all)
    print("\n  --- per-model meter (whole task, status-200) ---", flush=True)
    total = 0.0
    for (kind, model), slot in sorted(bm_all.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)
        total += slot["usd"]
    print(f"  metered total (status-200 rows this task): ${total:.4f} "
          f"/ cap ${HARD_CAP_USD:.2f}", flush=True)
    print(f"\n=== LOCAL-831 OVERALL: {'PASS' if all_pass else 'FAIL'} ===", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
