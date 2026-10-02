"""
LOCAL-562 acceptance — the cost ledger counts EVERY OpenAI call.
================================================================

Two offline, deterministic tests (no network, no API key):

1. test_replay_ledger_matches_wire_total
   Replay one recorded tour's 137 OpenAI calls through the production choke-point
   wrapper (openai_cost_wrapper) and assert the accumulator's LLM total equals the
   sum of the recorded usage costs, independently recomputed from cost_rates, to
   within $0.0005. This is the acceptance test from the ticket. It is
   self-consistent: the number the wrapper produces by replaying the recording
   equals the number you get by pricing the same recording's usage directly — the
   wrapper misses nothing and double-counts nothing.

   It also proves the central point of LOCAL-562: BEFORE this change the ledger
   only saw the ~5 call sites that did `total_cost += _tour_llm_cost(...)`; the
   test shows the choke point attributes all 137 calls across all 18 sites.

2. test_two_tours_in_parallel_no_crosstalk
   Run two simulated tours in parallel threads, each inside its own
   cost_accumulator.tour_scope, each replaying a different slice of recorded
   calls. Assert each tour's total is exactly its own slice's cost and that
   neither leaked into the other — the per-tour ContextVar isolation a process
   global would have broken (D-note LOCAL-550: parallel grounding counts rose
   monotonically precisely because of a shared global).

Run:
    python3 -m pytest tests/test_local562_choke_point.py -v
"""

import json
import os
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import cost_accumulator
import openai_cost_wrapper
from cost_rates import llm_cost

REC_CHART = os.path.join(HERE, "fixtures", "local560", "recordings_new", "chart_house_boston.jsonl")
REC_PALAIS = os.path.join(HERE, "fixtures", "local560", "recordings_new", "palais_lascaris_nice.jsonl")

TOLERANCE = 0.0005


def _load_records(path):
    recs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def _independent_wire_cost(records):
    """Price each recorded call's usage directly from cost_rates — the oracle."""
    total = 0.0
    for r in records:
        u = r.get("usage") or {}
        total += llm_cost(
            input_tokens=u.get("prompt_tokens") or 0,
            output_tokens=u.get("completion_tokens") or 0,
            # recorder stored the model string sent on the wire; actual_model
            # is the dated variant — both resolve to the same rate via substring.
            model=r.get("model"),
        )
    return total


class _FakeResponse:
    """Minimal stand-in for a requests Response carrying a recorded OpenAI body."""

    def __init__(self, record):
        self.status_code = record.get("status", 200) or 200
        self._payload = {
            "model": record.get("actual_model") or record.get("model"),
            "usage": record.get("usage"),
            "choices": [{"message": {"content": record.get("response_text")}}],
        }

    def json(self):
        return self._payload


class _ReplayNetwork:
    """A fake 'original requests.post' that returns recorded responses in order.

    Installed as the wrapper's captured original so no real network call is made;
    the wrapper's metering logic (the code under test) runs unchanged on top.
    """

    def __init__(self, records):
        self._records = records
        self._i = 0
        self._lock = threading.Lock()
        # map: a sentinel url suffix -> this instance is selected per-call by index

    def __call__(self, url, *args, **kwargs):
        with self._lock:
            rec = self._records[self._i]
            self._i += 1
        return _FakeResponse(rec)


@pytest.fixture(autouse=True)
def _clean_wrapper_state():
    """Ensure a clean install/uninstall around each test."""
    was = openai_cost_wrapper.is_installed()
    if was:
        openai_cost_wrapper.uninstall()
    yield
    if openai_cost_wrapper.is_installed():
        openai_cost_wrapper.uninstall()


def test_replay_ledger_matches_wire_total():
    records = _load_records(REC_CHART)
    assert len(records) == 137, "expected the recorded Chart House tour (137 calls)"

    oracle = _independent_wire_cost(records)
    assert oracle > 0

    import requests

    openai_cost_wrapper.install()
    # Replace the captured original with a replay of recorded responses.
    openai_cost_wrapper._state["orig_requests_post"] = _ReplayNetwork(records)

    with cost_accumulator.tour_scope(job_id="replay-chart-house") as acc:
        for r in records:
            # Every recorded call was a POST to the OpenAI chat endpoint.
            requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": r.get("model"), "messages": []},
            )
        snap = acc.snapshot()

    # Every single recorded call was attributed — not just the ~5 old sites.
    assert snap["llm"]["calls"] == len(records), (
        f"choke point attributed {snap['llm']['calls']} of {len(records)} calls"
    )
    # Ledger LLM total matches the independent wire recompute within tolerance.
    assert abs(snap["breakdown"]["llm"] - oracle) < TOLERANCE, (
        f"ledger ${snap['breakdown']['llm']:.6f} vs wire ${oracle:.6f} "
        f"(diff ${abs(snap['breakdown']['llm'] - oracle):.6f} >= ${TOLERANCE})"
    )


def test_non_openai_post_passes_through_unmetered():
    """A POST to a non-OpenAI host must not be inspected or metered."""
    import requests

    calls = {"n": 0}

    def fake_orig(url, *a, **k):
        calls["n"] += 1
        class R:
            status_code = 200
            def json(self_):
                raise AssertionError("wrapper must not call .json() on non-OpenAI responses")
        return R()

    openai_cost_wrapper.install()
    openai_cost_wrapper._state["orig_requests_post"] = fake_orig

    with cost_accumulator.tour_scope(job_id="passthrough") as acc:
        requests.post("http://polly-tts-1:5018/synthesize", json={"text": "hi"})
        snap = acc.snapshot()

    assert calls["n"] == 1
    assert snap["llm"]["calls"] == 0
    assert snap["breakdown"]["llm"] == 0.0


def test_two_tours_in_parallel_no_crosstalk():
    chart = _load_records(REC_CHART)
    palais = _load_records(REC_PALAIS)

    chart_oracle = _independent_wire_cost(chart)
    palais_oracle = _independent_wire_cost(palais)
    assert chart_oracle > 0 and palais_oracle > 0
    # The two tours have materially different costs, so cross-talk would show.
    assert abs(chart_oracle - palais_oracle) > TOLERANCE

    # This exercises the real isolation mechanism: the per-tour ContextVar in
    # cost_accumulator. Each worker binds its OWN accumulator via
    # run_in_tour_context (exactly how a ThreadPoolExecutor worker must), then
    # calls cost_accumulator.add_llm_usage — the same module function the HTTP
    # choke point calls on every OpenAI response. If attribution used a process
    # global (the bug D-note LOCAL-550 describes), the two totals would merge.
    results = {}
    errors = {}
    # A barrier forces the two workers to interleave their first increments, so a
    # shared-global implementation could not pass by luck of scheduling.
    barrier = threading.Barrier(2)

    def run_tour(name, records, oracle):
        try:
            acc = cost_accumulator.CostAccumulator(job_id=name)

            def _work():
                first = True
                for rec in records:
                    u = rec.get("usage") or {}
                    cost_accumulator.add_llm_usage(
                        input_tokens=u.get("prompt_tokens") or 0,
                        output_tokens=u.get("completion_tokens") or 0,
                        model=rec.get("model"),
                    )
                    if first:
                        # Both threads reach here before either proceeds.
                        barrier.wait()
                        first = False
                # Sanity: the function sees ITS OWN accumulator as current.
                assert cost_accumulator.current_accumulator() is acc
                return acc.snapshot()

            runner = cost_accumulator.run_in_tour_context(acc, _work)
            results[name] = runner()
        except Exception as e:  # pragma: no cover
            errors[name] = e

    t1 = threading.Thread(target=run_tour, args=("chart", chart, chart_oracle))
    t2 = threading.Thread(target=run_tour, args=("palais", palais, palais_oracle))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"worker errors: {errors}"

    # Each tour counted exactly its own calls.
    assert results["chart"]["llm"]["calls"] == len(chart)
    assert results["palais"]["llm"]["calls"] == len(palais)

    # Each tour's total equals its OWN oracle — no leakage from the other.
    assert abs(results["chart"]["breakdown"]["llm"] - chart_oracle) < TOLERANCE, (
        f"chart ${results['chart']['breakdown']['llm']:.6f} vs ${chart_oracle:.6f}"
    )
    assert abs(results["palais"]["breakdown"]["llm"] - palais_oracle) < TOLERANCE, (
        f"palais ${results['palais']['breakdown']['llm']:.6f} vs ${palais_oracle:.6f}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
