#!/usr/bin/env python3
"""LOCAL-811 — pooled museum-stop checks + the universal disambiguation-line
guard (pure, no DB).

The ticket's required properties, at the unit level:
  1. a pooled Belvedere row that is one of the two FOREIGN works (held elsewhere,
     carrying a P195 that excludes the Belvedere) is rejected as wrong_collection;
  2. a pooled row whose body is a "may refer to" disambiguation passage is
     rejected as disambiguation_text;
  3. a Met gift-shop pooled row is rejected as a shop/junk title;
  4. a genuine in-collection work is KEPT — including a local-language work with
     no artist and no P31 enrichment (the pooled rows lack both), so the checks
     never quarantine real exhibits;
  5. the universal text guard drops a disambiguation line wherever it appears and
     leaves real prose untouched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pool_museum_checks as pmc
import disambiguation_guard as dg


# The Belvedere's own works (Klimt). A cached/SPARQL work set carries P195.
_BELVEDERE_QID = "Q303139"
_BELVEDERE_WORKS = [
    {"label_en": "The Kiss", "label_local": "Der Kuss",
     "collection_qids": [_BELVEDERE_QID], "instance_of": ["Q3305213"],
     "creator": "Gustav Klimt"},
    {"label_en": "Judith and the Head of Holofernes",
     "collection_qids": [_BELVEDERE_QID], "instance_of": ["Q3305213"],
     "creator": "Gustav Klimt"},
]


def _check(row, works=_BELVEDERE_WORKS, venue="Belvedere Museum, Vienna, Austria",
           qid=_BELVEDERE_QID):
    return pmc.check_pooled_museum_stop(
        row, venue_name=venue, venue_qid=qid, sparql_works=works)


class TestBelvedereForeignWorks:
    def test_monet_pere_paul_wrong_collection(self):
        # Monet's work carries a P195 that is some OTHER museum → wrong_collection.
        monet = {
            "title": "Portrait of Père Paul", "artist": "Claude Monet",
            "narration": "A portrait Monet painted in 1882.",
            "stop_record": {"collection_qids": ["Q23402"],  # Musée d'Orsay
                            "creator": "Claude Monet", "instance_of": ["Q3305213"]},
        }
        ok, reason = _check(monet)
        assert ok is False
        assert reason.startswith("wrong_collection"), reason

    def test_van_gogh_plain_of_auvers_wrong_collection(self):
        vg = {
            "title": "Plain of Auvers", "artist": "Vincent van Gogh",
            "narration": "Van Gogh painted this in 1890.",
            "stop_record": {"collection_qids": ["Q153306"],  # some other museum
                            "creator": "Vincent van Gogh",
                            "instance_of": ["Q3305213"]},
        }
        ok, reason = _check(vg)
        assert ok is False
        assert reason.startswith("wrong_collection"), reason


class TestDisambiguationPassageRejected:
    def test_may_refer_to_body_rejected(self):
        row = {
            "title": "The Kiss", "artist": "Gustav Klimt",
            "narration": "The Kiss may refer to: several works of art. "
                         "This one is by Klimt.",
        }
        ok, reason = _check(row)
        assert ok is False
        assert reason == "disambiguation_text", reason

    def test_raw_block_disambiguation_rejected(self):
        row = {
            "title": "Belvedere Palace", "artist": "",
            "narration": "A fine building.",
            "raw_block": "Belvedere may refer to: a palace, a place, a ship.",
        }
        ok, reason = _check(row)
        assert ok is False
        assert reason == "disambiguation_text", reason


class TestMetGiftShopRejected:
    def test_shop_product_title_rejected(self):
        row = {
            "title": "Starry Night Mug — The Met Store",
            "narration": "A ceramic mug.",
            "sources": ["https://store.metmuseum.org/products/starry-night-mug"],
        }
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Metropolitan Museum of Art, New York, NY",
            venue_qid="Q160236", sparql_works=[])
        assert ok is False
        assert reason == "shop_or_junk_title", reason

    def test_commerce_source_url_rejected(self):
        row = {
            "title": "Wall Calendar 2027",
            "narration": "A calendar.",
            "sources": ["https://store.metmuseum.org/shop/calendars/wall-calendar"],
        }
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Metropolitan Museum of Art", venue_qid="Q160236",
            sparql_works=[])
        assert ok is False
        assert reason in ("shop_or_junk_title", "shop_product_title"), reason


class TestRealWorksKept:
    def test_in_collection_klimt_kept(self):
        row = {"title": "The Kiss", "artist": "Gustav Klimt",
               "narration": "Klimt painted this between 1907 and 1908."}
        ok, reason = _check(row)
        assert ok is True, reason

    def test_local_language_work_no_artist_no_enrichment_kept(self):
        # A real foreign-language work with NO artist on the pooled row and whose
        # title is NOT in the (English-keyed) cache must be KEPT — the pooled path
        # must not quarantine a real exhibit for lack of P31/creator enrichment.
        row = {"title": "Adorazione dei Magi",
               "narration": "An unfinished Leonardo painting."}
        ok, reason = _check(row)
        assert ok is True, reason

    def test_no_reference_set_keeps_clean_stop(self):
        # No SPARQL set → the membership arm is a no-op; a clean title/body is kept.
        row = {"title": "The Kiss", "artist": "Gustav Klimt",
               "narration": "A painting."}
        ok, reason = _check(row, works=[])
        assert ok is True, reason


class TestEventAndRoomRejected:
    def test_event_title_rejected(self):
        row = {"title": "Austrian State Treaty",
               "narration": "The 1955 treaty was signed in this hall."}
        ok, reason = _check(row)
        assert ok is False
        assert reason in ("event_or_architecture_title", "nonartwork_class"), reason


class TestSplit:
    def test_split_keeps_good_rejects_bad(self):
        good = {"title": "The Kiss", "artist": "Gustav Klimt",
                "narration": "Klimt, 1907-08."}
        monet = {"title": "Portrait of Père Paul", "artist": "Claude Monet",
                 "narration": "x",
                 "stop_record": {"collection_qids": ["Q23402"]}}
        disamb = {"title": "Something", "narration": "X may refer to: a, b, c."}
        kept, rejected = pmc.split_pooled_museum_stops(
            [good, monet, disamb], venue_name="Belvedere Museum",
            venue_qid=_BELVEDERE_QID, sparql_works=_BELVEDERE_WORKS)
        assert [r["title"] for r in kept] == ["The Kiss"]
        reasons = {r["title"]: reason for r, reason in rejected}
        assert reasons["Portrait of Père Paul"].startswith("wrong_collection")
        assert reasons["Something"] == "disambiguation_text"


class TestStripDisambiguationLines:
    def test_whole_stub_paragraph_dropped(self):
        t = "Belvedere may refer to:\nBelvedere, Vienna\nBelvedere, California"
        cleaned, n = dg.strip_disambiguation_lines(t)
        assert n == 1
        assert "may refer to" not in cleaned

    def test_embedded_stub_sentence_dropped_body_kept(self):
        t = ("Welcome to the Belvedere. Belvedere may refer to: a place. "
             "The Upper Belvedere houses the collection.")
        cleaned, n = dg.strip_disambiguation_lines(t)
        assert n >= 1
        assert "may refer to" not in cleaned
        assert "Upper Belvedere houses the collection" in cleaned

    def test_real_prose_kept(self):
        t = ("In art-historical usage the term baroque may refer to a sweeping "
             "stylistic movement that spanned several decades across Europe and "
             "influenced countless painters, sculptors, and architects of the age.")
        cleaned, n = dg.strip_disambiguation_lines(t)
        assert n == 0
        assert cleaned == t

    def test_idempotent(self):
        t = "Schloss steht für: das Gebäude oder die Burg."
        once, n1 = dg.strip_disambiguation_lines(t)
        twice, n2 = dg.strip_disambiguation_lines(once)
        assert n2 == 0
        assert twice == once

    def test_empty(self):
        assert dg.strip_disambiguation_lines("") == ("", 0)

    def test_multilingual_leads(self):
        for lead in ("X may refer to: a, b.",
                     "Y peut faire référence à : a, b.",
                     "Z può riferirsi a: a, b.",
                     "W puede referirse a: a, b.",
                     "V kan verwijzen naar: a, b."):
            cleaned, n = dg.strip_disambiguation_lines(lead)
            assert n == 1, (lead, cleaned)
