"""
run_storied_db_migration.py — Migration runner with pre/post validation.
=========================================================================
Task [S78]: Connects to Postgres, executes storied_db_migration.sql,
then validates all 5 tables exist with expected column counts.

Usage:
    DATABASE_URL=postgresql://admin:admin@localhost:5432/audiotours python run_storied_db_migration.py

Exit codes:
    0 = MIGRATION OK for all 5 tables
    1 = MIGRATION FAILED (missing DATABASE_URL or table validation error)
"""
import os
import sys

# Expected tables and their column counts
EXPECTED_TABLES = {
    "tour_cache": 4,
    "user_preferences": 3,
    "shared_tours": 7,
    "referral_codes": 4,
    "referral_redemptions": 4,  # id, referral_code, new_user_id, redeemed_at
}

MIGRATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storied_db_migration.sql")


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        print("Usage: DATABASE_URL=postgresql://user:pass@host:port/db python run_storied_db_migration.py")
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    # Read migration SQL
    if not os.path.exists(MIGRATION_FILE):
        print(f"ERROR: Migration file not found: {MIGRATION_FILE}")
        sys.exit(1)

    with open(MIGRATION_FILE, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    print("=" * 60)
    print("Storied v2.2.0 — Database Migration Runner")
    print(f"Database: {database_url.split('@')[-1] if '@' in database_url else '(hidden)'}")
    print(f"Migration file: {MIGRATION_FILE}")
    print("=" * 60)

    # Connect and execute migration
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(migration_sql)
            # Fetch the verification SELECT result
            if cur.description:
                row = cur.fetchone()
                if row:
                    print(f"\nMigration output: {row[0]}")
        print("\n--- Migration executed successfully ---\n")
    except Exception as e:
        print(f"\nMIGRATION FAILED: {e}")
        sys.exit(1)

    # Validate tables exist with expected column counts
    all_ok = True
    try:
        with conn.cursor() as cur:
            for table_name, expected_cols in EXPECTED_TABLES.items():
                cur.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                """, (table_name,))
                row = cur.fetchone()
                actual_cols = row[0] if row else 0

                if actual_cols == 0:
                    print(f"MIGRATION FAILED: {table_name} — table does not exist")
                    all_ok = False
                elif actual_cols >= expected_cols:
                    print(f"MIGRATION OK: {table_name} ({actual_cols} columns, expected ≥{expected_cols})")
                else:
                    print(f"MIGRATION FAILED: {table_name} — {actual_cols} columns, expected ≥{expected_cols}")
                    all_ok = False
    except Exception as e:
        print(f"MIGRATION FAILED: validation error — {e}")
        all_ok = False
    finally:
        conn.close()

    print()
    if all_ok:
        print("✅ ALL 5 TABLES VALIDATED — migration complete.")
        sys.exit(0)
    else:
        print("❌ MIGRATION VALIDATION FAILED — see errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
