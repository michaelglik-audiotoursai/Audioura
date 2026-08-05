#!/usr/bin/env python3
"""run_local235_r10_measurement.py — Corpus-wide R10 rate and impact assessment.

Measures:
1. R10 firing rate across all stored tours, by tour type
2. How many paragraphs would be emptied by R10 + R9 combined
3. Whether any tour would lose more than 1/3 of its sentences
4. Re-runs calibration against Michael's 11 marks (QUALITY_PROFILE.md §5)

READ-ONLY. No writes to audio_tours.
"""
import json
import os
import sys
import re
from collections import defaultdict
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_validator_detector import (
    check_r10_unfulfilled_promise,
    apply_r10_to_description,
    apply_r9_to_description,
    check_r9_generic,
    check_r1_imperatives,
    check_r8_prompt_leakage,
    _is_style_navigation_sentence,
    _split_sentences,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR TYPE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_tour_type(request_string: str, tour_name: str) -> str:
    text = (request_string or '').lower() + ' ' + (tour_name or '').lower()
    if any(k in text for k in ['cycling', 'bike', 'biking', 'cycle', 'bicycle']):
        return 'cycling'
    if any(k in text for k in ['museum', 'gallery', 'galleries', 'exhibition',
                                'collection', 'musée', 'palazzo', 'palais']):
        return 'museum'
    if any(k in text for k in ['walking', 'walk', 'stroll', 'hike', 'hiking',
                                'neighborhood', 'district', 'historic', 'village']):
        return 'walking'
    return 'other'


# ═══════════════════════════════════════════════════════════════════════════════
# PARSE TOUR STOPS
# ═══════════════════════════════════════════════════════════════════════════════

def parse_stop_descriptions(tour_content: str) -> List[str]:
    """Extract stop descriptions from tour content."""
    if not tour_content:
        return []
    # Split on stop markers
    has_stop_markers = bool(re.search(r'Stop \d+:', tour_content))
    if has_stop_markers:
        parts = re.split(r'\nStop \d+:\s*', tour_content)
        if not parts[0].strip() or 'Tour-Category' in parts[0]:
            parts = parts[1:]
    else:
        parts = [tour_content]

    descriptions = []
    for part in parts:
        # Extract narrative paragraphs (skip metadata lines)
        lines = part.strip().split('\n')
        desc_lines = []
        in_narrative = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if desc_lines:
                    desc_lines.append('')
                continue
            # Skip metadata
            if re.match(r'^(Address|Coordinates|Type|Museum|Orientation|Directions):', stripped):
                continue
            if re.match(r'^[A-Z][a-z]+:', stripped) and len(stripped) < 80:
                continue
            # Narrative content
            if len(stripped) > 50:
                in_narrative = True
            if in_narrative:
                desc_lines.append(stripped)

        desc = '\n\n'.join('\n'.join(g) for g in _group_paragraphs(desc_lines))
        if desc.strip():
            descriptions.append(desc.strip())

    return descriptions


def _group_paragraphs(lines):
    """Group lines into paragraphs (separated by empty lines)."""
    groups = []
    current = []
    for line in lines:
        if not line:
            if current:
                groups.append(current)
                current = []
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


# ═══════════════════════════════════════════════════════════════════════════════
# CALIBRATION against Michael's 11 marks (QUALITY_PROFILE.md §5)
# ═══════════════════════════════════════════════════════════════════════════════

# Michael's scores for tour 163's 11 groups
MICHAEL_SCORES = [5, 1, 3, 3, 2, 1, 1, 5, 1, 0, 0]

# The correct many-to-one mapping from QUALITY_PROFILE.md:
# M0=5: navigation+R1(exempt) → AGREE
# M1=1: R1 fires → AGREE
# M2=3: R1 fires (conditional) → PARTIAL
# M3=3: R8 fires → DISAGREE (machine too harsh)
# M4=2: clean (machine misses) → DISAGREE (machine too lenient)
# M5=1: clean (machine misses) → DISAGREE (machine too lenient)
# M6=1: R1 fires → AGREE
# M7=5: clean → AGREE
# M8=1: clean (machine misses) → DISAGREE (machine too lenient)
# M9=0: R9 fires → AGREE
# M10=0: R9 fires → AGREE

# With R10, groups 4 and 8 may now be caught:
# M4 (score 2): "Pedal along the coastline, envisioning the hidden coves and
#   stories that lie just beyond the horizon, immersing yourself..."
# M8 (score 1): "The Rue Obscure, with its shadowy passageways, whispers tales
#   of a bygone era when it provided shelter and secrecy..."

# Michael's group 8 sentences (machine groups 14, 15):
M8_SENTENCES = [
    "Walking through the narrow streets may evoke the scent of sea salt, linking you to the town's maritime legacy.",
    "The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town's residents.",
    "This historical gem adds depth to your understanding of Villefranche-sur-Mer's past and its resilience through the centuries.",
]

# Michael's group 4 sentence (machine group 10):
M4_SENTENCES = [
    "Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
]


def run_calibration():
    """Re-run calibration with R10 added. Return agreement count."""
    # Check if R10 fires on groups where machine previously said CLEAN
    results = {}

    # M8: "whispers tales of a bygone era" — does R10 fire?
    r10_m8 = check_r10_unfulfilled_promise(M8_SENTENCES, 1)
    results['M8_R10'] = r10_m8 is not None

    # M4: "envisioning the hidden coves and stories" — R10?
    # Context: previous sentence is concrete (has measurement 2.7 km)
    m4_context = [
        "Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east.",
        "As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels.",
        "The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem.",
        "Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
    ]
    r10_m4 = check_r10_unfulfilled_promise(m4_context, 3)
    results['M4_R10'] = r10_m4 is not None

    # Original calibration: 5 agree, 2 partial, 4 disagree (from QUALITY_PROFILE.md)
    # Original agreements: groups 0, 1, 6, 7, 9, 10 = 6 (with partial for 2)
    # Let's be precise: "5 agree · 2 partial · 4 disagree"
    base_agree = 5
    base_partial = 2
    base_disagree = 4

    new_agree = base_agree
    new_partial = base_partial
    new_disagree = base_disagree

    # If R10 fires on M8 (score 1), that's a new agreement
    if results['M8_R10']:
        new_agree += 1
        new_disagree -= 1

    # If R10 fires on M4 (score 2), that's a new partial (it's not 0/5,
    # machine says delete but Michael says rewritable 2/5)
    if results['M4_R10']:
        # This is now a "machine too harsh" case — Michael scored 2 but R10 wants delete.
        # Actually wait — R10 fires means the machine now SEES the problem.
        # But the action (delete) vs Michael's implicit action (rewrite) differ.
        # Agreement means: machine detects something wrong where Michael detected something wrong.
        # Michael scored 2/5 — definitely a problem. R10 firing = detection is correct.
        # So this converts a DISAGREE (machine missed) to a PARTIAL (detects but action differs)
        new_partial += 1
        new_disagree -= 1

    return {
        'M8_R10_fires': results['M8_R10'],
        'M4_R10_fires': results['M4_R10'],
        'original': {'agree': base_agree, 'partial': base_partial, 'disagree': base_disagree},
        'with_r10': {'agree': new_agree, 'partial': new_partial, 'disagree': new_disagree},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MEASUREMENT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("LOCAL-235: R10 UNFULFILLED PROMISE — Corpus-Wide Measurement")
    print("=" * 70)

    # Connect to database
    conn = get_connection()
    cur = conn.cursor()

    # Get total row count
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_rows = cur.fetchone()[0]
    print(f"\naudio_tours row count: {total_rows}")

    # Verify Nice list
    nice_ids = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
    cur.execute("SELECT id FROM audio_tours WHERE id = ANY(%s) ORDER BY id", (nice_ids,))
    found_nice = [r[0] for r in cur.fetchall()]
    assert found_nice == nice_ids, f"Nice list mismatch: {found_nice}"
    print(f"Nice list: {found_nice} ✓")

    # Get all tours with content
    cur.execute("""
        SELECT id, tour_content, request_string, tour_name
        FROM audio_tours
        WHERE tour_content IS NOT NULL AND tour_content != ''
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"Tours with content: {len(rows)}")

    # Measure R10 per tour
    by_type = defaultdict(lambda: {
        'tours': 0, 'sentences_total': 0, 'r10_fires': 0,
        'r9_fires': 0, 'r10_paras_emptied': 0, 'tours_over_third': []
    })
    all_results = []

    for tour_id, tour_content, request_string, tour_name in rows:
        tour_type = detect_tour_type(request_string or '', tour_name or '')
        descriptions = parse_stop_descriptions(tour_content)

        tour_total_sentences = 0
        tour_r10_deleted = 0
        tour_r9_deleted = 0
        tour_r10_paras = 0
        tour_r9_paras = 0

        for desc in descriptions:
            if not desc.strip():
                continue

            # Count total sentences
            for para in desc.split('\n\n'):
                if para.strip():
                    sents = _split_sentences(para.strip())
                    tour_total_sentences += len([s for s in sents if len(s) >= 15])

            # Apply R10
            _, r10_del, r10_emp = apply_r10_to_description(desc)
            tour_r10_deleted += r10_del
            tour_r10_paras += r10_emp

            # Apply R9
            _, r9_del, r9_emp = apply_r9_to_description(desc)
            tour_r9_deleted += r9_del
            tour_r9_paras += r9_emp

        # Check if combined deletion exceeds 1/3
        combined_deleted = tour_r10_deleted + tour_r9_deleted
        fraction = combined_deleted / max(tour_total_sentences, 1)

        record = {
            'tour_id': tour_id,
            'tour_type': tour_type,
            'total_sentences': tour_total_sentences,
            'r10_deleted': tour_r10_deleted,
            'r9_deleted': tour_r9_deleted,
            'combined_deleted': combined_deleted,
            'fraction_deleted': round(fraction, 3),
            'r10_paras_emptied': tour_r10_paras,
            'r9_paras_emptied': tour_r9_paras,
            'over_third': fraction > 0.333,
        }
        all_results.append(record)

        stats = by_type[tour_type]
        stats['tours'] += 1
        stats['sentences_total'] += tour_total_sentences
        stats['r10_fires'] += tour_r10_deleted
        stats['r9_fires'] += tour_r9_deleted
        stats['r10_paras_emptied'] += tour_r10_paras
        if fraction > 0.333:
            stats['tours_over_third'].append(tour_id)

    cur.close()
    conn.close()

    # ── Report by tour type ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("R10 RATE BY TOUR TYPE")
    print("─" * 70)
    print(f"{'Type':<12} {'Tours':<7} {'Sentences':<11} {'R10 del':<9} {'R10 rate':<10} "
          f"{'R9 del':<8} {'Combined':<10} {'> 1/3'}")
    print("-" * 70)

    total_sents = 0
    total_r10 = 0
    total_r9 = 0
    total_over = 0

    for ttype in sorted(by_type.keys()):
        s = by_type[ttype]
        r10_rate = s['r10_fires'] / max(s['sentences_total'], 1)
        combined_rate = (s['r10_fires'] + s['r9_fires']) / max(s['sentences_total'], 1)
        over_count = len(s['tours_over_third'])
        print(f"{ttype:<12} {s['tours']:<7} {s['sentences_total']:<11} "
              f"{s['r10_fires']:<9} {r10_rate:.1%}{'':>4} "
              f"{s['r9_fires']:<8} {combined_rate:.1%}{'':>4} "
              f"{over_count}")
        total_sents += s['sentences_total']
        total_r10 += s['r10_fires']
        total_r9 += s['r9_fires']
        total_over += over_count

    print("-" * 70)
    overall_r10_rate = total_r10 / max(total_sents, 1)
    combined_rate = (total_r10 + total_r9) / max(total_sents, 1)
    print(f"{'TOTAL':<12} {len(rows):<7} {total_sents:<11} "
          f"{total_r10:<9} {overall_r10_rate:.1%}{'':>4} "
          f"{total_r9:<8} {combined_rate:.1%}{'':>4} "
          f"{total_over}")

    # ── Tours over 1/3 combined deletion ─────────────────────────────────────
    over_third_tours = [r for r in all_results if r['over_third']]
    print(f"\n{'─' * 70}")
    print(f"TOURS EXCEEDING 1/3 COMBINED DELETION (R9 + R10): {len(over_third_tours)}")
    print(f"{'─' * 70}")
    if over_third_tours:
        for r in sorted(over_third_tours, key=lambda x: -x['fraction_deleted']):
            print(f"  Tour {r['tour_id']:>4} ({r['tour_type']:<8}): "
                  f"{r['combined_deleted']}/{r['total_sentences']} sentences = "
                  f"{r['fraction_deleted']:.0%}")
    else:
        print("  None.")

    # ── Paragraphs emptied ───────────────────────────────────────────────────
    total_r10_paras = sum(r['r10_paras_emptied'] for r in all_results)
    total_r9_paras = sum(r['r9_paras_emptied'] for r in all_results)
    print(f"\nParagraphs emptied: R10={total_r10_paras}, R9={total_r9_paras}, "
          f"combined={total_r10_paras + total_r9_paras}")

    # ── Calibration ──────────────────────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("CALIBRATION vs Michael's 11 marks (QUALITY_PROFILE.md §5)")
    print(f"{'─' * 70}")
    cal = run_calibration()
    print(f"  M8 ('whispers tales of a bygone era'): R10 fires = {cal['M8_R10_fires']}")
    print(f"  M4 ('envisioning the hidden coves and stories'): R10 fires = {cal['M4_R10_fires']}")
    print(f"  Original:  {cal['original']['agree']} agree · "
          f"{cal['original']['partial']} partial · "
          f"{cal['original']['disagree']} disagree")
    print(f"  With R10:  {cal['with_r10']['agree']} agree · "
          f"{cal['with_r10']['partial']} partial · "
          f"{cal['with_r10']['disagree']} disagree")

    # ── Verify audio_tours unchanged ─────────────────────────────────────────
    conn2 = get_connection()
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) FROM audio_tours")
    final_rows = cur2.fetchone()[0]
    cur2.execute("SELECT id FROM audio_tours WHERE id = ANY(%s) ORDER BY id", (nice_ids,))
    final_nice = [r[0] for r in cur2.fetchall()]
    cur2.close()
    conn2.close()

    print(f"\naudio_tours: {final_rows} (expected {total_rows})")
    print(f"Nice list: {final_nice}")
    assert final_rows == total_rows, f"ROW COUNT CHANGED: {total_rows} → {final_rows}"
    assert final_nice == nice_ids, f"Nice list CHANGED: {final_nice}"
    print("✓ audio_tours unchanged, Nice list intact")

    # ── Save JSON ────────────────────────────────────────────────────────────
    output = {
        'total_rows': total_rows,
        'tours_measured': len(rows),
        'by_type': {k: {kk: vv for kk, vv in v.items()} for k, v in by_type.items()},
        'overall_r10_rate': round(overall_r10_rate, 4),
        'overall_combined_rate': round(combined_rate, 4),
        'tours_over_third': [r['tour_id'] for r in over_third_tours],
        'calibration': cal,
        'per_tour': all_results,
    }
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'r10_measurement_output.json')
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON: {json_path}")
    print("\n=== DONE ===")
    return output


if __name__ == '__main__':
    main()
