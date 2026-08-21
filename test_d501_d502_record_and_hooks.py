#!/usr/bin/env python3
"""test_d501_d502_record_and_hooks.py — the object record, and the unwalked doors.

  [1] D501 object-record parsing and derivation — OFFLINE, on a captured page
  [2] D501 the false-match guards, which are the whole risk of this module
  [3] D502 hooks: what the text asserts and does not substantiate

No network. The eMuseum fixture below is the real markup from
collections.mfa.org/objects/698625, trimmed.
"""
import os
import re
import unittest

import object_record as orec
import story_hooks as hooks
from story_focus_fact import candidate_facts_with_hooks

EMUSEUM = '''
<div class="detailField mediumField"><span class="detailFieldLabel topLabel">Medium/Technique</span><span class="detailFieldValue">
Illustrated book with forty color lithographs (including wrapper front and cover); publisher's vellum<br></span></div>
<div class="detailField dimensionsField"><span class="detailFieldLabel topLabel">Dimensions</span><span class="detailFieldValue">
Overall: 36.8 x 51 x 5 cm<br></span></div>
<div class="detailField creditlineField"><span class="detailFieldLabel topLabel">Credit Line</span><span class="detailFieldValue">
Gift of Boris Fridman<br></span></div>
<div class="detailField invnolineField"><span class="detailFieldLabel topLabel">Accession Number</span><span class="detailFieldValue">2021.1055</span></div>
<div class="detailField"><span class="detailFieldLabel topLabel">Catalogue Raisonn&eacute;</span><span class="detailFieldValue">
Cramer, Mir&oacute; livres illustr&eacute;s,148; Mourlot 789 - 828<br></span></div>
<div class="detailField"><span class="detailFieldLabel topLabel">Description</span><span class="detailFieldValue">
(Paris: Louis Broder, 1971)<br></span></div>
<div class="detailField"><span class="detailFieldLabel topLabel">Provenance</span><span class="detailFieldValue">
Boris Fridman, Newton, MA; 2021, gift of Boris Fridman to the MFA.<br></span></div>
'''


# ─── [1] parsing and derivation ──────────────────────────────────────────────
class TestObjectRecordParsing(unittest.TestCase):
    """RED-CHECK: change the `detailFieldValue` class name in the parser regex.
    Every test here goes red."""

    def setUp(self):
        self.rec = orec.parse_object_page(EMUSEUM)

    def test_fields_map_onto_matrix_slots(self):
        self.assertEqual(self.rec['credit_line'], 'Gift of Boris Fridman')
        self.assertIn('forty color lithographs', self.rec['medium'])
        self.assertEqual(self.rec['accession_number'], '2021.1055')

    def test_publisher_comes_out_of_the_imprint(self):
        # "(Paris: Louis Broder, 1971)" — the Description field on a book.
        pub, year = orec._publisher_from_imprint(self.rec)
        self.assertEqual(pub, 'Louis Broder')
        self.assertEqual(year, '1971')

    def test_printer_comes_out_of_the_catalogue_raisonne(self):
        # THE POINT OF D501. `printed_by` — D500's `builder` role — has been
        # empty in every production run ever made, and Mourlot is sitting in the
        # raisonné line of the museum's own record.
        self.assertEqual(orec._printer_from_raisonne(self.rec), 'Mourlot')

    def test_an_unknown_raisonne_authority_is_not_guessed_at(self):
        # "Cramer" is a scholar; "Mourlot" is a press. Nothing in the string
        # distinguishes them, so an unrecognised authority yields nothing rather
        # than a fabricated printer — which would arrive PRE-GROUNDED, since it
        # really is in the museum's record.
        self.assertEqual(
            orec._printer_from_raisonne({'catalogue_raisonne': 'Bartsch 005; Massari 72'}),
            '')

    def test_placeholders_in_the_record_are_dropped(self):
        rec = orec.parse_object_page(
            '<span class="detailFieldLabel">Credit Line</span>'
            '<span class="detailFieldValue">Not specified</span>')
        self.assertNotIn('credit_line', rec)

    def test_collections_host_is_derived_not_hardcoded(self):
        # The `_try_aic_api` precedent is hardcoded to one venue — the
        # hand-maintained-list mistake D495 removed from domain tiering.
        self.assertIn('collections.mfa.org', orec.collections_hosts_for('http://www.mfa.org/'))
        self.assertIn('collections.rijksmuseum.nl',
                      orec.collections_hosts_for('https://www.rijksmuseum.nl/en'))
        self.assertEqual(orec.collections_hosts_for(''), [])


# ─── [2] the false-match guards ──────────────────────────────────────────────
class TestFalseMatchGuards(unittest.TestCase):
    """RED-CHECK: put `and`/`the` back into scoring by emptying `_STOPWORDS`, or
    drop the harmonic mean for plain coverage. `test_the_moses_false_match` goes
    red — and that match really happened, filling the matrix with a different
    work's credit line and provenance."""

    WRONG_MOSES = ('Moses Telling the Israelites to Gather the Manna and '
                   'Moses Striking the Rock')

    def test_the_moses_false_match(self):
        # Live, before the fix: "Moses and Monotheism" scored 0.67 against a
        # Rembrandt-school "Moses Striking the Rock" and was accepted at 0.6.
        #
        # An earlier version of this test asserted only `score < 0.75` and stayed
        # GREEN with both guards removed, because 0.67 is under 0.75 anyway — it
        # was testing the threshold, not the scoring. Both guards are now pinned
        # by the margin they actually buy.
        score = orec._title_match_score('Moses and Monotheism', self.WRONG_MOSES)
        self.assertLess(score, 0.4,
                        f'a wrong record scores {score:.2f} — too close to a real match')

    def test_stopwords_do_not_earn_a_match(self):
        # `and` was one of the two matching tokens that produced 0.67.
        self.assertIn('and', orec._STOPWORDS)
        a = {t for t in re.findall(r'\w{3,}', orec.fold('Moses and Monotheism'))}
        self.assertIn('and', a, 'fixture assumption changed')

    def test_scoring_is_symmetric(self):
        # Plain coverage-of-query cannot tell "Moses and Monotheism" inside a
        # 12-word unrelated title from a real match. The harmonic mean can,
        # because the result side scores badly.
        long_side = orec._title_match_score('Moses and Monotheism', self.WRONG_MOSES)
        exact = orec._title_match_score('Moses and Monotheism', 'Moses and Monotheism')
        self.assertGreater(exact - long_side, 0.55,
                           'scoring does not separate a buried match from a real one')

    def test_the_real_match_still_scores(self):
        self.assertGreaterEqual(
            orec._title_match_score("Le Lézard aux plumes d’or",
                                    "Le Lézard aux plumes d'or"), 0.99)

    def test_our_own_english_gloss_does_not_sink_the_score(self):
        # The stop title carries a gloss WE added; the record has only the
        # French. Scoring the full string gave 0.40 and missed a record that was
        # the top search hit.
        full = 'Le Lézard aux plumes d’or (The Lizard with Golden Feathers)'
        bare = re.sub(r'\s*\([^)]*\)\s*', ' ', full).strip()
        self.assertLess(orec._title_match_score(full, "Le Lézard aux plumes d'or"), 0.75)
        self.assertGreater(orec._title_match_score(bare, "Le Lézard aux plumes d'or"), 0.9)

    def test_the_checklist_wins_where_both_speak(self):
        m = {'canonical_title': 'X', 'credit_line': 'Gift of A Real Donor'}
        out, _ = orec.enrich_matrix(dict(m), '', verbose=False)
        self.assertEqual(out['credit_line'], 'Gift of A Real Donor')

    def test_copyright_tail_is_the_one_exception(self):
        # D493 recorded this as live and predicted it would reappear: the
        # checklist credit line carries an ARS rights tail, and the focus fact
        # became "Boris Fridman. © Successió Miró / Artists Rights Society (ARS)
        # gave ..." — a donor named after a rights agency.
        derived = {'credit_line': 'Gift of Boris Fridman'}
        existing = 'Gift of Boris Fridman. © Successió Miró / ARS, New York'
        self.assertIn('©', existing)
        self.assertNotIn('©', derived['credit_line'])


# ─── [3] hooks ───────────────────────────────────────────────────────────────
MICHAELS_SENTENCE = (
    '"Au Soleil du Plafond" vividly represents the exhibition\'s thesis, which '
    'highlights how visual artists and poets collaborated to challenge the '
    'boundaries of artistic media.')


class TestHooks(unittest.TestCase):
    """RED-CHECK: empty `_NOT_A_NAME`, or drop the two-token rule in
    `_entities_in`. `test_gallery_and_spanish_are_not_people` goes red."""

    def test_michaels_sentence_produces_his_question(self):
        got = hooks.find_hooks(MICHAELS_SENTENCE, 'Au Soleil du Plafond',
                               'Museum of Fine Arts, Boston')
        self.assertTrue(got)
        qs = ' | '.join(h['question'] for h in got)
        self.assertIn('boundaries of artistic media', qs)
        self.assertIn('before', qs.lower())

    def test_gallery_and_spanish_are_not_people(self):
        # Asserted on `_entities_in` directly. The earlier version checked the
        # resulting hook's subject and stayed GREEN with both filters removed,
        # because that sentence's hook falls back to the no-subject branch either
        # way — it was testing the fallback, not the filter. Live, this sentence
        # produced the subject "Gallery and Spanish".
        text = ('This exhibition in Gallery 184 features extraordinary works by '
                'Spanish artists, focusing on a form that revolutionized the book.')
        found = hooks._entities_in(text)
        self.assertEqual(found, [], f'common nouns harvested as people: {found}')

    def test_a_real_two_token_name_still_survives(self):
        # The filter must not be so aggressive that it removes actual people.
        found = hooks._entities_in(
            'In 1971 Louis Broder commissioned the work from Joan Miró.')
        self.assertIn('Louis Broder', found)

    # Two guards protect `_entities_in`, and on the Gallery/Spanish sentence
    # EITHER ONE alone is sufficient — so removing one and re-running kept the
    # suite green and proved nothing about it. Each is now pinned by a case only
    # it can catch.

    def test_common_noun_pairs_are_rejected_by_name(self):
        # Two tokens, so the arity rule passes it; only `_NOT_A_NAME` stops it.
        found = hooks._entities_in('The Illustrated Book transformed the form.')
        self.assertEqual(found, [], f'common-noun pair harvested: {found}')

    def test_lone_capitalised_words_are_rejected_by_arity(self):
        # Not in `_NOT_A_NAME`, so only the two-token rule stops it. A single
        # capitalised word mid-sentence is more often a common noun than a name.
        found = hooks._entities_in('The work changed how Everything was made.')
        self.assertEqual(found, [], f'lone capitalised word harvested: {found}')

    def test_a_known_agent_beats_the_arity_rule(self):
        # One token, but the matrix already names them, so it is admitted.
        self.assertIn('Mourlot', hooks._entities_in(
            'The lithographs were printed at Mourlot in Paris.', {'mourlot'}))

    def test_the_venue_is_the_setting_not_a_party(self):
        # LOCAL-475/494/496 are the same mistake at three other gates: without
        # this the subject is "Fine Arts and Boston" and Torf — the only real
        # handle in the sentence — is lost.
        text = ('The Museum of Fine Arts, Boston, enriched its collection through '
                'this piece, thanks in part to the visionary support of patrons like Torf.')
        got = hooks.find_hooks(text, 'X', 'Museum of Fine Arts, Boston',
                               known_agents=['Torf'])
        self.assertTrue(got)
        self.assertIn('Torf', got[0]['subject'])
        self.assertNotIn('Fine Arts', got[0]['subject'])

    def test_tour_packaging_is_not_stop_content(self):
        text = ("That's 3 stops — Au Soleil du Plafond showcases collaboration "
                "between visual artists and poets and Le Lézard blends narratives.")
        self.assertEqual(hooks.find_hooks(text, 'X', 'Y'), [])

    def test_a_hook_is_a_question_never_an_answer(self):
        # The circularity guard. A hook must never assert anything — it names
        # what to research. Every one ends in a question mark.
        for h in hooks.find_hooks(MICHAELS_SENTENCE, 'Au Soleil du Plafond', 'MFA'):
            self.assertTrue(h['question'].rstrip().endswith('?'), h['question'])

    def test_facts_outrank_hooks_in_the_rotation(self):
        # A matrix fact is grounded in the museum's record; a hook is grounded
        # only in the fact that we said something.
        cands = candidate_facts_with_hooks(
            {'canonical_title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
             'venue_name': 'MFA'},
            MICHAELS_SENTENCE, 'MFA')
        kinds = [c['key'].startswith('hook:') for c in cands]
        self.assertIn(True, kinds, 'no hooks generated')
        self.assertIn(False, kinds, 'no facts generated')
        self.assertLess(kinds.index(False), kinds.index(True),
                        'a hook outranked a museum-sourced fact')

    def test_no_stop_text_means_no_hooks(self):
        cands = candidate_facts_with_hooks({'canonical_title': 'X', 'artist': 'A'}, '')
        self.assertFalse([c for c in cands if c['key'].startswith('hook:')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
