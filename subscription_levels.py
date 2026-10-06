"""
subscription_levels.py — LOCAL-595 enforcement for the L1/L2/L3/L4/Tester model.
================================================================================

Design of record: SUBSCRIPTION_LEVELS.md (D613, ClickUp wdvrdayu5a).

This is the single decision point the orchestrator (generate) and the editing
service (add-stops) call:

    check_operation(user_id, op, requested_stops, new_stops=0) -> dict

It returns either an ALLOW result (allowed=True, with clamped_stops), or a
STRUCTURED REFUSAL that follows the LOCAL-580 error contract:
    error_code  — a stable enum
    message     — one plain-language sentence
    suggestion  — a short actionable hint

error_code values this module emits:
    plan_limit_daily, plan_limit_monthly, pack_exhausted,
    level_cannot_generate, stops_over_plan, renewal_due,
    by_reference_unavailable   (L2 generate, until LOCAL-597)

Every number comes from the `plans` row for the device's level — the code holds
NO tier constants. Per-device state (level, pack window, counters) lives in
`device_entitlement`. A device with no row is treated as L1 (install default).

The wallet / PPU / Unlimited model is superseded: nothing here reads or writes
wallet_* / subscriptions / cost_ledger. Routing of free/ppu/unlimited plans
stays in entitlements.check_tour_quota for backward compatibility.
"""

import os
import logging
import calendar
from datetime import datetime, date, timedelta

import psycopg2

logger = logging.getLogger(__name__)

# Operations that never generate fresh content — always allowed, at every level
# (listen, download, read articles, reuse an existing translation, re-voice an
# edit that adds no stops). The design: "edits that only re-voice text are
# always allowed."
_ALWAYS_ALLOWED_OPS = frozenset({'edit_text', 'listen', 'download', 'translate_reuse'})

# Operations that consume a fresh-generation or stop-adding allowance.
_GATED_OPS = frozenset({'generate', 'edit_add_stops'})

_ALL_OPS = _ALWAYS_ALLOWED_OPS | _GATED_OPS


def _get_conn():
    """Connect using the same env contract as entitlements.py."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432'),
    )


# ───────────────────────────────────────────────────────────────────────────
# Anniversary arithmetic
# ───────────────────────────────────────────────────────────────────────────
def add_one_calendar_month(when):
    """Payment date + 1 calendar month, clamped to the target month's last day.

    Examples (per the design doc and Michael's cases):
        Jan 31 -> Feb 28 (Feb 29 in a leap year)
        May 31 -> Jun 30
        May 1  -> Jun 1
        Jun 1  -> Jul 1

    Preserves the time-of-day component. Accepts date or datetime; returns the
    same type it was given.
    """
    is_datetime = isinstance(when, datetime)
    y, m, d = when.year, when.month, when.day
    # Advance the month, rolling the year over December.
    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    # Clamp the day to the last valid day of the target month.
    last_day = calendar.monthrange(ny, nm)[1]
    nd = min(d, last_day)
    if is_datetime:
        return when.replace(year=ny, month=nm, day=nd)
    return date(ny, nm, nd)


def is_renewal_due(anniversary_at, now=None):
    """True at or after the anniversary (boundary INCLUSIVE — at the instant the
    anniversary arrives, renewal is due). None anniversary -> never due."""
    if anniversary_at is None:
        return False
    now = now or datetime.utcnow()
    return now >= anniversary_at


def warn_renewal(anniversary_at, now=None, days=3):
    """True within `days` before the anniversary (the 3-day warning window), and
    not yet due. None anniversary -> no warning."""
    if anniversary_at is None:
        return False
    now = now or datetime.utcnow()
    if now >= anniversary_at:
        return False
    return now >= (anniversary_at - timedelta(days=days))


# ───────────────────────────────────────────────────────────────────────────
# Device state + plan access
# ───────────────────────────────────────────────────────────────────────────
def get_plan_row(cur, level):
    """Fetch the plans row for a level as a dict of the LOCAL-595 columns.
    Returns None if the level is unknown."""
    cur.execute("""
        SELECT plan_id, tours_per_day, tours_per_month, fresh_per_pack,
               edits_per_pack, ops_per_pack, max_stops, max_new_stops_per_edit,
               by_reference_only, referrals_allowed, referral_period, seat_cap,
               can_sell, price_usd, inactivity_days
        FROM plans WHERE plan_id = %s
    """, (level,))
    row = cur.fetchone()
    if not row:
        return None
    cols = ['plan_id', 'tours_per_day', 'tours_per_month', 'fresh_per_pack',
            'edits_per_pack', 'ops_per_pack', 'max_stops', 'max_new_stops_per_edit',
            'by_reference_only', 'referrals_allowed', 'referral_period', 'seat_cap',
            'can_sell', 'price_usd', 'inactivity_days']
    return dict(zip(cols, row))


def get_device_state(cur, user_id):
    """Fetch the device_entitlement row as a dict, or a synthetic L1 default if
    the device has no row yet (install default)."""
    cur.execute("""
        SELECT user_id, level, pack_started_at, anniversary_at,
               fresh_used, edits_used, ops_used, last_activity_at
        FROM device_entitlement WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        return {
            'user_id': user_id, 'level': 'l1', 'pack_started_at': None,
            'anniversary_at': None, 'fresh_used': 0, 'edits_used': 0,
            'ops_used': 0, 'last_activity_at': None, '_exists': False,
        }
    cols = ['user_id', 'level', 'pack_started_at', 'anniversary_at',
            'fresh_used', 'edits_used', 'ops_used', 'last_activity_at']
    d = dict(zip(cols, row))
    d['_exists'] = True
    return d


def ensure_device(user_id, level='l1'):
    """Create a device_entitlement row if absent (install default L1). Idempotent."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, level))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def record_activity(user_id):
    """Record any app activity (app-open, listen, download). Creates the device
    row at L1 if missing. Returns the resulting state dict with renewal flags."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET last_activity_at = NOW(), updated_at = NOW()
        """, (user_id,))
        conn.commit()
        state = get_device_state(cur, user_id)
        cur.close()
        return state
    finally:
        conn.close()


def lapse_to_l1(user_id):
    """Drop a device to L1 and clear its pack window/counters. Idempotent."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = 'l1',
                pack_started_at = NULL,
                anniversary_at = NULL,
                fresh_used = 0,
                edits_used = 0,
                ops_used = 0,
                updated_at = NOW()
        """, (user_id,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def grant_pack(user_id, level, paid_at=None):
    """Grant / renew a paid level: set the level, reset the pack counters and
    set a fresh anniversary (paid_at + 1 calendar month, clamped). Paying early
    resets the date and replaces the allowance (unused units do not carry over).

    Returns the new state dict.
    """
    paid_at = paid_at or datetime.utcnow()
    anniversary = add_one_calendar_month(paid_at)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement
                (user_id, level, pack_started_at, anniversary_at,
                 fresh_used, edits_used, ops_used, last_activity_at)
            VALUES (%s, %s, %s, %s, 0, 0, 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = EXCLUDED.level,
                pack_started_at = EXCLUDED.pack_started_at,
                anniversary_at = EXCLUDED.anniversary_at,
                fresh_used = 0,
                edits_used = 0,
                ops_used = 0,
                updated_at = NOW()
        """, (user_id, level, paid_at, anniversary))
        conn.commit()
        state = get_device_state(cur, user_id)
        cur.close()
        return state
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Period counting for L2 / Tester (daily & monthly fresh-generation caps)
# ───────────────────────────────────────────────────────────────────────────
def _count_fresh_generations(cur, user_id, scope):
    """Count DELIVERED generations by this device today ('day') or this calendar
    month ('month'). Uses tour_requests rows written by the orchestrator — the
    single authoritative writer (source='orchestrator').

    [LOCAL-595B defect 2] Count only status='completed' rows. A tour that was
    requested but never delivered (status 'started' = in flight, or 'failed' =
    generation/credit/factual-integrity failure) must NOT consume the device's
    daily/monthly allowance: a listener who hit a failure keeps their tour.
    The orchestrator reserves a row at 'started', flips it to 'completed' on
    successful delivery, and to 'failed' on error (see release_reservation).

    [LOCAL-595B defect 3] A cache hit / stop-pool-only tour still reaches
    'completed' (it was delivered), so it DOES count here — these caps limit
    volume, not cost. Only the L3 fresh_used / L4 ops_used cost pools are
    released for a cache hit.
    """
    if scope == 'day':
        where = "started_at::date = CURRENT_DATE"
    else:  # month
        where = "started_at >= date_trunc('month', CURRENT_DATE)"
    cur.execute(f"""
        SELECT COUNT(*) FROM tour_requests
        WHERE secret_id = %s AND source = 'orchestrator'
          AND status = 'completed' AND {where}
    """, (user_id,))
    return cur.fetchone()[0]


# ───────────────────────────────────────────────────────────────────────────
# Structured refusal helpers (LOCAL-580 contract)
# ───────────────────────────────────────────────────────────────────────────
def _refuse(error_code, message, suggestion, **extra):
    out = {
        'allowed': False,
        'error_code': error_code,
        'error': message,       # legacy field for pre-LOCAL-581 clients
        'message': message,
        'suggestion': suggestion,
    }
    out.update(extra)
    return out


def _allow(level, clamped_stops, **extra):
    out = {
        'allowed': True,
        'error_code': None,
        'level': level,
        'clamped_stops': clamped_stops,
    }
    out.update(extra)
    return out


# ───────────────────────────────────────────────────────────────────────────
# The single decision point
# ───────────────────────────────────────────────────────────────────────────
def check_operation(user_id, op, requested_stops=0, new_stops=0, now=None):
    """Decide whether `op` is allowed for `user_id` under the levels model.

    Args:
        user_id: anonymous device / secret_id.
        op: one of generate / edit_add_stops / edit_text / listen / download /
            translate_reuse.
        requested_stops: tour size being requested (for generate / stop clamp).
        new_stops: number of NEW stops an edit would add (for edit_add_stops).
        now: optional datetime override (tests).

    Returns an allow dict or a structured refusal (see module docstring).
    FAIL-CLOSED: on any internal error, refuse.
    """
    now = now or datetime.utcnow()

    if op not in _ALL_OPS:
        return _refuse(
            'generation_failed',
            f"Unknown operation '{op}'.",
            "Contact support — this is a client bug.",
        )

    # Re-voicing / listening / downloading / reusing a translation is free at
    # every level and never touches an allowance. (Checked before any DB work.)
    if op in _ALWAYS_ALLOWED_OPS:
        return _allow(level=None, clamped_stops=requested_stops, free_operation=True)

    if not user_id or not user_id.strip():
        return _refuse(
            'level_cannot_generate',
            "A valid device id is required to generate or edit tours.",
            "Reinstall the app or contact support.",
        )

    try:
        conn = _get_conn()
    except Exception as e:
        logger.error(f"[LEVELS] DB connection error for {user_id}: {e}")
        return _refuse(
            'generation_failed',
            "We could not verify your plan right now. Please try again in a moment.",
            "Try again shortly.",
        )

    try:
        cur = conn.cursor()
        state = get_device_state(cur, user_id)
        level = state['level']
        plan = get_plan_row(cur, level)
        if plan is None:
            logger.error(f"[LEVELS] Unknown level '{level}' for {user_id}")
            cur.close()
            return _refuse(
                'generation_failed',
                "Your plan is misconfigured. Please contact support.",
                "Contact support.",
            )

        # Anniversary gate: at/after the anniversary, generate & edits are
        # refused with renewal_due until the device renews or lapses. Listening
        # is still allowed (handled above as an always-allowed op).
        if is_renewal_due(state['anniversary_at'], now):
            cur.close()
            return _refuse(
                'renewal_due',
                "Your pack has reached its renewal date. Renew to generate new tours, "
                "or keep listening to what you already have.",
                f"Renew your ${plan['price_usd']:.0f} pack, or drop to the free level.",
                level=level,
            )

        # ─── generate ──────────────────────────────────────────────────────
        if op == 'generate':
            result = _check_generate(cur, user_id, level, plan, requested_stops)
            cur.close()
            return result

        # ─── edit_add_stops ──────────────────────────────────────────────────
        if op == 'edit_add_stops':
            result = _check_edit_add_stops(cur, user_id, level, plan, new_stops)
            cur.close()
            return result

        cur.close()
        return _refuse('generation_failed', f"Unhandled operation '{op}'.", "Contact support.")
    except Exception as e:
        logger.error(f"[LEVELS] check_operation error for {user_id} op={op}: {e}")
        return _refuse(
            'generation_failed',
            "We could not verify your plan right now. Please try again in a moment.",
            "Try again shortly.",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _clamp_or_refuse_stops(plan, requested_stops):
    """Return (clamped_stops, refusal_or_None). max_stops=0 means the level may
    not generate at all. A request over max_stops is refused (not silently
    clamped) because a stop list is a promise — matching the orchestrator's
    existing stops_exceed_plan behaviour."""
    max_stops = plan['max_stops'] or 0
    if max_stops <= 0:
        return 0, _refuse(
            'level_cannot_generate',
            "Your level does not include new tours.",
            "Buy a $10 pack for 5 new tours.",
            level=plan['plan_id'],
        )
    if requested_stops and requested_stops > max_stops:
        return max_stops, _refuse(
            'stops_over_plan',
            f"You asked for {requested_stops} stops, but your level allows at most {max_stops}.",
            f"Reduce the tour to {max_stops} stops or fewer, or upgrade your level.",
            level=plan['plan_id'],
            max_stops=max_stops,
            requested_stops=requested_stops,
        )
    clamped = min(requested_stops, max_stops) if requested_stops else max_stops
    return clamped, None


def _check_generate(cur, user_id, level, plan, requested_stops):
    # L1: no new tours at all.
    if level == 'l1':
        return _refuse(
            'level_cannot_generate',
            "The free install level does not include generating new tours.",
            "Buy a $10 pack for 5 new tours, or join the free queue.",
            level=level,
        )

    # Stop ceiling (also catches max_stops=0).
    clamped, refusal = _clamp_or_refuse_stops(plan, requested_stops)
    if refusal:
        return refusal

    # L2: by-reference only. The by-reference generation path is LOCAL-597; until
    # then L2 generate is refused with a stable, documented code.
    if plan['by_reference_only']:
        # Still enforce the daily/monthly caps so the refusal is honest about why
        # even once 597 lands the counting is in place.
        daily_cap = plan['tours_per_day']
        monthly_cap = plan['tours_per_month']
        if daily_cap is not None:
            used_today = _count_fresh_generations(cur, user_id, 'day')
            if used_today >= daily_cap:
                return _refuse(
                    'plan_limit_daily',
                    f"You've used your {daily_cap} free tour(s) for today.",
                    "Come back tomorrow, or buy a $10 pack for 5 new tours.",
                    level=level, used=used_today, max=daily_cap,
                )
        if monthly_cap is not None:
            used_month = _count_fresh_generations(cur, user_id, 'month')
            if used_month >= monthly_cap:
                return _refuse(
                    'plan_limit_monthly',
                    f"You've used your {monthly_cap} free tours for this month.",
                    "Buy a $10 pack for 5 new tours.",
                    level=level, used=used_month, max=monthly_cap,
                )
        return _refuse(
            'by_reference_unavailable',
            "Free tours reuse already-researched places, and that path isn't available yet.",
            "Buy a $10 pack for a freshly researched tour, or pick a nearby existing tour.",
            level=level,
        )

    # Tester: daily + monthly fresh-generation caps.
    if plan['tours_per_day'] is not None or plan['tours_per_month'] is not None:
        daily_cap = plan['tours_per_day']
        monthly_cap = plan['tours_per_month']
        if daily_cap is not None and daily_cap < 999:
            used_today = _count_fresh_generations(cur, user_id, 'day')
            if used_today >= daily_cap:
                return _refuse(
                    'plan_limit_daily',
                    f"You've reached your {daily_cap} tours for today.",
                    "Come back tomorrow.",
                    level=level, used=used_today, max=daily_cap,
                )
        if monthly_cap is not None:
            used_month = _count_fresh_generations(cur, user_id, 'month')
            if used_month >= monthly_cap:
                return _refuse(
                    'plan_limit_monthly',
                    f"You've reached your {monthly_cap} tours for this month.",
                    "Your monthly allowance resets at the start of next month.",
                    level=level, used=used_month, max=monthly_cap,
                )

    # L3: consumable fresh-per-pack pool.
    if plan['fresh_per_pack'] is not None:
        state = get_device_state(cur, user_id)
        if state['fresh_used'] >= plan['fresh_per_pack']:
            return _refuse(
                'pack_exhausted',
                f"You've used all {plan['fresh_per_pack']} new tours in your pack.",
                "Buy another $10 pack for 5 more new tours.",
                level=level, used=state['fresh_used'], max=plan['fresh_per_pack'],
            )

    # L4: combined ops pool (new + edit).
    if plan['ops_per_pack'] is not None:
        state = get_device_state(cur, user_id)
        if state['ops_used'] >= plan['ops_per_pack']:
            return _refuse(
                'pack_exhausted',
                f"You've used all {plan['ops_per_pack']} operations in your round.",
                "Buy another $25 round for 25 more operations.",
                level=level, used=state['ops_used'], max=plan['ops_per_pack'],
            )

    return _allow(level=level, clamped_stops=clamped)


def _check_edit_add_stops(cur, user_id, level, plan, new_stops):
    # Adding zero new stops is a text-only edit — always allowed.
    if not new_stops or new_stops <= 0:
        return _allow(level=level, clamped_stops=0, free_operation=True)

    # L1 / L2 cannot add stops at all (max_new_stops_per_edit == 0).
    cap = plan['max_new_stops_per_edit'] or 0
    if cap <= 0:
        return _refuse(
            'level_cannot_generate',
            "Your level does not include edits that add new stops.",
            "Buy a $10 pack to add stops to your tours.",
            level=level,
        )

    # Per-edit new-stop ceiling.
    if new_stops > cap:
        return _refuse(
            'stops_over_plan',
            f"This edit adds {new_stops} stops, but your level allows at most {cap} new stops per edit.",
            f"Add {cap} stops or fewer per edit, or upgrade your level.",
            level=level, max_new_stops_per_edit=cap, new_stops=new_stops,
        )

    # L3: edits_per_pack pool.
    if plan['edits_per_pack'] is not None:
        state = get_device_state(cur, user_id)
        if state['edits_used'] >= plan['edits_per_pack']:
            return _refuse(
                'pack_exhausted',
                f"You've used all {plan['edits_per_pack']} stop-adding edits in your pack.",
                "Buy another $10 pack for 5 more edits.",
                level=level, used=state['edits_used'], max=plan['edits_per_pack'],
            )

    # L4: combined ops pool (new + edit).
    if plan['ops_per_pack'] is not None:
        state = get_device_state(cur, user_id)
        if state['ops_used'] >= plan['ops_per_pack']:
            return _refuse(
                'pack_exhausted',
                f"You've used all {plan['ops_per_pack']} operations in your round.",
                "Buy another $25 round for 25 more operations.",
                level=level, used=state['ops_used'], max=plan['ops_per_pack'],
            )

    return _allow(level=level, clamped_stops=new_stops)


# ───────────────────────────────────────────────────────────────────────────
# Pack-counter reservation / release (L3 fresh_used, L4 ops_used).
# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-595B defect 2] The orchestrator RESERVES a pack unit at request time
# (before generation) so that two concurrent requests cannot both pass a limit
# of 1 — the reservation is the concurrency guard. On successful FRESH delivery
# the reservation stands (it is the real consumption). On FAILURE, or on a
# [defect 3] CACHE HIT / stop-pool-only delivery that cost ~$0, the orchestrator
# RELEASES the reservation so the paid allowance is not spent. L2/Tester period
# levels are counted from completed tour_requests rows (not these counters), so
# they neither reserve nor release here.
def reserve(user_id, op, new_stops=0):
    """Increment the appropriate pack counter when a gated op is about to run.

    - generate       : L3 fresh_used++, L4 ops_used++.
    - edit_add_stops : L3 edits_used++, L4 ops_used++ (only when new_stops>0).

    Period levels (L2/Tester) count via completed tour_requests, so no bump.
    Best-effort; failure is logged, not raised.
    """
    if op == 'edit_add_stops' and (not new_stops or new_stops <= 0):
        return  # text-only edit reserves nothing
    conn = _get_conn()
    try:
        cur = conn.cursor()
        state = get_device_state(cur, user_id)
        level = state['level']
        plan = get_plan_row(cur, level)
        if plan is None:
            cur.close()
            return
        if op == 'generate':
            if plan['fresh_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET fresh_used = fresh_used + 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            if plan['ops_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET ops_used = ops_used + 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
        elif op == 'edit_add_stops':
            if plan['edits_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET edits_used = edits_used + 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
            if plan['ops_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET ops_used = ops_used + 1, updated_at = NOW() WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"[LEVELS] reserve error for {user_id} op={op}: {e}")
    finally:
        conn.close()


# Backward-compatible name. The orchestrator/editing service historically called
# `consume_operation` at request time; that call is now a RESERVATION (released
# on failure / cache hit). Kept as an alias so existing imports keep working.
consume = reserve


def release(user_id, op, new_stops=0):
    """Give back a pack unit reserved by `reserve`, flooring the counter at 0.

    Called by the orchestrator when a reserved generation did NOT result in a
    fresh paid delivery:
      * generation failed  (defect 2), or
      * the tour was served from cache / the stop pool at ~$0 (defect 3).

    Idempotency / correctness is the caller's concern (one release per reserve).
    Best-effort; failure is logged, not raised.
    """
    if op == 'edit_add_stops' and (not new_stops or new_stops <= 0):
        return  # nothing was reserved for a text-only edit
    conn = _get_conn()
    try:
        cur = conn.cursor()
        state = get_device_state(cur, user_id)
        level = state['level']
        plan = get_plan_row(cur, level)
        if plan is None:
            cur.close()
            return
        # GREATEST(x-1, 0) so a double-release or a release with no prior reserve
        # can never drive a counter negative.
        if op == 'generate':
            if plan['fresh_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET fresh_used = GREATEST(fresh_used - 1, 0), updated_at = NOW() WHERE user_id = %s", (user_id,))
            if plan['ops_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET ops_used = GREATEST(ops_used - 1, 0), updated_at = NOW() WHERE user_id = %s", (user_id,))
        elif op == 'edit_add_stops':
            if plan['edits_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET edits_used = GREATEST(edits_used - 1, 0), updated_at = NOW() WHERE user_id = %s", (user_id,))
            if plan['ops_per_pack'] is not None:
                cur.execute("UPDATE device_entitlement SET ops_used = GREATEST(ops_used - 1, 0), updated_at = NOW() WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"[LEVELS] release error for {user_id} op={op}: {e}")
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Edit (add-stops) gate decision — pure, framework-free, so the editing service
# AND tests can share one implementation without importing Flask/boto3.
# ───────────────────────────────────────────────────────────────────────────
def evaluate_edit_add_stops(data):
    """[LOCAL-595B defect 4] Decide an edit's add-stops gate from the request body.

    `data` is the parsed edit request body ({'stops': [...], optional 'user_id'
    or 'secret_id'}).

    Returns a dict:
        {
          'new_stops': int,            # stops with action='add'
          'user_id':   str|None,       # resolved device id, if any
          'gated':     bool,           # whether the add-stops gate applies
          'proceed':   bool,           # True => caller may continue the save
          'status':    int|None,       # HTTP status to return when not proceeding
          'body':      dict|None,      # response body when not proceeding
        }

    FAIL CLOSED: an add-stops edit with no user id -> 401 user_id_required.
    A text-only edit (new_stops == 0) is never gated (proceed=True). When an id
    is present, the levels check runs; on allow the caller must still consume the
    pack allowance via consume(user_id, 'edit_add_stops', new_stops).
    """
    stops = (data or {}).get('stops', []) or []
    new_stops = sum(1 for s in stops if str(s.get('action', '')).lower() == 'add')
    user_id = (data or {}).get('user_id') or (data or {}).get('secret_id')

    # Text-only / re-voice edit — always allowed, never gated.
    if new_stops <= 0:
        return {'new_stops': 0, 'user_id': user_id, 'gated': False,
                'proceed': True, 'status': None, 'body': None}

    # Add-stops edit with no id — refuse, never silently allow (fail-closed).
    if not user_id or not str(user_id).strip():
        return {
            'new_stops': new_stops, 'user_id': None, 'gated': True,
            'proceed': False, 'status': 401,
            'body': {
                'allowed': False,
                'error_code': 'user_id_required',
                'error': 'A valid device id is required to add stops to a tour.',
                'message': 'A valid device id is required to add stops to a tour.',
                'suggestion': 'Update the app so it sends your device id with edits.',
            },
        }

    try:
        gate = check_operation(user_id, 'edit_add_stops', new_stops=new_stops)
    except Exception as e:
        logger.error(f"[LEVELS] edit_add_stops gate error for {user_id}: {e}")
        return {
            'new_stops': new_stops, 'user_id': user_id, 'gated': True,
            'proceed': False, 'status': 503,
            'body': {
                'status': 'error', 'error_code': 'generation_failed',
                'message': 'Could not verify your plan. Please try again.',
            },
        }

    if not gate.get('allowed'):
        return {'new_stops': new_stops, 'user_id': user_id, 'gated': True,
                'proceed': False, 'status': 429, 'body': gate}

    return {'new_stops': new_stops, 'user_id': user_id, 'gated': True,
            'proceed': True, 'status': None, 'body': None}
