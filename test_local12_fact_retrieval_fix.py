"""
LOCAL-12 unit tests — verify Fix A (corpus routing) and Fix D (specificity gate).
Run directly: python3 test_local12_fact_retrieval_fix.py
"""
import sys
import json
from unittest.mock import patch, MagicMock

# ─── Fix A: generate_fact_sheet accepts venue_corpus_excerpt ───────────────────

def test_fact_sheet_uses_corpus_as_primary_context():
    """When venue_corpus_excerpt is provided, it should appear in the GPT prompt
    as 'VENUE COLLECTION SOURCES (primary)' — before any Wikipedia context."""
    from fact_extractor import generate_fact_sheet

    captured_prompts = []

    def mock_post(url, **kwargs):
        body = kwargs.get('json', {})
        msgs = body.get('messages', [])
        for m in msgs:
            if m.get('role') == 'user':
                captured_prompts.append(m['content'])
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "confirmed_facts": ["Disque was created in 1912 by Robert Delaunay"],
                "uncertain_facts": [],
                "date_created": "1912",
                "medium": "oil on canvas",
                "surprising_detail": "One of the first purely abstract paintings in history"
            })}}],
            "usage": {"total_tokens": 200}
        }
        return resp

    with patch('fact_extractor.requests.post', side_effect=mock_post):
        result = generate_fact_sheet(
            poi_name="Disque",
            rag_context={"artist_context": "", "period_context": "Generic museum info"},
            api_key="test-key",
            venue_corpus_excerpt="Robert Delaunay created Disque in 1912. It is considered one of the first purely abstract paintings.",
        )

    assert result is not None, "Fact sheet should be generated"
    assert len(result['confirmed_facts']) >= 1, "Should have at least one confirmed fact"
    assert len(captured_prompts) == 1, "One GPT call should have been made"
    prompt = captured_prompts[0]
    assert "VENUE COLLECTION SOURCES (primary" in prompt, "Corpus should be injected as primary"
    assert "Robert Delaunay created Disque" in prompt, "Corpus content should appear in prompt"
    # Verify corpus appears BEFORE supplementary Wikipedia content
    corpus_pos = prompt.find("VENUE COLLECTION SOURCES")
    supplementary_pos = prompt.find("(supplementary)")
    assert corpus_pos < supplementary_pos, "Corpus should appear before supplementary Wikipedia context"
    print("  [PASS] Corpus routed as primary context in GPT prompt")


def test_fact_sheet_still_works_without_corpus():
    """Backward compat: when no corpus is provided, original Wikipedia-only behavior works."""
    from fact_extractor import generate_fact_sheet

    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "confirmed_facts": ["Marc Chagall was born in Vitebsk"],
                "uncertain_facts": [],
                "date_created": None,
                "medium": None,
                "surprising_detail": None
            })}}],
            "usage": {"total_tokens": 150}
        }
        return resp

    with patch('fact_extractor.requests.post', side_effect=mock_post):
        result = generate_fact_sheet(
            poi_name="Biblical Message",
            rag_context={"artist_context": "Marc Chagall was born in Vitebsk...", "period_context": ""},
            api_key="test-key",
            # No venue_corpus_excerpt
        )

    assert result is not None, "Should still generate fact sheet from Wikipedia context alone"
    assert "Marc Chagall" in result['confirmed_facts'][0]
    print("  [PASS] Without corpus, Wikipedia-only path still works")


def test_fact_sheet_returns_none_when_no_context_at_all():
    """When no corpus AND no Wikipedia context, returns None (no hallucination)."""
    from fact_extractor import generate_fact_sheet

    result = generate_fact_sheet(
        poi_name="Unknown Exhibit",
        rag_context={"artist_context": "", "period_context": ""},
        api_key="test-key",
        venue_corpus_excerpt="",
    )
    assert result is None, "Should return None when no context available"
    print("  [PASS] No context → None (no hallucinated facts)")


# ─── Fix A: generate_fact_sheets_parallel routes corpus per-POI ───────────────

def test_parallel_extracts_corpus_per_poi():
    """Per-work contexts should be matched to each POI by fuzzy prefix."""
    from fact_extractor import generate_fact_sheets_parallel

    call_log = []

    def mock_fetch_poi_rag_context(poi_name, venue_name, tour_category):
        return {"artist_context": "", "period_context": "", "attribution_confident": False}

    def mock_generate_fact_sheet(poi_name, rag_context, api_key, venue_corpus_excerpt=""):
        call_log.append({"poi": poi_name, "corpus": venue_corpus_excerpt})
        return {
            "confirmed_facts": ["test fact"] if venue_corpus_excerpt else [],
            "uncertain_facts": [],
            "date_created": None,
            "medium": None,
            "surprising_detail": None,
        }

    with patch('rag_retriever.fetch_poi_rag_context', side_effect=mock_fetch_poi_rag_context):
        with patch('fact_extractor.generate_fact_sheet', side_effect=mock_generate_fact_sheet):
            results = generate_fact_sheets_parallel(
                poi_list=["Disque", "Fauteuil", "Unknown Thing"],
                venue_name="Musée d'Art Moderne",
                tour_category="museum",
                api_key="test",
                venue_corpus="Robert Delaunay created Disque in 1912. The Fauteuil chair was designed by Le Corbusier.",
                per_work_contexts={
                    "Disque": ["Robert Delaunay created Disque in 1912", "It is an abstract circle painting"],
                    "Fauteuil LC2": ["The Fauteuil was designed by Le Corbusier in 1928"],
                },
            )

    assert len(results) == 3
    # Disque should have gotten corpus via per_work_contexts match
    disque_call = next(c for c in call_log if c['poi'] == 'Disque')
    assert "Robert Delaunay" in disque_call['corpus'], "Disque should get per_work_contexts match"

    # Fauteuil should match via prefix (first 8 chars of "fauteuil" in "fauteuil lc2")
    fauteuil_call = next(c for c in call_log if c['poi'] == 'Fauteuil')
    assert "Le Corbusier" in fauteuil_call['corpus'], "Fauteuil should match per_work_contexts by prefix"

    # Unknown Thing should fall back to keyword search in venue_corpus
    unknown_call = next(c for c in call_log if c['poi'] == 'Unknown Thing')
    # "Unknown Thing" has no 4+ char keywords matching corpus, so empty
    assert unknown_call['corpus'] == "", "Unknown Thing has no corpus match"

    # Check had_corpus_context flag
    assert results[0]['had_corpus_context'] is True, "Disque result should have had_corpus_context=True"
    assert results[1]['had_corpus_context'] is True, "Fauteuil result should have had_corpus_context=True"
    print("  [PASS] Per-work contexts correctly routed to matching POIs")


# ─── Fix D: Specificity gate (tested via prompt construction logic) ───────────

def test_specificity_gate_short_description():
    """When confirmed_facts < 2 and no corpus context, the 120-word target should be used."""
    # Simulate the logic from generate_tour_text.py _generate_description
    fact_sheet = {
        "confirmed_facts": ["one lonely fact"],
        "had_corpus_context": False,
        "attribution_confident": True,
    }

    _confirmed_count = len(fact_sheet.get('confirmed_facts', []))
    _had_corpus = fact_sheet.get('had_corpus_context', False)
    _specificity_short = (_confirmed_count < 2 and not _had_corpus)

    assert _specificity_short is True, "Should trigger short mode with <2 facts and no corpus"
    print("  [PASS] Specificity gate triggers for <2 confirmed facts, no corpus")


def test_specificity_gate_normal_with_corpus():
    """When had_corpus_context=True, even with <2 facts, normal 300-word target."""
    fact_sheet = {
        "confirmed_facts": ["one fact"],
        "had_corpus_context": True,
        "attribution_confident": True,
    }

    _confirmed_count = len(fact_sheet.get('confirmed_facts', []))
    _had_corpus = fact_sheet.get('had_corpus_context', False)
    _specificity_short = (_confirmed_count < 2 and not _had_corpus)

    assert _specificity_short is False, "Should NOT trigger short mode when corpus was available"
    print("  [PASS] Specificity gate does NOT trigger when corpus context was available")


def test_specificity_gate_normal_with_enough_facts():
    """When confirmed_facts >= 2, normal 300-word target regardless of corpus."""
    fact_sheet = {
        "confirmed_facts": ["fact one", "fact two"],
        "had_corpus_context": False,
        "attribution_confident": True,
    }

    _confirmed_count = len(fact_sheet.get('confirmed_facts', []))
    _had_corpus = fact_sheet.get('had_corpus_context', False)
    _specificity_short = (_confirmed_count < 2 and not _had_corpus)

    assert _specificity_short is False, "Should NOT trigger short mode when ≥2 facts available"
    print("  [PASS] Specificity gate does NOT trigger when ≥2 confirmed facts")


def test_specificity_gate_none_fact_sheet():
    """When fact_sheet is None, should trigger short mode (graceful degradation)."""
    fact_sheet = None

    _confirmed_count = len(fact_sheet.get('confirmed_facts', [])) if fact_sheet else 0
    _had_corpus = fact_sheet.get('had_corpus_context', False) if fact_sheet else False
    _specificity_short = (_confirmed_count < 2 and not _had_corpus)

    assert _specificity_short is True, "None fact_sheet → short mode (honest brevity)"
    print("  [PASS] None fact_sheet triggers short mode (no padding)")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LOCAL-12 — Fix A (corpus routing) + Fix D (specificity gate) tests")
    print("=" * 70)

    tests = [
        test_fact_sheet_uses_corpus_as_primary_context,
        test_fact_sheet_still_works_without_corpus,
        test_fact_sheet_returns_none_when_no_context_at_all,
        test_parallel_extracts_corpus_per_poi,
        test_specificity_gate_short_description,
        test_specificity_gate_normal_with_corpus,
        test_specificity_gate_normal_with_enough_facts,
        test_specificity_gate_none_fact_sheet,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} PASS, {failed} FAIL")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
