"""test_local653_site_candidates.py — [LOCAL-653] regression tests.

Built from the REAL candidate list in
``~/Audioura/.continuous_dev/bench/AB2/run_OFF-1_courtauld586.log`` (the Courtauld,
tours 586 OFF / 592 ON, fresh). Both arms shipped "Van Gogh's iconic Self-Portrait
with Bandaged Ear", "Manet's A Bar at the Folies-Bergère" and "Courtauld Institute"
as stops because the SITE-LISTED / venue_corpus canonical set — the set D1v2
matches against — only filtered chrome/rooms/the venue itself.

Asserts the three LOCAL-653 fixes on that exact data:
  * the SIBLING institution and the venue itself are dropped, location-suffix
    robust (the production venue arg carried ", London, United Kingdom");
  * a bare ARTIST NAME held by the venue is dropped (matched against the SPARQL
    creators), while real works — including donor portraits named after the
    Courtaulds, and "Mont Sainte-Victoire" — are kept;
  * the MARKETING prefix is stripped from an otherwise-real title, keeping the
    artist for the narration, and a genuine possessive/short title is untouched.

Pure/offline — no network, no DB, no LLM.
"""
import unittest

from site_candidate_guard import (
    venue_core_name,
    is_venue_or_sibling_title,
    is_artist_name_alone,
    strip_marketing_prefix,
    filter_site_candidates,
)

# The production venue argument on 586/592: name + city/country tail.
VENUE = "The Courtauld Gallery, London, United Kingdom"

# The venue's own creator labels, as they arrive from the SPARQL works.
ARTISTS = [
    "Paul Cézanne", "Georges Seurat", "Edgar Degas", "Édouard Manet",
    "Vincent van Gogh", "Peter Paul Rubens", "Sandro Botticelli",
]

# A slice of the real line-146 candidate set: the junk/sibling/artist titles that
# leaked, plus real works that MUST survive (donor portraits carry the Courtauld
# surname; "Mont Sainte-Victoire" is a bare two-token-ish work).
REAL_WORKS_KEPT = [
    "A Bar at the Folies-Bergère",
    "Self-Portrait with Bandaged Ear",
    "Christ and the Woman Taken in Adultery",
    "Footed Bowl with the Crucifixion",
    "The Card Players",
    "Mont Sainte-Victoire with Large Pine",
    "La loge",
    "Young Woman Powdering Herself",
    "Nevermore",
    "Samuel Courtauld (1876–1947)",     # donor portrait — a real work
    "Jeanne Courtauld (1909–2003)",     # donor portrait — a real work
    "A Woman Holding a Lily-of-the-Valley and a Pansy",
    "Peach Trees in Blossom",
    "Antibes",
    "Bridge of Courbevoie",
]

JUNK_DROPPED = [
    "Courtauld Institute",    # sibling institution
    "Courtauld Gallery",      # the venue itself (bare)
    "Paul Cézanne",           # artist name alone
    "Georges Seurat",
    "Edgar Degas",
]


class TestVenueCoreName(unittest.TestCase):
    def test_strips_location_and_institution_tail(self):
        self.assertEqual(venue_core_name(VENUE), "courtauld")
        self.assertEqual(venue_core_name("The Courtauld Gallery"), "courtauld")
        self.assertEqual(venue_core_name("Walters Art Museum, Baltimore, MD"),
                         "walters art")
        self.assertEqual(venue_core_name("National Gallery, London"),
                         "national")
        self.assertEqual(venue_core_name("Uffizi"), "uffizi")


class TestVenueSibling(unittest.TestCase):
    def test_sibling_and_venue_dropped_with_suffix(self):
        # The root-cause bug: these failed when the venue carried a location tail.
        self.assertTrue(is_venue_or_sibling_title("Courtauld Institute", VENUE))
        self.assertTrue(is_venue_or_sibling_title("Courtauld Gallery", VENUE))
        self.assertTrue(is_venue_or_sibling_title("The Courtauld", VENUE))
        self.assertTrue(is_venue_or_sibling_title(
            "Courtauld Institute of Art", VENUE))

    def test_site_brand_dropped(self):
        self.assertTrue(is_venue_or_sibling_title("Official Website", VENUE))
        self.assertTrue(is_venue_or_sibling_title("Homepage", VENUE))

    def test_real_works_not_sibling(self):
        for t in REAL_WORKS_KEPT:
            self.assertFalse(is_venue_or_sibling_title(t, VENUE), t)
        # A painting that merely begins with the venue surname but continues with
        # a non-institution word is a work, not the institution.
        self.assertFalse(is_venue_or_sibling_title("Courtauld Family Portrait",
                                                   VENUE))


class TestArtistNameAlone(unittest.TestCase):
    def test_known_artist_dropped(self):
        for a in ["Paul Cézanne", "Georges Seurat", "Edgar Degas",
                  "Vincent van Gogh"]:
            self.assertTrue(is_artist_name_alone(a, ARTISTS), a)

    def test_real_works_kept_precise_mode(self):
        # Precise (default) mode: only a known creator name is dropped. Real works
        # that SHARE the 2–3-capitalised-token shape must survive.
        for t in REAL_WORKS_KEPT + ["Peach Trees", "Turning Road",
                                    "Mont Sainte-Victoire"]:
            self.assertFalse(is_artist_name_alone(t, ARTISTS), t)

    def test_shape_fallback_is_opt_in(self):
        # The shape fallback would catch an unknown bare name, but is OFF by
        # default so real works are never over-rejected.
        self.assertFalse(is_artist_name_alone("Henri Matisse", []))
        self.assertTrue(is_artist_name_alone("Henri Matisse", [],
                                             allow_shape_fallback=True))
        # Even with the fallback ON, a work-signal word protects a real work.
        self.assertFalse(is_artist_name_alone("Portrait of a Man", [],
                                              allow_shape_fallback=True))


class TestMarketingPrefix(unittest.TestCase):
    KNOWN = [
        "Self-Portrait with Bandaged Ear",
        "A Bar at the Folies-Bergère",
        "The Hammock",
        "Au Café",
    ]

    def test_strips_real_courtauld_prefixes(self):
        cases = [
            ("Van Gogh\u2019s iconic\xa0Self-Portrait with Bandaged Ear",
             "Self-Portrait with Bandaged Ear", "Van Gogh"),
            ("Vincent van Gogh\u2019s\xa0 Self-Portrait with Bandaged Ear",
             "Self-Portrait with Bandaged Ear", "Vincent van Gogh"),
            ("\u00c9douard\xa0Manet\u2019s famous painting\xa0A Bar at the Folies-Bergère",
             "A Bar at the Folies-Bergère", "Édouard Manet"),
            ("Manet\u2019s  A Bar at the Folies-Bergère",
             "A Bar at the Folies-Bergère", "Manet"),
            ("Courbet\u2019s provocative The Hammock",
             "The Hammock", "Courbet"),
            ("Manet\u2019s groundbreaking depiction of modern life\u202f Au Café",
             "Au Café", "Manet"),
        ]
        for raw, want_title, want_artist in cases:
            clean, artist = strip_marketing_prefix(raw, known_titles=self.KNOWN)
            self.assertEqual(clean, want_title, raw)
            self.assertEqual(artist, want_artist, raw)

    def test_genuine_titles_untouched(self):
        for t in ["Whistlejacket", "A Lady of the Court",
                  "The Night Watch", "Mont Sainte-Victoire with Large Pine"]:
            clean, artist = strip_marketing_prefix(t, known_titles=None)
            self.assertEqual(clean, t)
            self.assertEqual(artist, "")

    def test_strip_rejected_when_remainder_not_known(self):
        # If the stripped tail is not a known title, don't mangle it.
        clean, artist = strip_marketing_prefix(
            "Van Gogh\u2019s iconic Something Not In The Set",
            known_titles=self.KNOWN)
        self.assertEqual(clean, "Van Gogh\u2019s iconic Something Not In The Set")
        self.assertEqual(artist, "")

    def test_strip_without_reference_set(self):
        # With no known_titles, a clear prefix + plausible tail still strips.
        clean, artist = strip_marketing_prefix(
            "Van Gogh\u2019s iconic Self-Portrait with Bandaged Ear")
        self.assertEqual(clean, "Self-Portrait with Bandaged Ear")
        self.assertEqual(artist, "Van Gogh")


class TestFilterSiteCandidates(unittest.TestCase):
    def test_courtauld_586_set_filtered(self):
        candidates = JUNK_DROPPED + REAL_WORKS_KEPT
        kept, dropped = filter_site_candidates(
            candidates, VENUE, artist_names=ARTISTS,
            protected_titles=[])  # none SPARQL-protected in this slice
        dropped_titles = set(dropped)
        for j in JUNK_DROPPED:
            self.assertIn(j, dropped_titles, f"should drop {j!r}")
        for w in REAL_WORKS_KEPT:
            self.assertIn(w, kept, f"should keep {w!r}")

    def test_protected_sparql_title_never_dropped(self):
        # Even if a SPARQL-confirmed label happened to look like an artist name,
        # protecting it keeps it. (Defensive: a work titled after a person.)
        kept, dropped = filter_site_candidates(
            ["Paul Cézanne"], VENUE, artist_names=ARTISTS,
            protected_titles=["Paul Cézanne"])
        self.assertEqual(kept, ["Paul Cézanne"])
        self.assertEqual(dropped, [])

    def test_dict_candidates_carry_reason(self):
        kept, dropped = filter_site_candidates(
            [{"title": "Courtauld Institute"}, {"title": "The Card Players"}],
            VENUE, artist_names=ARTISTS)
        self.assertEqual([k["title"] for k in kept], ["The Card Players"])
        self.assertEqual(len(dropped), 1)
        # "Courtauld Institute" is a sibling institution; junk_title_guard (which
        # runs first and shares the venue-itself authority) or the sibling guard
        # may claim it — either is a correct drop reason.
        self.assertIn(dropped[0]["_reject_reason"],
                      {"junk_page_title", "venue_or_sibling_institution"})

    def test_order_preserving(self):
        candidates = ["The Card Players", "Courtauld Institute",
                      "Mont Sainte-Victoire with Large Pine", "Paul Cézanne"]
        kept, _ = filter_site_candidates(candidates, VENUE, artist_names=ARTISTS)
        self.assertEqual(kept, ["The Card Players",
                                "Mont Sainte-Victoire with Large Pine"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
