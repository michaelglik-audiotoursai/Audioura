#!/usr/bin/env python3
"""test_local215_holdout.py — Holdout test for claim_check.py on Chagall data.

Tests against a venue (Musée National Marc Chagall) that was NOT used during
development of claim_check.py (which was tuned on MAMAC + Matisse).

Hand-scored claims derive from known facts in the Chagall corpus:
- The corpus mentions: donation of 1972 (250+ works), Message Biblique from
  1966, born 1887, died 1985, French nationality 1937, oil on canvas works,
  Charles Sorlier lithographer, daughter Ida, married Valentina Brodsky.
- Claims marked UNSUPPORTED are fabricated specifics that do NOT appear.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import claim_check
from db_connection import get_connection


def run_holdout():
    conn = get_connection()
    cur = conn.cursor()

    # Get Chagall passages
    cur.execute(
        "SELECT stop_title, passages_json FROM stop_corpus "
        "WHERE venue_name ILIKE %s",
        ('%Chagall%',)
    )
    stop_rows = cur.fetchall()
    all_stop_passages = []
    for title, pj in stop_rows:
        data = json.loads(pj) if isinstance(pj, str) else pj
        for p in data:
            text = p.get('text', '') if isinstance(p, dict) else p
            if text:
                all_stop_passages.append(text)

    cur.execute(
        "SELECT pages_json FROM venue_corpus WHERE venue_name ILIKE %s LIMIT 1",
        ('%Chagall%',)
    )
    row = cur.fetchone()
    venue_passages = []
    if row:
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        for p in data:
            text = p.get('text', '') if isinstance(p, dict) else p
            if text:
                venue_passages.append(text)

    all_passages = all_stop_passages + venue_passages
    conn.close()

    print(f"Chagall passages: {len(all_stop_passages)} stop + {len(venue_passages)} venue = {len(all_passages)}")
    print()

    # ─── Hand-scored holdout claims ──────────────────────────────────────────
    # SUPPORTED: facts that ARE in the corpus
    # UNSUPPORTED: fabricated specifics that are NOT in the corpus
    holdout_claims = [
        # SUPPORTED — dates/facts directly in corpus
        ('Chagall was born in 1887', 'SUPPORTED', 'DATE'),
        ('Chagall died on 28 March 1985', 'SUPPORTED', 'DATE'),
        ('Chagall took French nationality in 1937', 'SUPPORTED', 'DATE'),
        ('The donation of 1972 represents more than 250 works', 'SUPPORTED', 'NUMBER'),
        ('Chagall married Valentina Brodsky', 'SUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('Daughter Ida married art historian Franz Meyer', 'SUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('Charles Sorlier donated lithographs to the museum', 'SUPPORTED', 'ATTRIBUTION'),
        ('In 1960 Brandeis University awarded Chagall an honorary degree', 'SUPPORTED', 'DATE'),
        ('The Message Biblique illustrates Genesis and Exodus', 'SUPPORTED', 'PROPER_NOUN_PREDICATE'),
        # SUPPORTED — paraphrase-level (requires stem/synonym matching)
        ('Chagall enriched the collections until his death', 'SUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('The museum received donations after the artist passed away', 'SUPPORTED', 'ATTRIBUTION'),
        ('Successive curators broadened the collection scope', 'SUPPORTED', 'PROPER_NOUN_PREDICATE'),
        # UNSUPPORTED — fabricated specifics with NO year/number overlap in corpus
        ('The museum was designed by architect Jean Nouvel', 'UNSUPPORTED', 'ATTRIBUTION'),
        ('Chagall studied under Henri Matisse in Paris', 'UNSUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('Salvador Dali influenced Chagall deeply', 'UNSUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('The stained glass windows depict the twelve tribes of Israel', 'UNSUPPORTED', 'COMPOSITION'),
        ('Chagall was awarded the Nobel Prize in Literature', 'UNSUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('The museum hosts a permanent sculpture garden', 'UNSUPPORTED', 'COMPOSITION'),
        ('Picasso and Chagall collaborated on ceramic works', 'UNSUPPORTED', 'PROPER_NOUN_PREDICATE'),
        ('The building was renovated by Renzo Piano in 2003', 'UNSUPPORTED', 'ATTRIBUTION'),
    ]

    print("=" * 70)
    print("HOLDOUT TEST: Musée National Marc Chagall (20 hand-scored claims)")
    print("=" * 70)
    print()

    total = 0
    agreements = 0
    false_supported = 0
    false_unsupported = 0
    disagreements = []

    for claim_text, hand_verdict, claim_type in holdout_claims:
        total += 1
        claim = {
            'text': claim_text,
            'type': claim_type,
            'sentence': claim_text,
        }

        # Basic matching
        evidence, score = claim_check._find_best_evidence(
            claim, all_passages, threshold=claim_check.PARAPHRASE_THRESHOLD
        )

        if score >= claim_check.PARAPHRASE_THRESHOLD and evidence:
            detector_verdict = 'SUPPORTED_PARAPHRASE'
        else:
            detector_verdict = 'UNSUPPORTED'

        # Enhanced pass (same logic as check_paragraph)
        if detector_verdict == 'UNSUPPORTED':
            enh_evidence, enh_score = claim_check._find_best_evidence_enhanced(
                claim, all_passages, threshold=claim_check.ENHANCED_THRESHOLD
            )
            if enh_score >= claim_check.ENHANCED_THRESHOLD and enh_evidence:
                detector_verdict = 'SUPPORTED_PARAPHRASE'
                evidence = enh_evidence
                score = enh_score

        # Compare
        hand_is_supported = hand_verdict == 'SUPPORTED'
        det_is_supported = detector_verdict.startswith('SUPPORTED')

        if hand_is_supported == det_is_supported:
            agreements += 1
            status = '✓'
        else:
            status = '✗'
            if det_is_supported and not hand_is_supported:
                false_supported += 1
            else:
                false_unsupported += 1
            disagreements.append({
                'claim': claim_text,
                'hand': hand_verdict,
                'detector': detector_verdict,
                'score': score,
            })

        print(f"  {status} [{hand_verdict:11s}] → [{detector_verdict:22s}] (score={score:.3f}) | {claim_text[:55]}")

    print()
    print("=" * 70)
    print("HOLDOUT SUMMARY")
    print("=" * 70)
    print(f"  Total claims: {total}")
    print(f"  Agreements: {agreements} ({100*agreements/total:.1f}%)")
    print(f"  False SUPPORTED (CRITICAL): {false_supported}")
    print(f"  False UNSUPPORTED (over-flagged): {false_unsupported}")
    print()

    if false_supported > 0:
        print("  ⚠️  REGRESSION: False SUPPORTED detected!")
        for d in disagreements:
            if d['detector'].startswith('SUPPORTED'):
                print(f"    DANGER: \"{d['claim'][:60]}\" (score={d['score']:.3f})")
    else:
        print("  ✓  Zero false SUPPORTED on holdout data")

    if false_unsupported > 0:
        print(f"\n  Over-flagged claims ({false_unsupported}):")
        for d in disagreements:
            if d['detector'] == 'UNSUPPORTED' and d['hand'] == 'SUPPORTED':
                print(f"    \"{d['claim'][:60]}\" (score={d['score']:.3f})")

    print()
    return false_supported, false_unsupported, total, agreements


if __name__ == '__main__':
    false_pass, false_flag, total, agree = run_holdout()
    if false_pass > 0:
        print("*** HARD CONSTRAINT VIOLATED: false SUPPORTED detected ***")
        sys.exit(1)
    sys.exit(0)
