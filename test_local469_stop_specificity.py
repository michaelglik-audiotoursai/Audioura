#!/usr/bin/env python3
"""test_local469_stop_specificity.py — LOCAL-469 acceptance (unit level).

These tests CALL the gate functions. They do not grep any source file for a
marker string (D418/D421 — LOCAL-453/456 were bounced for that). The LLM is
injected via `llm_fn` so the logic is exercised deterministically with no
network and no key.

Acceptance criteria covered here:
  AC1 — Michael's Example A is flagged transferable at HIGH confidence and removed.
  AC2 — Michael's Example B is flagged for an ungrounded named entity.
  AC3 — the real Cimiez Monastery paragraph (1546 Saint-Pons swap) is NOT flagged.

The wiring / call-site proof lives in test_local469_wiring.py (separate file,
per the LOCAL-465 lesson: unit tests that call the function directly never
exercise the call site).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stop_specificity_gate as g


# ── Example paragraphs (verbatim from the task) ─────────────────────────────────

EXAMPLE_A = (
    "Cycling on the French Riviera, stop at Cap d'Antibes to experience the "
    "enduring power of nature, inspiring creativity and stimulating the "
    "imagination while admiring panoramic views and soaking up the atmosphere "
    "of this everyday paradise."
)

EXAMPLE_B = (
    "As you stand on Cap d'Antibes with Mediterranean sea stretching out before "
    "you Imagine the scene that once captivated Scott Fitzgerald inspiring the "
    "setting of his timeless novels."
)

# The real shipped paragraph — Cimiez Monastery, from TOUR_CIMIEZ_WALKING_20260830.md.
# Names a date (1546), a place (Saint-Pons Abbey) and an event (the property swap)
# true of nowhere else.
CIMIEZ_MONASTERY = (
    "The Cimiez Monastery, with roots stretching back to the 9th century, stands "
    "as a silent witness to the passage of time and the resilience of faith. The "
    "Count of Savoy ordered the destruction of buildings, including the "
    "Franciscans' entire monastery, in a desperate act of defense. In 1546, a "
    "pivotal moment unfolded when Franciscan friars negotiated a property swap "
    "with Benedictine monks of Saint-Pons Abbey, acquiring a small chapel and "
    "plot of land in Cimiez. The French Revolution brought turmoil once more, as "
    "the monastery was seized and transformed into military barracks and an army "
    "hospital."
)

SIBLINGS = ["Villa Leopolda", "Roman Ruins of Cemenelum", "Musée Marc Chagall"]


# ── Stub LLMs — deterministic stand-ins for the model ───────────────────────────

def make_specificity_stub(verdict_by_substring):
    """Return an llm_fn that answers the substitution-test prompt. It reads the
    SWAPPED PARAGRAPH out of the prompt and returns SPECIFIC/TRANSFERABLE based on
    substrings, mimicking a model that checks whether a concrete claim broke."""
    def _fn(prompt, api_key, model=None):
        # Only answer the substitution-test prompt here.
        if 'VERDICT: SPECIFIC | TRANSFERABLE' not in prompt:
            return None
        for needle, verdict in verdict_by_substring:
            if needle in prompt:
                return f"VERDICT: {verdict}\nREASON: stub"
        return "VERDICT: TRANSFERABLE\nREASON: stub default"
    return _fn


def make_relationship_stub(ungrounded_entities):
    """Return an llm_fn answering the relationship prompt: any entity in
    `ungrounded_entities` → UNGROUNDED, else GROUNDED."""
    def _fn(prompt, api_key, model=None):
        if 'VERDICT: GROUNDED | UNGROUNDED' not in prompt:
            return None
        for ent in ungrounded_entities:
            if f'names "{ent}"' in prompt:
                return "VERDICT: UNGROUNDED\nREASON: sentiment only, no link"
        return "VERDICT: GROUNDED\nREASON: concrete link stated"
    return _fn


def combined_stub(spec_fn, rel_fn):
    def _fn(prompt, api_key, model=None):
        r = spec_fn(prompt, api_key, model)
        if r is not None:
            return r
        return rel_fn(prompt, api_key, model)
    return _fn


class TestPart1Substitution(unittest.TestCase):

    def test_ac1_example_a_is_transferable_high(self):
        """AC1: Example A — nothing breaks when the place name is swapped, so the
        model returns TRANSFERABLE for every sibling → high confidence."""
        stub = make_specificity_stub([])  # default TRANSFERABLE for all
        res = g.check_paragraph_specificity(
            EXAMPLE_A, "Cap d'Antibes", SIBLINGS, api_key="x", llm_fn=stub,
        )
        self.assertTrue(res['transferable'], res)
        self.assertEqual(res['confidence'], 'high', res)

    def test_ac3_cimiez_is_specific_not_flagged(self):
        """AC3: the 1546 Saint-Pons swap is false of any other stop, so the model
        returns SPECIFIC on the first sibling → transferable=False."""
        stub = make_specificity_stub([("VERDICT: SPECIFIC | TRANSFERABLE", "SPECIFIC")])
        res = g.check_paragraph_specificity(
            CIMIEZ_MONASTERY, "Cimiez Monastery", SIBLINGS, api_key="x", llm_fn=stub,
        )
        self.assertFalse(res['transferable'], res)

    def test_specific_on_one_sibling_wins(self):
        """One broken claim on any sibling ⇒ SPECIFIC, even if others transfer."""
        stub = make_specificity_stub([("VERDICT: SPECIFIC | TRANSFERABLE", "SPECIFIC")])
        res = g.check_paragraph_specificity(
            CIMIEZ_MONASTERY, "Cimiez Monastery", SIBLINGS, api_key="x", llm_fn=stub,
        )
        self.assertFalse(res['transferable'])
        self.assertEqual(res['confidence'], 'high')

    def test_failsafe_no_model(self):
        """No api_key and no llm_fn ⇒ never transferable, low confidence."""
        res = g.check_paragraph_specificity(
            EXAMPLE_A, "Cap d'Antibes", SIBLINGS, api_key=None, llm_fn=None,
        )
        self.assertFalse(res['transferable'])
        self.assertEqual(res['confidence'], 'low')

    def test_no_siblings_cannot_run(self):
        res = g.check_paragraph_specificity(EXAMPLE_A, "Cap d'Antibes", [], api_key="x")
        self.assertFalse(res['transferable'])
        self.assertEqual(res['confidence'], 'low')


class TestPart2NamedEntity(unittest.TestCase):

    def test_ac2_example_b_flags_fitzgerald(self):
        """AC2: Example B names Scott Fitzgerald with no stated relationship."""
        stub = make_relationship_stub(["Scott Fitzgerald"])
        res = g.check_named_entity_relationships(
            EXAMPLE_B, "Cap d'Antibes", [], api_key="x", llm_fn=stub,
        )
        names = [u['entity'] for u in res['ungrounded']]
        self.assertIn("Scott Fitzgerald", names, res)

    def test_grounded_relationship_not_flagged(self):
        grounded = (
            "Fitzgerald wrote Tender Is the Night while staying at the Hôtel du "
            "Cap at the far end of this headland."
        )
        stub = make_relationship_stub([])  # everything GROUNDED
        res = g.check_named_entity_relationships(
            grounded, "Cap d'Antibes", [], api_key="x", llm_fn=stub,
        )
        self.assertEqual(res['ungrounded'], [], res)

    def test_detects_the_entity_deterministically(self):
        ents = g._detect_named_entities(EXAMPLE_B, "Cap d'Antibes", [])
        self.assertIn("Scott Fitzgerald", ents)

    def test_geography_and_structures_not_treated_as_persons(self):
        """French Riviera (region) and Saint-Pons Abbey (structure) are the
        setting, not name-dropped persons/works — they must not be detected as
        entities that need a stop-relationship."""
        ents_a = g._detect_named_entities(EXAMPLE_A, "Cap d'Antibes", [])
        self.assertNotIn("French Riviera", ents_a, ents_a)
        ents_c = g._detect_named_entities(CIMIEZ_MONASTERY, "Cimiez Monastery", [])
        self.assertNotIn("Saint-Pons Abbey", ents_c, ents_c)
        self.assertNotIn("Pons Abbey", ents_c, ents_c)

    def test_ac3_cimiez_has_no_ungrounded_entities(self):
        """AC3 (Part 2 side): the shipped Cimiez paragraph must not be flagged for
        any ungrounded named entity. With the geography/structure filter, no
        person/work candidates remain, so nothing is even sent to the model."""
        # A stub that would flag ANYTHING it were asked about — proving the
        # paragraph is clean because no entity is submitted, not because the
        # model happened to say GROUNDED.
        stub = make_relationship_stub(["Saint-Pons Abbey", "Pons Abbey", "Cimiez",
                                       "Franciscan", "Benedictine", "Savoy"])
        res = g.check_named_entity_relationships(
            CIMIEZ_MONASTERY, "Cimiez Monastery", SIBLINGS, api_key="x", llm_fn=stub,
        )
        self.assertEqual(res['ungrounded'], [], res)


class TestPart3ApplyToTour(unittest.TestCase):

    def _tour(self):
        # ≥2 siblings so the substitution test can reach HIGH confidence.
        return [
            {'name': 'Cap d\'Antibes',
             'description': EXAMPLE_A + "\n\n" + CIMIEZ_MONASTERY},
            {'name': 'Villa Leopolda',
             'description': "Something concrete and specific about Villa Leopolda in 1922."},
            {'name': 'Roman Ruins of Cemenelum',
             'description': "The amphitheatre at Cemenelum held 4,000 spectators in the 2nd century."},
        ]

    def test_ac1_removes_example_a_keeps_cimiez(self):
        """Example A removed (transferable/high); the specific paragraph kept."""
        spec = make_specificity_stub([
            (EXAMPLE_A[:40], "TRANSFERABLE"),
            (CIMIEZ_MONASTERY[:40], "SPECIFIC"),
        ])
        rel = make_relationship_stub([])
        stub = combined_stub(spec, rel)
        tour = self._tour()
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
        self.assertEqual(stats['paragraphs_removed'], 1, stats)
        self.assertNotIn("everyday paradise", tour[0]['description'])
        self.assertIn("Saint-Pons Abbey", tour[0]['description'])

    def test_never_empties_a_stop(self):
        """A stop whose ONLY paragraph is transferable/high is protected."""
        spec = make_specificity_stub([])  # everything TRANSFERABLE
        rel = make_relationship_stub([])
        stub = combined_stub(spec, rel)
        # ≥2 siblings so the verdict reaches HIGH — otherwise low-conf can't test the guard.
        tour = [
            {'name': 'Cap d\'Antibes', 'description': EXAMPLE_A},
            {'name': 'Villa Leopolda', 'description': "About Villa Leopolda in 1922."},
            {'name': 'Roman Ruins', 'description': "Cemenelum amphitheatre, 2nd century."},
        ]
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
        # Every stop here has a single paragraph that is high-transferable, so
        # each is protected and none is emptied.
        self.assertEqual(stats['last_paragraph_protected'], 3, stats)
        self.assertEqual(stats['paragraphs_removed'], 0, stats)
        self.assertTrue(tour[0]['description'].strip())

    def test_low_confidence_does_not_delete(self):
        """Only high-confidence transferable deletes (LOCAL-359). A single-sibling
        tour yields medium confidence at best → nothing removed."""
        spec = make_specificity_stub([])  # TRANSFERABLE
        rel = make_relationship_stub([])
        stub = combined_stub(spec, rel)
        tour = [
            {'name': 'A', 'description': EXAMPLE_A + "\n\nSecond paragraph here about A."},
            {'name': 'B', 'description': "About B."},
        ]
        # Only one sibling for stop A → medium confidence → kept.
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
        self.assertEqual(stats['paragraphs_removed'], 0, stats)
        self.assertGreaterEqual(stats['transferable_low_conf_kept'], 1, stats)


if __name__ == '__main__':
    unittest.main(verbosity=2)
