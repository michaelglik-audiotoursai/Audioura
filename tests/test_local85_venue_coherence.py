"""
test_local85_venue_coherence.py — Tests for the revised venue-coherence gate (LOCAL-85).

The old check 11 required ≥ len(stops)//3 stops to contain venue[:15] as a
literal substring.  This conflicted with LOCAL-47's repetition cap (max 2
occurrences) and penalized natural prose.

The new check fires only when a MAJORITY of stops reference a foreign venue —
genuine drift — rather than demanding a specific phrase be repeated.
"""
import re
import subprocess
import sys
import tempfile
import os
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_museum_tour(venue_name: str, stop_descriptions: list, category="museum") -> str:
    """Construct a minimal valid tour text for QA testing."""
    lines = [
        f"Audio Guided Tour: {venue_name} - Museum Tour",
        f"Tour-Category: {category}",
        f"Location: {venue_name}",
        "",
    ]
    for i, desc in enumerate(stop_descriptions, 1):
        lines.append(f"Stop {i}: Stop Title {i}")
        lines.append(f"Address: 123 Rue Test, Nice")
        lines.append(f"Coordinates: 43.7, 7.2")
        lines.append(f"Orientation: Welcome to stop {i}.")
        lines.append(f"")
        lines.append(desc)
        lines.append(f"")
        lines.append(f"Directions: Continue to the next exhibit.")
        lines.append("")
    return "\n".join(lines)


def _run_qa(tour_text: str) -> tuple:
    """Run content_qa_runner.py on text, return (exit_code, stdout)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(tour_text)
        f.flush()
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "content_qa_runner.py", tmp_path],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return result.returncode, result.stdout + result.stderr
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Tests: Good tours pass
# ---------------------------------------------------------------------------

class TestVenueCoherencePass:
    """Tours with natural writing about the correct venue should PASS."""

    def test_matisse_natural_prose_passes(self):
        """Musée Matisse tour using 'the museum' and 'Matisse' — no full venue
        string repeated — should pass the coherence gate."""
        stops = [
            "The collection opens with Matisse's early experiments in light and colour.",
            "This room shows how the museum preserves works from his Nice period.",
            "Matisse's paper cut-outs dominate this gallery space.",
            "The Fauvist palette is on full display in this corner of the museum.",
            "A bronze sculpture reveals Matisse's three-dimensional thinking.",
            "The museum's garden offers context for the pastoral scenes inside.",
            "Odalisques and patterned interiors reflect his North African influences.",
            "Late-period liturgical designs show Matisse at his most contemplative.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # Check 11 should pass (0 foreign venues)
        assert "PASS: Venue coherence" in output, f"Expected PASS, got:\n{output}"

    def test_asian_arts_no_venue_name_repeated_passes(self):
        """Asian Arts Museum tour that never writes 'Musée des Arts Asiatiques, Nice'
        verbatim but stays on topic."""
        stops = [
            "This Edo-period samurai armour is one of the finest in France.",
            "The jade Buddha radiates serenity in its alcove.",
            "Ganesh dances in cosmic rhythm across this bronze relief.",
            "Kannon extends compassion through a thousand delicate hands.",
            "Ulysses Grant's diplomatic gifts connect East and West.",
            "A Taoist priest's robe shimmers with celestial embroidery.",
            "The thousand-armed Kannon towers above the meditation hall.",
            "The Noh mask captures centuries of theatrical tradition.",
        ]
        tour = _make_museum_tour("Musée des Arts Asiatiques, Nice", stops)
        exit_code, output = _run_qa(tour)
        assert "PASS: Venue coherence" in output, f"Expected PASS, got:\n{output}"

    def test_single_foreign_mention_passes(self):
        """One stop mentioning a related foreign venue should not trip the gate."""
        stops = [
            "Matisse donated many works after seeing how the Musée du Louvre displayed them.",
            "This room shows the artist's evolution from dark to light.",
            "Matisse was influenced by North African patterns.",
            "Paper cut-outs dominate his late period.",
            "Bronze sculpture shows his spatial awareness.",
            "Garden views inspired many canvases.",
            "Matisse's final designs for a chapel are here.",
            "The collection spans fifty years of creative output.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # 1 stop with a foreign venue (Louvre) out of 8 — well under majority
        assert "PASS: Venue coherence" in output, f"Expected PASS, got:\n{output}"


# ---------------------------------------------------------------------------
# Tests: Drifted tours fail
# ---------------------------------------------------------------------------

class TestVenueCoherenceFail:
    """Tours that have genuinely drifted to a different venue should FAIL."""

    def test_majority_stops_reference_wrong_museum(self):
        """A 'Musée Matisse' tour where 5/8 stops describe the Musée Picasso
        should fail the coherence gate."""
        stops = [
            "The Musée Picasso houses a world-class cubist collection in its vaults.",
            "At the Musée Picasso, blue period paintings glow with melancholy light.",
            "The Musée Picasso courtyard offers views of the ancient quarter nearby.",
            "Guernica studies are a highlight of the Musée Picasso visit today.",
            "The Musée Picasso building itself was once a medieval salt warehouse.",
            "Matisse's early work is in this gallery.",
            "A bronze sculpture by Matisse sits in the corner.",
            "The garden outside has Matisse-inspired plantings.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # 5/8 stops reference Musée Picasso — that's majority drift
        assert "FAIL: Venue coherence" in output, f"Expected FAIL, got:\n{output}"

    def test_all_stops_reference_different_museum(self):
        """Complete drift — every stop is about the British Museum."""
        stops = [
            "The British Museum glass court greets millions of visitors each year.",
            "Inside the British Museum the Rosetta Stone draws enormous crowds daily.",
            "The British Museum Egyptian wing contains royal sarcophagi from Thebes.",
            "Greek sculptures in the British Museum include the Elgin Marbles collection.",
            "The British Museum acquired this piece during colonial campaigns abroad.",
            "Assyrian reliefs from Nineveh hang in the British Museum east gallery.",
            "The British Museum medieval foundations are visible in the lower basement.",
            "The British Museum reopened this wing after extensive restoration work.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        assert "FAIL: Venue coherence" in output, f"Expected FAIL, got:\n{output}"

    def test_exactly_half_does_not_fail(self):
        """4/8 stops with foreign venues = exactly half, should NOT fail
        (threshold is >50%, i.e. >4 needed for 8 stops)."""
        stops = [
            "The Musée Picasso across town has a fine cubist collection.",
            "Visitors sometimes confuse this with Galerie Lafayette exhibits.",
            "The Palais Longchamp in Marseille also has Fauvist works.",
            "Villa Ephrussi on Cap Ferrat shares a similar aesthetic.",
            "Matisse's early work shows his evolving palette.",
            "A bronze sculpture demonstrates his spatial thinking.",
            "Paper cut-outs from his later period fill this room.",
            "The garden frames his landscape paintings perfectly.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # 4/8 = exactly half, threshold is >4, so 4 passes
        assert "PASS: Venue coherence" in output, f"Expected PASS, got:\n{output}"


# ---------------------------------------------------------------------------
# Tests: Consistency with LOCAL-47 repetition cap
# ---------------------------------------------------------------------------

class TestConsistencyWithRepetitionCap:
    """The coherence gate and the repetition cap must be mutually satisfiable.
    LOCAL-47 caps venue-name occurrences at max 2.
    LOCAL-85's coherence gate requires ZERO venue-name mentions (negative test).
    Therefore: a tour with 0-2 venue mentions can satisfy BOTH rules simultaneously."""

    def test_zero_mentions_passes_both(self):
        """A tour with ZERO explicit venue-name mentions passes both rules."""
        stops = [
            "The collection opens with early experiments in colour.",
            "This room preserves works from the artist's Nice period.",
            "Paper cut-outs dominate this gallery space.",
            "The Fauvist palette is on full display here.",
            "A bronze sculpture reveals three-dimensional thinking.",
            "The garden offers context for the pastoral scenes inside.",
            "Odalisques and patterned interiors reflect North African influences.",
            "Late-period liturgical designs show the artist at his most contemplative.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # No foreign venues → passes coherence
        assert "PASS: Venue coherence" in output, f"Coherence should pass:\n{output}"
        # Zero mentions of full venue name → within cap of 2
        full_venue_count = tour.lower().count("musée matisse, nice")
        # Only appears in title/header lines, not in stop descriptions
        assert full_venue_count <= 2, f"Repetition cap violated: {full_venue_count}"

    def test_two_mentions_passes_both(self):
        """A tour with exactly 2 venue-name mentions passes both rules."""
        stops = [
            "Welcome to Musée Matisse, Nice — the artist's spiritual home.",
            "This gallery at Musée Matisse, Nice houses his best-known cut-outs.",
            "The Fauvist palette dominates this room.",
            "Bronze sculptures show his spatial awareness.",
            "Paper cut-outs reveal late-period mastery.",
            "Garden scenes connect interior and exterior.",
            "North African influences appear throughout.",
            "Late liturgical works complete the journey.",
        ]
        tour = _make_museum_tour("Musée Matisse, Nice", stops)
        exit_code, output = _run_qa(tour)
        # No foreign venues → passes coherence
        assert "PASS: Venue coherence" in output, f"Coherence should pass:\n{output}"
        # Count in stop descriptions only
        stop_text = "\n".join(stops)
        cap_count = len(re.findall(r'musée matisse, nice', stop_text, re.IGNORECASE))
        assert cap_count <= 2, f"Repetition cap would be violated: {cap_count}"
