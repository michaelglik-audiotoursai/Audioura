"""LOCAL-631 — offline concurrency isolation of per-job generator state.

Bench R0 ran 6 tours at once on the shared generator (one process, one thread
per job). The Musee Rodin (tour 498) spoke the Rijksmuseum's (tour 499) opening
hours and admission price, because the per-job "last generation" holders were
plain MODULE GLOBALS — one object shared by every job thread. Whichever job
wrote last won, and the loser read the winner's facts.

This test reproduces the exact mechanism OFFLINE (no network): it runs several
generate_tour_text-level jobs concurrently in threads, each a different venue,
each writing the holders the real pipeline writes —
  * generate_tour_text._LAST_VENUE_PREFLIGHT  (hours + admission)
  * generate_tour_text._LAST_DELIVERY_PATH
  * generate_tour_text._LAST_GENERATION_COST
  * generate_tour_text._LAST_POI_LIST         (the venue's stops)
  * generate_tour_text._DIRECT_SNIPPETS_PER_STOP
  * content_qa_runner.FACTUAL_FAIL_COUNT / FAIL_COUNT / G4_UNGROUNDED_SENTENCES
  * story_leads grounding counters
— then, after a deliberate interleave, reads them back through the SAME
cross-module attribute interface the service uses and asserts that no venue's
hours, admission, stops, QA state or grounding counts appear in another's.

A `_shared_global_control` case shows the pre-fix behaviour (a plain module
global) DOES bleed, so the test proves the fix rather than passing vacuously.
"""
import threading
import time
import unittest

import generate_tour_text as gtt
import content_qa_runner as cqr
import story_leads as sl


# Two distinct venues with DISTINCT practical facts — the bench R0 pair.
VENUES = {
    "rodin": {
        "hours": "Tuesday to Sunday, 10:00 AM to 6:30 PM",
        "admission": "Adult admission is €14",
        "stops": ["The Thinker", "The Gates of Hell"],
        "factual_fails": 0,
        "g4": [],
        "grounding_queries": 3,
        "cost": 0.57,
        "path": "fresh",
    },
    "rijks": {
        "hours": "Open daily 9:00 AM to 5:00 PM",
        "admission": "Adult admission is €25; entry is free for visitors under 18",
        "stops": ["The Night Watch", "The Milkmaid"],
        "factual_fails": 1,
        "g4": ["This wing opened in 1885."],
        "grounding_queries": 7,
        "cost": 0.91,
        "path": "pool",
    },
}


def _run_job(venue_key, barrier, results, errors):
    """Simulate one generate_tour_text-level job on its own thread, writing the
    per-job holders exactly as the engine does, then reading them back the way
    the service does — with a barrier + sleep forcing the two jobs to interleave
    their writes before either reads."""
    try:
        spec = VENUES[venue_key]

        # Fresh thread => fresh contextvars context => holders start at defaults.
        # (If they were still shared globals, another already-started job may have
        # written them — so assert the clean baseline FIRST.)
        assert gtt._LAST_VENUE_PREFLIGHT == {}, (venue_key, "preflight not clean", gtt._LAST_VENUE_PREFLIGHT)
        assert gtt._LAST_POI_LIST == [], (venue_key, "poi not clean", gtt._LAST_POI_LIST)
        assert cqr.FACTUAL_FAIL_COUNT == 0, (venue_key, "qa not clean", cqr.FACTUAL_FAIL_COUNT)
        assert sl.get_grounding_queries() == 0, (venue_key, "grounding not clean")

        # --- WRITE this job's holders (engine side) -----------------------
        gtt._J._LAST_VENUE_PREFLIGHT = {
            "venue": venue_key,
            "hours": spec["hours"],
            "admission": spec["admission"],
        }
        gtt._J._LAST_DELIVERY_PATH = spec["path"]
        gtt._J._LAST_GENERATION_COST = {"total_cost": spec["cost"], "venue": venue_key}
        gtt._J._LAST_POI_LIST = list(spec["stops"])
        for i, s in enumerate(spec["stops"]):
            gtt._J._DIRECT_SNIPPETS_PER_STOP.setdefault(s, []).append({"venue": venue_key, "idx": i})

        # QA counters (content_qa_runner side)
        sl.reset_grounding_requests()
        for _ in range(spec["grounding_queries"]):
            sl._J._GROUNDING_QUERIES += 1
        cqr._J.FACTUAL_FAIL_COUNT = spec["factual_fails"]
        cqr._J.G4_UNGROUNDED_SENTENCES = list(spec["g4"])

        # Force the other job to write before anyone reads.
        barrier.wait(timeout=5)
        time.sleep(0.05)

        # --- READ back through the SERVICE interface (cross-module attrs) --
        got = {
            "preflight": dict(gtt._LAST_VENUE_PREFLIGHT),
            "path": gtt._LAST_DELIVERY_PATH,
            "cost": dict(gtt._LAST_GENERATION_COST),
            "stops": list(gtt._LAST_POI_LIST),
            "snippets": {k: list(v) for k, v in gtt._DIRECT_SNIPPETS_PER_STOP.items()},
            "factual_fails": cqr.FACTUAL_FAIL_COUNT,
            "g4": list(cqr.G4_UNGROUNDED_SENTENCES),
            "grounding_queries": sl.get_grounding_queries(),
        }
        results[venue_key] = got
    except Exception as e:  # pragma: no cover - surfaced by the test
        errors.append((venue_key, repr(e)))


class TestConcurrencyIsolation(unittest.TestCase):
    def test_two_concurrent_jobs_do_not_share_facts(self):
        """Rodin and Rijksmuseum generated at the same instant must each read
        back ONLY their own hours, admission, stops, QA state and grounding."""
        barrier = threading.Barrier(2)
        results, errors = {}, []
        threads = [
            threading.Thread(target=_run_job, args=(k, barrier, results, errors))
            for k in ("rodin", "rijks")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"job thread(s) raised: {errors}")
        self.assertEqual(set(results), {"rodin", "rijks"})

        for key, spec in VENUES.items():
            got = results[key]
            # Practical facts — the bench R0 symptom.
            self.assertEqual(got["preflight"]["venue"], key)
            self.assertEqual(got["preflight"]["hours"], spec["hours"])
            self.assertEqual(got["preflight"]["admission"], spec["admission"])
            # The other venue's facts must NOT appear.
            other = "rijks" if key == "rodin" else "rodin"
            self.assertNotIn(VENUES[other]["hours"], got["preflight"].values())
            self.assertNotIn(VENUES[other]["admission"], got["preflight"].values())
            # Stops, path, cost, QA, grounding — all this job's own.
            self.assertEqual(got["stops"], spec["stops"])
            self.assertEqual(got["path"], spec["path"])
            self.assertEqual(got["cost"]["venue"], key)
            self.assertAlmostEqual(got["cost"]["total_cost"], spec["cost"])
            self.assertEqual(got["factual_fails"], spec["factual_fails"])
            self.assertEqual(got["g4"], spec["g4"])
            self.assertEqual(got["grounding_queries"], spec["grounding_queries"])
            # Snippets dict holds only this venue's stops.
            self.assertEqual(set(got["snippets"]), set(spec["stops"]))
            for s, items in got["snippets"].items():
                for it in items:
                    self.assertEqual(it["venue"], key)

    def test_three_concurrent_jobs_each_isolated(self):
        """Three venues at once (bench R0 ran six) — pairwise non-contamination."""
        venues3 = {
            "rodin": VENUES["rodin"],
            "rijks": VENUES["rijks"],
            "orsay": {
                "hours": "Closed Mondays; otherwise 9:30 AM to 6:00 PM",
                "admission": "Adult admission is €16",
                "stops": ["Olympia", "Bal du moulin de la Galette"],
                "factual_fails": 0, "g4": [], "grounding_queries": 5,
                "cost": 0.73, "path": "cache",
            },
        }
        # Temporarily extend the module-level VENUES so _run_job can see orsay.
        VENUES["orsay"] = venues3["orsay"]
        try:
            barrier = threading.Barrier(3)
            results, errors = {}, []
            threads = [
                threading.Thread(target=_run_job, args=(k, barrier, results, errors))
                for k in venues3
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [], f"job thread(s) raised: {errors}")
            self.assertEqual(set(results), set(venues3))
            for key, spec in venues3.items():
                got = results[key]
                self.assertEqual(got["preflight"]["venue"], key)
                self.assertEqual(got["preflight"]["hours"], spec["hours"])
                self.assertEqual(got["preflight"]["admission"], spec["admission"])
                self.assertEqual(got["stops"], spec["stops"])
                self.assertEqual(got["grounding_queries"], spec["grounding_queries"])
        finally:
            VENUES.pop("orsay", None)

    def test_control_shared_global_would_bleed(self):
        """Guard against a vacuous pass: a PLAIN module global (the pre-fix
        design) MUST bleed across threads, proving the test can detect the bug."""
        import types
        shared = types.ModuleType("shared_global_control")
        shared.LAST_HOURS = None  # one object shared by all threads

        barrier = threading.Barrier(2)
        seen = {}

        def job(key, hours):
            shared.LAST_HOURS = hours
            barrier.wait(timeout=5)
            time.sleep(0.05)
            seen[key] = shared.LAST_HOURS

        t1 = threading.Thread(target=job, args=("rodin", "RODIN-HOURS"))
        t2 = threading.Thread(target=job, args=("rijks", "RIJKS-HOURS"))
        t1.start(); t2.start(); t1.join(); t2.join()
        # Both threads read whichever wrote last — they are NOT isolated.
        self.assertEqual(seen["rodin"], seen["rijks"],
                         "shared global unexpectedly isolated — control invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
