#!/usr/bin/env python3
"""test_local589_fill_the_count.py — LOCAL-589 Deliverable 4.

Fill the count from REAL exhibitions.

Field case: Griffin has 9 real current shows; a 7-stop request must deliver 7.
When one selected show's narration later comes back empty, the LOCAL-292 gate
removes it. Without headroom the tour ships 6. The site-first path carries a
small narration HEADROOM of REAL extra exhibitions so a single empty-narration
drop still leaves the requested count, and the tour is trimmed back to EXACTLY
the request afterwards. Nothing is invented; non-site paths are untouched.

Tested via the pure cap helper (the behaviour was observed live: run 1 delivered
6/7 on an empty-narration drop; the headroom covers exactly that case).

Run: python3 -m pytest test_local589_fill_the_count.py -q
"""
import inspect
import unittest

import generate_tour_text as g


class TestSiteFillCap(unittest.TestCase):
    def test_site_path_gets_one_spare_when_extra_shows_exist(self):
        # 9 real shows, 7 requested -> carry 8 through narration (1 spare).
        self.assertEqual(8, g._site_fill_effective_cap('site_exhibition', 9, 7))

    def test_spare_bounded_by_available_shows(self):
        # Only 7 shows for a 7-stop request -> no spare possible.
        self.assertEqual(7, g._site_fill_effective_cap('site_exhibition', 7, 7))
        # 8 shows, 7 requested -> 1 spare available.
        self.assertEqual(8, g._site_fill_effective_cap('site_exhibition', 8, 7))

    def test_non_site_paths_keep_plain_cap(self):
        for src in ('checklist', 'partial', 'prose_llm', 'creator_filter', 'none'):
            self.assertEqual(
                7, g._site_fill_effective_cap(src, 9, 7),
                f"path '{src}' must not take site-fill headroom"
            )

    def test_headroom_never_exceeds_requested_plus_one(self):
        # Even with many extra shows, default headroom is a single spare.
        self.assertEqual(8, g._site_fill_effective_cap('site_exhibition', 20, 7))


class TestTrimBackToRequest(unittest.TestCase):
    """Source-level guard: whatever headroom was carried, the site path is
    trimmed back to the listener's ask after the LOCAL-292 empty-stop gate, and
    the LOCAL-394 invariant counter is re-based to the request so a consumed
    spare is not mis-reported as a lost stop."""

    def _fn_src(self):
        return inspect.getsource(getattr(g, '_generate_tour_text_impl', g.generate_tour_text))  # LOCAL-562 wrapper on subscribed (LEAD)

    def test_trims_back_to_requested_after_gate(self):
        src = self._fn_src()
        self.assertIn("site-first headroom trimmed", src)
        self.assertIn("poi_list[:_requested_stop_count_original]", src)

    def test_rebases_invariant_counter(self):
        src = self._fn_src()
        self.assertIn("_l292_requested_stops = _requested_stop_count_original", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
