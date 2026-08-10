"""tests/test_local365_closed_exhibition_signal.py — LOCAL-365: Closed exhibition must fail, not become a tour.

Verifies:
1. generate_tour_text returns (None, None, (None, None)) for a closed exhibition —
   the hard-failure convention, not a fake tour.
2. _LAST_CLEAN_FAIL_EVIDENCE is populated with error_type='exhibition_closed',
   the exhibition title, closing date, and venue.
3. _LAST_GENERATION_COST records zero cost (no TTS, no LLM spend).
4. generate_tour_text_service.generate_tour_async sets job status='error' with
   a user-facing message containing the exhibition title and closing date.
5. No file is written to output_file on closed-exhibition path.
6. Open exhibitions are not blocked.
7. Unscoped venue tours are unchanged.

Every test imports and calls real production code. No inline re-implementation.
"""
import os
import sys
import tempfile
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures and helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_closed_checklist_result(title="Picasso, Miró, Dalí: Unbound",
                                   closing_date=None, venue="Museum of Fine Arts"):
    """Build a real ExhibitionChecklistResult that represents a closed show."""
    from exhibition_checklist import ExhibitionChecklistResult
    result = ExhibitionChecklistResult()
    result.is_closed = True
    result.exhibition_title = title
    result.closing_date = closing_date or (date.today() - timedelta(days=30))
    result.reason = f'Exhibition "{title}" closed on {result.closing_date}.'
    result.exhibition_url = "https://www.mfa.org/exhibition/picasso-miro-dali"
    result.path = 'checklist'
    return result


def _make_open_checklist_result(title="Impressionism Now", works=None):
    """Build a real ExhibitionChecklistResult that represents an open show with works."""
    from exhibition_checklist import ExhibitionChecklistResult
    result = ExhibitionChecklistResult()
    result.is_closed = False
    result.exhibition_title = title
    result.closing_date = date.today() + timedelta(days=60)
    result.works = works or [
        {"title": "Water Lilies"},
        {"title": "Impression, Sunrise"},
        {"title": "Dance at Le Moulin de la Galette"},
        {"title": "A Sunday Afternoon on the Island of La Grande Jatte"},
        {"title": "Starry Night Over the Rhône"},
    ]
    result.path = 'checklist'
    result.reason = f"Extracted {len(result.works)} works from exhibition page"
    return result


def _make_mock_intent(venue_name="Museum of Fine Arts", requirements="Picasso, Miró, Dalí: Unbound exhibition"):
    """Return a dict mimicking Phase 1 intent analysis for a museum-scoped request."""
    return {
        "venue_name": venue_name,
        "requirements": requirements,
        "poi_type": "exhibition",
        "location": "Boston, MA",
        "business_hours_relevant": False,
    }


def _make_mock_entity(official_url="https://www.mfa.org"):
    """Return a mock venue entity with an official_url."""
    entity = MagicMock()
    entity.official_url = official_url
    entity.name = "Museum of Fine Arts"
    return entity


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Set minimal environment for generate_tour_text to reach the exhibition branch."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    monkeypatch.setenv("STORIED_MODE", "true")
    monkeypatch.setenv("DISABLE_TOUR_CACHE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin:password123@localhost:5433/audiotours")


# ═══════════════════════════════════════════════════════════════════════════════
# Core: closed exhibition returns None (not fake tour text)
# ═══════════════════════════════════════════════════════════════════════════════

class TestClosedExhibitionReturnsNone:
    """A closed exhibition must produce a hard failure (None), not tour text."""

    def test_returns_none_tuple_on_closed_exhibition(self):
        """generate_tour_text must return (None, None, (None, None)) when exhibition is closed."""
        from generate_tour_text import generate_tour_text

        closed_result = _make_closed_checklist_result()
        mock_intent = _make_mock_intent()
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            result = generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                output_file=None,
                total_stops=8,
            )

        tour_text, output_file, coordinates = result
        assert tour_text is None, (
            f"Closed exhibition must return tour_text=None, got: {repr(tour_text)[:200]}"
        )
        assert output_file is None
        assert coordinates == (None, None)

    def test_no_output_file_written_on_closed_exhibition(self):
        """No file should be written when the exhibition is closed."""
        from generate_tour_text import generate_tour_text

        closed_result = _make_closed_checklist_result()
        mock_intent = _make_mock_intent()
        mock_entity = _make_mock_entity()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
            temp_path = tf.name

        try:
            with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
                 patch("venue_resolver.resolve_venue", return_value=mock_entity), \
                 patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

                result = generate_tour_text(
                    location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                    tour_type="museum",
                    output_file=temp_path,
                    total_stops=8,
                )

            # The file should either not exist or be empty (no tour content written)
            tour_text = result[0]
            assert tour_text is None
            # Output file should not have tour content
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    content = f.read()
                assert content == "" or not content, (
                    f"Output file should be empty for closed exhibition, got: {content[:200]}"
                )
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Evidence: _LAST_CLEAN_FAIL_EVIDENCE is populated correctly
# ═══════════════════════════════════════════════════════════════════════════════

class TestClosedExhibitionEvidence:
    """_LAST_CLEAN_FAIL_EVIDENCE must carry the exhibition details to the service layer."""

    def test_evidence_has_exhibition_closed_type(self):
        """error_type must be 'exhibition_closed'."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        closing = date(2025, 3, 9)
        closed_result = _make_closed_checklist_result(
            title="Picasso, Miró, Dalí: Unbound",
            closing_date=closing,
        )
        mock_intent = _make_mock_intent()
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                total_stops=8,
            )

        evidence = gtt._LAST_CLEAN_FAIL_EVIDENCE
        assert evidence.get("error_type") == "exhibition_closed", (
            f"Expected error_type='exhibition_closed', got: {evidence}"
        )

    def test_evidence_contains_exhibition_title(self):
        """The exhibition title must be in the evidence."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        closed_result = _make_closed_checklist_result(title="Art of the Ancient World")
        mock_intent = _make_mock_intent(requirements="Art of the Ancient World exhibition")
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            generate_tour_text(
                location="Art of the Ancient World exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                total_stops=8,
            )

        evidence = gtt._LAST_CLEAN_FAIL_EVIDENCE
        assert evidence.get("exhibition_title") == "Art of the Ancient World"

    def test_evidence_contains_closing_date(self):
        """The closing date must be in the evidence as a string."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        closing = date(2025, 3, 9)
        closed_result = _make_closed_checklist_result(closing_date=closing)
        mock_intent = _make_mock_intent()
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                total_stops=8,
            )

        evidence = gtt._LAST_CLEAN_FAIL_EVIDENCE
        assert "2025-03-09" in evidence.get("closing_date", ""), (
            f"Expected closing_date to contain '2025-03-09', got: {evidence.get('closing_date')}"
        )

    def test_evidence_contains_venue(self):
        """The venue name must be in the evidence."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        closed_result = _make_closed_checklist_result(venue="Museum of Fine Arts")
        mock_intent = _make_mock_intent(venue_name="Museum of Fine Arts")
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                total_stops=8,
            )

        evidence = gtt._LAST_CLEAN_FAIL_EVIDENCE
        assert "Museum of Fine Arts" in evidence.get("venue", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Cost: zero cost recorded for closed exhibitions
# ═══════════════════════════════════════════════════════════════════════════════

class TestClosedExhibitionZeroCost:
    """No LLM or TTS spend should be recorded for a closed exhibition."""

    def test_generation_cost_is_zero(self):
        """_LAST_GENERATION_COST must show zero for a closed exhibition."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        closed_result = _make_closed_checklist_result()
        mock_intent = _make_mock_intent()
        mock_entity = _make_mock_entity()

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=closed_result):

            generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at Museum of Fine Arts, Boston, MA",
                tour_type="museum",
                total_stops=8,
            )

        cost = gtt._LAST_GENERATION_COST
        assert cost["total_cost"] == 0.0
        assert cost["total_tokens"] == 0
        assert cost.get("cache_hit") is False
        # The old flag should NOT be present (it was the bug — downstream read it)
        assert "exhibition_closed" not in cost, (
            "exhibition_closed flag must NOT appear in _LAST_GENERATION_COST — "
            "nothing downstream reads it; the signal goes through _LAST_CLEAN_FAIL_EVIDENCE"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Service layer: error message reaches the user
# ═══════════════════════════════════════════════════════════════════════════════

class TestServiceLayerErrorMessage:
    """generate_tour_text_service must surface exhibition title and date in error."""

    def test_service_sets_error_status_with_exhibition_info(self):
        """When generate_tour_text returns None with exhibition_closed evidence,
        the service must set status='error' with title and date in the message."""
        import generate_tour_text as gtt

        # Pre-populate _LAST_CLEAN_FAIL_EVIDENCE as generate_tour_text would
        gtt._LAST_CLEAN_FAIL_EVIDENCE = {
            "error_type": "exhibition_closed",
            "exhibition_title": "Picasso, Miró, Dalí: Unbound",
            "closing_date": "2025-03-09",
            "venue": "Museum of Fine Arts",
            "reason": 'Exhibition "Picasso, Miró, Dalí: Unbound" closed on 2025-03-09.',
        }

        # Mock generate_tour_text to return None (as it now does for closed exhibitions)
        with patch("generate_tour_text_service.generate_tour_text", return_value=(None, None, (None, None))):
            from generate_tour_text_service import generate_tour_async, ACTIVE_JOBS

            job_id = "test-local365-svc"
            ACTIVE_JOBS.update(job_id, status="queued", progress="",
                               location="MFA, Boston, MA", tour_type="museum",
                               total_stops=8, created_at="2025-01-01T00:00:00")

            generate_tour_async(job_id, "MFA, Boston, MA", "museum", 8)

        job = ACTIVE_JOBS[job_id]
        assert job["status"] == "error", f"Expected status='error', got: {job['status']}"
        error_msg = job.get("error", "")
        assert "Picasso" in error_msg, (
            f"Error message must contain exhibition title, got: {error_msg}"
        )
        assert "2025-03-09" in error_msg, (
            f"Error message must contain closing date, got: {error_msg}"
        )

    def test_service_sets_exhibition_closed_error_type(self):
        """The job's error_type field must be 'exhibition_closed'."""
        import generate_tour_text as gtt

        gtt._LAST_CLEAN_FAIL_EVIDENCE = {
            "error_type": "exhibition_closed",
            "exhibition_title": "Impressionism Now",
            "closing_date": "2024-12-01",
            "venue": "Getty Center",
            "reason": 'Exhibition "Impressionism Now" closed on 2024-12-01.',
        }

        with patch("generate_tour_text_service.generate_tour_text", return_value=(None, None, (None, None))):
            from generate_tour_text_service import generate_tour_async, ACTIVE_JOBS

            job_id = "test-local365-type"
            ACTIVE_JOBS.update(job_id, status="queued", progress="",
                               location="Getty Center, LA", tour_type="museum",
                               total_stops=8, created_at="2025-01-01T00:00:00")

            generate_tour_async(job_id, "Getty Center, LA", "museum", 8)

        job = ACTIVE_JOBS[job_id]
        assert job.get("error_type") == "exhibition_closed", (
            f"Expected error_type='exhibition_closed', got: {job.get('error_type')}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Open exhibitions still work
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpenExhibitionUnaffected:
    """An exhibition that is currently open must NOT be blocked."""

    def test_open_exhibition_does_not_return_none(self):
        """An open exhibition with works should proceed past the closed check.

        We verify that generate_tour_text does NOT return None at the exhibition
        closed check. It will fail later (no real API key for enrichment), but
        the critical assertion is that it doesn't early-return with None due to
        the closed-exhibition logic.
        """
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        open_result = _make_open_checklist_result()
        mock_intent = _make_mock_intent(requirements="Impressionism Now exhibition")
        mock_entity = _make_mock_entity()

        # Clear evidence from prior tests
        gtt._LAST_CLEAN_FAIL_EVIDENCE = {}

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity), \
             patch("exhibition_checklist.find_exhibition_checklist", return_value=open_result):

            # The function will proceed past the closed-exhibition check.
            # It will eventually fail at a later stage (no real OpenAI key for
            # enrichment/spine), but _LAST_CLEAN_FAIL_EVIDENCE should NOT have
            # error_type='exhibition_closed'.
            try:
                generate_tour_text(
                    location="Impressionism Now at Museum of Fine Arts, Boston, MA",
                    tour_type="museum",
                    total_stops=5,
                )
            except Exception:
                pass  # Expected — downstream phases need real API keys

        # The key assertion: exhibition_closed should NOT be in evidence
        evidence = gtt._LAST_CLEAN_FAIL_EVIDENCE
        assert evidence.get("error_type") != "exhibition_closed", (
            f"Open exhibition must NOT trigger exhibition_closed evidence: {evidence}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Unscoped venue tours unchanged
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnscopedVenueUnchanged:
    """A plain venue tour (no exhibition name) must not trigger exhibition closed logic."""

    def test_palais_lascaris_not_affected(self):
        """Palais Lascaris, Nice, France — unscoped venue tour is untouched."""
        from generate_tour_text import generate_tour_text
        import generate_tour_text as gtt

        # An unscoped museum request: no requirements, poi_type = "museum exhibits"
        mock_intent = {
            "venue_name": "Palais Lascaris",
            "requirements": "",
            "poi_type": "museum exhibits",
            "location": "Nice, France",
            "business_hours_relevant": False,
        }
        mock_entity = _make_mock_entity(official_url="https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris")

        gtt._LAST_CLEAN_FAIL_EVIDENCE = {}

        with patch("generate_tour_text.analyze_tour_intent", return_value=mock_intent), \
             patch("venue_resolver.resolve_venue", return_value=mock_entity) as mock_rv, \
             patch("exhibition_checklist.find_exhibition_checklist") as mock_checklist:

            try:
                generate_tour_text(
                    location="Palais Lascaris, Nice, France",
                    tour_type="museum",
                    total_stops=8,
                )
            except Exception:
                pass  # Will fail at later stages — that's fine

        # find_exhibition_checklist should NOT be called for unscoped requests
        mock_checklist.assert_not_called(), (
            "find_exhibition_checklist must not be called for unscoped venue tours"
        )
        # Evidence should not contain exhibition_closed
        assert gtt._LAST_CLEAN_FAIL_EVIDENCE.get("error_type") != "exhibition_closed"
