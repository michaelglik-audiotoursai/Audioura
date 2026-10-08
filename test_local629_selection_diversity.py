"""test_local629_selection_diversity.py — LOCAL-629, one test per item.

Each test runs on a REAL candidate list (the Belvedere / Uffizi / Van Gogh works
as Wikidata returns them), not a toy.

  item 1 — artworks only: the Belvedere candidate list (Klimt's The Kiss, Schiele,
           Messerschmidt busts) PLUS the Austrian State Treaty (a treaty event,
           P31=Q625298), the Marble Hall (a room) and the building itself. After
           the guard only the artworks survive.
  item 2 — artist variety: the Uffizi list (3 Leonardos + Botticelli + Titian +
           Caravaggio) is capped at ceil(3/3)=1 per artist, so the top 3 are three
           DIFFERENT artists — Botticelli/Leonardo/Titian — not three Leonardos.
  item 3 — the conclusion never re-tells a stop: an LLM draft that re-narrates
           Stop 1 (the 2013 Sunset at Montmajour factoid, a July 1890 date, a
           measurement) is REJECTED, so the deterministic thematic template ships;
           a purely thematic draft is accepted.
  item 4 — Van Gogh hours: the "hours weren't published" line is spoken ONLY when
           the preflight genuinely returned no hours; when the preflight published
           hours (as the Van Gogh Museum does), plan_b_opening_practicals yields a
           SPOKEN hours sentence for Stop 1.

Run: python3 -m pytest test_local629_selection_diversity.py -q
"""
import math
import unittest

import artwork_selection_guard as g
import tour_conclusion as tc
import venue_preflight as vp
import practical_facts_gate as pfg


# ── item 1 — the real Belvedere candidate list ───────────────────────────────
# Wikidata Q303139 (Belvedere) returns, via P195/P276, both the paintings AND the
# Austrian State Treaty (signed in the Marble Hall) and the hall/building.
BELVEDERE_CANDIDATES = [
    {"title": "The Kiss", "instance_of": ["Q3305213"],
     "creator": "Gustav Klimt", "creator_qid": "Q34661"},
    {"title": "Judith and the Head of Holofernes", "instance_of": ["Q3305213"],
     "creator": "Gustav Klimt", "creator_qid": "Q34661"},
    {"title": "The Family", "instance_of": ["Q3305213"],
     "creator": "Egon Schiele", "creator_qid": "Q44032"},
    {"title": "Character Head", "instance_of": ["Q860861"],
     "creator": "Franz Xaver Messerschmidt", "creator_qid": "Q84753"},
    # non-artworks that leak in via P276 "location":
    {"title": "Austrian State Treaty", "instance_of": ["Q625298"],  # peace treaty
     "creator": ""},
    {"title": "Marble Hall", "instance_of": ["Q180516"],            # room
     "creator": ""},
    {"title": "Upper Belvedere", "instance_of": ["Q16560"],          # palace / building
     "creator": ""},
    {"title": "Signing of the Austrian State Treaty", "instance_of": [],  # event, no P31
     "creator": ""},
]


class TestItem1ArtworksOnly(unittest.TestCase):
    def test_belvedere_before_after(self):
        kept, dropped = g.enforce_artworks_only(
            BELVEDERE_CANDIDATES, venue_name="Belvedere", is_art_museum=True)
        kept_titles = [k["title"] for k in kept]
        dropped_titles = {d["title"] for d in dropped}

        # Artworks survive.
        self.assertIn("The Kiss", kept_titles)
        self.assertIn("Judith and the Head of Holofernes", kept_titles)
        self.assertIn("The Family", kept_titles)
        self.assertIn("Character Head", kept_titles)
        # Events / rooms / the building are rejected.
        self.assertIn("Austrian State Treaty", dropped_titles)          # by P31 class
        self.assertIn("Marble Hall", dropped_titles)                    # by P31 class / room
        self.assertIn("Upper Belvedere", dropped_titles)                # by P31 class (palace)
        self.assertIn("Signing of the Austrian State Treaty", dropped_titles)  # event title
        # Every surviving stop is a work with a creator.
        for k in kept:
            self.assertTrue(g.work_has_creator(k), f"{k['title']} has no creator")


# ── item 2 — the real Uffizi candidate list (prominence-ranked) ──────────────
# The Uffizi's SPARQL catalogue surfaces several Leonardos at the top of the
# prominence sort; Botticelli and Titian sit just below. The variety cap must
# yield 3 different artists.
UFFIZI_RANKED = [
    {"title": "Annunciation", "creator": "Leonardo da Vinci", "creator_qid": "Q762",
     "instance_of": ["Q3305213"]},
    {"title": "Adoration of the Magi", "creator": "Leonardo da Vinci", "creator_qid": "Q762",
     "instance_of": ["Q3305213"]},
    {"title": "Baptism of Christ", "creator": "Leonardo da Vinci", "creator_qid": "Q762",
     "instance_of": ["Q3305213"]},
    {"title": "The Birth of Venus", "creator": "Sandro Botticelli", "creator_qid": "Q5669",
     "instance_of": ["Q3305213"]},
    {"title": "Venus of Urbino", "creator": "Titian", "creator_qid": "Q47551",
     "instance_of": ["Q3305213"]},
    {"title": "Medusa", "creator": "Caravaggio", "creator_qid": "Q42207",
     "instance_of": ["Q3305213"]},
]


class TestItem2ArtistVariety(unittest.TestCase):
    def test_uffizi_three_different_artists(self):
        n = 3
        kept, dropped = g.cap_artist_variety(UFFIZI_RANKED, n)
        top3 = kept[:n]
        artists = [g.work_artist_key(w) for w in top3]
        # ceil(3/3) == 1 per artist → three DIFFERENT artists in the top 3.
        self.assertEqual(math.ceil(n / 3), 1)
        self.assertEqual(len(set(artists)), 3, f"not varied: {artists}")
        # Leonardo appears at most once among all kept.
        leo = [w for w in kept if w["creator_qid"] == "Q762"]
        self.assertEqual(len(leo), 1)
        # The two extra Leonardos were the ones capped.
        self.assertEqual({d["title"] for d in dropped},
                         {"Adoration of the Magi", "Baptism of Christ"})
        # Signature-first within the rule: the leading Leonardo (first ranked) is
        # the one kept.
        self.assertEqual(leo[0]["title"], "Annunciation")

    def test_six_stops_cap_two_each(self):
        # 6 stops → ceil(6/3)=2 per artist.
        works = (UFFIZI_RANKED
                 + [{"title": "Extra Botticelli", "creator": "Sandro Botticelli",
                     "creator_qid": "Q5669", "instance_of": ["Q3305213"]}])
        kept, _ = g.cap_artist_variety(works, 6)
        leo = [w for w in kept if w["creator_qid"] == "Q762"]
        bott = [w for w in kept if w["creator_qid"] == "Q5669"]
        self.assertEqual(len(leo), 2)
        self.assertEqual(len(bott), 2)

    def test_single_artist_venue_not_stranded(self):
        # A Van Gogh house museum: every work is Van Gogh. The cap must NOT strip
        # the tour to 1 stop — distinct artists < n_stops, so it is skipped.
        vg = [{"title": "a", "creator_qid": "Q5582"},
              {"title": "b", "creator_qid": "Q5582"},
              {"title": "c", "creator_qid": "Q5582"}]
        kept, dropped = g.cap_artist_variety(vg, 3)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])


# ── item 3 — the conclusion never re-tells a stop ─────────────────────────────
# The real Van Gogh delivered stops (titles + a short narration each). An LLM
# draft that re-narrates Stop 1 (the 2013 Sunset at Montmajour factoid) must be
# rejected; a thematic draft must be accepted.
VANGOGH_STOPS = [
    {"title": "Wheatfield with Crows",
     "narration": ("In July 1890, Vincent van Gogh painted this turbulent "
                   "wheatfield under a stormy sky at Auvers-sur-Oise. The long "
                   "double-square canvas measures 50.5 by 103 centimetres.")},
    {"title": "The Potato Eaters",
     "narration": ("Van Gogh painted this dark peasant interior in 1885 in "
                   "Nuenen, working the faces in earth tones.")},
    {"title": "Sunflowers",
     "narration": ("Van Gogh painted his sunflowers in Arles in 1888, in a "
                   "blaze of yellow, to welcome Gauguin to the Yellow House.")},
]
VANGOGH_TITLES = [s["title"] for s in VANGOGH_STOPS]


class TestItem3ConclusionNeverRetells(unittest.TestCase):
    def test_renarrating_draft_rejected(self):
        # Re-tells Stop 1 and adds a new "2013" discovery factoid.
        bad = ("Across these stops, one thread runs through: Van Gogh's final "
               "years. The museum unveiled the long-lost Sunset at Montmajour in "
               "2013.")
        self.assertTrue(tc._conclusion_renarrates_stop(bad))
        self.assertFalse(
            tc._thematic_draft_ok(bad, stops=VANGOGH_STOPS,
                                  titles=VANGOGH_TITLES, venue_name="Van Gogh Museum"))

    def test_date_or_measurement_draft_rejected(self):
        bad_date = ("Together, these works trace grief. Wheatfield with Crows "
                    "was painted in July 1890.")
        bad_meas = ("This tour followed one thread: colour. The canvas is oil on "
                    "canvas, 50.5 by 103 centimetres.")
        self.assertFalse(
            tc._thematic_draft_ok(bad_date, stops=VANGOGH_STOPS,
                                  titles=VANGOGH_TITLES, venue_name="Van Gogh Museum"))
        self.assertFalse(
            tc._thematic_draft_ok(bad_meas, stops=VANGOGH_STOPS,
                                  titles=VANGOGH_TITLES, venue_name="Van Gogh Museum"))

    def test_thematic_draft_accepted(self):
        # Thematic, names at most one example, no stop-body facts.
        good = ("Across these stops, one thread runs through Van Gogh's restless "
                "search for feeling in paint. Seen together, the works show how a "
                "single hand could hold both despair and joy.")
        self.assertFalse(tc._conclusion_renarrates_stop(good))
        self.assertTrue(
            tc._thematic_draft_ok(good, stops=VANGOGH_STOPS,
                                  titles=VANGOGH_TITLES, venue_name="Van Gogh Museum"))

    def test_deterministic_template_is_thematic(self):
        # The deterministic fallback (always-ship path) must itself be thematic —
        # it must never re-tell a stop.
        text = (
            "Step-by-step tour of the Van Gogh Museum.\n\n"
            "Stop 1: Wheatfield with Crows\n\n" + VANGOGH_STOPS[0]["narration"] + "\n\n"
            "Stop 2: The Potato Eaters\n\n" + VANGOGH_STOPS[1]["narration"] + "\n\n"
            "Stop 3: Sunflowers\n\n" + VANGOGH_STOPS[2]["narration"] + "\n")
        rebuilt = tc.rebuild_conclusion(text, venue_name="Van Gogh Museum")
        # Isolate the conclusion (after the last stop body).
        tail = rebuilt.split(VANGOGH_STOPS[2]["narration"])[-1]
        self.assertFalse(
            tc._conclusion_renarrates_stop(tail),
            f"deterministic conclusion re-told a stop: {tail!r}")


# ── item 4 — Van Gogh Museum hours ────────────────────────────────────────────
class TestItem4HoursSpoken(unittest.TestCase):
    def test_published_hours_are_spoken(self):
        # A preflight that found the Van Gogh Museum's hours yields a SPOKEN
        # sentence for Stop 1 (source lives in the text view only).
        pf = {
            "status": "open",
            "hours": "daily 9:00–18:00, Fridays until 21:00",
            "admission": "€22",
            "sources": {"hours": ["https://www.vangoghmuseum.nl/en/visit"]},
            "error": "", "skipped": False,
        }
        planb = vp.plan_b_opening_practicals(pf)
        self.assertTrue(planb["speak"], "no spoken hours sentence produced")
        self.assertIn("9:00", planb["speak"])
        self.assertIn("open", planb["speak"].lower())
        # The source is NOT spoken (D617) — it lives in the text-view note only.
        self.assertNotIn("http", planb["speak"])
        self.assertIn("vangoghmuseum", planb["source_note"])

    def test_unpublished_line_only_when_preflight_confirms(self):
        # When the preflight genuinely returned NO hours, say the honest line.
        museum_text = (
            "Step-by-step tour of the museum.\n\n"
            "Stop 1: A Work\n\nOrientation: You are at the museum. "
            "Some narration about the work in this gallery.\n")
        out, inserted = pfg.ensure_unpublished_hours_line(
            museum_text, hours_genuinely_absent=True)
        self.assertTrue(inserted)
        self.assertTrue(pfg.tour_speaks_hours(out) or "hours" in out.lower())

    def test_no_false_hours_claim_when_preflight_did_not_confirm(self):
        # When the preflight did NOT confirm hours are unpublished, we must NOT
        # assert "hours weren't published" (that would be a false claim).
        museum_text = (
            "Step-by-step tour of the museum.\n\n"
            "Stop 1: A Work\n\nOrientation: You are at the museum. "
            "Some narration about the work in this gallery.\n")
        out, inserted = pfg.ensure_unpublished_hours_line(
            museum_text, hours_genuinely_absent=False)
        self.assertFalse(inserted)

    def test_known_hours_spoken_when_only_in_field_line(self):
        # The Belvedere/Van Gogh live defect: hours were KNOWN but only landed in
        # a non-spoken "Museum Information:" field line, so no hours were SPOKEN.
        # ensure_spoken_hours_line injects a real spoken sentence into Stop 1.
        museum_text = (
            "Step-by-step tour of the museum.\n\n"
            "Stop 1: Madonna del Prato\n\n"
            "Museum Information: Tuesday to Sunday, 11 AM-6 PM. €65\n\n"
            "Orientation: You are at the Belvedere. Stand before the painting.\n")
        # A bare "Museum Information:" field line is NOT spoken hours.
        self.assertFalse(pfg.tour_speaks_hours_in_prose(museum_text))
        out, inserted = pfg.ensure_spoken_hours_line(
            museum_text, hours="Tuesday to Sunday, 11 AM-6 PM",
            admission="€65")
        self.assertTrue(inserted)
        self.assertTrue(pfg.tour_speaks_hours_in_prose(out))
        self.assertIn("open", out.lower())
        # [LOCAL-633] the COMPOSED spoken sentence uses the currency as a WORD.
        self.assertIn("65 euros", out)
        # Practical facts are placed in the opening section, never the Orientation.
        orientation = [p for p in out.split("\n\n")
                       if p.strip().lower().startswith("orientation:")][0]
        self.assertNotIn("is open", orientation)

    def test_spoken_hours_noop_when_prose_already_speaks(self):
        # No double-up: when prose already states hours, inject nothing.
        text = ("Tour of the museum.\n\n"
                "Stop 1: A Work\n\nOrientation: The museum is open daily 9 AM-6 PM. "
                "Stand before the work.\n")
        out, inserted = pfg.ensure_spoken_hours_line(
            text, hours="daily 9 AM-6 PM", admission="€10")
        self.assertFalse(inserted)
        self.assertEqual(out, text)


if __name__ == "__main__":
    unittest.main()
