"""test_sq2_fixtures.py — SQ2 deterministic fixtures.

Tests source tier classification, work_key normalization, free-tier enforcement,
and query synthesis. All deterministic — no network calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from work_story_searcher import (
    classify_domain, normalize_work_key, normalize_domain,
    synthesize_queries, search_stories_for_stop,
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

        # Tier 1 (institutional)
        ("en.wikipedia.org", "tier1", "encyclopedic"),
        ("britannica.com", "tier1", "encyclopedic"),
        ("harvard.edu", "tier1", ".edu TLD"),
        ("culture.gouv.fr", "tier1", ".gouv.fr TLD"),

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
    passed = len(queries) >= 2 and all('"Song of Songs IV"' in q for q in queries)
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] contained tour: {len(queries)} queries, all contain exact title: {passed}")
    if not passed:
        all_passed = False

    queries_walk = synthesize_queries(stop, 'distributed')
    passed = len(queries_walk) >= 2 and 'Nice' in queries_walk[0]
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] distributed tour: {len(queries_walk)} queries, contains city: {passed}")
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
