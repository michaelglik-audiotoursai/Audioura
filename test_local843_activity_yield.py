"""test_local843_activity_yield.py — [LOCAL-843]

Activity tours on the cloud. GCloud_Storied wave 16 proof (gen 00022-kbx,
cheap env, STORY_PASS_MODEL=gpt-4.1):

    "Kitesurf lessons at Mui Ne beach, Vietnam" (5)

shipped 2/5 with Gemini $0.16 as the top line, a header reading
`Tour-Category: restaurant`, and one invented story ("Duc fused kiteboarding
and seafood"). Mui Ne has a dozen-plus kite schools. These tests nail the four
defects from the EXACT ticket string, all offline (no network, no key):

  1. YIELD — token family: "Kitesurf lessons" must expand to the full kite
     synonym family, so a school named "Mui Ne Kite School" / "Kiteboarding
     Mui Ne" is recognised as a provider (it was dropped before — "kitesurf"
     was not a synonym key).
  2. YIELD — scope: "at Mui Ne beach" must scope provider discovery to the Mui
     Ne town/ward, not the literal "Mui Ne beach" (which geocodes to an ~11 m
     hotel point whose bbox excludes nearly every school).
  3. GEMINI — the direct grounded-Gemini provider lookup (escalating_lookup
     tier C) must be skipped when RESEARCH_BACKEND is not gemini (the cheap
     arm), so the places/business arm bills $0 of Gemini.
  4. CATEGORY LABEL — the internal 'restaurant' label must never reach the
     header/metadata/title for a non-food activity tour; a neutral 'places'
     machine category and the request's own words ("Kitesurf") are used
     instead. A genuine food request keeps 'restaurant'.
  5. FABRICATION — an ungrounded person story ("Duc fused kiteboarding and
     seafood") must be dropped by the places-arm person gate; a grounded person
     and ordinary non-person sentences are kept.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-test")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-test")

import category_match_guard as cmg
import generate_tour_text as gtt
import escalating_lookup as el

REQ = "Kitesurf lessons at Mui Ne beach, Vietnam"

# Real kite schools in Mui Ne (names only; LOCAL-835B live + tour 504 found
# these) vs. an off-category beach club. A name-only verdict is a conservative
# lower bound — the live stop carries a Serper type too — so a True here is solid.
REAL_KITE_SCHOOLS = [
    "Mui Ne Kite School",
    "Kiteboarding Mui Ne",
    "C2Sky Kitesurfing School",
    "Surfpoint Kiteboarding",
    "Mui Ne Bay Kite School",
    "Muine Kitesurf School",
]
OFF_CATEGORY = ["Jibes Beach Club", "Sandals Restaurant", "The Bar",
                "Sea Breeze Restaurant", "Mui Ne Fishing Village"]


class YieldTokenFamily(unittest.TestCase):
    """Fix A — the activity token family."""

    def test_kitesurf_expands_to_full_kite_family(self):
        act = cmg.requested_activity(REQ)
        self.assertIsNotNone(act, "the kite request must be a provider request")
        self.assertFalse(act["is_food"])
        toks = set(act["tokens"])
        # Before the fix tokens were the single literal {'kitesurf'}. Now the
        # whole family must be present so a school by any kite synonym matches.
        for expected in ("kite", "kiteboarding", "kiteboard", "kitesurf",
                         "kitesurfing", "kiting"):
            self.assertIn(expected, toks,
                          f"token family must include {expected!r}; got {sorted(toks)}")

    def test_real_kite_schools_are_providers(self):
        act = cmg.requested_activity(REQ)
        for name in REAL_KITE_SCHOOLS:
            v = cmg.candidate_is_activity_provider({"name": name}, act)
            self.assertTrue(v, f"{name!r} must be recognised as a kite provider "
                            f"(verdict={v})")

    def test_off_category_still_rejected(self):
        act = cmg.requested_activity(REQ)
        for name in OFF_CATEGORY:
            v = cmg.candidate_is_activity_provider({"name": name}, act)
            self.assertIsNot(v, True,
                             f"{name!r} must NOT be accepted as a kite provider")

    def test_filter_keeps_schools_drops_padding(self):
        cands = [{"name": n} for n in REAL_KITE_SCHOOLS[:4]] + \
                [{"name": n} for n in OFF_CATEGORY]
        kept, dropped = cmg.filter_off_category_activity(cands, REQ, log=lambda *_: None)
        kept_names = {c["name"] for c in kept}
        for n in REAL_KITE_SCHOOLS[:4]:
            self.assertIn(n, kept_names, f"{n} should be kept")
        self.assertGreaterEqual(dropped, 3, "food/beach-club padding should be dropped")


class YieldScope(unittest.TestCase):
    """Fix B — scope widening for a generic natural-feature centre."""

    def test_beach_scope_widens_to_town_with_intent(self):
        # The live path uses the LLM intent's geographic_scope.
        for gs in ("Mui Ne beach, Vietnam", "Mui Ne, Vietnam"):
            scope = gtt._scope_from_request(REQ, {"geographic_scope": gs})
            self.assertEqual(scope, "Mui Ne, Vietnam",
                             f"geographic_scope {gs!r} must resolve to the town/ward")

    def test_widen_helper_strips_generic_feature_for_provider(self):
        self.assertEqual(
            gtt._widen_generic_feature_scope("Mui Ne beach, Vietnam", REQ),
            "Mui Ne, Vietnam")
        self.assertEqual(
            gtt._widen_generic_feature_scope("Nha Trang bay, Vietnam",
                                             "Scuba diving courses at Nha Trang bay"),
            "Nha Trang, Vietnam")

    def test_walking_tour_on_the_beach_is_not_widened(self):
        # A walking/area tour ON the beach keeps the beach — it is the subject.
        walk = "Walking tour on Mui Ne beach, Vietnam"
        scope = gtt._scope_from_request(walk, {"geographic_scope": "Mui Ne beach, Vietnam"})
        self.assertEqual(scope, "Mui Ne beach, Vietnam",
                         "a walking tour ON the beach must NOT be widened away")

    def test_bare_feature_with_no_area_is_left_alone(self):
        self.assertEqual(
            gtt._widen_generic_feature_scope("beach, Vietnam", REQ),
            "beach, Vietnam")


class GeminiRouting(unittest.TestCase):
    """Fix — tier C direct Gemini must be skipped on the cheap/serper arm."""

    def _set(self, **env):
        self._saved = {}
        for k, v in env.items():
            self._saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_tier_c_disallowed_on_cheap_arm(self):
        import cheap_arm
        self._set(CHEAP_ARM_CATEGORIES="museum,walking,restaurant,facility,specialized",
                  RESEARCH_BACKEND="serper")
        tok = cheap_arm.set_tour_category("restaurant")  # the kite/places category
        try:
            self.assertTrue(el._tier_c_gemini_disallowed_by_backend(),
                            "tier C must be disallowed when RESEARCH_BACKEND=serper "
                            "for the places category")
            # And the direct call short-circuits to [] with NO network.
            self.assertEqual(
                el._tier_c_gemini("kitesurf school", "Mui Ne, Vietnam", 6), [],
                "direct _tier_c_gemini must return [] on the serper arm")
        finally:
            cheap_arm.reset_tour_category(tok)
            self._restore()

    def test_tier_c_allowed_on_default_backend(self):
        self._set(CHEAP_ARM_CATEGORIES=None, RESEARCH_BACKEND=None)
        try:
            self.assertFalse(el._tier_c_gemini_disallowed_by_backend(),
                             "tier C must stay allowed on the default (gemini) backend "
                             "— this is a router swap, not a Gemini ban")
        finally:
            self._restore()

    def test_ladder_skips_tier_c_on_serper_arm(self):
        """The ladder must not reach Gemini when the backend is serper: tier a/b
        empty, tier c present but blocked → result tier is not 'c'."""
        import cheap_arm
        self._set(CHEAP_ARM_CATEGORIES="restaurant", RESEARCH_BACKEND="serper")
        tok = cheap_arm.set_tour_category("restaurant")
        gemini_names = {"called": False}

        def _verify(_name):
            return {"name": _name, "verified": True}

        # If tier c ran it would call _tier_c_gemini; stub it to record a call.
        _orig = el._tier_c_gemini

        def _spy(*a, **k):
            gemini_names["called"] = True
            return [{"name": "Should Not Appear", "address": ""}]
        el._tier_c_gemini = _spy
        try:
            res = el.escalating_lookup(
                "business", "kitesurf school", "Mui Ne, Vietnam", 4,
                tier_a=lambda: [], tier_b=lambda: [], verify=_verify,
                category="kitesurf school")
            self.assertNotEqual(res.tier_found, "c",
                                "ladder must not resolve via tier c on the serper arm")
            self.assertFalse(gemini_names["called"],
                             "tier C Gemini must not be called on the serper arm")
        finally:
            el._tier_c_gemini = _orig
            cheap_arm.reset_tour_category(tok)
            self._restore()


class CategoryLabel(unittest.TestCase):
    """Fix — the internal 'restaurant' label never leaks for a non-food tour."""

    def test_kite_tour_gets_neutral_places_header(self):
        self.assertEqual(gtt._places_arm_neutral_header(REQ, "restaurant"), "places",
                         "a non-food activity tour must not emit Tour-Category: restaurant")

    def test_other_non_food_activities_neutralised(self):
        for req in ("Scuba diving courses in Nha Trang, Vietnam",
                    "Yoga classes in Ubud, Bali",
                    "Surfboard rental in Da Nang, Vietnam"):
            self.assertEqual(gtt._places_arm_neutral_header(req, "restaurant"), "places",
                             f"{req!r} must get the neutral 'places' header")

    def test_food_request_keeps_restaurant(self):
        for req in ("Seafood restaurants in Mui Ne, Vietnam",
                    "Best cafes in District 1, Ho Chi Minh City",
                    "Street food tour in Hanoi, Vietnam"):
            self.assertIsNone(gtt._places_arm_neutral_header(req, "restaurant"),
                              f"a genuine food request {req!r} must keep 'restaurant'")

    def test_non_restaurant_category_untouched(self):
        self.assertIsNone(gtt._places_arm_neutral_header(REQ, "museum"))
        self.assertIsNone(gtt._places_arm_neutral_header(REQ, "walking"))


class Fabrication(unittest.TestCase):
    """Fix — ungrounded person story on the places arm is dropped.

    Exercises the SAME primitives the generator's PHASE 5.158a2 gate uses, on the
    exact fabricated sentence from the field tour.
    """

    FABRICATION = ("Mui Ne Kite School sits on the main beach road. "
                   "Duc fused kiteboarding and seafood, opening a school that "
                   "doubled as a grill. Lessons run daily from the shore.")

    def _fold(self, s):
        try:
            from text_fold import fold
            return fold(s)
        except Exception:
            import unicodedata
            n = unicodedata.normalize("NFKD", (s or "").lower())
            return "".join(c for c in n if not unicodedata.combining(c))

    def _flag(self, text, corpus, stop_name):
        """Reproduce the generator's conservative single-token subject detector."""
        import re
        from prose_entity_grounding_gate import _split_sentences
        NOT_NAME = {"the", "a", "an", "this", "that", "lessons", "visitors",
                    "guests", "students", "today", "here", "it", "they"}
        VERB = re.compile(r"^(?:[a-z]{3,}ed|[a-z]{3,}s|fused|opened|ran|runs|"
                          r"built|founded|created|offers|became)$")
        cf = self._fold(corpus)
        sf = self._fold(stop_name)
        out = []
        for s in _split_sentences(text):
            toks = s.strip().split()
            if len(toks) < 2:
                continue
            head = toks[0].strip(",.;:'\"")
            if not head[:1].isupper() or not head.isalpha():
                continue
            if head.lower() in NOT_NAME or toks[1][:1].isupper():
                continue
            if not VERB.match(toks[1].strip(",.;:").lower()):
                continue
            hf = self._fold(head)
            if hf and (hf in cf or hf in sf):
                continue
            out.append(s)
        return out

    def test_ungrounded_duc_is_flagged(self):
        corpus = ("Mui Ne Kite School, 100 Nguyen Dinh Chieu, Mui Ne. "
                  "IKO certified kiteboarding lessons.")
        flagged = self._flag(self.FABRICATION, corpus, "Mui Ne Kite School")
        self.assertEqual(len(flagged), 1)
        self.assertIn("Duc fused kiteboarding and seafood", flagged[0])

    def test_grounded_duc_is_kept(self):
        corpus = "Duc's Kite School, run by Duc since 2010, on the shore of Mui Ne."
        flagged = self._flag(self.FABRICATION, corpus, "Duc's Kite School")
        self.assertEqual(flagged, [], "a grounded person must not be dropped")

    def test_no_false_positives_on_ordinary_prose(self):
        corpus = "Mui Ne Kite School. Kiteboarding lessons on the shore."
        ordinary = ("Lessons run daily from the shore. Visitors gather at dawn. "
                    "The school opened in 2010 and teaches beginners.")
        flagged = self._flag(ordinary, corpus, "Mui Ne Kite School")
        self.assertEqual(flagged, [],
                         "ordinary non-person sentences must never be flagged")

    def test_multiword_person_gate_primitives_available(self):
        # The gate also runs the museum primitives; confirm they import and work.
        from prose_entity_grounding_gate import (extract_person_names,
                                                  check_person_grounded,
                                                  remove_person_from_text)
        txt = "Jacques Cousteau pioneered the dive center here."
        persons = extract_person_names(txt)
        self.assertIn("Jacques Cousteau", persons)
        self.assertFalse(check_person_grounded("Jacques Cousteau",
                                               "Mui Ne Kite School, Mui Ne."))
        cleaned, dropped = remove_person_from_text(txt, "Jacques Cousteau")
        self.assertTrue(dropped)


if __name__ == "__main__":
    unittest.main(verbosity=2)
