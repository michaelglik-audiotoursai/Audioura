"""test_sq2_fixtures.py — SQ2 deterministic fixtures.

Tests source tier classification, work_key normalization, free-tier enforcement,
and query synthesis. All deterministic — no network calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from work_story_searcher import (
    classify_domain, normalize_work_key, normalize_domain,
    synthesize_queries, search_stories_for_stop,
    _strip_trailing_numeral, synthesize_fact_targeted_queries,
)


def run_tests() -> bool:
    all_passed = True

    # --- Domain tier classification ---
    fixtures_tier = [
        # Reject (evaluated FIRST per R1b)
        ("pinterest.com", "reject", "photo host"),
        ("flickr.com", "reject", "photo host"),
        ("theonion.com", "reject", "satire domain"),
        ("shop.matisse-prints.com", "reject", "commerce pattern"),
        ("facebook.com", "reject", "platform/UGC (F2)"),
        ("youtube.com", "reject", "platform/UGC (F2)"),
        ("m.facebook.com", "reject", "subdomain of platform (F2)"),

        # Tier 1 (institutional)
        ("en.wikipedia.org", "tier1", "encyclopedic"),
        ("britannica.com", "tier1", "encyclopedic"),
        ("harvard.edu", "tier1", ".edu TLD"),
        ("culture.gouv.fr", "tier1", ".gouv.fr TLD"),
        ("moma.org", "tier1", "institutional domain seed (F1)"),
        ("tate.org.uk", "tier1", "institutional domain seed (F1)"),
        ("metmuseum.org", "tier1", "institutional domain seed (F1)"),

        # Tier 2 (quality journalism)
        ("nytimes.com", "tier2", "news org"),
        ("theguardian.com", "tier2", "news org"),
        ("jstor.org", "tier2", "academic"),

        # Tier 3 (default — blogs/UGC; pre-cached to avoid network P856 call)
        ("randomartblog.blogspot.com", "tier3", "unknown blog"),
        ("somesubstack.substack.com", "tier3", "UGC"),
    ]

    # Pre-populate cache for domains that would hit network P856 check
    _offline_cache = {
        "randomartblog.blogspot.com": "tier3",
        "somesubstack.substack.com": "tier3",
        "france-today.com": "tier3",
    }

    print("  Domain Tier Classification:")
    for domain, expected, reason in fixtures_tier:
        result = classify_domain(domain, domain_cache=_offline_cache)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] {domain} → {result} (expected {expected}, {reason})")
        if not passed:
            all_passed = False

    # --- R1 ordering: P856-positive commerce domain stays Reject ---
    print("\n  R1 Ordering (Reject before P856):")
    # pinterest.com has P856 but should be Reject due to photo host list
    result = classify_domain("pinterest.com", domain_cache=_offline_cache)
    passed = result == "reject"
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] pinterest.com (has P856) → {result} (expected reject — photo host checked FIRST)")
    if not passed:
        all_passed = False

    # --- work_key normalization (R7) ---
    print("\n  work_key Normalization (R7):")
    norm_fixtures = [
        ("Le Cantique des Cantiques", "Marc Chagall", "le cantique des cantiques|||marc chagall"),
        ("La Création de l'homme", "Chagall", "la creation de lhomme|||chagall"),
        ("The Birth of Venus", "Botticelli", "the birth of venus|||botticelli"),
        ("  Résurrection  ", "CHAGALL", "resurrection|||chagall"),
    ]
    for title, artist, expected in norm_fixtures:
        result = normalize_work_key(title, artist)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] normalize('{title}', '{artist}') → '{result}' (expected '{expected}')")
        if not passed:
            all_passed = False

    # --- Free tier: ZERO SERP calls (R6) ---
    print("\n  Free Tier Enforcement (R6):")
    test_stop = {'canonical_title': 'Test Work', 'artist': 'Test Artist', 'venue_city': 'Paris'}
    result = search_stories_for_stop(test_stop, generation_tier='free')
    passed = result['total_queries'] == 0 and result['story_mining_status'] == 'cache_only'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] free tier → {result['total_queries']} queries, status={result['story_mining_status']}")
    if not passed:
        all_passed = False

    # --- Query synthesis ---
    print("\n  Query Synthesis:")
    stop = {'canonical_title': 'Song of Songs IV', 'artist': 'Chagall', 'venue_city': 'Nice'}
    queries = synthesize_queries(stop, 'contained')
    # W4: Now produces queries for BOTH "Song of Songs IV" AND "Song of Songs" (series)
    has_exact = any('"Song of Songs IV"' in q for q in queries)
    passed = len(queries) >= 2 and has_exact
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] contained tour: {len(queries)} queries, includes exact title: {has_exact}")
    if not passed:
        all_passed = False

    queries_walk = synthesize_queries(stop, 'distributed')
    passed = len(queries_walk) >= 2 and 'Nice' in queries_walk[0]
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] distributed tour: {len(queries_walk)} queries, contains city: {passed}")
    if not passed:
        all_passed = False

    # --- W4: Query granularity — series/cycle-level title ---
    print("\n  W4: Query Granularity (series/cycle title):")

    # Title with Roman numeral → produces both with and without
    stop_w4 = {'canonical_title': 'Le Cantique des Cantiques IV', 'artist': 'Chagall', 'venue_city': 'Nice'}
    queries_w4 = synthesize_queries(stop_w4, 'contained')
    has_full = any('"Le Cantique des Cantiques IV"' in q for q in queries_w4)
    has_series = any('"Le Cantique des Cantiques"' in q and 'IV' not in q for q in queries_w4)
    passed = has_full and has_series
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 'Le Cantique des Cantiques IV' → queries include BOTH full title and series: full={has_full}, series={has_series}")
    if not passed:
        all_passed = False

    # Title with Arabic numeral
    stop_w4b = {'canonical_title': 'Blue Nude II', 'artist': 'Matisse', 'venue_city': 'Nice'}
    queries_w4b = synthesize_queries(stop_w4b, 'contained')
    has_full_b = any('"Blue Nude II"' in q for q in queries_w4b)
    has_series_b = any('"Blue Nude"' in q and 'II' not in q for q in queries_w4b)
    passed = has_full_b and has_series_b
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 'Blue Nude II' → queries include BOTH full and series: full={has_full_b}, series={has_series_b}")
    if not passed:
        all_passed = False

    # strip_trailing_numeral helper
    passed = _strip_trailing_numeral("Le Cantique des Cantiques IV") == "Le Cantique des Cantiques"
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] _strip_trailing_numeral('Le Cantique des Cantiques IV') → 'Le Cantique des Cantiques'")
    if not passed:
        all_passed = False

    passed = _strip_trailing_numeral("Landscape") is None
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] _strip_trailing_numeral('Landscape') → None (no numeral)")
    if not passed:
        all_passed = False

    # --- W5: Title language split ---
    print("\n  W5: Title Language Split (local_title):")

    stop_w5 = {'canonical_title': 'Le Cantique des Cantiques IV', 'local_title': 'Song of Songs IV',
                'artist': 'Chagall', 'venue_city': 'Nice'}
    queries_w5 = synthesize_queries(stop_w5, 'contained')
    has_canonical = any('"Le Cantique des Cantiques IV"' in q for q in queries_w5)
    has_local = any('"Song of Songs IV"' in q for q in queries_w5)
    passed = has_canonical and has_local
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] canonical + local_title → queries include BOTH: canonical={has_canonical}, local={has_local}")
    if not passed:
        all_passed = False

    # Same title in both → no duplicate
    stop_w5_same = {'canonical_title': 'Blue Nude II', 'local_title': 'Blue Nude II',
                    'artist': 'Matisse', 'venue_city': 'Nice'}
    queries_w5_same = synthesize_queries(stop_w5_same, 'contained')
    # Should NOT have an extra duplicate query for same title
    local_queries = [q for q in queries_w5_same if '"Blue Nude II"' in q and 'story behind' in q]
    passed = len(local_queries) == 1  # Only one "Blue Nude II" story behind, not duplicated
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] same canonical and local → no duplicate query: count={len(local_queries)}")
    if not passed:
        all_passed = False

    # --- W6: Tier-list typo fix ---
    print("\n  W6: Tier-List Typo Fix (francetoday.com):")

    result = classify_domain("francetoday.com", domain_cache=_offline_cache)
    passed = result == "tier2"
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] classify_domain('francetoday.com') → {result} (expected tier2)")
    if not passed:
        all_passed = False

    # Old typo domain should NOT be tier2
    result_old = classify_domain("france-today.com", domain_cache=_offline_cache)
    passed = result_old != "tier2"  # The typo is gone, so it falls to default (tier3 via cache or P856)
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] classify_domain('france-today.com') → {result_old} (expected NOT tier2 — typo removed)")
    if not passed:
        all_passed = False

    # --- W7: Fact-targeted refinement trigger ---
    print("\n  W7: Fact-Targeted Refinement Trigger:")

    # Mock: reported dedication element with people/dates → produces targeted query
    stop_w7 = {'canonical_title': 'Le Cantique des Cantiques IV', 'artist': 'Chagall'}
    reported_elems = [
        {'type': 'dedication', 'corroboration_status': 'reported',
         'text': 'Chagall dedicated the cycle to Vava',
         'people': ['Vava'], 'dates': ['1966']},
    ]
    fact_queries = synthesize_fact_targeted_queries(stop_w7, reported_elems)
    passed = len(fact_queries) >= 1
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] reported dedication → generates fact-targeted query: {len(fact_queries)} queries")
    if not passed:
        all_passed = False
    else:
        # The query should mention key people or dates
        q = fact_queries[0]
        has_person_or_date = 'Vava' in q or '1966' in q
        passed = has_person_or_date
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] fact-targeted query includes person/date: '{q[:60]}...'")
        if not passed:
            all_passed = False

    # Non-high-value type (e.g. 'date') → no refinement triggered
    non_hv_elems = [
        {'type': 'date', 'corroboration_status': 'reported',
         'text': 'Created in 1952', 'people': [], 'dates': ['1952']},
    ]
    fact_queries_none = synthesize_fact_targeted_queries(stop_w7, non_hv_elems)
    passed = len(fact_queries_none) == 0
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] non-high-value 'date' type → no refinement: {len(fact_queries_none)} queries")
    if not passed:
        all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 70)
    print("SQ2 Fixtures — Source Tier + Query Synthesis + Free Tier + work_key")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    if success:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
