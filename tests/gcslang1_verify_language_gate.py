#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GCS-LANG1 end-to-end verification — language gate on the narration, by effect.

Stands up its OWN local cloud-equivalent stack (never production), the same
harness shape as tests/gcs5e_verify_ru_auth.py:
  * Postgres  : docker container on 127.0.0.1:5546
  * R2        : MinIO S3 API on 127.0.0.1:9012, bucket v1-audiotours-r2-bucket
  * Polly     : tests/gcs5e_polly_auth_stub.py (auth-required TTS stub)
  * Language  : tests/gcslang1_lang_stub.py via the LOCAL_LANGUAGE_STUB_URL seam
                in tour_editing_phase2 — deterministic, so NO AWS is touched.
  * Identity  : LOCAL_IDENTITY_TOKEN so authenticated Polly calls succeed.

Runs the REAL tour_editing_phase2.py container against a seeded RU tour and
proves, by effect (GCS-LANG1 acceptance #1 and #2):

  A. The exact reported blob — a Russian narration whose stop blob also carries
     the Latin header (Coordinates:/Address:/place name) and one English
     `Orientation:` line — is ACCEPTED (HTTP 200) after the fix. The language
     stub judges the raw blob 'cv' but the service now detects on the stripped
     narration, judged 'ru'.

  B. A genuinely wrong-language edit — an all-English narration on the same RU
     tour — is STILL rejected 400 LANGUAGE_MISMATCH (detected_language 'en').

Both full JSON responses are printed for the submission.

SAFETY: talks ONLY to local MinIO/Postgres/stubs. Hard-refuses a real
r2.cloudflarestorage.com endpoint. Never issues DELETE FROM audio_tours.
Windows-safe: utf-8 everywhere; the Cyrillic bodies are built in-process from
\\u escapes so this file stays ASCII and no shell handles raw Cyrillic.

Usage:  python tests/gcslang1_verify_language_gate.py
        (requires docker with postgres:15-alpine and quay.io/minio/minio:latest)
"""
import io
import os
import sys
import json
import time
import zipfile
import subprocess
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

R2_ENDPOINT = 'http://127.0.0.1:9012'
R2_BUCKET = 'v1-audiotours-r2-bucket'
R2_KEY_ID = 'minioadmin'
R2_SECRET = 'minioadmin'
DB = dict(host='127.0.0.1', port='5546', dbname='audiotours',
          user='admin', password='password123')

PG_CONTAINER = 'gcslang1-pg'
MINIO_CONTAINER = 'gcslang1-minio'
PG_IMAGE = 'postgres:15-alpine'
MINIO_IMAGE = 'quay.io/minio/minio:latest'

SVC_PORT = 5135
POLLY_PORT = 5596
LANG_PORT = 5599
POLLY_LOG = os.path.join(HERE, 'gcslang1_polly_voice_log.jsonl')
POLLY_UNAUTH_LOG = os.path.join(HERE, 'gcslang1_polly_unauth_log.jsonl')
LANG_LOG = os.path.join(HERE, 'gcslang1_lang_stub.jsonl')
LOCAL_TOKEN = 'gcslang1-local-identity-token'

if 'r2.cloudflarestorage.com' in os.getenv('R2_ENDPOINT', ''):
    print("[SAFETY] ambient R2_ENDPOINT points at real Cloudflare R2 — ignoring; "
          "this harness only ever talks to local MinIO at " + R2_ENDPOINT)
os.environ['R2_ENDPOINT'] = R2_ENDPOINT
assert 'r2.cloudflarestorage.com' not in R2_ENDPOINT, "refusing a real R2 endpoint"

# --- the exact reported blob (built from \u escapes; file stays ASCII) --------
_STOP_NAME = "\u041a\u043b\u0430\u0434\u0431\u0438\u0449\u0435 \u0420\u0438\u043a\u044c\u0435"
_RU_NARRATION = (
    "\u042d\u0442\u043e \u0441\u0442\u0430\u0440\u0435\u0439\u0448\u0435\u0435 "
    "\u043a\u043b\u0430\u0434\u0431\u0438\u0449\u0435 \u041d\u0438\u0446\u0446\u044b, "
    "\u0433\u0434\u0435 \u043f\u043e\u0445\u043e\u0440\u043e\u043d\u0435\u043d\u044b "
    "\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0435 \u0433\u043e\u0440\u043e"
    "\u0436\u0430\u043d\u0435 \u0438 \u043c\u0435\u0446\u0435\u043d\u0430\u0442\u044b.\n"
    "\u0417\u0434\u0435\u0441\u044c \u0446\u0430\u0440\u0438\u0442 \u0442\u0438"
    "\u0448\u0438\u043d\u0430, \u0430 \u0441 \u0445\u043e\u043b\u043c\u0430 "
    "\u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0432\u0438\u0434 "
    "\u043d\u0430 \u0437\u0430\u043b\u0438\u0432 \u0410\u043d\u0433\u0435\u043b\u043e\u0432."
)
RED_BLOB = (
    _STOP_NAME + "\n"
    "Coordinates: 43.7066, 7.2831\n"
    "Address: Avenue Auguste V\u00e9rola, 06300 Nice, France\n"
    "Orientation: Face l'Imp\u00e9ratrice gate.\n"
    "\n"
    + _RU_NARRATION
)
ENGLISH_BLOB = (
    "Rimiez Cemetery\n"
    "Coordinates: 43.7066, 7.2831\n"
    "Address: Avenue Auguste V\u00e9rola, 06300 Nice, France\n"
    "Orientation: Face the Empress gate.\n"
    "\n"
    "This is the oldest cemetery in Nice, where notable citizens and patrons "
    "are buried. Silence reigns here, and from the hill a view opens onto the "
    "Bay of Angels below the old town."
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


def run(cmd, check=True, capture=False):
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, text=True, capture_output=capture)
    if check and r.returncode != 0:
        out = (r.stdout or '') + (r.stderr or '')
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(cmd)}\n{out}")
    return r


def docker_available():
    try:
        subprocess.run(['docker', 'info'], text=True, capture_output=True, timeout=20)
        return True
    except Exception:
        return False


def start_infra():
    run(['docker', 'rm', '-f', PG_CONTAINER], check=False, capture=True)
    run(['docker', 'rm', '-f', MINIO_CONTAINER], check=False, capture=True)
    run(['docker', 'run', '-d', '--name', PG_CONTAINER,
         '-e', 'POSTGRES_USER=admin', '-e', 'POSTGRES_PASSWORD=password123',
         '-e', 'POSTGRES_DB=audiotours', '-p', '5546:5432', PG_IMAGE])
    run(['docker', 'run', '-d', '--name', MINIO_CONTAINER,
         '-e', 'MINIO_ROOT_USER=minioadmin', '-e', 'MINIO_ROOT_PASSWORD=minioadmin',
         '-p', '9012:9000', MINIO_IMAGE, 'server', '/data'])


def stop_infra():
    run(['docker', 'rm', '-f', PG_CONTAINER], check=False, capture=True)
    run(['docker', 'rm', '-f', MINIO_CONTAINER], check=False, capture=True)


def wait_pg(timeout=60):
    import psycopg2
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            psycopg2.connect(**DB).close()
            return True
        except Exception:
            time.sleep(1)
    return False


def s3():
    import boto3
    return boto3.client('s3', endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_KEY_ID,
                        aws_secret_access_key=R2_SECRET, region_name='auto')


def wait_minio(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s3().list_buckets()
            return True
        except Exception:
            time.sleep(1)
    return False


def build_source_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('audio_1.txt', _STOP_NAME + "\n\n" + _RU_NARRATION)
        z.writestr('audio_1.mp3', b'ID3ORIGRU1')
        z.writestr('index.html', '<html><body>original</body></html>')
    return buf.getvalue()


def ensure_bucket():
    client = s3()
    try:
        client.head_bucket(Bucket=R2_BUCKET)
    except Exception:
        client.create_bucket(Bucket=R2_BUCKET)


def seed_russian_tour():
    import psycopg2
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute("SELECT count(*) FROM audio_tours")
    before = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, audio_tour, lat, lng, "
        "content_language, creator_type, stops_count, number_requested) "
        "VALUES (%s, %s, NULL, %s, %s, 'ru', 'AI', %s, 0) RETURNING id",
        ('Rimiez Cemetery (ru)', 'seed-ru-lang1', 43.7066, 7.2831, 1))
    tour_id = cur.fetchone()[0]
    key = f"tours/{tour_id}.zip"
    s3().put_object(Bucket=R2_BUCKET, Key=key, Body=build_source_zip())
    cur.execute("UPDATE audio_tours SET tour_blob_uri = %s WHERE id = %s", (key, tour_id))
    cur.close()
    conn.close()
    print(f"[SETUP] seeded Russian tour id={tour_id} (content_language=ru, blob {key})")
    return tour_id, before


def svc_env(port):
    env = dict(os.environ)
    env.update({
        'TOUR_STORAGE_MODE': 'cloud',
        'BLOB_STORAGE_TYPE': 'r2',
        'R2_ENDPOINT': R2_ENDPOINT,
        'R2_BUCKET': R2_BUCKET,
        'R2_ACCESS_KEY_ID': R2_KEY_ID,
        'R2_SECRET_ACCESS_KEY': R2_SECRET,
        'AWS_ACCESS_KEY_ID': R2_KEY_ID,
        'AWS_SECRET_ACCESS_KEY': R2_SECRET,
        'AWS_DEFAULT_REGION': 'us-east-1',
        'DB_HOST': '127.0.0.1', 'DB_PORT': '5546', 'DB_NAME': 'audiotours',
        'DB_USER': 'admin', 'DB_PASSWORD': 'password123',
        'POLLY_TTS_URL': f'http://127.0.0.1:{POLLY_PORT}',
        'LOCAL_IDENTITY_TOKEN': LOCAL_TOKEN,
        # GCS-LANG1: deterministic language detection, no AWS.
        'LOCAL_LANGUAGE_STUB_URL': f'http://127.0.0.1:{LANG_PORT}/detect',
        'PORT': str(port),
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUNBUFFERED': '1',
    })
    return env


def start_service(port):
    logf = open(os.path.join(HERE, f'gcslang1_svc_{port}.log'), 'w', encoding='utf-8')
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tour_editing_phase2.py')],
                         cwd=ROOT, env=svc_env(port), text=True,
                         stdout=logf, stderr=subprocess.STDOUT)
    p._logf = logf
    return p


def start_stub(script, port, extra_env=None):
    env = dict(os.environ)
    env['PORT'] = str(port)
    env['PYTHONIOENCODING'] = 'utf-8'
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen([sys.executable, os.path.join(HERE, script)],
                            cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def wait_health(port, timeout=30):
    url = f'http://127.0.0.1:{port}/health'
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def http_post_json(port, path, body):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def reset_logs():
    for p in (POLLY_LOG, POLLY_UNAUTH_LOG, LANG_LOG):
        if os.path.exists(p):
            os.remove(p)


def main():
    if not docker_available():
        print("SKIP: docker not available — cannot stand up local Postgres/MinIO.")
        return 3

    fails = 0
    print("== Start local infra (Postgres + MinIO) ==")
    start_infra()
    svc = polly = lang = None
    try:
        if not wait_pg():
            raise SystemExit("Postgres did not become ready on 5546")
        if not wait_minio():
            raise SystemExit("MinIO did not become ready on 9012")
        ensure_bucket()
        reset_logs()
        tour_id, _ = seed_russian_tour()

        polly = start_stub('gcs5e_polly_auth_stub.py', POLLY_PORT,
                           {'POLLY_VOICE_LOG': POLLY_LOG, 'POLLY_UNAUTH_LOG': POLLY_UNAUTH_LOG})
        lang = start_stub('gcslang1_lang_stub.py', LANG_PORT, {'LANG_STUB_LOG': LANG_LOG})
        assert wait_health(POLLY_PORT), "polly stub did not become healthy"
        assert wait_health(LANG_PORT), "language stub did not become healthy"
        svc = start_service(SVC_PORT)
        if not wait_health(SVC_PORT):
            raise SystemExit("editing service did not become healthy (see gcslang1_svc log)")

        def check(name, cond, detail=""):
            nonlocal fails
            if cond:
                print(f"  PASS: {name}")
            else:
                print(f"  FAIL: {name} — {detail}")
                fails += 1

        # ---- A. reported blob: ru narration + Latin header + EN Orientation ----
        body_a = {"stops": [{"stop_number": 1, "text": RED_BLOB, "action": "modify",
                             "generate_audio_from_text": True}]}
        st_a, resp_a = http_post_json(SVC_PORT, f"/tour/{tour_id}/update-multiple-stops", body_a)
        print("\n" + "=" * 64)
        print("[A] reported blob (ru narration + Latin header + EN Orientation)")
        print(f"    HTTP {st_a}")
        print("    " + json.dumps(resp_a, ensure_ascii=False))
        check("A: reported blob ACCEPTED after fix (not 400 LANGUAGE_MISMATCH)",
              st_a == 200 and resp_a.get('error_code') != 'LANGUAGE_MISMATCH',
              f"got {st_a} {resp_a}")

        # ---- B. genuine mismatch: all-English narration on the ru tour ----
        body_b = {"stops": [{"stop_number": 1, "text": ENGLISH_BLOB, "action": "modify",
                             "generate_audio_from_text": True}]}
        st_b, resp_b = http_post_json(SVC_PORT, f"/tour/{tour_id}/update-multiple-stops", body_b)
        print("\n" + "=" * 64)
        print("[B] genuine mismatch (all-English narration on a ru tour)")
        print(f"    HTTP {st_b}")
        print("    " + json.dumps(resp_b, ensure_ascii=False))
        check("B: English narration on ru tour STILL rejected 400 LANGUAGE_MISMATCH",
              st_b == 400 and resp_b.get('error_code') == 'LANGUAGE_MISMATCH'
              and resp_b.get('detected_language') == 'en',
              f"got {st_b} {resp_b}")

    finally:
        for p in (svc, polly, lang):
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass
        stop_infra()

    print("\n" + "=" * 64)
    if fails == 0:
        print("RESULT: PASS — reported blob accepted; real mismatch still rejected.")
        return 0
    print(f"RESULT: FAIL — {fails} check(s) failed.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
