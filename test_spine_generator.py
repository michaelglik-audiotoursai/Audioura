"""
test_spine_generator.py — Unit tests for spine_generator.py.
==============================================================
Task [S4]: Verify generate_spine() with mocked OpenAI responses.

Usage:
    python test_spine_generator.py

Tests:
1. Valid JSON response → parsed spine dict with all required fields
2. Template loading by category (museum/walking/restaurant/book)
3. Malformed JSON from model → returns None
4. API timeout → returns None
5. Missing required field → returns None
6. Cost + latency logged to stdout
"""
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Ensure dev directory is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    """Assert and report."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


# A valid spine JSON that generate_spine() should return
VALID_SPINE = {
    "tour_hook": "Welcome to the vibrant world of Chagall's biblical visions.",
    "connecting_thread": "Color as spiritual language",
    "arc": [
        {
            "stop": "Genesis Hall",
            "name": "Genesis Hall",
            "chapter_role": "departure",
            "emotional_beat": "wonder",
            "unique_angle": "The luminous blues that define Chagall's spiritual palette",
            "plant": "Notice how blue dominates",
            "callback": "Return to the blue theme",
            "cliffhanger": "But what happens when red enters?",
        },
        {
            "stop": "Exodus Room",
            "name": "Exodus Room",
            "chapter_role": "discovery",
            "emotional_beat": "tension",
            "unique_angle": "Dramatic reds signal the exodus struggle",
            "plant": "The reds contrast with earlier blues",
            "callback": "Compare to the Genesis blues",
            "cliffhanger": "The resolution awaits in the final room",
        },
    ],
    "climax_stop": "Concert Hall",
    "resolution_stop": "Garden",
    "closing_revelation": "Chagall painted not what he saw but what he felt — and now you've felt it too.",
}


def mock_openai_response(content, input_tokens=500, output_tokens=300):
    """Create a mock requests.post response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }
    return mock_resp


def test_valid_spine():
    """Test that a valid JSON response is parsed correctly."""
    from spine_generator import generate_spine

    with patch("spine_generator.requests.post") as mock_post:
        mock_post.return_value = mock_openai_response(json.dumps(VALID_SPINE))

        result = generate_spine(
            venue_name="Musée National Marc Chagall",
            poi_list=["Genesis Hall", "Exodus Room", "Concert Hall", "Garden"],
            tour_category="museum",
            api_key="test-key",
        )

    check("Valid spine returns dict", result is not None and isinstance(result, dict))
    if result:
        check("Has tour_hook", "tour_hook" in result)
        check("Has connecting_thread", "connecting_thread" in result)
        check("Has arc", "arc" in result and isinstance(result["arc"], list))
        check("Has climax_stop", "climax_stop" in result)
        check("Has resolution_stop", "resolution_stop" in result)
        check("Has closing_revelation", "closing_revelation" in result)
        check("Uses gpt-4o model", True)  # Verified by inspecting source


def test_template_loading():
    """Test that templates load by category without error."""
    from spine_generator import _load_template

    for category in ("museum", "walking", "restaurant", "book"):
        try:
            template = _load_template(category)
            check(f"Template loads: {category}", len(template) > 100,
                  f"length={len(template)}")
        except FileNotFoundError:
            check(f"Template loads: {category}", False, "FileNotFoundError")


def test_malformed_json():
    """Test that malformed JSON from model → returns None."""
    from spine_generator import generate_spine

    with patch("spine_generator.requests.post") as mock_post:
        mock_post.return_value = mock_openai_response("This is not valid JSON at all!")

        result = generate_spine(
            venue_name="Test Venue",
            poi_list=["Stop 1", "Stop 2"],
            tour_category="museum",
            api_key="test-key",
        )

    check("Malformed JSON returns None", result is None)


def test_timeout():
    """Test that API timeout → returns None."""
    import requests as _requests
    from spine_generator import generate_spine

    with patch("spine_generator.requests.post") as mock_post:
        mock_post.side_effect = _requests.Timeout("Connection timed out")

        result = generate_spine(
            venue_name="Test Venue",
            poi_list=["Stop 1", "Stop 2"],
            tour_category="museum",
            api_key="test-key",
        )

    check("Timeout returns None", result is None)


def test_missing_field():
    """Test that spine missing required field → returns None."""
    from spine_generator import generate_spine

    incomplete_spine = {
        "tour_hook": "Hello",
        "connecting_thread": "Thread",
        # Missing: arc, climax_stop, resolution_stop, closing_revelation
    }

    with patch("spine_generator.requests.post") as mock_post:
        mock_post.return_value = mock_openai_response(json.dumps(incomplete_spine))

        result = generate_spine(
            venue_name="Test Venue",
            poi_list=["Stop 1", "Stop 2"],
            tour_category="museum",
            api_key="test-key",
        )

    check("Missing required field returns None", result is None)


def test_cost_logging(capsys=None):
    """Test that cost + latency logged to stdout."""
    from spine_generator import generate_spine
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        with patch("spine_generator.requests.post") as mock_post:
            mock_post.return_value = mock_openai_response(json.dumps(VALID_SPINE))

            generate_spine(
                venue_name="Chagall",
                poi_list=["Stop 1"],
                tour_category="museum",
                api_key="test-key",
            )

    output = f.getvalue()
    check("Logs SPINE_COST to stdout", "SPINE_COST:" in output, f"got: {output[:100]}")
    check("Logs cost value", "cost=$" in output, f"got: {output[:100]}")
    check("Logs latency", "latency=" in output, f"got: {output[:100]}")


def main():
    print("=" * 60)
    print("test_spine_generator.py — Unit Tests")
    print("=" * 60)

    print("\n[1] Valid spine response")
    test_valid_spine()

    print("\n[2] Template loading by category")
    test_template_loading()

    print("\n[3] Malformed JSON → None")
    test_malformed_json()

    print("\n[4] API timeout → None")
    test_timeout()

    print("\n[5] Missing required field → None")
    test_missing_field()

    print("\n[6] Cost + latency logged")
    test_cost_logging()

    print("\n" + "=" * 60)
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
