#!/usr/bin/env python3
"""restore_tour_version.py — reverse a LOCAL-606 content replacement (D622).

When a regenerated tour whose text differs from the stored row replaces that
row's content, ``tour_orchestrator_service.store_audio_tour`` first archives the
OLD content/ZIP/stops_count/lat/lng into ``audio_tour_versions`` and renames the
superseded ZIP to ``<name>.v<N>.zip`` (never deleted). This helper puts a chosen
archived version back onto the live ``audio_tours`` row, so every replacement is
reversible.

Usage
=====
    python3 restore_tour_version.py <tour_id> <version_no> --dry-run   # default
    python3 restore_tour_version.py <tour_id> <version_no> --apply

``--dry-run`` (the default when neither flag is given) prints exactly what would
change and touches nothing. ``--apply`` performs the restore in a single
transaction.

Reversibility of the restore itself
===================================
Applying a restore is ALSO archived: before overwriting the live row, the
helper snapshots the CURRENT row content as a NEW version row (version
MAX+1). So a restore can itself be undone by restoring that new snapshot. No row
in ``audio_tour_versions`` is ever deleted or overwritten.

Safety
======
  * No DELETE anywhere — only INSERT (new snapshot) and UPDATE (the live row).
  * The tour id and the share code (``shared_tours``) are never touched, so
    curator links keep working.
  * Connects via the same env vars the services use (DB_HOST/DB_NAME/DB_USER/
    DB_PASSWORD/DB_PORT). Under the test harness, ``PGOPTIONS`` routes it at the
    throwaway schema automatically.
  * The ZIP rename on disk is best-effort; the DB row is authoritative.

This file is a tool. It does nothing on import.
"""
import argparse
import os
import sys
import traceback

TOURS_DIR = os.getenv("TOURS_DIR", "/app/tours")


def _connect():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
    )


def _restore_zip_name_on_disk(archived_zip, dry_run):
    """Best-effort: give the archived ``<name>.v<N>.zip`` back its live basename.

    Returns the basename that should be written to the live row's zip_filename.
    If the archived file is not on disk, returns the archived name unchanged so
    the DB still records a coherent filename.
    """
    if not archived_zip:
        return archived_zip
    base = os.path.basename(archived_zip)
    # Reverse "<stem>.v<N>.zip" -> "<stem>.zip". If the name does not match that
    # shape, keep it as-is.
    live_name = base
    import re
    m = re.match(r"^(?P<stem>.+)\.v(?P<n>\d+)\.zip$", base, re.IGNORECASE)
    if m:
        live_name = f"{m.group('stem')}.zip"
    if dry_run:
        return live_name
    try:
        src = os.path.join(TOURS_DIR, base)
        dst = os.path.join(TOURS_DIR, live_name)
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
            print(f"  [disk] renamed {base} -> {live_name}")
        elif not os.path.exists(src):
            print(f"  [disk] archived ZIP {base} not on disk; "
                  f"recording {live_name} in row only")
    except Exception as e:
        print(f"  [disk] WARNING: could not rename {base} -> {live_name}: {e}")
    return live_name


def restore(tour_id, version_no, apply_changes):
    conn = _connect()
    cur = conn.cursor()
    try:
        # The archived version to restore.
        cur.execute(
            """
            SELECT tour_content, zip_filename, stops_count, lat, lng, replaced_at
            FROM audio_tour_versions
            WHERE tour_id = %s AND version_no = %s
            """,
            (tour_id, version_no),
        )
        ver = cur.fetchone()
        if ver is None:
            print(f"ERROR: no audio_tour_versions row for tour_id={tour_id} "
                  f"version_no={version_no}.")
            return 2
        (v_content, v_zip, v_stops, v_lat, v_lng, v_when) = ver

        # The current live row.
        cur.execute(
            """
            SELECT tour_content, zip_filename, stops_count, lat, lng, tour_name
            FROM audio_tours WHERE id = %s
            """,
            (tour_id,),
        )
        live = cur.fetchone()
        if live is None:
            print(f"ERROR: no audio_tours row with id={tour_id}.")
            return 2
        (c_content, c_zip, c_stops, c_lat, c_lng, c_name) = live

        print("=" * 70)
        print(f"RESTORE tour_id={tour_id}  version_no={version_no}  "
              f"(archived at {v_when})")
        print(f"  tour_name: {c_name}")
        print("=" * 70)

        def _fmt(x):
            if isinstance(x, str) and len(x) > 60:
                return f"<text len={len(x)}>"
            return repr(x)

        print("Field changes (current -> restored):")
        print(f"  tour_content : {_fmt(c_content)} -> {_fmt(v_content)}")
        print(f"  zip_filename : {_fmt(c_zip)} -> (from v{version_no}) {_fmt(v_zip)}")
        print(f"  stops_count  : {_fmt(c_stops)} -> {_fmt(v_stops)}")
        print(f"  lat          : {_fmt(c_lat)} -> {_fmt(v_lat)}")
        print(f"  lng          : {_fmt(c_lng)} -> {_fmt(v_lng)}")
        print(f"  id and share code: UNCHANGED")

        if not apply_changes:
            print("\n[DRY-RUN] No changes written. Re-run with --apply to perform "
                  "the restore.")
            return 0

        # --apply: snapshot the CURRENT content as a new version first (so the
        # restore is itself reversible), then overwrite the live row.
        cur.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 "
            "FROM audio_tour_versions WHERE tour_id = %s",
            (tour_id,),
        )
        snapshot_version = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO audio_tour_versions
                (tour_id, version_no, tour_content, zip_filename,
                 stops_count, lat, lng, replaced_by_job)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (tour_id, snapshot_version, c_content, c_zip, c_stops, c_lat, c_lng,
             f"restore_to_v{version_no}"),
        )

        live_zip_name = _restore_zip_name_on_disk(v_zip, dry_run=False)

        cur.execute(
            """
            UPDATE audio_tours
            SET tour_content = %s,
                zip_filename = %s,
                stops_count  = %s,
                lat          = %s,
                lng          = %s
            WHERE id = %s
            """,
            (v_content, live_zip_name, v_stops, v_lat, v_lng, tour_id),
        )
        conn.commit()
        print(f"\n[APPLIED] Restored tour_id={tour_id} to version {version_no}. "
              f"Current content snapshotted as version {snapshot_version} "
              f"(this restore is itself reversible).")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"ERROR during restore: {e}")
        print(traceback.format_exc())
        return 1
    finally:
        cur.close()
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reverse a LOCAL-606 tour content replacement by restoring an "
                    "archived audio_tour_versions row onto the live audio_tours row.")
    parser.add_argument("tour_id", type=int, help="audio_tours.id to restore")
    parser.add_argument("version_no", type=int,
                        help="audio_tour_versions.version_no to restore")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true",
                       help="show what would change, touch nothing (default)")
    group.add_argument("--apply", action="store_true",
                       help="perform the restore in a single transaction")
    args = parser.parse_args(argv)

    apply_changes = bool(args.apply)
    if not apply_changes:
        # Default to dry-run when neither flag (or --dry-run) is given.
        pass
    return restore(args.tour_id, args.version_no, apply_changes)


if __name__ == "__main__":
    sys.exit(main())
