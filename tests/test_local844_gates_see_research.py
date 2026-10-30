#!/usr/bin/env python3
"""test_local844_gates_see_research.py — LOCAL-844 acceptance (unit level).

The defect, from the LOCAL-842 live run (reports/local842/live_run.log):

  Line 3225  story pass writes, from the LOCAL-840 per-work research passages
             (verbatim Rijksmuseum/Wikipedia text):
               "On 14 September 1975, Wilhelmus de Rijk, an unemployed school
                teacher, attacked The Night Watch with a bread knife…"
  Line 3368  LOCAL-652 flags "Wilhelmus de Rijk" as a FOREIGN work/artist (his
             name shares no token with the delivered titles/artists) and removes
             the sentence.
  Line 3370  LOCAL-472 reports "No concrete link between Wilhelmus de Rijk and
             The Night Watch is established" — on the sentence that says he
             attacked it.
  Line 1379  Manet's "The Salon jury … rejected the painting …" removed the same
             way.

Both gates were blind to the SAME research that produced the sentence. The fix:
both gates see this stop's per-work research passages as grounding evidence. An
entity NAMED in those passages, in connection with this work, is grounded.

The bar (ticket Do §4), all four demonstrated against the fixed functions (no
network, no key; the LLM is injected to reproduce the live UNGROUNDED verdict):

  1. The exact Night Watch + Manet sentences WITH their passages → KEPT.
  2. The same sentences WITHOUT the passages → STILL REMOVED (today's behaviour).
  3. A foreign-painting sentence (an artwork on no stop, named in no passage) →
     STILL REMOVED, even when passages are present for the real work.
  4. No fabrication risk added: an entity in NO passage is judged exactly as
     today — the passage set only ever GROUNDS a name that actually appears in it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_specificity_gate as ssg


# ── The exact live sentences ──────────────────────────────────────────────────

NIGHT_WATCH_STORY = (
    "On 14 September 1975, Wilhelmus de Rijk, an unemployed school teacher, "
    "attacked The Night Watch with a bread knife, slashing several large "
    "zig-zagged cuts into the canvas before he was restrained."
)

MANET_STORY = (
    "The Salon jury, including the critic Charles Blanc, rejected the painting "
    "for this reason, leading to its display at the Salon des Refuses in 1863."
)

# Per-work research passages (LOCAL-840 museum_work_research output): verbatim
# Wikipedia-style event passages for THESE works. The attacker and the jury are
# named here, in connection with the work — this is the grounding evidence the
# gates were blind to.
NIGHT_WATCH_PASSAGES = [
    "In 1975 an unemployed schoolteacher named Wilhelmus de Rijk slashed the "
    "painting with a knife; the zig-zag cuts were later restored.",
    "During the Second World War The Night Watch was rolled onto a cylinder and "
    "evacuated from the Rijksmuseum to a bunker for safekeeping.",
]

MANET_PASSAGES = [
    "The painting was rejected by the jury of the 1863 Salon, where the critic "
    "Charles Blanc sat, and was shown instead at the Salon des Refuses.",
    "Manet's work provoked scandal and mockery when it was first exhibited.",
]

# A delivered Rijks tour. Artists are blank on the two story stops exactly as in
# the live run (work_identity_chars=0), so the delivered-grounding for those
# stops comes only from the titles — which is why the attacker's name looks
# "foreign" without the passages.
POI_NAMES = ["The Night Watch", "Luncheon on the Grass", "The Milkmaid"]
POI_ARTISTS = ["", "Edouard Manet", "Johannes Vermeer"]


def _ungrounded_llm(prompt, key, model=None):
    """Reproduce the live model: every detected entity is judged UNGROUNDED by
    the relationship check (that is the verdict that deleted the real stories),
    and every paragraph is SPECIFIC on the substitution test (so only the
    foreign-entity path can remove a sentence — isolating the LOCAL-652/472
    grounding behaviour under test)."""
    if 'VERDICT: GROUNDED | UNGROUNDED' in prompt:
        return "VERDICT: UNGROUNDED\nREASON: no concrete link stated"
    if 'VERDICT: SPECIFIC | TRANSFERABLE' in prompt:
        return "VERDICT: SPECIFIC\nREASON: concrete"
    return None


class TestEntityGroundedByPassagesHelper(unittest.TestCase):
    """The pure helper: an entity is grounded only when ALL its distinctive
    tokens appear in the passages."""

    def test_attacker_grounded_when_named_in_passages(self):
        toks = ssg._passage_grounding_tokens(NIGHT_WATCH_PASSAGES)
        self.assertTrue(ssg._entity_grounded_by_passages("Wilhelmus de Rijk", toks))

    def test_jury_critic_grounded_when_named_in_passages(self):
        toks = ssg._passage_grounding_tokens(MANET_PASSAGES)
        self.assertTrue(ssg._entity_grounded_by_passages("Charles Blanc", toks))

    def test_absent_name_not_grounded(self):
        toks = ssg._passage_grounding_tokens(NIGHT_WATCH_PASSAGES)
        self.assertFalse(ssg._entity_grounded_by_passages("Vincent van Gogh", toks))

    def test_no_passages_grounds_nothing(self):
        self.assertFalse(ssg._entity_grounded_by_passages("Wilhelmus de Rijk", set()))

    def test_partial_token_overlap_not_grounded(self):
        """A shared common token alone must not ground an unrelated name — ALL
        distinctive tokens must appear."""
        toks = ssg._passage_grounding_tokens(
            ["Wilhelmus arrived at the museum in 1975."])
        # 'Wilhelmus' is present but 'Rijk' is not → not grounded.
        self.assertFalse(ssg._entity_grounded_by_passages("Wilhelmus de Rijk", toks))


class TestRelationshipCheckSeesPassages(unittest.TestCase):
    """LOCAL-472 Part 2: a passage-grounded entity is never flagged ungrounded."""

    def test_de_rijk_grounded_by_passages(self):
        res = ssg.check_named_entity_relationships(
            NIGHT_WATCH_STORY, "The Night Watch", [], api_key="x",
            llm_fn=_ungrounded_llm, work_research_passages=NIGHT_WATCH_PASSAGES,
        )
        self.assertIn("Wilhelmus de Rijk", res['passage_grounded'])
        self.assertEqual(res['ungrounded'], [], res)

    def test_de_rijk_ungrounded_without_passages(self):
        """Exact same sentence, no passages → the live UNGROUNDED verdict stands."""
        res = ssg.check_named_entity_relationships(
            NIGHT_WATCH_STORY, "The Night Watch", [], api_key="x",
            llm_fn=_ungrounded_llm, work_research_passages=[],
        )
        names = [u['entity'] for u in res['ungrounded']]
        self.assertIn("Wilhelmus de Rijk", names, res)
        self.assertEqual(res['passage_grounded'], [], res)


class TestNightWatchSurvivesEndToEnd(unittest.TestCase):
    """Bar items 1 + 2 for the Night Watch."""

    # The story sentence sits in a multi-sentence paragraph, exactly as in the
    # live run — so the never-empty-a-paragraph guard does not itself protect it;
    # only the grounding evidence does.
    DESC = (
        "The Night Watch dramatizes civic pride through light and movement. "
        + NIGHT_WATCH_STORY +
        " Today the painting hangs in its own gallery at the Rijksmuseum."
    )

    def _poi_list(self, with_passages):
        pl = [
            {"name": POI_NAMES[0], "artist": POI_ARTISTS[0],
             "description": self.DESC},
            {"name": POI_NAMES[1], "artist": POI_ARTISTS[1],
             "description": "Manet painted Luncheon on the Grass in 1863."},
            {"name": POI_NAMES[2], "artist": POI_ARTISTS[2],
             "description": "The Milkmaid shows a servant pouring milk."},
        ]
        if with_passages:
            pl[0]["_wsr_passages"] = NIGHT_WATCH_PASSAGES
        return pl

    def test_kept_with_passages(self):
        pl = self._poi_list(with_passages=True)
        stats = ssg.apply_stop_specificity_gate(pl, api_key="x", llm_fn=_ungrounded_llm)
        self.assertIn("Wilhelmus de Rijk", pl[0]["description"],
                      "the sourced Night Watch attack must survive when its "
                      "research passages are present")
        self.assertEqual(stats['foreign_entity_sentences_removed'], 0, stats)
        self.assertGreaterEqual(stats['passage_grounded_entities'], 1, stats)

    def test_removed_without_passages(self):
        pl = self._poi_list(with_passages=False)
        stats = ssg.apply_stop_specificity_gate(pl, api_key="x", llm_fn=_ungrounded_llm)
        self.assertNotIn("Wilhelmus de Rijk", pl[0]["description"],
                         "without passages, today's behaviour is unchanged — the "
                         "sentence is still removed")
        self.assertGreaterEqual(stats['foreign_entity_sentences_removed'], 1, stats)
        # The surrounding real sentences survive.
        self.assertIn("civic pride", pl[0]["description"])


class TestManetSurvivesEndToEnd(unittest.TestCase):
    """Bar items 1 + 2 for Manet's Salon rejection."""

    DESC = (
        "Luncheon on the Grass placed a nude among clothed men in a park. "
        + MANET_STORY +
        " The composition borrows its poses from a Renaissance engraving."
    )

    def _poi_list(self, with_passages):
        pl = [
            {"name": POI_NAMES[1], "artist": POI_ARTISTS[1],
             "description": self.DESC},
            {"name": POI_NAMES[0], "artist": POI_ARTISTS[0],
             "description": "The Night Watch is by Rembrandt."},
        ]
        if with_passages:
            pl[0]["_wsr_passages"] = MANET_PASSAGES
        return pl

    def test_kept_with_passages(self):
        pl = self._poi_list(with_passages=True)
        stats = ssg.apply_stop_specificity_gate(pl, api_key="x", llm_fn=_ungrounded_llm)
        self.assertIn("Charles Blanc", pl[0]["description"],
                      "Manet's sourced Salon-rejection sentence must survive with "
                      "its passages")
        self.assertEqual(stats['foreign_entity_sentences_removed'], 0, stats)

    def test_removed_without_passages(self):
        pl = self._poi_list(with_passages=False)
        stats = ssg.apply_stop_specificity_gate(pl, api_key="x", llm_fn=_ungrounded_llm)
        self.assertNotIn("Charles Blanc", pl[0]["description"],
                         "without passages, the sentence is still removed")
        self.assertGreaterEqual(stats['foreign_entity_sentences_removed'], 1, stats)


class TestForeignPaintingStillRemoved(unittest.TestCase):
    """Bar item 3: the real protection is kept. A foreign work/artist named in NO
    passage is still removed, EVEN when real passages are present for this stop."""

    def test_foreign_callback_removed_with_passages_present(self):
        # A real, passage-grounded sentence PLUS a phantom cross-stop callback to
        # a foreign work/artist (Vigee Le Brun / Straw Hat) that appears in NO
        # passage. Only the foreign sentence must go.
        desc = (
            NIGHT_WATCH_STORY + " "
            "This echoes the calculated self-presentation of Vigee Le Brun's "
            "Self Portrait in a Straw Hat from your earlier stop."
        )
        pl = [
            {"name": POI_NAMES[0], "artist": POI_ARTISTS[0], "description": desc,
             "_wsr_passages": NIGHT_WATCH_PASSAGES},
            {"name": POI_NAMES[2], "artist": POI_ARTISTS[2],
             "description": "The Milkmaid shows a servant pouring milk."},
        ]
        stats = ssg.apply_stop_specificity_gate(pl, api_key="x", llm_fn=_ungrounded_llm)
        new = pl[0]["description"]
        # The foreign sentence is gone …
        self.assertNotIn("Vigee Le Brun", new, new)
        self.assertNotIn("Straw Hat", new, new)
        # … but the real, passage-grounded story survives.
        self.assertIn("Wilhelmus de Rijk", new, new)
        self.assertGreaterEqual(stats['foreign_entity_sentences_removed'], 1, stats)

    def test_foreign_painting_removed_even_with_unrelated_passages(self):
        """A foreign painting whose tokens are in no passage is removed; passages
        for a different work do not accidentally ground it (no fabrication risk)."""
        toks = ssg._passage_grounding_tokens(NIGHT_WATCH_PASSAGES)
        self.assertFalse(
            ssg._entity_grounded_by_passages("Self Portrait in a Straw Hat", toks))


if __name__ == "__main__":
    unittest.main(verbosity=2)
