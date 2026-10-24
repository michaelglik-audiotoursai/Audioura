#!/usr/bin/env python3
"""test_local753_member_discovery.py — LOCAL-753 / D707 (RED first).

DECISION D707 (LEAD 2026-10-23): a community's MEMBERS-ONLY tour must be visible
to an ACTIVE MEMBER or the OWNER on /tours-near, /search, /tour-by-code and
/tour-info (with the community badge); everyone else still never sees it. This
undoes, for discovery, the blanket D663 §3 rule that hid members-only tours from
EVERYONE on those endpoints. A PUBLIC community tour is unchanged — visible to
all with the badge; download still needs a membership (402 for a non-member).

map_delivery/app.py deploys as its own image and cannot import
community_tours_service, so the decision is a tiny PURE helper there:

    _discovery_visible(community_id, visibility, is_member) -> bool

  * ordinary tour (community_id is None)                 → True  (always shown);
  * public community tour                                → True  (badge, all);
  * members-only community tour, viewer IS member/owner  → True  (badge, member);
  * members-only community tour, viewer is NOT a member  → False (hidden).

Keeping the rule in one pure function lets the four list/detail endpoints share
it and this test exercise it hermetically (no Flask, no Postgres). The endpoints
pass is_member = _is_active_member(cur, user_id, community_id) — a separate,
already-tested read.

Run: python3 -m pytest tests/test_local753_member_discovery.py -q
"""
import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")


def _load_map_app():
    """Import map_delivery/app.py with Flask/psycopg2/boto3 stubbed so the pure
    helpers are reachable without a running service or DB. We only touch
    _discovery_visible, a dependency-free function."""
    # Stub flask so `from flask import Flask, ...` at import time succeeds.
    if "flask" not in sys.modules:
        flask = types.ModuleType("flask")

        class _App:
            def __init__(self, *a, **k):
                pass

            def route(self, *a, **k):
                def _wrap(fn):
                    return fn
                return _wrap

            def after_request(self, fn):
                return fn

            def before_request(self, fn):
                return fn

        flask.Flask = _App
        flask.request = types.SimpleNamespace(args={}, method="GET")
        flask.jsonify = lambda *a, **k: (a[0] if a else k)
        flask.make_response = lambda *a, **k: None
        flask.send_file = lambda *a, **k: None
        flask.Response = object
        flask.stream_with_context = lambda gen: gen
        flask.abort = lambda *a, **k: None
        sys.modules["flask"] = flask
    if "flask_cors" not in sys.modules:
        fc = types.ModuleType("flask_cors")
        fc.CORS = lambda *a, **k: None
        sys.modules["flask_cors"] = fc
    if "psycopg2" not in sys.modules:
        pg = types.ModuleType("psycopg2")
        pg.connect = lambda *a, **k: None
        pg.extras = types.ModuleType("psycopg2.extras")
        sys.modules["psycopg2"] = pg
        sys.modules["psycopg2.extras"] = pg.extras
    if "boto3" not in sys.modules:
        b = types.ModuleType("boto3")
        b.client = lambda *a, **k: object()
        sys.modules["boto3"] = b
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")

    if _MAPDIR not in sys.path:
        sys.path.insert(0, _MAPDIR)
    spec = importlib.util.spec_from_file_location(
        "map_delivery_app_under_test", os.path.join(_MAPDIR, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DiscoveryVisibleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _load_map_app()

    def test_helper_exists(self):
        self.assertTrue(
            hasattr(self.app, "_discovery_visible"),
            "_discovery_visible is missing — the list endpoints cannot show a "
            "members-only community tour to its members (LOCAL-753 / D707).")

    def test_ordinary_tour_always_visible(self):
        self.assertTrue(self.app._discovery_visible(None, None, is_member=False))
        self.assertTrue(self.app._discovery_visible(None, None, is_member=True))

    def test_public_community_tour_visible_to_everyone(self):
        self.assertTrue(self.app._discovery_visible(10, "public", is_member=False))
        self.assertTrue(self.app._discovery_visible(10, "public", is_member=True))

    def test_members_only_visible_to_member(self):
        self.assertTrue(
            self.app._discovery_visible(10, "members", is_member=True),
            "an active member/owner must SEE the community's members-only tour.")

    def test_members_only_hidden_from_non_member(self):
        self.assertFalse(
            self.app._discovery_visible(10, "members", is_member=False),
            "a non-member must NOT see a members-only community tour.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
