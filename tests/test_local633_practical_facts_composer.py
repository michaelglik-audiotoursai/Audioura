"""test_local633_practical_facts_composer.py — LOCAL-633.

Bench R1 flagged three tours that spoke the RAW preflight dump inside the first
stop:

  * Uffizi 488:  "The museum is open Tuesday to Sunday, 8:15 AM to 6:30 PM (the
                  ticket office closes at 5:30 PM …); closed on Mondays, January 1,
                  and December 25. Free admission: Visitors under 18, …"
  * Reina Sofía 505 (Stop 2): "admission is General Admission: €12; Combined
                  Ticket …: €18; Two-visit pass …: €18; Free Admission: …"
  * Met 507:     "admission is General admission is $30 for adults, $22 for seniors
                  (65+), $22 for visitors with disabilities, $17 for students, …"

LOCAL-633 composes ONE short spoken sentence pair from the STRUCTURED preflight,
places it ONCE in the Stop-1 opening section (right after the About sentences),
and never inside any Orientation. The "Museum Information:" field keeps the full
detail for the TEXT VIEW but is dropped WHOLE from TTS.

This suite asserts:
  1. the composer on the exact 488/505/507 dumps — short, no parens/discounts,
     one price, currency as a word, and every bench detector passes;
  2. the once-guard — the opening section speaks hours at most once;
  3. no practical facts land inside any Orientation paragraph;
  4. TTS drops the whole "Museum Information:" line while keeping the composed
     sentence.

Run: python3 -m pytest tests/test_local633_practical_facts_composer.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import practical_facts_gate as pfg  # noqa: E402
import about_museum_stop as ams  # noqa: E402


# ── The STRUCTURED preflight for each flagged tour (the exact R1 dump content,
#    carried as the hours / admission fields the preflight produced). ──────────
PREFLIGHT_488_UFFIZI = {
    "name": "Uffizi Gallery, Florence, Italy",
    "hours": ("Tuesday to Sunday, 8:15 AM to 6:30 PM (the ticket office closes at "
              "5:30 PM, and halls begin closing at 6:00 PM / 6:30 PM); closed on "
              "Mondays, January 1, and December 25"),
    "admission": ("Full price: €25. Free admission: Visitors under 18, visitors "
                  "with disabilities and a companion, and all visitors on the first "
                  "Sunday of each month. (Discounts exist for early morning/afternoon "
                  "slots, as well as combined multi-site/Vasari Corridor passes)"),
}

PREFLIGHT_505_REINA = {
    "name": "Museo Reina Sofía, Madrid, Spain",
    "hours": ("Monday, Wednesday to Saturday: 10:00 AM – 9:00 PM; Sunday: 10:00 AM "
              "– 2:30 PM; Tuesday: Closed"),
    "admission": ("General Admission: €12; Combined Ticket (with audioguide at ticket "
                  "office): €18; Two-visit pass (within one year): €18; Free Admission: "
                  "Offered to the general public Monday and Wednesday–Saturday from "
                  "7:00 PM – 9:00 PM, and Sunday from 12:30 PM – 2:30 PM; free at all "
                  "times for visitors under 18, over 65, and eligible students"),
}

PREFLIGHT_507_MET = {
    "name": "Metropolitan Museum of Art, New York",
    "hours": ("Sunday, Monday, Tuesday, Thursday, Friday, and Saturday from 10:00 "
              "AM to 5:00 PM; closed on Wednesdays"),
    "admission": ("General admission is $30 for adults, $22 for seniors (65+), $22 "
                  "for visitors with disabilities, $17 for students, and free for "
                  "children 12 and under as well as museum members"),
}


def _bench_detectors(spoken):
    """Mirror of the five bench detectors LOCAL-633 must satisfy
    (.continuous_dev/bench/detectors.py). Returns a list of failing names."""
    fails = []
    hours = re.findall(
        r"(?i)\b(?:is open|open daily|open (?:mon|tue|wed|thu|fri|sat|sun)\w*|"
        r"opening hours)\b", spoken)
    if len(hours) > 1:
        fails.append("hours_said_twice")
    adm = re.findall(r"(?i)admission[^.]*\.", spoken)
    if len(adm) > 1:
        fails.append("admission_twice")
    if (any("free" in a.lower() for a in adm)
            and any(re.search(r"[£€$]\s?\d", a) and "free" not in a.lower()
                    for a in adm)):
        fails.append("admission_conflict")
    if re.search(r"(?i)\bopen open\b|admission is (single|standard) ticket", spoken):
        fails.append("raw_label_dup")
    money = re.findall(r"[£€$]\s?\d+", spoken)
    if len(money) > 2:
        fails.append("price_list_dump")
    if re.search(r"(?i)\badmission is (general|adult|regular|standard|single)\b|"
                 r"\bis open (sunday|monday|tuesday|wednesday|thursday|friday|"
                 r"saturday),", spoken):
        fails.append("label_echo")
    long_pf = [x for x in re.split(r"(?<=[.!?])\s+|\n+", spoken)
               if re.search(r"\d{1,2}[:.]\d{2}", x) and len(x.split()) > 30]
    if long_pf:
        fails.append("long_practical_sentence")
    return fails


class TestComposerOnRealDumps(unittest.TestCase):
    def test_488_uffizi(self):
        out = pfg.compose_practical_facts(PREFLIGHT_488_UFFIZI)
        # Matches the example the task pins (day range + short time span, one price,
        # one free group, currency as a word).
        self.assertEqual(
            out,
            "The Uffizi is open Tuesday to Sunday from 8:15 to 6:30, and closed on "
            "Mondays. Admission is 25 euros for adults; under-18s go free.")
        self._assert_rules(out)

    def test_505_reina_sofia(self):
        out = pfg.compose_practical_facts(PREFLIGHT_505_REINA)
        self.assertIn("open", out)
        self.assertIn("12 euros", out)      # one adult price, currency as a word
        self.assertNotIn("€", out)          # never a currency symbol
        self.assertNotIn("18 euros", out)   # no combined/two-visit price table
        self._assert_rules(out)

    def test_507_met(self):
        out = pfg.compose_practical_facts(PREFLIGHT_507_MET)
        self.assertIn("The Met is open", out)
        self.assertIn("Wednesday", out)     # the single closed day
        self.assertIn("30 dollars", out)    # adult price, currency as a word
        self.assertNotIn("$", out)
        self.assertNotIn("22 dollars", out)  # no seniors/students price list
        self._assert_rules(out)

    def _assert_rules(self, out):
        # <= 2 sentences, about 30 words, no parentheses, no discount schemes.
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", out) if s.strip()]
        self.assertLessEqual(len(sentences), 2, out)
        self.assertLessEqual(len(out.split()), 32, out)
        self.assertNotIn("(", out)
        self.assertNotIn(")", out)
        self.assertNotIn("ticket office", out.lower())
        self.assertNotIn("discount", out.lower())
        self.assertNotIn("combined", out.lower())
        # currency spoken as a word, never a symbol.
        self.assertNotRegex(out, r"[£€$¥]")
        # every bench detector passes.
        self.assertEqual([], _bench_detectors(out), out)


class TestComposerFaithfulness(unittest.TestCase):
    def test_empty_preflight_is_silent(self):
        self.assertEqual("", pfg.compose_practical_facts({}))
        self.assertEqual("", pfg.compose_practical_facts(None))
        self.assertEqual("", pfg.compose_practical_facts(
            {"hours": "", "admission": ""}))

    def test_errored_or_skipped_preflight_is_silent(self):
        self.assertEqual("", pfg.compose_practical_facts(
            {"error": "timeout", "hours": "Tuesday to Sunday"}))
        self.assertEqual("", pfg.compose_practical_facts(
            {"skipped": True, "admission": "€25"}))

    def test_hours_only_still_spoken(self):
        out = pfg.compose_practical_facts(
            {"name": "Tate Modern", "hours": "open daily"})
        self.assertEqual("The Tate Modern is open daily.", out)

    def test_general_free_admission(self):
        out = pfg.compose_practical_facts(
            {"name": "Getty", "hours": "open daily except Monday",
             "admission": "Admission is free"})
        self.assertIn("Admission is free.", out)
        self.assertNotIn("Adult tickets", out)


class TestOnceGuardInOpeningSection(unittest.TestCase):
    """The composed sentence is spoken at MOST once; a second injection is a no-op."""

    def test_ensure_spoken_hours_line_is_noop_when_already_spoken(self):
        text = ("You are about to explore the Uffizi Gallery. The Uffizi is open "
                "Tuesday to Sunday, and closed on Mondays. Adult tickets are 25 "
                "euros; under-18s go free.\n\nStop 1: Leda col cigno\n\n"
                "Orientation: Walk to Gallery 15.")
        out, inserted = pfg.ensure_spoken_hours_line(
            text, hours="Tuesday to Sunday; closed on Mondays",
            admission="€25 adults; under 18 free")
        self.assertFalse(inserted)      # once-guard: already spoken -> no-op
        self.assertEqual(text, out)
        # Exactly one spoken hours statement.
        self.assertEqual(1, len(re.findall(r"(?i)\bis open\b", out)))

    def test_ensure_spoken_hours_line_inserts_once_when_absent(self):
        text = ("You are about to explore the Uffizi Gallery.\n\n"
                "Stop 1: Leda col cigno\n\nOrientation: Walk to Gallery 15.")
        out, inserted = pfg.ensure_spoken_hours_line(
            text, hours="Tuesday to Sunday; closed on Mondays",
            admission="€25 for adults; under 18 free")
        self.assertTrue(inserted)
        self.assertEqual(1, len(re.findall(r"(?i)\bis open\b", out)))


class TestNoPracticalFactsInOrientation(unittest.TestCase):
    """Practical facts belong in the opening section, NEVER in an Orientation."""

    def _orientation_blocks(self, text):
        return [p for p in text.split("\n\n")
                if re.search(r"(?i)^\s*orientation:", p.strip())]

    def test_ensure_spoken_hours_line_never_touches_orientation(self):
        text = ("You are about to explore the Metropolitan Museum of Art.\n\n"
                "Stop 1: Allegory of the Catholic Faith\n\n"
                "Orientation: Enter Gallery 614 and look up.")
        out, inserted = pfg.ensure_spoken_hours_line(
            text, hours="closed on Wednesdays",
            admission="$30 for adults; children 12 and under free")
        self.assertTrue(inserted)
        for block in self._orientation_blocks(out):
            self.assertNotRegex(block, r"(?i)\bis open\b")
            self.assertNotRegex(block, r"(?i)\badult tickets\b")
            self.assertNotRegex(block, r"[£€$]\s?\d")
            self.assertIn("Enter Gallery 614", block)   # Orientation value intact

    def test_opening_section_carries_the_sentence(self):
        """about_museum_stop._compose_visiting_sentences routes the gated facts
        string through the composer — one short pair, no verbatim dump."""
        gated = ("The museum is open Tuesday to Sunday. Closed on Mondays. "
                 "Admission is €25 for adults; free for under 18.")
        out = ams._compose_visiting_sentences(
            gated, "Uffizi Gallery", "uffizi.it", "October 2026")
        self.assertIn("open Tuesday to Sunday", out)
        self.assertIn("25 euros", out)
        self.assertNotIn("€", out)
        self.assertEqual([], _bench_detectors(out), out)


class TestTtsDropsMuseumInformationLine(unittest.TestCase):
    """TTS speaks only the composed sentence; the long 'Museum Information:' field
    value is dropped WHOLE (label + value) from the spoken text."""

    def test_english_tts_strip_drops_whole_museum_information_line(self):
        import tour_generation_modernized as tgm
        text = (
            "Stop 1: Leda col cigno\n\n"
            "The Uffizi is open Tuesday to Sunday, and closed on Mondays. "
            "Adult tickets are 25 euros; under-18s go free.\n\n"
            "Museum Information: The museum is open Tuesday to Sunday, 8:15 AM to "
            "6:30 PM (the ticket office closes at 5:30 PM); closed on Mondays, "
            "January 1, and December 25. Free admission: visitors under 18.\n\n"
            "Orientation: Walk to Gallery 15.")
        tts = tgm._strip_nav_fields_for_tts(text)
        # The field line (label AND its long value) is gone from TTS.
        self.assertNotIn("Museum Information", tts)
        self.assertNotIn("ticket office", tts)
        self.assertNotIn("8:15 AM", tts)
        # The composed sentence remains spoken.
        self.assertIn("Adult tickets are 25 euros", tts)
        # Orientation value is still spoken (label stripped, value kept).
        self.assertIn("Walk to Gallery 15", tts)
        self.assertNotIn("Orientation:", tts)


if __name__ == "__main__":
    unittest.main()
