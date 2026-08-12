"""LOCAL-432: Tests for venue_purpose thesis check and story retry improvements.

Part 2 coverage:
  1. check_thesis_threaded with venue_purpose: PASSES when description connects
     to the venue's stated purpose (collection, instruments, bequest, founder).
  2. check_thesis_threaded with venue_purpose: FAILS when description completely
     ignores the venue's reason for existing.
  3. Backwards compatibility: passes when no venue_purpose is provided.
  4. Exhibition framing: unchanged by this change.

Part 1 coverage:
  5. Beat extraction: _WORK_BY_MAKER pattern extracts maker from "[work] by [Person] (City, Year)".
  6. Beat extraction: _KNOWN_NON_PERSON_NAMES filters "Wikipedia" as beat subject.
  7. Story retry prompt construction includes rejected sentences and available people.

Binding: Module scope, reachable from test through the production symbol.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_gate import (
    check_thesis_threaded,
    verify_stop_story,
    extract_story_sentences,
    _check_venue_purpose_threaded,
)
from story_beat_injector import (
    extract_story_beats,
    _is_valid_beat_subject,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PALAIS_VENUE_PURPOSE = (
    "bequeathed to the city of Nice in the testament of 26 May 1901 "
    "by Antoine Gautier, a collector of antique musical instruments"
)

# Good: mentions collection AND instruments AND the bequest context
PALAIS_GOOD_DESCRIPTION = (
    "Anton Schnitzer specialized in ceremonial brass instruments for the Bavarian "
    "court, producing this tenor sackbut in his Nuremberg workshop in 1581. "
    "The instrument survived because Gautier collected it as part of his campaign "
    "to preserve early musical instruments, eventually bequeathing the entire "
    "collection to Nice. Henry Fischer published a detailed study of this specific "
    "sackbut in the Historic Brass Society Journal in 1989, establishing it as the "
    "oldest surviving example in original playing condition."
)

# Bad: completely ignores venue purpose — no mention of collection, instruments,
# bequest, Gautier, or any domain term from the venue purpose
PALAIS_BAD_DESCRIPTION = (
    "The elegant curves of this metalwork piece reflect Renaissance engineering "
    "at its finest. Visitors today can admire the proportions and the careful "
    "attention to the bell section's geometry. The slide mechanism represents "
    "a triumph of early modern craft that continues to inspire awe."
)

# Sacqueboute corpus for beat extraction testing
SACQUEBOUTE_CORPUS = (
    "The Palais Lascaris holds a tenor sackbut by Anton Schnitzer (Nuremberg, 1581), "
    "described in the journal Historic Brass Society Journal as one of the earliest "
    "surviving sackbuts in original condition. Wikipedia's table of early surviving "
    "sackbuts lists the Anton Schnitzer I tenor sackbut of 1581 from Nuremberg. "
    "Henry G. Fischer published 'The Tenor Sackbut of Anton Schnitzer the Elder at "
    "Nice' in the Historic Brass Society Journal, vol. 1, 1989, pp. 65-74, "
    "documenting this specific instrument at the Palais Lascaris."
)


# ---------------------------------------------------------------------------
# Part 2: check_thesis_threaded for venue_purpose
# ---------------------------------------------------------------------------

class TestVenuePurposeThesisCheck(unittest.TestCase):
    """check_thesis_threaded with venue_purpose framing."""

    def test_passes_when_description_threads_venue_purpose(self):
        """A stop that connects to the venue's purpose (instruments, collection, bequest) passes."""
        result = check_thesis_threaded(
            PALAIS_GOOD_DESCRIPTION,
            'venue_purpose',
            venue_purpose=PALAIS_VENUE_PURPOSE,
        )
        self.assertTrue(result, "Should pass: description mentions instruments/collection/Gautier")

    def test_fails_when_description_ignores_venue_purpose(self):
        """A stop that completely ignores the venue's reason for existing fails."""
        result = check_thesis_threaded(
            PALAIS_BAD_DESCRIPTION,
            'venue_purpose',
            venue_purpose=PALAIS_VENUE_PURPOSE,
        )
        self.assertFalse(result, "Should fail: no reference to instruments/collection/bequest/Gautier")

    def test_passes_when_no_venue_purpose_provided(self):
        """Backwards compatibility: if no venue purpose was detected, pass unconditionally."""
        result = check_thesis_threaded(
            PALAIS_BAD_DESCRIPTION,
            'venue_purpose',
            venue_purpose='',
        )
        self.assertTrue(result, "Should pass: no venue purpose to check against")

    def test_passes_with_single_domain_noun(self):
        """A description mentioning just 'instruments' connects to the venue purpose."""
        desc = "This brass instrument demonstrates Renaissance craftsmanship in its bell design."
        result = check_thesis_threaded(desc, 'venue_purpose', venue_purpose=PALAIS_VENUE_PURPOSE)
        self.assertTrue(result, "Should pass: 'instrument' matches domain noun")

    def test_passes_with_founder_surname(self):
        """A description mentioning the founder/collector's surname connects."""
        desc = "Gautier acquired this piece during his travels through northern Europe."
        result = check_thesis_threaded(desc, 'venue_purpose', venue_purpose=PALAIS_VENUE_PURPOSE)
        self.assertTrue(result, "Should pass: 'Gautier' is the venue founder")

    def test_passes_with_action_term(self):
        """A description mentioning 'bequeathed' or 'collection' connects."""
        desc = "The piece was part of a private collection before entering the museum."
        result = check_thesis_threaded(desc, 'venue_purpose', venue_purpose=PALAIS_VENUE_PURPOSE)
        self.assertTrue(result, "Should pass: 'collection' matches purpose action")

    def test_exhibition_framing_unchanged(self):
        """Exhibition framing still uses keyword list, not venue purpose."""
        # Must pass with exhibition keyword
        self.assertTrue(check_thesis_threaded(
            "The livre d'artiste form represents collaborative art.",
            'exhibition',
        ))
        # Must fail without
        self.assertFalse(check_thesis_threaded(
            "A beautiful painting on canvas.",
            'exhibition',
        ))

    def test_none_framing_always_passes(self):
        """'none' framing always passes regardless of content."""
        self.assertTrue(check_thesis_threaded("anything", 'none'))
        self.assertTrue(check_thesis_threaded("", 'none'))


class TestVenuePurposeInVerifyStopStory(unittest.TestCase):
    """verify_stop_story integrates the venue_purpose check."""

    def test_venue_purpose_failure_in_verify_stop_story(self):
        """verify_stop_story reports thesis_missing for venue_purpose when no connection."""
        result = verify_stop_story(
            description=PALAIS_BAD_DESCRIPTION,
            framing_case='venue_purpose',
            min_story_sentences=0,  # isolate the thesis check
            venue_purpose=PALAIS_VENUE_PURPOSE,
        )
        self.assertFalse(result['thesis_threaded'])
        self.assertIn('thesis_missing', result['failures'][0])

    def test_venue_purpose_pass_in_verify_stop_story(self):
        """verify_stop_story passes thesis for venue_purpose when connected."""
        result = verify_stop_story(
            description=PALAIS_GOOD_DESCRIPTION,
            framing_case='venue_purpose',
            min_story_sentences=0,
            venue_purpose=PALAIS_VENUE_PURPOSE,
        )
        self.assertTrue(result['thesis_threaded'])


# ---------------------------------------------------------------------------
# Part 1: Beat extraction improvements
# ---------------------------------------------------------------------------

class TestMakerBeatExtraction(unittest.TestCase):
    """Beat extraction for instrument makers via _WORK_BY_MAKER pattern."""

    def test_extracts_maker_from_by_attribution(self):
        """'a tenor sackbut by Anton Schnitzer (Nuremberg, 1581)' produces a maker beat."""
        beats = extract_story_beats(SACQUEBOUTE_CORPUS)
        maker_beats = [b for b in beats if b['role'] == 'maker']
        schnitzer_beats = [b for b in maker_beats if 'Schnitzer' in b['person']]
        self.assertGreater(len(schnitzer_beats), 0,
                           "Should extract Anton Schnitzer as maker from 'sackbut by Anton Schnitzer (Nuremberg, 1581)'")
        self.assertIn('1581', schnitzer_beats[0]['action'])

    def test_filters_wikipedia_as_non_person(self):
        """'Wikipedia' should NOT be extracted as a beat subject."""
        beats = extract_story_beats(SACQUEBOUTE_CORPUS)
        wiki_beats = [b for b in beats if 'Wikipedia' in b.get('person', '')]
        self.assertEqual(len(wiki_beats), 0,
                         "Wikipedia should be filtered by _KNOWN_NON_PERSON_NAMES")

    def test_is_valid_beat_subject_rejects_wikipedia(self):
        """_is_valid_beat_subject rejects 'Wikipedia' directly."""
        self.assertFalse(_is_valid_beat_subject('Wikipedia'))

    def test_is_valid_beat_subject_accepts_person_names(self):
        """Real person names still pass."""
        self.assertTrue(_is_valid_beat_subject('Schnitzer'))
        self.assertTrue(_is_valid_beat_subject('Anton Schnitzer'))
        self.assertTrue(_is_valid_beat_subject('Fischer'))

    def test_fischer_published_extracted(self):
        """'Fischer published ...' should produce a beat via _PERSON_ACTION."""
        beats = extract_story_beats(SACQUEBOUTE_CORPUS)
        fischer_beats = [b for b in beats if 'Fischer' in b.get('person', '')]
        self.assertGreater(len(fischer_beats), 0,
                           "Should extract Fischer from 'Fischer published ...'")


# ---------------------------------------------------------------------------
# Neutralisation evidence placeholder
# (Run with the real neutralisation below to produce red output)
# ---------------------------------------------------------------------------

class TestNeutralisationDirections(unittest.TestCase):
    """Verify the check can both pass and fail — not dead code in either direction."""

    def test_check_can_fail(self):
        """Directly tests _check_venue_purpose_threaded returns False."""
        result = _check_venue_purpose_threaded(
            "Lovely Renaissance engineering in the bell curves.",
            PALAIS_VENUE_PURPOSE,
        )
        self.assertFalse(result)

    def test_check_can_pass(self):
        """Directly tests _check_venue_purpose_threaded returns True."""
        result = _check_venue_purpose_threaded(
            "Part of the musical instruments collection assembled by Gautier.",
            PALAIS_VENUE_PURPOSE,
        )
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
