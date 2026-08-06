"""
test_local26_placeholder_leak.py — Regression test for LOCAL-26.
=================================================================
Verifies that _detect_placeholder_leak correctly rejects GPT outputs that
are template echoes rather than real content.

Tests both the detection function in isolation and the prompt template shape.
"""
import re
import sys
import os

# Add parent directory to path so we can import from generate_tour_text
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------- Inline copy of the detection function for unit testing ----------
# (avoids importing the full generate_tour_text module which has many dependencies)
# [LOCAL-295] Updated to match the refactored classification logic.

def _classify_placeholder_leak(text):
    """Classify text as placeholder echo, short-but-valid prose, or normal content."""
    if not text or not text.strip():
        return ("placeholder", "empty_text")
    stripped = text.strip()
    if re.search(r'\[.*\bword\b.*\bdescription\b.*\]', stripped, re.IGNORECASE):
        return ("placeholder", "bracketed_word_description_echo")
    if stripped.startswith('[') and stripped.endswith(']') and '\n' not in stripped:
        return ("placeholder", "wholly_bracketed")
    word_count = len(stripped.split())
    if word_count < 30:
        _lower = stripped.lower()
        _is_placeholder_like = (
            re.search(r'\b(insert|placeholder|description here|your .* here|todo|tbd)\b', _lower) or
            stripped.count('...') >= 2 or
            re.search(r'\b(create a|write a|generate a)\s+(detailed|brief)?\s*(description|narration)', _lower) or
            (word_count < 8 and '.' not in stripped)
        )
        if _is_placeholder_like:
            return ("placeholder", f"short_and_template_like ({word_count} words)")
        return ("short_valid", word_count)
    return (None, None)


def _detect_placeholder_leak(text):
    """Return True only for genuine placeholder echoes (not short-but-valid prose)."""
    classification, _ = _classify_placeholder_leak(text)
    return classification == "placeholder"


# ---------- Test cases ----------

def test_rejects_exact_placeholder_echo():
    """The exact failure mode from the scored run: GPT echoes the template."""
    text = "[120-word description of the exhibit]"
    assert _detect_placeholder_leak(text) is True, f"Should reject: {text!r}"


def test_rejects_placeholder_with_word_count_variant():
    """Different word counts should all be caught."""
    for n in (120, 300, 250, 150):
        text = f"[Detailed {n}-word description of the exhibit]"
        assert _detect_placeholder_leak(text) is True, f"Should reject: {text!r}"


def test_rejects_placeholder_embedded_in_otherwise_good_text():
    """If the placeholder leaks as part of a longer response, still detect it."""
    text = (
        "This gallery showcases a remarkable collection of Asian landscapes "
        "that capture the spiritual essence of the continent.\n\n"
        "[120-word description of the exhibit]\n\n"
        "The paintings use traditional techniques."
    )
    assert _detect_placeholder_leak(text) is True


def test_rejects_wholly_bracketed_output():
    """Short single-line bracketed content = placeholder."""
    assert _detect_placeholder_leak("[Description goes here]") is True


def test_rejects_empty_or_whitespace():
    """Empty or whitespace-only text is a leak."""
    assert _detect_placeholder_leak("") is True
    assert _detect_placeholder_leak("   ") is True
    assert _detect_placeholder_leak(None) is True


def test_rejects_too_short():
    """Under 30 words AND template-like is suspicious — reject."""
    # [LOCAL-295] Updated: short text is only rejected if it looks like a placeholder
    # (has template keywords, ellipsis, or no sentence structure).
    # A bare fragment with no period AND < 8 words is a placeholder:
    text = "This painting by an artist"
    assert _detect_placeholder_leak(text) is True
    # But a short sentence with a period is valid prose (short_valid):
    text2 = "This is a painting by an artist."
    assert _detect_placeholder_leak(text2) is False, "Short valid prose should NOT be rejected"


def test_accepts_valid_description():
    """A normal 120-word description should NOT be flagged."""
    # Generate a realistic ~120 word description
    text = (
        "Les paysages de l'âme presents a curated selection of landscape paintings "
        "from across Asia, spanning the Edo period in Japan through the modern Chinese "
        "ink-wash revival. The collection features works by both established masters "
        "and lesser-known regional artists whose contributions shaped the aesthetic "
        "philosophy of landscape as spiritual practice. Central to the display is a "
        "pair of six-panel screens attributed to the Kanō school, depicting the Four "
        "Seasons in gold leaf and mineral pigments. Adjacent panels showcase Song "
        "Dynasty-influenced compositions where vast empty space speaks as eloquently "
        "as brushwork. The curation deliberately juxtaposes formal court paintings with "
        "contemplative hermit-scholar works, revealing how landscape functioned as "
        "both political statement and personal meditation across centuries of Asian art."
    )
    assert _detect_placeholder_leak(text) is False, "Valid description should pass"


def test_accepts_description_with_legitimate_brackets():
    """Brackets used for legitimate purposes (e.g. dates) should not trigger."""
    text = (
        "Created in the late Ming dynasty [1368-1644], this scroll painting "
        "demonstrates the evolution of literati painting through its deliberate "
        "rejection of court aesthetics. The artist employed a dry-brush technique "
        "that emphasizes the texture of rock formations and the sparse foliage of "
        "winter plum trees. Unlike the polychrome works favored by imperial patrons, "
        "this monochrome composition relies entirely on tonal variation within black "
        "ink to convey depth and atmosphere."
    )
    assert _detect_placeholder_leak(text) is False


def test_prompt_template_has_no_copyable_bracket():
    """Verify the live prompt template no longer contains a bracketed placeholder slot."""
    # Read the actual generate_tour_text.py source
    gen_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "generate_tour_text.py")
    with open(gen_path, 'r') as f:
        source = f.read()

    # The old hazardous pattern: [Detailed {_word_target}-word description of the exhibit]
    matches = re.findall(r'\[Detailed.*word description.*\]', source)
    assert len(matches) == 0, (
        f"generate_tour_text.py still contains a copyable bracketed placeholder: {matches}"
    )


def test_sibling_templates_fixed():
    """All sibling files must also be free of the copyable placeholder."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    siblings = [
        "describe_point_of_interest.py",
        "generate_tour_path.py",
        "modified_generate_tour_text.py",
    ]
    for fname in siblings:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue  # dead code file removed? fine
        with open(fpath, 'r') as f:
            source = f.read()
        matches = re.findall(r'\[Detailed.*word description.*\]', source)
        assert len(matches) == 0, (
            f"{fname} still contains a copyable bracketed placeholder: {matches}"
        )


# ---------- Runner ----------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    if failed:
        sys.exit(1)
    print("All placeholder-leak regression tests passed.")
    sys.exit(0)
