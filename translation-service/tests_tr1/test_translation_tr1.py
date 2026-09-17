"""
GCS-TR1 red -> green tests for translation-service.

Covers the acceptance criteria:
  1. R2-migrated source (tour_content set, audio_tour NULL, tour_blob_uri -> real ZIP in MinIO):
     fixed code returns 200, inserts a row WITH an artifact, and the ZIP is valid with
     translated audio_N.txt. (Old code: 200 but artifact-less row -> download 404.)
  2. Failure path: source unobtainable (missing R2 key) -> endpoint non-200, NO row inserted.
  3. Cache trap: an artifact-less row for (original_tour_id, language) is ignored and a
     working row is created. (Old code returns the broken row.)
  4. Track: translation inherits the source tour's track ('storied' -> 'storied', 'beta' -> 'beta').
  5. Regression guard: a row inserted without an artifact must fail the test (D242).

External calls (AWS Translate / Polly) are patched at the method level so no money is spent.
Requires: local Postgres and MinIO (see docker-compose.test.yml), reached via env vars.

Run through run_tests_tr1.sh, which sets the env and brings the stack up/down.
"""
import io
import os
import zipfile

import psycopg2
import pytest

import translation_service as ts


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
RUS = "\u041f\u0435\u0440\u0435\u0432\u043e\u0434"  # "Перевод" — proves non-ASCII round-trips


def _fake_translate_text(self, text, target_language, preserve_voice_commands=False):
    if target_language == "en" or not text:
        return text
    return f"[{target_language}] {RUS}: {text}"


def _fake_generate_audio(self, text, target_language):
    # Deterministic fake MP3 bytes; never calls Polly.
    return b"ID3FAKEMP3" + text.encode("utf-8")[:16]


def _make_source_zip():
    """A realistic 'modernized' source tour ZIP: HTML + audio_1.mp3 + audio_1.txt (x3 stops)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        html = (
            "<html><head><title>Original Tour</title></head><body>"
            "<h1>Stop 1</h1><p>Welcome to the first stop of this tour.</p>"
            "<h1>Stop 2</h1><p>Here is the second stop with more history.</p>"
            "<h1>Stop 3</h1><p>The final stop wraps up the walk.</p>"
            "</body></html>"
        )
        z.writestr("tour.html", html)
        for i in (1, 2, 3):
            z.writestr(f"audio_{i}.mp3", b"ID3ORIGINALMP3STOP" + str(i).encode())
            z.writestr(f"audio_{i}.txt", f"English narration for stop {i}.")
    return buf.getvalue()


SOURCE_TOUR_CONTENT = (
    "Stop 1: Welcome to the first stop of this tour.\n\n"
    "Stop 2: Here is the second stop with more history.\n\n"
    "Stop 3: The final stop wraps up the walk."
)


def _db_connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=os.environ["DB_PORT"],
    )


def _has_artifact(row_audio_tour, row_blob_uri):
    """Mirror map_delivery_service.py:326-330 servability filter."""
    return row_audio_tour is not None or row_blob_uri is not None


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def r2_bucket():
    """Create the MinIO bucket used as R2 and yield an R2BlobStorage pointed at it."""
    from blobstorage import R2BlobStorage
    store = R2BlobStorage()
    try:
        store.client.create_bucket(Bucket=store.bucket)
    except Exception:
        pass  # already exists
    return store


@pytest.fixture()
def db():
    """Fresh audio_tours table per test (includes track + tour_blob_uri columns)."""
    conn = _db_connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS audio_tours")
    cur.execute(
        """
        CREATE TABLE audio_tours (
            id SERIAL PRIMARY KEY,
            tour_name TEXT,
            request_string TEXT,
            audio_tour BYTEA,
            number_requested INTEGER DEFAULT 0,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            content_language TEXT,
            original_tour_id INTEGER,
            tour_content TEXT,
            tour_blob_uri TEXT,
            track TEXT
        )
        """
    )
    cur.close()
    conn.close()
    yield
    # leave table for post-mortem inspection; next test drops it


@pytest.fixture()
def service(monkeypatch):
    monkeypatch.setattr(ts.TranslationService, "translate_text", _fake_translate_text)
    monkeypatch.setattr(ts.TranslationService, "generate_audio", _fake_generate_audio)
    return ts.TranslationService()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(ts.TranslationService, "translate_text", _fake_translate_text)
    monkeypatch.setattr(ts.TranslationService, "generate_audio", _fake_generate_audio)
    # rebind the module-level singleton the Flask routes use
    ts.translation_service = ts.TranslationService()
    ts.app.config["TESTING"] = True
    return ts.app.test_client()


def _seed_source(track="beta", store_zip_in_r2=True, r2_key="tours/107.zip", r2_bucket=None,
                 tour_content=SOURCE_TOUR_CONTENT, audio_tour=None):
    """Insert an R2-migrated source tour and (optionally) put its ZIP in MinIO."""
    if store_zip_in_r2 and r2_bucket is not None:
        r2_bucket.upload(r2_key, _make_source_zip())
    conn = _db_connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours
            (tour_name, request_string, audio_tour, number_requested, lat, lng,
             content_language, original_tour_id, tour_content, tour_blob_uri, track)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        ("Original Tour", "walking tour", audio_tour, 1, 40.0, -73.0,
         "en", None, tour_content, r2_key if store_zip_in_r2 else None, track),
    )
    sid = cur.fetchone()[0]
    cur.close()
    conn.close()
    return sid


def _count():
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM audio_tours")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def _fetch(row_id):
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, audio_tour, tour_blob_uri, track, content_language, original_tour_id "
        "FROM audio_tours WHERE id = %s",
        (row_id,),
    )
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r


# ----------------------------------------------------------------------------
# AC1: red -> green for the R2-migrated source
# ----------------------------------------------------------------------------
def test_ac1_r2_migrated_source_produces_valid_artifact(db, service, r2_bucket):
    sid = _seed_source(track="beta", r2_key="tours/107.zip", r2_bucket=r2_bucket)

    new_id = service.translate_tour_with_audio(sid, "ru")
    assert new_id, "translation should return a new tour id"

    row = _fetch(new_id)
    audio_tour, blob_uri = row[1], row[2]

    # D242 regression guard: the row MUST have a servable artifact.
    assert _has_artifact(audio_tour, blob_uri), (
        "GCS-TR1 regression: translation row was inserted without an artifact "
        "(audio_tour NULL and tour_blob_uri NULL) -> map-delivery would 404"
    )

    # The stored BYTEA must be a valid ZIP containing translated audio_N.txt.
    data = bytes(audio_tour)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        txt_names = [n for n in names if n.startswith("audio_") and n.endswith(".txt")]
        assert txt_names, f"no translated audio_N.txt in artifact: {names}"
        body = z.read(txt_names[0]).decode("utf-8")
        assert RUS in body, f"audio_1.txt not translated: {body!r}"


# ----------------------------------------------------------------------------
# AC2: failure path — source unobtainable, endpoint non-200, no row inserted
# ----------------------------------------------------------------------------
def test_ac2_missing_r2_key_fails_and_inserts_no_row(db, client):
    # Source points at an R2 key that was never uploaded.
    sid = _seed_source(track="beta", store_zip_in_r2=True, r2_key="tours/DOES_NOT_EXIST.zip",
                       r2_bucket=None)  # do NOT upload the object
    before = _count()

    resp = client.post("/translate-with-audio", json={
        "content_id": sid, "content_type": "tour", "languages": ["ru"],
    })
    assert resp.status_code != 200, "artifact failure must surface as non-200"
    payload = resp.get_json()
    assert payload["error_code"] == "TRANSLATION_ARTIFACT_FAILED"
    assert payload["translations"]["ru"]["error_code"] == "TRANSLATION_ARTIFACT_FAILED"

    after = _count()
    assert after == before, f"no row must be inserted on failure (before={before}, after={after})"


# ----------------------------------------------------------------------------
# AC3: cache trap — artifact-less row for same (tour, lang) is ignored
# ----------------------------------------------------------------------------
def test_ac3_cache_trap_ignores_artifactless_row(db, service, r2_bucket):
    sid = _seed_source(track="beta", r2_key="tours/107c.zip", r2_bucket=r2_bucket)

    # Seed a BROKEN prior translation: right (original_tour_id, language) but no artifact.
    conn = _db_connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours
            (tour_name, request_string, audio_tour, number_requested, lat, lng,
             content_language, original_tour_id, tour_content, tour_blob_uri, track)
        VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, NULL, %s) RETURNING id
        """,
        ("broken ru", "walking tour", 0, 40.0, -73.0, "ru", sid, "x", "beta"),
    )
    broken_id = cur.fetchone()[0]
    cur.close()
    conn.close()

    new_id = service.translate_tour_with_audio(sid, "ru")
    assert new_id != broken_id, "must NOT return the artifact-less cached row"

    row = _fetch(new_id)
    assert _has_artifact(row[1], row[2]), "regenerated row must have an artifact"


# ----------------------------------------------------------------------------
# AC4: track inheritance
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("track", ["storied", "beta"])
def test_ac4_track_inherited_from_source(db, service, r2_bucket, track):
    sid = _seed_source(track=track, r2_key=f"tours/track_{track}.zip", r2_bucket=r2_bucket)
    new_id = service.translate_tour_with_audio(sid, "ru")
    row = _fetch(new_id)
    assert row[3] == track, f"translation track should inherit source ({track!r}), got {row[3]!r}"


# ----------------------------------------------------------------------------
# AC5 / D242: explicit regression guard the task can 'break to see red'.
# If the artifact guard is removed, translate_tour_with_audio would insert a NULL-artifact
# row on ZIP-build failure; this test asserts that never happens.
# ----------------------------------------------------------------------------
def test_ac5_no_row_without_artifact_when_zip_build_fails(db, service, r2_bucket, monkeypatch):
    sid = _seed_source(track="beta", r2_key="tours/107z.zip", r2_bucket=r2_bucket)
    before = _count()

    # Force the ZIP builder to fail the way the historic bug did (returns None).
    monkeypatch.setattr(ts.TranslationService, "_create_mobile_compatible_zip",
                        lambda self, *a, **k: None)

    with pytest.raises(ts.TranslationArtifactError):
        service.translate_tour_with_audio(sid, "ru")

    after = _count()
    assert after == before, "no row may be inserted when the artifact build fails"
