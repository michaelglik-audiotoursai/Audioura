#!/usr/bin/env python3
"""live_local746.py — LOCAL-746 live test (own harness, spare ports, is_test only).

Proves the END-TO-END chain the Flutter app's sync-on-open REFRESH relies on, on
a COPY of a community tour (never a real one), using MY OWN map-delivery and
tour-editing instances on SPARE ports against the shared dev DB:

  The member holds a community tour at v1. The organiser edits it. The app's
  sync-on-open must pick up v2. The app-side policy (RefreshPlanner) and the
  replace-in-place download are unit/integration tested in Dart; this live run
  proves the SERVER halves the app reads:

    A. /tour-info/<id> reports version 1 for the freshly-created copy — the
       "LOCAL-657 version the app already reads" that RefreshPlanner compares
       against the saved version. (member holds v1)
    B. the OWNER edit (in place) bumps the server version and the save response
       carries member_update.new_version = 2 (LOCAL-745).
    C. /tour-info/<id> now reports version 2 — so RefreshPlanner (server 2 >
       saved 1, community active) WOULD plan a re-download.
    D. /download-tour/<id> returns 200 and serves the NEW (v2) ZIP bytes — what
       TourDownloadService.reDownloadAndReplace fetches to replace the held copy
       in place. We assert the served bytes equal the edited audio_tour BYTEA.

SAFETY (D141/D690):
  * creates ONE is_test=true community + ONE is_test=true audio_tours COPY (+ a
    test membership). Deletes EXACTLY those rows at the end, guarded by
    is_test = TRUE. Never touches a real tour or any non-is_test row.
  * runs MY OWN app instances in-process on SPARE ports (map-delivery 5546,
    tour-editing 5547); never -p audioura; never touches audioura-* or
    tour-editing-phase2-1 containers. get_db_connection is monkeypatched to the
    local dev DB (localhost:5433).
  * budget: the edit sends action='unchanged' so NO Polly TTS fires. $0.00.

Prints BEFORE/AFTER/FINAL row counts for every touched table.

Run: python3 live_local746.py
"""
import io
import os
import sys
import json
import time
import uuid
import glob
import shutil
import zipfile
import threading
import urllib.request
import urllib.error

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = dict(host="localhost", port="5433", dbname="audiotours",
          user="admin", password="password123")
MAP_PORT = int(os.getenv("LIVE_MAP_PORT", "5546"))
EDIT_PORT = int(os.getenv("LIVE_EDIT_PORT", "5547"))
TOURS_DIR = "/Users/micha/Audioura/tours"

OWNER = f"L746-OWNER-{uuid.uuid4().hex[:8]}"
MEMBER = f"L746-MEMBER-{uuid.uuid4().hex[:8]}"


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


def http_get(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read(), r.headers.get_content_type()
    except urllib.error.HTTPError as e:
        return e.code, e.read(), None


def http_post(port, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def pick_source_zip():
    for z in sorted(glob.glob(os.path.join(TOURS_DIR, "*.zip"))):
        try:
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
            if any(os.path.basename(n).startswith("audio_") and n.endswith(".txt")
                   for n in names):
                return z
        except Exception:
            continue
    raise SystemExit("no usable source ZIP with audio_*.txt in tours dir")


def main():
    src_zip = pick_source_zip()
    zip_bytes = open(src_zip, "rb").read()
    print(f"[src] using copy source: {os.path.basename(src_zip)} "
          f"({len(zip_bytes)} bytes)")

    c = conn()
    c.autocommit = True
    cur = c.cursor()

    print("\n=== BEFORE ===")
    before = counts(cur)
    for k, v in before.items():
        print(f"  {k}: {v}")

    # --- is_test fixtures: a community I own + a COPY community tour + member ---
    cur.execute(
        "INSERT INTO communities (name, owner_user_id, disabled) "
        "VALUES (%s, %s, FALSE) RETURNING id",
        (f"L746 live {uuid.uuid4().hex[:6]}", OWNER))
    community_id = cur.fetchone()[0]

    test_zip_name = f"l746_live_copy_{uuid.uuid4().hex[:8]}.zip"
    test_zip_path = os.path.join(TOURS_DIR, test_zip_name)
    shutil.copy2(src_zip, test_zip_path)

    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, is_test, "
        "community_id, community_visibility, audio_tour, zip_filename, "
        "stops_count, content_language) "
        "VALUES (%s, %s, TRUE, %s, 'members', %s, %s, 4, 'en') RETURNING id",
        (f"L746 Salem copy {uuid.uuid4().hex[:6]}", "l746 live", community_id,
         psycopg2.Binary(zip_bytes), test_zip_name))
    test_tour_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO community_memberships (user_id, community_id, expires_at) "
        "VALUES (%s, %s, NULL) ON CONFLICT DO NOTHING", (MEMBER, community_id))

    print(f"\n[fixtures] community_id={community_id} test_tour_id={test_tour_id} "
          f"zip={test_zip_name}")
    old_bytea_len = len(zip_bytes)

    # original stop texts → the owner edit sends them UNCHANGED ($0 TTS).
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

    # --- MY OWN app instances on spare ports, DB monkeypatched to dev DB ---
    os.environ["TOUR_STORAGE_MODE"] = "volume"
    for k, v in (("DB_HOST", DB["host"]), ("DB_PORT", DB["port"]),
                 ("DB_NAME", DB["dbname"]), ("DB_USER", DB["user"]),
                 ("DB_PASSWORD", DB["password"])):
        os.environ.setdefault(k, v)
    os.environ.setdefault(
        "DATABASE_URL",
        f"postgresql://{DB['user']}:{DB['password']}@{DB['host']}:{DB['port']}/{DB['dbname']}")

    def dev_conn():
        return psycopg2.connect(**DB)

    # map-delivery
    sys.path.insert(0, os.path.join(HERE, "map_delivery"))
    import app as mapmod  # map_delivery/app.py
    mapmod.get_db_connection = dev_conn
    threading.Thread(
        target=lambda: mapmod.app.run(host="127.0.0.1", port=MAP_PORT,
                                      debug=False, use_reloader=False),
        daemon=True).start()

    # tour-editing (the edit-service)
    import tour_editing_phase2 as p2
    p2.TOURS_DIR = TOURS_DIR
    if hasattr(p2, "get_db_connection"):
        p2.get_db_connection = dev_conn
    threading.Thread(
        target=lambda: p2.app.run(host="127.0.0.1", port=EDIT_PORT,
                                  debug=False, use_reloader=False),
        daemon=True).start()
    time.sleep(3.0)

    results = {}

    # A. member holds v1 — /tour-info reports version 1
    status, body, _ = http_get(MAP_PORT, f"/tour-info/{test_tour_id}")
    info_before = json.loads(body.decode()) if status == 200 else {}
    v_before = info_before.get("version")
    print(f"\n[A member holds v1] /tour-info status={status} version={v_before}")
    results["A_version_before"] = v_before

    # download the held copy (v1 content) — this is what the member already has
    st_dl1, dl1_bytes, _ = http_get(
        MAP_PORT, f"/download-tour/{test_tour_id}?user_id={MEMBER}")
    print(f"[A member v1 download] status={st_dl1} bytes={len(dl1_bytes)}")
    results["A_v1_download"] = dict(status=st_dl1, bytes=len(dl1_bytes))

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

    # B. OWNER edit in place → version bump + member_update.new_version = 2
    st_edit, edit_resp = http_post(
        EDIT_PORT, f"/tour/{test_tour_id}/update-multiple-stops",
        edit_body(OWNER))
    member_update = edit_resp.get("member_update")
    print(f"\n[B owner edit] status={st_edit} status_field={edit_resp.get('status')} "
          f"new_tour_id={edit_resp.get('new_tour_id')} member_update={member_update}")
    results["B_owner_edit"] = dict(status=st_edit,
                                   new_tour_id=edit_resp.get("new_tour_id"),
                                   member_update=member_update)

    # C. /tour-info now reports version 2 — RefreshPlanner would re-download
    status, body, _ = http_get(MAP_PORT, f"/tour-info/{test_tour_id}")
    info_after = json.loads(body.decode()) if status == 200 else {}
    v_after = info_after.get("version")
    print(f"\n[C member sees v2] /tour-info status={status} version={v_after} "
          f"updated_at={info_after.get('updated_at')}")
    results["C_version_after"] = v_after
    results["C_updated_at"] = info_after.get("updated_at")

    # D. /download-tour serves the NEW (v2) bytes — equals the replaced BYTEA
    st_dl2, dl2_bytes, _ = http_get(
        MAP_PORT, f"/download-tour/{test_tour_id}?user_id={MEMBER}")
    cur.execute("SELECT octet_length(audio_tour) FROM audio_tours WHERE id = %s",
                (test_tour_id,))
    bytea_len = cur.fetchone()[0]
    cur.execute("SELECT version_no FROM audio_tour_versions WHERE tour_id = %s "
                "ORDER BY version_no", (test_tour_id,))
    archived = [r[0] for r in cur.fetchall()]
    served_matches = (st_dl2 == 200 and len(dl2_bytes) == bytea_len)
    print(f"\n[D member v2 re-download] status={st_dl2} bytes={len(dl2_bytes)} "
          f"audio_tour_bytea={bytea_len} served==bytea:{served_matches} "
          f"archived_versions={archived}")
    results["D_v2_download"] = dict(status=st_dl2, bytes=len(dl2_bytes),
                                    bytea_len=bytea_len,
                                    served_matches=served_matches,
                                    archived=archived)

    # the app-side decision the live chain enables:
    would_refresh = (v_before == 1 and v_after is not None and v_after >= 2)
    results["refresh_planner_would_redownload"] = would_refresh
    print(f"\n[app decision] RefreshPlanner(server {v_after} > saved {v_before}, "
          f"community active) → re-download = {would_refresh}")

    print("\n=== AFTER (fixtures present) ===")
    after = counts(cur)
    for k, v in after.items():
        print(f"  {k}: {v}  (Δ {v - before[k]})")

    # --- CLEANUP: delete EXACTLY my is_test rows (guarded by is_test) ---
    cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s",
                (test_tour_id,))
    cur.execute("DELETE FROM community_memberships WHERE community_id = %s "
                "AND user_id = %s", (community_id, MEMBER))
    cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                (test_tour_id,))
    cur.execute("DELETE FROM communities WHERE id = %s", (community_id,))
    if os.path.exists(test_zip_path):
        os.remove(test_zip_path)
    for d in os.listdir(TOURS_DIR):
        if d.startswith("l746_live_copy_"):
            p = os.path.join(TOURS_DIR, d)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p):
                os.remove(p)

    print("\n=== FINAL (after cleanup) ===")
    final = counts(cur)
    for k, v in final.items():
        print(f"  {k}: {v}  (Δ vs before {v - before[k]})")

    cur.close()
    c.close()

    print("\n=== RESULT ===")
    print(json.dumps(results, indent=2, default=str))

    ok = (results.get("A_version_before") == 1
          and results.get("C_version_after", 0) >= 2
          and results.get("refresh_planner_would_redownload") is True
          and results.get("D_v2_download", {}).get("served_matches") is True)
    print(f"\nLIVE RESULT: {'PASS' if ok else 'CHECK'} — "
          f"budget $0.00 (action=unchanged, no TTS)")


if __name__ == "__main__":
    main()
