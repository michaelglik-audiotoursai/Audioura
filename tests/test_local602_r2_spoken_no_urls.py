#!/usr/bin/env python3
"""test_local602_r2_spoken_no_urls.py — LOCAL-602 r2 / D617 item 9.

No URL and no "Sources" block in any spoken audio_N.txt, on every tour type. The
r1 WNDR run folded the venue's own-page URLs and a trailing "Sources:" block into
the stop text, and the packer wrote them to disk verbatim — a synthesiser would
read a web address aloud.

These tests:
  1. unit-test spoken_text_hygiene.strip_sources_and_urls directly;
  2. run the REAL packer (break_text_to_pois.process_tour_file) on a tour whose
     stops carry http/https/www URLs and a Sources block, then SCAN every
     audio_*.txt it wrote for 'http'/'www.' — the acceptance test the task names.

Run: python3 -m pytest tests/test_local602_r2_spoken_no_urls.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spoken_text_hygiene as sth
import break_text_to_pois as pack


_URL_SCAN = re.compile(r'(?i)(https?://|www\.)')


class TestStripSourcesAndUrls(unittest.TestCase):

    def test_strips_bare_https_url(self):
        out, rep = sth.strip_sources_and_urls(
            "Flex is an immersive room. See https://wndrmuseum.com/installations/boston/flex for more.")
        self.assertNotIn('http', out)
        self.assertGreaterEqual(rep['urls'], 1)

    def test_strips_www_url(self):
        out, _ = sth.strip_sources_and_urls("Visit www.example.org today.")
        self.assertNotIn('www.', out)

    def test_strips_trailing_sources_block(self):
        text = (
            "Stop content here, a real sentence about the room.\n\n"
            "Sources (the museum's own pages):\n"
            "  - https://wndrmuseum.com/installations/boston/flex\n"
            "  - https://wndrmuseum.com/location/boston\n")
        out, rep = sth.strip_sources_and_urls(text)
        self.assertNotIn('Sources', out)
        self.assertNotIn('http', out)
        self.assertGreaterEqual(rep['sources_blocks'], 1)
        self.assertIn("Stop content here", out)

    def test_keeps_real_prose_intact(self):
        prose = "This immersive installation fills an entire room with mirrors."
        out, rep = sth.strip_sources_and_urls(prose)
        self.assertEqual(out.strip(), prose)
        self.assertEqual(rep['urls'], 0)
        self.assertEqual(rep['sources_blocks'], 0)


# A multi-stop tour whose stops carry URLs and a Sources block, exactly as the
# r1 WNDR overview/site-first text did.
_TOUR_TEXT = """Step-by-Step Audio Guided Tour: WNDR Museum, Boston, MA - Museum Tour
Tour-Category: Museum

Stop 1: Flex | WNDR Museum Boston

Flex is an immersive installation. Learn more at https://wndrmuseum.com/installations/boston/flex and plan your visit.

Address: 500 Washington St, Boston, MA 02111
Coordinates: 42.3545, -71.0616

Stop 2: Speak Up! | WNDR Museum Boston

Speak Up! invites visitors to record a message. See www.wndrmuseum.com/installations/boston/speak-up.

Address: 500 Washington St, Boston, MA 02111
Coordinates: 42.3545, -71.0616

Sources (the museum's own pages):
  - https://wndrmuseum.com/installations/boston/flex
  - https://wndrmuseum.com/installations/boston/speak-up
"""


class TestPackerScan(unittest.TestCase):

    def test_packer_audio_files_have_no_urls_or_sources(self):
        import shutil
        # The packer writes the output dir next to its own module (script_dir),
        # derived from the tour file's base name. Use a unique name and clean up.
        script_dir = os.path.dirname(os.path.abspath(pack.__file__))
        base = 'wndr_r2_tour_test_tmp'
        tour_file = os.path.join(script_dir, base + '.txt')
        out_dir = os.path.join(script_dir, base)
        self.addCleanup(lambda: shutil.rmtree(out_dir, ignore_errors=True))
        self.addCleanup(lambda: os.path.exists(tour_file) and os.remove(tour_file))

        with open(tour_file, 'w', encoding='utf-8') as f:
            f.write(_TOUR_TEXT)

        pack.process_tour_file(tour_file)

        self.assertTrue(os.path.isdir(out_dir), "packer did not create the dir")
        audio_files = [fn for fn in os.listdir(out_dir)
                       if fn.startswith('audio_') and fn.endswith('.txt')]
        self.assertGreaterEqual(len(audio_files), 2,
                                "packer should have written one file per stop")

        for fn in audio_files:
            with open(os.path.join(out_dir, fn), encoding='utf-8') as fh:
                body = fh.read()
            self.assertIsNone(
                _URL_SCAN.search(body),
                f"spoken file {fn} still contains a URL:\n{body}")
            self.assertNotIn('Sources', body,
                             f"spoken file {fn} still contains a Sources block")

        # Real prose survived the strip.
        flex = next(fn for fn in audio_files if fn.startswith('audio_1_'))
        with open(os.path.join(out_dir, flex), encoding='utf-8') as fh:
            self.assertIn('immersive installation', fh.read())


if __name__ == '__main__':
    unittest.main()
