"""LOCAL-530 — a verb welded onto "of" after its object noun was deleted.

LOGAN_2 (round 7), Control Tower stop, verbatim:

    "They authorized of Public Works to lease this land to the U.S. Army."

The subject noun of the object is gone. The tour meant "the Department of Public
Works"; a gate excised the head noun "Department" (an unglossed reference) and left
the transitive verb "authorized" abutting "of". This is the D583 / LOCAL-475 defect
class: a gate deletes a span from mid-sentence and the seven degrade guards pass the
wreckage.

DIAGNOSIS (reproduced, not assumed):
    _excise_governed_construction(
        "They authorized the Department of Public Works to lease this land ...",
        "Department")
    -> "They authorized of Public Works to lease this land ..."
    and _degrade_sentence_is_wellformed returned True for it.

Two fixes, mirroring D583:
  * unglossed_reference_gate._DEGRADE_GUARD_OBJECT_DROPPED — an eighth degrade guard
    so the gate drops the sentence instead of shipping it (fail-safe);
  * tour_quality._OBJECT_DROPPED — the scorer's net, so if the shape ever ships it
    is counted as a truncation defect and the loop regenerates the tour.

The round-3 sibling "engaged of Public Works" (LOGAN_1) is the same defect; the old
_MANGLED caught it only because 'engaged' was hand-listed. Both detectors here are
structural over a family of transitive verbs, not a two-verb list.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from unglossed_reference_gate import (
    _excise_governed_construction,
    _degrade_sentence_is_wellformed,
    validate_degrade_output,
    validate_and_repair_full_text,
)
import tour_quality


REAL = "They authorized of Public Works to lease this land to the U.S. Army."
INTACT = ("They authorized the Department of Public Works to lease this land "
          "to the U.S. Army.")
ROUND3_SIBLING = ("This reflects a strategic foresight that once engaged of "
                  "Public Works.")


class TestTheGateProducedTheDefect:
    """The sentence was made by the gate, not written by the model."""

    def test_excising_the_head_noun_reproduces_the_shipped_sentence(self):
        out = _excise_governed_construction(INTACT, "Department")
        assert out == REAL, f"expected the shipped defect, got: {out!r}"

    def test_the_defect_is_now_rejected_as_ill_formed(self):
        assert not _degrade_sentence_is_wellformed(REAL), \
            "the object-dropped sentence still passes the degrade guards"

    def test_the_intact_sentence_still_passes(self):
        assert _degrade_sentence_is_wellformed(INTACT), \
            "the guard now rejects the well-formed original"

    def test_the_round3_sibling_is_also_rejected(self):
        assert not _degrade_sentence_is_wellformed(ROUND3_SIBLING)

    def test_full_text_repair_drops_the_broken_sentence(self):
        text = ("Stop 4: Control Tower\n\n" + REAL +
                " The Control Tower orchestrates this vast network.")
        repaired, dropped = validate_and_repair_full_text(text)
        assert REAL not in repaired, f"broken sentence survived: {repaired!r}"
        assert any('authorized of' in d['sentence'] for d in dropped), dropped

    def test_validate_degrade_output_reports_the_guard(self):
        viol = validate_degrade_output(REAL)
        assert any(v['guard'] == 'object_dropped' for v in viol), viol


class TestLegitimateOfIdiomsAreNotTouched:
    """The guard must never fire on ordinary "-ed of" English."""

    LEGIT = [
        "The nave is comprised of granite blocks quarried nearby.",
        "The altar is composed of Carrara marble from Italy.",
        "The congregation consisted of Irish immigrant families.",
        "He was deprived of his cardinalate after the scandal.",
        "She was accused of heresy by the tribunal.",
        "The parishioners approved of the renovation plans.",
        "The architect died of pneumonia in 1889.",
        "Visitors were informed of the temporary closure.",
        "The mural was conceived of during the 1920s expansion.",
        "The reredos was made of hand-carved oak.",
    ]

    @pytest.mark.parametrize("s", LEGIT)
    def test_legit_of_idiom_passes_the_gate(self, s):
        assert _degrade_sentence_is_wellformed(s), f"wrongly rejected: {s}"

    @pytest.mark.parametrize("s", LEGIT)
    def test_legit_of_idiom_is_not_scored_as_a_defect(self, s):
        assert not tour_quality._OBJECT_DROPPED.search(s), f"false positive: {s}"


class TestTheScorerCatchesIt:
    """If the shape ever reaches a shipped tour, the loop must flag it."""

    def test_scorer_flags_the_real_sentence(self):
        assert tour_quality._OBJECT_DROPPED.search(REAL)

    def test_scorer_flags_the_round3_sibling(self):
        assert tour_quality._OBJECT_DROPPED.search(ROUND3_SIBLING)

    def test_score_tour_reports_a_truncated_defect(self):
        # A minimal tour body carrying the defect; a named person keeps it from
        # tripping the unrelated no_story defect.
        body = ("Stop 1: Control Tower\n\n"
                "Governor Channing H. Cox opened the airfield in 1923. " + REAL +
                " The tower has run continuously since.\n")
        result = tour_quality.score_tour(body)
        assert 'truncated' in result['defects'], result['defects']
        assert 'authorized of' in result['defects']['truncated']

    def test_a_clean_tour_has_no_truncated_defect(self):
        body = ("Stop 1: Control Tower\n\n"
                "Governor Channing H. Cox opened the airfield in 1923. " + INTACT +
                " The tower has run continuously since.\n")
        result = tour_quality.score_tour(body)
        assert 'truncated' not in result['defects'], result['defects']


class TestCorpusScan:
    """No false positives anywhere in TOURS_FOR_REVIEW; the two known hits fire."""

    def _tour_files(self):
        import glob
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return sorted(glob.glob(os.path.join(root, 'TOURS_FOR_REVIEW', '**', '*.txt'),
                                recursive=True))

    def test_scorer_fires_exactly_on_the_two_known_defects(self):
        files = self._tour_files()
        assert files, "no tour files found to scan"
        hits = []
        for f in files:
            with open(f, encoding='utf-8') as fh:
                txt = fh.read()
            for m in tour_quality._OBJECT_DROPPED.finditer(txt):
                hits.append((os.path.basename(os.path.dirname(f)), m.group(0)))
        # Exactly the round-7 "authorized of" and round-3 "engaged of".
        assert len(hits) == 2, f"expected 2 corpus hits, got {hits}"
        verbs = sorted(h[1].split()[0] for h in hits)
        assert verbs == ['authorized', 'engaged'], hits
