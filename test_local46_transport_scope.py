"""LOCAL-46: Transport/regional tour verification tests.

Tests that:
- Bug A: Transport words are stripped before area resolution
- Bug B: Detected transport mode drives the display category and constraints
- Region handling: Named regions (French Riviera) resolve correctly
- No regression: Normal walking tours, museum tours still work
"""
import sys
import re


def run_tests():
    """Run all LOCAL-46 unit tests."""
    results = []

    # ---- Bug A: Transport word stripping ----
    from area_resolver import _parse_location

    # After stripping, only geographic names should remain
    bug_a_cases = [
        ("French Riviera biking tour, France", ("French Riviera", "France")),
        ("French Riviera biking, France", ("French Riviera", "France")),
        ("Nice walking tour, France", ("Nice", "France")),
        ("horseback tour of Yellowstone, Wyoming", ("Yellowstone", "Wyoming")),
        ("cycling tour in Provence, France", ("Provence", "France")),
        ("kayaking tour of the coast, Alaska", ("the coast", "Alaska")),
        ("dog sledding tour near Big Lake, AK", ("Big Lake", "AK")),
    ]
    for input_str, (exp_n, exp_c) in bug_a_cases:
        got_n, got_c = _parse_location(input_str)
        got_n, got_c = got_n.strip(), got_c.strip()
        ok = (got_n == exp_n and got_c == exp_c)
        results.append(("Bug A: _parse_location strips transport words", input_str, ok,
                        f"got=({got_n!r}, {got_c!r})" if not ok else ""))

    # Bug A in generate_tour_text: _TRANSPORT_STRIP_RE
    from generate_tour_text import _TRANSPORT_STRIP_RE

    strip_cases = [
        ("French Riviera biking , France", "French Riviera , France"),
        ("horseback  Yellowstone, Wyoming", "Yellowstone, Wyoming"),
        ("cycling  Provence, France", "Provence, France"),
        ("Nice , France", "Nice , France"),  # no transport word → unchanged
        ("Beacon Hill, Boston", "Beacon Hill, Boston"),
    ]
    for input_str, expected in strip_cases:
        result = _TRANSPORT_STRIP_RE.sub('', input_str)
        result = re.sub(r'\s{2,}', ' ', result).strip()
        ok = (result == expected)
        results.append(("Bug A: _TRANSPORT_STRIP_RE", input_str, ok,
                        f"got={result!r}" if not ok else ""))

    # ---- Bug B: Transport mode drives category ----
    from generate_tour_text import _detect_transport_mode, _classify_tour_category, _TRANSPORT_MODE_KEYWORDS

    mode_cases = [
        ("French Riviera biking tour, France", "bike"),
        ("horseback tour of Yellowstone", "animal"),
        ("driving tour of Pacific Coast Highway", "vehicle"),
        ("road trip across Italy", "country_scale"),
        ("walking tour of Nice, France", "on_foot"),
        ("Beacon Hill, Boston", "on_foot"),
    ]
    for input_str, expected_mode in mode_cases:
        mode = _detect_transport_mode(input_str)
        ok = (mode == expected_mode)
        results.append(("Bug B: _detect_transport_mode", input_str, ok,
                        f"got={mode!r}" if not ok else ""))

    # Verify that tour_category stays 'walking' for transport tours
    # (the logical category is walking; display is transport mode)
    for loc in ["French Riviera, France", "Pacific Coast, USA"]:
        cat = _classify_tour_category(loc, "")
        ok = (cat == 'walking')
        results.append(("Bug B: category still 'walking' for transport tours", loc, ok,
                        f"got={cat!r}" if not ok else ""))

    # ---- Ensure _TRANSPORT_STRIP_WORDS is a superset of keywords in _TRANSPORT_MODE_KEYWORDS ----
    from generate_tour_text import _TRANSPORT_STRIP_WORDS

    # Manually verify key transport words are in the strip set (regex extraction is fragile)
    required_words = [
        'camel', 'camelback', 'horse', 'horseback', 'dog', 'dogsled', 'dogsledding',
        'bike', 'biking', 'cycling',
        'auto', 'car', 'driving', 'jeep', 'motorcycle', 'scooter',
        'walking', 'hiking', 'sledding',
        'boat', 'kayak', 'safari',
    ]
    for word in required_words:
        ok = word in _TRANSPORT_STRIP_WORDS
        results.append(("Sync: keyword in _TRANSPORT_STRIP_WORDS", word, ok,
                        f"missing from strip set" if not ok else ""))

    # ---- Normal cases not regressed ----
    normal_cases = [
        ("Beacon Hill, Boston", ("Beacon Hill", "Boston")),
        ("Musée National Marc Chagall, Nice", ("Musée National Marc Chagall", "Nice")),
    ]
    for input_str, (exp_n, exp_c) in normal_cases:
        got_n, got_c = _parse_location(input_str)
        got_n, got_c = got_n.strip(), got_c.strip()
        ok = (got_n == exp_n and got_c == exp_c)
        results.append(("No regression: normal parsing", input_str, ok,
                        f"got=({got_n!r}, {got_c!r})" if not ok else ""))

    # ---- Print results ----
    n_pass = sum(1 for _, _, ok, _ in results if ok)
    n_fail = sum(1 for _, _, ok, _ in results if not ok)
    print(f"\nLOCAL-46 Transport/Region Tests: {n_pass} PASS, {n_fail} FAIL")
    print("=" * 60)
    for category, case, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {category}: {case}"
        if detail:
            line += f" — {detail}"
        print(line)
    print("=" * 60)
    if n_fail:
        print(f"\n{n_fail} test(s) FAILED")
        return 1
    else:
        print("\nALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(run_tests())
