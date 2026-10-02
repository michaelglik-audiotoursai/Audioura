"""[LOCAL-560] Offline replay guard — a switched checker must not miss a recorded discrepancy.

Michael's acceptance rule, verbatim:
    "get stops where discrepancy was found with the old method and see if it is
     found with the new."

This test runs entirely OFFLINE from the committed fixtures:
    tests/fixtures/local560/recordings/*.jsonl   (old model, real tours)
    tests/fixtures/local560/replay_mini.jsonl    (gpt-4o-mini replay of every checker call)

For every call site that LOCAL-560 SWITCHED onto the central checker model
(CHECK_LLM_MODEL / gpt-4o-mini), it re-derives the OLD verdict and the NEW
verdict from the recordings and asserts recall == 100% on the recorded
discrepancy cases — i.e. every problem the old model found, the new model also
finds. A regression (a switched site that now misses a recorded discrepancy)
fails this test.

Sites that were NOT switched (verdict scope gates that failed recall, held on
their current model) are intentionally excluded: the whole point is that we did
not move them, so they carry no obligation here.

Documented exceptions (misses proven to be OLD-model false positives, source
text quoted in SUBMISSION_LOCAL-560.md §4) are listed in _ALLOWED_MISSES and do
not count against recall. Any NEW miss not in that list fails the test.

Run:  python3 -m pytest tests/test_local560_checker_replay.py -q
"""
import glob
import json
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "local560")
REC = os.path.join(FIX, "recordings")
REPLAY = os.path.join(FIX, "replay_mini.jsonl")


# ── verdict detectors (identical grammar to mark_discrepancies.py / compare.py) ──
def _spec_found(t):
    m = re.search(r"VERDICT:\s*([A-Z_]+)", t or "", re.I)
    tok = (m.group(1).upper() if m else "")
    return tok in ("UNGROUNDED", "TRANSFERABLE", "GENERIC")


def _jf_false(field):
    pat = re.compile(r'"%s"\s*:\s*false' % re.escape(field), re.I)
    return lambda t: bool(pat.search(t or ""))


def _gloss_found(t):
    return "GLOSS_NEEDED" in (t or "")


def _unsup_found(t):
    m = re.search(r"DELETE\s*:\s*(\d+)", t or "", re.I)
    if m and int(m.group(1)) >= 1:
        return True
    tt = (t or "").upper()
    return "UNGROUNDED" in tt or "UNSUPPORTED" in tt


def _se_conflict(t):
    tl = (t or "").lower()
    return '"conflicting": true' in tl or '"same_subject": false' in tl


# Only the sites LOCAL-560 actually SWITCHED/validated carry a recall obligation.
# These resolve through CHECK_LLM_MODEL (gpt-4o-mini) AND passed step-4 at 100%
# recall on recorded discrepancies with <=10% false alarms AND have at least one
# recorded discrepancy case to score.
#
# Explicitly NOT guarded (and NOT switched off their current model), with reasons:
#   stop_specificity_gate.py:433 — already gpt-4o-mini, but one GENUINE recall
#       miss remained on the recorded set (our_lady_help_newton #87, St.
#       Alphonsus); not re-pointed, so it carries no switch obligation.
#   story_gate.py:201 — already gpt-4o-mini, 15% false-alarm rate (> 10% cap);
#       not re-pointed.
#   story_element_extractor.py:419 — PASS, but ZERO recorded discrepancy cases,
#       so a recall assertion would be vacuous.
#   generate_tour_text.py:1083 / :1568 (geo) / :2914 (venue) — verdict scope
#       gates that FAILED recall; held on gpt-3.5-turbo via held_model().
SWITCHED_VERDICT_SITES = {
    "unglossed_reference_gate.py:690": _gloss_found,
    "unsupported_claim_gate.py:452": _unsup_found,
}

# Misses proven to be OLD-model false positives (SUBMISSION §4). key = (site, tour, record_index).
# Currently empty: the only such case (the Doherty window at
# stop_specificity_gate.py:433 #58) belongs to a site that was NOT switched, so
# it is not scored here. Kept as the extension point if a switched site ever
# produces a provable old-false-positive miss.
_ALLOWED_MISSES = set()


def _load_recordings():
    old = {}
    for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
        tour = os.path.basename(f).replace(".jsonl", "")
        idx = 0
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            idx += 1
            old[(tour, idx)] = r
    return old


def _load_replay():
    new = {}
    for line in open(REPLAY, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        new[(r["tour"], r["record_index"])] = r
    return new


def _subject(messages):
    if not messages:
        return ""
    usr = next((m.get("content") for m in messages if m.get("role") == "user"), "") or ""
    for ln in usr.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("{"):
            return ln[:160]
    return usr[:160]


def test_fixtures_present():
    assert os.path.isdir(REC), f"missing recordings dir {REC}"
    assert os.path.isfile(REPLAY), f"missing replay file {REPLAY}"


def test_replay_covers_every_checker_call():
    """Sanity: the replay has a row for every recorded checker call we score."""
    old = _load_recordings()
    new = _load_replay()
    missing = []
    for key, rec in old.items():
        if rec.get("site") in SWITCHED_VERDICT_SITES and key not in new:
            missing.append(key)
    assert not missing, f"replay missing {len(missing)} checker calls: {missing[:5]}"


@pytest.mark.parametrize("site", sorted(SWITCHED_VERDICT_SITES))
def test_switched_site_recall_is_100pct(site):
    """Every recorded discrepancy at a switched site must be reproduced by gpt-4o-mini."""
    det = SWITCHED_VERDICT_SITES[site]
    old = _load_recordings()
    new = _load_replay()

    found = 0
    misses = []
    for key, orec in old.items():
        if orec.get("site") != site:
            continue
        if not det(orec.get("response_text")):
            continue  # old model did not flag -> not a discrepancy case
        found += 1
        nrec = new.get(key)
        if nrec is None or not det(nrec.get("response_text")):
            if (site, key[0], key[1]) in _ALLOWED_MISSES:
                continue  # documented old-model false positive
            misses.append({
                "tour": key[0], "record_index": key[1],
                "subject": _subject(orec.get("messages")),
                "old": (orec.get("response_text") or "")[:200],
                "new": (nrec.get("response_text") if nrec else "(no replay)") or "",
            })

    assert found > 0, f"no recorded discrepancy cases for {site} (fixture problem?)"
    assert not misses, (
        f"{site}: gpt-4o-mini MISSED {len(misses)} recorded discrepancy case(s):\n"
        + "\n".join(
            f"  - {m['tour']} #{m['record_index']}: {m['subject']}\n"
            f"      OLD: {m['old']!r}\n      NEW: {m['new']!r}"
            for m in misses
        )
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
