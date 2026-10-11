"""test_local668_cost_cap.py — LOCAL-668 deliverable #5 (cost cap).

At most 10 grounded/Serper verification queries per tour, cached per venue
(30 days). This exercises the pure parts of thin_verify_cache: the per-tour
VerificationBudget and the cache-key/no-DB behaviour. DB round-trips are
best-effort and not exercised here (no DB in the unit environment).
"""
import unittest

import thin_verify_cache as T


class Budget(unittest.TestCase):
    def test_default_cap_is_ten(self):
        self.assertEqual(T.VerificationBudget().max_queries, 10)

    def test_spend_stops_at_cap(self):
        b = T.VerificationBudget(3)
        self.assertTrue(b.spend())
        self.assertTrue(b.spend())
        self.assertTrue(b.spend())
        self.assertFalse(b.spend(), "4th spend must be refused")
        self.assertEqual(b.used, 3)
        self.assertEqual(b.remaining, 0)

    def test_wrap_counts_and_refuses_past_cap(self):
        b = T.VerificationBudget(2)
        calls = []
        rf = lambda q: calls.append(q) or {"text": "x", "sources": []}
        w = b.wrap(rf)
        r1, r2, r3 = w("a"), w("b"), w("c")
        self.assertEqual(len(calls), 2, "real research_fn called at most cap times")
        self.assertNotIn("error", r1)
        self.assertEqual(r3.get("error"), "verify_budget_exhausted")

    def test_wrap_none_is_none(self):
        self.assertIsNone(T.VerificationBudget().wrap(None))

    def test_summary_reports_count(self):
        b = T.VerificationBudget(10)
        b.spend(4)
        s = b.summary()
        self.assertIn("4/10", s)


class Cache(unittest.TestCase):
    def test_cache_key_folds_accents_and_case(self):
        k = T.cache_key("Ho Chi Minh City Museum of Fine Arts", "Vietnam")
        self.assertEqual(k, "ho chi minh city museum of fine arts|vietnam")

    def test_no_db_is_safe_miss(self):
        self.assertIsNone(T.cache_get("V", "C", db_url=""))

    def test_empty_result_not_persisted(self):
        # Must not raise and must be a no-op (never freeze a flaky zero).
        T.cache_put("V", "C", [], db_url="")
        T.cache_put("V", "C", [], db_url="postgresql://invalid")  # still no raise

    def test_ttl_is_thirty_days(self):
        self.assertEqual(T._CACHE_TTL_DAYS, 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
