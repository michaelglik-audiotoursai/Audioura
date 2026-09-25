"""D584 — cap_person_across_stops shipped with no tests, and had two defects.

Found by running it against the real CHURCH_1 round-7 tour, where a critic had
flagged Father Cuenin appearing in every stop:

  1. It capped a "person" called `church`. _entity_year_key returns the last token
     of any capitalised run, so "Our Lady Help of Christians Catholic Church" gave
     `church` -- and the cap deleted a sentence about the altar.
  2. It never capped Cuenin at all. His sentences also yielded `windows` (from
     "Stained Glass Windows"), so they failed the "is this person the only one
     carrying this sentence?" guard and were always skipped.

Fixing (1) then caused (3): with common nouns filtered out, the closing recap
"That's 4 stops -- Stained Glass Windows, where Father Walter Cuenin's story is
etched..." looked like a sentence about Cuenin alone and was deleted, leaving the
recap promising four stops it no longer listed.
"""
from derepetition_guard import cap_person_across_stops, _person_names


def _pois(*descriptions):
    return [{'name': f'Stop {i+1}', 'description': d}
            for i, d in enumerate(descriptions)]


def test_a_common_noun_is_not_a_person():
    assert _person_names('The altar of Christians Catholic Church in Newton.') == set()
    assert 'windows' not in _person_names('The Stained Glass Windows were installed.')


def test_a_real_surname_that_is_also_a_word_is_still_a_person():
    """Cardinal Bernard Law must survive the common-noun filter."""
    assert 'law' in _person_names('Cardinal Bernard Law presided here in 1998.')


def test_the_cap_actually_fires():
    # Each stop needs a second sentence: the cap will not empty a stop, so a
    # single-sentence stop is deliberately left alone (see the last test).
    pois = _pois(
        'Father Cuenin welcomed the congregation warmly. Oak pews fill the room.',
        'Father Cuenin spoke about dissent here. Light falls through the glass.',
        'Father Cuenin returned to this aisle in 2005. The floor is worn smooth.',
        'Father Cuenin was removed in 2005. A brass plaque marks the spot.',
    )
    removed = cap_person_across_stops(pois, max_stops=2)
    assert removed, 'a person in four stops must be capped'
    present = [i for i, p in enumerate(pois) if 'Cuenin' in p['description']]
    assert len(present) <= 2, f'Cuenin still carries {len(present)} stops'


def test_the_cap_does_not_delete_a_recap():
    pois = _pois(
        'Father Cuenin welcomed the congregation.',
        'Father Cuenin spoke about dissent here.',
        'Father Cuenin returned in 2005.',
        "That's 4 stops - the Nave, where Father Cuenin's story is etched.",
    )
    cap_person_across_stops(pois, max_stops=2)
    assert "That's 4 stops" in pois[3]['description'], 'the recap was cut'


def test_the_cap_never_empties_a_stop():
    pois = _pois(
        'Father Cuenin welcomed the congregation.',
        'Father Cuenin spoke here.',
        'Father Cuenin returned in 2005.',
        'Father Cuenin left in 2005.',
    )
    cap_person_across_stops(pois, max_stops=2)
    assert all(p['description'].strip() for p in pois), 'a stop was emptied'
