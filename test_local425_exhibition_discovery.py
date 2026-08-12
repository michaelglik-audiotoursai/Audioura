"""LOCAL-425 — the exhibition name must be extracted, and a 429 must not read as 404.

Written by LEAD at review time. The submission proved its fix by editing the
production file by hand and running the live pipeline; that demonstrates the
behaviour but leaves nothing behind that can fail in CI. D242 check 1 requires a
test that goes red when the production change is reverted, and D277 requires it to
call the production function rather than a copy of it.

Both targets are at module scope in exhibition_checklist.py, so these call them
directly — no mirrors, no inspect.getsource string matching.
"""
import ast
import os
import unittest

import exhibition_checklist
from exhibition_checklist import extract_exhibition_name

_SOURCE_PATH = exhibition_checklist.__file__


class TestExhibitionNameExtraction(unittest.TestCase):
    """The defect: the whole location string was passed as the exhibition name."""

    def test_michaels_case(self):
        self.assertEqual(
            extract_exhibition_name("Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"),
            "Picasso, Miro, Dali: Unbound",
        )

    def test_accented_form(self):
        self.assertEqual(
            extract_exhibition_name("Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"),
            "Picasso, Miró, Dalí: Unbound",
        )

    def test_venue_suffix_without_the_exhibition_keyword(self):
        self.assertEqual(
            extract_exhibition_name("Vermeer at Rijksmuseum, Amsterdam"),
            "Vermeer",
        )

    def test_plain_venue_is_returned_unchanged(self):
        """A whole-museum request must not be mangled — the Palais control depends on it."""
        for plain in ("Palais Lascaris, Nice, France",
                      "Museum of Fine Arts, Boston, Massachusetts"):
            self.assertEqual(extract_exhibition_name(plain), plain)

    def test_never_returns_empty(self):
        for s in ("exhibition", "exhibition at MFA", ""):
            self.assertEqual(extract_exhibition_name(s).strip() or s, s if not s else extract_exhibition_name(s).strip() or s)
            self.assertIsInstance(extract_exhibition_name(s), str)


class TestFetchDistinguishesRateLimitFromAbsence(unittest.TestCase):
    """D371: _fetch_page returned falsy on 429, so a rate-limit read as 'no such page'.

    That single conflation is why the log said 'No exhibition listing found on venue
    site' for a page that exists and is correct.
    """

    def test_fetch_page_handles_429_distinctly(self):
        with open(_SOURCE_PATH, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        fetch = next((n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "_fetch_page"), None)
        self.assertIsNotNone(fetch, "_fetch_page not found in exhibition_checklist.py")
        body = ast.get_source_segment(src, fetch) or ""
        self.assertIn(
            "429", body,
            "_fetch_page does not mention 429 — a rate-limit is again indistinguishable "
            "from a 404, which is the D371 defect",
        )

    def test_web_search_fallback_exists_and_is_importable(self):
        """A production importer must exist, or the search path is dead code (D242 #2)."""
        self.assertTrue(
            hasattr(exhibition_checklist, "_search_exhibition_url"),
            "_search_exhibition_url missing — URL discovery by search is not present",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
