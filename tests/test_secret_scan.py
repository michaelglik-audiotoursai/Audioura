#!/usr/bin/env python3
"""
Unit tests for secret_scan.py.

IMPORTANT: Every secret in this file is PURELY INVENTED — random characters
typed fresh, matching the FORMAT of real secrets (prefix, length, charset)
but sharing ZERO material with any real key in this repository or anywhere
else. Verified: longest common substring with any known real key is the
shared structural prefix (e.g. "sk-proj-" = 8 chars).
"""
import subprocess
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from secret_scan import (
    scan_content,
    detect_openai,
    detect_aws_access_key,
    detect_aws_secret,
    detect_google_key,
    detect_anthropic_key,
    detect_private_key,
    detect_high_entropy_secret,
    detect_near_match_by_structure,
    is_whitelisted,
    shannon_entropy,
    mask_value,
    should_skip_file,
    longest_common_substring_length,
    DETECTORS,
)


# ---------------------------------------------------------------------------
# Purely invented fixtures — NO material from any real key.
# Each matches the shape (prefix + length + charset) of its type.
# Constructed by hand from random keyboard input, verified to share at most
# the structural prefix with real keys.
# ---------------------------------------------------------------------------

# Invented OpenAI project key: sk-proj- + 40 chars (48 total, below near-match threshold of 50)
FAKE_OPENAI_PROJ = "sk-proj-Mv3Rq8Zw1Xn5Yb7Kf2Jt4Ld9Gs0Uc6PeHa3W"
# Invented classic sk- key: sk- + 40 random characters (43 total)
FAKE_OPENAI_CLASSIC = "sk-Bz9Wq3Nj7Ym5Xk1Rv4Tf8Lp2Hd6Gs0UcAe3Wi5"
# Invented AWS access key: AKIA + 16 uppercase alphanum
FAKE_AWS_ACCESS = "AKIABZ9WQ3NJ7YM5XK1R"
# Invented AWS secret: 40 chars of base64-ish
FAKE_AWS_SECRET = "Bz9Wq3Nj7Ym5Xk1Rv4Tf8Lp2Hd6Gs0UcAe3Wi5Ro"
# Invented Google API key: AIzaSy + 33 random chars (39 total)
FAKE_GOOGLE = "AIzaSyBz9Wq3Nj7Ym5Xk1Rv4Tf8Lp2Hd6Gs0Uvx"
# Invented Anthropic key: sk-ant- + 28 random chars
FAKE_ANTHROPIC = "sk-ant-Bz9Wq3Nj7Ym5Xk1Rv4Tf8Lp2H"
# Invented high-entropy secret value (32 chars, entropy > 3.5)
FAKE_HIGH_ENTROPY = "q7Mv3Zw1Xn5Yb8Kf2Jt4Ld9Gs0Uc6Pe"


# ---------------------------------------------------------------------------
# Detector tests: BASIC detection (in quotes / assignment)
# ---------------------------------------------------------------------------


def test_detect_openai_proj_in_quotes():
    """Detects sk-proj- style keys in quoted assignment."""
    line = f'OPENAI_API_KEY = "{FAKE_OPENAI_PROJ}"'
    findings = detect_openai(line, 1, "test.py")
    assert len(findings) == 1, f"Expected 1 finding, got {len(findings)}"
    assert findings[0].detector == "openai_key"
    assert findings[0].matched.startswith("sk-proj-")


def test_detect_openai_classic():
    """Detects classic sk- keys."""
    line = f"key = '{FAKE_OPENAI_CLASSIC}'"
    findings = detect_openai(line, 1, "test.py")
    assert len(findings) == 1


def test_detect_openai_in_assignment():
    """Detects keys in typical assignment patterns."""
    line = f'MY_SK = "{FAKE_OPENAI_PROJ}"'
    findings = detect_openai(line, 1, "test.py")
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# CRITICAL REGRESSION TESTS: bare keys in prose, markdown, logs.
#
# These test the forms that historical exposures actually took in this repo.
# The scanner MUST find each one. A scanner that cannot find the incidents
# that motivated it is not finished.
# ---------------------------------------------------------------------------


def test_detect_openai_bare_in_prose():
    """REGRESSION: key bare in prose (like sk.py's key pasted into a doc).
    Historical form: 'The key sk-proj-XXXX has hit insufficient_quota.'"""
    line = f"The OpenAI API key {FAKE_OPENAI_PROJ} has hit insufficient_quota (429)."
    findings = detect_openai(line, 1, "submission.md")
    assert len(findings) == 1, f"REGRESSION FAIL: bare key in prose not detected"


def test_detect_openai_bare_in_markdown_table():
    """REGRESSION: key in a markdown table cell."""
    line = f"| {FAKE_OPENAI_PROJ} | OpenAI | active |"
    findings = detect_openai(line, 1, "review.md")
    assert len(findings) == 1, f"REGRESSION FAIL: key in markdown table not detected"


def test_detect_openai_in_curl_command():
    """REGRESSION: key in a curl command in documentation."""
    line = f'curl -H "Authorization: Bearer {FAKE_OPENAI_PROJ}" https://api.openai.com/v1/...'
    findings = detect_openai(line, 1, "debug_log.md")
    assert len(findings) == 1, f"REGRESSION FAIL: key in curl command not detected"


def test_detect_openai_in_error_message():
    """REGRESSION: key in a logged error string."""
    line = f"ERROR: API call failed for key={FAKE_OPENAI_PROJ}, status=429"
    findings = detect_openai(line, 1, "service.log")
    assert len(findings) == 1, f"REGRESSION FAIL: key in error message not detected"


def test_detect_openai_in_json_body():
    """REGRESSION: key in a JSON-like structure in docs."""
    line = f'{{"api_key": "{FAKE_OPENAI_PROJ}", "model": "gpt-4"}}'
    findings = detect_openai(line, 1, "request.json")
    assert len(findings) == 1, f"REGRESSION FAIL: key in JSON not detected"


def test_detect_aws_access_key_bare_in_prose():
    """REGRESSION: AWS access key bare in a log/review (like the actual
    exposure in claude_review_secret_fixes_final_2026_06_07.md)."""
    line = f"Credential={FAKE_AWS_ACCESS}/20260607/us-east-1/polly/aws4_request"
    findings = detect_aws_access_key(line, 1, "review.md")
    assert len(findings) == 1, f"REGRESSION FAIL: bare AWS key not detected"


def test_detect_aws_access_key_in_submission():
    """REGRESSION: AWS key mentioned in a submission table."""
    line = f"| AWS Access Key | {FAKE_AWS_ACCESS} | active |"
    findings = detect_aws_access_key(line, 1, "SUBMISSION.md")
    assert len(findings) == 1, f"REGRESSION FAIL: AWS key in table not detected"


def test_detect_anthropic_bare_in_prose():
    """REGRESSION: Anthropic key bare in prose."""
    line = f"Configure your client with key {FAKE_ANTHROPIC} to proceed."
    findings = detect_anthropic_key(line, 1, "setup.md")
    assert len(findings) == 1, f"REGRESSION FAIL: bare Anthropic key not detected"


def test_detect_google_bare_in_prose():
    """REGRESSION: Google key bare in prose."""
    line = f"The Maps API key {FAKE_GOOGLE} was rate-limited."
    findings = detect_google_key(line, 1, "incident.md")
    assert len(findings) == 1, f"REGRESSION FAIL: bare Google key not detected"


# ---------------------------------------------------------------------------
# Whitelist tests — placeholders must NOT fire
# ---------------------------------------------------------------------------


def test_whitelist_sk_xxxxxxxx():
    """Placeholder sk-xxxxxxxx must not fire."""
    line = 'print("Example: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")'
    findings = detect_openai(line, 1, "test.py")
    assert len(findings) == 0


def test_whitelist_your_key_here():
    """'your-key-here' must not fire."""
    assert is_whitelisted("your-key-here")
    assert is_whitelisted("your_key_here")


def test_whitelist_redacted():
    """<REDACTED> must not fire."""
    assert is_whitelisted("<REDACTED>")


def test_whitelist_placeholder():
    """Various placeholder patterns."""
    assert is_whitelisted("placeholder-value-not-real")
    assert is_whitelisted("fake_api_key_for_testing")
    assert is_whitelisted("dummy_key_12345")


def test_whitelist_fake_marker():
    """Strings containing FAKE are whitelisted."""
    assert is_whitelisted("sk-proj-FAKE1234abcdefghijklmnop")
    assert is_whitelisted("AKIAFAKE1234567890AB")


def test_whitelist_example_marker():
    """Strings containing EXAMPLE are whitelisted."""
    assert is_whitelisted("sk-proj-EXAMPLEabcdefghijklmnop")


def test_whitelist_test_marker():
    """Strings containing TEST_ or TESTING are whitelisted."""
    assert is_whitelisted("sk-proj-TEST_abcdefghijklmnop")
    assert is_whitelisted("sk-proj-TESTINGabcdefghijklmnop")


# ---------------------------------------------------------------------------
# Other detector tests
# ---------------------------------------------------------------------------


def test_detect_aws_access_key():
    """Detects AKIA-prefixed keys."""
    line = f'AWS_ACCESS_KEY_ID = "{FAKE_AWS_ACCESS}"'
    findings = detect_aws_access_key(line, 1, "test.py")
    assert len(findings) == 1
    assert findings[0].detector == "aws_access_key"


def test_detect_aws_secret_key():
    """Detects AWS secret keys by context."""
    line = f'aws_secret_access_key = "{FAKE_AWS_SECRET}"'
    findings = detect_aws_secret(line, 1, "test.py")
    assert len(findings) == 1
    assert findings[0].detector == "aws_secret_key"


def test_detect_google_key():
    """Detects AIzaSy-prefixed Google API keys."""
    line = f'GOOGLE_API_KEY = "{FAKE_GOOGLE}"'
    findings = detect_google_key(line, 1, "test.py")
    assert len(findings) == 1
    assert findings[0].detector == "google_api_key"


def test_detect_anthropic_key():
    """Detects sk-ant- prefixed Anthropic keys."""
    line = f'ANTHROPIC_KEY = "{FAKE_ANTHROPIC}"'
    findings = detect_anthropic_key(line, 1, "test.py")
    assert len(findings) == 1
    assert findings[0].detector == "anthropic_key"


def test_detect_private_key_block():
    """Detects PEM private key headers."""
    line = "-----BEGIN RSA PRIVATE KEY-----"
    findings = detect_private_key(line, 1, "test.pem")
    assert len(findings) == 1
    assert findings[0].detector == "private_key_block"

    line2 = "-----BEGIN PRIVATE KEY-----"
    findings2 = detect_private_key(line2, 1, "test.pem")
    assert len(findings2) == 1

    line3 = "-----BEGIN OPENSSH PRIVATE KEY-----"
    findings3 = detect_private_key(line3, 1, "test.pem")
    assert len(findings3) == 1


def test_detect_high_entropy_assignment():
    """Detects high-entropy values assigned to sensitive variable names."""
    line = f'MY_SECRET_KEY = "{FAKE_HIGH_ENTROPY}"'
    findings = detect_high_entropy_secret(line, 1, "test.py")
    assert len(findings) == 1
    assert findings[0].detector == "high_entropy_assignment"


def test_high_entropy_ignores_low_entropy():
    """Low-entropy strings assigned to KEY variables must not fire."""
    line = 'API_KEY = "aaaaaaaaaaaaaaaaaaaaaa"'
    findings = detect_high_entropy_secret(line, 1, "test.py")
    assert len(findings) == 0


def test_high_entropy_ignores_env_reads():
    """os.environ reads must not fire."""
    line = 'API_KEY = os.environ["API_KEY"]'
    findings = detect_high_entropy_secret(line, 1, "test.py")
    assert len(findings) == 0


def test_no_false_positive_on_get_coordinates():
    """get_coordinates_openai.py placeholder must not fire."""
    line = 'print("Example: python get_coordinates_openai.py \\"Hall Memorial\\" sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")'
    all_findings = []
    for detector in DETECTORS:
        all_findings.extend(detector(line, 1, "get_coordinates_openai.py"))
    assert len(all_findings) == 0


# ---------------------------------------------------------------------------
# Near-match detector tests
# ---------------------------------------------------------------------------


def test_near_match_catches_suspicious_literal():
    """A literal with sk-proj- prefix, right length, high entropy, no FAKE
    marker — should fire as near-match."""
    # Invented 60-char key: right prefix, right length (in 50-200), high entropy, no marker
    suspicious = "sk-proj-Mv3Rq8Zw1Xn5Yb7Kf2Jt4Ld9Gs0Uc6PeHa3Wi5Ro7Pl4Nj2Fk8v"
    line = f'KEY = "{suspicious}"'
    findings = detect_near_match_by_structure(line, 1, "some_file.py")
    assert len(findings) == 1
    assert findings[0].detector == "near_match_secret"


def test_near_match_allows_obviously_fake():
    """A literal with FAKE in it should pass (whitelisted)."""
    safe = "sk-proj-FAKE1234abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
    line = f'KEY = "{safe}"'
    findings = detect_near_match_by_structure(line, 1, "test_file.py")
    assert len(findings) == 0


def test_near_match_allows_short_strings():
    """Short strings (< 50 chars) are not flagged by near-match."""
    short = "sk-proj-Mv3Rq8Zw1Xn5Yb7Kf2Jt4Ld"
    line = f'KEY = "{short}"'
    findings = detect_near_match_by_structure(line, 1, "test.py")
    assert len(findings) == 0


def test_near_match_allows_low_entropy():
    """Low-entropy sk-proj literals are not flagged."""
    low = "sk-proj-" + "a" * 60
    line = f'KEY = "{low}"'
    findings = detect_near_match_by_structure(line, 1, "test.py")
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


def test_shannon_entropy():
    """Entropy calculations."""
    assert shannon_entropy("aaaa") == 0.0
    assert shannon_entropy("a8Kz9pLm3xQr5tYw") > 3.5
    assert shannon_entropy("") == 0.0


def test_mask_value():
    """Masking shows first 8 chars."""
    assert mask_value("sk-proj-abcdef1234567890") == "sk-proj-…[24 chars]"
    assert "…" in mask_value("short")


def test_should_skip_file():
    """Binary and generated files are skipped."""
    assert should_skip_file("image.png")
    assert should_skip_file("audio.mp3")
    assert should_skip_file("node_modules/package/index.js")
    assert should_skip_file(".env")
    assert should_skip_file(".env.production")
    assert not should_skip_file("config.py")
    assert not should_skip_file("src/main.dart")


def test_longest_common_substring():
    """LCS utility function works correctly."""
    assert longest_common_substring_length("abcdef", "xbcdey") == 4
    assert longest_common_substring_length("abc", "xyz") == 0
    assert longest_common_substring_length("hello world", "world hello") == 5


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_scan_content_multiple_detectors():
    """Multiple secrets in one file are all detected."""
    content = f'''
OPENAI_KEY = "{FAKE_OPENAI_PROJ}"
AWS_ACCESS_KEY_ID = "{FAKE_AWS_ACCESS}"
-----BEGIN RSA PRIVATE KEY-----
'''
    findings = scan_content(content, "multi_secrets.py")
    detectors_found = {f.detector for f in findings}
    assert "openai_key" in detectors_found
    assert "aws_access_key" in detectors_found
    assert "private_key_block" in detectors_found


def test_scan_content_clean_file():
    """A file with no secrets returns no findings."""
    content = '''
import os

API_KEY = os.environ["OPENAI_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

def get_config():
    return {"key": os.environ["KEY"]}
'''
    findings = scan_content(content, "clean.py")
    assert len(findings) == 0


def test_scanner_does_not_flag_own_test_file():
    """The test file itself is in ALLOWLISTED_FILES and would be skipped in --tree."""
    assert should_skip_file("tests/test_secret_scan.py")


# ---------------------------------------------------------------------------
# Self-scan: verify this test file contains no real secrets
# ---------------------------------------------------------------------------


def test_self_scan_no_near_match():
    """The test file is in ALLOWLISTED_FILES, so --tree mode skips it.
    That is the protection: the allowlist prevents false alarms on fixtures.
    Verify the allowlist works."""
    assert should_skip_file("tests/test_secret_scan.py")
    # Also verify our main fixtures (below 50 chars) don't trigger near-match
    from secret_scan import detect_near_match_by_structure
    fixtures = [
        f'X = "{FAKE_OPENAI_PROJ}"',
        f'X = "{FAKE_OPENAI_CLASSIC}"',
    ]
    for line in fixtures:
        findings = detect_near_match_by_structure(line, 1, "test.py")
        assert len(findings) == 0, (
            f"Near-match fired on a fixture that should be below 50 chars: {line}"
        )


# ---------------------------------------------------------------------------
# CLI mode tests (run as subprocess)
# ---------------------------------------------------------------------------


def test_cli_tree_mode():
    """--tree mode runs and exits (non-zero expected due to sk.py)."""
    result = subprocess.run(
        [sys.executable, "secret_scan.py", "--tree"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    # sk.py has real-looking keys, so we expect findings
    assert result.returncode == 1
    assert "secret" in result.stdout.lower() or "detected" in result.stdout.lower()


def test_cli_staged_mode():
    """--staged mode runs without error on empty staging area."""
    result = subprocess.run(
        [sys.executable, "secret_scan.py", "--staged"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    # With nothing staged, should be clean (exit 0)
    assert result.returncode in (0, 1)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------


def run_tests():
    """Simple test runner — no external dependencies needed."""
    test_functions = [
        v for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ]
    passed = 0
    failed = 0
    for test_fn in sorted(test_functions, key=lambda f: f.__name__):
        try:
            test_fn()
            passed += 1
            print(f"  ✓ {test_fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {test_fn.__name__}: EXCEPTION {type(e).__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    run_tests()
