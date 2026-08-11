"""tests/test_local418_date_as_work_rejection.py — LOCAL-418: Date ranges must not be works.

Verifies:
1. _is_date_like correctly identifies dates, date ranges, weekdays, months
2. _is_date_like does NOT falsely reject real artwork titles or artist names
3. plausibility_gate rejects 'Wednesday, September 16–Wednesday' as a title
4. plausibility_gate rejects 'October 7' as an artist
5. extract_works_from_exhibition_page rejects date-like titles at the source
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from exhibition_checklist import (
    _is_date_like,
    _work_entry_is_implausible,
    plausibility_gate,
    extract_works_from_exhibition_page,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _is_date_like
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsDateLike:
    """Date-like strings must be detected so they are never accepted as titles."""

    # ─── Must return True (dates/date-ranges/weekdays/months) ─────────────
    @pytest.mark.parametrize("text", [
        "Wednesday, September 16–Wednesday",      # The exact bug string
        "October 7",                               # The exact bug artist
        "Wednesday",
        "September",
        "March 2025",
        "January 15, 2025",
        "2024-10-05",
        "September 16",
        "Monday, October 7, 2026",
        "Wed",
        "Oct",
        "12 March 2024",
        "2025",
    ])
    def test_dates_are_detected(self, text):
        assert _is_date_like(text) is True, f"Expected True for date-like: '{text}'"

    # ─── Must return False (real titles, artists, not dates) ──────────────
    @pytest.mark.parametrize("text", [
        "Le Lézard aux plumes d'or",
        "Joan Miró",
        "Moses and Monotheism",
        "Au Soleil du Plafond",
        "The Persistence of Memory",
        "Guernica",
        "Pablo Picasso",
        "Salvador Dalí",
        "Juan Gris",
        "The Starry Night",
        "Self-Portrait with Cropped Hair",
        "Woman with a Hat",
        "May Stevens",                             # 'May' is a month but this is a name
    ])
    def test_non_dates_are_not_detected(self, text):
        assert _is_date_like(text) is False, f"Expected False for non-date: '{text}'"


# ═══════════════════════════════════════════════════════════════════════════════
# _work_entry_is_implausible — date checks
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkEntryImplausibleDates:
    """A work whose title is a date or whose artist is a date must be implausible."""

    def test_date_title_is_implausible(self):
        """The exact bug: 'Wednesday, September 16–Wednesday' as a title."""
        work = {'title': 'Wednesday, September 16–Wednesday', 'artist': 'October 7'}
        assert _work_entry_is_implausible(work) is True

    def test_date_artist_is_implausible(self):
        """'October 7' as an artist is implausible."""
        work = {'title': 'Some Real Title', 'artist': 'October 7'}
        assert _work_entry_is_implausible(work) is True

    def test_real_work_is_not_implausible(self):
        """A real artwork must NOT be flagged."""
        work = {'title': "Le Lézard aux plumes d'or", 'artist': 'Joan Miró'}
        assert _work_entry_is_implausible(work) is False


# ═══════════════════════════════════════════════════════════════════════════════
# plausibility_gate integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlausibilityGateRejectsDateWork:
    """The plausibility gate must reject the exact bug case."""

    def test_single_date_work_rejected(self):
        """A single date-as-work extraction must be discarded entirely."""
        works = [{'title': 'Wednesday, September 16–Wednesday', 'artist': 'October 7', 'date': '2026'}]
        result = plausibility_gate(works)
        assert result == [], (
            f"plausibility_gate should have rejected date-as-work, got: {result}"
        )

    def test_mixed_works_date_below_threshold(self):
        """One date-work among real works (below 50% threshold) is kept but flagged."""
        works = [
            {'title': "Le Lézard aux plumes d'or", 'artist': 'Joan Miró'},
            {'title': 'Moses and Monotheism', 'artist': 'Salvador Dalí'},
            {'title': 'Wednesday, September 16–Wednesday', 'artist': 'October 7'},
        ]
        # 1 out of 3 = 33% → below 50% threshold, keeps the list
        result = plausibility_gate(works)
        assert len(result) == 3  # gate keeps all when ratio < 50%


# ═══════════════════════════════════════════════════════════════════════════════
# extract_works_from_exhibition_page — date rejection at source
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractWorksRejectsDateAtSource:
    """The extractor must not emit date-like entries at all."""

    def test_date_line_not_extracted_as_work(self):
        """The date range 'Wednesday, September 16–Wednesday, October 7, 2026'
        must not appear in extracted works."""
        # Simulate just the problematic line as page content
        page_text = "Wednesday, September 16–Wednesday, October 7, 2026"
        works = extract_works_from_exhibition_page(page_text, [])
        assert len(works) == 0, (
            f"Date line should not produce works, got: {works}"
        )

    def test_real_structured_work_still_extracted(self):
        """A real structured work line must still be extracted normally."""
        page_text = "Pablo Picasso, Guernica, 1937"
        works = extract_works_from_exhibition_page(page_text, [])
        assert len(works) == 1
        # The disambiguation may swap title/artist but the work must be extracted
        combined = works[0].get('title', '') + ' ' + works[0].get('artist', '')
        assert 'Guernica' in combined or 'Picasso' in combined
