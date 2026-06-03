#!/usr/bin/env python3
"""
Phase D: Migrate tour and news audio ZIPs from PostgreSQL BYTEA to Cloudflare R2.

For each row in audio_tours and news_audios that has BYTEA data:
1. Upload the ZIP to R2 under tours/{id}.zip or news/{id}.zip
2. Set tour_blob_uri / news_blob_uri to the R2 key
3. Optionally NULL out the BYTEA column to reclaim DB space (--clear flag)

Safe to run multiple times (skips rows that already have a blob_uri set).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import psycopg2
from blobstorage import R2BlobStorage

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5433')
DB_NAME = os.getenv('DB_NAME', 'audiotours')
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password123')

def get_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)

def migrate_audio_tours(r2, clear_bytea=False):
    """Migrate audio_tours.audio_tour BYTEA → R2"""
    conn = get_db()
    cur = conn.cursor()
    
    # Count eligible rows
    cur.execute("SELECT count(*) FROM audio_tours WHERE audio_tour IS NOT NULL AND tour_blob_uri IS NULL")
    total = cur.fetchone()[0]
    print(f"\n=== audio_tours: {total} rows to migrate ===")
    
    if total == 0:
        print("Nothing to migrate.")
        cur.close()
        conn.close()
        return 0
    
    # Process in batches
    batch_size = 10
    migrated = 0
    failed = 0
    
    cur.execute("SELECT id, tour_name, octet_length(audio_tour) FROM audio_tours WHERE audio_tour IS NOT NULL AND tour_blob_uri IS NULL ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    for tour_id, tour_name, size_bytes in rows:
        try:
            # Read BYTEA
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("SELECT audio_tour FROM audio_tours WHERE id = %s", (tour_id,))
            data = cur2.fetchone()[0]
            cur2.close()
            conn2.close()
            
            if not data:
                continue
            
            # Upload to R2
            r2_key = f"tours/{tour_id}.zip"
            r2.upload(r2_key, bytes(data))
            
            # Update row with R2 URI
            conn3 = get_db()
            cur3 = conn3.cursor()
            if clear_bytea:
                cur3.execute("UPDATE audio_tours SET tour_blob_uri = %s, audio_tour = NULL WHERE id = %s", (r2_key, tour_id))
            else:
                cur3.execute("UPDATE audio_tours SET tour_blob_uri = %s WHERE id = %s", (r2_key, tour_id))
            conn3.commit()
            cur3.close()
            conn3.close()
            
            migrated += 1
            size_mb = (size_bytes or 0) / 1024 / 1024
            safe_name = tour_name.encode('ascii', 'replace').decode() if tour_name else ''
            print(f"  [{migrated}/{total}] Tour {tour_id} ({size_mb:.1f} MB) -> {r2_key}")
            
        except Exception as e:
            failed += 1
            print(f"  [ERROR] Tour {tour_id}: {str(e).encode('ascii', 'replace').decode()}")
    
    print(f"\naudio_tours migration: {migrated} migrated, {failed} failed, {total - migrated - failed} skipped")
    return migrated

def migrate_news_audios(r2, clear_bytea=False):
    """Migrate news_audios.news_article BYTEA → R2"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT count(*) FROM news_audios WHERE news_article IS NOT NULL AND news_blob_uri IS NULL")
    total = cur.fetchone()[0]
    print(f"\n=== news_audios: {total} rows to migrate ===")
    
    if total == 0:
        print("Nothing to migrate.")
        cur.close()
        conn.close()
        return 0
    
    cur.execute("SELECT id, article_id, octet_length(news_article) FROM news_audios WHERE news_article IS NOT NULL AND news_blob_uri IS NULL ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    migrated = 0
    failed = 0
    
    for row_id, article_id, size_bytes in rows:
        try:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("SELECT news_article FROM news_audios WHERE id = %s", (row_id,))
            data = cur2.fetchone()[0]
            cur2.close()
            conn2.close()
            
            if not data:
                continue
            
            r2_key = f"news/{article_id}.zip"
            r2.upload(r2_key, bytes(data))
            
            conn3 = get_db()
            cur3 = conn3.cursor()
            if clear_bytea:
                cur3.execute("UPDATE news_audios SET news_blob_uri = %s, news_article = NULL WHERE id = %s", (r2_key, row_id))
            else:
                cur3.execute("UPDATE news_audios SET news_blob_uri = %s WHERE id = %s", (r2_key, row_id))
            conn3.commit()
            cur3.close()
            conn3.close()
            
            migrated += 1
            size_mb = (size_bytes or 0) / 1024 / 1024
            print(f"  [{migrated}/{total}] News {article_id[:12]}... ({size_mb:.1f} MB) -> {r2_key}")
            
        except Exception as e:
            failed += 1
            print(f"  [ERROR] News {str(article_id)[:12]}: {str(e).encode('ascii', 'replace').decode()}")
    
    print(f"\nnews_audios migration: {migrated} migrated, {failed} failed, {total - migrated - failed} skipped")
    return migrated


def verify_migration(r2):
    """Verify R2 objects match DB BYTEA sizes. Use before --clear."""
    conn = get_db()
    cur = conn.cursor()
    
    print("\n=== VERIFICATION: Comparing R2 object sizes to DB BYTEA sizes ===")
    
    mismatches = 0
    verified = 0
    
    # Verify tours
    cur.execute("SELECT id, tour_blob_uri, octet_length(audio_tour) FROM audio_tours WHERE tour_blob_uri IS NOT NULL AND audio_tour IS NOT NULL")
    tour_rows = cur.fetchall()
    print(f"\nVerifying {len(tour_rows)} tour objects...")
    
    for tour_id, blob_uri, db_size in tour_rows:
        try:
            head = r2.client.head_object(Bucket=r2.bucket, Key=blob_uri)
            r2_size = head['ContentLength']
            if r2_size != db_size:
                print(f"  MISMATCH Tour {tour_id}: DB={db_size}, R2={r2_size}")
                mismatches += 1
            else:
                verified += 1
        except Exception as e:
            print(f"  ERROR Tour {tour_id}: {e}")
            mismatches += 1
    
    # Verify news
    cur.execute("SELECT id, article_id, news_blob_uri, octet_length(news_article) FROM news_audios WHERE news_blob_uri IS NOT NULL AND news_article IS NOT NULL")
    news_rows = cur.fetchall()
    print(f"\nVerifying {len(news_rows)} news objects...")
    
    for row_id, article_id, blob_uri, db_size in news_rows:
        try:
            head = r2.client.head_object(Bucket=r2.bucket, Key=blob_uri)
            r2_size = head['ContentLength']
            if r2_size != db_size:
                print(f"  MISMATCH News {str(article_id)[:12]}: DB={db_size}, R2={r2_size}")
                mismatches += 1
            else:
                verified += 1
        except Exception as e:
            print(f"  ERROR News {str(article_id)[:12]}: {e}")
            mismatches += 1
    
    cur.close()
    conn.close()
    
    print(f"\n{'=' * 50}")
    print(f"VERIFIED: {verified} objects match")
    if mismatches:
        print(f"MISMATCHES: {mismatches} — DO NOT run --clear until resolved!")
    else:
        print("✅ ALL objects verified — safe to --clear when ready")
    return mismatches == 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Migrate blobs from PostgreSQL to Cloudflare R2')
    parser.add_argument('--clear', action='store_true', help='NULL out BYTEA after successful upload (reclaims DB space)')
    parser.add_argument('--verify', action='store_true', help='Verify R2 object sizes match DB BYTEA sizes (run before --clear)')
    parser.add_argument('--tours-only', action='store_true', help='Only migrate audio_tours')
    parser.add_argument('--news-only', action='store_true', help='Only migrate news_audios')
    args = parser.parse_args()
    
    print("Phase D: Blob Migration to Cloudflare R2")
    print("=" * 50)
    
    r2 = R2BlobStorage()
    print(f"R2 endpoint: {r2.endpoint}")
    print(f"R2 bucket: {r2.bucket}")
    
    if not r2.health_check():
        print("ERROR: R2 health check failed. Check credentials.")
        sys.exit(1)
    
    print("R2 connectivity: OK")
    
    if args.verify:
        verify_migration(r2)
        sys.exit(0)
    
    total_migrated = 0
    
    if not args.news_only:
        total_migrated += migrate_audio_tours(r2, clear_bytea=args.clear)
    
    if not args.tours_only:
        total_migrated += migrate_news_audios(r2, clear_bytea=args.clear)
    
    print(f"\n{'=' * 50}")
    print(f"TOTAL MIGRATED: {total_migrated} objects to R2")
    if not args.clear:
        print("NOTE: BYTEA data preserved in DB. Run with --clear to reclaim space after verifying R2 delivery works.")
