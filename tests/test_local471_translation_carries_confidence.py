"""[LOCAL-471] The translation service must still read audio_N.txt with the new
Coordinate-Confidence line, and must carry it through in English.

translation_service.py imports boto3, which is not installed in this test
environment (it runs in the translation container). We stub the cloud SDKs so the
PURE parsing methods — _split_tour_content_into_stops, _restore_metadata_labels,
_strip_nav_fields_for_tts — run unchanged and unmocked. Nothing here touches AWS.

Run: python3 tests/test_local471_translation_carries_confidence.py
"""

import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'translation-service'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- stub the cloud/HTML SDKs translation_service imports at module load -----
for name in ('boto3', 'botocore', 'botocore.config', 'bs4'):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
sys.modules['botocore'].config = sys.modules['botocore.config']
sys.modules['botocore.config'].Config = object
sys.modules['boto3'].client = lambda *a, **k: None
sys.modules['bs4'].BeautifulSoup = object
sys.modules['bs4'].NavigableString = object

import translation_service as ts  # noqa: E402


class _FakeTranslate:
    """A stand-in translator: prefixes tokens so we can see what was translated,
    but leaves numbers and the structure intact. We only need to prove the
    English Coordinate-Confidence line survives restore — not real translation."""
    def translate_text(self, text, target_language, preserve_voice_commands=False):
        # Simulate a translator that would MANGLE the confidence label/value.
        out = text.replace('Coordinate-Confidence:', 'Confiance-Coordonnee:')
        out = out.replace('low', 'faible').replace('high', 'eleve')
        return out


class TranslationParserSafety(unittest.TestCase):
    def setUp(self):
        # Build an instance without running __init__ (which would need AWS creds).
        self.svc = ts.TranslationService.__new__(ts.TranslationService)

    def sample_stop(self):
        return ("Musee Matisse\n"
                "Address: 164 Avenue des Arenes, 06000 Nice\n"
                "Coordinates: 43.719450, 7.275970\n"
                "Coordinate-Confidence: high\n"
                "Type/Specialty: Museum\n"
                "The narration the visitor hears.")

    def test_splitter_keeps_the_confidence_line_in_the_stop(self):
        tour = ("Step-by-Step Audio Guided Tour: Test\n\n"
                f"Stop 1: {self.sample_stop()}\n")
        stops = self.svc._split_tour_content_into_stops(tour)
        self.assertEqual(len(stops), 1)
        self.assertIn('Coordinate-Confidence: high', stops[0])

    def test_restore_reinserts_english_confidence_after_title(self):
        # The translator mangles it; _restore_metadata_labels must put the English
        # line back so the app parses it, same as Coordinates/Address.
        original = self.sample_stop()
        translated = _FakeTranslate().translate_text(original, 'fr')
        restored = self.svc._restore_metadata_labels(original, translated, 'fr')
        self.assertIn('Coordinate-Confidence: high', restored,
                      "English confidence line was not restored for the app to read")
        # The English line sits with the other restored metadata, after the title.
        lines = [l for l in restored.split('\n') if l.strip()]
        title_i = 0
        conf_i = next(i for i, l in enumerate(lines) if l.startswith('Coordinate-Confidence:'))
        self.assertGreater(conf_i, title_i)

    def test_no_duplicate_confidence_after_pre_translation_strip(self):
        # This mirrors the production flow: the caller strips the confidence line
        # from the text sent to the translator (so it is never mangled), then
        # restore re-adds the English one. Result: exactly one, in English.
        original = self.sample_stop()
        translate_input = re.sub(r'(?im)^\s*Coordinate-Confidence\s*:.*$\n?', '', original)
        translated = _FakeTranslate().translate_text(translate_input, 'fr')
        restored = self.svc._restore_metadata_labels(original, translated, 'fr')
        self.assertEqual(restored.count('Coordinate-Confidence:'), 1,
                         "duplicate confidence lines after translation")
        self.assertIn('Coordinate-Confidence: high', restored)
        self.assertNotIn('Confiance-Coordonnee', restored)

    def test_tts_strip_removes_confidence(self):
        spoken = self.svc._strip_nav_fields_for_tts(self.sample_stop())
        self.assertNotIn('Coordinate-Confidence', spoken)
        self.assertIn('narration the visitor hears', spoken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
