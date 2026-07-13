"""test_w9_collection_anchor.py — W9 collection-anchor precision + collection-scoped extraction.

Proves:
1. Musée Marc Chagall page (text with "chagall", "national", "nice", "offered", "1966") passes check_collection_anchor
2. National Gallery of Canada page (text with "chagall", "national", "gallery", "canada" but NOT "nice") is REJECTED
3. extract_collection_provenance produces a dedication element from collection-level donation text

All mocked — no network calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch, MagicMock
from story_element_extractor import check_collection_anchor, extract_collection_provenance


def run_tests() -> bool:
    all_passed = True

    # --- Test 1: Musée Marc Chagall page passes collection_anchor ---
    print("  W9-1: Musée Marc Chagall page passes collection_anchor (Nice present)")

    chagall_museum_text = """The Musée national Marc Chagall in Nice houses the most important 
    permanent collection of works by Marc Chagall. The museum was opened in 1973 and contains 
    seventeen paintings painted by Chagall and offered to the French State in 1966 by the artist 
    and his wife Valentina. The national museum is dedicated to Chagall's biblical works."""

    result = check_collection_anchor(
        page_text=chagall_museum_text,
        artist='Marc Chagall',
        venue_name='Musée national Marc Chagall',
        venue_city='Nice',
    )
    passed = result is True
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] check_collection_anchor returns True for Chagall museum page (got: {result})")
    if not passed:
        all_passed = False

    # --- Test 2: National Gallery of Canada page is REJECTED ---
    print("\n  W9-2: National Gallery of Canada page REJECTED (no 'nice', only 1 non-artist venue token)")

    canada_gallery_text = """The National Gallery of Canada has acquired a significant collection 
    of works by Marc Chagall. The gallery in Ottawa features several paintings from his early period.
    Chagall's influence on Canadian modern art is well documented in national collections."""

    result2 = check_collection_anchor(
        page_text=canada_gallery_text,
        artist='Marc Chagall',
        venue_name='Musée national Marc Chagall',
        venue_city='Nice',
    )
    passed2 = result2 is False
    status = "PASS" if passed2 else "FAIL"
    print(f"    [{status}] check_collection_anchor returns False for Canada gallery page (got: {result2})")
    if not passed2:
        all_passed = False

    # --- Test 2b: Also test without venue_city — needs ≥2 non-artist venue tokens ---
    print("\n  W9-2b: Without venue_city, 'national' alone is insufficient (need ≥2 non-artist tokens)")

    # "national" is the only non-artist venue token from "Musée national Marc Chagall" 
    # that appears in the canada text (musee does NOT appear), so it should fail
    result2b = check_collection_anchor(
        page_text=canada_gallery_text,
        artist='Marc Chagall',
        venue_name='Musée national Marc Chagall',
        venue_city='',  # No city provided
    )
    passed2b = result2b is False
    status = "PASS" if passed2b else "FAIL"
    print(f"    [{status}] Without venue_city, 'national' alone → False (got: {result2b})")
    if not passed2b:
        all_passed = False

    # --- Test 2c: Page with both "musée" and "national" (≥2 non-artist tokens) passes ---
    print("\n  W9-2c: Page with both 'musée' and 'national' passes (≥2 non-artist venue tokens)")

    both_tokens_text = """The musée national dedicated to Marc Chagall contains biblical paintings.
    Chagall created these works throughout his career. The national museum preserves his legacy."""

    result2c = check_collection_anchor(
        page_text=both_tokens_text,
        artist='Marc Chagall',
        venue_name='Musée national Marc Chagall',
        venue_city='',  # No city, but ≥2 non-artist tokens present
    )
    passed2c = result2c is True
    status = "PASS" if passed2c else "FAIL"
    print(f"    [{status}] With 'musée' + 'national' (2 non-artist tokens) → True (got: {result2c})")
    if not passed2c:
        all_passed = False

    # --- Test 3: extract_collection_provenance produces dedication element ---
    print("\n  W9-3: extract_collection_provenance produces dedication element from donation text")

    donation_text = """The Musée national Marc Chagall was inaugurated in 1973. It houses 
    seventeen paintings painted by Chagall and offered to the French State in 1966 by the artist 
    and his wife Valentina (known as Vava). André Malraux, Minister of Culture, accepted the 
    donation which formed the core of what would become the national museum."""

    # Mock the OpenAI API call to return a dedication element
    mock_response_body = {
        'choices': [{
            'message': {
                'content': '{"elements": [{"type": "dedication", "text": "Chagall and his wife Valentina offered seventeen paintings to the French State in 1966", "source_sentence": "seventeen paintings painted by Chagall and offered to the French State in 1966 by the artist and his wife Valentina", "people": ["Valentina", "André Malraux"], "dates": ["1966", "1973"]}]}'
            }
        }]
    }

    # Mock urllib.request.urlopen
    mock_resp = MagicMock()
    mock_resp.read.return_value = __import__('json').dumps(mock_response_body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch('story_element_extractor.OPENAI_API_KEY', 'test-key'), \
         patch('urllib.request.urlopen', return_value=mock_resp):
        elements = extract_collection_provenance(
            page_text=donation_text,
            artist='Marc Chagall',
            venue_name='Musée national Marc Chagall',
            source_url='https://en.wikipedia.org/wiki/Mus%C3%A9e_Marc_Chagall',
        )

    passed3 = (len(elements) >= 1 and
               elements[0].get('type') in ('provenance', 'dedication') and
               '1966' in elements[0].get('text', ''))
    status = "PASS" if passed3 else "FAIL"
    print(f"    [{status}] extract_collection_provenance returned {len(elements)} element(s)")
    if elements:
        print(f"           Type: {elements[0].get('type')}")
        print(f"           Text: {elements[0].get('text', '')[:80]}")
        print(f"           Source domain: {elements[0].get('source_domain', '')}")
    if not passed3:
        all_passed = False

    # --- Test 3b: Verify source metadata attached ---
    if elements:
        print("\n  W9-3b: Source metadata attached correctly")
        passed3b = (elements[0].get('source_url') == 'https://en.wikipedia.org/wiki/Mus%C3%A9e_Marc_Chagall' and
                    elements[0].get('source_domain') == 'en.wikipedia.org')
        status = "PASS" if passed3b else "FAIL"
        print(f"    [{status}] source_url and source_domain set correctly")
        if not passed3b:
            all_passed = False

    # --- Test 4: Empty text returns empty list ---
    print("\n  W9-4: Empty text returns empty list")
    with patch('story_element_extractor.OPENAI_API_KEY', 'test-key'):
        empty_result = extract_collection_provenance('', 'Marc Chagall', 'Musée national Marc Chagall', 'http://x.com')
    passed4 = empty_result == []
    status = "PASS" if passed4 else "FAIL"
    print(f"    [{status}] Empty text → empty list (got: {empty_result})")
    if not passed4:
        all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 70)
    print("W9 Collection Anchor Fixture — Precision + Collection-Scoped Extraction")
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
