"""
Test suite for LOCAL-712 (D674): Claude (Anthropic) as a narration/story-pass
provider + bake-off arms.

Every test uses a STUBBED HTTP layer — no real Anthropic/OpenAI call and no
network of any kind. The DB write in the meter is monkeypatched to a no-op and
the log goes to a tmp file, so nothing touches the real paid_api_calls ledger.

What it proves (the five things the ticket asks for):
  * request shape      — call_anthropic sends the system message in the TOP-LEVEL
                         `system` field, the right model, max_tokens and
                         temperature, and the required Anthropic headers.
  * usage -> cost      — cost_rates.llm_cost and the network meter both price
                         Claude usage from the OFFICIAL rates, cache-read included.
  * meter row written  — a 200 Anthropic response writes exactly one paid_api_calls
                         row with kind='anthropic', the model, usage and $.
  * error/timeout      — an HTTP error and a timeout fall back the SAME way the
                         OpenAI path does (an "[HTTP n]" text / a raised timeout),
                         never a crash, and a non-200 row is metered at $0.
  * unset provider     — narration_model_route() with nothing set is byte-for-byte
                         today's OpenAI default; 'anthropic' opts in explicitly.
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


# ─────────────────────────────────────────────────────────────────────────────
# 1) cost_rates: the official Claude rates, and llm_cost usage -> cost
# ─────────────────────────────────────────────────────────────────────────────
def test_cost_rates_has_official_claude_rates():
    import cost_rates as cr
    # Claude Haiku 4.5: $1 in / $5 out ; Claude Sonnet 5: $2 in / $10 out
    assert cr.LLM_RATES["claude-haiku-4-5"] == {"input_per_1m": 1.00, "output_per_1m": 5.00}
    assert cr.LLM_RATES["claude-sonnet-5"] == {"input_per_1m": 2.00, "output_per_1m": 10.00}


def test_cost_rates_resolves_dated_id_by_substring():
    import cost_rates as cr
    # the harness arm id is the dated id; it must price at the Haiku 4.5 family rate
    assert cr._resolve_model_rates("claude-haiku-4-5-20251001") == \
        cr.LLM_RATES["claude-haiku-4-5"]
    assert cr._resolve_model_rates("claude-sonnet-5") == cr.LLM_RATES["claude-sonnet-5"]


def test_cost_rates_llm_cost_usage_to_cost():
    import cost_rates as cr
    # 1000 input + 500 output on Haiku 4.5 = 1000*1/1e6 + 500*5/1e6 = 0.0035
    assert cr.llm_cost(input_tokens=1000, output_tokens=500,
                       model="claude-haiku-4-5-20251001") == pytest.approx(0.0035)
    # Sonnet 5: 1000*2/1e6 + 500*10/1e6 = 0.007
    assert cr.llm_cost(input_tokens=1000, output_tokens=500,
                       model="claude-sonnet-5") == pytest.approx(0.007)


def test_cost_rates_openai_unchanged():
    """Adding Claude must not perturb the existing gpt-4.1 rate."""
    import cost_rates as cr
    assert cr.LLM_RATES["gpt-4.1"] == {"input_per_1m": 2.00, "output_per_1m": 8.00}
    assert cr._resolve_model_rates("gpt-4.1-2025-04-14") == cr.LLM_RATES["gpt-4.1"]


# ─────────────────────────────────────────────────────────────────────────────
# 2) the network meter: host kind, anthropic cost, and a metered row
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def meter(monkeypatch, tmp_path):
    """The meter writing to a tmp log, DB write + daily-limit check stubbed out."""
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


def test_meter_host_kind_anthropic():
    import paid_api_meter as m
    assert m._host_kind("https://api.anthropic.com/v1/messages") == "anthropic"
    # existing hosts unchanged
    assert m._host_kind("https://api.openai.com/v1/chat/completions") == "openai"
    assert m._host_kind("https://example.com/health") is None


def test_meter_anthropic_cost_reads_usage():
    import paid_api_meter as m
    # Haiku 4.5: 1000 in + 500 out = 0.0035
    usd, key = m._anthropic_cost("claude-haiku-4-5-20251001",
                                 {"input_tokens": 1000, "output_tokens": 500})
    assert key == "claude-haiku-4-5"
    assert usd == pytest.approx(0.0035)
    # cache_read_input_tokens billed at the 0.1x cache rate (Haiku 4.5 = $0.10/MTok)
    usd2, _ = m._anthropic_cost(
        "claude-haiku-4-5",
        {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 2000})
    # 0.0035 + 2000*0.10/1e6 = 0.0035 + 0.0002 = 0.0037
    assert usd2 == pytest.approx(0.0037)
    # unknown model -> (None, None), never a crash
    assert m._anthropic_cost("gpt-4o", {"input_tokens": 10}) == (None, None)


def test_meter_records_anthropic_row(meter):
    """A 200 Anthropic response writes exactly one row with kind/model/usage/$."""
    body = json.dumps({
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": "A fine stop."}],
        "usage": {"input_tokens": 1000, "output_tokens": 500},
    }).encode()
    meter._record("https://api.anthropic.com/v1/messages", 200, body,
                  {"model": "claude-sonnet-5"})
    recs = _read_log(meter)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "anthropic"
    assert r["status"] == 200
    assert r["model"] == "claude-sonnet-5"
    assert r["usage"] == {"input_tokens": 1000, "output_tokens": 500}
    assert r["usd"] == pytest.approx(0.007)  # 1000*2/1e6 + 500*10/1e6


def test_meter_anthropic_error_row_costs_zero(meter):
    """A non-200 is still metered (attributable) but at $0, like the OpenAI path."""
    body = json.dumps({"type": "error", "error": {"message": "overloaded"}}).encode()
    meter._record("https://api.anthropic.com/v1/messages", 529, body,
                  {"model": "claude-haiku-4-5-20251001"})
    recs = _read_log(meter)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "anthropic"
    assert r["status"] == 529
    assert r["usd"] == 0.0
    # model falls back to the request body so the row stays attributable
    assert r["model"] == "claude-haiku-4-5-20251001"


# ─────────────────────────────────────────────────────────────────────────────
# 3) the harness call_anthropic: request shape + usage normalisation + fallback
#    (generate_tour_text is heavy; stub it + cheap_arm so importing the harness
#     costs nothing and makes no DB/network call.)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def harness(monkeypatch):
    """Import replay_harness with its heavy production import stubbed out, and a
    stubbed meter bootstrap so no DB/network is touched at import."""
    # stub generate_tour_text (the harness only needs two helpers from it)
    gtt = types.ModuleType("generate_tour_text")
    gtt.build_museum_stop_prompt = lambda *a, **k: "PROMPT"
    gtt.narration_model_route = lambda: ("openai", "gpt-4.1")
    monkeypatch.setitem(sys.modules, "generate_tour_text", gtt)
    # stub the meter bootstrap so import does not try to patch real HTTP clients
    mb = types.ModuleType("meter_bootstrap")
    mb.install_meter = lambda: True
    monkeypatch.setitem(sys.modules, "meter_bootstrap", mb)
    # fresh import of the harness under the stubs
    for name in ("replay_harness",):
        sys.modules.pop(name, None)
    import importlib
    rh = importlib.import_module("replay_harness")
    importlib.reload(rh)
    return rh


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_call_anthropic_request_shape(harness, monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        captured["timeout"] = timeout
        return _FakeResp(200, {
            "model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": "The painting glows."}],
            "usage": {"input_tokens": 800, "output_tokens": 300},
        })

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-TESTKEY")
    monkeypatch.setattr(harness.requests, "post", fake_post)

    text, usage, status = harness.call_anthropic(
        "claude-haiku-4-5-20251001", "SYS MESSAGE", "USER PROMPT")

    # endpoint + required headers
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-TESTKEY"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    # system message goes TOP-LEVEL, not as a message
    body = captured["body"]
    assert body["system"] == "SYS MESSAGE"
    assert body["messages"] == [{"role": "user", "content": "USER PROMPT"}]
    # model, max_tokens (REQUIRED by Anthropic) and temperature mirror the OpenAI arm
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert body["max_tokens"] == 1000
    assert body["temperature"] == 0.7
    # response parsed; usage normalised to the OpenAI-shaped keys the report reads
    assert status == 200
    assert text == "The painting glows."
    assert usage["prompt_tokens"] == 800
    assert usage["completion_tokens"] == 300
    assert usage["total_tokens"] == 1100


def test_call_anthropic_http_error_fallback(harness, monkeypatch):
    """An HTTP error returns an '[HTTP n] ...' text and the error status, exactly
    like call_openai — the harness records the draft and moves on, no crash."""
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResp(400, {"type": "error",
                               "error": {"message": "max_tokens required"}})

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-TESTKEY")
    monkeypatch.setattr(harness.requests, "post", fake_post)
    text, usage, status = harness.call_anthropic("claude-sonnet-5", "SYS", "USER")
    assert status == 400
    assert text.startswith("[HTTP 400]")
    assert usage == {}  # no usage attributed on an error


def test_call_anthropic_timeout_propagates_like_openai(harness, monkeypatch):
    """A timeout raises (same as the OpenAI path, which does not catch it); the
    harness' per-call try/except around the draft handles it the identical way."""
    import requests as _requests

    def fake_post(url, headers=None, json=None, timeout=None):
        raise _requests.exceptions.Timeout("timed out")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-TESTKEY")
    monkeypatch.setattr(harness.requests, "post", fake_post)
    with pytest.raises(_requests.exceptions.Timeout):
        harness.call_anthropic("claude-sonnet-5", "SYS", "USER")


def test_harness_has_claude_arms(harness):
    assert harness.ARMS["F"] == ("anthropic", "claude-haiku-4-5-20251001")
    assert harness.ARMS["G"] == ("anthropic", "claude-sonnet-5")
    assert harness.D674_ARMS == ("B", "F", "G")


# ─────────────────────────────────────────────────────────────────────────────
# 4) narration_model_route: unset == today's default; 'anthropic' opts in
#    (generate_tour_text imports cleanly, so exercise the real function.)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def clean_narration_env(monkeypatch):
    for k in ("NARRATION_PROVIDER", "NARRATION_MODEL", "CHEAP_ARM_CATEGORIES"):
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch


def test_route_unset_is_todays_openai_default(clean_narration_env):
    import generate_tour_text as g
    provider, model = g.narration_model_route()
    assert provider == "openai"
    # the default must equal story_pass_model() byte-for-byte
    assert model == g.story_pass_model()


def test_route_anthropic_branch(clean_narration_env):
    import generate_tour_text as g
    clean_narration_env.setenv("NARRATION_PROVIDER", "anthropic")
    # default Claude model when NARRATION_MODEL is unset = the Haiku 4.5 arm id
    assert g.narration_model_route() == ("anthropic", "claude-haiku-4-5-20251001")
    clean_narration_env.setenv("NARRATION_MODEL", "claude-sonnet-5")
    assert g.narration_model_route() == ("anthropic", "claude-sonnet-5")


def test_route_gemini_branch_unchanged(clean_narration_env):
    import generate_tour_text as g
    clean_narration_env.setenv("NARRATION_PROVIDER", "gemini")
    assert g.narration_model_route() == ("gemini", "gemini-2.5-flash")


# ─────────────────────────────────────────────────────────────────────────────
# 5) blind relabelling scrubs the model name and keeps a separate key file
# ─────────────────────────────────────────────────────────────────────────────
def test_make_blind_scrubs_model_and_writes_key(tmp_path):
    import score_stops as s
    base = tmp_path
    # two tiny arms with the model name embedded in the stop file + results json
    for arm, model in (("B", "gpt-4.1-mini"), ("F", "claude-haiku-4-5-20251001")):
        d = base / arm
        d.mkdir()
        recs = [{"arm": arm, "provider": "x", "model": model,
                 "stop_id": f"{arm}-0", "museum": "Courtauld", "title": "A Bar",
                 "status": 200, "seconds": 1.0, "usage": {"completion_tokens": 10},
                 "output": f"ARM {arm} | prov:{model} | Courtauld | A Bar\n"
                           f"prompt_chars=1 status=200 seconds=1 usage={{}}\n"
                           + "=" * 80 + "\nThe work itself."}]
        (d / f"arm_{arm}_results.json").write_text(json.dumps(recs))
        (d / f"{arm}-0.txt").write_text(recs[0]["output"])

    key = s.make_blind(str(base), arms=["B", "F"], seed=7)
    # key maps blind labels -> real arms and is deterministic under the seed
    assert set(key.values()) == {"B", "F"}
    assert (base / "_blind" / "blind_key.json").exists()

    # every blinded results file has the model scrubbed to 'blind'
    for label in key:
        blinded = json.loads(
            (base / "_blind" / label / f"arm_{label}_results.json").read_text())
        assert all(r["model"] == "blind" for r in blinded)
        # the per-stop text no longer leaks the real model name in its header
        txt = (base / "_blind" / label / "B-0.txt")
        txt = txt if txt.exists() else (base / "_blind" / label / "F-0.txt")
        head = txt.read_text().splitlines()[0]
        assert "gpt-4.1-mini" not in head and "claude-haiku-4-5" not in head
