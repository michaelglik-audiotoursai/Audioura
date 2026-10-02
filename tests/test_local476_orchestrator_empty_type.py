#!/usr/bin/env python3
"""
LOCAL-476 — Test the service the app actually calls.

LOCAL-474 relaxed the same validation guard in TWO services:

    generate_tour_text_service.py   /generate               (text generator)
    tour_orchestrator_service.py    /generate-complete-tour (orchestrator)

...but its suite only drove the text generator's test_client. LEAD's
break-the-code check (D242) restored the old guard in the ORCHESTRATOR and the
suite stayed green — the endpoint Michael's phone hits, the one that 400'd in
production on 2026-09-03, had NO coverage (D418/D421: green over the unverified
path).

This suite closes that gap. It drives tour_orchestrator_service.app with a
Flask test_client and asserts the /generate-complete-tour VALIDATION GATE:

  AC1  empty tour_type      -> ACCEPTED  (200, queued)
  AC1  missing tour_type key-> ACCEPTED  (200, queued)
  AC3  missing location     -> 400, message names 'location'
  AC2  explicit tour_type   -> still wins (accepted, threaded through)

Nothing real runs: the quota check, the usage-recording DB insert, user
tracking, and the background generation thread are all stubbed. We are testing
the validation gate, not generation.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tour_orchestrator_service as orch


# The exact production payload location that 400'd on 2026-09-03.
BREAD_THYME = "Bread Thyme restaurant tour in West Roxbury, MA"


class TestOrchestratorValidationGate(unittest.TestCase):
    """The gate on /generate-complete-tour — the endpoint the app actually calls.

    Everything downstream of the location/tour_type checks (quota, DB, tracking,
    the generation thread) is stubbed, so a request that PASSES the gate returns
    the queued response without touching a live service.
    """

    @classmethod
    def setUpClass(cls):
        cls.orch = orch
        cls.app = orch.app.test_client()

    def _post(self, payload):
        """POST to /generate-complete-tour with all real side effects stubbed.

        Stubs, in the order the handler reaches them:
          - entitlements.check_tour_quota  -> always allowed, no plan/DB lookup
          - psycopg2.connect               -> usage-recording INSERT is a no-op
          - track_user_tour                -> no user-tracking side effect
          - threading.Thread               -> the generation thread never starts
        Only requests that clear the validation gate reach these stubs; a gate
        rejection (e.g. missing location) returns 400 before any of them run.
        """
        quota_ok = {"allowed": True, "clamped_stops": 1, "used": 0, "remaining": 99}

        fake_thread = mock.MagicMock()
        fake_thread.start = lambda: None
        fake_thread.is_alive = lambda: False

        with mock.patch("entitlements.check_tour_quota", return_value=quota_ok), \
             mock.patch("psycopg2.connect") as _pg, \
             mock.patch.object(self.orch, "track_user_tour", return_value=None), \
             mock.patch.object(self.orch.threading, "Thread", return_value=fake_thread):
            # Make the usage-INSERT fetchone() return a row id if it is reached.
            _pg.return_value.cursor.return_value.fetchone.return_value = [1]
            return self.app.post("/generate-complete-tour", json=payload)

    def _base_payload(self, **overrides):
        payload = {
            "location": BREAD_THYME,
            "tour_type": "",
            "total_stops": 1,
            "user_id": "test-user-476",
            "request_string": BREAD_THYME,
        }
        payload.update(overrides)
        return payload

    # --- AC1: empty / missing tour_type is ACCEPTED on the orchestrator ------

    def test_ac1_empty_tour_type_is_accepted(self):
        resp = self._post(self._base_payload(tour_type=""))
        self.assertEqual(
            resp.status_code, 200,
            f"empty tour_type must be accepted by the orchestrator, "
            f"got {resp.status_code}: {resp.data}",
        )
        self.assertEqual(resp.get_json().get("status"), "queued")

    def test_ac1_missing_tour_type_key_is_accepted(self):
        payload = self._base_payload()
        payload.pop("tour_type")
        resp = self._post(payload)
        self.assertEqual(
            resp.status_code, 200,
            f"missing tour_type key must be accepted by the orchestrator, "
            f"got {resp.status_code}: {resp.data}",
        )
        self.assertEqual(resp.get_json().get("status"), "queued")

    # --- AC3: missing / empty location still 400s, and it names 'location' ---

    def test_ac3_missing_location_still_400s_and_names_location(self):
        payload = self._base_payload()
        payload.pop("location")
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400,
                         f"missing location must 400, got {resp.status_code}")
        self.assertIn("location", resp.get_json().get("error", "").lower(),
                      "the 400 message must name 'location'")

    def test_ac3_empty_location_still_400s(self):
        resp = self._post(self._base_payload(location="", tour_type=""))
        self.assertEqual(resp.status_code, 400,
                         f"empty location must 400, got {resp.status_code}")
        self.assertIn("location", resp.get_json().get("error", "").lower())

    # --- AC2: an explicit tour_type is still honoured (accepted) -------------

    def test_ac2_explicit_tour_type_still_wins(self):
        resp = self._post(self._base_payload(tour_type="restaurant"))
        self.assertEqual(
            resp.status_code, 200,
            f"explicit tour_type must still be accepted, got {resp.status_code}",
        )
        self.assertEqual(resp.get_json().get("status"), "queued")


if __name__ == "__main__":
    unittest.main(verbosity=2)
