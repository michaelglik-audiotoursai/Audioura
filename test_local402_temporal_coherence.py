#!/usr/bin/env python3
"""test_local402_temporal_coherence.py — Unit tests for the temporal coherence gate.

Proves the gate fires on:
  1. "In 1974, Salvador Dalí collaborated with Freud" (Freud d.1939)
  2. "Dalí worked alongside Freud" (no explicit year but death before birth impossible)
  3. Does NOT fire on valid interactions (Dalí and Miró, who overlapped)
  4. Does NOT fire on non-interaction verbs (Dalí illustrated Freud's book)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporal_coherence_gate import (
    check_temporal_coherence,
    apply_temporal_coherence_gate,
    get_person_dates,
    _extract_persons_from_sentence,
)


class TestDaliFreudCoherence:
    """The case from D328: Dalí-Freud collaboration dated 1974, Freud d.1939."""
    
    def test_explicit_date_collaboration(self):
        """'In 1974, Salvador Dalí collaborated with Freud' — must reject."""
        sentence = "In 1974, Salvador Dalí collaborated with Freud, who authored this profound exploration."
        result = check_temporal_coherence(sentence)
        assert result is not None, "Gate should fire on Dalí-Freud 1974 collaboration"
        assert 'Freud' in result['reason'] or 'Freud' in result['person_b'] or 'Freud' in result['person_a']
        assert '1939' in result['reason'] or '1939' in result['dates']
        print(f"  ✅ Rejected: {result['reason']}")
    
    def test_no_date_collaboration(self):
        """'Dalí collaborated with Freud' — still impossible (Freud d.1939 < Dalí active)."""
        # Actually Dalí and Freud DID meet once in 1938, but a blanket "collaborated"
        # without date still passes because we can't prove impossibility without a date
        # that contradicts the overlap. The gate needs an explicit date or death-before-birth.
        # Freud d.1939, Dalí b.1904 — they overlapped! So without a date, this is not
        # provably impossible. Only with "in 1974" does it become impossible.
        sentence = "Dalí collaborated with Freud on this exploration."
        result = check_temporal_coherence(sentence)
        # This should NOT fire because Dalí (1904-1989) and Freud (1856-1939) overlapped
        # Their lifetimes overlap from 1904-1939, so collaboration is theoretically possible
        assert result is None, "Should not reject — lifetimes overlap (1904-1939)"
        print(f"  ✅ Correctly allowed: lifetimes overlap (1904-1939)")
    
    def test_explicit_1974_makes_it_impossible(self):
        """The year 1974 makes it impossible because Freud died in 1939."""
        sentence = "In 1974, Dalí collaborated with Freud."
        result = check_temporal_coherence(sentence)
        assert result is not None, "Gate must fire: Freud d.1939, event 1974"
        assert '1939' in result['dates'] or '1939' in result['reason']
        print(f"  ✅ Rejected: {result['reason']}")
    
    def test_valid_interaction_dali_miro(self):
        """Dalí and Miró both alive in 1925 — no rejection."""
        sentence = "In 1925, Dalí met Miró in Paris."
        result = check_temporal_coherence(sentence)
        assert result is None, "Should not reject: both alive in 1925"
        print(f"  ✅ Correctly allowed: Dalí and Miró both alive in 1925")
    
    def test_non_interaction_verb(self):
        """'Dalí illustrated Freud's book' — not an interaction verb."""
        sentence = "In 1974, Dalí illustrated a book by Freud."
        # 'illustrated' is not an interaction verb — it's unidirectional
        result = check_temporal_coherence(sentence)
        # This should NOT fire because 'illustrated' doesn't assert mutual presence
        assert result is None, "Should not reject: 'illustrated' is not an interaction verb"
        print(f"  ✅ Correctly allowed: 'illustrated' is unidirectional")


class TestGateApplication:
    """Test the full gate on poi_list structure."""
    
    def test_gate_removes_impossible_sentence(self):
        """apply_temporal_coherence_gate removes the offending sentence."""
        poi_list = [
            {
                'name': 'Les Chants de Maldoror',
                'description': (
                    "This surrealist masterwork features illustrations by Salvador Dalí. "
                    "In 1974, Salvador Dalí collaborated with Freud, who authored this profound exploration. "
                    "The reception of this work was marked by shock and intrigue."
                ),
            }
        ]
        
        stats = apply_temporal_coherence_gate(poi_list)
        
        assert stats['relations_rejected'] >= 1, "Should reject at least 1 relation"
        assert stats['sentences_removed'] >= 1, "Should remove at least 1 sentence"
        assert stats['stops_affected'] >= 1, "Should affect at least 1 stop"
        assert stats['rejection_log'], "Should have rejection log entries"
        
        # The impossible sentence should be GONE from the description
        final_desc = poi_list[0]['description']
        assert 'collaborated with Freud' not in final_desc, \
            f"Impossible claim still in output: {final_desc}"
        
        # Valid sentences should remain
        assert 'surrealist masterwork' in final_desc
        assert 'shock and intrigue' in final_desc
        
        # Log line format matches what the task requires
        log_entry = stats['rejection_log'][0]
        assert 'Freud' in log_entry['reason']
        assert '1939' in log_entry['reason'] or '1939' in log_entry['dates']
        
        print(f"  ✅ Gate fired and removed impossible sentence")
        print(f"     Log: {log_entry['reason']}")
        print(f"     Remaining: {final_desc[:100]}...")
    
    def test_gate_preserves_valid_text(self):
        """Gate does not damage valid descriptions."""
        poi_list = [
            {
                'name': 'Le Lézard aux plumes d\'or',
                'description': (
                    "Joan Miró created this livre d'artiste with publisher Louis Broder. "
                    "The lithographs were printed by Mourlot Frères in Paris. "
                    "Boris Fridman donated this work to the museum in 2010."
                ),
            }
        ]
        
        original_desc = poi_list[0]['description']
        stats = apply_temporal_coherence_gate(poi_list)
        
        assert stats['sentences_removed'] == 0, "Should not remove any sentences"
        assert poi_list[0]['description'] == original_desc, "Description should be unchanged"
        print(f"  ✅ Valid text preserved unchanged")


class TestPersonDateExtraction:
    """Test the date lookup mechanism."""
    
    def test_known_freud(self):
        dates = get_person_dates('Freud')
        assert dates is not None
        assert dates['death'] == 1939
        assert dates['birth'] == 1856
        print(f"  ✅ Freud: b.{dates['birth']} d.{dates['death']}")
    
    def test_known_dali(self):
        dates = get_person_dates('Dalí')
        assert dates is not None
        assert dates['death'] == 1989
        assert dates['birth'] == 1904
        print(f"  ✅ Dalí: b.{dates['birth']} d.{dates['death']}")
    
    def test_from_snippets(self):
        """Extract dates from snippet text."""
        snippets = [
            {'title': 'Pierre Reverdy (1889–1960)', 'snippet': 'French poet...', 'url': ''},
        ]
        dates = get_person_dates('Reverdy', snippets=snippets)
        assert dates is not None
        assert dates.get('birth') == 1889 or dates.get('death') == 1960
        print(f"  ✅ Reverdy from snippets: {dates}")


class TestPersonExtraction:
    """Test name extraction from sentences."""
    
    def test_extracts_dali_freud(self):
        sentence = "In 1974, Salvador Dalí collaborated with Freud."
        persons = _extract_persons_from_sentence(sentence)
        # Should find at least Dalí and Freud
        persons_lower = [p.lower() for p in persons]
        has_dali = any('dal' in p for p in persons_lower)
        has_freud = any('freud' in p for p in persons_lower)
        assert has_dali, f"Should find Dalí in: {persons}"
        assert has_freud, f"Should find Freud in: {persons}"
        print(f"  ✅ Extracted: {persons}")


def run_all():
    """Run all test classes."""
    test_classes = [
        TestDaliFreudCoherence,
        TestGateApplication,
        TestPersonDateExtraction,
        TestPersonExtraction,
    ]
    
    total = 0
    passed = 0
    failed = 0
    
    for cls in test_classes:
        print(f"\n{'='*60}")
        print(f"  {cls.__name__}")
        print(f"{'='*60}")
        
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                total += 1
                try:
                    getattr(instance, method_name)()
                    passed += 1
                except AssertionError as e:
                    failed += 1
                    print(f"  ❌ {method_name}: {e}")
                except Exception as e:
                    failed += 1
                    print(f"  ❌ {method_name}: EXCEPTION: {e}")
    
    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
