#!/usr/bin/env python3
"""repin_tours.py — LOCAL-815: re-pin EXISTING stored tours without regenerating.

WHY (ticket): pins improved a lot (LOCAL-791E → 803 → 813), but tours already
generated keep their OLD, LLM-written pins. Regenerating a tour costs money and
can change good content. This tool re-applies TODAY's ``pin_snap`` — the SAME
snapper the generator runs (``generate_tour_text.py`` ~L26528) — to a tour that
is already stored, so an existing tour gets the improved pins while its text,
audio, and everything else stay byte-for-byte unchanged.

WHAT it does, per tour id:
  1. Reads the stops (title + shipped coordinate) from ``audio_tours.tour_content``
     and the stored ZIP (``audio_tours.audio_tour`` bytea, or the R2 blob when the
     row uses one).
  2. Derives the tour's scope / city / bbox from the stored ``request_string`` the
     SAME way the generator does (``_scope_from_request`` → ``geocode`` →
     ``_geocode_scope_bbox``), so the snap sees the same context it saw at
     generation — no regeneration, no LLM.
  3. Runs ``pin_snap.snap_pin`` on each stop. When a stop would MOVE MORE THAN
     ``--move-threshold-m`` (default 50 m) from its shipped pin to the snapped
     reference, it is rewritten; otherwise it is kept untouched.
  4. Rewrites ONLY the ``Coordinates:`` line in the THREE places the app reads:
       * ``audio_tours.tour_content`` (DB column),
       * the ZIP's per-stop text files ``audio_N.txt`` (what the Flutter app
         actually reads for pins — navigation_service.dart / treats_source_
         resolver.dart / my_tours_screen.dart, regex
         ``Coordinates:\\s*([-\\d.]+)\\s*,\\s*([-\\d.]+)``),
       * the ZIP's ``tour_content.txt`` (the map/index copy).
     No other byte of the content or ZIP is changed (audio, html, manifest, order,
     filenames, compression entries are all preserved).
  5. Stores the updated ZIP back to ``audio_tours.audio_tour`` and — only when the
     row uses an R2 blob (``tour_blob_uri`` set) — re-uploads the object to R2.
  6. Bumps the tour's version via the EXISTING mechanism (the append-only
     ``audio_tour_versions`` archive that map-delivery reads as
     ``MAX(version_no)+1``), so phones see a new version and re-download.

SAFETY:
  * DRY-RUN BY DEFAULT: prints the per-stop old → new coordinate and distance and
    writes NOTHING. ``--apply`` performs the writes.
  * ONE TRANSACTION PER TOUR on apply: a tour is fully updated or not at all.
  * BACKUP FIRST: before any write, the old ``tour_content`` and the old ZIP are
    saved to a local backups folder (``--backup-dir``, default
    ``repin_backups/<timestamp>/``).
  * NEVER CHANGES NON-COORDINATE TEXT. Only the number pair on a ``Coordinates:``
    line is replaced, in place.
  * NO DELETE anywhere — only INSERT (version snapshot) + UPDATE (the live row).
  * Writes ONLY to the tour ids you pass (``--tour-ids``), nothing else.
  * Works against any Postgres: ``--db-url`` (postgresql://…) or the service env
    vars (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT). No Mac-only paths — the
    SAME code runs against Cloud SQL (GCloud_Storied).

PAID-API CAP: the only paid calls are the reference LOOKUPS pin_snap makes
(Serper Places; Nominatim and Wikidata are free). A hard cap (``--max-api-usd``,
default $0.20 TOTAL across all tours) is enforced by wrapping the live reference
function and counting Serper calls against ``serper_meter`` pricing; once the cap
is hit, no further paid lookup is issued (stops then resolve via free Nominatim /
Wikidata or are left unsnapped).

Usage
=====
    # dry-run report (default) for the six catalog tours on the Mac DB
    python3 repin_tours.py --tour-ids 854 855 857 860 861 862 \\
        --db-url postgresql://admin:password123@localhost:5433/audiotours

    # apply
    python3 repin_tours.py --tour-ids 854 855 857 860 861 862 --apply \\
        --db-url postgresql://admin:password123@localhost:5433/audiotours

This file is a tool. It does nothing on import.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
import zipfile
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ───────────────────────── constants ─────────────────────────────────────────

# The task: rewrite a stop's pin only when it MOVES more than this many metres.
DEFAULT_MOVE_THRESHOLD_M = 50.0
# Hard ceiling on PAID (Serper) lookups, in USD, across the whole run.
DEFAULT_MAX_API_USD = 0.20
# Absolute safety net: never rewrite a pin to a point more than this far from the
# OLD shipped pin. A move this large is a wrong same-name reference in another
# city (Venice "Palazzo Ducale" resolved to a palace near Modena, 140 km away),
# never a pin correction. pin_snap's own off-scope guard catches these when a
# scope centre is known; this is a belt-and-suspenders cap that holds even if the
# centre is missing. A stop needing a move this big is reported but LEFT as-is.
DEFAULT_MAX_MOVE_KM = 20.0

# The per-stop text files inside the ZIP the app reads for pins.
_AUDIO_TXT_RE = re.compile(r"^audio_(\d+)\.txt$", re.IGNORECASE)
# The map/index copy inside the ZIP.
_ZIP_MAP_INDEX_NAME = "tour_content.txt"

# A "Coordinates: <lat>, <lng>" line. We capture the prefix and the two numbers
# so a rewrite replaces ONLY the number pair and preserves the exact prefix,
# separator and trailing text. Matches the Flutter app's own parser
# (RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)')).
_COORD_LINE_RE = re.compile(
    r"(?mi)^(?P<prefix>\s*Coordinates:\s*)(?P<lat>-?\d+(?:\.\d+)?)"
    r"(?P<sep>\s*,\s*)(?P<lng>-?\d+(?:\.\d+)?)")

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


# ───────────────────────── coordinate formatting ─────────────────────────────

def _fmt_coord_num(x: float) -> str:
    """Format one coordinate number as the snapper/packer does: 6 decimals,
    trailing zeros trimmed but at least one decimal kept. This matches the
    ``f"{lat:.6f}, {lng:.6f}"`` shape pin_snap writes into a poi while staying a
    clean number the app's ``[-\\d.]+`` parser accepts."""
    s = f"{float(x):.6f}"
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def _fmt_coord_pair(lat: float, lng: float) -> str:
    return f"{_fmt_coord_num(lat)}, {_fmt_coord_num(lng)}"


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in metres between (lat,lng) a and b. Uses the
    project's own ``geocode_stops.haversine_m`` so numbers match the pin gates,
    with a local fallback when that module is unavailable (offline tests)."""
    try:
        from geocode_stops import haversine_m as _hm
        return _hm(a, b)
    except Exception:
        import math
        R = 6371000.0
        lat1, lng1 = math.radians(a[0]), math.radians(a[1])
        lat2, lng2 = math.radians(b[0]), math.radians(b[1])
        h = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
        return 2 * R * math.asin(math.sqrt(h))


# ───────────────────────── parsing stored content ────────────────────────────

def parse_stops(text: str) -> List[Dict]:
    """Extract ordered stops ``[{"title", "coordinate": (lat,lng)|None}, …]`` from
    a tour's content text. Delegates to ``pin_proof.parse_tour_stops`` (the same
    parser the proof uses) with a self-contained fallback so this tool works even
    if pin_proof is unavailable."""
    try:
        from pin_proof import parse_tour_stops
        return parse_tour_stops(text or "")
    except Exception:
        pass
    if not text:
        return []
    out: List[Dict] = []
    headers = list(_STOP_HEADER_RE.finditer(text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        m = _COORD_LINE_RE.search(block)
        coord = (float(m.group("lat")), float(m.group("lng"))) if m else None
        out.append({"title": h.group(1).strip(), "coordinate": coord})
    return out


def rewrite_nth_coordinate(text: str, index: int, lat: float, lng: float) -> str:
    """Replace ONLY the ``<lat>, <lng>`` numbers on the ``index``-th (0-based)
    ``Coordinates:`` line of ``text``; everything else is left byte-for-byte.
    Returns the new text. If there is no such line, returns the text unchanged."""
    new_pair = _fmt_coord_pair(lat, lng)
    counter = {"i": 0}

    def _sub(m: "re.Match") -> str:
        cur = counter["i"]
        counter["i"] += 1
        if cur != index:
            return m.group(0)
        return (f"{m.group('prefix')}{_fmt_coord_num(lat)}"
                f"{m.group('sep')}{_fmt_coord_num(lng)}")

    return _COORD_LINE_RE.sub(_sub, text)


# ───────────────────────── scope derivation (no regeneration) ────────────────

def derive_scope(request_string: str,
                 tour_name: str = "",
                 want_bbox: bool = True,
                 anchor: Optional[Tuple[float, float]] = None,
                 log: Callable[[str], None] = print,
                 ) -> Tuple[str, Optional[Tuple[float, float]], Optional[Sequence[float]]]:
    """Derive ``(scope, scope_center, scope_bbox)`` for a STORED tour the SAME way
    the generator does from the request string — no LLM, no regeneration.

    Mirrors generate_tour_text.py (~L26528):
      scope        = _scope_from_request(location) or location
      scope_center = geocode_stops.geocode(scope)  (free: Nominatim)
      scope_bbox   = stop_existence_gate._geocode_scope_bbox(scope)

    Every step is best-effort and degrades gracefully: a failure leaves that piece
    as the request string / None, exactly as the generator's own fallbacks do.
    ``_scope_from_request`` lives in the 1.8 MB generate_tour_text module; it is
    imported lazily and, if that import is too heavy / unavailable, the request
    string is used as the scope directly (the generator's own fallback)."""
    location = (request_string or tour_name or "").strip()
    scope = location
    try:
        from generate_tour_text import _scope_from_request
        scope = _scope_from_request(location) or location
    except Exception as e:
        log(f"    [scope] _scope_from_request unavailable ({e}); using request "
            f"string as scope")
        scope = location

    scope_center: Optional[Tuple[float, float]] = None
    try:
        from geocode_stops import geocode as _geocode, location_hint as _hint
        for cand in (scope, (_hint(location) if _hint else None), location):
            if not cand:
                continue
            try:
                scope_center = _geocode(cand)
            except Exception:
                scope_center = None
            if scope_center:
                break
    except Exception as e:
        log(f"    [scope] geocode unavailable ({e}); scope_center=None")

    # Fallback to the tour's own stored anchor (audio_tours.lat/lng) when the
    # scope could not be geocoded. The anchor is always present on a stored tour
    # and is free + authoritative, so the pin_snap off-scope / centroid guards
    # stay ACTIVE (without a center those guards are disabled, which let a wrong
    # same-name Wikidata hit move a pin 140 km — Venice "Palazzo Ducale" → Sassuolo).
    if scope_center is None and anchor:
        try:
            a = (float(anchor[0]), float(anchor[1]))
            if abs(a[0]) <= 90 and abs(a[1]) <= 180:
                scope_center = a
                log(f"    [scope] geocode miss; using stored tour anchor "
                    f"{scope_center} as scope_center")
        except (TypeError, ValueError):
            pass

    scope_bbox: Optional[Sequence[float]] = None
    if want_bbox:
        try:
            from stop_existence_gate import _geocode_scope_bbox as _bbox
            scope_bbox = _bbox(scope) if scope else None
        except Exception as e:
            log(f"    [scope] bbox unavailable ({e}); scope_bbox=None")

    return scope, scope_center, scope_bbox


@contextlib.contextmanager
def _landmark_live_lookup():
    """[LOCAL-820] Turn the live Wikidata landmark lookup ON (LANDMARK_LIVE_LOOKUP=1)
    for the duration of the ``with`` block ONLY, then restore the prior value.

    Why this exists: this tool needs the live lookup while it resolves a museum
    building pin, but it must NOT leave ``LANDMARK_LIVE_LOOKUP`` set in the process
    env afterwards. The old ``os.environ.setdefault("LANDMARK_LIVE_LOOKUP", "1")``
    did exactly that, and in a single pytest process it leaked into
    ``local802_relevance_gate`` — whose same-building alias bridge then fired for
    every later test, over-merging distinct stops (``test_local818_district_refill``
    failed the moment it ran after ``test_local815_repin_tours``). Scoping the env
    change here fixes that at the source for every caller and every test order.

    A value already present is left untouched for the block and restored exactly
    (an explicit ``LANDMARK_LIVE_LOOKUP=0`` from the environment wins)."""
    key = "LANDMARK_LIVE_LOOKUP"
    had = key in os.environ
    prev = os.environ.get(key)
    if not had:
        os.environ[key] = "1"
    try:
        yield
    finally:
        if had:
            os.environ[key] = prev  # restore the caller's explicit value
        else:
            os.environ.pop(key, None)  # remove what we set; no leak


def derive_museum_fallback(scope: str,
                           scope_center: Optional[Tuple[float, float]],
                           scope_bbox: Optional[Sequence[float]],
                           tour_name: str,
                           request_string: str,
                           log: Callable[[str], None] = print,
                           ) -> Optional[Tuple[float, float]]:
    """[LOCAL-813] For a museum/gallery tour whose stops are ARTWORK titles with no
    place identity of their own, resolve the museum building's authoritative
    Wikidata P625 ONCE so an artwork stop can snap to the building (the generator
    does this). Best-effort; None when not a museum or not resolvable."""
    try:
        venue = (request_string or tour_name or scope or "").strip()
        if not venue:
            return None
        # [LOCAL-820] Enable the live Wikidata lookup ONLY for the duration of this
        # call. The previous `os.environ.setdefault("LANDMARK_LIVE_LOOKUP", "1")`
        # permanently mutated the process env; in a single pytest process that leak
        # flipped local802_relevance_gate's same-building alias bridge ON for every
        # later test, over-merging distinct stops (test_local818_district_refill
        # failed when run after test_local815_repin_tours). Scope it instead.
        with _landmark_live_lookup():
            from wikidata_landmark_lookup import lookup as _wd_lookup
            hit = _wd_lookup(venue, scope=scope, scope_center=scope_center,
                             scope_bbox=list(scope_bbox) if scope_bbox else None,
                             tour_language="en")
        if hit:
            mb = (float(hit[0]), float(hit[1]))
            log(f"    [museum] building pin for {venue!r}: {mb} "
                f"({hit[2] if len(hit) > 2 else 'wikidata_p625'})")
            return mb
    except Exception as e:
        log(f"    [museum] building pin lookup skipped (non-fatal): {e}")
    return None


# ───────────────────────── paid-API cap (Serper) ─────────────────────────────

class ApiBudget:
    """Enforce a hard USD ceiling on PAID reference lookups across the run.

    The only paid lookup pin_snap makes is Serper Places (Nominatim and Wikidata
    are free). We wrap ``pin_proof.reference_for_name`` with a guard that, once the
    estimated Serper spend reaches the cap, disables the Serper leg (passes a
    no-op serper_fn) so the lookup falls back to free Nominatim or returns nothing
    — a stop then stays unsnapped rather than spending over budget.

    Serper price per call comes from ``serper_meter`` when available, else a
    conservative default (Serper lists ~$0.001–$0.003 per query depending on plan;
    we use $0.003 to stay safely under any real cap)."""

    def __init__(self, max_usd: float, log: Callable[[str], None] = print):
        self.max_usd = float(max_usd)
        self.spent_usd = 0.0
        self.serper_calls = 0
        self._price = self._serper_unit_price()
        self.log = log

    @staticmethod
    def _serper_unit_price() -> float:
        try:
            import serper_meter as _sm
            for attr in ("PRICE_PER_CALL_USD", "COST_PER_CALL_USD",
                         "USD_PER_CALL", "PRICE_PER_QUERY_USD"):
                v = getattr(_sm, attr, None)
                if isinstance(v, (int, float)) and v > 0:
                    return float(v)
        except Exception:
            pass
        return 0.003  # conservative upper bound

    def remaining_usd(self) -> float:
        return max(0.0, self.max_usd - self.spent_usd)

    def can_spend(self) -> bool:
        return self.remaining_usd() >= self._price

    def note_serper_call(self) -> None:
        self.serper_calls += 1
        self.spent_usd += self._price


@contextlib.contextmanager
def _metered_serper_door(budget: "ApiBudget", scope: str,
                         scope_center: Optional[Tuple[float, float]],
                         active: bool = True):
    """Temporarily replace ``pin_proof._default_serper`` with a METERED version so
    every Serper (paid) lookup pin_snap's default door makes is counted against
    ``budget`` and refused once the cap is reached. Nominatim and Wikidata (free)
    are untouched, so a capped stop still resolves for free or stays unsnapped.
    When ``active`` is False (offline tests) this is a no-op context."""
    if not active:
        yield
        return
    import pin_proof as _pp
    original = _pp._default_serper

    def _metered(name, _scope, _center):
        if not budget.can_spend():
            return None  # over the paid cap → skip the Serper leg
        budget.note_serper_call()
        return original(name, _scope, _center)

    _pp._default_serper = _metered
    try:
        yield
    finally:
        _pp._default_serper = original


# ───────────────────────── DB access ─────────────────────────────────────────

def connect(db_url: Optional[str]):
    """Open a psycopg2 connection from ``db_url`` (postgresql://…) or the service
    env vars (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT). No Mac-only default so
    the SAME call reaches Cloud SQL when ``--db-url`` points there."""
    import psycopg2
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
    )


def _get_blob_storage():
    """Return an R2 blob storage handle, or None when R2 is not configured. We
    only ever WRITE R2 for a row that already uses an R2 blob (tour_blob_uri set);
    this just constructs the client lazily when needed."""
    from blobstorage import R2BlobStorage
    return R2BlobStorage()


# ───────────────────────── ZIP rewrite ───────────────────────────────────────

def rewrite_zip_coordinates(zip_bytes: bytes,
                            new_coords: Dict[int, Tuple[float, float]],
                            ) -> Tuple[bytes, Dict[str, int]]:
    """Return a NEW ZIP with the ``Coordinates:`` lines rewritten in the per-stop
    ``audio_N.txt`` files and in the ``tour_content.txt`` map/index copy, using
    ``new_coords`` (0-based stop index → (lat,lng)). Every other entry is copied
    byte-for-byte, preserving order, names, and per-file compression type.

    Returns ``(new_zip_bytes, changed)`` where ``changed`` maps the entry name to
    the number of coordinate lines rewritten in it (0 when unchanged)."""
    src = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    out_buf = io.BytesIO()
    changed: Dict[str, int] = {}
    with zipfile.ZipFile(out_buf, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            name = info.filename
            m = _AUDIO_TXT_RE.match(os.path.basename(name))
            did = 0
            if m:
                stop_idx = int(m.group(1)) - 1  # audio_1.txt → stop index 0
                if stop_idx in new_coords:
                    lat, lng = new_coords[stop_idx]
                    text = data.decode("utf-8")
                    # Per-stop file: only the FIRST Coordinates line (its own stop).
                    new_text = rewrite_nth_coordinate(text, 0, lat, lng)
                    if new_text != text:
                        data = new_text.encode("utf-8")
                        did = 1
            elif os.path.basename(name).lower() == _ZIP_MAP_INDEX_NAME:
                text = data.decode("utf-8")
                # Map/index copy: rewrite EACH stop's Coordinates line in order.
                new_text = text
                for idx in sorted(new_coords):
                    lat, lng = new_coords[idx]
                    new_text = rewrite_nth_coordinate(new_text, idx, lat, lng)
                if new_text != text:
                    data = new_text.encode("utf-8")
                    did = sum(1 for _ in _COORD_LINE_RE.finditer(text))
            # Preserve the original compression type for each entry.
            zinfo = zipfile.ZipInfo(filename=info.filename,
                                    date_time=info.date_time)
            zinfo.compress_type = info.compress_type
            zinfo.external_attr = info.external_attr
            zinfo.internal_attr = info.internal_attr
            zinfo.create_system = info.create_system
            dst.writestr(zinfo, data)
            changed[name] = did
    src.close()
    return out_buf.getvalue(), changed


# ───────────────────────── per-tour processing ───────────────────────────────

class TourResult:
    def __init__(self, tour_id: int):
        self.tour_id = tour_id
        self.tour_name = ""
        self.scope = ""
        self.scope_center: Optional[Tuple[float, float]] = None
        self.rows: List[Dict] = []       # per-stop decision rows
        self.moved: List[int] = []       # 0-based indices rewritten
        self.applied = False
        self.version_no: Optional[int] = None
        self.backup_paths: Dict[str, str] = {}
        self.error: Optional[str] = None
        self.r2_written = False


def _ensure_versioning_objects(cur) -> None:
    """Idempotent DDL for the version archive, mirroring
    tour_orchestrator_service._ensure_versioning_objects so a bump works on any
    Postgres (Cloud SQL, Mac dev, a fresh checkout, a throwaway test schema)."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'translation_stale'
    """)
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE audio_tours "
                    "ADD COLUMN translation_stale BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audio_tour_versions (
            id SERIAL PRIMARY KEY,
            tour_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            tour_content TEXT,
            zip_filename VARCHAR(512),
            stops_count INTEGER,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            replaced_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            replaced_by_job VARCHAR(128),
            CONSTRAINT uq_audio_tour_versions_tour_version UNIQUE (tour_id, version_no)
        )
    """)


def process_tour(conn,
                 tour_id: int,
                 apply_changes: bool,
                 move_threshold_m: float,
                 budget: ApiBudget,
                 backup_dir: str,
                 reference_fn_factory: Optional[Callable] = None,
                 max_move_km: float = DEFAULT_MAX_MOVE_KM,
                 log: Callable[[str], None] = print,
                 ) -> TourResult:
    """Re-pin ONE stored tour. Reads the row, derives scope, snaps each stop, and
    (when ``apply_changes``) rewrites the three coordinate places, stores the ZIP
    back, and bumps the version — all in ONE transaction. ``reference_fn_factory``
    overrides the live reference lookup (unit tests inject an offline one, which
    also means NO paid call)."""
    from pin_snap import snap_pin

    res = TourResult(tour_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT tour_name, request_string, tour_content, audio_tour, "
            "zip_filename, tour_blob_uri, stops_count, lat, lng "
            "FROM audio_tours WHERE id = %s", (tour_id,))
        row = cur.fetchone()
        if row is None:
            res.error = f"no audio_tours row with id={tour_id}"
            log(f"[tour {tour_id}] ERROR: {res.error}")
            return res
        (tour_name, request_string, tour_content, audio_tour, zip_filename,
         tour_blob_uri, stops_count, lat, lng) = row
        res.tour_name = tour_name or ""
        zip_bytes = bytes(audio_tour) if audio_tour is not None else None

        log(f"\n{'='*72}")
        log(f"[tour {tour_id}] {tour_name}")
        log(f"{'='*72}")
        if not tour_content:
            res.error = "row has empty tour_content"
            log(f"[tour {tour_id}] ERROR: {res.error}")
            return res

        stops = parse_stops(tour_content)
        if not stops:
            res.error = "no stops parsed from tour_content"
            log(f"[tour {tour_id}] ERROR: {res.error}")
            return res

        scope, scope_center, scope_bbox = derive_scope(
            request_string, tour_name,
            anchor=((lat, lng) if lat is not None and lng is not None else None),
            log=log)
        res.scope = scope
        res.scope_center = scope_center
        log(f"[tour {tour_id}] scope={scope!r} center={scope_center} "
            f"bbox={'set' if scope_bbox else None}")

        # Museum building fallback (only matters for artwork-title tours).
        venue_fallback = derive_museum_fallback(
            scope, scope_center, scope_bbox, tour_name, request_string, log=log)

        # Stops' centroid — the bound a reference must sit within, matching
        # snap_poi_coordinates' intent for a stored tour.
        coords_all = [s.get("coordinate") for s in stops]
        present = [c for c in coords_all if c]
        centroid = (
            (sum(c[0] for c in present) / len(present),
             sum(c[1] for c in present) / len(present)) if present else None)

        # Run the SAME snapper the generator uses. We want pin_snap's own door —
        # the Wikidata P625 landmark table (FREE) first, then Serper→Nominatim —
        # so the re-pin matches generation exactly. The ONLY paid leg is Serper;
        # to hold the run's $ cap we temporarily install a metered Serper into
        # pin_proof (the module pin_snap's default door calls) so every Serper
        # attempt counts and is refused once the cap is reached. Offline tests
        # inject a whole door via reference_fn_factory → no paid call at all.
        new_coords: Dict[int, Tuple[float, float]] = {}
        with _metered_serper_door(budget, scope, scope_center,
                                  active=reference_fn_factory is None):
            for i, st in enumerate(stops):
                title = st.get("title", "")
                coord = st.get("coordinate")
                if reference_fn_factory is not None:
                    # Offline/test door: the injected reference IS the whole door.
                    decision = snap_pin(
                        title, coord, scope=scope, scope_center=scope_center,
                        threshold_m=move_threshold_m,
                        reference_fn=reference_fn_factory(scope, scope_center),
                        stops_centroid=centroid, require_name_match=False,
                        use_landmark_table=False,
                        scope_bbox=scope_bbox, tour_language="en",
                        venue_fallback_coordinate=venue_fallback)
                else:
                    # Live door: landmark table (free) first, then the metered
                    # Serper→Nominatim default. reference_fn=None keeps the table on.
                    decision = snap_pin(
                        title, coord, scope=scope, scope_center=scope_center,
                        threshold_m=move_threshold_m, reference_fn=None,
                        stops_centroid=centroid, require_name_match=True,
                        use_landmark_table=True,
                        scope_bbox=scope_bbox, tour_language="en",
                        venue_fallback_coordinate=venue_fallback)

                row_rec = {
                    "index": i, "title": title, "old": coord,
                    "new": decision.get("new_coordinate"),
                    "snapped": bool(decision.get("snapped")),
                    "source": decision.get("source"),
                    "distance_m": decision.get("distance_m"),
                    "reason": decision.get("reason"),
                    "move_m": None, "rewrite": False,
                }
                # The realised MOVE: distance old shipped pin → new.
                if decision.get("snapped") and decision.get("new_coordinate"):
                    new_pt = decision["new_coordinate"]
                    move = haversine_m(coord, new_pt) if coord else float("inf")
                    row_rec["move_m"] = (round(move, 1) if move != float("inf")
                                         else None)
                    # Belt-and-suspenders: refuse an absurd move (wrong same-name
                    # place in another city) even if pin_snap's own guard was
                    # disabled by a missing scope centre.
                    if coord and move > max_move_km * 1000.0:
                        row_rec["reason"] = (
                            f"move {move/1000.0:.0f} km > {max_move_km:.0f} km cap "
                            f"— refused (wrong same-name reference); kept shipped pin")
                        row_rec["rewrite"] = False
                    elif move > move_threshold_m:
                        row_rec["rewrite"] = True
                        new_coords[i] = (float(new_pt[0]), float(new_pt[1]))
                res.rows.append(row_rec)

        res.moved = sorted(new_coords)

        # ---- report ----
        _print_tour_report(res, move_threshold_m, log)

        if not new_coords:
            log(f"[tour {tour_id}] no stop moves more than {move_threshold_m:.0f} m "
                f"— nothing to rewrite.")
            return res

        if not apply_changes:
            log(f"[tour {tour_id}] DRY-RUN — {len(new_coords)} stop(s) would be "
                f"rewritten. Re-run with --apply to write.")
            return res

        # ---- APPLY (one transaction for this tour) ----
        # 1) Backup old content + ZIP FIRST.
        _write_backups(res, tour_id, zip_filename, tour_content, zip_bytes,
                       backup_dir, log)

        # 2) Build new tour_content (DB) and new ZIP.
        new_content = tour_content
        for idx in sorted(new_coords):
            lat_i, lng_i = new_coords[idx]
            new_content = rewrite_nth_coordinate(new_content, idx, lat_i, lng_i)
        new_zip = None
        zip_changed: Dict[str, int] = {}
        if zip_bytes is not None:
            new_zip, zip_changed = rewrite_zip_coordinates(zip_bytes, new_coords)

        # 3) Version bump: snapshot the OLD row into audio_tour_versions
        #    (version_no = MAX+1), then UPDATE the live row. Same mechanism
        #    store_audio_tour / restore_tour_version use. No DELETE.
        _ensure_versioning_objects(cur)
        cur.execute("SELECT COALESCE(MAX(version_no), 0) + 1 "
                    "FROM audio_tour_versions WHERE tour_id = %s", (tour_id,))
        snapshot_version = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO audio_tour_versions
                (tour_id, version_no, tour_content, zip_filename,
                 stops_count, lat, lng, replaced_by_job)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (tour_id, snapshot_version, tour_content, zip_filename,
             stops_count, lat, lng, "repin_tours_LOCAL-815"),
        )
        res.version_no = snapshot_version

        # 4) UPDATE the live row: new content and (when present) new ZIP bytea.
        if new_zip is not None:
            cur.execute(
                "UPDATE audio_tours SET tour_content = %s, audio_tour = %s "
                "WHERE id = %s",
                (new_content, __import__("psycopg2").Binary(new_zip), tour_id))
        else:
            cur.execute("UPDATE audio_tours SET tour_content = %s WHERE id = %s",
                        (new_content, tour_id))

        # 5) R2: re-upload the object ONLY when the row uses an R2 blob.
        if tour_blob_uri and new_zip is not None:
            try:
                blob = _get_blob_storage()
                blob.upload(tour_blob_uri, new_zip)
                res.r2_written = True
                log(f"[tour {tour_id}] R2 re-uploaded {tour_blob_uri} "
                    f"({len(new_zip)} bytes)")
            except Exception as e:
                # The R2 write failing must abort this tour's transaction so the
                # DB and R2 never disagree.
                raise RuntimeError(f"R2 upload failed for {tour_blob_uri}: {e}")

        conn.commit()
        res.applied = True
        log(f"[tour {tour_id}] APPLIED — rewrote {len(new_coords)} stop(s); "
            f"archived old content as version {snapshot_version}; "
            f"ZIP entries changed: "
            f"{ {k: v for k, v in zip_changed.items() if v} }")
        return res

    except Exception as e:
        conn.rollback()
        res.error = str(e)
        import traceback
        log(f"[tour {tour_id}] ERROR (rolled back): {e}")
        log(traceback.format_exc())
        return res
    finally:
        cur.close()


def _write_backups(res: TourResult, tour_id: int, zip_filename, tour_content,
                   zip_bytes, backup_dir: str, log: Callable[[str], None]) -> None:
    os.makedirs(backup_dir, exist_ok=True)
    content_path = os.path.join(backup_dir, f"tour_{tour_id}_tour_content.txt")
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(tour_content)
    res.backup_paths["tour_content"] = content_path
    if zip_bytes is not None:
        base = os.path.basename(zip_filename) if zip_filename else f"tour_{tour_id}.zip"
        zip_path = os.path.join(backup_dir, f"tour_{tour_id}_{base}")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)
        res.backup_paths["zip"] = zip_path
    log(f"[tour {tour_id}] backup written: {list(res.backup_paths.values())}")


# ───────────────────────── reporting ─────────────────────────────────────────

def _fmt_pt(c) -> str:
    return "—" if not c else f"{c[0]:.5f}, {c[1]:.5f}"


def _print_tour_report(res: TourResult, move_threshold_m: float,
                       log: Callable[[str], None]) -> None:
    log(f"[tour {res.tour_id}] per-stop decision "
        f"(move gate {move_threshold_m:.0f} m):")
    log("  # | stop | old pin | new pin | move | source | rewrite | reason")
    for r in res.rows:
        move = "—" if r["move_m"] is None else f"{r['move_m']:.0f} m"
        log(f"  {r['index']+1} | {r['title'][:28]:28s} | {_fmt_pt(r['old'])} | "
            f"{_fmt_pt(r['new'])} | {move} | {r['source'] or '—'} | "
            f"{'YES' if r['rewrite'] else 'no'} | {r['reason']}")


def pin_proof_table(conn, tour_id: int, budget: Optional[ApiBudget] = None,
                    reference_fn_factory: Optional[Callable] = None,
                    log: Callable[[str], None] = print) -> Optional[str]:
    """Build a pin_proof Markdown table for a tour's CURRENT stored content, for
    the before/after the ticket asks for. Uses the metered Serper door so the
    proof's lookups also count against the paid cap."""
    try:
        from pin_proof import pin_report, format_pin_table
    except Exception as e:
        log(f"[tour {tour_id}] pin_proof unavailable ({e})")
        return None
    cur = conn.cursor()
    cur.execute("SELECT tour_name, request_string, tour_content "
                "FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    cur.close()
    if not row:
        return None
    tour_name, request_string, tour_content = row
    stops = parse_stops(tour_content or "")
    scope, scope_center, _ = derive_scope(request_string, tour_name,
                                          want_bbox=False, log=lambda *_: None)
    if reference_fn_factory is not None:
        # Offline: the injected door is both legs; no paid call.
        inj = reference_fn_factory(scope, scope_center)

        def serper_fn(name):
            r = inj(name)
            return (r[0], r[1]) if r else None
        report = pin_report(stops, scope=scope, scope_center=scope_center,
                            serper_fn=serper_fn, nominatim_fn=lambda n: None)
        return (f"### Tour {tour_id} — {tour_name}\n\n"
                + format_pin_table(report))

    # Live: meter Serper against the budget via the shared door.
    _b = budget or ApiBudget(0.0)
    with _metered_serper_door(_b, scope, scope_center, active=True):
        report = pin_report(stops, scope=scope, scope_center=scope_center)
    return (f"### Tour {tour_id} — {tour_name}\n\n"
            + format_pin_table(report))


# ───────────────────────── CLI ───────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-pin EXISTING stored tours with today's pin_snap, without "
                    "regenerating them (LOCAL-815).")
    parser.add_argument("--tour-ids", type=int, nargs="+", required=True,
                        help="audio_tours.id values to re-pin (writes ONLY these).")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"),
                        help="postgresql:// connection URL. Falls back to the "
                             "DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT env vars.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="show per-stop old→new and distance, write nothing "
                            "(default).")
    group.add_argument("--apply", action="store_true",
                       help="perform the rewrites, one transaction per tour.")
    parser.add_argument("--move-threshold-m", type=float,
                        default=DEFAULT_MOVE_THRESHOLD_M,
                        help=f"rewrite a stop only when it moves more than this "
                             f"many metres (default {DEFAULT_MOVE_THRESHOLD_M:.0f}).")
    parser.add_argument("--max-api-usd", type=float, default=DEFAULT_MAX_API_USD,
                        help=f"hard ceiling on PAID (Serper) lookups in USD across "
                             f"the whole run (default {DEFAULT_MAX_API_USD}).")
    parser.add_argument("--max-move-km", type=float, default=DEFAULT_MAX_MOVE_KM,
                        help=f"absolute safety cap: refuse to rewrite a pin that "
                             f"would move farther than this (default "
                             f"{DEFAULT_MAX_MOVE_KM:.0f} km) — a wrong same-name "
                             f"reference in another city.")
    parser.add_argument("--backup-dir", default=None,
                        help="folder for old content + ZIP backups "
                             "(default repin_backups/<timestamp>/).")
    parser.add_argument("--pin-proof", action="store_true",
                        help="also print a pin_proof table for each tour (the "
                             "before/after the ticket asks for).")
    args = parser.parse_args(argv)

    apply_changes = bool(args.apply)
    backup_dir = args.backup_dir or os.path.join(
        "repin_backups", datetime.now().strftime("%Y%m%d_%H%M%S"))

    print("=" * 72)
    print("repin_tours.py — LOCAL-815")
    print(f"  mode       : {'APPLY' if apply_changes else 'DRY-RUN (default)'}")
    print(f"  tour ids   : {args.tour_ids}")
    print(f"  move gate  : {args.move_threshold_m:.0f} m")
    print(f"  max move   : {args.max_move_km:.0f} km (absurd-move safety cap)")
    print(f"  paid cap   : ${args.max_api_usd:.2f} (Serper lookups only)")
    print(f"  backup dir : {backup_dir}")
    print(f"  db         : {'--db-url' if args.db_url else 'env vars'}")
    print("=" * 72)

    os.environ.setdefault("LANDMARK_LIVE_LOOKUP", "1")
    budget = ApiBudget(args.max_api_usd)

    try:
        conn = connect(args.db_url)
    except Exception as e:
        print(f"ERROR: could not connect to the database: {e}")
        return 2

    results: List[TourResult] = []
    try:
        for tid in args.tour_ids:
            if args.pin_proof:
                print(f"\n----- pin_proof BEFORE — tour {tid} -----")
                tbl = pin_proof_table(conn, tid, budget=budget)
                if tbl:
                    print(tbl)
            res = process_tour(conn, tid, apply_changes, args.move_threshold_m,
                               budget, backup_dir, max_move_km=args.max_move_km)
            results.append(res)
            if args.pin_proof and res.applied:
                print(f"\n----- pin_proof AFTER — tour {tid} -----")
                tbl = pin_proof_table(conn, tid, budget=budget)
                if tbl:
                    print(tbl)
    finally:
        conn.close()

    # ---- summary ----
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    rewritten_total = 0
    for r in results:
        status = ("ERROR: " + r.error) if r.error else (
            "applied" if r.applied else "dry-run")
        rewritten = len(r.moved)
        rewritten_total += rewritten
        extra = ""
        if r.applied:
            extra = (f"  version→{r.version_no}  "
                     f"r2={'yes' if r.r2_written else 'no'}  "
                     f"backups={list(r.backup_paths.values())}")
        print(f"  tour {r.tour_id}: {status}; stops rewritten={rewritten}{extra}")
    print(f"\n  rows {'updated' if apply_changes else 'that WOULD be updated'}: "
          f"{sum(1 for r in results if r.moved and not r.error)}")
    print(f"  total stops rewritten: {rewritten_total}")
    print(f"  paid Serper calls: {budget.serper_calls} "
          f"(est ${budget.spent_usd:.4f} of ${budget.max_usd:.2f} cap)")
    if not apply_changes:
        print("\n  DRY-RUN: nothing was written. Re-run with --apply to perform "
              "the rewrites.")
    return 0 if all(not r.error for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
