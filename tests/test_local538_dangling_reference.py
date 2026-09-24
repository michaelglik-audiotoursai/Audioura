"""LOCAL-538 — the noun is gone and no rule sees it: round 2 of LOCAL-530.

Round 9 scored CLEAN while carrying two sentences broken in exactly the way
LOCAL-530 exists to catch, in shapes its "<verb> of <Capital>" regex cannot match.
Both are one grammatical fault: a phrase that requires a complement, standing
without one.

A. RELATIONAL NOUN WITH NO COMPLEMENT — round9/LOGAN_1.txt, Control Tower, verbatim:
     "Trippe, the founder and later Pan American World Airways, helped connect
      Boston to New York, ..."
   "the founder" lost its "of <what>"; LOCAL-530 matches the "of", which is the
   part that was deleted, so it sees nothing.

B. A REFERENT THAT DOES NOT EXIST — round9/CHURCH_1.txt, Stained Glass Windows,
   verbatim:
     "In the absence of stained glass, we find the church's story told through
      different means. This event, deeply etched into the church's modern
      history, demonstrates that ..."
   No event has been narrated anywhere earlier. "This event" points at nothing.

Every sentence asserted on below is READ FROM THE REAL FILE, never retyped — the
tests slice the exact substrings out of the file contents so they cannot drift from
the evidence. The only synthetic input is the pronoun case (B, second shape): no
tour on disk carries a genuine no-antecedent pronoun (every "Her"/"His" in round 7
and round 9 has a person named earlier — verified), so the pronoun half is exercised
on a constructed sentence and its negative is verified against a real file.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import tour_quality


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURS = os.path.join(ROOT, 'TOURS_FOR_REVIEW')
LOGAN_R9 = os.path.join(TOURS, 'round9', 'LOGAN_1.txt')
CHURCH_R9 = os.path.join(TOURS, 'round9', 'CHURCH_1.txt')
CHURCH_R7_2 = os.path.join(TOURS, 'round7', 'CHURCH_2.txt')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _sentence_containing(text, needle):
    """Slice the verbatim sentence containing *needle* out of *text* — read, not
    retyped. Bounds on the surrounding full stops."""
    i = text.index(needle)
    start = text.rfind('.', 0, i) + 1
    end = text.find('.', i)
    return text[start:end + 1].strip()


# ─── A. relational noun with no complement — verbatim from round9/LOGAN_1 ────────

class TestRelationalNounNoComplement:

    def test_the_defect_sentence_is_present_verbatim_in_the_real_file(self):
        txt = _read(LOGAN_R9)
        assert 'Trippe, the founder and later Pan American World Airways' in txt

    def test_the_check_fires_on_the_verbatim_defect(self):
        txt = _read(LOGAN_R9)
        hits = tour_quality._find_relational_no_complement(txt)
        assert hits, "the dangling relational noun was not detected"
        assert any('founder' == relnoun for relnoun, _ in hits), hits

    def test_score_tour_reports_dangling_complement_and_is_not_clean(self):
        txt = _read(LOGAN_R9)
        r = tour_quality.score_tour(txt, requested_stops=4, is_building_tour=True)
        assert 'dangling_complement' in r['defects'], r['defects']
        assert r['clean'] is False, "round9/LOGAN_1 must not score CLEAN"

    def test_local530_object_dropped_could_not_see_it(self):
        # Why this ticket exists: the "of" is exactly what was deleted, so the
        # older detector has nothing to match on the defect sentence.
        txt = _read(LOGAN_R9)
        sent = _sentence_containing(txt, 'the founder and later Pan American')
        assert tour_quality._OBJECT_DROPPED.search(sent) is None

    LEGIT = [
        "Juan Trippe, the founder of Pan American World Airways, helped connect cities.",
        "Jane Doe, the founder and chairman of Acme Corporation, spoke today.",
        "Jane Doe, the founder and CEO of Acme Corporation, resigned.",
        "Jane Doe, the founder, who later led Acme, spoke today.",
        "Bob Smith, the painter and sculptor, worked in Paris.",
        "Amy Lee, the director and Oscar winner, attended the gala.",
    ]

    @pytest.mark.parametrize("s", LEGIT)
    def test_legitimate_complemented_forms_do_not_fire(self, s):
        assert not tour_quality._find_relational_no_complement(s), f"false positive: {s}"


# ─── B. demonstrative / pronoun with no antecedent ──────────────────────────────

class TestDanglingDemonstrative:

    def test_the_defect_sentence_is_present_verbatim_in_the_real_file(self):
        txt = _read(CHURCH_R9)
        assert "This event, deeply etched into the church's modern history" in txt

    def test_the_check_fires_on_the_verbatim_defect(self):
        txt = _read(CHURCH_R9)
        hits = tour_quality._find_dangling_references(txt)
        assert any(kind == 'demonstrative' for kind, _ in hits), hits

    def test_score_tour_reports_dangling_reference_and_is_not_clean(self):
        txt = _read(CHURCH_R9)
        r = tour_quality.score_tour(txt, requested_stops=4, is_building_tour=True)
        assert 'dangling_reference' in r['defects'], r['defects']
        assert r['clean'] is False, "round9/CHURCH_1 must not score CLEAN"

    def test_a_dated_or_named_event_anaphor_is_not_flagged(self):
        # Legitimate encapsulating anaphora: a dated/named happening precedes it.
        legit = ("On September 11, 2001, two flights departing from Logan were "
                 "hijacked. This event reshaped airport security worldwide.")
        body = "Stop 1: Control Tower\n\n" + legit + "\n"
        assert not tour_quality._find_dangling_references(body), legit

    def test_a_noneventive_summariser_is_never_flagged(self):
        # "recognition"/"decision" can package a description, not only a happening,
        # so they are outside the eventive class and must never fire — this is the
        # round7/LOGAN_1 "This recognition" shape that a looser check falsely hit.
        body = ("Stop 1: Terminal A\n\nIt was the first terminal to achieve LEED "
                "certification. This recognition emphasized sustainability.\n")
        assert not tour_quality._find_dangling_references(body), body


class TestDanglingPronoun:

    # No tour on disk carries a genuine no-antecedent pronoun (see module docstring),
    # so the positive case is a constructed sentence. Documented, per the task.
    NO_WOMAN = ("Stop 1: Altar\n\nThe altar has witnessed many events over the "
                "decades. Her presence, though unexpected, filled the sanctuary "
                "with grace.\n")

    def test_pronoun_with_no_person_anywhere_is_flagged(self):
        hits = tour_quality._find_dangling_references(self.NO_WOMAN)
        assert any(kind == 'pronoun' for kind, _ in hits), hits

    def test_pronoun_clears_once_a_person_is_named(self):
        named = self.NO_WOMAN.replace(
            "The altar has witnessed many events over the decades.",
            "Mother Teresa visited the altar in June 1995.")
        hits = tour_quality._find_dangling_references(named)
        assert not any(kind == 'pronoun' for kind, _ in hits), hits

    def test_a_real_pronoun_with_a_valid_antecedent_is_not_flagged(self):
        # round7/CHURCH_2, verbatim: "Mother Teresa's visit in June 1995 ... Her
        # presence highlighted ..." — the woman is named, so nothing should fire.
        txt = _read(CHURCH_R7_2)
        assert 'Her presence highlighted' in txt          # the sentence is real
        hits = tour_quality._find_dangling_references(txt)
        assert not any(kind == 'pronoun' for kind, _ in hits), hits


# ─── Corpus scan — measured false-positive rate, matching the LOCAL-530 standard ──

class TestCorpusScan:
    """Both checks fire exactly on their known defects across the whole corpus and
    on nothing else — LOCAL-530's "fires exactly twice, both true positives"."""

    def _tour_files(self):
        return sorted(glob.glob(os.path.join(TOURS, '**', '*.txt'), recursive=True))

    def test_relational_check_fires_once_and_only_on_logan_r9(self):
        files = self._tour_files()
        assert files, "no tour files found to scan"
        hits = []
        for f in files:
            for relnoun, _span in tour_quality._find_relational_no_complement(_read(f)):
                hits.append((os.path.relpath(f, TOURS), relnoun))
        assert len(hits) == 1, f"expected exactly 1 corpus hit, got {hits}"
        assert hits[0] == (os.path.join('round9', 'LOGAN_1.txt'), 'founder'), hits

    def test_dangling_reference_check_fires_once_and_only_on_church_r9(self):
        files = self._tour_files()
        hits = []
        for f in files:
            for kind, _snip in tour_quality._find_dangling_references(_read(f)):
                hits.append((os.path.relpath(f, TOURS), kind))
        assert len(hits) == 1, f"expected exactly 1 corpus hit, got {hits}"
        assert hits[0] == (os.path.join('round9', 'CHURCH_1.txt'), 'demonstrative'), hits

    def test_combined_the_two_evidence_tours_are_the_only_ones_flagged(self):
        files = self._tour_files()
        flagged = []
        for f in files:
            r = tour_quality.score_tour(_read(f), is_building_tour=True)
            if ('dangling_complement' in r['defects']
                    or 'dangling_reference' in r['defects']):
                flagged.append(os.path.relpath(f, TOURS))
        assert sorted(flagged) == sorted([
            os.path.join('round9', 'CHURCH_1.txt'),
            os.path.join('round9', 'LOGAN_1.txt'),
        ]), flagged
