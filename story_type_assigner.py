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


def assign_story_types(poi_list: List[dict], tour_category: str = "museum", persona=None) -> List[dict]:
    """Assign a story_type to each POI, ensuring no adjacent duplicates.

    Args:
        poi_list: List of POI dicts (each must have at least 'name').
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.
        persona: Optional UserPersona enum. If given, biases selection toward
                 persona's preferred story types (weighted random, no consecutive repeats).

    Returns:
        The same list with 'story_type' key added to each POI dict.
        Without persona: deterministic round-robin (same input → same output).
        With persona: weighted selection (biased but varied).
    """
    if not poi_list:
        return poi_list

    if persona is not None:
        # Weighted selection mode — use persona weights
        import random
        from onboarding_preference import persona_to_story_type_weights
        weights = persona_to_story_type_weights(persona)
        types = list(weights.keys())
        type_weights = [weights[t] for t in types]

        # Use a seeded RNG for reproducibility per tour (seeded on category + persona)
        rng = random.Random(f"{tour_category}_{persona.value}_{len(poi_list)}")
        last_type = None

        for poi in poi_list:
            # Weighted selection, excluding last_type to prevent repeats
            available_types = [t for t in types if t != last_type]
            available_weights = [weights[t] for t in available_types]
            # Normalize
            total = sum(available_weights)
            norm_weights = [w / total for w in available_weights]

            chosen = rng.choices(available_types, weights=norm_weights, k=1)[0]
            poi["story_type"] = chosen
            last_type = chosen

        return poi_list

    # Original deterministic round-robin mode (unchanged behavior)
    pool = _CATEGORY_POOLS.get(tour_category.lower(), _DEFAULT_POOL)
    pool_len = len(pool)

    last_type = None
    pool_idx = 0

    for poi in poi_list:
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
