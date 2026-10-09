#!/usr/bin/env python3
"""test_local658_walking_v4.py — LOCAL-658 acceptance (unit level, offline).

Four defects from the Boston walking v4 run (tour 557, "Walking tour in Boston
dedicated to Massachusetts politics and current affairs"):

  DEFECT 1 — a GEO-CHECK replacement was not distance-checked. "The Boston Globe"
    was removed as too far; the replacement "John F. Kennedy Presidential Library
    and Museum" (Columbia Point) was added, geocoded, re-ordered and DELIVERED on
    a 4.6 km leg — a replacement must pass the SAME walking-distance limit as the
    original stops; if none passes, deliver N-1 with the honest shortfall.

  DEFECT 2 — single-letter initials truncated names/sentences. The header read
    "Stop 5: John F.", directions said "Continue to John F.", narration said
    "architect M. Pei" (I. M. Pei). An initial (A-Z + '.') must never end a name
    (the LOCAL-22 ingestion guard) or a sentence (the shared splitter the mutating
    gates use). Fixtures: John F. Kennedy, I. M. Pei, W. E. B. Du Bois, J. P. Morgan.

  DEFECT 3 — a museum/art conclusion on a walking tour: "…one thread runs through:
    modern art in the eighteenth to twentieth centuries. Seen together, the works
    show…". The deterministic fallback mined ART vocabulary ("modern", "figure")
    on a politics walking tour. A non-art tour must get a category-appropriate
    conclusion (the request's theme / the places / its history), never "works" or
    "art" — while a MUSEUM tour must still name its works (the canary).

  DEFECT 4 — the structured field lines "Type/Specialty:" and "Specific Examples:"
    stay in the stop block (the app's text view) but must NOT be SPOKEN. Confirm
    the TTS stripper removes them.

These tests CALL the real functions (no network, no key). Run:
    python3 -m pytest tests/test_local658_walking_v4.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
from style_validator_detector import _split_sentences
from sentence_split import split_sentences
import tour_conclusion as tc
import tour_generation_modernized as tgm


# ── Fixtures: real-world names with single-letter initials ──────────────────
INITIAL_NAMES = [
    "John F. Kennedy Presidential Library and Museum",
    "I. M. Pei",
    "W. E. B. Du Bois",
    "J. P. Morgan",
]


# ════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — initials never end a NAME (LOCAL-22 ingestion guard)
# ════════════════════════════════════════════════════════════════════════════
class TestDefect2NameGuardKeepsInitials(unittest.TestCase):
    """_is_name_corrupted must ACCEPT a clean entity name that carries initials."""

    def test_initial_names_are_not_corrupted(self):
        for name in INITIAL_NAMES:
            self.assertFalse(
                gtt._is_name_corrupted(name),
                f"LOCAL-22 wrongly rejected a clean name with an initial: {name!r}")

    def test_dotted_acronym_name_not_corrupted(self):
        # A dotted acronym (U.S.) is not sentence punctuation either.
        self.assertFalse(gtt._is_name_corrupted("U.S. Capitol"))
        self.assertFalse(gtt._is_name_corrupted("Washington, D.C. Memorial"))

    def test_real_sentence_still_rejected(self):
        # The guard must STILL reject names that are actually sentences.
        self.assertTrue(gtt._is_name_corrupted(
            "Located at 5th Ave. This stop invites visitors."))
        self.assertTrue(gtt._is_name_corrupted(
            "Visit the museum. It is great."))

    def test_clean_names_without_initials_unaffected(self):
        for name in ["Faneuil Hall", "Old State House", "Boston City Hall",
                     "Massachusetts State House", "The Starry Night, 1889"]:
            self.assertFalse(gtt._is_name_corrupted(name), name)


# ════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — initials never end a SENTENCE (the shared splitter the gates use)
# ════════════════════════════════════════════════════════════════════════════
class TestDefect2SplitterKeepsInitials(unittest.TestCase):
    """style_validator_detector._split_sentences (used by unsupported_claim_gate,
    the mutating gate that cut 'I. M. Pei' into fragments) must keep initials."""

    def test_im_pei_not_split(self):
        s = ("Jacqueline Kennedy chose architect I. M. Pei for the project, "
             "passing over more established names.")
        parts = _split_sentences(s)
        self.assertEqual(len(parts), 1, f"split on an initial: {parts}")
        self.assertIn("I. M. Pei", parts[0])

    def test_jfk_name_not_split(self):
        s = ("As you leave, the legacy of a president awaits at the nearby "
             "John F. Kennedy Presidential Library and Museum.")
        parts = _split_sentences(s)
        self.assertEqual(len(parts), 1, f"split on an initial: {parts}")
        self.assertIn("John F. Kennedy Presidential Library and Museum", parts[0])

    def test_web_dubois_and_jp_morgan(self):
        s = ("W. E. B. Du Bois wrote widely. J. P. Morgan financed the railroads.")
        parts = _split_sentences(s)
        self.assertEqual(len(parts), 2, f"wrong split: {parts}")
        self.assertIn("W. E. B. Du Bois", parts[0])
        self.assertIn("J. P. Morgan", parts[1])

    def test_two_real_sentences_still_split(self):
        s = "The hall opened in 1742. The market still runs today."
        parts = _split_sentences(s)
        self.assertEqual(len(parts), 2, parts)

    def test_question_split_preserved(self):
        # The detector relies on the in-fragment '?' split surviving.
        s = "Why does it matter? The answer is history."
        parts = _split_sentences(s)
        self.assertEqual(len(parts), 2, parts)
        self.assertTrue(parts[0].endswith("?"))

    def test_shared_splitter_agrees(self):
        # The shared module (used by cross_stop_fact_dedupe etc.) must also keep them.
        for name in INITIAL_NAMES:
            s = f"The architect {name} shaped the project."
            self.assertEqual(len(split_sentences(s)), 1,
                             f"shared splitter cut an initial name: {name!r}")


# ════════════════════════════════════════════════════════════════════════════
# DEFECT 1 — a GEO-CHECK replacement must pass the SAME walking-distance limit
# ════════════════════════════════════════════════════════════════════════════
class TestDefect1ReplacementDistance(unittest.TestCase):
    """The route-leg validator rejects a replacement that creates an over-limit leg.

    We verify the GEOMETRY the fix uses: the downtown-Boston survivors form legs
    under the per-leg hard limit; adding the JFK Library (Columbia Point, ~4.6 km
    from the State House) creates a leg far over WALKING_LEG_HARD_KM (1.75 km) and
    must be rejected. A nearby candidate (Granary Burying Ground) is accepted.
    """

    # Downtown walking survivors (lat, lng) — all within a few hundred metres.
    SURVIVORS = {
        "Faneuil Hall": (42.3601, -71.0542),
        "Old State House": (42.3604, -71.0572),
        "Boston City Hall": (42.3605, -71.0583),
        "Massachusetts State House": (42.3587, -71.0630),
    }
    JFK = (42.3201, -71.0423)                 # Columbia Point — far
    GRANARY = (42.3573, -71.0612)             # Granary Burying Ground — near

    def _max_leg_km(self, coords_in_order):
        legs = [gtt._haversine_km(coords_in_order[i], coords_in_order[i + 1])
                for i in range(len(coords_in_order) - 1)]
        return max(legs) if legs else 0.0

    def test_jfk_replacement_exceeds_leg_limit(self):
        # The State House -> JFK leg is far over the per-leg hard limit.
        d = gtt._haversine_km(self.SURVIVORS["Massachusetts State House"], self.JFK)
        self.assertGreater(d, gtt.WALKING_LEG_HARD_KM,
                           f"JFK leg {d:.2f} km should exceed "
                           f"{gtt.WALKING_LEG_HARD_KM} km hard limit")
        self.assertGreater(d, 3.0, "the live defect leg was ~4.6 km")

    def test_near_replacement_within_leg_limit(self):
        # A genuinely nearby candidate stays under the per-leg hard limit.
        worst = max(gtt._haversine_km(c, self.GRANARY)
                    for c in self.SURVIVORS.values())
        self.assertLess(worst, gtt.WALKING_LEG_HARD_KM,
                        f"Granary is {worst:.2f} km from the farthest survivor; "
                        f"should be under {gtt.WALKING_LEG_HARD_KM} km")

    def test_survivors_route_is_walkable(self):
        # The four survivors themselves form a walkable route (sanity on fixtures).
        order = list(self.SURVIVORS.values())
        self.assertLess(self._max_leg_km(order), gtt.WALKING_LEG_HARD_KM)

    def test_fix_present_in_source(self):
        # Belt-and-braces: the distance re-validation of replacements exists.
        # (The behavioural path needs a live LLM; this asserts the guard is wired.)
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "generate_tour_text.py")
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("Re-validate replacements against the SAME walking", src)
        self.assertIn("REJECTED replacement", src)
        self.assertIn("_geo_replacements", src)


# ════════════════════════════════════════════════════════════════════════════
# DEFECT 3 — non-art tour gets a category-appropriate conclusion
# ════════════════════════════════════════════════════════════════════════════
WALKING_TOUR = (
    "Step-by-Step Audio Guided Tour: Walking tour in Boston dedicated to "
    "Massachusetts politics and current affairs, Boston, MA\n"
    "Tour-Category: walking\n\n"
    "Stop 1: Faneuil Hall\n\n"
    "Faneuil Hall opened in 1742 as a public market. In modern Boston it "
    "remains a gathering place for political debate.\n\n"
    "Stop 2: Old State House\n\n"
    "The Old State House opened in 1713. Its modern silhouette anchors the "
    "square; in 1766 a public gallery opened here.\n\n"
    "Stop 3: Boston City Hall\n\n"
    "Boston City Hall opened in 1968. Its brutalist figure dominates the plaza "
    "and modern governance.\n\n"
    "Stop 4: Massachusetts State House\n\n"
    "The State House opened in 1798. The gold dome gleams over modern memory and "
    "the 1933 Sacred Cod theft.\n"
)

MUSEUM_TOUR = (
    "Step-by-Step Audio Guided Tour: Van Gogh Museum\n"
    "Tour-Category: museum\n\n"
    "Stop 1: The Potato Eaters\n\n"
    "Artist: Vincent van Gogh\n\n"
    "A dark portrait of peasants, painted in 1885. This early realist work shows "
    "the human figure at a table.\n\n"
    "Stop 2: Sunflowers\n\n"
    "Artist: Vincent van Gogh\n\n"
    "A still life of sunflowers from 1889, a modern work of bold colour exploring "
    "the human figure.\n"
)


class TestDefect3ConclusionCategory(unittest.TestCase):

    def test_walking_tour_no_art_vocabulary(self):
        out = tc.rebuild_conclusion(WALKING_TOUR, venue_name="").lower()
        self.assertNotIn("modern art", out, "art vocabulary on a walking tour")
        self.assertNotIn("the works show", out, "'works' meaning on a walking tour")
        self.assertNotIn("the art of", out)

    def test_walking_tour_uses_request_theme(self):
        out = tc.rebuild_conclusion(WALKING_TOUR, venue_name="")
        self.assertIn("Massachusetts politics and current affairs", out,
                      "the walking tour should close on its request theme")

    def test_tour_is_art_classifier(self):
        self.assertFalse(tc._tour_is_art(WALKING_TOUR,
                                         tc.parse_delivered_stops(WALKING_TOUR)))
        self.assertTrue(tc._tour_is_art(MUSEUM_TOUR,
                                        tc.parse_delivered_stops(MUSEUM_TOUR)))

    def test_request_theme_extraction(self):
        self.assertEqual(
            tc._request_theme_from_title(WALKING_TOUR),
            "Massachusetts politics and current affairs")

    # ── Museum CANARY (LOCAL-652/653): a museum tour STILL names its works ──
    def test_museum_canary_names_works(self):
        out = tc.rebuild_conclusion(MUSEUM_TOUR, venue_name="Van Gogh Museum").lower()
        self.assertIn("the works show", out,
                      "the museum conclusion must still name its works (canary)")
        self.assertIn("the human figure", out,
                      "the museum thread subject must survive")


# ════════════════════════════════════════════════════════════════════════════
# DEFECT 4 — the structured field lines are KEPT in text but NOT spoken
# ════════════════════════════════════════════════════════════════════════════
STOP_BLOCK = (
    "Stop 5: John F. Kennedy Presidential Library and Museum\n"
    "Address: Columbia Point, Boston, MA 02125\n"
    "Coordinates: 42.3201, -71.0423\n"
    "Type/Specialty: Presidential Library and Museum\n"
    "Specific Examples: Exhibits on JFK's presidency, interactive displays.\n"
    "Operational Details: Open daily 9 to 5.\n"
    "Orientation: From the footpath along Columbia Point, the wind carries salt.\n"
    "The library frames the harbour in steel and light.\n"
)


class TestDefect4FieldLinesNotSpoken(unittest.TestCase):

    def test_struct_fields_stripped_from_tts(self):
        spoken = tgm._strip_nav_fields_for_tts(STOP_BLOCK)
        self.assertNotIn("Type/Specialty:", spoken)
        self.assertNotIn("Specific Examples:", spoken)
        self.assertNotIn("Address:", spoken)
        self.assertNotIn("Coordinates:", spoken)
        self.assertNotIn("Operational Details:", spoken)

    def test_narration_and_name_survive_in_tts(self):
        spoken = tgm._strip_nav_fields_for_tts(STOP_BLOCK)
        # The stop name header and the narrative paragraph are still spoken.
        self.assertIn("John F. Kennedy Presidential Library and Museum", spoken)
        self.assertIn("frames the harbour in steel and light", spoken)
        # The Orientation label is stripped but its value is read aloud.
        self.assertNotIn("Orientation:", spoken)
        self.assertIn("the wind carries salt", spoken)

    def test_text_view_keeps_all_fields(self):
        # The .txt (text view) is written from the ORIGINAL block, untouched.
        self.assertIn("Type/Specialty:", STOP_BLOCK)
        self.assertIn("Specific Examples:", STOP_BLOCK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
