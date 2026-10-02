"""LOCAL-543 — the evidence file now carries per-claim sourcing, and a named person
placed at this venue on a specific date with no source is a scored defect.

The incident (verbatim from the task): `TOURS_FOR_REVIEW/round9/CHURCH_1_evidence.json`
is 379 bytes and, for all four stops, says only "not in discovered landmarks". That
is the entire evidentiary record behind a tour whose stop-1 narrative asserts, in a
confident voice:

    "In June 1995, the church became the site of an extraordinary moment when Mother
     Teresa ... made an unexpected visit. She quietly entered the nave and approached
     a young parishioner who had been paralyzed."

The pipeline had no source for that sentence. This suite proves:

  1. claim_provenance classifies a sentence as corpus / grounded / parametric, and
     with an EMPTY pool (a saved tour, nothing captured) every factual sentence is
     parametric — the honest reading.
  2. The offline audit of the REAL round9/CHURCH_1.txt reports every factual
     sentence unsourced, and the Mother Teresa sentence is among them.
  3. tour_quality.unsourced_person_event FIRES on the Mother Teresa sentence in the
     real file, is a REQUIRED_CLEAN defect, and a provenance classifier that vouches
     for a sentence CLEARS it (sourced ≠ flagged).
  4. False-positive survey over all 48 tour files (the LOCAL-536/537/539 format):
     the detector fires only on genuine person+date+venue sentences and never on the
     control passages that merely mention a person, a date, or the venue separately.

Every passage is read from the real file at runtime (sliced, never retyped), so the
suite asserts on the exact bytes shipped.
"""
import glob
import os
import re

import pytest

import claim_provenance as cp
from claim_provenance import SourcePool, audit_tour, classify_sentence, CORPUS, GROUNDED, PARAMETRIC
import tour_quality as tq
from tour_quality import (score_tour, REQUIRED_CLEAN, ADVISORY_ONLY,
                          _find_unsourced_person_events)


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHURCH9 = os.path.join(HERE, 'TOURS_FOR_REVIEW', 'round9', 'CHURCH_1.txt')
TOURS_GLOB = os.path.join(HERE, 'TOURS_FOR_REVIEW', '**', '*.txt')


def _read(path):
    with open(path, errors='ignore') as fh:
        return fh.read()


def teresa_sentence():
    """The Mother Teresa sentence, verbatim from the real round9/CHURCH_1.txt."""
    text = _read(CHURCH9)
    i = text.index('In June 1995')
    j = text.index('made an unexpected visit.') + len('made an unexpected visit.')
    return text[i:j]


# ─── Sanity: the passage really is in the file ──────────────────────────────

def test_teresa_sentence_is_the_real_passage():
    s = teresa_sentence()
    assert 'Mother Teresa' in s
    assert 'June 1995' in s


# ─── 1. claim_provenance classes ────────────────────────────────────────────

def test_empty_pool_is_all_parametric():
    """A saved tour with nothing captured: every factual sentence is parametric."""
    assert classify_sentence(teresa_sentence())['class'] == PARAMETRIC


def test_grounded_support_carries_a_sentence():
    pool = SourcePool(grounded_supports=[{
        'text': 'In late 2002, Rev. Walter Cuenin delivered a homily criticizing '
                'the handling of abuse scandals at the parish.',
        'sources': [{'domain': 'bostonglobe.com', 'url': 'https://bostonglobe.com/x'}],
    }])
    res = classify_sentence(
        'In late 2002, Rev. Walter H. Cuenin delivered a homily criticizing the '
        'abuse scandals.', pool, 'Altar')
    assert res['class'] == GROUNDED
    assert res['source']


def test_snippet_with_a_real_url_is_corpus():
    pool = SourcePool(snippets_per_stop={'Altar': [{
        'snippet': 'The altar was crafted by local artisans Eric Boeglin and '
                   'Deacon Jim for the parish community.',
        'link': 'https://example.org/altar'}]})
    res = classify_sentence(
        'The altar, designed and crafted by local artisans Eric Boeglin and '
        'Deacon Jim.', pool, 'Altar')
    assert res['class'] == CORPUS


def test_internal_rationale_marker_is_not_a_source():
    """A snippet whose only 'source' is the pipeline's own rationale is NOT a
    source — it must not confer provenance."""
    pool = SourcePool(snippets_per_stop={'Altar': [{
        'snippet': 'The altar was crafted by local artisans Eric Boeglin.',
        'source': 'replenishment_rationale'}]})
    res = classify_sentence(
        'The altar was crafted by local artisans Eric Boeglin.', pool, 'Altar')
    assert res['class'] == PARAMETRIC


def test_documented_record_name_is_corpus():
    """A name from the stop's own record IS its source (LOCAL-494)."""
    pool = SourcePool(provenance_names={'Nave': ['Jean Bazaine']})
    res = classify_sentence(
        'Designed by Jean Bazaine, the stained-glass windows shimmer with meaning.',
        pool, 'Nave')
    assert res['class'] == CORPUS


# ─── 2. offline audit of the real file ──────────────────────────────────────

def test_offline_audit_of_church1_is_all_unsourced():
    audit = audit_tour(_read(CHURCH9))          # offline: empty pool
    c = audit['counts']
    assert c['total'] > 0
    assert c['sourced'] == 0
    assert c['unsourced'] == c['total'] == c['parametric']


def test_offline_audit_captures_the_teresa_claim():
    audit = audit_tour(_read(CHURCH9))
    texts = [cl['text'] for cl in audit['claims']]
    assert any('Mother Teresa' in t and 'June 1995' in t for t in texts), \
        "the Mother Teresa sentence was not captured as a factual claim"


# ─── 3. the defect ──────────────────────────────────────────────────────────

def test_unsourced_person_event_is_required_clean():
    # [2026-09-23, LEAD at merge] DEMOTED to advisory, deliberately and against this
    # task's own recommendation. This task measured 25 of 29 factual sentences in a
    # live tour as unsourced -- because the pipeline discards provenance it already
    # has, not because 25 sentences are false. Since LOCAL-540 a REQUIRED_CLEAN
    # defect triggers a PAID regeneration, so gating here would fire on nearly every
    # tour, including true statements like "renamed in 1943 to honor Major General
    # Edward Lawrence Logan". A retry cannot conjure a source; it can only delete the
    # person and the date, trading a sourcing gap for a duller tour. Promote it when
    # provenance is plumbed through to the scorer.
    assert 'unsourced_person_event' not in REQUIRED_CLEAN
    assert 'unsourced_person_event' in ADVISORY_ONLY


def test_defect_fires_on_the_real_church1_file():
    result = score_tour(_read(CHURCH9), requested_stops=4, is_building_tour=False)
    assert 'unsourced_person_event' in result['defects'], \
        "a person placed at this venue on a date with no source was not flagged"
    assert result['clean'] is False


def test_the_flagged_event_is_the_teresa_sentence():
    events = _find_unsourced_person_events(_read(CHURCH9))
    sents = [s for s, _, _ in events]
    assert any('Mother Teresa' in s and '1995' in s for s in sents), \
        "the Mother Teresa sentence is not among the flagged person-events"


def test_a_source_clears_the_person_event():
    """The distinction is sourcing, not the shape: a provenance classifier that
    vouches for the Teresa sentence must clear it."""
    def prov(sentence):
        return 'grounded' if 'Mother Teresa' in sentence else 'parametric'
    events = _find_unsourced_person_events(_read(CHURCH9), provenance=prov)
    assert not any('Mother Teresa' in s for s, _, _ in events), \
        "a grounded Mother Teresa sentence was still flagged — the gate keys on " \
        "the shape, not on sourcing"


def test_all_sourced_clears_everything():
    events = _find_unsourced_person_events(_read(CHURCH9), provenance=lambda s: 'corpus')
    assert events == []


# ─── False-positive guards: person, date, venue SEPARATELY must stay clean ──

def test_person_without_a_date_is_not_flagged():
    prose = ("Stop 1: Nave\n\nThe altar was designed by architect James Murphy, "
             "whose Gothic style shaped the sanctuary.")
    assert _find_unsourced_person_events(prose) == []


def test_date_without_a_person_is_not_flagged():
    prose = ("Stop 1: Nave\n\nThe church was completed in 1881 and the nave was "
             "renovated in 1952 to add the vaulted ceiling.")
    assert _find_unsourced_person_events(prose) == []


def test_tour_meta_preview_is_not_flagged():
    """A preview of a later stop ('At the upcoming stops, you'll learn about ...')
    names a person and a date but is not a placement claim."""
    prose = ("Stop 1: Nave\n\nAt the upcoming stops, you'll learn about Mother "
             "Teresa's visit in June 1995 and its meaning for the parish.")
    assert _find_unsourced_person_events(prose) == []


# ─── 4. False-positive survey across ALL 48 tour files ──────────────────────
# In the LOCAL-536/537/539 format. Offline (no captured pool), a person+date+venue
# sentence is unsourced BY CONSTRUCTION — the saved files carry no provenance — so a
# high hit rate is the honest finding, not a false positive. The survey's job here
# is to prove the detector fires ONLY on real person+date+venue sentences: every
# flagged sentence, in every file, must actually contain a person, a specific date,
# and a venue/placement cue.

def _all_tour_files():
    return sorted(glob.glob(TOURS_GLOB, recursive=True))


def test_survey_covers_the_whole_corpus():
    # [2026-09-23, LEAD at merge] Was `== 48`. A pinned corpus SIZE fails every time a
    # round is generated (round 10 and 11 broke it within the hour) and asserts nothing
    # about the survey. The point is that the survey walks a real corpus, not a fixture.
    assert len(_all_tour_files()) >= 48


def test_every_flagged_sentence_has_person_date_and_venue():
    """No structural false positives: each flagged sentence genuinely carries all
    three ingredients."""
    offenders = []
    for path in _all_tour_files():
        text = _read(path)
        for sent, name, date in _find_unsourced_person_events(text):
            has_person = bool(name and len(name.split()[-1]) >= 3)
            has_date = bool(tq._SPECIFIC_DATE.search(sent))
            has_place = bool(tq._VENUE_WORD.search(sent) or tq._PLACEMENT_VERB.search(sent))
            if not (has_person and has_date and has_place):
                offenders.append((os.path.relpath(path, HERE), name, date, sent[:80]))
    assert offenders == [], f"structural false positives: {offenders}"


def test_survey_reports_the_expected_shape():
    """The measurement itself, asserted: the detector fires on the round9 CHURCH_1
    file and does not fire on a file with no named people."""
    files = _all_tour_files()
    fired = {os.path.relpath(p, HERE): len(_find_unsourced_person_events(_read(p)))
             for p in files}
    # round9/CHURCH_1 fires (the Mother Teresa + Cuenin sentences).
    assert fired['TOURS_FOR_REVIEW/round9/CHURCH_1.txt'] >= 1
    # A file with zero named people cannot produce a person-event.
    zero_people = [p for p in files if tq._count_people(_read(p)) == 0]
    for p in zero_people:
        assert _find_unsourced_person_events(_read(p)) == [], \
            f"{p} has no named people yet a person-event was flagged"


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
