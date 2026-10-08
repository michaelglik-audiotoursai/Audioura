#!/usr/bin/env python3
"""test_local627_reproduction_and_titles.py — LOCAL-627 defect 4.

Tour 487 (Prado) opened on "Wrestlers (sculpture, 2021)" — a 2021 plaster cast —
as if it were a Prado masterwork. The venue works intake must:
  * reject reproductions / casts / copies / replicas (Wikidata P31 item type or a
    label text marker);
  * reject works whose inception (P571) is after 1990, UNLESS the venue is a
    modern/contemporary-art museum (a post-1990 original is legitimate there);
  * strip a trailing parenthetical disambiguator from the SPOKEN title.

These tests drive the REAL venue_resolver.fetch_venue_works with a FAKE SPARQL
HTTP response (monkeypatched requests.get) — no network — plus the pure helpers.
RED on base, GREEN after.

Run: python3 -m pytest test_local627_reproduction_and_titles.py -q
"""
import json
import unittest
from unittest import mock

import venue_resolver as vr


def _binding(qid, label, sitelinks="0", inception=None, instance_of=None,
             creator=None, creator_label=None):
    b = {
        "work": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "workLabel": {"value": label},
        "workLabel_en": {"value": label},
        "sitelinks": {"value": sitelinks},
    }
    if inception is not None:
        b["inception"] = {"value": inception}
    if instance_of is not None:
        b["instanceOf"] = {"value": f"http://www.wikidata.org/entity/{instance_of}"}
    if creator is not None:
        b["creator"] = {"value": f"http://www.wikidata.org/entity/{creator}"}
    if creator_label is not None:
        b["creatorLabel"] = {"value": creator_label}
    return b


class _FakeResp:
    status_code = 200

    def __init__(self, bindings):
        self._bindings = bindings

    def json(self):
        return {"results": {"bindings": self._bindings}}


def _patch_sparql(bindings):
    return mock.patch.object(vr.requests, "get",
                             return_value=_FakeResp(bindings))


class TestParentheticalStrip(unittest.TestCase):
    def test_strip_type_and_year(self):
        self.assertEqual(
            vr.strip_parenthetical_disambiguator("Wrestlers (sculpture, 2021)"),
            "Wrestlers")

    def test_strip_medium(self):
        self.assertEqual(
            vr.strip_parenthetical_disambiguator("The Three Graces (painting)"),
            "The Three Graces")

    def test_strip_artist_disambiguator(self):
        self.assertEqual(
            vr.strip_parenthetical_disambiguator("David (Michelangelo)"), "David")

    def test_no_paren_unchanged(self):
        self.assertEqual(
            vr.strip_parenthetical_disambiguator("Las Meninas"), "Las Meninas")


class TestModernArtDetection(unittest.TestCase):
    def test_classical_not_modern(self):
        self.assertFalse(vr.venue_is_modern_art("Museo del Prado"))
        self.assertFalse(vr.venue_is_modern_art("Uffizi Gallery"))

    def test_modern_detected(self):
        self.assertTrue(vr.venue_is_modern_art("Museum of Modern Art"))
        self.assertTrue(vr.venue_is_modern_art("Tate Modern"))
        self.assertTrue(vr.venue_is_modern_art("Centre Pompidou"))


class TestReproductionAndModernFilter(unittest.TestCase):
    def _works(self):
        return [
            _binding("Q179158", "Las Meninas", sitelinks="40", inception="1656-01-01"),
            _binding("Q000CAST", "Wrestlers (sculpture, 2021)", sitelinks="0",
                     inception="2021-01-01", instance_of="Q16919298"),  # plaster cast
            _binding("Q000REPL", "Venus de Milo replica", sitelinks="0",
                     instance_of="Q1278452"),  # replica
            _binding("Q000MOD", "Untitled Modern Original", sitelinks="2",
                     inception="2005-01-01"),  # modern original (no repro type)
        ]

    def test_prado_rejects_cast_replica_and_modern(self):
        with _patch_sparql(self._works()):
            works = vr.fetch_venue_works("Q160112", venue_name="Museo del Prado")
        titles = {w["label_en"] for w in works}
        self.assertIn("Las Meninas", titles)
        self.assertNotIn("Wrestlers (sculpture, 2021)", titles)   # cast + post-1990
        self.assertNotIn("Venus de Milo replica", titles)         # replica
        self.assertNotIn("Untitled Modern Original", titles)      # post-1990 at classical museum

    def test_modern_museum_keeps_modern_original_but_not_cast(self):
        with _patch_sparql(self._works()):
            works = vr.fetch_venue_works("Q188740", venue_name="Museum of Modern Art")
        titles = {w["label_en"] for w in works}
        # The post-1990 ORIGINAL is kept at a modern-art museum.
        self.assertIn("Untitled Modern Original", titles)
        # The cast / replica are STILL dropped (a reproduction is never a stop).
        self.assertNotIn("Wrestlers (sculpture, 2021)", titles)
        self.assertNotIn("Venus de Milo replica", titles)

    def test_display_title_strips_parenthetical(self):
        works = [_binding("Q123", "The Three Graces (painting)", sitelinks="12",
                          inception="1639-01-01")]
        with _patch_sparql(works):
            got = vr.fetch_venue_works("Q160112", venue_name="Museo del Prado")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["display_title"], "The Three Graces")
        # The full label is preserved for matching.
        self.assertEqual(got[0]["label_en"], "The Three Graces (painting)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
