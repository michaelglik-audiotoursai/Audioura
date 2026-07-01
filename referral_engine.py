"""
Referral Engine — code generation + redemption tracking.
=========================================================
Generates deterministic referral codes and tracks redemptions in Postgres.
"""
import hashlib
import logging
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)

# Base36 for short, readable codes
_BASE36 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def generate_referral_code(user_id: str) -> str:
    """Generate a deterministic 6-char referral code from user_id hash."""
    digest = hashlib.sha256(f"referral:{user_id}".encode()).digest()
    num = int.from_bytes(digest[:4], "big")
    chars = []
    for _ in range(6):
        chars.append(_BASE36[num % 36])
        num //= 36
    return "".join(chars)


def _ensure_tables(conn) -> None:
    """Create referral tables if not exist (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                code VARCHAR(6) PRIMARY KEY,
                referrer_user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                redemption_count INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_redemptions (
                id SERIAL PRIMARY KEY,
                referral_code VARCHAR(6) NOT NULL REFERENCES referral_codes(code),
                new_user_id TEXT NOT NULL,
                redeemed_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


def store_referral(code: str, referrer_user_id: str, db_url: str) -> bool:
    """Store (upsert) a referral code. Returns True on success."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO referral_codes (code, referrer_user_id)
                VALUES (%s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (code, referrer_user_id))
        conn.commit()
        conn.close()
        logger.info(f"Stored referral code {code} for user {referrer_user_id}")
        return True
    except Exception as e:
        logger.error(f"Error storing referral {code}: {e}")
        return False


def record_referral_redemption(code: str, new_user_id: str, db_url: str) -> bool:
    """Record a redemption: increment count + insert redemption row. Returns True on success."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_tables(conn)
        with conn.cursor() as cur:
            # Increment redemption count
            cur.execute(
                "UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s",
                (code,),
            )
            # Insert redemption record
            cur.execute(
                "INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)",
                (code, new_user_id),
            )
        conn.commit()
        conn.close()
        logger.info(f"Recorded redemption of {code} by {new_user_id}")
        return True
    except Exception as e:
        logger.error(f"Error recording redemption {code}: {e}")
        return False
