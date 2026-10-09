#!/usr/bin/env python3
"""test_local641_fresh_equals_reuse.py — LOCAL-641.

A FRESH tour must open each stop with ITS OWN orientation, exactly like a REUSE
delivery of the same stops. The regression: a fresh delivery opened Stop 1 with
STOP 2's orientation (Courtauld R10: Stop 1 "Van Gogh" carried Seurat's
"tapestry of discrete points / pointillist" orientation), while the SAME stops
reused opened each stop with its own orientation.

Root cause: ``stop_pool_orchestrator._overall_from_new`` scanned the WHOLE
gen_text for the first ``Orientation:`` label and returned it as Stop 1's overall
seed. When Stop 1's own orientation was folded into opening prose (so Stop 1 had
no ``Orientation:`` label of its own), the first match belonged to Stop 2.

These tests drive the REAL orchestrator helpers (``_overall_from_new``,
``_new_unit_from_parsed``) and the REAL ``stop_pool_assembly.assemble_building_tour``
(no DB, no network, no LLM — deterministic directions templates), building the
fresh-path from a gen_text fixture and asserting:

  1. ``_overall_from_new`` NEVER returns a later stop's orientation; it returns
     Stop 1's own when Stop 1 has a label, else None.
  2. In the assembled FRESH tour, every stop's Orientation names ITS OWN work-title
     and no OTHER delivered stop's title, AND every stop that had an orientation in
     gen_text still has one (none is lost, none is shifted up a stop).
  3. The FRESH assembly equals the REUSE assembly of the same stops, per-stop
     orientation for orientation.

Run: python3 -m pytest tests/test_local641_fresh_equals_reuse.py -q
     python3 tests/test_local641_fresh_equals_reuse.py
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_pool_store as pool
import stop_pool_assembly as asm
from stop_pool_orchestrator import _overall_from_new, _new_unit_from_parsed


_ORIENT_RE = re.compile(r'^Orientation:\s*(.+?)\s*$', re.M)
_STOP_HDR = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)


# The failing shape: Stop 1's orientation is FOLDED INTO OPENING PROSE (no
# "Orientation:" label of its own), while every LATER stop carries its own
# "Orientation:" label at the top of its block. This is exactly what made
# _overall_from_new return Stop 2's (Seurat's) orientation.
GEN_STOP1_UNLABELLED = """\
Step-by-Step Audio Guided Tour: The Courtauld Gallery, London - Museum Tour
Tour-Category: museum

Stop 1: Van Gogh's Self-Portrait with Bandaged Ear

The Courtauld Gallery is an art museum in Somerset House, on the Strand in central London. It houses the Samuel Courtauld Trust collection.

The Courtauld Gallery is open 10:00 to 18:00. Admission is 11 pounds.

In January 1889, Van Gogh created Self-Portrait with Bandaged Ear a week after leaving hospital.

Directions: Continue through The Courtauld Gallery — next is Georges Seurat.

Stop 2: Georges Seurat

Orientation: To best appreciate Georges Seurat's work, stand close enough that the surface becomes a tapestry of discrete points. From this distance Seurat's pointillist technique emerges in full force.

Georges Seurat, who lived from 1859 to 1891, applied pointillism to capture light.

Directions: Your final stop in The Courtauld Gallery: Manet's A Bar at the Folies-Bergère.

Stop 3: Manet's A Bar at the Folies-Bergère

Orientation: Stand directly in front of Manet's A Bar at the Folies-Bergère to see the mirrored surface behind the barmaid Suzon.

Édouard Manet began this work by sketching on site at the Folies-Bergère.

Sources: https://courtauld.ac.uk
"""


# The well-formed shape: Stop 1 carries its OWN "Orientation:" label.
GEN_STOP1_LABELLED = """\
Step-by-Step Audio Guided Tour: The Courtauld Gallery, London - Museum Tour
Tour-Category: museum

Stop 1: Van Gogh's Self-Portrait with Bandaged Ear

Orientation: Stand just beyond arm's reach from Van Gogh's Self-Portrait with Bandaged Ear, where the textured strokes remain visible.

In January 1889, Van Gogh created Self-Portrait with Bandaged Ear a week after leaving hospital.

Directions: Continue through The Courtauld Gallery — next is Georges Seurat.

Stop 2: Georges Seurat

Orientation: To best appreciate Georges Seurat's work, stand close enough that the surface becomes a tapestry of discrete points.

Georges Seurat applied pointillism to capture light.

Directions: Your final stop in The Courtauld Gallery: Manet's A Bar at the Folies-Bergère.

Stop 3: Manet's A Bar at the Folies-Bergère

Orientation: Stand directly in front of Manet's A Bar at the Folies-Bergère to see the mirrored surface.

Édouard Manet began this work by sketching on site at the Folies-Bergère.

Sources: https://courtauld.ac.uk
"""


def _bare_title(raw):
    t = re.sub(r',\s*\d{3,4}\s*$', '', (raw or "").strip())
    t = re.sub(r'\s+by\s+.+$', '', t, flags=re.IGNORECASE)
    return t.strip()


def _assemble_fresh(gen_text):
    parsed = pool.parse_delivered_stops(gen_text)
    units = [_new_unit_from_parsed(s) for s in parsed]
    return asm.assemble_building_tour(
        "The Courtauld Gallery, London", "art", "museum", "Museum", "Museum",
        venue_name="The Courtauld Gallery",
        new_stops=units, pooled_stops=[],
        overall_orientation=_overall_from_new(gen_text),
        sources_block="Sources: https://courtauld.ac.uk",
        opening_section="", venue_address="Somerset House, Strand, London"), parsed


def _assemble_reuse(gen_text):
    """Same stops served from pooled rows — the correct baseline."""
    parsed = pool.parse_delivered_stops(gen_text)
    pooled_rows = []
    for u in parsed:
        m = _ORIENT_RE.search(u.get("raw_block") or "")
        pooled_rows.append({
            "title": u["title"], "artist": u.get("artist", ""), "year": u.get("year", ""),
            "narration": u["narration"], "orientation": m.group(1).strip() if m else "",
            "address": "", "coordinates": "", "type_specialty": "",
            "specific_examples": "", "operational_details": "", "_pool_reused": True,
        })
    return asm.assemble_building_tour(
        "The Courtauld Gallery, London", "art", "museum", "Museum", "Museum",
        venue_name="The Courtauld Gallery",
        new_stops=[], pooled_stops=pooled_rows,
        overall_orientation=None,
        sources_block="Sources: https://courtauld.ac.uk",
        opening_section="", venue_address="Somerset House, Strand, London")


def _per_stop_orientations(tour_text):
    """Return [(title, orientation_label_or_None), ...] for the assembled tour."""
    out = []
    headers = list(_STOP_HDR.finditer(tour_text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(tour_text)
        block = tour_text[start:end]
        om = re.search(r'(?im)^\s*Orientation:\s*(.+)$', block)
        out.append((_bare_title(h.group(2)), om.group(1).strip() if om else None))
    return out


class TestOverallFromNewScoping(unittest.TestCase):
    def test_unlabelled_stop1_returns_none_not_stop2(self):
        """When Stop 1 has no Orientation label, the overall seed must be None —
        NEVER Stop 2's orientation (the exact LOCAL-641 regression)."""
        overall = _overall_from_new(GEN_STOP1_UNLABELLED)
        self.assertIsNone(
            overall,
            f"overall seed must be None when Stop 1 is unlabelled, got: {overall!r}")

    def test_labelled_stop1_returns_its_own(self):
        overall = _overall_from_new(GEN_STOP1_LABELLED)
        self.assertIsNotNone(overall)
        self.assertIn("Van Gogh", overall)
        self.assertNotIn("Seurat", overall)
        self.assertNotIn("pointillist", overall)

    def test_never_returns_a_later_stop_orientation(self):
        for gen in (GEN_STOP1_UNLABELLED, GEN_STOP1_LABELLED):
            overall = _overall_from_new(gen) or ""
            # Stop 2's and Stop 3's distinctive phrases must never leak into the seed.
            self.assertNotIn("pointillist", overall)
            self.assertNotIn("Suzon", overall)


class TestFreshStopOrientationsAreOwn(unittest.TestCase):
    def _assert_each_names_own_and_none_foreign(self, tour_text):
        pairs = _per_stop_orientations(tour_text)
        titles = [t for t, _ in pairs]
        for title, orient in pairs:
            self.assertIsNotNone(
                orient, f"stop {title!r} LOST its orientation (none in assembled tour)")
            self.assertIn(
                title, orient,
                f"stop {title!r} Orientation does not name its own work: {orient!r}")
            for other in titles:
                if other == title:
                    continue
                self.assertNotIn(
                    other, orient,
                    f"stop {title!r} Orientation names FOREIGN stop {other!r}: {orient!r}")

    def test_unlabelled_stop1_fresh_each_stop_keeps_own(self):
        """The failing shape: Stop 2 (Seurat) and Stop 3 (Manet) keep their own
        orientation, and Stop 1 does NOT carry Seurat's."""
        result, _ = _assemble_fresh(GEN_STOP1_UNLABELLED)
        pairs = _per_stop_orientations(result.tour_text)
        by_title = {t: o for t, o in pairs}
        # Stop 1 must NOT carry Seurat's pointillist orientation.
        stop1_orient = by_title.get("Van Gogh's Self-Portrait with Bandaged Ear") or ""
        self.assertNotIn("pointillist", stop1_orient,
                         f"Stop 1 carried Seurat's orientation: {stop1_orient!r}")
        # Stop 2 (Seurat) must still have its own orientation (not lost).
        self.assertIsNotNone(by_title.get("Georges Seurat"),
                             "Stop 2 (Seurat) lost its orientation")
        self.assertIn("pointillist", by_title["Georges Seurat"])
        # Stop 3 (Manet) must still have its own.
        self.assertIsNotNone(by_title.get("Manet's A Bar at the Folies-Bergère"))

    def test_labelled_stop1_fresh_each_names_own(self):
        result, _ = _assemble_fresh(GEN_STOP1_LABELLED)
        self._assert_each_names_own_and_none_foreign(result.tour_text)


class TestFreshEqualsReuse(unittest.TestCase):
    def test_fresh_matches_reuse_per_stop_orientation(self):
        """The invariant: a fresh delivery == a reuse delivery of the same stops,
        orientation for orientation."""
        for gen in (GEN_STOP1_UNLABELLED, GEN_STOP1_LABELLED):
            fresh, _ = _assemble_fresh(gen)
            reuse = _assemble_reuse(gen)
            fresh_pairs = _per_stop_orientations(fresh.tour_text)
            reuse_pairs = _per_stop_orientations(reuse.tour_text)
            self.assertEqual(
                [t for t, _ in fresh_pairs], [t for t, _ in reuse_pairs],
                "fresh and reuse delivered a different stop order")
            for (ft, fo), (rt, ro) in zip(fresh_pairs, reuse_pairs):
                # Each stop's orientation presence + own-title must match reuse.
                self.assertEqual(
                    fo is None, ro is None,
                    f"stop {ft!r}: fresh orientation presence != reuse "
                    f"(fresh={fo!r} reuse={ro!r})")
                if fo is not None and ro is not None:
                    self.assertEqual(
                        fo, ro,
                        f"stop {ft!r}: fresh orientation != reuse orientation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
