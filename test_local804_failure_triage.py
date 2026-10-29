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
    # LOCAL-804B: a 402 "out of credit" is now the dedicated `budget` class, not
    # the generic `external` — the fix is to top up / raise the cap, not retry.
    assert f(_ev(http_status=402, message="gemini out of credit")) == "budget"
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


# ===========================================================================
# LOCAL-804B — the four review fixes, each with fixtures.
# ===========================================================================

# ---------------------------------------------------------------------------
# A. Test-traffic exclusion (test/TEST/p1- ids, LOCAL-NNN harnesses) +
#    --include-tests.
# ---------------------------------------------------------------------------

def test_looks_like_test_id_prefixes_and_harness():
    f = ft._looks_like_test_id
    # Prefixes.
    assert f("test-local365-type")
    assert f("TEST-123")
    assert f("test_local156_fe633157")
    assert f("p1-probe-99")
    # Embedded LOCAL-NNN harness ids.
    assert f("local365")
    assert f("run-local-156")
    assert f("LOCAL_804")
    # Real ids are NOT test traffic.
    assert not f("0a36d3be-1d15-41a6-8058-c22d4aebce62")
    assert not f("tour_1a16bdc56b2")
    assert not f(None)
    assert not f("")


def test_is_test_event_checks_all_id_fields():
    # A real production failure (no synthetic id anywhere).
    assert not ft.is_test_event(_ev(tour_id="0a36d3be-1d15-41a6-8058-c22d",
                                    user_id=None))
    # tour_id test prefix.
    assert ft.is_test_event(_ev(tour_id="test-local365-type"))
    # user_id harness id (the real-looking tour_id must not rescue it).
    assert ft.is_test_event(_ev(tour_id="0a36d3be-1d15-41a6", 
                                user_id="test_local156_fe633157"))
    # job_id harness id.
    assert ft.is_test_event(_ev(job_id="local365", tour_id="x"))
    # explicit is_test flag.
    assert ft.is_test_event(_ev(is_test=True))


def test_filter_test_events_default_and_include():
    evs = [
        _ev(tour_id="test-local365-type", error_code="exhibition_closed"),
        _ev(tour_id="test-local365-type", error_code="exhibition_closed"),
        _ev(user_id="test_local156_fe633157", error_code="generation_failed"),
        _ev(tour_id="0a36d3be-1d15-41a6-8058-c22d", exception_type="KeyError"),
    ]
    kept, excluded = ft.filter_test_events(evs)
    assert excluded == 3
    assert len(kept) == 1
    assert kept[0]["tour_id"] == "0a36d3be-1d15-41a6-8058-c22d"
    # include_tests keeps everything but still reports the count.
    kept2, excluded2 = ft.filter_test_events(evs, include_tests=True)
    assert excluded2 == 3
    assert len(kept2) == 4


def test_run_excludes_test_traffic_by_default():
    # Mirror the first report: 74 test `exhibition_closed` + 1 real crash.
    evs = [_ev(tour_id="test-local365-type", service="generator",
               error_code="exhibition_closed",
               message="The exhibition closed", triage="ux", ts=NOW)
           for _ in range(74)]
    evs.append(_ev(tour_id="df91b3c1-real", exception_type="ValueError",
                   message="real crash", ts=NOW))
    res_default = ft.run(days=7, events=list(evs), now=NOW, dry_run=True)
    # The 74 test events are gone; only the real crash remains.
    assert res_default["event_count"] == 1
    assert res_default["excluded_tests"] == 74
    assert "test/harness events excluded" in res_default["report_md"]
    # With include_tests the test traffic is back.
    res_incl = ft.run(days=7, events=list(evs), now=NOW, dry_run=True,
                      include_tests=True)
    assert res_incl["event_count"] == 75
    assert res_incl["excluded_tests"] == 74
    assert "test traffic INCLUDED" in res_incl["report_md"]


# ---------------------------------------------------------------------------
# B. Budget / external root-cause lookup from paid_api_calls.
# ---------------------------------------------------------------------------

def test_budget_hint_classifies_budget():
    f = ft.classify_event
    assert f(_ev(message="Intent analysis error: DAILY_PAID_LIMIT_USD reached")
             ) == "budget"
    assert f(_ev(http_status=402, message="gemini out of credit")) == "budget"
    assert f(_ev(message="insufficient_quota from provider")) == "budget"


def test_enrich_root_causes_attributes_budget_to_reasonless_failure():
    # A reasonless generation failure at NOW, and a 402 refusal 2 min earlier.
    fail = _ev(source="generator_jobs", service="generator",
               error_code="generation_failed",
               message="no stops could be generated", ts=NOW)
    refusals = [{"ts": NOW - timedelta(minutes=2), "kind": "gemini",
                 "status": 402, "detail_text": "out of credit"}]
    ft.enrich_root_causes([fail], refusals)
    assert fail.get("root_cause") == "budget"
    assert "budget" in fail["root_cause_detail"].lower()
    # classify now returns budget, NOT our_bug.
    assert ft.classify_event(fail) == "budget"


def test_enrich_root_causes_window_is_bounded():
    # A refusal far outside the window must NOT be attributed.
    fail = _ev(source="generator_jobs", error_code="generation_failed",
               message="no stops", ts=NOW)
    refusals = [{"ts": NOW - timedelta(hours=3), "kind": "gemini",
                 "status": 402, "detail_text": "out of credit"}]
    ft.enrich_root_causes([fail], refusals)
    assert fail.get("root_cause") is None
    # Without a budget cause it falls back to our_bug (generation_failed).
    assert ft.classify_event(fail) == "our_bug"


def test_budget_does_not_override_a_real_exception():
    # A row that names its own exception is NOT reasonless; a nearby refusal
    # must not steal it into budget.
    fail = _ev(source="failure_events", exception_type="KeyError",
               message="missing key", ts=NOW)
    refusals = [{"ts": NOW, "kind": "gemini", "status": 402,
                 "detail_text": "out of credit"}]
    ft.enrich_root_causes([fail], refusals)
    assert fail.get("root_cause") is None
    assert ft.classify_event(fail) == "our_bug"


def test_budget_group_wins_and_gets_ops_owner():
    fail = _ev(source="generator_jobs", error_code="generation_failed",
               message="no stops", ts=NOW)
    ft.enrich_root_causes([fail], [{"ts": NOW, "kind": "gemini", "status": 402,
                                    "detail_text": "out of credit"}])
    groups = ft.group_events([fail])
    ft.rank_groups(groups, NOW, set())
    assert groups[0]["class"] == "budget"
    report = ft.render_report(groups, NOW, days=7)
    assert "Budget / credit" in report
    assert "ops/budget" in report


# ---------------------------------------------------------------------------
# C. tour_request_failed requires client-side evidence before user_confusion.
# ---------------------------------------------------------------------------

def _treq(**kw):
    base = dict(source="tour_requests", service="orchestrator",
                surface="generate", error_code="tour_request_failed",
                message="tour request failed", platform="server", ts=NOW)
    base.update(kw)
    return _ev(**base)


def test_tour_request_failed_without_evidence_is_unknown():
    ev = _treq(tour_id="abc-123", request_text="Boston Common")
    evidence = ft.build_confusion_evidence([ev])
    assert ft.classify_event(ev, evidence) == "unknown"


def test_tour_request_failed_with_client_report_is_user_confusion():
    treq = _treq(tour_id="abc-123", request_text="Boston Common")
    # A client FailureReporter event (service='app') for the same tour.
    client = _ev(source="failure_events", service="app", platform="android",
                 surface="generate", error_code="tour_request_failed",
                 message="could not make tour", tour_id="abc-123", ts=NOW)
    evidence = ft.build_confusion_evidence([treq, client])
    assert ft.classify_event(treq, evidence) == "user_confusion"


def test_tour_request_failed_with_retry_is_user_confusion():
    # The same request appears twice (a user retry) → confusion signal.
    a = _treq(tour_id="t1", request_text="Arnold Arboretum, Boston")
    b = _treq(tour_id="t2", request_text="Arnold Arboretum, Boston")
    evidence = ft.build_confusion_evidence([a, b])
    assert ft.classify_event(a, evidence) == "user_confusion"
    assert ft.classify_event(b, evidence) == "user_confusion"


def test_client_signal_detection():
    assert ft._is_client_signal(_ev(service="app", platform="server"))
    assert ft._is_client_signal(_ev(service="generator", platform="ios"))
    assert not ft._is_client_signal(_ev(service="generator", platform="server"))
    assert not ft._is_client_signal(_ev(service="orchestrator",
                                        platform="unknown"))


# ---------------------------------------------------------------------------
# D. The launchd plist FILE meets the spec (02:30 daily, Mac DB, reports/).
# ---------------------------------------------------------------------------

def test_plist_file_meets_spec():
    import plistlib
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".continuous_dev",
                        "com.audioura.failure-triage.plist")
    assert os.path.exists(path), "plist FILE must exist"
    with open(path, "rb") as f:
        pl = plistlib.load(f)
    # Runs failure_triage.py.
    args = pl["ProgramArguments"]
    assert any("failure_triage.py" in a for a in args)
    # No --llm (nightly run must make NO paid call; cap $0).
    assert "--llm" not in args
    # 02:30 daily.
    sci = pl["StartCalendarInterval"]
    assert sci["Hour"] == 2 and sci["Minute"] == 30
    # Mac dev DB on localhost:5433.
    env = pl["EnvironmentVariables"]
    assert env["DB_HOST"] == "localhost"
    assert str(env["DB_PORT"]) == "5433"
    # It is a FILE only — NOT installed under LaunchAgents by this task.
    home_agent = os.path.expanduser(
        "~/Library/LaunchAgents/com.audioura.failure-triage.plist")
    # (We only assert the source file exists; we never install it.)
    assert path != home_agent


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
