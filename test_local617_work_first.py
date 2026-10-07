#!/usr/bin/env python3
"""test_local617_work_first.py — LOCAL-617 unit tests.

Michael's ruling (2026-10-07): museum stops talk about the museum — donors,
acquisitions, renovations, provenance, the founding story — instead of the WORK,
the ARTIST, what critics said, and the human/emotional reading. The independent
critic scored tours 399, 403–417 at 2.5–4/10 with criterion-1 (work/artist, not
museum history) the dominant Critical/Major defect on every one.

These tests pin the deterministic work-first evidence layer:
  item 2 — the evidence classifier + snippet filter + stop-body enforcement
  item 3 — the narration contract prompt block
  item 4 — the attribution check (catalogue creator wins on mismatch)
  item 5 — fresh-path shortfall recompute on the FINAL delivered count
  item 6 — a conclusion/recap that names only delivered stops

Every sentence used here is drawn from, or modelled directly on, the real
critique defect tables for tours 414/415/416/417. Offline and deterministic.

Run: python3 -m pytest test_local617_work_first.py -q
"""
import unittest

import work_first_evidence as wf


# Real criterion-1 defect sentences from the critic (tours 414–417).
INSTITUTIONAL_SENTENCES = [
    "In 1919, Frizzoni bequeathed the painting to the Museo Correr.",
    "In 1830, Teodoro Correr passed away, leaving behind a significant legacy.",
    "Founded in 1927 by textile industry Baron Jan Bernard Van Heek, who donated his private collection.",
    "A 61.2 million euro renovation modernised the galleries.",
    "In 1811, the French State decided to redistribute works among regional museums.",
    "Peter S. Lynch gifted the painting to the museum in 2003.",
    "The museum's mission is to preserve and present European art.",
    "This ethos of generosity echoes in the museum's decision to loan the work to the national collection.",
    "Alexandre Du Mège, conservateur du musée from 1832 to 1862, assembled the collection.",
]

WORK_SENTENCES = [
    "The composition shows two Venetian ladies seated on a terrace, their gaze averted.",
    "Bellini renders the Madonna in muted blues, the light falling softly across her hands.",
    "In the foreground a child reaches toward a bowl of fruit, painted in thick impasto.",
]

ARTIST_SENTENCES = [
    "At this point in his life Carpaccio had just lost his main patron and was working alone.",
    "She painted this only months before her death, her hand already failing.",
]

RECEPTION_SENTENCES = [
    "The critic Roberto Longhi called it the most tender portrait of the Venetian school.",
    "Contemporaries described the work as scandalous when it was first shown.",
]

EMOTION_SENTENCES = [
    "You cannot help but feel the loneliness in the woman's downcast eyes.",
    "There is a quiet grief here, a stillness that invites you to pause.",
]


class TestClassifier(unittest.TestCase):
    def test_institutional_sentences_classified_institutional(self):
        for s in INSTITUTIONAL_SENTENCES:
            self.assertEqual(
                wf.classify_sentence(s, venue_tokens=["museum", "correr"]),
                "institutional", msg=f"not institutional: {s!r}")

    def test_work_sentences_not_institutional(self):
        for s in WORK_SENTENCES:
            self.assertEqual(wf.classify_sentence(s), "work", msg=s)

    def test_artist_sentences(self):
        for s in ARTIST_SENTENCES:
            self.assertIn(wf.classify_sentence(s), ("artist", "emotion"), msg=s)
        # the first is unambiguously artist-circumstance
        self.assertEqual(wf.classify_sentence(ARTIST_SENTENCES[0]), "artist")

    def test_reception_sentences(self):
        for s in RECEPTION_SENTENCES:
            self.assertEqual(wf.classify_sentence(s), "reception", msg=s)

    def test_emotion_sentences(self):
        for s in EMOTION_SENTENCES:
            self.assertEqual(wf.classify_sentence(s), "emotion", msg=s)

    def test_reception_outranks_incidental_institutional(self):
        # an attributed opinion that mentions the museum is still reception
        s = ("The historian wrote that the painting, long before it reached the "
             "museum, had already become legendary.")
        self.assertEqual(wf.classify_sentence(s), "reception")

    def test_work_description_not_stolen_by_museum_word(self):
        # describing the work with an incidental 'museum' word stays 'work'
        s = ("The canvas depicts a storm at sea, its palette darkened, now one of "
             "the museum's best-loved paintings.")
        self.assertIn(wf.classify_sentence(s), ("work", "artist", "reception", "emotion"))


class TestOwnAcquisition(unittest.TestCase):
    def test_own_acquisition_true(self):
        s = "This painting was gifted to the museum by Boris Fridman in 2003."
        self.assertTrue(wf.is_own_acquisition(s))

    def test_own_acquisition_with_deictic_it(self):
        s = "It entered the collection as a bequest in 1919."
        self.assertTrue(wf.is_own_acquisition(s))

    def test_founding_is_not_own_acquisition(self):
        s = "The museum was founded in 1927 by Baron Van Heek."
        self.assertFalse(wf.is_own_acquisition(s))

    def test_other_work_acquisition_not_this_work(self):
        s = "The museum acquired a Rembrandt the following decade."
        # no deictic for THIS work and no subject match → not own-acquisition
        self.assertFalse(wf.is_own_acquisition(s, work_subject="Two Venetian Ladies"))


class TestSnippetFilter(unittest.TestCase):
    def test_drops_pure_institutional_snippets(self):
        snippets = [
            {"title": "History", "snippet": INSTITUTIONAL_SENTENCES[2]},
            {"title": "Renovation", "snippet": INSTITUTIONAL_SENTENCES[3]},
            {"title": "The work", "snippet": WORK_SENTENCES[0]},
        ]
        kept, report = wf.filter_snippets_work_first(snippets)
        kept_text = " ".join(s["snippet"] for s in kept)
        self.assertIn(WORK_SENTENCES[0], kept_text)
        self.assertEqual(report["dropped_institutional"], 2)

    def test_keeps_one_own_acquisition_snippet(self):
        snippets = [
            {"title": "Gift", "snippet": "This painting was donated to the museum by Peter S. Lynch in 2003."},
            {"title": "Founding", "snippet": INSTITUTIONAL_SENTENCES[2]},
            {"title": "The work", "snippet": WORK_SENTENCES[1]},
        ]
        kept, report = wf.filter_snippets_work_first(snippets, work_subject="")
        self.assertTrue(report["kept_own_acquisition"])
        # founding (not own-acquisition) is dropped; work + one acquisition kept
        self.assertEqual(len(kept), 2)


class TestStopBodyFilter(unittest.TestCase):
    def test_strips_institutional_keeps_one_acquisition(self):
        body = " ".join([
            WORK_SENTENCES[0],
            ARTIST_SENTENCES[0],
            "This painting was bequeathed to the museum by Frizzoni in 1919.",  # own acq — kept
            INSTITUTIONAL_SENTENCES[2],  # founding — dropped
            INSTITUTIONAL_SENTENCES[3],  # renovation — dropped
            EMOTION_SENTENCES[0],
        ])
        new_body, report = wf.filter_stop_body_work_first(body)
        self.assertEqual(report["institutional_total"], 3)
        self.assertEqual(report["institutional_kept"], 1)
        self.assertEqual(report["institutional_dropped"], 2)
        self.assertIn("bequeathed", new_body)
        self.assertNotIn("61.2 million", new_body)
        self.assertNotIn("Van Heek", new_body)
        # rich content preserved
        self.assertIn(WORK_SENTENCES[0], new_body)

    def test_opening_section_exempt(self):
        body = ("Before we look at anything on the walls, here is the story of the "
                "museum — who created it, why it exists. " + INSTITUTIONAL_SENTENCES[2])
        new_body, report = wf.filter_stop_body_work_first(body, is_opening_section=True)
        self.assertEqual(new_body, body)
        self.assertTrue(report["exempt_opening"])

    def test_never_empties_a_stop(self):
        # all-institutional stop with no rich content → left unchanged (never empty)
        body = " ".join(INSTITUTIONAL_SENTENCES[:3])
        new_body, report = wf.filter_stop_body_work_first(body)
        self.assertTrue(new_body.strip())
        self.assertFalse(report["changed"])

    def test_institutional_share_drops_after_filter(self):
        body = " ".join([
            WORK_SENTENCES[0], WORK_SENTENCES[1], ARTIST_SENTENCES[0],
            INSTITUTIONAL_SENTENCES[0], INSTITUTIONAL_SENTENCES[3],
        ])
        before = wf.institutional_share(body)
        new_body, _ = wf.filter_stop_body_work_first(body)
        after = wf.institutional_share(new_body)
        self.assertGreater(before, after)
        self.assertLessEqual(after, 1.0 / 3.0 + 1e-9)


class TestNarrationContract(unittest.TestCase):
    def test_contract_has_four_parts_in_order(self):
        text = wf.narration_contract_instruction(
            work_title="Two Venetian Ladies", artist="Vittore Carpaccio",
            has_reception_evidence=True)
        a = text.index("(a)")
        b = text.index("(b)")
        c = text.index("(c)")
        d = text.index("(d)")
        self.assertTrue(a < b < c < d)
        self.assertIn("Two Venetian Ladies", text)
        self.assertIn("Carpaccio", text)

    def test_no_reception_evidence_forbids_invented_critic(self):
        text = wf.narration_contract_instruction(has_reception_evidence=False)
        self.assertIn("SKIP", text)
        self.assertIn("invent", text.lower())

    def test_contract_forbids_institutional(self):
        text = wf.narration_contract_instruction()
        for word in ("donor", "bequest", "acquisition", "founding", "renovation"):
            self.assertIn(word, text.lower())


class TestAttribution(unittest.TestCase):
    def test_variant_given_name_is_match(self):
        # LOCAL-616 Groeningemuseum: "Johannes van Eyck" is Jan van Eyck
        r = wf.check_attribution("Johannes van Eyck", "Jan van Eyck")
        self.assertTrue(r["match"])
        self.assertFalse(r["mismatch"])

    def test_real_mismatch_catalogue_wins(self):
        # the LOCAL-616 defect: stop said van Eyck for a Memling
        r = wf.check_attribution("Jan van Eyck", "Hans Memling")
        self.assertFalse(r["match"])
        self.assertTrue(r["mismatch"])
        self.assertTrue(r["drop_conflicting"])
        self.assertEqual(r["use"], "Hans Memling")

    def test_subset_name_is_match(self):
        r = wf.check_attribution("Memling", "Hans Memling")
        self.assertTrue(r["match"])
        self.assertEqual(r["use"], "Hans Memling")

    def test_attributed_to_noise_ignored(self):
        r = wf.check_attribution("attributed to Hans Memling", "Hans Memling")
        self.assertTrue(r["match"])

    def test_unknown_side_no_conflict(self):
        r = wf.check_attribution("", "Hans Memling")
        self.assertTrue(r["match"])
        self.assertFalse(r["drop_conflicting"])
        self.assertEqual(r["use"], "Hans Memling")


class TestShortfallRecompute(unittest.TestCase):
    def test_recompute_on_final_count(self):
        # Granet: shortfall logic ran at 3, a late gate dropped to 2.
        s = wf.recompute_shortfall_on_delivered(
            venue_name="Musée Granet, Aix-en-Provence, France",
            exhibitions_on_view=2, final_delivered_stops=2, requested_stops=3)
        self.assertIn("2 stops", s)
        self.assertIn("rather than the 3", s)
        self.assertNotIn("3 stops rather", s)

    def test_no_sentence_when_ask_met(self):
        s = wf.recompute_shortfall_on_delivered(
            venue_name="X", exhibitions_on_view=5,
            final_delivered_stops=3, requested_stops=3)
        self.assertEqual(s, "")

    def test_single_stop_grammar(self):
        s = wf.recompute_shortfall_on_delivered(
            venue_name="Granet", exhibitions_on_view=1,
            final_delivered_stops=1, requested_stops=3)
        self.assertIn("1 stop ", s)
        self.assertNotIn("1 stops", s)


if __name__ == "__main__":
    unittest.main()
