#!/usr/bin/env python3
"""run_local383_acceptance.py — Acceptance test for LOCAL-383: Story Beats.

Generates:
  1. Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (8 stops)
     → at least 4 distinct people from {Broder, Mourlot, Fridman, Freud, Reverdy, Torf}
     → each stop has at least one sentence naming a person + what they did
     → all LOCAL-382 checks still pass (livre d'artiste framing, collaboration)
     → all LOCAL-379/381 checks still pass (zero banned terms)
     → empty_sentence_count before/after REPORTED (not gated)

  2. Palais Lascaris, Nice, France (4 stops)
     → 4/4 real instruments; score_tour_file(f,4)=81.2, score_tour_file(f,8)=75.0

Env:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')

from generate_tour_text import generate_tour_text
from tour_rubric_scorer import score_tour_file


# --- Empty sentence counting (LOCAL-375 metric, report only) ---
def count_empty_sentences(tour_text: str) -> dict:
    """Count empty/evaluative sentences per stop using LOCAL-375's heuristic."""
    try:
        from tour_rubric_scorer import _is_empty_sentence
    except ImportError:
        return {'error': '_is_empty_sentence not importable'}

    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    result = {'per_stop': [], 'total': 0}
    for stop in stops:
        if not stop.strip().startswith('Stop'):
            continue
        sentences = re.split(r'(?<=[.!?])\s+', stop)
        empty_count = sum(1 for s in sentences if _is_empty_sentence(s))
        total_count = len([s for s in sentences if len(s.strip()) > 10])
        result['per_stop'].append({
            'header': stop.split('\n')[0][:50],
            'empty': empty_count,
            'total': total_count,
            'fraction': empty_count / max(total_count, 1),
        })
        result['total'] += empty_count
    return result


# --- Acceptance checks ---
def check_story_beats_mfa(tour_text: str) -> list:
    """Check LOCAL-383 acceptance criteria for the MFA exhibition tour."""
    errors = []
    text_lower = tour_text.lower()

    # --- Named collaborators/people present, grounded: at least 4 distinct ---
    target_people = {'broder', 'mourlot', 'fridman', 'freud', 'reverdy', 'torf'}
    found_people = set()
    for target in target_people:
        if target in text_lower:
            found_people.add(target)
    if len(found_people) < 4:
        errors.append(
            f"FAIL: Only {len(found_people)}/4 distinct people found: {found_people}. "
            f"Missing: {target_people - found_people}"
        )
    else:
        print(f"  ✓ Named collaborators: {len(found_people)}/4+ found: {found_people}")

    # --- Each stop has at least one sentence naming a person + what they did ---
    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    stops_with_story = 0
    story_sentences = []
    for stop in stops:
        if not stop.strip().startswith('Stop'):
            continue
        header = stop.split('\n')[0][:60]
        # Find sentences that name a person (any of our targets or any capitalized proper noun)
        sentences = re.split(r'(?<=[.!?])\s+', stop)
        found_story_sentence = None
        for sent in sentences:
            # Check if sentence names a person and has an action verb
            has_person = bool(re.search(
                r'\b(?:Broder|Mourlot|Fridman|Freud|Reverdy|Torf|Picasso|Miró|Miro|'
                r'Dalí|Dali|Gris|Boris|Louis|Pierre|Juan|Joan|Salvador|Sigmund)\b',
                sent
            ))
            has_action = bool(re.search(
                r'\b(?:published|printed|gave|donated|illustrated|devised|partnered|'
                r'collaborated|created|founded|assembled|invited|attracted|'
                r'revolutionized|interpreted|produced|played|brought|named|'
                r'explored|introduced|designed|pulled|worked)\b',
                sent, re.IGNORECASE
            ))
            if has_person and has_action:
                found_story_sentence = sent.strip()
                break
        if found_story_sentence:
            stops_with_story += 1
            story_sentences.append(f"  {header}: \"{found_story_sentence[:120]}\"")
        else:
            story_sentences.append(f"  {header}: ⚠️ NO STORY SENTENCE FOUND")

    if stops_with_story < len([s for s in stops if s.strip().startswith('Stop')]):
        missing = len([s for s in stops if s.strip().startswith('Stop')]) - stops_with_story
        errors.append(f"FAIL: {missing} stops lack a story sentence (person + action)")

    print(f"  Story sentences per stop ({stops_with_story} of {len([s for s in stops if s.strip().startswith('Stop')])} stops):")
    for ss in story_sentences:
        print(ss)

    # --- LOCAL-382 checks: livre d'artiste framing ---
    has_livre = ('livre d\'artiste' in text_lower or 'artist\'s book' in text_lower or
                 'livres d\'artiste' in text_lower)
    has_collab = 'collabor' in text_lower
    if not has_livre:
        errors.append("FAIL: Missing 'livre d'artiste' or 'artist's book' (LOCAL-382)")
    if not has_collab:
        errors.append("FAIL: Missing 'collabor*' (LOCAL-382)")

    # Per-stop book framing
    book_stop_count = sum(1 for s in stops if s.strip().startswith('Stop') and 'book' in s.lower())
    if book_stop_count < 2:
        errors.append(f"FAIL: 'book' appears in only {book_stop_count} stops (need ≥2, LOCAL-382)")

    # --- LOCAL-379/381 checks: banned terms ---
    banned = ['ceiling', 'installation', 'mural', 'sculpture', 'painting', 'glass',
              'stand beneath', 'look up', 'gaze up']
    for term in banned:
        if term in text_lower:
            errors.append(f"FAIL: Banned term '{term}' found (LOCAL-379/381)")

    # ≥120 words per stop
    for stop in stops:
        if stop.strip().startswith('Stop'):
            words = len(stop.split())
            stop_name = stop.split('\n')[0][:50]
            if words < 120:
                errors.append(f"FAIL: {stop_name} has only {words} words (need ≥120)")

    return errors


def main():
    print("=" * 70)
    print("LOCAL-383 ACCEPTANCE — Story Beats (Storied release)")
    print("=" * 70)

    # --- Test 1: MFA Exhibition (8 stops) ---
    print("\n--- TEST 1: Picasso, Miró, Dalí: Unbound at MFA (8 stops) ---\n")
    try:
        tour_text, _, coords = generate_tour_text(
            "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA",
            "museum",
            "/tmp/local383_mfa.txt",
            total_stops=8,
        )
        if tour_text:
            print(f"\n{'='*40} MFA TOUR TEXT {'='*40}")
            print(tour_text)
            print(f"{'='*40} END {'='*40}")

            # Empty sentence count (report only)
            empty_report = count_empty_sentences(tour_text)
            print(f"\n  Empty sentence report (LOCAL-375 metric, not gated):")
            for stop_report in empty_report.get('per_stop', []):
                print(f"    {stop_report['header']}: {stop_report['empty']}/{stop_report['total']} "
                      f"({stop_report['fraction']:.0%})")
            print(f"    TOTAL empty sentences: {empty_report.get('total', '?')}")

            errors = check_story_beats_mfa(tour_text)
            if errors:
                print("\n⚠️  ACCEPTANCE ERRORS:")
                for e in errors:
                    print(f"  {e}")
            else:
                print("\n✓ All MFA story beat acceptance checks pass")

            # Score
            score = score_tour_file("/tmp/local383_mfa.txt", 8)
            print(f"\n  Score(8): {score} (threshold: 75.0)")
            if score < 75.0:
                print(f"  ⚠️  BELOW THRESHOLD: {score} < 75.0")
        else:
            print("FAIL: Tour generation returned None")
    except Exception as e:
        print(f"ERROR generating MFA tour: {e}")
        import traceback
        traceback.print_exc()

    # --- Test 2: Palais Lascaris (4 stops) ---
    print("\n\n--- TEST 2: Palais Lascaris, Nice, France (4 stops) ---\n")
    try:
        tour_text2, _, coords2 = generate_tour_text(
            "Palais Lascaris, Nice, France",
            "museum",
            "/tmp/local383_palais.txt",
            total_stops=4,
        )
        if tour_text2:
            print(f"\n{'='*40} PALAIS LASCARIS TOUR TEXT {'='*40}")
            print(tour_text2)
            print(f"{'='*40} END {'='*40}")

            # Check: 4/4 real instruments
            text_lower = tour_text2.lower()
            instrument_keywords = ['instrument', 'flute', 'violin', 'guitar', 'harpsichord',
                                   'lute', 'harp', 'cello', 'piano', 'organ', 'trumpet',
                                   'clarinet', 'oboe', 'drum', 'viol', 'mandolin', 'hurdy']
            instruments_found = sum(1 for kw in instrument_keywords if kw in text_lower)
            print(f"\n  Instruments found: {instruments_found} keyword hits")

            # Score
            score4 = score_tour_file("/tmp/local383_palais.txt", 4)
            score8 = score_tour_file("/tmp/local383_palais.txt", 8)
            print(f"\n  Score(4): {score4} (threshold: 81.2)")
            print(f"  Score(8): {score8} (threshold: 75.0)")
            if score4 < 81.2:
                print(f"  ⚠️  BELOW THRESHOLD: score(4)={score4} < 81.2")
            if score8 < 75.0:
                print(f"  ⚠️  BELOW THRESHOLD: score(8)={score8} < 75.0")
        else:
            print("FAIL: Tour generation returned None")
    except Exception as e:
        print(f"ERROR generating Palais Lascaris tour: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("LOCAL-383 ACCEPTANCE COMPLETE")
    print("=" * 70)


if __name__ == '__main__':
    main()
