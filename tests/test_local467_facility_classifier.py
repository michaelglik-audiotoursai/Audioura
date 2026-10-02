"""test_local467_facility_classifier.py — LOCAL-467: Gallery attribution fixes.

Tests:
  1. Facility-vs-person classifier: Linde Family Gallery, Torf Gallery,
     Boris Fridman, Louis Broder, The Hogarth Press, Éditions Verve.
  2. Narrowed pre_grounded_names exemption: exhibition_wide beat does NOT
     ground a claim about one specific work.
  3. Ordinary prose that must produce nothing (D316 standing lesson).
  4. Facility conflict detection.
  5. is_facility_name with source-text context.

D316 family: France (person), The Treat Page (person), visual tapestry (form),
', in' (quantity). LOCAL-393 fixed France; LOCAL-467 generalises the family.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prose_entity_grounding_gate import (
    _looks_like_person_name,
    apply_prose_entity_grounding_gate,
    check_facility_conflicts,
    extract_person_names,
    is_facility_name,
)


class TestFacilityClassifier(unittest.TestCase):
    """[LOCAL-467] Fix 1: A gallery is not a person."""

    def test_linde_family_gallery_is_facility(self):
        """'Linde Family Gallery' should NOT be a person name."""
        # The full string 'Linde Family Gallery' has 'Gallery' which is caught
        # by _ORG_MARKER_RE. But 'Linde Family' alone (as extracted by _NAMED_SPACE)
        # must also be caught — by the facility precursor check.
        self.assertFalse(_looks_like_person_name('Linde Family Gallery'))
        self.assertFalse(_looks_like_person_name('Linde Family'))
        self.assertTrue(is_facility_name('Linde Family'))
        self.assertTrue(is_facility_name('Linde Family Gallery'))

    def test_torf_gallery_is_facility(self):
        """'Torf Gallery' should NOT be a person name."""
        self.assertFalse(_looks_like_person_name('Torf Gallery'))
        self.assertTrue(is_facility_name('Torf Gallery'))

    def test_boris_fridman_is_person(self):
        """'Boris Fridman' IS a person — the regression that matters (acceptance #3)."""
        self.assertTrue(_looks_like_person_name('Boris Fridman'))
        self.assertFalse(is_facility_name('Boris Fridman'))

    def test_louis_broder_is_person(self):
        """'Louis Broder' IS a person."""
        self.assertTrue(_looks_like_person_name('Louis Broder'))
        self.assertFalse(is_facility_name('Louis Broder'))

    def test_the_hogarth_press_is_org(self):
        """'The Hogarth Press' is an organisation, not a person.

        Caught by _ORG_MARKER_RE (contains 'Press').
        """
        # 'The' is a non-name opener, so it fails on that first
        self.assertFalse(_looks_like_person_name('The Hogarth Press'))
        # Without 'The':
        self.assertFalse(_looks_like_person_name('Hogarth Press'))

    def test_editions_verve_is_org(self):
        """'Éditions Verve' is an organisation, not a person.

        Caught by _ORG_MARKER_RE (contains 'Éditions').
        """
        self.assertFalse(_looks_like_person_name('Éditions Verve'))

    def test_facility_precursor_words(self):
        """Words that commonly precede facility words are caught."""
        # 'Family' is a facility precursor
        self.assertTrue(is_facility_name('Koch Family'))
        self.assertTrue(is_facility_name('Sackler Family'))
        # 'Memorial' is a facility precursor
        self.assertTrue(is_facility_name('Veterans Memorial'))

    def test_context_aware_facility_detection(self):
        """is_facility_name uses source text to detect facility context."""
        # With context: 'Koch' followed by 'Gallery'
        self.assertTrue(is_facility_name('Koch', 'displayed in the Koch Gallery today'))
        # Without relevant context: 'Koch' alone
        self.assertFalse(is_facility_name('Koch', 'Robert Koch discovered tuberculosis'))
        # 'Koch' with no context
        self.assertFalse(is_facility_name('Koch'))

    def test_person_names_not_in_facility(self):
        """Real person names must not be falsely classified as facilities."""
        for name in ['Pierre Reverdy', 'Juan Gris', 'Salvador Dalí',
                     'Sigmund Freud', 'Pablo Picasso', 'Joan Miró']:
            self.assertFalse(is_facility_name(name), f"{name} wrongly classified as facility")
            self.assertTrue(_looks_like_person_name(name), f"{name} not recognised as person")


class TestNarrowedExemption(unittest.TestCase):
    """[LOCAL-467] Fix 2: pre_grounded_names proves EXISTENCE, not RELATION."""

    def setUp(self):
        """Common fixtures for exemption tests."""
        self.poi_list = [{
            'name': 'Le Lézard aux plumes d\'or',
            'description': (
                "Published by Louis Broder in Paris, this edition represents "
                "a landmark in livre d'artiste printing. Boris Fridman donated "
                "the copy to the museum."
            ),
        }]

        class MockResult:
            # Page text does NOT mention Broder or Fridman
            page_text = "An exhibition of livres d'artiste by Spanish artists."
            works = [{'artist': 'Miró'}]

        self.mock_result = MockResult()

    def test_exhibition_wide_beat_does_not_bypass(self):
        """An exhibition_wide beat does NOT ground a claim about one specific work.

        This is the core of the bug: 'Linde Family' was marked exhibition_wide
        by LOCAL-392 and the pre-grounded exemption still let it through.
        """
        poi_copy = copy.deepcopy(self.poi_list)
        stats = apply_prose_entity_grounding_gate(
            poi_copy, self.mock_result,
            stop_names=["Le Lézard aux plumes d'or"],
            pre_grounded_names=[{
                'person': 'Louis Broder',
                'source_work_index': None,  # exhibition_wide
                'exhibition_wide': True,
                'stop_index': 0,
            }],
        )
        # Broder is ungrounded (not in page text, not in artist names,
        # and the exhibition_wide exemption doesn't apply)
        self.assertIn('Louis Broder', stats['ungrounded_names'],
                      "exhibition_wide beat should NOT bypass grounding check")

    def test_correct_stop_beat_still_grounds(self):
        """A beat attributed to the correct stop still gets the exemption."""
        poi_copy = copy.deepcopy(self.poi_list)
        stats = apply_prose_entity_grounding_gate(
            poi_copy, self.mock_result,
            stop_names=["Le Lézard aux plumes d'or"],
            pre_grounded_names=[{
                'person': 'Louis Broder',
                'source_work_index': 0,  # stop 1
                'exhibition_wide': False,
                'stop_index': 0,
            }, {
                'person': 'Boris Fridman',
                'source_work_index': 0,
                'exhibition_wide': False,
                'stop_index': 0,
            }],
        )
        # Both are pre-grounded for stop 0 where they appear
        self.assertEqual(stats['persons_ungrounded'], 0,
                         "Beats grounded for correct stop should bypass")
        self.assertIn('Louis Broder', poi_copy[0]['description'])
        self.assertIn('Boris Fridman', poi_copy[0]['description'])

    def test_wrong_stop_beat_does_not_ground(self):
        """A beat for stop 2 does NOT ground a name appearing in stop 1."""
        poi_copy = copy.deepcopy(self.poi_list)
        stats = apply_prose_entity_grounding_gate(
            poi_copy, self.mock_result,
            stop_names=["Le Lézard aux plumes d'or"],
            pre_grounded_names=[{
                'person': 'Louis Broder',
                'source_work_index': 2,  # stop 3 — wrong stop
                'exhibition_wide': False,
                'stop_index': 2,
            }],
        )
        # Broder appears in stop 0 but is only grounded for stop 2
        self.assertIn('Louis Broder', stats['ungrounded_names'],
                      "Beat for wrong stop should NOT bypass grounding check")

    def test_legacy_string_format_still_works(self):
        """Legacy pre_grounded_names as List[str] still provides unconditional bypass."""
        poi_copy = copy.deepcopy(self.poi_list)
        stats = apply_prose_entity_grounding_gate(
            poi_copy, self.mock_result,
            stop_names=["Le Lézard aux plumes d'or"],
            pre_grounded_names=['Louis Broder', 'Boris Fridman'],
        )
        # Legacy format: unconditional bypass
        self.assertEqual(stats['persons_ungrounded'], 0)
        self.assertIn('Louis Broder', poi_copy[0]['description'])
        self.assertIn('Boris Fridman', poi_copy[0]['description'])


class TestFacilityConflict(unittest.TestCase):
    """[LOCAL-467] Fix 3: Do not silently discard the right answer."""

    def test_conflict_detected_when_stop_claims_wrong_gallery(self):
        """A stop claiming 'Linde Family Gallery' when exhibition says 'Torf' is a conflict."""
        poi_list = [{
            'name': "Le Lézard aux plumes d'or",
            'description': "This work hangs in the Linde Family Gallery at the MFA.",
        }]
        facility_beats = [{
            'person': 'Torf',
            'source_work_index': None,
            'exhibition_wide': True,
        }]
        conflicts = check_facility_conflicts(poi_list, facility_beats)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['stop_index'], 0)
        self.assertIn('Linde Family', conflicts[0]['claimed_facility'])
        self.assertEqual(conflicts[0]['exhibition_facility'], 'Torf')

    def test_no_conflict_when_correct_gallery(self):
        """A stop naming the correct gallery produces no conflict."""
        poi_list = [{
            'name': "Le Lézard aux plumes d'or",
            'description': "This work hangs in the Torf Gallery at the MFA.",
        }]
        facility_beats = [{
            'person': 'Torf',
            'source_work_index': None,
            'exhibition_wide': True,
        }]
        conflicts = check_facility_conflicts(poi_list, facility_beats)
        self.assertEqual(len(conflicts), 0)

    def test_no_conflict_when_no_gallery_mentioned(self):
        """A stop that names no gallery at all is not a conflict."""
        poi_list = [{
            'name': "Le Lézard aux plumes d'or",
            'description': "This luminous book contains forty lithographs.",
        }]
        facility_beats = [{
            'person': 'Torf',
            'source_work_index': None,
            'exhibition_wide': True,
        }]
        conflicts = check_facility_conflicts(poi_list, facility_beats)
        self.assertEqual(len(conflicts), 0)


class TestOrdinaryProse(unittest.TestCase):
    """[LOCAL-467] D316 standing lesson: ordinary prose must produce nothing.

    The classifier must not fire on normal English text that happens to contain
    capitalised words at sentence starts, titles, or common patterns.
    """

    def test_ordinary_prose_no_facility_names(self):
        """Ordinary prose without facility names yields no facility classification."""
        ordinary = (
            "The painting shows a woman reading a letter by a window. "
            "Light falls across the table, illuminating the paper she holds. "
            "Vermeer painted this around 1657 in Delft."
        )
        for word in ordinary.split():
            if word[0].isupper() and len(word) > 2:
                # No word in ordinary prose should trigger facility detection
                # (unless it actually IS a facility word)
                if word.lower() not in ('the', 'light', 'vermeer'):
                    pass  # just checking we don't crash

        persons = extract_person_names(ordinary)
        # Only real person names should be found
        for p in persons:
            self.assertFalse(is_facility_name(p),
                             f"'{p}' wrongly classified as facility in ordinary prose")

    def test_no_false_facility_on_family_surname(self):
        """A person named 'Family' as a surname would be unusual but the test
        confirms we don't fire on normal multi-word names containing 'family'
        ONLY when 'Family' is the last word of a standalone candidate.

        'The Royal Family' is not a person (starts with article).
        'Smith Family' IS classified as facility-precursor (ends with Family).
        But this is correct — 'Smith Family' in museum context almost always
        means 'Smith Family Gallery/Wing/Room'.
        """
        # 'The Royal Family' — starts with 'The', fails non-name opener check
        self.assertFalse(_looks_like_person_name('The Royal Family'))
        # 'Smith Family' — this is correctly classified as a facility name
        self.assertTrue(is_facility_name('Smith Family'))
        self.assertFalse(_looks_like_person_name('Smith Family'))

    def test_extract_persons_from_clean_prose_no_facilities(self):
        """Extract person names from clean art prose — no facilities should appear."""
        prose = (
            "Pablo Picasso and Georges Braque developed Cubism together in Paris. "
            "Their work in the Torf Gallery represents a pivotal moment. "
            "The Koch Family Wing also houses important pieces by Juan Gris. "
            "Boris Fridman later donated his collection to the museum."
        )
        persons = extract_person_names(prose)
        # Should find real persons
        person_set = set(persons)
        self.assertIn('Pablo Picasso', person_set)
        self.assertIn('Georges Braque', person_set)
        self.assertIn('Boris Fridman', person_set)
        # Should NOT find facility names
        self.assertNotIn('Torf Gallery', person_set)
        self.assertNotIn('Koch Family', person_set)
        self.assertNotIn('Koch Family Wing', person_set)


class TestBeatExtractionNoLinde(unittest.TestCase):
    """[LOCAL-467] Linde Family must not appear in the named_people list."""

    def test_linde_family_not_in_beats(self):
        """extract_story_beats must NOT produce 'Linde Family' as a person beat."""
        from story_beat_injector import extract_story_beats
        # Use the standard MFA page text fixture
        from tests.test_local390_beat_verification import MFA_PAGE_TEXT

        beats = extract_story_beats(MFA_PAGE_TEXT)
        person_names = [b['person'] for b in beats if b['role'] not in ('circumstance', 'stakes')]
        self.assertNotIn('Linde Family', person_names,
                         "Linde Family must not appear as a person beat")

    def test_boris_fridman_still_in_beats(self):
        """Boris Fridman MUST still be extracted — this is the regression that matters."""
        from story_beat_injector import extract_story_beats
        from tests.test_local390_beat_verification import MFA_PAGE_TEXT

        beats = extract_story_beats(MFA_PAGE_TEXT)
        person_names = [b['person'] for b in beats if b['role'] not in ('circumstance', 'stakes')]
        self.assertIn('Boris Fridman', person_names,
                      "Boris Fridman must still be extracted as a donor beat")

    def test_louis_broder_still_in_beats(self):
        """Louis Broder MUST still be extracted as a publisher beat."""
        from story_beat_injector import extract_story_beats
        from tests.test_local390_beat_verification import MFA_PAGE_TEXT

        beats = extract_story_beats(MFA_PAGE_TEXT)
        person_names = [b['person'] for b in beats if b['role'] not in ('circumstance', 'stakes')]
        self.assertIn('Louis Broder', person_names,
                      "Louis Broder must still be extracted as a publisher beat")


if __name__ == '__main__':
    unittest.main()
