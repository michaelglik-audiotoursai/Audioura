#!/usr/bin/env python3
"""
Tour Pricing Service (LOCAL-677, D624 / D652)

Curator paid tours. A CURATOR (a creator whose level has plans.can_sell = TRUE —
the L4 "Curator" level) sets or clears a PRICE TIER on ONE of their OWN tours.
Buyers then unlock the tour through an in-app purchase (verified by the existing
/purchases/verify path, which writes tour_unlocks); Stop 1 plays free as a
preview and the other stops are locked until the tour is unlocked.

This module owns the SERVER side of pricing and unlocking:

  1. set_price(user_id, tour_id, tier)  — curator-only, own-tour-only. tier is a
     number 1..7 (a row in price_tiers) or None to clear (make the tour free).
     A non-curator, or a curator who does not own the tour, is refused.
  2. get_price(tour_id)                 — {is_paid, price_tier, price_usd,
     price_label, product_id} for a tour. A translation inherits its SOURCE
     tour's price (resolve to original first).
  3. record_unlock(...)                 — write a tour_unlocks row idempotently
     (UNIQUE(user_id,tour_id) → a replayed purchase never unlocks twice).
  4. is_unlocked / sales_count          — the preview gate and the curator's
     Sales count.
  5. preview_state(user_id, tour_id)    — {is_paid, unlocked, preview_stop_index,
     locked} the app uses to gate playback (Stop 1 free; the rest locked until
     unlocked). free_stops = 1 (Stop 1), from a config constant.
  6. register_pricing_routes(app)       — the Flask routes for the orchestrator.

The tier values come from ONE config table (price_tiers, migration 022) via
price_tiers.py — never hard-coded in the app. The curator entitlement is the
plans.can_sell flag (data, not code), and the creator is resolved exactly as the
reviews service resolves it, so pricing and reviews agree on who owns a tour.

Translation mapping mirrors tour_ratings/tour_reviews: a translation row
(audio_tours.original_tour_id set) shares its SOURCE tour's price AND unlock.
Every read and write resolves the given id to its original first.

Design decisions documented in SUBMISSION_LOCAL-677.md.
"""

import os
import sys

# Reuse the shared DB connection helper the other services use (tests/).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection  # noqa: E402

# Translation→original + download helpers (same ORIGINAL id as ratings/reviews).
import tour_rating_service as rating_svc  # noqa: E402
# Creator resolution (plans + tour_requests fallback) — pricing and reviews must
# agree on who owns a tour.
import tour_reviews_service as reviews_svc  # noqa: E402
# The tier config of record (DB-authoritative, code fallback).
import price_tiers as price_tiers_cfg  # noqa: E402


# How many opening stops play free as a PREVIEW on a paid, not-yet-unlocked
# tour. D624 / D652: "Stop 1 is a free preview". A config constant so it can
# move without touching the gate logic.
FREE_PREVIEW_STOPS = 1

# [LOCAL-693 / D660] Cached presence of tour_unlocks.consumed_at (migration 031).
# None = not yet checked. Lets unlock reads fall back on a pre-031 DB.
_HAS_CONSUMED_COLUMN = None


# ─── Curator entitlement ──────────────────────────────────────────────────────

def is_curator(cur, user_id):
    """True if this device's level has plans.can_sell = TRUE (the Curator level).

    Reads device_entitlement.level then the plan's can_sell flag — DATA, not a
    hard-coded level name, so if Michael later grants can_sell to another level
    this honours it with no code change. A device with no entitlement row is L1
    (install default) and cannot sell. Never raises: any lookup error → not a
    curator (fail closed — pricing is a privileged action).
    """
    if not user_id:
        return False
    try:
        cur.execute(
            "SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,)
        )
        row = cur.fetchone()
        level = row[0] if row else 'l1'
        cur.execute("SELECT can_sell FROM plans WHERE plan_id = %s", (level,))
        prow = cur.fetchone()
        return bool(prow and prow[0])
    except Exception:  # noqa: BLE001 — a privileged check must fail closed, not 500
        return False


def is_tour_owner(cur, user_id, original_id):
    """True if user_id is the CREATOR of this (original) tour.

    Uses the SAME resolution as the reviews service (optional explicit
    audio_tours.creator_user_id, else the earliest tour_requests.secret_id), so
    pricing and reviews never disagree on ownership. Returns False when the
    creator cannot be resolved — a curator can only price a tour we can prove is
    theirs.
    """
    try:
        creator = reviews_svc.resolve_tour_creator(cur, original_id)
    except Exception:  # noqa: BLE001
        creator = None
    return creator is not None and str(creator) == str(user_id)


# ─── Tour role / ownership context (LOCAL-762 / D711 §1–§2) ───────────────────

# source_kind value that marks an organiser-audio (BROADCAST) tour: the
# organiser's own hosted audio, maintained off-app. Mirrors the app's
# isOrganiserAudioTour and organiser_audio_tours.SOURCE_KIND.
ORGANISER_AUDIO_SOURCE_KIND = 'organiser_audio'


def _tour_community_context(cur, original_id):
    """The community facts the Listen ⋮ menu + role line need for a tour, read
    off the ORIGINAL audio_tours row and its community (if any). Never raises —
    an absent column / row degrades to Nones. Returns:
        {source_kind, community_id, community_name, community_visibility,
         organiser_user_id}
    community_visibility is the TOUR's visibility inside the community
    ('members' | 'public'); organiser_user_id is the community OWNER.
    """
    ctx = {
        "source_kind": None,
        "community_id": None,
        "community_name": None,
        "community_visibility": None,
        "organiser_user_id": None,
    }
    try:
        cur.execute(
            "SELECT source_kind, community_id, community_visibility "
            "FROM audio_tours WHERE id = %s",
            (int(original_id),),
        )
        row = cur.fetchone()
        if row:
            ctx["source_kind"] = row[0]
            ctx["community_id"] = int(row[1]) if row[1] is not None else None
            ctx["community_visibility"] = row[2]
    except Exception:  # noqa: BLE001 — a missing column must not 500 a read
        return ctx

    if ctx["community_id"] is not None:
        try:
            cur.execute(
                "SELECT name, owner_user_id FROM communities WHERE id = %s",
                (ctx["community_id"],),
            )
            crow = cur.fetchone()
            if crow:
                ctx["community_name"] = crow[0]
                ctx["organiser_user_id"] = (
                    str(crow[1]) if crow[1] is not None else None
                )
        except Exception:  # noqa: BLE001
            pass
    return ctx


def tour_role(user_id, tour_id):
    """Per-tour ownership/role context for THIS viewer, for the Listen ⋮ menu and
    the role line (LOCAL-762 / D711). Resolves a translation to its original so
    a translation reports the same role as its source.

    Returns:
        {
          tour_id,                 # the original id the role is computed on
          is_owner,                # creator == this user
          is_curator,              # this user's level has plans.can_sell
          source_kind,             # e.g. 'organiser_audio' (broadcast) or None
          is_broadcast,            # source_kind == 'organiser_audio'
          community_id,            # int or None
          community_name,          # str or None
          community_visibility,    # 'members' | 'public' | None  (TOUR's)
          is_community,            # belongs to a community
          is_organiser,            # this user OWNS that community
        }
    Never raises — every lookup fails closed to the safe (least-privileged)
    value, so a transient error never grants Price/Re-score the user shouldn't
    see.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = rating_svc.resolve_original_id(cur, tour_id)
        ctx = _tour_community_context(cur, original_id)
        is_owner = is_tour_owner(cur, user_id, original_id)
        curator = is_curator(cur, user_id)
        community_id = ctx["community_id"]
        is_organiser = bool(
            user_id
            and ctx["organiser_user_id"] is not None
            and str(ctx["organiser_user_id"]) == str(user_id)
        )
        return {
            "tour_id": int(original_id),
            "is_owner": bool(is_owner),
            "is_curator": bool(curator),
            "source_kind": ctx["source_kind"],
            "is_broadcast": ctx["source_kind"] == ORGANISER_AUDIO_SOURCE_KIND,
            "community_id": community_id,
            "community_name": ctx["community_name"],
            "community_visibility": ctx["community_visibility"],
            "is_community": community_id is not None,
            "is_organiser": is_organiser,
        }
    finally:
        conn.close()


# ─── Price read ───────────────────────────────────────────────────────────────

def _price_payload(cur, original_id):
    """Build the {is_paid, price_tier, price_usd, price_label, product_id} block
    for an ORIGINAL tour id from its stored price_tier + the tier config."""
    tier = None
    try:
        cur.execute(
            "SELECT price_tier FROM audio_tours WHERE id = %s", (int(original_id),)
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            tier = int(row[0])
    except Exception:  # noqa: BLE001 — unknown/absent column → free
        tier = None

    if tier is None:
        return {
            "tour_id": int(original_id),
            "is_paid": False,
            "price_tier": None,
            "price_usd": None,
            "price_label": "Free",
            "product_id": None,
        }
    info = price_tiers_cfg.tier_info(tier, cur) or {}
    return {
        "tour_id": int(original_id),
        "is_paid": True,
        "price_tier": tier,
        "price_usd": info.get("price_usd"),
        "price_label": info.get("label") or "Free",
        "product_id": info.get("product_id"),
    }


def get_price(tour_id):
    """{is_paid, price_tier, price_usd, price_label, product_id} for a tour.

    A translation inherits its SOURCE tour's price (resolve to original first).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = rating_svc.resolve_original_id(cur, tour_id)
        return _price_payload(cur, original_id)
    finally:
        conn.close()


# ─── Price write (curator-only, own-tour-only) ────────────────────────────────

class PricingError(Exception):
    """Raised with a stable `code` so the route maps it to the right HTTP status.

    code ∈ 'not_curator' (403) | 'not_owner' (403) | 'invalid_tier' (400) |
           'unknown_tour' (404) | 'members_only_no_price' (400).
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def set_price(user_id, tour_id, tier):
    """Set or clear the price tier on a curator's OWN tour.

    tier: an int 1..7 (a valid, active row in price_tiers) to price the tour, or
          None to CLEAR the price (make it free again).

    Rules:
      * The caller must be a CURATOR (plans.can_sell) — else PricingError
        'not_curator'.
      * The caller must OWN the tour (be its creator) — else 'not_owner'.
      * A non-None tier must be a valid, active tier — else 'invalid_tier'.
      * The tour must exist — else 'unknown_tour'.
    The price is stored on the ORIGINAL tour (a translation inherits it), so a
    translation id is resolved to its original before writing.

    Returns the new {is_paid, price_tier, price_usd, price_label, product_id}.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        # The tour must exist (resolve translation → original).
        original_id = rating_svc.resolve_original_id(cur, tour_id)
        cur.execute("SELECT 1 FROM audio_tours WHERE id = %s", (int(original_id),))
        if cur.fetchone() is None:
            raise PricingError("unknown_tour", f"No tour with id {tour_id}.")

        # Curator entitlement.
        if not is_curator(cur, user_id):
            raise PricingError(
                "not_curator",
                "Only a Curator can set a price on a tour.",
            )

        # Ownership.
        if not is_tour_owner(cur, user_id, original_id):
            raise PricingError(
                "not_owner",
                "You can only set the price on a tour you created.",
            )

        # [LOCAL-762 / D711 §3] A members-only community tour cannot be priced:
        # it is already covered by the membership dues. Only a NON-None tier
        # (actually setting a price) is refused — CLEARING a price (tier=None)
        # on such a tour is always allowed. Members get the tour "Included with
        # membership"; a public community tour (community_visibility='public')
        # may be priced for non-members.
        if tier is not None:
            ctx = _tour_community_context(cur, original_id)
            if ctx["community_id"] is not None and \
                    ctx["community_visibility"] == 'members':
                raise PricingError(
                    "members_only_no_price",
                    "Members-only tours are covered by the membership dues "
                    "and cannot be priced.",
                )

        # Validate the tier (None = clear; any other value must be a valid tier).
        if tier is not None and not price_tiers_cfg.is_valid_tier(tier, cur):
            raise PricingError(
                "invalid_tier",
                f"'{tier}' is not a valid price tier.",
            )
        tier_value = int(tier) if tier is not None else None

        # Write the tier on the ORIGINAL tour. is_paid is a GENERATED column, so
        # it updates itself; we only ever write price_tier.
        cur.execute(
            "UPDATE audio_tours SET price_tier = %s WHERE id = %s",
            (tier_value, int(original_id)),
        )
        conn.commit()
        return _price_payload(cur, original_id)
    finally:
        conn.close()


# ─── Unlocks (written by the purchase path; read by the preview gate) ─────────

def record_unlock(user_id, tour_id, transaction_id=None, store=None,
                  price_usd=None):
    """Record (idempotently) that a buyer unlocked a tour.

    [LOCAL-693 / D660] Idempotency is on the ACTIVE (unconsumed) unlock only:
    ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING. A buyer
    holds at most one unconsumed unlock per language row, so a replayed purchase
    is still a no-op; but once a download has consumed the prior unlock, a fresh
    purchase writes a NEW active row (buy again to download again). This targets
    the partial unique index uq_tour_unlocks_active (migration 031) — the old
    full UNIQUE(user_id,tour_id) is gone, so a bare ON CONFLICT (user_id,tour_id)
    would error.

    [LOCAL-677B / D653] Every language copy unlocks SEPARATELY: the unlock keys
    on the GIVEN language row's OWN tour_id, NOT its source. Buying Russian
    unlocks Russian only; English needs its own purchase. (A translation still
    INHERITS its source's PRICE — see get_price — but not its unlock.) Returns
    {tour_id, unlocked:True, created:bool} where `created` is True only when a
    new row was written.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        own_id = int(tour_id)
        cur.execute(
            """
            INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING
            RETURNING id
            """,
            (user_id, own_id, transaction_id, store, price_usd),
        )
        created = cur.fetchone() is not None
        conn.commit()
        return {
            "tour_id": own_id,
            # Kept for backward compatibility with callers that read this key;
            # it now equals the OWN id (unlock is per language row, D653).
            "original_tour_id": own_id,
            "unlocked": True,
            "created": created,
        }
    finally:
        conn.close()


def _unlocks_has_consumed_column(cur):
    """True if tour_unlocks has the LOCAL-693 consumed_at column. Cached on the
    module. Lets is_unlocked_cur / the counts fall back gracefully on a DB that
    predates migration 031 (treat every unlock as active)."""
    global _HAS_CONSUMED_COLUMN
    if _HAS_CONSUMED_COLUMN is not None:
        return _HAS_CONSUMED_COLUMN
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'tour_unlocks' AND column_name = 'consumed_at'"
        )
        _HAS_CONSUMED_COLUMN = cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        _HAS_CONSUMED_COLUMN = False
    return _HAS_CONSUMED_COLUMN


def is_unlocked_cur(cur, user_id, original_id):
    """[LOCAL-693 / D660] True if this user holds an UNCONSUMED tour_unlocks row
    for this tour. A purchase now grants ONE download; once a download has
    consumed the unlock (consumed_at set), the tour is no longer "unlocked" for
    the purpose of a NEW download — the listener must buy again. (The row stays,
    keeping the buyer Verified, D647.) Cursor form, so it composes inside another
    transaction. Pre-031 DBs (no consumed_at) fall back to presence. Never
    raises."""
    if not user_id:
        return False
    try:
        if _unlocks_has_consumed_column(cur):
            cur.execute(
                "SELECT 1 FROM tour_unlocks "
                "WHERE user_id = %s AND tour_id = %s AND consumed_at IS NULL LIMIT 1",
                (user_id, int(original_id)),
            )
        else:
            cur.execute(
                "SELECT 1 FROM tour_unlocks WHERE user_id = %s AND tour_id = %s LIMIT 1",
                (user_id, int(original_id)),
            )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001 — absent table (pre-022) → not unlocked
        return False


def download_counts_cur(cur, user_id, tour_id):
    """[LOCAL-693 / D660] (downloads_bought, downloads_used) for (user, language
    row): how many unlocks the user has EVER bought for this row, and how many of
    those have been consumed by a successful download. downloads_bought -
    downloads_used = the unconsumed unlocks still spendable on a download. Keyed
    on the OWN language id (unlocks are per language, D653). Pre-031 DB → used=0
    (no unlock has been consumed because the column does not exist yet). Never
    raises; returns (0, 0) on any error or absent table."""
    if not user_id:
        return 0, 0
    try:
        if _unlocks_has_consumed_column(cur):
            cur.execute(
                "SELECT COUNT(*), COUNT(consumed_at) "
                "FROM tour_unlocks WHERE user_id = %s AND tour_id = %s",
                (user_id, int(tour_id)),
            )
            row = cur.fetchone()
            bought = int(row[0]) if row and row[0] is not None else 0
            used = int(row[1]) if row and row[1] is not None else 0
            return bought, used
        cur.execute(
            "SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s AND tour_id = %s",
            (user_id, int(tour_id)),
        )
        row = cur.fetchone()
        return (int(row[0]) if row and row[0] is not None else 0), 0
    except Exception:  # noqa: BLE001
        return 0, 0


def is_unlocked(user_id, tour_id):
    """True if this user has unlocked THIS language copy.

    [LOCAL-677B / D653] Per-language: keyed on the GIVEN tour_id's OWN unlock,
    not its source. Buying Russian does not unlock English.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        return is_unlocked_cur(cur, user_id, int(tour_id))
    finally:
        conn.close()


def _language_family_ids(cur, tour_id):
    """All audio_tours ids in the same language FAMILY as tour_id: the original
    plus every translation of it. Used where a figure should POOL across
    languages (the curator's Sales count; the Verified-listener mark). Never
    raises — returns at least the original id."""
    try:
        original_id = rating_svc.resolve_original_id(cur, tour_id)
    except Exception:  # noqa: BLE001
        return [int(tour_id)]
    ids = {int(original_id)}
    try:
        cur.execute(
            "SELECT id FROM audio_tours WHERE original_tour_id = %s", (int(original_id),)
        )
        for (tid,) in cur.fetchall():
            ids.add(int(tid))
    except Exception:  # noqa: BLE001
        pass
    return sorted(ids)


def sales_count(tour_id):
    """How many unlocks (sales) a tour has — the curator's Sales count.

    [LOCAL-677B / D653] A translation unlocks separately, so the curator's Sales
    POOL across the whole language family (the original + every translation):
    one Russian sale and one English sale on the same tour read as 2 sales for
    the curator. 0 if the table is absent (pre-022)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            ids = _language_family_ids(cur, tour_id)
            cur.execute(
                "SELECT COUNT(*) FROM tour_unlocks WHERE tour_id = ANY(%s)",
                (ids,),
            )
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except Exception:  # noqa: BLE001
            return 0
    finally:
        conn.close()


# ─── Preview gate ─────────────────────────────────────────────────────────────

def preview_state(user_id, tour_id):
    """What the app needs to gate playback of a (possibly paid) tour.

    Returns:
        {
          tour_id, is_paid, unlocked,
          free_preview_stops,          # how many opening stops play free (1)
          locked,                      # True iff paid AND not unlocked
          price_tier, price_usd, price_label, product_id
        }
    A FREE tour is never locked (unlocked implicitly). A PAID tour the user has
    unlocked is not locked. A PAID tour the user has NOT unlocked is `locked`:
    the app plays Stop 1 (indices < free_preview_stops) as a preview and blocks
    the rest behind the Buy button.

    [LOCAL-677B / D653] The PRICE is inherited from the source tour (resolve to
    original), but the UNLOCK is per LANGUAGE: `unlocked`/`locked` are decided by
    whether THIS tour_id (the language the listener opened) has its own unlock
    row.

    [LOCAL-693 / D660] `unlocked` now means the user holds an UNCONSUMED
    purchase for this row (a download still available). After a download has
    consumed the purchase the tour reads as `locked` again (buy again to
    download again) — but anything already on the phone keeps playing offline
    (D654), and the buyer stays Verified (D647). Two extra counts are reported:
      * downloads_bought — unlocks ever bought for this row;
      * downloads_used   — those consumed by a successful download.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = rating_svc.resolve_original_id(cur, tour_id)
        price = _price_payload(cur, original_id)
        # Unlock keys on the OWN language id, not the source.
        unlocked = (not price["is_paid"]) or is_unlocked_cur(cur, user_id, int(tour_id))
        bought, used = download_counts_cur(cur, user_id, int(tour_id))
        return {
            **price,
            # Report the id the listener actually opened (the language row).
            "tour_id": int(tour_id),
            "unlocked": bool(unlocked),
            "free_preview_stops": FREE_PREVIEW_STOPS,
            "locked": bool(price["is_paid"] and not unlocked),
            # [LOCAL-693 / D660] per-download accounting for this (user, row).
            "downloads_bought": int(bought),
            "downloads_used": int(used),
        }
    finally:
        conn.close()


# ─── Flask API routes ─────────────────────────────────────────────────────────

def register_pricing_routes(app):
    """Register the pricing/unlock endpoints on a Flask app (the orchestrator).

    Endpoints:
        POST /tour/<tour_id>/price      {user_id, tier}   → set/clear price (curator)
        GET  /tour/<tour_id>/price                        → price block
        GET  /tour/<tour_id>/role?user_id=...             → ownership/role context
        GET  /tour/<tour_id>/unlock-state?user_id=...     → preview/lock state
        GET  /tour/<tour_id>/sales                        → unlock (sales) count
        GET  /price-tiers                                 → the tier config
    """
    from flask import request, jsonify

    @app.route('/tour/<tour_id>/role', methods=['GET'])
    def api_tour_role(tour_id):
        # [LOCAL-762 / D711] Per-tour ownership/role for the Listen ⋮ menu + role
        # line. user_id is optional (an anonymous viewer is never owner/organiser).
        user_id = request.args.get("user_id")
        try:
            result = tour_role(user_id, tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200

    @app.route('/tour/<tour_id>/price', methods=['POST'])
    def api_set_price(tour_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        if "tier" not in data:
            return jsonify({"error": "tier is required (number 1..7, or null to clear)"}), 400

        tier = data.get("tier")
        try:
            result = set_price(user_id, tour_id, tier)
        except PricingError as pe:
            status = {
                "not_curator": 403,
                "not_owner": 403,
                "invalid_tier": 400,
                "unknown_tour": 404,
                "members_only_no_price": 400,
            }.get(pe.code, 400)
            return jsonify({"error": pe.code, "message": pe.message}), status
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "ok", **result}), 200

    @app.route('/tour/<tour_id>/price', methods=['GET'])
    def api_get_price(tour_id):
        try:
            result = get_price(tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200

    @app.route('/tour/<tour_id>/unlock-state', methods=['GET'])
    def api_unlock_state(tour_id):
        user_id = request.args.get("user_id")
        try:
            result = preview_state(user_id, tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200

    @app.route('/tour/<tour_id>/sales', methods=['GET'])
    def api_sales(tour_id):
        try:
            count = sales_count(tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"tour_id": tour_id, "sales": count}), 200

    @app.route('/price-tiers', methods=['GET'])
    def api_price_tiers():
        conn = get_connection()
        try:
            cur = conn.cursor()
            tiers = price_tiers_cfg.load_price_tiers(cur)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
        # Shape as an ordered list the app can render directly. Each row carries
        # tier, product_id, price_usd, label and in_picker.
        #
        # [LOCAL-734] Release plan L4: the picker must offer ONLY tour products
        # that exist on the stores now. We cap the served in_picker to the
        # Apple-live allowlist (price_tiers.APPLE_LIVE_TOUR_PRODUCTS) HERE, over
        # whatever the DB table carries, so the app (which filters on in_picker)
        # can never offer a price with no store product — without a DB rewrite
        # and without hard-coding the list in the app. A tour already priced
        # outside the list keeps its price; this only governs the picker.
        live = price_tiers_cfg.APPLE_LIVE_TOUR_PRODUCTS
        out = []
        for t, info in sorted(tiers.items()):
            row = {"tier": t, **info}
            row["in_picker"] = bool(info.get("in_picker")) and (
                info.get("product_id") in live)
            out.append(row)
        return jsonify({"tiers": out}), 200
