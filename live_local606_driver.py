#!/usr/bin/env python3
"""live_local606_driver.py — in-container live proof of LOCAL-606 (D622).

Runs INSIDE my own local606-orch container, pointed at the real audiotours DB.
It exercises the exact replaced code path (tour_orchestrator_service.store_audio_tour)
twice for a FRESH is_test tour (lat/lng NULL): first stores it, then regenerates
with DIFFERENT text and a DIFFERENT stop count. It then prints the archived
version row and the replaced live content.

No LLM/TTS is called — the two tour texts are supplied directly — so the run
costs ~$0 (well under the $1 cap). It only ever creates ONE new is_test row
(id > 400, never a Michael id ≤ 400) and never deletes anything.
"""
import os
import sys
import uuid
import zipfile

import tour_orchestrator_service as orch
import psycopg2


def _conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        dbname=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
    )


def _make_zip(path, payload):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


def count_rows():
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    n = cur.fetchone()[0]
    c.close()
    return n


def main():
    os.makedirs(orch.TOURS_DIR, exist_ok=True)
    name = f"LOCAL606 Live {uuid.uuid4().hex[:8]}"
    print(f"=== LOCAL-606 live driver ===")
    print(f"TOUR NAME: {name}")
    print(f"DB: {os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}")

    before = count_rows()
    print(f"\naudio_tours COUNT BEFORE: {before}")

    # --- generation 1: fresh is_test tour, 4 stops, lat/lng NULL ---
    z1 = os.path.join(orch.TOURS_DIR, "local606_live_v1.zip")
    _make_zip(z1, b"audio-generation-one")
    r1 = orch.store_audio_tour(
        name, "req:" + name, z1, None, None,
        tour_content="Generation one: alphabetical pre-fix stops (4).",
        stops_count=4, is_test=True, job_id="local606-live-gen1",
    )
    print(f"\n[gen1] result: {r1}")
    assert r1["success"] and r1["action"] == "inserted", r1

    c = _conn(); cur = c.cursor()
    cur.execute(
        "SELECT id, stops_count, lat, lng, is_test FROM audio_tours "
        "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL", (name,))
    row1 = cur.fetchone(); c.close()
    tour_id = row1[0]
    print(f"[gen1] stored id={tour_id} stops={row1[1]} lat={row1[2]} "
          f"lng={row1[3]} is_test={row1[4]}")
    assert tour_id > 400, f"must not reuse a Michael id <= 400, got {tour_id}"

    # --- generation 2: SAME name, DIFFERENT text + stop count -> REPLACE ---
    z2 = os.path.join(orch.TOURS_DIR, "local606_live_v2.zip")
    _make_zip(z2, b"audio-generation-two-improved")
    r2 = orch.store_audio_tour(
        name, "req:" + name, z2, None, None,
        tour_content="Generation two: improved 6-stop text after corrective.",
        stops_count=6, is_test=True, job_id="local606-live-gen2",
    )
    print(f"\n[gen2] result: {r2}")
    assert r2["success"] and r2["action"] == "replaced", r2
    assert r2["existing_tour_id"] == tour_id

    # --- show replaced live content + archived version row ---
    c = _conn(); cur = c.cursor()
    cur.execute(
        "SELECT id, tour_content, zip_filename, stops_count, lat, lng "
        "FROM audio_tours WHERE id=%s", (tour_id,))
    live = cur.fetchone()
    cur.execute(
        "SELECT version_no, tour_content, zip_filename, stops_count, lat, lng, "
        "replaced_by_job, replaced_at FROM audio_tour_versions "
        "WHERE tour_id=%s ORDER BY version_no", (tour_id,))
    versions = cur.fetchall()
    c.close()

    print(f"\n=== LIVE ROW (after replace) id={tour_id} ===")
    print(f"  tour_content : {live[1]!r}")
    print(f"  zip_filename : {live[2]!r}")
    print(f"  stops_count  : {live[3]}")
    print(f"  lat/lng      : {live[4]}/{live[5]}")

    print(f"\n=== ARCHIVED VERSION ROW(S) for tour_id={tour_id} ===")
    for v in versions:
        print(f"  v{v[0]}: content={v[1]!r} zip={v[2]!r} stops={v[3]} "
              f"lat/lng={v[4]}/{v[5]} job={v[6]} at={v[7]}")

    assert live[1] == "Generation two: improved 6-stop text after corrective."
    assert live[3] == 6
    assert len(versions) == 1 and versions[0][0] == 1
    assert versions[0][1] == "Generation one: alphabetical pre-fix stops (4)."
    assert versions[0][3] == 4
    assert versions[0][2] == "local606_live_v1.v1.zip"

    # ZIP rename on disk.
    v1_renamed = os.path.exists(os.path.join(orch.TOURS_DIR, "local606_live_v1.v1.zip"))
    v1_gone = not os.path.exists(os.path.join(orch.TOURS_DIR, "local606_live_v1.zip"))
    print(f"\n[disk] old ZIP renamed to .v1.zip: {v1_renamed}; original gone: {v1_gone}")
    assert v1_renamed and v1_gone

    after = count_rows()
    print(f"\naudio_tours COUNT AFTER: {after}  (delta={after - before}, "
          f"expected +1 for the one new is_test tour)")
    assert after == before + 1, f"expected +1, got delta {after - before}"

    print(f"\nLOCAL-606 LIVE PROOF OK — tour_id={tour_id} replaced; "
          f"version 1 archived; row count +1.")
    print(f"TOUR_ID={tour_id}")


if __name__ == "__main__":
    sys.exit(main())
