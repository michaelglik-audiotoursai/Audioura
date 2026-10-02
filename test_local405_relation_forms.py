#!/usr/bin/env python3
"""test_local405_relation_forms.py — Parametrised test: the coherence gate catches
ALL grammatical forms of interaction words, not just the verb.

D334 defect: "collaboration with" walked through the gate because it only matched
"collaborated with". This test proves the gate catches verb, noun, and participle
forms for every interaction word against the canonical Freud case.

Required by LOCAL-405 acceptance: a parametrised test over all interaction forms
against the Freud case, and at least one test on the real generation path (D307).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporal_coherence_gate import (
    check_temporal_coherence,
    apply_temporal_coherence_gate,
    _INTERACTION_RE,
)


# ---------------------------------------------------------------------------
# Parametrised form table: every form must be caught when the stop year is 1974
# (Freud d.1939, so any interaction in/after 1974 is impossible)
# ---------------------------------------------------------------------------

FREUD_INTERACTION_FORMS = [
    # (form_label, sentence)
    # -- collaborate family --
    ("collaborated with (verb)",
     "In 1974, Salvador Dalí collaborated with Freud on this exploration."),
    ("collaboration with (noun)",
     "Dalí's collaboration with Freud unveils a unique intersection of art and psychology."),
    ("collaboration between (noun+between)",
     "The collaboration between Dalí and Freud produced remarkable results."),
    ("collaborating with (participle)",
     "Dalí, collaborating with Freud, created a series of illustrations."),
    # -- partner family --
    ("partnered with (verb)",
     "Dalí partnered with Freud to create a landmark study."),
    ("partnership with (noun)",
     "The partnership with Freud drove Dalí to new heights."),
    # -- meet family --
    ("met (verb)",
     "Dalí met Freud to discuss psychoanalysis."),
    ("met with (verb+prep)",
     "Dalí met with Freud in Vienna."),
    ("meeting with (noun)",
     "A meeting with Freud inspired Dalí to explore the unconscious."),
    # -- work with/alongside family --
    ("worked with (verb)",
     "Dalí worked with Freud on the interpretation of dreams."),
    ("working with (participle)",
     "Working with Freud gave Dalí a new perspective."),
    ("worked alongside (verb+alongside)",
     "Dalí worked alongside Freud on several projects."),
    ("working alongside (participle+alongside)",
     "Working alongside Freud, Dalí pushed surrealism further."),
    # -- correspond family --
    ("corresponded with (verb)",
     "Dalí corresponded with Freud about dream symbolism."),
    ("correspondence with (noun)",
     "The correspondence with Freud influenced Dalí profoundly."),
    # -- dialogue family --
    ("in dialogue with (prepositional)",
     "Dalí was in dialogue with Freud about dream imagery."),
    ("dialogue with (noun)",
     "Dalí's dialogue with Freud shaped his artistic vision."),
    # -- joint family --
    ("joint project with (adjective+noun)",
     "The joint project with Freud occupied Dalí for years."),
    # -- alongside (standalone) --
    ("alongside (adverb)",
     "Dalí, alongside Freud, explored the surreal."),
    # -- together with --
    ("together with (prepositional)",
     "Together with Freud, Dalí ventured into the unconscious."),
    # -- co-author family --
    ("co-authored with (verb)",
     "Dalí co-authored with Freud a paper on dreams."),
    # -- co-create family --
    ("co-created with (verb)",
     "Dalí co-created with Freud a visual interpretation of dreams."),
    ("co-creation with (noun)",
     "Dalí's co-creation with Freud resulted in a surrealist masterpiece."),
    # -- commissioned --
    ("commissioned by (verb)",
     "Dalí was commissioned by Freud to illustrate a manuscript."),
]


class TestAllFormsParametrised:
    """Parametrised: every interaction form is caught against the Freud case."""

    def test_all_forms_caught_with_explicit_year(self):
        """Each form must be caught when the sentence carries '1974' or event_year=1974."""
        results = []
        for label, sentence in FREUD_INTERACTION_FORMS:
            # Try sentence-internal year first
            result = check_temporal_coherence(sentence)
            # If no year in sentence, pass event_year (simulating poi['year']='1974')
            if result is None:
                result = check_temporal_coherence(sentence, event_year=1974)
            caught = result is not None
            results.append((label, sentence, caught, result))

        # Print table
        print(f"\n  {'Form':<40} | Caught? | Reason")
        print(f"  {'-'*40}-+---------+{'-'*50}")
        failures = []
        for label, sentence, caught, result in results:
            reason = result['reason'][:48] if result else ''
            status = "yes" if caught else "NO ❌"
            print(f"  {label:<40} | {status:<7} | {reason}")
            if not caught:
                failures.append(label)

        assert not failures, (
            f"Gate MISSED {len(failures)} form(s): {failures}"
        )
        print(f"\n  ✅ All {len(results)} forms caught.")

    def test_all_forms_caught_via_poi_year(self):
        """apply_temporal_coherence_gate catches all forms when poi has year='1974'."""
        failures = []
        for label, sentence in FREUD_INTERACTION_FORMS:
            poi_list = [{
                'name': 'Test Stop',
                'year': '1974',
                'description': f"Some preamble. {sentence} Some conclusion.",
            }]
            stats = apply_temporal_coherence_gate(poi_list)
            if stats['relations_rejected'] == 0:
                failures.append(label)

        assert not failures, (
            f"apply_temporal_coherence_gate MISSED {len(failures)} form(s) with poi year: {failures}"
        )
        print(f"  ✅ All {len(FREUD_INTERACTION_FORMS)} forms caught via poi year field.")


class TestRegexCoverage:
    """Verify the regex itself matches all relevant surface forms."""

    def test_regex_matches_all_forms(self):
        """_INTERACTION_RE matches the interaction phrase in every test sentence."""
        failures = []
        for label, sentence in FREUD_INTERACTION_FORMS:
            m = _INTERACTION_RE.search(sentence)
            if not m:
                failures.append((label, sentence))

        if failures:
            print("  REGEX FAILURES:")
            for label, sentence in failures:
                print(f"    {label}: {sentence[:60]}")

        assert not failures, (
            f"_INTERACTION_RE missed {len(failures)} form(s): "
            f"{[f[0] for f in failures]}"
        )
        print(f"  ✅ Regex matched all {len(FREUD_INTERACTION_FORMS)} forms.")


class TestValidInteractionsPreserved:
    """Ensure valid interactions (both parties alive) are NOT rejected."""

    def test_dali_miro_1925(self):
        """Dalí (1904-1989) and Miró (1893-1983) — valid in 1925."""
        sentence = "In 1925, Dalí met Miró in Paris."
        result = check_temporal_coherence(sentence)
        assert result is None, f"Should not reject: {result}"
        print("  ✅ Dalí-Miró 1925 preserved.")

    def test_dali_broder_1960(self):
        """Dalí (1904-1989) and Broder (1906-1971) — valid in 1960."""
        sentence = "In 1960, Dalí collaborated with Broder on a livre d'artiste."
        result = check_temporal_coherence(sentence)
        assert result is None, f"Should not reject: {result}"
        print("  ✅ Dalí-Broder 1960 preserved.")

    def test_chagall_mourlot_1950(self):
        """Chagall (1887-1985) and Mourlot (1895-1988) — valid in 1950."""
        sentence = "Chagall's collaboration with Mourlot produced extraordinary lithographs."
        # No year in sentence, poi year would be needed — but both alive until 1985
        result = check_temporal_coherence(sentence, event_year=1950)
        assert result is None, f"Should not reject: {result}"
        print("  ✅ Chagall-Mourlot 1950 preserved.")

    def test_non_interaction_verbs(self):
        """Non-interaction verbs must not fire the gate."""
        non_interaction = [
            "In 1974, Dalí illustrated a book by Freud.",
            "Dalí was inspired by Freud's theories.",
            "This work is dedicated to Freud.",
            "Dalí's art was influenced by Freud's writings.",
        ]
        for sentence in non_interaction:
            result = check_temporal_coherence(sentence, event_year=1974)
            assert result is None, f"Non-interaction verb triggered gate: {sentence}"
        print(f"  ✅ {len(non_interaction)} non-interaction verbs correctly ignored.")


class TestRealGenerationPath:
    """D307: At least one test on the real generation path."""

    def test_apply_gate_full_pipeline(self):
        """Simulate a real poi_list through apply_temporal_coherence_gate.
        
        Tests that:
        1. The nominalised form is caught when poi year is set
        2. Valid sentences are preserved
        3. The gate does not damage structure
        """
        poi_list = [
            {
                'name': 'Les Chants de Maldoror',
                'year': '1974',
                'artist': 'Salvador Dalí',
                'description': (
                    "This surrealist masterwork features etchings by Salvador Dalí. "
                    "Dalí's collaboration with Freud unveils a unique intersection of art and psychology. "
                    "The reception was marked by shock and intrigue."
                ),
            },
            {
                'name': 'Le Lézard aux plumes d\'or',
                'year': '1967',
                'artist': 'Joan Miró',
                'description': (
                    "Joan Miró created this livre d'artiste with publisher Louis Broder. "
                    "The lithographs were printed by Mourlot Frères in Paris."
                ),
            },
        ]

        stats = apply_temporal_coherence_gate(poi_list)

        # Stop 1: collaboration with Freud rejected
        assert stats['relations_rejected'] >= 1
        assert 'collaboration with Freud' not in poi_list[0]['description']
        assert 'surrealist masterwork' in poi_list[0]['description']
        assert 'shock and intrigue' in poi_list[0]['description']

        # Stop 2: valid text preserved unchanged
        assert 'Miró created' in poi_list[1]['description']
        assert 'Mourlot' in poi_list[1]['description']

        print(f"  ✅ Full pipeline: {stats['relations_rejected']} rejection(s), valid text intact.")
        print(f"     Stop 1 final: {poi_list[0]['description'][:80]}...")


class TestRevertBreaksLogic:
    """D296: revert breaks the LOGIC, not the symbol.
    
    If you revert the pattern expansion in temporal_coherence_gate.py back to
    verb-only patterns, these tests fail because the noun/participle forms escape.
    """

    def test_revert_would_miss_collaboration_noun(self):
        """Without LOCAL-405 patterns, 'collaboration with' is missed."""
        sentence = "Dalí's collaboration with Freud was groundbreaking."
        # This test proves the LOGIC fix: the gate must match nouns
        m = _INTERACTION_RE.search(sentence)
        assert m is not None, (
            "REVERT DETECTED: _INTERACTION_RE no longer matches 'collaboration with' — "
            "LOCAL-405 fix reverted"
        )
        print("  ✅ 'collaboration with' matched by regex (logic intact).")

    def test_revert_would_miss_partnership_noun(self):
        """Without LOCAL-405 patterns, 'partnership with' is missed."""
        sentence = "The partnership with Freud led to new discoveries."
        m = _INTERACTION_RE.search(sentence)
        assert m is not None, (
            "REVERT DETECTED: _INTERACTION_RE no longer matches 'partnership with' — "
            "LOCAL-405 fix reverted"
        )
        print("  ✅ 'partnership with' matched by regex (logic intact).")

    def test_revert_would_miss_meeting_noun(self):
        """Without LOCAL-405 patterns, 'meeting with' is missed."""
        sentence = "A meeting with Freud changed everything."
        m = _INTERACTION_RE.search(sentence)
        assert m is not None, (
            "REVERT DETECTED: _INTERACTION_RE no longer matches 'meeting with' — "
            "LOCAL-405 fix reverted"
        )
        print("  ✅ 'meeting with' matched by regex (logic intact).")


def run_all():
    """Run all test classes."""
    test_classes = [
        TestRegexCoverage,
        TestAllFormsParametrised,
        TestValidInteractionsPreserved,
        TestRealGenerationPath,
        TestRevertBreaksLogic,
    ]

    total = 0
    passed = 0
    failed = 0

    for cls in test_classes:
        print(f"\n{'='*60}")
        print(f"  {cls.__name__}")
        print(f"{'='*60}")

        instance = cls()
        for method_name in sorted(dir(instance)):
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
    print(f"  Expected red-on-revert: 3 (TestRevertBreaksLogic)")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
