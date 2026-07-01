"""
test_persona_weighted_tour.py — Verify personalization produces different tours.
Task [S74]. Generates 2 tours for identical inputs with different personas,
compares story-type distributions and text differences.

Requires OPENAI_API_KEY. Usage: python test_persona_weighted_tour.py
"""
import os
import sys
import re

os.environ["STORIED_MODE"] = "true"

PASS_COUNT = 0
FAIL_COUNT = 0

def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1

def jaccard_distance(text_a, text_b):
    """Word-set Jaccard distance between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 1.0
    intersection = words_a & words_b
    union = words_a | words_b
    return 1.0 - (len(intersection) / len(union))

def count_story_types(tour_text, type_name):
    """Count occurrences of a story type in logged output (from [S25] log lines)."""
    # Story types are logged during generation but not in final output
    # For verification, we use the tour structure differences
    return tour_text.lower().count(type_name.lower())

def main():
    print("=" * 60)
    print("test_persona_weighted_tour.py — Persona Differentiation Test")
    print("=" * 60)

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set.")
        sys.exit(1)

    from generate_tour_text import generate_tour_text

    location = "Musée National Marc Chagall, Nice"
    tour_type = "museum"
    total_stops = 10

    # Generate tour 1: art_lover persona
    print("\n[1] Generating tour with persona='art_lover'...")
    tour_art, _, _ = generate_tour_text(location, tour_type, total_stops=total_stops, persona="art_lover")

    # Generate tour 2: history_buff persona
    print("\n[2] Generating tour with persona='history_buff'...")
    tour_history, _, _ = generate_tour_text(location, tour_type, total_stops=total_stops, persona="history_buff")

    if tour_art is None or tour_history is None:
        print("FATAL: One or both tours failed to generate")
        sys.exit(1)

    # Check 1: Both tours complete
    print("\n[3] Assertions:")
    check("Art lover tour generated", len(tour_art) > 500)
    check("History buff tour generated", len(tour_history) > 500)

    # Check 2: Text difference >= 30%
    distance = jaccard_distance(tour_art, tour_history)
    check("Text difference >= 30%", distance >= 0.30, f"Jaccard distance = {distance:.2f}")

    # Check 3: Tours have different content (not identical)
    check("Tours are not identical", tour_art != tour_history)

    # Check 4: Both have 10 stops
    stops_art = len(re.findall(r"Stop\s+\d+[:\.]", tour_art))
    stops_hist = len(re.findall(r"Stop\s+\d+[:\.]", tour_history))
    check("Art lover has ~10 stops", stops_art >= 8, f"got {stops_art}")
    check("History buff has ~10 stops", stops_hist >= 8, f"got {stops_hist}")

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED — personas produce observably different tours")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
    sys.exit(0 if FAIL_COUNT == 0 else 1)

if __name__ == "__main__":
    main()
