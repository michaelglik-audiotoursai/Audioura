-- D613 addendum (LEAD, 2026-10-06): an 'admin' level for Michael's own devices.
-- Tester (<=5 stops, 10/day) would block his field tests (he routinely asks for
-- 7-stop museum tours). Data-only, additive, idempotent. No DELETE.
INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period,
                   news_period, news_max_minutes, downloads_unlimited, max_stops,
                   max_new_stops_per_edit, by_reference_only, referrals_allowed,
                   referral_period, can_sell, price_usd)
VALUES ('admin', 999, 50, 300, 999, 'day', 60, true, 50, 50, false, 0, 'lifetime', true, 0)
ON CONFLICT (plan_id) DO NOTHING;

INSERT INTO device_entitlement (user_id, level, last_activity_at)
VALUES ('USER-1073427300', 'admin', NOW())
ON CONFLICT (user_id) DO UPDATE SET level = 'admin';
