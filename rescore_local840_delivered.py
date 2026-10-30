#!/usr/bin/env python3
"""rescore_local840_delivered.py — Orsay/Rijks re-scored on the 840 DELIVERED texts.

LOCAL-842 Do-item 4: no new generation. This re-runs `story_opportunity_scan` on
the stories the LOCAL-840 live run delivered, with the scanner's stakes vocabulary
BEFORE this ticket (the pre-842 `_STAKES`, depiction guard off) and AFTER it, and
prints the per-stop verdict and the stake sentence each AFTER-story turns on.

The delivered material:
  * Orsay — parsed from the delivered tour file this run wrote
    (Musée_d_Orsay__…_museum_tour_20261030_040300.txt).
  * Rijks — the delivered story paragraphs captured in SUBMISSION_LOCAL-840.md /
    reports/local840 (no Rijks tour .txt was persisted); the BEFORE per-stop
    verdicts are the ones recorded in reports/local840/live_result.json.
"""
import glob
import re
import sys

import story_opportunity_scan as sos

# The exact pre-842 _STAKES (from git HEAD:story_opportunity_scan.py), to score BEFORE.
_STAKES_BEFORE = re.compile(
    r'\b(only|never|no one|nothing|until|despite|although|even though|'
    r'the last|the only|the first|for the first time|would not|could not|'
    r'had to|refused|in the end|by then|too late|instead of|but not|'
    r'at the cost|risked|forced|'
    r'destroyed|destroy|pulped|burned|burnt|abandoned|scrapped|cancelled|'
    r'canceled|unfinished|incomplete|posthumous(?:ly)?|left\s+half|'
    r'started\s+over|began\s+again|withdrew|withdrawn|lost|'
    r'bequeathed|left\s+(?:it|them|this|the\s+\w+)\s+to|'
    r'broke\s+with|departed\s+from|complained|condemned|sentenced|'
    r'executed|exiled|banished|martyred|imprisoned|seized|confiscated|'
    r'looted|smuggled|rescued|hidden|concealed|'
    r'after\s+his\s+death|after\s+her\s+death|never\s+again|'
    r'the\s+only\s+time|would\s+never)\b', re.IGNORECASE)


def score(text):
    m = sos.measure(text)
    v = sos.verdict(m)
    lr = m['longest_run']
    return (not v['needs_additional_story'], lr)


def score_before(text):
    """Temporarily restore the pre-842 scanner: old vocabulary, guard off."""
    real_stakes = sos._STAKES
    real_guard = sos._sentence_has_stakes
    try:
        sos._STAKES = _STAKES_BEFORE
        sos._sentence_has_stakes = lambda s: bool(_STAKES_BEFORE.search(s))
        return score(text)
    finally:
        sos._STAKES = real_stakes
        sos._sentence_has_stakes = real_guard


def stake_sentence(text):
    """The sentence in the longest run that turns the AFTER-verdict (quoted in report)."""
    m = sos.measure(text)
    lr = m['longest_run']
    if lr.get('handle') is None:
        return None
    sents = m['sentences']
    # recover the best span for the winning handle
    h = next((x for x in m['handles'] if x['surface'] == lr['handle']), None)
    if not h:
        return None
    for i in h['at']:
        if sos._sentence_has_stakes(sents[i]):
            return sents[i].strip()
    return None


def parse_delivered_tour(path):
    """Return {stop_title: story_prose} from a delivered tour .txt.

    The story-bearing prose is the body paragraphs of each stop (between the
    Orientation line and the Directions line), which is what the scanner judged.
    """
    text = open(path, encoding='utf-8').read()
    stops = {}
    chunks = re.split(r'\nStop \d+: ', text)
    for chunk in chunks[1:]:
        title = chunk.splitlines()[0].strip()
        body = chunk
        # keep everything from the first Orientation to Directions/next
        mo = re.search(r'Orientation:(.*?)(?:\nDirections:|\Z)', body, re.S)
        prose = (mo.group(1) if mo else body)
        stops[title] = re.sub(r'\s+', ' ', prose).strip()
    return stops


def report_tour(name, stops):
    print(f"\n{'='*78}\n{name} — re-scored on the DELIVERED 840 text\n{'='*78}")
    before_pass = after_pass = 0
    for title, prose in stops.items():
        b_story, _ = score_before(prose)
        a_story, lr = score(prose)
        before_pass += int(b_story)
        after_pass += int(a_story)
        print(f"\n  {title}")
        print(f"    BEFORE: {'STORY' if b_story else 'NO STORY'}   "
              f"AFTER: {'STORY' if a_story else 'NO STORY'}   "
              f"(run={lr.get('run')} agency={lr.get('agency')} stakes={lr.get('stakes')} "
              f"handle={lr.get('handle')!r})")
        if a_story:
            ss = stake_sentence(prose)
            if ss:
                print(f"    stake: \"{ss[:180]}\"")
    print(f"\n  → BEFORE {before_pass}/{len(stops)}   AFTER {after_pass}/{len(stops)}")
    return before_pass, after_pass


# ── Rijks delivered story paragraphs (from SUBMISSION_LOCAL-840.md / reports) ──
# No Rijks tour .txt was persisted by the run, so the AFTER re-score below covers
# the one Rijks stop whose delivered story the submission quotes verbatim — the
# Night Watch. The authoritative BEFORE per-stop verdicts for every Rijks stop are
# the ones the run recorded in reports/local840/live_result.json, printed first.
RIJKS_NIGHT_WATCH = (
    "On 14 September 1975, Wilhelmus de Rijk, an unemployed school teacher, "
    "attacked The Night Watch with a bread knife, slashing several large "
    "zig-zagged cuts up to 30 centimetres long into the canvas. "
    "The painting was left permanently scarred. "
    "De Rijk died by suicide in April 1976, before he could be charged.")


def report_recorded_before(path):
    """Print the BEFORE per-stop verdicts the 840 run itself recorded."""
    import json
    data = json.load(open(path))
    print(f"\n{'='*78}\nBEFORE — per-stop verdicts RECORDED by the 840 live run\n"
          f"({path})\n{'='*78}")
    for venue in data['results']:
        passed = sum(1 for st in venue['per_stop'] if st['has_story'])
        print(f"\n  {venue['location']}  →  {passed}/{len(venue['per_stop'])}")
        for st in venue['per_stop']:
            tag = 'STORY' if st['has_story'] else 'NO STORY'
            print(f"    stop {st['stop']} {st['title'][:46]:46} {tag}")


def main():
    report_recorded_before('reports/local840/live_result.json')

    orsay_files = sorted(glob.glob(
        'Mus*Orsay*museum_tour_2026103*.txt'))
    if orsay_files:
        orsay = parse_delivered_tour(orsay_files[-1])
        report_tour(f"AFTER — ORSAY re-scored on delivered prose "
                    f"[{orsay_files[-1]}]", orsay)
    else:
        print("WARN: no delivered Orsay tour .txt found", file=sys.stderr)

    # Rijks: the one delivered story the submission quotes verbatim.
    print(f"\n{'='*78}\nAFTER — RIJKS Night Watch (delivered paragraph, 840 submission)\n{'='*78}")
    b_story, _ = score_before(RIJKS_NIGHT_WATCH)
    a_story, lr = score(RIJKS_NIGHT_WATCH)
    print(f"\n  De Nachtwacht (The Night Watch)")
    print(f"    BEFORE: {'STORY' if b_story else 'NO STORY'}   "
          f"AFTER: {'STORY' if a_story else 'NO STORY'}   "
          f"(run={lr.get('run')} agency={lr.get('agency')} stakes={lr.get('stakes')} "
          f"handle={lr.get('handle')!r})")
    if a_story:
        print(f"    stake: \"{stake_sentence(RIJKS_NIGHT_WATCH)[:180]}\"")


if __name__ == '__main__':
    main()
