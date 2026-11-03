#!/usr/bin/env python3
"""test_local855b_fixes.py — LOCAL-855B (the bounce of LOCAL-855).

LEAD read the delivered artifact (submission_artifacts/local855/live_tour_7stops.txt)
and listed ten defects that still shipped. Each string below is quoted from that
delivered text. Deterministic, offline (no network, no LLM):

  1  Title: "… the biking category - Museum Tour" — a user-stops tour is never a
     museum; the title builder must not say "Museum Tour" for this path.
  3  Legend: Longan "This egg hatched a dragon that helped the village survive…"
     — a folk tale narrated as the venue's own story, dropped by a post-check.
  4  Fabricated anecdote/firsts: Thi Bar "Before one pivotal night… That evening
     changed the pattern"; Acoustic Bar "credits her early gigs here with
     securing her first record deal" — dropped for a thin venue.
  5  Off-topic hedge: A Star is Born "While there is no direct tie to Hồ Chí
     Minh, born Nguyễn Sinh Cung…" — the hedge + biography dropped.
  8  Scope: the dated scrub fires ONLY when no retrieved source names the venue;
     a famous stop (Notre-Dame Cathedral Saigon) keeps "built 1863–1880".
  9  Thread safety: _USER_STOP_TITLES is per JOB (per contextvars Context), so two
     concurrent jobs never see each other's titles.
  10 Closer: a user-stops tour drops "Rambutan is one you might carry with you."

Run: python3 -m pytest tests/test_local855b_fixes.py -q
"""
import contextvars
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_narration as usn
import tour_conclusion as tc
import generate_tour_text as gtt


# ── defect 3 — folk-tale / legend narrative dropped (thin user venue) ─────────
class Defect3Legend(unittest.TestCase):
    LONGAN = {"name": "Longan", "title": "Longan",
              "type_specialty": "Restaurant", "user_explicit": True}
    BODY = (
        "Longan restaurant offers more than just a taste of Vietnamese cuisine. "
        "This egg hatched a dragon that helped the village survive harsh dry "
        "seasons by spraying water upon the fields. "
        "The raven did not keep the eye but handed it over to a robber. "
        "The young boy defeated the robber, reclaiming the stolen eye. "
        "Within Longan's humble walls, the sound of clinking chopsticks blends "
        "with the soft murmur of conversation.")

    def test_legend_sentences_dropped_venue_kept(self):
        scrubbed, dropped = usn.scrub_user_stop_body(
            self.BODY, self.LONGAN, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("dragon", scrubbed.lower())
        self.assertNotIn("village", scrubbed.lower())
        self.assertNotIn("robber", scrubbed.lower())
        # The two real venue sentences survive.
        self.assertIn("Vietnamese cuisine", scrubbed)
        self.assertIn("clinking chopsticks", scrubbed)

    def test_legend_dropped_even_when_sentence_names_venue(self):
        # "Longan, or dragon's eye" names the venue AND tells the legend — drop.
        txt = ("Longan, or dragon's eye, preserves the memory of this sacrifice. "
               "Longan is a cozy restaurant with wood paneling.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            txt, self.LONGAN, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("dragon", scrubbed.lower())
        self.assertIn("wood paneling", scrubbed)


# ── defect 4 — fabricated anecdote / claim-of-firsts dropped (thin venue) ─────
class Defect4Anecdote(unittest.TestCase):
    THI = {"name": "Thi Bar Saigon", "title": "The LGBT bar Thi Bar Saigon",
           "type_specialty": "LGBT Bar", "user_explicit": True}
    AC = {"name": "Acoustic Bar", "title": "Acoustic Bar",
          "type_specialty": "Live Music Bar", "user_explicit": True}

    def test_thi_bar_one_pivotal_night_dropped(self):
        txt = ("Before one pivotal night, drag performances in the city were rare. "
               "That evening changed the pattern by opening its stage to drag "
               "artists. "
               "Thi Bar Saigon is painted in midnight blue with splashes of neon.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            txt, self.THI, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("pivotal", scrubbed.lower())
        self.assertNotIn("that evening changed", scrubbed.lower())
        self.assertIn("midnight blue", scrubbed)

    def test_acoustic_bar_first_record_deal_dropped(self):
        txt = ("Acoustic Bar hosts weekly sessions where emerging artists test "
               "new material. "
               "One story from Acoustic Bar's recent past involves a local "
               "songwriter who credits her early gigs here with securing her "
               "first record deal. "
               "After a string of performances, her blend of personal lyrics "
               "caught the attention of a producer, leading to a recording "
               "contract that launched her career.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            txt, self.AC, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("first record deal", scrubbed.lower())
        self.assertNotIn("recording contract", scrubbed.lower())
        self.assertNotIn("launched her career", scrubbed.lower())
        # The honest venue sentence survives.
        self.assertIn("weekly sessions", scrubbed)


# ── defect 5 — no-direct-tie hedge + off-topic biography dropped ──────────────
class Defect5Hedge(unittest.TestCase):
    STAR = {"name": "A Star is Born", "title": "A Star is Born",
            "type_specialty": "Karaoke Bar", "user_explicit": True}

    def test_no_direct_tie_hedge_dropped(self):
        txt = ("The private rooms provide a contrast to the crowded streets. "
               "While there is no direct tie to Hồ Chí Minh, born Nguyễn Sinh "
               "Cung, the acts of singing recall patriotic songs. "
               "The faint buzz of neon hues sets the bar apart.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            txt, self.STAR, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("no direct tie", scrubbed.lower())
        self.assertNotIn("nguy", scrubbed.lower())
        self.assertIn("private rooms", scrubbed)
        self.assertIn("neon hues", scrubbed)

    def test_no_direct_link_variant_dropped(self):
        txt = ("There is no direct link to the national poet whose verses echo "
               "across the region. "
               "The lounge seats forty at polished wooden tables.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            txt, self.STAR, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("no direct link", scrubbed.lower())
        self.assertIn("forty", scrubbed)


# ── defect (cross-tour art) — foreign museum artwork provenance dropped ───────
class DefectArtProvenance(unittest.TestCase):
    CRAZY = {"name": "The Crazy street", "title": "The Crazy street",
             "type_specialty": "Nightlife Street", "user_explicit": True}

    def test_caillebotte_chicago_digression_dropped(self):
        # The painting's TITLE ("Paris Street; Rainy Day") contains "street", so
        # the sentence looks on-topic — it is dropped anyway because it is an art
        # museum provenance digression, not the street's own content.
        body = ("Here, Paris Street; Rainy Day, Gustave Caillebotte's 1877 oil "
                "painting now housed at the Art Institute of Chicago, finds an "
                "echo in this nightlife spot. "
                "The Crazy street's cramped layout forces bodies and sound to "
                "collide. "
                "The scent of grilled street food mixes with motorbike exhaust.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            body, self.CRAZY, "Ho Chi Minh City, Vietnam",
            outdoor_facts=["The Crazy street is a nightlife area."])
        self.assertTrue(dropped)
        self.assertNotIn("Art Institute of Chicago", scrubbed)
        self.assertNotIn("Caillebotte", scrubbed)
        self.assertIn("cramped layout", scrubbed)


# ── always-drop off-venue classes (survive LLM rephrasing, even when on-topic) ─
class DefectAlwaysDropClasses(unittest.TestCase):
    LONGAN = {"name": "Longan", "type_specialty": "Fruit Cafe",
              "user_explicit": True}
    CRAZY = {"name": "The Crazy street", "type_specialty": "Street Experience",
             "user_explicit": True}
    THI = {"name": "Thi Bar Saigon", "type_specialty": "LGBT Bar",
           "user_explicit": True}
    RAMB = {"name": "Rambutan", "type_specialty": "Bar and Restaurant",
            "user_explicit": True}
    STAR = {"name": "A Star is Born", "type_specialty": "Karaoke Bar",
            "user_explicit": True}

    def test_population_written_out_dropped(self):
        txt = ("The name Longan echoes a tale. Cần Thơ's growth to a population "
               "of 4,199,824 as of 2024 situates this café amid change. "
               "The café channels a pause.")
        s, d = usn.scrub_user_stop_body(txt, self.LONGAN,
                                        "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("4,199,824", s)
        self.assertIn("channels a pause", s)

    def test_military_history_dropped_even_on_topic(self):
        txt = ("The Crazy street pulses with energy. In early 1975, an attack "
               "was launched on the Central Highlands, capturing Buôn Ma Thuột "
               "on March 18. The scent of incense cuts through the air.")
        s, d = usn.scrub_user_stop_body(txt, self.CRAZY,
                                        "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("Buôn Ma Thu", s)
        self.assertIn("incense", s)

    def test_national_figure_biography_dropped(self):
        # The city is NAMED for Hồ Chí Minh so city tokens falsely anchor it.
        txt = ("Nearby, the memory of Hồ Chí Minh, born Nguyễn Sinh Cung, whose "
               "life stretched from 1890 to 1969, hangs across the city. "
               "The constant hum of voices merges with street aromas.")
        s, d = usn.scrub_user_stop_body(txt, self.STAR,
                                        "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("Nguyễn Sinh Cung", s)
        self.assertIn("street aromas", s)

    def test_infrastructure_airport_dropped_even_on_topic(self):
        txt = ("Just as the government approved the construction of Long Thanh "
               "International Airport in 2021, Rambutan reflects the city's "
               "balancing act. Rambutan stands as a quiet witness.")
        s, d = usn.scrub_user_stop_body(txt, self.RAMB,
                                        "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("Airport", s)
        self.assertIn("quiet witness", s)

    def test_firsts_claim_dropped(self):
        txt = ("Thi Bar Saigon marks a turning point. In 2018, it hosted the "
               "first-ever drag show within its walls. The low murmur of "
               "conversations blends with music.")
        s, d = usn.scrub_user_stop_body(txt, self.THI,
                                        "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("first-ever", s)
        self.assertIn("murmur of conversations", s)


# ── final-text pass: re-scrubs the assembled tour; source-gated per block ─────
class DefectFinalTextPass(unittest.TestCase):
    TOUR = (
        "Step-by-Step Audio Guided Tour: HCMC - Cycling Tour\n\n"
        "Stop 1: The LGBT bar 🌈Thi Bar Saigon\n\n"
        "Coordinates: 10.7677, 106.6940\n\nType/Specialty: LGBT Bar\n\n"
        "Specific Examples: drag.\n\n"
        "Orientation: A rainbow flag marks the door. In 2019, Thi Bar Saigon "
        "became a focal point during VietPride, the annual celebration of LGBT "
        "rights. Inside, lively music mingles with cheers.\n\n"
        "Directions: Ride on.\n\n"
        "Stop 2: Notre-Dame Cathedral Basilica of Saigon\n\n"
        "Address: 1 Công xã Paris, Quận 1\n\n"
        "Coordinates: 10.779722, 106.699167\n\nType/Specialty: Cathedral\n\n"
        "Orientation: The towers rise.\n\n"
        "The current cathedral was constructed between 1877 and 1880 by French "
        "administrators. It replaced a wooden church from 1863.\n\n"
        "Directions: Done.\n\n")

    def test_thin_stop_unsourced_date_dropped_famous_kept(self):
        titles = ["The LGBT bar 🌈Thi Bar Saigon",
                  "Notre-Dame Cathedral Basilica of Saigon"]
        out, n = usn.scrub_tour_text_user_stops(
            self.TOUR, titles, "Ho Chi Minh City, Vietnam")
        self.assertGreaterEqual(n, 1)
        # Thin bar: unsourced VietPride 2019 dropped.
        self.assertNotIn("VietPride", out)
        # Famous cathedral (has Address): sourced dates kept.
        self.assertIn("1877", out)
        self.assertIn("1863", out)


# ── defect 8 — dated/anecdote scrub scope: keep sourced dates ─────────────────
class Defect8SourcedDatesKept(unittest.TestCase):
    NDAME = {"name": "Notre-Dame Cathedral Basilica of Saigon",
             "title": "Notre-Dame Cathedral Basilica of Saigon",
             "type_specialty": "Cathedral", "user_explicit": True}

    def test_famous_stop_keeps_its_sourced_dates(self):
        facts = ["Notre-Dame Cathedral Basilica of Saigon was built between "
                 "1863 and 1880 by French colonists."]
        body = ("Notre-Dame Cathedral Basilica of Saigon was built between 1863 "
                "and 1880. "
                "Its two bell towers reach nearly sixty metres. "
                "The red bricks were imported from Marseille.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            body, self.NDAME, "Ho Chi Minh City, Vietnam", outdoor_facts=facts)
        # Nothing dropped: the stop is SOURCED, so dated facts are kept.
        self.assertEqual(dropped, [])
        self.assertIn("1863", scrubbed)
        self.assertIn("1880", scrubbed)

    def test_thin_stop_still_drops_unsourced_date(self):
        thin = {"name": "Mystery Bar", "title": "Mystery Bar",
                "type_specialty": "Bar", "user_explicit": True}
        body = ("Mystery Bar is a cosy spot. "
                "It first opened its doors in 1998 to great fanfare.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            body, thin, "Ho Chi Minh City, Vietnam")  # no facts -> thin
        self.assertTrue(dropped)
        self.assertNotIn("1998", scrubbed)
        self.assertIn("cosy spot", scrubbed)

    def test_hedge_dropped_even_when_sourced(self):
        # A source about the venue never excuses an off-topic national-figure
        # hedge — it is dropped regardless of sourcing.
        facts = ["Notre-Dame Cathedral Basilica of Saigon was built 1863–1880."]
        body = ("Notre-Dame Cathedral Basilica of Saigon was built 1863–1880. "
                "While there is no direct tie to the national hero, the square "
                "outside hosts rallies.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            body, self.NDAME, "Ho Chi Minh City, Vietnam", outdoor_facts=facts)
        self.assertTrue(dropped)
        self.assertNotIn("no direct tie", scrubbed.lower())
        self.assertIn("1863", scrubbed)


# ── defect 10 — user-stops tour drops the generic named-example closer ────────
class Defect10Closer(unittest.TestCase):
    TOUR = (
        "Step-by-Step Audio Guided Tour: Ho Chi Minh City - Cycling Tour\n"
        "Tour-Category: biking\n\n"
        "Stop 1: Rambutan\n\nRambutan is a hostel-bar in the city.\n\n"
        "Stop 2: Longan\n\nLongan is a restaurant.\n\n"
        "Stop 3: An Spa\n\nAn Spa is a spa.\n\n")

    def test_user_stops_close_has_no_carry_with_you(self):
        out = tc.build_conclusion(self.TOUR, venue_name="Ho Chi Minh City",
                                  user_stops=True, use_llm=False,
                                  restaurant_offer=False)
        self.assertNotIn("carry with you", out.lower())
        self.assertNotIn("Rambutan is one", out)

    def test_non_user_stops_close_keeps_example(self):
        out = tc.build_conclusion(self.TOUR, venue_name="Ho Chi Minh City",
                                  user_stops=False, use_llm=False,
                                  restaurant_offer=False)
        self.assertIn("carry with you", out.lower())


# ── defect 1 — a user-stops tour's display category is never 'museum' ─────────
class Defect1TitleCategory(unittest.TestCase):
    def test_user_stop_titles_are_per_job_and_feed_the_guard(self):
        # The title/conclusion guards use _get_user_stop_titles(); prove it
        # reflects what was seeded for THIS job.
        gtt._set_user_stop_titles(["Rambutan", "Longan", "An Spa"])
        self.assertTrue(gtt._get_user_stop_titles())
        self.assertTrue(gtt._is_user_stop_title("Rambutan"))
        self.assertTrue(gtt._is_user_stop_title("An Spa"))
        self.assertFalse(gtt._is_user_stop_title("Metropolitan Museum of Art"))

    def test_title_guard_restores_cycling_not_museum(self):
        # The live root cause: the model wrote a spoken title with no "is a
        # {category} tour" tail, and title_line_guard defaulted the category to
        # "museum" → "… - Museum Tour". It must now read the real category and
        # never default to museum.
        import title_line_guard as tlg
        spoken = ("Step-by-step audio guided tour of Ho Chi Minh City, Vietnam, "
                  "featuring a cycling tour in the biking category.\n\n"
                  "Stop 1: Rambutan\n")
        out, restored = tlg.restore_title_line(spoken)
        self.assertTrue(restored)
        header = out.split("\n", 1)[0]
        self.assertNotIn("Museum", header)
        self.assertIn("Cycling Tour", header)
        self.assertIn("Ho Chi Minh City, Vietnam", header)
        self.assertNotIn("featuring", header)

    def test_title_guard_preserves_genuine_museum(self):
        import title_line_guard as tlg
        spoken = ("Step-by-step audio guided tour of the Museo Reina Sofía in "
                  "Madrid, Spain, is a museum tour.\n\nStop 1: X\n")
        out, _ = tlg.restore_title_line(spoken)
        self.assertIn("Museum Tour", out.split("\n", 1)[0])


# ── defect 9 — _USER_STOP_TITLES is per-job (thread safety) ───────────────────
class Defect9ThreadSafety(unittest.TestCase):
    """Two concurrent JOBS, each in its own thread (its own contextvars Context,
    exactly as generate_tour_text_service runs them), must each read back ONLY
    their own user-stop titles — tour A's titles never leak into tour B, and a
    second job's seeding never overwrites the first's."""

    def test_two_concurrent_jobs_are_isolated(self):
        start = threading.Barrier(2)
        results = {}
        errors = []

        def job(job_id, titles):
            def run():
                try:
                    gtt._set_user_stop_titles(titles)
                    # Interleave: both jobs have now seeded before either reads.
                    start.wait(timeout=5)
                    # A later poi_list rebuild / worker read happens here.
                    seen = set(gtt._get_user_stop_titles())
                    # A worker thread spawned from THIS job must inherit THIS
                    # job's titles (contextvars copied into the pool worker).
                    worker_seen = {}

                    def worker():
                        worker_seen["v"] = set(gtt._get_user_stop_titles())

                    ctx = contextvars.copy_context()
                    t = threading.Thread(target=lambda: ctx.run(worker))
                    t.start()
                    t.join(timeout=5)
                    results[job_id] = (seen, worker_seen.get("v"))
                except Exception as e:  # pragma: no cover
                    errors.append((job_id, repr(e)))

            # Each JOB runs in its OWN thread => its own contextvars Context,
            # just as the service starts each generation job.
            th = threading.Thread(target=run)
            th.start()
            return th

        a = job("A", ["Rambutan", "Longan"])
        b = job("B", ["Eiffel Tower", "Louvre"])
        a.join(timeout=10)
        b.join(timeout=10)

        self.assertEqual(errors, [], f"job errors: {errors}")
        self.assertIn("A", results)
        self.assertIn("B", results)

        a_main, a_worker = results["A"]
        b_main, b_worker = results["B"]

        # Each job sees ONLY its own titles — no cross-contamination.
        self.assertEqual(a_main, {"rambutan", "longan"})
        self.assertEqual(b_main, {"eiffel tower", "louvre"})
        self.assertFalse(a_main & b_main,
                         "job A and job B user-stop titles overlapped (leak)")
        # The pool worker inherits its own job's titles via copy_context().
        self.assertEqual(a_worker, {"rambutan", "longan"})
        self.assertEqual(b_worker, {"eiffel tower", "louvre"})


# ── defect 6 — orientation/body cite only landmarks within ~300 m of the pin ──
class Defect6OffPinLandmark(unittest.TestCase):
    ANSPA = {"name": "An Spa", "title": "An Spa", "type_specialty": "Spa",
             "user_explicit": True, "coordinates": "10.7820, 106.6935"}

    def test_district1_landmarks_dropped_from_district3_spa(self):
        orient = ("An Spa lies just steps from the corner where Đồng Khởi Street "
                  "meets Lam Sơn Square, nearby the Saigon Municipal Theatre. "
                  "Cyclists will notice its quiet entrance amid the city's buzz.")
        scrubbed, dropped = usn.scrub_offpin_landmarks(
            orient, self.ANSPA, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("Lam Sơn", scrubbed)
        self.assertNotIn("Đồng Khởi", scrubbed)
        self.assertIn("quiet entrance", scrubbed)

    def test_body_far_street_dropped(self):
        body = ("Near the corner of Đồng Khởi Street—once the Rue N°6—this spa "
                "stands quietly. "
                "Its role as a sanctuary amid urban motion is unmistakable.")
        scrubbed, dropped = usn.scrub_offpin_landmarks(
            body, self.ANSPA, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("Đồng Khởi", scrubbed)
        self.assertIn("sanctuary", scrubbed)

    def test_nearby_landmark_kept(self):
        # A landmark within 300 m of the pin is NOT dropped (injected resolver
        # returns a point ~120 m away).
        near = (self.ANSPA["coordinates"].split(",")[0].strip(),
                self.ANSPA["coordinates"].split(",")[1].strip())
        def lm_fn(_name):
            return (10.7829, 106.6936)  # ~100 m north of the pin
        txt = ("An Spa sits beside the leafy Trần Quốc Thảo Park. "
               "The entrance is marked by soft lanterns.")
        scrubbed, dropped = usn.scrub_offpin_landmarks(
            txt, self.ANSPA, "Ho Chi Minh City, Vietnam", landmark_fn=lm_fn)
        self.assertEqual(dropped, [])


# ── defect 7 — The Crazy Street resolves to Bùi Viện (pin fix) ────────────────
class Defect7CrazyStreetPin(unittest.TestCase):
    def test_landmark_table_resolves_crazy_street_to_bui_vien(self):
        from landmark_reference import lookup
        hit = lookup("The Crazy street")
        self.assertIsNotNone(hit)
        lat, lng = hit[0], hit[1]
        # Bùi Viện Walking Street, District 1 (~10.767, 106.693).
        self.assertAlmostEqual(lat, 10.767, places=2)
        self.assertAlmostEqual(lng, 106.693, places=2)

    def test_pin_snap_moves_wrong_crazy_street_pin(self):
        import pin_snap
        r = pin_snap.snap_pin(
            title="The Crazy street",
            coordinate=(10.7752, 106.6955),  # the wrong delivered pin
            scope="Ho Chi Minh City, Vietnam",
            scope_center=(10.7769, 106.7009))
        self.assertTrue(r.get("snapped"))
        new = r.get("new_coordinate")
        self.assertIsNotNone(new)
        self.assertAlmostEqual(new[0], 10.767, places=2)
        self.assertAlmostEqual(new[1], 106.693, places=2)

    def test_crazy_street_token_does_not_match_unrelated(self):
        from landmark_reference import lookup
        self.assertIsNone(lookup("Rambutan"))
        self.assertIsNone(lookup("A Star is Born"))


# ── BOUNCE hardening: the exact rephrasings the first 855B run shipped ─────────
class DefectBounceRephrasings(unittest.TestCase):
    """Each string below is quoted from the FIRST 855B delivered artifact that the
    runner falsely PASSED — the literal markers from 855 had been rephrased. The
    scrub must now catch the CLASS, not the phrasing."""

    def test_caillebotte_canvas_digression_dropped(self):
        crazy = {"name": "The Crazy street", "type_specialty": "Vibrant Street Scene",
                 "user_explicit": True}
        body = ("The canvas painstakingly plots architectural lines and changing "
                "city life. "
                "The street's dense mosaic of vendors is alive with contrasts, "
                "echoing the layered urban fabric Caillebotte studied. "
                "Local performers set up impromptu stages near grilling bánh mì.")
        s, d = usn.scrub_user_stop_body(body, crazy, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("Caillebotte", s)
        self.assertNotIn("canvas", s.lower())
        self.assertIn("bánh mì", s)

    def test_acoustic_rephrased_discovery_anecdote_dropped(self):
        ac = {"name": "Acoustic Bar", "type_specialty": "Acoustic Music Bar",
              "user_explicit": True}
        body = ("Acoustic Bar hosts a consistent calendar of shows. "
                "One account that lingers among regulars tells of a fledgling "
                "artist, unknown beyond the neighborhood. "
                "These performances opened doors to professional contracts, "
                "shifting that artist's trajectory from local obscurity to a "
                "wider audience. "
                "The bar's role as a springboard is concrete.")
        s, d = usn.scrub_user_stop_body(body, ac, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        for banned in ("one account", "springboard", "opened doors to professional",
                       "local obscurity"):
            self.assertNotIn(banned, s.lower())
        self.assertIn("calendar of shows", s)

    def test_thi_bar_pioneering_claim_dropped(self):
        thi = {"name": "Thi Bar Saigon", "type_specialty": "LGBT Bar",
               "user_explicit": True}
        body = ("Thi Bar Saigon marks a turning point in the city's social scene. "
                "Before this, drag performances were confined to underground "
                "venues, but this bar opened a door for the community to step "
                "into public view. "
                "The narrow entrance opens onto a space of colorful LED lights.")
        s, d = usn.scrub_user_stop_body(body, thi, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        for banned in ("turning point", "opened a door", "public view",
                       "before this"):
            self.assertNotIn(banned, s.lower())
        self.assertIn("LED lights", s)

    def test_an_spa_ho_tram_offpin_placement_dropped(self):
        spa = {"name": "An Spa", "type_specialty": "Spa & Wellness Center",
               "user_explicit": True, "coordinates": "10.7750, 106.6955"}
        body = ("An Spa sits along a quieter stretch near Hồ Tràm, a coastal "
                "commune now part of Ho Chi Minh City's sprawling new wards. "
                "It embodies the slower rhythms of coastal life just a hundred "
                "kilometers southeast of Saigon. "
                "The light catches on wooden surfaces arranged to soothe.")
        s, d = usn.scrub_user_stop_body(body, spa, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("Hồ Tràm", s)
        self.assertNotIn("coastal commune", s.lower())
        self.assertNotIn("kilometers southeast", s.lower())
        self.assertIn("soothe", s)

    def test_vague_legend_allusion_dropped(self):
        longan = {"name": "Longan", "type_specialty": "Vietnamese restaurant",
                  "user_explicit": True}
        body = ("This place carries a tale, one rooted in the legends of this "
                "land. "
                "The sounds here are in contrast to the timeless narrative "
                "nearby. "
                "The atmosphere inside Longan is warm and lived-in.")
        s, d = usn.scrub_user_stop_body(body, longan, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        self.assertNotIn("legends of this land", s.lower())
        self.assertNotIn("timeless narrative", s.lower())
        self.assertIn("lived-in", s)

    def test_national_figure_regex_no_false_positive_on_a_star_is_born(self):
        # "A Star is Born is known…" must NOT match the "born <Proper>" biography
        # pattern (the (?i) flag used to let [A-Z] match lowercase "is").
        star = {"name": "A Star is Born", "type_specialty": "Karaoke bar",
                "user_explicit": True}
        body = ("A Star is Born is known in the neighborhood as a venue that "
                "champions local musicians. "
                "The worn wooden floors reflect a space where creativity thrives.")
        s, d = usn.scrub_user_stop_body(body, star, "Ho Chi Minh City, Vietnam")
        self.assertEqual(d, [])
        self.assertIn("champions local musicians", s)


# ── grounded-body substitution when a thin stop is fabrication end-to-end ─────
class DefectGroundedSubstitution(unittest.TestCase):
    def test_all_fabrication_body_replaced_with_grounded_description(self):
        poi = {"name": "Mystery Bar", "title": "Mystery Bar",
               "type_specialty": "Cocktail Bar", "user_explicit": True,
               "specific_examples": "Craft cocktails, dim lighting, jazz nights",
               "address": "12 Lê Lợi, District 1, 700000"}
        # Every sentence is a fabricated anecdote / legend → nothing survivable.
        body = ("One pivotal night changed everything here. "
                "A dragon legend is said to haunt these walls. "
                "The owner credits her first record deal to this stage.")
        s, d = usn.scrub_user_stop_body(body, poi, "Ho Chi Minh City, Vietnam")
        self.assertTrue(d)
        # The grounded replacement names the venue + kind + district, no date/
        # anecdote/legend.
        self.assertIn("Mystery Bar", s)
        self.assertIn("cocktail bar", s.lower())
        self.assertIn("District 1", s)
        for banned in ("dragon", "pivotal", "record deal", "legend"):
            self.assertNotIn(banned, s.lower())


# ── user-stops tour: every cross-stop callback is stripped (no shared thread) ─
class DefectUserStopCrossCallback(unittest.TestCase):
    def test_sackbut_callback_stripped(self):
        import cross_stop_reference_guard as csrg
        text = (
            "Stop 1: Rambutan\n\nType/Specialty: Bar\n\n"
            "Rambutan is a lively bar.\n\n"
            "Stop 2: A Star is Born\n\nType/Specialty: Karaoke bar\n\n"
            "The energy here pulses like a secret rite, a launching point not "
            "unlike the sackbut you paused beside earlier, where new voices "
            "began. The street's rhythm shifts once more.\n\n")
        out, n = csrg.strip_all_cross_stop_callbacks_in_text(text)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("sackbut", out)
        self.assertIn("rhythm shifts once more", out)


# ── number-spelled spine recap is stripped by the conclusion rebuild ──────────
class DefectSpelledRecapStripped(unittest.TestCase):
    def test_spelled_out_recap_removed_before_thematic_close(self):
        tour = (
            "Step-by-Step Audio Guided Tour: Ho Chi Minh City - Cycling Tour\n"
            "Tour-Category: biking\n\n"
            "Stop 1: Rambutan\n\nRambutan is a bar.\n\n"
            "Stop 2: Longan\n\nLongan is a restaurant.\n\n"
            "Stop 3: An Spa\n\nAn Spa is a spa.\n\n"
            "That's three stops and nine kilometres. Longan carries a tale rooted "
            "in the legends of this land, and Crazy street rides over the echoes "
            "of a reshaped nation.\n")
        out = tc.rebuild_conclusion(tour, venue_name="Ho Chi Minh City",
                                    user_stops=True)
        self.assertNotIn("reshaped nation", out)
        self.assertNotIn("legends of this land", out)
        self.assertIn("the places you chose", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
