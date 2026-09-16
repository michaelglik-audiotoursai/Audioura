#!/usr/bin/env python3
"""test_local479_wiring.py — LOCAL-479 call-site proof.

LOCAL-465 shipped 27 green unit tests and a NameError on every live run because
no test touched the call site. This test does what those did not: it exercises
the ACTUAL PHASE 5.157 wiring block from generate_tour_text.py that invokes the
unglossed-reference gate (into which Part 2's dependant-cut is wired).

  1. It extracts the verbatim PHASE 5.157 block from generate_tour_text.py
     (banner to next banner), so deleting or renaming the block fails this test.
  2. It exec()s that block in a namespace binding the SAME names the surrounding
     code binds at the call site — poi_list, api_key, os, sys, total_tokens,
     total_cost — with requests.post monkeypatched so no network is touched.
  3. It asserts the block imported the gate, ran, produced its PHASE 5.157 log
     line and summary, and detected the single-token orphans end to end.

If the block references a name that does not exist at the call site (the exact
LOCAL-465 failure mode) exec() raises NameError HERE and the test goes red.
"""
import os
import re
import sys
import io
import json
import types
import unittest
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GEN_PATH = os.path.join(ROOT, 'generate_tour_text.py')

PHASE_BANNER = '# -------- [LOCAL-269] PHASE 5.157: Unglossed-reference gate --------'
NEXT_BANNER = '# -------- [LOCAL-378] PHASE 5.158: Prose entity grounding gate --------'


def _extract_phase_block():
    """Pull the PHASE 5.157 block verbatim and dedent one level to run at
    module scope under exec()."""
    src = open(GEN_PATH, encoding='utf-8').read()
    start = src.index(PHASE_BANNER)
    end = src.index(NEXT_BANNER, start)
    block = src[start:end]
    lines = block.splitlines()
    dedented = [ln[4:] if ln.startswith('    ') else ln for ln in lines]
    return '\n'.join(dedented)


class TestWiring(unittest.TestCase):

    def test_block_exists_in_source(self):
        block = _extract_phase_block()
        self.assertIn('apply_gate_to_stop_descriptions', block)
        self.assertIn('PHASE 5.157', block)
        self.assertIn('DISABLE_UNGLOSSED_REFERENCE_GATE', block)
        self.assertIn('unglossed_reference_gate', block)

    def test_call_site_executes_and_fires(self):
        """Exec the real block with the call-site's variable names bound.

        No api_key is provided, so the gate runs its detection stage and returns
        without any network call (triage/gloss need a key). This still proves the
        wiring: the block imports the gate, calls it with the arguments the call
        site actually passes, and prints its phase banner + summary.
        """
        poi_list = [
            {'name': 'Boston Logan Airport History Walk',
             'description': (
                 "The plane made an emergency landing at Logan. "
                 "Reid's failed attempt serves as a stark reminder of vigilance. "
                 "The disappearance of Walter added a layer of mystery.")},
        ]

        import requests as _requests

        def _fake_post(url, headers=None, data=None, timeout=None):
            raise AssertionError("no network expected without api_key")

        _orig_post = _requests.post
        _requests.post = _fake_post
        try:
            ns = {
                'os': os,
                'sys': sys,
                'poi_list': poi_list,
                'api_key': None,          # call site reads `api_key` from scope
                'total_tokens': 0,        # call site increments these
                'total_cost': 0.0,
            }
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(_extract_phase_block(), GEN_PATH, 'exec'), ns, ns)
            out = buf.getvalue()
        finally:
            _requests.post = _orig_post

        self.assertIn('PHASE 5.157: Unglossed-reference gate', out)
        self.assertIn('Unglossed-reference gate summary', out)
        # The gate saw the stop and detected the single-token orphans (Reid,
        # Walter) — total_detected is reported in the summary.
        self.assertIn('References detected:', out)
        m = re.search(r'References detected:\s*(\d+)', out)
        self.assertIsNotNone(m, out)
        self.assertGreaterEqual(int(m.group(1)), 2, out)

    def test_disable_flag_at_call_site(self):
        """The DISABLE env var short-circuits the real block (no import, no run)."""
        block = _extract_phase_block()
        poi_list = [{'name': 'A', 'description': 'x'}]
        ns = {'os': os, 'sys': sys, 'poi_list': poi_list, 'api_key': None,
              'total_tokens': 0, 'total_cost': 0.0}
        os.environ['DISABLE_UNGLOSSED_REFERENCE_GATE'] = '1'
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(block, GEN_PATH, 'exec'), ns, ns)
            out = buf.getvalue()
        finally:
            del os.environ['DISABLE_UNGLOSSED_REFERENCE_GATE']
        self.assertIn('DISABLED by DISABLE_UNGLOSSED_REFERENCE_GATE=1', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
