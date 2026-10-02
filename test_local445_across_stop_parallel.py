"""test_local445_across_stop_parallel.py — LOCAL-445 verification tests.

Tests bind directly to module-scope symbols (D242 #1):
  1. Across-stop parallelism: N stops × Xs completes in ~budget, not N×X
  2. Neutralisation: serialise → timing test goes red (LOCAL-441 pattern)
  3. Dead-host rule: second call to a cold host issues NO network request
  4. Dead-host fallback chain order verification
  5. Per-key in-flight map: duplicate candidates → only one LLM call
  6. Phase timer: basic functionality
"""
import time
import threading
import unittest
from unittest.mock import patch, MagicMock, call

import story_first
from dead_host_breaker import (
    mark_host_cold, is_host_cold, get_cold_hosts, reset_cold_hosts,
    extract_host, WIKIMEDIA_HOSTS, _WIKIMEDIA_GROUP,
)
from phase_timer import PhaseTimer


class TestAcrossStopParallelism(unittest.TestCase):
    """Verify that story_first_pipeline_batch runs stops concurrently."""

    def setUp(self):
        story_first.parallelise_across_stops()
        story_first.enable_story_seeking()

    def tearDown(self):
        story_first.parallelise_across_stops()
        story_first.enable_story_seeking()

    def _make_slow_pipeline(self, delay=5.0):
        """Create a mock that simulates a slow pipeline per stop."""
        def slow_pipeline(stop_data, fact_sheet='', snippets=None,
                         credit_line='', existing_search_results=None):
            time.sleep(delay)
            return {
                'stories': [{'text': f"Story about {stop_data.get('canonical_title', '')}",
                            'people': [], 'interest_score': 0.8, 'verified': True}],
                'anchor_facts': {},
                'seeking_result': {},
                'fullpage_fetch_result': {},
                'evaluation_count': 3,
                'prefilter_input_count': 10,
                'verified_count': 1,
                'elapsed_seconds': delay,
                'cost_usd': 0.001,
                'fallback': False,
                'budget_exhausted': False,
            }
        return slow_pipeline

    def _make_stop_entries(self, n=6):
        """Create N stop entries for batch testing."""
        return [
            {
                'name': f'Stop_{i}',
                'stop_data': {'canonical_title': f'Stop_{i}', 'artist': f'Artist_{i}'},
                'snippets': [],
                'credit_line': '',
                'existing_search_results': [],
            }
            for i in range(n)
        ]

    @patch('story_first.story_first_pipeline')
    def test_batch_completes_within_budget(self, mock_pipeline):
        """CORE TEST: 6 stops × 5s delay completes in ~budget, not ~30s."""
        n_stops = 6
        per_delay = 5.0
        budget = 12.0

        mock_pipeline.side_effect = self._make_slow_pipeline(delay=per_delay)

        stops = self._make_stop_entries(n_stops)

        start = time.time()
        results = story_first.story_first_pipeline_batch(stops, tour_budget_seconds=budget)
        elapsed = time.time() - start

        print(f"\n  [GREEN] {n_stops} stops × {per_delay}s each")
        print(f"  [GREEN] Budget: {budget}s")
        print(f"  [GREEN] Actual elapsed: {elapsed:.2f}s")
        print(f"  [GREEN] Serial would have been: {n_stops * per_delay:.0f}s")
        print(f"  [GREEN] Speedup: {(n_stops * per_delay) / max(elapsed, 0.1):.1f}x")

        # Must complete well under serial time
        self.assertLess(elapsed, budget + 2.0,
                       f"Batch took {elapsed:.1f}s, should be ≤{budget + 2.0}s")
        # All stops should have results
        self.assertEqual(len(results), n_stops)
        # Verify results contain stories
        for name, result in results.items():
            self.assertIn('stories', result)

    @patch('story_first.story_first_pipeline')
    def test_serial_neutralisation_goes_red(self, mock_pipeline):
        """NEUTRALISATION (D242 #1): serial mode makes timing test FAIL.

        When across-stop is serialised, the same workload that passes in parallel
        must take ~N×delay time, proving the parallelism is load-bearing.
        """
        n_stops = 6
        per_delay = 3.0
        budget = 40.0  # High budget so serial doesn't hit it

        mock_pipeline.side_effect = self._make_slow_pipeline(delay=per_delay)

        stops = self._make_stop_entries(n_stops)

        # Serial mode
        story_first.serialise_across_stops()
        start = time.time()
        results_serial = story_first.story_first_pipeline_batch(stops, tour_budget_seconds=budget)
        serial_elapsed = time.time() - start

        # Parallel mode
        story_first.parallelise_across_stops()
        start = time.time()
        results_parallel = story_first.story_first_pipeline_batch(stops, tour_budget_seconds=budget)
        parallel_elapsed = time.time() - start

        print(f"\n  [NEUTRALISATION] Serial: {serial_elapsed:.2f}s")
        print(f"  [NEUTRALISATION] Parallel: {parallel_elapsed:.2f}s")
        print(f"  [NEUTRALISATION] Ratio: {serial_elapsed / max(parallel_elapsed, 0.1):.1f}x")

        # Serial must be significantly slower than parallel
        # (At least 2x, since 6 × 3s serial = 18s vs parallel ≈ 3-4s)
        self.assertGreater(serial_elapsed, parallel_elapsed * 2.0,
                          f"Serial ({serial_elapsed:.1f}s) should be >2× parallel "
                          f"({parallel_elapsed:.1f}s)")

        # Both should produce results for all stops
        self.assertEqual(len(results_serial), n_stops)
        self.assertEqual(len(results_parallel), n_stops)

    @patch('story_first.story_first_pipeline')
    def test_tour_budget_cuts_off_slow_stops(self, mock_pipeline):
        """Tour-level budget prevents runaway: stops that don't finish are marked budget_exhausted."""
        n_stops = 6
        per_delay = 10.0  # Each stop takes 10s
        budget = 5.0  # Budget only allows ~1 batch of concurrent work

        mock_pipeline.side_effect = self._make_slow_pipeline(delay=per_delay)

        stops = self._make_stop_entries(n_stops)

        start = time.time()
        results = story_first.story_first_pipeline_batch(stops, tour_budget_seconds=budget)
        elapsed = time.time() - start

        print(f"\n  [BUDGET] {n_stops} stops × {per_delay}s, budget={budget}s")
        print(f"  [BUDGET] Elapsed: {elapsed:.2f}s")

        # Should not take much longer than budget
        self.assertLess(elapsed, budget + 3.0)

        # All stops have results (some budget_exhausted)
        self.assertEqual(len(results), n_stops)


class TestDeadHostBreaker(unittest.TestCase):
    """Verify Michael's dead-host rule: first failure marks cold, no retry."""

    def setUp(self):
        reset_cold_hosts()

    def tearDown(self):
        reset_cold_hosts()

    def test_extract_host_normalises(self):
        """extract_host normalises URLs to hostnames."""
        self.assertEqual(extract_host('https://www.example.com/page'), 'www.example.com')
        self.assertEqual(extract_host('http://api.museum.org:8080/v1/data'), 'api.museum.org')
        self.assertEqual(extract_host('example.com'), 'example.com')

    def test_wikimedia_bucket_rule(self):
        """All Wikimedia hosts map to the single 'wikimedia' group."""
        self.assertEqual(extract_host('https://en.wikipedia.org/wiki/Foo'), _WIKIMEDIA_GROUP)
        self.assertEqual(extract_host('https://fr.wikipedia.org/wiki/Bar'), _WIKIMEDIA_GROUP)
        self.assertEqual(extract_host('https://query.wikidata.org/sparql'), _WIKIMEDIA_GROUP)
        self.assertEqual(extract_host('https://www.wikidata.org/w/api.php'), _WIKIMEDIA_GROUP)

    def test_mark_cold_and_check(self):
        """After marking cold, is_host_cold returns True."""
        self.assertFalse(is_host_cold('https://example.com'))
        mark_host_cold('https://example.com', reason='test 429')
        self.assertTrue(is_host_cold('https://example.com'))

    def test_wikimedia_429_makes_all_wikimedia_cold(self):
        """A 429 on en.wikipedia.org makes query.wikidata.org cold too."""
        self.assertFalse(is_host_cold('https://query.wikidata.org'))
        # Mark en.wikipedia.org cold (simulating 429)
        mark_host_cold('https://en.wikipedia.org/wiki/Something')
        # Now query.wikidata.org should be cold (same bucket)
        self.assertTrue(is_host_cold('https://query.wikidata.org'))
        self.assertTrue(is_host_cold('https://fr.wikipedia.org'))

    def test_non_wikimedia_independent(self):
        """Non-Wikimedia hosts are independent."""
        mark_host_cold('https://example.com')
        self.assertFalse(is_host_cold('https://other.com'))

    @patch('work_story_searcher.urllib.request.urlopen')
    def test_p856_no_network_after_cold(self, mock_urlopen):
        """After host is cold, _check_wikidata_p856 issues NO network request."""
        import work_story_searcher as wss

        # First: mark Wikidata cold
        mark_host_cold('https://query.wikidata.org', reason='simulated 429')

        # Now call P856 — it should NOT call urlopen
        result = wss._check_wikidata_p856('example-museum.org')

        # [D495] Result must be `unverified`, not `tier3`. This assertion used to
        # read 'tier3' and that value was the bug: because
        # `batch_check_wikidata_p856` submits `_check_wikidata_p856` per domain,
        # the first failure marked the host cold and every remaining domain in
        # the run took THIS path — so one Wikidata hiccup demoted a whole run by
        # 5 points, the toured museum's own site included. "We could not reach
        # Wikidata" and "Wikidata answered, not an institution" are now different
        # verdicts. The no-network assertion below is what this test is FOR and
        # is unchanged.
        self.assertEqual(result, wss.TIER_UNVERIFIED)
        # NO network call issued
        mock_urlopen.assert_not_called()
        print(f"\n  [DEAD-HOST] Second call to cold host: NO network request ✓")

    @patch('work_story_searcher.urllib.request.urlopen')
    def test_p856_marks_cold_on_first_429(self, mock_urlopen):
        """First 429 marks the host cold; second call short-circuits."""
        import work_story_searcher as wss
        import urllib.error

        # Simulate 429
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://query.wikidata.org/sparql', 429, 'Too Many Requests', {}, None
        )

        # First call — should hit the network and get 429
        result1 = wss._check_wikidata_p856('domain-a.org')
        self.assertEqual(result1, 'tier3')
        self.assertEqual(mock_urlopen.call_count, 1)

        # Host should now be cold
        self.assertTrue(is_host_cold('https://query.wikidata.org'))

        # Second call — should NOT hit the network
        mock_urlopen.reset_mock()
        result2 = wss._check_wikidata_p856('domain-b.org')
        self.assertEqual(result2, 'tier3')
        mock_urlopen.assert_not_called()
        print(f"\n  [DEAD-HOST] First 429 marks cold, second call short-circuits ✓")

    @patch('work_story_searcher.urllib.request.urlopen')
    def test_p856_marks_cold_on_timeout(self, mock_urlopen):
        """First timeout marks the host cold."""
        import work_story_searcher as wss

        # Simulate timeout
        mock_urlopen.side_effect = TimeoutError("Connection timed out")

        result = wss._check_wikidata_p856('timeout-domain.org')
        self.assertEqual(result, 'tier3')
        self.assertTrue(is_host_cold('https://query.wikidata.org'))

    def test_reset_cold_hosts(self):
        """reset_cold_hosts clears all state (for test teardown)."""
        mark_host_cold('https://example.com')
        mark_host_cold('https://query.wikidata.org')
        self.assertEqual(len(get_cold_hosts()), 2)
        reset_cold_hosts()
        self.assertEqual(len(get_cold_hosts()), 0)
        self.assertFalse(is_host_cold('https://example.com'))

    def test_thread_safety(self):
        """mark_host_cold and is_host_cold are thread-safe."""
        results = []

        def mark_and_check(host, delay):
            time.sleep(delay)
            mark_host_cold(host)
            results.append(is_host_cold(host))

        threads = [
            threading.Thread(target=mark_and_check, args=(f'host-{i}.com', 0.01 * i))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should report True after marking
        self.assertEqual(len(results), 20)
        self.assertTrue(all(results))


class TestPerKeyInflight(unittest.TestCase):
    """Verify that duplicate candidates across stops don't cause duplicate LLM calls."""

    def setUp(self):
        # Clear caches
        from story_gate import _verdict_cache
        _verdict_cache.clear()
        story_first._inflight_events.clear()
        story_first._inflight_results.clear()

    def tearDown(self):
        from story_gate import _verdict_cache
        _verdict_cache.clear()
        story_first._inflight_events.clear()
        story_first._inflight_results.clear()

    @patch('story_gate.classify_story_unit')
    def test_duplicate_candidates_single_llm_call(self, mock_classify):
        """When 3 threads race on the same text, only 1 LLM call is made."""
        candidate_text = (
            "Henri Matisse was deeply moved by the light of the Côte d'Azur. "
            "He settled in Nice in 1917 and spent the rest of his life there. "
            "The chapel at Vence represents his spiritual testament to the region."
        )

        # Mock: classify returns is_story=True, takes 1s
        def slow_classify(text):
            time.sleep(1.0)
            return {
                'is_story': True,
                'reason': 'narrative arc present',
                'emotional_content': 3,
                'new_information': 4,
                'deduction': 0,
                'cost_usd': 0.001,
                'from_cache': False,
            }

        mock_classify.side_effect = slow_classify

        results = [None] * 3

        def classify_thread(idx):
            results[idx] = story_first._classify_single_candidate(candidate_text, idx)

        threads = [threading.Thread(target=classify_thread, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only 1 LLM call should have been made (not 3)
        self.assertEqual(mock_classify.call_count, 1,
                        f"Expected 1 LLM call, got {mock_classify.call_count}")

        # All threads should get results
        for r in results:
            self.assertIsNotNone(r)
            self.assertTrue(r.get('is_story'))

        print(f"\n  [INFLIGHT] 3 threads, same text → "
              f"{mock_classify.call_count} LLM call(s) (expected 1) ✓")


class TestPhaseTimer(unittest.TestCase):
    """Verify phase timing instrumentation."""

    def test_basic_timing(self):
        """Timer records elapsed time per phase."""
        timer = PhaseTimer()
        timer.start('phase_a')
        time.sleep(0.1)
        timer.end('phase_a')

        phases = timer.get_phases()
        self.assertIn('phase_a', phases)
        self.assertGreaterEqual(phases['phase_a'], 0.08)
        self.assertLess(phases['phase_a'], 0.5)

    def test_auto_end_on_start(self):
        """Starting a new phase auto-ends the previous one."""
        timer = PhaseTimer()
        timer.start('phase_a')
        time.sleep(0.05)
        timer.start('phase_b')
        time.sleep(0.05)
        timer.end('phase_b')

        phases = timer.get_phases()
        self.assertIn('phase_a', phases)
        self.assertIn('phase_b', phases)

    def test_summary_format(self):
        """Summary line has the expected format."""
        timer = PhaseTimer()
        timer.start('narration')
        time.sleep(0.05)
        timer.end('narration')
        timer.start('packing')
        time.sleep(0.02)
        timer.end('packing')

        summary = timer.summary()
        self.assertIn('[TIMING] TOTAL wall=', summary)
        self.assertIn('narration=', summary)
        self.assertIn('packing=', summary)

    def test_wall_seconds(self):
        """get_wall_seconds returns total elapsed since creation."""
        timer = PhaseTimer()
        time.sleep(0.1)
        wall = timer.get_wall_seconds()
        self.assertGreaterEqual(wall, 0.08)

    def test_get_phase_elapsed(self):
        """get_phase_elapsed returns 0 for unrecorded phases."""
        timer = PhaseTimer()
        self.assertEqual(timer.get_phase_elapsed('nonexistent'), 0.0)
        timer.start('test')
        time.sleep(0.05)
        timer.end('test')
        self.assertGreater(timer.get_phase_elapsed('test'), 0.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
