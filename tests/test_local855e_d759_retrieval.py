r"""
LOCAL-855E item 3 / D759 — one Serper search per user stop, narrate ONLY from
the venue-naming snippets, and write a deterministic grounded body + orientation
when no snippet names the venue.
================================================================================
The second bounce proved a regex (and even the fact-sheet verifier) cannot beat a
narrator that invents a fresh phrasing each run, because the fact sheet had
NOTHING retrieved about the venue to contradict the invention — so "played a
critical role for many local artists" slipped through as atmosphere. D759:

  (a) Retrieve: ONE Serper query per user stop, "<name>" <district or city>,
      keeping only snippets that NAME the venue → the fact sheet.
  (b) ≥1 venue-naming snippet: narrate ONLY from it; the verifier keeps SUPPORTED
      sentences; SENSORY only when generic to the venue kind (no specific object,
      decor, smell or geography). [prompt-level — exercised live, not here]
  (c) No venue-naming snippet: the deterministic grounded body + a deterministic
      orientation ("Look for <name> at <where>"). No LLM body at all — so no
      invented sea/coast/harp/altar/film-poster can ship.

These tests run OFFLINE with an injected ``serp_fn`` and a monkeypatched verify
call. They assert: the query shape, the venue-naming filter, and that a
no-snippet stop is rewritten to the deterministic body regardless of the model's
labels (so the SENSORY loophole cannot ship invented detail).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_verify as usv


SOPHIA = """Step-by-Step Audio Guided Tour: Ho Chi Minh City, Vietnam - Cycling Tour

Stop 1: An Spa

Coordinates: 10.7820, 106.6935

Type/Specialty: Spa offering wellness treatments

Specific Examples: Traditional massages, herbal baths

Orientation: Follow the coastal breeze southward along open stretches that meet the South China Sea, where the maritime air drifts in. An Spa is a calm retreat.

Directions: Head north. It is roughly 500 meters away.

Stop 2: A Star is Born

Coordinates: 10.7760, 106.6968

Type/Specialty: Karaoke Bar

Specific Examples: Private rooms, themed nights

Orientation: Notice the harp from the first room and a corner altar beneath vintage film posters. A Star is Born hosts themed nights.

Directions: Head east. It is roughly 400 meters away.
"""


def _labels(label_map):
    def _fake(system, user, api_key, model, timeout=40):
        stops = [{"id": sid, "labels": [{"i": i, "label": l}
                                        for i, l in labs.items()]}
                 for sid, labs in label_map.items()]
        return {"stops": stops}, 800, 90
    return _fake


class TestRetrievalQueryAndFilter(unittest.TestCase):
    def test_query_is_quoted_name_plus_district(self):
        poi = {"name": "Acoustic Bar", "address": "1 Ngô Thời Nhiệm, Quận 3"}
        q = usv._build_stop_query("Acoustic Bar", poi,
                                  "Ho Chi Minh City, Vietnam")
        self.assertIn('"Acoustic Bar"', q)
        self.assertIn("Quận 3", q)

    def test_query_falls_back_to_city_without_address(self):
        q = usv._build_stop_query("An Spa", {}, "Ho Chi Minh City, Vietnam")
        self.assertIn('"An Spa"', q)
        self.assertIn("Ho Chi Minh City", q)

    def test_only_venue_naming_snippets_kept(self):
        def serp(query):
            return ([
                {"title": "Acoustic Bar Ngo Thoi Nhiem",
                 "snippet": "Acoustic Bar on Ngô Thời Nhiệm, live music nightly."},
                {"title": "Acoustic music theory basics",
                 "snippet": "A guide to acoustic guitar tuning."},  # generic, no venue
            ], 1.0)
        snippets, q, nq = usv.retrieve_user_stop_snippets(
            "Acoustic Bar", {"address": "Quận 3"},
            "Ho Chi Minh City", serp_fn=serp)
        self.assertEqual(nq, 1)
        self.assertTrue(any("Ngô Thời Nhiệm" in s for s in snippets))
        self.assertFalse(any("guitar tuning" in s for s in snippets),
                         "a generic non-venue snippet was kept")

    def test_full_phrase_name_requires_the_phrase(self):
        # "A Star is Born" has no distinctive single token (all generic), so a
        # film page must NOT qualify — only a result naming the venue phrase.
        def serp(query):
            return ([{"title": "A Star Is Born (2018 film)",
                      "snippet": "A musician helps a young singer find fame."}],
                    1.0)
        snippets, _q, _nq = usv.retrieve_user_stop_snippets(
            "A Star is Born", {}, "Ho Chi Minh City", serp_fn=serp)
        # The film snippet does not contain the full folded venue phrase as used
        # about the venue; it is a movie plot — must be dropped.
        self.assertEqual(snippets, [], f"a film page qualified: {snippets}")


class TestNoSnippetDeterministic(unittest.TestCase):
    """D759 (c) — a stop with no venue-naming snippet gets the deterministic body
    and orientation, so no invented sensory detail (sea/harp/altar/poster) ships,
    EVEN IF the model labels those invented sentences SENSORY."""

    def setUp(self):
        self._orig = usv._call_openai

    def tearDown(self):
        usv._call_openai = self._orig

    def test_no_snippet_wipes_invented_sensory(self):
        # The model (wrongly) calls every invented sentence SENSORY — but with no
        # venue-naming snippet the stop is rewritten deterministically anyway.
        usv._call_openai = _labels({
            0: {0: "SENSORY", 1: "SENSORY"},
            1: {0: "SENSORY", 1: "SENSORY"},
        })

        def serp(query):
            return ([], 1.0)   # retrieval finds NO venue-naming snippet

        out, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["An Spa", "A Star is Born"],
            "Ho Chi Minh City, Vietnam", api_key="x", serp_fn=serp)
        # None of the invented physical details survive.
        for bad in ["South China Sea", "coastal breeze", "maritime air",
                    "harp from the first room", "corner altar",
                    "vintage film posters"]:
            self.assertNotIn(bad, out, f"invented detail shipped: {bad}")
        # Each stop keeps a deterministic orientation + grounded body.
        self.assertIn("Look for An Spa", out)
        self.assertIn("An Spa is", out)
        self.assertIn("Look for A Star is Born", out)
        for s in rep["stops"]:
            self.assertTrue(s["grounded"])
            self.assertEqual(s["snippets"], 0)
        self.assertEqual(rep["serper_queries"], 2)

    def test_deterministic_path_fires_without_model(self):
        # Even when the verify model call cannot run (no key), a no-snippet stop
        # is still rewritten deterministically — the SENSORY loophole cannot ride
        # on an unavailable model.
        def serp(query):
            return ([], 1.0)
        out, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["An Spa", "A Star is Born"],
            "Ho Chi Minh City, Vietnam", api_key="", serp_fn=serp)
        self.assertFalse(rep["ran"])
        for bad in ["South China Sea", "harp from the first room",
                    "vintage film posters"]:
            self.assertNotIn(bad, out, f"invented detail shipped: {bad}")
        self.assertIn("Look for An Spa", out)


class TestOrientation(unittest.TestCase):
    def test_orientation_uses_name_and_place(self):
        o = usv._deterministic_orientation(
            {"name": "An Spa", "address": "Trần Quốc Thảo, Quận 3"},
            "Ho Chi Minh City")
        self.assertTrue(o.startswith("Look for An Spa at"))
        self.assertIn("Quận 3", o)

    def test_orientation_city_fallback(self):
        o = usv._deterministic_orientation({"name": "An Spa"},
                                           "Ho Chi Minh City, Vietnam")
        self.assertEqual(o, "Look for An Spa in Ho Chi Minh City.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
