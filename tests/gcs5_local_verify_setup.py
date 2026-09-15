#!/usr/bin/env python3
"""GCS-5 local verification: seed a cloud-equivalent (R2 + Postgres) tour.

Creates the minimal audio_tours schema, builds a 2-stop tour ZIP, uploads it to
the MinIO (R2 stand-in) bucket under tours/<id>.zip, and inserts a row with
audio_tour = NULL and tour_blob_uri set — reproducing the exact post-migration
state described in gap 3. Prints row counts before/after.

Env (override as needed):
  DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
  R2_ENDPOINT/R2_BUCKET/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY
"""
import io
import os
import sys
import zipfile
import psycopg2
import boto3

# SAFETY: this harness must ONLY ever talk to the local MinIO stand-in, never
# the real Cloudflare R2. Hard-set the endpoint/creds (do NOT read ambient env,
# which on dev machines points at production R2), and refuse to run otherwise.
R2_ENDPOINT = 'http://127.0.0.1:9010'
R2_BUCKET = 'v1-audiotours-r2-bucket'
R2_KEY_ID = 'minioadmin'
R2_SECRET = 'minioadmin'
if 'r2.cloudflarestorage.com' in os.getenv('R2_ENDPOINT', ''):
    print("[SAFETY] ambient R2_ENDPOINT points at real Cloudflare R2 — ignoring it; using local MinIO only.")

DB = dict(
    host=os.getenv('DB_HOST', '127.0.0.1'),
    port=os.getenv('DB_PORT', '5544'),
    dbname=os.getenv('DB_NAME', 'audiotours'),
    user=os.getenv('DB_USER', 'admin'),
    password=os.getenv('DB_PASSWORD', 'password123'),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS audio_tours (
    id               SERIAL PRIMARY KEY,
    tour_name        TEXT,
    request_string   TEXT,
    audio_tour       BYTEA,
    lat              DOUBLE PRECISION,
    lng              DOUBLE PRECISION,
    content_language TEXT,
    creator_type     TEXT,
    stops_count      INTEGER,
    tour_content     TEXT,
    original_tour_id INTEGER,
    derived_from_tour_id INTEGER,
    number_requested INTEGER DEFAULT 0,
    tour_blob_uri    TEXT
);
"""

STOP1 = "Welcome to the original first stop. This audio was generated before any edits."
STOP2 = "This is the second stop of the original tour, describing the east wing."


def build_source_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('audio_1.txt', STOP1)
        z.writestr('audio_1.mp3', b'ID3ORIGINALAUDIO1')  # dummy mp3-ish bytes
        z.writestr('audio_2.txt', STOP2)
        z.writestr('audio_2.mp3', b'ID3ORIGINALAUDIO2')
        z.writestr('index.html', '<html><body>original</body></html>')
    return buf.getvalue()


def main():
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)

    # Row count before
    cur.execute("SELECT count(*) FROM audio_tours")
    before = cur.fetchone()[0]
    print(f"[SETUP] audio_tours row count BEFORE seed: {before}")

    zip_bytes = build_source_zip()

    # Insert row first to get id, then set tour_blob_uri = tours/<id>.zip
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, audio_tour, lat, lng, "
        "content_language, creator_type, stops_count, number_requested) "
        "VALUES (%s, %s, NULL, %s, %s, 'en', 'AI', %s, 0) RETURNING id",
        ('GCS5 R2 Migrated Tour', 'seed', 42.36, -71.06, 2))
    tour_id = cur.fetchone()[0]
    key = f"tours/{tour_id}.zip"

    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_KEY_ID,
                      aws_secret_access_key=R2_SECRET, region_name='auto')
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=zip_bytes)

    cur.execute("UPDATE audio_tours SET tour_blob_uri = %s WHERE id = %s", (key, tour_id))

    cur.execute("SELECT count(*) FROM audio_tours")
    after = cur.fetchone()[0]
    print(f"[SETUP] audio_tours row count AFTER seed: {after}")

    cur.execute("SELECT id, audio_tour IS NULL AS bytea_null, tour_blob_uri FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    print(f"[SETUP] seeded tour id={row[0]} audio_tour_is_null={row[1]} tour_blob_uri={row[2]}")
    print(f"[SETUP] R2 object: s3://{R2_BUCKET}/{key} ({len(zip_bytes)} bytes)")
    print(f"TOUR_ID={tour_id}")
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
