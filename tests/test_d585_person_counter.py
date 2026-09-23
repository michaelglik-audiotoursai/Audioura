"""D585 — the named_people counter, third correction.

Two independent kiro critics reviewed round 7. Both said the counter misled, and
the SECOND one (LOCAL-517) was the one that mattered: it listed the people the
counter was still missing after the first fix, because they appear with no title
and no role word the counter knew.

Verified against the tours: LOGAN_3 really does name five people, the same as the
churches. The "church 5 vs Logan 1-2" gap LEAD reported to Michael was an artefact
of the instrument, not a property of the tours.

Every sentence here is verbatim from TOURS_FOR_REVIEW/round7.
"""
import pytest
from tour_quality import _count_people, _PERSON


def names(text):
    out = []
    for m in _PERSON.findall(text):
        out.extend([m] if isinstance(m, str) else [g for g in m if g])
    return [n.strip() for n in out]


def test_a_role_introduces_two_coordinated_people():
    """One introducer, two people -- the second was invisible before."""
    got = names('The tragic events prompted flight attendants Betty Ann Ong and '
                'Madeline Amy Sweeney to provide vital intelligence.')
    assert 'Betty Ann Ong' in got and 'Madeline Amy Sweeney' in got, got


def test_a_middle_initial_does_not_eat_the_surname():
    """With the initial's period optional, this yielded "Betty A" / "Charles L"."""
    assert 'Charles Lindbergh' in names('the historic landing of Charles Lindbergh here.')
    assert 'Walter H. Cuenin' in names('Rev. Walter H. Cuenin, then pastor, was vocal.')


def test_frames_without_a_role_word():
    assert 'Mohamed Atta' in names('five hijackers, including Mohamed Atta, passed through.')
    assert 'Charles Lindbergh' in names('the landing of Charles Lindbergh at this field.')


def test_scenery_is_not_a_person():
    """"including Terminal B" handed the counter a person called Terminal."""
    assert _count_people('passengers moved through, including Terminal B gates.') == 0


@pytest.mark.parametrize('name,expected', [
    ('CHURCH_1', 5), ('CHURCH_2', 5), ('CHURCH_3', 5),
    ('LOGAN_1', 2), ('LOGAN_2', 3), ('LOGAN_3', 5),
])
def test_round7_counts_are_stable(name, expected):
    """Pins the corrected counts. LOGAN_3 ties the churches at five."""
    text = open(f'TOURS_FOR_REVIEW/round7/{name}.txt', errors='ignore').read()
    assert _count_people(text) == expected
