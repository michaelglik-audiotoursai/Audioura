r"""
LOCAL-614 item 3 — the About selector rejects academic-program / admissions /
course / catalog boilerplate; a kept sentence must be about the MUSEUM.
=========================================================================
The kiro-cli critique of McMullen tour 399 found a Boston College degree-program
page scraped into the About section:

    "Grounded in Boston College's renowned liberal arts tradition, the history
     major offers a robust grounding in the contemporary practice of history
     that will prepare you to address the challenges of the present."

That is a university HISTORY-MAJOR page, not the museum's story — yet it carries
a story verb ("offers") and a signal word ("history"), so the LOCAL-599C/602 r2
selector lifted it. The About-text selector (``about_museum_stop._is_story_sentence``)
must reject academic-program, admissions, course and catalog boilerplate.

These tests CALL the real selector (D418/D421). RED on base (the degree-program
sentence is accepted), GREEN after.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import about_museum_stop as am


VENUE = "McMullen Museum of Art"
_vc = am._venue_core(VENUE)
_vf = _vc.split()[0] if _vc else ""


# Academic-program / admissions / course / catalog boilerplate — NOT the museum's
# story. Each is a real shape from a college site.
ACADEMIC_BOILERPLATE = [
    ("Grounded in Boston College's renowned liberal arts tradition, the history "
     "major offers a robust grounding in the contemporary practice of history "
     "that will prepare you to address the challenges of the present."),
    ("The history major offers a robust grounding in the contemporary practice "
     "of history."),
    ("The art history minor requires the completion of six courses, including "
     "two seminars."),
    ("Undergraduate applicants must submit transcripts, and admission to the "
     "program is highly selective."),
    ("This course introduces students to the fundamentals of medieval art and "
     "its historical context."),
    ("Students who major in studio art complete a capstone thesis in their "
     "senior year."),
    ("The department offers graduate degrees including the M.A. and Ph.D. in "
     "art history."),
]

# Genuine museum-identity sentences that MUST still be accepted.
MUSEUM_STORY = [
    ("The McMullen Museum of Art is the university art museum of Boston College "
     "in Brighton, Massachusetts."),
    ("Founded in 1993, the McMullen Museum of Art presents scholarly exhibitions "
     "drawn from many cultures and periods."),
]


class TestRejectAcademicBoilerplate(unittest.TestCase):
    def test_academic_program_sentences_rejected(self):
        for s in ACADEMIC_BOILERPLATE:
            self.assertFalse(
                am._is_story_sentence(s, _vc, _vf),
                f"academic/admissions/course boilerplate accepted: {s[:60]!r}")

    def test_museum_identity_still_accepted(self):
        for s in MUSEUM_STORY:
            self.assertTrue(
                am._is_story_sentence(s, _vc, _vf),
                f"museum story wrongly rejected: {s[:60]!r}")


class TestCollectDropsAcademicBoilerplate(unittest.TestCase):
    """End-to-end over the collector: the degree-program line is not lifted, the
    museum identity sentence is."""

    def test_collector_prefers_museum_over_degree_program(self):
        corpus = (
            "Grounded in Boston College's renowned liberal arts tradition, the "
            "history major offers a robust grounding in the contemporary practice "
            "of history that will prepare you to address the challenges of the "
            "present. The McMullen Museum of Art is the university art museum of "
            "Boston College in Brighton, Massachusetts. Founded in 1993, the "
            "McMullen Museum of Art presents scholarly exhibitions drawn from many "
            "cultures and periods.")
        picked = am._collect_story_sentences(corpus, VENUE, limit=4)
        joined = " ".join(picked)
        self.assertNotIn("history major offers", joined)
        self.assertTrue(any("university art museum of Boston College" in p
                            for p in picked),
                        f"museum identity not lifted: {picked}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
