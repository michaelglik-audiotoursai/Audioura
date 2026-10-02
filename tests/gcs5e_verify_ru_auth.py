#!/usr/bin/env python3
"""GCS-5E end-to-end verification — Russian tour, authenticated Polly, by effect.

Stands up its OWN local cloud-equivalent stack (never production):
  * Postgres  : docker container on 127.0.0.1:5544
  * R2        : MinIO S3 API on 127.0.0.1:9010, bucket v1-audiotours-r2-bucket
  * Polly     : tests/gcs5e_polly_auth_stub.py — REQUIRES Authorization: Bearer
                <token> (403 otherwise) and records the requested voice_id
  * Identity  : LOCAL_IDENTITY_TOKEN (test-only seam in tour_editing_phase2) so
                the service attaches a token to the http stub, exercising the
                real _authenticated_request path end to end.

Proves (GCS-5E acceptance #1 green + #3):
  * A Russian edit save -> HTTP 200 and the persisted ZIP has audio_1.mp3 > 0
    for the edited stop (the bug: it was MISSING).
  * That MP3 was requested with the RUSSIAN voice (Tatyana), not Joanna.
  * The Polly stub logged ZERO unauthenticated (403) /synthesize hits during the
    save — i.e. the service authenticated every call.
  * E2E durability: save on instance A -> kill A -> fresh instance B -> download
    serves the edited Russian ZIP from R2.
  * Safety: audio_tours grows only by the seeded row; edits never touch it.

SAFETY: talks ONLY to local MinIO/Postgres. Hard-refuses a real
r2.cloudflarestorage.com endpoint. Never issues DELETE FROM audio_tours.
Windows-safe: utf-8 everywhere, subprocess(text=True).

Usage:  python tests/gcs5e_verify_ru_auth.py
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

# --- Local stand-in config (never production) --------------------------------
R2_ENDPOINT = 'http://127.0.0.1:9010'
R2_BUCKET = 'v1-audiotours-r2-bucket'
R2_KEY_ID = 'minioadmin'
R2_SECRET = 'minioadmin'
DB = dict(host='127.0.0.1', port='5544', dbname='audiotours',
          user='admin', password='password123')

PG_CONTAINER = 'gcs5e-pg'
MINIO_CONTAINER = 'gcs5e-minio'
PG_IMAGE = 'postgres:15-alpine'
MINIO_IMAGE = 'quay.io/minio/minio:latest'

SVC_A_PORT = 5133
SVC_B_PORT = 5134
POLLY_PORT = 5598
POLLY_LOG = os.path.join(HERE, 'gcs5e_polly_voice_log.jsonl')
POLLY_UNAUTH_LOG = os.path.join(HERE, 'gcs5e_polly_unauth_log.jsonl')
LOCAL_TOKEN = 'gcs5e-local-identity-token'

if 'r2.cloudflarestorage.com' in os.getenv('R2_ENDPOINT', ''):
    print("[SAFETY] ambient R2_ENDPOINT points at real Cloudflare R2 — ignoring; "
          "this harness only ever talks to local MinIO at " + R2_ENDPOINT)
# Force the local endpoint for THIS process (seeding/verification) regardless of
# ambient env, and hard-refuse if anything later flips it to real R2.
os.environ['R2_ENDPOINT'] = R2_ENDPOINT
assert 'r2.cloudflarestorage.com' not in R2_ENDPOINT, "refusing a real R2 endpoint"

RU_STOP1 = ("Добро пожаловать на еврейское кладбище. Здесь покоятся многие "
            "выдающиеся жители нашего города.")
RU_STOP2 = ("Вторая остановка нашей экскурсии посвящена старинным надгробиям "
            "девятнадцатого века.")
RU_EDIT1 = ("ИЗМЕНЕНО: Это новый текст первой остановки на русском языке для "
            "проверки редактирования тура с аутентификацией.")

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
         '-e', 'POSTGRES_DB=audiotours', '-p', '5544:5432', PG_IMAGE])
    run(['docker', 'run', '-d', '--name', MINIO_CONTAINER,
         '-e', 'MINIO_ROOT_USER=minioadmin', '-e', 'MINIO_ROOT_PASSWORD=minioadmin',
         '-p', '9010:9000', MINIO_IMAGE, 'server', '/data'])


def stop_infra():
    run(['docker', 'rm', '-f', PG_CONTAINER], check=False, capture=True)
    run(['docker', 'rm', '-f', MINIO_CONTAINER], check=False, capture=True)


def wait_pg(timeout=60):
    import psycopg2
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(**DB)
            conn.close()
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
        z.writestr('audio_1.txt', RU_STOP1)
        z.writestr('audio_1.mp3', b'ID3ORIGRU1')
        z.writestr('audio_2.txt', RU_STOP2)
        z.writestr('audio_2.mp3', b'ID3ORIGRU2')
        z.writestr('index.html', '<html><body>оригинал</body></html>')
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
        ('Excursion over Jewish Cemetery', 'seed-ru', 42.36, -71.06, 2))
    tour_id = cur.fetchone()[0]
    key = f"tours/{tour_id}.zip"
    s3().put_object(Bucket=R2_BUCKET, Key=key, Body=build_source_zip())
    cur.execute("UPDATE audio_tours SET tour_blob_uri = %s WHERE id = %s", (key, tour_id))
    cur.close()
    conn.close()
    print(f"[SETUP] seeded Russian tour id={tour_id} (audio_tour NULL, blob {key})")
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
        'DB_HOST': '127.0.0.1', 'DB_PORT': '5544', 'DB_NAME': 'audiotours',
        'DB_USER': 'admin', 'DB_PASSWORD': 'password123',
        'POLLY_TTS_URL': f'http://127.0.0.1:{POLLY_PORT}',
        'LOCAL_IDENTITY_TOKEN': LOCAL_TOKEN,  # test-only seam: attach a token
        'PORT': str(port),
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUNBUFFERED': '1',
    })
    return env


def start_service(port):
    logf = open(os.path.join(HERE, f'gcs5e_svc_{port}.log'), 'w', encoding='utf-8')
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tour_editing_phase2.py')],
                         cwd=ROOT, env=svc_env(port), text=True,
                         stdout=logf, stderr=subprocess.STDOUT)
    p._logf = logf
    return p


def start_polly():
    env = dict(os.environ)
    env['PORT'] = str(POLLY_PORT)
    env['POLLY_VOICE_LOG'] = POLLY_LOG
    env['POLLY_UNAUTH_LOG'] = POLLY_UNAUTH_LOG
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.Popen([sys.executable, os.path.join(HERE, 'gcs5e_polly_auth_stub.py')],
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
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def http_get_bytes(port, path):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method='GET')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def reset_logs():
    for p in (POLLY_LOG, POLLY_UNAUTH_LOG):
        if os.path.exists(p):
            os.remove(p)


def audio_tours_count():
    import psycopg2
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM audio_tours")
    n = cur.fetchone()[0]
    cur.close(); conn.close()
    return n


def main():
    if not docker_available():
        print("SKIP: docker not available — cannot stand up local Postgres/MinIO.")
        return 3

    fails = 0
    print("== Start local infra (Postgres + MinIO) ==")
    start_infra()
    svc_a = polly = None
    try:
        if not wait_pg():
            raise SystemExit("Postgres did not become ready on 5544")
        if not wait_minio():
            raise SystemExit("MinIO did not become ready on 9010")
        ensure_bucket()
        reset_logs()
        tour_id, rows_before = seed_russian_tour()

        polly = start_polly()
        assert wait_health(POLLY_PORT), "polly auth stub did not become healthy"
        svc_a = start_service(SVC_A_PORT)
        if not wait_health(SVC_A_PORT):
            raise SystemExit("editing service A did not become healthy (see gcs5e_svc log)")

        # ---- Russian edit save (NO content_language: server reads 'ru' from tour)
        body = {"stops": [
            {"stop_number": 1, "text": RU_EDIT1, "action": "modify",
             "generate_audio_from_text": True}]}
        st, resp = http_post_json(SVC_A_PORT, f"/tour/{tour_id}/update-multiple-stops", body)
        print(f"\n[SAVE] status={st} new_tour_id={resp.get('new_tour_id')} msg={resp.get('message')!r}")

        voices = [v['voice_id'] for v in read_jsonl(POLLY_LOG)]
        unauth = read_jsonl(POLLY_UNAUTH_LOG)
        print(f"[SAVE] polly voices requested={voices}  unauth_403_hits={len(unauth)}")

        def check(name, cond, detail=""):
            nonlocal fails
            if cond:
                print(f"  PASS: {name}")
            else:
                print(f"  FAIL: {name} — {detail}")
                fails += 1

        check("save returned 200", st == 200, f"got {st} {resp}")
        check("save authenticated every Polly call (0 unauthenticated 403s)",
              len(unauth) == 0, f"{len(unauth)} unauthenticated hits")
        check("edited stop synthesised with Russian voice Tatyana (not Joanna)",
              'Tatyana' in voices and 'Joanna' not in voices, f"voices={voices}")

        new_tour_id = resp.get('new_tour_id')
        if not new_tour_id:
            raise SystemExit(f"save did not return new_tour_id: {resp}")

        # ---- E2E: kill A, fresh B, download from R2 ----
        svc_a.terminate()
        try:
            svc_a.wait(timeout=10)
        except Exception:
            svc_a.kill()
        print("\n[E2E] instance A killed; starting fresh instance B")
        svc_b = start_service(SVC_B_PORT)
        try:
            if not wait_health(SVC_B_PORT):
                raise SystemExit("editing service B did not become healthy")
            st, blob = http_get_bytes(SVC_B_PORT, f"/tour/{new_tour_id}/download")
            print(f"[E2E] download from fresh B: status={st} size={len(blob)}")
            names, audio1_txt, mp3_size = [], '', -1
            if st == 200:
                zf = zipfile.ZipFile(io.BytesIO(blob), 'r')
                names = zf.namelist()
                if 'audio_1.txt' in names:
                    audio1_txt = zf.read('audio_1.txt').decode('utf-8', 'replace')
                if 'audio_1.mp3' in names:
                    mp3_size = zf.getinfo('audio_1.mp3').file_size
                print(f"[E2E] ZIP files: {names}")
                print(f"[E2E] audio_1.txt prefix: {audio1_txt[:60]!r}  audio_1.mp3 size={mp3_size}")
            check("fresh instance served the edited ZIP (200)", st == 200, f"got {st}")
            check("edited stop audio_1.mp3 present and > 0 bytes",
                  mp3_size > 0, f"mp3_size={mp3_size} names={names}")
            check("edited Russian text present in served ZIP",
                  'ИЗМЕНЕНО' in audio1_txt, f"audio_1.txt={audio1_txt[:60]!r}")
        finally:
            svc_b.terminate()
            try:
                svc_b.wait(timeout=10)
            except Exception:
                svc_b.kill()

        rows_after = audio_tours_count()
        print(f"\n[SAFETY] audio_tours rows before={rows_before} after={rows_after} "
              f"(delta={rows_after - rows_before}; expect 1 seed, 0 from edits)")
        check("audio_tours grew only by the seed row (edits never touch it)",
              (rows_after - rows_before) == 1, f"delta={rows_after - rows_before}")

    finally:
        for p in (svc_a, polly):
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass
        stop_infra()

    print("\n" + "=" * 64)
    if fails == 0:
        print("RESULT: PASS — authenticated Polly, Russian MP3 present, E2E from R2.")
        return 0
    print(f"RESULT: FAIL — {fails} check(s) failed.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
