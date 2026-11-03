r"""
LOCAL-855D item 1 — an address abbreviation's full stop is never a sentence end.
================================================================================
Michael read the delivered Sophia cycling tour and found every address cut at the
first dot:

    "Address: 15 Đ."          (should be "15 Đ. Nguyễn Văn Tráng, …")
    "Address: 8 Đ."
    "Address: Đ."
    "Start by cycling along Đ."   (directions echoing the truncated road)

"Đ." is the Vietnamese abbreviation for *Đường* (Street); "P." = Phường (Ward),
"Q." = Quận (District), "TP." = Thành phố (City). The one shared splitter the
whole pipeline uses, ``sentence_split.split_sentences``, treated "Đ." as a
sentence boundary (its abbreviation guard only knew English titles, and its
single-initial rule only matched ASCII [A-Z], never the Vietnamese "Đ"), so
"15 Đ. Nguyễn Văn Tráng, …" split into "15 Đ." + "Nguyễn Văn Tráng, …". A later
gate drops/keeps one fragment and the stub "15 Đ." ships.

The fix is at the splitter root (so EVERY gate that calls it is fixed at once),
NOT a new regex in a scrub: ``đ, p, q, tp, kp`` are abbreviations whose dot is not
a boundary, and the trailing-token extractor recognises the Vietnamese "Đ/đ".

These tests CALL the real splitter (D418/D421 — never grep source). RED on base,
GREEN with the fix.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentence_split import split_sentences


# The exact address from the ticket.
ADDR = "15 Đ. Nguyễn Văn Tráng, Phường Bến Thành, Quận 1"


class TestAddressAbbreviationDotNotSplit(unittest.TestCase):
    """Đ. / P. / Q. / TP. are abbreviations, never a sentence end."""

    def test_ticket_address_stays_whole(self):
        parts = split_sentences(ADDR)
        self.assertEqual(parts, [ADDR],
                         f"address was cut at an abbreviation dot: {parts}")

    def test_no_bare_stub(self):
        # The exact defect: the stub "15 Đ." must never be produced.
        parts = split_sentences(ADDR)
        self.assertNotIn("15 Đ.", parts, f"produced the field stub: {parts}")
        self.assertEqual(len(parts), 1)

    def test_fully_abbreviated_vietnamese_address(self):
        s = "8 Đ. Lê Lợi, P. Bến Nghé, Q. 1, TP. Hồ Chí Minh"
        parts = split_sentences(s)
        self.assertEqual(parts, [s], f"split on a ward/district dot: {parts}")

    def test_bare_duong_prefix(self):
        parts = split_sentences("Đ. Nguyễn Thái Học")
        self.assertEqual(parts, ["Đ. Nguyễn Thái Học"])

    def test_directions_sentence_with_duong_not_cut(self):
        # "Start by cycling along Đ. Nguyễn Thái Học." — the road abbreviation must
        # not split the direction into "…along Đ." + "Nguyễn Thái Học.".
        s = "Start by cycling along Đ. Nguyễn Thái Học toward the market."
        parts = split_sentences(s)
        self.assertEqual(parts, [s], f"road abbreviation split a direction: {parts}")


class TestNoRegressionOnRealBoundaries(unittest.TestCase):
    """The fix must not weld two genuine sentences together."""

    def test_two_real_sentences_still_split(self):
        parts = split_sentences("This is the first stop. The second stop is ahead.")
        self.assertEqual(len(parts), 2, f"real boundary lost: {parts}")

    def test_english_initials_still_protected(self):
        s = ("In 1996, named The Charles S. and Isabella V. "
             "This transition mirrored growth.")
        self.assertEqual(split_sentences(s), [s])

    def test_us_acronym_still_protected(self):
        s = "He served in the U.S. Army for years."
        self.assertEqual(split_sentences(s), [s])

    def test_sentence_ending_in_word_then_new_sentence(self):
        # A sentence that ENDS on a real word followed by a new sentence must
        # still split — the abbrev set must not swallow ordinary endings.
        parts = split_sentences("We stopped at the shop. Then we rode on.")
        self.assertEqual(len(parts), 2, f"ordinary ending welded: {parts}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
