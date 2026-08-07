#!/usr/bin/env python3
"""
[LOCAL-330] Test that the prolog location slot carries a PLACE NAME,
not the raw request string.

The defect: "You are about to embark on a walking journey through a restaurant
tour in Old Nice (Vieux Nice), France" — the category keyword "restaurant" and
the word "tour" leaked into the location slot.

The fix: module-level `_prolog_place()` in generate_tour_text.py strips a
leading "<category> tour (in|of|...)" prefix. If no prefix matches, the
location passes through unchanged — protecting real place names like
Hyde Park, Central Park, Boat Quay, Garden District.

Tests import the PRODUCTION function directly (LOCAL-324 pattern). No
reimplementation — if production breaks, these tests break.
"""
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import _prolog_place


# ─── The actual defect case ───────────────────────────────────────────────────

class TestRestaurantCategory:
    """Restaurant tours: category word + 'tour' must be stripped."""

    def test_restaurant_tour_old_nice(self):
        result = _prolog_place("restaurant tour in Old Nice (Vieux Nice), France")
        assert "restaurant" not in result.lower()
        assert "tour" not in result.lower()
        assert "Old Nice" in result
        assert "France" in result

    def test_restaurants_tour_old_city(self):
        result = _prolog_place("restaurants tour in old city of Nice, France")
        assert "restaurant" not in result.lower()
        assert "tour" not in result.lower()
        assert "Nice" in result

    def test_food_tour_bangkok(self):
        result = _prolog_place("food tour in Bangkok, Thailand")
        assert "food" not in result.lower()
        assert "tour" not in result.lower()
        assert "Bangkok" in result
        assert "Thailand" in result

    def test_culinary_tour_lyon(self):
        result = _prolog_place("culinary tour in Lyon, France")
        assert "culinary" not in result.lower()
        assert "Lyon" in result


# ─── Walking tours ────────────────────────────────────────────────────────────

class TestWalkingCategory:
    """Walking tours: 'walking' and 'tour' stripped, place remains."""

    def test_walking_tour_paris(self):
        result = _prolog_place("walking tour in Paris, France")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Paris" in result

    def test_walking_tour_rome_neighborhoods(self):
        result = _prolog_place("walking tour of Trastevere, Rome, Italy")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Trastevere" in result
        assert "Rome" in result


# ─── Cycling / bike tours ─────────────────────────────────────────────────────

class TestCyclingCategory:
    """Cycling/bike tours: transport + 'tour' stripped."""

    def test_cycling_tour_french_riviera(self):
        result = _prolog_place("cycling tour of the French Riviera")
        assert "cycling" not in result.lower()
        assert "tour" not in result.lower()
        assert "French Riviera" in result

    def test_bike_tour_amsterdam(self):
        result = _prolog_place("bike tour in Amsterdam, Netherlands")
        assert "bike" not in result.lower()
        assert "tour" not in result.lower()
        assert "Amsterdam" in result


# ─── Animal transport (dog/camel) ─────────────────────────────────────────────

class TestAnimalTransport:
    """Animal tours: animal word + 'tour' stripped."""

    def test_camel_tour_sahara(self):
        result = _prolog_place("camel tour in the Sahara Desert, Morocco")
        assert "camel" not in result.lower()
        assert "tour" not in result.lower()
        assert "Sahara" in result
        assert "Morocco" in result

    def test_dog_sled_tour_alaska(self):
        result = _prolog_place("dogsled tour in Fairbanks, Alaska")
        assert "dogsled" not in result.lower()
        assert "tour" not in result.lower()
        assert "Fairbanks" in result
        assert "Alaska" in result

    def test_horseback_tour_patagonia(self):
        result = _prolog_place("horseback tour through Patagonia, Argentina")
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
        result = _prolog_place("Musée Matisse, Nice, France museum tour")
        # "museum" and "tour" stripped; venue name intact
        assert "museum" not in result.lower()
        assert "tour" not in result.lower()
        assert "Matisse" in result
        assert "Nice" in result

    def test_gallery_tour_florence(self):
        result = _prolog_place("Uffizi Gallery, Florence, Italy museum tour")
        assert "museum" not in result.lower()
        assert "tour" not in result.lower()
        assert "Uffizi" in result
        assert "Florence" in result


# ─── LEAD-mandated: place names containing category words UNCHANGED ───────────

class TestPlaceNamesUnchanged:
    """
    LEAD review 2026-08-06: these six inputs must return UNCHANGED.
    They have no "<category> tour in/of" prefix, so the function must
    not touch them.
    """

    def test_hyde_park_london(self):
        result = _prolog_place("Hyde Park, London")
        assert result == "Hyde Park, London"

    def test_central_park_new_york(self):
        result = _prolog_place("Central Park, New York")
        assert result == "Central Park, New York"

    def test_golden_gate_park_san_francisco(self):
        result = _prolog_place("Golden Gate Park, San Francisco")
        assert result == "Golden Gate Park, San Francisco"

    def test_garden_district_new_orleans(self):
        result = _prolog_place("Garden District, New Orleans")
        assert result == "Garden District, New Orleans"

    def test_boat_quay_singapore(self):
        result = _prolog_place("Boat Quay, Singapore")
        assert result == "Boat Quay, Singapore"

    def test_car_free_zermatt(self):
        result = _prolog_place("Car-free Zermatt, Switzerland")
        assert result == "Car-free Zermatt, Switzerland"


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Protect against over-stripping and empty results."""

    def test_plain_place_name_unchanged(self):
        """A location with no category words should pass through unchanged."""
        result = _prolog_place("Old Nice (Vieux Nice), France")
        assert result == "Old Nice (Vieux Nice), France"

    def test_empty_after_strip_falls_back(self):
        """If everything is stripped, fall back to original."""
        result = _prolog_place("tour")
        assert result == "tour"  # fallback to original

    def test_accented_place_preserved(self):
        """Accented characters in the place name must survive."""
        result = _prolog_place("restaurant tour in Côte d'Azur, France")
        assert "restaurant" not in result.lower()
        assert "Côte d'Azur" in result

    def test_self_guided_tour(self):
        """Self-guided prefix is also stripped."""
        result = _prolog_place("self-guided walking tour in Edinburgh, Scotland")
        assert "self-guided" not in result.lower()
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Edinburgh" in result

    def test_walking_tour_hyde_park(self):
        """A walking tour OF Hyde Park — prefix stripped, Park retained."""
        result = _prolog_place("walking tour in Hyde Park, London")
        assert "walking" not in result.lower()
        assert "tour" not in result.lower()
        assert "Hyde Park" in result
        assert "London" in result

    def test_tours_france_unchanged(self):
        """Tours (the city) must not be stripped."""
        assert _prolog_place("Tours, France") == "Tours, France"

    def test_tour_eiffel_unchanged(self):
        """Tour Eiffel must not be stripped."""
        assert _prolog_place("Tour Eiffel, Paris") == "Tour Eiffel, Paris"

    def test_museum_island_berlin_unchanged(self):
        """Museum Island — category word in place name, no 'tour' keyword."""
        assert _prolog_place("Museum Island, Berlin") == "Museum Island, Berlin"

    def test_safari_park_nairobi_unchanged(self):
        """Safari Park — category word in place name, no 'tour' keyword."""
        assert _prolog_place("Safari Park, Nairobi") == "Safari Park, Nairobi"


# ─── LEAD bounce 2: multi-word categories (the list-free approach) ────────────

class TestMultiWordCategories:
    """
    LEAD bounce 2026-08-06: multi-word categories must strip correctly.
    These failed with the single-word category alternation list.
    The fix anchors on 'tour' + preposition, not the category word.
    """

    def test_dog_sledding_tour(self):
        result = _prolog_place("dog sledding tour in Big Lake, Alaska")
        assert result == "Big Lake, Alaska"

    def test_horse_riding_tour(self):
        result = _prolog_place("horse riding tour of Patagonia")
        assert result == "Patagonia"

    def test_hot_air_balloon_tour(self):
        result = _prolog_place("hot air balloon tour of Cappadocia")
        assert result == "Cappadocia"

    def test_food_and_wine_tour(self):
        result = _prolog_place("food and wine tour of Tuscany")
        assert result == "Tuscany"

    def test_street_art_tour(self):
        result = _prolog_place("street art tour of Lisbon")
        assert result == "Lisbon"

    def test_camelback_riding_tour_with_dash_suffix(self):
        """Michael's real string: prefix + dash suffix."""
        result = _prolog_place(
            "Camelback riding tour in Abu Dhabi desert, UAE - museum Tour"
        )
        assert result == "Abu Dhabi desert, UAE"

    def test_dog_ridding_tour_comma_separator(self):
        """Michael's real string: comma after 'tour' as separator."""
        result = _prolog_place(
            "dog ridding tour, Big Lake, AK - Dog Sledding Tour"
        )
        assert result == "Big Lake, AK"

    def test_camel_tour_with_dash_suffix(self):
        """Michael's real string: 'tour in a ...' with preposition chain."""
        result = _prolog_place(
            "Camel tour in a desert of Abu Dhabi, UAE - museum Tour"
        )
        assert "Abu Dhabi" in result
        assert "museum" not in result.lower()


# ─── Integration: verify the production code wiring ───────────────────────────

class TestProductionCodeWiring:
    """
    Verify the production prolog prompt uses _prolog_place_name (the result
    of calling _prolog_place), not raw location.
    """

    def test_production_uses_prolog_place_name(self):
        """The production prolog prompt must use _prolog_place_name, not raw location."""
        import generate_tour_text
        source_path = generate_tour_text.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            source = f.read()
        # The example shape line should reference _prolog_place_name
        assert "journey through [{_prolog_place_name}]" in source, \
            "Production prolog still uses raw {location} — LOCAL-330 fix not wired"
        # The TOUR DATA line should also use _prolog_place_name
        assert "Tour name/location: {_prolog_place_name}" in source, \
            "TOUR DATA still uses raw {location} — LOCAL-330 fix incomplete"

    def test_module_level_function_exists(self):
        """The _prolog_place function must be importable from generate_tour_text."""
        from generate_tour_text import _prolog_place as fn
        assert callable(fn)


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
