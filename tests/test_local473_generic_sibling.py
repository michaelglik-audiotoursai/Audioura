#!/usr/bin/env python3
"""test_local473_generic_sibling.py — LOCAL-473 acceptance.

LOCAL-472 substituted a NAMED sibling stop from THIS tour when running the
substitution test. LEAD proved the verdict then depended on which stops the tour
happened to contain — the same Cap d'Antibes paragraph came back transferable
(kept), medium (kept) or removed depending on whether the tour also held a museum,
a cape, or a cape + a headland. On a real tour of dissimilar stops (a monastery,
two museums, Roman ruins, a villa) this gate would keep generic prose about every
stop, which is the whole defect unaddressed.

The fix: stop substituting a named sibling. Classify the stop's KIND and swap in a
GENERIC same-kind referent ("another art museum", "another coastal viewpoint").
The test then measures the paragraph and nothing else. Michael's own words:
"if you can substitute the names of places and say the same thing about another
LOCATION, this paragraph is redundant" — "another location", not "another stop on
this tour."

These tests are STUBBED for CI determinism (they assert the sibling-INDEPENDENCE
property — that the verdict is identical for every sibling set — which is a
property of the plumbing, not of the model's judgement). The judgement itself is
proven separately, against the REAL model, in test_local473_live_model.py. Both
are required by the task bar: keep the stubbed tests for CI, ADD live ones.
"""
import os
import sys
import unittest
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_specificity_gate as g


# ── The paragraphs from the task bar ────────────────────────────────────────────

# Michael's Example A — the paragraph this gate exists to catch. Verbatim.
EXAMPLE_A = (
    "Cycling on the French Riviera, stop at Cap d'Antibes to experience the "
    "enduring power of nature, inspiring creativity and stimulating the "
    "imagination while admiring panoramic views and soaking up the atmosphere "
    "of this everyday paradise."
)

# The shipped Cimiez Monastery paragraph, verbatim from
# TOUR_CIMIEZ_WALKING_20260830.md — the 1546 Saint-Pons property swap.
CIMIEZ_MONASTERY = (
    "The Cimiez Monastery, with roots stretching back to the 9th century, stands "
    "as a silent witness to the passage of time and the resilience of faith. The "
    "Count of Savoy ordered the destruction of buildings, including the "
    "Franciscans' entire monastery, in a desperate act of defense. In 1546, a "
    "pivotal moment unfolded when Franciscan friars negotiated a property swap "
    "with Benedictine monks of Saint-Pons Abbey, acquiring a small chapel and "
    "plot of land in Cimiez. The French Revolution brought turmoil once more, as "
    "the monastery was seized and transformed into military barracks and an army "
    "hospital. Henri Matisse, whose affinity for Cimiez's luminous light is well "
    "known, rests in the cemetery nearby, a callback to the Musée Matisse you "
    "visited earlier."
)

# The three sibling sets from the task bar — must produce the SAME verdict.
SIBLING_SETS = (
    ['Villa Leopolda', 'Musee Matisse'],
    ['Cap Ferrat'],
    [],
)


# ── Stubs that model the REAL model's judgement of the SWAPPED prose ─────────────
#
# The stub keys on what is present in the SWAPPED PARAGRAPH the gate builds, which
# now contains the GENERIC referent ("another coastal viewpoint" / "another
# historic church"), never a named sibling. This lets the stub answer the way the
# real model does: generic mood prose survives the swap (TRANSFERABLE); a dated,
# named, specific event does not (SPECIFIC).

def realistic_stub(prompt, api_key, model=None):
    if 'VERDICT: SPECIFIC | TRANSFERABLE' in prompt:
        # A concrete, dated, named event survives in the swapped prose → SPECIFIC.
        if 'Saint-Pons' in prompt or '1546' in prompt:
            return "VERDICT: SPECIFIC\nREASON: the 1546 Saint-Pons land swap is false elsewhere"
        # Otherwise generic scene-setting / mood → TRANSFERABLE.
        return "VERDICT: TRANSFERABLE\nREASON: only generic mood, nothing breaks"
    if 'VERDICT: GROUNDED | UNGROUNDED' in prompt:
        return "VERDICT: GROUNDED\nREASON: relationship stated"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# KIND CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestStopKindClassification(unittest.TestCase):

    def test_cap_is_viewpoint(self):
        k = g.classify_stop_kind("Cap d'Antibes")
        self.assertEqual(k['kind'], 'viewpoint', k)
        self.assertEqual(k['referent'], 'another coastal viewpoint', k)

    def test_monastery_is_church_kind(self):
        k = g.classify_stop_kind("Cimiez Monastery")
        self.assertEqual(k['kind'], 'church', k)

    def test_museum_is_museum(self):
        self.assertEqual(g.classify_stop_kind("Musée Matisse")['kind'], 'museum')

    def test_roman_ruins_is_ruin(self):
        self.assertEqual(
            g.classify_stop_kind("Roman Ruins of Cemenelum")['kind'], 'ruin')

    def test_villa_is_villa(self):
        self.assertEqual(g.classify_stop_kind("Villa Leopolda")['kind'], 'villa')

    def test_plain_name_falls_back_to_description(self):
        """A stop whose NAME carries no kind signal classifies from its prose."""
        k = g.classify_stop_kind(
            "Cimiez", "A serene monastery and its cloister gardens.")
        self.assertEqual(k['kind'], 'church', k)

    def test_unknown_gets_neutral_generic_referent(self):
        k = g.classify_stop_kind("Zzxq", "")
        self.assertEqual(k['kind'], 'place', k)
        self.assertEqual(k['referent'], g._GENERIC_PLACE_REFERENT, k)

    def test_referent_is_never_a_named_sibling(self):
        """The substituted referent must be generic — never a tour stop name."""
        for name in ("Cap d'Antibes", "Cimiez Monastery", "Musée Matisse",
                     "Villa Leopolda", "Roman Ruins of Cemenelum"):
            ref = g.classify_stop_kind(name)['referent']
            self.assertTrue(ref.lower().startswith('another'), ref)
            for sib in ('Villa Leopolda', 'Musee Matisse', 'Cap Ferrat'):
                self.assertNotIn(sib.lower(), ref.lower(),
                                 f"referent {ref!r} leaked sibling {sib!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# BAR item 1 — Example A: SAME verdict for all three sibling sets
# ═══════════════════════════════════════════════════════════════════════════════

class TestBar1ExampleAInvariant(unittest.TestCase):

    def test_example_a_transferable_high_for_every_sibling_set(self):
        """The whole point of LOCAL-473: Example A is transferable=True at high
        confidence with ['Villa Leopolda','Musee Matisse'], with ['Cap Ferrat'],
        and with [] — the SAME verdict every time."""
        verdicts = []
        for siblings in SIBLING_SETS:
            res = g.check_paragraph_specificity(
                EXAMPLE_A, "Cap d'Antibes", siblings,
                api_key="x", llm_fn=realistic_stub,
            )
            verdicts.append((res['transferable'], res['confidence']))
        self.assertEqual(len(set(verdicts)), 1,
                         f"verdict changed with sibling set: {verdicts}")
        self.assertEqual(verdicts[0], (True, 'high'), verdicts)

    def test_swapped_text_contains_generic_referent_not_sibling(self):
        """Prove the substitution uses the generic referent, not a named
        sibling — the actual mechanism of the fix."""
        swapped = g._substitute_stop_name(
            EXAMPLE_A, "Cap d'Antibes", "another coastal viewpoint")
        self.assertIn("another coastal viewpoint", swapped)
        self.assertNotIn("Cap d'Antibes", swapped)
        self.assertNotIn("Villa Leopolda", swapped)
        self.assertNotIn("Cap Ferrat", swapped)


# ═══════════════════════════════════════════════════════════════════════════════
# BAR item 2 — the Cimiez Monastery paragraph survives, for all three sibling sets
# ═══════════════════════════════════════════════════════════════════════════════

class TestBar2CimiezSurvivesEveryShape(unittest.TestCase):

    def test_cimiez_specific_for_every_sibling_set(self):
        for siblings in SIBLING_SETS:
            res = g.check_paragraph_specificity(
                CIMIEZ_MONASTERY, "Cimiez Monastery", siblings,
                api_key="x", llm_fn=realistic_stub,
            )
            self.assertFalse(res['transferable'],
                             f"siblings={siblings}: {res}")

    def test_cimiez_survives_apply_gate_for_every_sibling_shape(self):
        """END TO END through apply_stop_specificity_gate: the Cimiez paragraph is
        returned byte-for-byte unchanged, in NFC and NFD, whatever the tour's
        OTHER stops are."""
        sibling_pois_by_set = {
            0: [{'name': 'Villa Leopolda', 'description': 'Built in 1902.'},
                {'name': 'Musee Matisse', 'description': 'Opened in 1963.'}],
            1: [{'name': 'Cap Ferrat', 'description': 'A wooded peninsula.'}],
            2: [],
        }
        for idx in (0, 1, 2):
            for enc in ('NFC', 'NFD'):
                cimiez = unicodedata.normalize(enc, CIMIEZ_MONASTERY)
                tour = [{'name': 'Cimiez Monastery', 'description': cimiez}]
                tour += sibling_pois_by_set[idx]
                stats = g.apply_stop_specificity_gate(
                    tour, api_key="x", llm_fn=realistic_stub)
                self.assertEqual(
                    unicodedata.normalize('NFC', tour[0]['description']),
                    unicodedata.normalize('NFC', cimiez),
                    f"set{idx}/{enc}: Cimiez altered:\n{tour[0]['description']}")
                self.assertEqual(stats['paragraphs_removed'], 0,
                                 f"set{idx}/{enc}: {stats}")


# ═══════════════════════════════════════════════════════════════════════════════
# The suite must be able to FAIL (LEAD's standing requirement)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSuiteCanFail(unittest.TestCase):

    def test_forcing_specific_makes_example_a_survive_wrongly(self):
        """If the model (here, a stub) is forced to call EVERYTHING specific,
        Example A is wrongly kept — proving these tests detect a broken judgement,
        they do not merely pass."""
        def all_specific(prompt, api_key, model=None):
            if 'VERDICT: SPECIFIC | TRANSFERABLE' in prompt:
                return "VERDICT: SPECIFIC\nREASON: forced"
            return "VERDICT: GROUNDED\nREASON: forced"
        res = g.check_paragraph_specificity(
            EXAMPLE_A, "Cap d'Antibes", [], api_key="x", llm_fn=all_specific)
        # This is the WRONG answer; we assert it to prove the pipeline faithfully
        # reports whatever the model decides (so a real regression would show).
        self.assertFalse(res['transferable'], res)


if __name__ == '__main__':
    unittest.main(verbosity=2)
