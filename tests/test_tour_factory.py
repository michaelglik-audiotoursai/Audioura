#!/usr/bin/env python3
"""
TestTourFactory — the ONLY sanctioned way to create tours from test code.

LOCAL-139: Replaces ad-hoc is_test handling with a structural guarantee.
Every tour created through this factory is flagged is_test=TRUE at the DB
level, regardless of what the orchestrator does or what env vars are set.

Design principles:
  - is_test=TRUE is set UNCONDITIONALLY on every INSERT — there is no
    parameter to opt out.
  - For HTTP-path tests that must go through the orchestrator, the factory
    provides ensure_flagged() which verifies and fixes the flag after
    creation — so even if the orchestrator silently drops the flag, the
    row is safe.
  - Cleanup nulls lat/lng (never DELETEs) per CLAUDE.md rules.
  - Only IDs created by THIS instance are touched.

Usage:

    from test_tour_factory import TestTourFactory

    factory = TestTourFactory()

    # Direct DB insertion (preferred for most tests):
    tour_id = factory.create(
        tour_name="My Test Tour",
        request_string="Test, City",
        lat=43.70, lng=7.27,
    )

    # After HTTP-path tour generation (orchestrator may drop is_test):
    factory.adopt_and_ensure_flagged(tour_id)

    # Cleanup happens automatically on exit, or call:
    factory.cleanup()
"""
import os
import sys
import atexit
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection


# Pattern that identifies test-generated tour names (same as the guard query)
TEST_NAME_PATTERN = re.compile(
    r'(LOCAL\d+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)',
    re.IGNORECASE,
)


class TestTourFactory:
    """
    Structural guarantee: every tour this factory touches has is_test=TRUE.

    There is no bypass. The 'unsafe' path (production tours with is_test=FALSE)
    requires explicitly using raw SQL outside this class — and the guard test
    (test_no_unflagged_test_tours) will catch it.
    """

    def __init__(self, auto_cleanup=True):
        self._created_ids = []
        self._adopted_ids = []
        # Set env var for any indirect orchestrator path
        os.environ['TOUR_TEST_MODE'] = 'true'
        if auto_cleanup:
            atexit.register(self.cleanup)

    @property
    def created_ids(self):
        """All IDs this factory created or adopted."""
        return list(self._created_ids + self._adopted_ids)

    def create(
        self,
        tour_name,
        request_string="Test Location",
        lat=None,
        lng=None,
        audio_tour=None,
        tour_content=None,
        stops_count=None,
    ):
        """
        Insert a test tour with is_test=TRUE. Returns the new row ID.

        There is NO is_test parameter. It is always TRUE.
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
                         lat, lng, tour_content, stops_count, is_test)
                    VALUES (%s, %s, %s, 0, %s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string, psycopg2.Binary(audio_tour),
                     lat, lng, tour_content, stops_count),
                )
            elif lat is not None and lng is not None:
                cur.execute(
                    """
                    INSERT INTO audio_tours
                        (tour_name, request_string, number_requested, lat, lng,
                         tour_content, stops_count, is_test)
                    VALUES (%s, %s, 0, %s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string, lat, lng, tour_content, stops_count),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO audio_tours
                        (tour_name, request_string, number_requested,
                         tour_content, stops_count, is_test)
                    VALUES (%s, %s, 0, %s, %s, TRUE)
                    RETURNING id
                    """,
                    (tour_name, request_string, tour_content, stops_count),
                )
            new_id = cur.fetchone()[0]
            conn.commit()
            self._created_ids.append(new_id)
            return new_id
        finally:
            cur.close()
            conn.close()

    def adopt_and_ensure_flagged(self, tour_id):
        """
        Adopt an externally-created tour ID and FORCE is_test=TRUE.

        Use after HTTP-path tests that go through the orchestrator. The
        orchestrator may or may not have set the flag (depends on env vars
        inside Docker). This ensures it regardless.

        Returns the number of rows updated (0 means it was already flagged).
        """
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE audio_tours
                SET is_test = TRUE
                WHERE id = %s AND (is_test IS NOT TRUE)
                """,
                (tour_id,),
            )
            updated = cur.rowcount
            conn.commit()
            if tour_id not in self._adopted_ids:
                self._adopted_ids.append(tour_id)
            return updated
        finally:
            cur.close()
            conn.close()

    def verify_flagged(self, tour_id):
        """
        Assert that a tour has is_test=TRUE. Raises AssertionError if not.
        """
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT is_test FROM audio_tours WHERE id = %s",
                (tour_id,),
            )
            row = cur.fetchone()
            assert row is not None, f"Tour {tour_id} does not exist"
            assert row[0] is True, (
                f"Tour {tour_id} has is_test={row[0]} — UNSAFE! "
                f"This tour would be visible to users."
            )
        finally:
            cur.close()
            conn.close()

    def cleanup(self):
        """
        Null lat/lng on all tours this factory created or adopted.
        Never DELETEs. is_test remains TRUE.
        """
        all_ids = self._created_ids + self._adopted_ids
        if not all_ids:
            return

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE audio_tours
                SET lat = NULL, lng = NULL
                WHERE id = ANY(%s) AND is_test = TRUE
                """,
                (all_ids,),
            )
            affected = cur.rowcount
            conn.commit()
            print(
                f"[TestTourFactory] Cleaned {affected} tour(s): ids={all_ids}"
            )
        finally:
            cur.close()
            conn.close()
            self._created_ids.clear()
            self._adopted_ids.clear()

    def cleanup_specific(self, tour_ids):
        """
        Clean specific IDs. Must have been created/adopted by this instance.
        """
        all_known = self._created_ids + self._adopted_ids
        for tid in tour_ids:
            if tid not in all_known:
                raise ValueError(
                    f"Tour {tid} not created/adopted by this factory. "
                    f"Known ids: {all_known}"
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
                if tid in self._created_ids:
                    self._created_ids.remove(tid)
                if tid in self._adopted_ids:
                    self._adopted_ids.remove(tid)
            print(
                f"[TestTourFactory] Selectively cleaned {affected} tour(s): "
                f"ids={list(tour_ids)}"
            )
        finally:
            cur.close()
            conn.close()
