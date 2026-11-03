# [LOCAL-854] Audioura map-tile cache proxy (D757).
#
# WHY THIS EXISTS
# ---------------
# The app currently loads raster map tiles straight from
# tile.openstreetmap.org. That is a problem on three fronts (D757, DECISIONS.md):
#   1. OSM's tile-usage policy forbids heavy / commercial use of that server.
#   2. From Vietnam (Michael's field tests) the OSM host fails DNS and connect
#      intermittently, so the Home map goes grey.
#   3. The app's "fallback" hosts (a/b/c.tile.openstreetmap.org) are the SAME
#      OSM CDN, so they fail together.
#
# This service is our OWN read-through cache in front of a tile origin. The app
# points MAP_TILE_URL at it; it serves tiles from a Google Cloud Storage bucket
# (or a local dir in tests), only reaching the origin on a cache miss, and
# serving a stale cached copy when the origin is unreachable. That both honours
# OSM's policy (one well-identified client, cached, no bulk prefetch) and keeps
# the map alive on a flaky network.
#
# ORIGIN IS SWITCHABLE WITH NO CODE CHANGE
# ----------------------------------------
# TILE_ORIGIN is a URL template with {z}/{x}/{y} and an OPTIONAL {key}. To move
# off OSM to MapTiler later, set e.g.
#   TILE_ORIGIN=https://api.maptiler.com/maps/streets/{z}/{x}/{y}.png?key={key}
#   TILE_ORIGIN_KEY=<the key>
# and redeploy. No code change. The key is read from env, never committed.

from __future__ import annotations

import io
import logging
import os
import threading
from typing import Optional, Tuple

import requests
from flask import Flask, Response, abort, jsonify, request

# --------------------------------------------------------------------------- #
# Configuration (all via env so the same image runs in tests and on Cloud Run)
# --------------------------------------------------------------------------- #

# Origin template. {z}/{x}/{y} are required; {key} is optional (MapTiler etc.).
TILE_ORIGIN = os.environ.get(
    "TILE_ORIGIN", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
)
# Secret for the origin, injected into {key} if the template has it. Never logged.
TILE_ORIGIN_KEY = os.environ.get("TILE_ORIGIN_KEY", "")

# GCS bucket for the shared cache. When unset, fall back to a local directory
# (used by the local / CI tests — no cloud credentials needed).
TILE_CACHE_BUCKET = os.environ.get("TILE_CACHE_BUCKET", "").strip()
TILE_CACHE_DIR = os.environ.get("TILE_CACHE_DIR", "/tmp/tile_cache").strip()

# Descriptive User-Agent so the origin can identify us (OSM REQUIRES this; a
# generic agent is throttled or blocked).
ORIGIN_USER_AGENT = os.environ.get(
    "TILE_USER_AGENT",
    "Audioura/1.0 (+https://audioura.com; audiotoursai@gmail.com)",
)

# How long clients (and the app's on-disk cache) may keep a tile.
TILE_MAX_AGE = int(os.environ.get("TILE_MAX_AGE", "604800"))  # 7 days

# Cap concurrent ORIGIN fetches per instance so we never hammer the origin.
MAX_CONCURRENT_ORIGIN = int(os.environ.get("TILE_MAX_CONCURRENT_ORIGIN", "4"))

# Timeout for a single origin fetch.
ORIGIN_TIMEOUT = float(os.environ.get("TILE_ORIGIN_TIMEOUT", "10"))

# Zoom bounds for OSM-style raster tiles.
MIN_ZOOM = 0
MAX_ZOOM = 19

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tile_proxy")

# A bounded semaphore enforces the concurrency cap across the gunicorn worker's
# threads. (Each worker process has its own; keep the worker count modest.)
_origin_gate = threading.BoundedSemaphore(MAX_CONCURRENT_ORIGIN)


# --------------------------------------------------------------------------- #
# Cache backends — a tiny interface with a GCS and a local-filesystem impl.
# Both are read-through: the proxy reads, and on a miss writes the fetched tile.
# --------------------------------------------------------------------------- #


class _CacheBackend:
    def get(self, key: str) -> Optional[bytes]:  # pragma: no cover - interface
        raise NotImplementedError

    def put(self, key: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError


class _LocalCache(_CacheBackend):
    """Filesystem cache under TILE_CACHE_DIR. Used in tests / no-bucket mode."""

    def __init__(self, root: str):
        self._root = root
        os.makedirs(self._root, exist_ok=True)

    def _path(self, key: str) -> str:
        # key is "z/x/y"; keep the directory shape so it is easy to inspect.
        return os.path.join(self._root, key.replace("/", os.sep) + ".png")

    def get(self, key: str) -> Optional[bytes]:
        path = self._path(key)
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            return None
        except OSError as exc:  # unreadable cache must never break serving
            log.warning("[LOCAL-854] local cache read error %s: %s", key, exc)
            return None

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)  # atomic
        except OSError as exc:
            log.warning("[LOCAL-854] local cache write error %s: %s", key, exc)


class _GcsCache(_CacheBackend):
    """Google Cloud Storage cache. Object name is the tile key 'z/x/y.png'."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage  # imported lazily: tests don't need it

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def _blob(self, key: str):
        return self._bucket.blob(key + ".png")

    def get(self, key: str) -> Optional[bytes]:
        try:
            blob = self._blob(key)
            data = blob.download_as_bytes()
            return data
        except Exception as exc:  # NotFound or transient GCS error
            # NotFound is the common path (a miss); log transient errors quietly.
            name = type(exc).__name__
            if name not in ("NotFound",):
                log.warning("[LOCAL-854] gcs cache read error %s: %s", key, exc)
            return None

    def put(self, key: str, data: bytes) -> None:
        try:
            self._blob(key).upload_from_file(
                io.BytesIO(data), content_type="image/png"
            )
        except Exception as exc:
            log.warning("[LOCAL-854] gcs cache write error %s: %s", key, exc)


def _build_cache() -> _CacheBackend:
    if TILE_CACHE_BUCKET:
        log.info("[LOCAL-854] cache backend: GCS bucket %s", TILE_CACHE_BUCKET)
        return _GcsCache(TILE_CACHE_BUCKET)
    log.info("[LOCAL-854] cache backend: local dir %s", TILE_CACHE_DIR)
    return _LocalCache(TILE_CACHE_DIR)


# --------------------------------------------------------------------------- #
# Tile key validation and origin fetch
# --------------------------------------------------------------------------- #


def _validate(z: int, x: int, y: int) -> bool:
    """z 0-19 and x/y within [0, 2**z) — anything else is a bad request."""
    if z < MIN_ZOOM or z > MAX_ZOOM:
        return False
    limit = 1 << z
    return 0 <= x < limit and 0 <= y < limit


def _origin_url(z: int, x: int, y: int) -> str:
    return TILE_ORIGIN.format(z=z, x=x, y=y, key=TILE_ORIGIN_KEY)


def _etag(z: int, x: int, y: int, data: bytes) -> str:
    # A stable, content-sensitive ETag: tile coords + body length is enough to
    # let a client revalidate cheaply without hashing megabytes.
    return 'W/"{}-{}-{}-{}"'.format(z, x, y, len(data))


def _fetch_from_origin(z: int, x: int, y: int) -> Optional[bytes]:
    """Fetch one tile from the origin, capped by the concurrency gate.

    Returns PNG bytes on a 200 image/png response, else None. Never raises:
    the caller decides between stale-serve and 502.
    """
    url = _origin_url(z, x, y)
    acquired = _origin_gate.acquire(timeout=ORIGIN_TIMEOUT)
    if not acquired:
        log.warning("[LOCAL-854] origin gate timeout z=%s x=%s y=%s", z, x, y)
        return None
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": ORIGIN_USER_AGENT},
            timeout=ORIGIN_TIMEOUT,
        )
    except requests.RequestException as exc:
        log.warning("[LOCAL-854] origin error z=%s x=%s y=%s: %s", z, x, y, exc)
        return None
    finally:
        _origin_gate.release()

    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code == 200 and content_type.startswith("image/png"):
        return resp.content
    log.warning(
        "[LOCAL-854] origin non-tile z=%s x=%s y=%s status=%s type=%s",
        z, x, y, resp.status_code, content_type,
    )
    return None


# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #


def create_app(cache: Optional[_CacheBackend] = None) -> Flask:
    app = Flask(__name__)
    app.config["CACHE"] = cache or _build_cache()

    def _tile_response(data: bytes, z: int, x: int, y: int) -> Response:
        resp = Response(data, mimetype="image/png")
        resp.headers["Cache-Control"] = "public, max-age={}".format(TILE_MAX_AGE)
        resp.headers["ETag"] = _etag(z, x, y, data)
        return resp

    @app.route("/health")
    def health() -> Response:
        return jsonify(status="ok", origin_has_key="{key}" in TILE_ORIGIN)

    @app.route("/<int:z>/<int:x>/<int:y>.png")
    def tile(z: int, x: int, y: int) -> Response:
        if not _validate(z, x, y):
            abort(400, description="tile out of range")

        key = "{}/{}/{}".format(z, x, y)
        backend: _CacheBackend = app.config["CACHE"]

        cached = backend.get(key)
        if cached is not None:
            log.info("[LOCAL-854] tile hit %s", key)
            return _tile_response(cached, z, x, y)

        log.info("[LOCAL-854] tile miss %s", key)
        fetched = _fetch_from_origin(z, x, y)
        if fetched is not None:
            backend.put(key, fetched)
            return _tile_response(fetched, z, x, y)

        # Origin failed. Serve a stale copy if we somehow have one (another
        # worker may have written it between our get and now), else 502.
        stale = backend.get(key)
        if stale is not None:
            log.info("[LOCAL-854] tile stale %s", key)
            return _tile_response(stale, z, x, y)

        log.warning("[LOCAL-854] tile unavailable %s (origin down, no cache)", key)
        abort(502, description="tile origin unavailable and tile not cached")

    return app


# Module-level app for gunicorn: `gunicorn app:app`.
app = create_app()


if __name__ == "__main__":
    # Local dev convenience only; production uses gunicorn (see Dockerfile).
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
