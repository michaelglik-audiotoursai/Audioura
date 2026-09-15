#!/usr/bin/env python3
"""GCS-5R verification harness — by effect against a running editing container.

Cloud-equivalent stand-ins:
  * Postgres  : local container (127.0.0.1:5544)
  * R2        : MinIO S3 API (127.0.0.1:9010), bucket v1-audiotours-r2-bucket
  * Polly     : tests/gcs5r_polly_stub.py, records the requested voice_id

Reproduces Michael's failing tour: "Excursion over Jewish Cemetery", Russian,
R2-migrated (audio_tour = NULL, tour_blob_uri = tours/<id>.zip),
content_language = 'ru'.

Proves:
  B3 RED  : a save that defaults content_language to 'en' (old behaviour, sent
            explicitly here) synthesizes with the ENGLISH voice (Joanna).
  B3 GREEN: a save with NO content_language (exactly what the app sends) makes
            the fixed server read content_language='ru' from the source tour and
            synthesize with the RUSSIAN voice (Tatyana).
  E2E     : save (instance A) -> kill A -> fresh instance B -> download; the
            edited Russian text is present in the ZIP served by B (from R2).
  Safety  : audio_tours row counts before/after; no production row/blob/R2 key.

SAFETY: talks ONLY to local MinIO. Refuses any r2.cloudflarestorage.com endpoint.
Windows-safe: utf-8 everywhere, subprocess(text=True).
"""
import io
import os
import sys
import json
import time
import signal
import zipfile
import subprocess
import urllib.request

import boto3
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# --- Local stand-in config (never production) --------------------------------
R2_ENDPOINT = 'http://127.0.0.1:9010'
R2_BUCKET = 'v1-audiotours-r2-bucket'
R2_KEY_ID = 'minioadmin'
R2_SECRET = 'minioadmin'
if 'r2.cloudflarestorage.com' in os.getenv('R2_ENDPOINT', ''):
    print("[SAFETY] ambient R2_ENDPOINT points at real Cloudflare R2 — ignoring; local MinIO only.")

DB = dict(host='127.0.0.1', port='5544', dbname='audiotours',
          user='admin', password='password123')

SVC_A_PORT = 5123
SVC_B_PORT = 5124
POLLY_PORT = 5599
POLLY_LOG = os.path.join(HERE, 'polly_voice_log.jsonl')

RU_STOP1 = ("Добро пожаловать на еврейское кладбище. Здесь покоятся многие "
            "выдающиеся жители нашего города.")
RU_STOP2 = ("Второй остановка нашей экскурсии посвящена старинным надгробиям "
            "девятнадцатого века.")
RU_EDIT1 = ("ИЗМЕНЕНО: Это новый текст первой остановки на русском языке для "
            "проверки редактирования тура.")

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


def s3():
    return boto3.client('s3', endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_KEY_ID,
                        aws_secret_access_key=R2_SECRET, region_name='auto')


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
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute("SELECT count(*) FROM audio_tours")
    before = cur.fetchone()[0]
    print(f"[SETUP] audio_tours row count BEFORE seed: {before}")

    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, audio_tour, lat, lng, "
        "content_language, creator_type, stops_count, number_requested) "
        "VALUES (%s, %s, NULL, %s, %s, 'ru', 'AI', %s, 0) RETURNING id",
        ('Excursion over Jewish Cemetery', 'seed-ru', 42.36, -71.06, 2))
    tour_id = cur.fetchone()[0]
    key = f"tours/{tour_id}.zip"
    s3().put_object(Bucket=R2_BUCKET, Key=key, Body=build_source_zip())
    cur.execute("UPDATE audio_tours SET tour_blob_uri = %s WHERE id = %s", (key, tour_id))

    cur.execute("SELECT count(*) FROM audio_tours")
    after = cur.fetchone()[0]
    cur.execute("SELECT id, audio_tour IS NULL, content_language, tour_blob_uri "
                "FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    print(f"[SETUP] audio_tours row count AFTER seed: {after}")
    print(f"[SETUP] seeded tour id={row[0]} audio_tour_is_null={row[1]} "
          f"content_language={row[2]!r} tour_blob_uri={row[3]}")
    cur.close()
    conn.close()
    return tour_id, before


def svc_env():
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
        'PYTHONIOENCODING': 'utf-8',
    })
    return env


def start_service(port):
    env = svc_env()
    env['PORT'] = str(port)
    env['PYTHONUNBUFFERED'] = '1'
    logf = open(os.path.join(HERE, f'svc_{port}.log'), 'w', encoding='utf-8')
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tour_editing_phase2.py')],
                         cwd=ROOT, env=env, text=True,
                         stdout=logf, stderr=subprocess.STDOUT)
    p._logf = logf
    return p


def start_polly():
    env = dict(os.environ)
    env['PORT'] = str(POLLY_PORT)
    env['POLLY_VOICE_LOG'] = POLLY_LOG
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.Popen([sys.executable, os.path.join(HERE, 'gcs5r_polly_stub.py')],
                            cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def wait_health(port, timeout=25):
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


def read_voices():
    voices = []
    if os.path.exists(POLLY_LOG):
        with open(POLLY_LOG, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    voices.append(json.loads(line))
    return voices


def reset_voice_log():
    if os.path.exists(POLLY_LOG):
        os.remove(POLLY_LOG)


def audio_tours_count():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM audio_tours")
    n = cur.fetchone()[0]
    cur.close(); conn.close()
    return n


def tour_edit_blobs_count():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM tour_edit_blobs")
        n = cur.fetchone()[0]
    except Exception:
        n = 0
    cur.close(); conn.close()
    return n


def main():
    fails = 0
    ensure_bucket()
    reset_voice_log()
    tour_id, rows_before = seed_russian_tour()
    edit_blobs_before = tour_edit_blobs_count()

    polly = start_polly()
    svc_a = start_service(SVC_A_PORT)
    try:
        assert wait_health(POLLY_PORT), "polly stub did not become healthy"
        if not wait_health(SVC_A_PORT):
            print(svc_a.stdout.read() if svc_a.stdout else '')
            raise SystemExit("editing service A did not become healthy")

        # ---- B3 RED: explicit content_language='en' (== old default) -> English voice
        reset_voice_log()
        red_body = {"content_language": "en", "stops": [
            {"stop_number": 1, "text": RU_EDIT1, "action": "modify",
             "generate_audio_from_text": True}]}
        st, resp = http_post_json(SVC_A_PORT, f"/tour/{tour_id}/update-multiple-stops", red_body)
        red_voices = [v['voice_id'] for v in read_voices()]
        print(f"\n[B3 RED] status={st} voices={red_voices}")
        red_ok = ('Joanna' in red_voices) and ('Tatyana' not in red_voices)
        print(f"[B3 RED] English default -> Joanna (wrong voice for Russian): {red_ok}")
        fails += 0 if red_ok else 1

        # ---- B3 GREEN: NO content_language (what the app sends) -> Russian voice
        reset_voice_log()
        green_body = {"stops": [
            {"stop_number": 1, "text": RU_EDIT1, "action": "modify",
             "generate_audio_from_text": True}]}
        st, resp = http_post_json(SVC_A_PORT, f"/tour/{tour_id}/update-multiple-stops", green_body)
        green_voices = [v['voice_id'] for v in read_voices()]
        print(f"\n[B3 GREEN] status={st} new_tour_id={resp.get('new_tour_id')} voices={green_voices}")
        green_ok = ('Tatyana' in green_voices) and ('Joanna' not in green_voices)
        print(f"[B3 GREEN] source content_language='ru' -> Tatyana (Russian voice): {green_ok}")
        fails += 0 if green_ok else 1

        new_tour_id = resp.get('new_tour_id')
        if not new_tour_id:
            raise SystemExit(f"GREEN save did not return new_tour_id: {resp}")

        # ---- E2E: kill A, start fresh B, download from B (served from R2) ----
        svc_a.terminate()
        try:
            svc_a.wait(timeout=10)
        except Exception:
            svc_a.kill()
        print("\n[E2E] instance A killed; starting fresh instance B")
        svc_b = start_service(SVC_B_PORT)
        try:
            if not wait_health(SVC_B_PORT):
                print(svc_b.stdout.read() if svc_b.stdout else '')
                raise SystemExit("editing service B did not become healthy")
            st, blob = http_get_bytes(SVC_B_PORT, f"/tour/{new_tour_id}/download")
            print(f"[E2E] download from fresh instance B: status={st} size={len(blob)}")
            contains_edit = False
            names = []
            if st == 200:
                zf = zipfile.ZipFile(io.BytesIO(blob), 'r')
                names = zf.namelist()
                try:
                    audio1 = zf.read('audio_1.txt').decode('utf-8', 'replace')
                except KeyError:
                    audio1 = ''
                contains_edit = 'ИЗМЕНЕНО' in audio1
                print(f"[E2E] ZIP files: {names}")
                print(f"[E2E] audio_1.txt prefix: {audio1[:60]!r}")
            e2e_ok = (st == 200) and contains_edit
            print(f"[E2E] fresh instance served edited Russian text from R2: {e2e_ok}")
            fails += 0 if e2e_ok else 1
        finally:
            svc_b.terminate()
            try:
                svc_b.wait(timeout=10)
            except Exception:
                svc_b.kill()
    finally:
        for p in (svc_a, polly):
            try:
                p.terminate()
            except Exception:
                pass

    # ---- Safety: row counts before/after ----
    rows_after = audio_tours_count()
    edit_blobs_after = tour_edit_blobs_count()
    print(f"\n[SAFETY] audio_tours rows: before={rows_before} after={rows_after} "
          f"(delta={rows_after - rows_before}; expected 1 seeded, 0 from edits)")
    print(f"[SAFETY] tour_edit_blobs rows: before={edit_blobs_before} after={edit_blobs_after}")
    # audio_tours must only grow by the 1 seed row (edits never touch audio_tours)
    fails += 0 if (rows_after - rows_before) == 1 else 1

    print("\n" + "=" * 64)
    if fails == 0:
        print("RESULT: PASS — B3 red->green + E2E save/kill/fresh-download verified.")
        return 0
    print(f"RESULT: FAIL — {fails} check(s) failed.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
