"""
Audioura Entitlements — Data-driven usage limits.
===================================================

Limits live in the `plans` table (changeable via SQL, no redeploy).
Users have a `plan` field (default 'free').
Enforcement is server-side, keyed on user_id.

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
import psycopg2
from datetime import datetime, date


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
    Check if user can generate a tour. Returns dict with allowed/rejection info.
    
    Returns:
        {'allowed': True, 'clamped_stops': N} — proceed with (possibly clamped) stops
        {'allowed': False, 'error': 'quota_exceeded', ...} — reject with 429 info
    """
    plan = get_user_plan(user_id)
    used_today = get_tours_used_today(user_id)
    
    if used_today >= plan['tours_per_day']:
        from datetime import timedelta
        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
        return {
            'allowed': False,
            'error': 'quota_exceeded',
            'limit': 'tours_per_day',
            'plan': plan['plan_id'],
            'used': used_today,
            'max': plan['tours_per_day'],
            'reset': tomorrow,
            'upgrade': True
        }
    
    # Clamp stops to plan maximum
    # NOTE: tour_max_minutes is not enforced directly — the POI clamp serves as its proxy.
    # Tour duration is roughly proportional to stop count (2-5 min/stop), so clamping POI
    # to tour_max_poi effectively caps duration. Direct time enforcement would require
    # post-generation measurement + rejection, which wastes the compute cost.
    clamped_stops = min(requested_stops, plan['tour_max_poi'])
    
    return {
        'allowed': True,
        'clamped_stops': clamped_stops,
        'plan': plan['plan_id'],
        'used': used_today,
        'max': plan['tours_per_day'],
        'remaining': plan['tours_per_day'] - used_today - 1
    }


def check_news_quota(user_id):
    """
    Check if user can process a news article. Returns dict with allowed/rejection info.
    """
    plan = get_user_plan(user_id)
    used = get_news_used_period(user_id, plan['news_period'])
    
    if used >= plan['news_per_period']:
        return {
            'allowed': False,
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
        'plan': plan['plan_id'],
        'used': used,
        'max': plan['news_per_period'],
        'remaining': plan['news_per_period'] - used - 1,
        'news_max_minutes': plan['news_max_minutes']
    }


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
