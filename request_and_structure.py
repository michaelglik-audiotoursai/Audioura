#!/usr/bin/env python3
"""request_and_structure.py — Routine 1 (Request_to_AI) and Routine 2 (Structure_AI_output).

LOCAL-462: Michael's two coupled routines for interrogating an AI about a stop.

Routine 1 reads the interrogation matrix and builds the question.
Routine 2 takes the AI's answer and forces it to Michael's shape (3-5 sentences).

    python3 request_and_structure.py --text-file TOUR_MFA_20260812_2030.txt --stop 2
"""
import os
import re
import sys
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from interrogation_matrix import build_matrix, extract_stops, extract_tour_header, infer_tour_type, SLOTS  # noqa: E402
from story_opportunity_scan import measure, _fold, split_sentences  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# CREDIT-LINE CANDIDATES — the ordered list Routine 2 iterates through
# ═══════════════════════════════════════════════════════════════════════════════

# Same filtering constants as interrogation_matrix._pick_credit_line
_NOT_CREDIT_PREFIXES = frozenset({
    'the', 'at', 'in', 'on', 'le', 'la', 'les',
    'a', 'an', 'au', 'du', 'des', 'un', 'une',
})
_PLACE_WORDS_CL = frozenset({
    'museum', 'library', 'park', 'square', 'street', 'church', 'chapel',
    'house', 'ave', 'boston', 'arts', 'fine', 'avenue', 'st', 'rd', 'ln',
    'blvd', 'mountain', 'lake', 'bay', 'building',
})
_VENUE_SUFFIXES = (
    'gallery', 'museum', 'room', 'hall', 'center', 'centre', 'farmhouse',
    'house', 'building', 'st', 'ave', 'rd', 'street', 'avenue', 'blvd',
    'ln', 'square',
)


def _credit_line_candidates(stop_text: str, exclude_values: List[str] = None) -> List[str]:
    """Return the ordered list of credit_line candidates from story_opportunity_scan.

    Priority order: FLAT → MENTIONED → DANGLING, never DEVELOPED.
    Within each tier: proper noun > title > loaded noun; then by sentence count.

    This is the same logic as interrogation_matrix._pick_credit_line but returns
    ALL candidates in order, not just the first. Routine 2 needs the cursor.
    """
    exclude_folded = set(_fold(v) for v in (exclude_values or []) if v)

    m = measure(stop_text)
    handles = m.get('handles', [])

    by_state: Dict[str, List] = {'FLAT': [], 'MENTIONED': [], 'DANGLING': []}
    for h in handles:
        state = h.get('state', '')
        if state not in by_state:
            continue
        if '\n' in h['surface']:
            continue
        hf = _fold(h['surface'])
        if any(hf in ex or ex in hf for ex in exclude_folded if ex):
            continue
        first_word = hf.split()[0] if hf.split() else ''
        if first_word in _NOT_CREDIT_PREFIXES:
            continue
        handle_words = set(hf.split())
        non_place_words = handle_words - _PLACE_WORDS_CL
        if not non_place_words:
            continue
        last_word = hf.split()[-1] if hf.split() else ''
        if last_word in _VENUE_SUFFIXES:
            continue
        by_state[state].append(h)

    def handle_score(h):
        kind_rank = {'proper noun': 3, 'title': 2, 'loaded noun': 1}.get(h['kind'], 0)
        return (kind_rank, h.get('sentences', 0))

    ordered: List[str] = []
    for state in ('FLAT', 'MENTIONED', 'DANGLING'):
        candidates = by_state[state]
        candidates.sort(key=handle_score, reverse=True)
        for c in candidates:
            ordered.append(c['surface'])

    return ordered


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTINE 1 — Request_to_AI
# ═══════════════════════════════════════════════════════════════════════════════

def request_to_ai(matrix: Dict[str, Dict]) -> Dict:
    """Build the AI question from the interrogation matrix.

    Michael's template:
        "What story can be told to visitors of [medium] + [venue] : regarding
         [canonical_title] or [english_title] about [credit_line] in connection
         with [artist] and [publisher] and [printed_by]?"

    Rules:
    - ABSENT slots drop out cleanly — no "and None", "and —", or dangling "and".
    - When english_title == canonical_title, do not write it twice.
    - Return unverified_terms: every value whose matrix status is CLAIMED.
    - Deterministic. No network.
    """
    def val(slot: str) -> str:
        """Get the value for a slot, or empty string if ABSENT."""
        cell = matrix.get(slot, {})
        if cell.get('status') == 'ABSENT' or not cell.get('value'):
            return ''
        return cell['value']

    medium = val('medium')
    venue = val('venue')
    canonical_title = val('canonical_title')
    english_title = val('english_title')
    credit_line = val('credit_line')
    artist = val('artist')
    publisher = val('publisher')
    printed_by = val('printed_by')

    # Build "of [medium] + [venue]" segment — omit missing, no dangling "+"
    of_parts = []
    if medium:
        of_parts.append(medium)
    if venue:
        of_parts.append(venue)
    of_segment = ' + '.join(of_parts) if of_parts else ''

    # Build "regarding [canonical_title] or [english_title]" — deduplicate
    regarding_parts = []
    if canonical_title:
        regarding_parts.append(canonical_title)
    if english_title and english_title != canonical_title:
        regarding_parts.append(english_title)
    regarding_segment = ' or '.join(regarding_parts) if regarding_parts else ''

    # Build "about [credit_line]"
    about_segment = credit_line if credit_line else ''

    # Build "in connection with [artist] and [publisher] and [printed_by]"
    connection_parts = []
    if artist:
        connection_parts.append(artist)
    if publisher:
        connection_parts.append(publisher)
    if printed_by:
        connection_parts.append(printed_by)
    connection_segment = ' and '.join(connection_parts) if connection_parts else ''

    # Assemble the sentence
    parts = ['What story can be told to visitors']
    if of_segment:
        parts.append(f'of {of_segment}')
    if regarding_segment:
        parts.append(f': regarding {regarding_segment}')
    if about_segment:
        parts.append(f'about {about_segment}')
    if connection_segment:
        parts.append(f'in connection with {connection_segment}')

    # Join with spaces, append ? directly (no space before it)
    request = ' '.join(parts) + '?'
    # Clean double spaces
    request = re.sub(r'\s+', ' ', request).strip()

    # Collect unverified terms (CLAIMED status)
    unverified_terms = []
    for slot in SLOTS:
        cell = matrix.get(slot, {})
        if cell.get('status') == 'CLAIMED' and cell.get('value'):
            unverified_terms.append(cell['value'])

    # Collect omitted slots (ABSENT)
    omitted_slots = []
    for slot in SLOTS:
        cell = matrix.get(slot, {})
        if cell.get('status') == 'ABSENT' or not cell.get('value'):
            omitted_slots.append(slot)

    return {
        'request': request,
        'unverified_terms': unverified_terms,
        'omitted_slots': omitted_slots,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTINE 2 — Structure_AI_output
# ═══════════════════════════════════════════════════════════════════════════════

def structure_ai_output(
    answer: str,
    matrix: Dict[str, Dict],
    ask: Callable[[str], str],
    max_retries: int = 3,
    *,
    _stop_text: str = '',
    _tour_context: str = '',
) -> Dict:
    """Take the AI's answer and force it to Michael's shape.

    Rules:
    - Count sentences.
    - More than 5 → ask the AI: "Summarize the following into 3 sentences: " + answer
    - Fewer than 3 → substitute credit_line with the next handle from
      story_opportunity_scan in priority order FLAT → MENTIONED → DANGLING,
      rebuild the request with request_to_ai, ask again, re-enter.
    - 3-5 sentences → accept as is.

    Args:
        answer: The AI's raw answer text.
        matrix: The interrogation matrix for the stop.
        ask: An injected callable (prompt) -> str, so tests can use a fake.
        max_retries: Max substitution retries before returning INSUFFICIENT.
        _stop_text: The stop text (needed to get credit_line candidates for substitution).
        _tour_context: Full tour text (needed for matrix rebuild).

    Returns:
        {'status', 'sentences', 'text', 'credit_line_used', 'chain': [...], 'asks': n}
    """
    # Get the full ordered candidate list for credit_line substitution
    exclude_values = [
        matrix.get('canonical_title', {}).get('value', ''),
        matrix.get('english_title', {}).get('value', ''),
        matrix.get('artist', {}).get('value', ''),
        matrix.get('publisher', {}).get('value', ''),
        matrix.get('printed_by', {}).get('value', ''),
        matrix.get('venue', {}).get('value', ''),
        matrix.get('medium', {}).get('value', ''),
    ]
    all_candidates = _credit_line_candidates(_stop_text, exclude_values) if _stop_text else []

    # Current credit_line is the first candidate (already picked by _pick_credit_line)
    current_credit_line = matrix.get('credit_line', {}).get('value', '')
    chain = [current_credit_line] if current_credit_line else []

    # Cursor: find where current credit_line sits in the ordered list
    cursor = 0
    if current_credit_line:
        current_folded = _fold(current_credit_line)
        for i, cand in enumerate(all_candidates):
            if _fold(cand) == current_folded:
                cursor = i + 1  # next one to try
                break
        else:
            cursor = 0  # not found, start from beginning

    asks_count = 0  # How many times we called ask()

    def count_sentences(text: str) -> int:
        return len(split_sentences(text))

    def try_answer(text: str, retries_left: int) -> Dict:
        nonlocal asks_count, chain, cursor

        n = count_sentences(text)

        if n > 5:
            # Too long → ask for a summary
            prompt = f"Summarize the following into 3 sentences: {text}"
            summary = ask(prompt)
            asks_count += 1
            sents = split_sentences(summary)
            return {
                'status': 'OK',
                'sentences': len(sents),
                'text': summary,
                'credit_line_used': chain[-1] if chain else current_credit_line,
                'chain': list(chain),
                'asks': asks_count,
            }

        if n < 3:
            # Too short → substitute credit_line and retry
            if retries_left <= 0:
                return {
                    'status': 'INSUFFICIENT',
                    'sentences': n,
                    'text': text,
                    'credit_line_used': chain[-1] if chain else current_credit_line,
                    'chain': list(chain),
                    'asks': asks_count,
                }

            # Find next credit_line candidate
            if cursor < len(all_candidates):
                next_credit = all_candidates[cursor]
                cursor += 1
            else:
                # No more candidates
                return {
                    'status': 'INSUFFICIENT',
                    'sentences': n,
                    'text': text,
                    'credit_line_used': chain[-1] if chain else current_credit_line,
                    'chain': list(chain),
                    'asks': asks_count,
                }

            chain.append(next_credit)

            # Rebuild matrix with new credit_line
            new_matrix = dict(matrix)
            new_matrix['credit_line'] = {
                'value': next_credit,
                'status': 'DERIVED',
                'source': 'substitution',
                'rung': '',
            }

            # Build new request
            req = request_to_ai(new_matrix)
            new_answer = ask(req['request'])
            asks_count += 1

            return try_answer(new_answer, retries_left - 1)

        # 3-5 sentences → accept
        sents = split_sentences(text)
        return {
            'status': 'OK',
            'sentences': n,
            'text': text,
            'credit_line_used': chain[-1] if chain else current_credit_line,
            'chain': list(chain),
            'asks': asks_count,
        }

    return try_answer(answer, max_retries)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import json

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--text-file', required=True, help='Tour file')
    p.add_argument('--stop', type=int, required=True, help='Stop number')
    p.add_argument('--json', dest='as_json', action='store_true')
    a = p.parse_args()

    full_text = open(a.text_file, encoding='utf-8').read()
    stops = extract_stops(full_text)
    if a.stop not in stops:
        sys.exit(f"Stop {a.stop} not found. Available: {sorted(stops.keys())}")

    tour_type = infer_tour_type(extract_tour_header(full_text), stops[a.stop]['text'])
    matrix = build_matrix(
        stop_text=stops[a.stop]['text'],
        tour_type=tour_type,
        tour_context=full_text,
    )

    result = request_to_ai(matrix)

    if a.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 78}")
        print(f"REQUEST TO AI — stop {a.stop}")
        print(f"{'=' * 78}\n")
        print(f"  {result['request']}")
        if result['unverified_terms']:
            print(f"\n  Unverified (CLAIMED): {result['unverified_terms']}")
        if result['omitted_slots']:
            print(f"  Omitted (ABSENT):    {result['omitted_slots']}")
        print(f"\n{'=' * 78}")


if __name__ == '__main__':
    main()
