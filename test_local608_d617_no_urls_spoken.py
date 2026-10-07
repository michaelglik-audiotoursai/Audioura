#!/usr/bin/env python3
"""test_local608_d617_no_urls_spoken.py — LOCAL-608 item 1 / D617.

A listener never hears a URL or a read-aloud "Sources:" block. The LIVE packer
(tour_generation_modernized.parse_tour_content_to_modernized) writes each stop's
spoken text to the audio_N.txt files; on `storied` it did so VERBATIM, so the
venue's own-page URLs and the trailing "Sources (the museum's own pages):" block
were spoken aloud (D617). This backports subscribed 2b5706c:

  * spoken_text_hygiene.strip_sources_and_urls — deterministic strip of URLs and
    any "Sources:" block from spoken text;
  * its call inside parse_tour_content_to_modernized so audio_N.txt never carries
    http/www./Sources.

RED on 354da34: strip_sources_and_urls does not exist, and the packer leaves the
URL/Sources block in the spoken text.
GREEN after the port.

Run: python3 -m pytest test_local608_d617_no_urls_spoken.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestStripSourcesAndUrls(unittest.TestCase):

    def test_function_exists(self):
        import spoken_text_hygiene as sth
        self.assertTrue(hasattr(sth, 'strip_sources_and_urls'),
                        "spoken_text_hygiene.strip_sources_and_urls must exist (D617)")

    def test_strips_sources_block_and_urls(self):
        import spoken_text_hygiene as sth
        text = (
            "At this work, witness the installation of mirrors and light.\n"
            "Learn more at https://wndrmuseum.com/installations/boston/flex now.\n\n"
            "Sources (the museum's own pages):\n"
            "  - https://wndrmuseum.com/visit\n"
            "  - www.wndrmuseum.com/about\n")
        out, rep = sth.strip_sources_and_urls(text)
        self.assertNotIn("http", out)
        self.assertNotIn("www.", out)
        self.assertNotIn("Sources", out)
        self.assertGreaterEqual(rep['urls'], 1)
        self.assertEqual(rep['sources_blocks'], 1)
        # The real content survives.
        self.assertIn("witness the installation of mirrors and light", out)

    def test_published_text_unchanged(self):
        import spoken_text_hygiene as sth
        text = "The museum is open Tuesday through Sunday, 10 AM to 8 PM.\n"
        out, rep = sth.strip_sources_and_urls(text)
        self.assertEqual(rep['urls'], 0)
        self.assertEqual(rep['sources_blocks'], 0)
        self.assertEqual(out, text)


class TestLivePackerStripsSpokenText(unittest.TestCase):
    """The live packer must apply the strip so audio_N.txt is clean."""

    def test_parse_removes_urls_and_sources_from_spoken_text(self):
        import tour_generation_modernized as tgm
        tour_content = (
            "Step-by-Step Audio Guided Tour: Harvard Art Museums - Museum\n\n"
            "Stop 1: The Great Hall\n"
            "This gallery holds the collection's earliest holdings.\n"
            "Details at https://harvardartmuseums.org/visit before you go.\n\n"
            "Sources (the museum's own pages):\n"
            "  - https://harvardartmuseums.org/visit\n")
        parsed = tgm.parse_tour_content_to_modernized(tour_content)
        joined = "\n".join(parsed.get("text_content", []))
        self.assertNotIn("http", joined)
        self.assertNotIn("www.", joined)
        self.assertNotIn("Sources", joined)
        self.assertIn("earliest holdings", joined)


if __name__ == '__main__':
    unittest.main()
