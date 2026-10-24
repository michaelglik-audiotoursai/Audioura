#!/usr/bin/env python3
"""test_local755_organiser_audio_updates.py — LOCAL-755 (RED first on 1942ea37).

Organiser-audio tours (source_kind='organiser_audio', LOCAL-754B) are edited on
the ORGANISER'S OWN site, never through our voice pipeline, and members opt-in to
re-download updates (never pushed). This proves the SERVER pieces, hermetically
(no Postgres, no network — a scripted fake cursor / an injected URL checker), the
same style as test_local754b_organiser_audio.

PART A — the tour-editing service refuses an organiser-audio edit (Rule 1).
  tour_editing_phase2._organiser_audio_edit_block(cur, tour_id) returns
  (409, body) with error_code 'organiser_audio_not_editable' when the tour's
  source tour row carries source_kind='organiser_audio', and None for an
  ordinary/generated tour. No organiser audio/text ever reaches TTS: the guard
  is consulted at the TOP of _bulk_save_core, before any build/metering.

PART B — the builder bumps the version ONLY with the checkbox (Rule 2).
  communities_api.build_audio_tour, on an EDIT of an own organiser-audio tour:
    * WITHOUT notify_members (default)  → details saved silently, NO
      audio_tour_versions archive, the version stays (200 version:1);
    * WITH notify_members=true          → the old content is archived (version
      bump), the version rises (200 version:2).

These assertions FAIL on 1942ea37: _organiser_audio_edit_block does not exist
there, and build_audio_tour ALWAYS archives+bumps on an edit. They pass once
LOCAL-755 lands.

Run: python3 -m pytest tests/test_local755_organiser_audio_updates.py -q
"""
import io
import os
import sys
import zipfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_UT, _ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)


# ════════════════════════════════════════════════════════════════════════════
# PART A — tour-editing refuses an organiser-audio edit (409)
# ════════════════════════════════════════════════════════════════════════════
import tour_editing_phase2 as p2  # noqa: E402  (repo root)


class _EditFakeCursor:
    """A scripted cursor: each execute matches the FIRST (needle, rows) whose
    needle is a substring of the normalised SQL."""

    def __init__(self, plan):
        self._plan = plan
        self._rows = []
        self.connection = self

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        for needle, rows in self._plan:
            if needle.lower() in text:
                self._rows = list(rows(params) if callable(rows) else rows)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass

    def rollback(self):
        pass

    def commit(self):
        pass


class OrganiserAudioEditBlockTest(unittest.TestCase):
    def setUp(self):
        # tour_source_kind caches a one-off information_schema probe; reset it so
        # the scripted cursor's answer is honoured per test.
        import community_tours_service as cts
        cts._HAS_SOURCE_KIND_COLUMN = None

    _PROBE = ("information_schema.columns", [(1,)])  # source_kind column exists

    def test_organiser_audio_tour_is_refused_409(self):
        # The tour's source row reports source_kind='organiser_audio'.
        cur = _EditFakeCursor([
            self._PROBE,
            ("coalesce(orig.source_kind, t.source_kind)",
             [("organiser_audio",)]),
        ])
        result = p2._organiser_audio_edit_block(cur, "734")
        self.assertIsNotNone(result, "an organiser-audio tour must be refused")
        status, body = result
        self.assertEqual(status, 409)
        self.assertEqual(body.get("error_code"), "organiser_audio_not_editable")

    def test_generated_tour_is_allowed(self):
        cur = _EditFakeCursor([
            self._PROBE,
            ("coalesce(orig.source_kind, t.source_kind)", [(None,)]),
        ])
        self.assertIsNone(
            p2._organiser_audio_edit_block(cur, "421"),
            "an ordinary/generated tour must not be refused")

    def test_unknown_tour_is_allowed(self):
        # No row → not an organiser-audio tour → the guard does not block (the
        # downstream TOUR_NOT_FOUND path handles a genuinely missing tour).
        cur = _EditFakeCursor([self._PROBE])
        self.assertIsNone(p2._organiser_audio_edit_block(cur, "999999"))

    def test_bulk_save_core_returns_409_for_organiser_audio(self):
        """End-to-end through the REAL _bulk_save_core: an organiser-audio tour
        is refused 409 organiser_audio_not_editable BEFORE any build/metering,
        so no organiser audio/text ever reaches TTS."""
        import community_tours_service as cts
        cts._HAS_SOURCE_KIND_COLUMN = None
        orig_conn = p2.get_db_connection

        class _Conn:
            def cursor(self):
                return _EditFakeCursor([
                    ("information_schema.columns", [(1,)]),
                    ("coalesce(orig.source_kind, t.source_kind)",
                     [("organiser_audio",)]),
                ])

            def close(self):
                pass

        p2.get_db_connection = lambda: _Conn()
        try:
            flask_app = p2.app
            with flask_app.test_request_context():
                resp = p2._bulk_save_core("734", {
                    "user_id": "owner-1",
                    "stops": [{"stop_number": 1, "text": "x", "action": "modify"}],
                })
            # Flask returns (response, status) from jsonify tuples.
            body, status = resp if isinstance(resp, tuple) else (resp, 200)
            self.assertEqual(status, 409, f"expected 409, got {status}")
            payload = body.get_json()
            self.assertEqual(payload.get("error_code"),
                             "organiser_audio_not_editable")
        finally:
            p2.get_db_connection = orig_conn


# ════════════════════════════════════════════════════════════════════════════
# PART B — the builder bumps the version only with the checkbox
# ════════════════════════════════════════════════════════════════════════════
import communities_api  # noqa: E402  (user-tracking/)


class _FakeCursor:
    def __init__(self, plan, writes):
        self._plan = plan
        self._rows = []
        self.writes = writes
        self.connection = self

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        self.writes.append((text, params))
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result(params) if callable(result) else result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass

    def rollback(self):
        pass


class _FakeConn:
    def __init__(self, plan, writes):
        self._plan = plan
        self.writes = writes

    def cursor(self):
        return _FakeCursor(self._plan, self.writes)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


_OWNER = 'owner-123'
_COMMUNITY_ID = 7


def _community_row_rows(owner):
    return [(
        _COMMUNITY_ID, owner, 'The Owls', 'desc', 'Org', None, None, None,
        None, None, False, True, 'listed', 42.1, -71.2, 'CODE1234', None, False,
        'active', None, None, None, None, None, 'week',
    )]


class BuilderCheckboxVersionBumpTest(unittest.TestCase):
    def setUp(self):
        communities_api.API_KEY = ''
        os.environ['ALLOW_UNAUTHENTICATED_ENTITLEMENTS'] = 'true'
        from flask import Flask
        flask_app = Flask(__name__)
        flask_app.register_blueprint(communities_api.communities_bp)
        self.client = flask_app.test_client()
        self._orig_get_db = communities_api._get_db
        communities_api._audio_url_check = lambda url: (True, 'audio/mpeg', 1000)

    def tearDown(self):
        communities_api._get_db = self._orig_get_db

    def _install(self, plan):
        writes = []
        communities_api._get_db = lambda: _FakeConn(plan, writes)
        return writes

    def _edit_body(self, **over):
        body = {
            'user_id': _OWNER,
            'tour_name': 'River Walk (typo fixed)',
            'tour_type': 'walking',
            'rights_accepted': True,
            'visibility': 'members',
            'tour_id': 99,
            'stops': [
                {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
                 'text': 'Heart of town.', 'audio_url': 'https://host/a1.mp3'},
                {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
                 'text': 'A mill.', 'audio_url': 'https://host/a2.mp3'},
            ],
        }
        body.update(over)
        return body

    def _edit_plan(self):
        return [
            ("from communities where id", _community_row_rows(_OWNER)),
            ("select id, source_kind", [(99, 'organiser_audio', 'old content')]),
            ("coalesce(max(version_no), 0)", [(0,)]),
            ("insert into audio_tour_versions", [(1,)]),
            ("update audio_tours", lambda p: []),
        ]

    def test_edit_without_checkbox_keeps_version_no_archive(self):
        """A silent save (typo fix) — no notify_members — does NOT archive the
        old content and the version stays at 1."""
        writes = self._install(self._edit_plan())
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._edit_body())  # notify_members absent/false
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertFalse(
            any('insert into audio_tour_versions' in w[0] for w in writes),
            "a silent save must NOT archive/bump the version")
        self.assertEqual(r.get_json().get('version'), 1,
                         "the version stays when the box is unticked")

    def test_edit_with_checkbox_bumps_version(self):
        """'I changed this tour — tell my members' — notify_members=true —
        archives the old content (version bump), the version rises to 2."""
        writes = self._install(self._edit_plan())
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._edit_body(notify_members=True))
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(
            any('insert into audio_tour_versions' in w[0] for w in writes),
            "the checkbox must archive the old content (version bump)")
        self.assertEqual(r.get_json().get('version'), 2,
                         "MAX(0)+1 archived → the new live version is 2")


if __name__ == '__main__':
    unittest.main(verbosity=2)
