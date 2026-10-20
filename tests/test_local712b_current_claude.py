"""
Test suite for LOCAL-712B (D674 addendum 2): Anthropic's CURRENT Claude models
(Haiku 5.5, Sonnet 5.5, Opus 5.5) added as extra bake-off arms, alongside the
LOCAL-712 arms (Haiku 4.5 / Sonnet 5), which must stay untouched.

Like the LOCAL-712 suite, every test uses a STUBBED HTTP layer — no real
Anthropic/OpenAI call and no network. The DB write in the meter is monkeypatched
to a no-op and the log goes to a tmp file, so nothing touches the real
paid_api_calls ledger.

Model ids and rates confirmed from docs.anthropic.com (models overview +
pricing), read 2026-10-18:
  * claude-haiku-5-5   $0.10 in / $0.50 out  (prompts <=100k; >100k is $0.50/$2.50),
                       cache-read $0.01
  * claude-sonnet-5-5  $2.00 in / $10.00 out, cache-read $0.10
  * claude-opus-5-5    $4.00 in / $20.00 out, cache-read $0.20  (fast mode NOT used)
"""
import json
import os
import sys
import types

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "_meter"))


def _load_root_report():
    """Load the PROJECT-ROOT report.py by file path.

    A plain ``import report`` is unsafe in the full suite: another test
    (test_local611_canary.py) imports ``canary/report.py`` under the SAME top
    name ``report``, so whichever runs first wins ``sys.modules['report']``.
    Loading by path guarantees we always get the bake-off report module with
    ARM_LABEL / _model_matches, independent of test ordering.
    """
    import importlib.util
    path = os.path.join(_PROJECT_ROOT, "report.py")
    spec = importlib.util.spec_from_file_location("_local712b_root_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1) cost_rates: the official CURRENT Claude rates + llm_cost usage -> cost
# ─────────────────────────────────────────────────────────────────────────────
def test_cost_rates_has_current_claude_rates():
    import cost_rates as cr
    # <=100k tier for Haiku 5.5 (our prompts are ~3k tokens, so this always applies)
    assert cr.LLM_RATES["claude-haiku-5-5"] == {"input_per_1m": 0.10, "output_per_1m": 0.50}
    assert cr.LLM_RATES["claude-sonnet-5-5"] == {"input_per_1m": 2.00, "output_per_1m": 10.00}
    assert cr.LLM_RATES["claude-opus-5-5"] == {"input_per_1m": 4.00, "output_per_1m": 20.00}


def test_cost_rates_haiku55_cheaper_than_gpt41_mini():
    """The D674 point: Haiku 5.5 must be cheaper than today's gpt-4.1-mini."""
    import cost_rates as cr
    h = cr.LLM_RATES["claude-haiku-5-5"]
    m = cr.LLM_RATES["gpt-4.1-mini"]
    assert h["input_per_1m"] < m["input_per_1m"]
    assert h["output_per_1m"] < m["output_per_1m"]


def test_cost_rates_current_llm_cost_usage_to_cost():
    import cost_rates as cr
    # Haiku 5.5: 1000*0.10/1e6 + 500*0.50/1e6 = 0.0001 + 0.00025 = 0.00035
    assert cr.llm_cost(input_tokens=1000, output_tokens=500,
                       model="claude-haiku-5-5") == pytest.approx(0.00035)
    # Sonnet 5.5: 1000*2/1e6 + 500*10/1e6 = 0.007
    assert cr.llm_cost(input_tokens=1000, output_tokens=500,
                       model="claude-sonnet-5-5") == pytest.approx(0.007)
    # Opus 5.5: 1000*4/1e6 + 500*20/1e6 = 0.014
    assert cr.llm_cost(input_tokens=1000, output_tokens=500,
                       model="claude-opus-5-5") == pytest.approx(0.014)


def test_cost_rates_substring_does_not_collide_sonnet():
    """'claude-sonnet-5-5' must resolve to the 5.5 rate, not the older
    'claude-sonnet-5' (Sonnet 5), and vice-versa — longest substring wins."""
    import cost_rates as cr
    assert cr._resolve_model_rates("claude-sonnet-5-5") == cr.LLM_RATES["claude-sonnet-5-5"]
    # the old arm-G id (no trailing -5) still prices at Sonnet 5, unchanged
    assert cr._resolve_model_rates("claude-sonnet-5") == cr.LLM_RATES["claude-sonnet-5"]
    # and Haiku: 5.5 wins over the 4.5 family for the 5-5 id
    assert cr._resolve_model_rates("claude-haiku-5-5") == cr.LLM_RATES["claude-haiku-5-5"]


def test_cost_rates_local712_rows_unchanged():
    """Adding the current lineup must not perturb the LOCAL-712 rows."""
    import cost_rates as cr
    assert cr.LLM_RATES["claude-haiku-4-5"] == {"input_per_1m": 1.00, "output_per_1m": 5.00}
    assert cr.LLM_RATES["claude-sonnet-5"] == {"input_per_1m": 2.00, "output_per_1m": 10.00}
    assert cr._resolve_model_rates("claude-haiku-4-5-20251001") == \
        cr.LLM_RATES["claude-haiku-4-5"]


# ─────────────────────────────────────────────────────────────────────────────
# 2) the network meter: current Claude cost + a metered row
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def meter(monkeypatch, tmp_path):
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)
    m._LOG_PATH_FOR_TEST = str(log)
    return m


def _read_log(m):
    path = m._LOG_PATH_FOR_TEST
    if not os.path.exists(path):
        return []
    return [json.loads(ln) for ln in open(path) if ln.strip()]


def test_meter_current_claude_cost_reads_usage():
    import paid_api_meter as m
    # Haiku 5.5: 1000 in + 500 out = 0.00035
    usd, key = m._anthropic_cost("claude-haiku-5-5",
                                 {"input_tokens": 1000, "output_tokens": 500})
    assert key == "claude-haiku-5-5"
    assert usd == pytest.approx(0.00035)
    # cache_read billed at Haiku 5.5's $0.01/MTok cache rate
    usd2, _ = m._anthropic_cost(
        "claude-haiku-5-5",
        {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 2000})
    # 0.00035 + 2000*0.01/1e6 = 0.00035 + 0.00002 = 0.00037
    assert usd2 == pytest.approx(0.00037)
    # Opus 5.5
    usd3, key3 = m._anthropic_cost("claude-opus-5-5",
                                   {"input_tokens": 1000, "output_tokens": 500})
    assert key3 == "claude-opus-5-5"
    assert usd3 == pytest.approx(0.014)


def test_meter_sonnet_key_does_not_collide():
    """The meter's longest-key-wins must pick claude-sonnet-5-5 for the 5.5 id and
    claude-sonnet-5 for the older id."""
    import paid_api_meter as m
    _, key55 = m._anthropic_cost("claude-sonnet-5-5", {"input_tokens": 1})
    assert key55 == "claude-sonnet-5-5"
    _, key5 = m._anthropic_cost("claude-sonnet-5", {"input_tokens": 1})
    assert key5 == "claude-sonnet-5"


def test_meter_records_current_claude_row(meter):
    body = json.dumps({
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "A fine stop."}],
        "usage": {"input_tokens": 1000, "output_tokens": 500},
    }).encode()
    meter._record("https://api.anthropic.com/v1/messages", 200, body,
                  {"model": "claude-opus-5-5"})
    recs = _read_log(meter)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "anthropic"
    assert r["status"] == 200
    assert r["model"] == "claude-opus-5-5"
    assert r["usd"] == pytest.approx(0.014)  # 1000*4/1e6 + 500*20/1e6


# ─────────────────────────────────────────────────────────────────────────────
# 3) the harness: the new arms route through call_anthropic unchanged
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def harness(monkeypatch):
    gtt = types.ModuleType("generate_tour_text")
    gtt.build_museum_stop_prompt = lambda *a, **k: "PROMPT"
    gtt.narration_model_route = lambda: ("openai", "gpt-4.1")
    monkeypatch.setitem(sys.modules, "generate_tour_text", gtt)
    mb = types.ModuleType("meter_bootstrap")
    mb.install_meter = lambda: True
    monkeypatch.setitem(sys.modules, "meter_bootstrap", mb)
    for name in ("replay_harness",):
        sys.modules.pop(name, None)
    import importlib
    rh = importlib.import_module("replay_harness")
    importlib.reload(rh)
    return rh


def test_harness_has_current_claude_arms(harness):
    assert harness.ARMS["H"] == ("anthropic", "claude-haiku-5-5")
    assert harness.ARMS["I"] == ("anthropic", "claude-sonnet-5-5")
    assert harness.ARMS["J"] == ("anthropic", "claude-opus-5-5")


def test_harness_keeps_local712_arms(harness):
    """The original LOCAL-712 arms must remain exactly as they were."""
    assert harness.ARMS["F"] == ("anthropic", "claude-haiku-4-5-20251001")
    assert harness.ARMS["G"] == ("anthropic", "claude-sonnet-5")
    # the gpt-4.1-mini baseline (B) and gpt-4.1 (A) are still there
    assert harness.ARMS["B"] == ("openai", "gpt-4.1-mini")
    assert harness.ARMS["A"] == ("openai", "gpt-4.1")


def test_harness_d674_arm_set_extended(harness):
    """D674_ARMS now spans baseline + both the LOCAL-712 and current Claude arms."""
    assert harness.D674_ARMS == ("B", "F", "G", "H", "I", "J")


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_call_anthropic_current_arm_request_shape(harness, monkeypatch):
    """A current-lineup arm (Opus 5.5) sends the identical request shape as the
    LOCAL-712 arms: system TOP-LEVEL, the model id, max_tokens=2500 (LOCAL-720B
    shared budget). The 5.5 lineup deprecates `temperature`, so it is omitted."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _FakeResp(200, {
            "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": "The painting glows."}],
            "usage": {"input_tokens": 800, "output_tokens": 300},
            "stop_reason": "end_turn",
        })

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-TESTKEY")
    monkeypatch.setattr(harness.requests, "post", fake_post)

    text, usage, status, finish = harness.call_anthropic(
        "claude-opus-5-5", "SYS MESSAGE", "USER PROMPT")

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-TESTKEY"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    body = captured["body"]
    assert body["system"] == "SYS MESSAGE"
    assert body["messages"] == [{"role": "user", "content": "USER PROMPT"}]
    assert body["model"] == "claude-opus-5-5"
    # [LOCAL-720B] shared budget 2500 for every arm (was 1000 in LOCAL-720)
    assert body["max_tokens"] == 2500
    # [LOCAL-720] the 5.5 lineup deprecates `temperature`; it is omitted for Opus
    assert "temperature" not in body
    assert status == 200
    assert text == "The painting glows."
    assert usage["prompt_tokens"] == 800
    assert usage["completion_tokens"] == 300
    assert finish == "end_turn"


def test_call_anthropic_requires_key_env(harness, monkeypatch):
    """The key gate is unchanged: no ANTHROPIC_API_KEY -> KeyError, never a call
    made with an empty key (the harness reads os.environ['ANTHROPIC_API_KEY'])."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake_post(*a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("no HTTP call may be made without a key")

    monkeypatch.setattr(harness.requests, "post", fake_post)
    with pytest.raises(KeyError):
        harness.call_anthropic("claude-haiku-5-5", "SYS", "USER")


# ─────────────────────────────────────────────────────────────────────────────
# 4) scorer/report arm tables include the new arms
# ─────────────────────────────────────────────────────────────────────────────
def test_score_stops_arms_include_current_claude():
    import score_stops as s
    for arm in ("H", "I", "J"):
        assert arm in s.ARMS
    # the original arms are still present
    for arm in ("A", "B", "C", "D", "E", "F", "G"):
        assert arm in s.ARMS


def test_report_arm_labels_include_current_claude():
    rp = _load_root_report()
    assert rp.ARM_LABEL["H"] == ("claude-haiku-5-5", "Claude Haiku 5.5")
    assert rp.ARM_LABEL["I"] == ("claude-sonnet-5-5", "Claude Sonnet 5.5")
    assert rp.ARM_LABEL["J"] == ("claude-opus-5-5", "Claude Opus 5.5")


def test_report_model_match_no_sonnet_collision():
    """The ledger matcher must not let arm G (claude-sonnet-5) absorb arm I's
    (claude-sonnet-5-5) ledger rows, nor vice-versa."""
    rp = _load_root_report()
    # arm G key is 'claude-sonnet-5'; it must NOT match the 5-5 ledger model
    assert rp._model_matches("claude-sonnet-5", "claude-sonnet-5-5") is False
    # arm I key is 'claude-sonnet-5-5'; it matches its own ledger model exactly
    assert rp._model_matches("claude-sonnet-5-5", "claude-sonnet-5-5") is True
    # arm G still matches its own id exactly
    assert rp._model_matches("claude-sonnet-5", "claude-sonnet-5") is True
