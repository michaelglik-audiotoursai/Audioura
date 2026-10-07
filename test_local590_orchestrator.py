"""
LOCAL-590 integration test — stop_pool_orchestrator end-to-end (mocked generator).
==================================================================================
Exercises maybe_generate_with_pool against the REAL pool store (dev Postgres,
isolated UUID identity, never DELETE) with a MOCKED generator so no LLM/network
is touched. Proves the reuse economics Michael asked for:

  * Building, N > K: the generator is asked for EXACTLY N-K new stops with the
    pooled titles excluded; the delivered tour reuses all K pooled narrations
    verbatim and places the N-K new stops BEFORE them; reused/new counts match.
  * Building, N <= K: NO generation happens (generator mock asserts it is not
    called), N stops are served from the pool.
  * Classifier routes museum → building (new-before-pooled) and walking → outdoor
    (route re-sequenced).

ZERO PRODUCTION WRITES (LOCAL-601).
===================================
This suite used to store a fresh ``loc:zz_isolated_*`` venue into the SHARED
``public.stop_pool`` on every run (two explicit ``store_delivered_tour`` seeds
plus the ones ``maybe_generate_with_pool`` issues internally) and never cleaned
up — the dominant source of the 927 test rows that accumulated in the dev
Postgres pool Michael's app reads from. It now:

  * resolves the DB via ``db_connection.get_db_config`` (``audiotours_test`` under
    pytest — never production), and
  * runs every DB test inside a private throwaway schema (LOCAL-597B's mechanism,
    extracted to ``tests/_isolated_db.py``): ``PGOPTIONS=-c search_path=<schema>,
    public`` routes every connection — the ones this file opens AND the ones
    ``stop_pool_store`` / the orchestrator open internally — at a schema whose
    ``stop_pool`` shadows ``public.stop_pool``. ``tearDownModule`` drops the
    schema (CASCADE) and asserts ``public`` row counts are identical before and
    after. No row ever lands in ``public``; there is no DELETE anywhere.

If the DB is unreachable the DB classes SKIP rather than fail — the pure logic is
covered by the no-DB suites.
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# tests/ holds the shared isolation helper and db_connection resolver.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

from db_connection import get_db_config
from _isolated_db import IsolatedSchema

# Resolve the DB the shared helper picks (audiotours_test under pytest) and point
# BOTH this file's DB_URL AND any env-var-based connection at it, so the pool
# store (which connects via the passed db_url) and the orchestrator hit the same
# database. The throwaway schema makes the choice doubly safe: even if this
# resolved to production, the writes would land in the schema, not public.
_cfg = get_db_config()
os.environ.setdefault("DB_HOST", _cfg["host"])
os.environ.setdefault("DB_PORT", _cfg["port"])
DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{_cfg['user']}:{_cfg['password']}@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}")

import stop_pool_store as pool
import stop_pool_orchestrator as orch

# ─── Throwaway-schema isolation (LOCAL-601) ──────────────────────────────────
# Only stop_pool is written by this suite (directly and via the orchestrator's
# internal store_delivered_tour), so that is the single table to clone and prove
# unchanged. db_url is passed explicitly so the proof/admin connection targets
# the exact DB the pool store writes to.
_ISO = IsolatedSchema(
    prefix="t590",
    clone_tables=["stop_pool"],
    proof_tables=["stop_pool"],
    db_url=DB_URL,
    banner="LOCAL-590",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


def _db_up():
    return _ISO.db_up()


# A delivered 5-stop museum tour to seed the pool (current format).
def _seed_tour(titles):
    body = "Step-by-Step Audio Guided Tour: ZZ Museum\nTour-Category: museum\n\n"
    for i, t in enumerate(titles):
        body += f"Stop {i+1}: {t}\n\n"
        body += "Address: 1 Test St\n\n"
        body += f"Orientation: Stand before {t}.\n\n"
        body += f"This is the pooled narration body for {t}. It is reusable prose.\n\n"
        if i < len(titles) - 1:
            body += f"Directions: Proceed to {titles[i+1]}.\n\n"
    body += (f"From {titles[0]} to {titles[-1]}, you have followed the thread.\n\n"
             f"That's {len(titles)} stops.\n\n"
             "Sources: This tour draws on information from example.org.\n")
    return body


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestOrchestratorBuilding(unittest.TestCase):
    def setUp(self):
        self.loc = "ZZ_ISOLATED_ORCH_" + uuid.uuid4().hex[:8]
        self.ttype = "museum"
        self.pooled_titles = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        pool.store_delivered_tour(self.loc, self.ttype, _seed_tour(self.pooled_titles), DB_URL)

    def test_n_greater_than_k_generates_only_new(self):
        # Mock generator: must be asked for EXACTLY 2 new stops, excluding pooled.
        calls = {}

        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            calls["total_stops"] = total_stops
            calls["exclude_titles"] = list(exclude_titles or [])
            # Deliver 2 brand-new stops.
            text = _seed_tour(["New One", "New Two"])
            return text, output_file, (None, None)

        out = orch.maybe_generate_with_pool(
            self.loc, self.ttype, 7, DB_URL, generate_fn=fake_generate,
        )
        self.assertIsNotNone(out)
        # Asked for exactly N-K = 2 new stops.
        self.assertEqual(calls["total_stops"], 2)
        # Pooled titles were passed as the exclusion.
        self.assertEqual(set(calls["exclude_titles"]), set(self.pooled_titles))
        # Counts: 5 reused, 2 new.
        self.assertEqual(out["reused_stops"], 5)
        self.assertEqual(out["new_stops"], 2)
        self.assertFalse(out["served_from_pool_only"])
        # New stops placed BEFORE pooled ones.
        text = out["text"]
        self.assertIn("Stop 1: New One", text)
        self.assertIn("Stop 2: New Two", text)
        self.assertIn("Stop 3: Alpha", text)
        # Pooled narration reused verbatim.
        for t in self.pooled_titles:
            self.assertIn(f"pooled narration body for {t}", text)

    def test_n_leq_k_serves_from_pool_without_generating(self):
        def fail_generate(*a, **k):
            raise AssertionError("generator must NOT be called when N <= K")

        out = orch.maybe_generate_with_pool(
            self.loc, self.ttype, 3, DB_URL, generate_fn=fail_generate,
        )
        self.assertIsNotNone(out)
        self.assertTrue(out["served_from_pool_only"])
        self.assertEqual(out["new_stops"], 0)
        self.assertEqual(out["reused_stops"], 3)
        self.assertEqual(out["new_cost"], 0.0)
        # Exactly 3 stops delivered, in pool order.
        self.assertIn("Stop 1: Alpha", out["text"])
        self.assertIn("Stop 3: Gamma", out["text"])
        self.assertNotIn("Stop 4:", out["text"])

    def test_empty_pool_returns_none(self):
        empty_loc = "ZZ_ISOLATED_EMPTY_" + uuid.uuid4().hex[:8]
        out = orch.maybe_generate_with_pool(
            empty_loc, "museum", 5, DB_URL, generate_fn=lambda *a, **k: ("x", None, (None, None)),
        )
        self.assertIsNone(out)  # empty pool → normal generation path


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestOrchestratorOutdoor(unittest.TestCase):
    def test_walking_resequences_and_reuses(self):
        loc = "ZZ_ISOLATED_WALK_" + uuid.uuid4().hex[:8]
        ttype = "walking"
        # Seed 4 pooled walking stops with coordinates in the raw blocks is not
        # needed — the orchestrator reads coordinates from the pooled 'coordinates'
        # field; seed a tour that carries them.
        body = "Step-by-Step Audio Guided Tour: ZZ Common - Walking Tour\nTour-Category: walking\n\n"
        stops = [("Common A", "42.0, -71.0"), ("Common B", "42.0, -71.1"),
                 ("Common C", "42.0, -71.2"), ("Common D", "42.0, -71.3")]
        for i, (t, c) in enumerate(stops):
            body += f"Stop {i+1}: {t}\n\nAddress: Boston Common\n\nCoordinates: {c}\n\n"
            body += f"Walking narration for {t}.\n\n"
            if i < len(stops) - 1:
                body += f"Directions: Continue to {stops[i+1][0]}.\n\n"
        body += "From Common A to Common D, you have followed the thread.\n\nThat's 4 stops.\n\n"
        pool.store_delivered_tour(loc, ttype, body, DB_URL)

        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            nb = ("Step-by-Step Audio Guided Tour: ZZ Common - Walking Tour\n"
                  "Tour-Category: walking\n\n"
                  "Stop 1: Common E\n\nAddress: Boston Common\n\nCoordinates: 42.0, -71.15\n\n"
                  "Walking narration for Common E.\n\n"
                  "Stop 2: Common F\n\nAddress: Boston Common\n\nCoordinates: 42.0, -71.25\n\n"
                  "Walking narration for Common F.\n\n"
                  "From Common E to Common F, you have followed the thread.\n\nThat's 2 stops.\n")
            return nb, output_file, (None, None)

        out = orch.maybe_generate_with_pool(loc, ttype, 6, DB_URL, generate_fn=fake_generate)
        self.assertIsNotNone(out)
        self.assertEqual(out["new_stops"], 2)
        self.assertEqual(out["reused_stops"], 4)   # 4 pooled narrations untouched
        # Some transitions adjacent to insertions were rewritten.
        self.assertGreaterEqual(out["rewritten_transitions"], 1)
        # All 6 stops present.
        for t in ["Common A", "Common B", "Common C", "Common D", "Common E", "Common F"]:
            self.assertIn(t, out["text"])


class TestAudioReuseContract(unittest.TestCase):
    """LOCAL-590 step 5: the pool's audio-reuse PRECONDITION, verifiable without
    a TTS backend. Reused stops keep byte-identical narration → identical audio
    identity (so a text+voice+engine-keyed renderer reuses the audio); new or
    transition-rewritten stops have different text → different identity → new
    audio. Also: a voice/engine change forces a fresh render even for identical
    text."""

    def test_identical_narration_same_identity(self):
        pooled_text = "This is the pooled narration body for Alpha. It is reusable prose."
        reused_text = pooled_text  # the pool reuses it verbatim
        self.assertEqual(orch.audio_reuse_identity(pooled_text, "Joanna"),
                         orch.audio_reuse_identity(reused_text, "Joanna"))

    def test_new_stop_text_differs(self):
        a = orch.audio_reuse_identity("Fresh narration one.", "Joanna")
        b = orch.audio_reuse_identity("This is the pooled narration body for Alpha.", "Joanna")
        self.assertNotEqual(a, b)

    def test_voice_change_forces_new_audio(self):
        text = "Same narration, different voice."
        self.assertNotEqual(orch.audio_reuse_identity(text, "Joanna"),
                            orch.audio_reuse_identity(text, "Matthew"))

    def test_engine_tracks_voice(self):
        # Joanna is a neural voice; a non-neural voice resolves to standard.
        self.assertEqual(orch.audio_reuse_identity("x", "Joanna")[2], "neural")
        self.assertEqual(orch.audio_reuse_identity("x", "Tatyana")[2], "standard")


if __name__ == "__main__":
    unittest.main(verbosity=2)