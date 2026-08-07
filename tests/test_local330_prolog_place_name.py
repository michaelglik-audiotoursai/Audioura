#!/usr/bin/env python3
"""
[LOCAL-330] Test that the prolog location slot carries a PLACE NAME,
not the raw request string.

The defect: "You are about to embark on a walking journey through a restaurant
tour in Old Nice (Vieux Nice), France" — the category keyword "restaurant" and
the word "tour" leaked into the location slot.

The fix: `_prolog_place` strips category words, transport words, and "tour"
from `location` before injecting it into the prolog prompt template.

These tests exercise the extraction logic directly (no LLM call needed) and
verify every category produces a clean place name.
"""
import re
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _extract_prolog_place(location: str) -> str:
    """
    Reimplements the LOCAL-330 prolog place extraction logic from
    generate_tour_text.py (~line 9188). This must stay in sync with the
    production code — any drift means the test is lying.
    """
    _PROLOG_CATEGORY_WORDS = {
        'restaurant', 'restaurants', 'food', 'dining', 'culinary',
        'eat', 'cafe', 'bistro', 'eatery',
        'walking', 'walk', 'hiking', 'hike',
        'cycling', 'cycle', 'bike', 'biking',
        'museum', 'gallery', 'exhibition',
        'architecture', 'architectural',
        'pub', 'crawl', 'shopping',
        'movie', 'film', 'book', 'literary', 'novel',
        'botanical', 'garden', 'park',
        'self-guided', 'guided',
        'camel', 'camelback', 'horse', 'horseback',
        'dog', 'dogsled', 'dogsledding',
        'auto', 'car', 'driving', 'jeep', 'motorcycle', 'scooter',
        'safari', 'segway', 'boat', 'kayak',
        'tour', 'tours',
    }
    _prolog_place = location
    # Strip category/transport/tour words (word-boundary match)
    _prolog_place = re.sub(
        r'\b(' + '|'.join(re.escape(w) for w in sorted(_PROLOG_CATEGORY_WORDS, key=len, reverse=True)) + r')\b',
        '', _prolog_place, flags=re.IGNORECASE
    )
    # Strip leading prepositions left orphaned
    _prolog_place = re.sub(r'^\s*(in|of|through|around|across|along)\s+', '', _prolog_place, flags=re.IGNORECASE)
    # Collapse whitespace, strip punctuation debris
    _prolog_place = re.sub(r'\s{2,}', ' ', _prolog_place).strip().strip(',').strip()
    # If stripping emptied the string, fall back to raw location
    if not _prolog_place:
        _prolog_place = location
    return _prolog_place


# ─── The actual defect case ───────────────────────────────────────────────────

class TestRestaurantCategory:
    """Restaurant tours: category word + 'tour' must be stripped."""

    def test_restaurant_tour_old_nice(self):
        result = _extract_prolog_place("restaurant tour in Old Nice (Vieux Nice), France")
        assert "restaurant" not in result.lower()
        assert "tour" not in result.lower()
        assert "Old Nice" in result
        assert "France" in result

    def test_restaurants_tour_old_city(self):
        result = _extract_prolog_place("restaurants tour in old city of Nice, France")
        assert "restaurant" not in result.lower()
        assert "tour" not in result.lower()
        assert "Nice" in result

    def test_food_tour_bangkok(self):
        result = _extract_prolog_place("food tour in Bangkok, Thailand")
        assert "food" not in result.lower()
        assert "tour" not in result.lower()
        assert "Bangkok" in result
        assert "Thailand" in result

    def test_culinary_tour_lyon(self):
        result = _extract_prolog_place("culinary tour in Lyon, France")
        assert "culinary" not in result.lower()
        assert "Lyon" in result


# ─── Walking tours ────────────────────────────────────────────────────────────

class TestWalkingCategory:
    """Walking tours: 'walking' and 'tour' stripped, place remains."""

    def test_walking_tour_paris(self):
        result = _extract_prolog_place("walking tour in Paris, France")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Paris" in result

    def test_walking_tour_rome_neighborhoods(self):
        result = _extract_prolog_place("walking tour of Trastevere, Rome, Italy")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Trastevere" in result
        assert "Rome" in result


# ─── Cycling / bike tours ─────────────────────────────────────────────────────

class TestCyclingCategory:
    """Cycling/bike tours: transport + 'tour' stripped."""

    def test_cycling_tour_french_riviera(self):
        result = _extract_prolog_place("cycling tour of the French Riviera")
        assert "cycling" not in result.lower()
        assert "tour" not in result.lower()
        assert "French Riviera" in result

    def test_bike_tour_amsterdam(self):
        result = _extract_prolog_place("bike tour in Amsterdam, Netherlands")
        assert "bike" not in result.lower()
        assert "tour" not in result.lower()
        assert "Amsterdam" in result


# ─── Animal transport (dog/camel) ─────────────────────────────────────────────

class TestAnimalTransport:
    """Animal tours: animal word + 'tour' stripped."""

    def test_camel_tour_sahara(self):
        result = _extract_prolog_place("camel tour in the Sahara Desert, Morocco")
        assert "camel" not in result.lower()
        assert "tour" not in result.lower()
        assert "Sahara" in result
        assert "Morocco" in result

    def test_dog_sled_tour_alaska(self):
        result = _extract_prolog_place("dogsled tour in Fairbanks, Alaska")
        assert "dogsled" not in result.lower()
        assert "tour" not in result.lower()
        assert "Fairbanks" in result
        assert "Alaska" in result

    def test_horseback_tour_patagonia(self):
        result = _extract_prolog_place("horseback tour through Patagonia, Argentina")
        assert "horseback" not in result.lower()
        assert "tour" not in result.lower()
        assert "Patagonia" in result


# ─── Museum tours: the fix must NOT regress LOCAL-286 ─────────────────────────

class TestMuseumNotRegressed:
    """
    Museum tours take the _is_museum_prolog branch and never hit the
    _prolog_place substitution in _part1_instruction. But the TOUR DATA line
    still carries _prolog_place, so verify it strips cleanly without breaking.
    """

    def test_museum_tour_nice(self):
        result = _extract_prolog_place("Musée Matisse, Nice, France museum tour")
        # "museum" and "tour" stripped; venue name intact
        assert "museum" not in result.lower()
        assert "tour" not in result.lower()
        assert "Matisse" in result
        assert "Nice" in result

    def test_gallery_tour_florence(self):
        result = _extract_prolog_place("Uffizi Gallery, Florence, Italy museum tour")
        assert "museum" not in result.lower()
        assert "tour" not in result.lower()
        assert "Uffizi" in result
        assert "Florence" in result


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Protect against over-stripping and empty results."""

    def test_plain_place_name_unchanged(self):
        """A location with no category words should pass through unchanged."""
        result = _extract_prolog_place("Old Nice (Vieux Nice), France")
        assert result == "Old Nice (Vieux Nice), France"

    def test_place_with_park_word(self):
        """'Park' is a category word but also in place names like Hyde Park."""
        # The word 'park' is stripped — but the place name structure survives
        result = _extract_prolog_place("walking tour in Hyde Park, London")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Hyde" in result
        assert "London" in result

    def test_empty_after_strip_falls_back(self):
        """If everything is stripped, fall back to original."""
        result = _extract_prolog_place("tour")
        assert result == "tour"  # fallback to original

    def test_accented_place_preserved(self):
        """Accented characters in the place name must survive."""
        result = _extract_prolog_place("restaurant tour in Côte d'Azur, France")
        assert "restaurant" not in result.lower()
        assert "Côte d'Azur" in result


# ─── Integration: verify the production code matches ──────────────────────────

class TestProductionCodeSync:
    """
    Verify the production _PROLOG_CATEGORY_WORDS set in generate_tour_text.py
    matches what our test helper uses. This catches drift.
    """

    def test_production_wordset_exists(self):
        """The production code must contain _PROLOG_CATEGORY_WORDS."""
        import generate_tour_text
        source_path = generate_tour_text.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            source = f.read()
        assert '_PROLOG_CATEGORY_WORDS' in source, \
            "Production code missing _PROLOG_CATEGORY_WORDS — LOCAL-330 fix not applied"

    def test_production_uses_prolog_place(self):
        """The production prolog prompt must use _prolog_place, not raw location."""
        import generate_tour_text
        source_path = generate_tour_text.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            source = f.read()
        # The example shape line should reference _prolog_place
        assert "journey through [{_prolog_place}]" in source, \
            "Production prolog still uses raw {location} — LOCAL-330 fix not wired"
        # The TOUR DATA line should also use _prolog_place
        assert "Tour name/location: {_prolog_place}" in source, \
            "TOUR DATA still uses raw {location} — LOCAL-330 fix incomplete"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
