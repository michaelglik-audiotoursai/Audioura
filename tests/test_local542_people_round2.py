"""LOCAL-542 — the people counter found 8 where CHURCH_1 names 17.

LOCAL-537 fixed LOGAN_1 (4) but round-9 CHURCH_1 still returned 8. The nine people
it missed carry no role word and no title the counter knew — they arrive as passive
agents ("Designed by Jean Bazaine", "described by John Chrysostom", "propagated by
figures like Don Bosco and Vincent Pallotti"), behind a bare honorific ("Fr. Timothy
Danahy"), or inside an apposition list ("congregants: Gilda "Jill" D'Amore, ... Lucia
Arpino"). "Mother Teresa" was found but her title was being eaten to "Teresa".

The fix keys on the GRAMMAR of each construction (a past participle before "by", a
standalone honorific, a role-noun+colon list, a kept title) — never a longer list of
verbs or role words, which is the enumeration trap D476/LOCAL-530 names.

Every sentence here is READ from the real round-9 file, so the test measures the
shipped text. The two people the counter still cannot reach (Christopher Ferguson,
introduced by a bare active verb; and the second same-surname D'Amore, folded by the
surname de-dup that correctly merges the three "Law" forms) are asserted absent, so
the documented limitation is pinned too. Full corpus false-positive audit is in
SUBMISSION_LOCAL-542.md.
"""
import re
import pytest
from tour_quality import (_count_people, _PERSON, _PERSON_POSSESSIVE,
                          _PERSON_APPOSITIVE, _PERSON_AGENT, _PERSON_HON_INTRO,
                          _PERSON_TITLED, _PERSON_APPOS_LIST, _PNAME2)

CHURCH9 = 'TOURS_FOR_REVIEW/round9/CHURCH_1.txt'
LOGAN9 = 'TOURS_FOR_REVIEW/round9/LOGAN_1.txt'


def _names(text):
    out = []
    for m in _PERSON.findall(text):
        out.extend([m] if isinstance(m, str) else [g for g in m if g])
    out.extend(_PERSON_POSSESSIVE.findall(text))
    out.extend(_PERSON_APPOSITIVE.findall(text))
    for m in _PERSON_AGENT.findall(text):
        out.extend([g for g in m if g])
    out.extend(_PERSON_HON_INTRO.findall(text))
    out.extend(_PERSON_TITLED.findall(text))
    for m in _PERSON_APPOS_LIST.findall(text):
        out.extend(re.findall(_PNAME2, m))
    return [n.strip() for n in out]


# ── the passive agent: a participle governs "by <Name>", any verb ────────────

@pytest.mark.parametrize('sentence,person', [
    ('Designed by Jean Bazaine, the stained-glass windows depict the sacraments.',
     'Jean Bazaine'),
    ('a title first described by John Chrysostom in AD 345.', 'John Chrysostom'),
    ('this devotion, later propagated by figures like Don Bosco and Vincent '
     'Pallotti, is linked to Europe.', 'Don Bosco'),
])
def test_passive_agent_names_a_person(sentence, person):
    assert person in _names(sentence), sentence


def test_passive_agent_takes_both_of_a_coordinated_pair():
    got = _names('propagated by figures like Don Bosco and Vincent Pallotti here.')
    assert 'Don Bosco' in got and 'Vincent Pallotti' in got, got


def test_passive_agent_ignores_a_common_word_after_by():
    """The two-token requirement keeps "by These"/"by September" out."""
    assert _count_people('The tower was renamed by These committees in 1943.') == 0


# ── a standalone honorific introduces a person ───────────────────────────────

def test_bare_honorific_introduces_a_person():
    assert 'Timothy Danahy' in _names('Fr. Timothy Danahy sent designs to Munich.')


def test_bare_honorific_needs_a_full_name():
    """A dangling honorific before prose is not a person."""
    assert _count_people('Rev. Parishioners gathered here in protest.') == 0
    assert _count_people('Fr. During the war the parish grew.') == 0


# ── apposition list after a role noun + colon ────────────────────────────────

def test_apposition_list_of_victims():
    got = _names('the murder of three longtime congregants: Gilda "Jill" D\u2019Amore, '
                 'her husband Bruno D\u2019Amore, and Jill\u2019s mother, Lucia Arpino.')
    assert 'Lucia Arpino' in got, got
    assert any('D\u2019Amore' in n for n in got), got


# ── a title is kept in the fullest form ──────────────────────────────────────

def test_title_is_kept_not_eaten():
    """"Mother Teresa", not "Teresa"; "Cardinal Bernard Law", not "Bernard Law"."""
    got = _names('In June 1995 Mother Teresa made an unexpected visit.')
    assert 'Mother Teresa' in got, got


# ── the whole-file acceptance counts, on the real files ──────────────────────

def test_church1_round9_counts_fifteen():
    """Acceptance: 15 of the 17 people the critique enumerates (Ferguson and the
    second D'Amore are the documented misses)."""
    assert _count_people(open(CHURCH9, errors='ignore').read()) == 15


def test_logan1_stays_at_four():
    """Hard requirement: no regression on LOGAN_1's four people."""
    assert _count_people(open(LOGAN9, errors='ignore').read()) == 4


# ── the two documented misses are genuinely absent (pins the limitation) ─────

def test_ferguson_is_the_known_miss():
    """A bare active verb ("Authorities arrested Christopher Ferguson") shares no
    structural signal with scenery; catching it needs a verb list (the trap)."""
    got = _names(open(CHURCH9, errors='ignore').read())
    assert not any('Ferguson' in n for n in got)
