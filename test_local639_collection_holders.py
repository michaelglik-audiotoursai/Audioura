#!/usr/bin/env python3
"""test_local639_collection_holders.py — LOCAL-639 defect 3.

The Uffizi (Q51252) collection-membership gate dropped works held by a SIBLING
sub-collection, because their Wikidata P195 collection is not Q51252 and the LEAD
derived-holder rule only promotes a P195 that holds >= 10% of the venue's OWN
SPARQL set. The generator log shows the drops, e.g.:

    collection-membership dropped: ('Due storie di san Nicola di Bari',
        'wrong_collection (P195=Q3683040 excludes Q51252; …)')
    collection-membership dropped: ('Ritratto di giovane donna',
        'wrong_collection (P195=Q3756440 excludes Q51252; …)')

Fix: ``venue_resolver.fetch_collection_holder_qids(venue_qid)`` runs ONE cached
SPARQL query returning the venue's related holder QIDs (P361 part-of / P749
parent-org / P127 owned-by / P527 has-part / P1830 owner-of, plus siblings that
share one of those parents). ``_apply_artwork_guards`` merges them into
``parent_qids``, so a work held by a sibling/parent collection is kept, while a
true foreign leak (Ophelia P195=Tate) or a different museum (Arringatore P195=the
National Archaeological Museum) still fails the gate.

These tests are OFFLINE (the holder set is injected). A separate network-gated
test asserts the live Q51252 query actually returns the two sibling QIDs the log
flagged — skipped when AUDIOURA_LIVE_WD is not set.

Run: python3 -m pytest test_local639_collection_holders.py -q
"""
import os
import unittest

from artwork_selection_guard import enforce_collection_membership
import venue_resolver as vr


class TestSiblingHolderAccepted(unittest.TestCase):
    """A work whose P195 is a derived sibling/parent holder is KEPT; a foreign
    collection and a different museum are still dropped."""

    def _works(self):
        return [
            # genuine Uffizi work (P195 = the venue)
            {"title": "Nascita di Venere", "collection_qids": ["Q51252"]},
            # sibling sub-collection the log flagged (P195 = Q3683040 / Q3756440)
            {"title": "Due storie di san Nicola di Bari",
             "collection_qids": ["Q3683040"]},
            {"title": "Ritratto di giovane donna", "collection_qids": ["Q3756440"]},
            # a true foreign leak — the National Archaeological Museum
            {"title": "Arringatore", "collection_qids": ["Q637237"]},
        ]

    def test_siblings_kept_foreign_dropped(self):
        # Derived related holders for Q51252 (what the SPARQL returns).
        related = ("Q3683040", "Q3756440", "Q913058")
        parent_qids = tuple(related)
        kept, dropped = enforce_collection_membership(
            self._works(), sparql_works=self._works(),
            venue_name="Uffizi Gallery", venue_qid="Q51252",
            parent_qids=parent_qids)
        kept_titles = {k["title"] for k in kept}
        self.assertIn("Nascita di Venere", kept_titles)
        self.assertIn("Due storie di san Nicola di Bari", kept_titles)
        self.assertIn("Ritratto di giovane donna", kept_titles)
        # The National Archaeological Museum work is NOT a derived holder → dropped.
        dropped_titles = {d["title"] for d in dropped}
        self.assertIn("Arringatore", dropped_titles)

    def test_without_holders_siblings_dropped(self):
        # Baseline: with no derived holders the siblings are (wrongly) dropped —
        # this is exactly the pre-fix behaviour the derivation corrects.
        kept, dropped = enforce_collection_membership(
            self._works(), sparql_works=self._works(),
            venue_name="Uffizi Gallery", venue_qid="Q51252", parent_qids=())
        dropped_titles = {d["title"] for d in dropped}
        self.assertIn("Due storie di san Nicola di Bari", dropped_titles)
        self.assertIn("Ritratto di giovane donna", dropped_titles)


class TestHolderFetchCachingAndSafety(unittest.TestCase):
    def test_bad_qid_returns_empty_no_network(self):
        # A non-QID never hits the network and returns ().
        self.assertEqual(vr.fetch_collection_holder_qids(""), ())
        self.assertEqual(vr.fetch_collection_holder_qids("not-a-qid"), ())

    def test_cache_is_used(self):
        # Seed the cache; the fetch must return it without a network call.
        vr._RELATED_HOLDERS_CACHE["Q999999"] = ("Q1", "Q2")
        self.assertEqual(vr.fetch_collection_holder_qids("Q999999"), ("Q1", "Q2"))

    def test_result_excludes_self(self):
        vr._RELATED_HOLDERS_CACHE["Q123456"] = ("Q1", "Q2")
        self.assertNotIn("Q123456", vr.fetch_collection_holder_qids("Q123456"))


@unittest.skipUnless(os.environ.get("AUDIOURA_LIVE_WD"),
                     "live Wikidata test — set AUDIOURA_LIVE_WD=1 to run")
class TestLiveUffiziHolders(unittest.TestCase):
    def test_q51252_rescues_sibling_qids(self):
        vr._RELATED_HOLDERS_CACHE.pop("Q51252", None)
        holders = set(vr.fetch_collection_holder_qids("Q51252"))
        # The two sibling collections the generator log flagged as dropped.
        self.assertIn("Q3683040", holders)
        self.assertIn("Q3756440", holders)
        # A genuinely different museum must NOT be a derived holder.
        self.assertNotIn("Q637237", holders)  # National Archaeological Museum


if __name__ == "__main__":
    unittest.main(verbosity=2)
