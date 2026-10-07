#!/usr/bin/env python3
"""test_local612_shortfall_everywhere.py — LOCAL-612 (D616 on EVERY tour type).

D616's honest shortfall sentence ("…so this tour has X stops rather than the Y you
asked for") was only emitted on the site-first/exhibition museum path (LOCAL-600).
Vietnam National Museum of Fine Arts #402 (4 of 5) and Harvard #400 (6 of 7)
delivered fewer stops with NO explanation because they flow through the MAIN
delivery loop (a verified-works museum), and so did every walking / biking /
by-reference tour that fell short.

LOCAL-612 widens the ONE builder (about_museum_stop.build_shortfall_sentence,
never a second one) with an outdoor mode and wires the sentence into:
  * the non-pool MAIN delivery loop (fresh museum, walking, biking, by-reference),
    led into Stop 1's opening section; and
  * the outdoor stop-pool reuse path (assemble_outdoor_tour).

These tests pin, per path and OFFLINE:
  * the sentence is PRESENT at 4/5 and ABSENT at 5/5;
  * it APPEARS ONCE in Stop 1;
  * the museum phrasing is byte-identical to LOCAL-600 (no regression);
  * the outdoor phrasing uses the route wording, no museum vocabulary;
  * the wiring exists in the engine and the orchestrator, and double-emission is
    suppressed during the orchestrator's nested generation.

Run: python3 -m pytest tests/test_local612_shortfall_everywhere.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from about_museum_stop import build_shortfall_sentence, build_opening_section, AboutStop
import stop_pool_assembly as asm


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


class TestBuilderOutdoorMode(unittest.TestCase):
    """The single builder gains an outdoor mode; museum default is unchanged."""

    def test_outdoor_present_at_four_of_five(self):
        s = build_shortfall_sentence("Freedom Trail, Boston", 0, 4, 5, mode="outdoor")
        self.assertEqual(
            s,
            "We could confirm 4 stops along this route, so this tour has 4 stops "
            "rather than the 5 you asked for.")

    def test_outdoor_absent_at_five_of_five(self):
        self.assertEqual(
            build_shortfall_sentence("Freedom Trail", 0, 5, 5, mode="outdoor"), "")

    def test_outdoor_absent_when_requested_unknown(self):
        self.assertEqual(
            build_shortfall_sentence("Freedom Trail", 0, 4, None, mode="outdoor"), "")

    def test_outdoor_singular_grammar(self):
        self.assertEqual(
            build_shortfall_sentence("A River Walk", 0, 1, 3, mode="outdoor"),
            "We could confirm 1 stop along this route, so this tour has 1 stop "
            "rather than the 3 you asked for.")

    def test_outdoor_uses_no_museum_vocabulary(self):
        s = build_shortfall_sentence("Harbor Walk", 0, 2, 6, mode="outdoor")
        low = s.lower()
        for word in ("exhibition", "exhibitions", "museum", "on view"):
            self.assertNotIn(word, low, f"outdoor sentence must not say {word!r}")

    def test_museum_default_unchanged(self):
        # Byte-identical to the LOCAL-600 contract (default mode).
        self.assertEqual(
            build_shortfall_sentence("MassArt Art Museum, Boston, MA", 3, 5, 7),
            "MassArt Art Museum currently has 3 exhibitions on view, so this tour "
            "has 5 stops rather than the 7 you asked for.")

    def test_museum_mode_explicit_matches_default(self):
        self.assertEqual(
            build_shortfall_sentence("X Museum", 3, 5, 7, mode="museum"),
            build_shortfall_sentence("X Museum", 3, 5, 7))


class TestOutdoorAssemblyPath(unittest.TestCase):
    """Walking/biking pool reuse: the sentence leads Stop 1 and appears once."""

    def _stops(self):
        return [
            {"title": "Old State House", "narration": "Narration one.",
             "orientation": "Stand facing the balcony.",
             "coordinates": "42.3588, -71.0576", "directions": "Head east."},
            {"title": "Faneuil Hall", "narration": "Narration two.",
             "orientation": "Face the grasshopper weathervane.",
             "coordinates": "42.3600, -71.0568"},
        ]

    def _assemble(self, sentence):
        return asm.assemble_outdoor_tour(
            "Freedom Trail, Boston, MA", "walking", "walking", "Walking", "Walking",
            new_stops=[], pooled_stops=self._stops(),
            shortfall_sentence=sentence).tour_text

    def test_present_at_two_of_five_once_in_stop1(self):
        sentence = build_shortfall_sentence(
            "Freedom Trail", 0, 2, 5, mode="outdoor")
        text = self._assemble(sentence)
        self.assertEqual(text.count(sentence), 1, "must appear exactly once")
        i1 = text.find("Stop 1:")
        i2 = text.find("Stop 2:")
        self.assertTrue(i1 != -1 and i2 != -1)
        self.assertTrue(i1 < text.find(sentence) < i2,
                        "the sentence must lead Stop 1, before Stop 2")

    def test_absent_when_ask_met(self):
        # delivered(2) == requested(2) → builder returns "", nothing injected.
        sentence = build_shortfall_sentence(
            "Freedom Trail", 0, 2, 2, mode="outdoor")
        self.assertEqual(sentence, "")
        text = self._assemble(sentence)
        self.assertNotIn("rather than", text)
        self.assertNotIn("along this route", text)

    def test_opening_section_rendered_before_orientation(self):
        sentence = build_shortfall_sentence("Trail", 0, 2, 5, mode="outdoor")
        text = self._assemble(sentence)
        stop1 = text[text.find("Stop 1:"):text.find("Stop 2:")]
        # The shortfall (opening section) comes before the Orientation line.
        self.assertLess(stop1.find(sentence), stop1.find("Orientation:"))


class TestMuseumOpeningSectionPath(unittest.TestCase):
    """Fresh/pool museum: the sentence folds into the opening section, after the
    About story and once only (reusing the LOCAL-600 primitive)."""

    def _about(self):
        return AboutStop(
            museum_name="Vietnam National Museum of Fine Arts",
            narration="The Vietnam National Museum of Fine Arts preserves the "
                      "nation's art heritage.",
            practical_facts="", site_domain="vnfam.vn", as_of="October 2026")

    def test_present_at_four_of_five_once(self):
        sentence = build_shortfall_sentence(
            "Vietnam National Museum of Fine Arts", 4, 4, 5)
        section = build_opening_section(self._about(), shortfall_sentence=sentence)
        self.assertEqual(section.count(sentence), 1)
        self.assertLess(section.index("preserves the"),
                        section.index("rather than"))

    def test_absent_at_five_of_five(self):
        sentence = build_shortfall_sentence(
            "Vietnam National Museum of Fine Arts", 5, 5, 5)
        self.assertEqual(sentence, "")
        section = build_opening_section(self._about(), shortfall_sentence="")
        self.assertNotIn("rather than", section)


class TestStopsCountEqualsDelivered(unittest.TestCase):
    """Deliverable 2: the tour row's stops_count is the DELIVERED number — the
    orchestrator service derives it from the count of delivered audio files
    (one audio_N.mp3 per delivered stop), never the requested number. Pin the
    derivation so a future change cannot silently reintroduce a requested-count."""

    def test_actual_stops_counts_delivered_audio_files(self):
        src = _read("tour_orchestrator_service.py")
        # stops_count persisted == actual_stops == len(audio_files_in_zip)
        self.assertIn("actual_stops = len(audio_files_in_zip)", src)
        self.assertIn(r"re.fullmatch(r'audio_\d+\.mp3', n)", src)
        self.assertIn('stops_count=ACTIVE_JOBS[job_id].get("actual_stops")', src)


class TestWiring(unittest.TestCase):
    """Prove the fix is wired into the engine, the orchestrator and the assembler —
    not only the pure helpers exercised above."""

    @classmethod
    def setUpClass(cls):
        cls.gen = _read("generate_tour_text.py")
        cls.orch = _read("stop_pool_orchestrator.py")
        cls.asmb = _read("stop_pool_assembly.py")

    def test_engine_computes_inline_shortfall(self):
        self.assertIn("_inline_shortfall", self.gen)
        self.assertIn("build_shortfall_sentence", self.gen)
        # Keyed on the listener's original ask vs delivered.
        self.assertIn("_requested_stop_count_original", self.gen)

    def test_engine_leads_stop1_with_inline_shortfall(self):
        # Injected into Stop 1's orientation prefix (i == 0), before the prolog.
        self.assertIn("if i == 0 and _inline_shortfall:", self.gen)

    def test_engine_has_suppression_flag(self):
        self.assertIn("_SUPPRESS_INLINE_SHORTFALL", self.gen)

    def test_engine_skips_site_first_path(self):
        # The site-first path is owned by the orchestrator/overview; the main loop
        # must not also inject for it.
        self.assertIn("_exhibition_stops_source != 'site_exhibition'", self.gen)

    def test_orchestrator_suppresses_during_nested_gen(self):
        self.assertIn("_suppress_inline_shortfall", self.orch)
        # Both nested generate_fn calls are wrapped.
        self.assertEqual(self.orch.count("with _suppress_inline_shortfall():"), 2)

    def test_orchestrator_passes_outdoor_shortfall(self):
        self.assertIn("mode='outdoor'", self.orch)
        self.assertIn("shortfall_sentence=_outdoor_shortfall", self.orch)

    def test_assembler_accepts_outdoor_shortfall(self):
        self.assertIn("shortfall_sentence: str = \"\"", self.asmb)
        self.assertIn('ordered[0]["_opening_section"]', self.asmb)

    def test_single_builder_only(self):
        # LOCAL-612 must not introduce a second builder.
        self.assertEqual(self.gen.count("def build_shortfall_sentence"), 0,
                         "the engine must reuse the builder, not define one")
        about = _read("about_museum_stop.py")
        self.assertEqual(about.count("def build_shortfall_sentence"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
