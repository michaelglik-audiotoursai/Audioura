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
    # [LOCAL-811B] The original fixtures asserted Monet's "Portrait of Père Paul"
    # and Van Gogh's "The Plain of Auvers" are foreign to the Belvedere. That was
    # WRONG — both ARE in the Österreichische Galerie Belvedere (LEAD correction).
    # A truly foreign work is used instead: Leonardo's "Mona Lisa" (Q12418), a
    # UNIQUE painting (P31=painting) whose single P195 is the Louvre (Q19675) — it
    # is not, and cannot be, in the Belvedere. This still exercises the
    # wrong_collection reject on a genuinely foreign, UNIQUE work.
    def test_mona_lisa_foreign_wrong_collection(self):
        mona = {
            "title": "Mona Lisa", "artist": "Leonardo da Vinci",
            "narration": "Leonardo's portrait, painted c. 1503-1519.",
            "stop_record": {"collection_qids": ["Q19675"],  # Louvre
                            "creator": "Leonardo da Vinci",
                            "instance_of": ["Q3305213"]},   # painting (unique)
        }
        ok, reason = _check(mona)
        assert ok is False
        assert reason.startswith("wrong_collection"), reason

    def test_belvedere_own_monet_is_kept(self):
        # Monet's "Portrait of Père Paul" IS in the Belvedere: with the venue's own
        # P195 it must be KEPT, proving the guard does not reject a work the museum
        # actually holds.
        monet = {
            "title": "Portrait of Père Paul", "artist": "Claude Monet",
            "narration": "A portrait Monet painted in 1882, held at the Belvedere.",
            "stop_record": {"collection_qids": [_BELVEDERE_QID],
                            "creator": "Claude Monet", "instance_of": ["Q3305213"]},
        }
        ok, reason = _check(monet)
        assert ok is True, reason


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
        mona = {"title": "Mona Lisa", "artist": "Leonardo da Vinci",
                "narration": "x",
                "stop_record": {"collection_qids": ["Q19675"],  # Louvre
                                "instance_of": ["Q3305213"]}}
        disamb = {"title": "Something", "narration": "X may refer to: a, b, c."}
        kept, rejected = pmc.split_pooled_museum_stops(
            [good, mona, disamb], venue_name="Belvedere Museum",
            venue_qid=_BELVEDERE_QID, sparql_works=_BELVEDERE_WORKS)
        assert [r["title"] for r in kept] == ["The Kiss"]
        reasons = {r["title"]: reason for r, reason in rejected}
        assert reasons["Mona Lisa"].startswith("wrong_collection")
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


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-811B] LEAD review of reports/local811_pool_audit_apply.txt — the first
# 811 audit over-rejected real artworks. These lock in the four corrections.
# ─────────────────────────────────────────────────────────────────────────────

import junk_title_guard as jtg


class TestIssue1CommerceIsWordOrUrlNotSubstring:
    """Commerce/junk detection must be word/URL based, never a substring of an
    artwork title; a quoted title is normal (LEAD item 1)."""

    def test_the_shop_girl_is_kept(self):
        # Tissot's "The Shop Girl" — "shop" is a substring, not a shop.
        assert jtg.is_junk_page_title("The Shop Girl") is False
        row = {"title": "The Shop Girl", "artist": "James Tissot",
               "narration": "A Tissot painting of a London shop interior."}
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Art Gallery of Ontario", sparql_works=[])
        assert ok is True, reason

    def test_lady_of_shalott_quote_is_kept(self):
        # Waterhouse's '"I am half sick of shadows," said the Lady of Shalott' —
        # a quoted line of verse, not a scraped news headline.
        t = '"I am half sick of shadows," said the Lady of Shalott'
        assert jtg.is_junk_page_title(t) is False
        ok, reason = pmc.check_pooled_museum_stop(
            {"title": t, "narration": "A Waterhouse painting."},
            venue_name="Tate Britain", sparql_works=[])
        assert ok is True, reason

    def test_guillemet_quoted_title_is_kept(self):
        # A balanced French-quote pair wrapping a span is a quoted title, not a
        # breadcrumb — "Pendule « L'Amitié voilant les heures »".
        t = "Pendule « L’Amitié voilant les heures »"
        assert jtg.is_junk_page_title(t) is False
        ok, reason = pmc.check_pooled_museum_stop(
            {"title": t, "narration": "A gilt-bronze mantel clock."},
            venue_name="Musée Marmottan Monet", sparql_works=[])
        assert ok is True, reason

    def test_real_commerce_still_rejected(self):
        # The genuine signals the LEAD lists must still bite.
        assert jtg.is_junk_page_title("Gift Shop") is True
        assert jtg.is_junk_page_title("Visit our online shop") is True
        assert jtg.is_junk_page_title(
            "Explore this painting in our virtual tour") is True
        assert jtg.is_junk_page_title(
            "Profile « The ALBERTINA Museum Vienna") is True        # breadcrumb
        assert jtg.is_junk_page_title(
            "BU Masters Show 2026 | Traces: Pursuing Process") is True  # pipe
        assert jtg.is_shop_product_title("Wall Calendar 2027") is True
        assert jtg.is_commerce_url(
            "https://store.metmuseum.org/products/x") is True


class TestIssue2MultiplesAndEditionsKept:
    """A cast/print/edition, a work with >=2 P195 values, or a site-listed work
    is KEPT; reject on P195 only when the work is UNIQUE with a single foreign
    P195 (LEAD item 2)."""

    def test_age_of_bronze_cast_is_kept(self):
        # Rodin's "The Age of Bronze" is a bronze cast (P31 sculpture) held in
        # many collections; one foreign P195 must not reject it.
        row = {"title": "The Age of Bronze", "artist": "Auguste Rodin",
               "narration": "A life-size bronze figure by Rodin.",
               "stop_record": {"collection_qids": ["Q23402"],
                               "creator": "Auguste Rodin",
                               "instance_of": ["Q860861"]}}  # sculpture
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Rodin Museum", venue_qid="Q840886", sparql_works=[])
        assert ok is True, reason

    def test_print_by_title_word_is_kept(self):
        row = {"title": "The Great Wave (woodcut print)", "artist": "Hokusai",
               "narration": "A colour woodblock print.",
               "stop_record": {"collection_qids": ["Q23402"], "creator": "Hokusai"}}
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Some Museum", venue_qid="Q840886", sparql_works=[])
        assert ok is True, reason

    def test_two_p195_values_kept(self):
        row = {"title": "A Shared Work", "artist": "X",
               "narration": "y",
               "stop_record": {"collection_qids": ["Q23402", "Q111111"],
                               "instance_of": ["Q3305213"]}}  # unique painting…
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Some Museum", venue_qid="Q840886", sparql_works=[])
        assert ok is True, reason  # …but two P195 → kept

    def test_unique_painting_single_foreign_p195_still_rejected(self):
        # The one case that MUST still reject: a unique work whose single P195 is
        # another museum (Mona Lisa at the Belvedere).
        row = {"title": "Mona Lisa", "artist": "Leonardo da Vinci",
               "narration": "y",
               "stop_record": {"collection_qids": ["Q19675"],   # Louvre
                               "instance_of": ["Q3305213"]}}     # unique painting
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Belvedere", venue_qid=_BELVEDERE_QID, sparql_works=[])
        assert ok is False
        assert reason.startswith("wrong_collection"), reason

    def test_site_listed_overrides_foreign_p195(self):
        # If the venue's own SPARQL/site set lists the title, a stale foreign P195
        # must not reject it.
        works = [{"label_en": "Ophelia", "collection_qids": ["Q860861X"],
                  "instance_of": ["Q3305213"]}]
        row = {"title": "Ophelia", "artist": "John Everett Millais",
               "narration": "y",
               "stop_record": {"collection_qids": ["Q23402"],
                               "instance_of": ["Q3305213"]}}
        ok, reason = pmc.check_pooled_museum_stop(
            row, venue_name="Tate Britain", venue_qid="Q842858",
            sparql_works=works, site_titles=["Ophelia"])
        assert ok is True, reason


class TestIssue4RoomTitleOnlyForContainedTours:
    """room_or_space_title (and venue_itself_title) must apply ONLY to contained
    (museum/facility) tours, never to walking/neighbourhood pools (LEAD item 4)."""

    _SALEM = ["Salem Witch Trials Memorial", "Salem Common",
              "Salem Maritime National Historic Site", "Salem Willows Park",
              "Salem Witch Museum"]

    def test_walking_pool_keeps_named_places(self):
        for t in self._SALEM:
            ok, reason = pmc.check_pooled_museum_stop(
                {"title": t, "narration": "A Salem stop."},
                venue_name="Salem", contained=False, sparql_works=[])
            assert ok is True, (t, reason)

    def test_contained_tour_still_rejects_a_room(self):
        ok, reason = pmc.check_pooled_museum_stop(
            {"title": "Gallery 5", "narration": "x"},
            venue_name="Some Museum", contained=True, sparql_works=[])
        assert ok is False
        assert reason == "room_or_space_title", reason

    def test_split_respects_contained_flag(self):
        rows = [{"title": t, "narration": "x"} for t in self._SALEM]
        kept_walk, rej_walk = pmc.split_pooled_museum_stops(
            rows, venue_name="Salem", contained=False, sparql_works=[])
        assert len(kept_walk) == len(self._SALEM) and not rej_walk
        kept_mus, rej_mus = pmc.split_pooled_museum_stops(
            rows, venue_name="Salem", contained=True, sparql_works=[])
        # On a contained tour those same titles read as spaces → all rejected.
        assert not kept_mus and len(rej_mus) == len(self._SALEM)
        assert all(r == "room_or_space_title" for _, r in rej_mus)
