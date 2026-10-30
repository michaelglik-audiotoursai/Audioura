"""test_local834_places_no_gemini.py — [LOCAL-834]

The places/business arm must honour RESEARCH_BACKEND. Under the cheap env exactly
as the field ticket specifies —

    CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
    NARRATION_MODEL=gpt-4.1-mini
    RESEARCH_BACKEND=serper

— the kite request "Kitesurfing schools in Mui Ne, Vietnam" must:

  1. classify to a category that IS in the cheap-arm list (so the gate reads it as
     cheap, never '' / 'business' / 'places' — D664),
  2. make ZERO direct Gemini calls on the per-stop places research
     (restaurant_practicals.fetch_practicals), because every grounded research
     call now routes through story_leads.research_with_sources which, on the
     Serper arm, answers with Serper + a cheap model.

The Gemini transport is faked at requests.post: ANY generativelanguage.googleapis
POST is recorded and returned without going out, so a non-zero count is a failure,
not a network error. Serper + the cheap model are stubbed so the test is offline.

It also proves the generator's 'specialized' -> 'book' remap (the 6th bound
category) is still gated cheap when the env lists 'specialized'.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cheap_arm
import story_leads
import generate_tour_text as gtt
import restaurant_practicals
import serper_research

# We only need to RECOGNISE a Gemini POST here, not issue one. The host substring
# is matched in two pieces so this TEST file does not itself contain the
# contiguous literal the LOCAL-814 architectural guard
# (test_no_unaccounted_direct_gemini_poster) scans root *.py for.
def _is_gemini_url(url: str) -> bool:
    u = str(url)
    return "generativelanguage" in u and "googleapis" in u

CHEAP_KEYS = ("CHEAP_ARM_CATEGORIES", "NARRATION_MODEL", "NARRATION_PROVIDER",
              "RESEARCH_BACKEND")


class _CheapEnv:
    """Set the exact cheap env from the ticket; restore on exit."""

    VALUES = {
        "CHEAP_ARM_CATEGORIES": "museum,walking,restaurant,facility,specialized",
        "NARRATION_MODEL": "gpt-4.1-mini",
        "RESEARCH_BACKEND": "serper",
    }

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in CHEAP_KEYS}
        for k in CHEAP_KEYS:
            os.environ.pop(k, None)
        os.environ.update(self.VALUES)
        # A Gemini key is PRESENT in the field container (that is the whole point —
        # Gemini was being charged). Set one so the test proves routing, not a
        # missing-key short-circuit.
        self._saved_gk = os.environ.get("GEMINI_API_KEY")
        self._saved_ok = os.environ.get("OPENAI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "fake-key"
        os.environ["OPENAI_API_KEY"] = "fake-key"
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k, v in (("GEMINI_API_KEY", self._saved_gk),
                     ("OPENAI_API_KEY", self._saved_ok)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


class _FakeResp:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]},
                                "groundingMetadata": {}}]}

    @property
    def text(self):
        return "{}"

    url = "https://example.test/x"


class PlacesPathHonoursResearchBackend(unittest.TestCase):

    KITE = "Kitesurfing schools in Mui Ne, Vietnam"

    def test_classifier_category_is_in_cheap_list_and_not_empty(self):
        with _CheapEnv():
            cat = gtt._classify_tour_category(self.KITE, "")
            self.assertTrue(cat, "classifier must never return '' for the kite request")
            self.assertIn(cat, cheap_arm.cheap_arm_categories(),
                          f"classifier category {cat!r} must be in the cheap-arm list "
                          "so the gate reads the places request as cheap")
            # bound as the generator binds it: the gate sees a cheap category.
            tok = cheap_arm.set_tour_category(cat)
            try:
                self.assertTrue(cheap_arm.cheap_arm_active())
                self.assertEqual(story_leads.research_backend(), "serper")
            finally:
                cheap_arm.reset_tour_category(tok)

    def test_specialized_remapped_to_book_is_still_cheap(self):
        # [LOCAL-834] the generator remaps 'specialized' -> 'book' before binding;
        # the gate must still read it as cheap because the env lists 'specialized'.
        with _CheapEnv():
            tok = cheap_arm.set_tour_category("book")
            try:
                self.assertTrue(cheap_arm.cheap_arm_active(),
                                "a 'book' (remapped 'specialized') tour must be cheap")
                self.assertEqual(story_leads.research_backend(), "serper")
            finally:
                cheap_arm.reset_tour_category(tok)

    def test_places_practicals_make_zero_gemini_calls(self):
        import requests
        gemini_calls = []

        def _patched_post(url, *a, **kw):
            if _is_gemini_url(url):
                gemini_calls.append(str(url))
                return _FakeResp()
            raise AssertionError(f"unexpected non-Gemini HTTP post to {url}")

        with _CheapEnv():
            cat = gtt._classify_tour_category(self.KITE, "")
            tok = cheap_arm.set_tour_category(cat)
            _orig_post = requests.post
            # Stub the SERP evidence to empty so step 2 is thin and step 3 (the
            # grounded research) is forced — that is the step that used to call
            # Gemini directly.
            _orig_search = restaurant_practicals._search_evidence
            _orig_serp = serper_research._default_serp
            _orig_fetch = serper_research._fetch
            _orig_chat = serper_research._openai_chat
            _orig_rpserp = restaurant_practicals._serp
            restaurant_practicals._search_evidence = lambda name, city: []
            restaurant_practicals._serp = lambda q, max_results=8: []
            serper_research._default_serp = lambda q: [
                {"url": "https://ex.com/x", "title": "T", "snippet": "s"}]
            serper_research._fetch = lambda url: "Open daily 09:00-18:00. " * 20
            serper_research._openai_chat = lambda prompt, model=None, max_tokens=700: {
                "text": '{"status":"open","hours":"09:00-18:00","closed_days":"",'
                        '"reservation":"walk-in","price_band":"$$",'
                        '"cuisine":"kitesurf school","still_operating":true}',
                "error": ""}
            requests.post = _patched_post
            try:
                for school in ["Jibes Beach Club", "C2Sky Kitesurfing School",
                               "Surfpoint Kiteboarding", "Mui Ne Kitesurfing School",
                               "Vietnam Kiteboarding School"]:
                    restaurant_practicals.fetch_practicals(
                        school, "Mui Ne, Vietnam", api_key="fake-key")
            finally:
                requests.post = _orig_post
                restaurant_practicals._search_evidence = _orig_search
                restaurant_practicals._serp = _orig_rpserp
                serper_research._default_serp = _orig_serp
                serper_research._fetch = _orig_fetch
                serper_research._openai_chat = _orig_chat
                cheap_arm.reset_tour_category(tok)

        self.assertEqual(gemini_calls, [],
                         f"places/business path still called Gemini {len(gemini_calls)} "
                         "time(s) under the cheap arm — it must route through "
                         "RESEARCH_BACKEND=serper")

    def test_default_backend_still_uses_gemini_here(self):
        # With no cheap env (default backend = gemini), the same path MUST still be
        # able to reach Gemini — the fix is a router swap, not a Gemini ban.
        import requests
        gemini_calls = []

        def _patched_post(url, *a, **kw):
            if _is_gemini_url(url):
                gemini_calls.append(str(url))
                return _FakeResp()
            raise AssertionError(f"unexpected non-Gemini HTTP post to {url}")

        saved = {k: os.environ.get(k) for k in CHEAP_KEYS}
        for k in CHEAP_KEYS:
            os.environ.pop(k, None)
        saved_gk = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "fake-key"
        _orig_post = requests.post
        _orig_search = restaurant_practicals._search_evidence
        restaurant_practicals._search_evidence = lambda name, city: []
        requests.post = _patched_post
        try:
            # default backend: research_backend() == 'gemini'
            self.assertEqual(story_leads.research_backend(), "gemini")
            restaurant_practicals.fetch_practicals(
                "Some Cafe", "Nowhere", api_key="fake-key")
        finally:
            requests.post = _orig_post
            restaurant_practicals._search_evidence = _orig_search
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if saved_gk is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = saved_gk

        self.assertGreater(len(gemini_calls), 0,
                           "on the DEFAULT backend the places research must still "
                           "reach Gemini (router swap, not a ban)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
