"""
LOCAL-357: Forced stops verification harness  +  LOCAL-525: user-chosen stops API.

The forced_stops ENGINE mechanism (LOCAL-357) is still tested here:
1. forced_stops parameter bypasses candidate generation (Phase 3A) and injects
   exact stops in order, while keeping downstream gates/corpus/enrichment intact.
2. The existence gate still applies to forced stops — a bogus stop fails it.
3. Normal generation (forced_stops=None) is completely unchanged.
4. Forced-stop tours are stamped with a banner and never cached.
5. Museum bounds as properties (D258): 8-stop 75.0, 4-stop 81.2.

LOCAL-525 CHANGES THE API-LAYER DECISION. This file originally asserted the HTTP
API must NOT expose forced_stops (it was a test harness). That assertion has been
REPLACED — not deleted — by TestUserChosenStopsAPIContract, which encodes the new
decision: a validated, ordered stop list IS accepted on the /generate endpoint and
forwarded to the engine, malformed input is rejected with a clear message, and
omitting 'stops' behaves exactly as before. The class docstring records why.
"""
import os
import sys
import re
import pytest
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestForcedStopsParameterExists:
    """The forced_stops parameter must be accepted by generate_tour_text."""

    def test_parameter_accepted_in_signature(self):
        """generate_tour_text must accept forced_stops keyword argument."""
        import inspect
        from generate_tour_text import generate_tour_text
        sig = inspect.signature(generate_tour_text)
        assert 'forced_stops' in sig.parameters, (
            "generate_tour_text() must accept 'forced_stops' parameter (LOCAL-357)"
        )

    def test_parameter_default_is_none(self):
        """forced_stops must default to None (no change to normal path)."""
        import inspect
        from generate_tour_text import generate_tour_text
        sig = inspect.signature(generate_tour_text)
        param = sig.parameters['forced_stops']
        assert param.default is None, (
            f"forced_stops default must be None, got {param.default!r}"
        )


class TestForcedStopsInjection:
    """Forced stops bypass Phase 3A and appear in poi_list unchanged."""

    def test_forced_stops_bypass_phase3a(self, capsys):
        """When forced_stops is provided, Phase 3A GPT call is skipped."""
        # We can't run the full pipeline (no API key), but we CAN verify
        # the injection logic by checking the function's early behaviour.
        # The function will fail later (no OPENAI_API_KEY), but the forced
        # stops injection and Phase 3A skip happen BEFORE any API call.
        from generate_tour_text import generate_tour_text

        # Set required env vars for the gate to run
        os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
        os.environ['DISABLE_TOUR_CACHE'] = '1'

        # Without an API key, the function will fail at Phase 1 (intent analysis)
        # BUT with forced_stops, Phase 3A is skipped. Phase 1 still needs the key.
        # So we test the injection logic indirectly via the source code structure.
        import inspect
        source = inspect.getsource(generate_tour_text)

        # Verify the injection logic exists
        assert '_forced_stops_active' in source, (
            "generate_tour_text must contain _forced_stops_active flag"
        )
        assert 'FORCED STOPS ACTIVE' in source, (
            "generate_tour_text must log forced stops activation"
        )
        assert 'Phase 3A GPT call' not in source or 'SKIPPED' in source, (
            "forced stops must skip Phase 3A"
        )

    def test_forced_stops_creates_poi_list_from_names(self):
        """The _new_poi helper must be called for each forced stop name."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # Verify the code creates poi_list from forced_stops
        assert "poi_list = [_new_poi(name) for name in forced_stops]" in source, (
            "forced stops must create poi_list via _new_poi(name) for each stop"
        )

    def test_forced_stops_sets_total_stops(self):
        """When forced_stops is provided, total_stops is set to len(forced_stops)."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        assert "total_stops = len(forced_stops)" in source, (
            "forced stops must override total_stops with len(forced_stops)"
        )


class TestForcedStopsGateNotWeakened:
    """Gates must still apply to forced stops — never weakened."""

    def test_existence_gate_code_runs_after_forced_stops(self):
        """The existence gate code path must execute regardless of forced_stops."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # The existence gate code must NOT be conditioned on _forced_stops_active
        # being False. It should run for ALL tours.
        gate_section = source[source.index('STOP-EXISTENCE GATE (INLINE ENFORCEMENT)'):]
        gate_section = gate_section[:gate_section.index('END [LOCAL-245] STOP-EXISTENCE GATE')]

        assert '_forced_stops_active' not in gate_section, (
            "Existence gate must NOT check _forced_stops_active — it must run "
            "for ALL tours including forced stops (LOCAL-357 requirement: "
            "'Do not weaken the gates for forced stops')"
        )

    def test_d1v2_verification_runs_for_forced_museum_stops(self):
        """D1v2 museum verification must run regardless of forced stops."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # D1v2 verification section
        d1v2_section = source[source.index('D1] In-collection verification for museum'):]
        d1v2_section = d1v2_section[:3000]  # Just the start

        assert '_forced_stops_active' not in d1v2_section, (
            "D1v2 verification must NOT be gated by _forced_stops_active"
        )


class TestForcedStopsOutputMarking:
    """Forced tours must be clearly marked in the output."""

    def test_banner_written_to_output(self):
        """Output file must contain FORCED STOPS banner when forced_stops used."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        assert 'FORCED STOPS — VERIFICATION HARNESS' in source, (
            "Output must contain 'FORCED STOPS — VERIFICATION HARNESS' banner"
        )
        assert 'LOCAL-357' in source, (
            "Banner must reference LOCAL-357"
        )

    def test_banner_warns_not_natural_selection(self):
        """Banner must warn that this is not a naturally-selected tour."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        assert 'NOT a naturally-selected tour' in source, (
            "Banner must clearly state tour is NOT naturally-selected"
        )

    def test_forced_tours_not_cached(self):
        """Forced-stop tours must never be written to the tour cache."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # Find the cache store section
        cache_idx = source.index('store in cache after successful generation')
        cache_line = source[cache_idx:cache_idx + 200]

        assert '_forced_stops_active' in cache_line or 'not _forced_stops_active' in cache_line, (
            "Cache store must be guarded by _forced_stops_active check"
        )


class TestNormalPathUnchanged:
    """Normal generation (forced_stops=None) must work exactly as before."""

    def test_default_none_does_not_activate_forced_path(self):
        """With forced_stops=None, the _forced_stops_active flag stays False."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # The condition must check both None and empty
        assert "forced_stops is not None and len(forced_stops) > 0" in source, (
            "Forced path activation must require non-None AND non-empty list"
        )

    def test_empty_list_does_not_activate_forced_path(self):
        """With forced_stops=[], the _forced_stops_active flag stays False."""
        import inspect
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(generate_tour_text)

        # len(forced_stops) > 0 ensures empty list doesn't activate
        assert "len(forced_stops) > 0" in source, (
            "Empty forced_stops list must not activate forced path"
        )


class TestMuseumBoundsProperty:
    """Museum bounds (D258) must hold as regression properties."""

    @pytest.fixture
    def db_conn(self):
        """Get a database connection for scoring."""
        from tests.db_connection import get_connection
        conn = get_connection()
        yield conn
        conn.close()

    def test_museum_8stop_score_bound(self, db_conn):
        """Museum 8-stop tour must score >= 75.0 (D258).

        This test scores an existing 8-stop museum tour file.
        The forced_stops harness does not change the scoring rubric.
        """
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )
        if not os.path.exists(tour_file):
            pytest.skip("8-stop museum tour file not in worktree (tours/ is gitignored)")

        from tour_rubric_scorer import score_tour_file
        result = score_tour_file(tour_file, n_requested=8)
        assert result.total_score >= 75.0, (
            f"Museum 8-stop score {result.total_score} < 75.0 bound (D258)"
        )

    def test_museum_4stop_score_bound(self, db_conn):
        """Museum 4-stop tour must score >= 81.2 (D258).

        Uses Palais Lascaris (6-stop) as the closest available proxy.
        """
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'Palais_Lascaris__Nice_museum_tour_20260727_174018.txt'
        )
        if not os.path.exists(tour_file):
            pytest.skip("Palais Lascaris museum tour file not in worktree (tours/ is gitignored)")

        from tour_rubric_scorer import score_tour_file
        result = score_tour_file(tour_file, n_requested=6)
        assert result.total_score >= 81.2, (
            f"Museum Palais score {result.total_score} < 81.2 bound (D258)"
        )


class TestUserChosenStopsAPIContract:
    """LOCAL-525: user-chosen stops ARE now exposed through the HTTP API.

    HISTORY — why this replaces the old assertion:
        LOCAL-357 built forced_stops as an INTERNAL verification harness and this
        file originally asserted the HTTP API must NOT expose it
        (test_service_layer_does_not_expose_forced_stops /
        test_orchestrator_does_not_expose_forced_stops). That decision was correct
        at the time: the parameter was a test tool, not a product input.

        LOCAL-525 changes the decision, on evidence. On 2026-09-23 Igor visited the
        MFA, recorded the exact stops he wanted, and had no way to get them into a
        tour; cramming them into the free-text request string was cumbersome and not
        reliably honoured. The engine already accepts an exact, ordered stop list
        (generate_tour_text(..., forced_stops=[...])) and runs every downstream gate
        over it unchanged — so the safe move is to PROMOTE it to a product feature
        behind validation, not to keep it walled off.

        The old "must not expose" assertions are therefore deliberately replaced by
        the contract below: a validated list is accepted and forwarded; malformed
        input is rejected with a clear message; omitting 'stops' is unchanged.
    """

    def test_service_layer_exposes_validated_stops(self):
        """The tour-generator /generate endpoint accepts 'stops' and forwards it
        to the engine as forced_stops, guarded by validation."""
        service_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text_service.py'
        )
        with open(service_path, 'r') as f:
            service_source = f.read()

        # It reads the stops input, validates it, and threads it to the engine.
        assert "data.get('stops')" in service_source, (
            "generate_tour_text_service.py must read 'stops' from the request "
            "(LOCAL-525)"
        )
        assert "def validate_stops(" in service_source, (
            "generate_tour_text_service.py must validate the stops list before use "
            "(LOCAL-525 acceptance #2)"
        )
        assert "forced_stops=forced_stops" in service_source, (
            "the validated stops must be passed to generate_tour_text as "
            "forced_stops (LOCAL-525 acceptance #1)"
        )

    def test_orchestrator_exposes_validated_stops(self):
        """The orchestrator accepts 'stops', validates/sanitizes it, and forwards
        it to the tour-generator."""
        orch_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_orchestrator_service.py'
        )
        with open(orch_path, 'r') as f:
            orch_source = f.read()

        assert "data.get('stops')" in orch_source, (
            "tour_orchestrator_service.py must read 'stops' from the request "
            "(LOCAL-525)"
        )
        assert "def validate_stops(" in orch_source, (
            "tour_orchestrator_service.py must validate the stops list (LOCAL-525)"
        )
        assert 'generate_data["stops"] = stops' in orch_source, (
            "the orchestrator must forward the validated stops to the "
            "tour-generator (LOCAL-525 acceptance #1)"
        )

    def test_validate_stops_accepts_a_clean_ordered_list(self):
        """A non-empty list of non-empty strings is accepted, stripped, order kept
        (acceptance #1: 'exactly those stops, in order')."""
        from generate_tour_text_service import validate_stops
        clean, err = validate_stops(["  Gallery A ", "Sculpture Court", "Print Room"])
        assert err is None
        assert clean == ["Gallery A", "Sculpture Court", "Print Room"], (
            "order must be preserved and names stripped"
        )

    def test_validate_stops_rejects_malformed_never_silently_ignored(self):
        """Malformed input is rejected with a clear message (acceptance #2)."""
        from generate_tour_text_service import validate_stops

        # Not a list
        clean, err = validate_stops("Gallery A")
        assert clean is None and err and "list" in err.lower()

        # Empty list
        clean, err = validate_stops([])
        assert clean is None and err and "empty" in err.lower()

        # Non-string element
        clean, err = validate_stops(["ok", 42])
        assert clean is None and err and "string" in err.lower()

        # Blank / whitespace-only element
        clean, err = validate_stops(["ok", "   "])
        assert clean is None and err and "blank" in err.lower()

    def test_omitting_stops_behaves_as_before(self):
        """Omitting 'stops' (None) is NOT an error and yields no forced list
        (acceptance #3: unchanged behaviour)."""
        from generate_tour_text_service import validate_stops
        clean, err = validate_stops(None)
        assert clean is None
        assert err is None, "absent 'stops' must not be treated as malformed"

    def test_orchestrator_validate_stops_sanitizes_entries(self):
        """The orchestrator sanitizes each stop name (same safety as every other
        user string) while preserving order."""
        from tour_orchestrator_service import validate_stops as orch_validate_stops
        clean, err = orch_validate_stops(["Gallery <A>", "Court/1"])
        assert err is None
        # sanitize_input strips angle brackets and replaces filesystem-dangerous
        # characters; the names remain non-empty and in order.
        assert len(clean) == 2
        assert "<" not in clean[0] and ">" not in clean[0]
        assert "/" not in clean[1]
