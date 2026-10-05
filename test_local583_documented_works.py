#!/usr/bin/env python3
"""test_local583_documented_works.py — Deliverable 1 (LOCAL-583).

Site-derived (canonical) titles are NOT documented works.

The Griffin field defect (Michael, 2026-10-05, job 797a637d): an earlier run
wrote 23 SITE-CHROME titles into venue_corpus as "canonical titles". The next
run read them from cache and LOCAL-30's deterministic selection counted all 23
as "documented works" (0 catalogue, 0 SPARQL) → DETERMINISTIC BYPASS fired on
chrome, and because len(_det_documented) != 0 the LOCAL-580 site-first path was
never eligible.

The rule under test (both deterministic blocks in generate_tour_text.py):
  * "documented" counts ONLY source in {catalogue, sparql}
  * canonical titles neither trigger the deterministic bypass nor block the
    LOCAL-580 site-first eligibility (which requires 0 documented works).

Run: python3 -m pytest test_local583_documented_works.py -q
"""
import unittest


# The exact 23 chrome titles LEAD backed up from venue_corpus Q99108607.
GRIFFIN_CACHED_CHROME = [
    "Calls For Entry", "Griffin Travel", "Exhibition Closed", "Membership Levels",
    "When Are The Member Portfolio Reviews Scheduled", "Our Team",
    "Terms Conditions", "Nepr 2026", "Function Rentals",
    "Bu Masters Show 2026 Traces Pursuing Process", "Intertidal Field Notes",
    "State Of Our Union 2026", "Portfolio Development", "Leave A Legacy",
    "Exhibition Archive", "Griffin Museum Board Of Directors 2", "Members Bulletin",
    "Membership Account", "Earth Wind Fire", "Griffin Salon",
    "Arthur Griffin Archive", "Your Support Matters", "Lua Kobayashi",
]


def documented_count(det_documented):
    """Mirror of the LOCAL-583 D1 rule in generate_tour_text.py."""
    return sum(1 for d in det_documented if d.get('source') in ('catalogue', 'sparql'))


class TestDocumentedCount(unittest.TestCase):
    def test_canonical_only_counts_zero(self):
        """23 cached chrome 'canonical' titles → 0 documented works."""
        det = [{'title': t, 'source': 'canonical'} for t in GRIFFIN_CACHED_CHROME]
        self.assertEqual(0, documented_count(det))

    def test_canonical_does_not_trigger_bypass(self):
        """With 0 documented works, the deterministic bypass (>= total_stops)
        must NOT fire even though there are 23 canonical titles."""
        det = [{'title': t, 'source': 'canonical'} for t in GRIFFIN_CACHED_CHROME]
        total_stops = 5
        self.assertFalse(documented_count(det) >= total_stops)

    def test_canonical_does_not_block_site_first(self):
        """Site-first eligibility requires documented_count == 0. Canonical
        titles must not raise that count above 0."""
        det = [{'title': t, 'source': 'canonical'} for t in GRIFFIN_CACHED_CHROME]
        _site_first_eligible = (documented_count(det) == 0)
        self.assertTrue(_site_first_eligible)

    def test_catalogue_and_sparql_still_count(self):
        """Real catalogue + SPARQL works are still documented and still bypass."""
        det = (
            [{'title': f'Cat {i}', 'source': 'catalogue'} for i in range(3)] +
            [{'title': f'Spa {i}', 'source': 'sparql'} for i in range(2)] +
            [{'title': t, 'source': 'canonical'} for t in GRIFFIN_CACHED_CHROME]
        )
        total_stops = 5
        self.assertEqual(5, documented_count(det))
        self.assertTrue(documented_count(det) >= total_stops)
        # 0 documented would be false here, so site-first NOT eligible — correct.
        self.assertFalse(documented_count(det) == 0)

    def test_mixed_below_threshold_no_bypass(self):
        """2 documented + many canonical, 5 stops → no bypass (2 < 5)."""
        det = (
            [{'title': 'Cat A', 'source': 'catalogue'},
             {'title': 'Spa B', 'source': 'sparql'}] +
            [{'title': t, 'source': 'canonical'} for t in GRIFFIN_CACHED_CHROME]
        )
        total_stops = 5
        self.assertEqual(2, documented_count(det))
        self.assertFalse(documented_count(det) >= total_stops)
        # But also NOT site-first eligible (there ARE documented works).
        self.assertFalse(documented_count(det) == 0)


class TestSourceWiring(unittest.TestCase):
    """Prove the rule is actually wired into generate_tour_text.py, not only
    mirrored in this test. Both deterministic gates must key on the documented
    (catalogue+SPARQL) count, and site-first eligibility must do the same."""

    @classmethod
    def setUpClass(cls):
        import os
        _here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(_here, 'generate_tour_text.py'), encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_documented_count_defined(self):
        self.assertIn("_det_documented_count = sum(", self.src)
        self.assertIn("if d.get('source') in ('catalogue', 'sparql')", self.src)

    def test_bypass_uses_documented_count(self):
        self.assertIn("if _det_documented_count >= total_stops:", self.src)

    def test_site_first_eligibility_uses_documented_count(self):
        self.assertIn("if _det_documented_count == 0:", self.src)

    def test_old_len_gates_removed(self):
        # The buggy gates that counted canonical titles must be gone.
        self.assertNotIn("if len(_det_documented) == 0:", self.src)
        self.assertNotIn("if len(_det_documented) >= total_stops:", self.src)


if __name__ == '__main__':
    unittest.main(verbosity=2)