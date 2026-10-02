#!/usr/bin/env python3
"""LOCAL-560 Step 2 — mark discrepancy cases.

A DISCREPANCY CASE is a recorded CHECKER call whose verdict FOUND a problem
(the old model flagged / rejected / dropped / adjudicated-out something). These
are exactly the calls Michael's rule targets: "get stops where discrepancy was
found with the old method and see if it is found with the new."

We decide FOUND vs CLEAN purely from each checker's recorded response_text,
using the verdict grammar each gate actually emits (confirmed from the
recordings and the .log outcome markers: [LOCAL-472] UNGROUNDED, [LOCAL-229]
BLOCKED, DROPPED, is_story:false, GLOSS_NEEDED, inside_scope:false, DELETE:N).

Output: tests/fixtures/local560/discrepancies.json
  { "sites": { "<file:line>": {role, model, calls, found, clean, found_examples[]} },
    "summary": {total_checker_calls, total_found} }

Only CHECKER sites are considered. WRITER sites (prose) are excluded by design.
"""
import json, glob, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, "recordings")
OUT = os.path.join(HERE, "discrepancies.json")

# CHECKER call sites and how each one's response signals "found a problem".
# key -> (detector(resp_text) -> bool found, human description of the verdict)
def _json_field_false(field):
    pat = re.compile(r'"%s"\s*:\s*false' % re.escape(field), re.I)
    return lambda t: bool(pat.search(t or ""))

def _json_field_true(field):
    pat = re.compile(r'"%s"\s*:\s*true' % re.escape(field), re.I)
    return lambda t: bool(pat.search(t or ""))

def _specificity_found(t):
    # UNGROUNDED/GENERIC verdict = flagged; SPECIFIC = clean
    t = (t or "").upper()
    return "UNGROUNDED" in t or "GENERIC" in t

def _gloss_triage_found(t):
    # any GLOSS_NEEDED among the triaged references = found a reference to gloss
    return "GLOSS_NEEDED" in (t or "")

def _unsupported_found(t):
    # "DELETE: N" with N>=1, or any UNGROUNDED/UNSUPPORTED token
    m = re.search(r'DELETE\s*:\s*(\d+)', t or "", re.I)
    if m and int(m.group(1)) >= 1:
        return True
    tt = (t or "").upper()
    return "UNGROUNDED" in tt or "UNSUPPORTED" in tt

def _story_element_conflict(t):
    return '"conflicting": true' in (t or "").lower() or '"same_subject": false' in (t or "").lower()

CHECKERS = {
    "stop_specificity_gate.py:433": (_specificity_found,
        "VERDICT: UNGROUNDED/GENERIC (paragraph not specific to this stop)"),
    "story_gate.py:201": (_json_field_false("is_story"),
        '"is_story": false (candidate rejected as not a real story)'),
    "unglossed_reference_gate.py:690": (_gloss_triage_found,
        "GLOSS_NEEDED (reference needs explanation)"),
    "unsupported_claim_gate.py:452": (_unsupported_found,
        "DELETE:N / UNGROUNDED (claim not supported by corpus)"),
    "generate_tour_text.py:1083": (_json_field_false("matches"),
        '"matches": false (candidate is not actually of the requested type)'),
    "generate_tour_text.py:1577": (_json_field_false("inside_scope"),
        '"inside_scope": false (stop is outside the bounded tour area)'),
    "story_element_extractor.py:419": (_story_element_conflict,
        "conflicting/not-same-subject (claims disagree)"),
    # Extraction / listing checkers: these do not emit a reject/accept verdict,
    # so a single call cannot be labelled FOUND vs CLEAN from the response alone.
    # They are inventoried as checkers but excluded from the recall denominator
    # (no discrepancy verdict to miss). Marked role=extraction below.
    "fact_extractor.py:76": (None, "extraction (JSON facts) — no reject verdict"),
    "generate_tour_text.py:1008": (None, "intent extraction (JSON) — no reject verdict"),
    "generate_tour_text.py:9580": (None, "stop ordering (JSON) — no reject verdict"),
    "generate_tour_text.py:18583": (None, "fact ranking (JSON) — no reject verdict"),
    "generate_tour_text.py:9983": (None, "coordinate extraction — no reject verdict"),
    "generate_tour_text.py:7770": (None, "restaurant listing (JSON) — no reject verdict"),
    "generate_tour_text.py:8781": (None, "restaurant listing (JSON) — no reject verdict"),
    "generate_tour_text.py:10105": (None, "stop listing (JSON) — no reject verdict"),
    "theme_thread_discoverer.py:260": (None, "theme discovery (JSON) — no reject verdict"),
}


def _tour_of(path):
    return os.path.basename(path).replace(".jsonl", "")


def _user_subject(messages):
    """Pull a short identifying snippet (stop/claim) from the user message."""
    if not messages:
        return ""
    usr = next((m.get("content") for m in messages if m.get("role") == "user"), "") or ""
    # First meaningful line
    for ln in usr.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("{"):
            return ln[:180]
    return usr[:180]


def main():
    sites = {}
    for site, (det, desc) in CHECKERS.items():
        sites[site] = {
            "role": "CHECKER",
            "verdict_grammar": desc,
            "has_reject_verdict": det is not None,
            "calls": 0, "found": 0, "clean": 0,
            "found_examples": [],
        }

    for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
        tour = _tour_of(f)
        idx = 0
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            idx += 1
            site = r.get("site")
            if site not in CHECKERS:
                continue
            det, _ = CHECKERS[site]
            s = sites[site]
            s["calls"] += 1
            if det is None:
                continue
            found = det(r.get("response_text"))
            if found:
                s["found"] += 1
                if len(s["found_examples"]) < 50:
                    s["found_examples"].append({
                        "tour": tour,
                        "record_index": idx,       # 1-based line number in the tour's jsonl
                        "subject": _user_subject(r.get("messages")),
                        "verdict": (r.get("response_text") or "")[:200],
                    })
            else:
                s["clean"] += 1

    total_calls = sum(s["calls"] for s in sites.values())
    total_found = sum(s["found"] for s in sites.values())
    out = {
        "generated_by": "tests/fixtures/local560/mark_discrepancies.py",
        "note": "A discrepancy case = a CHECKER call whose recorded verdict FOUND a problem. "
                "Extraction/listing checkers (has_reject_verdict=false) emit no reject verdict "
                "and are excluded from the recall denominator.",
        "summary": {
            "checker_sites": len(sites),
            "sites_with_reject_verdict": sum(1 for s in sites.values() if s["has_reject_verdict"]),
            "total_checker_calls": total_calls,
            "total_discrepancy_cases_found": total_found,
        },
        "sites": sites,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"wrote {OUT}")
    print(f"checker sites: {len(sites)}  total checker calls: {total_calls}  "
          f"discrepancy cases found: {total_found}")
    for site, s in sorted(sites.items(), key=lambda kv: -kv[1]["found"]):
        if s["has_reject_verdict"]:
            print(f"  {site:42s} found={s['found']:3d}/{s['calls']:<3d} clean={s['clean']}")
        else:
            print(f"  {site:42s} (extraction, {s['calls']} calls, no reject verdict)")


if __name__ == "__main__":
    main()
