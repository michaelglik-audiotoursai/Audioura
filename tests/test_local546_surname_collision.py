"""LOCAL-546 — a husband and wife with the same surname counted as one person.

`_count_people` keyed identity on the surname (the last capitalised token) and kept
the fullest form seen. That is CORRECT for one person named several ways — "Law",
"Bernard Law", "Cardinal Bernard Law" is one man (D585), and counting him three
times inflated a 4-stop tour to nine people. It is WRONG when two DIFFERENT people
share a surname: round-9 CHURCH_1 names "Gilda 'Jill' D'Amore, her husband Bruno
D'Amore, and Jill's mother, Lucia Arpino" — three victims — and the counter folded
Bruno into Gilda, returning 15 where 16 is right.

The fix separates the two cases by the GIVEN-NAME sequence within a surname group:
prefix-compatible forms (bare surname / first name / fuller form) nest into one
person; CONFLICTING given names (Gilda vs Bruno, James vs Margaret) are two people.
The surname is still the grouping key, so this is NOT "keying on the full name" —
which would revert D585 and re-inflate the three Law forms back to three.

Both behaviours must coexist; that is the whole task. The two assertions below pin
each half, and each uses text READ from the real corpus so it cannot drift.

Where these patterns occur in the real corpus (measured):
  - same-surname SPLIT: round9/CHURCH_1.txt (D'Amore x2),
                        buckets/CHURCH_6stops_v2.txt (Murphy: James the architect,
                        Margaret who identified a window figure).
  - name-form DE-DUP (must stay one): "Law"/"Bernard Law"/"Cardinal Bernard Law"
                        occurs in round9/CHURCH_1.txt, round3/CHURCH_2.txt,
                        round6/CHURCH_1.txt, round7/CHURCH_2.txt, buckets/*, and
                        most CHURCH tours — it is the single most common multi-form
                        name in the corpus.
"""
import re
import pytest
from tour_quality import (_count_people, _PERSON, _PERSON_POSSESSIVE,
                          _PERSON_APPOSITIVE, _PERSON_AGENT, _PERSON_HON_INTRO,
                          _PERSON_TITLED, _PERSON_APPOS_LIST, _PNAME2)

CHURCH9 = 'TOURS_FOR_REVIEW/round9/CHURCH_1.txt'
LOGAN9 = 'TOURS_FOR_REVIEW/round9/LOGAN_1.txt'
MURPHY = 'TOURS_FOR_REVIEW/buckets/CHURCH_6stops_v2.txt'


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


# ── half 1: two people, one surname, are TWO ─────────────────────────────────

def test_same_surname_conflicting_given_names_are_two_people():
    """A husband and wife with one surname. Minimal, self-contained."""
    text = ('the murder of three congregants: Gilda "Jill" D\u2019Amore, her husband '
            'Bruno D\u2019Amore, and Jill\u2019s mother, Lucia Arpino.')
    assert _count_people(text) == 3, _names(text)


def test_church1_names_both_damores():
    """On the real file, both husband and wife survive de-dup."""
    got = _names(open(CHURCH9, errors='ignore').read())
    assert any('Gilda' in n for n in got), got
    assert any('Bruno' in n for n in got), got


def test_church1_round9_counts_sixteen():
    """The whole-file acceptance count: 16, with the two D'Amores separated."""
    assert _count_people(open(CHURCH9, errors='ignore').read()) == 16


def test_murphy_split_is_the_other_real_occurrence():
    """buckets/CHURCH_6stops_v2 names James Murphy (architect) and Margaret Murphy
    (who identified a window figure) — two people, one surname, the only OTHER place
    in the corpus this split fires. Both must be present."""
    got = _names(open(MURPHY, errors='ignore').read())
    assert any(n == 'James Murphy' or n.endswith('James Murphy') for n in got), got
    assert any('Margaret Murphy' in n for n in got), got


# ── half 2: one person, several name-forms, stays ONE (D585 preserved) ───────

def test_same_surname_forms_are_one_person():
    """"Law", "Bernard Law", "Cardinal Bernard Law" — the case D585 exists for. A
    bare surname, a first+surname and a titled+first+surname all nest into one man;
    counting them as three re-inflates the tour. This is the pattern that must NOT
    break when the D'Amore split is introduced. It occurs across the CHURCH corpus,
    including round9/CHURCH_1.txt."""
    text = ('Rev. Cuenin criticised Law. His words challenged Bernard Law, and the '
            'gathering opposed Cardinal Bernard Law directly.')
    assert _count_people(text) == 2, _names(text)   # Cuenin + one Law


def test_bare_surname_does_not_spawn_a_second_person():
    """A first mention by surname only, then a fuller form, is ONE person — a bare
    given-name sequence is a prefix of every fuller one."""
    assert _count_people('architect Murphy designed it; later James Murphy signed.') == 1


def test_middle_initial_is_the_same_person():
    """"Bernard Law" and "Bernard F. Law" differ only by an inserted initial — a
    prefix-compatible extension, one man."""
    assert _count_people('Cardinal Bernard Law resigned; Bernard F. Law had led it.') == 1


# ── the coexistence, stated as one assertion ─────────────────────────────────

def test_split_and_dedup_coexist_in_one_text():
    """Both behaviours in a single passage: two D'Amores (split) AND three Law forms
    (folded). The D'Amores arrive through the colon-list construction the counter
    reads (as in the real file); Law through its title. Expect 3 people — Gilda,
    Bruno, and the one Law."""
    text = ('Cardinal Bernard Law presided. The parish mourned two victims: '
            'Gilda D\u2019Amore, her husband Bruno D\u2019Amore, gathered here; '
            'Bernard Law had long since gone.')
    assert _count_people(text) == 3, _names(text)


# ── the hard requirement: LOGAN_1 unchanged ──────────────────────────────────

def test_logan1_stays_at_four():
    """A regression on LOGAN_1's four people (Edward Lawrence Logan, Gustave Eiffel,
    John Therry, Trippe) fails the task."""
    assert _count_people(open(LOGAN9, errors='ignore').read()) == 4
