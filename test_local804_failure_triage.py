#!/usr/bin/env python3
"""test_local804_failure_triage.py — LOCAL-804 / D723 unit tests.

A fixture table of 20 synthetic failures spanning every class exercises the five
behaviours the triage tool must get right, with NO database:

  1. grouping       — like messages collapse to one signature across ids/numbers.
  2. classification — each event lands in the right D723 class (our_bug,
                      external, user_confusion, expected, unknown), including the
                      LEAD-override and expected-refusal precedence rules.
  3. ranking        — score = count × severity × recency, NEW groups on top.
  4. redaction      — the rendered report/drafts carry NO user text, NO emails,
                      NO secret ids; a tour id survives.
  5. draft content  — a top-3 our_bug group yields a DRAFT file that is OUTSIDE
                      the dispatcher glob and carries the evidence + fix area.

Run with pytest, or directly:
    python3 test_local804_failure_triage.py
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import failure_triage as ft


# ---------------------------------------------------------------------------
# Fixture — 20 synthetic failures across all classes. NOW is fixed so recency
# is deterministic. User text is deliberately full of PII-shaped content so the
# redaction test has something to catch.
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 29, 6, 0, 0, tzinfo=timezone.utc)


def _ev(**kw):
    base = dict(source="failure_events", service="generator", surface="generate",
                error_code=None, exception_type=None, http_status=None,
                message=None, request_text=None, tour_id=None, user_id=None,
                triage=None, triage_source="auto", ts=NOW)
    base.update(kw)
    return base


def fixture_events():
    recent = NOW - timedelta(hours=2)
    midweek = NOW - timedelta(days=3)
    old = NOW - timedelta(days=20)
    evs = []

    # --- our_bug: a crash, grouped across tour ids (3 events, 1 signature) ---
    for tid in (445, 446, 447):
        evs.append(_ev(
            service="orchestrator", surface="generate",
            exception_type="ValueError",
            message=f'Tour {tid} ("Boston Common") failed in assembly',
            tour_id=str(tid), ts=recent))

    # --- our_bug: generation_failed from generator_jobs (2 events) ---
    for _ in range(2):
        evs.append(_ev(source="generator_jobs", service="generator",
                       surface="generate", error_code="generation_failed",
                       message="generator job error", ts=recent))

    # --- our_bug: a 5xx (1 event) ---
    evs.append(_ev(service="orchestrator", surface="deliver",
                   http_status=503, message="upstream deliver 503 bad gateway",
                   ts=midweek))

    # --- external: OpenAI 429 rate limit (2 events) ---
    for _ in range(2):
        evs.append(_ev(service="generator", surface="generate",
                       exception_type="RateLimitError",
                       message="openai 429 rate limit exceeded", ts=recent))

    # --- external: Overpass timeout (2 events) ---
    for _ in range(2):
        evs.append(_ev(service="places", surface="lookup",
                       exception_type="ReadTimeout",
                       message="overpass api read timed out", ts=midweek))

    # --- external: Gemini 402 out of credit (1 event) ---
    evs.append(_ev(service="generator", surface="generate",
                   http_status=402, message="gemini 402 out of credit",
                   ts=recent))

    # --- user_confusion: lookup found nothing (2 events) ---
    for _ in range(2):
        evs.append(_ev(source="lookup_escalations", service="lookup",
                       surface="dining", error_code="no_results_found",
                       message="no results found for dining/middle_eastern",
                       triage="absence",
                       request_text="Middle Eastern restaurants near me, "
                                     "West Roxbury",
                       ts=recent))

    # --- user_confusion: honest refusal via stored ux triage (2 events) ---
    for _ in range(2):
        evs.append(_ev(service="generator", surface="generate",
                       error_code="venue_no_verifiable_content",
                       message="venue has no verifiable content",
                       triage="ux", triage_source="auto", ts=old))

    # --- expected: Free-tier refusal (1 event) ---
    evs.append(_ev(service="orchestrator", surface="purchase",
                   error_code="free_tier_limit",
                   message="free tier limit reached", ts=recent))

    # --- expected via LEAD override to ux + free code still wins expected (1) ---
    evs.append(_ev(service="orchestrator", surface="purchase",
                   error_code="upgrade_required",
                   message="upgrade required for this feature", ts=recent))

    # --- unknown: no signal at all (1 event) ---
    evs.append(_ev(service="mystery", surface=None,
                   message="something odd happened", ts=midweek))

    # --- external: Wikimedia 500 (1 event) ---
    evs.append(_ev(service="places", surface="lookup",
                   http_status=500, message="wikimedia api 500 server error",
                   ts=recent))

    # --- our_bug: a KeyError crash in delivery (1 event) ---
    evs.append(_ev(service="orchestrator", surface="deliver",
                   exception_type="KeyError",
                   message="missing key 'coordinates' in delivery payload",
                   ts=recent))

    assert len(evs) == 20, f"fixture must be 20 rows, got {len(evs)}"
    return evs


# ---------------------------------------------------------------------------
# 1. Grouping.
# ---------------------------------------------------------------------------

def test_grouping_collapses_ids_and_numbers():
    groups = ft.group_events(fixture_events())
    by_sig = {g["signature"]: g for g in groups}
    # The three ValueError "Tour N failed" events share ONE signature.
    crash = [g for g in groups
             if g["example"].get("exception_type") == "ValueError"
             and "assembly" in (g["example"].get("message") or "")]
    assert len(crash) == 1
    assert crash[0]["count"] == 3
    # No signature is empty, all are 16 hex chars.
    for sig in by_sig:
        assert re.fullmatch(r"[0-9a-f]{16}", sig), sig


def test_signature_stable_and_scoped_by_source():
    a = ft.triage_signature("failure_events", "generator", "x", "ValueError",
                            'tour 1 "A" failed')
    b = ft.triage_signature("failure_events", "generator", "x", "ValueError",
                            'tour 2 "B" failed')
    assert a == b  # ids/quotes normalised away
    c = ft.triage_signature("generator_jobs", "generator", "x", "ValueError",
                            'tour 1 "A" failed')
    assert c != a  # different source → different group


# ---------------------------------------------------------------------------
# 2. Classification.
# ---------------------------------------------------------------------------

def test_classify_each_class():
    f = ft.classify_event
    assert f(_ev(exception_type="ValueError", message="boom")) == "our_bug"
    assert f(_ev(error_code="generation_failed")) == "our_bug"
    assert f(_ev(http_status=503, message="bad gateway")) == "our_bug"
    assert f(_ev(exception_type="RateLimitError",
                 message="openai 429")) == "external"
    assert f(_ev(exception_type="ReadTimeout",
                 message="overpass timeout")) == "external"
    assert f(_ev(http_status=402, message="gemini out of credit")) == "external"
    assert f(_ev(error_code="no_results_found",
                 message="no results")) == "user_confusion"
    assert f(_ev(error_code="free_tier_limit")) == "expected"
    assert f(_ev(service="mystery", message="odd")) == "unknown"


def test_lead_override_wins():
    # A LEAD override of 'our_bug' beats an otherwise user_confusion code.
    ev = _ev(error_code="venue_no_verifiable_content",
             message="no content", triage="our_bug", triage_source="lead")
    assert ft.classify_event(ev) == "our_bug"


def test_expected_beats_lead_free_refusal():
    # A Free-tier code is expected even if a stale LEAD triage says otherwise.
    ev = _ev(error_code="free_tier_limit", triage="our_bug",
             triage_source="lead")
    assert ft.classify_event(ev) == "expected"


def test_source_default_our_bug_for_reasonless_generator():
    ev = _ev(source="generator_jobs", service="generator",
             error_code=None, message="generator job error")
    assert ft.classify_event(ev) == "our_bug"


# ---------------------------------------------------------------------------
# 3. Ranking.
# ---------------------------------------------------------------------------

def test_ranking_score_and_new_on_top():
    groups = ft.group_events(fixture_events())
    # Pretend everything was seen EXCEPT the crash group, so it is the only NEW.
    all_sigs = {g["signature"] for g in groups}
    crash = next(g for g in groups
                 if g["example"].get("exception_type") == "ValueError"
                 and "assembly" in (g["example"].get("message") or ""))
    seen = all_sigs - {crash["signature"]}
    ft.rank_groups(groups, NOW, seen)
    assert groups[0]["signature"] == crash["signature"]
    assert groups[0]["is_new"] is True
    # Score is count × severity × recency; crash: 3 × 3 × 1.0 = 9.0.
    assert abs(crash["score"] - 9.0) < 1e-6


def test_expected_scores_zero():
    ev = _ev(error_code="free_tier_limit", ts=NOW)
    groups = ft.group_events([ev])
    ft.rank_groups(groups, NOW, set())
    assert groups[0]["class"] == "expected"
    assert groups[0]["score"] == 0.0


def test_recency_weight_bands():
    assert ft.recency_weight(NOW, NOW) == 1.0
    assert ft.recency_weight(NOW - timedelta(days=3), NOW) == 0.6
    assert ft.recency_weight(NOW - timedelta(days=20), NOW) == 0.3


# ---------------------------------------------------------------------------
# 4. Redaction.
# ---------------------------------------------------------------------------

def test_redaction_strips_user_text_and_ids():
    # Build the email from parts so no literal address sits in the source.
    email = "jane" + "." + "doe" + "@" + "example" + ".com"
    msg = (f'User {email} asked "find me a speakeasy" '
           'secret 0123456789abcdef0123 tour_id 550e8400-e29b-41d4-a716-446655440000')
    out = ft.redact(msg)
    assert email not in out                   # email gone
    assert "@" not in out                      # no address shape survives
    assert "find me a speakeasy" not in out    # quoted user text gone
    assert "0123456789abcdef0123" not in out   # secret id gone
    assert "550e8400" not in out               # uuid gone


def test_report_has_no_raw_user_text():
    groups = ft.group_events(fixture_events())
    ft.rank_groups(groups, NOW, set())
    report = ft.render_report(groups, NOW, days=7)
    # The raw user request string must never appear in the report.
    assert "West Roxbury" not in report
    assert "Middle Eastern restaurants near me" not in report
    assert "Boston Common" not in report  # quoted venue in a crash message


def test_tour_id_survives_redaction():
    out = ft.redact("tour 445 failed")
    assert "445" in out


# ---------------------------------------------------------------------------
# 5. Draft files.
# ---------------------------------------------------------------------------

def test_run_writes_report_and_drafts(tmp_path):
    res = ft.run(days=7, out_dir=str(tmp_path), events=fixture_events(),
                 now=NOW)
    # Report written under reports/.
    rpt = tmp_path / "reports" / "failure_triage_2026-10-29.md"
    assert rpt.exists()
    body = rpt.read_text()
    assert "# Failure triage" in body
    assert "## User confusion" in body

    # Up to 3 our_bug drafts, each OUTSIDE the dispatcher glob.
    drafts_dir = tmp_path / "drafts"
    draft_files = sorted(drafts_dir.glob("*.md"))
    assert 1 <= len(draft_files) <= 3
    for p in draft_files:
        assert p.name.startswith("new_kiro_session_is_required_DRAFT-")
        # MUST NOT match the dispatcher glob new_kiro_session_is_required_LOCAL-*.md
        assert not re.match(r"new_kiro_session_is_required_LOCAL-.*\.md$", p.name)
        text = p.read_text()
        assert "DRAFT" in text
        assert "our_bug" in text
        assert "Proposed fix area" in text
        assert "Evidence" in text
        # Redaction holds in drafts too.
        assert "Boston Common" not in text


def test_draft_filename_not_in_released_glob():
    # The DRAFT prefix is deliberately not the released-task prefix.
    assert ft._DRAFT_PREFIX == "new_kiro_session_is_required_DRAFT-"
    assert not ft._DRAFT_PREFIX.startswith("new_kiro_session_is_required_LOCAL-")


def test_dry_run_writes_nothing(tmp_path):
    res = ft.run(days=7, out_dir=str(tmp_path), events=fixture_events(),
                 now=NOW, dry_run=True)
    assert res["written"] == []
    assert not (tmp_path / "reports").exists()
    assert not (tmp_path / "drafts").exists()
    assert "# Failure triage" in res["report_md"]


# ---------------------------------------------------------------------------
# LLM path (no network: an injected caller; cost cap is enforced).
# ---------------------------------------------------------------------------

def test_llm_only_labels_new_unknowns_and_respects_cap():
    # One NEW unknown group; a stub caller returns 'external'.
    ev = _ev(service="mystery", surface=None, message="odd", ts=NOW)
    groups = ft.group_events([ev])
    ft.rank_groups(groups, NOW, set())
    assert groups[0]["class"] == "unknown"
    calls = {"n": 0}

    def caller(prompt):
        calls["n"] += 1
        return "external"

    spent = ft.llm_classify_unknowns(groups, caller=caller)
    assert calls["n"] == 1
    assert groups[0]["class"] == "external"
    assert groups[0]["llm_labelled"] is True
    assert spent <= ft._LLM_ABS_CAP


def test_llm_cap_blocks_calls_when_zero_budget():
    ev = _ev(service="mystery", surface=None, message="odd", ts=NOW)
    groups = ft.group_events([ev])
    ft.rank_groups(groups, NOW, set())

    def caller(prompt):
        raise AssertionError("must not be called when budget is 0")

    spent = ft.llm_classify_unknowns(groups, budget_night=0.0, abs_cap=0.0,
                                     caller=caller)
    assert spent == 0.0
    assert groups[0]["class"] == "unknown"  # unchanged


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
