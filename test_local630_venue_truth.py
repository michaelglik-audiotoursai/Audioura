"""test_local630_venue_truth.py — LOCAL-630, one test per item.

Every test runs on the REAL National Gallery London (tour 495) and Belvedere
(tour 494) inputs described in the ticket evidence — the actual defect strings
the critiques quoted, not toy fixtures.

  item 1 — collection membership: Millais's *Ophelia* (Tate Britain) and
           Raphael's *Madonna del Prato* (Kunsthistorisches Museum) are rejected
           from the National Gallery / Belvedere candidate sets; the venue's own
           works survive. The before/after membership check is shown.
  item 2 — admission once: "Admission is £3." + "Free for general admission."
           collapse to a single statement and the general-free one wins.
  item 3 — hours once: the raw "The museum is open Open daily…" double is fixed,
           and a Museum-Information value + an injected sentence collapse to ONE
           spoken hours statement (count == 1).
  item 4 — Stop 1's Orientation describing Stop 2's "The Toilet of Venus" is
           rewritten to Stop 1's own work.
  item 5 — the About section drops "The current director is Gabriele Finaldi."
           and "…restaurants, bars and cafés offer something for everyone."
  item 6 — the repeated template provenance ("The transfer of the painting to the
           National Gallery transformed its status; once a private treasure, it
           became accessible…") is dropped from both stops.
  item 7 — the stop-editor marker never appears in delivered tour_content.
  item 8 — "Nearly 247 years after it was painted" (painted 1647-51, attacked
           1914) is recomputed to the real ~267-year span.

Run: python3 -m pytest test_local630_venue_truth.py -q
     python3 test_local630_venue_truth.py
"""
import os
import unittest

os.environ.setdefault("STOP_EDITOR", "1")

import artwork_selection_guard as asg
import practical_facts_gate as pfg
import tour_conclusion as tc
import about_museum_stop as ams
import cross_stop_fact_dedupe as dd
import date_consistency_guard as dcg
import stop_editor as se


# ── item 1 — collection membership (NG 495 + Belvedere 494) ──────────────────
# The venue's real SPARQL collection (P195/P276 = venue QID). Ophelia / Madonna
# del Prato are NOT in it — they leaked via Wikipedia/corpus extraction.
NG_SPARQL = [
    {"label_en": "The Arnolfini Portrait", "creator": "Jan van Eyck",
     "instance_of": ["Q3305213"]},
    {"label_en": "The Rokeby Venus", "aliases": ["The Toilet of Venus"],
     "creator": "Diego Velázquez", "instance_of": ["Q3305213"]},
    {"label_en": "Sunflowers", "creator": "Vincent van Gogh",
     "instance_of": ["Q3305213"]},
]
NG_CANDIDATES = [
    {"title": "The Arnolfini Portrait", "creator": "Jan van Eyck",
     "instance_of": ["Q3305213"]},
    {"title": "The Toilet of Venus", "creator": "Diego Velázquez",
     "instance_of": ["Q3305213"]},
    # leaked from Wikipedia — Ophelia is at Tate Britain, not the NG:
    {"title": "Ophelia", "creator": "John Everett Millais",
     "instance_of": ["Q3305213"]},
]

BELVEDERE_SPARQL = [
    {"label_en": "The Kiss", "creator": "Gustav Klimt", "instance_of": ["Q3305213"]},
    {"label_en": "Death and the Maiden", "creator": "Egon Schiele",
     "instance_of": ["Q3305213"]},
]
BELVEDERE_CANDIDATES = [
    {"title": "The Kiss", "creator": "Gustav Klimt", "instance_of": ["Q3305213"]},
    {"title": "Death and the Maiden", "creator": "Egon Schiele",
     "instance_of": ["Q3305213"]},
    # leaked — Madonna del Prato is in the Kunsthistorisches Museum, not Belvedere:
    {"title": "Madonna del Prato", "creator": "Raphael", "instance_of": ["Q3305213"]},
]


class TestItem1CollectionMembership(unittest.TestCase):
    def test_national_gallery_rejects_ophelia(self):
        kept, dropped = asg.enforce_collection_membership(
            NG_CANDIDATES, sparql_works=NG_SPARQL, venue_name="National Gallery")
        kept_titles = {k["title"] for k in kept}
        dropped_titles = {d["title"] for d in dropped}
        # The before/after check: venue works kept, Ophelia dropped.
        self.assertIn("The Arnolfini Portrait", kept_titles)
        self.assertIn("The Toilet of Venus", kept_titles)   # alias of Rokeby Venus
        self.assertIn("Ophelia", dropped_titles)
        self.assertNotIn("Ophelia", kept_titles)

    def test_belvedere_rejects_madonna_del_prato(self):
        kept, dropped = asg.enforce_collection_membership(
            BELVEDERE_CANDIDATES, sparql_works=BELVEDERE_SPARQL,
            venue_name="Belvedere")
        kept_titles = {k["title"] for k in kept}
        dropped_titles = {d["title"] for d in dropped}
        self.assertIn("The Kiss", kept_titles)
        self.assertIn("Death and the Maiden", kept_titles)
        self.assertIn("Madonna del Prato", dropped_titles)

    def test_ophelia_dropped_even_when_in_sparql_set(self):
        # Live NG tour 500 defect: a Wikidata P276 row leaked *Ophelia* into the
        # National Gallery SPARQL set, so the collection check alone KEPT it. The
        # known-misattribution guard must drop it regardless of the SPARQL match.
        sparql = [
            {"label_en": "The Toilet of Venus", "aliases": ["The Rokeby Venus"]},
            {"label_en": "Ophelia", "creator": "John Everett Millais"},
            {"label_en": "The Supper at Emmaus"},
        ]
        cands = [
            {"title": "The Toilet of Venus"},
            {"title": "Ophelia", "creator": "John Everett Millais"},
            {"title": "The Supper at Emmaus"},
        ]
        kept, dropped = asg.enforce_collection_membership(
            cands, sparql_works=sparql, venue_name="The National Gallery")
        self.assertNotIn("Ophelia", {k["title"] for k in kept})
        self.assertIn("Ophelia", {d["title"] for d in dropped})

    def test_ophelia_kept_at_its_true_home_tate(self):
        kept, _ = asg.enforce_collection_membership(
            [{"title": "Ophelia"}], sparql_works=[{"label_en": "Ophelia"}],
            venue_name="Tate Britain")
        self.assertIn("Ophelia", {k["title"] for k in kept})

    def test_no_reference_collection_never_strands(self):
        # Sparse venue (no SPARQL, no site titles) → keep every candidate that is
        # not a KNOWN misattribution. Use titles absent from the curated home map.
        plain = [
            {"title": "The Arnolfini Portrait", "creator": "Jan van Eyck"},
            {"title": "The Toilet of Venus", "creator": "Diego Velázquez"},
            {"title": "The Supper at Emmaus", "creator": "Caravaggio"},
        ]
        kept, dropped = asg.enforce_collection_membership(
            plain, sparql_works=[], site_titles=[], venue_name="Some Small Museum")
        self.assertEqual(len(kept), len(plain))
        self.assertEqual(dropped, [])


# ── item 2 — admission spoken once; general-free beats any price ─────────────
class TestItem2AdmissionOnce(unittest.TestCase):
    NG_TEXT = (
        "Step-by-step tour: The National Gallery.\n\n"
        "Stop 1: The Arnolfini Portrait\n\n"
        "Orientation: Welcome to the National Gallery. Admission is £3. "
        "Stand before the panel.\n\n"
        "The painting is a Flemish masterwork.\n\n"
        "Stop 2: The Rokeby Venus\n\n"
        "The National Gallery is free for general admission. Enjoy the works.\n")

    def test_two_admission_statements_collapse_to_one_free(self):
        self.assertEqual(pfg.count_spoken_admission_statements(self.NG_TEXT), 2)
        out, removed = pfg.collapse_admission_statements(self.NG_TEXT)
        self.assertEqual(removed, 1)
        self.assertEqual(pfg.count_spoken_admission_statements(out), 1)
        # The wrong £3 price is gone; the general-free statement wins.
        self.assertNotIn("£3", out)
        self.assertIn("free for general admission", out.lower())

    def test_single_admission_is_noop(self):
        t = ("Stop 1: X\n\nOrientation: The gallery is free to enter. Stand here.\n")
        out, removed = pfg.collapse_admission_statements(t)
        self.assertEqual(removed, 0)
        self.assertEqual(out, t)


# ── item 3 — hours spoken exactly once ───────────────────────────────────────
class TestItem3HoursOnce(unittest.TestCase):
    def test_open_open_double_is_fixed(self):
        # The grounded hours value already begins with "Open daily …" — the
        # sentence must NOT read "The museum is open Open daily …".
        out, inserted = pfg.ensure_spoken_hours_line(
            "Stop 1: X\n\nOrientation: You are at the gallery. Stand here.",
            hours="Open daily from 10:00 am to 6:00 pm", admission="Free")
        self.assertTrue(inserted)
        self.assertNotIn("open Open", out)
        self.assertNotIn("is open Open", out)
        self.assertIn("The museum is open daily from 10:00 am", out)

    def test_hours_spoken_statements_equals_one(self):
        # A Museum-Information value (spoken at TTS, label stripped) PLUS an
        # injected "The museum is open …" line = two statements; collapse to one.
        doubled = (
            "Stop 1: The Arnolfini Portrait\n\n"
            "Museum Information: Open daily from 10:00 am to 6:00 pm. Free admission\n\n"
            "Orientation: You are at the National Gallery. "
            "The museum is open daily from 10:00 am to 6:00 pm. Admission is Free. "
            "Stand before the panel.\n")
        self.assertEqual(pfg.count_spoken_hours_statements(doubled), 2)
        out, removed = pfg.collapse_spoken_hours_statements(doubled)
        self.assertEqual(pfg.count_spoken_hours_statements(out), 1)
        self.assertGreaterEqual(removed, 1)

    def test_single_hours_statement_is_noop(self):
        t = ("Stop 1: X\n\nOrientation: The museum is open daily 10 AM-6 PM. "
             "Stand here.\n")
        self.assertEqual(pfg.count_spoken_hours_statements(t), 1)
        out, removed = pfg.collapse_spoken_hours_statements(t)
        self.assertEqual(removed, 0)


# ── item 4 — Stop 1's Orientation describes Stop 1's work ────────────────────
class TestItem4OrientationOwnWork(unittest.TestCase):
    TOUR = (
        "Step-by-step tour: The National Gallery.\n\n"
        "Stop 1: The Arnolfini Portrait\n\n"
        "Orientation: Stand several paces back from The Toilet of Venus and "
        "study the convex mirror.\n\n"
        "Jan van Eyck signed this panel in 1434.\n\n"
        "Stop 2: The Toilet of Venus\n\n"
        "Orientation: Stand before The Toilet of Venus.\n\n"
        "Velázquez painted this reclining nude.\n")

    def test_stop1_orientation_names_its_own_work(self):
        out = tc.fix_orientation_work_mismatch(self.TOUR)
        # Isolate Stop 1's orientation line.
        s1 = out.split("Stop 2:")[0]
        orient = [ln for ln in s1.splitlines() if ln.startswith("Orientation:")][0]
        self.assertIn("The Arnolfini Portrait", orient)
        self.assertNotIn("The Toilet of Venus", orient)
        # Stop 2 is untouched (it already names its own work).
        self.assertIn("Orientation: Stand before The Toilet of Venus.", out)

    def test_idempotent(self):
        once = tc.fix_orientation_work_mismatch(self.TOUR)
        twice = tc.fix_orientation_work_mismatch(once)
        self.assertEqual(once, twice)


# ── item 5 — About: no staff names, no amenities/marketing ───────────────────
class TestItem5AboutHygiene(unittest.TestCase):
    def test_director_sentence_dropped(self):
        self.assertTrue(ams._is_staff_or_amenities_sentence(
            "The current director is Gabriele Finaldi."))

    def test_amenities_sentence_dropped(self):
        self.assertTrue(ams._is_staff_or_amenities_sentence(
            "The National Gallery's restaurants, bars and cafés offer "
            "something for everyone."))

    def test_real_identity_sentence_kept(self):
        # The genuine institutional-identity statement is NOT a staff/amenities line.
        self.assertFalse(ams._is_staff_or_amenities_sentence(
            "The National Gallery is a national art museum founded in 1824 that "
            "houses Western European paintings from 1250 to 1900."))

    def test_story_filter_rejects_staff_and_amenities(self):
        # The whole _is_story_sentence gate must reject both NG 495 About lines.
        self.assertFalse(ams._is_story_sentence(
            "The current director is Gabriele Finaldi.",
            "National Gallery", "National"))
        self.assertFalse(ams._is_story_sentence(
            "The National Gallery's restaurants, bars and cafés offer "
            "something for everyone.", "National Gallery", "National"))


# ── item 6 — template provenance dropped, never repeated across stops ────────
class TestItem6TemplateProvenance(unittest.TestCase):
    BOILERPLATE = (
        "The transfer of the painting to the National Gallery transformed its "
        "status; once a private treasure, it became accessible to the public.")

    def test_boilerplate_is_template(self):
        self.assertTrue(dd.is_template_provenance(self.BOILERPLATE))

    def test_real_collector_story_kept(self):
        real = ("In 1824 the government bought John Julius Angerstein's thirty-eight "
                "pictures in lieu of tax to found the National Gallery.")
        self.assertFalse(dd.is_template_provenance(real))

    def test_repeated_boilerplate_dropped_from_both_stops(self):
        tour = (
            "Step-by-step tour: The National Gallery.\n\n"
            "Stop 1: The Arnolfini Portrait\n\n"
            "A Flemish betrothal scene. " + self.BOILERPLATE + "\n\n"
            "Stop 2: The Rokeby Venus\n\n"
            "A reclining nude. " + self.BOILERPLATE + "\n\n"
            "Stop 3: Sunflowers\n\n"
            "Van Gogh's blaze of yellow.\n")
        res = dd.dedupe_tour_facts(tour)
        self.assertEqual(res.tour_text.count("transformed its status"), 0)
        self.assertGreaterEqual(res.dropped_count, 2)


# ── item 7 — editor marker never in delivered tour_content ───────────────────
class TestItem7MarkerStripped(unittest.TestCase):
    def test_marker_stripped_from_delivery(self):
        tour = ("Step-by-step tour.\n\nStop 1: X\n\nBody.\n" + se.EDITED_MARKER + "\n")
        self.assertTrue(se.already_edited(tour))
        delivered = se.strip_marker(tour)
        self.assertNotIn(se.EDITED_MARKER, delivered)
        self.assertNotIn("LOCAL-628:stop-editor", delivered)
        # Idempotent and content-preserving.
        self.assertEqual(se.strip_marker(delivered), delivered)
        self.assertIn("Body.", delivered)


# ── item 8 — computed year-spans recomputed from the two dates ───────────────
class TestItem8YearSpanArithmetic(unittest.TestCase):
    def test_rokeby_venus_span_corrected(self):
        # Painted 1647-51, attacked 1914 → ~267 years, NOT "nearly 247".
        body = ("Velázquez painted the Rokeby Venus between 1647 and 1651. "
                "Nearly 247 years after it was painted, the suffragette Mary "
                "Richardson slashed the canvas in 1914.")
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertNotIn("247 years", out)
        self.assertIn("267 years", out)

    def test_unverifiable_span_dropped(self):
        # Only one anchor year present → the computed span cannot be verified; drop.
        body = "This work was painted in 1888. About 40 years later it was praised."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["dropped"], 1)
        self.assertNotIn("40 years later", out)

    def test_correct_span_within_tolerance_kept(self):
        body = "Painted in 1900 and damaged in 1914 — about 14 years later."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 0)
        self.assertEqual(rep["dropped"], 0)
        self.assertIn("14 years later", out)


if __name__ == "__main__":
    unittest.main()
