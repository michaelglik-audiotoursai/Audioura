#!/usr/bin/env python3
"""run_quality_profile.py — LOCAL-231: Corpus quality profile.

Scores every stored tour with tour_content using the existing instruments
at every level of §7's profile: sentence group → paragraph → stop → tour.

READ-ONLY. No generation, no writes to audio_tours, no detector changes.
"""
import json
import os
import sys
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_validator_detector import (
    check_r1_imperatives,
    check_r2_questions,
    check_r3_suggestive_exploration,
    check_r4_prescribed_feeling,
    check_r7_hallucinated_sensory,
    check_r8_prompt_leakage,
    check_r9_generic,
    _is_style_navigation_sentence,
    _split_sentences,
)
from sentence_group_scorer import (
    split_into_sentence_groups,
    classify_group,
    score_group,
    score_paragraph_groups,
)
from claim_check import check_paragraph as check_claims
from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR TYPE DETECTION (from request_string — museum/walking/cycling/other)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_tour_type_category(request_string: str, tour_name: str) -> str:
    """Classify tour as museum, walking, cycling, or other."""
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
# PARSE TOUR STOPS (from stop_anchor_detector_v2)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_tour_stops(tour_content: str) -> List[Dict]:
    """Parse tour_content text into structured stops with paragraphs."""
    if not tour_content:
        return []

    has_stop_markers = bool(re.search(r'Stop \d+:', tour_content))

    if has_stop_markers:
        parts = re.split(r'\nStop \d+:\s*', tour_content)
        if not parts[0].strip() or 'Tour-Category' in parts[0]:
            parts = parts[1:]
        else:
            if re.match(r'Stop \d+:', tour_content):
                parts = re.split(r'Stop \d+:\s*', tour_content)[1:]
            else:
                parts = parts[1:]
    else:
        parts = re.split(r'\n(?=[^\n]+\n\nAddress:)', tour_content)
        if parts and ('Address:' not in parts[0][:200]):
            parts = parts[1:]

    stops = []
    for part in parts:
        lines = part.strip().split('\n')
        if not lines:
            continue
        title = lines[0].strip().rstrip(':').strip()
        if not title or 'Tour-Category' in title or 'Step-by-Step' in title:
            continue

        paragraphs = []
        metadata_patterns = [
            r'^Address:', r'^Coordinates:', r'^Type/Specialty:',
            r'^Specific Examples:', r'^Museum Information:',
            r'^Directions?:', r'^\s*$',
        ]
        current_para = []
        in_directions = False

        for line in lines[1:]:
            line_stripped = line.strip()
            if not line_stripped:
                if current_para:
                    para_text = ' '.join(current_para).strip()
                    if len(para_text) > 50:
                        paragraphs.append(para_text)
                    current_para = []
                in_directions = False
                continue

            is_metadata = False
            for pat in metadata_patterns:
                if re.match(pat, line_stripped, re.IGNORECASE):
                    is_metadata = True
                    if 'direction' in pat.lower():
                        in_directions = True
                    break

            if is_metadata or in_directions:
                if current_para:
                    para_text = ' '.join(current_para).strip()
                    if len(para_text) > 50:
                        paragraphs.append(para_text)
                    current_para = []
                continue

            if line_stripped.startswith('Orientation:'):
                content_after = line_stripped[len('Orientation:'):].strip()
                if content_after.startswith('Orientation:'):
                    content_after = content_after[len('Orientation:'):].strip()
                if content_after:
                    current_para.append(content_after)
            elif line_stripped.startswith('Description:'):
                content_after = line_stripped[len('Description:'):].strip()
                if content_after:
                    current_para.append(content_after)
            else:
                current_para.append(line_stripped)

        if current_para:
            para_text = ' '.join(current_para).strip()
            if len(para_text) > 50:
                paragraphs.append(para_text)

        if paragraphs:
            stops.append({
                'title': title,
                'paragraphs': paragraphs,
            })

    return stops


# ═══════════════════════════════════════════════════════════════════════════════
# PER-SENTENCE STYLE SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def score_sentence_style(sentence: str) -> Dict:
    """Run style rules on a single sentence. Returns rule violations."""
    if len(sentence) < 10:
        return {'rules': [], 'findings': []}
    if _is_style_navigation_sentence(sentence):
        return {'rules': [], 'findings': [], 'nav_exempt': True}

    findings = []
    findings.extend(check_r1_imperatives(sentence))
    findings.extend(check_r3_suggestive_exploration(sentence))
    findings.extend(check_r4_prescribed_feeling(sentence))
    findings.extend(check_r7_hallucinated_sensory(sentence))
    findings.extend(check_r8_prompt_leakage(sentence))
    findings.extend(check_r9_generic(sentence))

    rules = sorted(set(f.get('rule_id', f.get('rule', '')) for f in findings))
    return {'rules': rules, 'findings': findings}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PROFILING
# ═══════════════════════════════════════════════════════════════════════════════

def profile_tour(tour_id, tour_name, tour_content, request_string, is_test, conn):
    """Profile a single tour. Returns a comprehensive record."""
    stops = parse_tour_stops(tour_content)
    if not stops:
        return None

    tour_type = detect_tour_type_category(request_string, tour_name)

    # Get stop corpus
    stop_names = [s['title'] for s in stops]
    venue_name = tour_name.split(' - ')[0].strip() if ' - ' in tour_name else tour_name

    try:
        stop_corpus = get_stop_corpus_for_tour(venue_name, stop_names, conn)
    except Exception:
        stop_corpus = {name: None for name in stop_names}

    # Per-stop profiling
    stop_records = []
    all_group_records = []

    for stop in stops:
        stop_title = stop['title']
        paragraphs = stop['paragraphs']

        # Corpus coverage
        corpus_data = stop_corpus.get(stop_title)
        passages = []
        if corpus_data and isinstance(corpus_data, dict):
            passages = corpus_data.get('passages', [])

        coverage = assess_stop_coverage(stop_title, venue_name, passages)
        coverage_verdict = coverage['verdict']

        # Per-paragraph, per-group scoring
        para_records = []
        stop_group_records = []

        for para_idx, para_text in enumerate(paragraphs):
            groups = split_into_sentence_groups(para_text)
            para_group_records = []

            for group_sentences in groups:
                group_text = ' '.join(group_sentences)
                classification = classify_group(group_sentences)

                # Style check per sentence
                group_style_rules = set()
                r9_deletable = False
                for sent in group_sentences:
                    sv = score_sentence_style(sent)
                    for r in sv.get('rules', []):
                        group_style_rules.add(r)
                    if 'R9_GENERIC' in sv.get('rules', []):
                        r9_deletable = True

                # Claim check (only for CONTENT groups with passages)
                unsupported_count = 0
                contradicted_count = 0
                supported_count = 0
                claims_total = 0
                if classification == 'CONTENT':
                    try:
                        claim_result = check_claims(
                            group_text,
                            stop_title=stop_title,
                            venue_name=venue_name,
                            passages=passages if passages else [],
                        )
                        vc = claim_result.get('verdict_counts', {})
                        unsupported_count = vc.get('unsupported', 0)
                        contradicted_count = vc.get('contradicted', 0)
                        supported_count = (vc.get('supported', 0) +
                                          vc.get('supported_paraphrase', 0) +
                                          vc.get('supported_elsewhere', 0))
                        claims_total = sum(vc.values())
                    except Exception:
                        pass

                group_record = {
                    'sentences': group_sentences,
                    'classification': classification,
                    'style_rules_violated': sorted(group_style_rules),
                    'r9_deletable': r9_deletable,
                    'unsupported_claims': unsupported_count,
                    'contradicted_claims': contradicted_count,
                    'supported_claims': supported_count,
                    'total_claims': claims_total,
                    'has_corpus': len(passages) > 0,
                }
                para_group_records.append(group_record)
                stop_group_records.append(group_record)
                all_group_records.append(group_record)

            para_records.append({
                'text': para_text[:200],
                'groups': para_group_records,
            })

        # Stop-level aggregates
        stop_style_rules = set()
        stop_r9_count = 0
        stop_unsupported = 0
        stop_contradicted = 0
        stop_group_count = len(stop_group_records)

        for gr in stop_group_records:
            for r in gr['style_rules_violated']:
                stop_style_rules.add(r)
            if gr['r9_deletable']:
                stop_r9_count += 1
            stop_unsupported += gr['unsupported_claims']
            stop_contradicted += gr['contradicted_claims']

        stop_records.append({
            'title': stop_title,
            'coverage_verdict': coverage_verdict,
            'passage_count': coverage['passage_count'],
            'paragraph_count': len(paragraphs),
            'group_count': stop_group_count,
            'style_rules_violated': sorted(stop_style_rules),
            'r9_deletable_groups': stop_r9_count,
            'unsupported_claims': stop_unsupported,
            'contradicted_claims': stop_contradicted,
            'para_records': para_records,
        })

    # Tour-level aggregates
    tour_style_rules = set()
    tour_r9_count = 0
    tour_unsupported = 0
    tour_contradicted = 0
    tour_group_count = len(all_group_records)

    coverage_summary = defaultdict(int)
    for sr in stop_records:
        coverage_summary[sr['coverage_verdict']] += 1
        for r in sr['style_rules_violated']:
            tour_style_rules.add(r)
        tour_r9_count += sr['r9_deletable_groups']
        tour_unsupported += sr['unsupported_claims']
        tour_contradicted += sr['contradicted_claims']

    # Per-rule rates across all groups
    rule_rates = {}
    for rule in ['R1_IMPERATIVE', 'R3_SUGGESTIVE', 'R4_FEELING',
                 'R7_HALLUCINATED_SENSORY', 'R8_PROMPT_LEAKAGE', 'R9_GENERIC']:
        count = sum(1 for gr in all_group_records if rule in gr['style_rules_violated'])
        rule_rates[rule] = count / tour_group_count if tour_group_count > 0 else 0

    # Worst sentence (R9 or most rules violated)
    worst_sentence = None
    worst_sentence_rules = 0
    for gr in all_group_records:
        for sent in gr['sentences']:
            sv = score_sentence_style(sent)
            n_rules = len(sv.get('rules', []))
            if n_rules > worst_sentence_rules:
                worst_sentence_rules = n_rules
                worst_sentence = sent[:150]

    return {
        'tour_id': tour_id,
        'tour_name': tour_name,
        'tour_type': tour_type,
        'is_test': bool(is_test),
        'stop_count': len(stop_records),
        'group_count': tour_group_count,
        'coverage_summary': dict(coverage_summary),
        'style_rules_violated': sorted(tour_style_rules),
        'rule_rates': rule_rates,
        'r9_deletable_groups': tour_r9_count,
        'unsupported_claims_total': tour_unsupported,
        'contradicted_claims_total': tour_contradicted,
        'worst_sentence': worst_sentence,
        'worst_sentence_rules': worst_sentence_rules,
        'stops': stop_records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MICHAEL'S CALIBRATION (tour 163)
# ═══════════════════════════════════════════════════════════════════════════════

MICHAEL_SCORES = [5, 1, 3, 3, 2, 1, 1, 5, 1, 0, 0]


def calibrate_against_michael(tour_record):
    """Compare machine analysis against Michael's 11 sentence group scores."""
    if not tour_record:
        return None

    # Flatten all groups from all stops
    all_groups = []
    for stop in tour_record['stops']:
        for para in stop['para_records']:
            for gr in para['groups']:
                all_groups.append(gr)

    # Michael scored 11 groups — we compare what we can
    calibration = []
    for i, group in enumerate(all_groups[:len(MICHAEL_SCORES)]):
        michael_score = MICHAEL_SCORES[i] if i < len(MICHAEL_SCORES) else None
        machine_data = {
            'group_index': i,
            'michael_score': michael_score,
            'classification': group['classification'],
            'style_rules': group['style_rules_violated'],
            'r9_deletable': group['r9_deletable'],
            'unsupported': group['unsupported_claims'],
            'contradicted': group['contradicted_claims'],
            'has_corpus': group['has_corpus'],
            'text_preview': ' '.join(group['sentences'])[:120],
        }
        # Can we identify the machine would flag this?
        machine_data['would_block'] = (
            group['r9_deletable'] or group['contradicted_claims'] > 0
        )
        machine_data['has_style_error'] = len(group['style_rules_violated']) > 0
        calibration.append(machine_data)

    return calibration


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    conn = get_connection()

    # Verify row count first
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_rows = cur.fetchone()[0]
    print(f"audio_tours row count: {total_rows}")

    # Fetch all tours with tour_content
    cur.execute("""
        SELECT id, tour_name, tour_content, request_string, is_test
        FROM audio_tours
        WHERE tour_content IS NOT NULL AND tour_content != ''
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    print(f"Tours with tour_content: {len(rows)}")

    # Profile each tour
    results = []
    for i, (tour_id, tour_name, tour_content, request_string, is_test) in enumerate(rows):
        print(f"  [{i+1}/{len(rows)}] Tour {tour_id}: {tour_name[:50]}...", end='')
        try:
            record = profile_tour(tour_id, tour_name, tour_content, request_string, is_test, conn)
            if record:
                results.append(record)
                print(f" ✓ ({record['group_count']} groups, {record['stop_count']} stops)")
            else:
                print(" (no parseable stops)")
        except Exception as e:
            print(f" ERROR: {e}")

    # Calibrate against Michael's marks (tour 163)
    tour_163 = next((r for r in results if r['tour_id'] == 163), None)
    calibration = calibrate_against_michael(tour_163) if tour_163 else None

    # Save raw JSON
    output = {
        'total_audio_tours_rows': total_rows,
        'tours_with_content': len(rows),
        'tours_profiled': len(results),
        'per_tour': results,
        'calibration_tour_163': calibration,
    }

    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quality_profile_data.json')
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON saved: {json_path}")

    # Verify row count unchanged
    cur2 = conn.cursor()
    cur2.execute("SELECT COUNT(*) FROM audio_tours")
    final_rows = cur2.fetchone()[0]
    cur2.close()
    conn.close()

    print(f"audio_tours row count after: {final_rows}")
    assert final_rows == total_rows, f"ROW COUNT CHANGED: {total_rows} → {final_rows}"

    # Verify Nice list unchanged
    conn2 = get_connection()
    cur3 = conn2.cursor()
    nice_ids = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
    cur3.execute("SELECT id FROM audio_tours WHERE id = ANY(%s) ORDER BY id", (nice_ids,))
    found_ids = [r[0] for r in cur3.fetchall()]
    cur3.close()
    conn2.close()
    print(f"Nice list check: {found_ids}")
    assert found_ids == nice_ids, f"Nice list changed! Expected {nice_ids}, got {found_ids}"

    print("\n=== DONE ===")
    return output


if __name__ == '__main__':
    main()
