#!/usr/bin/env python3
"""style_validator_detector.py — SHIM (LOCAL-192)

The canonical implementation now lives at the REPO ROOT:
  /style_validator_detector.py

This shim re-exports everything so that existing test scripts using
  from style_validator_detector import validate_paragraph
continue to work unchanged when tests/ is on sys.path.
"""
import sys
import os
import importlib.util

# Load the canonical module from repo root by absolute path to avoid
# circular import when running from within tests/ directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CANONICAL_PATH = os.path.join(_REPO_ROOT, 'style_validator_detector.py')

_spec = importlib.util.spec_from_file_location("_style_validator_canonical", _CANONICAL_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export public API
validate_paragraph = _mod.validate_paragraph
analyze_tour_style = _mod.analyze_tour_style
run_report = _mod.run_report
check_r1_imperatives = _mod.check_r1_imperatives
check_r2_questions = _mod.check_r2_questions
check_r3_suggestive_exploration = _mod.check_r3_suggestive_exploration
check_r4_prescribed_feeling = _mod.check_r4_prescribed_feeling
check_r7_hallucinated_sensory = _mod.check_r7_hallucinated_sensory
check_r8_prompt_leakage = _mod.check_r8_prompt_leakage
check_r9_generic = _mod.check_r9_generic
apply_r9_deletions = _mod.apply_r9_deletions
apply_r9_to_description = _mod.apply_r9_to_description
_is_style_navigation_paragraph = _mod._is_style_navigation_paragraph
_is_style_navigation_sentence = _mod._is_style_navigation_sentence
_split_sentences = _mod._split_sentences
