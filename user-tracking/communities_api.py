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
  POST /communities/<id>/step-down         owner steps down -> handover (D663 §1)
  POST /communities/<id>/offer-organiser   a member volunteers to take over
  POST /communities/<id>/withdraw-offer    a volunteer withdraws
  POST /communities/<id>/pick-organiser    owner picks a volunteer
  POST /communities/<id>/accept-organiser  picked member accepts -> becomes owner, reopens
  DELETE /communities/<id>                 owner deletes a MEMBER-LESS community (D663 §1 d)
  POST /communities/archive/run            daily archive tick (handover 30d -> archived)
  POST /communities/reminders/run         reminder tick (3-days-before + at-expiry)
  POST /communities/launch-window/run     launch-window tick (D664): archive a
                                          community that missed its first-two-
                                          members bar; remind the organiser at
                                          48 h / 12 h left. Daily AND hourly.

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
# Organiser step-down state machine (LOCAL-702, D663 §1)
# ───────────────────────────────────────────────────────────────────────────
# A community's `status` is the state machine:
#   active   — normal; new members may join and buy passes.
#   handover — the owner stepped down (D663 §1 (a)): stays readable/playable for
#              existing members, REFUSES new joins/pass sales (409
#              community_closed_to_new_members), shows "Looking for a new
#              organiser". A member volunteers; the owner picks; the member
#              accepts → becomes owner, the community reopens (→ active).
#   archived — no new organiser within ARCHIVE_AFTER_DAYS of stepping down
#              (D663 §1 (c)): members keep downloads, nothing new. Terminal.
STATUS_ACTIVE = 'active'
STATUS_HANDOVER = 'handover'
STATUS_ARCHIVED = 'archived'

# D663 §1 (c): no new organiser within 30 days → archived. The daily job on the
# tick flips handover→archived at this age. Overridable for tests.
ARCHIVE_AFTER_DAYS = int(os.getenv('COMMUNITY_ARCHIVE_AFTER_DAYS', '30'))

# [LOCAL-703 / D664] The launch window. A new community must win its first two
# QUALIFYING members (excluding the owner) within this many hours of creation or
# the launch-window job archives it. 168 h = 7 days, configurable.
COMMUNITY_LAUNCH_HOURS = int(os.getenv('COMMUNITY_LAUNCH_HOURS', '168'))

# [LOCAL-703 / D664] The bar: two members (the organiser does not count).
COMMUNITY_LAUNCH_MEMBERS_NEEDED = int(os.getenv('COMMUNITY_LAUNCH_MEMBERS_NEEDED', '2'))

# [LOCAL-703 / D664] Why a community was archived — distinguishes the launch
# window miss from the LOCAL-702 30-day hand-over expiry.
ARCHIVED_REASON_LAUNCH_MISSED = 'launch_window_missed'
ARCHIVED_REASON_HANDOVER_EXPIRED = 'handover_expired'

# [LOCAL-704 / D666] After launch, a community that stays at 0 active members
# for this many consecutive days is archived (reason 'no_members'). Between 1
# and 2 members it keeps running (with weekly warnings); only a full week at 0
# dissolves it.
ARCHIVED_REASON_NO_MEMBERS = 'no_members'
COMMUNITY_ZERO_MEMBERS_ARCHIVE_DAYS = int(
    os.getenv('COMMUNITY_ZERO_MEMBERS_ARCHIVE_DAYS', '7'))

# [LOCAL-704 / D666] The launch bar — and the post-launch keep-alive bar — is 2
# active members. Below it, the organiser and remaining members are warned the
# day the count drops, then every this-many days while it stays below.
COMMUNITY_MIN_ACTIVE_MEMBERS = int(os.getenv('COMMUNITY_MIN_ACTIVE_MEMBERS', '2'))
LOW_MEMBERS_WARNING_EVERY_DAYS = int(
    os.getenv('COMMUNITY_LOW_MEMBERS_WARNING_EVERY_DAYS', '7'))

# [LOCAL-703 / D664] Organiser reminders at 48 h and 12 h left (once each). The
# launch-window job stamps the matching column so a reminder never double-sends.
LAUNCH_REMINDER_HOURS = (48, 12)

# The terms a NEW organiser must accept when taking over (LOCAL-691
# document_acceptance). Recorded server-side on accept so the hand-over leaves
# the same audit trail as creating a community.
ORGANISER_TERMS_DOCUMENT = 'organiser_terms'
ORGANISER_TERMS_VERSION = os.getenv('ORGANISER_TERMS_VERSION', '2026-10-14-draft1')


def _accepts_new_members(status):
    """True iff a community in `status` accepts NEW members (free joins and pass
    sales). Only an 'active' community does; a 'handover' or 'archived' community
    is closed to new members (D663 §1 (a)/(c)). An unknown/NULL status is
    treated as active (the pre-LOCAL-702 default)."""
    return status in (None, '', STATUS_ACTIVE)


def _record_organiser_terms_acceptance(cur, user_id):
    """Record the incoming organiser's terms acceptance (LOCAL-691). Idempotent
    (ON CONFLICT DO NOTHING). Best-effort: a missing document_acceptance table
    must not break the hand-over, so any error is swallowed — the ownership
    transfer is the binding act, the acceptance is its audit trail."""
    try:
        cur.execute(
            """INSERT INTO document_acceptance (user_id, document, version)
               VALUES (%s, %s, %s)
               ON CONFLICT (user_id, document, version) DO NOTHING""",
            (user_id, ORGANISER_TERMS_DOCUMENT, ORGANISER_TERMS_VERSION),
        )
    except Exception:  # noqa: BLE001 — acceptance is an audit trail, not a gate
        logger.warning("[LOCAL-702] could not record organiser terms acceptance")


def _community_member_count(cur, community_id):
    """How many members a community has (D658: a community WITHOUT members can
    still be deleted by its owner; once members exist, it cannot be closed)."""
    cur.execute(
        "SELECT COUNT(*) FROM community_memberships WHERE community_id = %s",
        (community_id,),
    )
    return cur.fetchone()[0]


def archive_stale_handovers(cur, now=None, after_days=ARCHIVE_AFTER_DAYS):
    """The daily archive job (D663 §1 (c)). Flip every community that has been
    in 'handover' for ≥ after_days (measured from stepped_down_at) to
    'archived', stamping archived_at. Returns the list of community ids archived
    this run. Idempotent: a community already archived is not touched (the WHERE
    only matches status='handover'); running twice archives nothing new.

    LEAD wires the daily tick to call this (see SUBMISSION) — the same pattern
    as the reminder tick: a tiny endpoint the external scheduler hits daily."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=after_days)
    cur.execute(
        """UPDATE communities
              SET status = %s, archived_at = %s, archived_reason = %s,
                  updated_at = NOW()
            WHERE status = %s
              AND stepped_down_at IS NOT NULL
              AND stepped_down_at <= %s
            RETURNING id""",
        (STATUS_ARCHIVED, now, ARCHIVED_REASON_HANDOVER_EXPIRED,
         STATUS_HANDOVER, cutoff),
    )
    return [r[0] for r in cur.fetchall()]


# ───────────────────────────────────────────────────────────────────────────
# Launch window (LOCAL-703, D664)
# ───────────────────────────────────────────────────────────────────────────
# A new community must win its first COMMUNITY_LAUNCH_MEMBERS_NEEDED (2)
# QUALIFYING members, EXCLUDING the owner, within COMMUNITY_LAUNCH_HOURS (168 h)
# of creation. Paid communities count members holding a verified paid pass
# (community_memberships.transaction_id IS NOT NULL); free communities count
# joined members. Launch is checked on every join / pass verification: once the
# bar is met, launched_at is stamped ONCE and never reverted, and the countdown
# is gone for good. Miss the bar → the launch-window job archives the community
# (archived_reason = 'launch_window_missed'); its invite code then resolves to
# 410 community_closed and nothing new is served or sold (members keep their
# downloads, D658).


def _qualifying_member_count(cur, community_id, is_paid=True):
    """How many QUALIFYING members a community has toward launch, EXCLUDING the
    owner (D664/D665). Every community is paid now (D665: no free communities),
    so a qualifying member is one holding a verified PAID pass —
    community_memberships.transaction_id IS NOT NULL. A grandfathered free
    member of a converted community (transaction_id NULL) never counts: a
    committed paid member is the bar. The owner is excluded by joining against
    the community's owner_user_id.

    `is_paid` is accepted for backward compatibility with existing callers but
    is ignored — the launch bar is always 2 PAYING members (D664 as amended by
    D665; the free-community branch was removed in LOCAL-704)."""
    cur.execute(
        """SELECT COUNT(*)
             FROM community_memberships m
             JOIN communities c ON c.id = m.community_id
            WHERE m.community_id = %s
              AND m.transaction_id IS NOT NULL
              AND m.user_id <> c.owner_user_id""",
        (community_id,),
    )
    return cur.fetchone()[0]


def _active_member_count(cur, community_id, now=None):
    """[LOCAL-704 / D666] How many ACTIVE members a community has, EXCLUDING the
    owner — the number shown as `member_count` and the one the post-launch
    low-members rule watches. An active member holds a verified paid pass
    (transaction_id IS NOT NULL) that has NOT expired (expires_at IS NULL — a
    perpetual membership — or expires_at > now). The owner is never a member
    (D665 addendum), so they are excluded via owner_user_id. A grandfathered
    free member (transaction_id NULL) is not counted — only paid, unexpired
    members are 'active' for the member count and the keep-alive bar."""
    now = now or datetime.utcnow()
    cur.execute(
        """SELECT COUNT(*)
             FROM community_memberships m
             JOIN communities c ON c.id = m.community_id
            WHERE m.community_id = %s
              AND m.transaction_id IS NOT NULL
              AND m.user_id <> c.owner_user_id
              AND (m.expires_at IS NULL OR m.expires_at > %s)""",
        (community_id, now),
    )
    return cur.fetchone()[0]


def _check_and_maybe_launch(cur, community_id, now=None):
    """Launch the community if it now meets the bar. Called on every join / pass
    verification. Idempotent and one-way: if launched_at is already set it is a
    no-op (never reverted); otherwise, when the qualifying-member count reaches
    COMMUNITY_LAUNCH_MEMBERS_NEEDED, stamp launched_at = now. Returns True iff
    the community is (now or already) launched.

    Launching stamps ONLY launched_at — status stays whatever it is (an active
    community simply stops being a launch-window candidate; the partial index
    and the job both key off launched_at IS NULL)."""
    now = now or datetime.utcnow()
    c = _community_row(cur, community_id)
    if not c:
        return False
    if c['launched_at'] is not None:
        return True
    count = _qualifying_member_count(cur, community_id, c['is_paid'])
    if count >= COMMUNITY_LAUNCH_MEMBERS_NEEDED:
        cur.execute(
            "UPDATE communities SET launched_at = %s, updated_at = NOW() "
            "WHERE id = %s AND launched_at IS NULL",
            (now, community_id),
        )
        return True
    return False


def _launch_info(c, cur=None, now=None):
    """The `launch` payload block for the community page (D664): the deadline,
    hours left, the bar, how many qualifying members so far, and whether the
    community has launched. `c` is a _community_row dict; `cur` is used to count
    members (omit to report members_so_far=0, e.g. a cheap caller).

    hours_left is max(0, ceil((deadline - now)/1h)) so the organiser's countdown
    never goes negative and the LAST partial hour still reads as 1 (the hourly
    cadence matters for the final hours — D664)."""
    now = now or _utcnow_aware()
    launched = c['launched_at'] is not None
    deadline = c['launch_deadline']
    members_so_far = 0
    if cur is not None:
        members_so_far = _qualifying_member_count(cur, c['id'], c['is_paid'])
    hours_left = 0
    if deadline is not None:
        delta = deadline - _as_aware(now)
        secs = delta.total_seconds()
        if secs > 0:
            # ceil to whole hours so a partial final hour still shows as 1.
            hours_left = int((secs + 3599) // 3600)
    return {
        'deadline': deadline.isoformat() if deadline else None,
        'hours_left': hours_left,
        'members_needed': COMMUNITY_LAUNCH_MEMBERS_NEEDED,
        'members_so_far': members_so_far,
        'launched': launched,
        'launched_at': c['launched_at'].isoformat() if c['launched_at'] else None,
    }


def _utcnow_aware():
    """A timezone-aware UTC now. launch_deadline is TIMESTAMPTZ, so psycopg2
    returns an aware datetime; comparisons must be aware too."""
    from datetime import timezone
    return datetime.now(timezone.utc)


def _as_aware(dt):
    """Coerce a datetime to timezone-aware UTC (naive is assumed UTC) so a
    deadline (aware, from TIMESTAMPTZ) and a test-injected naive `now` compare
    cleanly."""
    from datetime import timezone
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def run_launch_window(cur, now=None):
    """[LOCAL-703 / D664] The launch-window job (daily AND hourly — the hourly
    cadence keeps the organiser's final-hours countdown accurate). Two jobs in
    one pass, both idempotent:

      1. ARCHIVE: every ACTIVE, un-launched community whose launch_deadline has
         passed → status 'archived', archived_at, archived_reason
         'launch_window_missed'. A LAUNCHED community (launched_at set) is never
         touched; a community already archived/handover is not active and so is
         skipped. Running twice archives nothing new.
      2. REMIND: an ACTIVE, un-launched community with <= 48 h / <= 12 h left
         (and not past the deadline) gets the organiser reminder once each; the
         matching column is stamped so it never double-sends.

    Returns {'archived': [ids], 'reminded_48h': [ids], 'reminded_12h': [ids]}.
    The reminder buckets are the community ids to notify; the actual push is the
    app/notification layer's job (same split as run_reminders)."""
    now = now or _utcnow_aware()
    now = _as_aware(now)

    # ─── 1. Archive past-deadline, un-launched, still-active communities ──────
    cur.execute(
        """UPDATE communities
              SET status = %s, archived_at = %s, archived_reason = %s,
                  updated_at = NOW()
            WHERE status = %s
              AND launched_at IS NULL
              AND launch_deadline IS NOT NULL
              AND launch_deadline <= %s
            RETURNING id""",
        (STATUS_ARCHIVED, now, ARCHIVED_REASON_LAUNCH_MISSED,
         STATUS_ACTIVE, now),
    )
    archived = [r[0] for r in cur.fetchall()]

    # ─── 2. Organiser reminders at 48 h and 12 h left (once each) ─────────────
    # A reminder fires for an active, un-launched community whose deadline is in
    # (now, now + Xh] and whose matching column is still NULL. The 12 h bucket
    # intentionally also catches a community already inside 12 h even if its 48 h
    # reminder somehow never ran — each column guards its own bucket.
    reminded = {}
    for hours in LAUNCH_REMINDER_HOURS:
        col = f'launch_reminded_{hours}h_at'
        cutoff = now + timedelta(hours=hours)
        cur.execute(
            f"""SELECT id FROM communities
                 WHERE status = %s
                   AND launched_at IS NULL
                   AND launch_deadline IS NOT NULL
                   AND launch_deadline > %s
                   AND launch_deadline <= %s
                   AND {col} IS NULL""",
            (STATUS_ACTIVE, now, cutoff),
        )
        ids = [r[0] for r in cur.fetchall()]
        if ids:
            cur.execute(
                f"UPDATE communities SET {col} = %s WHERE id = ANY(%s)",
                (now, ids),
            )
        reminded[hours] = ids

    # ─── 3. Post-launch member health (D666) ─────────────────────────────────
    health = run_post_launch_member_health(cur, now=now)

    return {
        'archived': archived,
        'reminded_48h': reminded.get(48, []),
        'reminded_12h': reminded.get(12, []),
        # [LOCAL-704 / D666] Post-launch low/zero-member handling.
        'low_members_warned': health['low_members_warned'],
        'archived_no_members': health['archived_no_members'],
    }


def run_post_launch_member_health(cur, now=None):
    """[LOCAL-704 / D666] The post-launch member-health pass of the hourly job.

    For every LAUNCHED, still-active community, compute its ACTIVE member count
    (unexpired paid passes, owner excluded) and apply D666:

      * count >= 2 → healthy: clear low_members_since / zero_members_since /
        last_low_warning_at so a later dip starts a fresh warning cycle.
      * count < 2  → low: stamp low_members_since the FIRST time it drops (day
        0), warn the organiser + remaining members that day, then again every
        LOW_MEMBERS_WARNING_EVERY_DAYS (7) days while it stays below. The warn
        buckets are returned (ids to notify); the push itself is the app/
        notification layer's job, exactly like the launch reminders.
      * count == 0 → also track zero_members_since; at
        COMMUNITY_ZERO_MEMBERS_ARCHIVE_DAYS (7) consecutive days at 0 → archive
        (status 'archived', archived_reason 'no_members'). A community at 1
        member for any length of time is NEVER archived (only a full week at 0).

    Returns {'low_members_warned': [ids], 'archived_no_members': [ids]}.
    Idempotent per cadence: last_low_warning_at guards the weekly warning;
    zero_members_since guards the archive. A healthy community is cleared, so a
    later drop warns again immediately (a fresh day 0).

    Note: a membership expiring is what makes a count drop — expiry is not an
    event the server is pinged on, so this pass is where the drop is observed
    (the hourly cadence keeps it timely). Everything keys off
    _active_member_count, the single source of truth for member_count."""
    now = now or _utcnow_aware()
    now = _as_aware(now)

    low_warned = []
    archived_no_members = []

    # Every launched, still-active community is a candidate. (A launched
    # community whose status is handover/archived is not 'active' and is left
    # to the step-down / launch-window paths.)
    cur.execute(
        """SELECT id, low_members_since, last_low_warning_at, zero_members_since
             FROM communities
            WHERE status = %s AND launched_at IS NOT NULL""",
        (STATUS_ACTIVE,),
    )
    rows = cur.fetchall()
    for cid, low_since, last_warn, zero_since in rows:
        count = _active_member_count(cur, cid, now=now)

        if count >= COMMUNITY_MIN_ACTIVE_MEMBERS:
            # Healthy — clear the low/zero tracking so a later dip starts fresh.
            if low_since is not None or zero_since is not None or last_warn is not None:
                cur.execute(
                    "UPDATE communities SET low_members_since = NULL, "
                    "zero_members_since = NULL, last_low_warning_at = NULL, "
                    "updated_at = NOW() WHERE id = %s",
                    (cid,),
                )
            continue

        # Below the bar (0 or 1 active member).
        set_cols = []
        set_vals = []
        # Stamp low_members_since the first time it drops.
        if low_since is None:
            low_since = now
            set_cols.append("low_members_since = %s")
            set_vals.append(now)
        # Track zero_members_since only while at exactly 0.
        if count == 0:
            if zero_since is None:
                zero_since = now
                set_cols.append("zero_members_since = %s")
                set_vals.append(now)
        else:
            # 1 member — not zero; clear any zero timer (a member came back to 1).
            if zero_since is not None:
                zero_since = None
                set_cols.append("zero_members_since = NULL")

        # Should we warn this run? Day 0 (no warning yet) OR >= 7 days since the
        # last warning.
        warn_now = False
        if last_warn is None:
            warn_now = True
        else:
            if (now - _as_aware(last_warn)) >= timedelta(days=LOW_MEMBERS_WARNING_EVERY_DAYS):
                warn_now = True
        if warn_now:
            set_cols.append("last_low_warning_at = %s")
            set_vals.append(now)

        if set_cols:
            cur.execute(
                f"UPDATE communities SET {', '.join(set_cols)}, updated_at = NOW() "
                "WHERE id = %s",
                (*set_vals, cid),
            )
        if warn_now:
            low_warned.append(cid)

        # Archive after a full week at 0 active members.
        if count == 0 and zero_since is not None:
            if (now - _as_aware(zero_since)) >= timedelta(days=COMMUNITY_ZERO_MEMBERS_ARCHIVE_DAYS):
                cur.execute(
                    """UPDATE communities
                          SET status = %s, archived_at = %s,
                              archived_reason = %s, updated_at = NOW()
                        WHERE id = %s AND status = %s""",
                    (STATUS_ARCHIVED, now, ARCHIVED_REASON_NO_MEMBERS,
                     cid, STATUS_ACTIVE),
                )
                archived_no_members.append(cid)

    return {'low_members_warned': low_warned,
            'archived_no_members': archived_no_members}


# ───────────────────────────────────────────────────────────────────────────
# Community row -> page payload
# ───────────────────────────────────────────────────────────────────────────
def _community_row(cur, community_id):
    cur.execute(
        """SELECT id, owner_user_id, name, description, organiser_name,
                  organiser_photo_url, organiser_bio, organiser_contact,
                  rules_text, waiver_text, has_waiver, is_paid, visibility,
                  latitude, longitude, join_code, feed_url, disabled,
                  status, stepped_down_at, archived_at,
                  launch_deadline, launched_at, archived_reason
           FROM communities WHERE id = %s""",
        (community_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = ['id', 'owner_user_id', 'name', 'description', 'organiser_name',
            'organiser_photo_url', 'organiser_bio', 'organiser_contact',
            'rules_text', 'waiver_text', 'has_waiver', 'is_paid', 'visibility',
            'latitude', 'longitude', 'join_code', 'feed_url', 'disabled',
            'status', 'stepped_down_at', 'archived_at',
            'launch_deadline', 'launched_at', 'archived_reason']
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
        # [LOCAL-702 / D663 §1] The hand-over state machine. `status` is active |
        # handover | archived. `looking_for_organiser` is the banner flag the
        # member sees while the community is in hand-over (closed to new members,
        # waiting for a volunteer to take over). `archived` tells the app to show
        # the read-only "archived — downloads only" state.
        'status': c['status'] or STATUS_ACTIVE,
        'looking_for_organiser': (c['status'] == STATUS_HANDOVER),
        'archived': (c['status'] == STATUS_ARCHIVED),
        'accepts_new_members': _accepts_new_members(c['status']),
        'stepped_down_at': c['stepped_down_at'].isoformat() if c['stepped_down_at'] else None,
        'archived_at': c['archived_at'].isoformat() if c['archived_at'] else None,
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
        # [LOCAL-704 / D665] The community's member count: ACTIVE members
        # (unexpired paid passes), EXCLUDING the owner (the organiser is never a
        # member). Shown on the community page, My communities, search/code
        # results, the map pin sheet and the invite email ("12 members").
        'member_count': _active_member_count(cur, community_id, now=now),
        # [LOCAL-703 / D664] The launch window: the deadline, hours left, the bar
        # (2), how many qualifying members so far, and whether it has launched.
        # The organiser's page and the creation confirmation render the live
        # countdown from this ("152 h left to get 2 paid members — 1 of 2 so
        # far"), turning green "Launched 🎉" once launched is true.
        'launch': _launch_info(c, cur=cur, now=now),
    }
    # [LOCAL-702 / D663 §1] While in hand-over, a member can see whether THEY
    # have volunteered (and whether they are the one the owner picked), so the
    # app can show "You volunteered" / "You were picked — Accept". NULL when the
    # caller has no offer. The owner additionally gets the full volunteer list to
    # pick from.
    if c['status'] == STATUS_HANDOVER:
        if user_id:
            payload['my_offer'] = _my_offer(cur, community_id, user_id)
        if is_owner:
            payload['organiser_offers'] = _offers_for(cur, community_id)
    # [LOCAL-700 §4] The organiser's page ALWAYS carries the invite code (with
    # Copy/Share/Email/Regenerate in the app). The code is owner-only — a member
    # or non-member never sees another community's code here.
    if is_owner:
        payload['join_code'] = c['join_code']
        payload['invite_message'] = build_invite_message(c['name'], c['join_code'])
    return payload


def _offers_for(cur, community_id):
    """The hand-over volunteers for a community (owner view). Each: the member,
    their offer status, and the pick/accept timestamps. Withdrawn/superseded
    offers are omitted — the owner only picks from live volunteers."""
    cur.execute(
        """SELECT member_user_id, status, picked_at, accepted_at, created_at
           FROM community_organiser_offers
           WHERE community_id = %s AND status IN ('offered', 'picked', 'accepted')
           ORDER BY created_at""",
        (community_id,),
    )
    return [{'member_user_id': r[0], 'status': r[1],
             'picked_at': r[2].isoformat() if r[2] else None,
             'accepted_at': r[3].isoformat() if r[3] else None,
             'offered_at': r[4].isoformat() if r[4] else None}
            for r in cur.fetchall()]


def _my_offer(cur, community_id, user_id):
    """The caller's own hand-over offer for a community, or None. Lets the app
    show "You volunteered" and, when picked, the "Accept" action."""
    cur.execute(
        """SELECT status, picked_at, accepted_at
           FROM community_organiser_offers
           WHERE community_id = %s AND member_user_id = %s""",
        (community_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {'status': row[0],
            'picked': row[0] == 'picked',
            'picked_at': row[1].isoformat() if row[1] else None,
            'accepted_at': row[2].isoformat() if row[2] else None}


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

        # [LOCAL-704 / D665 addendum] The organiser is NOT a member and cannot
        # buy a pass for their own community. The owner has full access to all
        # content without a pass; a self-purchase is refused (409) so the owner
        # never pads member_count or the launch bar.
        if user_id == c['owner_user_id']:
            cur.close()
            return jsonify({
                "error": "owner_cannot_join",
                "message": "You are the organiser of this community. The "
                           "organiser is not a member and has full access "
                           "without a pass.",
            }), 409

        # [LOCAL-702 / D663 §1] A community in hand-over or archived is CLOSED to
        # new members: no pass sales. An EXISTING member buying again (renewing)
        # is still allowed — the gate blocks a NEW membership, not a renewal of
        # one that already exists (the member joined while it was active).
        if not _accepts_new_members(c['status']):
            existing_member = _membership(cur, user_id, int(community_id)) is not None
            if not existing_member:
                cur.close()
                return jsonify({
                    "error": "community_closed_to_new_members",
                    "message": "This community has stopped taking new members "
                               "while it looks for a new organiser.",
                    "status": c['status'],
                }), 409

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
        # [LOCAL-703 / D664] A paid community launches on its 2nd paid member
        # (owner excluded; free joins never count for a paid community). Check
        # and stamp launched_at once; never reverts.
        _check_and_maybe_launch(cur, int(community_id))
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

    # [LOCAL-704 / D665] No free communities: every community is paid and must
    # offer at least one pass option. `is_paid` is accepted from the client for
    # back-compat but is always forced TRUE — the create form no longer has a
    # Free option. A create with no pass option is refused (400 pass_required).
    is_paid = True
    pass_products = data.get('pass_products') or []
    if not pass_products:
        return jsonify({
            "error": "pass_required",
            "message": "Every community charges at least $1 to join. Offer at "
                       "least one pass option.",
        }), 400

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
                    latitude, longitude, join_code, feed_url, launch_deadline)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       NOW() + make_interval(hours => %s))
               RETURNING id""",
            (owner_user_id, name, data.get('description'),
             data.get('organiser_name'), data.get('organiser_photo_url'),
             data.get('organiser_bio'), data.get('organiser_contact'),
             data.get('rules_text'), data.get('waiver_text'), has_waiver,
             is_paid, visibility, lat, lng, join_code, data.get('feed_url'),
             COMMUNITY_LAUNCH_HOURS),
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
        cur.execute("SELECT id, disabled, status FROM communities WHERE join_code = %s", (code,))
        row = cur.fetchone()
        if not row or row[1]:
            cur.close()
            return jsonify({"error": "not_found",
                            "message": "No community with that code."}), 404
        # [LOCAL-703 / D664] An ARCHIVED community's invite code stops working:
        # the code resolves to 410 community_closed ("This community has
        # closed"). This covers the launch-window miss (archived_reason
        # 'launch_window_missed') AND the LOCAL-702 hand-over expiry — once a
        # community is archived, its code is dead for new members. Existing
        # members keep their downloads (D658); they reach the community through
        # /communities/mine, not the code.
        if row[2] == STATUS_ARCHIVED:
            cur.close()
            return jsonify({"error": "community_closed",
                            "message": "This community has closed."}), 410
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
    """[LOCAL-704 / D665] Free join is gone — every community charges at least
    $1. This endpoint now refuses every caller: the owner with 409
    owner_cannot_join (the organiser is never a member), everyone else with 402
    pass_required (buy a pass through /purchases/verify). Kept for the app's
    old join path and for a clear, specific error."""
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
        # [LOCAL-704 / D665 addendum] The organiser is not a member and cannot
        # join their own community.
        if user_id == c['owner_user_id']:
            cur.close()
            return jsonify({
                "error": "owner_cannot_join",
                "message": "You are the organiser of this community. The "
                           "organiser is not a member and has full access "
                           "without a pass.",
            }), 409
        # Every community is paid (D665): a free join is always refused — buy a
        # pass through /purchases/verify.
        cur.close()
        return jsonify({
            "error": "pass_required",
            "message": "This community requires a pass. Every member pays at "
                       "least $1 to join.",
        }), 402
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
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({'id': r[0], 'name': r[1], 'latitude': r[2],
                        'longitude': r[3], 'is_paid': r[4], 'badge': 'community',
                        # [LOCAL-704 / D665] The member count shown on the map
                        # pin sheet for a Listed community (owner excluded).
                        'member_count': _active_member_count(cur, r[0])})
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
                # [LOCAL-704 / D665] The member count shown on each My
                # communities row (active members, owner excluded).
                'member_count': _active_member_count(cur, r[0], now=now),
            })
        cur.close()
        return jsonify({"communities": out}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/mine-owned', methods=['GET'])
def my_owned_communities():
    """[LOCAL-701 / D663 §3] The communities a user OWNS (is the organiser of),
    for the Generate tab's "For: my community <name>" selector. Only an owner of
    ≥ 1 community sees the selector, so the app calls this to populate it. Lists
    non-disabled communities only (a disabled community cannot receive a tour).
    Returns {communities: [{id, name}, ...]} (minimal shape — the selector needs
    only id + name)."""
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
            "SELECT id, name FROM communities "
            "WHERE owner_user_id = %s AND disabled = FALSE ORDER BY name",
            (user_id,),
        )
        out = [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]
        cur.close()
        return jsonify({"communities": out}), 200
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Organiser step-down, hand-over and archive (LOCAL-702, D663 §1)
# ───────────────────────────────────────────────────────────────────────────
@communities_bp.route('/communities/<int:community_id>/step-down', methods=['POST'])
def step_down(community_id):
    """[D663 §1 (a)] The OWNER steps down as organiser (after a confirmation in
    the app). active → handover. The community then: stays readable/playable for
    existing members, REFUSES new joins/pass sales (409), and shows "Looking for
    a new organiser" to members. Sets stepped_down_at, which starts the 30-day
    archive clock.

    Body: {owner_user_id | user_id}. 404 unknown; 403 not the owner; 409
    already_archived (an archived community cannot step down again). Stepping
    down an already-handover community is idempotent (200, no clock reset)."""
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
        if not c or c['disabled']:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['owner_user_id'] != user_id:
            cur.close()
            return jsonify({"error": "forbidden",
                            "message": "Only the owner can step down."}), 403
        if c['status'] == STATUS_ARCHIVED:
            cur.close()
            return jsonify({"error": "already_archived",
                            "message": "This community is archived."}), 409
        if c['status'] == STATUS_HANDOVER:
            # Idempotent — already stepping down. Do not reset the archive clock.
            payload = _community_page(cur, community_id, user_id=user_id)
            cur.close()
            return jsonify(payload), 200
        now = datetime.utcnow()
        cur.execute(
            "UPDATE communities SET status = %s, stepped_down_at = %s, "
            "updated_at = NOW() WHERE id = %s",
            (STATUS_HANDOVER, now, community_id),
        )
        conn.commit()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/offer-organiser', methods=['POST'])
def offer_organiser(community_id):
    """[D663 §1 (b)] A member VOLUNTEERS to take over a community in hand-over.
    Before stepping down the OWNER may also volunteer a hand-over (so this is
    open to the owner too); after stepping down, ANY member may volunteer. The
    offer is recorded (offered); the owner then picks one.

    Body: {user_id}. 404 unknown; 409 not_in_handover (only a hand-over
    community takes offers). Re-volunteering reuses the row and resets it to
    'offered' (so a withdrawn/superseded member can volunteer again)."""
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
        if c['status'] != STATUS_HANDOVER:
            cur.close()
            return jsonify({"error": "not_in_handover",
                            "message": "This community is not looking for a new "
                                       "organiser."}), 409
        cur.execute(
            """INSERT INTO community_organiser_offers
                   (community_id, member_user_id, status)
               VALUES (%s, %s, 'offered')
               ON CONFLICT (community_id, member_user_id) DO UPDATE SET
                   status = 'offered', picked_at = NULL, accepted_at = NULL,
                   updated_at = NOW()""",
            (community_id, user_id),
        )
        conn.commit()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/withdraw-offer', methods=['POST'])
def withdraw_offer(community_id):
    """[D663 §1 (b)] A volunteer withdraws their offer. Body: {user_id}. The
    offer becomes 'withdrawn' (inert). 404 if there is no such open offer."""
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
        cur.execute(
            "UPDATE community_organiser_offers SET status = 'withdrawn', "
            "picked_at = NULL, accepted_at = NULL, updated_at = NOW() "
            "WHERE community_id = %s AND member_user_id = %s "
            "AND status IN ('offered', 'picked') RETURNING id",
            (community_id, user_id),
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            cur.close()
            return jsonify({"error": "not_found",
                            "message": "No open offer to withdraw."}), 404
        cur.close()
        return jsonify({"withdrawn": True}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/pick-organiser', methods=['POST'])
def pick_organiser(community_id):
    """[D663 §1 (b)] The stepping-down OWNER picks a volunteer. Body:
    {owner_user_id | user_id, member_user_id}. The picked offer becomes
    'picked'; any previously picked offer for this community is superseded back
    to 'offered' (the owner can change their mind). The picked member then
    ACCEPTS to become the owner.

    404 unknown community / no such offer; 403 not the owner; 409 not_in_handover."""
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('owner_user_id') or data.get('user_id')
    member_user_id = data.get('member_user_id')
    if not user_id or not member_user_id:
        return jsonify({"error": "missing_fields",
                        "message": "owner_user_id and member_user_id are required."}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        c = _community_row(cur, community_id)
        if not c or c['disabled']:
            cur.close()
            return jsonify({"error": "not_found"}), 404
        if c['owner_user_id'] != user_id:
            cur.close()
            return jsonify({"error": "forbidden",
                            "message": "Only the owner can pick a new organiser."}), 403
        if c['status'] != STATUS_HANDOVER:
            cur.close()
            return jsonify({"error": "not_in_handover",
                            "message": "This community is not in hand-over."}), 409
        # The target must have an open offer.
        cur.execute(
            "SELECT id, status FROM community_organiser_offers "
            "WHERE community_id = %s AND member_user_id = %s",
            (community_id, member_user_id),
        )
        offer = cur.fetchone()
        if not offer or offer[1] not in ('offered', 'picked'):
            cur.close()
            return jsonify({"error": "no_such_offer",
                            "message": "That member has not volunteered."}), 404
        # Supersede any OTHER picked offer back to 'offered' (one pick at a time),
        # then pick this one. Done in this order so the partial unique index
        # (one 'picked' per community) is never violated mid-statement.
        cur.execute(
            "UPDATE community_organiser_offers SET status = 'offered', "
            "picked_at = NULL, updated_at = NOW() "
            "WHERE community_id = %s AND status = 'picked' AND member_user_id <> %s",
            (community_id, member_user_id),
        )
        cur.execute(
            "UPDATE community_organiser_offers SET status = 'picked', "
            "picked_at = %s, updated_at = NOW() "
            "WHERE community_id = %s AND member_user_id = %s",
            (datetime.utcnow(), community_id, member_user_id),
        )
        conn.commit()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>/accept-organiser', methods=['POST'])
def accept_organiser(community_id):
    """[D663 §1 (b)] The PICKED member accepts and becomes the owner. The
    community REOPENS (handover → active), ownership transfers to the member,
    the archive clock clears, and the incoming organiser's terms acceptance is
    recorded (LOCAL-691 document_acceptance). All open offers are closed.

    Body: {user_id}. 404 unknown; 409 not_in_handover; 403 not_picked (only the
    member the owner picked may accept)."""
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
        if c['status'] != STATUS_HANDOVER:
            cur.close()
            return jsonify({"error": "not_in_handover",
                            "message": "This community is not in hand-over."}), 409
        cur.execute(
            "SELECT status FROM community_organiser_offers "
            "WHERE community_id = %s AND member_user_id = %s",
            (community_id, user_id),
        )
        offer = cur.fetchone()
        if not offer or offer[0] != 'picked':
            cur.close()
            return jsonify({"error": "not_picked",
                            "message": "Only the member the owner picked can "
                                       "accept the hand-over."}), 403

        now = datetime.utcnow()
        # Transfer ownership + reopen. The organiser card is left as stored; the
        # app lets the new owner edit it. stepped_down_at/archived_at clear so
        # the community starts fresh.
        cur.execute(
            "UPDATE communities SET owner_user_id = %s, status = %s, "
            "stepped_down_at = NULL, archived_at = NULL, updated_at = NOW() "
            "WHERE id = %s",
            (user_id, STATUS_ACTIVE, community_id),
        )
        # Mark this offer accepted; close every other offer for the community.
        cur.execute(
            "UPDATE community_organiser_offers SET status = 'accepted', "
            "accepted_at = %s, updated_at = NOW() "
            "WHERE community_id = %s AND member_user_id = %s",
            (now, community_id, user_id),
        )
        cur.execute(
            "UPDATE community_organiser_offers SET status = 'withdrawn', "
            "picked_at = NULL, updated_at = NOW() "
            "WHERE community_id = %s AND member_user_id <> %s "
            "AND status IN ('offered', 'picked')",
            (community_id, user_id),
        )
        # [LOCAL-691] Record the incoming organiser's terms acceptance.
        _record_organiser_terms_acceptance(cur, user_id)
        conn.commit()
        payload = _community_page(cur, community_id, user_id=user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@communities_bp.route('/communities/<int:community_id>', methods=['DELETE'])
def delete_community(community_id):
    """[D663 §1 (d)] A community WITHOUT members can still be DELETED by its
    owner. The D658 rule only forbids CLOSING a community once members exist —
    so this refuses (409 has_members) when the community has ≥ 1 membership, and
    deletes the empty community (and its children, via ON DELETE CASCADE)
    otherwise.

    Body: {owner_user_id | user_id}. 404 unknown; 403 not the owner; 409
    has_members. 200 {deleted:true} on success."""
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
                            "message": "Only the owner can delete a community."}), 403
        if _community_member_count(cur, community_id) > 0:
            cur.close()
            return jsonify({
                "error": "has_members",
                "message": "A community with members cannot be deleted. Step "
                           "down to hand it over instead.",
            }), 409
        cur.execute("DELETE FROM communities WHERE id = %s", (community_id,))
        conn.commit()
        cur.close()
        return jsonify({"deleted": True, "id": community_id}), 200
    finally:
        conn.close()


@communities_bp.route('/communities/archive/run', methods=['POST'])
def archive_run():
    """[D663 §1 (c)] The DAILY archive job. Flip every community that has been in
    hand-over for ≥ 30 days (from stepped_down_at) to 'archived'. Returns the
    archived community ids. Idempotent (only matches status='handover').

    LEAD wires the daily tick to call this — see SUBMISSION_LOCAL-702.md."""
    err = _require_api_key()
    if err:
        return err
    conn = _get_db()
    try:
        cur = conn.cursor()
        archived = archive_stale_handovers(cur)
        conn.commit()
        cur.close()
        return jsonify({"archived": archived, "count": len(archived)}), 200
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


@communities_bp.route('/communities/launch-window/run', methods=['POST'])
def launch_window_run():
    """[LOCAL-703 / D664] The launch-window tick. Runs DAILY AND HOURLY (the
    hourly cadence keeps the organiser's final-hours countdown accurate). In one
    idempotent pass it:

      * ARCHIVES every active, un-launched community past its launch_deadline
        (status 'archived', archived_reason 'launch_window_missed'); its invite
        code then resolves to 410 community_closed. A launched community is
        never touched.
      * stamps the organiser reminders at 48 h and 12 h left (once each).

    Returns {archived, reminded_48h, reminded_12h} — the community ids affected
    this run. LEAD wires the tick to call this (see SUBMISSION_LOCAL-703.md)."""
    err = _require_api_key()
    if err:
        return err
    conn = _get_db()
    try:
        cur = conn.cursor()
        result = run_launch_window(cur)
        conn.commit()
        cur.close()
        return jsonify(result), 200
    finally:
        conn.close()
