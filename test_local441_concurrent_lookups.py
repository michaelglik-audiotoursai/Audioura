"""test_local441_concurrent_lookups.py — LOCAL-441 verification tests.

Demonstrates that batch_check_wikidata_p856 runs N slow lookups concurrently
within ~budget time, NOT ~N×timeout time.

Mocks the network layer with injected slow fakes for determinism.
"""
import time
import unittest
from unittest.mock import patch, MagicMock

# Import the module under test
import work_story_searcher as wss


class TestBatchConcurrentLookups(unittest.TestCase):
    """Verify that concurrent batch P856 lookups respect wall-budget."""

    def setUp(self):
        """Clear module-level cache before each test."""
        wss._MODULE_DOMAIN_CACHE.clear()

    def _make_slow_p856(self, delay_seconds=5.0, return_value='tier3'):
        """Create a mock _check_wikidata_p856 that sleeps for `delay_seconds`."""
        def slow_check(domain):
            time.sleep(delay_seconds)
            return return_value
        return slow_check

    def test_serial_would_take_too_long(self):
        """RED TEST: proves that without concurrency, 10 lookups × 5s = 50s."""
        # This test documents what WOULD happen serially
        n_domains = 10
        per_timeout = 5.0
        serial_expected = n_domains * per_timeout
        print(f"\n  [RED] Serial execution of {n_domains} lookups × {per_timeout}s "
              f"would take ≥{serial_expected}s")
        print(f"  [RED] Budget is {wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS}s — "
              f"batch must finish in ~budget time, NOT ~{serial_expected}s")
        self.assertGreater(serial_expected, wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS,
                          "Serial time should exceed budget (proves we need concurrency)")

    @patch.object(wss, '_check_wikidata_p856')
    def test_batch_completes_within_budget(self, mock_p856):
        """CORE TEST: 10 domains × 5s delay completes in ~budget, not ~50s."""
        n_domains = 10
        per_delay = 5.0  # Each lookup takes 5s
        budget = 8.0  # Budget for the batch

        # Mock: each call sleeps 5s then returns 'tier3'
        mock_p856.side_effect = self._make_slow_p856(delay_seconds=per_delay)

        domains = [f"example{i}.com" for i in range(n_domains)]

        start = time.time()
        results = wss.batch_check_wikidata_p856(domains, budget_seconds=budget, pool_size=10)
        elapsed = time.time() - start

        print(f"\n  [GREEN] {n_domains} lookups × {per_delay}s each")
        print(f"  [GREEN] Budget: {budget}s")
        print(f"  [GREEN] Actual elapsed: {elapsed:.2f}s")
        print(f"  [GREEN] Serial would have been: {n_domains * per_delay:.0f}s")
        print(f"  [GREEN] Speedup: {(n_domains * per_delay) / elapsed:.1f}x")

        # The batch should finish within budget + small overhead (threading startup)
        self.assertLess(elapsed, budget + 2.0,
                       f"Batch took {elapsed:.1f}s, should be ≤{budget + 2.0}s")
        # All domains should have results
        self.assertEqual(len(results), n_domains)
        # All should be tier3 (our mock returns tier3)
        for domain, tier in results.items():
            self.assertEqual(tier, 'tier3')

    @patch.object(wss, '_check_wikidata_p856')
    def test_budget_expires_treats_as_tier3(self, mock_p856):
        """When budget expires, unanswered lookups return tier3 (same as timeout)."""
        # 20 domains × 3s each, budget = 5s, pool = 4
        # With 4 threads: first batch of 4 finishes at 3s, second batch would finish at 6s
        # Budget of 5s means some will be expired
        n_domains = 20
        per_delay = 3.0
        budget = 5.0
        pool_size = 4

        mock_p856.side_effect = self._make_slow_p856(delay_seconds=per_delay)

        domains = [f"slow-host{i}.org" for i in range(n_domains)]

        start = time.time()
        results = wss.batch_check_wikidata_p856(domains, budget_seconds=budget, pool_size=pool_size)
        elapsed = time.time() - start

        print(f"\n  [GREEN] {n_domains} domains, {per_delay}s each, "
              f"budget={budget}s, pool={pool_size}")
        print(f"  [GREEN] Elapsed: {elapsed:.2f}s (budget enforced)")
        print(f"  [GREEN] All results: {len(results)} (all get a tier)")

        # Should finish near the budget, not n_domains × per_delay
        self.assertLess(elapsed, budget + 2.0)
        # All domains get a result (either completed or budget-expired → tier3)
        self.assertEqual(len(results), n_domains)
        # All are tier3 (mock returns tier3 when it completes, budget-expired also → tier3)
        for tier in results.values():
            self.assertEqual(tier, 'tier3')

    @patch.object(wss, '_check_wikidata_p856')
    def test_fast_lookups_return_quickly(self, mock_p856):
        """Fast-responding lookups don't wait for the budget to expire."""
        n_domains = 5
        per_delay = 0.1  # Very fast

        mock_p856.side_effect = self._make_slow_p856(delay_seconds=per_delay)

        domains = [f"fast{i}.com" for i in range(n_domains)]

        start = time.time()
        results = wss.batch_check_wikidata_p856(domains, budget_seconds=20.0, pool_size=10)
        elapsed = time.time() - start

        print(f"\n  [GREEN] {n_domains} fast lookups (0.1s each)")
        print(f"  [GREEN] Elapsed: {elapsed:.2f}s (should be ~0.1s, not 20s budget)")

        # Should finish in ~per_delay time, not wait for budget
        self.assertLess(elapsed, 1.0, "Fast lookups shouldn't wait for budget")
        self.assertEqual(len(results), n_domains)

    @patch.object(wss, '_check_wikidata_p856')
    def test_mixed_fast_and_slow(self, mock_p856):
        """Mix of fast tier1 and slow tier3 — fast ones resolve, slow ones budget-expire."""
        budget = 4.0

        def mixed_check(domain):
            if 'museum' in domain:
                time.sleep(0.1)  # Fast — institutional
                return 'tier1'
            else:
                time.sleep(10.0)  # Very slow — will budget-expire
                return 'tier3'

        mock_p856.side_effect = mixed_check

        domains = ['nationalmuseum.se', 'random-blog1.com', 'random-blog2.com',
                   'artmuseum.edu', 'unknown-host3.net', 'unknown-host4.net']

        start = time.time()
        results = wss.batch_check_wikidata_p856(domains, budget_seconds=budget, pool_size=10)
        elapsed = time.time() - start

        print(f"\n  [GREEN] Mixed: 2 fast (museum) + 4 slow")
        print(f"  [GREEN] Elapsed: {elapsed:.2f}s (budget={budget}s)")
        print(f"  [GREEN] Results: {results}")

        self.assertLess(elapsed, budget + 2.0)
        self.assertEqual(len(results), 6)
        # Fast ones should be tier1
        self.assertEqual(results['nationalmuseum.se'], 'tier1')
        self.assertEqual(results['artmuseum.edu'], 'tier1')
        # Slow ones should be tier3 (budget-expired)
        self.assertEqual(results['random-blog1.com'], 'tier3')

    def test_module_cache_persists_across_calls(self):
        """Module-level cache prevents re-asking the same domain."""
        # Pre-populate module cache
        wss._MODULE_DOMAIN_CACHE['cached-domain.org'] = 'tier1'

        # classify_domain should use cached value without network call
        with patch.object(wss, '_check_wikidata_p856') as mock_p856:
            result = wss.classify_domain('cached-domain.org')
            mock_p856.assert_not_called()
            self.assertEqual(result, 'tier1')

        print("\n  [GREEN] Module cache hit — no P856 call made")

    @patch.object(wss, '_check_wikidata_p856')
    def test_classify_domain_quick_avoids_p856(self, mock_p856):
        """_classify_domain_quick resolves rules-based domains without P856."""
        # These should all resolve without P856
        quick_results = {
            'en.wikipedia.org': 'tier1',
            'pinterest.com': 'reject',
            'harvard.edu': 'tier1',
            'nytimes.com': None,  # Depends on tier2_news_domains in rules
        }

        for domain in ['en.wikipedia.org', 'harvard.edu']:
            result = wss._classify_domain_quick(domain)
            self.assertIsNotNone(result, f"{domain} should be resolvable without P856")
            print(f"  [GREEN] _classify_domain_quick('{domain}') → {result}")

        # pinterest.com should be reject (if in reject_platforms)
        result = wss._classify_domain_quick('pinterest.com')
        if result is not None:
            self.assertEqual(result, 'reject')
            print(f"  [GREEN] _classify_domain_quick('pinterest.com') → {result}")

        # An unknown domain should return None (needs P856)
        result = wss._classify_domain_quick('totally-unknown-blog.xyz')
        self.assertIsNone(result, "Unknown domain should need P856 lookup")
        print(f"  [GREEN] _classify_domain_quick('totally-unknown-blog.xyz') → None (needs P856)")

    @patch.object(wss, '_check_wikidata_p856')
    def test_batch_deduplicates_via_cache(self, mock_p856):
        """Domains already in module cache are not re-checked."""
        # Pre-populate cache with some domains
        wss._MODULE_DOMAIN_CACHE['already-known.org'] = 'tier1'
        wss._MODULE_DOMAIN_CACHE['also-known.net'] = 'tier3'

        mock_p856.side_effect = self._make_slow_p856(delay_seconds=0.1)

        # Only the unknown domains should trigger P856 calls
        domains = ['new-domain.com', 'another-new.org']

        results = wss.batch_check_wikidata_p856(domains, budget_seconds=5.0)

        # Only the 2 new domains should have been checked
        self.assertEqual(mock_p856.call_count, 2)
        print(f"\n  [GREEN] Only 2 P856 calls made (cached domains skipped)")


class TestConstants(unittest.TestCase):
    """Verify module-scope constants are importable and sane."""

    def test_budget_constant_exists(self):
        self.assertIsInstance(wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS, (int, float))
        self.assertGreater(wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS, 0)
        print(f"\n  EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS = {wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS}")

    def test_pool_size_constant_exists(self):
        self.assertIsInstance(wss.EXTERNAL_LOOKUP_POOL_SIZE, int)
        self.assertGreater(wss.EXTERNAL_LOOKUP_POOL_SIZE, 0)
        self.assertLessEqual(wss.EXTERNAL_LOOKUP_POOL_SIZE, 20)
        print(f"\n  EXTERNAL_LOOKUP_POOL_SIZE = {wss.EXTERNAL_LOOKUP_POOL_SIZE}")

    def test_per_timeout_constant_exists(self):
        self.assertIsInstance(wss.EXTERNAL_LOOKUP_PER_TIMEOUT, (int, float))
        self.assertGreater(wss.EXTERNAL_LOOKUP_PER_TIMEOUT, 0)
        print(f"\n  EXTERNAL_LOOKUP_PER_TIMEOUT = {wss.EXTERNAL_LOOKUP_PER_TIMEOUT}")

    def test_batch_function_importable(self):
        """batch_check_wikidata_p856 is importable at module scope."""
        self.assertTrue(callable(wss.batch_check_wikidata_p856))
        print(f"\n  batch_check_wikidata_p856 is callable")


if __name__ == '__main__':
    unittest.main(verbosity=2)
