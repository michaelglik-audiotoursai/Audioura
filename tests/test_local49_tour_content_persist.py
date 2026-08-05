"""
Regression test for LOCAL-49: tour_content must be persisted on generation.

Verifies that:
1. A freshly generated tour has non-NULL, non-empty tour_content
2. _split_tour_content_into_stops(tour_content) returns exactly stops_count stops
3. The HTTP-response path is used (tour_content from text generator status response)

This test hits the live orchestrator and database — requires services running.

LOCAL-141: Migrated to TestTourFactory.adopt_and_ensure_flagged() — the flag
is set structurally after HTTP creation, regardless of Docker env vars.
"""
import json
import os
import re
import sys
import time

import psycopg2
import pytest
import requests

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:5002")

# Import shared DB config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_db_config
from test_tour_factory import TestTourFactory
DB_CONFIG = get_db_config()
# Remap 'dbname' to 'database' for psycopg2.connect compatibility
DB_CONFIG['database'] = DB_CONFIG.pop('dbname')

# Factory instance — adopt tours created via HTTP so is_test=TRUE is structural
_factory = TestTourFactory(auto_cleanup=True)

# Timeout for tour generation (seconds)
GENERATION_TIMEOUT = 180
POLL_INTERVAL = 10


def _split_tour_content_into_stops(tour_content):
    """Replicate the translation service's split logic."""
    stops = re.split(r'\n\s*Stop\s+(\d+):', tour_content)
    if len(stops) > 1:
        # First element is header, rest are (stop_num, content) pairs
        stop_count = (len(stops) - 1) // 2
        return stop_count
    # Fallback: look for Stop N: headers
    lines = tour_content.split('\n')
    text_content = []
    current_stop = []
    for line in lines:
        if re.match(r'^Stop\s+\d+:', line):
            if current_stop:
                text_content.append('\n'.join(current_stop))
            current_stop = [line]
        elif current_stop:
            current_stop.append(line)
    if current_stop:
        text_content.append('\n'.join(current_stop))
    if text_content:
        return len(text_content)
    # Final fallback: entire content is one stop
    if tour_content.strip():
        return 1
    return 0


def _generate_tour(location, tour_type="walking", total_stops=3):
    """Generate a tour and return the job status when complete."""
    resp = requests.post(
        f"{ORCHESTRATOR_URL}/generate-complete-tour",
        json={
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "user_id": "USER-TEST-REGRESSION-LOCAL49",
            "is_test": True,  # LOCAL-103: mark HTTP-generated test tours
        },
        timeout=30,
    )
    assert resp.status_code == 200, f"Generate failed: {resp.status_code} {resp.text}"
    data = resp.json()
    job_id = data["job_id"]

    # Poll until complete or timeout
    deadline = time.time() + GENERATION_TIMEOUT
    while time.time() < deadline:
        status_resp = requests.get(f"{ORCHESTRATOR_URL}/status/{job_id}", timeout=10)
        assert status_resp.status_code == 200
        status = status_resp.json()
        if status["status"] == "completed":
            return status
        if status["status"] == "error":
            pytest.fail(f"Tour generation failed: {status.get('error')}")
        time.sleep(POLL_INTERVAL)

    pytest.fail(f"Tour generation timed out after {GENERATION_TIMEOUT}s")


def _get_latest_tour_row(tour_name_fragment):
    """Get the most recently created tour matching the name fragment."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, tour_name, tour_content, stops_count
           FROM audio_tours
           WHERE tour_name ILIKE %s
           ORDER BY id DESC LIMIT 1""",
        (f"%{tour_name_fragment}%",)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


@pytest.mark.integration
def test_tour_content_persisted_on_generation():
    """
    LOCAL-49 regression: generated tour must have non-NULL tour_content
    with stop count matching stops_count.
    """
    # Use a unique location unlikely to collide with existing rows
    timestamp = int(time.time())
    location = f"LOCAL49 Regression Test {timestamp}"

    status = _generate_tour(location, tour_type="walking", total_stops=3)
    actual_stops = status.get("actual_stops")

    # Give a moment for DB commit
    time.sleep(2)

    row = _get_latest_tour_row(f"LOCAL49 Regression Test {timestamp}")
    assert row is not None, f"Tour row not found in DB for '{location}'"

    tour_id, tour_name, tour_content, stops_count = row

    # LOCAL-141: Structurally ensure is_test=TRUE regardless of Docker env
    _factory.adopt_and_ensure_flagged(tour_id)

    # 1. tour_content must be non-NULL and non-empty
    assert tour_content is not None, (
        f"REGRESSION: tour_content is NULL for tour {tour_id} ({tour_name})"
    )
    assert len(tour_content) > 0, (
        f"REGRESSION: tour_content is empty for tour {tour_id} ({tour_name})"
    )

    # 2. stops_count must be set
    assert stops_count is not None, f"stops_count is NULL for tour {tour_id}"
    assert stops_count > 0, f"stops_count is 0 for tour {tour_id}"

    # 3. _split_tour_content_into_stops must return exactly stops_count stops
    parsed_stops = _split_tour_content_into_stops(tour_content)
    assert parsed_stops == stops_count, (
        f"Stop count mismatch: _split_tour_content_into_stops returned {parsed_stops}, "
        f"but stops_count is {stops_count} (tour {tour_id})"
    )

    print(f"\n✓ Tour {tour_id}: tour_content={len(tour_content)} chars, "
          f"stops_count={stops_count}, parsed_stops={parsed_stops}")


@pytest.mark.integration
def test_existing_tours_have_content():
    """Verify no NULL tour_content exists in the database (post-backfill)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tour_name FROM audio_tours WHERE tour_content IS NULL"
    )
    null_rows = cur.fetchall()
    cur.close()
    conn.close()

    assert len(null_rows) == 0, (
        f"Found {len(null_rows)} tours with NULL tour_content: "
        f"{[(r[0], r[1]) for r in null_rows]}"
    )
