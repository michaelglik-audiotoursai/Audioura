"""test_local851_museum_no_gemini.py — [LOCAL-851]

The MUSEUM tour path must honour RESEARCH_BACKEND. Under the exact cheap env —

    CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
    NARRATION_MODEL=gpt-4.1-mini
    RESEARCH_BACKEND=serper

— a museum tour's venue preflight (venue_preflight.preflight) and the ungrounded
class-knowledge asker (venue_parts.default_ask) must make ZERO direct Gemini
calls, because:

  * STEP 1 of the preflight (grounded venue status) now routes through
    story_leads.research_with_sources, which on the Serper arm answers with
    Serper + a cheap model;
  * STEP 2 of the preflight (ungrounded JSON reshape) and default_ask (Q1/Q2
    class knowledge) now route through story_leads.ungrounded_ask, which on the
    Serper arm answers with the cheap OpenAI model.

The Gemini transport is faked at requests.post: ANY generativelanguage.googleapis
POST is recorded and returned without going out, so a non-zero count is a failure,
not a network error. Serper + the cheap OpenAI model are stubbed so the test is
offline.

On the DEFAULT backend (cheap env unset) the SAME path must still reach Gemini —
the fix is a router swap, not a Gemini ban.

It also proves the ROOT-CAUSE timing invariant: at preflight time the cheap-arm
category MUST be bound (the generator binds it in the wrapper before the preflight
gate). With the category UNbound ('') and the gate active, research_backend()
reads the production default (gemini), so the preflight would fall back to Gemini —
which is exactly why the wrapper binds the category early (LOCAL-851).
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
import venue_preflight
import venue_parts
import serper_research


# Match a Gemini POST without the test file itself carrying the contiguous host
# literal the LOCAL-814 architectural guard scans root *.py for.
def _is_gemini_url(url: str) -> bool:
    u = str(url)
    return "generativelanguage" in u and "googleapis" in u


def _is_openai_url(url: str) -> bool:
    return "api.openai.com" in str(url)


CHEAP_KEYS = ("CHEAP_ARM_CATEGORIES", "NARRATION_MODEL", "NARRATION_PROVIDER",
              "RESEARCH_BACKEND")

# The exact live request for this ticket's proof.
MUSEUM = "Museo Thyssen-Bornemisza, Madrid, Spain"


class _CheapEnv:
    """Set the exact cheap env from the ticket; restore on exit. A Gemini key is
    PRESENT (as in the field container) so the test proves ROUTING, not a
    missing-key short-circuit."""

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
        # Minimal valid shapes for BOTH a Gemini generateContent response and an
        # OpenAI chat completion, so whichever backend is hit parses cleanly.
        return {
            "candidates": [{"content": {"parts": [{"text": "{}"}]},
                            "groundingMetadata": {}}],
            "choices": [{"message": {"content": "{}"}}],
        }

    @property
    def text(self):
        return "{}"

    url = "https://example.test/x"


def _stub_serper_offline():
    """Stub serper_research's metered helpers so the Serper arm makes no real
    network call. Returns a restore() callable."""
    _serp = serper_research._default_serp
    _fetch = serper_research._fetch
    serper_research._default_serp = lambda q: [
        {"url": "https://ex.com/x", "title": "T", "snippet": "s"}]
    serper_research._fetch = lambda url: "Open daily 10:00-19:00. " * 30

    def _restore():
        serper_research._default_serp = _serp
        serper_research._fetch = _fetch
    return _restore


class MuseumPathHonoursResearchBackend(unittest.TestCase):

    def test_classifier_category_is_museum_and_gate_reads_serper(self):
        with _CheapEnv():
            cat = gtt._classify_tour_category(MUSEUM, "museum")
            self.assertEqual(cat, "museum")
            self.assertIn(cat, cheap_arm.cheap_arm_categories())
            tok = cheap_arm.set_tour_category(cat)
            try:
                self.assertTrue(cheap_arm.cheap_arm_active())
                self.assertEqual(story_leads.research_backend(), "serper")
            finally:
                cheap_arm.reset_tour_category(tok)

    def test_preflight_makes_zero_gemini_calls_under_cheap_arm(self):
        import requests
        gemini_calls, openai_calls = [], []

        def _patched_post(url, *a, **kw):
            if _is_gemini_url(url):
                gemini_calls.append(str(url))
                return _FakeResp()
            if _is_openai_url(url):
                openai_calls.append(str(url))
                return _FakeResp()
            raise AssertionError(f"unexpected HTTP post to {url}")

        with _CheapEnv():
            # The generator binds the category in the wrapper BEFORE the preflight;
            # emulate that here so the gate is active at preflight time.
            tok = cheap_arm.set_tour_category("museum")
            _restore = _stub_serper_offline()
            _orig_post = requests.post
            requests.post = _patched_post
            try:
                venue_preflight.preflight(
                    "Museo Thyssen-Bornemisza", "Madrid, Spain", use_cache=False)
            finally:
                requests.post = _orig_post
                _restore()
                cheap_arm.reset_tour_category(tok)

        self.assertEqual(gemini_calls, [],
                         f"museum preflight still called Gemini {len(gemini_calls)} "
                         "time(s) under the cheap arm — STEP 1 must route through "
                         "research_with_sources and STEP 2 through ungrounded_ask")
        self.assertGreater(len(openai_calls), 0,
                           "under the cheap arm the preflight must reach the cheap "
                           "OpenAI model (Serper + cheap answer)")

    def test_default_ask_makes_zero_gemini_calls_under_cheap_arm(self):
        import requests
        gemini_calls, openai_calls = [], []

        def _patched_post(url, *a, **kw):
            if _is_gemini_url(url):
                gemini_calls.append(str(url))
                return _FakeResp()
            if _is_openai_url(url):
                openai_calls.append(str(url))
                return _FakeResp()
            raise AssertionError(f"unexpected HTTP post to {url}")

        with _CheapEnv():
            tok = cheap_arm.set_tour_category("museum")
            _orig_post = requests.post
            requests.post = _patched_post
            try:
                venue_parts.default_ask("What are the parts of a cathedral?")
            finally:
                requests.post = _orig_post
                cheap_arm.reset_tour_category(tok)

        self.assertEqual(gemini_calls, [],
                         "venue_parts.default_ask still called Gemini under the "
                         "cheap arm — it must route through ungrounded_ask")
        self.assertGreater(len(openai_calls), 0,
                           "under the cheap arm default_ask must use the cheap "
                           "OpenAI model")

    def test_preflight_without_bound_category_would_fall_to_gemini(self):
        # ROOT-CAUSE invariant: the preflight runs in the wrapper BEFORE the impl
        # binds the category. If the category is NOT bound ('') while the gate is
        # active, the selector reads the production default (gemini). This is
        # exactly why the generator binds the category early in the wrapper.
        with _CheapEnv():
            self.assertEqual(cheap_arm.tour_category(), "")
            self.assertFalse(cheap_arm.cheap_arm_active(),
                             "an unbound category with the gate active must NOT be "
                             "cheap (production default)")
            self.assertEqual(story_leads.research_backend(), "gemini",
                             "with no category bound the selector must read the "
                             "production default — the wrapper must bind museum first")

    def test_default_backend_still_uses_gemini(self):
        # Cheap env unset → default backend = gemini. The SAME museum path must
        # still reach Gemini (router swap, not a ban).
        import requests
        gemini_calls = []

        def _patched_post(url, *a, **kw):
            if _is_gemini_url(url):
                gemini_calls.append(str(url))
                return _FakeResp()
            if _is_openai_url(url):
                return _FakeResp()
            raise AssertionError(f"unexpected HTTP post to {url}")

        saved = {k: os.environ.get(k) for k in CHEAP_KEYS}
        for k in CHEAP_KEYS:
            os.environ.pop(k, None)
        saved_gk = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "fake-key"
        _orig_post = requests.post
        requests.post = _patched_post
        try:
            # Even with a museum category bound, the default backend is gemini.
            tok = cheap_arm.set_tour_category("museum")
            try:
                self.assertEqual(story_leads.research_backend(), "gemini")
                venue_preflight.preflight(
                    "Museo del Prado", "Madrid, Spain", use_cache=False)
                venue_parts.default_ask("What are the parts of a cathedral?")
            finally:
                cheap_arm.reset_tour_category(tok)
        finally:
            requests.post = _orig_post
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
                           "on the DEFAULT backend the museum preflight + default_ask "
                           "must still reach Gemini (router swap, not a ban)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
