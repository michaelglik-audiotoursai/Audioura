#!/usr/bin/env python3
"""test_local608_d612r3_contained_provenance.py — LOCAL-608 item 2 / D612 r3.

Venue-coherence drift (check 11) is about WHERE a stop is, not what its prose
names. In an address-contained tour — every stop at the venue's own address —
a stop that IS at that address has not drifted, however many other museums its
provenance names ("donated to the Fogg", "lent by the Museum of Fine Arts").
Harvard Art Museums was refused 4/6 on exactly those provenance mentions.

This backports subscribed 5943569: in a contained tour, a stop whose own
`Address:` matches the tour's address set is exempt from the foreign-venue drift
count.

RED on 354da34: the contained Harvard-style tour FAILS venue coherence because a
majority of stops name foreign museums.
GREEN after the port: it PASSES, because every stop is at the venue address.

Run: python3 -m pytest test_local608_d612r3_contained_provenance.py -q
"""
import os
import sys
import subprocess
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _make_contained_tour(venue_name: str, address: str, stop_descriptions: list) -> str:
    """A tour where EVERY stop carries the SAME venue address (address-contained)."""
    lines = [
        f"Audio Guided Tour: {venue_name} - Museum Tour",
        "Tour-Category: museum",
        f"Location: {venue_name}",
        "",
    ]
    for i, desc in enumerate(stop_descriptions, 1):
        lines.append(f"Stop {i}: Gallery {i}")
        lines.append(f"Address: {address}")
        lines.append("Coordinates: 42.374, -71.114")
        lines.append(f"Orientation: Welcome to gallery {i}.")
        lines.append("")
        lines.append(desc)
        lines.append("")
        lines.append("Directions: Continue to the next gallery.")
        lines.append("")
    return "\n".join(lines)


def _run_qa(tour_text: str) -> tuple:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(tour_text)
        f.flush()
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "content_qa_runner.py", tmp_path],
            capture_output=True, text=True, cwd=_ROOT)
        return result.returncode, result.stdout + result.stderr
    finally:
        os.unlink(tmp_path)


_HARVARD_ADDR = "32 Quincy Street, Cambridge, Massachusetts"


def test_contained_tour_with_provenance_mentions_passes():
    """Harvard case: every stop at the Harvard address, but a majority of stops
    name OTHER museums as provenance. Must PASS — the stops have not drifted.

    The named venues share no words with 'Harvard Art Museums, Cambridge, MA',
    match the drift pattern, and carry distinctive tokens, so on 354da34 this is
    counted as 4/6 drift and FAILS (Harvard's exact refusal)."""
    stops = [
        "The Rijksmuseum Amsterdam lent this canvas for a decade before it returned.",
        "A companion panel hangs in the Prado Museum far across the ocean today.",
        "The Uffizi Gallery once catalogued this very drawing in its archives.",
        "The Hermitage Museum displayed the bronze during its long restoration abroad.",
        "The Rodin Museum keeps the plaster study that preceded this final cast.",
        "This gallery gathers the works described above under one roof.",
    ]
    tour = _make_contained_tour("Harvard Art Museums, Cambridge, MA", _HARVARD_ADDR, stops)
    _, output = _run_qa(tour)
    assert "PASS: Venue coherence" in output, f"Expected PASS (contained), got:\n{output}"


def test_non_contained_drift_still_fails():
    """Guard: when stops carry DIFFERENT addresses (not contained) and a majority
    name a foreign venue, the drift check still fails."""
    venue = "Musee Matisse, Nice"
    lines = [
        f"Audio Guided Tour: {venue} - Museum Tour",
        "Tour-Category: museum",
        f"Location: {venue}",
        "",
    ]
    # Each stop at a DIFFERENT address -> not address-contained.
    addrs = [
        "1 Rue Alpha, Nice", "2 Rue Beta, Paris", "3 Rue Gamma, Lyon",
        "4 Rue Delta, Marseille", "5 Rue Epsilon, Lille", "6 Rue Zeta, Rennes",
    ]
    descs = [
        "The British Museum glass court greets millions of visitors each year.",
        "Inside the British Museum the Rosetta Stone draws enormous crowds daily.",
        "The British Museum Egyptian wing contains royal sarcophagi from Thebes.",
        "Greek sculptures in the British Museum include the Elgin Marbles collection.",
        "The British Museum acquired this piece during colonial campaigns abroad.",
        "Matisse's early work is shown in this final gallery.",
    ]
    for i, (a, d) in enumerate(zip(addrs, descs), 1):
        lines += [f"Stop {i}: Room {i}", f"Address: {a}", "Coordinates: 43.7, 7.2",
                  f"Orientation: Welcome to room {i}.", "", d, "",
                  "Directions: Continue.", ""]
    _, output = _run_qa("\n".join(lines))
    assert "FAIL: Venue coherence" in output, f"Expected FAIL (not contained), got:\n{output}"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
