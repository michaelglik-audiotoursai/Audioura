#!/usr/bin/env python3
"""test_local592_r4_dayrange_spoken.py — LOCAL-592 r4.

Why r3 bounced (LEAD review, 2026-10-06 11:0x):

  1. HOURS DROP THEIR DAYS. The Athenaeum source says "Monday–Thursday: 9 am –
     8 pm", the Griffin says "Tuesday through Sunday: Noon to 4 PM". r3 stated
     only the TIME ("9 AM–8 PM", "Noon–4 PM"), which a Saturday listener hears as
     every day. Hours without their days is a misleading half-fact: the day range
     MUST be bound to every time range, through the extractor AND the composer. If
     a page lists several day groups, state each one; if the days cannot be bound
     to the times, OMIT the times and point to the website.

  2. IT READS LIKE A NOTE, NOT SPEECH. r3 emitted
     "Before you go in, a few practical notes. Closed on Monday. Noon–4 PM. $12."
     r4 composes sentences and keeps the source + month honesty signal (D584/D582)
     and the admission categories the page gives (adults / seniors / students /
     teachers), never inventing one:
       "The Griffin is open Tuesday through Sunday, noon to 4 PM, and closed on
        Mondays and major holidays. Admission is $12 for adults and $8 for seniors,
        students and teachers, as listed on griffinmuseum.org in October 2026."

These tests are OFFLINE and deterministic. They are RED on 7bba912 (the r3
extractor stores no day range; the r3 composer emits note fragments) and GREEN
after r4.

Run: python3 -m pytest test_local592_r4_dayrange_spoken.py -q
"""
import re
import unittest

import about_museum_stop as am
from visitor_facts_extractor import extract_visitor_facts_from_text


# ── 1. Extractor binds the DAY RANGE to each time range ──────────────────────

class TestExtractorBindsDayRange(unittest.TestCase):
    """Each extracted hours entry carries the day range the page bound to it."""

    def test_griffin_hours_carry_tuesday_through_sunday(self):
        page = ("Hours Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.")
        f = extract_visitor_facts_from_text(
            page, 'en', venue_name="Griffin Museum of Photography")
        self.assertTrue(f.hours, "the venue's hours must be extracted")
        # The day range travels WITH the time range, not dropped.
        days = " ".join(h.get("days", "") for h in f.hours).lower()
        self.assertIn("tuesday", days, f"day range must bind to the hours: {f.hours}")
        self.assertIn("sunday", days, f"day range must bind to the hours: {f.hours}")

    def test_athenaeum_monday_thursday_binds_days(self):
        page = ("Hours Monday-Thursday: 9 am – 8 pm Friday and Saturday: 9 am – 5 pm "
                "Sunday: Closed. Questions? Call (617) 720-7604.")
        f = extract_visitor_facts_from_text(
            page, 'en', venue_name="Boston Athenaeum")
        self.assertTrue(f.hours)
        # The FIRST group's hours (9 AM–8 PM) must carry Monday–Thursday, so a
        # Saturday listener is never told the whole week opens 9–8.
        first = f.hours[0]
        self.assertRegex(first.get("days", "").lower(), r"mon",
                         f"first hours group must carry its days: {f.hours}")
        self.assertRegex(first.get("days", "").lower(), r"thu",
                         f"first hours group must carry its days: {f.hours}")

    def test_several_day_groups_each_stated(self):
        page = ("Hours Monday-Thursday: 9 am – 8 pm Friday and Saturday: 9 am – 5 pm "
                "Sunday: Closed.")
        f = extract_visitor_facts_from_text(
            page, 'en', venue_name="Boston Athenaeum")
        # Two distinct day groups, each with its own time range.
        self.assertGreaterEqual(len(f.hours), 2,
                                f"each day group the page gives must be stated: {f.hours}")
        all_days = " ".join(h.get("days", "") for h in f.hours).lower()
        self.assertIn("mon", all_days)
        self.assertIn("fri", all_days)

    def test_formatted_hours_include_the_days(self):
        # format_en() must render the day range with the time range, never a bare
        # "Noon–4 PM" that reads as every day.
        page = ("Hours Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.")
        f = extract_visitor_facts_from_text(
            page, 'en', venue_name="Griffin Museum of Photography")
        out = f.format_en()
        self.assertRegex(out.lower(), r"tuesday.*sunday",
                         f"formatted hours must carry the day range: {out!r}")
        self.assertIn("4 PM", out)


# ── 2. Day-less hours are NOT stated as hours (misleading half-fact) ─────────

class TestNoDaylessHours(unittest.TestCase):
    """A time range with no bindable day group must NOT be emitted as the venue's
    hours — stating "9 AM–8 PM" with no day is the exact bounce. The composer
    points to the website instead."""

    def test_bare_time_with_no_day_is_not_bound_hours(self):
        # A lone time range with no weekday nearby (and no 'daily'): must not be
        # presented as the venue's day-bound hours.
        page = ("Our café serves lunch 11 am – 2 pm. Visit the shop for gifts.")
        f = extract_visitor_facts_from_text(
            page, 'en', venue_name="Some Museum")
        for h in f.hours:
            # If any hours slipped through, it must carry a day range — never a
            # day-less time masquerading as the week's hours.
            self.assertTrue(h.get("days", "").strip(),
                            f"day-less time must not be stated as hours: {f.hours}")


# ── 3. Composer: SPOKEN visiting sentences with source + month ───────────────

class TestSpokenVisitingComposition(unittest.TestCase):
    """The opening section's visiting information reads as speech, not a note:
    full sentences, the day range spoken with the hours, the admission categories
    the page gives, and the source + month honesty signal."""

    def _section(self, practical_facts):
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url="https://griffinmuseum.org",
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            requested_stops=7, available_exhibition_stops=7,
            fetcher=_griffin_fetcher,
            practical_facts=practical_facts,
            as_of="October 2026",
        )
        return am.build_opening_section(about)

    def test_reads_as_sentences_not_note_fragments(self):
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. Closed on Monday. "
            "$12 for adults, $8 for seniors, students and teachers")
        # The r3 note lead must be gone.
        self.assertNotIn("a few practical notes", section)
        # A spoken opening verb ("is open" / "opens") introduces the hours.
        self.assertRegex(section, r"(?i)\bis open\b|\bopens\b",
                         f"visiting info must read as a sentence: {section!r}")

    def test_day_range_spoken_with_hours(self):
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. Closed on Monday. $12 for adults")
        low = section.lower()
        self.assertIn("tuesday", low)
        self.assertIn("sunday", low)
        self.assertIn("4 pm", low)
        # The day range precedes the time in the spoken sentence.
        self.assertLess(low.index("tuesday"), low.index("4 pm"),
                        f"days must be spoken with (before) the hours: {section!r}")

    def test_source_and_month_present(self):
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. $12 for adults, $8 for seniors")
        self.assertIn("griffinmuseum.org", section)
        self.assertIn("October 2026", section)
        # The honesty signal reads naturally ("as listed on <domain> in <month>").
        self.assertRegex(section, r"(?i)as listed on griffinmuseum\.org in October 2026")

    def test_admission_categories_kept_never_invented(self):
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. "
            "$12 for adults, $8 for seniors, students and teachers")
        self.assertIn("$12", section)
        self.assertIn("$8", section)
        low = section.lower()
        for cat in ("adults", "seniors", "students", "teachers"):
            self.assertIn(cat, low, f"page-given category '{cat}' must be kept: {section!r}")
        # A category the page did NOT give must never be invented.
        self.assertNotIn("children", low)
        self.assertNotIn("military", low)

    def test_griffin_sentence_shape_end_to_end(self):
        # The LEAD's target shape (content, not exact wording): open <days>, <time>,
        # closed <day>; admission <price> for <cats>, as listed on <domain> in <month>.
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. Closed on Monday. "
            "$12 for adults, $8 for seniors, students and teachers")
        low = section.lower()
        i_open = re.search(r"(?i)is open|opens", section).start()
        i_days = low.index("tuesday")
        i_time = low.index("4 pm")
        i_closed = low.index("closed")
        i_adm = section.index("$12")
        # The source signal we mean is the visiting one ("as listed on <domain>
        # in <month>") — not the About narration's own sourcing close, which may
        # also name the domain earlier. Anchor on the dated signal.
        m_src = re.search(r"(?i)as listed on griffinmuseum\.org in October 2026", section)
        self.assertIsNotNone(m_src, f"visiting source signal missing: {section!r}")
        i_src = m_src.start()
        # open → days → time all in the hours sentence; closed stated; then
        # admission; then the dated source signal last.
        self.assertLess(i_open, i_days)
        self.assertLess(i_days, i_time)
        self.assertLess(i_time, i_adm)
        self.assertLess(i_closed, i_adm)
        self.assertLess(i_adm, i_src)

    def test_no_pointer_when_both_known(self):
        # Full facts → no "check the website" pointer (r3 contract preserved).
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. Closed on Monday. $12 for adults")
        self.assertNotRegex(section, r"(?i)check .*before you go")


# ── 4. Athenaeum spoken shape with its OWN day groups ────────────────────────

class TestAthenaeumSpokenDayGroups(unittest.TestCase):
    """The Athenaeum lists several day groups; the spoken sentence states each
    group's days with its times — never a single day-less range."""

    def _section(self, practical_facts):
        about = am.build_about_stop(
            venue_name="Boston Athenaeum",
            base_site_url="https://bostonathenaeum.org",
            request_text="Art and Architectual tour in Boston Athenaeum",
            locality="Boston, MA",
            requested_stops=5, available_exhibition_stops=5,
            fetcher=_athenaeum_fetcher,
            practical_facts=practical_facts,
            as_of="October 2026",
        )
        return am.build_opening_section(about)

    def test_each_day_group_spoken(self):
        section = self._section(
            "Open Monday to Thursday, 9 AM–8 PM; Friday and Saturday, 9 AM–5 PM. "
            "Closed on Sunday. Admission is free")
        low = section.lower()
        self.assertIn("monday", low)
        self.assertIn("thursday", low)
        self.assertIn("friday", low)
        self.assertIn("8 pm", low)
        self.assertIn("5 pm", low)
        # Source + month honesty signal present.
        self.assertIn("bostonathenaeum.org", section)
        self.assertIn("October 2026", section)

    def test_free_admission_spoken_without_invented_price(self):
        section = self._section(
            "Open Monday to Thursday, 9 AM–8 PM. Closed on Sunday. Admission is free")
        self.assertRegex(section, r"(?i)admission is free|free admission|free to")
        self.assertNotRegex(section, r"\$\d")   # no fabricated price
        self.assertNotIn("€", section)


# ── Fixtures (match the LOCAL-592 suite) ─────────────────────────────────────

_GRIFFIN_ABOUT_HTML = (
    "<html><body>"
    "<h1>About the Griffin Museum of Photography</h1>"
    "<p>The Griffin Museum of Photography was founded in 1992 by the photographer "
    "Arthur Griffin.</p>"
    "<h2>Hours</h2><p>Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.</p>"
    "<h2>Admission</h2><p>General Admission: $12 for adults.</p>"
    "</body></html>"
)


def _griffin_fetcher(url):
    u = url.rstrip("/")
    if (u.endswith("about") or u.endswith("about-us") or u.endswith("about-the-museum")
            or u.endswith("history") or u.endswith("mission")
            or u.endswith("your-support-matters") or u.endswith("visit")
            or u.endswith("plan-your-visit") or u == "https://griffinmuseum.org"):
        return _GRIFFIN_ABOUT_HTML, []
    return "", []


_ATHENAEUM_HTML = (
    "<html><body>"
    "<h1>About the Boston Athenaeum</h1>"
    "<p>The Boston Athenaeum, founded in 1807, is one of the oldest independent "
    "libraries in the United States. Its landmark building was designed by the "
    "architect Edward Clarke Cabot.</p>"
    "<h2>Hours</h2><p>Monday through Saturday: 9 AM to 5 PM. Closed: Sunday.</p>"
    "<h2>Admission</h2><p>Admission is free to the first floor.</p>"
    "</body></html>"
)


def _athenaeum_fetcher(url):
    u = url.rstrip("/")
    if (u.endswith("about") or u.endswith("about-us") or u.endswith("the-building")
            or u.endswith("architecture") or u.endswith("history")
            or u.endswith("visit") or u.endswith("plan-your-visit")
            or u == "https://bostonathenaeum.org"):
        return _ATHENAEUM_HTML, []
    return "", []


if __name__ == "__main__":
    unittest.main(verbosity=2)
