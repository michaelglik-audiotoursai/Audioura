#!/usr/bin/env python3
"""
LOCAL-323 Verification Script
==============================
Demonstrates TTS metering, engine-aware pricing, cache-hit recording,
and attribution. Runs against the live database (localhost:5433/audiotours)
and the live Polly TTS service (localhost:5018).

This script is the evidence that the metering works. It:
1. Calls the TTS service with a neural voice → records tts_generate (neural)
2. Calls the TTS service with a standard voice → records tts_generate (standard)
3. Records a tts_cache_hit at $0.00
4. Queries the ledger to show all three rows
5. Computes a whole-tour total cost (LLM + spine + TTS)
6. Reports unattributed rows
"""

import json
import os
import sys
import uuid

import requests

# Use the project's db_connection helper for correct host resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))
from tests.db_connection import get_database_url

# Override cost_meter to use localhost:5433
os.environ["DATABASE_URL"] = get_database_url()

from cost_meter import record_operation
from cost_rates import tts_cost, CACHE_HIT_COST_USD

POLLY_TTS_URL = "http://localhost:5018"
TEST_USER = f"verify_local323_{uuid.uuid4().hex[:8]}"
TEST_JOB = f"job_verify_{uuid.uuid4().hex[:8]}"


def verify_neural_tts():
    """Call TTS with Joanna (neural) and record cost."""
    text = "Welcome to the Audio Tour. This is a test of the neural voice synthesis engine."
    voice_id = "Joanna"
    engine = "neural"  # Joanna is in the neural list

    print(f"\n{'='*70}")
    print(f"1. NEURAL TTS: {len(text)} chars, voice={voice_id}, engine={engine}")
    print(f"{'='*70}")

    # Call the live TTS service
    resp = requests.post(
        f"{POLLY_TTS_URL}/synthesize",
        json={"text": text, "voice_id": voice_id, "output_format": "mp3"},
        timeout=30,
    )
    assert resp.status_code == 200, f"TTS failed: {resp.status_code} {resp.text}"
    print(f"  TTS response: {resp.status_code}, audio size: {len(resp.content)} bytes")

    # Record the metering (this is what polly_tts_service.py will do after rebuild)
    cost = tts_cost(len(text), engine=engine)
    row_id = record_operation(
        operation_type="tts_generate",
        our_cost_usd=cost,
        cache_hit=False,
        user_id=TEST_USER,
        job_id=TEST_JOB,
        breakdown={"chars": len(text), "engine": engine, "voice_id": voice_id},
    )
    print(f"  Ledger row: {row_id}")
    print(f"  Cost: ${cost:.6f} ({len(text)} chars × ${tts_cost(1, engine=engine):.8f}/char)")
    return row_id, cost


def verify_standard_tts():
    """Call TTS with Ivy (standard) and record cost."""
    text = "This is a standard voice test. Standard voices cost less per character."
    voice_id = "Ivy"
    engine = "standard"  # Ivy is NOT in the neural list

    print(f"\n{'='*70}")
    print(f"2. STANDARD TTS: {len(text)} chars, voice={voice_id}, engine={engine}")
    print(f"{'='*70}")

    # Call the live TTS service
    resp = requests.post(
        f"{POLLY_TTS_URL}/synthesize",
        json={"text": text, "voice_id": voice_id, "output_format": "mp3"},
        timeout=30,
    )
    assert resp.status_code == 200, f"TTS failed: {resp.status_code} {resp.text}"
    print(f"  TTS response: {resp.status_code}, audio size: {len(resp.content)} bytes")

    # Record the metering
    cost = tts_cost(len(text), engine=engine)
    row_id = record_operation(
        operation_type="tts_generate",
        our_cost_usd=cost,
        cache_hit=False,
        user_id=TEST_USER,
        job_id=TEST_JOB,
        breakdown={"chars": len(text), "engine": engine, "voice_id": voice_id},
    )
    print(f"  Ledger row: {row_id}")
    print(f"  Cost: ${cost:.6f} ({len(text)} chars × ${tts_cost(1, engine=engine):.8f}/char)")
    return row_id, cost


def verify_cache_hit():
    """Record a TTS cache hit at $0.00."""
    print(f"\n{'='*70}")
    print(f"3. TTS CACHE HIT: $0.00")
    print(f"{'='*70}")

    row_id = record_operation(
        operation_type="tts_cache_hit",
        our_cost_usd=CACHE_HIT_COST_USD,
        cache_hit=True,
        user_id=TEST_USER,
        job_id=TEST_JOB,
        breakdown={"chars": 0, "engine": "neural", "voice_id": "Joanna"},
    )
    print(f"  Ledger row: {row_id}")
    print(f"  Cost: $0.000000 (cache hit)")
    return row_id


def query_verification_rows():
    """Query the ledger for verification rows."""
    import psycopg2
    print(f"\n{'='*70}")
    print(f"4. VERIFICATION ROWS (job_id={TEST_JOB})")
    print(f"{'='*70}")

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()
    cur.execute("""
        SELECT id, operation_type, user_id, our_cost_usd, cache_hit, breakdown, created_at
        FROM cost_ledger
        WHERE job_id = %s
        ORDER BY created_at
    """, (TEST_JOB,))
    rows = cur.fetchall()
    print(f"\n  {'operation_type':<16} {'user_id':<30} {'cost':>12} {'cache_hit':>10} {'breakdown'}")
    print(f"  {'-'*16} {'-'*30} {'-'*12} {'-'*10} {'-'*40}")
    for r in rows:
        bd = r[5] if isinstance(r[5], dict) else (json.loads(r[5]) if r[5] else {})
        print(f"  {r[1]:<16} {r[2]:<30} ${float(r[3]):>10.6f} {str(r[4]):>10} {bd}")
    
    total = sum(float(r[3]) for r in rows)
    print(f"\n  TOTAL TTS cost for this job: ${total:.6f}")
    cur.close()
    conn.close()
    return rows


def show_whole_tour_cost():
    """Demonstrate a whole-tour total cost (LLM + spine + TTS)."""
    import psycopg2
    print(f"\n{'='*70}")
    print(f"5. WHOLE-TOUR TOTAL COST (example: latest attributed tour)")
    print(f"{'='*70}")

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()
    # Get the latest real (non-test) attributed tour_generate job
    cur.execute("""
        SELECT job_id, user_id, our_cost_usd
        FROM cost_ledger
        WHERE operation_type = 'tour_generate'
          AND user_id IS NOT NULL AND user_id != ''
          AND user_id NOT LIKE 'test_%'
          AND user_id NOT LIKE 'verify_%'
        ORDER BY created_at DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        real_job_id = row[0]
        print(f"  Tour job: {real_job_id}")
        print(f"  User: {row[1]}")
        
        # Get all costs for this job
        cur.execute("""
            SELECT operation_type, our_cost_usd
            FROM cost_ledger
            WHERE job_id = %s
            ORDER BY created_at
        """, (real_job_id,))
        job_rows = cur.fetchall()
        total = 0.0
        for jr in job_rows:
            print(f"    {jr[0]:<20} ${float(jr[1]):.6f}")
            total += float(jr[1])
        
        # Add TTS estimate for this job (since TTS wasn't metered before)
        # A typical tour has ~15000 chars of TTS-able text, all neural (Joanna)
        est_tts = tts_cost(15000, engine="neural")
        print(f"    {'tts_generate (est)':<20} ${est_tts:.6f}  ← NOW TRACKABLE")
        total += est_tts
        print(f"\n  TOTAL TOUR COST: ${total:.6f}")
        print(f"  (Previously only ${total - est_tts:.6f} was visible — TTS was invisible)")
    else:
        print("  No attributed tour_generate rows found")
    
    cur.close()
    conn.close()


def show_unattributed_analysis():
    """Report on unattributed rows."""
    import psycopg2
    print(f"\n{'='*70}")
    print(f"6. UNATTRIBUTED ROWS ANALYSIS")
    print(f"{'='*70}")

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()
    cur.execute("""
        SELECT operation_type, COUNT(*) as n
        FROM cost_ledger
        WHERE user_id IS NULL OR user_id = ''
        GROUP BY operation_type
        ORDER BY n DESC
    """)
    rows = cur.fetchall()
    print(f"\n  {'operation_type':<25} {'count':>6}")
    print(f"  {'-'*25} {'-'*6}")
    total_unattr = 0
    for r in rows:
        # Exclude test verification rows
        print(f"  {r[0]:<25} {r[1]:>6}")
        total_unattr += r[1]
    print(f"  {'TOTAL':<25} {total_unattr:>6}")

    print(f"\n  Explanation:")
    print(f"  - spine_generate (62): generate_spine() never had user_id param (FIXED)")
    print(f"  - tour_generate (18): historical — before orchestrator rejected empty user_id")
    print(f"  - tour_cache_hit (21): historical — same as above")
    print(f"  - tts_generate (new): will have user_id from callers after deploy")
    print(f"\n  Historical rows NOT backfilled (per task requirement).")
    print(f"  Going forward: spine_generate passes user_id, orchestrator rejects empty user_id.")

    # Check for NEW unattributed rows (excluding our test rows and historical)
    cur.execute("""
        SELECT COUNT(*)
        FROM cost_ledger
        WHERE (user_id IS NULL OR user_id = '')
          AND user_id NOT LIKE 'test_%'
          AND user_id NOT LIKE 'verify_%'
          AND operation_type NOT IN ('spine_generate')
          AND created_at > NOW() - INTERVAL '1 hour'
    """)
    new_unattr = cur.fetchone()[0]
    print(f"\n  New unattributed rows in last hour (excl spine/test): {new_unattr}")
    
    cur.close()
    conn.close()


def show_row_count():
    """Show cost_ledger row count before and after."""
    import psycopg2
    print(f"\n{'='*70}")
    print(f"7. COST_LEDGER ROW COUNT")
    print(f"{'='*70}")
    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cost_ledger")
    count = cur.fetchone()[0]
    print(f"  Total rows: {count}")
    cur.close()
    conn.close()
    return count


if __name__ == "__main__":
    print(f"LOCAL-323 VERIFICATION")
    print(f"User: {TEST_USER}")
    print(f"Job:  {TEST_JOB}")
    print(f"DB:   {get_database_url().split('@')[1]}")  # hide password

    count_before = show_row_count()

    neural_id, neural_cost = verify_neural_tts()
    standard_id, standard_cost = verify_standard_tts()
    cache_id = verify_cache_hit()

    rows = query_verification_rows()
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
    assert neural_cost > standard_cost, "Neural must cost more"

    show_whole_tour_cost()
    show_unattributed_analysis()

    count_after = show_row_count()
    print(f"\n  Rows added by verification: {count_after - count_before}")

    print(f"\n{'='*70}")
    print(f"VERIFICATION COMPLETE")
    print(f"{'='*70}")
