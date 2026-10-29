#!/usr/bin/env python3
"""LOCAL-808 catalog exporter — build the GCloud_Storied bundle for the KEPT tours.

For each kept tour it writes:
  catalog/export/<tour_id>.zip   — the stored ZIP bytes from audio_tours.audio_tour (verbatim)
  catalog/export/manifest.json   — one object per kept tour with the columns GCloud_Storied needs
                                    for an INSERT into its Cloud SQL audio_tours table.

Read-only on the source DB (single SELECT per tour, no writes). Uploads nothing.

The exporter does NOT upload anything and does NOT touch the source rows. The export/ directory
is gitignored: the 3-4 MB audio ZIPs stay on disk for GCloud_Storied and are never committed.

Source DB: the Mac dev Postgres (container `development-postgres-2-1`, db `audiotours`, user `admin`),
reached with `docker exec` so no DB password handling is needed locally. Override with env vars
(PGHOST/PGPORT/PGUSER/PGDATABASE + PGPASSWORD) to run against psql directly instead.

Score policy: CATALOG_REVIEW.md scores tours 0-10, but the destination `audio_tours.editor_score`
column has a CHECK constraint 5.0 <= editor_score <= 8.0. The manifest therefore carries BOTH the
raw review score (`review_score`, 0-10, for humans) and `editor_score` clamped into [5.0, 8.0] so the
INSERT cannot violate the constraint. All kept tours score >= 7.5 so the clamp only caps the top.
"""
import argparse, base64, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXPORT = os.path.join(HERE, "catalog", "export")

# Kept tours and their 0-10 review scores, straight from catalog/CATALOG_REVIEW.md.
# Six from the original LOCAL-808 review; four (844, 850, 852, 853) added by the LOCAL-808B
# re-score of LEAD's re-made tours (same keep rule: score >= 7.5 AND every pin <= 150 m).
KEEP_SCORES = {844: 7.5, 845: 7.5, 846: 8.5, 848: 8.5, 850: 8.0,
               852: 7.5, 853: 8.0, 856: 7.5, 858: 8.0, 859: 7.5,
               # LEAD 2026-10-29 18:1x: re-pinned by LOCAL-815 (pin_proof 5/5 <= 100 m); 808B score 7.5, pins were the only reason to drop.
               857: 7.5, 860: 7.5}

# Catalog policy constants (free official catalog tours on the subscribed track).
TRACK = "subscribed"
CREATOR_TYPE = "audioura"
EDITOR_SCORE_MIN, EDITOR_SCORE_MAX = 5.0, 8.0  # audio_tours_editor_score_check

CONTAINER = os.environ.get("CATALOG_DB_CONTAINER", "development-postgres-2-1")
DB = os.environ.get("CATALOG_DB_NAME", "audiotours")
DBUSER = os.environ.get("CATALOG_DB_USER", "admin")

# Columns needed for an INSERT in the destination. Pulled read-only from the source row.
COLS = ["id", "tour_name", "request_string", "lat", "lng", "language", "stops_count",
        "tour_content", "content_language", "tour_kind", "zip_filename", "description",
        "short_title"]


def psql(sql):
    """Run a read-only SQL statement and return stdout (tab-separated, -A). Prefers docker exec."""
    if os.environ.get("CATALOG_USE_LOCAL_PSQL"):
        cmd = ["psql", "-U", DBUSER, "-d", DB, "-Atc", sql]
    else:
        cmd = ["docker", "exec", CONTAINER, "psql", "-U", DBUSER, "-d", DB, "-Atc", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"DB read failed: {r.stderr.strip()}")
    return r.stdout


def fetch_row(tid):
    """Fetch the INSERT columns for one tour as a dict (JSON round-trip keeps types/NULLs clean)."""
    sql = ("select row_to_json(t) from (select " + ", ".join(COLS) +
           f" from audio_tours where id={int(tid)}) t")
    out = psql(sql).strip()
    if not out:
        sys.exit(f"tour id {tid} not found in source DB")
    return json.loads(out)


def fetch_zip_bytes(tid):
    """Fetch the stored ZIP (bytea) for one tour as raw bytes, via base64 to stay binary-safe."""
    out = psql(f"select encode(audio_tour,'base64') from audio_tours where id={int(tid)}")
    b64 = "".join(out.split())
    if not b64:
        sys.exit(f"tour id {tid} has no audio_tour ZIP")
    return base64.b64decode(b64)


def main():
    ap = argparse.ArgumentParser(description="Export kept catalog tours for GCloud_Storied.")
    ap.add_argument("--export-dir", default=os.environ.get("CATALOG_EXPORT_DIR", DEFAULT_EXPORT),
                    help="output directory (default: catalog/export, which is gitignored)")
    args = ap.parse_args()

    os.makedirs(args.export_dir, exist_ok=True)
    manifest = []
    for tid in sorted(KEEP_SCORES):
        row = fetch_row(tid)
        zb = fetch_zip_bytes(tid)
        # Verify the exported ZIP matches the stored byte length exactly.
        stored_len = int(psql(f"select octet_length(audio_tour) from audio_tours where id={tid}").strip())
        if len(zb) != stored_len:
            sys.exit(f"tour {tid}: exported {len(zb)} bytes != stored {stored_len}")
        zip_path = os.path.join(args.export_dir, f"{tid}.zip")
        with open(zip_path, "wb") as f:
            f.write(zb)

        review_score = KEEP_SCORES[tid]
        editor_score = round(min(EDITOR_SCORE_MAX, max(EDITOR_SCORE_MIN, review_score)), 1)
        manifest.append({
            # identity / content columns for the destination INSERT
            "source_id": row["id"],
            "tour_name": row["tour_name"],
            "request_string": row["request_string"],
            "lat": row["lat"],
            "lng": row["lng"],
            "language": row["language"],
            "stops_count": row["stops_count"],
            "tour_content": row["tour_content"],
            "content_language": row["content_language"],
            "tour_kind": row["tour_kind"],
            "short_title": row.get("short_title"),
            "description": row.get("description"),
            # catalog policy columns
            "track": TRACK,
            "is_test": False,
            "price_tier": None,   # free catalog tour; is_paid is GENERATED from price_tier
            "is_paid": False,     # informational only; destination column is generated, do not insert
            "creator_type": CREATOR_TYPE,
            "review_score": review_score,          # 0-10, from CATALOG_REVIEW.md
            "editor_score": editor_score,          # clamped into [5.0, 8.0] for the CHECK constraint
            # packaging metadata
            "zip_file": f"{tid}.zip",
            "zip_filename": row.get("zip_filename"),
            "zip_bytes": len(zb),
        })
        print(f"exported {tid}: {len(zb)} bytes -> {zip_path}  (review {review_score} / editor {editor_score})")

    manifest_path = os.path.join(args.export_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({"track": TRACK, "creator_type": CREATOR_TYPE, "count": len(manifest),
                   "tours": manifest}, f, indent=2)
    print(f"\nwrote {manifest_path} with {len(manifest)} kept tours")
    print("export/ is gitignored — ZIPs stay on disk, not committed.")


if __name__ == "__main__":
    main()
