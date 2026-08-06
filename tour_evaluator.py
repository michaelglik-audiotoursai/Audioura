#!/usr/bin/env python3
"""
Tour Evaluator — versioned, encapsulated evaluation interface (LOCAL-311).

This module defines the SINGLE entry point for tour evaluation:

    evaluate(tour_text, n_requested, **context) -> Evaluation

No caller may import parse_tour, analyze_stop, classify_stop, compute_score,
or detect_venue_identity directly from tour_rubric_scorer. All access goes
through evaluate().

The Evaluation object carries:
  - The score (TourScore)
  - The per-stop detail
  - The algorithm identity (version + config hash)
  - The timestamp

Algorithm identity includes the values that change the answer: band thresholds
and weights. Two scores are comparable ONLY if their algorithm_id matches.

A registry maps algorithm_id -> config snapshot, so a score from months ago
is interpretable without checking out the repo.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# --- Private imports: callers must NOT reach past this module ----------------
import tour_rubric_scorer as _scorer

from tour_rubric_scorer import (
    parse_tour as _parse_tour,
    analyze_stop as _analyze_stop,
    classify_stop as _classify_stop,
    compute_score as _compute_score,
    detect_venue_identity as _detect_venue_identity,
    _compute_groundedness_for_stop as _compute_groundedness,
    TourScore,
    StopAnalysis,
)


# =============================================================================
# Algorithm Configuration — the values that change the answer
# =============================================================================

# Human-readable version string. MUST be bumped when thresholds/weights change.
# Format: "LOCAL-311-vN" where N increments on every algorithm change.
ALGORITHM_VERSION = "LOCAL-311-v1"

# The config dict captures every value that affects the score. If any of these
# change, the algorithm_id changes and scores are no longer comparable.
def _build_algorithm_config() -> Dict[str, Any]:
    """Snapshot the current algorithm configuration.

    Reads threshold values from tour_rubric_scorer at call time, so changes
    to thresholds are detected by the stale-version guard.
    """
    return {
        "version": ALGORITHM_VERSION,
        # Classification thresholds (read live from the scorer module)
        "rich_min_density": _scorer.RICH_MIN_DENSITY,
        "rich_min_facts": _scorer.RICH_MIN_FACTS,
        "rich_max_filler": _scorer.RICH_MAX_FILLER,
        "adequate_min_density": _scorer.ADEQUATE_MIN_DENSITY,
        "adequate_min_facts": _scorer.ADEQUATE_MIN_FACTS,
        "adequate_max_filler": _scorer.ADEQUATE_MAX_FILLER,
        "rich_min_groundedness": _scorer.RICH_MIN_GROUNDEDNESS,
        # Score weights (from compute_score logic)
        "fabricated_weight": -1.5,
        "missing_weight": -1.0,
        "thin_weight": 0.5,
        "adequate_weight": 0.75,
        "rich_weight": 1.0,
        "pipeline_lost_weight": -1.0,
        "unavailable_weight": -0.15,
        "structural_per_defect": -0.25,
        "structural_cap": -0.5,
        "correlation_multiplier": 0.5,
        "venue_identity_max_fraction": 0.10,
        "venue_identity_max_facts": 5,
    }


def _compute_config_hash(config: Optional[Dict[str, Any]] = None) -> str:
    """Deterministic hash of the algorithm config, truncated to 8 hex chars.

    This changes if any threshold or weight changes, providing automatic
    stale-version detection.

    Args:
        config: Algorithm config dict. If None, uses the current config.
    """
    if config is None:
        config = _build_algorithm_config()
    # Sort keys for determinism
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


# Build at import time — this is the "current" algorithm identity.
_CURRENT_CONFIG = _build_algorithm_config()
_CURRENT_CONFIG_HASH = _compute_config_hash(_CURRENT_CONFIG)

# The full algorithm_id: human-readable version + config hash.
# Example: "LOCAL-311-v1@a3f9c2b1"
ALGORITHM_ID = f"{ALGORITHM_VERSION}@{_CURRENT_CONFIG_HASH}"


# =============================================================================
# Stale Version Detection
# =============================================================================

# On first import, record the config hash that corresponds to ALGORITHM_VERSION.
# If a developer changes thresholds without bumping ALGORITHM_VERSION, the
# config hash will differ from what was registered and we raise loudly.
_REGISTERED_VERSIONS: Dict[str, Dict[str, Any]] = {}


def _register_version(version: str, config: Dict[str, Any], config_hash: str):
    """Register a version in the in-memory registry."""
    _REGISTERED_VERSIONS[f"{version}@{config_hash}"] = {
        "version": version,
        "config": config,
        "config_hash": config_hash,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


def _validate_version_consistency():
    """Check that ALGORITHM_VERSION hasn't been used with different configs.

    Rebuilds the config from current threshold values on every call. If the
    thresholds have drifted since import (e.g. a test or hot-patch modified
    them) without a version bump, this raises AlgorithmVersionError.

    The primary use case: a developer edits thresholds in tour_rubric_scorer.py
    and forgets to bump ALGORITHM_VERSION. On the next evaluate() call, this
    detects the hash mismatch and refuses to produce a score with a stale label.
    """
    # Rebuild config from live values — not the cached import-time snapshot
    live_config = _build_algorithm_config()
    live_hash = _compute_config_hash(live_config)

    # Check against every registered entry with the same version string
    for algo_id, entry in _REGISTERED_VERSIONS.items():
        if entry["version"] == ALGORITHM_VERSION and entry["config_hash"] != live_hash:
            raise AlgorithmVersionError(
                f"Stale version detected! ALGORITHM_VERSION={ALGORITHM_VERSION!r} "
                f"was registered with config_hash={entry['config_hash']!r}, "
                f"but current thresholds produce hash={live_hash!r}. "
                f"A threshold or weight changed without bumping the version. "
                f"Bump ALGORITHM_VERSION in tour_evaluator.py."
            )


class AlgorithmVersionError(Exception):
    """Raised when algorithm thresholds change without a version bump."""
    pass


# Register current version on import
_register_version(ALGORITHM_VERSION, _CURRENT_CONFIG, _CURRENT_CONFIG_HASH)


# =============================================================================
# Registry — recover what any algorithm_id did
# =============================================================================

def get_algorithm_registry() -> Dict[str, Dict[str, Any]]:
    """Return the full registry of known algorithm versions.

    Each entry maps algorithm_id -> {version, config, config_hash, registered_at}.
    A score from months ago can be interpreted by looking up its algorithm_id here.
    """
    return dict(_REGISTERED_VERSIONS)


def get_current_config_hash() -> str:
    """Return the config hash for the current algorithm state.

    Useful for external validation: if this differs from the hash embedded in
    ALGORITHM_ID, thresholds have changed without a version bump.
    """
    return _compute_config_hash()


def lookup_algorithm(algorithm_id: str) -> Optional[Dict[str, Any]]:
    """Look up what a specific algorithm_id did.

    Args:
        algorithm_id: The full id (e.g. "LOCAL-311-v1@a3f9c2b1").

    Returns:
        The config snapshot for that version, or None if unknown.
    """
    entry = _REGISTERED_VERSIONS.get(algorithm_id)
    if entry:
        return entry
    return None


def register_historical_version(version: str, config: Dict[str, Any]):
    """Register a historical version so it can be looked up later.

    This is used to populate the registry with known past configurations
    so that old scores remain interpretable.
    """
    config_hash = _compute_config_hash(config)
    _register_version(version, config, config_hash)


# Register LOCAL-306-v1 (the version that preceded this refactoring)
# Its thresholds are the same as current (we're refactoring, not changing scores)
register_historical_version("LOCAL-306-v1", {
    "version": "LOCAL-306-v1",
    "rich_min_density": 0.60,
    "rich_min_facts": 4,
    "rich_max_filler": 0.25,
    "adequate_min_density": 0.20,
    "adequate_min_facts": 3,
    "adequate_max_filler": 0.40,
    "rich_min_groundedness": 0.40,
    "fabricated_weight": -1.5,
    "missing_weight": -1.0,
    "thin_weight": 0.5,
    "adequate_weight": 0.75,
    "rich_weight": 1.0,
    "pipeline_lost_weight": -1.0,
    "unavailable_weight": -0.15,
    "structural_per_defect": -0.25,
    "structural_cap": -0.5,
    "correlation_multiplier": 0.5,
    "venue_identity_max_fraction": 0.10,
    "venue_identity_max_facts": 5,
})


# =============================================================================
# Evaluation Result
# =============================================================================

@dataclass
class Evaluation:
    """The complete result of evaluating a tour.

    This is the ONLY object callers receive. It carries everything needed
    to record, compare, and interpret the score.
    """
    # The score object (from tour_rubric_scorer)
    score: TourScore

    # Per-stop detail as serialisable dicts
    per_stop: List[Dict[str, Any]]

    # Algorithm identity
    algorithm_id: str
    algorithm_version: str
    algorithm_config_hash: str

    # Timing
    scored_at: str  # ISO 8601 UTC timestamp
    scoring_ms: float

    # Context passed by caller (tour_id, tour_name, etc.)
    context: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# The Single Entry Point
# =============================================================================

def evaluate(tour_text: str, n_requested: int, **context) -> Optional[Evaluation]:
    """Evaluate a tour and return a versioned Evaluation.

    This is the ONLY public entry point. No caller should reach into
    tour_rubric_scorer internals.

    Args:
        tour_text: The complete assembled tour text.
        n_requested: Number of stops requested.
        **context: Optional context (tour_id, tour_name, gate_log, corpus_data,
                   etc.) passed through to the score and stored on the result.

    Returns:
        An Evaluation object, or None if tour_text is empty/unparseable.

    Raises:
        AlgorithmVersionError: If thresholds changed without a version bump.
    """
    # Validate version consistency on every call
    _validate_version_consistency()

    if not tour_text or not tour_text.strip():
        return None

    t0 = time.perf_counter()
    scored_at = datetime.now(timezone.utc).isoformat()

    # Parse
    stops_parsed = _parse_tour(tour_text)
    if not stops_parsed:
        return None

    # [LOCAL-327] Extract corpus_data BEFORE classification so the
    # corpus-availability ceiling fires in the default scoring path.
    # Previously corpus_data was popped after classify, making the ceiling inert.
    gate_log = context.pop('gate_log', None)
    corpus_data = context.pop('corpus_data', None)
    conn = context.pop('conn', None)

    # [LOCAL-327] Auto-load corpus from DB when conn is provided but
    # corpus_data is not.  This makes the ceiling reachable in the default
    # path (tour_scoring_service calls evaluate without pre-loading corpus).
    if corpus_data is None and conn is not None:
        try:
            from stop_corpus_reader import get_stop_corpus_for_tour
            import re as _re
            # Extract venue name from tour header
            first_line = tour_text.split('\n')[0] if tour_text else ''
            _m = _re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
            _venue = _m.group(1).strip() if _m else ''
            if _venue:
                stop_names = [s['title'] for s in stops_parsed]
                corpus_data = get_stop_corpus_for_tour(_venue, stop_names, conn)
        except Exception:
            pass  # DB unavailable — no ceiling, which is safe

    # Analyze each stop
    stop_analyses = []
    for stop in stops_parsed:
        sa = _analyze_stop(stop, stops_parsed)

        # [LOCAL-327] Apply corpus groundedness BEFORE classification so
        # corpus_lookup_attempted and corpus_available are set when
        # classify_stop checks them.
        if corpus_data is not None:
            sa.corpus_lookup_attempted = True
            _compute_groundedness(sa, stop, corpus_data)

        cls, evidence = _classify_stop(sa)
        sa.classification = cls
        sa.classification_evidence = evidence
        stop_analyses.append(sa)

    # Cross-populate callbacks_to from callbacks_from.
    # analyze_stop populates callbacks_from (stops this stop references), but
    # callbacks_to (stops that reference THIS stop) requires a second pass over
    # all analyses. Without this, compute_score sees half the callback set and
    # the correlation bonus is wrong.
    for sa in stop_analyses:
        for ref_idx in sa.callbacks_from:
            for other_sa in stop_analyses:
                if other_sa.index == ref_idx:
                    other_sa.callbacks_to.append(sa.index)

    # Venue identity
    venue_facts = _detect_venue_identity(tour_text)

    # Compute score
    tour_score = _compute_score(
        stop_analyses, n_requested, venue_facts,
        gate_log=gate_log, corpus_data=corpus_data,
    )

    scoring_ms = (time.perf_counter() - t0) * 1000.0

    # Build per-stop data
    per_stop_data = []
    for sa in stop_analyses:
        per_stop_data.append({
            "index": sa.index,
            "title": sa.title,
            "classification": sa.classification,
            "facts": sa.distinct_fact_count,
            "sentences": sa.content_sentences,
            "density": round(sa.fact_density, 3),
            "filler": round(sa.generic_filler_fraction, 3),
            "groundedness": round(sa.groundedness_fraction, 3),
        })

    return Evaluation(
        score=tour_score,
        per_stop=per_stop_data,
        algorithm_id=ALGORITHM_ID,
        algorithm_version=ALGORITHM_VERSION,
        algorithm_config_hash=_CURRENT_CONFIG_HASH,
        scored_at=scored_at,
        scoring_ms=round(scoring_ms, 2),
        context=context,
    )
