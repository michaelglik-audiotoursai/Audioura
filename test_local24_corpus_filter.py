"""
test_local24_corpus_filter.py — LOCAL-24 diagnostic + acceptance test.

Deletes the venue_corpus row for Q3330160 (Asian Arts Museum Nice),
re-scrapes, and prints the resulting titles with kind + source + tier.
"""
import os
import sys
import json

os.environ["STORIED_MODE"] = "true"

# Ensure we can import from this worktree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def delete_corpus_cache(qid: str):
    """Delete the venue_corpus row for a QID."""
    try:
        import psycopg2
        db_url = os.environ.get('VENUE_CACHE_DB_URL',
                 os.environ.get('DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours'))
        conn = psycopg2.connect(db_url, connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM venue_corpus WHERE qid = %s", (qid,))
            deleted = cur.rowcount
            conn.commit()
        conn.close()
        print(f"  [test] Deleted {deleted} venue_corpus row(s) for {qid}")
        return deleted
    except Exception as e:
        print(f"  [test] DB delete failed: {e}")
        return 0


def run_corpus_diagnostic():
    """Re-scrape Asian Arts Museum and print all canonical titles with classification."""
    from story_miner import fetch_venue_narrative_corpus, extract_canonical_titles, filter_corpus_titles
    from venue_resolver import fetch_venue_works, build_canonical_titles_from_works
    
    venue_name = "Musée des Arts asiatiques, Nice"
    venue_qid = "Q3330160"
    # Known properties from prior resolution (avoid re-resolving via flaky Wikidata search)
    wikipedia_title = "Musée des Arts asiatiques"
    official_url = "https://www.musee-arts-asiatiques.fr"
    language = "fr"
    
    print("=" * 70)
    print(f"LOCAL-24 CORPUS DIAGNOSTIC: {venue_name} ({venue_qid})")
    print("=" * 70)
    
    # Step 1: Delete cache
    delete_corpus_cache(venue_qid)
    
    # Step 2: SPARQL works
    print("\n--- SPARQL works ---")
    sparql_works = fetch_venue_works(venue_qid, language)
    sparql_titles = build_canonical_titles_from_works(sparql_works)
    print(f"  {len(sparql_titles)} SPARQL titles:")
    for t in sorted(sparql_titles):
        print(f"    - {t}")
    
    # Step 3: Full corpus fetch (site + Wikipedia)
    print("\n--- Corpus fetch (site + Wikipedia) ---")
    corpus_result = fetch_venue_narrative_corpus(
        venue_name=venue_name,
        base_site_url=official_url,
        wikipedia_title=wikipedia_title,
        language=language,
        venue_qid=venue_qid,
    )
    
    site_wiki_titles = corpus_result['canonical_titles']
    all_titles = site_wiki_titles | sparql_titles
    
    print(f"\n--- ALL canonical titles BEFORE filtering ({len(all_titles)}) ---")
    for i, t in enumerate(sorted(all_titles), 1):
        sources = corpus_result.get('title_sources', {}).get(t, [])
        tier = min((s.get('tier', 1) for s in sources), default=1) if sources else '?'
        source_types = set()
        for s in sources:
            url = s.get('source_url', '')
            if 'wikipedia' in url:
                source_types.add('wiki')
            elif 'pop.culture' in url:
                source_types.add('joconde')
            else:
                source_types.add('site')
        if t in sparql_titles:
            source_types.add('sparql')
        print(f"  {i:2d}. {t}")
        print(f"      sources: {sorted(source_types)}, tier: {tier}")
    
    # Step 4: LOCAL-24 filter
    print(f"\n--- LOCAL-24 WORK-VS-NONWORK FILTER ---")
    title_sources = corpus_result.get('title_sources', {})
    filter_result = filter_corpus_titles(
        raw_titles=all_titles,
        sparql_works=sparql_works,
        source_urls_map=title_sources,
        venue_name=venue_name,
        venue_address="405 Promenade des Anglais, Nice",
        preferred_language=language,
    )
    
    print(f"\n--- FINAL RESULT ---")
    print(f"  Works ({len(filter_result['works'])}):")
    for t in sorted(filter_result['works']):
        print(f"    ✓ {t}")
    print(f"  Galleries ({len(filter_result['galleries'])}):")
    for t in sorted(filter_result['galleries']):
        print(f"    ◈ {t} [kind=gallery]")
    print(f"  Excluded ({len(filter_result['excluded'])}):")
    for ex in filter_result['excluded']:
        print(f"    ✗ {ex['title']} — {ex['rule']}")
    if filter_result['aliases']:
        print(f"  Cross-language aliases ({len(filter_result['aliases'])}):")
        for removed, kept in filter_result['aliases'].items():
            print(f"    '{removed}' → '{kept}'")
    if filter_result['collapsed']:
        print(f"  Near-duplicate collapses ({len(filter_result['collapsed'])}):")
        for removed, kept in filter_result['collapsed'].items():
            print(f"    '{removed}' → '{kept}'")
    
    return all_titles, corpus_result, sparql_works, filter_result


if __name__ == "__main__":
    titles, corpus_result, sparql_works, filter_result = run_corpus_diagnostic()
    
    # --- Additional unit test: verify rules catch the KNOWN problematic titles ---
    print("\n" + "=" * 70)
    print("LOCAL-24 UNIT TEST: Known problematic titles from task spec")
    print("=" * 70)
    
    from story_miner import classify_corpus_entry, dedup_near_duplicates, filter_corpus_titles
    
    # Titles that MUST be excluded (from task description)
    must_exclude = [
        ("Promenade des Anglais", "street_address"),
        ("Origin of the museum's pieces", "wiki_section_heading"),
        ("The museum's collections", "wiki_section_heading"),
        ("Monstre de poche", "themed_program"),
        ("Monstres de poche", "themed_program"),
        ("Monstres et Cie", "themed_program"),
        ("Super-héros, super-pouvoirs", "themed_program"),
        ("Voyage en Asie", "themed_program"),
        ("En harmonie avec la nature", "themed_program"),
        ("Pour ne pas perdre la mémoire", "themed_program"),
    ]
    
    # Titles that MUST be tagged as gallery
    must_gallery = [
        "L'Asie du Sud-Est",
        "Le Japon, pays du soleil levant",
        "Les quatre grands courants religieux d'Asie",
        "Rites et cérémonies en Asie",
    ]
    
    # Titles that MUST be kept as works
    must_work = [
        "Daim et Daine symbolisant le premier sermon de Bouddha",
        "la geste de Bouddha",
        "les paysages de l'âme",
        # LOCAL-28: "disque" and "fauteuil" are now excluded as bare generic nouns
        "Hokusai – Voyage au pied du mont Fuji",
    ]
    
    # LOCAL-28: Bare generic nouns that must now be excluded
    must_exclude_bare_nouns = [
        ("disque", "bare_generic_noun"),
        ("fauteuil", "bare_generic_noun"),
    ]
    
    pass_count = 0
    fail_count = 0
    
    print("\n--- Exclusion rules ---")
    for title, expected_rule in must_exclude:
        result = classify_corpus_entry(title, venue_name="Musée des Arts asiatiques, Nice")
        if result['kind'] == 'excluded':
            print(f"  PASS: '{title}' → excluded ({result['rule']})")
            pass_count += 1
        else:
            print(f"  FAIL: '{title}' → {result['kind']} (expected excluded, got rule={result['rule']})")
            fail_count += 1
    
    print("\n--- Gallery tagging ---")
    for title in must_gallery:
        result = classify_corpus_entry(title, venue_name="Musée des Arts asiatiques, Nice")
        if result['kind'] == 'gallery':
            print(f"  PASS: '{title}' → gallery ({result['rule']})")
            pass_count += 1
        else:
            print(f"  FAIL: '{title}' → {result['kind']} (expected gallery, got rule={result['rule']})")
            fail_count += 1
    
    print("\n--- Work preservation ---")
    from venue_resolver import build_canonical_titles_from_works
    _sparql_titles_set = build_canonical_titles_from_works(sparql_works) if sparql_works else set()
    for title in must_work:
        result = classify_corpus_entry(title, venue_name="Musée des Arts asiatiques, Nice",
                                       sparql_confirmed=(title in _sparql_titles_set))
        if result['kind'] == 'work':
            print(f"  PASS: '{title}' → work ({result['rule']})")
            pass_count += 1
        else:
            print(f"  FAIL: '{title}' → {result['kind']} (expected work, got rule={result['rule']})")
            fail_count += 1
    
    print("\n--- LOCAL-28: Bare generic noun exclusion ---")
    for title, expected_rule in must_exclude_bare_nouns:
        result = classify_corpus_entry(title, venue_name="Musée des Arts asiatiques, Nice")
        if result['kind'] == 'excluded' and result['rule'] == expected_rule:
            print(f"  PASS: '{title}' → excluded ({result['rule']})")
            pass_count += 1
        else:
            print(f"  FAIL: '{title}' → {result['kind']} (expected excluded/{expected_rule}, got {result['rule']})")
            fail_count += 1
    
    print("\n--- Near-duplicate collapse ---")
    dup_test = {"Monstre de poche", "Monstres de poche", "Monstres et Cie"}
    deduped, collapse_map = dedup_near_duplicates(dup_test)
    # "Monstre de poche" and "Monstres de poche" are singular/plural → must collapse.
    # "Monstres et Cie" is semantically different (different phrase) → may remain separate.
    # All three are caught by themed_program exclusion rule anyway.
    if len(deduped) <= 2 and ("Monstre de poche" not in deduped or "Monstres de poche" not in deduped):
        print(f"  PASS: Singular/plural pair collapsed: {deduped}, map: {collapse_map}")
        pass_count += 1
    else:
        print(f"  FAIL: Expected singular/plural collapse, got {len(deduped)}: {deduped}")
        fail_count += 1
    
    print(f"\n{'=' * 70}")
    print(f"UNIT TEST RESULTS: {pass_count} PASS, {fail_count} FAIL")
    print(f"{'=' * 70}")
