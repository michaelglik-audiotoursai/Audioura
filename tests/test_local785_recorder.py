#!/usr/bin/env python3
"""[LOCAL-785] failure_log recorder + failure_report scoring — red-first.

Proves the recorder's HARD CONTRACT and the report's ranking without a DB:

  * record() NEVER raises, even with the DB unreachable, and in that case emits
    the event as a `FAILURE_EVENT {json}` line on stdout (the 445/446 recovery).
  * The signature is STABLE across ids / numbers / quoted strings.
  * Auto-triage follows the documented rules table.
  * failure_report ranks groups by priority score (a crash hitting many users
    outranks an honest UX refusal; a userless real failure still scores).

Run: python3 -m pytest tests/test_local785_recorder.py -q
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import failure_log as fl
import failure_report as fr


# --- signature ------------------------------------------------------------

def test_signature_is_16_hex_chars():
    sig = fl.compute_signature("orchestrator", "generation_failed", "Exception",
                               "Tour 445 failed")
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig)


def test_signature_stable_across_ids_numbers_and_quotes():
    a = fl.compute_signature("orchestrator", "generation_failed", "Exception",
                             'Tour 445 ("Boston Common") failed after 3 polls')
    b = fl.compute_signature("orchestrator", "generation_failed", "Exception",
                             'Tour 446 ("Paris 7e") failed after 11 polls')
    c = fl.compute_signature("orchestrator", "generation_failed", "Exception",
                             'Tour 999999 ("x") failed after 1 polls')
    assert a == b == c, "ids/numbers/quotes must not change the signature"


def test_signature_differs_on_real_difference():
    a = fl.compute_signature("orchestrator", "generation_failed", "Exception", "boom")
    b = fl.compute_signature("generator", "generation_failed", "Exception", "boom")
    c = fl.compute_signature("orchestrator", "venue_closed", "Exception", "boom")
    assert len({a, b, c}) == 3


# --- auto-triage ----------------------------------------------------------

def test_auto_triage_rules():
    assert fl.auto_triage("no_matching_places_in_area", None, None) == "ux"
    assert fl.auto_triage("venue_no_verifiable_content", None, None) == "ux"
    assert fl.auto_triage("exhibition_not_found", None, None) == "absence"
    assert fl.auto_triage("by_reference_no_material", None, None) == "absence"
    assert fl.auto_triage("generation_failed", None, None) == "our_bug"
    assert fl.auto_triage(None, None, 500) == "our_bug"
    assert fl.auto_triage(None, "ReadTimeout", None) == "external"
    assert fl.auto_triage(None, "ConnectionError", None) == "external"
    assert fl.auto_triage(None, "ValueError", None) == "our_bug"
    assert fl.auto_triage(None, None, None) == "unknown"


# --- record() never raises; stdout fallback when DB is down ---------------

def _force_db_down():
    # Point at a port that refuses fast so the 1s timeout is never the slow path.
    os.environ["DATABASE_URL"] = "postgresql://u:p@127.0.0.1:1/db"
    os.environ["FAILURE_LOG_DB_TIMEOUT"] = "1"


def test_record_never_raises_with_db_down(capsys):
    _force_db_down()
    sig = fl.record(service="orchestrator", surface="generate",
                    message="boom", exception_type="ValueError", job_id="j1")
    assert len(sig) == 16
    out = capsys.readouterr().out
    assert "FAILURE_EVENT " in out, "a down DB must still emit the event on stdout"
    assert "db_unavailable" in out


def test_record_never_raises_with_bad_arguments():
    _force_db_down()
    # Even nonsense arguments must not raise.
    sig = fl.record(service="x", http_status="not-an-int", tour_id=object())
    assert isinstance(sig, str)


def test_record_fills_exception_from_exc(capsys):
    _force_db_down()
    try:
        raise RuntimeError("kaboom 42")
    except RuntimeError as e:
        sig = fl.record(service="generator", surface="generate", exc=e)
    out = capsys.readouterr().out
    assert "RuntimeError" in out
    assert len(sig) == 16


# --- report ranking -------------------------------------------------------

def test_report_ranks_our_bug_above_ux_at_equal_reach():
    now = datetime.now(timezone.utc)
    bug = fr.priority_score(10, "our_bug", now, now)
    ux = fr.priority_score(10, "ux", now, now)
    assert bug > ux


def test_report_recency_lowers_score():
    now = datetime.now(timezone.utc)
    fresh = fr.priority_score(5, "our_bug", now, now)
    stale = fr.priority_score(5, "our_bug", now - timedelta(days=30), now)
    assert fresh > stale


def test_report_userless_failure_still_scores():
    now = datetime.now(timezone.utc)
    assert fr.priority_score(0, "our_bug", now, now) > 0


def test_parse_since_units():
    assert fr.parse_since("24h") == timedelta(hours=24)
    assert fr.parse_since("7d") == timedelta(days=7)
    assert fr.parse_since("1h") == timedelta(hours=1)
    assert fr.parse_since("2w") == timedelta(weeks=2)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
