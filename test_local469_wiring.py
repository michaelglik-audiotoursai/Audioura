#!/usr/bin/env python3
"""test_local469_wiring.py — LOCAL-469 call-site proof.

LOCAL-465 shipped 27 green unit tests and a NameError on every live run because
every test called the decision function directly and none exercised the call
site. This test exercises the ACTUAL wiring block from generate_tour_text.py:

  1. It extracts the verbatim PHASE 5.152 source block out of
     generate_tour_text.py (so if the block is deleted or renamed, this fails).
  2. It exec()s that block in a namespace that mimics the call site — the SAME
     variable names the surrounding code binds (poi_list, api_key, os, sys) —
     with a monkeypatched requests.post so no network is touched.
  3. It asserts the block ran, imported the gate, produced its PHASE 5.152 log
     line, and mutated poi_list.

If the block references a name that does not exist at the call site (the exact
LOCAL-465 failure), exec() raises NameError here and the test goes red.
"""
import os
import re
import sys
import io
import json
import types
import unittest
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GEN_PATH = os.path.join(HERE, 'generate_tour_text.py')


def _extract_phase_block():
    """Pull the PHASE 5.152 block verbatim: from its banner comment up to (but
    not including) the next PHASE banner (5.156)."""
    src = open(GEN_PATH, encoding='utf-8').read()
    start = src.index('# -------- [LOCAL-469] PHASE 5.152: Stop-specificity gate --------')
    end = src.index('# -------- [LOCAL-263] PHASE 5.156: Unsupported-claim gate --------', start)
    block = src[start:end]
    # The block is indented one level (inside the function). Dedent 4 spaces so it
    # runs at module level in exec().
    lines = block.splitlines()
    dedented = []
    for ln in lines:
        dedented.append(ln[4:] if ln.startswith('    ') else ln)
    return '\n'.join(dedented)


class TestWiring(unittest.TestCase):

    def test_block_exists_in_source(self):
        block = _extract_phase_block()
        self.assertIn('apply_stop_specificity_gate', block)
        self.assertIn('PHASE 5.152', block)
        self.assertIn('DISABLE_STOP_SPECIFICITY_GATE', block)

    def test_call_site_executes_and_fires(self):
        """Exec the real block with the call-site's variable names bound."""
        block = _extract_phase_block()

        # A tour with a clearly transferable paragraph and ≥2 siblings so the
        # substitution verdict can reach HIGH.
        transferable = ("Cycling on the French Riviera, stop at Cap d'Antibes to "
                        "experience the enduring power of nature and soak up the "
                        "atmosphere of this everyday paradise.")
        poi_list = [
            {'name': "Cap d'Antibes", 'description': transferable + "\n\nIn 1546 the friars swapped land with Saint-Pons Abbey."},
            {'name': 'Villa Leopolda', 'description': 'Villa Leopolda was built in 1902.'},
            {'name': 'Roman Ruins', 'description': 'Cemenelum amphitheatre, 2nd century.'},
        ]

        # Monkeypatch requests.post so the DEFAULT llm path (the one the live run
        # uses) returns deterministic verdicts and never hits the network.
        import requests as _requests

        class _Resp:
            status_code = 200
            def __init__(self, content):
                self._content = content
            def json(self):
                return {"choices": [{"message": {"content": self._content}}],
                        "usage": {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 1}}

        def _fake_post(url, headers=None, data=None, timeout=None):
            payload = json.loads(data)
            user = payload["messages"][-1]["content"]
            if 'VERDICT: SPECIFIC | TRANSFERABLE' in user:
                # The Saint-Pons sentence is specific; the paradise line transfers.
                if 'Saint-Pons' in user or '1546' in user:
                    return _Resp("VERDICT: SPECIFIC\nREASON: dated event")
                return _Resp("VERDICT: TRANSFERABLE\nREASON: generic mood")
            if 'VERDICT: GROUNDED | UNGROUNDED' in user:
                return _Resp("VERDICT: GROUNDED\nREASON: link stated")
            return _Resp("VERDICT: TRANSFERABLE\nREASON: default")

        _orig_post = _requests.post
        _requests.post = _fake_post
        try:
            ns = {
                'os': os,
                'sys': sys,
                'poi_list': poi_list,
                'api_key': 'test-key',   # call site reads `api_key` from scope
            }
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(_extract_phase_block(), GEN_PATH, 'exec'), ns, ns)
            out = buf.getvalue()
        finally:
            _requests.post = _orig_post

        # The gate's real log line must appear (AC4-shape at the call site).
        self.assertIn('PHASE 5.152: Stop-specificity gate', out)
        self.assertIn('Stop-specificity gate summary', out)
        # The transferable paragraph was removed; the specific one survived.
        self.assertNotIn('everyday paradise', poi_list[0]['description'], out)
        self.assertIn('Saint-Pons', poi_list[0]['description'], out)
        # And the removal was logged with the stop and reason.
        self.assertIn('REMOVED transferable paragraph', out)
        self.assertIn("Cap d'Antibes", out)

    def test_disable_flag_at_call_site(self):
        """The DISABLE env var short-circuits the real block (no import, no run)."""
        block = _extract_phase_block()
        poi_list = [{'name': 'A', 'description': 'x'}]
        ns = {'os': os, 'sys': sys, 'poi_list': poi_list, 'api_key': None}
        os.environ['DISABLE_STOP_SPECIFICITY_GATE'] = '1'
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(block, GEN_PATH, 'exec'), ns, ns)
            out = buf.getvalue()
        finally:
            del os.environ['DISABLE_STOP_SPECIFICITY_GATE']
        self.assertIn('DISABLED by DISABLE_STOP_SPECIFICITY_GATE=1', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
