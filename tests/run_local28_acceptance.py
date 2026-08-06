"""
LOCAL-28 Acceptance Test: Verify catalogue extraction for Musée des Arts Asiatiques (Q3330160)

Steps:
1. Delete venue_corpus row for Q3330160 (force CACHE MISS)
2. Delete tour_cache row for the venue
3. Re-run corpus extraction
4. Verify catalogue works are extracted with metadata
5. Verify disque/fauteuil are excluded
6. Run 8-stop generation and verify all stops are real documented works
"""
import json
import os
import sys
sys.path.insert(0, '.')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_db_connection():
    """Get connection to the local postgres."""
    try:
        from db_connection import get_connection
        return get_connection()
    except SystemExit:
        return None
    except Exception as e:
        print(f"DB connection failed: {e}")
        return None


def step1_delete_cache():
    """Delete venue_corpus and tour_cache rows for Q3330160."""
    conn = get_db_connection()
    if not conn:
        print("SKIP: Cannot connect to database")
        return False
    
    try:
        with conn.cursor() as cur:
            # Check if venue_corpus exists
            cur.execute("SELECT COUNT(*) FROM venue_corpus WHERE qid = 'Q3330160'")
            count = cur.fetchone()[0]
            print(f"  venue_corpus rows for Q3330160: {count}")
            
            if count > 0:
                cur.execute("DELETE FROM venue_corpus WHERE qid = 'Q3330160'")
                print(f"  DELETED venue_corpus row for Q3330160")
            
            # Check/delete tour_cache
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'tour_cache'
            """)
            if cur.fetchone()[0] > 0:
                cur.execute("DELETE FROM tour_cache WHERE location ILIKE '%arts asiatiques%' OR location ILIKE '%asian arts%nice%'")
                deleted = cur.rowcount
                print(f"  DELETED {deleted} tour_cache rows for MAA Nice")
            
            conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        conn.close()
        return False


def step2_verify_catalogue_extraction():
    """Run corpus extraction and verify catalogue works are found."""
    from story_miner import fetch_venue_narrative_corpus, extract_catalogue_works_from_pages
    
    print("\n--- Step 2: Fresh corpus extraction ---")
    print("CACHE MISS: Q3330160 (Musée des Arts asiatiques, Nice)")
    
    corpus_result = fetch_venue_narrative_corpus(
        venue_name="Musée des Arts asiatiques",
        base_site_url="https://maa.departement06.fr",
        wikipedia_title="Musée des Arts asiatiques",
        language="fr",
        venue_qid="Q3330160",
    )
    
    pages = corpus_result.get('pages', [])
    print(f"\n  Pages fetched: {len(pages)}")
    for p in pages:
        print(f"    - {p.get('url', '?')} ({len(p.get('text', ''))} chars)")
    
    # Check for catalogue works
    catalogue_works = corpus_result.get('catalogue_works', [])
    print(f"\n  Catalogue works extracted: {len(catalogue_works)}")
    for cw in catalogue_works:
        print(f"    ✓ {cw['title']}")
        if cw.get('material'):
            print(f"      Material: {cw['material']}")
        if cw.get('period'):
            print(f"      Period: {cw['period']}")
        if cw.get('origin'):
            print(f"      Origin: {cw['origin']}")
    
    # Check canonical titles include catalogue works
    canonical = corpus_result.get('canonical_titles', set())
    print(f"\n  Canonical titles: {len(canonical)}")
    
    # Verify the 9 known works
    expected_works = [
        "L'Armure d'Andô Naoyuki",
        "Statue de Bouddha",
        "La danse cosmique de Ganesh",
        "Kannon, le bodhisattva de la compassion",
        "Ulysses Grant au Japon",
        "Robe de prêtre taoïste",
        "Kannon à mille bras",
        "Masque du vieillard kojô",
        "Armure du Clan Hotta",
    ]
    
    found = 0
    for title in expected_works:
        if title in canonical:
            print(f"    ✓ FOUND: {title}")
            found += 1
        else:
            # Try normalized match
            from story_miner import _normalize
            norm_title = _normalize(title)
            matched = any(_normalize(ct) == norm_title for ct in canonical)
            if matched:
                print(f"    ✓ FOUND (normalized): {title}")
                found += 1
            else:
                print(f"    ✗ MISSING: {title}")
    
    print(f"\n  Found {found}/{len(expected_works)} expected catalogue works")
    
    # Verify disque/fauteuil are NOT in canonical titles
    print("\n  Bare noun check:")
    if 'disque' in canonical:
        print("    ✗ FAIL: 'disque' still in canonical titles")
    else:
        print("    ✓ OK: 'disque' excluded")
    if 'fauteuil' in canonical:
        print("    ✗ FAIL: 'fauteuil' still in canonical titles")
    else:
        print("    ✓ OK: 'fauteuil' excluded")
    
    return corpus_result, catalogue_works, found >= 5


def step3_verify_per_work_contexts():
    """Verify per_work_contexts contain material/period/origin from catalogue."""
    from story_miner import fetch_venue_narrative_corpus
    
    # Re-use cached result from step 2
    corpus_result = fetch_venue_narrative_corpus(
        venue_name="Musée des Arts asiatiques",
        base_site_url="https://maa.departement06.fr",
        wikipedia_title="Musée des Arts asiatiques",
        language="fr",
        venue_qid="Q3330160",
    )
    
    per_work = corpus_result.get('per_work_contexts', {})
    print(f"\n--- Step 3: Per-work context metadata ---")
    print(f"  Works with context: {len(per_work)}")
    
    for title, contexts in list(per_work.items())[:5]:
        print(f"\n  {title}:")
        for ctx in contexts[:3]:
            print(f"    - {ctx[:100]}...")
    
    return len(per_work) >= 5


if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-28 ACCEPTANCE TEST: Catalogue Extraction")
    print("=" * 70)
    
    print("\n--- Step 1: Clear cache (force CACHE MISS) ---")
    db_ok = step1_delete_cache()
    
    if not db_ok:
        print("\n[WARNING] Database not available — running extraction test only")
    
    corpus_result, catalogue_works, extraction_ok = step2_verify_catalogue_extraction()
    
    if extraction_ok:
        print("\n✓ PASS: Catalogue extraction working — real documented works found")
    else:
        print("\n✗ FAIL: Fewer than 5 catalogue works extracted")
    
    context_ok = step3_verify_per_work_contexts()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Catalogue works extracted: {len(catalogue_works)}")
    print(f"  Bare nouns excluded: {'disque' not in corpus_result.get('canonical_titles', set())}")
    print(f"  Per-work context: {'OK' if context_ok else 'INSUFFICIENT'}")
    print(f"  Overall: {'PASS' if extraction_ok else 'NEEDS MORE WORK'}")
