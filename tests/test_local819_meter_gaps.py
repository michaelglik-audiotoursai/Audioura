"""Test suite for LOCAL-819: close the paid-API meter gaps.

Covers the four changes this task makes to the meter and its reporting, with NO
real paid call and NO network (httpx.MockTransport) and NO DB (the DB write is
stubbed, the log goes to a tmp file):

  token=0 fix        — an OpenAI chat response is metered with TOP-LEVEL
                       tokens_in / tokens_out (not only nested under usage), so the
                       report page stops showing 0 on every row. Same for Anthropic.
  key_suffix         — a row carries the NON-sensitive METER_KEY_SUFFIX tag.
  service default    — SERVICE falls back to TASK_BUDGET_ID when METER_SERVICE is
                       unset (so every budgeted task container tags service=<id>),
                       and METER_SERVICE still overrides.
  meter_report       — aggregation totals by day / service / model / key-suffix,
                       filters by --since, and sums tokens from the top-level fields.
"""
import importlib
import json
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "_meter"))

httpx = pytest.importorskip("httpx")


@pytest.fixture
def meter(monkeypatch, tmp_path):
    """The meter writing to a tmp log, DB + daily-limit stubbed. install() is
    idempotent so it never double-wraps."""
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)
    monkeypatch.setattr(m, "check_task_budget", lambda: None)
    m.install()
    m._LOG_PATH_FOR_TEST = str(log)
    return m


def _read_log(m):
    path = m._LOG_PATH_FOR_TEST
    recs = []
    if not os.path.exists(path):
        return recs
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


# ── token=0 fix ───────────────────────────────────────────────────────────────
def test_openai_row_has_top_level_tokens(meter):
    """The whole bug: OpenAI rows showed tokens_in/out = 0 because the counts
    lived only under usage. They must now be at the top level too."""
    def handler(request):
        return httpx.Response(200, json={
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 123, "completion_tokens": 45,
                      "total_tokens": 168},
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini"})
    recs = _read_log(meter)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "openai"
    assert r["tokens_in"] == 123, "prompt_tokens must be surfaced as tokens_in"
    assert r["tokens_out"] == 45, "completion_tokens must be surfaced as tokens_out"
    # usage dict is still present (back-compat) and the $ unchanged.
    assert r["usage"]["prompt_tokens"] == 123
    assert abs(r["usd"] - (123 * 0.15 + 45 * 0.60) / 1e6) < 1e-12


def test_openai_tokens_helper_both_shapes():
    import paid_api_meter as m
    # chat/completions shape
    assert m._openai_tokens({"prompt_tokens": 10, "completion_tokens": 3}) == (10, 3)
    # responses API shape
    assert m._openai_tokens({"input_tokens": 7, "output_tokens": 2}) == (7, 2)
    # empty / junk never raises
    assert m._openai_tokens({}) == (0, 0)
    assert m._openai_tokens({"prompt_tokens": None}) == (0, 0)


def test_anthropic_row_has_top_level_tokens(meter):
    def handler(request):
        return httpx.Response(200, json={
            "model": "claude-haiku-4-5-20251001",
            "usage": {"input_tokens": 80, "output_tokens": 20,
                      "cache_read_input_tokens": 10},
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.post("https://api.anthropic.com/v1/messages",
                json={"model": "claude-haiku-4-5"})
    recs = _read_log(meter)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "anthropic"
    # input_tokens (uncached) + cache_read folded in = 90
    assert r["tokens_in"] == 90
    assert r["tokens_out"] == 20


def test_anthropic_tokens_helper():
    import paid_api_meter as m
    assert m._anthropic_tokens(
        {"input_tokens": 80, "output_tokens": 20,
         "cache_read_input_tokens": 10}) == (90, 20)
    assert m._anthropic_tokens({}) == (0, 0)


# ── key_suffix ──────────────────────────────────────────────────────────────
def test_key_suffix_on_row(meter, monkeypatch):
    monkeypatch.setenv("METER_KEY_SUFFIX", "k9sA")

    def handler(request):
        return httpx.Response(200, json={
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini"})
    recs = _read_log(meter)
    assert recs[-1]["key_suffix"] == "k9sA"


def test_key_suffix_absent_is_empty(meter, monkeypatch):
    monkeypatch.delenv("METER_KEY_SUFFIX", raising=False)

    def handler(request):
        return httpx.Response(200, json={
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini"})
    assert _read_log(meter)[-1]["key_suffix"] == ""


def test_key_suffix_truncates_and_never_logs_full_key(monkeypatch):
    import paid_api_meter as m
    # A long value is truncated to the last 8 chars — never the whole key.
    monkeypatch.setenv("METER_KEY_SUFFIX", "sk-proj-SECRETlongkey_endsk9sA")
    assert m._key_suffix() == "_endsk9sA"[-8:]
    assert len(m._key_suffix()) <= 8


# ── service default (TASK_BUDGET_ID) ─────────────────────────────────────────
def test_service_defaults_to_task_budget_id(monkeypatch):
    monkeypatch.delenv("METER_SERVICE", raising=False)
    monkeypatch.setenv("TASK_BUDGET_ID", "LOCAL-819")
    import paid_api_meter as m
    assert m._default_service() == "LOCAL-819"


def test_meter_service_overrides_task_budget_id(monkeypatch):
    monkeypatch.setenv("METER_SERVICE", "explicit-service")
    monkeypatch.setenv("TASK_BUDGET_ID", "LOCAL-819")
    import paid_api_meter as m
    assert m._default_service() == "explicit-service"


# ── meter_container_env helper ────────────────────────────────────────────────
def test_docker_meter_args_contract(tmp_path):
    import meter_container_env as mce
    args = mce.docker_meter_args(task_id="LOCAL-819",
                                 meter_dir="/repo/_meter",
                                 host_meter_dir=str(tmp_path),
                                 key_suffix="k9sA")
    joined = " ".join(args)
    assert "METER_SERVICE=LOCAL-819" in joined
    assert "PAID_API_LOG=/meterlogs/paid_api_calls.jsonl" in joined
    assert "PYTHONPATH=/opt/meter" in joined
    assert "%s:/meterlogs" % tmp_path in joined
    assert "/repo/_meter:/opt/meter:ro" in joined
    assert "METER_KEY_SUFFIX=k9sA" in joined


# ── meter_report aggregation ─────────────────────────────────────────────────
def _write_rows(path, rows):
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_meter_report_aggregates(tmp_path):
    import meter_report as rep
    log = tmp_path / "paid_api_calls.jsonl"
    _write_rows(log, [
        {"ts": "2026-10-26T05:00:00Z", "kind": "openai", "status": 200,
         "service": "LOCAL-819", "model": "gpt-4o-mini-2024-07-18",
         "key_suffix": "k9sA", "usd": 0.01, "tokens_in": 100, "tokens_out": 50},
        {"ts": "2026-10-26T06:00:00Z", "kind": "openai", "status": 200,
         "service": "LOCAL-819", "model": "gpt-4.1", "key_suffix": "k9sA",
         "usd": 0.20, "tokens_in": 1000, "tokens_out": 200},
        # before --since: must be excluded
        {"ts": "2026-10-25T23:59:59Z", "kind": "openai", "status": 200,
         "service": "LOCAL-819", "model": "gpt-4o", "key_suffix": "k9sA",
         "usd": 9.99, "tokens_in": 1, "tokens_out": 1},
        # non-200: counted as a request, $0 and tokens 0
        {"ts": "2026-10-26T07:00:00Z", "kind": "openai", "status": 429,
         "service": "LOCAL-819", "model": "gpt-4o", "key_suffix": "k9sA",
         "usd": 0.0, "tokens_in": 0, "tokens_out": 0},
    ])
    by_day, by_service, by_model, by_key, totals, scanned, kept = rep.aggregate(
        rep._iter_rows([str(log)]),
        rep._norm_since("2026-10-26"), None, billed_only=True)

    assert scanned == 4 and kept == 3  # the 10-25 row excluded by --since
    assert totals["requests"] == 3
    assert abs(totals["usd"] - 0.21) < 1e-9
    assert totals["tokens_in"] == 1100
    assert totals["tokens_out"] == 250
    # by day
    assert by_day["2026-10-26"]["requests"] == 3
    assert abs(by_day["2026-10-26"]["usd"] - 0.21) < 1e-9
    # by model (family-normalised: the dated gpt-4o-mini collapses)
    assert abs(by_model["gpt-4o-mini"]["usd"] - 0.01) < 1e-9
    assert abs(by_model["gpt-4.1"]["usd"] - 0.20) < 1e-9
    # by key-suffix
    assert by_key["k9sA"]["requests"] == 3
    # by service
    assert by_service["LOCAL-819"]["tokens_in"] == 1100


def test_meter_report_since_normalisation():
    import meter_report as rep
    assert rep._norm_since("2026-10-26") == "2026-10-26T00:00:00Z"
    assert rep._norm_since("2026-10-26T04") == "2026-10-26T04:00:00Z"
    assert rep._norm_since("2026-10-26 04:30") == "2026-10-26T04:30:00Z"
    assert rep._norm_since("2026-10-26T04:30:00Z") == "2026-10-26T04:30:00Z"


def test_meter_report_model_family_norm():
    import meter_report as rep
    assert rep._norm_model("gpt-4o-mini-2024-07-18") == "gpt-4o-mini"
    assert rep._norm_model("gpt-4.1") == "gpt-4.1"
    assert rep._norm_model("") == "(none)"
    assert rep._norm_model("gemini-flash-latest") == "gemini-flash-latest"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
