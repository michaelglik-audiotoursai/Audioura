#!/usr/bin/env python3
"""LOCAL-296 verification: AUDIOURA_DB_TARGET switch routes generation to test DB.

Two runs:
  1. Switch OFF (default): verify generation writes to audiotours (production)
  2. Switch ON (AUDIOURA_DB_TARGET=test): verify write goes to audiotours_test,
     production unchanged

Does NOT call generate_tour_text (no API cost). Inserts a minimal test row
directly, confirms the database, then removes it by captured id after
confirming is_test=true.

Reports production row counts and Nice list before/after.
"""
import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

import psycopg2

# ═══════════════════════════════════════════════════════════════════════════════
# BASELINE: Production state BEFORE
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("LOCAL-296 VERIFICATION: AUDIOURA_DB_TARGET switch")
print("=" * 70)

conn_prod = psycopg2.connect(
    host='localhost', port=5433, dbname='audiotours',
    user='admin', password='password123'
)
cur = conn_prod.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
total_before = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_before = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test = true")
test_before = cur.fetchone()[0]
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_before = [r[0] for r in cur.fetchall()]
conn_prod.close()

print(f"\n[BEFORE] Production audio_tours: {total_before} total = {real_before} real + {test_before} test")
print(f"[BEFORE] Nice list (non-translation): {[x for x in nice_before if x in [1,12,14,17,24,29,152]]}")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: Switch OFF — verify default writes to production
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("TEST 1: Switch OFF (default) — generation writes to audiotours")
print("─" * 70)

# Run a subprocess without AUDIOURA_DB_TARGET set
result = subprocess.run(
    [sys.executable, '-c', '''
import sys, os
sys.path.insert(0, os.path.join(os.environ["PROJECT_ROOT"], "tests"))
from db_connection import get_db_config, log_db_target, get_connection
log_db_target("verification-switch-off")
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT current_database()")
db = cur.fetchone()[0]
print(f"  Connected to: {db}")
assert db == "audiotours", f"Expected audiotours, got {db}"

# Insert a test row to prove the path works
cur.execute("""
    INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test)
    VALUES (%s, %s, %s, %s) RETURNING id
""", ("LOCAL-296 verification switch-off", "verification", 2, True))
row_id = cur.fetchone()[0]
conn.commit()
print(f"  Inserted test row id={row_id} (is_test=true)")

# Immediately verify and clean up (D141: by captured id, after confirming is_test)
cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
is_test = cur.fetchone()[0]
assert is_test is True, f"is_test should be True, got {is_test}"
cur.execute("DELETE FROM audio_tours WHERE id = %s", (row_id,))
conn.commit()
print(f"  Cleaned up row id={row_id} (confirmed is_test=true before delete)")
conn.close()
print("  ✓ TEST 1 PASSED: default path writes to audiotours")
'''],
    env={**os.environ, 'PROJECT_ROOT': PROJECT_ROOT},
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"STDERR: {result.stderr}")
    print("✗ TEST 1 FAILED")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Switch ON — verify AUDIOURA_DB_TARGET=test writes to audiotours_test
# ═══════════════════════════════════════════════════════════════════════════════
print("─" * 70)
print("TEST 2: Switch ON (AUDIOURA_DB_TARGET=test) — writes to audiotours_test")
print("─" * 70)

result = subprocess.run(
    [sys.executable, '-c', '''
import sys, os
sys.path.insert(0, os.path.join(os.environ["PROJECT_ROOT"], "tests"))
from db_connection import get_db_config, log_db_target, get_connection
log_db_target("verification-switch-on")
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT current_database()")
db = cur.fetchone()[0]
print(f"  Connected to: {db}")
assert db == "audiotours_test", f"Expected audiotours_test, got {db}"

# Insert a test row to prove it goes to audiotours_test
cur.execute("""
    INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test)
    VALUES (%s, %s, %s, %s) RETURNING id
""", ("LOCAL-296 verification switch-on", "verification", 2, True))
row_id = cur.fetchone()[0]
conn.commit()
print(f"  Inserted test row id={row_id} in audiotours_test (is_test=true)")

# Clean up from audiotours_test (D141 rule)
cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
is_test = cur.fetchone()[0]
assert is_test is True, f"is_test should be True, got {is_test}"
cur.execute("DELETE FROM audio_tours WHERE id = %s", (row_id,))
conn.commit()
print(f"  Cleaned up row id={row_id} from audiotours_test")
conn.close()
print("  ✓ TEST 2 PASSED: switch routes to audiotours_test")
'''],
    env={**os.environ, 'PROJECT_ROOT': PROJECT_ROOT, 'AUDIOURA_DB_TARGET': 'test'},
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"STDERR: {result.stderr}")
    print("✗ TEST 2 FAILED")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Invalid value — verify fatal exit
# ═══════════════════════════════════════════════════════════════════════════════
print("─" * 70)
print("TEST 3: Invalid value (AUDIOURA_DB_TARGET=bogus) — must fail loudly")
print("─" * 70)

result = subprocess.run(
    [sys.executable, '-c', '''
import sys, os
sys.path.insert(0, os.path.join(os.environ["PROJECT_ROOT"], "tests"))
from db_connection import get_db_config
'''],
    env={**os.environ, 'PROJECT_ROOT': PROJECT_ROOT, 'AUDIOURA_DB_TARGET': 'bogus'},
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"  Exit code: {result.returncode}")
    # Show just the meaningful lines from stderr
    for line in result.stderr.split('\n'):
        if 'FATAL' in line or 'Value' in line or 'Valid' in line:
            print(f"  {line.strip()}")
    print("  ✓ TEST 3 PASSED: invalid value exits fatally")
else:
    print("✗ TEST 3 FAILED: should have exited non-zero")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Verify production UNCHANGED after all tests
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("TEST 4: Production unchanged")
print("─" * 70)

conn_prod = psycopg2.connect(
    host='localhost', port=5433, dbname='audiotours',
    user='admin', password='password123'
)
cur = conn_prod.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
total_after = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test IS NOT TRUE")
real_after = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test = true")
test_after = cur.fetchone()[0]
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_after = [r[0] for r in cur.fetchall()]
conn_prod.close()

print(f"[AFTER] Production audio_tours: {total_after} total = {real_after} real + {test_after} test")
nice_filtered = [x for x in nice_after if x in [1, 12, 14, 17, 24, 29, 152]]
print(f"[AFTER] Nice list (non-translation): {nice_filtered}")

assert total_after == total_before, f"Total changed: {total_before} → {total_after}"
assert real_after == real_before, f"Real changed: {real_before} → {real_after}"
assert test_after == test_before, f"Test changed: {test_before} → {test_after}"
assert nice_after == nice_before, f"Nice list changed!"

print("  ✓ TEST 4 PASSED: production row counts unchanged")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)
print(f"  Production: {total_after} rows ({real_after} real + {test_after} test) — unchanged")
print(f"  Nice list: {nice_filtered}")
print(f"  Switch OFF → audiotours (production, default)")
print(f"  Switch ON  → audiotours_test (test database)")
print(f"  Invalid    → fatal exit (no silent wrong choice)")
