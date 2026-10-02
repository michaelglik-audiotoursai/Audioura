#!/usr/bin/env python3
"""test_local472_stop_specificity.py — LOCAL-472 acceptance (unit level).

Supersedes test_local469_stop_specificity.py. These tests CALL the gate
functions; they do not grep source for a marker string (D418/D421). The LLM is
injected via `llm_fn` so the logic is exercised deterministically, no network,
no key.

The bar LEAD set for LOCAL-472 (all three, demonstrated):
  1. Whole names only — no truncation, including an accented multi-word venue
     name, in BOTH NFC and NFD encoding (D243 accent folding is where 469 broke).
  2. The Cimiez Monastery paragraph survives END TO END (the full
     check_paragraph_specificity path), unchanged.
  3. Michael's Cap d'Antibes example is still caught (transferable/high).

Plus the conservative-removal invariants (LOCAL-359 + never-empty-a-stop) and a
proof the detector has exactly one definition (Defect 2).

This suite is designed to FAIL if the detector regresses: test_detector_can_fail
documents the failure mode LEAD caught, and the accent tests go red the moment
`_norm`/NFC handling is removed.
"""
import os
import sys
import unittest
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_specificity_gate as g


# ── Example paragraphs ──────────────────────────────────────────────────────────

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

# The real shipped paragraph — Cimiez Monastery, verbatim from
# TOUR_CIMIEZ_WALKING_20260830.md. Names a date (1546), a named party
# (Saint-Pons Abbey) and an event (the property swap) true of nowhere else.
# It also names "Musée Matisse" — the accented venue name 469 truncated.
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

SIBLINGS = ["Villa Leopolda", "Roman Ruins of Cemenelum", "Musée Marc Chagall"]


# ── Stub LLMs — deterministic stand-ins for the model ───────────────────────────

def make_specificity_stub(verdict_by_substring):
    """Return an llm_fn that answers the substitution-test prompt based on
    substrings found in the SWAPPED PARAGRAPH."""
    def _fn(prompt, api_key, model=None):
        if 'VERDICT: SPECIFIC | TRANSFERABLE' not in prompt:
            return None
        for needle, verdict in verdict_by_substring:
            if needle in prompt:
                return f"VERDICT: {verdict}\nREASON: stub"
        return "VERDICT: TRANSFERABLE\nREASON: stub default"
    return _fn


def make_relationship_stub(ungrounded_entities):
    """Any entity in `ungrounded_entities` → UNGROUNDED, else GROUNDED."""
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


# A stub that models the real Cimiez verdict: the 1546 Saint-Pons swap breaks on
# any sibling → SPECIFIC. Nothing else present makes it transferable.
def cimiez_specificity_stub():
    return make_specificity_stub([
        ("Saint-Pons", "SPECIFIC"),
        ("1546", "SPECIFIC"),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — exactly one _detect_named_entities definition
# ═══════════════════════════════════════════════════════════════════════════════

class TestDefect2SingleDefinition(unittest.TestCase):

    def test_detector_defined_exactly_once(self):
        """LOCAL-469 defined _detect_named_entities twice; the first copy had a
        truncated body and was silently shadowed. Prove there is exactly one."""
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'stop_specificity_gate.py')
        with open(src_path, encoding='utf-8') as f:
            src = f.read()
        n = src.count('def _detect_named_entities(')
        self.assertEqual(n, 1,
                         f'expected exactly one _detect_named_entities def, found {n}')

    def test_detector_returns_a_list(self):
        """A shadowed truncated def returned None; the live one returns a list."""
        out = g._detect_named_entities("Henri Matisse painted here.", "Some Stop", [])
        self.assertIsInstance(out, list)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 1 (the bar, item 1) — whole names only, no truncation, accent-robust
# ═══════════════════════════════════════════════════════════════════════════════

class TestBar1WholeNamesNoTruncation(unittest.TestCase):

    def test_accented_multiword_venue_name_is_whole_nfc(self):
        """'Musée Matisse' must be detected WHOLE (not 'Musée Mati') — NFC."""
        text = unicodedata.normalize('NFC',
            "Henri Matisse lived here; the Musée Matisse displays his work.")
        ents = g._detect_named_entities(text, "Cimiez Monastery", [])
        self.assertIn("Musée Matisse", ents, ents)
        self.assertNotIn("Musée Mati", ents, ents)

    def test_accented_multiword_venue_name_is_whole_nfd(self):
        """The macOS/NFD (decomposed é) form is exactly where 469 truncated.
        This is the regression test for D243. Remove `_norm`/NFC and it goes red.
        """
        text = unicodedata.normalize('NFD',
            "Henri Matisse lived here; the Musée Matisse displays his work.")
        ents = g._detect_named_entities(text, "Cimiez Monastery", [])
        self.assertIn("Musée Matisse", ents, ents)
        self.assertNotIn("Musée Mati", ents, ents)

    def test_no_detected_entity_is_a_truncated_fragment(self):
        """General guard: every detected entity, once accent-folded, is a whole
        word-sequence present in the (folded) source — never a mid-word cut."""
        for enc in ('NFC', 'NFD'):
            text = unicodedata.normalize(enc, CIMIEZ_MONASTERY)
            ents = g._detect_named_entities(text, "Cimiez Monastery", SIBLINGS)
            folded_src = g._fold(text).lower()
            for e in ents:
                self.assertIn(g._fold(e).lower(), folded_src,
                              f"{enc}: detected entity {e!r} is not a whole "
                              f"substring of the source (truncated?)")

    def test_detector_can_fail(self):
        """The suite must be able to fail (LEAD's requirement). This asserts the
        POSITIVE behaviour that the old broken regex path violated: feeding NFD
        text through the *unnormalized* regex truncates 'Musée Matisse'. Our fix
        (`_norm`) prevents that; this documents the exact failure and proves the
        test would catch a regression if `_norm` were removed."""
        import re as _re
        nfd = unicodedata.normalize('NFD', "the Musée Matisse displays")
        # Simulate the pre-fix code path: regex straight over NFD text.
        raw = [m.group(1) for m in g._PERSON_PATTERN.finditer(nfd)]
        self.assertNotIn("Musée Matisse", raw,
            "pre-fix path unexpectedly kept the whole name — the test can no "
            "longer distinguish fixed from broken")
        # The fixed detector recovers the whole name from the same NFD input.
        fixed = g._detect_named_entities(nfd, "Cimiez Monastery", [])
        self.assertIn("Musée Matisse", fixed, fixed)


# ═══════════════════════════════════════════════════════════════════════════════
# BAR item 2 — the Cimiez Monastery paragraph survives END TO END
# ═══════════════════════════════════════════════════════════════════════════════

class TestBar2CimiezSurvivesEndToEnd(unittest.TestCase):

    def test_cimiez_paragraph_is_specific_not_transferable(self):
        """Full check_paragraph_specificity path: the 1546 Saint-Pons swap is
        false of any other stop → SPECIFIC → not transferable."""
        res = g.check_paragraph_specificity(
            CIMIEZ_MONASTERY, "Cimiez Monastery", SIBLINGS,
            api_key="x", llm_fn=cimiez_specificity_stub(),
        )
        self.assertFalse(res['transferable'], res)

    def test_cimiez_survives_apply_gate_unchanged(self):
        """END TO END through apply_stop_specificity_gate: the Cimiez paragraph
        is returned byte-for-byte unchanged (in both NFC and NFD input)."""
        for enc in ('NFC', 'NFD'):
            cimiez = unicodedata.normalize(enc, CIMIEZ_MONASTERY)
            tour = [
                {'name': 'Cimiez Monastery', 'description': cimiez},
                {'name': 'Villa Leopolda',
                 'description': 'Villa Leopolda was built in 1902.'},
                {'name': 'Roman Ruins of Cemenelum',
                 'description': 'The amphitheatre held 4,000 spectators.'},
            ]
            spec = cimiez_specificity_stub()
            rel = make_relationship_stub([])  # any entity found → GROUNDED
            stub = combined_stub(spec, rel)
            stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
            # The paragraph is unchanged (allowing for NFC normalization the gate
            # applies on split — compare in NFC).
            self.assertEqual(
                unicodedata.normalize('NFC', tour[0]['description']),
                unicodedata.normalize('NFC', cimiez),
                f"{enc}: Cimiez paragraph was altered:\n{tour[0]['description']}")
            self.assertEqual(stats['paragraphs_removed'], 0, stats)
            self.assertEqual(stats['stops_affected'], 0, stats)

    def test_cimiez_has_no_ungrounded_entities(self):
        """The shipped Cimiez paragraph must not be flagged for any ungrounded
        entity. The detector must find its real persons (Henri Matisse, Musée
        Matisse) as WHOLE names and the model (stub) grounds them; the setting
        (Saint-Pons Abbey, French Revolution) is filtered out entirely."""
        for enc in ('NFC', 'NFD'):
            cimiez = unicodedata.normalize(enc, CIMIEZ_MONASTERY)
            # A stub that GROUNDS the real persons but would flag setting terms if
            # they were (wrongly) submitted.
            stub = make_relationship_stub(["Saint-Pons Abbey", "Pons Abbey",
                                           "French Revolution", "Savoy"])
            res = g.check_named_entity_relationships(
                cimiez, "Cimiez Monastery", SIBLINGS, api_key="x", llm_fn=stub,
            )
            self.assertEqual(res['ungrounded'], [], f"{enc}: {res}")
            # And the setting terms were never treated as name-dropped entities.
            self.assertNotIn("Saint-Pons Abbey", res['entities'], res)
            self.assertNotIn("Pons Abbey", res['entities'], res)


# ═══════════════════════════════════════════════════════════════════════════════
# BAR item 3 — Michael's Cap d'Antibes example is still caught
# ═══════════════════════════════════════════════════════════════════════════════

class TestBar3CapDAntibesStillCaught(unittest.TestCase):

    def test_example_a_is_transferable_high(self):
        """Example A — nothing breaks when the place name is swapped, so the
        model returns TRANSFERABLE for every sibling → high confidence."""
        stub = make_specificity_stub([])  # default TRANSFERABLE for all
        res = g.check_paragraph_specificity(
            EXAMPLE_A, "Cap d'Antibes", SIBLINGS, api_key="x", llm_fn=stub,
        )
        self.assertTrue(res['transferable'], res)
        self.assertEqual(res['confidence'], 'high', res)

    def test_example_a_removed_end_to_end(self):
        """Through apply_stop_specificity_gate, Example A is removed while a
        specific sibling paragraph beside it survives."""
        spec = make_specificity_stub([
            (EXAMPLE_A[:40], "TRANSFERABLE"),
            ("Saint-Pons", "SPECIFIC"),
            ("1546", "SPECIFIC"),
        ])
        rel = make_relationship_stub([])
        stub = combined_stub(spec, rel)
        tour = [
            {'name': "Cap d'Antibes",
             'description': EXAMPLE_A + "\n\n" + CIMIEZ_MONASTERY},
            {'name': 'Villa Leopolda',
             'description': 'Villa Leopolda was built in 1902.'},
            {'name': 'Roman Ruins of Cemenelum',
             'description': 'The amphitheatre held 4,000 spectators.'},
        ]
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
        self.assertEqual(stats['paragraphs_removed'], 1, stats)
        self.assertNotIn("everyday paradise", tour[0]['description'])
        self.assertIn("Saint-Pons Abbey", tour[0]['description'])

    def test_example_b_flags_fitzgerald(self):
        """Example B names Scott Fitzgerald with no stated relationship."""
        stub = make_relationship_stub(["Scott Fitzgerald"])
        res = g.check_named_entity_relationships(
            EXAMPLE_B, "Cap d'Antibes", [], api_key="x", llm_fn=stub,
        )
        names = [u['entity'] for u in res['ungrounded']]
        self.assertIn("Scott Fitzgerald", names, res)


# ═══════════════════════════════════════════════════════════════════════════════
# Conservative removal (LOCAL-359 + never-empty-a-stop)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConservativeRemoval(unittest.TestCase):

    def test_failsafe_no_model(self):
        """No api_key and no llm_fn ⇒ never transferable, low confidence."""
        res = g.check_paragraph_specificity(
            EXAMPLE_A, "Cap d'Antibes", SIBLINGS, api_key=None, llm_fn=None,
        )
        self.assertFalse(res['transferable'])
        self.assertEqual(res['confidence'], 'low')

    def test_only_high_confidence_deletes(self):
        """Only high-confidence transferable deletes (LOCAL-359). A verdict that
        the model cannot produce (returns None → low confidence) must never
        delete, even for a paragraph that would otherwise be transferable.

        [LOCAL-473] The old form of this test asserted "single-sibling tour →
        medium confidence → nothing removed". That premise was the defect: the
        verdict must NOT depend on how many siblings the tour has. Confidence is
        now driven by the model verdict, not sibling count, so we exercise the
        LOCAL-359 rule via the no-verdict (low-confidence) path instead."""
        def no_verdict_stub(prompt, api_key, model=None):
            # Model declines to answer the substitution prompt → low confidence.
            if 'VERDICT: SPECIFIC | TRANSFERABLE' in prompt:
                return None
            return "VERDICT: GROUNDED\nREASON: link stated"
        tour = [
            {'name': 'A', 'description': EXAMPLE_A + "\n\nSecond paragraph about A."},
            {'name': 'B', 'description': "About B."},
        ]
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=no_verdict_stub)
        self.assertEqual(stats['paragraphs_removed'], 0, stats)

    def test_verdict_independent_of_sibling_count(self):
        """[LOCAL-473] The core requirement: a transferable paragraph gets the
        SAME verdict and confidence whether the tour has 0, 1 or many siblings.
        This is the property LOCAL-472 lacked (verdict flipped on sibling count)."""
        spec = make_specificity_stub([])  # TRANSFERABLE for every swap
        results = []
        for siblings in ([], ["Only One Sibling"],
                         ["Villa Leopolda", "Musee Matisse", "Cap Ferrat"]):
            res = g.check_paragraph_specificity(
                EXAMPLE_A, "Cap d'Antibes", siblings, api_key="x", llm_fn=spec,
            )
            results.append((res['transferable'], res['confidence']))
        self.assertEqual(len(set(results)), 1,
                         f"verdict changed with sibling count: {results}")
        self.assertEqual(results[0], (True, 'high'), results)

    def test_never_empties_a_stop(self):
        """A stop whose ONLY paragraph is transferable/high is protected."""
        spec = make_specificity_stub([])  # everything TRANSFERABLE
        rel = make_relationship_stub([])
        stub = combined_stub(spec, rel)
        tour = [
            {'name': "Cap d'Antibes", 'description': EXAMPLE_A},
            {'name': 'Villa Leopolda', 'description': "About Villa Leopolda in 1922."},
            {'name': 'Roman Ruins', 'description': "Cemenelum amphitheatre, 2nd century."},
        ]
        stats = g.apply_stop_specificity_gate(tour, api_key="x", llm_fn=stub)
        self.assertEqual(stats['last_paragraph_protected'], 3, stats)
        self.assertEqual(stats['paragraphs_removed'], 0, stats)
        for poi in tour:
            self.assertTrue(poi['description'].strip(), poi)


if __name__ == '__main__':
    unittest.main(verbosity=2)
