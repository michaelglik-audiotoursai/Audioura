#!/usr/bin/env python3
"""migrate_local464_add_score_columns.py — ADDITIVE migration for LOCAL-464.

Adds four new integer columns (0–100) to stop_metrics:
    score_historic    — independent historic score (NOT normalised)
    score_detail      — independent detail score (NOT normalised)
    score_social      — independent social score (NOT normalised)
    valuation_index   — overall story usefulness

These DO NOT replace the existing class_historic/class_details/class_social columns.
The old columns remain untouched — superseding them is a later decision.

This migration is ADDITIVE ONLY:
    - No rows are deleted
    - No existing columns are modified
    - No existing data is changed
    - Row count is identical before and after

Usage:
    python3 migrate_local464_add_score_columns.py
    python3 migrate_local464_add_score_columns.py --rollback   # drop the new columns
"""
import argparse
import sys

import psycopg2


DB_CONFIG = {
    'dbname': 'audiotours',
    'user': 'admin',
    'password': 'password123',
    'host': 'localhost',
    'port': 5433,
}

NEW_COLUMNS = [
    ('score_historic', 'INTEGER'),
    ('score_detail', 'INTEGER'),
    ('score_social', 'INTEGER'),
    ('valuation_index', 'INTEGER'),
]


def migrate():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Report row count before
    cur.execute("SELECT count(*) FROM stop_metrics")
    before = cur.fetchone()[0]
    print(f"Row count BEFORE: {before}")

    # Add columns if they don't already exist
    for col_name, col_type in NEW_COLUMNS:
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'stop_metrics' AND column_name = '{col_name}'
        """)
        if cur.fetchone():
            print(f"  Column '{col_name}' already exists — skipping")
        else:
            cur.execute(f"ALTER TABLE stop_metrics ADD COLUMN {col_name} {col_type}")
            print(f"  Added column '{col_name}' ({col_type})")

    # Report row count after
    cur.execute("SELECT count(*) FROM stop_metrics")
    after = cur.fetchone()[0]
    print(f"Row count AFTER:  {after}")
    assert before == after, f"Row count changed! {before} → {after}"
    print(f"✓ Row count unchanged: {after}")

    cur.close()
    conn.close()


def rollback():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    for col_name, _ in NEW_COLUMNS:
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'stop_metrics' AND column_name = '{col_name}'
        """)
        if cur.fetchone():
            cur.execute(f"ALTER TABLE stop_metrics DROP COLUMN {col_name}")
            print(f"  Dropped column '{col_name}'")
        else:
            print(f"  Column '{col_name}' does not exist — skipping")

    cur.close()
    conn.close()
    print("Rollback complete")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback', action='store_true', help='Remove the added columns')
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        migrate()


if __name__ == '__main__':
    main()
