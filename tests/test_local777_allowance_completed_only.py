"""test_local777_allowance_completed_only.py — LOCAL-777.

The "tours left" the Plan screen shows (entitlements_api._allowances_left) and
the free-plan gate (entitlements.get_tours_used_today) must count a tour the
SAME way the real gate (subscription_levels._count_fresh_generations) does:
only a DELIVERED tour, status='completed', source='orchestrator'. A request
that is still in flight ('started') or that was refused/failed ('failed') must
NOT reduce "tours left". Before LOCAL-777 the display counted every row, so one
refused request read "0 new tours left today" while the gate would still let the
user generate — the screen told them they couldn't when they could.

Red-first contract: for the SAME set of rows
    {completed today, failed today, started 9 days ago, refused (failed) today}
the DISPLAY and the GATE return the same used-count, and it is 1 (the single
completed row) — so today-left = tours_per_day - 1 and month-left =
tours_per_month - 1.

Runs against audiotours_test under pytest (host port 5433).
Run: python3 -m pytest tests/test_local777_allowance_completed_only.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# entitlements_api lives in the self-contained user-api build context.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user-tracking'))

from db_connection import get_db_config

_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]
# entitlements_api reads DATABASE_URL (not DB_*); point it at the test DB.
os.environ["DATABASE_URL"] = (
    f"postgresql://{_cfg['user']}:{_cfg['password']}"
    f"@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}"
)

import psycopg2
import subscription_levels as sl          # the real gate
import entitlements as ent                # the free-plan gate
import entitlements_api as eapi           # the Plan-screen display


def _conn():
    return psycopg2.connect(
        host=_cfg["host"], port=_cfg["port"], dbname=_cfg["dbname"],
        user=_cfg["user"], password=_cfg["password"],
    )


class TestLocal777AllowanceCompletedOnly(unittest.TestCase):
    """Display ("tours left") and gate must both count only completed tours."""

    def setUp(self):
        self.uid = 'L777-' + uuid.uuid4().hex[:10]
        self._cleanup()
        # L2: tours_per_day = 1, tours_per_month = 3 (the ticket's Free/L2 case).
        self.plan = {
            'tours_per_day': 1, 'tours_per_month': 3,
            'fresh_per_pack': None, 'edits_per_pack': None, 'ops_per_pack': None,
        }
        self.state = {'user_id': self.uid, 'level': 'l2'}

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (self.uid,))
                cur.execute("DELETE FROM users WHERE secret_id = %s", (self.uid,))
            c.commit()
        finally:
            c.close()

    def _seed_rows(self):
        """Seed the four-row scenario from the ticket:
          - 1 completed today        (the only tour that counts)
          - 1 failed today           (the refusal — must NOT count)
          - 1 started 9 days ago     (in-flight, old — must NOT count)
          - 1 'failed' today         (a second refused request — must NOT count)
        """
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (secret_id, plan) VALUES (%s, 'l2')
                    ON CONFLICT (secret_id) DO NOTHING
                """, (self.uid,))
                rows = [
                    ('completed', 'NOW()'),
                    ('failed', 'NOW()'),
                    ('started', "NOW() - interval '9 days'"),
                    ('failed', 'NOW()'),
                ]
                for status, when_sql in rows:
                    cur.execute(f"""
                        INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
                        VALUES (%s, %s, %s, {when_sql}, 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8], status))
            c.commit()
        finally:
            c.close()

    # ── the gate's view ────────────────────────────────────────────────────
    def _gate_used(self):
        c = _conn()
        try:
            cur = c.cursor()
            day = sl._count_fresh_generations(cur, self.uid, 'day')
            month = sl._count_fresh_generations(cur, self.uid, 'month')
            cur.close()
            return day, month
        finally:
            c.close()

    # ── the display's view ─────────────────────────────────────────────────
    def _display_left(self):
        c = _conn()
        try:
            cur = c.cursor()
            out = eapi._allowances_left(cur, self.state, self.plan)
            cur.close()
            return out
        finally:
            c.close()

    def test_gate_counts_only_completed(self):
        self._seed_rows()
        day, month = self._gate_used()
        self.assertEqual(1, day, "gate day-used must count only the completed row")
        self.assertEqual(1, month, "gate month-used must count only the completed row")

    def test_get_tours_used_today_counts_only_completed(self):
        self._seed_rows()
        self.assertEqual(1, ent.get_tours_used_today(self.uid),
                         "free-plan gate must count only the completed row today")

    def test_display_left_matches_gate(self):
        """The Plan screen's remaining counts must equal cap - (completed only)."""
        self._seed_rows()
        left = self._display_left()
        # today: 1 cap - 1 completed = 0 ; NOT 1 - (completed+failed+failed) < 0.
        self.assertEqual(0, left['tours_today_left'],
                         "today-left must be cap minus the single completed tour")
        # month: 3 cap - 1 completed = 2 ; before the fix this was 3 - 3 = 0.
        self.assertEqual(2, left['tours_this_month_left'],
                         "month-left must be cap minus the single completed tour")

    def test_display_and_gate_agree_on_used(self):
        """display used == gate used, for the same rows (the core LOCAL-777 claim)."""
        self._seed_rows()
        day_gate, month_gate = self._gate_used()
        left = self._display_left()
        display_day_used = self.plan['tours_per_day'] - left['tours_today_left']
        display_month_used = self.plan['tours_per_month'] - left['tours_this_month_left']
        self.assertEqual(day_gate, display_day_used,
                         "display today-used must equal the gate's day count")
        self.assertEqual(month_gate, display_month_used,
                         "display month-used must equal the gate's month count")
        self.assertEqual(ent.get_tours_used_today(self.uid), day_gate,
                         "get_tours_used_today must equal the gate's day count")

    def test_only_failed_rows_leave_full_allowance(self):
        """A device whose only requests today were refused keeps its full day/month
        allowance — the LOCAL-777 bug exactly: 0 completed -> nothing spent."""
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (secret_id, plan) VALUES (%s, 'l2')
                    ON CONFLICT (secret_id) DO NOTHING
                """, (self.uid,))
                for _ in range(2):
                    cur.execute("""
                        INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
                        VALUES (%s, %s, 'failed', NOW(), 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8]))
            c.commit()
        finally:
            c.close()
        left = self._display_left()
        self.assertEqual(1, left['tours_today_left'], "refusals must not spend the day allowance")
        self.assertEqual(3, left['tours_this_month_left'], "refusals must not spend the month allowance")
        self.assertEqual(0, ent.get_tours_used_today(self.uid))


if __name__ == '__main__':
    unittest.main()
