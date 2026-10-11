"""test_local669b_identity_dedup.py — LOCAL-669B.

LOCAL-669's live HCMC run shipped ONE National Treasure as THREE stops:
  * "North Central South Spring Garden"       (R4, English Wikidata label)
  * "Central South and North Spring Garden"   (R4, reordered English altLabel)
  * "Vườn xuân Trung Nam Bắc"                  (grounded highlights, Vietnamese)
plus kept "Thanh niên Thành đồng" (Iron Wall Youth) as a legitimately SEPARATE
work. The token-based collapse guard folds the English permutations but cannot
bridge the Vietnamese to the English — so two of the three survived.

These tests pin the identity-based fix (identity_dedup.py):
  * the three Spring Garden variants collapse to ONE stop;
  * a Wikidata QID match collapses two differently-titled candidates;
  * a word-ORDER permutation collapses (sorted token set);
  * a Vietnamese/English pair collapses (carried bilingual pair, or via the
    D1v2 bilingual word map);
  * "Iron Wall Youth" (its own identity / own QID) is KEPT as a separate work;
  * a QID CONFLICT (two different QIDs) is NEVER merged;
  * the best-sourced title is the survivor.

Also pins the grounded_highlights bilingual-title split that feeds identity:
parse_highlights returns BOTH the local and English title.

Run: python3 -m pytest test_local669b_identity_dedup.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import identity_dedup as idd  # noqa: E402
from grounded_highlights import parse_highlights  # noqa: E402


# The HCMC National Treasure, in its three real surface forms, plus the distinct
# Iron Wall Youth work and one more distinct work.
_SPRING_EN = "North Central South Spring Garden"           # English Wikidata label
_SPRING_EN_ALT = "Central South and North Spring Garden"   # reordered altLabel
_SPRING_VN = "Vườn xuân Trung Nam Bắc"                      # Vietnamese
_SPRING_QID = "Q109406846"


def _poi(name, **kw):
    d = {"name": name}
    d.update(kw)
    return d


class TestNormSet(unittest.TestCase):
    """The order-ignored normalisation: lowercase, strip accents, drop punct,
    drop glue (the/of/and), SORTED token set."""

    def test_word_order_ignored(self):
        self.assertEqual(idd.norm_set(_SPRING_EN), idd.norm_set(_SPRING_EN_ALT))

    def test_glue_and_punct_dropped(self):
        a = idd.norm_set("Spring Garden of the Central, South, and North Region")
        b = idd.norm_set("Central South North Region Spring Garden")
        self.assertEqual(a, b)

    def test_accents_stripped(self):
        self.assertEqual(idd.norm_set("Café Terrace"), idd.norm_set("Cafe Terrace"))

    def test_empty_or_glue_only_is_blank(self):
        self.assertEqual(idd.norm_set(""), "")
        self.assertEqual(idd.norm_set("the of and"), "")

    def test_bilingual_map_expands(self):
        # A tiny per-venue map pairing VN words to their English counterparts.
        bmap = {"vuon": "garden", "xuan": "spring", "trung": "central",
                "nam": "south", "bac": "north",
                "garden": "vuon", "spring": "xuan", "central": "trung",
                "south": "nam", "north": "bac"}
        # With the map, the VN title's expanded set contains the English words.
        vn = set(idd.norm_set(_SPRING_VN, bmap).split())
        self.assertTrue({"garden", "spring", "central", "south", "north"} <= vn)


class TestThreeSpringGardensCollapse(unittest.TestCase):
    """The headline bug: one work, three stops → ONE stop."""

    def test_three_variants_one_stop(self):
        pool = [
            _poi(_SPRING_EN, qid=_SPRING_QID, verified=True,
                 thin_sources=[{"origin": "baotangmythuattphcm.com.vn",
                                "detail": "own_domain"}]),
            _poi(_SPRING_EN_ALT, verified=True),
            _poi(_SPRING_VN + f" ({_SPRING_EN})", title_local=_SPRING_VN,
                 title_en=_SPRING_EN, verified=True,
                 highlight_sources=[{"origin": "wikimedia.org", "detail": ""}]),
            _poi("Thanh niên Thành đồng", title_local="Thanh niên Thành đồng",
                 title_en="Iron Wall Youth", qid="Q555", verified=True),
            _poi("The Fisherman", verified=True),
        ]
        out, collapses = idd.dedup_by_identity(pool)
        names = [o["name"] for o in out]
        # Exactly one Spring Garden survives.
        spring_survivors = [n for n in names
                            if "spring" in idd.norm_set(n)]
        self.assertEqual(len(spring_survivors), 1, names)
        # Iron Wall Youth and The Fisherman are kept.
        self.assertIn("Thanh niên Thành đồng", names)
        self.assertIn("The Fisherman", names)
        self.assertEqual(len(out), 3, names)
        # One collapse record covering the two dropped Spring Garden forms.
        self.assertEqual(len(collapses), 1)
        self.assertEqual(len(collapses[0].dropped_titles), 2)

    def test_best_sourced_title_survives(self):
        # The QID-bearing, own-domain-sourced English form must be the survivor,
        # not the bare reordered altLabel.
        pool = [
            _poi(_SPRING_EN_ALT, verified=True),  # bare
            _poi(_SPRING_EN, qid=_SPRING_QID, verified=True,
                 thin_sources=[{"origin": "baotangmythuattphcm.com.vn",
                                "detail": "own_domain"}]),
        ]
        out, _ = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], _SPRING_EN)
        self.assertEqual(idd.candidate_qid(out[0]), _SPRING_QID)


class TestQidMatch(unittest.TestCase):
    def test_same_qid_different_titles_collapse(self):
        pool = [
            _poi("Some English Rendering", qid=_SPRING_QID, verified=True),
            _poi("Une tout autre formulation", qid=_SPRING_QID),
        ]
        out, collapses = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 1)
        self.assertEqual(collapses[0].reason, "qid")

    def test_qid_conflict_never_merges(self):
        # Same surface tokens but DIFFERENT QIDs → two distinct works.
        pool = [_poi("Spring Garden", qid="Q1"),
                _poi("Spring Garden", qid="Q2")]
        out, collapses = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 2)
        self.assertEqual(collapses, [])


class TestWordOrderMatch(unittest.TestCase):
    def test_reordered_english_collapses(self):
        pool = [_poi(_SPRING_EN), _poi(_SPRING_EN_ALT)]
        out, collapses = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 1)
        self.assertEqual(collapses[0].reason, "bilingual_title")


class TestBilingualMatch(unittest.TestCase):
    def test_vn_en_pair_collapses_on_carried_pair(self):
        # One candidate carries only the VN title; the other carries the VN+EN
        # pair → they share the VN normalised set.
        pool = [
            _poi(_SPRING_VN, title_local=_SPRING_VN),
            _poi(_SPRING_EN, title_local=_SPRING_VN, title_en=_SPRING_EN,
                 verified=True),
        ]
        out, _ = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 1)
        # The verified English form is kept.
        self.assertEqual(out[0]["name"], _SPRING_EN)

    def test_pure_vn_vs_pure_en_bridged_by_bilingual_map(self):
        bmap = {"vuon": "garden", "xuan": "spring", "trung": "central",
                "nam": "south", "bac": "north",
                "garden": "vuon", "spring": "xuan", "central": "trung",
                "south": "nam", "north": "bac"}
        pool = [_poi(_SPRING_VN), _poi(_SPRING_EN)]
        out, _ = idd.dedup_by_identity(pool, bilingual_map=bmap)
        self.assertEqual(len(out), 1)


class TestIronWallYouthKept(unittest.TestCase):
    """A distinct work must never be folded into the Spring Garden identity."""

    def test_iron_wall_youth_separate_no_qid(self):
        pool = [
            _poi(_SPRING_EN, qid=_SPRING_QID, verified=True),
            _poi("Iron Wall Youth", title_local="Thanh niên Thành đồng",
                 title_en="Iron Wall Youth", verified=True),
        ]
        out, _ = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 2)

    def test_iron_wall_youth_separate_own_qid(self):
        pool = [
            _poi(_SPRING_EN, qid=_SPRING_QID),
            _poi("Thanh niên Thành đồng", qid="Q777"),
        ]
        out, _ = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 2)


class TestDistinctWorksUntouched(unittest.TestCase):
    def test_unrelated_works_all_kept(self):
        pool = [_poi("The Fisherman"), _poi("Lotus Pond"),
                _poi("Mother and Child"), _poi("Rice Harvest")]
        out, collapses = idd.dedup_by_identity(pool)
        self.assertEqual(len(out), 4)
        self.assertEqual(collapses, [])

    def test_order_stable(self):
        pool = [_poi("Alpha"), _poi("Beta"), _poi("Gamma")]
        out, _ = idd.dedup_by_identity(pool)
        self.assertEqual([o["name"] for o in out], ["Alpha", "Beta", "Gamma"])


class TestBilingualTitleParse(unittest.TestCase):
    """parse_highlights must emit BOTH local and English titles so a candidate
    can match on either language."""

    def test_paren_gloss_split(self):
        res = {"text": ("1. Vườn xuân Trung Nam Bắc (North Central South Spring "
                        "Garden) — Nguyễn Gia Trí — lacquer, 1989\n"),
               "sources": [], "supports": []}
        cands = parse_highlights(res)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["title_local"], "Vườn xuân Trung Nam Bắc")
        self.assertEqual(cands[0]["title_en"], "North Central South Spring Garden")

    def test_quoted_gloss_split(self):
        res = {"text": ('1. Thanh niên Thành đồng — "Iron Wall Youth"\n'),
               "sources": [], "supports": []}
        cands = parse_highlights(res)
        self.assertEqual(cands[0]["title_local"], "Thanh niên Thành đồng")
        self.assertEqual(cands[0]["title_en"], "Iron Wall Youth")

    def test_year_paren_is_not_an_english_gloss(self):
        # A parenthetical YEAR must not be mistaken for an English title.
        res = {"text": ("1. The Fisherman (1943) — Nguyen\n"),
               "sources": [], "supports": []}
        cands = parse_highlights(res)
        self.assertEqual(cands[0]["title_local"], "The Fisherman")
        self.assertEqual(cands[0]["title_en"], "")

    def test_no_gloss_single_title(self):
        res = {"text": ("1. Lotus Pond — oil on canvas, 1960\n"),
               "sources": [], "supports": []}
        cands = parse_highlights(res)
        self.assertEqual(cands[0]["title_local"], "Lotus Pond")
        self.assertEqual(cands[0]["title_en"], "")


if __name__ == "__main__":
    unittest.main()
