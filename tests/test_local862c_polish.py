"""LOCAL-862C — legends are one disclosed block, name->venue bridge, no repeated
names, review claims never redefine the kind."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_context as usc  # noqa: E402
from user_stop_narration import _split_sentences  # noqa: E402

RAMBUTAN_LEGEND = ("In the Philippines, a legend tells how a man saves a deer from a tiger. "
                   "The deer turns into a fairy, Rodona, who offers him one wish. "
                   "He chooses a child: it is a girl named Rabona.")
GOOD_LEGEND = ("A Vietnamese folk tale tells of a dragon whose eye fell to earth. "
               "From it grew a tree with small black seeds. "
               "People called the fruit longan, the dragon's eye.")


class LegendBlock(unittest.TestCase):
    def test_fragment_is_omitted(self):
        self.assertIsNone(usc.legend_block(
            ["There was a young highly-skilled man, named Longan."], "longan"))
        self.assertIsNone(usc.legend_block(
            ["A legend tells of a young highly-skilled man named Longan."], "longan"))

    def test_story_that_never_returns_to_the_name_is_omitted(self):
        self.assertIsNone(usc.legend_block(_split_sentences(RAMBUTAN_LEGEND), "rambutan"))

    def test_dangling_pronoun_start_is_omitted(self):
        self.assertIsNone(usc.legend_block(
            ["He chose a child from the village that day.",
             "People later called the fruit longan, the dragon's eye."], "longan"))

    def test_coherent_block_kept_and_disclosed_once(self):
        blk = usc.legend_block(_split_sentences(GOOD_LEGEND), "longan")
        self.assertTrue(blk)
        out = usc.legend_block_text(blk)
        self.assertEqual(len(usc.DISCLOSURE_RE.findall(out)), 1)
        self.assertTrue(usc.has_disclosure(_split_sentences(out)[0]))
        self.assertLessEqual(len(_split_sentences(out)), 4)

    def test_marker_not_added_when_present(self):
        out = usc.legend_block_text("A legend tells how a dragon fell. Its eye became longan fruit.")
        self.assertEqual(len(usc.DISCLOSURE_RE.findall(out)), 1)
        self.assertTrue(out.startswith("A legend tells"))


FACTS = [
    {"kind": "name_meaning", "layer": 2, "text": "The name longan comes from the Chinese for dragon eye."},
    {"kind": "legend", "layer": 3, "text": GOOD_LEGEND},
]


class BlockReplace(unittest.TestCase):
    def test_per_sentence_markers_replaced_by_one_block(self):
        body = ("The name longan comes from the Chinese for dragon eye. "
                "A folk tale tells that a dragon whose eye fell to earth. "
                "A folk tale tells that from it grew a tree with small black seeds.")
        new, n = usc.apply_legend_blocks(body, FACTS)
        self.assertEqual(n, 1)
        self.assertEqual(len(usc.DISCLOSURE_RE.findall(new)), 1)
        self.assertIn("People called the fruit longan", new)

    def test_gate_licenses_continuation_and_drops_block_together(self):
        body = usc.apply_legend_blocks("The name longan comes from the Chinese for dragon eye.",
                                       FACTS)[0]
        sents = _split_sentences(body)
        lines = ["[context] " + FACTS[0]["text"], "[legend] " + GOOD_LEGEND]
        whys = usc.gate_body(sents, "Longan", lines)
        self.assertEqual([w for w in whys if w], [])
        keep = [True] * len(sents)
        keep[-1] = False                      # labeler dropped the last sentence
        keep = usc.enforce_legend_blocks(sents, keep, "Longan", lines)
        self.assertEqual(keep, [True, False, False, False])


class Bridge(unittest.TestCase):
    def test_kind_known(self):
        b = usc.bridge_sentence("Rambutan", "Bar", [
            {"kind": "name_meaning", "layer": 2, "text": "The name rambutan comes from rambut."}])
        self.assertEqual(b, 'The bar probably takes its name from the word "Rambutan".')

    def test_fruit_name_is_not_circular(self):
        b = usc.bridge_sentence("Rambutan", "", [
            {"kind": "name_meaning", "layer": 2, "text": "Rambutan is the edible fruit of a tree."}])
        self.assertEqual(b, "Its name probably comes from the rambutan fruit.")

    def test_kind_unknown(self):
        b = usc.bridge_sentence("Longan", "", FACTS)
        self.assertEqual(b, "Its name probably comes from the longan fruit.")

    def test_title_name(self):
        b = usc.bridge_sentence("A Star is Born", "", [
            {"kind": "name_meaning", "layer": 2,
             "text": 'The words "A Star is Born" are also the title of a film.'},
            {"kind": "unconfirmed", "layer": 3, "text": "The venue may have taken its name."}])
        self.assertEqual(b, "Its name probably comes from a well-known title.")

    def test_not_name_based(self):
        self.assertIsNone(usc.bridge_sentence("Thi Bar Saigon", "Gay bar", [
            {"kind": "street", "layer": 2, "text": "Along with Pham Ngu Lao, it is the Backpacker District."}]))

    def test_inserted_before_name_sentence_once(self):
        body = ("Longan is a stop you chose. The name longan comes from the Chinese for dragon eye. "
                "The seed looks like an eye.")
        new, br = usc.insert_bridge(body, "Longan", "", FACTS)
        ss = _split_sentences(new)
        self.assertEqual(ss[1], br)
        self.assertEqual(ss[2][:8], "The name")
        again, br2 = usc.insert_bridge(new, "Longan", "", FACTS)
        self.assertIsNone(br2)
        self.assertEqual(again, new)


class Dedupe(unittest.TestCase):
    def test_thi_bar(self):
        s = ("The bar is located on Đề Thám Street, which along with Phạm Ngũ Lão and "
             "Đề Thám Streets, forms Saigon's Backpacker District.")
        out = usc.dedupe_names(s)
        self.assertEqual(out.count("Đề Thám"), 1)
        self.assertIn("Phạm Ngũ Lão", out)

    def test_list_repeat(self):
        out = usc.dedupe_names("It sits near Pham Ngu Lao, De Tham and Pham Ngu Lao.")
        self.assertEqual(out.count("Pham Ngu Lao"), 1)

    def test_clean_sentence_untouched(self):
        s = "It sits near Pham Ngu Lao, De Tham and Bui Vien."
        self.assertEqual(usc.dedupe_names(s), s)


class Kind(unittest.TestCase):
    def test_kind_guard_attributes_redefinition(self):
        b = ("Thi Bar Saigon is rated 4.4 from about 1,200 reviews and is known as a live "
             "music bar with drag shows. The scene is small.")
        out = usc.kind_guard(b, "Gay bar")
        self.assertIn("and reviews describe it as a live music bar", out)
        self.assertNotIn("and is known as", out)

    def test_kind_guard_subject_form(self):
        out = usc.kind_guard("Thi Bar Saigon is a popular live music venue.", "Gay bar")
        self.assertEqual(out, "Thi Bar Saigon, according to reviews, is a popular live music venue.")

    def test_kind_guard_leaves_same_kind(self):
        t = "Thi Bar Saigon is a gay bar with a friendly crowd."
        self.assertEqual(usc.kind_guard(t, "Gay bar"), t)
        self.assertEqual(usc.kind_guard("It is a live music bar.", ""), "It is a live music bar.")

    def test_redefinition_is_attributed(self):
        t = ("Thi Bar Saigon is a popular live music venue in Ho Chi Minh City, known for "
             "its excellent bands.")
        out = usc.attribute_story(t, "Thi Bar Saigon", "Gay bar")
        self.assertTrue(out.startswith("Web reviews describe it as a popular live music venue"))

    def test_same_kind_untouched(self):
        t = "Acoustic Bar is a bar in District 1 with live sets."
        self.assertEqual(usc.attribute_story(t, "Acoustic Bar", "Bar"), t)

    def test_no_category_untouched(self):
        t = "Rambutan is a popular live music venue."
        self.assertEqual(usc.attribute_story(t, "Rambutan", ""), t)


if __name__ == "__main__":
    unittest.main()
