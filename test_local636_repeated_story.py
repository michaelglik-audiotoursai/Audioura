#!/usr/bin/env python3
"""test_local636_repeated_story.py — issue 2: the same story told twice.

Grounded on the REAL Bench R2 tours the critic flagged with D533 reporting
"No cross-stop fact repetition detected":

  * Brera 513 told the Brera-name etymology in Stop 1 ("the Germanic word
    'braida,' meaning a grassy opening in the city structure") AND Stop 2 ("its
    name drawn from an ancient word for a grassy opening"). Neither carries a
    year, so the (year, entity) fact signature was blind to it. A rare-noun-phrase
    keyphrase signature ("grassy opening") catches it.
  * Courtauld 485 repeated the collector boast — Stop 1 "the most important group
    of Cézanne's works in Britain", Stop 2 "the largest collection of Seurat's
    work in the United Kingdom". Different artist, different wording, no shared
    year: a superlative-collection signature keyed on the (canonicalised) place
    collapses them.

Keep the FIRST telling, drop the later one. No false positives on previews,
titles, or ordinary prose collocations. Pure/offline. Run:
    python3 -m pytest test_local636_repeated_story.py -q
"""
import os
import unittest

import derepetition_guard as d


def _tour(tid):
    p = "/Users/micha/Audioura/.continuous_dev/calib/critique/tour_%d.txt" % tid
    return open(p).read() if os.path.exists(p) else None


# ── keyphrase signature unit behaviour ────────────────────────────────────────
class TestKeyphraseSignature(unittest.TestCase):
    def test_rare_noun_phrase_keys(self):
        s = ("the Germanic word braida, meaning a grassy opening in the city "
             "structure")
        self.assertIn(("kp", ("grassy", "opening")), d.keyphrase_signatures(s))

    def test_ordinary_collocation_does_not_key(self):
        # "turning point", "faith and loss", "evolution of modern art" are common
        # English and must NOT produce a keyphrase signature.
        for s in ("the incident became a turning point in his life",
                  "our shared experiences of faith and loss",
                  "the evolution of modern art through innovative techniques"):
            self.assertEqual(d.keyphrase_signatures(s), set(),
                             "ordinary prose should not key: %r" % s)

    def test_quoted_title_and_proper_names_do_not_key(self):
        s = ('Stand before "Madonna col Bambino e santi, angeli e Federico da '
             'Montefeltro" in Sala XXIV.')
        # Nothing distinctive outside the quoted title / proper nouns.
        self.assertEqual(d.keyphrase_signatures(s), set())

    def test_superlative_collection_collapses_across_place_synonyms(self):
        a = ("the gallery holds the most important group of Cézanne's works in "
             "Britain")
        b = ("Courtauld's acquisitions brought together the largest collection "
             "of Seurat's work in the United Kingdom")
        sa = {x for x in d.keyphrase_signatures(a) if x[0] == "coll"}
        sb = {x for x in d.keyphrase_signatures(b) if x[0] == "coll"}
        self.assertTrue(sa and sa == sb,
                        "Britain and the UK must canonicalise to one place: %s vs %s"
                        % (sa, sb))


# ── end-to-end on the real tours ──────────────────────────────────────────────
class TestRealTourDedupe(unittest.TestCase):
    def test_brera_grassy_opening_told_once(self):
        t = _tour(513)
        if t is None:
            self.skipTest("tour_513.txt not present")
        self.assertEqual(t.count("grassy opening"), 2, "fixture precondition")
        out, actions = d.strip_repeated_facts(t)
        self.assertEqual(out.count("grassy opening"), 1,
                         "the etymology must survive exactly once")
        self.assertTrue(any(a["removed"] and "grassy opening" in a["sentence"]
                            for a in actions))

    def test_courtauld_collector_boast_told_once(self):
        t = _tour(485)
        if t is None:
            self.skipTest("tour_485.txt not present")
        reps = d.check_cross_stop_fact_repetition(t)
        self.assertTrue(any(r["signature"].startswith("coll/") for r in reps),
                        "the superlative-collection boast must be detected")
        out, actions = d.strip_repeated_facts(t)
        # The later (Stop 2 / Seurat) telling is removed; the first (Stop 1) kept.
        self.assertNotIn("largest collection of Seurat", out.replace("\u2019", "'"))
        self.assertIn("most important group of Cézanne", out)

    def test_dedupe_empties_no_stop(self):
        import re
        for tid in (513, 485):
            t = _tour(tid)
            if t is None:
                continue
            out, _ = d.strip_repeated_facts(t)
            for n in (1, 2, 3):
                m = re.search(r"Stop %d:.*?(?=\nStop %d:|$)" % (n, n + 1), out, re.S)
                if m:
                    self.assertGreater(len(m.group(0).strip()), 200,
                                       "tour %d stop %d emptied" % (tid, n))


if __name__ == "__main__":
    unittest.main()
