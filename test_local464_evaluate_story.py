#!/usr/bin/env python3
"""test_local464_evaluate_story.py — acceptance tests for evaluate_story.

Tests the three acceptance criteria:
1. D434 stop-2 scores Social high, Detail low; sothebys line scores Detail high, Social low.
2. Independence: three scores do NOT sum to 100 — at least one story totals well over 100,
   at least one totals well under.
3. Score all nine D433 stops.

D418/D421/D432 requirement: the test must be able to FAIL. A neutralised evaluate_story
(returning zeros) must cause assertion failures.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from evaluate_story import evaluate_story


def test_d434_stop2_social_high_detail_low():
    """D434 stop-2 (Dalí and Freud) scores Social HIGH and Detail LOW."""
    with open(os.path.join(HERE, 'story_lab_state/stop2_prod.json')) as f:
        data = json.load(f)
    story = data['tour_prose']
    result = evaluate_story(story)

    print(f"D434 stop-2: Historic={result['historic']} Detail={result['detail']} "
          f"Social={result['social']} Valuation={result['valuation_index']}")

    # Social must be meaningfully higher than Detail
    assert result['social'] >= 40, f"Social={result['social']} should be ≥40 (high)"
    assert result['detail'] <= 20, f"Detail={result['detail']} should be ≤20 (low)"
    assert result['social'] > result['detail'] + 20, (
        f"Social ({result['social']}) should dominate Detail ({result['detail']})")
    print("  PASS: Social high, Detail low")


def test_sothebys_detail_high_social_low():
    """Sotheby's catalogue line scores Detail HIGH and Social LOW."""
    sothebys = "Drypoints and lithographs on sheepskin. Sold as a set of 10."
    result = evaluate_story(sothebys)

    print(f"Sothebys: Historic={result['historic']} Detail={result['detail']} "
          f"Social={result['social']} Valuation={result['valuation_index']}")

    # Detail must be meaningfully higher than Social
    assert result['detail'] >= 20, f"Detail={result['detail']} should be ≥20 (high)"
    assert result['social'] <= 10, f"Social={result['social']} should be ≤10 (low)"
    assert result['detail'] > result['social'] + 15, (
        f"Detail ({result['detail']}) should dominate Social ({result['social']})")
    print("  PASS: Detail high, Social low")


def test_independence_not_summing_to_100():
    """Prove scores do NOT sum to any fixed number.

    At least one story where H+D+S > 100, at least one where H+D+S < 100.
    A normalising implementation cannot pass this test.
    """
    with open(os.path.join(HERE, 'story_lab_state/stop2_prod.json')) as f:
        data = json.load(f)
    story_over = data['tour_prose']

    story_under = "Drypoints and lithographs on sheepskin. Sold as a set of 10."

    result_over = evaluate_story(story_over)
    result_under = evaluate_story(story_under)

    sum_over = result_over['historic'] + result_over['detail'] + result_over['social']
    sum_under = result_under['historic'] + result_under['detail'] + result_under['social']

    print(f"Sum over 100:  {sum_over} (D434 stop-2: H={result_over['historic']} "
          f"D={result_over['detail']} S={result_over['social']})")
    print(f"Sum under 100: {sum_under} (Sothebys: H={result_under['historic']} "
          f"D={result_under['detail']} S={result_under['social']})")

    assert sum_over > 100, f"Expected sum > 100 for D434 stop-2, got {sum_over}"
    assert sum_under < 100, f"Expected sum < 100 for sothebys, got {sum_under}"
    print("  PASS: independence proven — sums are NOT constrained to 100")


def test_d433_nine_stops():
    """Score all nine D433 stops and report the table.

    D433 stops: MFA Unbound stops 1-3, Fruitlands stops 1-3, Beacon Hill stops 1-3.
    """
    import re

    def extract_stop_prose(tour_text, stop_numbers=None):
        """Extract prose bodies from a tour file."""
        stops = re.split(r'\nStop \d+:', tour_text)
        results = []
        if len(stops) <= 1:
            return results

        for i, stop_text in enumerate(stops[1:], 1):
            if stop_numbers and i not in stop_numbers:
                continue
            # Extract title
            title_match = re.match(r'\s*(.+?)(?:\n|$)', stop_text)
            title = title_match.group(1).strip() if title_match else f'Stop {i}'

            # Extract body prose
            parts = stop_text.split('\n\n')
            prose_parts = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if p.startswith(('Address:', 'Coordinates:', 'Orientation:', 'Directions:')):
                    continue
                if p.startswith("That's"):
                    break
                if len(p) > 80:
                    prose_parts.append(p)
            prose = ' '.join(prose_parts)
            if prose:
                results.append((title, prose))
        return results

    mfa_file = os.path.join(HERE, 'TOUR_MFA_20260812_2030.txt')
    fruitlands_file = os.path.join(HERE, 'fruitlands_museum_tour.txt')
    beacon_file = os.path.join(HERE, 'Beacon_Hill__Boston_walking_tour_20260714_135649.txt')

    with open(mfa_file) as f:
        mfa_stops = extract_stop_prose(f.read())
    with open(fruitlands_file) as f:
        fruitlands_stops = extract_stop_prose(f.read(), stop_numbers={1, 2, 3})
    with open(beacon_file) as f:
        beacon_stops = extract_stop_prose(f.read(), stop_numbers={1, 2, 3})

    all_stops = []
    for title, prose in mfa_stops:
        all_stops.append(('MFA Unbound', title, prose))
    for title, prose in fruitlands_stops:
        all_stops.append(('Fruitlands', title, prose))
    for title, prose in beacon_stops:
        all_stops.append(('Beacon Hill', title, prose))

    print(f"\n{'Tour':<16} {'Stop':<40} {'H':>3} {'D':>3} {'S':>3} {'Val':>4} {'Sum':>4}")
    print('-' * 80)

    any_nonzero = False
    for tour, title, prose in all_stops:
        result = evaluate_story(prose)
        h, d, s, v = result['historic'], result['detail'], result['social'], result['valuation_index']
        total = h + d + s
        print(f"{tour:<16} {title[:38]:<40} {h:3d} {d:3d} {s:3d} {v:4d} {total:4d}")
        if h > 0 or d > 0 or s > 0:
            any_nonzero = True

    assert any_nonzero, "All scores are zero — evaluate_story appears neutralised"
    assert len(all_stops) == 9, f"Expected 9 stops, got {len(all_stops)}"
    print(f"\n  PASS: {len(all_stops)} stops scored")


def main():
    print("=" * 70)
    print("LOCAL-464 evaluate_story acceptance tests")
    print("=" * 70)

    tests = [
        test_d434_stop2_social_high_detail_low,
        test_sothebys_detail_high_social_low,
        test_independence_not_summing_to_100,
        test_d433_nine_stops,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 70}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
