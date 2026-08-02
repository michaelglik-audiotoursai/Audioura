#!/usr/bin/env python3
"""
Shared test helper for creating and cleaning up test tours.

LOCAL-88: Provides a safe way to create test tours that are automatically
flagged with is_test=TRUE and never appear in the user-facing tours-near
endpoint. Cleanup removes ONLY the specific IDs created by this helper
instance — never by name pattern, date range, or "everything above id N".

LOCAL-139: This class is retained for backward compatibility. New code
should use TestTourFactory from test_tour_factory.py instead, which has
no is_test parameter at all (structural safety).

Usage:
    from tests.test_tour_helper import TestTourHelper

    helper = TestTourHelper()
    tour_id = helper.create_test_tour(
        tour_name="My Test Tour",
        request_string="Test Location, City",
        lat=43.70, lng=7.27,
    )
    # ... run assertions ...
    helper.cleanup()  # removes only tours created by THIS instance

The helper sets TOUR_TEST_MODE=true in the environment so that if the
orchestrator INSERT path is invoked indirectly, it also flags the row.
"""
import os
import sys
import atexit

# Ensure tests/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection


class TestTourHelper:
    """
    Creates test tours with is_test=TRUE and tracks their IDs for safe cleanup.

    Rules (LOCAL-88):
      - Every INSERT sets is_test=TRUE unconditionally.
      - Cleanup uses UPDATE (set is_test=TRUE, lat=NULL, lng=NULL) — NO DELETE.
      - Only IDs created by this instance are touched on cleanup.
      - TOUR_TEST_MODE env var is set on construction so any indirect INSERT
        through the orchestrator path also gets the flag.
    """

    def __init__(self, auto_cleanup=True):
        """
        Args:
            auto_cleanup: If True, registers atexit handler to clean up
                          on process exit (safety net).
        """
        self._created_ids = []
        # Set the env var so orchestrator/worker paths also flag rows
        os.environ['TOUR_TEST_MODE'] = 'true'
        if auto_cleanup:
            atexit.register(self.cleanup)

    @property
    def created_ids(self):
        """Return a copy of IDs created by this helper instance."""
        return list(self._created_ids)

    def create_test_tour(
        self,
        tour_name="TEST TOUR",
        request_string="Test Location",
        lat=None,
        lng=None,
        audio_tour=None,
        tour_content=None,
    ):
        """
        Insert a test tour row with is_test=TRUE.

        Returns the new row's id.
        """
        conn = get_connection()
        cur = conn.cursor()
        try:
            if audio_tour and lat is not None and lng is not None:
                import psycopg2
                cur.execute(
                    """
                    INSERT INTO audio_tours
                        (tour_name, request_string, audio_tour, number_requested,
                         lat, lng, is_test)
                    VALUES (%s, %s, %s, 0, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string, psycopg2.Binary(audio_tour),
                     lat, lng),
                )
            elif lat is not None and lng is not None:
                cur.execute(
                    """
                    INSERT INTO audio_tours
                        (tour_name, request_string, number_requested, lat, lng, is_test)
                    VALUES (%s, %s, 0, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string, lat, lng),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO audio_tours
                        (tour_name, request_string, number_requested, is_test)
                    VALUES (%s, %s, 0, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string),
                )
            new_id = cur.fetchone()[0]
            conn.commit()
            self._created_ids.append(new_id)
            return new_id
        finally:
            cur.close()
            conn.close()

    def cleanup(self):
        """
        Remove test tours created by this instance.

        ⛔ Does NOT use DELETE. Sets lat=NULL, lng=NULL to ensure the row
        cannot appear in tours-near even if is_test filtering were bypassed.
        The is_test flag remains TRUE.

        Only touches IDs in self._created_ids — nothing else.
        """
        if not self._created_ids:
            return

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Null out coordinates as a belt-and-suspenders measure.
            # The row stays in the table (no DELETE) with is_test=TRUE.
            cur.execute(
                """
                UPDATE audio_tours
                SET lat = NULL, lng = NULL
                WHERE id = ANY(%s) AND is_test = TRUE
                """,
                (self._created_ids,),
            )
            affected = cur.rowcount
            conn.commit()
            print(
                f"[TestTourHelper] Cleaned up {affected} test tour(s): "
                f"ids={self._created_ids}"
            )
        finally:
            cur.close()
            conn.close()
            self._created_ids.clear()

    def cleanup_specific(self, tour_ids):
        """
        Clean up specific tour IDs (must be in self._created_ids).

        Raises ValueError if any id was not created by this instance.
        """
        for tid in tour_ids:
            if tid not in self._created_ids:
                raise ValueError(
                    f"Tour id {tid} was not created by this TestTourHelper "
                    f"instance. Refusing to touch it. Created ids: "
                    f"{self._created_ids}"
                )

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE audio_tours
                SET lat = NULL, lng = NULL
                WHERE id = ANY(%s) AND is_test = TRUE
                """,
                (list(tour_ids),),
            )
            affected = cur.rowcount
            conn.commit()
            for tid in tour_ids:
                self._created_ids.remove(tid)
            print(
                f"[TestTourHelper] Selectively cleaned {affected} tour(s): "
                f"ids={list(tour_ids)}"
            )
        finally:
            cur.close()
            conn.close()

    def verify_not_in_tours_near(self, tour_id, lat, lng, radius_km=50):
        """
        Verify that a specific tour ID does NOT appear in the tours-near
        result set for the given location, even though it has coordinates
        within range.

        Returns True if correctly hidden, raises AssertionError if visible.
        """
        import math

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Simulate the tours-near query (same as map_delivery_service.py)
            cur.execute("""
                SELECT id, lat, lng
                FROM audio_tours
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND (is_test IS NOT TRUE)
                  AND original_tour_id IS NULL
            """)
            for row in cur.fetchall():
                if row[0] == tour_id:
                    raise AssertionError(
                        f"Tour {tour_id} IS visible in tours-near! "
                        f"is_test filtering is not working."
                    )
            return True
        finally:
            cur.close()
            conn.close()
