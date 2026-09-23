"""D583 — the possessive branch of _excise_governed_construction glued words together.

Found by the kiro critic on round 7 as "Archdiocesethe", then traced: the branch
that rewrites "Entity's X" into "the X" strips the dangling preposition from the
text BEFORE the entity (along with its trailing space) and then concatenated the
two halves directly. The sibling branch for non-possessive entities had guarded
this since it was written; this one never did.

All three cases below are verbatim from tours that reached TOURS_FOR_REVIEW.
"""
import re
import pytest
from unglossed_reference_gate import _excise_governed_construction

REAL_CASES = [
    ("In 2002, during the height of the Archdiocese of Boston's clergy abuse "
     "crisis, this narthex became a focal point.", "Boston", "Archdiocesethe"),
    ("The echoes of D'Amore's voice and the memories linger here.",
     "D'Amore", "echoesthe"),
    ("Inspired by Logan's own historic pathways, its design channels the city.",
     "Logan", "Inspiredthe"),
]


@pytest.mark.parametrize("sentence,entity,splice", REAL_CASES)
def test_possessive_excision_does_not_glue_words(sentence, entity, splice):
    out = _excise_governed_construction(sentence, entity)
    assert splice not in out, f"word-splice {splice!r} reappeared in: {out!r}"
    # The general form of the defect: a 6+ letter stem with a function word
    # welded onto it. Nothing in a clean tour looks like this.
    glued = re.search(r'\b[a-z]{6,}(?:the|this|that|when|after|which)\b', out, re.I)
    assert not glued, f"word-splice {glued.group(0)!r} in: {out!r}"


def test_possessive_determiner_does_not_take_an_article():
    """"Logan's own pathways" must not become "the own pathways"."""
    out = _excise_governed_construction(REAL_CASES[2][0], "Logan")
    assert 'the own' not in out.lower(), out


def test_excision_still_removes_the_entity():
    """The guard must not defeat the gate's actual job."""
    out = _excise_governed_construction(REAL_CASES[0][0], "Boston")
    assert "Boston's" not in out, out
    assert 'clergy abuse crisis' in out, out
