"""test_local845_leftovers.py — LOCAL-845.

Two leftover field defects, exercised with the EXACT strings from the ticket,
pure/offline (no network, no DB):

  (1) PROVIDER GUARD — a restaurant passed the activity-provider guard.
      LOCAL-835B live (reports/local835b/gen_835b_final.log): "Scuba diving
      courses in Nha Trang, Vietnam" kept **Nha Trang Xua** (Nhà hàng Nha Trang
      Xưa, a heritage-house RESTAURANT) as a dive provider. Its carried name/type
      had no English food word, so classify_place returned None → UNKNOWN → the
      guard kept it on no evidence. Fix: (a) Vietnamese food words so the name
      alone classifies; (b) a ``category_resolver`` the guard calls on the UNKNOWN
      tail (ONE cheap 24 h-cached Serper Places lookup) that returns the place's
      real category ("Vietnamese restaurant") → off-category. Unknown after the
      lookup is still kept (never drop on no evidence).

  (2) OLYMPIA D1v2 — a famous work dropped on the live canonical set.
      LEAD Mac run after 826B (Orsay, real cache): "[D1v2] DROPPED 'Olympia' —
      no canonical title match". Root cause: the canonical-set prune ("prefer
      longer forms") removed the bare SPARQL work "Olympia" (Manet) because its
      normalized form is a substring of the sibling works "A Modern Olympia" /
      "Une moderne Olympia" (Cézanne). The candidate then had only the longer
      siblings to match, which the specificity gate correctly rejects → DROPPED.
      Fix: story_miner.is_distinct_shorter_work keeps a DISTINCT shorter work (the
      longer adds a distinctive SUBJECT word and the shorter is not its prefix),
      while a genuine left-anchored truncation is still pruned.

Run:
    python3 -m pytest test_local845_leftovers.py -q
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_miner as sm
from story_miner import (match_candidate_to_canonical, is_distinct_shorter_work,
                         _normalize, _is_subject_word)
from venue_resolver import build_dynamic_aliases, build_canonical_titles_from_works
from category_match_guard import (requested_activity,
                                  candidate_is_activity_provider,
                                  filter_off_category_activity)

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "tests", "fixtures", "local826b")


# ══════════════════════════ (1) PROVIDER GUARD ══════════════════════════════
class TestNhaTrangXuaRestaurant(unittest.TestCase):
    """"Nha Trang Xua" (Nhà hàng Nha Trang Xưa) must be dropped from a scuba
    diving-courses tour — it is a restaurant, not a dive provider."""

    REQUEST = "Scuba diving courses in Nha Trang, Vietnam"

    def test_request_is_a_scuba_provider_request(self):
        act = requested_activity(self.REQUEST)
        self.assertIsNotNone(act)
        self.assertEqual(act["trigger"], "courses")
        self.assertFalse(act["is_food"])
        self.assertIn("dive", act["tokens"])

    def test_vietnamese_name_classifies_as_food(self):
        # The full local name carries "Nhà hàng" (restaurant) → off-category even
        # with NO category text and NO resolver.
        act = requested_activity(self.REQUEST)
        cand = {"name": "Nhà hàng Nha Trang Xưa"}
        self.assertIs(candidate_is_activity_provider(cand, act), False)

    def test_bare_name_unknown_without_resolver_is_kept(self):
        # The field shape: the stop reached the guard as the bare "Nha Trang Xua"
        # with no category and no food word → UNKNOWN → kept (the OLD behaviour).
        act = requested_activity(self.REQUEST)
        cand = {"name": "Nha Trang Xua"}
        self.assertIsNone(candidate_is_activity_provider(cand, act))

    def test_resolver_classifies_unknown_tail_off_category(self):
        # LOCAL-845: with a resolver that returns the real Serper Places category
        # ("Vietnamese restaurant"), the UNKNOWN bare name is now off-category.
        act = requested_activity(self.REQUEST)
        cand = {"name": "Nha Trang Xua"}

        def _resolver(name):
            return "Vietnamese restaurant" if "nha trang xua" in name.lower() else None

        self.assertIs(
            candidate_is_activity_provider(cand, act, category_resolver=_resolver),
            False)

    def test_resolver_called_once_per_name(self):
        act = requested_activity(self.REQUEST)
        calls = []

        def _resolver(name):
            calls.append(name)
            return "Seafood restaurant"

        rows = [{"name": "Nha Trang Xua"}, {"name": "Nha Trang Xua"}]
        # filter builds its own call per row; candidate_is_activity_provider calls
        # the resolver at most once per invocation (only on the unknown tail).
        for r in rows:
            candidate_is_activity_provider(r, act, category_resolver=_resolver)
        self.assertEqual(len(calls), 2)

    def test_unknown_after_lookup_is_kept(self):
        # Resolver returns nothing useful (Serper off / no match) → still UNKNOWN
        # → kept. Never drop on no evidence. The name carries no activity signal
        # and no food/landmark word, so only the resolver could decide it.
        act = requested_activity(self.REQUEST)
        cand = {"name": "Phuong Mai Place"}
        self.assertIsNone(
            candidate_is_activity_provider(cand, act, category_resolver=lambda n: None))

    def test_filter_drops_restaurant_keeps_dive_providers(self):
        # The exact scuba delivery from the 835B live run, with Nha Trang Xua as a
        # bare name (no food word) that the resolver classifies as a restaurant.
        rows = [
            {"name": "Vietnam Diving and Training Nha Trang",
             "_serper_category": "Scuba diving center"},
            {"name": "Sailing Club Nha Trang", "_serper_category": "Dive center"},
            {"name": "Nha Trang Xua"},   # bare restaurant, no food word carried
            {"name": "Rainbow Divers", "_serper_category": "Scuba diving center"},
        ]

        def _resolver(name):
            return "Vietnamese restaurant" if name.strip().lower() == "nha trang xua" else None

        logs = []
        kept, dropped = filter_off_category_activity(
            rows, self.REQUEST, log=logs.append, category_resolver=_resolver)
        names = [r["name"] for r in kept]
        self.assertNotIn("Nha Trang Xua", names)
        self.assertEqual(dropped, 1)
        self.assertIn("Nha Trang Xua", " ".join(logs))
        for keep in ("Vietnam Diving and Training Nha Trang",
                     "Sailing Club Nha Trang", "Rainbow Divers"):
            self.assertIn(keep, names)

    def test_dive_provider_not_sent_to_resolver(self):
        # A candidate already decided by its own type never reaches the resolver
        # (cost control: resolver only on the UNKNOWN tail).
        act = requested_activity(self.REQUEST)
        called = []

        def _resolver(name):
            called.append(name)
            return "Vietnamese restaurant"

        cand = {"name": "Rainbow Divers", "_serper_category": "Scuba diving center"}
        self.assertIs(
            candidate_is_activity_provider(cand, act, category_resolver=_resolver),
            True)
        self.assertEqual(called, [], "resolver must not be called for a decided stop")

    def test_food_request_is_noop_even_with_resolver(self):
        # A restaurants request keeps restaurants; resolver irrelevant.
        rows = [{"name": "Nha Trang Xua"}]
        kept, dropped = filter_off_category_activity(
            rows, "Seafood restaurants in Nha Trang, Vietnam",
            log=lambda *_: None, category_resolver=lambda n: "Vietnamese restaurant")
        self.assertEqual(dropped, 0)
        self.assertEqual(len(kept), 1)


# ══════════════════════════ (2) OLYMPIA D1v2 ════════════════════════════════
class TestDistinctShorterWork(unittest.TestCase):
    """The prune-guard primitive, from the exact Orsay strings."""

    def test_olympia_is_distinct_from_modern_olympia(self):
        self.assertTrue(is_distinct_shorter_work(
            _normalize("Olympia"), _normalize("A Modern Olympia")))
        self.assertTrue(is_distinct_shorter_work(
            _normalize("Olympia"), _normalize("Une moderne Olympia")))

    def test_prefix_truncation_is_not_distinct(self):
        # A left-anchored site-extraction truncation is still prunable.
        self.assertFalse(is_distinct_shorter_work(
            _normalize("The Adoration"), _normalize("The Adoration of the Magi")))
        self.assertFalse(is_distinct_shorter_work(
            _normalize("Starry Night"), _normalize("Starry Night Over the Rhone")))

    def test_descriptor_enriched_is_same_work(self):
        # "Olympia" → "Olympia (toile)" (LOCAL-34 material enrichment) is the SAME
        # work: the extra word is a descriptor, not a subject → prunable.
        self.assertFalse(is_distinct_shorter_work(
            _normalize("Olympia"), _normalize("Olympia (toile)")))

    def test_subject_vs_descriptor_words(self):
        self.assertTrue(_is_subject_word("modern"))
        self.assertTrue(_is_subject_word("moderne"))
        self.assertFalse(_is_subject_word("toile"))      # descriptor
        self.assertFalse(_is_subject_word("1863"))       # year
        self.assertFalse(_is_subject_word("the"))        # stopword


class TestOlympiaOnRealCachedCanon(unittest.TestCase):
    """End-to-end on the EXACT cached Q23402 rows (300 works), running the real
    canonical-set prune the generator applies, then the real matcher."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_FIX, "q23402_venue_works_cache.json"),
                  encoding="utf-8") as f:
            cls.works = json.load(f)["works"]
        cls.titles = set(build_canonical_titles_from_works(cls.works))
        sm.CANONICAL_ALIASES = build_dynamic_aliases(cls.works)
        sm.build_bilingual_map_from_sparql(cls.works)

    @staticmethod
    def _prune(titles, guard):
        """Replicate the generate_tour_text 'prefer longer forms' substring prune,
        with (guard=True) or without (guard=False) the LOCAL-845 distinct-work
        exception."""
        nm = {t: _normalize(t) for t in titles}
        remove = set()
        for t in titles:
            nt = nm[t]
            for o in titles:
                if t != o:
                    no = nm[o]
                    if len(nt) < len(no) and nt in no:
                        if guard and is_distinct_shorter_work(nt, no):
                            continue
                        remove.add(t)
                        break
        return set(titles) - remove

    def test_real_cache_contains_the_three_olympias(self):
        oly = sorted(t for t in self.titles if "olympia" in _normalize(t))
        self.assertIn("Olympia", oly)
        self.assertIn("A Modern Olympia", oly)
        self.assertIn("Une moderne Olympia", oly)

    def test_old_prune_drops_olympia(self):
        # Reproduces the field defect: without the guard the bare "Olympia" is
        # pruned out, and the candidate then has no canonical title match.
        pruned = self._prune(self.titles, guard=False)
        self.assertNotIn("Olympia", pruned)
        self.assertIsNone(
            match_candidate_to_canonical("Olympia", pruned, ""),
            "repro: OLD prune makes 'Olympia' DROP")

    def test_new_prune_keeps_olympia_and_it_verifies(self):
        pruned = self._prune(self.titles, guard=True)
        self.assertIn("Olympia", pruned)
        m = match_candidate_to_canonical("Olympia", pruned, "")
        self.assertIsNotNone(m, "'Olympia' must VERIFY, not DROP")
        self.assertEqual(m[0], "Olympia")

    def test_une_moderne_olympia_stays_a_distinct_work(self):
        pruned = self._prune(self.titles, guard=True)
        mm = match_candidate_to_canonical("Une moderne Olympia", pruned, "")
        self.assertIsNotNone(mm)
        self.assertIn("modern", mm[0].lower(),
                      f"'Une moderne Olympia' wrongly folded to {mm[0]!r}")
        self.assertNotEqual(_normalize(mm[0]), _normalize("Olympia"))

    def test_genuine_truncations_still_pruned_on_real_set(self):
        # The guard must not turn the prune into a no-op: a left-anchored
        # truncation present in the real set is still removed.
        titles = set(self.titles) | {"The Church"}  # prefix of The Church at Auvers
        pruned = self._prune(titles, guard=True)
        self.assertNotIn("The Church", pruned,
                         "a prefix truncation must still be pruned")


# ══════════════════════════ wiring sanity ═══════════════════════════════════
class TestWiring(unittest.TestCase):
    def test_generate_tour_text_wires_the_resolver_and_guard(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "generate_tour_text.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("serper_category_resolver", src)
        self.assertIn("is_distinct_shorter_work", src)
        self.assertIn("category_resolver=", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
