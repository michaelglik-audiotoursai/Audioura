#!/usr/bin/env python3
"""
[LOCAL-573] Unit tests for the shared /synthesize caller timeout helper.
Formula: timeout = 30 + 0.05 * len(text), capped at 180.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tts_timeout import synthesize_timeout, TTS_TIMEOUT_MAX_SECONDS  # noqa: E402


def test_base_for_empty_and_none():
    assert synthesize_timeout("") == 30.0
    assert synthesize_timeout(None) == 30.0
    assert synthesize_timeout(0) == 30.0


def test_scales_with_length():
    # 100 chars -> 30 + 5 = 35
    assert synthesize_timeout("x" * 100) == 35.0
    # 1000 chars -> 30 + 50 = 80
    assert synthesize_timeout("x" * 1000) == 80.0
    # 2300-char stop -> 30 + 115 = 145
    assert synthesize_timeout("x" * 2300) == 145.0


def test_accepts_int_char_count():
    assert synthesize_timeout(2300) == 145.0
    assert synthesize_timeout(100) == 35.0


def test_capped_at_180():
    # 3000 chars would be 30 + 150 = 180 (exactly the cap)
    assert synthesize_timeout("x" * 3000) == 180.0
    # Beyond the cap stays at 180
    assert synthesize_timeout("x" * 10000) == 180.0
    assert synthesize_timeout(1_000_000) == TTS_TIMEOUT_MAX_SECONDS


def test_never_below_base_and_handles_negative():
    assert synthesize_timeout(-5) == 30.0
    assert synthesize_timeout(1) == 30.05


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
