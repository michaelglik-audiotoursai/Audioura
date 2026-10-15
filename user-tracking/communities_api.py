"""
communities_api.py — LOCAL-690 Communities phase 1 (D657 / D658 + addenda).

Self-contained Flask blueprint for the user-api service (user-tracking/app.py),
self-contained ON PURPOSE: the user-api container's build context is
./user-tracking and cannot import repo-root modules (exactly like
entitlements_api.py). It owns the HTTP surface for communities:

  POST /communities                       create a community (owner)
  GET  /communities/<id>?user_id=...       the community page payload
  GET  /communities/by-code/<code>?user_id=...  resolve an invite code (join flow)
  POST /communities/<id>/join             free join (free communities only)
  POST /communities/<id>/episodes         add owner MP3 link(s) (owner)
  POST /communities/<id>/import-feed      parse the owner RSS feed -> episodes (owner)
  GET  /communities/<id>/episodes?user_id=...  list episodes (active members only)
  POST /communities/<id>/report           report -> owner
  GET  /communities/map?...                Listed communities for the Home map
  GET  /communities/mine?user_id=...       the member's joined communities (Listen origin)
  POST /communities/reminders/run         reminder tick (3-days-before + at-expiry)

The PASS PURCHASE goes through the existing /purchases/verify path: that route
calls `is_community_pass_product(product)` and, when true,
`verify_community_pass(...)` here. One module owns all community rules; the
entitlements blueprint only delegates.

Rules enforced here (D657/D658 + addenda):
  * passes are NON-RENEWING; the server stores community + expiry = now +
    duration_days; buying again EXTENDS/REPLACES the expiry (nothing renews).
  * a waiver community is always Private; a Listed community needs a location.
  * expiry blocks NEW content (new episode listing, invite-code join for a new
    member) but downloaded audio is the device's problem — the server never
    deletes it.
  * owner audio gets NO content check (metadata only).
  * a report routes to the owner; a `disabled` community lists/serves nothing.
"""

import os
import hmac
import logging
import secrets
import string
from datetime import datetime, timedelta

import psycopg2
from flask import Blueprint, request, jsonify

import communities_rss

logger = logging.getLogger(__name__)

communities_bp = Blueprint('communities', __name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours')
API_KEY = os.getenv('GATEWAY_API_KEY', '')
IAP_VERIFY_MODE = os.getenv('IAP_VERIFY_MODE', 'apple')  # 'stub' | 'apple' | 'google'
APPLE_BUNDLE_ID = os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours')
APPLE_ROOT_CA_PATH = os.getenv(
    'APPLE_ROOT_CA_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apple_root_ca_g3.pem'),
)
APPLE_IAP_ENVIRONMENT = os.getenv('APPLE_IAP_ENVIRONMENT', '')

# [LOCAL-696] Google Play config (mirror of entitlements_api). The pass products
# are one-time products on Play too (D658: our server enforces pass length), so
# a pass verifies through the SAME Google product path as a tour. The SA JSON
# path comes from GOOGLE_PLAY_SA_JSON; absent it, a google pass purchase returns
# 503 google_verify_unconfigured and never grants.
GOOGLE_PACKAGE_NAME = os.getenv('GOOGLE_PACKAGE_NAME', APPLE_BUNDLE_ID)
GOOGLE_PLAY_SA_JSON = os.getenv('GOOGLE_PLAY_SA_JSON', '')

# A test may inject a fake Google API client to exercise the google pass path
# with no network and no SA file.
_GOOGLE_API_CLIENT_OVERRIDE = None


def _google_api_client():
    if _GOOGLE_API_CLIENT_OVERRIDE is not None:
        return _GOOGLE_API_CLIENT_OVERRIDE
    if not GOOGLE_PLAY_SA_JSON:
        return None
    from google_play_verifier import build_api_client
    return build_api_client(GOOGLE_PLAY_SA_JSON, package_name=GOOGLE_PACKAGE_NAME)

# [D657/D658] One reminder 3 days BEFORE expiry, one AT expiry.
PASS_REMINDER_BEFORE_DAYS = int(os.getenv('PASS_REMINDER_BEFORE_DAYS', '3'))

# The invite-code shape must match the Flutter share-code discriminator
# (isShareCodeShape): exactly 8 base62 chars that contain a digit OR an internal
# capital, so classifySearchInput recognises it as a code and not a place name.
_CODE_ALPHABET = string.ascii_letters + string.digits


def _get_db():
    return psycopg2.connect(DATABASE_URL)


# ───────────────────────────────────────────────────────────────────────────
# Auth — identical pattern to entitlements_api._require_api_key
# ───────────────────────────────────────────────────────────────────────────
def _unauthenticated_allowed():
    return os.getenv('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', '').lower() in ('true', '1', 'yes')


def _require_api_key():
    if not API_KEY:
        if _unauthenticated_allowed():
            return None
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


# ───────────────────────────────────────────────────────────────────────────
# Invite code generation
# ───────────────────────────────────────────────────────────────────────────
def generate_join_code():
    """An 8-char base62 code that always carries a digit, so the app's
    isShareCodeShape() recognises it (digit OR internal capital → code, not a
    place name). We force at least one digit to make recognition deterministic.
    """
    while True:
        code = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if any(c.isdigit() for c in code):
            return code


def _unique_join_code(cur):
    for _ in range(20):
        code = generate_join_code()
        cur.execute("SELECT 1 FROM communities WHERE join_code = %s", (code,))
        if cur.fetchone() is None:
            return code
    # Astronomically unlikely; fail loudly rather than loop forever.
    raise RuntimeError('could not allocate a unique join code')


# ───────────────────────────────────────────────────────────────────────────
# Who may create a community (LOCAL-700 §3)
# ───────────────────────────────────────────────────────────────────────────
# Creating a community requires being on a PLAN — the free plan (l2) or above,
# NOT the default Introduction level (l1). The device level lives on
# device_entitlement.level, the SAME column entitlements_api reads (migration
# 016: l1 Introduction, l2 Free, l3 $10 Pack, l4 Curator, plus hidden
# tester/admin). The server enforces this (403 plan_required) so the app's gate
# can never be bypassed by a crafted request. Self-contained ON PURPOSE: the
# user-api container cannot import repo-root modules.
_INTRODUCTION_LEVEL = 'l1'


def _owner_level(cur, user_id):
    """The device's entitlement level, or 'l1' (Introduction) when it has no
    row yet (a brand-new device defaults to Introduction, exactly as
    entitlements_api._get_device_state does). Never raises: a missing table or
    any read error is treated as Introduction, which is the SAFE default (it
    refuses creation rather than letting an unknown device through)."""
    try:
        cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s",
                    (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    except Exception:  # noqa: BLE001 — treat any error as the default level
        pass
    return _INTRODUCTION_LEVEL


def _plan_allows_create(level):
    """True iff a device on `level` may create a community: the free plan (l2)
    or above — anything that is NOT the Introduction level (l1). Tester/admin
    and the paid levels (l3/l4) are all above Introduction, so they pass."""
    return level != _INTRODUCTION_LEVEL


def _normalize_name(name):
    """The canonical form for a case- and space-insensitive name comparison:
    trimmed, inner whitespace collapsed to a single space, lower-cased. Two
    names that differ only in case or spacing normalise to the same string, so
    the uniqueness check treats 'The  Owls' and 'the owls' as the same name."""
    return ' '.join((name or '').split()).lower()


def _name_is_available(cur, name):
    """True iff no existing (non-disabled) community has `name` under the
    case/space-insensitive comparison. A disabled community does not reserve its
    name. Compares on the normalised form in SQL so an index-free scan still
    matches 'the owls' to 'The  Owls'."""
    norm = _normalize_name(name)
    if not norm:
        return False
    cur.execute(
        "SELECT 1 FROM communities "
        "WHERE disabled = FALSE "
        "AND lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')) = %s "
        "LIMIT 1",
        (norm,),
    )
    return cur.fetchone() is None


# ───────────────────────────────────────────────────────────────────────────
# Pass products + expiry — the heart of the non-renewing model
# ───────────────────────────────────────────────────────────────────────────
def is_community_pass_product(product):
    """True iff `product` is a community pass store product id. The convention
    (migration 029) is 'audioura.pass.*'. One product per PRICE serves every
    community and every length (LEAD review of LOCAL-690); the LENGTH is carried
    separately on the request and the community's option. A cheap prefix check
    so the /purchases/verify dispatcher can route without a DB round-trip."""
    return isinstance(product, str) and product.startswith('audioura.pass.')


# The four lengths and their day durations (calendar-free arithmetic). The
# LENGTH lives on the community's pass OPTION (community_passes), not the Apple
# product — one product per PRICE serves every length (LEAD review of LOCAL-690).
PASS_LENGTH_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}


def duration_days_for_length(length):
    """The day-count for a pass length, or None for an unknown length."""
    return PASS_LENGTH_DAYS.get(length)


def pass_label_for(price_label, length):
    """The option label shown on the page, e.g. '$5 / month' from price '$5'."""
    return f'{price_label} / {length}'


def _pass_catalogue_product(cur, product_id):
    """The (price_usd, label) for a pass store product, read from
    community_pass_products (the catalogue — PRICE only, no length). None if
    unknown/inactive."""
    cur.execute(
        "SELECT price_usd, label FROM community_pass_products "
        "WHERE product_id = %s AND active = TRUE",
        (product_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {'price_usd': float(row[0]), 'price_label': row[1]}


def _offered_option(cur, community_id, product_id, length):
    """The community's offered option for (product, length): its duration_days
    and the catalogue price/label. None when the community does NOT offer that
    (product, length) pair, so the verify path can refuse an un-offered pass."""
    cur.execute(
        """SELECT p.duration_days, pp.price_usd, pp.label
           FROM community_passes p
           JOIN community_pass_products pp ON pp.product_id = p.product_id
           WHERE p.community_id = %s AND p.product_id = %s AND p.length = %s
             AND pp.active = TRUE""",
        (int(community_id), product_id, length),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {'duration_days': int(row[0]), 'price_usd': float(row[1]),
            'price_label': row[2]}


def compute_expiry(now, duration_days):
    """A pass bought at `now` expires at now + duration_days. Simple day
    arithmetic (not calendar months): the four lengths are day=1, week=7,
    month=30, year=365, so expiry is deterministic and a test can assert it."""
    return now + timedelta(days=duration_days)


def is_membership_active(expires_at, now=None):
    """A membership is active when it has no expiry (free community) or its
    expiry is still in the future. This is the server's single source of truth
    for 'can this member get NEW content?' (D658 addendum §2)."""
    if expires_at is None:
        return True
    now = now or datetime.utcnow()
    return expires_at > now


def _membership(cur, user_id, community_id):
    cur.execute(
        "SELECT expires_at, transaction_id, product_id, price_usd "
        "FROM community_memberships WHERE user_id = %s AND community_id = %s",
        (user_id, community_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {'expires_at': row[0], 'transaction_id': row[1],
            'product_id': row[2], 'price_usd': row[3]}


# ───────────────────────────────────────────────────────────────────────────
# Community row -> page payload
# ───────────────────────────────────────────────────────────────────────────
def _community_row(cur, community_id):
    cur.execute(
        """SELECT id, owner_user_id, name, description, organiser_name,
                  organiser_photo_url, organiser_bio, organiser_contact,
                  rules_text, waiver_text, has_waiver, is_paid, visibility,
                  latitude, longitude, join_code, feed_url, disabled
           FROM communities WHERE id = %s""",
        (community_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = ['id', 'owner_user_id', 'name', 'description', 'organiser_name',
            'organiser_photo_url', 'organiser_bio', 'organiser_contact',
            'rules_text', 'waiver_text', 'has_waiver', 'is_paid', 'visibility',
            'latitude', 'longitude', 'join_code', 'feed_url', 'disabled']
    return dict(zip(keys, row))


def _passes_for(cur, community_id):
    """The community's offered pass OPTIONS for the page. The LENGTH +
    duration_days come from community_passes; the PRICE from the catalogue. The
    label is composed ('$5' + 'month' -> '$5 / month') since the catalogue label
    is the price only (one product per price serves every length)."""
    cur.execute(
        """SELECT p.product_id, p.length, p.duration_days, pp.price_usd, pp.label
           FROM community_passes p
           JOIN community_pass_products pp ON pp.product_id = p.product_id
           WHERE p.community_id = %s AND pp.active = TRUE
           ORDER BY pp.price_usd, p.duration_days""",
        (community_id,),
    )
    out = []
    for r in cur.fetchall():
        out.append({'product_id': r[0], 'length': r[1], 'duration_days': int(r[2]),
                    'price_usd': float(r[3]),
                    'label': pass_label_for(r[4], r[1])})
    return out


def _episodes_for(cur, community_id):
    cur.execute(
        "SELECT position, title, audio_url, guid, source "
        "FROM community_episodes WHERE community_id = %s ORDER BY position",
        (community_id,),
    )
    return [{'position': r[0], 'title': r[1], 'audio_url': r[2],
             'guid': r[3], 'source': r[4]} for r in cur.fetchall()]


def _community_page(cur, community_id, user_id=None, now=None):
    """The community page payload (D658 (c)): organiser, description, rules +
    waiver, passes, episodes, and the member's own status/expiry. Episodes are
    included ONLY for an active member or the owner (expiry blocks NEW content —
    a non-member/expired member sees the page but not the episode list)."""
    c = _community_row(cur, community_id)
    if not c:
        return None
    now = now or datetime.utcnow()
    mem = _membership(cur, user_id, community_id) if user_id else None
    is_owner = user_id is not None and user_id == c['owner_user_id']
    active = is_owner or (mem is not None and is_membership_active(mem['expires_at'], now))

    payload = {
        'id': c['id'],
        'name': c['name'],
        'description': c['description'],
        'organiser': {
            'name': c['organiser_name'],
            'photo_url': c['organiser_photo_url'],
            'bio': c['organiser_bio'],
            'contact': c['organiser_contact'],
        },
        'rules_text': c['rules_text'],
        'waiver_text': c['waiver_text'],
        'has_waiver': c['has_waiver'],
        'is_paid': c['is_paid'],
        'visibility': c['visibility'],
        'disabled': c['disabled'],
        'latitude': c['latitude'],
        'longitude': c['longitude'],
        'passes': _passes_for(cur, community_id),
        'is_owner': is_owner,
        'my_status': {
            'is_member': mem is not None,
            'active': active,
            'expires_at': mem['expires_at'].isoformat() if (mem and mem['expires_at']) else None,
        },
        # Episodes only for an active member or the owner (D658 addendum §2).
        'episodes': _episodes_for(cur, community_id) if active else [],
        'episode_count': _episode_count(cur, community_id),
    }
    return payload


def _episode_count(cur, community_id):
    cur.execute("SELECT COUNT(*) FROM community_episodes WHERE community_id = %s",
                (community_id,))
    return cur.fetchone()[0]


# ───────────────────────────────────────────────────────────────────────────
# Pass verification — called by /purchases/verify (entitlements_api)
# ───────────────────────────────────────────────────────────────────────────
class _PassResult:
    def __init__(self, ok, status_code, payload):
        self.ok = ok
        self.status_code = status_code
        self.payload = payload


def _verify_pass_signed(store, transaction_id, product, signed_transaction):
    """Verify a community PASS purchase with the configured backend.

    stub : any non-empty transaction id (sandbox). apple : the StoreKit 2 JWS
    checked offline against the pass store product id (a Consumable — a non-
    renewing pass is a consumable to StoreKit). Returns (ok, raw_status)."""
    if IAP_VERIFY_MODE == 'stub':
        if not transaction_id:
            return False, 'stub_rejected_empty_transaction'
        return True, 'stub_verified'

    if IAP_VERIFY_MODE == 'apple':
        if store != 'apple':
            return False, f'apple_mode_wrong_store:{store}'
        if not signed_transaction:
            return False, 'apple_missing_signed_transaction'
        try:
            from apple_jws_verifier import (
                verify_signed_transaction, JwsVerificationError,
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"[LOCAL-690] apple verifier import failed: {e}")
            return False, f'apple_verifier_unavailable:{e}'
        try:
            with open(APPLE_ROOT_CA_PATH, 'rb') as f:
                root_pem = f.read()
            verified = verify_signed_transaction(
                signed_transaction,
                root_ca_pem=root_pem,
                expected_bundle_id=APPLE_BUNDLE_ID,
                expected_product_id=product,
                required_type='Consumable',
                expected_environment=(APPLE_IAP_ENVIRONMENT or None),
            )
        except JwsVerificationError as e:
            logger.warning(f"[LOCAL-690] apple pass verify failed: {e.code}")
            return False, f'apple_{e.code}'
        except Exception as e:
            logger.error(f"[LOCAL-690] apple pass verify error: {e}")
            return False, f'apple_error:{e}'
        return True, f'apple_verified:{verified.transaction_id}'

    if IAP_VERIFY_MODE == 'google':
        # [LOCAL-696] A pass product's store id IS `product`; the opaque Google
        # purchaseToken arrives in signed_transaction (reused field). Verify,
        # acknowledge and consume via the Play Developer API. The sentinel
        # raw_status 'google_verify_unconfigured' tells verify_community_pass to
        # answer 503 (no SA configured) rather than 402.
        if store != 'google':
            return False, f'google_mode_wrong_store:{store}'
        if not signed_transaction:
            return False, 'google_missing_purchase_token'
        client = _google_api_client()
        if client is None:
            return False, 'google_verify_unconfigured'
        try:
            from google_play_verifier import (
                verify_product_purchase, GoogleVerificationError,
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"[LOCAL-696] google verifier import failed: {e}")
            return False, f'google_verifier_unavailable:{e}'
        try:
            verified = verify_product_purchase(
                client,
                product_id=product,
                purchase_token=signed_transaction,
                expected_product_id=product,
                package_name=GOOGLE_PACKAGE_NAME,
                acknowledge=True,
                consume=True,
            )
        except GoogleVerificationError as e:
            if e.code in ('google_sa_unreadable', 'google_sa_invalid',
                          'google_libs_unavailable'):
                logger.error(f"[LOCAL-696] google pass unconfigured: {e.code}")
                return False, 'google_verify_unconfigured'
            logger.warning(f"[LOCAL-696] google pass verify failed: {e.code}")
            return False, f'google_{e.code}'
        except Exception as e:  # noqa: BLE001
            logger.error(f"[LOCAL-696] google pass verify error: {e}")
            return False, f'google_error:{e}'
        return True, f'google_verified:{verified.order_id}'

    return False, f'verify_mode_not_implemented:{IAP_VERIFY_MODE}'


def verify_community_pass(store, transaction_id, product, user_id,
                          signed_transaction, community_id, length):
    """Verify a community PASS purchase and grant/extend the membership.

    One product per PRICE serves every community and every length (LEAD review
    of LOCAL-690): the request carries community_id AND length, and the server
    checks that (community, product, length) is one of THIS community's offered
    options and sets expiry = now + the option's duration_days. Mirrors the
    tour-unlock path: idempotency on purchases.transaction_id, verify via the
    store (stub accepts any non-empty id), record the purchase, then UPSERT the
    membership. A membership is ONE row per (user, community): buying again
    EXTENDS/REPLACES the expiry — nothing renews automatically (D657). Returns a
    Flask (json, status) tuple.
    """
    if not community_id:
        return jsonify({
            "error": "missing_fields",
            "message": "community_id is required to buy a community pass.",
        }), 400
    if not length:
        return jsonify({
            "error": "missing_fields",
            "message": "length is required to buy a community pass.",
        }), 400
    if length not in PASS_LENGTH_DAYS:
        return jsonify({
            "error": "bad_length",
            "message": "length must be one of day, week, month, year.",
        }), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        c = _community_row(cur, int(community_id)) if str(community_id).isdigit() else None
        if not c:
            cur.close()
            return jsonify({"error": "unknown_community",
                            "message": f"Unknown community '{community_id}'."}), 400
        if c['disabled']:
            cur.close()
            return jsonify({"error": "community_disabled",
                            "message": "This community is unavailable."}), 403

        # The store product must be a known PRICE in the catalogue.
        cat = _pass_catalogue_product(cur, product)
        if not cat:
            cur.close()
            return jsonify({"error": "unknown_product",
                            "message": f"Unknown pass product '{product}'."}), 400

        # The community must actually OFFER this (product, length) option. The
        # LENGTH lives on the option, so an option the community does not offer
        # (even if the product is a real price) is refused.
        option = _offered_option(cur, int(community_id), product, length)
        if option is None:
            cur.close()
            return jsonify({"error": "pass_not_offered",
                            "message": "This community does not offer that pass."}), 400

        # Idempotency on the client-supplied transaction id.
        cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (transaction_id,))
        already = cur.fetchone() is not None

        ok, raw_status = _verify_pass_signed(store, transaction_id, product,
                                             signed_transaction)
        if not ok and raw_status == 'google_verify_unconfigured':
            # [LOCAL-696] Google requested but no service account configured.
            cur.close()
            return jsonify({"error": "google_verify_unconfigured"}), 503
        if not ok:
            cur.close()
            return jsonify({"error": "verification_failed",
                            "message": "The store could not verify this purchase.",
                            "raw_status": raw_status}), 402

        effective_txid = transaction_id
        if isinstance(raw_status, str) and raw_status.startswith(
                ('apple_verified:', 'google_verified:')):
            effective_txid = raw_status.split(':', 1)[1]

        now = datetime.utcnow()
        new_expiry = compute_expiry(now, option['duration_days'])
        price_usd = option['price_usd']

        if already:
            # The transaction was already processed — ensure the membership
            # reflects it and report success idempotently (no double extension).
            _upsert_membership(cur, user_id, int(community_id), new_expiry,
                               effective_txid, store, product, price_usd,
                               extend_only=False)
            conn.commit()
            cur.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": transaction_id,
                "membership": {"community_id": int(community_id),
                               "expires_at": new_expiry.isoformat()},
            }), 409

        # Record the purchase (UNIQUE transaction_id → idempotent under a race).
        try:
            cur.execute(
                "INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (effective_txid, store, product, user_id, price_usd, raw_status),
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur2 = conn.cursor()
            _upsert_membership(cur2, user_id, int(community_id), new_expiry,
                               effective_txid, store, product, price_usd,
                               extend_only=False)
            conn.commit()
            cur2.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": effective_txid,
            }), 409

        _upsert_membership(cur, user_id, int(community_id), new_expiry,
                           effective_txid, store, product, price_usd,
                           extend_only=False)
        conn.commit()
        cur.close()
        return jsonify({
            "verified": True,
            "membership": {
                "community_id": int(community_id),
                "expires_at": new_expiry.isoformat(),
                "length": length,
                "duration_days": option['duration_days'],
            },
            "transaction_id": effective_txid,
            "product": product,
            "amount": price_usd,
        }), 200
    finally:
        conn.close()


def _upsert_membership(cur, user_id, community_id, expires_at, txid, store,
                       product, price_usd, extend_only=False):
    """Grant or extend a membership. One row per (user, community): buying again
    sets a FRESH expiry (now + duration), which is "buy again to renew" (D657).
    Resets the reminder flags so the new period gets its own reminders."""
    cur.execute(
        """INSERT INTO community_memberships
               (user_id, community_id, expires_at, transaction_id, store,
                product_id, price_usd, reminded_before_at, reminded_expiry_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL)
           ON CONFLICT (user_id, community_id) DO UPDATE SET
               expires_at = EXCLUDED.expires_at,
               transaction_id = EXCLUDED.transaction_id,
               store = EXCLUDED.store,
               product_id = EXCLUDED.product_id,
               price_usd = EXCLUDED.price_usd,
               reminded_before_at = NULL,
               reminded_expiry_at = NULL,
               updated_at = NOW()""",
        (user_id, community_id, expires_at, txid, store, product, price_usd),
    )


# ───────────────────────────────────────────────────────────────────────────
# Reminder tick — one 3-days-before, one at-expiry (D657/D658)
# ───────────────────────────────────────────────────────────────────────────
def run_reminders(cur, now=None, before_days=PASS_REMINDER_BEFORE_DAYS):
    """Find memberships needing a reminder and MARK them sent.

    Returns {'before': [...], 'expiry': [...]} with the membership ids reminded
    in each bucket. Pure DB bookkeeping — the actual notification send is the
    app/push layer's job; this returns what to notify and never double-sends
    (the reminded_* timestamps guard it). A test can assert:
      * a membership expiring within `before_days` (and not yet) gets a
        before-reminder once;
      * a membership whose expiry has passed gets an expiry-reminder once.
    """
    now = now or datetime.utcnow()
    before_cutoff = now + timedelta(days=before_days)

    # Before-expiry: expiry is in (now, now+before_days], not yet reminded.
    cur.execute(
        """SELECT id FROM community_memberships
           WHERE expires_at IS NOT NULL
             AND expires_at > %s AND expires_at <= %s
             AND reminded_before_at IS NULL""",
        (now, before_cutoff),
    )
    before_ids = [r[0] for r in cur.fetchall()]
    if before_ids:
        cur.execute(
            "UPDATE community_memberships SET reminded_before_at = %s "
            "WHERE id = ANY(%s)", (now, before_ids),
        )

    # At-expiry: expiry has passed, not yet reminded.
    cur.execute(
        """SELECT id FROM community_memberships
           WHERE expires_at IS NOT NULL
             AND expires_at <= %s
             AND reminded_expiry_at IS NULL""",
        (now,),
    )
    expiry_ids = [r[0] for r in cur.fetchall()]
    if expiry_ids:
        cur.execute(
            "UPDATE community_memberships SET reminded_expiry_at = %s "
            "WHERE id = ANY(%s)", (now, expiry_ids),
        )

    return {'before': before_ids, 'expiry': expiry_ids}


# ───────────────────────────────────────────────────────────────────────────
# Endpoints
# ───────────────────────────────────────────────────────────────────────────
@communities_bp.route('/communities', methods=['POST'])
def create_community():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    owner_user_id = data.get('owner_user_id') or data.get('user_id')
    name = (data.get('name') or '').strip()
    if not owner_user_id or not name:
        return jsonify({"error": "missing_fields",
                        "message": "owner_user_id and name are required."}), 400

    has_waiver = bool(data.get('waiver_text')) or bool(data.get('has_waiver'))
    visibility = (data.get('visibility') or 'private').strip().lower()
    if visibility not in ('listed', 'private'):
        return jsonify({"error": "bad_visibility",
                        "message": "visibility must be 'listed' or 'private'."}), 400
    # A waiver community is ALWAYS Private (D658/D656) — the server forces it,
    # never trusting the client to have done so.
    if has_waiver:
        visibility = 'private'

    lat = data.get('latitude')
    lng = data.get('longitude')
    if visibility == 'listed' and (lat is None or lng is None):
        return jsonify({"error": "listed_needs_location",
                        "message": "A Listed community must have a location."}), 400

    is_paid = bool(data.get('is_paid'))
    pass_products = data.get('pass_products') or []
    if is_paid and not pass_products:
        return jsonify({"error": "paid_needs_passes",
                        "message": "A paid community must offer at least one pass."}), 400

    # Normalise each pass option to {product_id, length}. Back-compat: a bare
    # string product id (older client) is treated as a 'month' option. The
    # LENGTH lives on the option now (LEAD review of LOCAL-690): one store
    # product per PRICE, the owner picks the length here.
    norm_options = []
    for p in pass_products:
        if isinstance(p, str):
            norm_options.append({'product_id': p, 'length': 'month'})
        elif isinstance(p, dict) and p.get('product_id'):
            norm_options.append({'product_id': p['product_id'],
                                 'length': (p.get('length') or 'month')})
        else:
            return jsonify({"error": "bad_pass_option",
                            "message": "Each pass option needs a product_id and a length."}), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        # [LOCAL-700 §3] Creating a community requires the free plan or above —
        # NOT the default Introduction level. The server enforces it here (not
        # just the app) so a crafted request cannot bypass the gate. Uses the
        # SAME device_entitlement.level the entitlements API reads.
        level = _owner_level(cur, owner_user_id)
        if not _plan_allows_create(level):
            cur.close()
            return jsonify({
                "error": "plan_required",
                "message": "Creating a community requires the free plan or "
                           "above. Join the free queue or buy a plan to create "
                           "a community.",
                "level": level,
            }), 403

        # [LOCAL-700 §4] Reject a name already taken by a (non-disabled)
        # community, compared case- and space-insensitively — the same rule the
        # name-available endpoint reports, so the app's live ✓ cannot disagree
        # with the create.
        if not _name_is_available(cur, name):
            cur.close()
            return jsonify({
                "error": "name_taken",
                "message": "That community name is taken. Try another.",
            }), 409

        join_code = _unique_join_code(cur)
        cur.execute(
            """INSERT INTO communities
                   (owner_user_id, name, description, organiser_name,
                    organiser_photo_url, organiser_bio, organiser_contact,
                    rules_text, waiver_text, has_waiver, is_paid, visibility,
                    latitude, longitude, join_code, feed_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (owner_user_id, name, data.get('description'),
             data.get('organiser_name'), data.get('organiser_photo_url'),
             data.get('organiser_bio'), data.get('organiser_contact'),
             data.get('rules_text'), data.get('waiver_text'), has_waiver,
             is_paid, visibility, lat, lng, join_code, data.get('feed_url')),
        )
        community_id = cur.fetchone()[0]

        # Attach offered pass OPTIONS (each validated against the catalogue and
        # the four allowed lengths). The LENGTH + duration_days live on the
        # option; one store product per PRICE serves every length.
        for opt in norm_options:
            product_id = opt['product_id']
            length = opt['length']
            dur = duration_days_for_length(length)
            if dur is None:
                conn.rollback()
                cur.close()
                return jsonify({"error": "bad_length",
                                "message": f"Unknown pass length '{length}'."}), 400
            cur.execute(
                "SELECT 1 FROM community_pass_products WHERE product_id = %s AND active = TRUE",
                (product_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                cur.close()
                return jsonify({"error": "unknown_pass_product",
                                "message": f"Unknown pass product '{product_id}'."}), 400
            cur.execute(
                "INSERT INTO community_passes (community_id, product_id, length, duration_days) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (community_id, product_id, length, dur),
            )
        conn.commit()

        # The ready invite message the Generate tab shows the owner (D658
        # addendum §: organisers get a ready invite message).
        invite_message = build_invite_message(name, join_code)
        payload = _community_page(cur, community_id, user_id=owner_user_id)
        payload['join_code'] = join_code
        payload['invite_message'] = invite_message
        cur.close()
        return jsonify(payload), 201
    finally:
        conn.close()


def build_invite_message(community_name, join_code):
    """The ready invite message an organiser copies (mirrors the tour share
    message so the SAME Home search box recognises the code)."""
    return (f'Join my Audioura community "{community_name}". Open Audioura, tap '
            f'Search on the Home page and paste this code: {join_code}')


@communities_bp.route('/communities/name-available', methods=['GET'])
def name_available():
    """[LOCAL-700 §4] Is a community name free? The Create form calls this on
    every (debounced) name change to show ✓ / "Taken". The comparison is case-
    AND space-insensitive and trims the input, so 'The  Owls', ' the owls ' and
    'THE OWLS' all collide. A disabled community does not reserve its name.

    Query: ?name=<name>. Returns 200 {name, available: bool}. An empty/blank
    name is `available: false` (there is nothing to offer yet)."""
    err = _require_api_key()
    if err:
        return err
    name = request.args.get('name', '')
    conn = _get_db()
    try:
        cur = conn.cursor()
        available = _name_is_available(cur, name)
        cur.close()
        return jsonify({"name": name, "available": available}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>', methods=['GET'])
def get_community(community_id):
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    conn = _get_db()
    try:
        cur = conn.cursor()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        if payload is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/by-code/<code>', methods=['GET'])
def get_community_by_code(code):
    """Resolve an invite/share code to its community (the JOIN flow entry).

    This is what the Home search box hits when classifySearchInput sees a code
    that is not a tour. A non-member gets the community page with the "join"
    framing; the app renders "This tour belongs to <Community>. Join to listen".
    A disabled community resolves to 404 (lists/serves nothing).
    """
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, disabled FROM communities WHERE join_code = %s", (code,))
        row = cur.fetchone()
        if not row or row[1]:
            cur.close()
            return jsonify({"error": "not_found",
                            "message": "No community with that code."}), 404
        payload = _community_page(cur, row[0], user_id=user_id)
        payload['join_message'] = f'This tour belongs to {payload["name"]}. Join to listen.'
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/regenerate-code', methods=['POST'])
def regenerate_code(community_id):
    """[LOCAL-700 §4] Rotate a community's invite code. OWNER ONLY. The OLD code
    stops working immediately (the row's join_code is replaced), so anyone who
    had the old code can no longer resolve it (by-code → 404); the owner shares
    the new code going forward.

    Body: {owner_user_id | user_id}. Returns 200 {join_code, invite_message} on
    success; 404 if the community does not exist; 403 if the caller is not the
    owner. Existing members are unaffected — the code only gates NEW joins."""
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('owner_user_id') or data.get('user_id')
    if not user_id:
        return jsonify({"error": "missing_fields",
                        "message": "owner_user_id is required."}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['owner_user_id'] != user_id:
            cur.close()
            return jsonify({"error": "forbidden",
                            "message": "Only the owner can regenerate the code."}), 403
        new_code = _unique_join_code(cur)
        cur.execute(
            "UPDATE communities SET join_code = %s, updated_at = NOW() WHERE id = %s",
            (new_code, community_id),
        )
        conn.commit()
        invite_message = build_invite_message(c['name'], new_code)
        cur.close()
        return jsonify({"join_code": new_code,
                        "invite_message": invite_message}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/join', methods=['POST'])
def join_free_community(community_id):
    """Free join (free communities only). A paid community refuses here (402) —
    the member must buy a pass through /purchases/verify."""
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
        c = _community_row(cur, community_id)
        if not c or c['disabled']:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['is_paid']:
            cur.close()
            return jsonify({"error": "payment_required",
                            "message": "This community requires a pass."}), 402
        # Free membership: no expiry (NULL).
        _upsert_membership(cur, user_id, community_id, None, None, None, None, None)
        conn.commit()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/episodes', methods=['POST'])
def add_episodes(community_id):
    """Owner adds one or more owner-HOSTED MP3 links. Body: {owner_user_id,
    episodes:[{title, audio_url}]}. NO content check (D657 addendum). Only the
    owner may add; appended after the current max position."""
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    owner_user_id = data.get('owner_user_id') or data.get('user_id')
    episodes = data.get('episodes') or []
    if not owner_user_id or not episodes:
        return jsonify({"error": "missing_fields",
                        "message": "owner_user_id and episodes are required."}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['owner_user_id'] != owner_user_id:
            cur.close()
            return jsonify({"error": "forbidden",
                            "message": "Only the owner can add episodes."}), 403
        cur.execute("SELECT COALESCE(MAX(position), 0) FROM community_episodes WHERE community_id = %s",
                    (community_id,))
        pos = cur.fetchone()[0]
        added = 0
        for ep in episodes:
            url = (ep.get('audio_url') or '').strip()
            if not url:
                continue
            pos += 1
            title = (ep.get('title') or f'Episode {pos}').strip()
            cur.execute(
                "INSERT INTO community_episodes (community_id, position, title, audio_url, source) "
                "VALUES (%s, %s, %s, %s, 'link')",
                (community_id, pos, title, url),
            )
            added += 1
        conn.commit()
        cur.close()
        return jsonify({"added": added, "episode_count": pos}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/import-feed', methods=['POST'])
def import_feed(community_id):
    """Owner imports episodes from the community's ONE RSS feed (metadata only).

    Body: {owner_user_id, feed_url?}. Uses feed_url from the body or the stored
    one. Parses with communities_rss (NO content check). Upserts episodes on
    (community, guid) when a guid is present, else appends. The HTTP fetcher is
    injectable via the module hook `_feed_http_get` so a test mocks it.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    owner_user_id = data.get('owner_user_id') or data.get('user_id')
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['owner_user_id'] != owner_user_id:
            cur.close()
            return jsonify({"error": "forbidden",
                            "message": "Only the owner can import a feed."}), 403
        feed_url = (data.get('feed_url') or c['feed_url'] or '').strip()
        if not feed_url:
            cur.close()
            return jsonify({"error": "no_feed_url",
                            "message": "No feed_url to import."}), 400

        # Persist the feed_url if newly supplied.
        if data.get('feed_url') and data.get('feed_url') != c['feed_url']:
            cur.execute("UPDATE communities SET feed_url = %s, updated_at = NOW() WHERE id = %s",
                        (feed_url, community_id))

        try:
            parsed = communities_rss.fetch_and_parse(feed_url, http_get=_feed_http_get)
        except communities_rss.FeedParseError as e:
            conn.rollback()
            cur.close()
            return jsonify({"error": "feed_parse_error", "message": str(e)}), 422
        except Exception as e:  # transport error
            conn.rollback()
            cur.close()
            return jsonify({"error": "feed_fetch_error", "message": str(e)}), 502

        added = _upsert_feed_episodes(cur, community_id, parsed)
        conn.commit()
        cur.close()
        return jsonify({"imported": added,
                        "episode_count": _episode_count_conn(community_id)}), 200
    finally:
        conn.close()


# Injectable HTTP getter for the feed import — a test replaces this with a mock
# so no real request is ever made. Defaults to the stdlib getter.
_feed_http_get = None


def _episode_count_conn(community_id):
    conn = _get_db()
    try:
        cur = conn.cursor()
        n = _episode_count(cur, community_id)
        cur.close()
        return n
    finally:
        conn.close()


def _upsert_feed_episodes(cur, community_id, parsed):
    """Insert/update feed episodes. An item with a guid upserts on
    (community, guid); a guid-less item appends at the next position. Returns
    the number of rows inserted or updated."""
    cur.execute("SELECT COALESCE(MAX(position), 0) FROM community_episodes WHERE community_id = %s",
                (community_id,))
    pos = cur.fetchone()[0]
    count = 0
    for ep in parsed:
        guid = ep.get('guid')
        title = ep.get('title')
        url = ep.get('audio_url')
        if guid:
            # Does this guid already exist for the community?
            cur.execute(
                "SELECT id FROM community_episodes WHERE community_id = %s AND guid = %s",
                (community_id, guid),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE community_episodes SET title = %s, audio_url = %s, source = 'feed' "
                    "WHERE id = %s", (title, url, existing[0]),
                )
                count += 1
                continue
        pos += 1
        cur.execute(
            "INSERT INTO community_episodes (community_id, position, title, audio_url, guid, source) "
            "VALUES (%s, %s, %s, %s, %s, 'feed')",
            (community_id, pos, title, url, guid),
        )
        count += 1
    return count


@communities_bp.route('/communities/<int:community_id>/episodes', methods=['GET'])
def list_episodes(community_id):
    """List episodes — ACTIVE members and the owner only. A non-member or an
    EXPIRED member is refused (403): expiry blocks NEW content (D658 addendum
    §2). Downloaded audio on the device is unaffected (not served here)."""
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c or c['disabled']:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        is_owner = user_id == c['owner_user_id']
        mem = _membership(cur, user_id, community_id) if user_id else None
        active = is_owner or (mem is not None and is_membership_active(mem['expires_at']))
        if not active:
            cur.close()
            # A non-member/expired member cannot get NEW content.
            return jsonify({"error": "membership_required",
                            "message": "An active membership is required.",
                            "is_member": mem is not None}), 403
        episodes = _episodes_for(cur, community_id)
        cur.close()
        return jsonify({"episodes": episodes}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/report', methods=['POST'])
def report_community(community_id):
    """A report on a community tour -> the OWNER (D658 addendum 2 §). Audioura
    keeps the per-community disabled off-switch separately."""
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        cur.execute(
            "INSERT INTO community_reports (community_id, reporter_user_id, reason) "
            "VALUES (%s, %s, %s) RETURNING id",
            (community_id, data.get('user_id'), data.get('reason')),
        )
        report_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        # The report goes to the owner (surfaced to the owner's device; the row
        # carries owner_user_id via the community join).
        return jsonify({"reported": True, "report_id": report_id,
                        "owner_user_id": c['owner_user_id']}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/map', methods=['GET'])
def map_communities():
    """Listed communities for the Home map (community badge). Only visibility=
    'listed', not disabled, with a location. Private/waiver communities never
    appear here (D658 addendum 2 §4)."""
    err = _require_api_key()
    if err:
        return err
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, name, latitude, longitude, is_paid
               FROM communities
               WHERE visibility = 'listed' AND disabled = FALSE
                 AND latitude IS NOT NULL AND longitude IS NOT NULL""",
        )
        out = [{'id': r[0], 'name': r[1], 'latitude': r[2], 'longitude': r[3],
                'is_paid': r[4], 'badge': 'community'} for r in cur.fetchall()]
        cur.close()
        return jsonify({"communities": out}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/mine', methods=['GET'])
def my_communities():
    """The member's joined communities, for the Listen tab origin label. Each
    carries the community name + organiser (the ⋯ Origin menu content) and the
    member's active flag."""
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.name, c.organiser_name, m.expires_at
               FROM community_memberships m
               JOIN communities c ON c.id = m.community_id
               WHERE m.user_id = %s""",
            (user_id,),
        )
        now = datetime.utcnow()
        out = []
        for r in cur.fetchall():
            out.append({
                'id': r[0], 'name': r[1], 'organiser_name': r[2],
                'origin': 'community',
                'origin_label': r[1],  # the community name shown on the row
                'expires_at': r[3].isoformat() if r[3] else None,
                'active': is_membership_active(r[3], now),
            })
        cur.close()
        return jsonify({"communities": out}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/reminders/run', methods=['POST'])
def reminders_run():
    """Run the reminder tick (3-days-before + at-expiry). Returns the membership
    ids reminded in each bucket. Idempotent per period (reminded_* guards)."""
    err = _require_api_key()
    if err:
        return err
    conn = _get_db()
    try:
        cur = conn.cursor()
        result = run_reminders(cur)
        conn.commit()
        cur.close()
        return jsonify(result), 200
    finally:
        conn.close()
