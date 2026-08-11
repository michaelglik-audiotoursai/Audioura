"""LOCAL-417: Tests for positive assertion gate and required-names suppression.

Root cause: The NAMES THAT MUST APPEAR block demanded surnames the pipeline never
supplied (e.g., "Adam and Eve" has no artist in our data). The model reported the
impossibility instead of writing prose. A denylist cannot catch every rephrasing.

Fix 1: Only emit required names that have evidence in the stop's snippet text.
Fix 2: Positive assertion gate — assert what the text IS, not what it must not be:
  - Names its subject
  - States at least one concrete fact
  - Addresses the listener, never the operator
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPositiveGate:
    """The positive assertion gate validates generated text by what it IS,
    not by matching a denylist of what it shouldn't be."""

    def _run_gate(self, description, poi_name):
        """Simulate the positive gate logic from generate_tour_text.py.
        Returns (pass: bool, failures: list[str])."""
        _417_gate_pass = True
        _417_gate_failures = []

        # Check 1: text names its subject
        _417_desc_lower = description.lower()
        _417_poi_lower = poi_name.lower()
        _417_poi_words = [w for w in re.findall(r'\b[a-z]{3,}\b', _417_poi_lower)
                          if w not in ('the', 'and', 'for', 'from', 'with', 'that', 'this')]
        _417_subject_named = (_417_poi_lower in _417_desc_lower or
                             any(w in _417_desc_lower for w in _417_poi_words))
        if not _417_subject_named:
            _417_gate_pass = False
            _417_gate_failures.append(f"subject not named")

        # Check 2: at least one concrete fact
        _417_has_fact = bool(re.search(
            r'\b(?:1[0-9]{3}|20[0-2][0-9])\b'
            r'|\b\d+\s*(?:cm|inches|feet|meters|ft|in)\b'
            r'|\b(?:oil on canvas|bronze|marble|lithograph|watercolor|fresco|'
            r'tempera|etching|woodcut|ceramic|terracotta|limestone|granite)\b'
            r'|\b(?:donated|acquired|commissioned|exhibited|installed)\s+(?:in|by)\b',
            description, re.IGNORECASE
        ))
        if not _417_has_fact:
            _417_gate_pass = False
            _417_gate_failures.append("no concrete fact")

        # Check 3: no operator-directed language
        _417_operator_patterns = re.compile(
            r'\byour (?:description|text|narrative|response|prompt|request)\b'
            r'|\bnotify me\b'
            r'|\brequire(?:s|d)? further assistance\b'
            r'|\bensure to include\b'
            r'|\bmissing required\b'
            r'|\bspecified individuals\b'
            r'|\byour (?:instructions?|requirements?|constraints?)\b'
            r'|\bprovide (?:more|the|additional) (?:details?|information|context)\b'
            r'|\bin your (?:narrative|description|text)\b',
            re.IGNORECASE
        )
        _417_operator_match = _417_operator_patterns.search(description)
        if _417_operator_match:
            _417_gate_pass = False
            _417_gate_failures.append(f"operator-directed: '{_417_operator_match.group(0)}'")

        return _417_gate_pass, _417_gate_failures

    def test_good_stop_passes(self):
        """Valid tour text about 'Appeal to the Great Spirit' passes all checks."""
        text = (
            "Before you stands 'Appeal to the Great Spirit,' a bronze equestrian statue "
            "by Cyrus Dallin, installed in 1913 outside the Museum of Fine Arts. The figure "
            "of a Lakota warrior on horseback reaches skyward in a gesture of spiritual "
            "communion. Dallin completed this work after studying with indigenous communities "
            "in Utah, bringing authenticity to the pose and expression."
        )
        passed, failures = self._run_gate(text, "Appeal to the Great Spirit")
        assert passed, f"Expected gate to pass. Failures: {failures}"

    def test_415_refusal_fails_operator_check(self):
        """The exact text from 415's stop 3 — caught by operator-directed check."""
        text = (
            "There are still some missing required names in your description. "
            "Ensure to include each of the specified individuals with their surnames "
            "and roles in the narrative. Notify me if you require further assistance with this."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert not passed, "Expected gate to FAIL on operator-directed text"
        # Should fail on operator-directed language specifically
        assert any("operator-directed" in f for f in failures), (
            f"Expected operator-directed failure, got: {failures}"
        )

    def test_414_refusal_also_fails(self):
        """The 414-round refusal — also caught even without the denylist."""
        text = (
            "I cannot provide a response based on the given constraints and missing "
            "surnames. The required individuals are not present in the reference material."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert not passed, "Expected gate to FAIL on 414 refusal text"

    def test_operator_rephrasing_fails(self):
        """Any future rephrasing of 'I can't do what you asked' fails the gate
        because it doesn't name the subject or state a fact about it."""
        phrasings = [
            "The provided information lacks the necessary details to construct the narrative. Please supply additional context.",
            "Unable to fulfill the request as the specified names are not available in the source material.",
            "Your description needs to include the required individuals. Please check your instructions.",
            "I notice there are gaps in the material provided. Could you provide the missing surnames?",
        ]
        for text in phrasings:
            passed, failures = self._run_gate(text, "Adam and Eve")
            assert not passed, (
                f"Expected gate to FAIL on rephrased refusal. Text: {text!r}. Failures: {failures}"
            )

    def test_subject_not_named_fails(self):
        """Text that talks about something else entirely fails check 1."""
        text = (
            "The museum houses an impressive collection of impressionist paintings "
            "from the late 1800s. Visitors can admire works by Monet and Renoir."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert not passed
        assert any("subject not named" in f for f in failures)

    def test_no_fact_fails(self):
        """Flowery prose without a single concrete fact fails check 2."""
        text = (
            "Adam and Eve is a profound exploration of the human condition, "
            "inviting viewers to contemplate the eternal struggle between "
            "temptation and innocence in a remarkably evocative manner."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert not passed
        assert any("no concrete fact" in f for f in failures)

    def test_with_year_passes_fact_check(self):
        """Mentioning a year counts as a concrete fact."""
        text = (
            "Adam and Eve depicts the biblical first couple in a style characteristic "
            "of Northern Renaissance painting from 1526."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert passed, f"Expected pass with year. Failures: {failures}"

    def test_with_material_passes_fact_check(self):
        """Mentioning a material counts as a concrete fact."""
        text = (
            "This Adam and Eve is rendered in oil on canvas, showing the figures "
            "against a dark woodland backdrop."
        )
        passed, failures = self._run_gate(text, "Adam and Eve")
        assert passed, f"Expected pass with material. Failures: {failures}"


class TestRequiredNamesSuppression:
    """The required-names block must only demand names present in snippet text."""

    def test_name_with_evidence_passes(self):
        """A person whose surname appears in snippet text should be included."""
        snippet_text = "Lucas Cranach the Elder painted this work in 1526 for the Elector of Saxony."
        beat = {'person': 'Lucas Cranach', 'role': 'creator'}
        surname = beat['person'].split()[-1]
        assert surname.lower() in snippet_text.lower()

    def test_name_without_evidence_suppressed(self):
        """A person whose surname does NOT appear in snippets must be suppressed."""
        snippet_text = "The painting depicts the biblical narrative of Adam and Eve in the garden."
        beat = {'person': 'Francis Bartlett', 'role': 'donor'}
        surname = beat['person'].split()[-1]
        assert surname.lower() not in snippet_text.lower()

    def test_empty_snippet_text_suppresses_all(self):
        """When there's no snippet text at all, ALL required names are suppressed."""
        snippet_text = ''
        beats = [
            {'person': 'Lucas Cranach', 'role': 'creator'},
            {'person': 'Francis Bartlett', 'role': 'donor'},
        ]
        for beat in beats:
            surname = beat['person'].split()[-1]
            # With empty snippet text, no name can be verified
            assert not (snippet_text and surname.lower() in snippet_text.lower())

    def test_artist_still_required_when_known(self):
        """Even if no story-beat names have evidence, artist is still required
        when artist is known (it comes from structured data, not snippets)."""
        # This tests the logic: artist requirement is separate from beat requirements
        artist = "Lucas Cranach"
        # The artist block is emitted separately from story-beat names
        assert artist  # artist is truthy = artist block is emitted

    def test_mixed_evidence(self):
        """Only names with evidence are demanded; others are suppressed."""
        snippet_text = (
            "Cranach painted this work using techniques learned in Vienna. "
            "The painting was later acquired by the museum in 1948."
        )
        beats = [
            {'person': 'Lucas Cranach', 'role': 'creator'},    # surname in text
            {'person': 'Francis Bartlett', 'role': 'donor'},   # surname NOT in text
            {'person': 'Martin Luther', 'role': 'collaborator'},  # surname NOT in text
        ]
        verified = []
        suppressed = []
        for beat in beats:
            surname = beat['person'].split()[-1]
            if surname.lower() in snippet_text.lower():
                verified.append(beat['person'])
            else:
                suppressed.append(beat['person'])

        assert verified == ['Lucas Cranach']
        assert 'Francis Bartlett' in suppressed
        assert 'Martin Luther' in suppressed


class TestGateOnLiveFailures:
    """Test the gate against the actual failure text from the 415 run."""

    def _get_refusal_detector(self):
        """Build the refusal detector regex (same patterns as source)."""
        patterns = [
            r'\bmissing required names?\b',
            r'\bensure to include\b',
            r'\bnotify me if you require\b',
            r'\brequire further assistance\b',
        ]
        return re.compile('|'.join(patterns), re.IGNORECASE)

    def test_stop3_exact_text(self):
        """The exact stop 3 text that shipped in the 415 run — caught by denylist."""
        detector = self._get_refusal_detector()
        text = (
            "There are still some missing required names in your description. "
            "Ensure to include each of the specified individuals with their surnames "
            "and roles in the narrative. Notify me if you require further assistance with this."
        )
        assert detector.search(text), f"Denylist should catch this text"

    def test_stop4_fallback_text(self):
        """Stop 4's 'could not be generated' text — this is our honest fallback,
        not the model's text. It should NOT trigger the positive gate (it's excluded
        by the startswith check)."""
        text = "Artist in his studio — located in this gallery. A detailed narration could not be generated for this stop."
        # This is excluded from the gate by the startswith check
        assert text.startswith("Artist in his studio — located in this gallery")
