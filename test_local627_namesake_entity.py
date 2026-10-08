#!/usr/bin/env python3
"""test_local627_namesake_entity.py — LOCAL-627 defect 8.

Tour 487 (Prado) attributed "Titian Ramsey Peale II" — a 19th-century American
naturalist — to Titian the painter, because the snippet's first token matched
"Titian". Entity linking must bind to the artist record of the delivered work,
never to a namesake. story_verifier.is_namesake_collision /
disambiguate_snippet(s) exclude the namesake snippet.

Run: python3 -m pytest test_local627_namesake_entity.py -q
"""
import unittest

import story_verifier as sv


class TestNamesakeCollision(unittest.TestCase):
    def test_titian_naturalist_is_namesake(self):
        text = ("Titian Ramsey Peale II was a 19th-century American naturalist "
                "and explorer who illustrated expeditions.")
        is_ns, reason = sv.is_namesake_collision(text, "Titian")
        self.assertTrue(is_ns)
        self.assertIn("Titian Ramsey Peale", reason)

    def test_titian_painter_not_namesake(self):
        text = "Titian painted the Venus of Urbino in 1538 for the Duke of Urbino."
        is_ns, _ = sv.is_namesake_collision(text, "Titian")
        self.assertFalse(is_ns)

    def test_titian_possessive_not_namesake(self):
        text = "Titian's mastery of colour transformed Venetian painting."
        is_ns, _ = sv.is_namesake_collision(text, "Titian")
        self.assertFalse(is_ns)

    def test_multitoken_artist_not_triggered(self):
        # A multi-token artist name is matched in full elsewhere, not here.
        text = "Pablo Picasso Jones is a different modern collector."
        is_ns, _ = sv.is_namesake_collision(text, "Pablo Picasso")
        self.assertFalse(is_ns)

    def test_generational_suffix_namesake(self):
        text = "Titian Peale II catalogued North American butterflies."
        is_ns, _ = sv.is_namesake_collision(text, "Titian")
        self.assertTrue(is_ns)


class TestDisambiguateSnippetWithArtist(unittest.TestCase):
    def test_namesake_snippet_excluded(self):
        is_valid, reason = sv.disambiguate_snippet(
            "Titian Ramsey Peale II was an American naturalist.",
            snippet_title="Titian Ramsey Peale",
            artist_name="Titian")
        self.assertFalse(is_valid)
        self.assertIn("Namesake", reason)

    def test_artist_snippet_kept(self):
        is_valid, _ = sv.disambiguate_snippet(
            "Titian completed the Assumption of the Virgin in 1518.",
            snippet_title="Titian",
            artist_name="Titian")
        self.assertTrue(is_valid)


class TestDisambiguateSnippetsBatch(unittest.TestCase):
    def test_batch_excludes_namesake(self):
        snippets = [
            {"title": "Titian", "snippet": "Titian painted Danae for Philip II."},
            {"title": "Titian Ramsey Peale",
             "snippet": "Titian Ramsey Peale II was an American naturalist."},
        ]
        valid, excluded = sv.disambiguate_snippets(snippets, "", artist_name="Titian")
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(excluded), 1)
        self.assertIn("naturalist", excluded[0]["snippet"])


class TestVerifyStoryCandidateThreadsArtist(unittest.TestCase):
    def test_verify_excludes_namesake_snippet(self):
        snippets = [
            {"title": "Titian Ramsey Peale",
             "snippet": "Titian Ramsey Peale II was a 19th-century American naturalist."},
        ]
        result = sv.verify_story_candidate(
            story_text="Titian was a Venetian master of colour.",
            snippets=snippets,
            artist_name="Titian",
            stop_name="Venus of Urbino")
        self.assertTrue(any("Namesake" in e.get("exclusion_reason", "")
                            for e in result.get("disambiguation_excluded", []))
                        or result.get("claims_sourced", 0) == 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
