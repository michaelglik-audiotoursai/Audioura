#!/usr/bin/env python3
"""test_local706_kokoro_pronunciation.py — LOCAL-706 (D667).

Unit tests for the Kokoro-path foreign-name pronunciation aid and the generic
pronunciation lexicon. No network, no model, no paid calls — the misaki G2P
round-trip test is SKIPPED (not failed) when misaki is not importable in the
test environment, so these run anywhere; the real misaki validation also runs in
the evaluation (see SUBMISSION_LOCAL-706.md).

Covered:
  * generic lexicon JSON loads and overlays IPA onto the in-code records;
  * to_kokoro wraps the FIRST mention of each known name in misaki markup
    [name](/IPA/) when kokoro_ipa is present;
  * to_kokoro substitutes the English respelling when kokoro_ipa is absent;
  * only the first mention is annotated (later mentions stay plain);
  * text with no known name is returned unchanged;
  * the visible/narration text is NOT changed by the Kokoro builder;
  * the Polly SSML path is UNCHANGED by LOCAL-706 (still <sub alias=respelling>,
    never the misaki IPA) — guards against the misaki alphabet leaking to Polly;
  * every lexicon IPA string round-trips through the REAL misaki G2P (skipped if
    misaki unavailable);
  * polly_tts_service._maybe_kokoro_markup applies the markup and fails open.
"""
import json
import os
import unittest

import vietnamese_name_aid as v

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICON_JSON = os.path.join(HERE, 'pronunciation_lexicon.json')


class GenericLexiconLoad(unittest.TestCase):
    def test_json_parses_and_has_entries(self):
        with open(LEXICON_JSON, encoding='utf-8') as fh:
            data = json.load(fh)
        self.assertIn('entries', data)
        self.assertGreaterEqual(len(data['entries']), 3)
        for e in data['entries']:
            self.assertTrue(e.get('key'))
            self.assertTrue(e.get('written'))
            self.assertIn('language', e)
            self.assertIn('respelling', e)
            self.assertIn('sources', e)
            self.assertTrue(e['sources'], f"{e['key']} has no sources")

    def test_overlay_populated_kokoro_ipa(self):
        # The three HCMC names in the ticket must carry misaki IPA after load.
        for key in ('nguyen_gia_tri', 'to_ngoc_van', 'bui_xuan_phai'):
            self.assertIn(key, v.LEXICON)
            self.assertTrue(getattr(v.LEXICON[key], 'kokoro_ipa', ''),
                            f'{key} missing kokoro_ipa')

    def test_load_is_failsafe_on_missing_file(self):
        # A missing file must leave LEXICON intact and return a note, not raise.
        notes = v._load_generic_lexicon('/no/such/lexicon.json')
        self.assertTrue(any('absent' in n for n in notes))
        self.assertIn('nguyen_gia_tri', v.LEXICON)


class KokoroMarkup(unittest.TestCase):
    def test_first_mention_wrapped_with_ipa(self):
        text = 'A work by Nguyễn Gia Trí hangs here.'
        out, notes = v.to_kokoro(text)
        ipa = v.LEXICON['nguyen_gia_tri'].kokoro_ipa
        self.assertIn(f'[Nguyễn Gia Trí](/{ipa}/)', out)
        self.assertTrue(any('kokoro_ipa' in n for n in notes))

    def test_only_first_mention_annotated(self):
        text = 'Nguyễn Gia Trí painted it. Later, Nguyễn Gia Trí returned.'
        out, _ = v.to_kokoro(text)
        self.assertEqual(out.count('](/'), 1, 'should annotate first mention only')
        # The second mention stays as the plain diacritic name.
        self.assertIn('Later, Nguyễn Gia Trí returned.', out)

    def test_respelling_substituted_when_no_ipa(self):
        # Temporarily clear the IPA for one artist to exercise the fallback.
        a = v.LEXICON['nguyen_sang']
        saved = a.kokoro_ipa
        try:
            a.kokoro_ipa = ''
            out, notes = v.to_kokoro('Here is Nguyễn Sáng today.')
            self.assertIn(a.say, out)                 # respelling spoken
            self.assertNotIn('Nguyễn Sáng', out)      # name replaced for audio
            self.assertTrue(any('kokoro_respell' in n for n in notes))
        finally:
            a.kokoro_ipa = saved

    def test_no_known_name_unchanged(self):
        text = 'The museum opened in 1929 near the river.'
        out, notes = v.to_kokoro(text)
        self.assertEqual(out, text)
        self.assertEqual(notes, [])

    def test_multiple_names_each_wrapped(self):
        text = 'Tô Ngọc Vân and Bùi Xuân Phái both taught.'
        out, _ = v.to_kokoro(text)
        self.assertIn('[Tô Ngọc Vân](/', out)
        self.assertIn('[Bùi Xuân Phái](/', out)


class VisibleTextUnchanged(unittest.TestCase):
    def test_kokoro_builder_does_not_mutate_input(self):
        text = 'Work by Nguyễn Gia Trí.'
        before = text
        _ = v.to_kokoro(text)
        self.assertEqual(text, before)  # pure function, input untouched

    def test_apply_narration_has_no_markup_and_no_say(self):
        # The narration text (what the listener's words are) must stay clean:
        # no misaki markup, no "(say:)" parenthetical.
        out, _ = v.apply('Spring Garden by Nguyen Van Tri.')
        self.assertNotIn('](/', out)
        self.assertNotIn('(say:', out)
        self.assertIn('Nguyễn Gia Trí', out)  # name corrected in text


class PollyPathUnchanged(unittest.TestCase):
    def test_polly_ssml_uses_sub_alias_not_misaki_ipa(self):
        # LOCAL-706 must not leak misaki IPA into Polly's <phoneme>. With only
        # kokoro_ipa set (no polly_ipa), Polly keeps the proven <sub alias>.
        text = 'A work by Nguyễn Gia Trí.'
        ssml, _ = v.to_ssml(text)
        self.assertIn('<sub alias="ngwen zah chee">Nguyễn Gia Trí</sub>', ssml)
        misaki_ipa = v.LEXICON['nguyen_gia_tri'].kokoro_ipa
        self.assertNotIn(misaki_ipa, ssml)


class ServiceWiring(unittest.TestCase):
    def test_maybe_kokoro_markup_applies_and_failsafe(self):
        import importlib
        # polly_tts_service imports boto3 at module load. Where boto3 is not
        # installed (e.g. the kokoro-venv used for the misaki round-trip), skip —
        # the helper's logic is the same to_kokoro() path covered above; the
        # real wiring is exercised end-to-end in the evaluation (container has
        # boto3). This keeps the unit suite runnable in any environment.
        try:
            mod = importlib.import_module('polly_tts_service')
        except Exception as e:  # pragma: no cover - env without boto3
            self.skipTest(f'polly_tts_service deps unavailable: {e}')
        marked = mod._maybe_kokoro_markup('A work by Nguyễn Gia Trí.')
        self.assertIn('](/', marked)
        # No-name text passes through unchanged.
        self.assertEqual(mod._maybe_kokoro_markup('No names.'), 'No names.')
        # Empty/None fail open.
        self.assertEqual(mod._maybe_kokoro_markup(''), '')


class MisakiRoundTrip(unittest.TestCase):
    """Every lexicon IPA must be valid misaki US-English phonemes so Kokoro
    accepts [name](/IPA/) verbatim. Skipped when misaki is not importable."""

    def setUp(self):
        try:
            from misaki import en  # noqa: F401
        except Exception as e:  # pragma: no cover - env without misaki
            self.skipTest(f'misaki not available: {e}')

    def test_each_ipa_roundtrips_through_misaki(self):
        from misaki import en
        g = en.G2P(trf=False, british=False, fallback=None)
        with open(LEXICON_JSON, encoding='utf-8') as fh:
            entries = json.load(fh)['entries']
        for e in entries:
            ipa = (e.get('ipa') or '').strip()
            if not ipa:
                continue
            markup = f"[{e['written']}](/{ipa}/)"
            phonemes, _ = g(markup)
            self.assertEqual(
                phonemes.replace(' ', ''), ipa.replace(' ', ''),
                f"misaki did not preserve IPA for {e['written']}: {phonemes!r}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
