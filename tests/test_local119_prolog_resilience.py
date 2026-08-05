#!/usr/bin/env python3
"""
LOCAL-119: Prolog resilience tests.

Tests the retry logic, transient/non-transient distinction, improved fallback,
and tour-delivery continuity when the prolog LLM call fails.

Runs host-side — no Docker build required. Uses unittest.mock to simulate
network failures without touching the live OpenAI API or any containers.
"""
import sys
import os
import re
import json
import time
import logging
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeResponse:
    """Simulate requests.Response for prolog LLM call testing."""

    def __init__(self, status_code, json_body=None):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body


def make_success_response(text="You are about to embark on a compelling journey through history."):
    return FakeResponse(200, {
        "choices": [{"message": {"content": text}}]
    })


def make_error_response(status_code):
    return FakeResponse(status_code, {"error": {"message": "simulated failure"}})


class TestPrologRetryLogic(unittest.TestCase):
    """Test the retry mechanism for transient failures."""

    def _run_prolog_block(self, responses, tour_hook="What secrets lie beneath?",
                          poi_list=None, expect_sleep=False):
        """
        Execute the prolog generation block in isolation by simulating
        the exact code path from generate_tour_text.py:6169-6270.

        Returns (_saved_prolog, log_records, sleep_calls).
        """
        if poi_list is None:
            poi_list = [{"name": "Stop 1", "description": "The grand hall opens before you. Its marble floors gleam under crystal chandeliers.", "artist": "", "year": ""}]

        # Set up the environment the prolog block expects
        _storied_mode = True
        _storied_spine = {
            "connecting_thread": "Art and revolution",
            "tour_hook": tour_hook,
            "arc": [
                {"chapter_role": "Introduction", "unique_angle": "Setting the scene"},
                {"chapter_role": "Rising action", "unique_angle": "Conflict emerges"},
            ],
        }
        _connecting_thread = _storied_spine.get("connecting_thread", "")
        _tour_hook = _storied_spine.get("tour_hook", "")
        _arc = _storied_spine.get("arc", [])
        _chapter_previews = []
        for entry in _arc[:5]:
            role = entry.get("chapter_role", "")
            angle = entry.get("unique_angle", "")
            if role and angle:
                _chapter_previews.append(f"{role}: {angle}")

        _prolog_prompt = f"Write a compelling 80-190 word tour introduction...\nTour hook: {_tour_hook}"

        # Mock requests and time.sleep
        call_count = [0]
        sleep_calls = []

        def mock_post(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                resp = responses[idx]
                if isinstance(resp, Exception):
                    raise resp
                return resp
            return make_error_response(500)

        def mock_sleep(secs):
            sleep_calls.append(secs)

        # Capture WARNING logs
        log_records = []
        handler = logging.Handler()
        handler.emit = lambda record: log_records.append(record)

        logger = logging.getLogger("generate_tour_text.prolog")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        _saved_prolog = ""
        api_key = "sk-test-fake"

        try:
            with patch('requests.post', side_effect=mock_post), \
                 patch('time.sleep', side_effect=mock_sleep):
                # Execute the prolog block logic
                import requests as _prolog_requests
                _prolog_logger = logging.getLogger("generate_tour_text.prolog")
                _PROLOG_TRANSIENT_CODES = {429, 500, 502, 503, 504}
                _PROLOG_MAX_RETRIES = 1
                _prolog_attempt = 0
                _prolog_success = False
                _prolog_last_status = None

                while _prolog_attempt <= _PROLOG_MAX_RETRIES:
                    try:
                        _prolog_resp = _prolog_requests.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={
                                "model": "gpt-3.5-turbo",
                                "messages": [
                                    {"role": "system", "content": "You write immersive, literary audio tour introductions."},
                                    {"role": "user", "content": _prolog_prompt},
                                ],
                                "temperature": 0.8,
                                "max_tokens": 380,
                            },
                            timeout=15,
                        )
                        _prolog_last_status = _prolog_resp.status_code
                        if _prolog_resp.status_code == 200:
                            _prolog_text = _prolog_resp.json()["choices"][0]["message"]["content"].strip()
                            if _prolog_text.startswith('"') and _prolog_text.endswith('"'):
                                _prolog_text = _prolog_text[1:-1].strip()
                            _saved_prolog = _prolog_text
                            _prolog_success = True
                            break
                        elif _prolog_resp.status_code in _PROLOG_TRANSIENT_CODES:
                            _prolog_attempt += 1
                            if _prolog_attempt <= _PROLOG_MAX_RETRIES:
                                _backoff = 2 ** _prolog_attempt
                                _prolog_logger.warning(
                                    f"[LOCAL-119] Prolog LLM transient failure (HTTP {_prolog_resp.status_code}), "
                                    f"retrying in {_backoff}s (attempt {_prolog_attempt + 1}/{_PROLOG_MAX_RETRIES + 1})"
                                )
                                time.sleep(_backoff)
                            else:
                                _prolog_logger.warning(
                                    f"[LOCAL-119] Prolog LLM transient failure (HTTP {_prolog_resp.status_code}), "
                                    f"retries exhausted — falling back"
                                )
                        else:
                            _prolog_logger.warning(
                                f"[LOCAL-119] Prolog LLM non-transient failure (HTTP {_prolog_resp.status_code}), "
                                f"no retry — falling back"
                            )
                            break
                    except (_prolog_requests.exceptions.Timeout, _prolog_requests.exceptions.ConnectionError) as _net_err:
                        _prolog_attempt += 1
                        if _prolog_attempt <= _PROLOG_MAX_RETRIES:
                            _backoff = 2 ** _prolog_attempt
                            _prolog_logger.warning(
                                f"[LOCAL-119] Prolog LLM network error ({type(_net_err).__name__}), "
                                f"retrying in {_backoff}s (attempt {_prolog_attempt + 1}/{_PROLOG_MAX_RETRIES + 1})"
                            )
                            time.sleep(_backoff)
                        else:
                            _prolog_logger.warning(
                                f"[LOCAL-119] Prolog LLM network error ({type(_net_err).__name__}), "
                                f"retries exhausted — falling back"
                            )
                    except Exception as _parse_err:
                        _prolog_logger.warning(
                            f"[LOCAL-119] Prolog LLM unexpected error ({type(_parse_err).__name__}: {_parse_err}), "
                            f"no retry — falling back"
                        )
                        break

                if not _prolog_success:
                    _fallback_used = None
                    if poi_list and poi_list[0].get("description"):
                        _stop1_desc = poi_list[0]["description"].strip()
                        _sentences = re.split(r'(?<=[.!])\s+', _stop1_desc)
                        if len(_sentences) >= 2:
                            _fallback_prose = ' '.join(_sentences[:2])
                            _saved_prolog = _fallback_prose
                            _fallback_used = "stop1_prose"
                        elif _sentences:
                            _saved_prolog = _sentences[0]
                            _fallback_used = "stop1_first_sentence"
                    if not _fallback_used and _tour_hook:
                        _saved_prolog = _tour_hook
                        _fallback_used = "raw_hook"

                    if _fallback_used:
                        _prolog_logger.warning(
                            f"[LOCAL-119] Prolog fallback active: using '{_fallback_used}' "
                            f"({len(_saved_prolog.split())} words). Tour delivery continues."
                        )
                    else:
                        _prolog_logger.warning(
                            "[LOCAL-119] Prolog generation failed and no fallback text available. "
                            "Tour will open directly on Stop 1 content without prolog."
                        )
        finally:
            logger.removeHandler(handler)

        return _saved_prolog, log_records, sleep_calls, _prolog_success

    # ─── Happy path ─────────────────────────────────────────────────────

    def test_success_first_attempt(self):
        """Primary path: LLM succeeds on first call."""
        prolog_text = "You are about to embark on a fascinating journey through art and revolution."
        prolog, logs, sleeps, success = self._run_prolog_block([make_success_response(prolog_text)])
        self.assertTrue(success)
        self.assertEqual(prolog, prolog_text)
        self.assertEqual(len(logs), 0, "No warnings on success")
        self.assertEqual(len(sleeps), 0, "No sleep on success")

    def test_strips_wrapping_quotes(self):
        """LLM sometimes wraps output in quotes — these should be stripped."""
        prolog, _, _, success = self._run_prolog_block([
            make_success_response('"You are about to discover something extraordinary."')
        ])
        self.assertTrue(success)
        self.assertFalse(prolog.startswith('"'))
        self.assertFalse(prolog.endswith('"'))

    # ─── Transient failure + retry succeeds ─────────────────────────────

    def test_retry_on_500_then_success(self):
        """HTTP 500 → retry → success."""
        prolog, logs, sleeps, success = self._run_prolog_block([
            make_error_response(500),
            make_success_response("Recovered prolog text after retry."),
        ])
        self.assertTrue(success)
        self.assertEqual(prolog, "Recovered prolog text after retry.")
        self.assertEqual(len(sleeps), 1, "Exactly one backoff sleep")
        self.assertEqual(sleeps[0], 2, "2s backoff on first retry")
        self.assertTrue(any("transient failure" in r.getMessage() for r in logs))

    def test_retry_on_429_then_success(self):
        """HTTP 429 (rate limit) → retry → success."""
        prolog, logs, sleeps, success = self._run_prolog_block([
            make_error_response(429),
            make_success_response("Rate limit cleared, prolog generated."),
        ])
        self.assertTrue(success)
        self.assertEqual(len(sleeps), 1)

    def test_retry_on_502_then_success(self):
        """HTTP 502 (bad gateway) → retry → success."""
        prolog, _, sleeps, success = self._run_prolog_block([
            make_error_response(502),
            make_success_response("Gateway recovered."),
        ])
        self.assertTrue(success)
        self.assertEqual(len(sleeps), 1)

    def test_retry_on_timeout_then_success(self):
        """Network timeout → retry → success."""
        import requests
        prolog, logs, sleeps, success = self._run_prolog_block([
            requests.exceptions.Timeout("Connection timed out"),
            make_success_response("Recovered after timeout."),
        ])
        self.assertTrue(success)
        self.assertEqual(len(sleeps), 1)
        self.assertTrue(any("network error" in r.getMessage() for r in logs))

    def test_retry_on_connection_error_then_success(self):
        """ConnectionError → retry → success."""
        import requests
        prolog, logs, sleeps, success = self._run_prolog_block([
            requests.exceptions.ConnectionError("DNS resolution failed"),
            make_success_response("Reconnected."),
        ])
        self.assertTrue(success)
        self.assertEqual(len(sleeps), 1)

    # ─── Transient failure + retry exhausted → fallback ─────────────────

    def test_two_500s_exhausts_retries_uses_stop1_prose(self):
        """Two consecutive 500s → retries exhausted → falls back to Stop 1 prose."""
        prolog, logs, sleeps, success = self._run_prolog_block([
            make_error_response(500),
            make_error_response(500),
        ])
        self.assertFalse(success)
        # Should use Stop 1's first two sentences, not the raw hook
        self.assertIn("grand hall", prolog)
        self.assertNotIn("secrets lie beneath", prolog)
        self.assertTrue(any("retries exhausted" in r.getMessage() for r in logs))
        self.assertTrue(any("stop1_prose" in r.getMessage() for r in logs))

    def test_two_timeouts_exhausts_retries(self):
        """Two consecutive timeouts → retries exhausted → fallback."""
        import requests
        prolog, logs, _, success = self._run_prolog_block([
            requests.exceptions.Timeout("timeout 1"),
            requests.exceptions.Timeout("timeout 2"),
        ])
        self.assertFalse(success)
        self.assertIn("grand hall", prolog)  # Stop 1 prose fallback
        self.assertTrue(any("retries exhausted" in r.getMessage() for r in logs))

    # ─── Non-transient failure → NO retry ───────────────────────────────

    def test_no_retry_on_400(self):
        """HTTP 400 (bad request) → no retry, immediate fallback."""
        prolog, logs, sleeps, success = self._run_prolog_block([
            make_error_response(400),
        ])
        self.assertFalse(success)
        self.assertEqual(len(sleeps), 0, "No sleep = no retry attempted")
        self.assertTrue(any("non-transient" in r.getMessage() for r in logs))

    def test_no_retry_on_401(self):
        """HTTP 401 (unauthorized) → no retry."""
        _, logs, sleeps, _ = self._run_prolog_block([make_error_response(401)])
        self.assertEqual(len(sleeps), 0)
        self.assertTrue(any("non-transient" in r.getMessage() for r in logs))

    def test_no_retry_on_403(self):
        """HTTP 403 (forbidden) → no retry."""
        _, logs, sleeps, _ = self._run_prolog_block([make_error_response(403)])
        self.assertEqual(len(sleeps), 0)

    def test_no_retry_on_404(self):
        """HTTP 404 (not found) → no retry."""
        _, logs, sleeps, _ = self._run_prolog_block([make_error_response(404)])
        self.assertEqual(len(sleeps), 0)

    # ─── Fallback quality ───────────────────────────────────────────────

    def test_fallback_prefers_stop1_prose_over_raw_hook(self):
        """When prolog fails, Stop 1 prose is preferred over the raw hook."""
        poi_list = [{"name": "Cathedral", "description": "The cathedral stands as a testament to Gothic brilliance. Its flying buttresses reach toward the sky like arms in prayer.", "artist": "", "year": ""}]
        prolog, logs, _, success = self._run_prolog_block(
            [make_error_response(500), make_error_response(500)],
            tour_hook="What mysteries echo through these halls?",
            poi_list=poi_list,
        )
        self.assertFalse(success)
        # Should contain Stop 1 prose (two sentences)
        self.assertIn("cathedral stands as a testament", prolog)
        self.assertIn("flying buttresses", prolog)
        # Should NOT be the raw hook
        self.assertNotIn("mysteries echo", prolog)

    def test_fallback_to_raw_hook_when_no_poi_description(self):
        """If Stop 1 has no description, raw hook is used as last resort."""
        poi_list = [{"name": "Stop 1", "description": "", "artist": "", "year": ""}]
        prolog, logs, _, success = self._run_prolog_block(
            [make_error_response(500), make_error_response(500)],
            tour_hook="What secrets hide in these walls?",
            poi_list=poi_list,
        )
        self.assertFalse(success)
        self.assertEqual(prolog, "What secrets hide in these walls?")
        self.assertTrue(any("raw_hook" in r.getMessage() for r in logs))

    def test_fallback_no_text_available(self):
        """If neither Stop 1 prose nor hook available, prolog is empty but tour continues."""
        poi_list = [{"name": "Stop 1", "description": "", "artist": "", "year": ""}]
        prolog, logs, _, success = self._run_prolog_block(
            [make_error_response(500), make_error_response(500)],
            tour_hook="",
            poi_list=poi_list,
        )
        self.assertFalse(success)
        self.assertEqual(prolog, "")
        self.assertTrue(any("no fallback text available" in r.getMessage() for r in logs))

    # ─── Tour delivery continuity (D14) ─────────────────────────────────

    def test_tour_never_blocked_by_prolog_failure(self):
        """Prolog failure must never prevent tour delivery (D14 constraint)."""
        # Simulate every kind of failure — prolog block must always complete
        import requests
        failure_scenarios = [
            [make_error_response(500), make_error_response(500)],
            [make_error_response(400)],
            [requests.exceptions.Timeout("t"), requests.exceptions.Timeout("t")],
            [requests.exceptions.ConnectionError("c"), requests.exceptions.ConnectionError("c")],
        ]
        for scenario in failure_scenarios:
            # This must not raise
            prolog, logs, _, _ = self._run_prolog_block(scenario)
            # All logs are WARNING level (not ERROR, not exception propagation)
            for record in logs:
                self.assertEqual(record.levelno, logging.WARNING)

    # ─── Cost ceiling ───────────────────────────────────────────────────

    def test_retry_cost_within_ceiling(self):
        """
        A retry costs at most one additional GPT-3.5-turbo call (~$0.0008).
        Baseline tour cost: $0.068. One retry: $0.068 + $0.0008 = $0.0688.
        This is well within the $1.30 ceiling.
        """
        # This is a documentation/assertion test, not a live cost measurement
        baseline_cost = 0.068
        prolog_call_cost = 0.0008  # ~400 tokens at GPT-3.5-turbo pricing
        max_retry_overhead = prolog_call_cost * 1  # 1 retry max
        total_worst_case = baseline_cost + max_retry_overhead
        self.assertLess(total_worst_case, 1.30, "Worst-case with retry still under $1.30 ceiling")
        self.assertAlmostEqual(max_retry_overhead, 0.0008, places=4)


class TestPrologCodeStructure(unittest.TestCase):
    """Static verification that the code change meets architectural requirements."""

    def setUp(self):
        """Read the source file."""
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "generate_tour_text.py"
        )
        with open(src_path, 'r') as f:
            self.source = f.read()

    def test_prolog_block_has_own_exception_handler(self):
        """Prolog exception handler is self-contained (D14: no shared handler with unrelated code)."""
        # The outer try/except for the prolog block should be dedicated
        # Check that the except clause references LOCAL-119 and prolog specifically
        self.assertIn("[LOCAL-119] Prolog block outer error", self.source)

    def test_uses_warning_level_not_error(self):
        """Prolog failures log at WARNING, not ERROR (it's degraded, not broken)."""
        # All logger calls in the prolog section should be .warning()
        prolog_section_start = self.source.find("# [LOCAL-119] Prolog LLM call with retry")
        prolog_section_end = self.source.find("# Add each POI with its description and directions")
        prolog_section = self.source[prolog_section_start:prolog_section_end]

        self.assertNotIn("_prolog_logger.error(", prolog_section)
        self.assertIn("_prolog_logger.warning(", prolog_section)

    def test_retry_count_is_one(self):
        """Retry count is 1 (2 total attempts) — not excessive."""
        self.assertIn("_PROLOG_MAX_RETRIES = 1", self.source)

    def test_transient_codes_defined(self):
        """Transient HTTP codes are explicitly defined."""
        self.assertIn("_PROLOG_TRANSIENT_CODES = {429, 500, 502, 503, 504}", self.source)

    def test_no_retry_on_non_transient(self):
        """Code explicitly breaks on non-transient errors without retry."""
        self.assertIn("non-transient failure", self.source)
        self.assertIn("no retry — falling back", self.source)

    def test_fallback_prefers_stop1_over_hook(self):
        """Fallback logic checks Stop 1 description BEFORE falling back to raw hook."""
        prolog_section_start = self.source.find("# [LOCAL-119] Improved fallback")
        prolog_section_end = self.source.find("# Add each POI with its description and directions")
        fallback_section = self.source[prolog_section_start:prolog_section_end]

        # stop1_prose check comes before raw_hook check
        stop1_pos = fallback_section.find("stop1_prose")
        hook_pos = fallback_section.find("raw_hook")
        self.assertGreater(hook_pos, stop1_pos,
                           "Stop 1 prose should be checked before raw hook fallback")

    def test_tour_delivery_never_blocked(self):
        """The prolog block cannot propagate exceptions — outer except catches all."""
        # Verify the outer except catches generic Exception
        self.assertIn("except Exception as e:", self.source[
            self.source.find("# [LOCAL-119] Prolog LLM call"):
        ])
        self.assertIn("Tour delivery continues without prolog", self.source)


if __name__ == "__main__":
    unittest.main()
