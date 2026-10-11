"""test_local668_foreign_museum_snippets.py — LOCAL-668 deliverable #3.

Fixtures from ~/Audioura/.continuous_dev/bench/AB11/hcmc_on_664.log — the
cheap-arm "Woodblock prints collection" stop (stop 5) whose research returned
snippets about OTHER museums:

  line 580: "e-museum: Items from four national museums in Japan. Honolulu
             Museum of Art–Japanese Woodblock Prints Collection ... Mus..."
  line 581: "[JAPANESE WOODBLOCK PRINTS] COLLECTION EMILE JAVAL: ESTAMPES
             JAPONAISES ..."
  and the Saint-Louis holdings that bled into the narration ("Phil Guston …
  Saint Louis holdings … Holbein and Pippin").

The filter must DROP these foreign-museum snippets at the evidence stage, while
KEEPING genuine HCMC evidence and generic medium/technique evidence.
"""
import unittest

from venue_anchored_research import (
    venue_content_tokens,
    mentions_this_venue,
    names_foreign_museum,
    drop_foreign_museum_snippets,
)

_VENUE = "Ho Chi Minh City Museum of Fine Arts"
_CITY = "Ho Chi Minh City, Vietnam"


class VenueTokens(unittest.TestCase):
    def test_distinctive_tokens_only(self):
        tok = venue_content_tokens(_VENUE)
        self.assertIn("chi", tok)
        self.assertIn("minh", tok)
        # generic museum words are NOT distinctive
        for generic in ("museum", "fine", "arts", "city"):
            self.assertNotIn(generic, tok)

    def test_mentions_this_venue_requires_distinctive_tokens(self):
        self.assertTrue(mentions_this_venue(
            "The Ho Chi Minh City Museum of Fine Arts holds lacquer works.", _VENUE))
        # a generic "fine arts museum" mention is NOT our venue
        self.assertFalse(mentions_this_venue(
            "A fine arts museum in another country.", _VENUE))


class ForeignMuseumDetector(unittest.TestCase):
    def test_detects_honolulu(self):
        txt = ("e-museum: Items from four national museums in Japan. Honolulu "
               "Museum of Art Japanese Woodblock Prints Collection.")
        self.assertIsNotNone(names_foreign_museum(txt, _VENUE))

    def test_detects_saint_louis(self):
        txt = ("Phil Guston's works, represented in the Saint Louis Art Museum, "
               "entered alongside those of Holbein and Pippin.")
        got = names_foreign_museum(txt, _VENUE)
        self.assertIsNotNone(got)
        self.assertIn("louis", got.lower())

    def test_own_venue_is_not_foreign(self):
        txt = ("The Ho Chi Minh City Museum of Fine Arts showcases woodblock "
               "prints depicting centuries-old Vietnamese life.")
        self.assertIsNone(names_foreign_museum(txt, _VENUE))

    def test_generic_medium_text_is_not_foreign(self):
        txt = ("Woodblock printing (mộc bản) is a relief technique used widely "
               "across Vietnamese folk art.")
        self.assertIsNone(names_foreign_museum(txt, _VENUE))


class DropForeignSnippets(unittest.TestCase):
    def _snips(self):
        return [
            {"title": "HCMC Fine Arts — woodblock",
             "snippet": "The Ho Chi Minh City Museum of Fine Arts holds a "
                        "collection of Vietnamese woodblock prints.",
             "url": "http://baotangmythuattphcm.com.vn/"},
            {"title": "e-museum Japan",
             "snippet": "Items from four national museums in Japan. Honolulu "
                        "Museum of Art Japanese Woodblock Prints Collection.",
             "url": "http://e-museum.example/jp"},
            {"title": "Emile Javal estampes",
             "snippet": "[JAPANESE WOODBLOCK PRINTS] COLLECTION EMILE JAVAL at "
                        "the Saint Louis Art Museum: estampes japonaises.",
             "url": "http://slam.example"},
            {"title": "Woodblock technique",
             "snippet": "Woodblock printing is a relief technique with a long "
                        "tradition in Vietnamese folk art.",
             "url": "http://generic.example"},
        ]

    def test_drops_foreign_keeps_venue_and_generic(self):
        kept, report = drop_foreign_museum_snippets(self._snips(), _VENUE, _CITY)
        titles = [s["title"] for s in kept]
        self.assertIn("HCMC Fine Arts — woodblock", titles)   # our venue — kept
        self.assertIn("Woodblock technique", titles)          # generic — kept
        self.assertNotIn("e-museum Japan", titles)            # Honolulu — dropped
        self.assertNotIn("Emile Javal estampes", titles)      # Saint Louis — dropped
        self.assertEqual(report["dropped"], 2)
        self.assertEqual(report["output"], 2)
        # every dropped snippet reports a non-empty foreign institution name
        self.assertTrue(all(d["foreign"] for d in report["dropped_log"]))

    def test_no_saint_louis_survives(self):
        kept, _ = drop_foreign_museum_snippets(self._snips(), _VENUE, _CITY)
        joined = " ".join(f"{s['title']} {s['snippet']}" for s in kept).lower()
        self.assertNotIn("saint louis", joined)
        self.assertNotIn("honolulu", joined)

    def test_empty_input(self):
        kept, report = drop_foreign_museum_snippets([], _VENUE)
        self.assertEqual(kept, [])
        self.assertEqual(report["dropped"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
