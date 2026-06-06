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
    """Get the user's plan limits. Returns plan dict or free-tier defaults."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        # Try to get user's specific plan
        cur.execute("""
            SELECT p.plan_id, p.tours_per_day, p.tour_max_poi, p.tour_max_minutes,
                   p.news_per_period, p.news_period, p.news_max_minutes, p.downloads_unlimited
            FROM plans p
            LEFT JOIN users u ON u.plan = p.plan_id
            WHERE u.secret_id = %s OR u.device_id = %s
            LIMIT 1
        """, (user_id, user_id))
        row = cur.fetchone()
        
        if not row:
            # Default to free plan
            cur.execute("SELECT * FROM plans WHERE plan_id = 'free'")
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
        print(f"[ENTITLEMENTS] Error getting plan for {user_id}: {e}")
    
    # Fallback defaults if DB unavailable
    return {
        'plan_id': 'free',
        'tours_per_day': 1,
        'tour_max_poi': 30,
        'tour_max_minutes': 120,
        'news_per_period': 10,
        'news_period': 'day',
        'news_max_minutes': 10,
        'downloads_unlimited': True
    }


def get_tours_used_today(user_id):
    """Count tours generated today by this user."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM tour_requests 
            WHERE secret_id = %s AND started_at::date = CURRENT_DATE
        """, (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"[ENTITLEMENTS] Error counting tours for {user_id}: {e}")
        return 0


def get_news_used_period(user_id, period='day'):
    """Count news articles processed this period by this user."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        if period == 'day':
            cur.execute("""
                SELECT COUNT(*) FROM article_requests 
                WHERE (url IS NOT NULL OR article_text IS NOT NULL)
                AND created_at::date = CURRENT_DATE
            """)
        else:  # month
            cur.execute("""
                SELECT COUNT(*) FROM article_requests 
                WHERE (url IS NOT NULL OR article_text IS NOT NULL)
                AND created_at >= date_trunc('month', CURRENT_DATE)
            """)
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"[ENTITLEMENTS] Error counting news for {user_id}: {e}")
        return 0


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
        tomorrow = date.today().strftime('%Y-%m-%d') + 'T00:00:00Z'
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
            'upgrade': True
        }
    
    return {
        'allowed': True,
        'plan': plan['plan_id'],
        'used': used,
        'max': plan['news_per_period'],
        'remaining': plan['news_per_period'] - used - 1
    }
