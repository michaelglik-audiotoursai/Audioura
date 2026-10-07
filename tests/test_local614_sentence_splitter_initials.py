r"""
LOCAL-614 item 1 — a single capital letter + period (an initial) is never a
sentence end, in the ONE shared splitter the dedupe/strip pipeline uses.
=========================================================================
The kiro-cli critique of McMullen tour 399 found three broken sentences, all the
same bug: the cross-stop fact dedupe (LOCAL-607) split sentences with the raw
``re.split(r'(?<=[.!?])\s+', text)`` regex, which treats an initial's full stop
("V.", "L.") as a sentence boundary. A later gate then drops one half, leaving

    "…named The Charles S. and Isabella V.This transition…"   (space eaten)
    "…along with Gail L. The expertise…"                       (fragment kept)
    "Brody and Gail L. Hoffman. Through their…"                (name split off)

The fix: ``cross_stop_fact_dedupe`` must use the shared ``sentence_split`` module
(which already guards initials and abbreviations) instead of its own regex, so a
single capital letter followed by a period is never a sentence end.

These tests CALL the real splitter and the real dedupe entry points (D418/D421 —
never grep source). They are RED on the base (own-regex splitter) and GREEN once
the shared splitter is wired in.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cross_stop_fact_dedupe as dd
from sentence_split import split_sentences


# The exact strings the critique flagged (tour 399).
INITIAL_MIDNAME = (
    "In 1996, the museum was officially named The Charles S. and Isabella V. "
    "This transition mirrored the museum's evolving role.")
INITIAL_CURATOR = (
    "The role as a curator, along with Gail L. The expertise brought the "
    "exhibit to life.")
INITIAL_TRAILING = (
    "Brody and Gail L. Hoffman assembled the catalog. Through their expertise, "
    "the catalog provides context.")


class TestSharedSplitterInitials(unittest.TestCase):
    """A single capital letter + '.' is an initial, never a sentence boundary."""

    def test_middle_initial_in_name_not_split(self):
        # "Isabella V." must stay joined to what follows it.
        parts = split_sentences(INITIAL_MIDNAME)
        self.assertEqual(len(parts), 1, f"split on an initial: {parts}")
        self.assertIn("Isabella V. This transition", " ".join(parts))

    def test_curator_initial_not_split(self):
        parts = split_sentences(INITIAL_CURATOR)
        self.assertEqual(len(parts), 1, f"split on an initial: {parts}")

    def test_trailing_name_initial_keeps_surname(self):
        # "Gail L. Hoffman" is ONE name — the surname must not be orphaned.
        parts = split_sentences(INITIAL_TRAILING)
        self.assertEqual(len(parts), 2, f"wrong split: {parts}")
        self.assertIn("Gail L. Hoffman", parts[0])


class TestDedupeSplitsOnlyOnRealBoundaries(unittest.TestCase):
    """The LOCAL-607 dedupe must split with the shared splitter: an initial inside
    a name must NOT be a split point, so the dedupe can never drop half a name."""

    def test_dedupe_internal_splitter_keeps_initial_name_whole(self):
        # The dedupe's sentence splitter must keep "The Charles S. and Isabella V."
        # as ONE sentence with what follows — not three fragments.
        s = ("In 1996, the museum was named The Charles S. and Isabella V. "
             "This transition mirrored growth.")
        parts = dd._split_sentences(s)
        self.assertEqual(len(parts), 1,
                         f"dedupe split on an initial into {len(parts)}: {parts}")

    def test_dedupe_drop_cannot_orphan_a_name(self):
        # Stop 1 states the 1996 renaming; Stop 2 restates it in a sentence that
        # also carries the donor initials. On the base, the raw regex splits that
        # restatement at "Charles S." and "Isabella V.", so the dedupe drops the
        # year-anchored fragment and leaves the orphan "and Isabella V. This
        # transition…". With the shared splitter the WHOLE restatement is one
        # sentence: it is dropped cleanly or kept whole — never half.
        units = [
            {"title": "Grace Hoops", "narration":
                "In 1996 the Charles bequest renamed the institution. "
                "Grace Hoops shows two women at play."},
            {"title": "Paris Along the Seine", "narration":
                "In 1996, the museum was officially named The Charles S. and "
                "Isabella V. McMullen Museum of Art. Marquet painted the Seine."},
        ]
        new_units, _ = dd.dedupe_stop_units(units, stop1_owns_history=True)
        out = new_units[1]["narration"]
        # The donor initials belong to one whole sentence. On the base, the raw
        # splitter cut it at "The Charles S." — a fragment that fingerprints to
        # (1996, charles), collides with Stop 1 and is DROPPED, orphaning
        # "and Isabella V. McMullen Museum of Art." With the shared splitter the
        # restatement is ONE sentence (fingerprint 1996+charles+isabella+mcmullen),
        # which does not collide, so the whole sentence survives — name intact.
        self.assertIn("The Charles S. and Isabella V. McMullen", out,
                      f"name was broken by a split: {out!r}")
        # The real work sentence must survive intact.
        self.assertIn("Marquet painted the Seine", out)

    def test_dedupe_tour_text_preserves_initials(self):
        tour = (
            "Step-by-Step Audio Guided Tour: McMullen Museum of Art\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Grace Hoops\n\n"
            "Grace Hoops shows two young women at play. The role as a curator, "
            "along with Gail L. The expertise brought the exhibit to life.\n")
        res = dd.dedupe_tour_facts(tour)
        self.assertIn("Gail L. The expertise", res.tour_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
