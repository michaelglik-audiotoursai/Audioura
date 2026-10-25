"""
Stop Pool Provenance (LOCAL-766 / D713) — which tour(s) each pooled stop served.
================================================================================
The stop pool (LOCAL-590, ``stop_pool_store``) stores each reusable stop ONCE per
(venue identity, tour_type, cache version), keyed ``(pool_key, title_norm)``, with
no link to the tour it was written for. So an identical request by ANOTHER user is
served the same stops (``[LOCAL-590] POOL DELIVERY: reused=N``) — a free rebuild of
a PRICED or COMMUNITY tour. Whole-tour reuse is already creator-scoped
(LOCAL-727/D678); the pool was the remaining bypass (Michael, 2026-10-25).

This module records PROVENANCE and enforces the delivery rule:

  * :func:`record_pool_sources` — after an ``audio_tours`` row is INSERTed (so the
    tour id exists), link every pooled stop that tour delivered to the tour id.
    Called from ``tour_orchestrator_service.store_audio_tour`` where the id, the
    creator, the location and the tour_type are all in scope.

  * :func:`filter_protected_titles` / :func:`partition_pool_rows` — at SELECTION
    time (``stop_pool_orchestrator.maybe_generate_with_pool``), decide which pooled
    stops the requester may reuse. A pooled stop is SKIPPED (generated fresh
    instead) when ANY of its source tours is a community tour
    (``community_id IS NOT NULL``) or priced (``price_tier > 0``), UNLESS the
    requester is that tour's ``creator_user_id``. Checked at delivery time, so
    pricing a tour or attaching it to a community LATER protects it from then on.
    Each skip logs ``[LOCAL-766] POOL SKIP protected source tour=<id>
    reason=community|paid``.

  * :func:`backfill_from_tours` — match existing pooled stops to existing tours by
    content: for every ORIGINAL ``audio_tours`` row, parse its ``tour_content`` into
    the SAME stop units the pool stores and link the ones whose
    ``(pool_key, title_norm)`` is actually in ``stop_pool``. A pooled stop no tour's
    content matches stays UNPROVEN and therefore shareable (ticket rule).

Provenance identity is reproduced from ``stop_pool_store`` directly — the SAME
``_pool_key`` / ``_title_norm`` / ``venue_identity`` / ``parse_delivered_stops``
used to WRITE the pool, so a recorded link always targets the row the pool actually
holds. Organiser-audio tours (``source_kind = 'organiser_audio'``) are not generated
and never enter the pool, so they never produce provenance rows (there is nothing to
parse); the backfill skips them explicitly as a belt-and-braces guard.

Table discipline: additive only. This module CREATEs ``stop_pool_sources`` IF NOT
EXISTS (self-healing DDL identical to migration 051) and only ever INSERTs
(``ON CONFLICT DO NOTHING``). It never issues DELETE or DROP.
"""
import logging
from typing import Dict, List, Optional, Tuple

import psycopg2

logger = logging.getLogger(__name__)


# ── Schema (additive; mirrors migration 051; never DELETE/DROP) ──────────────

def ensure_table(conn) -> None:
    """Create the additive ``stop_pool_sources`` table if absent (idempotent).

    Identical to migration 051 so a service self-heals the table on any Postgres
    whether or not the migration has run. The FK to audio_tours is added guarded
    (only when audio_tours exists and the constraint is absent) with ON DELETE
    CASCADE so a provenance row never outlives its source tour.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stop_pool_sources (
                pool_key      TEXT    NOT NULL,
                title_norm    TEXT    NOT NULL,
                audio_tour_id INTEGER NOT NULL,
                recorded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (pool_key, title_norm, audio_tour_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_stop_pool_sources_stop "
            "ON stop_pool_sources (pool_key, title_norm)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_stop_pool_sources_tour "
            "ON stop_pool_sources (audio_tour_id)"
        )
        # Guarded FK (safe before audio_tours exists; not duplicated on re-run).
        cur.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('audio_tours') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_constraint
                       WHERE conname = 'fk_stop_pool_sources_tour'
                         AND conrelid = 'stop_pool_sources'::regclass
                   ) THEN
                    ALTER TABLE stop_pool_sources
                        ADD CONSTRAINT fk_stop_pool_sources_tour
                        FOREIGN KEY (audio_tour_id) REFERENCES audio_tours(id)
                        ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )
    conn.commit()


# ── Identity: reproduce the pool's own keying ────────────────────────────────

def _pool_identity(location: str, tour_type: str, qid: Optional[str]) -> Tuple[str, str]:
    """Return (pool_key, resolved_qid) for a venue, using stop_pool_store's own
    identity functions so a recorded link targets the row the pool actually holds.
    """
    import stop_pool_store as pool
    identity = pool.venue_identity(location, qid)
    return pool._pool_key(identity, tour_type), qid


def _titles_norm_for_tour(tour_content: str) -> List[Tuple[str, str]]:
    """Parse a delivered tour into [(title, title_norm)] using the pool's own
    parser and normaliser — so the (pool_key, title_norm) computed here matches
    the stop_pool row the stop was stored under. Empty titles are dropped."""
    import stop_pool_store as pool
    out = []
    for u in pool.parse_delivered_stops(tour_content or ""):
        title = u.get("title") or ""
        tnorm = pool._title_norm(title)
        if tnorm:
            out.append((title, tnorm))
    return out


# ── Record (live path) ───────────────────────────────────────────────────────

def record_pool_sources(
    db_url: str,
    location: str,
    tour_type: str,
    audio_tour_id: int,
    tour_content: str,
    qid: Optional[str] = None,
) -> int:
    """Link every pooled stop THIS tour delivered to its audio_tours id.

    Called after the audio_tours row is INSERTed (new-insert or replacement path),
    where the tour id exists. Parses ``tour_content`` into the pool's stop units,
    computes each stop's ``(pool_key, title_norm)`` exactly as the pool store does,
    and INSERTs a provenance row per stop (``ON CONFLICT DO NOTHING`` — recording
    the same link twice is a no-op). Returns the number of rows written (new links).

    A row is inserted for a stop even if that stop is not (yet) in ``stop_pool``:
    the pool store runs in the SAME delivery, so the row normally exists; recording
    the provenance unconditionally means a later pool read finds the link whichever
    order the two writes landed in. The delivery rule only consults provenance for
    stops that ARE in the pool, so a provenance row for an absent stop is inert.

    Best-effort and non-fatal: any failure logs and returns 0 — provenance must
    never fail a tour that is already stored (mirrors the pool store's own
    swallow-and-continue contract).
    """
    if not db_url or not audio_tour_id or not tour_content:
        return 0
    try:
        pool_key, _ = _pool_identity(location, tour_type, qid)
        pairs = _titles_norm_for_tour(tour_content)
        if not pairs:
            return 0
        written = 0
        conn = psycopg2.connect(db_url)
        ensure_table(conn)
        with conn.cursor() as cur:
            for _title, tnorm in pairs:
                cur.execute(
                    "INSERT INTO stop_pool_sources (pool_key, title_norm, audio_tour_id) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (pool_key, tnorm, int(audio_tour_id)),
                )
                written += cur.rowcount
        conn.commit()
        conn.close()
        logger.info(
            f"[LOCAL-766] provenance: linked {written} pooled stop(s) to tour "
            f"{audio_tour_id} under {pool_key}"
        )
        return written
    except Exception as e:
        logger.warning(f"[LOCAL-766] provenance record error (non-fatal): {e}")
        return 0


# ── Delivery rule ─────────────────────────────────────────────────────────────

def _protected_titles_for_keys(
    conn,
    pool_keys: List[str],
    requester_user_id: Optional[str],
) -> Dict[str, Tuple[int, str]]:
    """Return {title_norm: (tour_id, reason)} for pooled stops under ANY of
    ``pool_keys`` that are PROTECTED for ``requester_user_id``.

    A stop is protected when it has a source tour that is community
    (community_id IS NOT NULL) or priced (price_tier > 0) AND the requester is NOT
    that tour's creator_user_id. The requester's OWN protected tours never protect
    a stop from that same requester (the creator keeps reuse). When several source
    tours protect the same stop, the FIRST (lowest id) protecting tour is reported
    for the log line; 'community' is preferred over 'paid' when a tour is both.

    Dual-key (D582 class). ``get_pool_stops`` reads a venue's stops under BOTH the
    ``qid:`` pool key and the ``loc:`` pool key (resolver flakiness can split one
    venue's pool across the two), and the live recording path records under the
    ``loc:`` key while a delivery that resolves a QID reads under the ``qid:`` key.
    So the protection lookup must span BOTH keys too, keyed only by ``title_norm``
    (which is identical across the two keys for the same stop) — otherwise a stop
    recorded under one key would never be found when read under the other, and a
    priced/community tour's stop would leak. ``pool_key = ANY(%s)`` unions them.

    Reads audio_tours.community_id / price_tier / creator_user_id directly (all
    present from migrations 035/022/041); on a schema without them the caller
    catches the error and treats every stop as unproven (shareable) — the safe,
    backward-compatible default.
    """
    protected: Dict[str, Tuple[int, str]] = {}
    norm = (requester_user_id or "").strip() or None
    if not pool_keys:
        return protected
    with conn.cursor() as cur:
        # Join provenance to its source tours; keep only PROTECTED source tours the
        # requester does not own. ORDER BY id so the lowest-id protecting tour is
        # the one reported per stop.
        cur.execute(
            """
            SELECT sps.title_norm,
                   at.id,
                   (at.community_id IS NOT NULL) AS is_community,
                   (COALESCE(at.price_tier, 0) > 0) AS is_paid
            FROM stop_pool_sources sps
            JOIN audio_tours at ON at.id = sps.audio_tour_id
            WHERE sps.pool_key = ANY(%s)
              AND (at.community_id IS NOT NULL OR COALESCE(at.price_tier, 0) > 0)
              AND (%s IS NULL OR at.creator_user_id IS DISTINCT FROM %s)
            ORDER BY at.id ASC
            """,
            (list(pool_keys), norm, norm),
        )
        for tnorm, tour_id, is_community, is_paid in cur.fetchall():
            if tnorm in protected:
                continue  # first (lowest-id) protecting tour already recorded
            reason = "community" if is_community else "paid"
            protected[tnorm] = (int(tour_id), reason)
    return protected


def _candidate_pool_keys(location: str, tour_type: str, qid: Optional[str]) -> List[str]:
    """Both pool keys a venue's stops may live under: the ``qid:`` key (when a QID
    is supplied) and the ``loc:`` key — mirroring ``get_pool_stops``. Deduped,
    order stable (qid first when present)."""
    import stop_pool_store as pool
    keys: List[str] = []
    if qid:
        keys.append(pool._pool_key(pool.venue_identity(location, qid), tour_type))
    loc_key = pool._pool_key(pool.venue_identity(location), tour_type)
    if loc_key not in keys:
        keys.append(loc_key)
    return keys


def partition_pool_rows(
    pooled_rows: List[Dict],
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Tuple[List[Dict], List[Tuple[Dict, int, str]]]:
    """Split pooled rows into (allowed, skipped) for this requester.

    ``allowed`` are the rows the requester may reuse (free/non-community stops, the
    requester's own protected stops, and any stop with UNPROVEN provenance — no
    stop_pool_sources row). ``skipped`` are rows protected by a community/paid
    source tour the requester does not own, each paired with the protecting
    (tour_id, reason) for the ``[LOCAL-766] POOL SKIP`` log.

    Backward compatible: if the provenance table or the audio_tours protection
    columns are unavailable (old schema), every row is ALLOWED — the pre-LOCAL-766
    behaviour — so a DB that has not run migration 051/022/035 keeps sharing as
    today (never withholds a stop it cannot evaluate).
    """
    if not pooled_rows:
        return [], []
    try:
        import stop_pool_store as pool
        pool_keys = _candidate_pool_keys(location, tour_type, qid)
        conn = psycopg2.connect(db_url)
        ensure_table(conn)
        try:
            protected = _protected_titles_for_keys(conn, pool_keys, user_id)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(
            f"[LOCAL-766] provenance unavailable ({e}); serving pool unfiltered")
        return list(pooled_rows), []

    if not protected:
        return list(pooled_rows), []

    import stop_pool_store as pool
    allowed: List[Dict] = []
    skipped: List[Tuple[Dict, int, str]] = []
    for row in pooled_rows:
        tnorm = pool._title_norm(row.get("title") or "")
        hit = protected.get(tnorm)
        if hit:
            skipped.append((row, hit[0], hit[1]))
        else:
            allowed.append(row)
    return allowed, skipped


def filter_protected_titles(
    pooled_rows: List[Dict],
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
    user_id: Optional[str] = None,
    log_fn=None,
) -> List[Dict]:
    """Return only the pooled rows the requester may reuse, logging each skip.

    Thin wrapper over :func:`partition_pool_rows` that emits one
    ``[LOCAL-766] POOL SKIP protected source tour=<id> reason=community|paid`` line
    per skipped stop (via ``log_fn`` or ``print``) and returns the allowed rows.
    The orchestrator calls this immediately after ``pool.get_pool_stops`` so every
    downstream count (K, reuse vs new) already reflects the protection.
    """
    allowed, skipped = partition_pool_rows(
        pooled_rows, location, tour_type, db_url, qid=qid, user_id=user_id)
    emit = log_fn or (lambda m: print(m))
    for _row, tour_id, reason in skipped:
        emit(f"  [LOCAL-766] POOL SKIP protected source tour={tour_id} reason={reason}")
    return allowed


# ── Backfill (prove what can be proven from existing data) ───────────────────

def backfill_from_tours(db_url: str, verbose: bool = True) -> Dict[str, int]:
    """Attribute existing pooled stops to existing tours by content.

    For every ORIGINAL ``audio_tours`` row (``original_tour_id IS NULL``) that is
    NOT an organiser-audio tour (``source_kind IS DISTINCT FROM 'organiser_audio'``
    — those never enter the pool), parse its ``tour_content`` into the pool's stop
    units and, for every stop whose ``(pool_key, title_norm)`` is actually present
    in ``stop_pool``, INSERT a provenance link (``ON CONFLICT DO NOTHING``).

    The venue identity and tour_type are reconstructed the same way the pool store
    computed them at generation time: identity from ``request_string`` (the
    location passed to generation; QID-resolved exactly as the store does), and
    tour_type from the tour's own content header / name. Because a pooled stop may
    have been stored under either the QID key or the normalised-location key
    (resolver flakiness, D582 class), BOTH candidate keys are tried and the link is
    recorded under whichever key actually holds the row.

    A pooled stop no tour's content matches stays UNPROVEN (no row) and therefore
    shareable — the ticket's "rows whose source cannot be proven stay shareable".

    Returns a counts dict:
        {"tours_scanned", "links_written", "pool_rows_total",
         "pool_rows_proven", "pool_rows_unproven"}
    so the caller can state the proven/unproven split. Idempotent: a second run
    writes 0 new links and reports the same proven/unproven counts.
    """
    import stop_pool_store as pool

    counts = {
        "tours_scanned": 0,
        "links_written": 0,
        "pool_rows_total": 0,
        "pool_rows_proven": 0,
        "pool_rows_unproven": 0,
    }
    conn = psycopg2.connect(db_url)
    try:
        ensure_table(conn)
        # The full set of pooled stops (every (pool_key, title_norm) in the pool).
        with conn.cursor() as cur:
            cur.execute("SELECT pool_key, title_norm FROM stop_pool")
            all_pool_rows = set((pk, tn) for pk, tn in cur.fetchall())
        counts["pool_rows_total"] = len(all_pool_rows)

        # Does audio_tours carry source_kind (migration 049)? Guard the SELECT so
        # it works on a schema that predates it.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'audio_tours' AND column_name = 'source_kind'"
            )
            _has_source_kind = cur.fetchone() is not None

        _src_filter = (
            " AND source_kind IS DISTINCT FROM 'organiser_audio'"
            if _has_source_kind else "")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tour_name, request_string, tour_content "
                "FROM audio_tours "
                "WHERE original_tour_id IS NULL AND tour_content IS NOT NULL"
                + _src_filter
            )
            tours = cur.fetchall()

        with conn.cursor() as cur:
            for tour_id, tour_name, request_string, tour_content in tours:
                counts["tours_scanned"] += 1
                location = request_string or tour_name or ""
                tour_type = _tour_type_from_tour(tour_name, tour_content)
                # Candidate pool keys: the QID identity (resolver may add one) and
                # the plain normalised-location identity. Record under whichever
                # actually holds the stop.
                try:
                    qid_identity = pool.resolve_venue_identity(location)
                except Exception:
                    qid_identity = pool.venue_identity(location)
                candidate_keys = []
                k_qid = pool._pool_key(qid_identity, tour_type)
                candidate_keys.append(k_qid)
                k_loc = pool._pool_key(pool.venue_identity(location), tour_type)
                if k_loc not in candidate_keys:
                    candidate_keys.append(k_loc)

                for _title, tnorm in _titles_norm_for_tour(tour_content):
                    for pk in candidate_keys:
                        if (pk, tnorm) in all_pool_rows:
                            cur.execute(
                                "INSERT INTO stop_pool_sources "
                                "(pool_key, title_norm, audio_tour_id) "
                                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                (pk, tnorm, int(tour_id)),
                            )
                            counts["links_written"] += cur.rowcount
        conn.commit()

        # Proven = distinct pooled stops that now have at least one provenance row.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ("
                "  SELECT DISTINCT sps.pool_key, sps.title_norm "
                "  FROM stop_pool_sources sps "
                "  JOIN stop_pool sp "
                "    ON sp.pool_key = sps.pool_key AND sp.title_norm = sps.title_norm"
                ") t"
            )
            counts["pool_rows_proven"] = cur.fetchone()[0]
        counts["pool_rows_unproven"] = (
            counts["pool_rows_total"] - counts["pool_rows_proven"])
    finally:
        conn.close()

    if verbose:
        print(
            "[LOCAL-766] backfill: "
            f"tours_scanned={counts['tours_scanned']} "
            f"links_written={counts['links_written']} "
            f"pool_rows_total={counts['pool_rows_total']} "
            f"pool_rows_proven={counts['pool_rows_proven']} "
            f"pool_rows_unproven={counts['pool_rows_unproven']}"
        )
    return counts


def _tour_type_from_tour(tour_name: str, tour_content: str) -> str:
    """Recover the tour_type the pool keyed on from a tour's own text.

    The pool key folds in ``(tour_type or '').strip().lower()``. A delivered tour's
    FIRST line reads ``"<location> - <Category> Tour"`` and the stored tour_name is
    built the same way (``store_audio_tour``), so the category word before " Tour"
    is the tour_type the pool used. Falls back to the tour_name's own suffix, then
    to "" (which still matches a pool key stored with an empty tour_type).
    """
    import re
    for text in (tour_content or "", tour_name or ""):
        first = (text or "").split("\n", 1)[0].strip()
        m = re.search(r"-\s*(.+?)\s+Tour\s*$", first)
        if m:
            return m.group(1).strip().lower()
    return ""


# ── CLI: run the backfill against DATABASE_URL ───────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import os
    import sys

    _db = os.environ.get("DATABASE_URL")
    if not _db:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    _c = backfill_from_tours(_db, verbose=True)
    sys.exit(0)
