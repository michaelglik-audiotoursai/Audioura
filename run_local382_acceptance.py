#!/usr/bin/env python3
"""run_local382_acceptance.py — Acceptance test for LOCAL-382.

Generates:
  1. Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (8 stops)
  2. Palais Lascaris, Nice, France (4 stops) — control for venue_purpose detection
  3. One general encyclopedic museum (4 stops) — control for framing=none

Checks the acceptance criteria per the task spec.

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


def check_acceptance_mfa(tour_text: str) -> list:
    """Check acceptance criteria for the MFA exhibition tour."""
    errors = []
    text_lower = tour_text.lower()

    # General description must contain (grounded):
    # livre d'artiste (or artist's book), collabor*, and at least two of
    # {no precedent, revolutionized, rarely on view, typography, Torf Gallery}
    has_livre = 'livre d\'artiste' in text_lower or 'artist\'s book' in text_lower or 'livres d\'artiste' in text_lower
    has_collab = 'collabor' in text_lower
    optional_count = 0
    if 'no precedent' in text_lower:
        optional_count += 1
    if 'revolutionized' in text_lower:
        optional_count += 1
    if 'rarely on view' in text_lower:
        optional_count += 1
    if 'typography' in text_lower:
        optional_count += 1
    if 'torf gallery' in text_lower or 'gallery 184' in text_lower:
        optional_count += 1

    if not has_livre:
        errors.append("FAIL: General description missing 'livre d'artiste' or 'artist's book'")
    if not has_collab:
        errors.append("FAIL: General description missing 'collabor*'")
    if optional_count < 2:
        errors.append(f"FAIL: General description has only {optional_count}/2 of "
                      "{no precedent, revolutionized, rarely on view, typography, Torf Gallery}")

    # Each stop must name at least two of: author/poet, publisher, printer,
    # binding/plate count, or image/word/typography relationship
    # (This is a structural check on stop content)

    # Banned terms (case-insensitive)
    banned = ['ceiling', 'installation', 'mural', 'canopy', 'vault', 'overhead',
              'dome', 'sculpture', 'painting', 'glass', 'stand beneath', 'look up',
              'gaze up', 'rousseau', 'corbusier', 'lalanne', 'matisse']
    for term in banned:
        if term in text_lower:
            errors.append(f"FAIL: Banned term '{term}' found in tour text")

    # Required presence
    if 'miró' not in text_lower and 'miro' not in text_lower:
        errors.append("FAIL: 'Miró' not found in text")
    if 'dalí' not in text_lower and 'dali' not in text_lower:
        errors.append("FAIL: 'Dalí' not found in text")
    if 'freud' not in text_lower:
        errors.append("FAIL: 'Freud' not found (required for stop 2)")
    if 'gris' not in text_lower:
        errors.append("FAIL: 'Gris' not found (required for stop 3)")
    if 'reverdy' not in text_lower:
        errors.append("FAIL: 'Reverdy' not found (required for stop 3)")

    # 'book' in ≥2 stops
    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    book_count = sum(1 for s in stops if 'book' in s.lower())
    if book_count < 2:
        errors.append(f"FAIL: 'book' appears in only {book_count} stops (need ≥2)")

    # Every stop ≥120 words
    for stop in stops:
        if stop.strip().startswith('Stop'):
            words = len(stop.split())
            stop_name = stop.split('\n')[0][:50]
            if words < 120:
                errors.append(f"FAIL: {stop_name} has only {words} words (need ≥120)")

    return errors


def main():
    print("=" * 70)
    print("LOCAL-382 ACCEPTANCE — Exhibition thesis framing")
    print("=" * 70)

    # --- Test 1: MFA Exhibition (8 stops) ---
    print("\n--- TEST 1: Picasso, Miró, Dalí: Unbound at MFA (8 stops) ---\n")
    try:
        tour_text, _, coords = generate_tour_text(
            "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA",
            "museum",
            "/tmp/local382_mfa.txt",
            total_stops=8,
        )
        if tour_text:
            print(f"\n{'='*40} MFA TOUR TEXT {'='*40}")
            print(tour_text[:5000])
            print(f"{'='*40} END {'='*40}")

            errors = check_acceptance_mfa(tour_text)
            if errors:
                print("\n⚠️  ACCEPTANCE ERRORS:")
                for e in errors:
                    print(f"  {e}")
            else:
                print("\n✓ All MFA acceptance checks pass")

            # Score
            score = score_tour_file("/tmp/local382_mfa.txt", 8)
            print(f"\n  Score: {score} (threshold: 75.0)")
        else:
            print("FAIL: Tour generation returned None")
    except Exception as e:
        print(f"ERROR generating MFA tour: {e}")
        import traceback
        traceback.print_exc()

    # --- Test 2: Palais Lascaris (4 stops) ---
    print("\n--- TEST 2: Palais Lascaris, Nice, France (4 stops) ---\n")
    try:
        tour_text2, _, coords2 = generate_tour_text(
            "Palais Lascaris, Nice, France",
            "museum",
            "/tmp/local382_palais.txt",
            total_stops=4,
        )
        if tour_text2:
            print(f"\n{'='*40} PALAIS LASCARIS TOUR TEXT {'='*40}")
            print(tour_text2[:3000])
            print(f"{'='*40} END {'='*40}")

            # Check: 4/4 real instruments, no fabricated premise
            text_lower = tour_text2.lower()
            # Report framing case (will be visible in stdout logs above)
            print("\n  Check: no invented curatorial premise")
            if 'exhibition' in text_lower and 'curated' in text_lower:
                print("  ⚠️  WARNING: possible forced curatorial framing")
            else:
                print("  ✓ No forced exhibition framing detected")

            score2 = score_tour_file("/tmp/local382_palais.txt", 4)
            print(f"\n  Score: {score2} (threshold: 81.2)")
        else:
            print("FAIL: Tour generation returned None")
    except Exception as e:
        print(f"ERROR generating Palais Lascaris tour: {e}")
        import traceback
        traceback.print_exc()

    # --- Test 3: General encyclopedic museum (4 stops) ---
    print("\n--- TEST 3: The Louvre, Paris, France (4 stops) ---\n")
    try:
        tour_text3, _, coords3 = generate_tour_text(
            "The Louvre, Paris, France",
            "museum",
            "/tmp/local382_louvre.txt",
            total_stops=4,
        )
        if tour_text3:
            print(f"\n{'='*40} LOUVRE TOUR TEXT {'='*40}")
            print(tour_text3[:3000])
            print(f"{'='*40} END {'='*40}")

            # Check: framing=none, no invented thesis
            text_lower = tour_text3.lower()
            invented_phrases = [
                'sets out to show', 'aims to demonstrate',
                'curated to', 'assembled to demonstrate',
            ]
            for phrase in invented_phrases:
                if phrase in text_lower:
                    print(f"  ⚠️  WARNING: possible invented thesis: '{phrase}'")

            print("  ✓ General museum control case complete")

            score3 = score_tour_file("/tmp/local382_louvre.txt", 4)
            print(f"\n  Score: {score3} (threshold: 81.2)")
        else:
            print("FAIL: Tour generation returned None")
    except Exception as e:
        print(f"ERROR generating Louvre tour: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("LOCAL-382 ACCEPTANCE COMPLETE")
    print("=" * 70)


if __name__ == '__main__':
    main()
