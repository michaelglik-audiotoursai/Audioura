"""
Test suite for LOCAL-323: TTS Metering and Attribution
=======================================================
Tests:
1. tts_cost() returns engine-aware rates (neural vs standard)
2. TTS metering records a ledger row via cost_meter (mocked DB)
3. TTS cache_hit records $0.00
4. spine_generate now accepts user_id
5. polly_tts_service reads attribution fields
6. generate_tour_text exposes job context vars
"""

import json
import os
import sys
import uuid
from unittest.mock import patch, MagicMock

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


def test_tts_cost_engine_aware():
    """tts_cost() returns different rates for neural vs standard."""
    from cost_rates import tts_cost, POLLY_NEURAL_COST_PER_CHAR, POLLY_STANDARD_COST_PER_CHAR

    # Standard: $4.00 / 1M chars
    assert tts_cost(1_000_000, engine="standard") == 4.00
    assert tts_cost(1_000_000) == 4.00  # default is standard

    # Neural: $16.00 / 1M chars
    assert tts_cost(1_000_000, engine="neural") == 16.00

    # Verify per-char rates
    assert POLLY_STANDARD_COST_PER_CHAR == 4.00 / 1_000_000
    assert POLLY_NEURAL_COST_PER_CHAR == 16.00 / 1_000_000

    # Practical example: 5000 chars neural (Joanna voice)
    expected = 5000 * 16.00 / 1_000_000  # $0.00008
    assert tts_cost(5000, engine="neural") == expected

    # Practical example: 5000 chars standard
    expected_std = 5000 * 4.00 / 1_000_000  # $0.00002
    assert tts_cost(5000, engine="standard") == expected_std

    print("PASS: tts_cost() engine-aware pricing verified")


def test_tts_metering_records_row():
    """cost_meter.record_operation accepts tts_generate type and records correct values."""
    from cost_meter import record_operation
    from cost_rates import tts_cost

    test_user = f"test_local323_{uuid.uuid4().hex[:8]}"
    test_job = f"job_local323_{uuid.uuid4().hex[:8]}"
    chars = 3000
    engine = "neural"
    cost = tts_cost(chars, engine=engine)

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        row_id = record_operation(
            operation_type="tts_generate",
            our_cost_usd=cost,
            cache_hit=False,
            user_id=test_user,
            job_id=test_job,
            breakdown={"chars": chars, "engine": engine, "voice_id": "Joanna"},
        )

    assert row_id is not None, "record_operation should return a UUID"
    # Verify the INSERT params
    call_args = mock_cursor.execute.call_args
    params = call_args[0][1]
    assert params[1] == "tts_generate"  # operation_type
    assert params[2] == test_user  # user_id
    assert float(params[3]) == cost  # our_cost_usd
    assert params[4] is False  # cache_hit
    assert params[5] == test_job  # job_id
    breakdown = json.loads(params[6])
    assert breakdown["chars"] == 3000
    assert breakdown["engine"] == "neural"
    print(f"PASS: TTS metered: row_id={row_id}, cost=${cost:.6f}, engine={engine}")


def test_tts_cache_hit_records_zero():
    """tts_cache_hit records $0.00 cost."""
    from cost_meter import record_operation
    from cost_rates import CACHE_HIT_COST_USD

    test_user = f"test_local323_cache_{uuid.uuid4().hex[:8]}"
    test_job = f"job_local323_cache_{uuid.uuid4().hex[:8]}"

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        row_id = record_operation(
            operation_type="tts_cache_hit",
            our_cost_usd=CACHE_HIT_COST_USD,
            cache_hit=True,
            user_id=test_user,
            job_id=test_job,
            breakdown={"chars": 0, "engine": "neural", "voice_id": "Joanna"},
        )

    assert row_id is not None, "cache_hit should still record"
    call_args = mock_cursor.execute.call_args
    params = call_args[0][1]
    assert float(params[3]) == 0.00  # cost forced to 0
    assert params[4] is True  # cache_hit
    print(f"PASS: TTS cache_hit metered at $0.00: row_id={row_id}")


def test_tts_standard_and_neural_different_costs():
    """Neural and standard produce different unit costs for the same char count."""
    from cost_rates import tts_cost

    chars = 10000
    neural_cost = tts_cost(chars, engine="neural")
    standard_cost = tts_cost(chars, engine="standard")

    assert neural_cost > standard_cost, "Neural must cost more than standard"
    assert neural_cost == standard_cost * 4, "Neural is 4x standard rate"
    print(f"PASS: {chars} chars: neural=${neural_cost:.6f}, standard=${standard_cost:.6f}")


def test_spine_generator_accepts_user_id():
    """spine_generator.generate_spine accepts user_id kwarg."""
    import inspect
    from spine_generator import generate_spine

    sig = inspect.signature(generate_spine)
    assert "user_id" in sig.parameters, "generate_spine must accept user_id"
    print("PASS: generate_spine accepts user_id parameter")


def test_polly_service_accepts_attribution_fields():
    """polly_tts_service.synthesize_speech reads user_id and job_id from request body."""
    # Read the source directly rather than importing (avoids boto3 side effects)
    polly_path = os.path.join(_project_root, "polly_tts_service.py")
    with open(polly_path, "r") as f:
        source = f.read()

    assert "user_id" in source, "synthesize_speech must read user_id from request"
    assert "job_id" in source, "synthesize_speech must read job_id from request"
    assert "tts_generate" in source, "synthesize_speech must record tts_generate"
    assert "non-fatal" in source.lower() or "non_fatal" in source.lower(), \
        "TTS metering must be non-fatal"
    # Verify metering is in its own try block (pattern match)
    assert "except Exception as _meter_err:" in source, \
        "Metering must have its own exception handler"
    print("PASS: polly_tts_service handles attribution fields")


def test_generate_tour_text_has_job_context_vars():
    """generate_tour_text module exposes _CURRENT_JOB_USER_ID and _CURRENT_JOB_ID."""
    import generate_tour_text as gtt
    assert hasattr(gtt, "_CURRENT_JOB_USER_ID"), "Must have _CURRENT_JOB_USER_ID"
    assert hasattr(gtt, "_CURRENT_JOB_ID"), "Must have _CURRENT_JOB_ID"
    # Default values should be None
    assert gtt._CURRENT_JOB_USER_ID is None
    assert gtt._CURRENT_JOB_ID is None
    print("PASS: generate_tour_text exposes job context variables")


def test_modernized_service_accepts_attribution():
    """tour_generation_modernized.py process_tour accepts user_id and job_id."""
    modernized_path = os.path.join(_project_root, "tour_generation_modernized.py")
    with open(modernized_path, "r") as f:
        source = f.read()

    # The /process endpoint must read user_id and job_id
    assert "user_id" in source
    assert "orchestrator_job_id" in source
    # generate_modernized_tour_async must accept user_id
    assert "def generate_modernized_tour_async(job_id, tour_file_path, user_id=None, orchestrator_job_id=None)" in source
    print("PASS: tour_generation_modernized accepts attribution fields")


def test_orchestrator_forwards_attribution_to_modernized():
    """tour_orchestrator_service.py forwards user_id and job_id to modernized service."""
    orchestrator_path = os.path.join(_project_root, "tour_orchestrator_service.py")
    with open(orchestrator_path, "r") as f:
        source = f.read()

    # Must contain the LOCAL-323 forwarding
    assert 'modernized_data["user_id"]' in source
    assert 'modernized_data["job_id"]' in source
    print("PASS: orchestrator forwards attribution to modernized service")
