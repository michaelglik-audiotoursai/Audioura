"""
entitlements_api.py — LOCAL-595 user-api endpoints for subscription levels.
============================================================================

Self-contained Flask blueprint for the user-api service (user-tracking/app.py).
It is self-contained ON PURPOSE: the user-api container's build context is
./user-tracking, so it cannot import the repo-root subscription_levels.py. The
device-state and anniversary logic here MIRRORS subscription_levels.py exactly
(same tables, same arithmetic). The repo-root module remains the authority used
by the orchestrator and editing service; this blueprint is the HTTP surface.

Endpoints (auth: X-API-Key == GATEWAY_API_KEY, the existing referral pattern):

  GET  /entitlements/me?user_id=...     -> level, allowances left, anniversary,
                                           warn_renewal, renewal_prompt
  POST /entitlements/app-open  {user_id}        -> record activity, renewal_prompt
  POST /entitlements/lapse     {user_id}        -> drop to L1
  POST /purchases/verify {store, transaction_id, product, user_id}
        -> verify via the IAP verifier (sandbox stub when IAP_VERIFY_MODE=stub),
           idempotent on transaction_id; a verified L3/L4 purchase sets the
           level, resets the pack and sets the anniversary.

Real Apple/Google verification lands in LOCAL-598; this ships the interface and
the stub only.
"""

import os
import hmac
import logging
import calendar
from datetime import datetime, date, timedelta

import psycopg2
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

entitlements_bp = Blueprint('entitlements', __name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours')
API_KEY = os.getenv('GATEWAY_API_KEY', '')
# LEAD 2026-10-06: default 'apple' — a 'stub' default would grant a free pack to any
# POST /purchases/verify. Tests set IAP_VERIFY_MODE=stub explicitly.
#
# [LOCAL-734] A fourth mode, 'per_store', chooses the backend by the request's
# `store` instead of one global value, so ONE server can verify real Apple
# sandbox purchases from the iPhone AND accept a TEST PURCHASE from a sideloaded
# Android build at the same time (Michael's Subscribed review uses both phones,
# and there is no Play service account locally yet). The three original modes
# ('stub' | 'apple' | 'google') keep working EXACTLY as before.
IAP_VERIFY_MODE = os.getenv('IAP_VERIFY_MODE', 'apple')  # 'stub' | 'apple' | 'google' | 'per_store'
RENEWAL_WARN_DAYS = int(os.getenv('RENEWAL_WARN_DAYS', '3'))

# [LOCAL-734] In per_store mode a store=='stub' purchase (the Android TEST
# PURCHASE path) is granted ONLY when this flag is explicitly on. It defaults
# OFF so a per_store server never grants on an unsigned stub transaction by
# accident; GCloud must NEVER set it. It has no effect in the other three modes
# (plain 'stub' mode already grants; 'apple'/'google' never take a stub store).
IAP_ALLOW_STUB_STORE = os.getenv('IAP_ALLOW_STUB_STORE', '').lower() in ('true', '1', 'yes')

# [LOCAL-598] Apple verification config. The bundle id the JWS must carry; the
# path to the bundled Apple Root CA G3 we pin the x5c chain to.
APPLE_BUNDLE_ID = os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours')
APPLE_ROOT_CA_PATH = os.getenv(
    'APPLE_ROOT_CA_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apple_root_ca_g3.pem'),
)

# [LOCAL-598B] Expected StoreKit environment. The signed transaction carries an
# `environment` claim; a Sandbox transaction must never grant on Production and
# vice-versa. 'Sandbox' locally, 'Production' once live. Empty disables the
# check (we pass None), which keeps older stub tests working.
APPLE_IAP_ENVIRONMENT = os.getenv('APPLE_IAP_ENVIRONMENT', '')

# [LOCAL-764] APPLE_IAP_ENVIRONMENT may be a single value ('Production') or a
# comma-separated list ('Production,Sandbox') for the Production-with-Sandbox
# fallback TestFlight needs (TestFlight purchases are signed 'Sandbox' even
# against Production). Parse once into the list the verifier accepts; None when
# unset (check disabled — keeps older stub tests working).
_APPLE_IAP_ENV_EXPECTED = (
    [e.strip() for e in APPLE_IAP_ENVIRONMENT.split(',') if e.strip()] or None
)

# [LOCAL-696] Google Play verification config. The Play package the purchase
# tokens belong to (same bundle as Apple — ClickUp wdvrdayx33), and the PATH to
# the service-account JSON used to call the Google Play Developer API. The key
# file is NEVER committed; LEAD/Michael place it in the container and set
# GOOGLE_PLAY_SA_JSON to its path. When the path is unset, Google purchases
# return 503 google_verify_unconfigured and NEVER grant (stub mode still works).
GOOGLE_PACKAGE_NAME = os.getenv('GOOGLE_PACKAGE_NAME', APPLE_BUNDLE_ID)
GOOGLE_PLAY_SA_JSON = os.getenv('GOOGLE_PLAY_SA_JSON', '')

# [LOCAL-807] Auto-renewing subscriptions. The Google RTDN endpoint +
# subscriptionsv2.get are gated behind this flag: the code and its tests ship
# now, but live Google verification only turns on once the audioura-play-verify
# service account is granted the subscriptions permission (currently 403 —
# D733 §3). Defaults OFF so a deployment never attempts an unauthorised Play
# call by accident. The Apple notifications endpoint has no such gate (Apple
# verification is fully working offline).
GOOGLE_SUBS_ENABLED = os.getenv('GOOGLE_SUBS_ENABLED', '').lower() in ('true', '1', 'yes')

# A sentinel returned by the Google verify path when no service account is
# configured, so the HTTP layer answers 503 google_verify_unconfigured. A
# TEST may inject a fake Google API client here to exercise the google path
# with no network and no SA file.
_GOOGLE_API_CLIENT_OVERRIDE = None


def _google_api_client():
    """Return a Google Play API client for a real verification, or None when no
    service account is configured (the caller then answers 503). A test can set
    `_GOOGLE_API_CLIENT_OVERRIDE` to inject a fake client with no network/SA."""
    if _GOOGLE_API_CLIENT_OVERRIDE is not None:
        return _GOOGLE_API_CLIENT_OVERRIDE
    if not GOOGLE_PLAY_SA_JSON:
        return None
    from google_play_verifier import build_api_client
    return build_api_client(GOOGLE_PLAY_SA_JSON, package_name=GOOGLE_PACKAGE_NAME)

# product -> level mapping. Data, not logic: a new product is one dict entry.
# Keys are the SERVER product keys.
PRODUCT_LEVELS = {
    'l3_pack_10': 'l3',
    'l4_round_25': 'l4',
}

# [LOCAL-598] The app/StoreKit product ids (App Store Connect / StoreKit config
# file) mapped to the server product keys above. The device sends the STORE id
# in `product`; we accept either the store id or the server key so the stub and
# apple paths share one endpoint. A new product is one more dict entry.
STORE_PRODUCT_IDS = {
    'audioura.pack.l3': 'l3_pack_10',
    'audioura.round.l4': 'l4_round_25',
}

# Reverse: server key -> expected store productId (for the apple JWS check).
SERVER_TO_STORE_PRODUCT = {v: k for k, v in STORE_PRODUCT_IDS.items()}

# [LOCAL-677] Tour price-tier products. A paid CURATOR tour is sold as one of a
# fixed set of CONSUMABLE store products (per-tour products can't be created on
# the fly — D624). The server records which tour a verified transaction
# unlocked, in tour_unlocks. Unlike a LEVEL purchase (which grants an allowance
# on device_entitlement), a tour purchase unlocks ONE tour for the buyer and
# does NOT change their level.
#
# This map is the self-contained mirror of the repo-root price_tiers table
# (migration 022) / price_tiers.py — the user-api container's build context is
# ./user-tracking and cannot import the repo-root module, exactly like
# PRODUCT_LEVELS mirrors subscription_levels. The price_tiers TABLE is the
# source of record; this is the fallback the stub path uses to stamp the amount.
# Keep these entries in lock-step with migrations 022/024/026's seed rows: the 7
# legacy .99 tiers (D652) plus the 34 round-dollar ladder tiers 8..41 (LOCAL-686).
TOUR_TIER_PRODUCTS = {
    'audioura.tour.tier1': {'tier': 1, 'price_usd': 1.99},
    'audioura.tour.tier2': {'tier': 2, 'price_usd': 2.99},
    'audioura.tour.tier3': {'tier': 3, 'price_usd': 4.99},
    'audioura.tour.tier4': {'tier': 4, 'price_usd': 7.99},
    'audioura.tour.tier5': {'tier': 5, 'price_usd': 9.99},
    'audioura.tour.tier6': {'tier': 6, 'price_usd': 19.99},  # [LOCAL-684] migration 024
    'audioura.tour.tier7': {'tier': 7, 'price_usd': 49.99},
    # [LOCAL-686] the round-dollar ladder (migration 026), tiers 8..41.
    'audioura.tour.usd2': {'tier': 8, 'price_usd': 2.0},
    'audioura.tour.usd3': {'tier': 9, 'price_usd': 3.0},
    'audioura.tour.usd4': {'tier': 10, 'price_usd': 4.0},
    'audioura.tour.usd5': {'tier': 11, 'price_usd': 5.0},
    'audioura.tour.usd6': {'tier': 12, 'price_usd': 6.0},
    'audioura.tour.usd7': {'tier': 13, 'price_usd': 7.0},
    'audioura.tour.usd8': {'tier': 14, 'price_usd': 8.0},
    'audioura.tour.usd9': {'tier': 15, 'price_usd': 9.0},
    'audioura.tour.usd10': {'tier': 16, 'price_usd': 10.0},
    'audioura.tour.usd11': {'tier': 17, 'price_usd': 11.0},
    'audioura.tour.usd12': {'tier': 18, 'price_usd': 12.0},
    'audioura.tour.usd13': {'tier': 19, 'price_usd': 13.0},
    'audioura.tour.usd14': {'tier': 20, 'price_usd': 14.0},
    'audioura.tour.usd15': {'tier': 21, 'price_usd': 15.0},
    'audioura.tour.usd16': {'tier': 22, 'price_usd': 16.0},
    'audioura.tour.usd17': {'tier': 23, 'price_usd': 17.0},
    'audioura.tour.usd18': {'tier': 24, 'price_usd': 18.0},
    'audioura.tour.usd19': {'tier': 25, 'price_usd': 19.0},
    'audioura.tour.usd20': {'tier': 26, 'price_usd': 20.0},
    'audioura.tour.usd25': {'tier': 27, 'price_usd': 25.0},
    'audioura.tour.usd30': {'tier': 28, 'price_usd': 30.0},
    'audioura.tour.usd35': {'tier': 29, 'price_usd': 35.0},
    'audioura.tour.usd40': {'tier': 30, 'price_usd': 40.0},
    'audioura.tour.usd45': {'tier': 31, 'price_usd': 45.0},
    'audioura.tour.usd50': {'tier': 32, 'price_usd': 50.0},
    'audioura.tour.usd60': {'tier': 33, 'price_usd': 60.0},
    'audioura.tour.usd70': {'tier': 34, 'price_usd': 70.0},
    'audioura.tour.usd80': {'tier': 35, 'price_usd': 80.0},
    'audioura.tour.usd90': {'tier': 36, 'price_usd': 90.0},
    'audioura.tour.usd100': {'tier': 37, 'price_usd': 100.0},
    'audioura.tour.usd125': {'tier': 38, 'price_usd': 125.0},
    'audioura.tour.usd150': {'tier': 39, 'price_usd': 150.0},
    'audioura.tour.usd175': {'tier': 40, 'price_usd': 175.0},
    'audioura.tour.usd200': {'tier': 41, 'price_usd': 200.0},
}


def _is_tour_product(product):
    """True if `product` is a tour price-tier store product id."""
    return product in TOUR_TIER_PRODUCTS


_UNLOCK_CONSUMPTION_READY = False


def _ensure_unlock_consumption_schema(cur):
    """[LOCAL-693 / D660] Self-heal the per-download consumption schema on
    tour_unlocks (mirrors migration 031) so writes here work whether or not 031
    has run on this DB: add consumed_at + consumed_by_download_id, drop the old
    full UNIQUE(user_id,tour_id), and create the partial unique index
    uq_tour_unlocks_active. The INSERTs below target that partial index with
    ON CONFLICT (user_id,tour_id) WHERE consumed_at IS NULL, so the index MUST
    exist or the insert errors. Idempotent; cached so it runs at most once per
    process. Does NOT commit (the caller owns the transaction). Never raises."""
    global _UNLOCK_CONSUMPTION_READY
    if _UNLOCK_CONSUMPTION_READY:
        return
    try:
        cur.execute(
            "ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ"
        )
        cur.execute(
            "ALTER TABLE tour_unlocks "
            "ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)"
        )
        cur.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname = 'uq_tour_unlocks_user_tour' "
            "AND conrelid = 'tour_unlocks'::regclass) THEN "
            "ALTER TABLE tour_unlocks DROP CONSTRAINT uq_tour_unlocks_user_tour; "
            "END IF; END $$;"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tour_unlocks_active "
            "ON tour_unlocks (user_id, tour_id) WHERE consumed_at IS NULL"
        )
        _UNLOCK_CONSUMPTION_READY = True
    except Exception:  # noqa: BLE001 — never fail a purchase over self-heal
        pass


def _tour_price_usd(cur, product):
    """The buyer price for a tour-tier product. Reads the price_tiers table when
    present (DB is authoritative — Michael's SQL edits take effect), else the
    code fallback above. Never raises."""
    info = TOUR_TIER_PRODUCTS.get(product, {})
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'price_tiers'"
        )
        if cur.fetchone() is not None:
            cur.execute(
                "SELECT price_usd FROM price_tiers WHERE product_id = %s", (product,)
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except Exception:  # noqa: BLE001 — fall back to the code default on any error
        pass
    return info.get('price_usd')


def _resolve_original_tour_id(cur, tour_id):
    """Map a (possibly translation) tour id to the ORIGINAL audio_tours.id its
    unlock keys on — the same rule the rating/review/pricing services use. A
    translation row has original_tour_id set; an original (or unknown id) maps to
    itself. Returns an int, or None if the id is not an integer."""
    try:
        tid = int(tour_id)
    except (TypeError, ValueError):
        return None
    try:
        cur.execute("SELECT original_tour_id FROM audio_tours WHERE id = %s", (tid,))
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    except Exception:  # noqa: BLE001
        pass
    return tid


def _normalize_product(product):
    """Accept either a store product id (audioura.pack.l3) or a server product
    key (l3_pack_10); return the SERVER key, or None if unknown."""
    if product in PRODUCT_LEVELS:
        return product
    return STORE_PRODUCT_IDS.get(product)


def _get_db():
    return psycopg2.connect(DATABASE_URL)


def _unauthenticated_entitlements_allowed():
    """[LOCAL-598B] True iff the local-only unauthenticated bypass is engaged.

    Read live (not cached at import) so tests can toggle it. The flag is only
    ever consulted when GATEWAY_API_KEY is empty — see _require_api_key."""
    return os.getenv('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', '').lower() in ('true', '1', 'yes')


def _require_api_key():
    """X-API-Key header check — identical pattern to referral_endpoints.

    [LOCAL-598B] The Mac Mini LOCAL stack has no GATEWAY_API_KEY, and the app in
    local server mode sends no X-API-Key (endpoints.dart apiHeaders only adds
    Content-Type locally). So every entitlements/queue call returned 503
    service_misconfigured and the Plan screen, app-open and queue could not be
    tested on Michael's phone against the Mac Mini.

    Following the ST-4 ALLOW_UNAUTHENTICATED_SHARING precedent exactly: when —
    and ONLY when — GATEWAY_API_KEY is empty, honour ALLOW_UNAUTHENTICATED_
    ENTITLEMENTS=true to serve the request unauthenticated. This is NOT a silent
    fail-open: the bypass opens only when someone has explicitly set the flag,
    it is documented as local development only, it is set in the LOCAL compose
    file and nowhere else, and it NEVER defaults on. Cloud has a real
    GATEWAY_API_KEY, so this branch is never reached there and the fail-closed
    503 remains for any deployment that is genuinely misconfigured."""
    if not API_KEY:
        if _unauthenticated_entitlements_allowed():
            return None
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


# [LOCAL-598B] Loud startup warning when the local-only bypass is engaged, so an
# operator who leaves it on in the wrong place sees it immediately in the logs.
# Only fires in the exact bypass condition: no key AND flag on.
if not API_KEY and _unauthenticated_entitlements_allowed():
    logger.warning(
        "[LOCAL-598B] ALLOW_UNAUTHENTICATED_ENTITLEMENTS is ON and "
        "GATEWAY_API_KEY is empty: the entitlements/queue API is serving "
        "UNAUTHENTICATED requests. This is for LOCAL DEVELOPMENT ONLY. Never "
        "enable this where the API is reachable from untrusted networks.")


# ───────────────────────────────────────────────────────────────────────────
# Anniversary arithmetic (mirror of subscription_levels.add_one_calendar_month)
# ───────────────────────────────────────────────────────────────────────────
def add_one_calendar_month(when):
    is_dt = isinstance(when, datetime)
    y, m, d = when.year, when.month, when.day
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last_day = calendar.monthrange(ny, nm)[1]
    nd = min(d, last_day)
    return when.replace(year=ny, month=nm, day=nd) if is_dt else date(ny, nm, nd)


def _is_renewal_due(anniversary_at, now):
    return anniversary_at is not None and now >= anniversary_at


def _warn_renewal(anniversary_at, now, days=RENEWAL_WARN_DAYS):
    if anniversary_at is None or now >= anniversary_at:
        return False
    return now >= (anniversary_at - timedelta(days=days))


# ───────────────────────────────────────────────────────────────────────────
# Device state helpers
# ───────────────────────────────────────────────────────────────────────────
_DEV_COLS = ['user_id', 'level', 'pack_started_at', 'anniversary_at',
             'fresh_used', 'edits_used', 'ops_used', 'last_activity_at']


def _get_device_state(cur, user_id):
    cur.execute("""
        SELECT user_id, level, pack_started_at, anniversary_at,
               fresh_used, edits_used, ops_used, last_activity_at
        FROM device_entitlement WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        return {'user_id': user_id, 'level': 'l1', 'pack_started_at': None,
                'anniversary_at': None, 'fresh_used': 0, 'edits_used': 0,
                'ops_used': 0, 'last_activity_at': None}
    return dict(zip(_DEV_COLS, row))


_PLAN_COLS = ['plan_id', 'tours_per_day', 'tours_per_month', 'tours_per_week',
              'fresh_per_pack',
              'edits_per_pack', 'ops_per_pack', 'max_stops', 'max_new_stops_per_edit',
              'by_reference_only', 'referrals_allowed', 'referral_period', 'seat_cap',
              'can_sell', 'price_usd', 'inactivity_days', 'display_name', 'hidden']


def _get_plan(cur, level):
    cur.execute("""
        SELECT plan_id, tours_per_day, tours_per_month, tours_per_week,
               fresh_per_pack,
               edits_per_pack, ops_per_pack, max_stops, max_new_stops_per_edit,
               by_reference_only, referrals_allowed, referral_period, seat_cap,
               can_sell, price_usd, inactivity_days, display_name, hidden
        FROM plans WHERE plan_id = %s
    """, (level,))
    row = cur.fetchone()
    return dict(zip(_PLAN_COLS, row)) if row else None


def _visible_levels(cur):
    """[LOCAL-604 D619] The ordered list of VISIBLE plans for the plan page:
    only rows with hidden=false, in plan order (l1, l2, l3, l4; tester and admin
    are hidden). Each entry carries the fields the app needs to render a level
    row without hardcoding any of them:
        plan_id, display_name, price_usd, can_sell, referrals_allowed,
        referral_period, max_stops.
    Ordering: by a fixed plan rank so the app always shows Introduction, Free,
    $10 Pack, Curator in that order regardless of row insertion order."""
    cur.execute("""
        SELECT plan_id, display_name, price_usd, can_sell,
               referrals_allowed, referral_period, max_stops,
               tours_per_day, tours_per_month, fresh_per_pack, ops_per_pack,
               inactivity_days
        FROM plans
        WHERE COALESCE(hidden, FALSE) = FALSE
        ORDER BY CASE plan_id
                     WHEN 'l1' THEN 1 WHEN 'l2' THEN 2
                     WHEN 'l3' THEN 3 WHEN 'l4' THEN 4
                     ELSE 99 END,
                 plan_id
    """)
    out = []
    for r in cur.fetchall():
        (plan_id, display_name, price_usd, can_sell, referrals_allowed,
         referral_period, max_stops, tpd, tpm, fpp, opp, inactivity_days) = r
        out.append({
            'plan_id': plan_id,
            'display_name': display_name or plan_id,
            'price_usd': float(price_usd) if price_usd is not None else 0.0,
            'can_sell': bool(can_sell),
            'referrals_allowed': referrals_allowed or 0,
            'referral_period': referral_period,
            'max_stops': max_stops,
            'tours_per_day': tpd,
            'tours_per_month': tpm,
            'fresh_per_pack': fpp,
            'ops_per_pack': opp,
            # [LOCAL-610 req 3] passthrough so the plan page can show the Free
            # inactivity rule ("After N days…") with the Free level's own N even
            # when the current device is on another level.
            'inactivity_days': inactivity_days,
        })
    return out


def _allowances_left(cur, state, plan):
    """Compute remaining allowances for the current level, as a dict the app can
    render. Period levels (L2/Tester) report remaining day/month fresh counts;
    pack levels (L3/L4) report remaining pack units."""
    out = {}
    level = state['level']
    if plan is None:
        return out
    # Period caps (count tour_requests written by the orchestrator).
    #
    # [LOCAL-777] Count only DELIVERED tours: status='completed'. This is the
    # SAME predicate the real gate uses — subscription_levels._count_fresh_
    # generations = "source='orchestrator' AND status='completed' AND {scope}"
    # (LOCAL-595B defect 2). A request that is still in flight ('started') or
    # that was refused/failed ('failed') must NOT reduce "tours left": before
    # this fix the display counted every row, so one refused request read "0 new
    # tours left today" while the gate would still let the user generate — the
    # screen told them they couldn't when they could. Display and gate must agree.
    if plan['tours_per_day'] is not None and plan['tours_per_day'] < 999:
        cur.execute("""SELECT COUNT(*) FROM tour_requests
                       WHERE secret_id=%s AND source='orchestrator'
                         AND status='completed'
                         AND started_at::date = CURRENT_DATE""", (state['user_id'],))
        used_day = cur.fetchone()[0]
        out['tours_today_left'] = max(0, plan['tours_per_day'] - used_day)
    if plan['tours_per_month'] is not None:
        cur.execute("""SELECT COUNT(*) FROM tour_requests
                       WHERE secret_id=%s AND source='orchestrator'
                         AND status='completed'
                         AND started_at >= date_trunc('month', CURRENT_DATE)""",
                    (state['user_id'],))
        used_month = cur.fetchone()[0]
        out['tours_this_month_left'] = max(0, plan['tours_per_month'] - used_month)
    # [LOCAL-807B] Weekly subscription allowance. The Weekly plan (sub_week)
    # grants tours_per_week with tours_per_month NULL and tours_per_day=999, so
    # neither branch above fires and the plans screen showed NO "N new tours
    # left" for a Weekly subscriber — the exact line D734's "Your plan" banner
    # needs. Count the SAME delivered tours, scoped to the current week
    # (date_trunc('week') = Monday per ISO) with the same orchestrator/completed
    # predicate the gate uses, so display and gate agree.
    if plan.get('tours_per_week') is not None:
        cur.execute("""SELECT COUNT(*) FROM tour_requests
                       WHERE secret_id=%s AND source='orchestrator'
                         AND status='completed'
                         AND started_at >= date_trunc('week', CURRENT_DATE)""",
                    (state['user_id'],))
        used_week = cur.fetchone()[0]
        out['tours_this_week_left'] = max(0, plan['tours_per_week'] - used_week)
    if plan['fresh_per_pack'] is not None:
        out['fresh_left'] = max(0, plan['fresh_per_pack'] - state['fresh_used'])
    if plan['edits_per_pack'] is not None:
        out['edits_left'] = max(0, plan['edits_per_pack'] - state['edits_used'])
    if plan['ops_per_pack'] is not None:
        out['ops_left'] = max(0, plan['ops_per_pack'] - state['ops_used'])
    return out


def _pack_units_left(plan, state):
    """What is left on the device's CURRENT pack, per unit kind, as a dict.
    Uses the same max(0, per_pack - used) the app sees. Only the pack-unit
    kinds the level defines are present (L3: fresh/edits; L4: ops)."""
    out = {}
    if plan is None:
        return out
    if plan.get('fresh_per_pack') is not None:
        out['fresh'] = max(0, plan['fresh_per_pack'] - state['fresh_used'])
    if plan.get('edits_per_pack') is not None:
        out['edits'] = max(0, plan['edits_per_pack'] - state['edits_used'])
    if plan.get('ops_per_pack') is not None:
        out['ops'] = max(0, plan['ops_per_pack'] - state['ops_used'])
    return out


def _carry_over_used(old_state, old_plan, new_level, new_plan, now):
    """[LOCAL-733 / D703] Compute the fresh_used/edits_used/ops_used for a NEW
    pack purchase, carrying over what is left on the current pack.

    Rules (D703):
      1. Same level while the current pack is active (now < anniversary_at):
         the new pack ADDS to what is left. We lower the used counters by the
         new pack's per-pack allowance (used = used - per_pack), so a negative
         "used" is the carried extra and max(0, per_pack - used) = per_pack +
         extra. The columns allow negatives (no CHECK; INTEGER NOT NULL).
      2. Different level while active (L3 $10 Pack <-> L4 Curator): what is left
         converts ONE FOR ONE into the new level's units, then the new pack is
         added.
           - L3 -> L4: (fresh_left + edits_left) become extra L4 ops.
           - L4 -> L3: ops_left become extra L3 fresh tours (edits start fresh).
      3. Expired pack (now >= anniversary_at), first purchase, or no prior pack
         window: start fresh from zero.

    Returns (fresh_used, edits_used, ops_used) for the new row. Carried extra
    shows up as a NEGATIVE used on the kind(s) the new level has.
    """
    def fresh_from_zero():
        # A new pack's counters begin at the new pack's full allowance unused.
        return (0, 0, 0)

    # Rule 3: no active prior pack -> fresh.
    old_ann = old_state.get('anniversary_at') if old_state else None
    if old_ann is None or now >= old_ann:
        return fresh_from_zero()
    if old_plan is None:
        return fresh_from_zero()

    left = _pack_units_left(old_plan, old_state)
    old_level = old_state['level']

    # Rule 1: same level -> add. Lower each used by the new pack's allowance so
    # the carried units stack on top of the fresh pack.
    if old_level == new_level:
        fresh_used = edits_used = ops_used = 0
        if new_plan.get('fresh_per_pack') is not None:
            fresh_used = -left.get('fresh', 0)
        if new_plan.get('edits_per_pack') is not None:
            edits_used = -left.get('edits', 0)
        if new_plan.get('ops_per_pack') is not None:
            ops_used = -left.get('ops', 0)
        return (fresh_used, edits_used, ops_used)

    # Rule 2: different level -> convert 1:1 into the new level's units.
    fresh_used = edits_used = ops_used = 0
    if new_level == 'l4':
        # L3 -> L4: fresh_left + edits_left become extra L4 ops.
        carried_ops = left.get('fresh', 0) + left.get('edits', 0)
        if new_plan.get('ops_per_pack') is not None:
            ops_used = -carried_ops
    elif new_level == 'l3':
        # L4 -> L3: ops_left become extra L3 fresh tours.
        carried_fresh = left.get('ops', 0)
        if new_plan.get('fresh_per_pack') is not None:
            fresh_used = -carried_fresh
        # edits start fresh (nothing to convert into edits).
    # Any other cross-level pairing starts fresh (no pack units to carry).
    return (fresh_used, edits_used, ops_used)


def _me_payload(cur, user_id, now=None):
    now = now or datetime.utcnow()
    state = _get_device_state(cur, user_id)
    plan = _get_plan(cur, state['level'])
    ann = state['anniversary_at']
    renewal_due = _is_renewal_due(ann, now)

    # [LOCAL-596] Queue + offer status for the L2 seat lifecycle. queue_position
    # is the device's 1-based place in the FIFO waiting line (None if it is not
    # waiting). pending_offer is its live, unexpired claim offer (None if it has
    # none). Both come from the shared seat core so the API and the job agree.
    queue_position = None
    pending_offer = None
    try:
        import l2_seats
        queue_position = l2_seats.queue_position(cur, user_id)
        offer = l2_seats.pending_offer(cur, user_id)
        if offer:
            pending_offer = {
                'code': offer['code'],
                'expires_at': offer['expires_at'].isoformat() if offer['expires_at'] else None,
            }
    except Exception as e:  # pragma: no cover - seat tables optional pre-015
        logger.warning(f"[LOCAL-596] queue/offer lookup failed for {user_id}: {e}")

    return {
        'user_id': user_id,
        'level': state['level'],
        # [LOCAL-604 D619] The current level's human display name (falls back to
        # the plan_id if unset), and the ordered list of VISIBLE levels for the
        # plan page (tester/admin excluded). The app renders names from here and
        # hardcodes nothing.
        'display_name': (plan.get('display_name') if plan else None) or state['level'],
        'levels': _visible_levels(cur),
        # [LOCAL-610 req 3] The current level's inactivity window, straight from
        # plans.inactivity_days (the SAME column l2_seat_job reads to evict idle
        # L2 devices). Passthrough only — no behaviour changes here. The plan
        # page shows "After N days without a visit…" using this N instead of a
        # hardcoded 7, so the copy can never drift from the DB value.
        'inactivity_days': (plan.get('inactivity_days') if plan else None),
        'anniversary_at': ann.isoformat() if ann else None,
        'allowances_left': _allowances_left(cur, state, plan),
        'warn_renewal': _warn_renewal(ann, now),
        'renewal_prompt': renewal_due,
        'can_sell': bool(plan['can_sell']) if plan else False,
        'queue_position': queue_position,
        'pending_offer': pending_offer,
    }


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-734] Shared verifier selection — the ONE place every purchase path
# (level, tour, pass, restore) asks "which backend verifies THIS store?". It
# replaces three copies of `if IAP_VERIFY_MODE == ...` so a new mode or policy
# lives in exactly one function.
# ───────────────────────────────────────────────────────────────────────────
# Returned by _verifier_for when a store must be REFUSED (never granted). The
# code travels in raw_status so the HTTP layer can map it (stub-not-allowed and
# google-not-configured both become refusals, never a silent grant).
_STUB_STORE_NOT_ALLOWED = 'stub_store_not_allowed'
_GOOGLE_NOT_CONFIGURED = 'google_not_configured'


def _verifier_for(store):
    """[LOCAL-734] Resolve the verification backend for a purchase with the
    given request `store`, honouring the configured IAP_VERIFY_MODE.

    Returns one of:
      * 'stub'   — grant on any non-empty transaction id (no crypto, no charge);
      * 'apple'  — verify the StoreKit 2 JWS offline (Sandbox/Production per
                   APPLE_IAP_ENVIRONMENT);
      * 'google' — verify the purchase token with the Play Developer API;
      * a REFUSAL string (never grant): _STUB_STORE_NOT_ALLOWED or
        _GOOGLE_NOT_CONFIGURED.

    The three ORIGINAL modes are unchanged: 'stub'/'apple'/'google' always
    resolve to themselves (the per-store verify functions already reject a
    mismatched store, e.g. apple mode + store='google'). Only 'per_store' uses
    the request store:
      * store == 'apple'  -> 'apple'  (real Apple JWS);
      * store == 'google' -> 'google' when a Play service account is configured,
                             else _GOOGLE_NOT_CONFIGURED (never grant);
      * store == 'stub'   -> 'stub' ONLY when IAP_ALLOW_STUB_STORE is on, else
                             _STUB_STORE_NOT_ALLOWED;
      * any other store   -> _STUB_STORE_NOT_ALLOWED (unknown store, refuse).

    Read live (module globals, not captured) so a test that monkeypatches
    IAP_VERIFY_MODE / IAP_ALLOW_STUB_STORE sees the change.
    """
    mode = IAP_VERIFY_MODE
    if mode != 'per_store':
        # 'stub' / 'apple' / 'google' (and anything unrecognised) pass through
        # exactly as before; the verify functions handle an unknown mode with
        # their existing verify_mode_not_implemented path.
        return mode

    if store == 'apple':
        return 'apple'
    if store == 'google':
        # Never grant a Google purchase without a service account to verify it.
        return 'google' if _google_api_client() is not None else _GOOGLE_NOT_CONFIGURED
    if store == 'stub':
        return 'stub' if IAP_ALLOW_STUB_STORE else _STUB_STORE_NOT_ALLOWED
    # Unknown store under per_store: refuse rather than guess.
    return _STUB_STORE_NOT_ALLOWED


def _platform_modes():
    """[LOCAL-734] The per-platform verifier answer for /purchases/mode, so the
    app chooses the right buy path on EACH platform without guessing.

    Returns {'ios': <v>, 'android': <v>} where each <v> is one of 'apple',
    'google' or 'stub' — what store the app should drive on that platform:
      * per_store: ios -> 'apple' (real StoreKit sandbox/prod); android ->
        'google' when a Play SA is configured, else 'stub' when
        IAP_ALLOW_STUB_STORE is on (the Android TEST PURCHASE path), else
        'google' (the app will attempt real Play billing and the server will
        refuse an unverifiable purchase — it never silently grants).
      * stub:   both platforms -> 'stub'.
      * apple:  both platforms -> 'apple'.
      * google: both platforms -> 'google'.
    """
    mode = IAP_VERIFY_MODE
    if mode == 'per_store':
        if _google_api_client() is not None:
            android = 'google'
        elif IAP_ALLOW_STUB_STORE:
            android = 'stub'
        else:
            android = 'google'
        return {'ios': 'apple', 'android': android}
    if mode in ('stub', 'apple', 'google'):
        return {'ios': mode, 'android': mode}
    # Unknown/unimplemented mode: report it verbatim on both platforms.
    return {'ios': mode, 'android': mode}


# ───────────────────────────────────────────────────────────────────────────
# IAP verifier interface + sandbox stub + offline Apple verification
# ───────────────────────────────────────────────────────────────────────────
class VerificationResult:
    def __init__(self, ok, raw_status, amount=None, unconfigured=False):
        self.ok = ok
        self.raw_status = raw_status
        self.amount = amount
        # [LOCAL-696] True when Google verification was requested but no service
        # account is configured — the HTTP layer must answer 503
        # google_verify_unconfigured and NEVER grant (never a 402 as if the
        # store refused). Distinct from ok=False so the two cases never blur.
        self.unconfigured = unconfigured


_PLAN_AMOUNTS = {'l3_pack_10': 10.00, 'l4_round_25': 25.00}


def _google_verify(store, product_id, purchase_token, expected_product_id,
                   amount, tag='LOCAL-696'):
    """[LOCAL-696] Shared Google Play verification for every product kind (level,
    tour, pass). Verifies the purchase token with the Google Play Developer API
    (purchases.products.get), then acknowledges and consumes it so it can be
    bought again (D660). Returns a VerificationResult:

      * store != 'google'              -> ok=False  google_mode_wrong_store:<store>
      * no purchase_token              -> ok=False  google_missing_purchase_token
      * no service account configured  -> unconfigured=True (HTTP 503)
      * verify/ack/consume failure      -> ok=False  google_<code>
      * success                         -> ok=True   google_verified:<orderId>

    The authoritative Google orderId is returned in raw_status
    ('google_verified:<orderId>') so the caller records/idempotency-checks the
    orderId on purchases.transaction_id (UNIQUE), exactly like the apple path."""
    if store != 'google':
        return VerificationResult(False, f'google_mode_wrong_store:{store}')
    if not purchase_token:
        return VerificationResult(False, 'google_missing_purchase_token')

    client = _google_api_client()
    if client is None:
        return VerificationResult(False, 'google_verify_unconfigured',
                                  unconfigured=True)

    try:
        from google_play_verifier import (
            verify_product_purchase, GoogleVerificationError,
        )
    except Exception as e:  # pragma: no cover - import-time safety
        logger.error(f"[{tag}] google verifier import failed: {e}")
        return VerificationResult(False, f'google_verifier_unavailable:{e}')

    try:
        verified = verify_product_purchase(
            client,
            product_id=product_id,
            purchase_token=purchase_token,
            expected_product_id=expected_product_id,
            package_name=GOOGLE_PACKAGE_NAME,
            acknowledge=True,
            consume=True,
        )
    except GoogleVerificationError as e:
        # A missing/unreadable SA surfaces here only if the client was built but
        # the file vanished mid-flight; treat the unconfigured-ish codes as 503.
        if e.code in ('google_sa_unreadable', 'google_sa_invalid',
                      'google_libs_unavailable'):
            logger.error(f"[{tag}] google verify unconfigured: {e.code}")
            return VerificationResult(False, f'google_{e.code}', unconfigured=True)
        logger.warning(f"[{tag}] google verify failed: {e.code}")
        return VerificationResult(False, f'google_{e.code}')
    except Exception as e:  # noqa: BLE001
        logger.error(f"[{tag}] google verify error: {e}")
        return VerificationResult(False, f'google_error:{e}')

    return VerificationResult(True, f'google_verified:{verified.order_id}', amount)


def _load_apple_root_ca():
    with open(APPLE_ROOT_CA_PATH, 'rb') as f:
        return f.read()


def verify_purchase(store, transaction_id, product, signed_transaction=None):
    """Verify an IAP against the store. IAP_VERIFY_MODE selects the backend.

    Args:
        store: 'apple' (or 'google', not implemented).
        transaction_id: the store transaction id (used by the stub and for the
            idempotency check at the call site).
        product: the SERVER product key (l3_pack_10 / l4_round_25).
        signed_transaction: the StoreKit 2 JWS (required for apple mode).

    stub   : accept any non-empty transaction_id (sandbox). No crypto.
    apple  : verify the StoreKit 2 JWS OFFLINE — x5c chain pinned to Apple Root
             CA G3, ES256 signature, bundleId, productId and type==Consumable.
             No API key, no network. The verified transactionId from the JWS is
             authoritative; it is returned in raw_status for the caller.

    [LOCAL-734] The backend is chosen by the shared _verifier_for(store) helper,
    so per_store mode (Apple on iOS, stub/Google on Android) routes here too.
    """
    mode = _verifier_for(store)
    if mode == _STUB_STORE_NOT_ALLOWED:
        return VerificationResult(False, _STUB_STORE_NOT_ALLOWED)
    if mode == _GOOGLE_NOT_CONFIGURED:
        return VerificationResult(False, _GOOGLE_NOT_CONFIGURED, unconfigured=True)

    if mode == 'stub':
        if not transaction_id:
            return VerificationResult(False, 'stub_rejected_empty_transaction')
        return VerificationResult(True, 'stub_verified', _PLAN_AMOUNTS.get(product))

    if mode == 'apple':
        if store != 'apple':
            return VerificationResult(False, f'apple_mode_wrong_store:{store}')
        if not signed_transaction:
            return VerificationResult(False, 'apple_missing_signed_transaction')
        try:
            # Imported lazily so stub-mode deployments need no crypto dep.
            from apple_jws_verifier import (
                verify_signed_transaction, JwsVerificationError,
            )
        except Exception as e:  # pragma: no cover - import-time safety
            logger.error(f"[LOCAL-598] apple verifier import failed: {e}")
            return VerificationResult(False, f'apple_verifier_unavailable:{e}')

        expected_store_product = SERVER_TO_STORE_PRODUCT.get(product)
        try:
            root_pem = _load_apple_root_ca()
            verified = verify_signed_transaction(
                signed_transaction,
                root_ca_pem=root_pem,
                expected_bundle_id=APPLE_BUNDLE_ID,
                expected_product_id=expected_store_product,
                required_type='Consumable',
                expected_environment=_APPLE_IAP_ENV_EXPECTED,
            )
        except JwsVerificationError as e:
            logger.warning(f"[LOCAL-598] apple verify failed: {e.code}")
            return VerificationResult(False, f'apple_{e.code}')
        except Exception as e:
            logger.error(f"[LOCAL-598] apple verify error: {e}")
            return VerificationResult(False, f'apple_error:{e}')

        # The JWS is authoritative: trust the transactionId FROM the signed
        # transaction, not the client-supplied one. Report it so the caller
        # records/idempotency-checks the verified id.
        return VerificationResult(
            True, f'apple_verified:{verified.transaction_id}',
            _PLAN_AMOUNTS.get(product))

    if mode == 'google':
        # [LOCAL-696] The device sends the STORE product id in `product` and the
        # opaque purchaseToken in `signed_transaction` (reused field; the app's
        # google path puts the token there). The Play product id for a level is
        # the store id mapped from the server key.
        expected_store_product = SERVER_TO_STORE_PRODUCT.get(product)
        product_id = expected_store_product or product
        return _google_verify(
            store, product_id=product_id, purchase_token=signed_transaction,
            expected_product_id=expected_store_product,
            amount=_PLAN_AMOUNTS.get(product), tag='LOCAL-696')

    # other: not implemented.
    return VerificationResult(False, f'verify_mode_not_implemented:{mode}')


# ───────────────────────────────────────────────────────────────────────────
# Endpoints
# ───────────────────────────────────────────────────────────────────────────
@entitlements_bp.route('/entitlements/me', methods=['GET'])
def entitlements_me():
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/support-id', methods=['GET', 'POST'])
def support_id_endpoint():
    """[LOCAL-729/D692] The device's public Support ID (AU-XXXX), shown in About
    with a Copy button. The app sends its device user_id (GET ?user_id= or POST
    {user_id}); we allocate one on first call and return the SAME alias forever
    (support_ids.user_id UNIQUE). This is the ONLY non-admin surface for the
    Support ID: it creates/reads the device's own alias and nothing else — it
    never reveals the secret id and cannot read another device's data. Gateway
    key only (the admin tools resolve a Support ID back to a device separately).
    """
    err = _require_api_key()
    if err:
        return err
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or data.get('secret_id')
    else:
        user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    import support_id as _sid
    conn = _get_db()
    try:
        cur = conn.cursor()
        sid = _sid.ensure_support_id(cur, user_id)
        conn.commit()
        cur.close()
        return jsonify({"user_id": user_id, "support_id": sid}), 200
    finally:
        conn.close()


@entitlements_bp.route('/entitlements/app-open', methods=['POST'])
def entitlements_app_open():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        # Record activity; create at L1 if the device is new.
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET last_activity_at = NOW(), updated_at = NOW()
        """, (user_id,))
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/entitlements/lapse', methods=['POST'])
def entitlements_lapse():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = 'l1', pack_started_at = NULL, anniversary_at = NULL,
                fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        """, (user_id,))
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


def _verify_tour_purchase(store, transaction_id, product, user_id,
                          signed_transaction, tour_id):
    """[LOCAL-677] Verify a TOUR price-tier purchase and unlock the tour.

    A tour purchase unlocks ONE tour for the buyer (writes tour_unlocks) and
    does NOT change their level. Flow mirrors the level path: idempotency on
    transaction_id, verify via the store (stub accepts any non-empty id), record
    the purchase, then write the unlock idempotently (ON CONFLICT on the partial
    index uq_tour_unlocks_active — one ACTIVE unlock per user+row; D660 lets a
    re-buy after a download consumed the prior unlock).
    Requires tour_id in the body. Returns a Flask (json, status) tuple.
    """
    if not tour_id:
        return jsonify({
            "error": "missing_fields",
            "message": "tour_id is required to unlock a tour purchase.",
        }), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        # [LOCAL-693 / D660] Ensure the consumption schema (consumed_at + the
        # partial unique index) exists before any ON CONFLICT ... WHERE
        # consumed_at IS NULL insert below.
        _ensure_unlock_consumption_schema(cur)

        # [LOCAL-677B / D653] The unlock keys on the OWN language id the buyer
        # purchased (buying Russian unlocks Russian only), NOT the source. We
        # still validate the tour EXISTS (via the resolver, which also proves the
        # id is an integer and a known tour); the unlock row then uses the own id.
        resolved = _resolve_original_tour_id(cur, tour_id)
        if resolved is None:
            cur.close()
            return jsonify({
                "error": "unknown_tour",
                "message": f"Unknown tour '{tour_id}'.",
            }), 400
        own_tour_id = int(tour_id)
        # The tour id must be a real row (the resolver returns the id itself for
        # an unknown-but-integer id, so confirm existence explicitly).
        cur.execute("SELECT 1 FROM audio_tours WHERE id = %s", (own_tour_id,))
        if cur.fetchone() is None:
            cur.close()
            return jsonify({
                "error": "unknown_tour",
                "message": f"Unknown tour '{tour_id}'.",
            }), 400

        # Idempotency on the client-supplied transaction id (apple re-checks the
        # authoritative id below).
        cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (transaction_id,))
        if cur.fetchone():
            # Already processed — ensure the unlock exists (idempotent) and
            # report success so a redelivery is not an error.
            cur.execute(
                """
                INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING
                """,
                (user_id, own_tour_id, transaction_id, store,
                 _tour_price_usd(cur, product)),
            )
            conn.commit()
            cur.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": transaction_id,
                "unlocked": True,
                "tour_id": own_tour_id,
            }), 409

        # Verify with the store. For apple mode, verify_purchase checks the
        # signed transaction against the expected store product id; it already
        # knows tour products are Consumable (SERVER_TO_STORE_PRODUCT is only for
        # level products, so a tour product uses the store id directly below).
        result = _verify_tour_signed(store, transaction_id, product,
                                     signed_transaction)
        if getattr(result, 'unconfigured', False):
            # [LOCAL-696] Google requested but no service account configured —
            # 503, never a grant and never a 402 as if the store refused.
            cur.close()
            return jsonify({"error": "google_verify_unconfigured"}), 503
        if not result.ok:
            cur.close()
            return jsonify({
                "error": "verification_failed",
                "message": "The store could not verify this purchase.",
                "raw_status": result.raw_status,
            }), 402

        # apple/google mode: the verifier yields the authoritative transaction
        # id (apple JWS transactionId, or the Google orderId).
        effective_txid = transaction_id
        _auth_prefixes = ('apple_verified:', 'google_verified:')
        if isinstance(result.raw_status, str) and result.raw_status.startswith(_auth_prefixes):
            effective_txid = result.raw_status.split(':', 1)[1]
            cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (effective_txid,))
            if cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING
                    """,
                    (user_id, own_tour_id, effective_txid, store,
                     _tour_price_usd(cur, product)),
                )
                conn.commit()
                cur.close()
                return jsonify({
                    "error": "already_verified",
                    "message": "This transaction has already been processed.",
                    "transaction_id": effective_txid,
                    "unlocked": True,
                    "tour_id": own_tour_id,
                }), 409

        price_usd = _tour_price_usd(cur, product)

        # Record the purchase (product = the tour store product id). UNIQUE
        # transaction_id enforces idempotency under a race.
        try:
            cur.execute("""
                INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (effective_txid, store, product, user_id, price_usd, result.raw_status))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur2 = conn.cursor()
            cur2.execute(
                """
                INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING
                """,
                (user_id, own_tour_id, effective_txid, store, price_usd),
            )
            conn.commit()
            cur2.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": effective_txid,
                "unlocked": True,
                "tour_id": own_tour_id,
            }), 409

        # Write the unlock (idempotent on UNIQUE(user_id, tour_id)): a replayed
        # purchase of the same tour by the same buyer never unlocks twice.
        cur.execute(
            """
            INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING
            """,
            (user_id, own_tour_id, effective_txid, store, price_usd),
        )
        conn.commit()
        cur.close()
        return jsonify({
            "verified": True,
            "unlocked": True,
            "tour_id": own_tour_id,
            "transaction_id": effective_txid,
            "product": product,
            "amount": price_usd,
        }), 200
    finally:
        conn.close()


def _verify_tour_signed(store, transaction_id, product, signed_transaction):
    """Verify a TOUR purchase with the configured backend.

    stub : any non-empty transaction id (sandbox) — the LOCAL path until Apple
           and Google products exist. apple : the StoreKit 2 JWS checked offline
           against the tour store product id (a Consumable). google : not yet.

    [LOCAL-734] The backend is chosen by the shared _verifier_for(store) helper,
    so per_store mode routes a tour purchase the same way as a level/pass.
    """
    mode = _verifier_for(store)
    if mode == _STUB_STORE_NOT_ALLOWED:
        return VerificationResult(False, _STUB_STORE_NOT_ALLOWED)
    if mode == _GOOGLE_NOT_CONFIGURED:
        return VerificationResult(False, _GOOGLE_NOT_CONFIGURED, unconfigured=True)

    if mode == 'stub':
        if not transaction_id:
            return VerificationResult(False, 'stub_rejected_empty_transaction')
        return VerificationResult(True, 'stub_verified',
                                  TOUR_TIER_PRODUCTS.get(product, {}).get('price_usd'))

    if mode == 'apple':
        if store != 'apple':
            return VerificationResult(False, f'apple_mode_wrong_store:{store}')
        if not signed_transaction:
            return VerificationResult(False, 'apple_missing_signed_transaction')
        try:
            from apple_jws_verifier import (
                verify_signed_transaction, JwsVerificationError,
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"[LOCAL-677] apple verifier import failed: {e}")
            return VerificationResult(False, f'apple_verifier_unavailable:{e}')
        try:
            root_pem = _load_apple_root_ca()
            verified = verify_signed_transaction(
                signed_transaction,
                root_ca_pem=root_pem,
                expected_bundle_id=APPLE_BUNDLE_ID,
                expected_product_id=product,  # the tour store product id itself
                required_type='Consumable',
                expected_environment=_APPLE_IAP_ENV_EXPECTED,
            )
        except JwsVerificationError as e:
            logger.warning(f"[LOCAL-677] apple verify failed: {e.code}")
            return VerificationResult(False, f'apple_{e.code}')
        except Exception as e:
            logger.error(f"[LOCAL-677] apple verify error: {e}")
            return VerificationResult(False, f'apple_error:{e}')
        return VerificationResult(
            True, f'apple_verified:{verified.transaction_id}',
            TOUR_TIER_PRODUCTS.get(product, {}).get('price_usd'))

    if mode == 'google':
        # [LOCAL-696] A tour product's store id IS `product`; the opaque
        # purchaseToken arrives in signed_transaction (reused field).
        return _google_verify(
            store, product_id=product, purchase_token=signed_transaction,
            expected_product_id=product,
            amount=TOUR_TIER_PRODUCTS.get(product, {}).get('price_usd'),
            tag='LOCAL-696-tour')

    return VerificationResult(False, f'verify_mode_not_implemented:{mode}')


@entitlements_bp.route('/purchases/mode', methods=['GET'])
def purchases_mode():
    """[LOCAL-699 / LOCAL-734] Report how this server verifies purchases, so the
    app can choose the right buy path on EACH platform WITHOUT guessing from a
    device-side flag.

    Returns
      {"mode": <IAP_VERIFY_MODE>, "stub": <bool>, "verifies_real": <bool>,
       "platforms": {"ios": <v>, "android": <v>}}:
      • mode          — the raw IAP_VERIFY_MODE
                        ('stub' | 'apple' | 'google' | 'per_store').
      • stub          — [legacy, unchanged for old apps] true ONLY in plain
                        'stub' mode: the whole server grants on any non-empty
                        transaction id (no real store, no charge). A per_store
                        server answers stub=FALSE even though it accepts a stub
                        store on Android — an old app (no `platforms` key) must
                        NOT treat per_store as a global TEST PURCHASE server.
      • verifies_real — the inverse of `stub` (legacy meaning preserved).
      • platforms     — [LOCAL-734] the per-platform answer a new app reads
                        first: each value is the store that platform should
                        drive — 'apple' (StoreKit), 'google' (Play billing) or
                        'stub' (the TEST PURCHASE path that posts store='stub').
                        per_store ⇒ {"ios":"apple","android":"stub"|"google"};
                        the three original modes repeat the mode on both.

    A LOCAL stack with IAP_VERIFY_MODE=stub answers stub=true; cloud (apple, the
    default) answers stub=false. The per_store Mac Mini stack answers stub=false
    with platforms={"ios":"apple","android":"stub"} (SA absent + stub allowed),
    so the iPhone drives real Apple sandbox and the Pixel runs a TEST PURCHASE,
    from ONE server. No DB access; auth is the same X-API-Key gate as the other
    routes (the local bypass applies identically)."""
    err = _require_api_key()
    if err:
        return err
    mode = IAP_VERIFY_MODE
    # Legacy field: true ONLY for plain 'stub' mode (never for per_store), so an
    # old app without the platforms key keeps today's exact behaviour.
    is_stub = (mode == 'stub')
    return jsonify({
        "mode": mode,
        "stub": is_stub,
        "verifies_real": not is_stub,
        "platforms": _platform_modes(),
    }), 200


@entitlements_bp.route('/purchases/verify', methods=['POST'])
def purchases_verify():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    store = data.get('store')
    transaction_id = data.get('transaction_id')
    product = data.get('product')
    user_id = data.get('user_id')
    # [LOCAL-598] StoreKit 2 JWS signed transaction (apple mode). Optional in
    # stub mode so existing sandbox tests keep working.
    signed_transaction = data.get('signed_transaction')

    # [LOCAL-696] Android/Google purchases carry different field names: the app
    # sends {store:'google', purchase_token, product_id, order_id}. Normalise
    # them onto the shared variables so the whole verify/record/idempotency
    # pipeline below is store-agnostic:
    #   • order_id      -> transaction_id (the authoritative Google order id;
    #                       verify re-asserts it as google_verified:<orderId>);
    #   • product_id    -> product (the Play store product id);
    #   • purchase_token-> signed_transaction (the Google verify path reads the
    #                       token from that field).
    if store == 'google':
        if not transaction_id:
            transaction_id = data.get('order_id')
        if not product:
            product = data.get('product_id')
        if not signed_transaction:
            signed_transaction = data.get('purchase_token')

    if not all([store, transaction_id, product, user_id]):
        return jsonify({
            "error": "missing_fields",
            "message": "store, transaction_id, product and user_id are all required.",
        }), 400

    # [LOCAL-690] A COMMUNITY PASS purchase (audioura.pass.*) grants/extends a
    # community membership rather than a level or a tour unlock. It is a
    # NON-RENEWING pass: the server stores community + expiry (now + duration),
    # and buying again extends/replaces the expiry (nothing renews). Delegated
    # to communities_api so one module owns all community rules.
    try:
        import communities_api
        if communities_api.is_community_pass_product(product):
            return communities_api.verify_community_pass(
                store, transaction_id, product, user_id, signed_transaction,
                community_id=data.get('community_id'),
                length=data.get('length'))
    except ImportError:  # pragma: no cover - communities module optional
        pass

    # [LOCAL-677] A TOUR price-tier purchase (audioura.tour.tierN) unlocks ONE
    # tour for the buyer rather than granting a level. It takes a separate path:
    # verify the transaction (stub accepts any non-empty id), record the purchase
    # idempotently, and write a tour_unlocks row (idempotent on
    # UNIQUE(user_id,tour_id)) so a replayed purchase never unlocks twice.
    if _is_tour_product(product):
        return _verify_tour_purchase(
            store, transaction_id, product, user_id, signed_transaction,
            tour_id=data.get('tour_id'))

    # Accept either the store product id (audioura.pack.l3) or the server key
    # (l3_pack_10). Normalize to the server key for the level mapping.
    server_product = _normalize_product(product)
    level = PRODUCT_LEVELS.get(server_product) if server_product else None
    if level is None:
        return jsonify({
            "error": "unknown_product",
            "message": f"Unknown product '{product}'.",
        }), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        # Idempotency (first pass): the client-supplied transaction_id can
        # never grant twice. In apple mode the JWS yields the authoritative id
        # which we re-check below before recording.
        cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (transaction_id,))
        if cur.fetchone():
            cur.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": transaction_id,
            }), 409

        # Verify with the store. apple mode verifies the JWS offline; google
        # mode verifies the token with the Play Developer API; stub accepts any
        # non-empty transaction_id.
        result = verify_purchase(
            store, transaction_id, server_product,
            signed_transaction=signed_transaction)
        if getattr(result, 'unconfigured', False):
            # [LOCAL-696] Google requested but no service account configured.
            cur.close()
            return jsonify({"error": "google_verify_unconfigured"}), 503
        if not result.ok:
            cur.close()
            return jsonify({
                "error": "verification_failed",
                "message": "The store could not verify this purchase.",
                "raw_status": result.raw_status,
            }), 402

        # In apple/google mode the verified transaction id is authoritative —
        # use it for recording and the uniqueness check, not the client-supplied
        # one. raw_status is 'apple_verified:<txid>' or 'google_verified:<orderId>'.
        effective_txid = transaction_id
        if isinstance(result.raw_status, str) and result.raw_status.startswith(
                ('apple_verified:', 'google_verified:')):
            effective_txid = result.raw_status.split(':', 1)[1]
            # Re-check idempotency on the authoritative id.
            cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (effective_txid,))
            if cur.fetchone():
                cur.close()
                return jsonify({
                    "error": "already_verified",
                    "message": "This transaction has already been processed.",
                    "transaction_id": effective_txid,
                }), 409

        # Record the purchase (UNIQUE transaction_id enforces idempotency even
        # under a race; catch the violation and report 409).
        try:
            cur.execute("""
                INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (effective_txid, store, server_product, user_id, result.amount, result.raw_status))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur2 = conn.cursor()
            payload = {"error": "already_verified",
                       "message": "This transaction has already been processed.",
                       "transaction_id": effective_txid}
            cur2.close()
            return jsonify(payload), 409

        # [LOCAL-733 / D703] Grant the level and start a new month at the
        # purchase (anniversary = now + 1 calendar month, clamped). A pack
        # bought while the current pack is still active carries over what is
        # left: same level ADDS, a different level converts the remainder 1:1
        # into the new level's units. An expired pack or a first purchase starts
        # fresh from zero. Carried units live as NEGATIVE used counters so
        # max(0, per_pack - used) = per_pack + carried (columns allow negatives;
        # no CHECK constraint). Idempotency above still guarantees one grant per
        # transaction.
        paid_at = datetime.utcnow()
        anniversary = add_one_calendar_month(paid_at)
        old_state = _get_device_state(cur, user_id)
        old_plan = _get_plan(cur, old_state['level'])
        new_plan = _get_plan(cur, level)
        fresh_used, edits_used, ops_used = _carry_over_used(
            old_state, old_plan, level, new_plan, paid_at)
        cur.execute("""
            INSERT INTO device_entitlement
                (user_id, level, pack_started_at, anniversary_at,
                 fresh_used, edits_used, ops_used, last_activity_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = EXCLUDED.level,
                pack_started_at = EXCLUDED.pack_started_at,
                anniversary_at = EXCLUDED.anniversary_at,
                fresh_used = EXCLUDED.fresh_used,
                edits_used = EXCLUDED.edits_used,
                ops_used = EXCLUDED.ops_used,
                updated_at = NOW()
        """, (user_id, level, paid_at, anniversary,
              fresh_used, edits_used, ops_used))
        conn.commit()

        payload = _me_payload(cur, user_id)
        payload['verified'] = True
        payload['transaction_id'] = effective_txid
        payload['granted_level'] = level
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-596] L2 seat queue + claim endpoints
# ───────────────────────────────────────────────────────────────────────────
@entitlements_bp.route('/l2/queue/join', methods=['POST'])
def l2_queue_join():
    """Join the FIFO queue for a free L2 seat.

    Body: {"user_id": "...", "email": "..."}
    L1 only (a device already holding an L2 seat is refused). Idempotent: a
    device already waiting/holding an offer gets its current position back.
    [LOCAL-604 D619] An optional email is stored on the queue row so the offer
    code can be emailed when a seat frees; it is held only while queued/offered
    and nulled on claim, leave or expiry. Returns 200 {queue_position, status}
    on success, 409 if already L2.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    email = data.get('email')
    if email is not None:
        email = str(email).strip() or None

    import l2_seats
    conn = _get_db()
    try:
        cur = conn.cursor()
        result = l2_seats.join_queue(cur, user_id, email=email)
        conn.commit()
        if not result['joined'] and result.get('reason') == 'already_l2':
            cur.close()
            return jsonify({
                "error": "already_l2",
                "message": "This device already holds an L2 seat.",
            }), 409
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/l2/queue/leave', methods=['POST'])
def l2_queue_leave():
    """Leave the FIFO queue (idempotent).

    Body: {"user_id": "..."}
    Marks the queue row 'left' and expires any live offer. Always 200.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    import l2_seats
    conn = _get_db()
    try:
        cur = conn.cursor()
        l2_seats.leave_queue(cur, user_id)
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


def _claim_referral(cur, user_id, code):
    """[LOCAL-604 D619] Cursor-based friend-invitation (referral) redemption for
    the single claim box. Mirrors referral_engine.redeem_referral_for_seat's
    checks (self, duplicate, referrer allowance by period, 100-seat cap) but
    composes inside the caller's transaction and cursor so the claim route works
    in the user-api container, whose build context cannot import repo-root
    referral_engine. The repo-root engine remains the authority for the
    /referral/redeem HTTP path; this is the same rules, cursor-style.

    Returns {'ok': bool, 'code': str, 'message': str, 'matched': bool}. matched
    is False when the code is not a referral code at all (so the caller can tell
    'no such code' from 'a referral code that was refused').
    """
    import l2_seats
    if not code or not str(code).strip():
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'No code was provided.'}

    # Referral codes live in referral_codes.code. Absent table (never created on
    # a fresh DB) → treat as "not a referral code".
    try:
        cur.execute("SELECT referrer_user_id FROM referral_codes WHERE code = %s", (code,))
    except Exception:
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'Not a referral code.'}
    row = cur.fetchone()
    if not row:
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'Not a referral code.'}
    referrer_user_id = row[0]

    if user_id == referrer_user_id:
        return {'ok': False, 'code': 'referral_self', 'matched': True,
                'message': 'You cannot redeem your own invitation code.'}

    cur.execute("""
        SELECT 1 FROM referral_redemptions
        WHERE referral_code = %s AND new_user_id = %s
    """, (code, user_id))
    if cur.fetchone():
        return {'ok': False, 'code': 'referral_duplicate', 'matched': True,
                'message': 'You have already used this invitation code.'}

    # Referrer allowance from the referrer's plan row.
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (referrer_user_id,))
    lrow = cur.fetchone()
    ref_level = lrow[0] if lrow else 'l1'
    cur.execute("SELECT referrals_allowed, referral_period FROM plans WHERE plan_id = %s",
                (ref_level,))
    arow = cur.fetchone()
    allowed = (arow[0] or 0) if arow else 0
    period = arow[1] if arow else None
    if allowed <= 0:
        return {'ok': False, 'code': 'referral_allowance_spent', 'matched': True,
                'message': 'This invitation code can no longer grant seats.'}
    window = "AND rr.redeemed_at >= date_trunc('month', CURRENT_DATE)" if period == 'month' else ""
    cur.execute(f"""
        SELECT COUNT(*) FROM referral_redemptions rr
        JOIN referral_codes rc ON rc.code = rr.referral_code
        WHERE rc.referrer_user_id = %s {window}
    """, (referrer_user_id,))
    if cur.fetchone()[0] >= allowed:
        return {'ok': False, 'code': 'referral_allowance_spent', 'matched': True,
                'message': 'This inviter has used all of their invitations.'}

    # Seat free under the cap (referral seats count against the 100 cap).
    l2_seats._acquire_seat_lock(cur)
    cap = l2_seats.get_seat_cap(cur)
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    de = cur.fetchone()
    already_l2 = de is not None and de[0] == 'l2'
    if not already_l2 and cap is not None and l2_seats.seats_in_use(cur) >= cap:
        return {'ok': False, 'code': 'referral_seats_full', 'matched': True,
                'message': 'The free level is full right now, so this invite can’t be used yet.'}

    cur.execute("UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s",
                (code,))
    cur.execute("INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)",
                (code, user_id))
    cur.execute("""
        INSERT INTO device_entitlement (user_id, level, last_activity_at)
        VALUES (%s, 'l2', NOW())
        ON CONFLICT (user_id) DO UPDATE SET level = 'l2', updated_at = NOW()
    """, (user_id,))
    return {'ok': True, 'code': 'ok', 'matched': True,
            'message': 'Invitation redeemed — you now have a free seat.'}


@entitlements_bp.route('/l2/claim', methods=['POST'])
def l2_claim():
    """Claim a level/seat with a single code box ([LOCAL-604 D619]).

    Body: {"user_id": "...", "code": "..."}
    The server decides which of THREE code kinds the code is, in this order:
      1. LEVEL CODE (level_codes, sha256 hash) — LEAD's code that moves the
         device to ANY level (incl. tester/admin), reusable, revocable. A level
         switch to l3/l4 starts a test pack. 200 on success; a revoked level
         code is refused 403 (level_code_revoked).
      2. QUEUE-OFFER CODE (l2_offers) — the queue claim offer. Grants L2 under
         the cap. Structured refusals: claim_wrong_device (403),
         claim_expired (409), claim_seats_full (409).
      3. FRIEND INVITATION (referral) CODE (referral_codes) — grants L2 under
         the cap, gated by the referrer's allowance. Refusals: referral_self
         (403), referral_duplicate (409), referral_allowance_spent (409),
         referral_seats_full (409).
    If the code matches none, 400 claim_invalid_code.
    On success returns the refreshed /me payload with claimed=true.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    code = data.get('code')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    import l2_seats
    import level_codes
    conn = _get_db()
    try:
        cur = conn.cursor()

        # ── 1. Level code (checked first) ──────────────────────────────────
        # [LOCAL-735 / D703] A code that switches to a PAID level while a paid
        # pack is active must carry over what is left, exactly as a purchase
        # does. We inject _carry_over_used (the single LOCAL-733 implementation,
        # reused — never copied into the framework-free level_codes module) via
        # a small adapter that reads the device's CURRENT pack before the switch
        # overwrites it. A code to l1/l2/tester/admin never calls this.
        def _carry_over(cur_, user_id_, new_level_, now_):
            old_state = _get_device_state(cur_, user_id_)
            old_plan = _get_plan(cur_, old_state['level'])
            new_plan = _get_plan(cur_, new_level_)
            return _carry_over_used(old_state, old_plan, new_level_, new_plan, now_)

        lc = level_codes.claim_level_code(
            cur, user_id, code, carry_over=_carry_over)
        if lc['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'level_code'
            payload['granted_level'] = lc['level']
            cur.close()
            return jsonify(payload), 200
        if lc['code'] == level_codes.LEVEL_REVOKED:
            conn.rollback()
            cur.close()
            return jsonify({
                "error": lc['code'], "error_code": lc['code'],
                "message": lc['message'],
            }), 403
        # LEVEL_NOT_FOUND → fall through to the offer path.

        # ── 2. Queue-offer code ────────────────────────────────────────────
        result = l2_seats.claim_seat(cur, user_id, code)
        if result['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'offer'
            cur.close()
            return jsonify(payload), 200
        # A genuine offer code that failed for a reason OTHER than "no such
        # code" is a real offer refusal — return it. CLAIM_BAD_CODE means the
        # code is not an offer code, so fall through to the referral path.
        if result['code'] != l2_seats.CLAIM_BAD_CODE:
            conn.rollback()
            status_map = {
                l2_seats.CLAIM_WRONG_DEVICE: 403,
                l2_seats.CLAIM_EXPIRED: 409,
                l2_seats.CLAIM_SEATS_FULL: 409,
            }
            http = status_map.get(result['code'], 400)
            cur.close()
            return jsonify({
                "error": result['code'], "error_code": result['code'],
                "message": result['message'],
            }), http

        # ── 3. Friend invitation (referral) code ───────────────────────────
        ref = _claim_referral(cur, user_id, code)
        if ref['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'referral'
            cur.close()
            return jsonify(payload), 200
        if ref['matched']:
            conn.rollback()
            status_map = {
                'referral_self': 403,
                'referral_duplicate': 409,
                'referral_allowance_spent': 409,
                'referral_seats_full': 409,
            }
            http = status_map.get(ref['code'], 400)
            cur.close()
            return jsonify({
                "error": ref['code'], "error_code": ref['code'],
                "message": ref['message'],
            }), http

        # ── Matched nothing ────────────────────────────────────────────────
        conn.rollback()
        cur.close()
        return jsonify({
            "error": l2_seats.CLAIM_BAD_CODE,
            "error_code": l2_seats.CLAIM_BAD_CODE,
            "message": "That code is not valid.",
        }), 400
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-807] Auto-renewing subscriptions — store server notifications and the
# app-reported subscription purchase.
#
# The notification endpoints are STORE-to-SERVER webhooks (Apple ASSN v2,
# Google RTDN), so they are NOT behind the X-API-Key gate the app uses — the
# store calls them directly. Their authenticity comes from the signed JWS
# (Apple, pinned to Apple Root CA G3) and the Pub/Sub + subscriptionsv2 lookup
# (Google). Every event is applied idempotently (dedupe by notification uuid).
# ───────────────────────────────────────────────────────────────────────────
@entitlements_bp.route('/iap/apple/notifications', methods=['POST'])
def apple_notifications():
    """Apple App Store Server Notifications v2. Body: {"signedPayload": "<JWS>"}.

    Verifies the signed payload (and its nested transaction/renewal JWS) against
    the pinned Apple Root CA G3, maps the notificationType to a lifecycle status
    (SUBSCRIBED, DID_RENEW, DID_FAIL_TO_RENEW, GRACE_PERIOD_EXPIRED, EXPIRED,
    REFUND, REVOKE, DID_CHANGE_RENEWAL_STATUS), and applies it idempotently.
    Returns 200 on success/duplicate so Apple stops re-delivering; a forged
    payload returns 401 (content fault), a malformed body 400."""
    import subscription_notifications as sn
    body = request.get_json(silent=True) or {}
    try:
        root_pem = _load_apple_root_ca()
        event = sn.parse_apple_notification(
            body, root_ca_pem=root_pem, expected_bundle_id=APPLE_BUNDLE_ID)
    except sn.SubscriptionNotificationError as e:
        # 200 for a handled-but-ignored type (unknown notificationType) so Apple
        # does not retry forever; the real error codes carry their http_status.
        logger.info(f"[LOCAL-807] apple notification not applied: {e.code}")
        return jsonify({"status": "ignored", "reason": e.code}), e.http_status

    conn = _get_db()
    try:
        cur = conn.cursor()
        result = sn.apply_event(cur, event,
                                user_id_hint=body.get('user_id'))
        conn.commit()
        cur.close()
        return jsonify({"status": "ok", **result}), 200
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        logger.error(f"[LOCAL-807] apple notification apply error: {e}")
        # 500 so Apple retries a genuine server-side failure.
        return jsonify({"error": "apply_failed"}), 500
    finally:
        conn.close()


@entitlements_bp.route('/iap/google/rtdn', methods=['POST'])
def google_rtdn():
    """Google Real-time developer notifications (Pub/Sub push). Body:
    {"message": {"data": "<base64 JSON>", "messageId": "..."}}.

    GATED behind GOOGLE_SUBS_ENABLED (D733 §3): until the audioura-play-verify
    service account has the subscriptions permission, this returns 503
    google_subs_disabled and never attempts a Play call. When enabled it decodes
    the RTDN, fetches the authoritative state via subscriptionsv2.get, maps the
    Google notificationType to a lifecycle status, and applies it idempotently."""
    import subscription_notifications as sn
    if not GOOGLE_SUBS_ENABLED:
        return jsonify({"error": "google_subs_disabled"}), 503

    body = request.get_json(silent=True) or {}
    client = _google_api_client()
    if client is None:
        return jsonify({"error": "google_verify_unconfigured"}), 503

    try:
        event = sn.parse_google_rtdn(
            body, api_client=client, package_name=GOOGLE_PACKAGE_NAME)
    except sn.SubscriptionNotificationError as e:
        logger.info(f"[LOCAL-807] google rtdn not applied: {e.code}")
        return jsonify({"status": "ignored", "reason": e.code}), e.http_status

    conn = _get_db()
    try:
        cur = conn.cursor()
        result = sn.apply_event(cur, event, user_id_hint=body.get('user_id'))
        conn.commit()
        cur.close()
        return jsonify({"status": "ok", **result}), 200
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        logger.error(f"[LOCAL-807] google rtdn apply error: {e}")
        return jsonify({"error": "apply_failed"}), 500
    finally:
        conn.close()


@entitlements_bp.route('/subscriptions/verify', methods=['POST'])
def subscriptions_verify():
    """[LOCAL-807] The app reports an auto-renewing subscription purchase it just
    made, so the server grants the level immediately (without waiting for the
    first server notification). Body:
        {store, user_id, product_id, signed_transaction}   (Apple JWS), or
        {store:'google', user_id, product_id, purchase_token}.

    Apple: verify the StoreKit 2 JWS offline (type='Auto-Renewable Subscription'),
    read the originalTransactionId + expiresDate, upsert the subscription row and
    set the device level. Google: gated by GOOGLE_SUBS_ENABLED; verify the token
    with subscriptionsv2.get. Idempotent on the original transaction id."""
    import subscription_notifications as sn
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    store = data.get('store')
    user_id = data.get('user_id')
    product_id = data.get('product_id') or data.get('product')
    signed_transaction = data.get('signed_transaction')
    purchase_token = data.get('purchase_token')
    if not all([store, user_id, product_id]):
        return jsonify({"error": "missing_fields",
                        "message": "store, user_id and product_id are required."}), 400

    if store == 'apple':
        if not signed_transaction:
            return jsonify({"error": "apple_missing_signed_transaction"}), 400
        try:
            from apple_jws_verifier import (
                verify_signed_transaction, JwsVerificationError)
        except Exception as e:  # pragma: no cover
            return jsonify({"error": f"apple_verifier_unavailable:{e}"}), 500
        try:
            root_pem = _load_apple_root_ca()
            verified = verify_signed_transaction(
                signed_transaction,
                root_ca_pem=root_pem,
                expected_bundle_id=APPLE_BUNDLE_ID,
                expected_product_id=product_id,
                # A subscription's type is 'Auto-Renewable Subscription', not
                # 'Consumable' — do not enforce the consumable type here.
                required_type='Auto-Renewable Subscription',
                expected_environment=_APPLE_IAP_ENV_EXPECTED,
            )
        except JwsVerificationError as e:
            return jsonify({"error": f"apple_{e.code}"}), 402
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": f"apple_error:{e}"}), 500

        p = verified.raw_payload or {}
        original_txn = (p.get('originalTransactionId')
                        or verified.transaction_id)
        expires = p.get('expiresDate')
        period_end = None
        if expires is not None:
            try:
                period_end = datetime.utcfromtimestamp(float(expires) / 1000.0)
            except (TypeError, ValueError, OSError, OverflowError):
                period_end = None
        event = sn.SubscriptionEvent(
            store='apple',
            notification_uuid=f'app_verify:{original_txn}:{verified.transaction_id}',
            notification_type='APP_REPORTED_PURCHASE',
            target_status=sn.STATUS_ACTIVE,
            original_transaction_id=str(original_txn),
            product_id=product_id,
            period_end=period_end,
            auto_renew=True,
            event_at=datetime.utcnow(),
            raw_summary={'source': 'app', 'productId': product_id},
        )
    elif store == 'google':
        if not GOOGLE_SUBS_ENABLED:
            return jsonify({"error": "google_subs_disabled"}), 503
        client = _google_api_client()
        if client is None:
            return jsonify({"error": "google_verify_unconfigured"}), 503
        if not purchase_token:
            return jsonify({"error": "google_missing_purchase_token"}), 400
        try:
            state = client.get_subscription_v2(GOOGLE_PACKAGE_NAME, purchase_token)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": f"google_subs_get_failed:{e}"}), 402
        period_end = None
        line_items = state.get('lineItems') or []
        if line_items:
            period_end = sn._parse_rfc3339(line_items[0].get('expiryTime'))
        event = sn.SubscriptionEvent(
            store='google',
            notification_uuid=f'app_verify:{purchase_token}',
            notification_type='APP_REPORTED_PURCHASE',
            target_status=sn.STATUS_ACTIVE,
            original_transaction_id=str(purchase_token),
            product_id=product_id,
            period_end=period_end,
            auto_renew=True,
            event_at=datetime.utcnow(),
            raw_summary={'source': 'app', 'productId': product_id},
        )
    else:
        return jsonify({"error": f"unsupported_store:{store}"}), 400

    conn = _get_db()
    try:
        cur = conn.cursor()
        result = sn.apply_event(cur, event, user_id_hint=user_id)
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify({"status": "ok", "result": result, "entitlements": payload}), 200
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        logger.error(f"[LOCAL-807] subscriptions/verify apply error: {e}")
        return jsonify({"error": "apply_failed"}), 500
    finally:
        conn.close()
