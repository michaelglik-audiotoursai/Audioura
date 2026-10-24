#!/usr/bin/env python3
"""test_local751_area_parse_danvers.py — LOCAL-751 part B1 (area parser).

"Walking tour in Danvers, MA including Witchcraft Victims Memorial" corrupted the
area parse on baseline 027584b0 because the "including …" clause rode along in the
state/city segment:

    [area_resolver] Parsed: city='MA including Witchcraft Victims Memorial.',
                            neighborhood='Danvers'
    [WALK-D1] Area resolution failed … — proceeding unverified

LOCAL-751 B1: the parser must cut "including …" / "with …" / "featuring …" /
"and visit …" clauses (and a trailing period) BEFORE reading city/state, so the
parse of the request with the clause is IDENTICAL to the parse of the same
request without it ("Walking tour in Danvers, MA"). The clause text must never
leak into the city or neighborhood.

`_parse_location` is pure and importable standalone. The downstream
`resolve_area` + the named-place policy (B2) handle resolution and the memorial;
B1's single job is to stop the clause corrupting the location.

RED on 027584b0: city='MA including Witchcraft Victims Memorial[.]'.
GREEN after the fix: parse == parse of the clause-free request, no leak.

Run: python3 -m pytest test_local751_area_parse_danvers.py -q
"""
import unittest

from area_resolver import _parse_location


class TestDanversAreaParse(unittest.TestCase):
    def test_including_clause_is_cut_no_leak(self):
        baseline = _parse_location("Walking tour in Danvers, MA")
        for req in (
            "Walking tour in Danvers, MA including Witchcraft Victims Memorial",
            "Walking tour in Danvers, MA including Witchcraft Victims Memorial.",
        ):
            neighborhood, city = _parse_location(req)
            # The clause must be gone: identical to the clause-free parse.
            self.assertEqual(
                baseline, (neighborhood, city),
                f"clause not cut for {req!r}: got (neighborhood={neighborhood!r}, "
                f"city={city!r}), expected {baseline}",
            )
            # And explicitly: no clause text anywhere.
            self.assertNotIn("including", (city + " " + neighborhood).lower())
            self.assertNotIn("memorial", (city + " " + neighborhood).lower())
            self.assertNotIn("witchcraft", (city + " " + neighborhood).lower())

    def test_other_clause_markers_are_cut(self):
        cases = {
            "Walking tour in Salem, MA with the Witch House":
                _parse_location("Walking tour in Salem, MA"),
            "Walking tour in Concord, MA featuring the Old Manse":
                _parse_location("Walking tour in Concord, MA"),
            "Walking tour in Lexington, MA and visit the Battle Green":
                _parse_location("Walking tour in Lexington, MA"),
        }
        for req, expected in cases.items():
            got = _parse_location(req)
            self.assertEqual(
                expected, got,
                f"clause not cut for {req!r}: got {got}, expected {expected}",
            )

    def test_clause_cut_preserves_us_zip_format(self):
        # With a ZIP the US-format detector already resolves the city; the clause
        # must still be cut so it stays that way.
        n, c = _parse_location(
            "Walking tour in Danvers, MA 01923 including Witchcraft Victims Memorial")
        self.assertEqual("", n)
        self.assertEqual("Danvers", c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
