"""[D571] The two-question stop source — a building's stops are its parts."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import venue_parts as vp

CHURCH_PARTS = ["Narthex", "Baptismal Font", "Nave", "Stained Glass Windows",
                "Pulpit", "Stations of the Cross", "Altar", "Tabernacle",
                "Side Chapels", "Sacristy", "Crypt"]

def make_ask(kind="Catholic parish church", parts=None):
    parts = CHURCH_PARTS if parts is None else parts
    def ask(prompt):
        if "What kind of place" in prompt:
            return kind
        if "take a tour inside" in prompt:
            import json; return json.dumps(parts)
        return ""
    return ask

def make_grounded(present, absent=(), sources=("https://example.org/parish",)):
    def ask_grounded(prompt):
        import json
        return json.dumps({"present": list(present), "absent": list(absent),
                           "unknown": []}), list(sources)
    return ask_grounded


class TestTheChain(unittest.TestCase):
    def test_church_stops_are_parts_of_the_church(self):
        stops, ev = vp.venue_parts_stops(
            "Our Lady Help of Christians", "Newton MA",
            make_ask(), make_grounded(["Nave", "Altar", "Stained Glass Windows"]), want=4, use_cache=False)
        self.assertEqual(ev["kind"], "Catholic parish church")
        self.assertIn("Nave", stops)
        self.assertIn("Altar", stops)
        # Present parts come first, in class order.
        self.assertEqual(stops[:3], ["Nave", "Stained Glass Windows", "Altar"])

    def test_airport_uses_the_same_chain(self):
        parts = ["Check-In Hall", "Security Checkpoint", "Concourse", "Jetbridge",
                 "Control Tower", "Baggage Claim"]
        stops, ev = vp.venue_parts_stops(
            "Boston Logan International Airport", "Boston MA",
            make_ask("international airport", parts),
            make_grounded(["Check-In Hall", "Control Tower"]), want=3, use_cache=False)
        self.assertEqual(ev["kind"], "international airport")
        self.assertEqual(stops[:2], ["Check-In Hall", "Control Tower"])


class TestD577UnverifiedStillShips(unittest.TestCase):
    def test_unknown_parts_ship_after_the_confirmed_ones(self):
        stops, ev = vp.venue_parts_stops(
            "Some Parish", "Newton MA", make_ask(),
            make_grounded(["Nave"]), want=5, use_cache=False)
        self.assertEqual(stops[0], "Nave")
        self.assertGreater(len(stops), 1, "unknown parts must still ship (D577)")
        self.assertIn("Baptismal Font", ev["unknown"])

    def test_absent_parts_are_dropped(self):
        stops, ev = vp.venue_parts_stops(
            "Some Parish", "Newton MA", make_ask(),
            make_grounded(["Nave"], absent=["Crypt"]), want=20, use_cache=False)
        self.assertNotIn("Crypt", stops)
        self.assertIn("Crypt", ev["absent"])

    def test_a_grounder_that_fails_leaves_everything_unknown_and_shipping(self):
        def boom(prompt): raise RuntimeError("no network")
        stops, ev = vp.venue_parts_stops("Some Parish", "Newton MA", make_ask(), boom, want=4, use_cache=False)
        self.assertEqual(len(stops), 4, "a failed grounding must not empty the tour (D577)")
        self.assertEqual(ev["present"], [])


class TestItDoesNotInviteFabrication(unittest.TestCase):
    """The Sistine Chapel failure (D564) came from asking an open question."""

    def test_class_question_never_names_the_venue(self):
        seen = {}
        def ask(prompt):
            if "take a tour inside" in prompt:
                seen['q2'] = prompt
                return '["Nave"]'
            return "Catholic parish church"
        vp.venue_parts_stops("Our Lady Help of Christians", "Newton MA",
                             ask, make_grounded(["Nave"]), use_cache=False)
        self.assertNotIn("Our Lady Help of Christians", seen['q2'],
                         "Q2 must ask about the CLASS only — naming the venue is what "
                         "invites venue-specific fabrication (D564)")

    def test_per_venue_question_is_closed_not_open(self):
        seen = {}
        def grounded(prompt):
            seen['q3'] = prompt
            return '{"present":["Nave"],"absent":[],"unknown":[]}', []
        vp.venue_parts_stops("Some Parish", "Newton MA", make_ask(), grounded, use_cache=False)
        self.assertIn("which of the", seen['q3'].lower())
        self.assertIn("do not guess", seen['q3'].lower())


class TestParsing(unittest.TestCase):
    def test_numbered_and_bulleted_lists_are_accepted(self):
        got = vp._coerce_list("1. Narthex\n2. Nave — the central approach\n- Altar\n* Crypt")
        self.assertEqual(got, ["Narthex", "Nave", "Altar", "Crypt"])

    def test_explanations_after_a_dash_are_trimmed(self):
        self.assertEqual(vp._coerce_list(["Pulpit - where sermons are delivered"]), ["Pulpit"])


if __name__ == '__main__':
    unittest.main()


class TestQ2ValidatesQ1(unittest.TestCase):
    """Michael: Q2's answer is a stronger sanity check on Q1 than checking Q1 alone."""

    GEMINI_THEOLOGY = ["The People", "Believers", "The Head: Jesus Christ",
                       "The Holy Spirit", "Universal Church"]

    def test_the_theology_answer_that_michael_actually_got_is_rejected(self):
        ok, physical, why = vp.validate_kind_via_parts(self.GEMINI_THEOLOGY)
        self.assertFalse(ok, why)
        self.assertIn("stand next to", why)

    def test_an_architectural_answer_passes(self):
        ok, physical, why = vp.validate_kind_via_parts(CHURCH_PARTS)
        self.assertTrue(ok, why)
        self.assertGreaterEqual(len(physical), 3)

    def test_looks_physical_discriminates(self):
        self.assertTrue(vp.looks_physical("Baptismal Font"))
        self.assertTrue(vp.looks_physical("Control Tower"))
        self.assertFalse(vp.looks_physical("The People"))
        self.assertFalse(vp.looks_physical("Faith"))


class TestCachePolicy(unittest.TestCase):
    def test_denominations_never_collapse(self):
        """St Nicholas Nice has an iconostasis; a Catholic parish has Stations of
        the Cross. Collapsing these kinds would give one the other's parts."""
        self.assertNotEqual(vp.normalise_kind("Russian Orthodox church"),
                            vp.normalise_kind("Catholic parish church"))

    def test_casing_articles_and_punctuation_do_collapse(self):
        self.assertEqual(vp.normalise_kind("a Catholic Parish Church."),
                         vp.normalise_kind("Catholic parish church"))

    def test_a_novel_kind_still_works_on_a_cache_miss(self):
        """His point: never assume the cache covers everything — zoo, industrial
        port, synagogue. A miss costs one ask and must not fail."""
        calls = []
        def ask(prompt):
            calls.append(prompt)
            return '["Enclosure", "Aviary", "Aquarium House"]'
        parts = vp.parts_for_kind("uncached novelty kind %s" % os.getpid(), ask, use_cache=False)
        self.assertEqual(parts, ["Enclosure", "Aviary", "Aquarium House"])
        self.assertEqual(len(calls), 1)


class TestStoryQuestions(unittest.TestCase):
    """The parts list is the skeleton; these are what make it worth listening to."""

    def test_part_question_asks_who_came_not_what_it_is(self):
        p = vp.part_story_prompt("Altar", "St Nicholas Cathedral", "Nice")
        self.assertIn("Who came to this Altar", p)
        self.assertIn("hoping to achieve", p)
        self.assertIn("not a description of what a", p)

    def test_venue_question_asks_why_it_exists_and_who_paid(self):
        p = vp.venue_story_prompt("St Nicholas Cathedral", "Nice", "Russian Orthodox church")
        for needle in ("Why was it built", "Who paid for it", "largest, first, only",
                       "Cite your sources"):
            self.assertIn(needle, p)
