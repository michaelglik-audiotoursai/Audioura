"""
Story Type Assigner — assigns a narrative story_type to each POI in a tour.
============================================================================
Ensures no two consecutive stops share the same type (variety).
Uses per-category weighting (round-robin from a weighted pool).
No API calls. Deterministic. Fast (< 0.1s for any list size).
"""
from typing import List, Dict


# Per-category type pools (weighted by repetition count in the pool list).
# More occurrences = higher weight in the round-robin assignment.
_CATEGORY_POOLS: Dict[str, List[str]] = {
    "museum": ["art", "history", "anecdote", "art", "history", "art"],
    "walking": ["culture", "history", "architecture", "culture", "history", "anecdote"],
    "restaurant": ["anecdote", "culture", "anecdote", "culture", "history", "nature"],
    "book": ["history", "anecdote", "culture", "history", "anecdote", "art"],
}

# Default pool if category not recognized
_DEFAULT_POOL = ["history", "anecdote", "architecture", "culture", "nature", "art"]


def assign_story_types(poi_list: List[dict], tour_category: str = "museum") -> List[dict]:
    """Assign a story_type to each POI, ensuring no adjacent duplicates.

    Args:
        poi_list: List of POI dicts (each must have at least 'name').
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.

    Returns:
        The same list with 'story_type' key added to each POI dict.
        Assignment is deterministic (same input → same output).
    """
    if not poi_list:
        return poi_list

    pool = _CATEGORY_POOLS.get(tour_category.lower(), _DEFAULT_POOL)
    pool_len = len(pool)

    last_type = None
    pool_idx = 0

    for poi in poi_list:
        # Pick next type from pool, skipping if it would duplicate the previous
        candidate = pool[pool_idx % pool_len]
        attempts = 0
        while candidate == last_type and attempts < pool_len:
            pool_idx += 1
            candidate = pool[pool_idx % pool_len]
            attempts += 1

        poi["story_type"] = candidate
        last_type = candidate
        pool_idx += 1

    return poi_list
