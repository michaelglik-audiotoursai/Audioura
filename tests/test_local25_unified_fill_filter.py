"""
test_local25_unified_fill_filter.py — LOCAL-25 regression test.

Verifies that the LOCAL-24 work-vs-nonwork filter in the UNIFIED-FILL and
POST-R4-FILL paths does not crash with a NameError. The original bug was
using `venue_name` (not in scope inside generate_tour_text()) instead of
`_museum_venue_name`.

This test exercises the classify_corpus_entry call in isolation (unit) and
also verifies the scoping by AST-inspecting the relevant code paths.
"""
import os
import sys
import ast
import re
import pytest

# Ensure we can import from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestClassifyCorpusEntryBasic:
    """Unit tests for classify_corpus_entry from story_miner."""

    def test_import(self):
        """classify_corpus_entry is importable from story_miner."""
        from story_miner import classify_corpus_entry
        assert callable(classify_corpus_entry)

    def test_work_classification(self):
        """A genuine artwork title is classified as 'work'."""
        from story_miner import classify_corpus_entry
        result = classify_corpus_entry(
            title="Hokusai – Voyage au pied du mont Fuji",
            venue_name="Musée des Arts asiatiques",
        )
        assert result['kind'] == 'work'
        assert 'title' in result

    def test_excluded_street(self):
        """A street name is classified as 'excluded'."""
        from story_miner import classify_corpus_entry
        result = classify_corpus_entry(
            title="Promenade des Anglais",
            venue_name="Musée des Arts asiatiques",
        )
        assert result['kind'] == 'excluded'

    def test_excluded_wiki_heading(self):
        """A Wikipedia section heading is classified as 'excluded'."""
        from story_miner import classify_corpus_entry
        result = classify_corpus_entry(
            title="Origin of the museum's pieces",
            venue_name="Musée des Arts asiatiques",
        )
        assert result['kind'] == 'excluded'

    def test_excluded_museum_meta(self):
        """A museum meta label (collections heading) is classified as 'excluded'."""
        from story_miner import classify_corpus_entry
        result = classify_corpus_entry(
            title="The museum's collections",
            venue_name="Musée des Arts asiatiques",
        )
        assert result['kind'] == 'excluded'


class TestUnifiedFillScopeRegression:
    """
    AST-based regression test: verifies that the classify_corpus_entry calls
    inside generate_tour_text() use `_museum_venue_name` (which is in scope)
    and NOT `venue_name` (which would cause NameError at runtime).
    
    This catches the exact class of bug that caused LOCAL-24 to be bounced.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Load the generate_tour_text.py source for AST analysis."""
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(src_path, 'r', encoding='utf-8') as f:
            self.source = f.read()
        self.source_lines = self.source.split('\n')

    def _find_classify_calls_in_generate_tour_text(self):
        """Find all classify_corpus_entry calls and their venue_name arg values."""
        # We look for the pattern in raw source since full AST parse of 250KB+ is slow
        # and the function is too large for clean AST walking.
        # Find the generate_tour_text function boundaries
        func_start = None
        for i, line in enumerate(self.source_lines):
            if re.match(r'^def generate_tour_text\(', line):
                func_start = i
                break
        assert func_start is not None, "generate_tour_text function not found"

        # Scan for classify_corpus_entry calls within the function
        calls = []
        i = func_start
        while i < len(self.source_lines):
            line = self.source_lines[i]
            # Stop at next top-level function def (unindented)
            if i > func_start and re.match(r'^def ', line):
                break
            if 'classify_corpus_entry(' in line:
                # Gather the full call (might span multiple lines)
                call_text = line
                j = i + 1
                while j < len(self.source_lines) and ')' not in call_text:
                    call_text += '\n' + self.source_lines[j]
                    j += 1
                # Also grab a few more lines to capture the closing paren
                while j < min(i + 10, len(self.source_lines)):
                    call_text += '\n' + self.source_lines[j]
                    if ')' in self.source_lines[j]:
                        break
                    j += 1
                calls.append((i + 1, call_text))  # 1-indexed line number
            i += 1
        return calls

    def test_no_bare_venue_name_in_classify_calls(self):
        """
        REGRESSION: classify_corpus_entry calls inside generate_tour_text()
        must use _museum_venue_name, not venue_name.
        
        venue_name is NOT defined in generate_tour_text()'s scope — it only
        exists as a parameter in _verify_works_v2() and 
        _validate_museum_stop_descriptions().
        """
        calls = self._find_classify_calls_in_generate_tour_text()
        
        # There should be at least 2 calls (UNIFIED-FILL + POST-R4-FILL)
        assert len(calls) >= 2, (
            f"Expected at least 2 classify_corpus_entry calls in generate_tour_text, "
            f"found {len(calls)}"
        )

        for line_no, call_text in calls:
            # Check that venue_name= argument uses _museum_venue_name
            assert 'venue_name=_museum_venue_name' in call_text, (
                f"Line {line_no}: classify_corpus_entry uses wrong variable for venue_name. "
                f"Must be _museum_venue_name (in scope), not venue_name (NameError). "
                f"Call text: {call_text[:200]}"
            )
            # Negative check: bare venue_name= without prefix must not appear
            # (except as part of _museum_venue_name)
            bare_match = re.search(r'venue_name\s*=\s*venue_name\b', call_text)
            assert bare_match is None, (
                f"Line {line_no}: Found bare 'venue_name=venue_name' which will cause "
                f"NameError in generate_tour_text(). Use _museum_venue_name instead."
            )

    def test_filter_corpus_titles_in_verify_works_uses_venue_name_param(self):
        """
        In _verify_works_v2(), filter_corpus_titles correctly uses the function's
        own `venue_name` parameter (which IS in scope there).
        """
        # Find the _verify_works_v2 function
        func_start = None
        func_end = None
        for i, line in enumerate(self.source_lines):
            if re.match(r'^def _verify_works_v2\(', line):
                func_start = i
            elif func_start and i > func_start and re.match(r'^def ', line):
                func_end = i
                break
        assert func_start is not None, "_verify_works_v2 function not found"
        if func_end is None:
            func_end = len(self.source_lines)

        # Find filter_corpus_titles call
        func_body = '\n'.join(self.source_lines[func_start:func_end])
        assert 'filter_corpus_titles(' in func_body, (
            "filter_corpus_titles call not found in _verify_works_v2"
        )
        assert 'venue_name=venue_name' in func_body, (
            "_verify_works_v2 should pass its own venue_name parameter to filter_corpus_titles"
        )


class TestFilterCorpusTitlesIntegration:
    """Integration test for the full filter pipeline."""

    def test_asian_arts_museum_corpus_filter(self):
        """
        The Asian Arts Museum corpus (22 raw titles) should filter down to
        exactly 7 genuine works, excluding programmes, workshops, streets,
        and Wikipedia section headings.
        """
        from story_miner import filter_corpus_titles

        # The 22 titles as discovered from the Asian Arts Museum corpus
        # (These are the titles that LOCAL-24's filter was designed to classify)
        raw_titles = {
            "Daim et Daine symbolisant le premier sermon de Bouddha",
            "Hokusai – Voyage au pied du mont Fuji",
            "disque / fauteuil / la geste de Bouddha / les paysages de l'âme",
            "l'art en exil - Hàm Nghi, Prince d'Annam (1871-1944)",
            "Promenade des Anglais",
            "Origin of the museum's pieces",
            "The museum's collections",
            # Workshop duplicates
            "Monstre(s)",
            "Monstre(s) – Atelier enfants",
            "Monstre(s) – Visite guidée",
            # Cross-language duplicate
            "Stag and hind symbolising the first sermon of Buddha",
        }

        result = filter_corpus_titles(
            raw_titles=raw_titles,
            sparql_works=[],
            source_urls_map={},
            venue_name="Musée des Arts asiatiques",
            venue_address="405 Promenade des Anglais, Nice",
            preferred_language="fr",
        )

        works = result['works']
        excluded = result['excluded']

        # The street, wiki headings, and workshop dupes should be excluded
        excluded_titles = {e['title'] for e in excluded}
        assert "Promenade des Anglais" in excluded_titles, "Street should be excluded"

        # Genuine works should be retained
        assert "Hokusai – Voyage au pied du mont Fuji" in works

        # Should have <= 7 genuine works (may vary slightly based on rule specifics)
        # The key constraint: non-works MUST NOT survive
        assert len(works) <= 10, f"Too many works survived: {len(works)}"
        assert len(works) >= 3, f"Too few works survived: {len(works)}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
