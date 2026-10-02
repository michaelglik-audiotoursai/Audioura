#!/usr/bin/env python3
"""Tests for LOCAL-318: Dangling-demonstrative detector.

Verifies:
  - Dangling demonstrative NPs are detected (no antecedent in same stop)
  - Schema lines do NOT count as antecedents
  - Legitimate demonstratives are NOT flagged:
    * "This restaurant opened in 1927." (the stop IS the restaurant)
    * "Chagall painted the ceiling. This work took two years." (antecedent present)
    * "These narrow streets wind through Vieux Nice." (setting word)
  - Repair from corpus works (substitutes proper name)
  - Deletion as fallback when no corpus name available
  - Corpus-wide scan of tours/*.txt

Run with: python3 -m pytest tests/test_local318_dangling_demonstrative.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from dangling_demonstrative_gate import (
    detect_dangling_demonstratives,
    repair_dangling_demonstrative,
    apply_dangling_demonstrative_gate,
    _noun_has_antecedent,
    _find_name_in_corpus,
    _get_stop_body_text,
    SCHEMA_LABEL_RE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION — The core defect: "This chickpea flour pancake" with no antecedent
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetection:
    """Dangling demonstratives must be caught."""

    def test_chickpea_pancake_detected(self):
        """The exact defect from LOCAL-318: 'This chickpea flour pancake'."""
        body = (
            "Madalin's great-grandchildren continue to honor her culinary traditions. "
            "This chickpea flour pancake, cooked to a golden crisp, exemplifies the "
            "region's resourcefulness."
        )
        findings = detect_dangling_demonstratives(body, "Acchiardo")
        assert len(findings) >= 1
        assert any(f['head_noun'] == 'pancake' for f in findings)

    def test_dangling_these_detected(self):
        """'These ornate frescoes' with no prior mention of frescoes."""
        body = (
            "The chapel was built in the 15th century. "
            "These ornate frescoes depict scenes from the life of Saint Catherine."
        )
        findings = detect_dangling_demonstratives(body, "Chapelle de la Miséricorde")
        assert len(findings) >= 1
        assert any(f['head_noun'] == 'frescoes' for f in findings)

    def test_dangling_that_detected(self):
        """'That ancient recipe' with no prior mention of any recipe."""
        body = (
            "The family has run this restaurant for four generations. "
            "That ancient recipe continues to draw visitors from across the region."
        )
        findings = detect_dangling_demonstratives(body, "Chez René")
        assert len(findings) >= 1
        assert any(f['head_noun'] == 'recipe' for f in findings)

    def test_schema_line_does_not_count(self):
        """A noun in a schema line must NOT serve as antecedent."""
        # "socca" appears only in a schema line — should NOT prevent detection
        lines = [
            "Type/Specialty: Niçoise traditional",
            "Specific Examples: socca (chickpea pancake), pissaladière",
            "Madalin's great-grandchildren continue to honor her traditions.",
            "This chickpea flour pancake exemplifies the region's resourcefulness.",
        ]
        body = _get_stop_body_text(lines)
        findings = detect_dangling_demonstratives(body, "Acchiardo", lines)
        assert len(findings) >= 1, (
            "Schema line 'socca (chickpea pancake)' should NOT count as antecedent"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CLEAN CASES — must NOT fire on legitimate demonstratives
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanCases:
    """Legitimate demonstratives must not be flagged."""

    def test_restaurant_stop_is_the_restaurant(self):
        """'This restaurant opened in 1927.' — the stop IS the restaurant."""
        body = "This restaurant opened in 1927."
        findings = detect_dangling_demonstratives(body, "Chez Palmyre")
        assert len(findings) == 0, (
            f"'This restaurant' should NOT fire — it's a setting word. Got: {findings}"
        )

    def test_antecedent_present_in_same_stop(self):
        """'Chagall painted the ceiling. This work took two years.' — antecedent present."""
        body = (
            "Chagall painted the ceiling. This work took two years."
        )
        findings = detect_dangling_demonstratives(body, "Musée Chagall")
        assert len(findings) == 0, (
            f"'This work' should NOT fire — 'work' is synonymous with 'painted'. Got: {findings}"
        )

    def test_narrow_streets_setting(self):
        """'These narrow streets wind through Vieux Nice.' — setting word."""
        body = "These narrow streets wind through Vieux Nice."
        findings = detect_dangling_demonstratives(body, "Vieux Nice")
        assert len(findings) == 0, (
            f"'These narrow streets' should NOT fire — 'streets' is a setting word. Got: {findings}"
        )

    def test_title_serves_as_antecedent(self):
        """Stop title provides the antecedent."""
        body = (
            "The ceiling was painted over two years. "
            "This ceiling remains one of the most celebrated in France."
        )
        findings = detect_dangling_demonstratives(body, "The Painted Ceiling of the Opéra")
        assert len(findings) == 0, (
            "'This ceiling' has 'ceiling' in title AND preceding text."
        )

    def test_earlier_mention_in_same_stop(self):
        """Noun mentioned earlier in the stop → not dangling."""
        body = (
            "The mosaic covers the entire floor. "
            "This mosaic was created by Roman artisans in the 2nd century."
        )
        findings = detect_dangling_demonstratives(body, "Villa des Arènes")
        assert len(findings) == 0, "'mosaic' was mentioned in the previous sentence"

    def test_plural_antecedent_singular_demonstrative(self):
        """'mosaics' mentioned earlier → 'this mosaic' is fine."""
        body = (
            "The villa contains several mosaics from the Roman era. "
            "This mosaic depicts Neptune riding a chariot."
        )
        findings = detect_dangling_demonstratives(body, "Villa des Arènes")
        assert len(findings) == 0, "'mosaics' (plural) licenses 'this mosaic' (singular)"


# ═══════════════════════════════════════════════════════════════════════════════
# REPAIR — Corpus name substitution
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepair:
    """Repair should prefer corpus name over deletion."""

    def test_repair_with_corpus_name(self):
        """Corpus contains 'socca, a chickpea pancake' → repair to 'Socca, a...'."""
        finding = {
            'sentence': 'This chickpea flour pancake, cooked to a golden crisp, exemplifies the region.',
            'demonstrative_np': 'This chickpea flour pancake',
            'head_noun': 'pancake',
            'full_np': 'chickpea flour pancake',
        }
        corpus = "The socca, a chickpea pancake, reflects the city's Italian influences."
        repaired, action = repair_dangling_demonstrative(
            finding['sentence'], finding, corpus
        )
        assert action == 'repaired'
        assert 'socca' in repaired.lower() or 'Socca' in repaired
        assert 'chickpea' in repaired.lower()
        # Should not start with "This" anymore
        assert not repaired.startswith('This chickpea')

    def test_delete_when_no_corpus(self):
        """No corpus available → sentence deleted."""
        finding = {
            'sentence': 'This ancient artifact dates back to the Bronze Age.',
            'demonstrative_np': 'This ancient artifact',
            'head_noun': 'artifact',
            'full_np': 'ancient artifact',
        }
        repaired, action = repair_dangling_demonstrative(
            finding['sentence'], finding, ''
        )
        assert action == 'deleted'
        assert repaired == ''

    def test_delete_when_corpus_has_no_name(self):
        """Corpus exists but doesn't contain a proper name for the noun."""
        finding = {
            'sentence': 'This elaborate tapestry covers the entire wall.',
            'demonstrative_np': 'This elaborate tapestry',
            'head_noun': 'tapestry',
            'full_np': 'elaborate tapestry',
        }
        corpus = "The museum has many exhibits from the medieval period."
        repaired, action = repair_dangling_demonstrative(
            finding['sentence'], finding, corpus
        )
        assert action == 'deleted'


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION — apply_dangling_demonstrative_gate on a poi_list
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Full gate application to a poi_list."""

    def test_gate_modifies_description(self):
        """Gate should modify description in place when dangling found."""
        poi_list = [{
            'name': 'Acchiardo',
            'stop_number': 2,
            'description': (
                "Madalin's great-grandchildren continue to honor her culinary traditions. "
                "This chickpea flour pancake, cooked to a golden crisp, exemplifies the "
                "region's resourcefulness. The kitchen has barely changed since 1927."
            ),
        }]

        # Provide corpus that contains "socca"
        corpus_data = {
            0: ["The socca, a chickpea pancake, reflects the city's Italian influences."],
        }

        stats = apply_dangling_demonstrative_gate(poi_list, stop_corpus_data=corpus_data)
        assert stats['total_detected'] >= 1
        # Either repaired or deleted
        assert stats['total_repaired'] + stats['total_deleted'] >= 1
        # The description should be different now
        assert 'This chickpea flour pancake' not in poi_list[0]['description']

    def test_gate_does_not_touch_clean_stops(self):
        """Stops without dangling demonstratives are untouched."""
        original_desc = (
            "This restaurant opened in 1927. The narrow streets around it "
            "are part of the historic old town."
        )
        poi_list = [{
            'name': 'Chez Palmyre',
            'stop_number': 1,
            'description': original_desc,
        }]

        stats = apply_dangling_demonstrative_gate(poi_list)
        assert stats['total_detected'] == 0
        assert poi_list[0]['description'] == original_desc


# ═══════════════════════════════════════════════════════════════════════════════
# CORPUS-WIDE SCAN — report count of dangling demonstratives in tours/*.txt
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorpusScan:
    """Scan all tours/*.txt for dangling demonstratives and report."""

    def test_corpus_scan(self):
        """Scan existing tour files — report findings (always passes)."""
        tours_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours'
        )
        if not os.path.isdir(tours_dir):
            pytest.skip("tours/ directory not found")

        from tour_rubric_scorer import parse_tour

        total_findings = 0
        affected_stops = []

        for fname in sorted(os.listdir(tours_dir)):
            fpath = os.path.join(tours_dir, fname)
            if not fname.endswith('.txt') or os.path.isdir(fpath):
                continue

            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            stops = parse_tour(content)
            for stop in stops:
                body = stop.get('body', '')
                title = stop.get('title', '')
                if not body:
                    continue

                findings = detect_dangling_demonstratives(body, title, stop.get('lines', []))
                if findings:
                    total_findings += len(findings)
                    for finding in findings:
                        affected_stops.append({
                            'file': fname,
                            'stop': stop.get('index', '?'),
                            'title': title,
                            'demonstrative_np': finding['demonstrative_np'],
                            'head_noun': finding['head_noun'],
                            'sentence': finding['sentence'][:100],
                        })

        # Report findings
        print(f"\n{'='*70}")
        print(f"CORPUS-WIDE DANGLING DEMONSTRATIVE SCAN")
        print(f"{'='*70}")
        print(f"Total dangling demonstratives found: {total_findings}")
        print(f"Affected stops: {len(affected_stops)}")
        if affected_stops:
            for item in affected_stops:
                print(f"  [{item['file']}] Stop {item['stop']} ({item['title']}): "
                      f"'{item['demonstrative_np']}' — head noun '{item['head_noun']}'")
                print(f"    Sentence: {item['sentence']}...")
        print(f"{'='*70}\n")

        # This test always passes — it's a measurement, not an assertion
        # The count is the finding
        assert True
