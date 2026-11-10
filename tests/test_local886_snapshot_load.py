#!/usr/bin/env python3
"""LOCAL-886 offline test: load the cloud cache snapshot into an EMPTY disposable
proof DB (own-port postgres, no network/LLM) and assert 122 landmark_wiki_cache rows.
Skips when the snapshot or the proof DB is unavailable."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import run_cloud_parity_proof as h  # noqa: E402

SNAP = os.path.expanduser("~/Audioura/cloud_cache_snapshot")
DB = h._SNAP_DB


def _can_connect():
    try:
        import psycopg2
        psycopg2.connect(DB).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(os.path.isdir(SNAP) and _can_connect(), "snapshot or proof DB absent")
class SnapshotLoad(unittest.TestCase):
    def test_load_into_empty_db_gives_122_wiki_rows(self):
        import psycopg2
        conn = psycopg2.connect(DB)
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('landmark_wiki_cache')")
            if cur.fetchone()[0] is not None:
                cur.execute("SELECT COUNT(*) FROM landmark_wiki_cache")
                self.assertEqual(cur.fetchone()[0], 0, "proof DB must start empty")
        conn.close()
        res = h.load_snapshot(SNAP, DB, log=lambda m: None)
        self.assertEqual(res["landmark_wiki_cache"], (0, 122))
        self.assertEqual(res["landmark_coord_cache"][1], 179)
        # idempotent: a second load adds nothing
        res2 = h.load_snapshot(SNAP, DB, log=lambda m: None)
        self.assertEqual(res2["landmark_wiki_cache"], (122, 122))

    def test_refuses_shared_db(self):
        with self.assertRaises(RuntimeError):
            h.load_snapshot(SNAP, "postgresql://a:b@localhost:5433/x")


if __name__ == "__main__":
    unittest.main()
