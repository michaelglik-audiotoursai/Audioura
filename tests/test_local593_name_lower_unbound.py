#!/usr/bin/env python3
"""test_local593_name_lower_unbound.py — Deliverable 3 (LOCAL-593).

The LOCAL-37 three-class retrieval logged a non-fatal error on the Harvard Art
Museums run:

    [LOCAL-37] Three-class retrieval error (non-fatal):
    local variable 'name_lower' referenced before assignment

Root cause: in three_class_retrieval.determine_category, `name_lower` was
assigned only inside `if catalogue_works:` (section 1). A stop with NO catalogue
works but WITH per_work_contexts fell through to section 3, which also reads
`name_lower` — raising UnboundLocalError.

RED on 0315513:  the section-3 path raises UnboundLocalError.
GREEN after fix: name_lower is bound once up front; every section can use it.

Run: python3 -m pytest tests/test_local593_name_lower_unbound.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from three_class_retrieval import determine_category


class TestNameLowerBound(unittest.TestCase):
    def test_section3_no_catalogue_with_contexts(self):
        """The exact failing path: no catalogue_works, but per_work_contexts
        present. Must NOT raise UnboundLocalError and must read the Material."""
        cat = determine_category(
            {"name": "Autumn Landscape"},
            per_work_contexts={"Autumn Landscape": ["Material: ink on silk"]},
            catalogue_works=None,
        )
        self.assertEqual("ink on silk", cat)

    def test_section3_empty_catalogue_list(self):
        """Empty (not None) catalogue list is also falsy — same path."""
        cat = determine_category(
            {"name": "Autumn Sunset"},
            per_work_contexts={"Autumn Sunset": ["Material: hanging scroll"]},
            catalogue_works=[],
        )
        self.assertEqual("hanging scroll", cat)

    def test_section1_catalogue_still_works(self):
        """Section 1 (catalogue) path is unchanged."""
        cat = determine_category(
            {"name": "Ganesh"},
            catalogue_works=[{"title": "Ganesh", "material": "chlorite schist",
                              "type_label": "sculpture"}],
        )
        self.assertEqual("chlorite schist sculpture", cat)

    def test_no_metadata_returns_empty(self):
        self.assertEqual("", determine_category({"name": "Mystery Object"}))

    def test_stop_dict_metadata_path(self):
        self.assertEqual("painting",
                         determine_category({"name": "X", "wikidata_class": "painting"}))

    def test_no_match_in_contexts_returns_empty(self):
        """per_work_contexts present but title does not match — must still not
        raise, and returns '' (no material found)."""
        cat = determine_category(
            {"name": "A Courtier"},
            per_work_contexts={"Totally Different Title": ["Material: bronze"]},
            catalogue_works=None,
        )
        self.assertEqual("", cat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
