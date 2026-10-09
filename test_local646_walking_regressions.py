#!/usr/bin/env python3
"""test_local646_walking_regressions.py — LOCAL-646.

Two WALKING-tour regressions introduced by the museum work (LOCAL-628/638/642/643),
seen on tour audio_tours.id=557 ("Walking tour in Boston dedicated to Massachusetts
politics and current affairs", walking, 5 stops) against the Oct-6 baseline:

  REG 1 — Stop 4 layout collapsed. The delivered Stop 4 read:
      Type/Specialty: Historical Landmark Specific Examples: Colonial architecture, …
      Orientation: Stand beneath … <the ENTIRE narration on the Orientation line>
    Root cause: ``stop_editor._split_stop_block``'s ``_STRUCT_LABELS`` set did not
    know ``Type/Specialty:`` / ``Specific Examples:`` (nor ``Operational Details:`` /
    ``Museum Information:``). A stop carrying those fields had the field lines — and
    everything after them, including the ``Orientation:`` block and the narration —
    mis-classified as rewritable *body*, which the LLM editor then reflowed into one
    run-on line. Field lines must never be joined, and the Orientation and the
    narration must stay separate paragraphs.

  REG 2 — a duplicate transition. Stop 3 ended with a real
      "Directions: … until you reach the iconic Old State House …"
    and then the LOCAL-638 Note-4 "every stop ends with directions" guarantee
    appended a DUPLICATE "Continue to The Old State House." Root cause:
    ``directions_guarantee._DIRECTIONS_LABEL_RE`` lacked ``re.MULTILINE``, so an
    existing "Directions:" line that was not the first of the joined tail lines was
    never recognised. The guarantee must recognise an existing walking "Directions:"
    line and add nothing when one is present.

The fixtures below are the REAL tour-557 Stop 3 and Stop 4 blocks (verbatim from
audio_tours.id=557). A third, DB-backed test reads the live row when it is
reachable and otherwise skips, so the suite runs offline.

A third fix covers the museum CANARY (the Courtauld, tour 559): the stop_editor
fix exposed a pre-existing LEAD field-sync bug where the composed hours/admission
were placed BOTH as the Stop-1 spoken opening paragraph AND copied into the
(TTS-stripped) "Museum Information:" field line, so the bench detector counted
hours/admission twice. The fix clears that field line.

Run: python3 -m pytest test_local646_walking_regressions.py -q
     python3 test_local646_walking_regressions.py
"""
import os
import re
import unittest

os.environ.setdefault("STOP_EDITOR", "1")

import stop_editor as se
import directions_guarantee as dg
import practical_facts_gate as pfg


# ─────────────────────────────────────────────────────────────────────────────
# REAL tour-557 blocks (verbatim). These are the delivered, damaged blocks.
# ─────────────────────────────────────────────────────────────────────────────

# Stop 3 as delivered: a correct "Directions:" line AND the duplicate
# "Continue to The Old State House." the guarantee wrongly added (reg 2).
STOP557_3_DELIVERED = (
    "Stop 3: Faneuil Hall\n\n"
    "Coordinates: 42.3605, -71.0542\n\n"
    "As you stand beneath the brick and granite of Faneuil Hall, the city\u2019s "
    "cadence shifts from the solemn gold dome of the Massachusetts State House you "
    "visited earlier to the marketplace bustle here.\n\n"
    "Faneuil Hall stands because Peter Faneuil, one of Boston\u2019s wealthiest "
    "merchants, gave this building to the city in 1742.\n\n"
    "The story of Faneuil Hall is not only about colonial dissent. Its bricks have "
    "absorbed the ongoing negotiations of Boston\u2019s civic life.\n\n"
    "Directions: As you leave Faneuil Hall, stroll down Congress Street towards "
    "State Street. Continue walking until you reach the iconic Old State House on "
    "your left. You'll pass by historic sites and bustling city life along the way, "
    "so take your time and enjoy the walk.\n\n"
    "Continue to The Old State House.\n\n"
)

# The pre-guarantee Stop 3 (the duplicate "Continue to" removed): what the
# guarantee actually sees when it runs. It MUST NOT re-add the duplicate.
STOP557_3_PRE_GUARANTEE = STOP557_3_DELIVERED.replace(
    "\n\nContinue to The Old State House.\n\n", "\n\n")

# Stop 4's REAL field VALUES (from 557), used to build the well-formed
# pre-collapse block the editor should preserve.
S4_ADDRESS = "206 Washington St, Boston, MA 02109"
S4_COORDS = "42.3601, -71.0569"
S4_TYPE = "Historical Landmark"
S4_EXAMPLES = "Colonial architecture, museum exhibits, site of the Boston Massacre."
S4_ORIENTATION = (
    "Stand beneath the crisp lines of the Old State House\u2019s weathered brick "
    "and pale stone, just where Congress Street splits the city\u2019s modern rhythm."
)
S4_NARRATION = (
    "Inside, the world first glimpsed the machinery of government. John Adams, a "
    "key figure in the American Revolution, would later call this the moment the "
    "child Independence was born."
)

# A WELL-FORMED Stop 4 block: every field on its own line, Orientation its own
# paragraph, narration a separate paragraph — the shape the renderer emits before
# any late pass. This is the input the stop editor must NOT collapse.
STOP557_4_WELLFORMED = (
    "Stop 4: The Old State House\n\n"
    f"Address: {S4_ADDRESS}\n\n"
    f"Coordinates: {S4_COORDS}\n\n"
    f"Type/Specialty: {S4_TYPE}\n\n"
    f"Specific Examples: {S4_EXAMPLES}\n\n"
    f"Orientation: {S4_ORIENTATION}\n\n"
    f"{S4_NARRATION}\n\n"
    "Directions: As you leave The Old State House, head south on Washington Street.\n"
)


def _flatten_llm(prompt, api_key):
    """A stand-in editor LLM that reflows whatever BODY it is handed into one
    run-on line (collapsing blank-line paragraph breaks into spaces) — exactly
    the behaviour that produced the 557 collapse when field lines were wrongly
    handed to the editor as body."""
    body = prompt.split("STOP BODY:\n", 1)[1].strip()
    return re.sub(r"\s*\n\s*\n\s*", " ", body).replace("\n", " ")


# ─────────────────────────────────────────────────────────────────────────────
# REG 1 — stop editor must preserve field lines; keep Orientation + narration apart
# ─────────────────────────────────────────────────────────────────────────────

class TestReg1StopEditorFieldPreservation(unittest.TestCase):
    def test_struct_labels_include_the_museum_fields(self):
        """The split-set must now know the fields the museum work added."""
        for lbl in ("Type/Specialty:", "Specific Examples:",
                    "Operational Details:", "Museum Information:"):
            self.assertIn(lbl, se._STRUCT_LABELS, f"{lbl} not in _STRUCT_LABELS")

    def test_split_keeps_fields_out_of_body(self):
        """_split_stop_block must put the fields + Orientation in preserved meta
        and hand the editor ONLY the narration paragraph."""
        _h, meta, body, _tail = se._split_stop_block(STOP557_4_WELLFORMED)
        # Each field label is preserved verbatim in the meta, on its own line.
        for line in ("Type/Specialty: " + S4_TYPE,
                     "Specific Examples: " + S4_EXAMPLES,
                     "Orientation: " + S4_ORIENTATION):
            self.assertIn(line, meta)
        # The body sent to the editor is the narration only — no field labels.
        self.assertEqual(body.strip(), S4_NARRATION)
        for lbl in ("Type/Specialty", "Specific Examples", "Orientation"):
            self.assertNotIn(lbl, body)

    def test_editor_does_not_collapse_fields(self):
        """Through the (flattening) editor, the fields and Orientation survive on
        their own lines and only the narration is reflowed — no 557-style run-on."""
        new_block, edited, _reason = se.edit_stop(
            STOP557_4_WELLFORMED, stop_number=4, llm_fn=_flatten_llm, api_key="x")
        self.assertTrue(edited)
        # The pathological 557 run-on must NOT appear.
        self.assertNotIn(
            f"Type/Specialty: {S4_TYPE} Specific Examples:", new_block)
        self.assertNotIn("Specific Examples: " + S4_EXAMPLES + " Orientation:",
                         new_block)
        # Each field is on its own physical line.
        lines = new_block.split("\n")
        self.assertIn(f"Type/Specialty: {S4_TYPE}", lines)
        self.assertIn(f"Specific Examples: {S4_EXAMPLES}", lines)
        # The Orientation line starts with the label and the narration does NOT
        # share that line (it is a later, separate paragraph).
        orient_line = next(l for l in lines if l.startswith("Orientation:"))
        self.assertNotIn("Inside, the world first glimpsed", orient_line)
        self.assertIn("Inside, the world first glimpsed", new_block)
        # Orientation paragraph and narration paragraph are separated by a blank
        # line (the Orientation line ends, a blank line, then the narration).
        self.assertRegex(new_block, r"Orientation: [^\n]*\n\s*\n")

    def test_regression_shape_is_what_557_showed(self):
        """Documents the exact 557 damage: without the fix the editor would glue
        'Type/Specialty: … Specific Examples: … Orientation: <narration>'. Here we
        assert the FIXED code never reproduces that collapsed first line."""
        new_block, _edited, _r = se.edit_stop(
            STOP557_4_WELLFORMED, stop_number=4, llm_fn=_flatten_llm, api_key="x")
        collapsed = (f"Type/Specialty: {S4_TYPE} Specific Examples: {S4_EXAMPLES} "
                     f"Orientation: {S4_ORIENTATION}")
        self.assertNotIn(collapsed, new_block)


# ─────────────────────────────────────────────────────────────────────────────
# REG 2 — directions guarantee must recognise an existing Directions line
# ─────────────────────────────────────────────────────────────────────────────

class TestReg2DirectionsGuaranteeNoDuplicate(unittest.TestCase):
    def test_directions_label_re_is_multiline(self):
        self.assertTrue(dg._DIRECTIONS_LABEL_RE.flags & re.MULTILINE)

    def test_block_with_directions_counts_as_having_transition(self):
        """The real 557 Stop 3 (pre-guarantee) ends with a 'Directions:' line as
        the last paragraph; it must be recognised as a hand-off to Stop 4."""
        has = dg._block_has_transition(STOP557_3_PRE_GUARANTEE, "The Old State House")
        self.assertTrue(has, "existing Directions: line not recognised")

    def test_guarantee_adds_no_duplicate_continue_to(self):
        """On the pre-guarantee Stop 3, the guarantee must add NOTHING (0) and must
        not introduce a 'Continue to The Old State House.' duplicate."""
        fixed, added = dg.ensure_directions_between_stops(STOP557_3_PRE_GUARANTEE)
        self.assertEqual(added, 0)
        self.assertNotIn("Continue to The Old State House.", fixed)

    def test_full_pre_guarantee_tour_has_no_missing_and_no_duplicate(self):
        """A 2-stop slice (557 Stop 3 → Stop 4 header) proves end-to-end: the
        existing Directions line means 0 missing and no appended transition."""
        two = (STOP557_3_PRE_GUARANTEE
               + "Stop 4: The Old State House\n\n"
               + "Coordinates: 42.3601, -71.0569\n\n"
               + "Narration for the Old State House ends the slice.\n\n"
               + "That's 2 stops in all.\n")
        self.assertEqual(dg.count_stops_missing_directions(two), 0)
        fixed, added = dg.ensure_directions_between_stops(two)
        self.assertEqual(added, 0)
        self.assertEqual(fixed.count("Continue to The Old State House."), 0)

    def test_guarantee_still_adds_when_truly_missing(self):
        """Guard against over-correction: a stop with NO Directions line and NO
        transition cue must still receive a hand-off."""
        t = ("Stop 1: Alpha\n\nCoordinates: 1,2\n\n"
             "Alpha narration with no transition at all.\n\n"
             "Stop 2: Beta\n\nCoordinates: 3,4\n\n"
             "Beta narration ends the tour.\n\n"
             "That's 2 stops in all.\n")
        self.assertEqual(dg.count_stops_missing_directions(t, "Test Museum"), 1)
        fixed, added = dg.ensure_directions_between_stops(t, "Test Museum")
        self.assertEqual(added, 1)
        self.assertIn("Your final stop in Test Museum: Beta.", fixed)


# ─────────────────────────────────────────────────────────────────────────────
# MUSEUM CANARY — Museum Information field must not duplicate the spoken facts
# ─────────────────────────────────────────────────────────────────────────────
#
# A SEPARATE, pre-existing bug (LEAD 2026-10-09, place_practical_facts_in_opening)
# that the stop_editor fix EXPOSED on the museum canary (the Courtauld, tour 559):
# the composed hours/admission are placed as the Stop-1 spoken opening paragraph,
# and the LEAD field-sync ALSO copied the SAME composed facts into the
# "Museum Information:" field line. The TTS extractor strips the whole
# "Museum Information:" line, so the audio spoke the facts once — but the bench
# detector (and count_spoken_hours_statements) count the field-line value too, so
# the canary showed hours_said_twice / admission_twice. The fix clears the field
# line (the facts stay in the spoken opening paragraph), so hours/admission appear
# exactly ONCE in the delivered text.

class TestMuseumCanaryNoHoursDuplication(unittest.TestCase):
    _STOP1_BOTH = (
        "Step-by-Step Audio Guided Tour: The Courtauld Gallery - Museum Tour\n\n"
        "Stop 1: Georges Seurat\n\n"
        "Coordinates: 51.5115, -0.1195\n\n"
        "Museum Information: The museum is open Monday to Sunday from 10:00 to "
        "18:00. Admission is 14 pounds for adults.\n\n"
        "Orientation: Stand before Seurat's painting.\n\n"
        "The museum is open Monday to Sunday from 10:00 to 18:00. Admission is 14 "
        "pounds for adults.\n\n"
        "Georges Seurat pioneered pointillism.\n\n"
        "Stop 2: Van Gogh\n\n"
        "Orientation: Stand before it.\n"
    )

    def test_place_practical_facts_clears_museum_information_line(self):
        """After placement, the composed facts are spoken once and the
        Museum Information field line carries no duplicate value."""
        out, _n = pfg.place_practical_facts_in_opening(self._STOP1_BOTH)
        # Hours/admission spoken exactly once (as the listener hears it).
        self.assertEqual(pfg.count_spoken_hours_statements(out), 1)
        self.assertEqual(out.count("The museum is open Monday to Sunday"), 1)
        # The Museum Information field line is present but EMPTY (no duplicate).
        mi = re.search(r"(?m)^Museum Information:(.*)$", out)
        self.assertIsNotNone(mi)
        self.assertEqual(mi.group(1).strip(), "")

    def test_bench_detector_shape_passes(self):
        """Mirror the bench detectors (hours_said_twice / admission_twice) on the
        delivered text: both must be clear after placement."""
        out, _n = pfg.place_practical_facts_in_opening(self._STOP1_BOTH)
        spoken = out.split("\nSources:")[0]
        hours = re.findall(
            r"(?i)\b(?:is open|open daily|open (?:mon|tue|wed|thu|fri|sat|sun)\w*|"
            r"opening hours)\b", spoken)
        adm = re.findall(r"(?i)admission[^.]*\.", spoken)
        self.assertLessEqual(len(hours), 1, f"hours_said_twice: {hours}")
        self.assertLessEqual(len(adm), 1, f"admission_twice: {adm}")

    def test_idempotent(self):
        out, _n = pfg.place_practical_facts_in_opening(self._STOP1_BOTH)
        out2, n2 = pfg.place_practical_facts_in_opening(out)
        self.assertEqual(n2, 0)
        self.assertEqual(out2, out)


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed check on the live 557 row (skips when the DB is unreachable)
# ─────────────────────────────────────────────────────────────────────────────

class TestLive557Row(unittest.TestCase):
    def _fetch_557(self):
        try:
            import psycopg2
        except Exception as e:  # pragma: no cover
            self.skipTest(f"psycopg2 unavailable: {e}")
        try:
            conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5433")),
                user=os.environ.get("DB_USER", "admin"),
                password=os.environ.get("DB_PASSWORD", "password123"),
                dbname=os.environ.get("DB_NAME", "audiotours"),
                connect_timeout=4)
        except Exception as e:  # pragma: no cover
            self.skipTest(f"DB unreachable: {e}")
        try:
            cur = conn.cursor()
            cur.execute("SELECT tour_content FROM audio_tours WHERE id=557")
            row = cur.fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            self.skipTest("audio_tours.id=557 not present")
        return row[0]

    def test_live_557_after_refix_would_be_clean(self):
        """Read the live 557 row; reconstruct its pre-guarantee text and prove the
        FIXED directions guarantee adds nothing (no duplicate). This asserts the
        delivery-path guarantee is now idempotent on the real tour."""
        tc = self._fetch_557()
        pre = tc.replace("\n\nContinue to The Old State House.\n", "\n")
        pre = re.sub(
            r"\n\nYour final stop in Boston dedicated to Massachusetts politics "
            r"and current affairs: Massachusetts politics and current affairs\.\n",
            "\n", pre)
        self.assertEqual(dg.count_stops_missing_directions(pre), 0)
        fixed, added = dg.ensure_directions_between_stops(pre)
        self.assertEqual(added, 0)
        self.assertNotIn("Continue to The Old State House.", fixed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
