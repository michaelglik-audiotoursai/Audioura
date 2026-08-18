#!/usr/bin/env python3
"""gate_fp_probe.py — measure a gate's FALSE-REJECTION rate on known-good text.

Michael's mission, 2026-08-18:

    "improve the validators so the good stories for humans are not dismissed as
    inaccurate when there is no evidence that they are."

Before tightening or loosening anything we have to know how often a gate's
rejection is RIGHT. The standing check (D242 #3) says: run the instrument
against a case whose answer you already know.

THE KNOWN-ANSWER CASE
---------------------
`TOUR_MFA_20260812_2030.txt` is delivered text. It already survived the full
gate chain, and Michael read it and confirmed the stories are real, factual and
correctly assigned. So for this input the correct number of drops is ZERO.

Every sentence a gate removes from it is therefore one of exactly two things,
and both are defects:

  * a FALSE REJECTION — the gate rejects prose a human accepted, or
  * NON-IDEMPOTENCE  — the gate disagrees with the run that produced the text.

This probe does not decide which; it prints the sentence and the gate's stated
reason so a human can. It never writes to the tour files.

Only deterministic, offline, free gate paths are exercised (no api_key, so
`unsupported_claim_gate` never escalates) — the strict path is the one that
does the rejecting, and it is the one under test.

    python3 gate_fp_probe.py                       # the approved MFA tour
    python3 gate_fp_probe.py --file OTHER_TOUR.txt
    python3 gate_fp_probe.py --json out.json
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULT_TOUR = os.path.join(HERE, 'TOUR_MFA_20260812_2030.txt')
# The exhibition page_text this tour was actually grounded against — captured by
# story_lab (D424). The live gate is SKIPPED when this is empty, so probing with
# it is the only run that reproduces production.
DEFAULT_CORPUS = os.path.join(HERE, 'story_lab_state', 'stop2_page_text.txt')

# The fields the live gates actually scan (GATED_PROSE_FIELDS in
# generate_tour_text.py): the narrative body and the orientation.
_STOP_RE = re.compile(r'^Stop\s+(\d+):\s*(.+?)\s*$', re.MULTILINE)


def parse_tour(text):
    """Split delivered tour text into stops with their orientation and body.

    The delivered format is flat text, not JSON, so this reproduces the field
    split the gates see: `Orientation:` is one field, and the prose paragraphs
    between it and `Directions:` are the description.
    """
    stops = []
    marks = list(_STOP_RE.finditer(text))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = text[start:end]

        orientation = ''
        om = re.search(r'^Orientation:\s*(.+?)$', block, re.MULTILINE)
        if om:
            orientation = om.group(1).strip()

        body_start = om.end() if om else 0
        dm = re.search(r'^Directions:', block[body_start:], re.MULTILINE)
        body = block[body_start:body_start + dm.start()] if dm else block[body_start:]
        body = '\n\n'.join(p.strip() for p in body.split('\n\n') if p.strip())

        stops.append({'n': int(m.group(1)), 'name': m.group(2),
                      'orientation': orientation, 'description': body})
    return stops


def _diff_sentences(before, after):
    """Sentences present in `before` and absent from `after`, in order."""
    from unsupported_claim_gate import _split_sentences
    kept = {s.strip() for s in _split_sentences(after)}
    return [s.strip() for s in _split_sentences(before)
            if s.strip() and s.strip() not in kept]


# ═══════════════════════════════════════════════════════════════════════════════
# GATE 1 — LOCAL-263 unsupported-claim gate (PHASE 5.156)
# ═══════════════════════════════════════════════════════════════════════════════
# Runs on EVERY tour, not only museums. Fully text-internal: a "claim" survives
# only if a sentence within +2/-1 carries a concrete payload on the same
# subject. That is a PROXIMITY rule, not an evidence rule — which is why it is
# the first suspect for Michael's complaint.

def probe_unsupported_claim_gate(stops):
    from unsupported_claim_gate import apply_unsupported_claim_gate, classify_claim

    findings = []
    for st in stops:
        for field in ('orientation', 'description'):
            text = st[field]
            if not text.strip():
                continue
            # api_key=None -> deterministic path only, no escalation, $0.00
            new_text, stats = apply_unsupported_claim_gate(
                text, corpus_passages=[], api_key=None, model=None)
            if stats['sentences_removed'] == 0:
                continue
            for sent in _diff_sentences(text, new_text):
                findings.append({
                    'gate': 'LOCAL-263 unsupported-claim',
                    'stop': st['name'],
                    'field': field,
                    'claim_type': classify_claim(sent) or '(none)',
                    'reason': 'no adjacent sentence supplies a concrete payload '
                              'on the same subject (+2/-1 window)',
                    'sentence': sent,
                })
    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# GATE 2 — LOCAL-458 role-claim gate (PHASE 5.158b)
# ═══════════════════════════════════════════════════════════════════════════════
# Drops any sentence naming an agent in a ROLE (publisher, printer, donor) when
# the stop record's slot is empty AND the agent is absent from the corpus.
# Absence from a corpus is absence of evidence — exactly the shape Michael is
# objecting to. Probed here with an EMPTY corpus, which is the worst case and
# is also what the live gate sees whenever retrieval returns no page text.

def probe_role_claim_gate(stops, corpus=''):
    from stop_claim_audit import apply_role_claim_gate, extract_role_claims

    findings = []
    for st in stops:
        for field in ('orientation', 'description'):
            text = st[field]
            if not text.strip():
                continue
            stop_record = {'publisher': '', 'credit_line': '', 'artist': ''}
            cleaned, drop_log = apply_role_claim_gate(text, stop_record, corpus)
            for row in drop_log:
                for sent in row['dropped_sentences']:
                    findings.append({
                        'gate': 'LOCAL-458 role-claim',
                        'stop': st['name'],
                        'field': field,
                        'claim_type': f"{row['role']} -> {row['agent']}",
                        'reason': row['reason'],
                        'sentence': sent.strip(),
                    })
            _ = extract_role_claims  # kept importable for interactive use
    return findings


PROBES = [
    ('LOCAL-263 unsupported-claim', probe_unsupported_claim_gate),
    ('LOCAL-458 role-claim', probe_role_claim_gate),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default=DEFAULT_TOUR)
    ap.add_argument('--corpus', default=DEFAULT_CORPUS,
                    help='exhibition page_text the live gate grounds against. '
                         'Empty string = the worst case (retrieval returned '
                         'nothing), which live SKIPS the gate for.')
    ap.add_argument('--json', default='')
    a = ap.parse_args()

    text = open(a.file, encoding='utf-8').read()
    stops = parse_tour(text)
    corpus = ''
    if a.corpus and os.path.exists(a.corpus):
        corpus = open(a.corpus, encoding='utf-8').read()
    print(f"\n{os.path.basename(a.file)} — {len(stops)} stops, "
          f"{len(text)} chars. Human-approved: correct drop count is 0.")
    print(f"corpus: {os.path.basename(a.corpus) if corpus else '(none)'} "
          f"— {len(corpus)} chars\n")

    all_findings = []
    for label, fn in PROBES:
        found = fn(stops, corpus) if fn is probe_role_claim_gate else fn(stops)
        all_findings += found
        print(f"  {label:38} {len(found)} sentence(s) dropped")

    print()
    for f in all_findings:
        print(f"─── {f['gate']}  [{f['field']}]  stop: {f['stop'][:44]}")
        print(f"    type   : {f['claim_type']}")
        print(f"    reason : {f['reason']}")
        print(f"    DROPPED: {f['sentence']}")
        print()

    total_sents = 0
    from unsupported_claim_gate import _split_sentences
    for st in stops:
        for field in ('orientation', 'description'):
            total_sents += len([s for s in _split_sentences(st[field]) if s.strip()])

    print(f"TOTAL: {len(all_findings)} dropped out of {total_sents} sentences "
          f"in human-approved text "
          f"({100.0 * len(all_findings) / total_sents:.1f}% false-rejection floor)")

    if a.json:
        json.dump({'file': a.file, 'sentences': total_sents,
                   'findings': all_findings}, open(a.json, 'w'),
                  indent=2, ensure_ascii=False)
        print(f"  -> {a.json}")


if __name__ == '__main__':
    main()
