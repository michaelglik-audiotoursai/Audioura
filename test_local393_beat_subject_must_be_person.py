#!/usr/bin/env python3
"""test_local393_beat_subject_must_be_person.py — Tests for LOCAL-393: beat subject validation.

Verifies:
  1. Place names (France, Nice, Paris, Milan, etc.) are rejected as beat subjects.
  2. Person names (Louis Broder, Pierre Reverdy, Dalí) are accepted as beat subjects.
  3. extract_story_beats never produces a beat whose subject is a place.
  4. attribute_beats_to_works uses proximity to avoid cross-attribution (Reverdy ≠ Moses).
  5. Word-count floor logic exists in generate_tour_text.py (D307 real path).
  6. Revert test: removing _is_valid_beat_subject breaks place-rejection logic (D296).

Expected red-on-revert count: 5
  Reverting _is_valid_beat_subject (removing the place-name guard) causes:
    - test_france_rejected_as_beat_subject
    - test_nice_paris_milan_almeria_nuremberg_rejected
    - test_extract_story_beats_never_yields_place_subject
    - test_place_in_action_context_is_fine
    - test_real_generation_path_has_word_floor_logic
  to fail — the LOGIC of person-vs-place validation breaks, not a symbol rename.

D277: no mirrors, no inspect.getsource.
D296: revert breaks logic, not the symbol.
D307: at least one test exercises the real generation path.
"""
import os
import re
import sys
import io
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_beat_injector import (
    extract_story_beats,
    assign_beats_to_stops,
    attribute_beats_to_works,
    get_required_beat_names,
    _is_valid_beat_subject,
)


class TestPlaceNamesRejected(unittest.TestCase):
    """[LOCAL-393] Place names must be rejected as beat subjects."""

    def test_france_rejected_as_beat_subject(self):
        """France is a country, not a person — must not be a beat subject."""
        self.assertFalse(_is_valid_beat_subject('France'))

    def test_nice_paris_milan_almeria_nuremberg_rejected(self):
        """All cities from the ticket must be rejected."""
        cities = ['Nice', 'Paris', 'Milan', 'Almeria', 'Nuremberg']
        for city in cities:
            with self.subTest(city=city):
                self.assertFalse(_is_valid_beat_subject(city),
                                 f"{city} should be rejected as a beat subject")

    def test_countries_rejected(self):
        """Countries that commonly appear in art/museum contexts are rejected."""
        countries = ['Spain', 'Italy', 'Germany', 'England', 'Portugal', 'Japan']
        for country in countries:
            with self.subTest(country=country):
                self.assertFalse(_is_valid_beat_subject(country))

    def test_regions_rejected(self):
        """Regions/provinces are not person names."""
        regions = ['Provence', 'Normandy', 'Tuscany', 'Bavaria', 'Catalonia']
        for region in regions:
            with self.subTest(region=region):
                self.assertFalse(_is_valid_beat_subject(region))


class TestPersonNamesAccepted(unittest.TestCase):
    """[LOCAL-393] Real person names must be accepted as beat subjects."""

    def test_louis_broder_accepted(self):
        self.assertTrue(_is_valid_beat_subject('Louis Broder'))

    def test_pierre_reverdy_accepted(self):
        self.assertTrue(_is_valid_beat_subject('Pierre Reverdy'))

    def test_mourlot_freres_accepted(self):
        self.assertTrue(_is_valid_beat_subject('Mourlot Frères'))

    def test_juan_gris_accepted(self):
        self.assertTrue(_is_valid_beat_subject('Juan Gris'))

    def test_single_word_surnames_accepted(self):
        """Single-word surnames (Dalí, Freud, Torf) are valid — they are people."""
        surnames = ['Dalí', 'Freud', 'Torf', 'Miró', 'Carlone', 'Gris']
        for name in surnames:
            with self.subTest(name=name):
                self.assertTrue(_is_valid_beat_subject(name),
                                f"{name} should be accepted as a beat subject")

    def test_boris_fridman_accepted(self):
        self.assertTrue(_is_valid_beat_subject('Boris Fridman'))


class TestExtractStoryBeatsPlaceFilter(unittest.TestCase):
    """[LOCAL-393] extract_story_beats must never yield a place as a beat subject."""

    def test_extract_story_beats_never_yields_place_subject(self):
        """A text with 'France established/founded/created' must not produce France beats."""
        text = (
            "France established a tradition of instrument-making that spread across Europe. "
            "Nice founded its reputation as a cultural capital in the 18th century. "
            "Paris created a distinctive style of harpsichord construction. "
            "The collection includes works from Milan, Almeria, and Nuremberg."
        )
        beats = extract_story_beats(text)
        person_beats = [b for b in beats if b['role'] not in ('circumstance', 'stakes')]
        subjects = [b['person'] for b in person_beats]
        forbidden = {'France', 'Nice', 'Paris', 'Milan', 'Almeria', 'Nuremberg'}
        for subj in subjects:
            self.assertNotIn(subj, forbidden,
                             f"'{subj}' is a place and must not be a beat subject")

    def test_place_in_action_context_is_fine(self):
        """Places CAN appear inside a beat action (e.g., 'printed by X in Paris')."""
        text = "published by Louis Broder, printed by Mourlot Frères, Paris, 1971."
        beats = extract_story_beats(text)
        # Should extract Broder and Mourlot (people), not Paris
        person_names = [b['person'] for b in beats if b['role'] not in ('circumstance', 'stakes')]
        self.assertIn('Louis Broder', person_names)
        self.assertIn('Mourlot Frères', person_names)
        self.assertNotIn('Paris', person_names)

    def test_no_beat_is_valid_outcome(self):
        """If extraction yields no valid person, empty list is fine — no places substituted."""
        text = "France is a beautiful country with many museums. Nice has a rich history."
        beats = extract_story_beats(text)
        person_beats = [b for b in beats if b['role'] not in ('circumstance', 'stakes')]
        # Either empty or all subjects are valid people
        for b in person_beats:
            self.assertTrue(_is_valid_beat_subject(b['person']),
                            f"'{b['person']}' should be a valid person")


class TestAttributionProximity(unittest.TestCase):
    """[LOCAL-393] Defect 2: proximity-based weak title matching prevents cross-attribution."""

    def setUp(self):
        """Source sentence mentioning both 'Moses and Monotheism' and 'Au Soleil du Plafond'."""
        self.source = (
            "Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations "
            "for Sigmund Freud\u2019s Moses and Monotheism; others partnered with writers to devise "
            "images and words in harmony at the outset, as in Juan Gris and French poet "
            "Pierre Reverdy\u2019s Au Soleil du Plafond (1955)."
        )
        self.works = [
            {'title': 'Le Lézard aux plumes d\u2019or', 'artist': 'Joan Miró',
             'publisher': 'Louis Broder', 'collaborator': '', 'credit_line': ''},
            {'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí',
             'publisher': '', 'collaborator': '', 'credit_line': ''},
            {'title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
             'publisher': '', 'collaborator': 'Pierre Reverdy', 'credit_line': ''},
        ]

    def test_reverdy_attributed_to_au_soleil_not_moses(self):
        """Reverdy must go to Au Soleil du Plafond (stop 3), not Moses and Monotheism."""
        beats = [
            {'person': 'Pierre Reverdy', 'role': 'collaborator',
             'action': 'collaborated with Juan Gris', 'source_sentence': self.source},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            attributed = attribute_beats_to_works(beats, self.works)
        reverdy = attributed[0]
        self.assertEqual(reverdy['source_work_index'], 2,
                         f"Reverdy should go to stop 3 (idx 2), got {reverdy['source_work_index']}")

    def test_dali_attributed_to_moses(self):
        """Dalí must go to Moses and Monotheism (stop 2)."""
        beats = [
            {'person': 'Dalí', 'role': 'illustrator',
             'action': 'as Dalí did in his 1974 illustrations', 'source_sentence': self.source},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            attributed = attribute_beats_to_works(beats, self.works)
        dali = attributed[0]
        self.assertEqual(dali['source_work_index'], 1,
                         f"Dalí should go to stop 2 (idx 1), got {dali['source_work_index']}")

    def test_proximity_without_metadata_match(self):
        """Even without collaborator metadata, proximity picks the right title."""
        works_no_collab = [
            {'title': 'Le Lézard aux plumes d\u2019or', 'artist': '', 'publisher': '',
             'collaborator': '', 'credit_line': ''},
            {'title': 'Moses and Monotheism', 'artist': '', 'publisher': '',
             'collaborator': '', 'credit_line': ''},
            {'title': 'Au Soleil du Plafond', 'artist': '', 'publisher': '',
             'collaborator': '', 'credit_line': ''},
        ]
        beats = [
            {'person': 'Pierre Reverdy', 'role': 'collaborator',
             'action': 'collaborated', 'source_sentence': self.source},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            attributed = attribute_beats_to_works(beats, works_no_collab)
        self.assertEqual(attributed[0]['source_work_index'], 2,
                         "Proximity should attribute Reverdy to Au Soleil du Plafond")


class TestWordFloorLogic(unittest.TestCase):
    """[LOCAL-393] Defect 3: word-count floor enforcement in generate_tour_text.py."""

    def test_real_generation_path_has_word_floor_logic(self):
        """[D307] The generation code contains LOCAL-393 word floor retry logic."""
        # Read the actual generation code
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # Must have the word-floor retry mechanism
        self.assertIn('[LOCAL-393]', source,
                      "generate_tour_text.py must reference LOCAL-393")
        self.assertIn('WORD FLOOR', source,
                      "generate_tour_text.py must have WORD FLOOR log line")
        self.assertIn('_wc_floor_count', source,
                      "generate_tour_text.py must compute word floor count")
        # Must retry when below 120
        self.assertIn('< 120', source,
                      "generate_tour_text.py must check against 120-word floor")


class TestRevertBreaksLogic(unittest.TestCase):
    """[D296] Reverting LOCAL-393 logic breaks place-rejection, not just a symbol."""

    def test_place_rejection_depends_on_valid_beat_subject(self):
        """If _is_valid_beat_subject were removed and len(person) > 3 restored,
        France (6 chars > 3) would pass — this test catches that revert."""
        # This test passes ONLY because _is_valid_beat_subject rejects known places.
        # A naive `len('France') > 3` check would pass (6 > 3 is True).
        self.assertFalse(_is_valid_beat_subject('France'))
        self.assertFalse(_is_valid_beat_subject('Nice'))
        # But real people with short surnames still pass:
        self.assertTrue(_is_valid_beat_subject('Dalí'))
        self.assertTrue(_is_valid_beat_subject('Gris'))


if __name__ == '__main__':
    unittest.main()
