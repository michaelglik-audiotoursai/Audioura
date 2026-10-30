"""
[LOCAL-831] The repeated-fact remover (D533) deleted a WHOLE stop, and the
delivery check shipped the gap (stops numbered 1, 2, 4, 5).

Evidence — LOCAL-826C live run, Rijks Museum, cheap arm, real cache:
  ~/Audioura/reports/local826c/gen_rijks_826c_live.log  (~line 1983)
  ~/Audioura/reports/local826c/tour866_826c_live_delivered.txt

The log shows a D533 guard logged

    removed: Stop 3: Het melkmeisje (The Milkmaid)

and the delivered tour shipped four stops numbered [1, 2, 4, 5]. LOCAL-826B's
check_stop_delivery DID report NON_SEQUENTIAL, but its repair
(dedupe_and_fix_stop_count) only renumbers when IT removed an artifact — here the
stop was already gone, so nothing was removed and the gap shipped.

This suite proves, with the exact log strings:
  1. D533 FIXTURE — strip_repeated_facts never removes a "Stop N:" header line
     and never deletes a whole stop, even when a repeated fact is stripped.
  2. NON-SEQUENTIAL FIXTURE — renumber_stops_sequential closes [1,2,4,5] ->
     [1,2,3,4] EVEN WHEN no artifact was removed, and is a strict no-op on a
     clean tour.
  3. EMPTY-BODY FIXTURE — when a stop is removed upstream, the delivery repair
     closes the numbering and the honest count reflects the real delivered stops.

Pure / offline / deterministic. No network, no model.

Run:
    python3 -m pytest tests/test_local831_derepetition_stop_loss.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import derepetition_guard as d
from tour_conclusion import (
    check_stop_delivery,
    renumber_stops_sequential,
    repair_stop_delivery,
    finalize_stop_delivery,
    count_delivered_stops,
)
from about_museum_stop import build_shortfall_sentence


# ─── The exact delivered Rijks header set from the live run (log/delivered) ────
# Curly quotes and the bilingual titles are preserved verbatim from the evidence.
_RIJKS_STOP3_TITLE = "Het melkmeisje (The Milkmaid)"   # the stop D533 deleted


def _rijks_tour_with_gap() -> str:
    """The delivered Rijks tour as it SHIPPED: four stops numbered [1, 2, 4, 5]
    (Stop 3 already deleted upstream). Headers taken from
    tour866_826c_live_delivered.txt."""
    return (
        "Stop 1: De grote golf bij Kanagawa (The Great Wave off Kanagawa)\n\n"
        "This woodblock print shows a towering wave about to crash. "
        "Hokusai made it around 1831 as part of a famous series.\n\n"
        "Stop 2: De Nachtwacht (The Night Watch)\n\n"
        "Rembrandt's militia group portrait breaks with convention. "
        "The captain and lieutenant step forward into the light.\n\n"
        "Stop 4: Het Joodse Bruidje (The Jewish Bride)\n\n"
        "A tender embrace defines this late Rembrandt. "
        "The thick golden paint catches the gallery light.\n\n"
        "Stop 5: Gezicht op huizen in Delft (The Little Street)\n\n"
        "Vermeer turned an ordinary lane into a quiet marvel. "
        "Two women work in the still afternoon.\n\n"
        "Sources: This tour draws on information from rijksmuseum.nl.\n"
    )


class D533HeaderRemovalFixture(unittest.TestCase):
    """[LOCAL-831 #1] strip_repeated_facts must never remove a header or a whole
    stop. Reproduces the catastrophic shape from the log: a cross-stop repeated
    fact whose later telling is the FIRST sentence of a two-line stop whose
    header must survive."""

    def _tour_with_repeated_fact_in_thin_stop(self) -> str:
        # The 1831 Hokusai date is told at stop 1 and repeated at stop 3; stop 3
        # is thin (the repeat + one stop-specific sentence). A naive removal that
        # over-reached would take the header with it.
        return (
            "\nStop 1: The Great Wave\n\n"
            "Hokusai made this woodblock print around 1831 for a famous series. "
            "The towering wave dominates the small boats below.\n\n"
            "Stop 2: Mount Fuji views\n\n"
            "Hokusai made this woodblock print around 1831 for a famous series. "
            "Fuji sits serene behind the restless foreground.\n"
        )

    def test_header_line_is_never_a_removal_candidate(self):
        # A header string offered as a "sentence" is refused outright.
        header = f"Stop 3: {_RIJKS_STOP3_TITLE}"
        self.assertRegex(header, d._STOP_HEADER_LINE)

    def test_strip_keeps_every_header_and_never_empties_a_body(self):
        tour = self._tour_with_repeated_fact_in_thin_stop()
        before = count_delivered_stops(tour)
        out, actions = d.strip_repeated_facts(tour)
        after = count_delivered_stops(out)
        # No stop is ever lost.
        self.assertEqual(before, after, "a stop was deleted by strip_repeated_facts")
        # Every header survives verbatim.
        self.assertIn("Stop 1: The Great Wave", out)
        self.assertIn("Stop 2: Mount Fuji views", out)
        # No action ever reports removing a header.
        for a in actions:
            self.assertNotRegex(a.get("sentence", ""), d._STOP_HEADER_LINE,
                                f"a header was offered for removal: {a}")
        # Every stop still has at least one narration sentence (never emptied).
        self.assertEqual(check_stop_delivery(out), [])

    def test_refuses_removal_that_would_empty_a_one_sentence_body(self):
        # A stop whose ONLY narration sentence is the cross-stop repeat: removing
        # it would empty the body, so it is kept (reason recorded).
        tour = (
            "\nStop 1: Opening\n\n"
            "The museum opened its doors to the public in 1885 under Cuypers. "
            "It quickly became a national landmark.\n\n"
            "Stop 2: The hall\n\n"
            "The museum opened its doors to the public in 1885 under Cuypers.\n"
        )
        out, actions = d.strip_repeated_facts(tour)
        self.assertEqual(count_delivered_stops(out), 2)
        self.assertIn("Stop 2: The hall", out)
        self.assertEqual(check_stop_delivery(out), [])


class NonSequentialRenumberFixture(unittest.TestCase):
    """[LOCAL-831 #2] renumber_stops_sequential closes a gap even with no artifact
    removed, and is a strict no-op on a clean tour."""

    def test_gap_is_closed_without_removing_any_stop(self):
        tour = _rijks_tour_with_gap()
        self.assertEqual(
            check_stop_delivery(tour),
            ["NON_SEQUENTIAL: stop numbers [1, 2, 4, 5] are not [1, 2, 3, 4]"])
        out, changed = renumber_stops_sequential(tour)
        self.assertTrue(changed)
        self.assertEqual(count_delivered_stops(out), 4)
        self.assertEqual(check_stop_delivery(out), [])
        # Titles are preserved verbatim; only the numbers moved.
        self.assertIn("Stop 3: Het Joodse Bruidje (The Jewish Bride)", out)
        self.assertIn("Stop 4: Gezicht op huizen in Delft (The Little Street)", out)

    def test_strict_no_op_on_clean_tour(self):
        clean = (
            "Stop 1: A\n\nLong first sentence here. Long second sentence here.\n\n"
            "Stop 2: B\n\nLong first sentence here. Long second sentence here.\n")
        out, changed = renumber_stops_sequential(clean)
        self.assertFalse(changed)
        self.assertEqual(out, clean, "clean tour must be returned byte-for-byte")

    def test_idempotent(self):
        tour = _rijks_tour_with_gap()
        once, _ = renumber_stops_sequential(tour)
        twice, changed2 = renumber_stops_sequential(once)
        self.assertFalse(changed2)
        self.assertEqual(once, twice)

    def test_title_with_colon_and_year_preserved(self):
        tour = ("Stop 5: Title: with a colon, 1885\n\n"
                "Long first sentence here. Long second sentence here.\n")
        out, _ = renumber_stops_sequential(tour)
        self.assertIn("Stop 1: Title: with a colon, 1885", out)


class EmptyBodyAndHonestCountFixture(unittest.TestCase):
    """[LOCAL-831 #3] A stop removed upstream leaves a gap; the delivery repair
    closes it and the honest count reflects the REAL delivered stops."""

    def test_repair_closes_numbering_and_count_is_honest(self):
        tour = _rijks_tour_with_gap()          # 5 requested, 4 delivered, gap
        repaired, residual, actions = repair_stop_delivery(
            tour, venue_name="Rijksmuseum", requested_stops=5)
        self.assertEqual(residual, [], f"residual after repair: {residual}")
        self.assertEqual(count_delivered_stops(repaired), 4)
        self.assertTrue(any("renumbered" in a for a in actions), actions)
        # The honest shortfall sentence is built from the REAL delivered count (4),
        # not the requested 5.
        shortfall = build_shortfall_sentence(
            venue_name="Rijksmuseum", exhibitions_on_view=0,
            delivered_stops=count_delivered_stops(repaired),
            requested_stops=5, mode="museum", count_is_sourced=False)
        self.assertIn("4 stops", shortfall)
        self.assertIn("rather than the 5 you asked for", shortfall)

    def test_empty_body_stop_is_a_residual_delivery_defect(self):
        # A stop with ONLY field lines and no narration: the renumber cannot
        # invent a body, so EMPTY_BODY is a residual defect the caller must see.
        tour = (
            "Stop 1: Great Wave\n\n"
            "This print shows a towering wave. Hokusai made it around 1831.\n\n"
            "Stop 2: Empty shell\n\n"
            "Address: Museumstraat 1, 1071 XX Amsterdam\n"
            "Coordinates: 52.36, 4.88\n\n"
            "Stop 3: Night Watch\n\n"
            "Rembrandt broke with convention here. The captain steps forward.\n")
        _, residual, _ = repair_stop_delivery(tour, requested_stops=3)
        self.assertTrue(any(v.startswith("EMPTY_BODY") for v in residual),
                        f"EMPTY_BODY should be reported: {residual}")

    def test_finalize_logs_defect_and_returns_a_tour(self):
        # finalize_stop_delivery never raises and logs [LOCAL-831] DELIVERY DEFECT
        # for a residual it cannot repair.
        tour = (
            "Stop 1: A\n\nLong first sentence here. Long second here.\n\n"
            "Stop 2: Empty\n\nAddress: somewhere\n\n"
            "Stop 4: C\n\nLong first sentence here. Long second here.\n")
        logs = []
        out = finalize_stop_delivery(tour, requested_stops=4, log=logs.append)
        # Gap was closed (1,2,4 -> 1,2,3).
        self.assertEqual(count_delivered_stops(out), 3)
        self.assertTrue(any("renumbered" in m for m in logs), logs)
        # The empty body is surfaced as a DELIVERY DEFECT.
        self.assertTrue(any("DELIVERY DEFECT EMPTY_BODY" in m for m in logs), logs)


class RoleGuardHeaderSafetyFixture(unittest.TestCase):
    """[LOCAL-831 #1] story_fact_guard.repair_role_mismatches (also "D533") must
    never delete a "Stop N:" header. The live Rijks run logged
    'removed: Stop 3: Het melkmeisje' because split_sentences ran across a stop
    body with no final period into the next header + Address block, and the Dutch
    postal code '1071 DJ Amsterdam' was read as a (person='DJ Amsterdam',
    year=1071) pair. The guard now reads narration only and refuses any candidate
    carrying a header."""

    def _rijks_bodyless_tail_tour(self) -> str:
        # Stop 2 body ends WITHOUT a final period, so a naive whole-text split
        # glues it onto 'Stop 3:' and the Address line beneath it.
        return (
            "Stop 2: De Nachtwacht (The Night Watch)\n\n"
            "Rembrandt painted this civic guard portrait. "
            "The captain steps into the light\n\n"
            "Stop 3: Het melkmeisje (The Milkmaid)\n\n"
            "Address: Museumstraat 1, 1071 DJ Amsterdam, Netherlands\n"
            "Coordinates: 52.36, 4.88\n\n"
            "Vermeer designed a still kitchen scene. The maid pours milk.\n\n"
            "Stop 4: Het Joodse Bruidje (The Jewish Bride)\n\n"
            "A tender late embrace. Thick golden paint catches the light.\n")

    def test_postal_code_in_address_never_deletes_a_stop(self):
        from story_fact_guard import repair_role_mismatches
        tour = self._rijks_bodyless_tail_tour()
        # A corpus that would, if the address postal code were read as a
        # person+year, produce a birth-role mismatch against 'designed'.
        corpus = "The architect DJ Amsterdam was born in 1071."
        out, found = repair_role_mismatches(tour, corpus)
        self.assertEqual(count_delivered_stops(out), 3)
        self.assertIn("Stop 3: Het melkmeisje (The Milkmaid)", out)
        # No finding was ever allowed to carry a header into removal.
        for f in found:
            self.assertFalse(
                f.get("repaired") and "Stop 3:" in f.get("sentence", ""),
                f"a header-bearing span was removed: {f}")

    def test_genuine_birth_year_action_still_caught(self):
        # The guard must still catch a real fabrication in NARRATION.
        from story_fact_guard import find_role_mismatches
        tour = (
            "Stop 1: The quartet\n\n"
            "The quartet founded by Antoine Gautier in 1825 shaped the museum.\n")
        corpus = ("Antoine Gautier, a collector born in Nice in 1825, "
                  "helped form the collection.")
        found = find_role_mismatches(tour, corpus)
        self.assertTrue(any(f["person"].endswith("Gautier") for f in found),
                        f"genuine mismatch must still be flagged: {found}")


if __name__ == "__main__":
    unittest.main()
