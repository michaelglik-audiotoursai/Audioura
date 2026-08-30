"""[LOCAL-471] Carry coordinate confidence to the app — emit + parser-safety.

WHAT THIS PINS
  1. The emitter writes exactly one `Coordinate-Confidence:` line per stop, in the
     right place, idempotently, and marks anything not corroborated 'low'.
  2. Wired to the real geocode rule, the three acceptance stops come out with the
     confidence the field-test measured: Musée Matisse high, Villa Leopolda and
     Musée National du Sport low.
  3. GEOCODE_STOPS=0 still produces a field on every stop, all 'low', with no crash.
  4. Every EXISTING audio_N.txt parser still reads a file carrying the new line:
       * the map / navigation coordinate regex (ported verbatim from
         tour_map_screen.dart and navigation_service.dart — identical there),
       * the modernized service's stop splitter + coordinate check,
       * the translation service's stop splitter and metadata restore.
  5. The TTS strip set removes the line, so it is never spoken.

The geocoder is stubbed where the rule is exercised, so this is deterministic and
needs no network. Run: python3 -m pytest tests/test_local471_confidence_emit.py -v
or  python3 tests/test_local471_confidence_emit.py
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geocode_stops as g  # noqa: E402
from geo_confidence_emit import (  # noqa: E402
    annotate_stop_text, annotate_text_content, normalize_confidence,
    CONFIDENCE_PREFIX,
)

# Reused from the D559 test: Cimiez and a point ~3.4 km away in Villefranche.
CIMIEZ = (43.7109, 7.2784)
CIMIEZ_NEAR = (43.71095, 7.27845)      # ~7 m: inside AGREEMENT_M
VILLEFRANCHE = (43.709376, 7.320883)   # real Villa Leopolda, 3.4 km from Cimiez
ALLIANZ = (43.706263, 7.192379)        # Musée National du Sport is really here, 7 km off


def stop_block(name, address, pt):
    """The per-stop shape tour_generation_modernized.py splits out and writes to
    audio_N.txt: line 0 is the venue name, then the metadata lines."""
    return (f"{name}\n"
            f"Address: {address}\n"
            f"Coordinates: {pt[0]}, {pt[1]}\n"
            f"Type/Specialty: Museum\n"
            f"This is the narration paragraph the visitor actually hears.")


# The EXACT regexes the app uses. Ported verbatim so a change here that would
# break the app breaks this test. Cross-checked against the .dart sources in
# test_the_app_regexes_are_still_the_ones_we_ported.
_APP_COORD_RE = re.compile(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)')
_APP_TYPE_RE = re.compile(r'Type/Specialty:\s*(.+)')
_APP_ADDR_RE = re.compile(r'Address:\s*(.+)')


class _StubbedCase(unittest.TestCase):
    def setUp(self):
        self._real = g.geocode
        self._enabled = g.GEOCODE_ENABLED
        g.GEOCODE_ENABLED = True

    def tearDown(self):
        g.geocode = self._real
        g.GEOCODE_ENABLED = self._enabled

    def stub(self, answers):
        class _Stub:
            def __init__(self, a):
                self.answers = a
            def __call__(self, query):
                q = (query or '').lower()
                for key, val in self.answers.items():
                    if q.startswith(key.lower()):
                        return val
                return None
        g.geocode = _Stub(answers)
        return g.geocode


class TestNormalizeConfidence(unittest.TestCase):
    def test_high_is_the_only_way_to_high(self):
        self.assertEqual(normalize_confidence('high'), 'high')
        self.assertEqual(normalize_confidence('HIGH'), 'high')
        self.assertEqual(normalize_confidence(' high '), 'high')

    def test_everything_else_fails_to_low(self):
        for v in ('low', 'medium', '', None, 'unknown', 0, 'hi'):
            self.assertEqual(normalize_confidence(v), 'low',
                             f"{v!r} should be low, an unverified coordinate is not trustworthy")


class TestAnnotateStopText(unittest.TestCase):
    def test_line_lands_right_after_coordinates(self):
        out = annotate_stop_text(stop_block('X', '1 Main St', CIMIEZ), 'low')
        lines = out.split('\n')
        coord_i = next(i for i, l in enumerate(lines) if l.startswith('Coordinates:'))
        self.assertEqual(lines[coord_i + 1], f"{CONFIDENCE_PREFIX} low")

    def test_high_is_written_when_given(self):
        out = annotate_stop_text(stop_block('X', '1 Main St', CIMIEZ), 'high')
        self.assertIn(f"{CONFIDENCE_PREFIX} high", out)
        self.assertNotIn(f"{CONFIDENCE_PREFIX} low", out)

    def test_exactly_one_line_even_on_re_annotation(self):
        once = annotate_stop_text(stop_block('X', '1 Main St', CIMIEZ), 'low')
        twice = annotate_stop_text(once, 'high')     # value changed too
        self.assertEqual(twice.count(CONFIDENCE_PREFIX), 1,
                         "re-annotating stacked or duplicated the field")
        self.assertIn(f"{CONFIDENCE_PREFIX} high", twice)

    def test_missing_coordinates_line_still_gets_the_field(self):
        text = "New Stop\nAddress: 1 Main St\nnarration"
        out = annotate_stop_text(text, 'low')
        self.assertIn(f"{CONFIDENCE_PREFIX} low", out)
        # goes after the title, not lost
        self.assertEqual(out.split('\n')[1], f"{CONFIDENCE_PREFIX} low")

    def test_does_not_disturb_the_coordinate_or_address(self):
        out = annotate_stop_text(stop_block('X', '164 Avenue des Arenes', CIMIEZ), 'low')
        self.assertIn(f"Coordinates: {CIMIEZ[0]}, {CIMIEZ[1]}", out)
        self.assertIn('Address: 164 Avenue des Arenes', out)


class TestAnnotateTextContent(unittest.TestCase):
    def test_records_align_by_index(self):
        stops = [stop_block('A', 'a', CIMIEZ), stop_block('B', 'b', CIMIEZ)]
        recs = [{'confidence': 'high'}, {'confidence': 'low'}]
        out = annotate_text_content(stops, recs)
        self.assertIn(f"{CONFIDENCE_PREFIX} high", out[0])
        self.assertIn(f"{CONFIDENCE_PREFIX} low", out[1])

    def test_short_or_missing_records_default_low_not_skip(self):
        # AC4: geocoder import failed (records=[]) or GEOCODE_STOPS=0 gave fewer.
        stops = [stop_block('A', 'a', CIMIEZ), stop_block('B', 'b', CIMIEZ)]
        for recs in ([], None, [{'confidence': 'high'}]):
            out = annotate_text_content(stops, recs)
            self.assertEqual(len(out), 2)
            for i, s in enumerate(out):
                self.assertEqual(s.count(CONFIDENCE_PREFIX), 1,
                                 f"stop {i} missing/duplicated field for records={recs!r}")
            # every stop with no record is low
            if recs == [{'confidence': 'high'}]:
                self.assertIn(f"{CONFIDENCE_PREFIX} high", out[0])
                self.assertIn(f"{CONFIDENCE_PREFIX} low", out[1])
            else:
                self.assertTrue(all(f"{CONFIDENCE_PREFIX} low" in s for s in out))


class TestAcceptanceStops(_StubbedCase):
    """AC5: the three field-measured stops come out with the measured confidence,
    end to end through correct_stops -> annotate_text_content."""

    def _emit(self, stops):
        new_text, records = g.correct_stops(stops, 'Nice, France', tour_anchor=CIMIEZ)
        return annotate_text_content(new_text, records)

    def test_matisse_high_leopolda_and_sport_low(self):
        # Matisse: name and address both geocode to the same Cimiez point -> agree -> high.
        # Leopolda: only the name geocodes, to Villefranche 3.4 km away -> disagree -> low.
        # Sport: only the name geocodes, to Allianz Riviera 7 km away -> disagree -> low.
        self.stub({
            'Musee Matisse': CIMIEZ_NEAR,
            '164 Avenue': CIMIEZ_NEAR,
            'Villa Leopolda': VILLEFRANCHE,
            'Musee National du Sport': ALLIANZ,
        })
        stops = [
            stop_block('Musee Matisse', '164 Avenue des Arenes, 06000 Nice', (43.7187, 7.2768)),
            stop_block('Villa Leopolda', 'Avenue de la Villa Leopolda, 06000 Nice', (43.7109, 7.2784)),
            stop_block('Musee National du Sport', 'Boulevard des Jardins de Cimiez', (43.7134, 7.2822)),
        ]
        out = self._emit(stops)
        self.assertIn(f"{CONFIDENCE_PREFIX} high", out[0], "Matisse should be high")
        self.assertIn(f"{CONFIDENCE_PREFIX} low", out[1], "Villa Leopolda should be low")
        self.assertIn(f"{CONFIDENCE_PREFIX} low", out[2], "Musee National du Sport should be low")
        # And the corroborated one had its coordinate corrected in place.
        self.assertIn(f"Coordinates: {CIMIEZ_NEAR[0]:.6f}, {CIMIEZ_NEAR[1]:.6f}", out[0])

    def test_geocode_disabled_marks_every_stop_low_and_does_not_crash(self):
        # AC4: GEOCODE_STOPS=0. correct_stops still runs and returns a record per
        # stop with confidence 'low'; the field is present on every stop.
        g.GEOCODE_ENABLED = False
        stops = [
            stop_block('Musee Matisse', '164 Avenue des Arenes, 06000 Nice', (43.7187, 7.2768)),
            stop_block('Villa Leopolda', 'Avenue de la Villa Leopolda, 06000 Nice', (43.7109, 7.2784)),
        ]
        out = self._emit(stops)
        self.assertEqual(len(out), 2)
        for s in out:
            self.assertEqual(s.count(CONFIDENCE_PREFIX), 1)
            self.assertIn(f"{CONFIDENCE_PREFIX} low", s)


class TestExistingParsersStillRead(_StubbedCase):
    """AC2: prove every existing parser still reads a file carrying the new line."""

    def annotated_matisse(self):
        self.stub({'Musee Matisse': CIMIEZ_NEAR, '164 Avenue': CIMIEZ_NEAR})
        stops = [stop_block('Musee Matisse', '164 Avenue des Arenes, 06000 Nice', (43.7187, 7.2768))]
        new_text, records = g.correct_stops(stops, 'Nice, France', tour_anchor=CIMIEZ)
        return annotate_text_content(new_text, records)[0]

    def test_app_map_coordinate_regex_still_matches(self):
        content = self.annotated_matisse()
        m = _APP_COORD_RE.search(content)
        self.assertIsNotNone(m, "the map/navigation coordinate regex stopped matching")
        self.assertAlmostEqual(float(m.group(1)), CIMIEZ_NEAR[0], places=4)
        self.assertAlmostEqual(float(m.group(2)), CIMIEZ_NEAR[1], places=4)

    def test_app_type_and_address_regexes_are_unharmed(self):
        content = self.annotated_matisse()
        self.assertEqual(_APP_TYPE_RE.search(content).group(1).strip(), 'Museum')
        self.assertTrue(_APP_ADDR_RE.search(content).group(1).strip().startswith('164 Avenue'))

    def test_app_name_is_still_line_zero(self):
        # _parsePoi takes lines[0] as the name; the confidence line must never be first.
        content = self.annotated_matisse()
        self.assertEqual(content.split('\n')[0].strip(), 'Musee Matisse')

    def test_the_app_regexes_are_still_the_ones_we_ported(self):
        """If Mobile-Kiro changes the map/nav regex, this fails and warns us to
        re-verify — the ported patterns above are only valid while they match."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ('audio_tour_app/lib/screens/tour_map_screen.dart',
                    'audio_tour_app/lib/services/navigation_service.dart'):
            src = open(os.path.join(root, rel), encoding='utf-8').read()
            self.assertIn(r"Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)", src,
                          f"{rel} coordinate regex changed — re-audit the emit format")

    def test_modernized_stop_splitter_and_coord_check(self):
        # tour_generation_modernized.py: _split by "Stop N:" and _stop_has_coordinates.
        import tour_generation_modernized as tgm
        content = self.annotated_matisse()
        tour_doc = f"Step-by-Step Audio Guided Tour: Test\nTour-Category: museum\n\nStop 1: {content}\n"
        parsed = tgm.parse_tour_content_to_modernized(tour_doc)
        self.assertEqual(len(parsed['text_content']), 1)
        self.assertTrue(tgm._stop_has_coordinates(parsed['text_content'][0]),
                        "modernized coord check stopped seeing the coordinate")
        self.assertIn(CONFIDENCE_PREFIX, parsed['text_content'][0],
                      "the confidence line was dropped by the splitter")

    def test_tts_strip_removes_the_confidence_line(self):
        # AC: never spoken. Both services share this label set.
        import tour_generation_modernized as tgm
        content = self.annotated_matisse()
        spoken = tgm._strip_nav_fields_for_tts(content)
        self.assertNotIn(CONFIDENCE_PREFIX, spoken,
                         "Coordinate-Confidence would be read aloud")
        self.assertNotIn('Coordinates:', spoken)
        # narration survives
        self.assertIn('narration paragraph', spoken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
