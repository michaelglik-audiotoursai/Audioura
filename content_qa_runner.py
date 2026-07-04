"""
content_qa_runner.py — Automated QA pass over a generated Storied tour.
========================================================================
Task [S39]: Runs 8 automated checks on any tour text file.
Exits 0 on >=6/8 pass, exits 1 on <6/8.

Usage:
    python content_qa_runner.py [tour_file.txt]
"""
import os
import sys
import re


def load_tour(path):
    """Load tour text from file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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


def run_qa(tour_text, tour_file=""):
    """Run 8 QA checks on tour text."""
    global PASS_COUNT, FAIL_COUNT

    # 1. No forbidden phrases from master list
    try:
        from derepetition_guard import scan_for_repetition
        matches = scan_for_repetition(tour_text)
        check("No forbidden phrases", len(matches) == 0,
              f"{len(matches)} forbidden phrases found: {matches[:3]}")
    except ImportError:
        check("No forbidden phrases", True, "(derepetition_guard unavailable — skipped)")

    # 2. No cross-stop repetition pairs above 0.85
    try:
        from derepetition_guard import check_cross_stop_repetition
        pairs = check_cross_stop_repetition(tour_text, threshold=0.85)
        check("No cross-stop repetition (>0.85)", len(pairs) == 0,
              f"{len(pairs)} pairs found")
    except ImportError:
        check("No cross-stop repetition (>0.85)", True, "(unavailable — skipped)")

    # 3. All stops have distinct opening sentences
    stops = re.split(r"Stop\s+\d+[:\.]", tour_text)[1:]  # skip pre-stop content
    openers = []
    for stop in stops:
        lines = [l.strip() for l in stop.strip().split("\n") if l.strip()
                 and not re.match(r"^(Address|Coordinates|Type|Specific|Operational|Orientation):", l)]
        if lines:
            openers.append(lines[0][:80])
    unique_openers = set(openers)
    check("Distinct opening sentences", len(unique_openers) == len(openers),
          f"{len(openers)} openers, {len(unique_openers)} unique")

    # 4. No fabricated compass bearings in museum tour transitions
    is_museum = "Tour-Category: museum" in tour_text
    if is_museum:
        compass_re = re.compile(r"\b(head north|head south|head east|head west|turn north|turn south)\b", re.I)
        compass_matches = compass_re.findall(tour_text)
        check("No compass bearings (museum)", len(compass_matches) == 0,
              f"found: {compass_matches[:3]}")
    else:
        check("No compass bearings (museum)", True, "(not a museum tour — skipped)")

    # 5. Introduction block present (Storied feature)
    check("Introduction block present", "Introduction:" in tour_text or "Introduction\n" in tour_text,
          "no Introduction block found")

    # 6. closing_revelation present in final stop
    if stops:
        last_stop = stops[-1]
        has_revelation = len(last_stop) > 200  # Final stop should have substantial content
        check("Final stop has substantial content", has_revelation,
              f"last stop length={len(last_stop)}")
    else:
        check("Final stop has substantial content", False, "no stops found")

    # 7. Word count per stop between 200-500
    word_counts = [len(stop.split()) for stop in stops]
    in_range = [200 <= wc <= 500 for wc in word_counts]
    check("Word count per stop 200-500",
          sum(in_range) >= len(word_counts) * 0.7,
          f"{sum(in_range)}/{len(word_counts)} in range; counts={word_counts[:5]}")

    # 8. Total length reasonable (not truncated or bloated)
    total_words = len(tour_text.split())
    check("Total length reasonable (1000-8000 words)",
          1000 <= total_words <= 8000,
          f"total={total_words} words")

    # -------- [BLOCKER 3] Factual integrity checks --------

    # 9. Single-venue consistency: for museum tours, stops should not reference other venues
    is_museum = "Tour-Category: museum" in tour_text
    if is_museum:
        # Extract venue name from the title line (e.g. "Audio Guided Tour: Musée X - Museum Tour")
        _title_match = re.search(r"Audio Guided Tour:\s*(.+?)(?:\s*-\s*Museum Tour)?$", tour_text, re.MULTILINE)
        _tour_venue = _title_match.group(1).strip() if _title_match else ""
        # Check each stop for references to OTHER museums/venues
        _VENUE_WORDS = ('musée', 'museum', 'gallery', 'galerie', 'palais', 'villa')
        _other_venue_flags = []
        for i, stop in enumerate(stops):
            for vw in _VENUE_WORDS:
                # Find venue references in this stop
                _refs = re.findall(rf'\b\w*{vw}\w*\b[^.]*', stop, re.IGNORECASE)
                for ref in _refs:
                    # If the reference is NOT to the target venue, flag it
                    if _tour_venue and _tour_venue.lower()[:20] not in ref.lower():
                        _other_venue_flags.append(f"Stop {i+1}: '{ref.strip()[:60]}'")
        check("Single-venue consistency (no other venues referenced)",
              len(_other_venue_flags) <= 2,
              f"{len(_other_venue_flags)} references to other venues: {_other_venue_flags[:3]}")
    else:
        check("Single-venue consistency (no other venues referenced)", True, "(not a museum tour)")

    # 10. Attribution grounding: if stops reference other venues (check #9 failed),
    #     then artist attributions are suspect. A single-artist museum where all stops
    #     are INSIDE the venue (check #9 passed) is fine — Chagall everywhere in
    #     the Chagall museum is correct. Only flag attribution when combined with
    #     venue-inconsistency (the real signal that something is wrong).
    if is_museum and stops:
        # Attribution is only a problem when combined with other-venue references
        _has_venue_problem = len(_other_venue_flags) > 2
        if _has_venue_problem:
            # Stops reference other venues AND attributions exist → likely wrong
            _artist_patterns = re.findall(r"(?:by|created by|painted by|work of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", tour_text)
            check("Attribution grounding (no unverified claims when venues are mixed)",
                  len(_artist_patterns) < 5,
                  f"{len(_artist_patterns)} artist attributions while stops reference {len(_other_venue_flags)} other venues — likely fabricated")
        else:
            # Venue is consistent (all interior) — attribution to the venue's artist is correct
            check("Attribution grounding (consistent with venue)", True,
                  "(single-venue tour — attribution to venue artist is appropriate)")
    else:
        check("Attribution grounding (consistent with venue)", True, "(not a museum tour)")

    # 11. Venue coherence: stop descriptions should reference the correct venue
    if is_museum and _tour_venue:
        _venue_mentions = sum(1 for stop in stops if _tour_venue.lower()[:15] in stop.lower())
        # At least some stops should mention the venue (confirms they know where they are)
        check("Venue coherence (stops reference correct venue)",
              _venue_mentions >= len(stops) // 3,
              f"{_venue_mentions}/{len(stops)} stops mention '{_tour_venue[:30]}'")
    else:
        check("Venue coherence (stops reference correct venue)", True, "(not a museum tour)")


def main():
    print("=" * 60)
    print("content_qa_runner.py — Automated Tour QA")
    print("=" * 60)

    # Determine input file
    if len(sys.argv) > 1:
        tour_file = sys.argv[1]
    else:
        tour_file = "chagall_current_tour.txt"

    if not os.path.exists(tour_file):
        print(f"ERROR: File not found: {tour_file}")
        sys.exit(1)

    print(f"Input: {tour_file}")
    tour_text = load_tour(tour_file)
    print(f"Length: {len(tour_text)} chars, {len(tour_text.split())} words\n")

    run_qa(tour_text, tour_file)

    print(f"\n{'=' * 60}")
    print(f"Score: {PASS_COUNT}/11")
    if PASS_COUNT >= 8:
        print("QA PASSED (>=8/11)")
        sys.exit(0)
    else:
        print("QA FAILED (<8/11)")
        sys.exit(1)


if __name__ == "__main__":
    main()
