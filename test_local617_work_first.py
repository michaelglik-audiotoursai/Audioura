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

    def test_live_431_432_institutional_patterns(self):
        # [LOCAL-617 live] exact sentences the independent critic flagged as
        # criterion-1 institutional on tours 431 (Basel) and 432 (Sevilla) that
        # the first lexicon missed. All must now classify institutional.
        vb = ["Kunstmuseum", "Basel"]
        vs = ["Museo", "Bellas", "Artes", "Sevilla", "Seville"]
        for s, v in [
            ("The Würth Collection, which started in 1970, comprises over 20,000 "
             "works spanning more than 500 years.", vb),
            ("Hans Würth, the driving force behind the collection, dedicated "
             "himself to acquiring artwork.", vb),
            ("This governmental decision altered its setting and purpose, making "
             "it accessible to the wider public.", vs),
            ("This canvas entered public ownership through the redistribution of "
             "church property.", vs),
            ("The painting now resided in a collection crafted to showcase pieces "
             "from Seville's heritage.", vs),
        ]:
            self.assertEqual(wf.classify_sentence(s, venue_tokens=v),
                             "institutional", msg=f"not institutional: {s!r}")

    def test_provenance_predicate_does_not_steal_real_ekphrasis(self):
        # a true work description with a work deictic must NOT be dragged into
        # institutional by the provenance-predicate override.
        for s in [
            "This canvas depicts Saint Francis embracing the crucified Christ.",
            "The painting glows with a warm, enveloping light across the robes.",
            "Murillo painted this canvas in his final years, after a great loss.",
        ]:
            self.assertNotEqual(wf.classify_sentence(s), "institutional", msg=s)


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


class TestTourLevelFilter(unittest.TestCase):
    def test_opening_section_kept_work_stops_filtered(self):
        tour = (
            "Stop 1: About the Museo Correr\n"
            "Before we look at anything on the walls, here is the story of the "
            "Museo Correr — who created it, why it exists.\n\n"
            "The composition shows two Venetian ladies on a terrace, their gaze "
            "averted. In 1830, Teodoro Correr passed away, leaving behind a "
            "significant legacy. A 61.2 million euro renovation modernised the "
            "galleries. You cannot help but feel the loneliness in their eyes.\n\n"
            "Stop 2: La Crocifissione\n"
            "Bellini renders the figure in muted blues, the light soft on the "
            "hands. Founded in 1927, the collection grew through major donations. "
            "There is a quiet grief here that invites you to pause.\n"
        )
        new_tour, report = wf.filter_tour_text_work_first(
            tour, venue_tokens=["museo", "correr"])
        # opening section line survives
        self.assertIn("here is the story of the Museo Correr", new_tour)
        # work-stop institutional sentences stripped
        self.assertNotIn("61.2 million", new_tour)
        self.assertNotIn("Founded in 1927", new_tour)
        self.assertNotIn("Teodoro Correr passed away", new_tour)
        # work/emotion content preserved in both stops
        self.assertIn("two Venetian ladies", new_tour)
        self.assertIn("muted blues", new_tour)
        self.assertIn("quiet grief", new_tour)
        self.assertTrue(report["changed"])
        self.assertGreaterEqual(report["institutional_dropped"], 3)

    def test_no_stop_headers_unchanged(self):
        text = "Just some prose with no stops. Founded in 1927."
        new_text, report = wf.filter_tour_text_work_first(text)
        self.assertEqual(new_text, text)
        self.assertEqual(report["stops"], 0)

    def test_preamble_and_conclusion_untouched(self):
        tour = (
            "Welcome to the tour.\n"
            "Stop 1: Work\n"
            "The canvas depicts a storm. It was bequeathed to the museum in 1919.\n"
        )
        new_tour, _ = wf.filter_tour_text_work_first(tour, venue_tokens=["museum"])
        self.assertIn("Welcome to the tour.", new_tour)


class TestShortfallReconciliation(unittest.TestCase):
    def test_corrects_stale_delivered_count(self):
        # Granet: sentence said 3, but only 2 Stop headers survived a late gate.
        tour = (
            "Welcome.\n"
            "Stop 1: About\n"
            "Musee Granet currently has 3 exhibitions on view, so this tour has 3 "
            "stops rather than the 3 you asked for.\n"
            "The canvas depicts a landscape.\n\n"
            "Stop 2: Second work\n"
            "Bellini renders the figure in muted blues.\n"
        )
        # NB build_shortfall_sentence never emits delivered==requested, but a stale
        # sentence can; the reconciler fixes the clause to the real delivered count.
        new_tour, rep = wf.reconcile_shortfall_in_text(tour)
        self.assertEqual(rep["delivered"], 2)
        # 2 delivered < 3 requested → rewritten to "2 stops rather than the 3"
        self.assertIn("2 stops rather than the 3", new_tour)
        self.assertNotIn("3 stops rather than the 3", new_tour)

    def test_removes_sentence_when_ask_met(self):
        tour = (
            "Stop 1: A\nFirst work body.\n\n"
            "Stop 2: B\nSecond work body.\n\n"
            "Stop 3: C\nThird. This tour has 2 stops rather than the 3 you asked for.\n"
        )
        # 3 delivered >= 3 requested → shortfall removed
        new_tour, rep = wf.reconcile_shortfall_in_text(tour)
        self.assertEqual(rep["delivered"], 3)
        self.assertTrue(rep["removed"])
        self.assertNotIn("rather than the 3 you asked for", new_tour)

    def test_outdoor_confirm_clause_rewritten(self):
        tour = (
            "Stop 1: A\nbody.\n\n"
            "We could confirm 5 stops along this route, so this tour has 5 stops "
            "rather than the 7 you asked for.\n"
        )
        new_tour, rep = wf.reconcile_shortfall_in_text(tour)
        self.assertEqual(rep["delivered"], 1)
        self.assertIn("confirm 1 stop along this route", new_tour)

    def test_count_delivered_stops(self):
        tour = "pre\nStop 1: a\nx\nStop 2: b\ny\nStop 3: c\nz\n"
        self.assertEqual(wf.count_delivered_stops(tour), 3)


class TestConclusionNamesOnlyDelivered(unittest.TestCase):
    """item 6 — the recap must name only delivered stops, never a dropped one."""

    def test_recap_names_only_delivered_stops(self):
        import generate_tour_text as g
        delivered = [
            {"name": "Two Venetian Ladies",
             "description": ("The composition shows two Venetian ladies on a "
                             "terrace. Carpaccio painted this around 1495."),
             "latitude": 45.43, "longitude": 12.33},
            {"name": "La Crocifissione",
             "description": ("Bellini renders the crucifixion in muted blues around "
                             "1455. The light falls softly across the figures."),
             "latitude": 45.44, "longitude": 12.34},
        ]
        # A ranked fact for a stop that was DROPPED must never appear.
        ranked = [
            {"stop": "Two Venetian Ladies",
             "best_fact": "Carpaccio painted this around 1495.",
             "reason": "date"},
            {"stop": "A Dropped Stop",  # not in delivered → must be excluded
             "best_fact": "This never shipped.", "reason": "x"},
        ]
        recap = g._build_closing_recap(delivered, ranked, api_key=None)
        self.assertNotIn("A Dropped Stop", recap)
        self.assertNotIn("This never shipped", recap)
        # names only delivered stops; states the delivered count
        if recap:
            self.assertIn("2 stops", recap)


class TestShortfallRecompute(unittest.TestCase):
    def test_recompute_on_final_count(self):
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


class TestInstitutionalTheme(unittest.TestCase):
    def test_institutional_themes_rejected(self):
        for name in [
            "19th-Century Institutional Foundations",
            "The Making of a Museum: Donors and Benefactors",
            "Expropriation and the Collection",
            "The Desamortización and the Museum's Growth",
            "A Legacy of Patronage",
        ]:
            self.assertTrue(wf.is_institutional_theme(name), msg=name)

    def test_art_themes_kept(self):
        for name in [
            "Devotion and the Human Body in Baroque Seville",
            "From Early Realism to Late Abstraction",
            "Light, Shadow, and the Sacred",
            "El Greco and His Workshop",
            "Foundations of Modern Abstraction",  # 'foundations' but art-rescued
        ]:
            self.assertFalse(wf.is_institutional_theme(name), msg=name)


class TestNonArtworkListing(unittest.TestCase):
    def test_price_and_event_listings_rejected(self):
        for t in [
            "Kosten: Eintritt Sammlung",
            "Mit der wissenschaftlichen Assistentin Amélie Joller",
            "Öffnungszeiten",
            "Prix: 15 €",
            "Admission",
            "Eintritt CHF 26",
            "Visite guidée avec le conservateur",
            "Führung",
        ]:
            self.assertTrue(wf.looks_like_non_artwork_listing(t), msg=t)

    def test_real_artwork_titles_kept(self):
        for t in [
            "Madonna of the Napkin",
            "San Francisco abrazando a Cristo en la Cruz",
            "Retrato de Jorge Manuel Theotocopuli",
            "The Night Watch",
            "Two Venetian Ladies",
            "The Tango Lesson",
            "The Salon of 1824",
        ]:
            self.assertFalse(wf.looks_like_non_artwork_listing(t), msg=t)

    def test_museum_event_names_rejected(self):
        for t in [
            "Europäischer Tag der Restaurierung 2026",
            "Mitmach-Mittwoch",
            "Familientag",
            "Dübi-Müller Tango Salon",
            "Offene Werkstatt",
            "Lange Nacht der Museen",
        ]:
            self.assertTrue(wf.looks_like_non_artwork_listing(t), msg=t)

    def test_wired_into_chrome_gate(self):
        import exhibition_discovery as ed
        self.assertTrue(ed.is_chrome_title("Kosten: Eintritt Sammlung", "Kunstmuseum Basel"))
        self.assertFalse(ed.is_chrome_title("Madonna of the Napkin", "Museo de Bellas Artes"))


class TestDedupeConclusion(unittest.TestCase):
    def test_removes_redundant_covered_when_recap_present(self):
        text = ("That's 3 stops — A, B, and C. This tour covered B and C.\n")
        new, rep = wf.dedupe_conclusion(text)
        self.assertTrue(rep["removed_redundant_covered"])
        self.assertNotIn("This tour covered", new)
        self.assertIn("That's 3 stops", new)

    def test_keeps_covered_when_no_recap(self):
        text = "This tour covered A and B."
        new, rep = wf.dedupe_conclusion(text)
        self.assertFalse(rep["removed_redundant_covered"])
        self.assertEqual(new, text)


class TestTruncatedTail(unittest.TestCase):
    def test_drops_mid_clause_final_sentence(self):
        text = ("The composition is luminous and tender. "
                "San Francisco abrazando a Cristo en la Cruz showcases Murillo's talent for.")
        new, rep = wf.repair_truncated_tail(text)
        self.assertTrue(rep["repaired"])
        self.assertNotIn("talent for.", new)
        self.assertIn("luminous and tender", new)

    def test_complete_conclusion_untouched(self):
        text = ("You have stood before three works of quiet devotion. "
                "Each one rewards a slow, attentive gaze.")
        new, rep = wf.repair_truncated_tail(text)
        self.assertFalse(rep["repaired"])
        self.assertEqual(new.strip(), text.strip())

    def test_restaurant_offer_last_sentence_safe(self):
        text = ("A fitting close to the visit. "
                "If you would like to eat nearby we can build you a restaurant tour.")
        new, rep = wf.repair_truncated_tail(text)
        self.assertFalse(rep["repaired"])
        self.assertIn("restaurant tour", new)


class TestBrokenSentences(unittest.TestCase):
    """[LOCAL-617 item 3/8] repair_broken_sentences — missing-subject + dup clause.

    Real corruptions the independent critic flagged on the three live tours:
      tour 429  "During this period, was refining his techniques"  (missing subj)
      tour 427  "…a profound act of devotion, of Assisi in a profound act of
                 devotion"                                          (dup clause)
    """

    def test_drops_missing_subject_clause(self):
        text = ("Stop 2: Murillo\n"
                "During this period, was refining his techniques. "
                "The canvas glows with a warm, enveloping light.")
        new, rep = wf.repair_broken_sentences(text)
        self.assertTrue(rep["changed"])
        self.assertEqual(rep["missing_subject_dropped"], 1)
        self.assertNotIn("was refining his techniques", new)
        self.assertIn("warm, enveloping light", new)

    def test_collapses_duplicated_clause(self):
        text = ("Stop 2: Zurbaran\n"
                "It depicts Saint Francis, a profound act of devotion, "
                "of Assisi in a profound act of devotion.")
        new, rep = wf.repair_broken_sentences(text)
        self.assertTrue(rep["changed"])
        self.assertEqual(rep["dup_clauses_collapsed"], 1)
        # the verbatim repeat is gone — only one "profound act of devotion"
        self.assertEqual(new.count("a profound act of devotion"), 1)

    def test_never_empties_a_stop(self):
        # the ONLY sentence of the stop is broken — keep it rather than vanish it
        text = "Stop 5: X\nDuring this period, was refining his techniques."
        new, rep = wf.repair_broken_sentences(text)
        self.assertIn("was refining his techniques", new)

    def test_imperatives_untouched(self):
        text = "Walk to the next gallery. Look closely at the brushwork."
        new, rep = wf.repair_broken_sentences(text)
        self.assertFalse(rep["changed"])
        self.assertEqual(new, text)

    def test_legit_sentence_with_subject_preserved(self):
        text = "During this period, Murillo was refining his techniques."
        new, rep = wf.repair_broken_sentences(text)
        self.assertFalse(rep["changed"])
        self.assertEqual(new, text)

    def test_stop_header_not_altered(self):
        text = "Stop 3: The Immaculate Conception\nThe figure rises on a crescent moon."
        new, rep = wf.repair_broken_sentences(text)
        self.assertFalse(rep["changed"])
        self.assertIn("Stop 3: The Immaculate Conception", new)


if __name__ == "__main__":
    unittest.main()
