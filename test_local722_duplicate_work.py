"""test_local722_duplicate_work.py — LOCAL-722: the same work must not ship twice.

The defect: fresh 6-stop "Courtauld Gallery, London" museum tours were refused
with error / factual_integrity because D3(e) fired — the SAME work was delivered
as two stops though the LOCAL-212 Selected list held it once.

Two shapes of the duplicate, both proven here to MERGE:
  * "A Bar at the Folies-Bergère" vs "A Bar at the Folies-Bergère." (trailing period)
  * "Landscape with the Flight into Egypt" delivered twice verbatim (different label
    is simulated below by a curly-quote / accent variant)

And the guard against over-merging — two genuinely DIFFERENT works that must NEVER
collapse:
  * "Self-Portrait" vs "Self-Portrait with Bandaged Ear"

Plus the behaviour: dedupe_delivered_stops drops the later block, renumbers, is
idempotent; and the shared normalisation equals story_miner._normalize so the
guard and the D3(e) check can never drift.

Run:  python3 -m pytest test_local722_duplicate_work.py -q
"""
import re
import unittest

import stop_title_dedup as std


# ── 1. The normalisation: the two pairs merge, the distinct works do not ──────
class TestNormalisationMergesSameWork(unittest.TestCase):
    def _same(self, a, b):
        self.assertEqual(std.normalize_stop_title(a), std.normalize_stop_title(b),
                         f"expected SAME normal: {a!r} vs {b!r}")

    def _diff(self, a, b):
        self.assertNotEqual(std.normalize_stop_title(a), std.normalize_stop_title(b),
                            f"expected DIFFERENT normal: {a!r} vs {b!r}")

    def test_trailing_period_merges(self):
        # LEAD's Sonnet run
        self._same("A Bar at the Folies-Bergère", "A Bar at the Folies-Bergère.")

    def test_curly_quotes_and_accent_merge(self):
        # Same work, cosmetic label differences only.
        self._same("Landscape with the Flight into Egypt",
                   "Landscape with the Flight into Egypt")  # identical verbatim repeat
        self._same('“A Bar at the Folies-Bergère”', "A Bar at the Folies-Bergere")
        self._same("Résurrection", "Resurrection")

    def test_hyphen_and_space_equivalent(self):
        self._same("Self-Portrait", "Self Portrait")

    def test_different_works_do_not_merge(self):
        # The guard against over-merging — the ticket's explicit negative case.
        self._diff("Self-Portrait", "Self-Portrait with Bandaged Ear")

    def test_two_other_distinct_courtauld_works_do_not_merge(self):
        self._diff("A Bar at the Folies-Bergère", "Ambroise Vollard")
        self._diff("Christ and the Woman Taken in Adultery",
                   "Footed Bowl with the Crucifixion")


# ── 2. Shared normalisation is the SAME as story_miner._normalize (no drift) ──
class TestNormalisationMatchesStoryMiner(unittest.TestCase):
    def test_equal_to_story_miner_normalize(self):
        from story_miner import _normalize as sm_norm
        for t in [
            "A Bar at the Folies-Bergère.",
            "Self-Portrait with Bandaged Ear",
            "Landscape with the Flight into Egypt",
            "Résurrection",
            '“Quoted Title”',
            "Christ and the Woman Taken in Adultery",
        ]:
            self.assertEqual(std.normalize_stop_title(t), sm_norm(t),
                             f"drift from story_miner._normalize on {t!r}")


# ── 3. find_duplicate_stop_titles reports the right pairs ─────────────────────
class TestFindDuplicates(unittest.TestCase):
    def test_trailing_period_pair_found(self):
        dups = std.find_duplicate_stop_titles(
            ["A Bar at the Folies-Bergère", "A Bar at the Folies-Bergère."])
        self.assertEqual(dups, [("A Bar at the Folies-Bergère.",
                                 "A Bar at the Folies-Bergère")])

    def test_verbatim_repeat_found(self):
        dups = std.find_duplicate_stop_titles(
            ["Landscape with the Flight into Egypt", "Ambroise Vollard",
             "Landscape with the Flight into Egypt"])
        self.assertEqual(dups, [("Landscape with the Flight into Egypt",
                                 "Landscape with the Flight into Egypt")])

    def test_distinct_works_report_no_duplicate(self):
        dups = std.find_duplicate_stop_titles(
            ["Self-Portrait", "Self-Portrait with Bandaged Ear"])
        self.assertEqual(dups, [])

    def test_six_distinct_courtauld_works_no_duplicate(self):
        dups = std.find_duplicate_stop_titles([
            "Self-Portrait with Bandaged Ear",
            "Christ and the Woman Taken in Adultery",
            "Footed Bowl with the Crucifixion",
            "Ambroise Vollard",
            "A Bar at the Folies-Bergère",
            "Landscape with the Flight into Egypt",
        ])
        self.assertEqual(dups, [])


# ── 4. dedupe_delivered_stops: drop later block, renumber, idempotent ─────────
_TOUR_WITH_DUP = """Step-by-step audio guided tour of the Courtauld Gallery, London.

Stop 1: Self-Portrait with Bandaged Ear

Address: Somerset House, Strand, London

Coordinates: 51.5110, -0.1170

Orientation: Stand before the self-portrait.

Van Gogh painted this in 1889.

Directions: Next is A Bar at the Folies-Bergère.

Stop 2: A Bar at the Folies-Bergère

Address: Somerset House, Strand, London

Coordinates: 51.5110, -0.1170

Orientation: Stand before Manet's bar scene.

Manet painted this in 1882.

Directions: Next is the same work again.

Stop 3: A Bar at the Folies-Bergère.

Address: Somerset House, Strand, London

Coordinates: 51.5110, -0.1170

Orientation: The duplicate that must be dropped.

The same Manet painting, delivered twice.

Directions: Next is Ambroise Vollard.

Stop 4: Ambroise Vollard

Address: Somerset House, Strand, London

Coordinates: 51.5110, -0.1170

Orientation: Stand before the portrait of the dealer.

Cézanne painted this around 1899.

That's 4 stops in all.

Sources: courtauld.ac.uk
"""


class TestDedupeDeliveredStops(unittest.TestCase):
    def test_drops_the_duplicate_block(self):
        new, dropped = std.dedupe_delivered_stops(_TOUR_WITH_DUP)
        self.assertEqual(dropped,
                         [("A Bar at the Folies-Bergère.", "A Bar at the Folies-Bergère")])
        # The duplicate's unique body sentence is gone; the first copy's survives.
        self.assertNotIn("delivered twice", new)
        self.assertIn("Manet painted this in 1882.", new)

    def test_renumbers_survivors_1_to_k(self):
        new, _ = std.dedupe_delivered_stops(_TOUR_WITH_DUP)
        headers = re.findall(r'^Stop\s+(\d+):\s*(.+)$', new, re.MULTILINE)
        self.assertEqual([h[0] for h in headers], ["1", "2", "3"])
        self.assertEqual(
            [h[1].strip() for h in headers],
            ["Self-Portrait with Bandaged Ear",
             "A Bar at the Folies-Bergère",
             "Ambroise Vollard"])

    def test_idempotent(self):
        once, d1 = std.dedupe_delivered_stops(_TOUR_WITH_DUP)
        twice, d2 = std.dedupe_delivered_stops(once)
        self.assertEqual(d2, [])
        self.assertEqual(twice, once)

    def test_no_duplicate_is_a_noop(self):
        clean = _TOUR_WITH_DUP.replace(
            "Stop 3: A Bar at the Folies-Bergère.",
            "Stop 3: Landscape with the Flight into Egypt")
        new, dropped = std.dedupe_delivered_stops(clean)
        self.assertEqual(dropped, [])
        self.assertEqual(new, clean)

    def test_distinct_self_portraits_not_merged(self):
        # Two different works whose titles share a prefix must BOTH survive.
        t = _TOUR_WITH_DUP.replace(
            "Stop 3: A Bar at the Folies-Bergère.",
            "Stop 3: Self-Portrait")
        new, dropped = std.dedupe_delivered_stops(t)
        self.assertEqual(dropped, [])
        headers = re.findall(r'^Stop\s+\d+:\s*(.+)$', new, re.MULTILINE)
        self.assertIn("Self-Portrait", [h.strip() for h in headers])
        self.assertIn("Self-Portrait with Bandaged Ear", [h.strip() for h in headers])


# ── 5. D3(e) in the QA runner uses the shared helper and exposes the pairs ────
class TestQADuplicateCheckExposesPairs(unittest.TestCase):
    def test_d3e_populates_duplicate_stop_titles(self):
        import content_qa_runner as q
        try:
            q.run_qa(_TOUR_WITH_DUP, story_elements=None, venue_context=None)
        except SystemExit:
            pass
        self.assertEqual(
            list(q.DUPLICATE_STOP_TITLES),
            [("A Bar at the Folies-Bergère.", "A Bar at the Folies-Bergère")])
        self.assertGreaterEqual(q.FACTUAL_FAIL_COUNT, 1)

    def test_d3e_clean_tour_no_duplicate(self):
        import content_qa_runner as q
        clean = _TOUR_WITH_DUP.replace(
            "Stop 3: A Bar at the Folies-Bergère.",
            "Stop 3: Landscape with the Flight into Egypt")
        try:
            q.run_qa(clean, story_elements=None, venue_context=None)
        except SystemExit:
            pass
        self.assertEqual(list(q.DUPLICATE_STOP_TITLES), [])


# ── 6. replenish_to_count rejects a same-work candidate (trailing period) ─────
class TestReplenishRejectsSameWork(unittest.TestCase):
    def test_trailing_period_candidate_rejected(self):
        import generate_tour_text as gtt
        poi_list = [{"name": "A Bar at the Folies-Bergère"}]

        def propose(need, seen_names):
            # Proposer offers the SAME work with a trailing period, plus a new one.
            return [{"name": "A Bar at the Folies-Bergère.", "why": "dup"},
                    {"name": "Ambroise Vollard", "why": "new"}]

        def make_poi(name):
            return {"name": name}

        added, rejected, rounds = gtt.replenish_to_count(
            poi_list, want=2, scope="", headers={}, propose=propose,
            make_poi=make_poi, max_rounds=1)
        names = [p["name"] for p in poi_list]
        self.assertIn("Ambroise Vollard", names)
        self.assertNotIn("A Bar at the Folies-Bergère.", names)
        # Only ONE copy of the Manet work ever present.
        self.assertEqual(
            sum(1 for n in names
                if std.normalize_stop_title(n) == std.normalize_stop_title(
                    "A Bar at the Folies-Bergère")),
            1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
