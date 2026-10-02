#!/usr/bin/env python3
"""LOCAL-560 Step 4 — compare old (recorded) vs new (gpt-4o-mini replay) per site.

For each verdict-emitting CHECKER site:
  * recall on discrepancy cases = of the calls where the OLD model FOUND a
    problem, how many the NEW model also finds. Every MISS is listed with tour,
    subject, old verdict, new verdict.
  * false alarms = calls where OLD found nothing but NEW flags a problem,
    as a fraction of the old-clean calls.
  * old vs new cost (from recorded usage / replay usage, cost_rates.py rates).

Writes:
  tests/fixtures/local560/comparison.json   (machine-readable, incl. every miss)
  prints a markdown table for the submission.
"""
import json, glob, os, re, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)
REC = os.path.join(HERE, "recordings")
REPLAY = os.path.join(HERE, "replay_mini.jsonl")
OUT = os.path.join(HERE, "comparison.json")

RATES = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60), "gpt-3.5-turbo": (0.50, 1.50)}
def _cost(model, pin, pout):
    for k, (i, o) in RATES.items():
        if k in (model or ""):
            return pin * i / 1e6 + pout * o / 1e6
    return 0.0

# --- the same verdict detectors as mark_discrepancies.py ---
def _jf_false(field):
    pat = re.compile(r'"%s"\s*:\s*false' % re.escape(field), re.I)
    return lambda t: bool(pat.search(t or ""))
def _spec_found(t):
    # VERDICT token only (NAMES: UNGROUNDED; SWAP: TRANSFERABLE = found a problem)
    m = re.search(r"VERDICT:\s*([A-Z_]+)", t or "", re.I)
    tok = (m.group(1).upper() if m else "")
    return tok in ("UNGROUNDED", "TRANSFERABLE", "GENERIC")
def _gloss_found(t):
    return "GLOSS_NEEDED" in (t or "")
def _unsup_found(t):
    m = re.search(r'DELETE\s*:\s*(\d+)', t or "", re.I)
    if m and int(m.group(1)) >= 1: return True
    tt = (t or "").upper(); return "UNGROUNDED" in tt or "UNSUPPORTED" in tt
def _se_conflict(t):
    tl = (t or "").lower(); return '"conflicting": true' in tl or '"same_subject": false' in tl

DETECTORS = {
    "stop_specificity_gate.py:433": _spec_found,
    "story_gate.py:201": _jf_false("is_story"),
    "unglossed_reference_gate.py:690": _gloss_found,
    "unsupported_claim_gate.py:452": _unsup_found,
    "generate_tour_text.py:1083": _jf_false("matches"),
    "generate_tour_text.py:1577": _jf_false("inside_scope"),
    "story_element_extractor.py:419": _se_conflict,
}


def _user_subject(messages):
    if not messages: return ""
    usr = next((m.get("content") for m in messages if m.get("role") == "user"), "") or ""
    for ln in usr.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("{"):
            return ln[:200]
    return usr[:200]


def main():
    # index recordings: (tour, idx) -> record
    old = {}
    for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
        tour = os.path.basename(f).replace(".jsonl", "")
        idx = 0
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line: continue
            r = json.loads(line); idx += 1
            old[(tour, idx)] = r

    # index replay: (tour, idx) -> record
    new = {}
    for line in open(REPLAY, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        new[(r["tour"], r["record_index"])] = r

    sites = {}
    for site, det in DETECTORS.items():
        sites[site] = {
            "old_found": 0, "old_clean": 0,
            "recall_hit": 0, "recall_miss": 0,
            "false_alarm": 0,
            "old_cost": 0.0, "new_cost": 0.0,
            "misses": [], "false_alarms_examples": [],
        }

    for key, orec in old.items():
        site = orec.get("site")
        if site not in DETECTORS:
            continue
        det = DETECTORS[site]
        s = sites[site]
        nrec = new.get(key)
        # old cost
        ou = orec.get("usage") or {}
        s["old_cost"] += _cost(orec.get("model"), ou.get("prompt_tokens") or 0, ou.get("completion_tokens") or 0)
        # new cost
        if nrec:
            nu = nrec.get("usage") or {}
            s["new_cost"] += _cost("gpt-4o-mini", nu.get("prompt_tokens") or 0, nu.get("completion_tokens") or 0)

        old_found = det(orec.get("response_text"))
        new_found = det(nrec.get("response_text")) if nrec else False

        if old_found:
            s["old_found"] += 1
            if new_found:
                s["recall_hit"] += 1
            else:
                s["recall_miss"] += 1
                s["misses"].append({
                    "tour": orec_tour(key), "record_index": key[1],
                    "subject": _user_subject(orec.get("messages")),
                    "old_verdict": (orec.get("response_text") or "")[:240],
                    "new_verdict": (nrec.get("response_text") or "")[:240] if nrec else "(no replay)",
                })
        else:
            s["old_clean"] += 1
            if new_found:
                s["false_alarm"] += 1
                if len(s["false_alarms_examples"]) < 20:
                    s["false_alarms_examples"].append({
                        "tour": orec_tour(key), "record_index": key[1],
                        "subject": _user_subject(orec.get("messages")),
                        "old_verdict": (orec.get("response_text") or "")[:200],
                        "new_verdict": (nrec.get("response_text") or "")[:200] if nrec else "",
                    })

    # finalize metrics
    for site, s in sites.items():
        s["recall"] = (s["recall_hit"] / s["old_found"]) if s["old_found"] else None
        s["false_alarm_rate"] = (s["false_alarm"] / s["old_clean"]) if s["old_clean"] else None
        s["passes"] = (
            (s["old_found"] == 0 or s["recall"] == 1.0) and
            (s["old_clean"] == 0 or (s["false_alarm_rate"] is not None and s["false_alarm_rate"] <= 0.10))
        )

    out = {"sites": sites}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    # markdown table
    print("| Call site | Old found | Recall (hit/found) | Misses | False alarms (n/clean) | Old $ | New $ | PASS |")
    print("|---|---:|---|---:|---|---:|---:|:--:|")
    for site, s in sorted(sites.items(), key=lambda kv: -kv[1]["old_found"]):
        rec = "n/a" if s["recall"] is None else f"{s['recall']*100:.0f}% ({s['recall_hit']}/{s['old_found']})"
        far = "n/a" if s["false_alarm_rate"] is None else f"{s['false_alarm_rate']*100:.0f}% ({s['false_alarm']}/{s['old_clean']})"
        print(f"| `{site}` | {s['old_found']} | {rec} | {s['recall_miss']} | {far} | ${s['old_cost']:.4f} | ${s['new_cost']:.4f} | {'✅' if s['passes'] else '❌'} |")

    print("\n### Misses (every recorded discrepancy the new model did NOT reproduce)\n")
    any_miss = False
    for site, s in sites.items():
        for m in s["misses"]:
            any_miss = True
            print(f"- **{site}** — tour `{m['tour']}` #{m['record_index']}")
            print(f"  - subject: {m['subject']}")
            print(f"  - OLD: {m['old_verdict']!r}")
            print(f"  - NEW: {m['new_verdict']!r}")
    if not any_miss:
        print("_No misses: every recorded discrepancy case was reproduced by gpt-4o-mini._")

    print("\n### False alarms (new flags where old was clean)\n")
    any_fa = False
    for site, s in sites.items():
        for fa in s["false_alarms_examples"]:
            any_fa = True
            print(f"- **{site}** — tour `{fa['tour']}` #{fa['record_index']}: {fa['subject']}")
            print(f"  - OLD: {fa['old_verdict']!r}")
            print(f"  - NEW: {fa['new_verdict']!r}")
    if not any_fa:
        print("_No false alarms._")


def orec_tour(key):
    return key[0]


if __name__ == "__main__":
    main()
