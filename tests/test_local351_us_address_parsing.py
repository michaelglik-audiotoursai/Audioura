"""LOCAL-351: US address format parsing in area_resolver.

Tests that:
1. US-format addresses (City, ST ZIP, Country) parse correctly
2. The structural signal is a 2-letter uppercase code + 5-digit ZIP
3. Nice variants parse UNCHANGED (no regression)
4. Existing patterns (Beacon Hill, Yellowstone) unchanged
5. Tests FAIL on the unfixed code (D242 compliance)

The defect: "biking tour in Norwood, MA 02062, USA" was parsed as
  neighborhood='Norwood', city='MA 02062, USA'
instead of city='Norwood' — because the parser assumed City,Country format
which is true of Nice,France and false of every US address.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from area_resolver import _parse_location


class TestUSAddressParsing:
    """US-format addresses: City, ST ZIP, Country and variants."""

    def test_norwood_ma_02062_usa(self):
        """The exact failing input from the bug report."""
        n, c = _parse_location("biking tour in Norwood, MA 02062, USA")
        assert n == "" and c == "Norwood", f"got ({n!r}, {c!r})"

    def test_norwood_raw(self):
        """Without tour-type prefix."""
        n, c = _parse_location("Norwood, MA 02062, USA")
        assert n == "" and c == "Norwood", f"got ({n!r}, {c!r})"

    def test_norwood_no_country(self):
        """City, ST ZIP — no country suffix."""
        n, c = _parse_location("Norwood, MA 02062")
        assert n == "" and c == "Norwood", f"got ({n!r}, {c!r})"

    def test_norwood_state_country_no_zip(self):
        """City, ST, Country — state code without ZIP but with country."""
        n, c = _parse_location("Norwood, MA, USA")
        assert n == "" and c == "Norwood", f"got ({n!r}, {c!r})"

    def test_cambridge_ma(self):
        """Another MA city with ZIP."""
        n, c = _parse_location("Cambridge, MA 02139, USA")
        assert n == "" and c == "Cambridge", f"got ({n!r}, {c!r})"

    def test_austin_tx(self):
        """Texas city."""
        n, c = _parse_location("Austin, TX 78701, USA")
        assert n == "" and c == "Austin", f"got ({n!r}, {c!r})"

    def test_portland_or_no_country(self):
        """Oregon city with ZIP, no country."""
        n, c = _parse_location("Portland, OR 97201")
        assert n == "" and c == "Portland", f"got ({n!r}, {c!r})"

    def test_san_francisco_ca(self):
        """Multi-word city name."""
        n, c = _parse_location("San Francisco, CA 94102, USA")
        assert n == "" and c == "San Francisco", f"got ({n!r}, {c!r})"

    def test_zip_plus_four(self):
        """ZIP+4 format (NNNNN-NNNN)."""
        n, c = _parse_location("Boston, MA 02101-1234, USA")
        assert n == "" and c == "Boston", f"got ({n!r}, {c!r})"

    def test_biking_tour_prefix_stripped(self):
        """Tour-type words stripped before US detection."""
        n, c = _parse_location("biking tour in Cambridge, MA 02139")
        assert n == "" and c == "Cambridge", f"got ({n!r}, {c!r})"

    def test_walking_tour_us(self):
        """Walking tour in US city."""
        n, c = _parse_location("walking tour in Boston, MA 02101, USA")
        assert n == "" and c == "Boston", f"got ({n!r}, {c!r})"


class TestStructuralSignal:
    """The 2-letter + 5-digit pattern is the structural signal, not a hardcoded list."""

    def test_zip_cannot_be_city(self):
        """'MA 02062' cannot be a city name — ZIP is definitive."""
        # This is the core D236 test: structure, not a place-name list
        n, c = _parse_location("Norwood, MA 02062, USA")
        assert "02062" not in c, f"ZIP code leaked into city: {c!r}"
        assert c == "Norwood"

    def test_fictional_state_with_zip(self):
        """Even a non-real state code + ZIP triggers US detection (structural)."""
        n, c = _parse_location("Smalltown, ZZ 99999, USA")
        assert n == "" and c == "Smalltown", f"got ({n!r}, {c!r})"

    def test_bare_two_letter_no_zip_no_country_not_triggered(self):
        """Bare 2-letter code WITHOUT zip and WITHOUT country is ambiguous — no US detection.
        This preserves 'Big Lake, AK' → ('Big Lake', 'AK') existing behavior."""
        n, c = _parse_location("Big Lake, AK")
        assert n == "Big Lake" and c == "AK", f"got ({n!r}, {c!r})"


class TestNiceUnchanged:
    """Nice variants must parse EXACTLY as before (no regression)."""

    def test_nice_france(self):
        n, c = _parse_location("Nice, France")
        assert n == "Nice" and c == "France", f"got ({n!r}, {c!r})"

    def test_old_nice_vieux_nice_france(self):
        n, c = _parse_location("Old Nice (Vieux Nice), France")
        assert n == "Old Nice (Vieux Nice)" and c == "France", f"got ({n!r}, {c!r})"

    def test_museum_nice_france(self):
        """3-part with short country code: museum is neighborhood, Nice is city."""
        n, c = _parse_location("Musee des Arts Asiatiques (Asian Art Museum), Nice, France")
        assert n == "Musee des Arts Asiatiques (Asian Art Museum)" and c == "Nice", \
            f"got ({n!r}, {c!r})"

    def test_walking_tour_nice(self):
        n, c = _parse_location("walking tour in Nice, France")
        assert n == "Nice" and c == "France", f"got ({n!r}, {c!r})"

    def test_restaurant_tour_old_nice(self):
        """Restaurant tour prefix partially survives (not a transport word)."""
        n, c = _parse_location("restaurant tour in Old Nice (Vieux Nice), France")
        # "restaurant" is not a transport word, so it remains
        assert c == "France", f"city should be France, got {c!r}"
        assert "Old Nice" in n, f"neighborhood should contain Old Nice, got {n!r}"


class TestExistingPatternsUnchanged:
    """Patterns from LOCAL-46 and LOCAL-3 must not regress."""

    def test_beacon_hill_boston(self):
        n, c = _parse_location("Beacon Hill, Boston")
        assert n == "Beacon Hill" and c == "Boston", f"got ({n!r}, {c!r})"

    def test_french_riviera_biking(self):
        n, c = _parse_location("French Riviera biking tour, France")
        assert n == "French Riviera" and c == "France", f"got ({n!r}, {c!r})"

    def test_yellowstone_wyoming(self):
        n, c = _parse_location("horseback tour of Yellowstone, Wyoming")
        assert n == "Yellowstone" and c == "Wyoming", f"got ({n!r}, {c!r})"

    def test_provence_france(self):
        n, c = _parse_location("cycling tour in Provence, France")
        assert n == "Provence" and c == "France", f"got ({n!r}, {c!r})"

    def test_single_city(self):
        """Single city with no comma."""
        n, c = _parse_location("Boston")
        assert n == "" and c == "Boston", f"got ({n!r}, {c!r})"

    def test_musee_chagall_nice(self):
        """Accent-bearing name (D253: fold \u2018 as well as accents)."""
        n, c = _parse_location("Mus\u00e9e National Marc Chagall, Nice")
        assert n == "Mus\u00e9e National Marc Chagall" and c == "Nice", f"got ({n!r}, {c!r})"


class TestD242Compliance:
    """These tests MUST fail against the unfixed code (D242).

    The unfixed code returns neighborhood='Norwood', city='MA 02062, USA'.
    Our assertions require city='Norwood' — they would fail before the fix.
    """

    def test_unfixed_would_fail(self):
        """Core assertion that distinguishes fixed from unfixed code."""
        n, c = _parse_location("biking tour in Norwood, MA 02062, USA")
        # Unfixed: n='Norwood', c='MA 02062, USA'
        # Fixed:   n='', c='Norwood'
        assert c == "Norwood", (
            f"D242: city should be 'Norwood', got {c!r}. "
            f"If city contains 'MA' or '02062', the fix is missing."
        )
        assert "MA" not in c
        assert "02062" not in c
