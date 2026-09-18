"""A named violent death must carry its circumstances, or it does not ship."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tragedy_context_gate import (find_uncontextualised_deaths,
                                  strip_uncontextualised_deaths)

SHIPPED = ("Fast forward to June 2023, when tragedy struck the community with the "
           "murder of Bruno D'Amore, Gilda 'Jill' D'Amore, and Lucia Arpino. The "
           "narthex once again became a focal point for the community, hosting a "
           "'Mass of Peace' attended by hundreds. The church was completed in 1881.")


class TestTheSentenceThatShipped(unittest.TestCase):
    def test_it_is_flagged(self):
        flagged = find_uncontextualised_deaths(SHIPPED)
        self.assertEqual(len(flagged), 1, flagged)
        self.assertIn("D'Amore", flagged[0])

    def test_the_naming_and_its_orphan_both_go(self):
        clean, removed = strip_uncontextualised_deaths(SHIPPED)
        self.assertEqual(len(removed), 2, removed)
        self.assertNotIn("D'Amore", clean)
        self.assertNotIn("once again", clean,
                         "the consequence must fall with the naming it depended on")
        self.assertIn("completed in 1881", clean, "unrelated material must survive")


class TestItDoesNotOverreach(unittest.TestCase):
    """D577: we ship what we cannot verify. This narrow exception is only for a
    named death with no account of what happened."""

    def test_a_death_WITH_circumstances_ships(self):
        t = ("In June 2023 Bruno D'Amore was murdered during a burglary at his home; "
             "a suspect was arrested that week. The narthex hosted a Mass of Peace.")
        self.assertEqual(find_uncontextualised_deaths(t), [])

    def test_a_motive_counts_as_circumstances(self):
        t = ("Thomas Becket was murdered in the cathedral because he had defied "
             "the king. Pilgrims came for centuries.")
        self.assertEqual(find_uncontextualised_deaths(t), [])

    def test_an_unnamed_death_is_not_flagged(self):
        t = "Two workers were killed during construction. The tower was finished in 1931."
        self.assertEqual(find_uncontextualised_deaths(t), [])

    def test_ordinary_prose_is_untouched(self):
        t = ("The nave was completed in 1881 by Irish immigrant workers. Mother "
             "Teresa visited in 1995 and hundreds came.")
        clean, removed = strip_uncontextualised_deaths(t)
        self.assertEqual(removed, [])
        self.assertEqual(clean, t)


class TestItCanFail(unittest.TestCase):
    def test_removing_the_death_pattern_lets_it_through(self):
        import tragedy_context_gate as g
        saved = g._DEATH
        try:
            g._DEATH = __import__('re').compile(r'zzz-never-matches')
            self.assertEqual(find_uncontextualised_deaths(SHIPPED), [],
                             "with the detector disabled the passage must pass "
                             "through — the red state")
        finally:
            g._DEATH = saved
        self.assertEqual(len(find_uncontextualised_deaths(SHIPPED)), 1)


if __name__ == '__main__':
    unittest.main()
