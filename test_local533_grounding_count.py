#!/usr/bin/env python3
"""test_local533_grounding_count.py — prove the grounding counter equals the
number of grounded requests ACTUALLY ISSUED to the network.

The acceptance criterion for LOCAL-533 is not "we added a counter" — it is that
the counter matches the real number of requests. We prove that by intercepting
`requests.post` itself and counting, INDEPENDENTLY of story_leads, every HTTP
request that carries the `google_search` grounding tool. If the independent
network-level tally equals story_leads.get_grounding_requests(), the counter is
faithful.

No network, no API key needed: the fake post records the call and returns a
minimal valid Gemini response shape.

Run:  python3 test_local533_grounding_count.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# A key must be present or the wrappers short-circuit before issuing a request
# (which is exactly the keyless no-op we do NOT want to count). Set a dummy one;
# the network call is faked below, so the value is never used against Google.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

import story_leads  # noqa: E402
from cost_rates import grounding_cost, GROUNDING_COST_PER_REQUEST  # noqa: E402


# --- Independent, network-level tally of grounded requests -------------------
_ISSUED = {"grounded": 0, "ungrounded": 0, "total": 0}


class _FakeResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        # Minimal shape both _gemini and gemini_with_sources parse without error.
        return {
            "candidates": [
                {
                    "content": {"parts": [{"text": "ok"}]},
                    "groundingMetadata": {},
                }
            ]
        }


def _fake_post(url, headers=None, json=None, timeout=None, **kwargs):
    """Stand-in for requests.post. Counts, at the wire, whether the request that
    is being issued carries the google_search grounding tool."""
    _ISSUED["total"] += 1
    tools = (json or {}).get("tools") or []
    is_grounded = any("google_search" in (t or {}) for t in tools)
    if is_grounded:
        _ISSUED["grounded"] += 1
    else:
        _ISSUED["ungrounded"] += 1
    return _FakeResp()


def _reset():
    _ISSUED["grounded"] = 0
    _ISSUED["ungrounded"] = 0
    _ISSUED["total"] = 0
    story_leads.reset_grounding_requests()


def main():
    import requests
    _orig_post = requests.post
    # Patch in both the requests module and any local `import requests` inside
    # the functions (they call requests.post via the module attribute).
    requests.post = _fake_post
    # gemini_with_sources resolves redirects with requests.head when resolve=True;
    # keep it from touching the network too.
    requests.head = lambda *a, **k: type("H", (), {"url": ""})()

    failures = []
    try:
        # Case 1: N grounded _gemini calls -> counter == N == wire grounded tally
        _reset()
        N = 5
        for _ in range(N):
            story_leads._gemini("q", grounded=True)
        counter = story_leads.get_grounding_requests()
        print(f"[case1] {N} grounded _gemini calls: "
              f"wire_grounded={_ISSUED['grounded']} counter={counter}")
        if not (counter == N == _ISSUED["grounded"]):
            failures.append("case1: counter != wire grounded tally != N")

        # Case 2: ungrounded _gemini calls must NOT be counted
        _reset()
        for _ in range(3):
            story_leads._gemini("q", grounded=False)
        counter = story_leads.get_grounding_requests()
        print(f"[case2] 3 ungrounded _gemini calls: "
              f"wire_ungrounded={_ISSUED['ungrounded']} counter={counter}")
        if not (counter == 0 and _ISSUED["ungrounded"] == 3):
            failures.append("case2: ungrounded calls were counted (should be 0)")

        # Case 3: gemini_with_sources defaults grounded=True -> counted
        _reset()
        for _ in range(4):
            story_leads.gemini_with_sources("q", resolve=False)
        counter = story_leads.get_grounding_requests()
        print(f"[case3] 4 gemini_with_sources calls: "
              f"wire_grounded={_ISSUED['grounded']} counter={counter}")
        if not (counter == 4 == _ISSUED["grounded"]):
            failures.append("case3: counter != wire grounded tally != 4")

        # Case 4: gemini_with_sources(grounded=False) must NOT be counted
        _reset()
        story_leads.gemini_with_sources("q", resolve=False, grounded=False)
        counter = story_leads.get_grounding_requests()
        print(f"[case4] 1 ungrounded gemini_with_sources: "
              f"wire_ungrounded={_ISSUED['ungrounded']} counter={counter}")
        if not (counter == 0 and _ISSUED["ungrounded"] == 1):
            failures.append("case4: ungrounded with_sources was counted")

        # Case 5: mixed run — counter equals ONLY the grounded wire tally
        _reset()
        story_leads._gemini("q", grounded=True)
        story_leads._gemini("q", grounded=False)
        story_leads.gemini_with_sources("q", resolve=False)          # grounded
        story_leads.gemini_with_sources("q", resolve=False, grounded=False)
        story_leads._gemini("q", grounded=True)
        counter = story_leads.get_grounding_requests()
        print(f"[case5] mixed: wire_total={_ISSUED['total']} "
              f"wire_grounded={_ISSUED['grounded']} "
              f"wire_ungrounded={_ISSUED['ungrounded']} counter={counter}")
        if not (counter == _ISSUED["grounded"] == 3):
            failures.append("case5: counter != grounded wire tally (== 3)")
        if _ISSUED["total"] != 5:
            failures.append("case5: expected 5 total requests issued")

        # Case 6: reset zeroes it
        story_leads.reset_grounding_requests()
        if story_leads.get_grounding_requests() != 0:
            failures.append("case6: reset did not zero the counter")

        # Case 7: pricing is a flat per-request multiply at the documented rate
        if abs(grounding_cost(3) - 3 * GROUNDING_COST_PER_REQUEST) > 1e-12:
            failures.append("case7: grounding_cost is not n * rate")
        if abs(grounding_cost(0)) > 1e-12:
            failures.append("case7: grounding_cost(0) != 0")
        print(f"[case7] rate=${GROUNDING_COST_PER_REQUEST}/req  "
              f"grounding_cost(3)=${grounding_cost(3):.4f}  "
              f"grounding_cost(0)=${grounding_cost(0):.4f}")
    finally:
        requests.post = _orig_post

    print("=" * 60)
    if failures:
        for f in failures:
            print("FAIL:", f)
        print("RESULT: FAILED")
        sys.exit(1)
    print("RESULT: PASS — counter equals grounded requests issued at the wire")


if __name__ == "__main__":
    main()
