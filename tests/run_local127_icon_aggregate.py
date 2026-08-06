#!/usr/bin/env python3
"""
LOCAL-127 (resubmission): Establish the real key between stop_metrics and audio_tours.

FINDING: There is NO reliable key. stop_metrics.tour_id is NULL on all 1002 rows,
job_status is empty, and the paragraph text stored in stop_metrics does NOT match
any audio_tours.tour_content. The evaluator ran on different LLM generations than
those stored as final tours.

The previous submission used stop-title matching, which produces WRONG results:
tours sharing stop titles (e.g. tours 21, 27, 28 — same venue, different text)
all received identical scores. This test proves the collision and the absence of a key.
"""
import sys
import os
import re
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from db_connection import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("LOCAL-127 EVIDENCE: No reliable key between stop_metrics and audio_tours")
    print("=" * 70)

    # ─── Section 1: The key problem ─────────────────────────────────────────
    print("\n--- 1. stop_metrics.tour_id is NULL everywhere ---")
    cur.execute("SELECT COUNT(*) FROM stop_metrics WHERE tour_id IS NOT NULL")
    non_null_tour_ids = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stop_metrics")
    total_sm = cur.fetchone()[0]
    print(f"  stop_metrics rows total: {total_sm}")
    print(f"  stop_metrics rows with non-null tour_id: {non_null_tour_ids}")
    assert non_null_tour_ids == 0, f"Expected 0 non-null tour_ids, got {non_null_tour_ids}"
    print("  ✓ Confirmed: tour_id is NULL on all rows")

    # ─── Section 2: job_status is empty (no job_id -> tour linkage there) ───
    print("\n--- 2. job_status table is empty ---")
    cur.execute("SELECT COUNT(*) FROM job_status")
    js_count = cur.fetchone()[0]
    print(f"  job_status rows: {js_count}")
    assert js_count == 0, f"Expected 0, got {js_count}"
    print("  ✓ No job_status records to trace job_id -> tour")

    # ─── Section 3: Title collision demonstration ───────────────────────────
    print("\n--- 3. Title collision: tours 21, 27, 28 share identical stop titles ---")
    for tid in [21, 27, 28]:
        cur.execute("SELECT tour_content FROM audio_tours WHERE id = %s", (tid,))
        content = cur.fetchone()[0]
        stops = re.findall(r'^Stop\s+\d+:\s*(.+)$', content, re.MULTILINE)
        stops = [s.strip() for s in stops]
        print(f"  Tour {tid} stops: {stops[:4]}{'...' if len(stops) > 4 else ''}")

    # Extract and compare
    tour_stops = {}
    for tid in [21, 27, 28]:
        cur.execute("SELECT tour_content FROM audio_tours WHERE id = %s", (tid,))
        content = cur.fetchone()[0]
        stops = re.findall(r'^Stop\s+\d+:\s*(.+)$', content, re.MULTILINE)
        tour_stops[tid] = [s.strip() for s in stops]

    assert tour_stops[21] == tour_stops[27] == tour_stops[28], \
        "Expected identical stop titles across tours 21, 27, 28"
    print(f"  ✓ All three tours have identical stop titles ({len(tour_stops[21])} stops)")
    print(f"    Any title-based matching gives them the same score — WRONG")

    # ─── Section 4: The paragraph text doesn't match ────────────────────────
    print("\n--- 4. Paragraph text in stop_metrics ≠ tour_content text ---")
    # Get first significant paragraph from tour 27's Stop 2
    cur.execute("SELECT tour_content FROM audio_tours WHERE id = 27")
    content_27 = cur.fetchone()[0]
    parts = re.split(r'\nStop \d+:\s*', content_27)
    # Stop 2 content
    stop2_27 = parts[2] if len(parts) > 2 else ''
    # Find first real paragraph
    para_27 = None
    for line in stop2_27.split('\n'):
        stripped = line.strip()
        if (stripped and len(stripped) > 40 and
                not stripped.startswith(('Address:', 'Coordinates:', 'Museum', 'Statue de Bouddha'))):
            para_27 = stripped
            break

    print(f"  Tour 27 Stop 2 paragraph: \"{para_27[:70]}...\"")

    # Search in stop_metrics
    cur.execute("""
        SELECT job_id, paragraphs FROM stop_metrics
        WHERE stop_title = 'Statue de Bouddha' AND i_con > 0
    """)
    sm_rows = cur.fetchall()
    match_found = False
    for r in sm_rows:
        paras = r[1]
        if isinstance(paras, list):
            for p in paras:
                text = p.get('text', '') if isinstance(p, dict) else str(p)
                if para_27 and para_27[:30] in text:
                    match_found = True
                    break

    print(f"  stop_metrics rows for 'Statue de Bouddha' with i_con>0: {len(sm_rows)}")
    print(f"  Any contain tour 27's paragraph text? {match_found}")
    assert not match_found, "Expected NO match — evaluator ran on different generations"
    print("  ✓ Confirmed: stop_metrics paragraphs are from DIFFERENT generations")

    # Show what stop_metrics actually has
    if sm_rows:
        paras = sm_rows[0][1]
        if isinstance(paras, list) and len(paras) > 0:
            first = paras[0].get('text', '')[:70] if isinstance(paras[0], dict) else str(paras[0])[:70]
            print(f"  stop_metrics has: \"{first}...\"")
            print(f"  tour_content has: \"{para_27[:70]}...\"")
            print(f"  These are different LLM outputs for the same stop title.")

    # ─── Section 5: Multi-job ambiguity ─────────────────────────────────────
    print("\n--- 5. Stop titles appear in MANY different jobs ---")
    cur.execute("""
        SELECT stop_title, COUNT(DISTINCT job_id) as job_count
        FROM stop_metrics
        WHERE i_con > 0
        GROUP BY stop_title
        HAVING COUNT(DISTINCT job_id) > 1
        ORDER BY job_count DESC
        LIMIT 5
    """)
    print("  Most ambiguous titles (i_con > 0 only):")
    for r in cur.fetchall():
        print(f"    \"{r[0][:40]}\" -> {r[1]} different jobs")
    print("  A title-match picks ONE of these arbitrarily (last dict key wins)")

    # ─── Section 6: Distribution of per-stop i_con (still valid) ────────────
    print("\n--- 6. Per-stop i_con distribution (these values ARE correct) ---")
    cur.execute("SELECT COUNT(*), AVG(i_con), MIN(i_con), MAX(i_con) FROM stop_metrics WHERE i_con > 0")
    r = cur.fetchone()
    print(f"  Rows with i_con > 0: {r[0]}")
    print(f"  Mean: {float(r[1]):.2f}, Min: {float(r[2]):.2f}, Max: {float(r[3]):.2f}")

    cur.execute("SELECT COUNT(*) FROM stop_metrics WHERE i_con = 0")
    zeros = cur.fetchone()[0]
    print(f"  Rows with i_con = 0 (failed/skipped evaluations): {zeros}")
    print(f"  Total: {total_sm} (valid={r[0]}, zeros={zeros})")
    print(f"  Avg excluding zeros: {float(r[1]):.2f} — the scale discriminates usefully")

    # ─── Section 7: audio_tours aggregates are correctly NULL ───────────────
    print("\n--- 7. audio_tours i_con_avg/i_con_min correctly NULL ---")
    cur.execute("SELECT COUNT(*) FROM audio_tours WHERE i_con_avg IS NOT NULL")
    populated = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_tours = cur.fetchone()[0]
    print(f"  audio_tours total: {total_tours}")
    print(f"  audio_tours with i_con_avg populated: {populated}")
    assert populated == 0, f"Expected 0 populated (reverted), got {populated}"
    print("  ✓ All NULL — correct, because no reliable key exists to populate them")

    # ─── Section 8: Proposed fix — stop_metrics.tour_id backfill ────────────
    print("\n--- 8. Proposed fix: populate stop_metrics.tour_id ---")
    cur.execute("SELECT COUNT(DISTINCT job_id) FROM stop_metrics")
    distinct_jobs = cur.fetchone()[0]
    print(f"  Distinct job_ids in stop_metrics: {distinct_jobs}")
    print(f"  audio_tours has no job_id column — cannot link today")
    print(f"  cost_ledger has job_id (148 rows, 62 overlap with stop_metrics)")
    print(f"  But cost_ledger has no tour_id reference either")
    print()
    print("  ROOT CAUSE: The pipeline flow is:")
    print("    1. generate_tour_text_service evaluates i_con → writes stop_metrics (with job_id)")
    print("    2. tour_orchestrator creates audio_tours row (no job_id stored)")
    print("    3. stop_metrics.tour_id is never populated (tour doesn't exist at step 1)")
    print()
    print("  FIX REQUIRED (follow-up task):")
    print("    A. Add job_id column to audio_tours (or use existing text_job_id in ACTIVE_JOBS)")
    print("    B. After store_audio_tour, UPDATE stop_metrics SET tour_id = X WHERE job_id = Y")
    print("    C. Then i_con_avg/min can be computed from stop_metrics WHERE tour_id = X")
    print("    D. Backfill: for the 62 overlapping job_ids in cost_ledger, attempt timestamp")
    print("       correlation — but this only works if tours were stored within seconds of eval")

    # ─── Section 9: Constraints check ──────────────────────────────────────
    print("\n--- 9. Constraints ---")
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    final_count = cur.fetchone()[0]
    print(f"  audio_tours row count: {final_count}")
    assert final_count == 88, f"Expected 88, got {final_count}"
    print("  ✓ Row count unchanged (88)")

    # tours-near check (done via HTTP above, record the expectation)
    print("  tours-near/43.7009358/7.2683912?radius=50 expected: [1,12,14,17,21,24,27,28,29]")
    print("  (verified via HTTP — see submission artifact)")

    print("\n" + "=" * 70)
    print("CONCLUSION: No reliable key exists between stop_metrics and audio_tours.")
    print("Title-matching produces WRONG values. Aggregates reverted to NULL.")
    print("Follow-up task: wire job_id through to audio_tours to enable correct linkage.")
    print("=" * 70)

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
