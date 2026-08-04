#!/usr/bin/env python3
"""test_local210_calibration.py — Calibrate claim_check.py against hand-scored sets.

Runs claim_check against LOCAL-195 (MAMAC, 12 paragraphs) and LOCAL-205
(Matisse, ~30 paragraphs) hand-scored verdicts and reports:
- Agreement rate per verdict class
- Every disagreement, with the claim, both verdicts, and reading
"""

import sys
import os
import json
import re

# Repo root import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import claim_check
from db_connection import get_connection


def get_stop_passages(conn, venue_pattern, stop_title):
    """Fetch passages for a stop from the database."""
    cur = conn.cursor()
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE venue_name ILIKE %s AND stop_title = %s",
        (f'%{venue_pattern}%', stop_title)
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return []
    passages_json = row[0]
    if isinstance(passages_json, str):
        passages_json = json.loads(passages_json)
    passages = []
    for p in passages_json:
        if isinstance(p, dict):
            passages.append(p.get('text', ''))
        elif isinstance(p, str):
            passages.append(p)
    return [p for p in passages if p]


def get_venue_passages(conn, venue_pattern):
    """Fetch venue-level passages."""
    cur = conn.cursor()
    cur.execute(
        "SELECT pages_json FROM venue_corpus WHERE venue_name ILIKE %s LIMIT 1",
        (f'%{venue_pattern}%',)
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return []
    pages = row[0]
    if isinstance(pages, str):
        pages = json.loads(pages)
    texts = []
    for p in pages:
        if isinstance(p, dict):
            texts.append(p.get('text', ''))
        elif isinstance(p, str):
            texts.append(p)
    return [t for t in texts if t]


def split_paragraphs(tour_text):
    """Split tour text into paragraphs, skipping metadata lines."""
    lines = tour_text.split('\n')
    paragraphs = []
    current = []

    skip_prefixes = [
        'Step-by-Step', 'Tour-Category:', 'Stop ', 'Address:',
        'Coordinates:', 'Museum Information:', 'Directions:',
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                para = ' '.join(current)
                # Only keep substantial paragraphs (not one-liners)
                if len(para) > 50:
                    paragraphs.append(para)
                current = []
        elif any(stripped.startswith(p) for p in skip_prefixes):
            if current:
                para = ' '.join(current)
                if len(para) > 50:
                    paragraphs.append(para)
                current = []
        else:
            current.append(stripped)

    if current:
        para = ' '.join(current)
        if len(para) > 50:
            paragraphs.append(para)

    return paragraphs


def run_local195_calibration(conn):
    """Run claim_check against LOCAL-195 hand-scored paragraphs."""
    print("=" * 70)
    print("LOCAL-195 CALIBRATION (MAMAC, Arms A + B)")
    print("=" * 70)
    print()

    # Get passages for both MAMAC stops
    richard_long_passages = get_stop_passages(conn, 'Art Moderne', 'Richard Long ou la sculpture en marchant')
    she_bam_passages = get_stop_passages(conn, 'Art Moderne', 'She-Bam Pow POP Wizz')
    venue_passages = get_venue_passages(conn, 'Art Moderne')

    # Combine stop + venue passages (the hand check used both)
    # The hand check references SE[22], SE[23] etc from venue_corpus
    rl_all_passages = richard_long_passages + venue_passages
    sb_all_passages = she_bam_passages + venue_passages

    print(f"Richard Long passages: {len(richard_long_passages)} stop + {len(venue_passages)} venue = {len(rl_all_passages)}")
    print(f"She-Bam passages: {len(she_bam_passages)} stop + {len(venue_passages)} venue = {len(sb_all_passages)}")
    print()

    # ─── Hand-scored data from SUBMISSION_LOCAL-195 ───────────────────────────
    # Format: (paragraph_label, text_excerpt, stop_title, expected_unsupported, hand_claims)
    # hand_claims: list of (claim_text, hand_verdict)

    hand_scored_195 = [
        # ARM A
        {
            'label': 'A1 (Richard Long positioning)',
            'stop': 'Richard Long ou la sculpture en marchant',
            'expected_unsupported': 0,
            'hand_claims': [
                ('Exhibit titled "Richard Long ou la sculpture en marchant" exists at MAMAC', 'SUPPORTED_PARAPHRASE'),
                ('Located in Nice, France', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        {
            'label': 'A2 (Richard Long prolog)',
            'stop': 'Richard Long ou la sculpture en marchant',
            'expected_unsupported': 1,
            'hand_claims': [
                ('MAMAC inaugurated June 21, 1990', 'SUPPORTED_PARAPHRASE'),
                ('Pop art is part of MAMAC collection', 'SUPPORTED_PARAPHRASE'),
                ('Generous contributions shaped MAMAC', 'SUPPORTED_PARAPHRASE'),
                ('Yves Klein influenced the museum', 'SUPPORTED_PARAPHRASE'),
                ('Richard Long\'s transformative pieces', 'UNSUPPORTED'),
                ('Museum dedicated to modern and contemporary art', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        {
            'label': 'A3 (She-Bam main content)',
            'stop': 'She-Bam Pow POP Wizz',
            'expected_unsupported': 1,
            'hand_claims': [
                ('She-Bam Pow POP Wizz relates to pop art', 'SUPPORTED_PARAPHRASE'),
                ('One standout piece...large-scale painting', 'UNSUPPORTED'),
                ('popular culture references to convey social commentary', 'SUPPORTED_PARAPHRASE'),
                ('Pop art challenges boundaries between high and low culture', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        {
            'label': 'A4 (She-Bam epilog)',
            'stop': 'She-Bam Pow POP Wizz',
            'expected_unsupported': 0,
            'hand_claims': [
                ('Museum has presented over 213 exhibitions', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        # ARM B
        {
            'label': 'B1 (Richard Long positioning)',
            'stop': 'Richard Long ou la sculpture en marchant',
            'expected_unsupported': 2,  # 1-2 per hand check
            'hand_claims': [
                ('The work uses natural materials', 'UNSUPPORTED'),
                ('The museum has large windows', 'UNSUPPORTED'),
            ],
        },
        {
            'label': 'B2 (Richard Long prolog)',
            'stop': 'Richard Long ou la sculpture en marchant',
            'expected_unsupported': 2,
            'hand_claims': [
                ('MAMAC opened June 21, 1990', 'SUPPORTED_PARAPHRASE'),
                ('Donations shaped the collection', 'SUPPORTED_PARAPHRASE'),
                ('Richard Long\'s sculptures...essence of movement and nature', 'UNSUPPORTED'),
                ('the landscapes he traverses', 'UNSUPPORTED'),
                ('Niki de Saint Phalle as donor', 'SUPPORTED_PARAPHRASE'),
                ('Pop Art is part of MAMAC', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        {
            'label': 'B3 (Richard Long main content)',
            'stop': 'Richard Long ou la sculpture en marchant',
            'expected_unsupported': 6,
            'hand_claims': [
                ('circular arrangements made from stones', 'UNSUPPORTED'),
                ('choice of natural materials', 'UNSUPPORTED'),
                ('land art movement of the 1960s and 1970s', 'UNSUPPORTED'),
                ('Robert Smithson and Andy Goldsworthy', 'UNSUPPORTED'),
                ('sought to confront commercialization of art', 'UNSUPPORTED'),
                ('emerged during heightened environmental awareness', 'UNSUPPORTED'),
                ('museum mission: modern and contemporary art', 'SUPPORTED_PARAPHRASE'),
            ],
        },
        {
            'label': 'B4 (She-Bam epilog)',
            'stop': 'She-Bam Pow POP Wizz',
            'expected_unsupported': 0,
            'hand_claims': [
                ('MAMAC opened 21 June 1990, in Nice, France', 'SUPPORTED_PARAPHRASE'),
            ],
        },
    ]

    # ─── Run the detector on actual paragraph texts ───────────────────────────
    # We need the actual texts. Read from SUBMISSION_LOCAL-195 structure.
    # For calibration we'll use the claim texts from the hand-scored data
    # and check agreement on those specific claims.

    total_claims = 0
    agreements = 0
    disagreements = []

    for entry in hand_scored_195:
        stop = entry['stop']
        if 'Richard Long' in stop:
            passages = rl_all_passages
        else:
            passages = sb_all_passages

        print(f"--- {entry['label']} ---")
        print(f"  Hand-scored unsupported: {entry['expected_unsupported']}")

        for claim_text, hand_verdict in entry['hand_claims']:
            total_claims += 1
            # Create a synthetic claim and check it
            claim = {
                'text': claim_text,
                'type': 'MANUAL',
                'sentence': claim_text,
            }
            evidence, score = claim_check._find_best_evidence(claim, passages)

            # Determine effective threshold
            tokens = claim_check._tokenize(claim_text)
            content_tokens = [t for t in tokens if len(t) >= 3 and not t.isdigit()]
            eff_threshold = 0.55 if len(content_tokens) > 2 else 0.40

            if score >= eff_threshold and evidence:
                detector_verdict = 'SUPPORTED_PARAPHRASE'
            else:
                detector_verdict = 'UNSUPPORTED'

            # Compare
            hand_is_supported = hand_verdict.startswith('SUPPORTED')
            det_is_supported = detector_verdict.startswith('SUPPORTED')

            if hand_is_supported == det_is_supported:
                agreements += 1
                status = '✓'
            else:
                status = '✗'
                disagreements.append({
                    'paragraph': entry['label'],
                    'claim': claim_text,
                    'hand': hand_verdict,
                    'detector': detector_verdict,
                    'score': score,
                    'evidence': evidence[:100] if evidence else None,
                })

            print(f"  {status} [{hand_verdict:22s}] → [{detector_verdict:22s}] (score={score:.3f}) | {claim_text[:60]}")

        print()

    return total_claims, agreements, disagreements


def run_local205_calibration(conn):
    """Run claim_check against LOCAL-205 hand-scored paragraphs (Matisse)."""
    print("=" * 70)
    print("LOCAL-205 CALIBRATION (Musée Matisse, Arms A + B)")
    print("=" * 70)
    print()

    # Get passages
    nymphe_passages = get_stop_passages(conn, 'matisse', 'Nymphe dans la forêt')
    tempete_passages = get_stop_passages(conn, 'matisse', 'Tempête à Nice')
    venue_passages = get_venue_passages(conn, 'matisse')

    nymphe_all = nymphe_passages + venue_passages
    tempete_all = tempete_passages + venue_passages

    print(f"Nymphe passages: {len(nymphe_passages)} stop + {len(venue_passages)} venue = {len(nymphe_all)}")
    print(f"Tempête passages: {len(tempete_passages)} stop + {len(venue_passages)} venue = {len(tempete_all)}")
    print()

    # Read actual tour texts
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local205_paragraphs_v2')

    total_claims = 0
    total_unsupported_detector = 0
    total_unsupported_hand = 0
    all_paragraphs_checked = 0

    # Process all 6 tour files
    for fname in sorted(os.listdir(base_dir)):
        if not fname.endswith('_tour_text.txt'):
            continue

        fpath = os.path.join(base_dir, fname)
        with open(fpath, 'r') as f:
            tour_text = f.read()

        paragraphs = split_paragraphs(tour_text)
        arm = fname[0]  # A or B
        run_num = fname[1]  # 1, 2, or 3

        print(f"--- {fname} ({len(paragraphs)} paragraphs) ---")

        for i, para in enumerate(paragraphs):
            # Determine which stop this belongs to
            if 'Nymphe' in para or (i < len(paragraphs) // 2 + 1):
                passages = nymphe_all
                stop_title = 'Nymphe dans la forêt'
            else:
                passages = tempete_all
                stop_title = 'Tempête à Nice'

            # Skip structural/sources paragraphs
            if para.startswith('From ') and 'you have followed' in para:
                continue
            if para.startswith('Sources:'):
                continue
            if para.startswith('From ') and 'a collection that spans' in para:
                continue

            result = claim_check.check_paragraph(
                para, stop_title, 'Musee Matisse, Nice, France', passages
            )

            all_paragraphs_checked += 1
            total_claims += len(result['claims'])
            total_unsupported_detector += result['unsupported_count']

            if result['unsupported_count'] > 0:
                print(f"  Para {i+1} ({stop_title[:15]}): {result['unsupported_count']} unsupported / {len(result['claims'])} claims")
                for c in result['claims']:
                    if c['verdict'] == 'UNSUPPORTED':
                        print(f"    UNSUPPORTED: {c['text'][:70]}")

        print()

    # LOCAL-205 hand-scored totals: ARM A = 23 unsupported in 9 paragraphs,
    # ARM B = 31 unsupported in 10 paragraphs. Total = 54 across 3 runs per arm.
    # But per-run: ~7.7 (A) and ~10.3 (B) per run.
    # The hand count for a single A run is ~23/3 ≈ 7.7 unsupported per run.
    hand_per_run_a = 23 / 3
    hand_per_run_b = 31 / 3

    print(f"\n{'='*50}")
    print(f"LOCAL-205 AGGREGATE (all 6 runs):")
    print(f"  Paragraphs checked: {all_paragraphs_checked}")
    print(f"  Total claims extracted: {total_claims}")
    print(f"  Total UNSUPPORTED (detector): {total_unsupported_detector}")
    print(f"  Unsupported per paragraph (detector): {total_unsupported_detector/max(1,all_paragraphs_checked):.2f}")
    print(f"  Hand-scored reference: ARM A={hand_per_run_a:.1f}/run, ARM B={hand_per_run_b:.1f}/run")
    print(f"  Hand-scored total (all 6 runs): ~{23+31} claims")
    print()

    return total_claims, total_unsupported_detector, all_paragraphs_checked


def main():
    conn = get_connection()

    print("\n" + "=" * 70)
    print("CLAIM_CHECK.PY CALIBRATION REPORT — LOCAL-210")
    print("=" * 70 + "\n")

    # Run LOCAL-195 calibration
    total_195, agree_195, disagree_195 = run_local195_calibration(conn)

    print("\n" + "=" * 70)
    print("LOCAL-195 AGREEMENT SUMMARY")
    print("=" * 70)
    print(f"  Total claims checked: {total_195}")
    print(f"  Agreements: {agree_195} ({100*agree_195/max(1,total_195):.1f}%)")
    print(f"  Disagreements: {len(disagree_195)} ({100*len(disagree_195)/max(1,total_195):.1f}%)")
    print()

    if disagree_195:
        print("  DISAGREEMENTS:")
        for d in disagree_195:
            print(f"    [{d['paragraph']}] \"{d['claim'][:50]}\"")
            print(f"      Hand: {d['hand']}  |  Detector: {d['detector']}  (score={d['score']:.3f})")
            if d['evidence']:
                print(f"      Evidence: {d['evidence'][:80]}")
            print()

    # Run LOCAL-205 calibration
    print()
    total_205, unsupported_205, paras_205 = run_local205_calibration(conn)

    # ─── Direction of error ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DIRECTION OF ERROR ANALYSIS")
    print("=" * 70)
    print()

    false_supports = sum(1 for d in disagree_195 if d['hand'] == 'UNSUPPORTED' and d['detector'] == 'SUPPORTED_PARAPHRASE')
    false_unsupports = sum(1 for d in disagree_195 if d['hand'].startswith('SUPPORTED') and d['detector'] == 'UNSUPPORTED')

    print(f"  False SUPPORTED (missed unsupported claims): {false_supports}")
    print(f"  False UNSUPPORTED (over-flagged supported claims): {false_unsupports}")
    print()
    if false_supports > false_unsupports:
        print("  ⚠️  Direction: detector errs toward UNDER-FLAGGING (letting unsupported claims pass)")
        print("     This is the DANGEROUS direction (false pass = fabricated fact reaching listener)")
    elif false_unsupports > false_supports:
        print("  ✓  Direction: detector errs toward OVER-FLAGGING (marking supported claims as unsupported)")
        print("     This is the SAFE direction (erring toward UNSUPPORTED, as task requires)")
    else:
        print("  ≈  Errors balanced between directions")

    print()
    print("  Cost per paragraph: $0.00 (no LLM calls, pure regex/token matching)")
    print()

    conn.close()


if __name__ == '__main__':
    main()
