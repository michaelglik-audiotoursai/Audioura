#!/usr/bin/env python3
"""
LOCAL-107: Register preference routes, prove the loop over HTTP.

Tests:
  1. POST /user/<id>/stop-feedback returns 2xx (route exists on orchestrator)
  2. Full LOCAL-106 scenario over HTTP: swipe → read vector → regenerate → order changes → undo moves vector back
  3. Isolation: untouched user gets unbiased order over HTTP
  4. GET /user/<id>/preferences returns 2xx
  5. POST /stops/biased-order returns 2xx

This test FAILS if register_preference_routes(app) is not called in
tour_orchestrator_service.py — the routes would 404.
"""

import os
import sys
import json
import uuid
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available

# ─── Constants ─────────────────────────────────────────────────────────────────
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:5102")
MAP_DELIVERY_URL = os.environ.get("MAP_DELIVERY_URL", "http://localhost:5005")

# Unique test user IDs per run (cleanup on exit)
RUN_ID = uuid.uuid4().hex[:8]
USER_A = f"test_local107_a_{RUN_ID}"
USER_B = f"test_local107_b_{RUN_ID}"

# Nice, France — venue with existing stop_metrics (16 stops)
VENUE_LAT, VENUE_LNG = 43.7009358, 7.2683912


def separator(title):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def cleanup_test_users(conn, user_ids):
    """Remove test data from user_stop_feedback and user_class_prefs."""
    cur = conn.cursor()
    for uid in user_ids:
        cur.execute("DELETE FROM user_stop_feedback WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM user_class_prefs WHERE user_id = %s", (uid,))
    conn.commit()
    cur.close()


def get_nice_stops(conn):
    """Get Nice stop_metrics for the e2e test (same query as LOCAL-106)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (stop_title) stop_title, i_con, class_details, class_historic, class_social
        FROM stop_metrics
        WHERE job_id LIKE '4fb0424a%%' OR job_id LIKE '8fa84ebd%%'
        ORDER BY stop_title, created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    # Build canonical list ordered by quality (i_con desc) — same as LOCAL-106
    stops = []
    for i, row in enumerate(sorted(rows, key=lambda r: float(r[1]), reverse=True)):
        stops.append({
            "stop_index": i,
            "stop_title": row[0],
            "i_con": float(row[1]),
            "class_details": float(row[2]),
            "class_historic": float(row[3]),
            "class_social": float(row[4]),
        })
    return stops


def main():
    print("=" * 70)
    print("  LOCAL-107: Register Preference Routes — HTTP Proof")
    print(f"  Run: {datetime.now().isoformat()}")
    print(f"  Users: {USER_A}, {USER_B}")
    print("=" * 70)

    # ─── Pre-flight ─────────────────────────────────────────────────────────
    if not check_db_available():
        print("ERROR: Database not reachable")
        sys.exit(7)

    # Check orchestrator is up
    try:
        r = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        assert r.status_code == 200, f"Orchestrator /health returned {r.status_code}"
        print(f"  Orchestrator health: {r.status_code} OK")
    except requests.ConnectionError:
        print("ERROR: Orchestrator not reachable at localhost:5002")
        sys.exit(7)

    conn = get_connection()
    cur = conn.cursor()

    # Row count before
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    row_count_before = cur.fetchone()[0]
    print(f"  audio_tours row count BEFORE: {row_count_before}")

    # Get Nice stops for the scenario
    stops = get_nice_stops(conn)
    assert len(stops) >= 10, f"Expected ≥10 Nice stops, got {len(stops)}"
    print(f"  Nice stops available: {len(stops)}")

    # Clean any leftover test data
    cleanup_test_users(conn, [USER_A, USER_B])

    passed = 0
    failed = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 1: POST /user/<id>/stop-feedback returns 2xx
    # ═══════════════════════════════════════════════════════════════════════════
    separator("TEST 1: POST /user/<id>/stop-feedback returns 2xx")

    # Pick a historic-heavy stop to dislike
    dislike_stop = max(stops, key=lambda s: s["class_historic"])
    body = {
        "stop_index": dislike_stop["stop_index"],
        "swipe": -1,
        "class_details": dislike_stop["class_details"],
        "class_historic": dislike_stop["class_historic"],
        "class_social": dislike_stop["class_social"],
        "i_con": dislike_stop["i_con"],
    }

    r = requests.post(
        f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback",
        json=body,
        timeout=10,
    )
    print(f"  POST /user/{USER_A}/stop-feedback")
    print(f"  Body: {json.dumps(body, indent=4)}")
    print(f"  Response: {r.status_code} {r.text[:200]}")

    if r.status_code == 200:
        print("  ✓ PASS — Route exists and responds 200")
        passed += 1
    else:
        print(f"  ✗ FAIL — Expected 200, got {r.status_code}")
        print("    This means register_preference_routes() was NOT called!")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 2: Full scenario over HTTP — swipe, read vector, biased order
    # ═══════════════════════════════════════════════════════════════════════════
    separator("TEST 2: Full LOCAL-106 scenario over HTTP")

    # 2a: Record more swipes — dislike 2 historic, like 2 social-heavy
    historic_stops = sorted(stops, key=lambda s: -s["class_historic"])[:2]
    social_stops = sorted(stops, key=lambda s: -s["class_social"])[:2]

    print("  Recording swipes via HTTP:")
    for stop in historic_stops:
        body = {
            "stop_index": stop["stop_index"],
            "swipe": -1,
            "class_details": stop["class_details"],
            "class_historic": stop["class_historic"],
            "class_social": stop["class_social"],
            "i_con": stop["i_con"],
        }
        r = requests.post(f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback", json=body, timeout=10)
        assert r.status_code == 200, f"Swipe failed: {r.status_code} {r.text}"
        print(f"    DISLIKE: {stop['stop_title'][:40]} (h={stop['class_historic']:.2f}) → {r.status_code}")

    for stop in social_stops:
        body = {
            "stop_index": stop["stop_index"],
            "swipe": 1,
            "class_details": stop["class_details"],
            "class_historic": stop["class_historic"],
            "class_social": stop["class_social"],
            "i_con": stop["i_con"],
        }
        r = requests.post(f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback", json=body, timeout=10)
        assert r.status_code == 200, f"Swipe failed: {r.status_code} {r.text}"
        print(f"    LIKE:    {stop['stop_title'][:40]} (s={stop['class_social']:.2f}) → {r.status_code}")

    # 2b: Read preference vector via HTTP
    r = requests.get(f"{ORCHESTRATOR_URL}/user/{USER_A}/preferences", timeout=10)
    assert r.status_code == 200, f"GET preferences failed: {r.status_code}"
    prefs = r.json()
    print(f"\n  GET /user/{USER_A}/preferences → {r.status_code}")
    print(f"    pref_details:  {prefs.get('pref_details', 'N/A')}")
    print(f"    pref_historic: {prefs.get('pref_historic', 'N/A')}")
    print(f"    pref_social:   {prefs.get('pref_social', 'N/A')}")
    print(f"    swipe_count:   {prefs.get('swipe_count', 'N/A')}")
    print(f"    interpretation: {prefs.get('interpretation', 'N/A')}")

    pref_historic = prefs["pref_historic"]
    assert pref_historic < 0.5, f"Expected pref_historic < 0.5 (disliked), got {pref_historic}"
    print(f"  ✓ pref_historic={pref_historic:.4f} < 0.5 (historic disliked)")

    # 2c: Get biased order via HTTP
    order_body = {
        "user_id": USER_A,
        "stops": stops,
    }
    r = requests.post(f"{ORCHESTRATOR_URL}/stops/biased-order", json=order_body, timeout=10)
    assert r.status_code == 200, f"POST biased-order failed: {r.status_code}"
    biased = r.json()
    biased_ordering = biased["ordering"]
    print(f"\n  POST /stops/biased-order → {r.status_code}")
    print(f"    personalized: {biased.get('personalized')}")
    print(f"    Biased stop order (top 5):")
    for i, s in enumerate(biased_ordering[:5]):
        print(f"      {i+1}. {s['stop_title'][:45]:45s} combined={s['combined_score']:.4f}")

    # 2d: Get quality-only order (no prefs) for comparison
    order_body_neutral = {
        "user_id": USER_B,  # B has no swipes = cold start
        "stops": stops,
    }
    r = requests.post(f"{ORCHESTRATOR_URL}/stops/biased-order", json=order_body_neutral, timeout=10)
    assert r.status_code == 200
    baseline = r.json()
    baseline_ordering = baseline["ordering"]

    # Compare: biased order should differ from baseline
    biased_titles = [s["stop_title"] for s in biased_ordering]
    baseline_titles = [s["stop_title"] for s in baseline_ordering]
    positions_changed = sum(1 for a, b in zip(biased_titles, baseline_titles) if a != b)

    print(f"\n    Positions changed vs baseline: {positions_changed}/{len(stops)}")
    if positions_changed > 0:
        print("  ✓ PASS — Biased order differs from quality-only order")
        passed += 1
    else:
        print("  ✗ FAIL — Orders identical (preference bias had no effect)")
        failed += 1

    # 2e: Disliked class still present
    historic_in_biased = [s for s in biased_ordering if s.get("class_historic", 0) > 0.35]
    print(f"    Historic-heavy stops in biased order: {len(historic_in_biased)}")
    if len(historic_in_biased) > 0:
        print("  ✓ Disliked class still present — bias, not filter")
    else:
        print("  ✗ FAIL — Disliked class was filtered out entirely")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 3: Undo — vector moves back (over HTTP)
    # ═══════════════════════════════════════════════════════════════════════════
    separator("TEST 3: Undo one swipe — vector moves back")

    pref_before_undo = pref_historic
    # Undo = record a reversal swipe (+1) on the same stop we disliked
    undo_stop = historic_stops[0]
    undo_body = {
        "stop_index": undo_stop["stop_index"],
        "swipe": 1,  # reversal
        "class_details": undo_stop["class_details"],
        "class_historic": undo_stop["class_historic"],
        "class_social": undo_stop["class_social"],
        "i_con": undo_stop["i_con"],
    }
    r = requests.post(f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback", json=undo_body, timeout=10)
    assert r.status_code == 200, f"Undo swipe failed: {r.status_code}"
    print(f"  Reversal swipe (+1) on: {undo_stop['stop_title'][:40]} → {r.status_code}")

    # Re-read preferences
    r = requests.get(f"{ORCHESTRATOR_URL}/user/{USER_A}/preferences", timeout=10)
    assert r.status_code == 200
    prefs_after = r.json()
    pref_after_undo = prefs_after["pref_historic"]
    delta = pref_after_undo - pref_before_undo
    print(f"  pref_historic BEFORE undo: {pref_before_undo:.4f}")
    print(f"  pref_historic AFTER undo:  {pref_after_undo:.4f}")
    print(f"  Delta: {delta:+.4f}")

    if delta > 0:
        print(f"  ✓ PASS — Vector moved back (Δ = {delta:+.4f})")
        passed += 1
    else:
        print(f"  ✗ FAIL — Vector did not move back (Δ = {delta:+.4f})")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 4: Isolation — User B (untouched) gets unbiased order
    # ═══════════════════════════════════════════════════════════════════════════
    separator("TEST 4: Isolation — User B gets unbiased order")

    # User B preferences should be cold start
    r = requests.get(f"{ORCHESTRATOR_URL}/user/{USER_B}/preferences", timeout=10)
    assert r.status_code == 200
    prefs_b = r.json()
    print(f"  GET /user/{USER_B}/preferences → {r.status_code}")
    print(f"    cold_start: {prefs_b.get('cold_start')}")

    assert prefs_b.get("cold_start") is True, f"User B should be cold start, got: {prefs_b}"
    print("  ✓ User B is cold start (no preferences)")

    # User B biased order should equal quality-only
    r = requests.post(f"{ORCHESTRATOR_URL}/stops/biased-order", json={
        "user_id": USER_B,
        "stops": stops,
    }, timeout=10)
    assert r.status_code == 200
    b_order = r.json()["ordering"]
    b_titles = [s["stop_title"] for s in b_order]

    # User B order must match baseline (quality-only)
    # Note: baseline_ordering was generated with User B (cold start) so they should be identical
    b_rank_changes = sum(1 for s in b_order if s.get("rank_change", 0) != 0)
    print(f"    User B rank_changes: {b_rank_changes}")
    print(f"    User B top 3: {b_titles[:3]}")

    if b_rank_changes == 0:
        print("  ✓ PASS — User B order is unbiased (all rank_change = 0)")
        passed += 1
    else:
        print(f"  ✗ FAIL — User B has {b_rank_changes} rank changes (should be 0)")
        failed += 1

    # Confirm User A != User B ordering
    a_titles = [s["stop_title"] for s in biased_ordering]
    if a_titles != b_titles:
        print("  ✓ User A (personalized) ≠ User B (unbiased) — isolation confirmed")
    else:
        print("  ✗ WARNING — User A and User B have same ordering")

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 5: Validation errors return 400
    # ═══════════════════════════════════════════════════════════════════════════
    separator("TEST 5: Validation — bad requests return 400")

    # Missing required fields
    r = requests.post(f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback",
                      json={"swipe": 1}, timeout=10)
    print(f"  Missing fields → {r.status_code}")
    if r.status_code == 400:
        print("  ✓ PASS — 400 on missing fields")
        passed += 1
    else:
        print(f"  ✗ FAIL — Expected 400, got {r.status_code}")
        failed += 1

    # Invalid swipe value
    r = requests.post(f"{ORCHESTRATOR_URL}/user/{USER_A}/stop-feedback",
                      json={**body, "swipe": 5}, timeout=10)
    print(f"  Invalid swipe=5 → {r.status_code}")
    if r.status_code == 400:
        print("  ✓ PASS — 400 on invalid swipe value")
        passed += 1
    else:
        print(f"  ✗ FAIL — Expected 400, got {r.status_code}")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # POST-FLIGHT
    # ═══════════════════════════════════════════════════════════════════════════
    separator("POST-FLIGHT")

    # Row count after
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    row_count_after = cur.fetchone()[0]
    print(f"  audio_tours row count AFTER: {row_count_after}")
    assert row_count_after == row_count_before, (
        f"audio_tours changed: {row_count_before} → {row_count_after}")
    print(f"  ✓ audio_tours unchanged ({row_count_before} → {row_count_after})")

    # tours-near check
    try:
        r = requests.get(f"{MAP_DELIVERY_URL}/tours-near/{VENUE_LAT}/{VENUE_LNG}?radius=50", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                tour_ids = sorted(data)
            elif isinstance(data, dict) and "tours" in data:
                tour_ids = sorted([t["id"] for t in data["tours"]])
            else:
                tour_ids = sorted([t["id"] for t in data])
            expected = [1, 12, 14, 17, 21, 24, 27, 28, 29]
            print(f"  tours-near = {tour_ids}")
            assert tour_ids == expected, f"Expected {expected}, got {tour_ids}"
            print(f"  ✓ tours-near matches expected")
        else:
            print(f"  ⚠ tours-near returned {r.status_code} (non-fatal)")
    except requests.ConnectionError:
        print("  ⚠ Map delivery service not reachable (non-fatal for this test)")

    # Cleanup test data
    cleanup_test_users(conn, [USER_A, USER_B])
    print("  ✓ Test data cleaned up")

    cur.close()
    conn.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    separator("SUMMARY")
    total = passed + failed
    print(f"  Passed: {passed}/{total}")
    print(f"  Failed: {failed}/{total}")

    if failed > 0:
        print("\n  ✗ OVERALL: FAIL")
        sys.exit(1)
    else:
        print("\n  ✓ OVERALL: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
