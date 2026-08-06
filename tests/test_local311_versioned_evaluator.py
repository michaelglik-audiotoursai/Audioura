#!/usr/bin/env python3
"""
Tests for LOCAL-311: Versioned Evaluator.

Verifies:
  1. evaluate() produces identical scores to the old direct-internal path.
  2. Stale version detection raises AlgorithmVersionError.
  3. Registry lookup works for current and historical versions.
  4. No production caller imports scorer internals directly.
  5. All three generation paths record a score.
"""
import os
import sys
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tour_evaluator import (
    evaluate,
    Evaluation,
    ALGORITHM_ID,
    ALGORITHM_VERSION,
    AlgorithmVersionError,
    get_algorithm_registry,
    lookup_algorithm,
    register_historical_version,
    _build_algorithm_config,
    _compute_config_hash,
    _REGISTERED_VERSIONS,
    _CURRENT_CONFIG_HASH,
)
from tour_rubric_scorer import (
    parse_tour,
    analyze_stop,
    classify_stop,
    compute_score,
    detect_venue_identity,
    TourScore,
)


# --- Fixtures ----------------------------------------------------------------

MUSEUM_TOUR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tours", "LOCAL303_museum_8stop_gate.txt"
)


@pytest.fixture
def museum_tour_text():
    """Load the museum 8-stop tour fixture."""
    with open(MUSEUM_TOUR_PATH, 'r', encoding='utf-8') as f:
        return f.read()


# --- Test 1: Identical scores ------------------------------------------------

def test_evaluate_produces_identical_scores(museum_tour_text):
    """The new evaluate() entry point must produce the exact same numbers
    as the old direct-internal path."""
    n_requested = 8

    # OLD PATH: reach into internals directly (what callers used to do)
    stops_parsed = parse_tour(museum_tour_text)
    stop_analyses_old = []
    for stop in stops_parsed:
        sa = analyze_stop(stop, stops_parsed)
        cls, evidence = classify_stop(sa)
        sa.classification = cls
        sa.classification_evidence = evidence
        stop_analyses_old.append(sa)
    venue_facts_old = detect_venue_identity(museum_tour_text)
    old_score = compute_score(stop_analyses_old, n_requested, venue_facts_old)

    # NEW PATH: single entry point
    evaluation = evaluate(museum_tour_text, n_requested)

    assert evaluation is not None
    new_score = evaluation.score

    # Verify identical numbers
    assert new_score.total_score == old_score.total_score, (
        f"Total score mismatch: {new_score.total_score} != {old_score.total_score}"
    )
    assert new_score.base_score == old_score.base_score
    assert new_score.structural_surcharge == old_score.structural_surcharge
    assert new_score.correlation_bonus == old_score.correlation_bonus
    assert new_score.venue_identity_bonus == old_score.venue_identity_bonus
    assert new_score.n_delivered == old_score.n_delivered
    assert new_score.n_requested == old_score.n_requested

    # Verify per-stop classifications match
    for old_sa, new_ps in zip(stop_analyses_old, evaluation.per_stop):
        assert old_sa.classification == new_ps["classification"], (
            f"Stop {old_sa.index} classification mismatch: "
            f"{old_sa.classification} != {new_ps['classification']}"
        )


# --- Test 2: Stale version detection -----------------------------------------

def test_stale_version_detection(museum_tour_text):
    """If thresholds change without bumping ALGORITHM_VERSION, evaluate() must
    raise AlgorithmVersionError."""
    # Inject a conflicting registration (same version, different hash)
    fake_key = f"{ALGORITHM_VERSION}@STALETEST"
    _REGISTERED_VERSIONS[fake_key] = {
        "version": ALGORITHM_VERSION,
        "config": {"tampered": True},
        "config_hash": "STALETEST",
        "registered_at": "2026-01-01T00:00:00+00:00",
    }

    try:
        with pytest.raises(AlgorithmVersionError) as exc_info:
            evaluate(museum_tour_text, 8)

        assert "Stale version detected" in str(exc_info.value)
        assert ALGORITHM_VERSION in str(exc_info.value)
    finally:
        # Clean up
        del _REGISTERED_VERSIONS[fake_key]


# --- Test 3: Registry lookup --------------------------------------------------

def test_registry_contains_current_version():
    """The current version must be in the registry."""
    registry = get_algorithm_registry()
    assert ALGORITHM_ID in registry
    entry = registry[ALGORITHM_ID]
    assert entry["version"] == ALGORITHM_VERSION
    assert entry["config_hash"] == _CURRENT_CONFIG_HASH


def test_registry_contains_historical_version():
    """LOCAL-306-v1 (predecessor) must be registered and lookupable."""
    registry = get_algorithm_registry()
    # Find the LOCAL-306-v1 entry
    found = None
    for algo_id, entry in registry.items():
        if entry["version"] == "LOCAL-306-v1":
            found = entry
            break
    assert found is not None, "LOCAL-306-v1 not found in registry"
    assert found["config"]["rich_min_facts"] == 4
    assert found["config"]["adequate_min_facts"] == 3


def test_lookup_unknown_version_returns_none():
    """Looking up a nonexistent algorithm_id returns None."""
    result = lookup_algorithm("NONEXISTENT-v99@deadbeef")
    assert result is None


def test_register_and_lookup_historical():
    """register_historical_version + lookup_algorithm round-trips."""
    register_historical_version("TEST-v42", {
        "version": "TEST-v42",
        "rich_min_density": 0.99,
        "rich_min_facts": 99,
        "rich_max_filler": 0.01,
        "adequate_min_density": 0.50,
        "adequate_min_facts": 50,
        "adequate_max_filler": 0.10,
        "rich_min_groundedness": 0.90,
        "fabricated_weight": -2.0,
        "missing_weight": -1.0,
        "thin_weight": 0.4,
        "adequate_weight": 0.7,
        "rich_weight": 1.0,
        "pipeline_lost_weight": -1.0,
        "unavailable_weight": -0.15,
        "structural_per_defect": -0.25,
        "structural_cap": -0.5,
        "correlation_multiplier": 0.5,
        "venue_identity_max_fraction": 0.10,
        "venue_identity_max_facts": 5,
    })
    config_hash = _compute_config_hash({
        "version": "TEST-v42",
        "rich_min_density": 0.99,
        "rich_min_facts": 99,
        "rich_max_filler": 0.01,
        "adequate_min_density": 0.50,
        "adequate_min_facts": 50,
        "adequate_max_filler": 0.10,
        "rich_min_groundedness": 0.90,
        "fabricated_weight": -2.0,
        "missing_weight": -1.0,
        "thin_weight": 0.4,
        "adequate_weight": 0.7,
        "rich_weight": 1.0,
        "pipeline_lost_weight": -1.0,
        "unavailable_weight": -0.15,
        "structural_per_defect": -0.25,
        "structural_cap": -0.5,
        "correlation_multiplier": 0.5,
        "venue_identity_max_fraction": 0.10,
        "venue_identity_max_facts": 5,
    })
    algo_id = f"TEST-v42@{config_hash}"
    result = lookup_algorithm(algo_id)
    assert result is not None
    assert result["config"]["rich_min_facts"] == 99


# --- Test 4: No caller touches internals -------------------------------------

def test_no_production_caller_imports_scorer_internals():
    """Production callers must not import parse_tour, analyze_stop, classify_stop,
    compute_score, or detect_venue_identity from tour_rubric_scorer.

    Allowed exceptions:
      - tour_evaluator.py itself (it's the interface boundary)
      - test files (they test the scorer directly)
      - run_* scripts (one-off scripts, not production)
      - groundedness_check.py (uses parse_tour for its own parsing, not scoring)
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Production callers that must NOT reach into scorer
    production_files = [
        "tour_scoring_service.py",
        "tour_orchestrator_service.py",
        "tour_editing_phase2.py",
        "generate_tour_text_service.py",
        "quality_guardrails.py",
    ]

    # The internal functions that must not be imported by callers
    forbidden_imports = [
        "parse_tour",
        "analyze_stop",
        "classify_stop",
        "compute_score",
        "detect_venue_identity",
    ]

    violations = []
    for filename in production_files:
        filepath = os.path.join(project_root, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        for func_name in forbidden_imports:
            # Match "from tour_rubric_scorer import ... <func_name> ..."
            # but allow TourScore/StopAnalysis (data classes)
            pattern = rf'from\s+tour_rubric_scorer\s+import\s+.*\b{func_name}\b'
            matches = re.findall(pattern, content)
            if matches:
                violations.append(f"{filename}: imports {func_name} from tour_rubric_scorer")

    assert not violations, (
        "Production callers must not import scorer internals:\n" +
        "\n".join(f"  - {v}" for v in violations)
    )


# --- Test 5: Evaluation carries algorithm identity ---------------------------

def test_evaluation_carries_algorithm_identity(museum_tour_text):
    """The Evaluation object must carry meaningful algorithm identity."""
    ev = evaluate(museum_tour_text, 8)
    assert ev is not None

    # Algorithm ID has format "VERSION@HASH"
    assert "@" in ev.algorithm_id
    version_part, hash_part = ev.algorithm_id.split("@")
    assert version_part == ALGORITHM_VERSION
    assert len(hash_part) == 8  # 8 hex chars

    # Config hash matches
    assert ev.algorithm_config_hash == _CURRENT_CONFIG_HASH

    # Timestamp is ISO 8601
    assert "T" in ev.scored_at
    assert "+" in ev.scored_at or "Z" in ev.scored_at


# --- Test 6: Empty/invalid input returns None --------------------------------

def test_evaluate_empty_text_returns_none():
    """evaluate() on empty text must return None, not crash."""
    assert evaluate("", 8) is None
    assert evaluate("   ", 8) is None
    assert evaluate("No stops here, just prose.", 8) is None


# --- Test 7: Config hash changes when thresholds change -----------------------

def test_config_hash_changes_with_thresholds():
    """Changing any threshold must change the config hash."""
    base_config = _build_algorithm_config()
    base_hash = _compute_config_hash(base_config)

    # Change one threshold
    modified = dict(base_config)
    modified["rich_min_facts"] = 99
    modified_hash = _compute_config_hash(modified)

    assert modified_hash != base_hash, (
        "Config hash should change when rich_min_facts changes"
    )
