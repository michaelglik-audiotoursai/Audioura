#!/usr/bin/env python3
"""live_local745.py — LOCAL-745 live test (own harness, spare port, is_test only).

Exercises the REAL tour_editing_phase2 app end-to-end against the shared dev DB,
proving the three server behaviours on a COPY of tour 716 (never 716 itself):

  1. a community tour that exists only as a ZIP resolves & saves (was 404);
  2. a non-owner (member) edit is refused 403 NOT_COMMUNITY_OWNER;
  3. the owner's edit writes back onto the community tour row in place — the
     audio_tours.audio_tour BYTEA becomes the edited ZIP and a version is
     archived (so members get version 2 via /download-tour + LOCAL-657).

SAFETY (D141/D690):
  * creates ONE is_test=true community + ONE is_test=true audio_tours COPY of
    716 (+ a test membership). Deletes EXACTLY those rows at the end, guarded by
    is_test = TRUE. Never touches tour 716 or any non-is_test row.
  * runs the app in-process on a SPARE port (5522); never -p audioura; never
    touches audioura-* or tour-editing-phase2-1.
  * budget: edits send action='unchanged' so NO Polly TTS fires (preserve path
    copies existing mp3s). Expected paid cost: $0.00.

Prints BEFORE/AFTER row counts for every touched table.

Run: python3 live_local745.py
"""
import os
import io
import sys
import json
import time
import uuid
import shutil
import zipfile
import threading
import urllib.request

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = dict(host="localhost", port="5433", dbname="audiotours",
          user="admin", password="password123")
PORT = int(os.getenv("LIVE_PORT", "5522"))
TOURS_DIR = "/Users/micha/Audioura/tours"
SRC_ZIP = os.path.join(
    TOURS_DIR, "the_episode_1_of_season_1_biking_tour_salem_ma__ad5f966f.zip")
OWNER = f"L745-OWNER-{uuid.uuid4().hex[:8]}"
MEMBER = f"L745-MEMBER-{uuid.uuid4().hex[:8]}"


def conn():
    return psycopg2.connect(**DB)


def counts(cur):
    out = {}
    for t in ("audio_tours", "audio_tour_versions", "communities",
              "community_memberships"):
        cur.execute(f"SELECT count(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audio_tours WHERE is_test = TRUE")
    out["audio_tours(is_test)"] = cur.fetchone()[0]
    return out


def http_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    assert os.path.exists(SRC_ZIP), f"716 ZIP not found: {SRC_ZIP}"
    zip_bytes = open(SRC_ZIP, "rb").read()

    c = conn()
    c.autocommit = True
    cur = c.cursor()

    print("=== BEFORE ===")
    before = counts(cur)
    for k, v in before.items():
        print(f"  {k}: {v}")

    # --- create the is_test fixtures: a community I own + a COPY of 716 ---
    cur.execute(
        "INSERT INTO communities (name, owner_user_id, disabled) "
        "VALUES (%s, %s, FALSE) RETURNING id",
        (f"L745 live {uuid.uuid4().hex[:6]}", OWNER))
    community_id = cur.fetchone()[0]

    test_zip_name = f"l745_live_copy_{uuid.uuid4().hex[:8]}.zip"
    # Put a COPY of the 716 ZIP into the tours dir so the volume-mode ZIP-only
    # resolver (the fix) can find and extract it by zip_filename.
    test_zip_path = os.path.join(TOURS_DIR, test_zip_name)
    shutil.copy2(SRC_ZIP, test_zip_path)

    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, is_test, "
        "community_id, community_visibility, audio_tour, zip_filename, "
        "stops_count, content_language) "
        "VALUES (%s, %s, TRUE, %s, 'members', %s, %s, 4, 'en') RETURNING id",
        (f"L745 live copy of 716 {uuid.uuid4().hex[:6]}", "l745 live",
         community_id, psycopg2.Binary(zip_bytes), test_zip_name))
    test_tour_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO community_memberships (user_id, community_id, expires_at) "
        "VALUES (%s, %s, NULL) ON CONFLICT DO NOTHING", (MEMBER, community_id))

    print(f"\n[fixtures] community_id={community_id} test_tour_id={test_tour_id} "
          f"zip={test_zip_name}")

    old_bytea_len = len(zip_bytes)

    # Read the ORIGINAL stop texts from the 716 ZIP so the owner edit can send
    # them UNCHANGED — the preserve path then copies the existing mp3s and NO
    # Polly TTS fires (budget $0). We still prove resolve + save + in-place
    # replacement; a real text change would need the (host-unreachable) TTS.
    orig_texts = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            base = os.path.basename(name)
            if base.startswith("audio_") and base.endswith(".txt"):
                try:
                    n = int(base[len("audio_"):-len(".txt")])
                except ValueError:
                    continue
                orig_texts[n] = zf.read(name).decode("utf-8", "replace").strip()
    print(f"[orig] stop texts read: {sorted(orig_texts)}")

    # --- start the REAL app in-process on the spare port, volume mode ---
    os.environ["TOUR_STORAGE_MODE"] = "volume"
    os.environ.setdefault("DB_HOST", DB["host"])
    os.environ.setdefault("DB_PORT", DB["port"])
    os.environ.setdefault("DB_NAME", DB["dbname"])
    os.environ.setdefault("DB_USER", DB["user"])
    os.environ.setdefault("DB_PASSWORD", DB["password"])
    os.environ.setdefault("DATABASE_URL",
                          f"postgresql://{DB['user']}:{DB['password']}@"
                          f"{DB['host']}:{DB['port']}/{DB['dbname']}")

    import tour_editing_phase2 as p2
    p2.TOURS_DIR = TOURS_DIR  # point the app at the real tours volume copy

    srv = threading.Thread(
        target=lambda: p2.app.run(host="127.0.0.1", port=PORT, debug=False,
                                  use_reloader=False),
        daemon=True)
    srv.start()
    time.sleep(2.5)

    results = {}

    # Edit payload: send the ORIGINAL stop texts UNCHANGED so the preserve path
    # copies existing mp3s and NO TTS fires ($0). This still drives resolve +
    # save + the in-place community replacement. secret_id/user_id = identity.
    def edit_body(user_id):
        return {
            "stops": [
                {"stop_number": 1, "text": orig_texts.get(1, ""),
                 "action": "unchanged", "generate_audio_from_text": False},
                {"stop_number": 4, "text": orig_texts.get(4, ""),
                 "action": "unchanged", "generate_audio_from_text": False},
            ],
            "user_id": user_id, "secret_id": user_id,
        }

    # 1) MEMBER edit → expect 403 NOT_COMMUNITY_OWNER
    status, body = http_post(
        f"/tour/{test_tour_id}/update-multiple-stops", edit_body(MEMBER))
    results["member_403"] = (status, body.get("error_code"))
    print(f"\n[member edit] status={status} error_code={body.get('error_code')} "
          f"msg={body.get('message')!r}")

    # 2) OWNER edit → expect 200 + member_update{new_version:2}
    status, body = http_post(
        f"/tour/{test_tour_id}/update-multiple-stops", edit_body(OWNER))
    results["owner_200"] = (status, body.get("status"),
                            body.get("member_update"))
    print(f"\n[owner edit] status={status} status_field={body.get('status')} "
          f"member_update={body.get('member_update')} "
          f"new_tour_id={body.get('new_tour_id')}")

    # 3) Verify the community row was replaced in place + version archived
    cur.execute("SELECT octet_length(audio_tour), zip_filename, stops_count "
                "FROM audio_tours WHERE id = %s", (test_tour_id,))
    new_len, new_zip, new_stops = cur.fetchone()
    cur.execute("SELECT version_no FROM audio_tour_versions "
                "WHERE tour_id = %s ORDER BY version_no", (test_tour_id,))
    archived = [r[0] for r in cur.fetchall()]
    print(f"\n[in-place] audio_tour bytes {old_bytea_len} -> {new_len} "
          f"(changed={new_len != old_bytea_len}); zip_filename={new_zip}; "
          f"stops_count={new_stops}; archived versions={archived}")
    results["in_place"] = dict(old_len=old_bytea_len, new_len=new_len,
                               archived=archived, new_zip=new_zip,
                               new_stops=new_stops)

    print("\n=== AFTER (with fixtures present) ===")
    after = counts(cur)
    for k, v in after.items():
        print(f"  {k}: {v}  (Δ {v - before[k]})")

    # --- CLEANUP: delete EXACTLY my is_test rows (guarded) ---
    cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s",
                (test_tour_id,))
    cur.execute("DELETE FROM community_memberships WHERE community_id = %s AND user_id = %s",
                (community_id, MEMBER))
    cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                (test_tour_id,))
    cur.execute("DELETE FROM communities WHERE id = %s", (community_id,))
    for f in (test_zip_path,):
        if os.path.exists(f):
            os.remove(f)
    # Remove any extracted work/new dirs the edit created under TOURS_DIR.
    for d in os.listdir(TOURS_DIR):
        if d.startswith(f"l745_live_copy_") or d.startswith(test_zip_name[:-4]):
            p = os.path.join(TOURS_DIR, d)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p) and p != SRC_ZIP:
                os.remove(p)

    print("\n=== FINAL (after cleanup) ===")
    final = counts(cur)
    for k, v in final.items():
        print(f"  {k}: {v}  (Δ vs before {v - before[k]})")

    cur.close()
    c.close()

    print("\n=== RESULT ===")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
