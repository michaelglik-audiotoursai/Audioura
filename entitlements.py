"""
Audioura Entitlements — Data-driven usage limits.
===================================================

Limits live in the `plans` table (changeable via SQL, no redeploy).
Users have a `plan` field (default 'free').
Enforcement is server-side, keyed on user_id.

For paid tiers (ppu, unlimited), the check transitions from quota-count logic
to balance/cost-stop logic. This is done by extending check_tour_quota() and
check_news_quota() to inspect the subscriptions table when plan != 'free'.
Same call site, same user_id path — no duplication needed.

The gate returns a STRUCTURED result the app can act on:
    - allowed: bool
    - reason: str (why denied, or 'ok')
    - remedy: str or None (what the user can do)
Plus additional fields per tier for backward compatibility.

Usage:
    from entitlements import check_tour_quota, check_news_quota

    # In tour-orchestrator before generation:
    result = check_tour_quota(user_id, requested_stops)
    if result['allowed'] is False:
        return jsonify(result), 429

    # In news-orchestrator before processing:
    result = check_news_quota(user_id)
    if result['allowed'] is False:
        return jsonify(result), 429
"""

import os
import logging
import psycopg2
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


def get_user_plan(user_id):
    """Get the user's plan limits. Returns plan dict or free-tier defaults.
    Supports per-user tours_per_day_override (COALESCE: override > plan > default).
    Raises on DB connection errors (caller returns 503).
    """
    if not user_id or user_id.strip() == '':
        # Anonymous/empty user — return free defaults immediately (no DB hit)
        print(f"[ENTITLEMENTS] Empty user_id — returning free defaults")
        return {
            'plan_id': 'free',
            'tours_per_day': 1,
            'tour_max_poi': 30,
            'tour_max_minutes': 120,
            'news_per_period': 10,
            'news_period': 'week',
            'news_max_minutes': 10,
            'downloads_unlimited': True
        }
    try:
        conn = _get_conn()
    except Exception as e:
        # DB connection failure — raise so orchestrator returns 503
        print(f"[ENTITLEMENTS] DB CONNECTION ERROR getting plan for {user_id}: {e}")
        raise

    try:
        cur = conn.cursor()
        # Get user's plan with per-user override support
        cur.execute("""
            SELECT p.plan_id,
                   COALESCE(u.tours_per_day_override, p.tours_per_day) AS tours_per_day,
                   p.tour_max_poi, p.tour_max_minutes,
                   p.news_per_period, p.news_period, p.news_max_minutes, p.downloads_unlimited
            FROM users u
            JOIN plans p ON u.plan = p.plan_id
            WHERE u.secret_id = %s
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        
        if not row:
            # User not in users table or no plan — default to free
            cur.execute("SELECT plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited FROM plans WHERE plan_id = 'free'")
            row = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if row:
            return {
                'plan_id': row[0],
                'tours_per_day': row[1],
                'tour_max_poi': row[2],
                'tour_max_minutes': row[3],
                'news_per_period': row[4],
                'news_period': row[5],
                'news_max_minutes': row[6],
                'downloads_unlimited': row[7]
            }
    except Exception as e:
        print(f"[ENTITLEMENTS] Error querying plan for {user_id}: {e}")
        try:
            conn.close()
        except Exception:
            pass
    
    # Fallback defaults if query fails (connected but query error) — last-resort backstop
    return {
        'plan_id': 'free',
        'tours_per_day': 1,
        'tour_max_poi': 30,
        'tour_max_minutes': 120,
        'news_per_period': 10,
        'news_period': 'week',
        'news_max_minutes': 10,
        'downloads_unlimited': True
    }


def _get_subscription_tier(user_id):
    """Get the user's subscription tier if they currently have access.

    Access-granting states:
      - 'active': normal paid subscription.
      - 'billing_retry': payment failed but within Apple's grace window
        (typically 16 days). Access continues while Apple retries.
      - 'cancelled': user cancelled auto-renew but has paid through period_end.
        Apple keeps the entitlement alive until period_end — cutting off early
        takes money for service not delivered.

    For 'cancelled', access is granted ONLY when period_end is still in the
    future. At or past period_end the row is treated as expired (returns None).

    Returns tier string ('ppu' or 'unlimited') or None if no current access.
    Raises on DB connection errors (caller fails closed).
    """
    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[ENTITLEMENTS] DB CONNECTION ERROR getting subscription for {user_id}: {e}")
        raise

    try:
        cur = conn.cursor()
        # First: check straightforward active/billing_retry states
        cur.execute("""
            SELECT tier FROM subscriptions
            WHERE user_id = %s AND state IN ('active', 'billing_retry')
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        if row:
            cur.close()
            conn.close()
            return row[0]

        # Second: check cancelled-but-not-yet-expired (Apple grace period to period_end)
        cur.execute("""
            SELECT tier FROM subscriptions
            WHERE user_id = %s AND state = 'cancelled' AND period_end > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"[ENTITLEMENTS] Error querying subscription for {user_id}: {e}")
        try:
            conn.close()
        except Exception:
            pass
        raise


def _check_ppu_balance(user_id):
    """Check Pay-Per-Use wallet balance. Returns structured result.
    Zero or negative balance → hard stop with low-balance reminder (D3).
    """
    from wallet_ledger import get_balance_cents, check_low_balance, CREDIT_TOPUP_USD

    balance_cents = get_balance_cents(user_id)
    
    if balance_cents <= 0:
        # Hard stop — zero balance means no service (D3)
        balance_usd = Decimal(balance_cents) / Decimal(100)
        return {
            'allowed': False,
            'reason': 'insufficient_balance',
            'remedy': 'topup',
            'error': 'insufficient_balance',
            'plan': 'ppu',
            'balance_usd': f"{balance_usd:.2f}",
            'balance_cents': balance_cents,
            'message': (
                f"Your balance is ${balance_usd:.2f}. "
                f"Top up ${CREDIT_TOPUP_USD:.2f} to continue generating audio tours and articles."
            ),
        }
    
    # Check low balance for reminder (non-blocking)
    low_balance_msg = check_low_balance(user_id)
    
    return {
        'allowed': True,
        'reason': 'ok',
        'remedy': None,
        'plan': 'ppu',
        'balance_cents': balance_cents,
        'low_balance_reminder': low_balance_msg,
    }


def _check_unlimited_cost_stop(user_id):
    """Check Unlimited tier cost stop. Returns structured result.
    Breach → clear message + offer to switch to Pay-Per-Use (D4).
    """
    from wallet_ledger import check_unlimited_cost_stop, UNLIMITED_COST_STOP_USD

    result = check_unlimited_cost_stop(user_id)
    
    if result['breached']:
        return {
            'allowed': False,
            'reason': 'cost_stop_reached',
            'remedy': 'switch_to_ppu',
            'error': 'cost_stop_reached',
            'plan': 'unlimited',
            'current_cost_usd': str(result['current_cost_usd']),
            'limit_usd': str(result['limit_usd']),
            'message': result['message'],
        }
    
    return {
        'allowed': True,
        'reason': 'ok',
        'remedy': None,
        'plan': 'unlimited',
        'current_cost_usd': str(result['current_cost_usd']),
        'limit_usd': str(result['limit_usd']),
    }


def get_tours_used_today(user_id):
    """Count tours generated today by this user. 
    Raises on DB connection errors (caller returns 503).
    Returns 9999 only on unexpected query errors (last-resort backstop).
    Only counts orchestrator-written rows (source='orchestrator') — the single authoritative writer."""
    try:
        conn = _get_conn()
    except Exception as e:
        # DB connection failure — raise so orchestrator returns 503
        print(f"[ENTITLEMENTS] DB CONNECTION ERROR counting tours for {user_id}: {e}")
        raise

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM tour_requests 
            WHERE secret_id = %s AND started_at::date = CURRENT_DATE
            AND source = 'orchestrator'
        """, (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"[ENTITLEMENTS] ERROR counting tours for {user_id}: {e} — DENYING (fail-closed)")
        try:
            conn.close()
        except Exception:
            pass
        return 9999  # Last-resort backstop: deny on query error


def get_news_used_period(user_id, period='week'):
    """Count news quota units consumed this period by this user.
    
    Counting rules:
      - Direct articles (not linked to a newsletter) count as 1 each.
      - Newsletter debit rows (status='newsletter_debit') count as 1 each.
      - Newsletter-sourced articles (linked via newsletters_article_link) are EXCLUDED
        because the newsletter debit row already accounts for the whole batch.
    
    Raises on DB connection errors (caller returns 503).
    Returns 9999 only on unexpected non-connection errors (last-resort backstop)."""
    try:
        conn = _get_conn()
    except Exception as e:
        # DB connection failure — raise so orchestrator returns 503
        print(f"[ENTITLEMENTS] DB CONNECTION ERROR counting news for {user_id}: {e}")
        raise

    try:
        cur = conn.cursor()
        if period == 'day':
            date_filter = "AND ar.created_at::date = CURRENT_DATE"
        elif period == 'week':
            date_filter = "AND ar.created_at >= date_trunc('week', CURRENT_DATE)"
        else:  # month
            date_filter = "AND ar.created_at >= date_trunc('month', CURRENT_DATE)"
        
        # Count only: direct articles (no newsletter link) + newsletter debit rows.
        # Exclude newsletter-sourced articles (they're covered by the debit row).
        cur.execute(f"""
            SELECT COUNT(*) FROM article_requests ar
            WHERE ar.secret_id = %s
            {date_filter}
            AND NOT EXISTS (
                SELECT 1 FROM newsletters_article_link nal
                WHERE nal.article_requests_id = ar.article_id
            )
        """, (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"[ENTITLEMENTS] ERROR counting news for {user_id}: {e} — DENYING (fail-closed)")
        try:
            conn.close()
        except Exception:
            pass
        return 9999  # Last-resort backstop: deny on query error


def check_tour_quota(user_id, requested_stops=10):
    """
    Check if user can generate a tour. Returns structured dict.
    
    Dispatches by tier:
      - free: quota-count logic (unchanged from pre-Subscribed)
      - ppu: wallet balance check — zero balance → hard stop
      - unlimited: month-to-date our-cost vs cost stop ($25)
    
    Returns structured result the app can act on:
        allowed: bool
        reason: str ('ok', 'quota_exceeded', 'insufficient_balance', 'cost_stop_reached')
        remedy: str or None ('upgrade', 'topup', 'switch_to_ppu')
    
    Plus backward-compatible fields (clamped_stops, used, max, etc.)
    
    On internal error: DENY, not allow. Log at ERROR with a message distinguishing
    "you are out of credit" from "we could not check your credit".
    """
    plan = get_user_plan(user_id)
    plan_id = plan['plan_id']
    
    # For paid tiers, check subscription state and billing gate
    if plan_id in ('ppu', 'unlimited'):
        return _check_tour_quota_paid(user_id, requested_stops, plan)
    
    # Free tier: existing quota-count logic, unchanged
    return _check_tour_quota_free(user_id, requested_stops, plan)


def _check_tour_quota_free(user_id, requested_stops, plan):
    """Free tier: existing quota-count behaviour. Every current user is on free.
    Identical logic to pre-Subscribed — a regression here breaks everyone.
    """
    used_today = get_tours_used_today(user_id)
    
    if used_today >= plan['tours_per_day']:
        from datetime import timedelta
        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
        return {
            'allowed': False,
            'reason': 'quota_exceeded',
            'remedy': 'upgrade',
            'error': 'quota_exceeded',
            'limit': 'tours_per_day',
            'plan': plan['plan_id'],
            'used': used_today,
            'max': plan['tours_per_day'],
            'reset': tomorrow,
            'upgrade': True
        }
    
    # Clamp stops to plan maximum
    clamped_stops = min(requested_stops, plan['tour_max_poi'])
    
    return {
        'allowed': True,
        'reason': 'ok',
        'remedy': None,
        'clamped_stops': clamped_stops,
        'plan': plan['plan_id'],
        'used': used_today,
        'max': plan['tours_per_day'],
        'remaining': plan['tours_per_day'] - used_today - 1
    }


def _check_tour_quota_paid(user_id, requested_stops, plan):
    """Paid tier (ppu or unlimited): billing-based gate.
    The plans table has generous safety ceilings for paid tiers (tours_per_day=999),
    so we skip quota-count and go straight to the billing check.
    """
    # Verify active subscription exists — fail closed if not
    try:
        tier = _get_subscription_tier(user_id)
    except Exception as e:
        logger.error(f"[ENTITLEMENTS] Subscription check error for {user_id}: {e}")
        print(f"[ENTITLEMENTS] ERROR: Could not verify subscription for {user_id}: {e} — DENYING (fail-closed)")
        return {
            'allowed': False,
            'reason': 'entitlement_check_error',
            'remedy': None,
            'error': 'entitlement_check_error',
            'plan': plan['plan_id'],
            'message': (
                "We could not verify your subscription status. "
                "This is a temporary issue on our end — please try again in a moment."
            ),
        }
    
    if not tier:
        # User's plan says ppu/unlimited but no active subscription row.
        # This is a data inconsistency — fail closed.
        logger.error(
            f"[ENTITLEMENTS] Plan={plan['plan_id']} but no active subscription row for {user_id}"
        )
        print(
            f"[ENTITLEMENTS] ERROR: Plan/subscription mismatch for {user_id} "
            f"(plan={plan['plan_id']}, no active subscription) — DENYING"
        )
        return {
            'allowed': False,
            'reason': 'subscription_inactive',
            'remedy': 'resubscribe',
            'error': 'subscription_inactive',
            'plan': plan['plan_id'],
            'message': (
                "Your subscription is not active. "
                "Please restore your subscription in Settings to continue."
            ),
        }
    
    # Dispatch to tier-specific billing check
    try:
        if tier == 'ppu':
            result = _check_ppu_balance(user_id)
        elif tier == 'unlimited':
            result = _check_unlimited_cost_stop(user_id)
        else:
            # Unknown tier — fail closed
            logger.error(f"[ENTITLEMENTS] Unknown subscription tier '{tier}' for {user_id}")
            print(f"[ENTITLEMENTS] ERROR: Unknown tier '{tier}' for {user_id} — DENYING")
            return {
                'allowed': False,
                'reason': 'entitlement_check_error',
                'remedy': None,
                'error': 'unknown_tier',
                'plan': plan['plan_id'],
                'message': "Could not determine your subscription type. Please contact support.",
            }
    except Exception as e:
        # Billing check itself errored — DENY, not allow (fail closed)
        logger.error(f"[ENTITLEMENTS] Billing check error for {user_id} (tier={tier}): {e}")
        print(
            f"[ENTITLEMENTS] ERROR: Billing check failed for {user_id} (tier={tier}): {e} — "
            f"DENYING (fail-closed, this is NOT a credit issue)"
        )
        return {
            'allowed': False,
            'reason': 'entitlement_check_error',
            'remedy': None,
            'error': 'entitlement_check_error',
            'plan': plan['plan_id'],
            'message': (
                "We could not verify your account balance. "
                "This is a temporary issue on our end — please try again in a moment."
            ),
        }
    
    # If billing check passed, apply stop clamping and return
    if result['allowed']:
        clamped_stops = min(requested_stops, plan['tour_max_poi'])
        result['clamped_stops'] = clamped_stops
        # Paid tiers don't have meaningful used/max/remaining for quota
        # but include them for API compatibility
        result['used'] = 0
        result['max'] = plan['tours_per_day']
        result['remaining'] = plan['tours_per_day']
    
    return result


def check_news_quota(user_id):
    """
    Check if user can process a news article. Returns structured dict.
    
    Dispatches by tier:
      - free: quota-count logic (unchanged)
      - ppu: wallet balance check
      - unlimited: month-to-date cost stop
    """
    plan = get_user_plan(user_id)
    plan_id = plan['plan_id']
    
    # For paid tiers, check subscription state and billing gate
    if plan_id in ('ppu', 'unlimited'):
        return _check_news_quota_paid(user_id, plan)
    
    # Free tier: existing quota-count logic, unchanged
    return _check_news_quota_free(user_id, plan)


def _check_news_quota_free(user_id, plan):
    """Free tier news quota: unchanged from pre-Subscribed."""
    used = get_news_used_period(user_id, plan['news_period'])
    
    if used >= plan['news_per_period']:
        return {
            'allowed': False,
            'reason': 'quota_exceeded',
            'remedy': 'upgrade',
            'error': 'quota_exceeded',
            'limit': 'news_per_period',
            'plan': plan['plan_id'],
            'used': used,
            'max': plan['news_per_period'],
            'period': plan['news_period'],
            'news_max_minutes': plan['news_max_minutes'],
            'upgrade': True
        }
    
    return {
        'allowed': True,
        'reason': 'ok',
        'remedy': None,
        'plan': plan['plan_id'],
        'used': used,
        'max': plan['news_per_period'],
        'remaining': plan['news_per_period'] - used - 1,
        'news_max_minutes': plan['news_max_minutes']
    }


def _check_news_quota_paid(user_id, plan):
    """Paid tier news quota: same billing gate as tours.
    News and tours are both covered by the same subscription (per design).
    """
    # Verify active subscription
    try:
        tier = _get_subscription_tier(user_id)
    except Exception as e:
        logger.error(f"[ENTITLEMENTS] Subscription check error for {user_id}: {e}")
        print(f"[ENTITLEMENTS] ERROR: Could not verify subscription for {user_id}: {e} — DENYING (fail-closed)")
        return {
            'allowed': False,
            'reason': 'entitlement_check_error',
            'remedy': None,
            'error': 'entitlement_check_error',
            'plan': plan['plan_id'],
            'news_max_minutes': plan['news_max_minutes'],
            'message': (
                "We could not verify your subscription status. "
                "This is a temporary issue on our end — please try again in a moment."
            ),
        }
    
    if not tier:
        logger.error(
            f"[ENTITLEMENTS] Plan={plan['plan_id']} but no active subscription row for {user_id}"
        )
        print(
            f"[ENTITLEMENTS] ERROR: Plan/subscription mismatch for {user_id} "
            f"(plan={plan['plan_id']}, no active subscription) — DENYING"
        )
        return {
            'allowed': False,
            'reason': 'subscription_inactive',
            'remedy': 'resubscribe',
            'error': 'subscription_inactive',
            'plan': plan['plan_id'],
            'news_max_minutes': plan['news_max_minutes'],
            'message': (
                "Your subscription is not active. "
                "Please restore your subscription in Settings to continue."
            ),
        }
    
    # Dispatch to tier-specific billing check
    try:
        if tier == 'ppu':
            result = _check_ppu_balance(user_id)
        elif tier == 'unlimited':
            result = _check_unlimited_cost_stop(user_id)
        else:
            logger.error(f"[ENTITLEMENTS] Unknown subscription tier '{tier}' for {user_id}")
            print(f"[ENTITLEMENTS] ERROR: Unknown tier '{tier}' for {user_id} — DENYING")
            return {
                'allowed': False,
                'reason': 'entitlement_check_error',
                'remedy': None,
                'error': 'unknown_tier',
                'plan': plan['plan_id'],
                'news_max_minutes': plan['news_max_minutes'],
                'message': "Could not determine your subscription type. Please contact support.",
            }
    except Exception as e:
        logger.error(f"[ENTITLEMENTS] Billing check error for {user_id} (tier={tier}): {e}")
        print(
            f"[ENTITLEMENTS] ERROR: Billing check failed for {user_id} (tier={tier}): {e} — "
            f"DENYING (fail-closed, this is NOT a credit issue)"
        )
        return {
            'allowed': False,
            'reason': 'entitlement_check_error',
            'remedy': None,
            'error': 'entitlement_check_error',
            'plan': plan['plan_id'],
            'news_max_minutes': plan['news_max_minutes'],
            'message': (
                "We could not verify your account balance. "
                "This is a temporary issue on our end — please try again in a moment."
            ),
        }
    
    # Include news_max_minutes for compatibility
    if result['allowed']:
        result['news_max_minutes'] = plan['news_max_minutes']
        result['used'] = 0
        result['max'] = plan['news_per_period']
        result['remaining'] = plan['news_per_period']
    else:
        result['news_max_minutes'] = plan['news_max_minutes']
    
    return result


# ---------------------------------------------------------------------------
# News narration length enforcement
# ---------------------------------------------------------------------------
NEWS_WORDS_PER_MINUTE = int(os.getenv('NEWS_WPM', '150'))  # Polly ~150 wpm; tune via env, no redeploy


def words_budget_for_minutes(max_minutes):
    """Convert max_minutes entitlement to a word budget for narration text.
    Returns None if no cap (max_minutes is 0 or None)."""
    if not max_minutes or max_minutes <= 0:
        return None
    return int(max_minutes * NEWS_WORDS_PER_MINUTE)


def truncate_to_word_budget(text, word_budget):
    """Truncate text to word_budget words, cutting at the last sentence boundary.
    Returns (text, was_truncated). If under budget, returns unchanged."""
    if not word_budget or not text:
        return text, False
    words = text.split()
    if len(words) <= word_budget:
        return text, False
    clipped = ' '.join(words[:word_budget])
    # Cut at last sentence-ending punctuation for cleaner output
    cut = max(clipped.rfind('.'), clipped.rfind('!'), clipped.rfind('?'))
    if cut > 0:
        clipped = clipped[:cut + 1]
    return clipped, True
