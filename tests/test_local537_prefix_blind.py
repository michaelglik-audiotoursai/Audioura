"""LOCAL-537 — the people counter only saw a person when a title preceded it.

`_PERSON` required a title or a role word IMMEDIATELY BEFORE the name. Three shapes
of a bare name were therefore invisible, and `_count_people` on the real
round-9 LOGAN_1 returned 1 for a tour that names four people:

  - possessive, no trigger word    "Gustave Eiffel's iconic Control Tower"
  - occupation AFTER the name      "Trippe, the founder ... Pan American World Airways"
  - a two-letter honorific token   "pioneer priest Fr John Therry" ("Fr" broke _NAME)

Every sentence in these tests is READ FROM THE REAL FILE, not retyped, so the test
measures the shipped text and cannot drift from it. The false-positive table that
justifies the new possessive/appositive rules is in SUBMISSION_LOCAL-537.md.
"""
import re
import pytest
from tour_quality import _count_people, _PERSON, _PERSON_POSSESSIVE, _PERSON_APPOSITIVE

LOGAN9 = 'TOURS_FOR_REVIEW/round9/LOGAN_1.txt'
CHURCH9 = 'TOURS_FOR_REVIEW/round9/CHURCH_1.txt'


def _sentence_containing(path, needle):
    """The verbatim sentence-ish window around `needle` in the real file."""
    text = open(path, errors='ignore').read()
    assert needle in text, f'{needle!r} not found in {path} -- evidence changed'
    i = text.index(needle)
    start = max(text.rfind('.', 0, i), text.rfind('\n', 0, i)) + 1
    end = text.find('.', i + len(needle))
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()


def _names(text):
    out = []
    for m in _PERSON.findall(text):
        out.extend([m] if isinstance(m, str) else [g for g in m if g])
    out.extend(_PERSON_POSSESSIVE.findall(text))
    out.extend(_PERSON_APPOSITIVE.findall(text))
    return [n.strip() for n in out]


# ── the three shapes that were invisible, each from the real LOGAN_1 ──────────

def test_possessive_name_is_a_person():
    """"Gustave Eiffel's iconic Control Tower" -- possessive, no preceding trigger."""
    sent = _sentence_containing(LOGAN9, "Gustave Eiffel's iconic Control Tower")
    assert 'Gustave Eiffel' in _names(sent), sent


def test_occupation_after_the_name_is_a_person():
    """"Trippe, the founder ..." -- the role word follows the name."""
    sent = _sentence_containing(LOGAN9, 'Trippe, the founder')
    assert any(n == 'Trippe' or n.endswith('Trippe') for n in _names(sent)), sent


def test_two_letter_honorific_does_not_hide_the_name():
    """"pioneer priest Fr John Therry" -- "Fr" is 2 letters and broke the shape."""
    sent = _sentence_containing(LOGAN9, 'pioneer priest Fr John Therry')
    assert 'John Therry' in _names(sent), sent


# ── the whole-file counts, on the real files ─────────────────────────────────

def test_logan1_round9_counts_its_four_people():
    """Acceptance: the real round-9 LOGAN_1 returns the people actually in it."""
    assert _count_people(open(LOGAN9, errors='ignore').read()) == 4


def test_church1_round9_does_not_regress():
    """[LOCAL-542] Was pinned at 8 — the count this task exists to correct. The
    round-9 CHURCH_1 names 17 people (CRITIQUE_ROUND9_FACTS count-check); the
    counter now returns 15 of them: it finds everyone except Christopher Ferguson
    (introduced by a bare active verb, "Authorities arrested ...", with no
    structural signal that is not shared by scenery) and the SECOND D'Amore (Gilda
    and Bruno share the surname D'Amore, and surname de-dup — the mechanism that
    correctly folds Law/Bernard Law/Cardinal Bernard Law into one man — folds them
    into one). Both misses are documented in SUBMISSION_LOCAL-542.md. Nothing that
    LOCAL-537 counted was lost."""
    assert _count_people(open(CHURCH9, errors='ignore').read()) == 15


# ── the counter must not become greedy ───────────────────────────────────────

@pytest.mark.parametrize('phrase', [
    "That's 4 stops",                 # a determiner, not a name
    "St. Mary's Cathedral",           # a place (single-token possessive)
    "Boston Logan's",                 # the airport, not a person named Logan
])
def test_possessive_scenery_is_not_a_person(phrase):
    assert _count_people(phrase + ' here.') == 0
