"""LOCAL-532 — the same EVENT told twice, even when the dates differ or are absent.

The kiro critic on LOGAN_1 (round 7), 2026-09-23: "Lindbergh appears in two of four
stops - the file tells its single best anecdote twice." Verified against the real
file, and the critic undercounted — Lindbergh is in stops 1, 3 AND 4. The two BODY
tellings are one landing told twice:

  stop 3  "...Charles Lindbergh once touched down..."        (no year in-sentence)
  stop 4  "In 1927, ...Charles Lindbergh landed the Spirit of St. Louis here..."

`_same_episode` (person AND year) misses it because stop 3's telling carries no
year. `cap_person_across_stops` (D584) permits it because Lindbergh is in exactly
two BODY stops, which is D584's allowance. The unit repeated is an EVENT — one
person + one action-class — and `_same_event` catches it while the year still acts
as a SEPARATOR so two genuinely different dated events by one person stay distinct.
"""
import os
import re

from derepetition_guard import (
    _event_key,
    _same_event,
    strip_cross_stop_repeats,
    _split_into_sentences,
)


def _pois(*descriptions):
    return [{'name': f'Stop {i + 1}', 'description': d}
            for i, d in enumerate(descriptions)]


# --- unit: _same_event discrimination ---------------------------------------

def test_same_event_matches_when_only_one_telling_is_dated():
    """The LOGAN_1 shape: same actor, same action-class, a year on only one side."""
    a = _event_key('Charles Lindbergh touched down here.')
    b = _event_key('In 1927 Charles Lindbergh landed the Spirit of St. Louis here.')
    assert _same_event(a, b)


def test_same_event_matches_when_neither_telling_is_dated():
    a = _event_key('Charles Lindbergh touched down on the tarmac here.')
    b = _event_key('Charles Lindbergh landed at this airport.')
    assert _same_event(a, b)


def test_different_years_are_two_events_not_one():
    """A person legitimately appears for two DATED events — do not collapse them.

    This is the D584 boundary: Cuenin's 2002 ovation and 2005 removal are two
    episodes. The year is a separator, so `_same_event` declines here and leaves
    the person-cap (D584) to govern how many stops he may span."""
    a = _event_key('Father Cuenin received a standing ovation in 2002.')
    b = _event_key('Father Cuenin was removed from the parish in 2005.')
    assert not _same_event(a, b)


def test_different_action_class_is_not_the_same_event():
    a = _event_key('Mozart was born in this house in 1756.')
    b = _event_key('Mozart performed his first concert here in 1762.')
    assert not _same_event(a, b)


def test_different_people_same_action_is_not_the_same_event():
    a = _event_key('Charles Lindbergh landed here in 1927.')
    b = _event_key('The Beatles arrived here in 1964.')
    assert not _same_event(a, b)


def test_a_sentence_with_no_action_verb_asserts_no_event():
    # A single-token surname mid-sentence is not extracted as a proper-noun core
    # (that needs a two-word run like "Charles Lindbergh"); regardless, the point
    # is that with no action verb there is no event to match on.
    _people, actions, _years = _event_key(
        'The tower continues the legacy that Charles Lindbergh symbolized.')
    assert actions == set()


# --- integration: strip_cross_stop_repeats keeps the first telling ----------

def test_strip_removes_the_later_telling_of_a_repeated_event():
    pois = _pois(
        'Charles Lindbergh once touched down here, marking a moment in aviation '
        'history. The bridge connects the terminal to the aircraft.',
        'In 1927 Charles Lindbergh landed the Spirit of St. Louis here during his '
        'goodwill tour. The tower saw 43.5 million passengers in 2024.',
    )
    removed = strip_cross_stop_repeats(pois)
    assert removed, 'the repeated Lindbergh landing should be removed'
    # The FIRST telling is kept, the later one dropped.
    assert 'touched down' in pois[0]['description']
    assert 'landed the Spirit of St. Louis' not in pois[1]['description']
    # Stop 2 keeps its own distinct fact.
    assert '43.5 million' in pois[1]['description']


def test_strip_does_not_collapse_two_different_dated_events():
    pois = _pois(
        'Father Cuenin received a standing ovation in 2002 as he criticized the '
        'cardinal. The nave holds three hundred worshippers.',
        'Father Cuenin was removed from the parish in 2005. The altar dates to 1890.',
    )
    strip_cross_stop_repeats(pois)
    # Both dated Cuenin events survive — this is D584's territory, not this rule's.
    assert '2002' in pois[0]['description']
    assert '2005' in pois[1]['description']


# --- verification against the REAL round-7 file -----------------------------

_LOGAN_1 = os.path.join(os.path.dirname(__file__), '..',
                        'TOURS_FOR_REVIEW', 'round7', 'LOGAN_1.txt')


def _stop_bodies(path):
    """Narration-only description per stop, mirroring what the pipeline stores:
    metadata lines and the Orientation preview are not part of `description`."""
    text = open(path).read()
    blocks = re.split(r'^Stop \d+:', text, flags=re.M)[1:]
    pois = []
    for i, block in enumerate(blocks):
        lines = []
        for ln in block.split('\n'):
            s = ln.strip()
            if not s:
                continue
            if re.match(r'^(Address|Coordinates|Type/Specialty|Specific Examples|'
                        r'Operational Details|Directions|Orientation):', s):
                continue
            lines.append(s)
        pois.append({'name': f'Stop {i + 1}', 'description': ' '.join(lines)})
    return pois


def test_real_logan_1_lindbergh_landing_told_twice_is_collapsed():
    pois = _stop_bodies(_LOGAN_1)
    before = [i + 1 for i, p in enumerate(pois)
              if 'Lindbergh' in p['description']]
    assert 3 in before and 4 in before, (
        f'fixture changed; expected Lindbergh in body stops 3 and 4, got {before}')

    removed = strip_cross_stop_repeats(pois)

    # The repeated landing telling in the LATER stop (4) is removed...
    assert any(r['stop'] == 4 and r['matched_stop'] == 3 for r in removed), (
        f'expected stop-4 landing to be matched to stop 3, got {removed}')
    # ...and the specific duplicated sentence is gone from stop 4.
    assert 'landed the Spirit of St. Louis' not in pois[3]['description']
    # The FIRST telling stays put in stop 3.
    assert 'touched down' in pois[2]['description']
    # Stop 4 keeps its own distinct facts.
    assert '43.5 million' in pois[3]['description']
    assert 'Channing H. Cox' in pois[3]['description']
