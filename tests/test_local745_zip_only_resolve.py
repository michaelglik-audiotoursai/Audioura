#!/usr/bin/env python3
"""test_local745_zip_only_resolve.py — LOCAL-745 requirement 1 (RED first).

Michael's community tour 716 exists on the server only as a ZIP in /app/tours
(audio_tours.zip_filename) with NO extracted directory. In volume mode
tour_editing_phase2.resolve_tour_to_directory('716') returned None, so
/tour/716/update-multiple-stops answered 404 TOUR_NOT_FOUND and the app showed
"Save failed".

The fix: in volume mode, when no extracted directory exists, resolve the tour
via its ZIP (by audio_tours.zip_filename, falling back to the BYTEA/R2 cloud
path) and extract it to a work directory whose contents are exactly what the
bulk-save reader expects (flat audio_*.txt + audio_*.mp3 at the top level).

These tests are DB-free: they monkeypatch TOURS_DIR and the DB resolver, so they
run anywhere /usr/bin/python3 has flask+psycopg2 importable.

Run: python3 -m pytest tests/test_local745_zip_only_resolve.py -q
"""
import os
import sys
import io
import zipfile
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tour_editing_phase2 as p2


def _make_flat_tour_zip(path, stops=2):
    """A ZIP whose files sit at the top level, like tour 716's real ZIP:
    index.html, audio_N.txt, audio_N.mp3, manifest.json."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('index.html', '<html>tour</html>')
        zf.writestr('manifest.json', '{"name": "Salem"}')
        for n in range(1, stops + 1):
            zf.writestr(f'audio_{n}.txt', f'Stop {n} narration text')
            zf.writestr(f'audio_{n}.mp3', b'\x00\x01\x02fakeaudio')


class ZipOnlyResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='local745_tours_')
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        # The tour exists ONLY as a ZIP in the tours dir — no extracted dir.
        self.zip_name = 'the_episode_1_of_season_1_biking_tour_salem_ma__ad5f966f.zip'
        self.zip_path = os.path.join(self.tmp, self.zip_name)
        _make_flat_tour_zip(self.zip_path, stops=4)

        # Point the service's volume store at our temp dir.
        self._orig_tours_dir = p2.TOURS_DIR
        p2.TOURS_DIR = self.tmp
        self.addCleanup(lambda: setattr(p2, 'TOURS_DIR', self._orig_tours_dir))

        # Volume mode (the live subscribed-local default).
        self._orig_env = os.environ.get('TOUR_STORAGE_MODE')
        os.environ['TOUR_STORAGE_MODE'] = 'volume'
        self.addCleanup(self._restore_env)

        # Resolve id 716 -> zip_filename without a DB: patch the DB lookup the
        # fix must use. The fix reads audio_tours.zip_filename for a numeric id.
        self._patched = []

    def _restore_env(self):
        if self._orig_env is None:
            os.environ.pop('TOUR_STORAGE_MODE', None)
        else:
            os.environ['TOUR_STORAGE_MODE'] = self._orig_env

    def _patch(self, name, value):
        orig = getattr(p2, name)
        setattr(p2, name, value)
        self.addCleanup(lambda: setattr(p2, name, orig))

    def test_zip_only_tour_resolves_to_a_readable_directory(self):
        """resolve_tour_to_directory('716') must return a directory holding the
        flat audio_*.txt files — not None (which caused the 404)."""
        # The fix depends on a DB lookup of zip_filename for a numeric id. Give
        # it one that returns our ZIP's basename.
        self._patch('_zip_filename_for_tour', lambda tid: self.zip_name)

        resolved = p2.resolve_tour_to_directory('716')

        self.assertIsNotNone(
            resolved,
            "resolve_tour_to_directory('716') returned None — the ZIP-only tour "
            "could not be resolved (this is the LOCAL-745 404 bug).")
        resolved = Path(resolved)
        self.assertTrue(resolved.is_dir(), f"{resolved} is not a directory")
        txts = sorted(resolved.glob('audio_*.txt'))
        self.assertEqual(
            len(txts), 4,
            f"expected 4 flat audio_*.txt files, found {[t.name for t in txts]}")

    def test_extracted_directory_is_preferred_when_present(self):
        """If an extracted directory already exists it is used as-is (no
        regression to the existing exact-path behaviour)."""
        existing = Path(self.tmp) / 'salem_ad5f966f'
        existing.mkdir()
        (existing / 'audio_1.txt').write_text('existing stop')
        resolved = p2.resolve_tour_to_directory('salem_ad5f966f')
        self.assertEqual(Path(resolved), existing)


if __name__ == '__main__':
    unittest.main()
