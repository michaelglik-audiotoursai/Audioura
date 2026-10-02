"""LOCAL-435: Test that the intent parser survives markdown-fenced JSON.

Module scope: imports strip_llm_json_fences from generate_tour_text (the production
symbol) and exercises it with fenced, prose-wrapped, and clean JSON fixtures.

Neutralise: removing the strip call (reverting to raw json.loads(intent_text)) must
make the fenced-input tests fail.
"""
import json
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from generate_tour_text import strip_llm_json_fences


# --- Fixtures: exact shapes observed in LOCAL-434's traces ---

CLEAN_JSON = '''{
    "poi_type": "museum exhibits",
    "location": "Boston, MA",
    "venue_name": "Museum of Fine Arts, Boston",
    "scope_precision": "BUILDING"
}'''

FENCED_JSON_TRIPLE = '''```json
{
    "poi_type": "museum exhibits",
    "location": "Boston, MA",
    "venue_name": "Museum of Fine Arts, Boston",
    "scope_precision": "BUILDING"
}
```'''

FENCED_JSON_NO_LANG = '''```
{
    "poi_type": "museum exhibits",
    "location": "Boston, MA",
    "venue_name": "Museum of Fine Arts, Boston",
    "scope_precision": "BUILDING"
}
```'''

FENCED_WITH_PREAMBLE = '''Here is the JSON analysis of the tour request:

```json
{
    "poi_type": "museum exhibits",
    "location": "Boston, MA",
    "venue_name": "Museum of Fine Arts, Boston",
    "scope_precision": "BUILDING"
}
```

Let me know if you need anything else.'''

PROSE_WRAPPED = '''Sure! Here is the analysis:

{
    "poi_type": "museum exhibits",
    "location": "Boston, MA",
    "venue_name": "Museum of Fine Arts, Boston",
    "scope_precision": "BUILDING"
}

I hope this helps!'''

SINGLE_BACKTICK = '''`{"poi_type": "museum exhibits", "location": "Boston, MA", "venue_name": "Museum of Fine Arts, Boston", "scope_precision": "BUILDING"}`'''

# Array case (less common but should not break)
FENCED_ARRAY = '''```json
[{"name": "Stop 1"}, {"name": "Stop 2"}]
```'''


class TestStripLlmJsonFences:
    """Test strip_llm_json_fences with various LLM response shapes."""

    def test_clean_json_unchanged(self):
        """Clean JSON passes through without modification."""
        result = strip_llm_json_fences(CLEAN_JSON)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"

    def test_triple_backtick_json_fence(self):
        """```json ... ``` fences are stripped — the exact failure from LOCAL-434."""
        result = strip_llm_json_fences(FENCED_JSON_TRIPLE)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"
        assert parsed["poi_type"] == "museum exhibits"

    def test_triple_backtick_no_language(self):
        """``` ... ``` without language tag is also stripped."""
        result = strip_llm_json_fences(FENCED_JSON_NO_LANG)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"

    def test_fenced_with_preamble_and_postamble(self):
        """Fenced JSON with surrounding prose is extracted."""
        result = strip_llm_json_fences(FENCED_WITH_PREAMBLE)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"

    def test_prose_wrapped_json(self):
        """JSON embedded in prose (no fences) is found by brace search."""
        result = strip_llm_json_fences(PROSE_WRAPPED)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"

    def test_single_backtick(self):
        """Single backtick wrapping is handled."""
        result = strip_llm_json_fences(SINGLE_BACKTICK)
        parsed = json.loads(result)
        assert parsed["venue_name"] == "Museum of Fine Arts, Boston"

    def test_fenced_array(self):
        """Array JSON inside fences is also extracted."""
        result = strip_llm_json_fences(FENCED_ARRAY)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Stop 1"

    def test_empty_string(self):
        """Empty string passes through (will fail json.loads, not our problem)."""
        result = strip_llm_json_fences("")
        assert result == ""

    def test_whitespace_around_fences(self):
        """Leading/trailing whitespace around fences is handled."""
        input_text = "  \n  ```json\n{\"key\": \"value\"}\n```  \n  "
        result = strip_llm_json_fences(input_text)
        parsed = json.loads(result)
        assert parsed["key"] == "value"


class TestNeutralisationProof:
    """Prove that without strip_llm_json_fences, fenced JSON breaks json.loads.

    This is the 'red when neutralised' requirement: if you remove the strip call,
    these inputs CANNOT parse.
    """

    def test_fenced_json_fails_raw_parse(self):
        """Fenced JSON absolutely cannot be parsed by raw json.loads."""
        import pytest
        with pytest.raises(json.JSONDecodeError):
            json.loads(FENCED_JSON_TRIPLE)

    def test_prose_wrapped_fails_raw_parse(self):
        """Prose-wrapped JSON cannot be parsed by raw json.loads."""
        import pytest
        with pytest.raises(json.JSONDecodeError):
            json.loads(PROSE_WRAPPED)

    def test_preamble_fails_raw_parse(self):
        """JSON with preamble/postamble cannot be parsed by raw json.loads."""
        import pytest
        with pytest.raises(json.JSONDecodeError):
            json.loads(FENCED_WITH_PREAMBLE)
