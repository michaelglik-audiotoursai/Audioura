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
    # [LOCAL-542] CHURCH_1 5->7: the passive-agent rule now finds Don Bosco and
    # John Chrysostom ("first described by John Chrysostom", "propagated by figures
    # like Don Bosco"), both real people that no title/role word introduced.
    ('CHURCH_1', 7), ('CHURCH_2', 5), ('CHURCH_3', 5),
    # LOGAN_1/2 gained Gustave Eiffel once attribution frames ("constructed in
    # 1887-1889 by ...") were understood. He is a HALLUCINATION -- the Eiffel Tower
    # pasted into an airport tour -- but he is genuinely a named person in the text,
    # and counting him is correct. Catching him is a grounding problem, not a
    # counting one; see the 'placeholder'/refutation work.
    ('LOGAN_1', 3), ('LOGAN_2', 4), ('LOGAN_3', 5),
])
def test_round7_counts_are_stable(name, expected):
    """Pins the corrected counts. LOGAN_3 ties the churches at five."""
    text = open(f'TOURS_FOR_REVIEW/round7/{name}.txt', errors='ignore').read()
    assert _count_people(text) == expected


def test_a_people_group_is_not_a_person():
    """"funded by Irish immigrants" produced a person called Irish."""
    from tour_quality import _count_people
    assert _count_people('The church was funded by Irish immigrants who settled here.') == 0


def test_an_attribution_frame_finds_the_builder():
    """The verb need not sit next to "by"."""
    assert 'Gustave Eiffel' in names('a structure constructed in 1887-1889 by Gustave Eiffel.')


def test_placeholder_stop_is_a_defect():
    """LOGAN_3 shipped an admitted void and scored ZERO defects."""
    from tour_quality import score_tour
    text = open('TOURS_FOR_REVIEW/round7/LOGAN_3.txt', errors='ignore').read()
    assert 'placeholder' in score_tour(text, 4, True)['defects']
    clean = open('TOURS_FOR_REVIEW/round7/CHURCH_2.txt', errors='ignore').read()
    assert 'placeholder' not in score_tour(clean, 4, True)['defects']
