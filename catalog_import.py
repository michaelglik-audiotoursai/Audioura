#!/usr/bin/env python3
"""LOCAL-808 catalog importer — GCloud_Storied runs this against its Cloud SQL `audio_tours`.

It reads the bundle produced by catalog_export.py (catalog/export/manifest.json + <id>.zip) and
INSERTS each kept tour, but ONLY when a row with the same (request_string, language) does not
already exist. It is INSERT-only by construction:

  * DRY-RUN BY DEFAULT. Nothing is written unless you pass --apply.
  * No DELETE, ever. No UPDATE of existing rows, ever — existing rows are left untouched and the
    tour is reported as "skipped (exists)".
  * Reports the audio_tours row count BEFORE and AFTER, plus per-tour inserted/skipped.

Connection: set DATABASE_URL (postgres://user:pass@host:port/db) — e.g. the Cloud SQL connection
string. Requires psycopg2 (psycopg2-binary). Safe to run repeatedly: a second run inserts nothing
because every (request_string, language) now exists (idempotent).

Policy columns written on INSERT (from the manifest): track='subscribed', is_test=false,
price_tier=NULL (free; is_paid is a GENERATED column and is never inserted), creator_type='audioura',
editor_score = the clamped [5.0, 8.0] score. The audio ZIP bytes are loaded into audio_tour (bytea).
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXPORT = os.path.join(HERE, "catalog", "export")

# Columns we INSERT. is_paid is GENERATED in the schema and is deliberately excluded.
INSERT_COLS = ["tour_name", "request_string", "audio_tour", "lat", "lng", "language",
               "tour_content", "content_language", "stops_count", "tour_kind", "track",
               "is_test", "price_tier", "creator_type", "editor_score", "zip_filename",
               "description", "short_title", "number_requested"]


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set — point it at the GCloud_Storied Cloud SQL database.")
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 is required (pip install psycopg2-binary).")
    return psycopg2.connect(url)


def row_count(cur):
    cur.execute("select count(*) from audio_tours")
    return cur.fetchone()[0]


def exists(cur, request_string, language):
    cur.execute("select 1 from audio_tours where request_string=%s and language=%s limit 1",
                (request_string, language))
    return cur.fetchone() is not None


def build_values(tour, zip_bytes):
    """Map a manifest tour + its ZIP bytes to the INSERT_COLS order."""
    import psycopg2
    return {
        "tour_name": tour["tour_name"],
        "request_string": tour["request_string"],
        "audio_tour": psycopg2.Binary(zip_bytes),
        "lat": tour["lat"],
        "lng": tour["lng"],
        "language": tour["language"],
        "tour_content": tour["tour_content"],
        "content_language": tour["content_language"],
        "stops_count": tour["stops_count"],
        "tour_kind": tour["tour_kind"],
        "track": tour["track"],
        "is_test": tour["is_test"],
        "price_tier": tour["price_tier"],          # None -> free (is_paid generated false)
        "creator_type": tour["creator_type"],
        "editor_score": tour["editor_score"],      # already clamped to [5.0, 8.0]
        "zip_filename": tour.get("zip_filename"),
        "description": tour.get("description"),
        "short_title": tour.get("short_title"),
        "number_requested": tour.get("stops_count") or 0,
    }


def main():
    ap = argparse.ArgumentParser(description="Import the kept catalog bundle into Cloud SQL (dry-run by default).")
    ap.add_argument("--export-dir", default=os.environ.get("CATALOG_EXPORT_DIR", DEFAULT_EXPORT))
    ap.add_argument("--apply", action="store_true",
                    help="actually INSERT. Without this flag the run is a dry-run (no writes).")
    args = ap.parse_args()

    manifest_path = os.path.join(args.export_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        sys.exit(f"manifest not found: {manifest_path} (run catalog_export.py first)")
    bundle = json.load(open(manifest_path))
    tours = bundle["tours"]

    mode = "APPLY (writing)" if args.apply else "DRY-RUN (no writes)"
    print(f"catalog_import — {mode} | {len(tours)} tours in bundle from {args.export_dir}\n")

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    before = row_count(cur)
    print(f"audio_tours rows BEFORE: {before}\n")

    to_insert, skipped = [], []
    for t in tours:
        if exists(cur, t["request_string"], t["language"]):
            skipped.append(t)
            print(f"  skip   {t['source_id']:>5}  (request_string, language) already exists: "
                  f"{t['request_string']!r} / {t['language']}")
        else:
            to_insert.append(t)
            print(f"  INSERT {t['source_id']:>5}  {t['tour_name'][:50]!r}")

    inserted = 0
    if args.apply:
        placeholders = ", ".join(["%s"] * len(INSERT_COLS))
        collist = ", ".join(INSERT_COLS)
        sql = f"insert into audio_tours ({collist}) values ({placeholders})"
        try:
            for t in to_insert:
                zip_path = os.path.join(args.export_dir, t["zip_file"])
                with open(zip_path, "rb") as f:
                    zb = f.read()
                vals = build_values(t, zb)
                cur.execute(sql, [vals[c] for c in INSERT_COLS])
                inserted += 1
            conn.commit()
            print(f"\ncommitted {inserted} INSERT(s).")
        except Exception as e:
            conn.rollback()
            sys.exit(f"\nINSERT failed, rolled back (no rows written): {e}")
    else:
        print(f"\nDRY-RUN: would INSERT {len(to_insert)}, would skip {len(skipped)}. "
              f"Re-run with --apply to write.")

    after = row_count(cur)
    cur.close()
    conn.close()

    print(f"\naudio_tours rows AFTER:  {after}  (delta {after - before})")
    print(f"summary: bundle={len(tours)}  insert_candidates={len(to_insert)}  "
          f"skipped_exists={len(skipped)}  inserted={inserted}")
    if not args.apply and after != before:
        print("WARNING: row count changed during a dry-run — unexpected.")


if __name__ == "__main__":
    main()
