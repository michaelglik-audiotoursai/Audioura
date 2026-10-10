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


class TestSearchBeforeDelete(unittest.TestCase):
    """Michael, 2026-09-20: *"omitting the fact should not be a substitution for us
    searching for a cause or circumstances."* Deletion is the fallback."""

    S = ("In June 2023 tragedy struck with the murder of Bruno D'Amore and Lucia "
         "Arpino. The narthex hosted a Mass of Peace.")

    def test_documented_circumstances_are_recovered_and_spliced_in(self):
        from tragedy_context_gate import resolve_uncontextualised_deaths as res
        def grounded(_p):
            return ("They were killed during a burglary at their home; a suspect "
                    "was arrested and later convicted."), ["https://example.org/news"]
        text, recovered, removed = res(self.S, "Narthex", "Newton MA", grounded)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(removed, [])
        self.assertIn("D'Amore", text, "the naming stays once it has circumstances")
        self.assertIn("burglary", text, "the circumstances are spliced in after it")

    def test_not_documented_falls_back_to_deletion(self):
        from tragedy_context_gate import resolve_uncontextualised_deaths as res
        text, recovered, removed = res(self.S, "", "", lambda p: ("NOT DOCUMENTED", ["x"]))
        self.assertEqual(recovered, [])
        self.assertTrue(removed)
        self.assertNotIn("D'Amore", text)

    def test_UNSOURCED_SPECULATION_IS_NEVER_PUBLISHED(self):
        """The worst failure available to this pipeline: a motive invented for a
        real murder. No sources means not found, whatever the model said."""
        from tragedy_context_gate import resolve_uncontextualised_deaths as res
        def speculating(_p):
            return "They were likely targeted because of their background.", []
        text, recovered, removed = res(self.S, "", "", speculating)
        self.assertEqual(recovered, [], "an unsourced motive must never be recovered")
        self.assertTrue(removed)
        self.assertNotIn("targeted because", text)

    def test_the_query_forbids_speculation_and_offers_an_out(self):
        from tragedy_context_gate import circumstances_query
        q = circumstances_query(self.S, "Narthex", "Newton MA")
        self.assertRegex(q, r'(?i)(do not|never)\s+speculate')
        self.assertRegex(q, r'(?i)do not use headings')   # narration, not a report
        self.assertIn("NOT DOCUMENTED", q)
        self.assertIn("Cite your sources", q)

    def test_no_grounded_client_means_the_old_behaviour(self):
        from tragedy_context_gate import resolve_uncontextualised_deaths as res
        text, recovered, removed = res(self.S, "", "", None)
        self.assertEqual(recovered, [])
        self.assertTrue(removed)


class TestVictimNameBackfillIsPeopleOnly(unittest.TestCase):
    """[LOCAL-663] "The victims were Boston Massacre." survived LOCAL-660.

    The producer is NOT the degrade path (where LOCAL-660's entity-gated copula
    guard runs) — it is this gate's `_as_narration`. When recovered circumstances
    drop a victim surname it back-fills "...The victims were <names>.", and the
    names came from a bare two-capitalised-token regex (`_NAME_IN`) with no
    filtering, which matched the EVENT ("Boston Massacre") and a DATE FRAGMENT
    ("On March") as victims. The fix filters to real person names and emits NO
    sentence when none remain.
    """

    # The exact death sentence from tour 557 Stop 5 (Boston Massacre), where
    # five colonists are named and the event is "the Boston Massacre".
    MASSACRE = ("On March 5, 1770, British soldiers fired into a crowd on King "
                "Street in the Boston Massacre.")

    def test_event_name_is_not_a_victim(self):
        import tragedy_context_gate as g
        self.assertNotIn("Boston Massacre", g._victim_names(self.MASSACRE))

    def test_date_fragment_is_not_a_victim(self):
        import tragedy_context_gate as g
        self.assertNotIn("On March", g._victim_names(self.MASSACRE))

    def test_no_victims_copula_when_no_real_names(self):
        """The red state: recovered prose that omits the event word must NOT
        be force-fed "The victims were Boston Massacre."."""
        import tragedy_context_gate as g
        recovered = ("British troops opened fire on a hostile crowd, killing "
                     "five men on King Street.")
        out = g._as_narration(recovered, g._victim_names(self.MASSACRE))
        self.assertNotIn("The victims were", out)
        self.assertNotIn("Boston Massacre", out)
        self.assertNotIn("On March", out)

    def test_as_narration_backstops_an_unfiltered_name_list(self):
        """Even if a caller passes raw `_NAME_IN` matches, the backfill still
        drops the event and the date fragment."""
        import tragedy_context_gate as g
        raw = g._NAME_IN.findall(self.MASSACRE)      # ['On March', 'Boston Massacre']
        self.assertIn("Boston Massacre", raw)         # the unfiltered input really has it
        out = g._as_narration("Soldiers fired into the crowd on King Street.", raw)
        self.assertNotIn("The victims were", out)

    def test_real_people_are_still_named(self):
        """D577 narrow exception must still work: when the recovered prose drops
        a real victim's surname, it is restored."""
        import tragedy_context_gate as g
        sent = ("Tragedy struck with the murder of Bruno D'Amore, "
                "Gilda 'Jill' D'Amore, and Lucia Arpino.")
        names = g._victim_names(sent)
        self.assertIn("Bruno D'Amore", names)
        self.assertIn("Lucia Arpino", names)
        out = g._as_narration("They were killed during a burglary at home.", names)
        self.assertIn("The victims were", out)
        self.assertIn("Arpino", out)

    def test_full_recover_path_never_emits_event_as_victim(self):
        """End-to-end through resolve_uncontextualised_deaths with a grounded
        answer that omits the event word — the spliced circumstances must carry
        no "The victims were Boston Massacre." sentence."""
        from tragedy_context_gate import resolve_uncontextualised_deaths as res
        text = (self.MASSACRE + " It became a rallying cry for the colonists.")

        def grounded(_p):
            return ("Soldiers of the 29th Regiment fired into a crowd on King "
                    "Street; the soldiers were later tried and most acquitted."), \
                   ["https://example.org/boston-massacre"]

        out, recovered, removed = res(text, "Old State House", "Boston MA", grounded)
        self.assertNotIn("The victims were", out)
        self.assertNotIn("were Boston Massacre", out)
