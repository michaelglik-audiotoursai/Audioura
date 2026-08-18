#!/usr/bin/env python3
"""test_local479 — ground ORGANISATIONS, not role-claim grammar.

The Hogarth Press fabrication escaped `stop_claim_audit` on three separate runs of
the release check, in three different constructions:

    "This work was printed by The Hogarth Press."            passive   (caught)
    "The Hogarth Press ... printed this work"                active    (D473)
    "the set's limited edition—published by The Hogarth
     Press—underscore ..."                                   em dash   (D478)

Each escape was closed by adding a pattern. That is a losing race: patterns are
enumerable and a generative model's phrasings are not. `apply_org_grounding_gate`
asks a question that has no grammar in it —

    is this organisation grounded in the stop record or the corpus at all?

— so one check covers all three forms and every form nobody has thought of yet.

It is the organisation-shaped sibling of `apply_prose_entity_grounding_gate`, which
has only ever handled PERSON names: "The Hogarth Press" opens with "The", so
`_looks_like_person_name` correctly rejects it as a person, and then nothing else
ever looked at it.

**This gate will produce some false rejections** — a true publisher absent from a
thin museum page reads the same as an invented one. That is the D455 trade
(prefer false rejection on facts) and it is only acceptable because the LOCAL-474
retry loop now exists: a wrong drop costs one regeneration instead of the story.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prose_entity_grounding_gate import (        # noqa: E402
    extract_organisation_names,
    check_org_grounded,
    apply_org_grounding_gate,
)

CORPUS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'story_lab_state', 'stop2_page_text.txt'),
              encoding='utf-8').read()

THREE_FORMS = [
    'This work was printed by The Hogarth Press.',
    'The Hogarth Press, known for its publications, printed this work.',
    "The set's limited edition—published by The Hogarth Press—underscores it.",
]


class TestOneCheckCoversEveryGrammar:

    def test_all_three_escaped_forms_are_detected(self):
        for s in THREE_FORMS:
            orgs = extract_organisation_names(s)
            assert any('Hogarth' in o for o in orgs), f"missed in: {s}"
        print("  ✅ passive, active and em-dash forms all detected")

    def test_hogarth_is_ungrounded_against_the_real_corpus(self):
        assert not check_org_grounded('The Hogarth Press', CORPUS, [])
        print("  ✅ Hogarth ungrounded against the real MFA page text")

    def test_the_gate_drops_the_sentence_in_every_form(self):
        for s in THREE_FORMS:
            poi = [{'name': 'Moses and Monotheism', 'description': s,
                    'orientation': ''}]
            stats = apply_org_grounding_gate(poi, CORPUS, exempt=[])
            assert stats['sentences_dropped'] >= 1, f"not dropped: {s}"
        print("  ✅ dropped in all three forms")


class TestNoFalseRejections:
    """The failure mode this whole session has been removing."""

    def test_an_org_in_the_corpus_is_grounded(self):
        assert check_org_grounded('Mourlot Frères', CORPUS, [])
        print("  ✅ Mourlot Frères grounded from the corpus")

    def test_the_venue_is_grounded(self):
        assert check_org_grounded('Museum of Fine Arts', CORPUS, [])
        print("  ✅ the venue is well-known and exempt")

    def test_an_org_in_the_stop_record_is_grounded(self):
        assert check_org_grounded('The Hogarth Press', '', ['The Hogarth Press'])
        print("  ✅ an org named in the stop record is grounded")

    def test_exempt_list_is_honoured(self):
        assert check_org_grounded('Éditions Verve', '', [],
                                  exempt=['Éditions Verve, Paris'])
        print("  ✅ exemptions honoured")

    def test_accent_folding(self):
        """D243, hit four times on 2026-08-18."""
        assert check_org_grounded('Editions Verve', 'published by Éditions Verve', [])
        assert check_org_grounded('Éditions Verve', 'published by Editions Verve', [])
        print("  ✅ accented and unaccented spellings both ground")

    def test_a_bare_marker_word_is_not_an_organisation(self):
        for s in ('The press covered the opening.',
                  'She walked through the gallery.',
                  'The museum is open on Sundays.'):
            assert not extract_organisation_names(s), s
        print("  ✅ bare marker words are not organisations")

    def test_grounded_text_is_left_completely_alone(self):
        poi = [{'name': 'X', 'orientation': '',
                'description': 'Printed by Mourlot Frères in Paris on Rives paper.'}]
        before = poi[0]['description']
        stats = apply_org_grounding_gate(poi, CORPUS, exempt=[])
        assert stats['sentences_dropped'] == 0
        assert poi[0]['description'] == before
        print("  ✅ grounded prose untouched")


def run_all():
    passed = failed = total = 0
    for cls in (TestOneCheckCoversEveryGrammar, TestNoFalseRejections):
        print(f"\n{'=' * 62}\n  {cls.__name__}\n{'=' * 62}")
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith('test_'):
                continue
            total += 1
            try:
                getattr(inst, name)()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"  ❌ {name}: {e}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {name}: EXCEPTION: {type(e).__name__}: {e}")
    print(f"\n{'=' * 62}\n  RESULTS: {passed}/{total} passed, {failed} failed\n{'=' * 62}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
