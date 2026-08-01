#!/usr/bin/env python3
"""
LOCAL-88 Migration: Add is_test column to audio_tours.

This migration adds a boolean `is_test` column (DEFAULT FALSE) that allows
test-generated tours to be structurally excluded from the user-facing
tours-near endpoint without needing to null their coordinates.

Idempotent — safe to run multiple times (uses IF NOT EXISTS via ALTER TABLE
with a pre-check).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
from db_connection import get_connection


def migrate():
    conn = get_connection()
    cur = conn.cursor()

    # Check if column already exists
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'is_test'
    """)
    if cur.fetchone():
        print("[LOCAL-88] is_test column already exists — skipping.")
    else:
        cur.execute("""
            ALTER TABLE audio_tours
            ADD COLUMN is_test BOOLEAN DEFAULT FALSE
        """)
        conn.commit()
        print("[LOCAL-88] Added is_test column to audio_tours (BOOLEAN DEFAULT FALSE).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    migrate()
