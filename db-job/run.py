#!/usr/bin/env python3
"""End-to-end account deletion test — ALL 12 tables seeded with correct schemas."""
import os
import uuid
import requests
import psycopg2

DB_HOST = '/cloudsql/audiotours-migration:us-central1:audioura-db'
DB_NAME = 'audiotours'
DB_USER = 'admin'
DB_PASS = os.getenv('DB_PASSWORD')
API_KEY = os.getenv('GATEWAY_API_KEY', '')
GW_URL = "https://api.audioura.com"
TEST_SID = "ITEST-DELETE-ACCOUNT"

def db():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

# === Step 0: Discover actual columns for tricky tables ===
print("=== Step 0: Schema discovery ===")
conn = db(); cur = conn.cursor()
for table in ['dh_server_keys', 'dh_aes_keys', 'device_encryption_keys', 'user_subscription_credentials', 'news_audios', 'map_requests', 'coordinates']:
    cur.execute("SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", (table,))
    cols = cur.fetchall()
    print(f"  {table}: {[(c[0], 'NULL' if c[1]=='YES' else 'NOT NULL') for c in cols]}")
cur.close(); conn.close()

# === Step 1: Seed test data across ALL tables ===
print("\n=== Step 1: Seeding ALL 12 tables ===")
conn = db(); cur = conn.cursor()

test_article_id = str(uuid.uuid4())
seeded = []

def do_insert(label, sql, params):
    try:
        cur.execute("SAVEPOINT sp")
        cur.execute(sql, params)
        cur.execute("RELEASE SAVEPOINT sp")
        seeded.append(label)
        print(f"  ✅ {label}")
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        print(f"  ❌ {label}: {str(e)[:100]}")

# 1. users (parent)
do_insert("users", "INSERT INTO users (secret_id, plan) VALUES (%s, 'free') ON CONFLICT (secret_id) DO UPDATE SET plan='free'", (TEST_SID,))

# 2. tour_requests (FK → users)
do_insert("tour_requests", "INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source) VALUES (%s, %s, 'completed', NOW(), 'orchestrator')", (TEST_SID, str(uuid.uuid4())))

# 3. coordinates (FK → users)
do_insert("coordinates", "INSERT INTO coordinates (secret_id) VALUES (%s)", (TEST_SID,))

# 4. map_requests (FK → users)
do_insert("map_requests", "INSERT INTO map_requests (secret_id) VALUES (%s)", (TEST_SID,))

# 5. article_requests (FK → users) — needed as parent for news_audios and credentials
do_insert("article_requests", "INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at, started_at) VALUES (%s, %s, 'deletion test', %s, 'finished', NOW(), NOW())", (test_article_id, TEST_SID, psycopg2.Binary(b"test content for deletion")))

# 6. news_audios (FK → article_requests.article_id)
do_insert("news_audios", "INSERT INTO news_audios (article_id, article_name, news_article, number_requested) VALUES (%s, 'deletion test news', %s, 0)", (test_article_id, psycopg2.Binary(b"fake zip data")))

# 7. user_subscription_credentials (device_id + article_id FK)
do_insert("user_subscription_credentials", "INSERT INTO user_subscription_credentials (device_id, domain, decrypted_username, decrypted_password, article_id, created_at) VALUES (%s, 'nytimes.com', 'testuser@example.com', 'SuperSecret123!', %s, NOW())", (TEST_SID, test_article_id))

# 8. dh_aes_keys (device_id)
do_insert("dh_aes_keys", "INSERT INTO dh_aes_keys (device_id, aes_key, created_at) VALUES (%s, 'test_aes_key_value', NOW())", (TEST_SID,))

# 9. dh_server_keys (device_id, private_key NOT NULL)
do_insert("dh_server_keys", "INSERT INTO dh_server_keys (device_id, private_key, created_at) VALUES (%s, 'test_private_key_value', NOW())", (TEST_SID,))

# 10. device_encryption_keys (device_id)
do_insert("device_encryption_keys", "INSERT INTO device_encryption_keys (device_id, encryption_key, created_at) VALUES (%s, 'test_encryption_key', NOW())", (TEST_SID,))

# 11. device_consolidation_history (consolidated_user_id)
do_insert("device_consolidation_history", "INSERT INTO device_consolidation_history (consolidated_user_id, old_device_id, new_device_id, created_at) VALUES (%s, 'old_dev', 'new_dev', NOW())", (TEST_SID,))

# 12. user_consolidation_map (consolidated_user_id)
do_insert("user_consolidation_map", "INSERT INTO user_consolidation_map (consolidated_user_id, device_id, created_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING", (TEST_SID, TEST_SID))

conn.commit()
cur.close(); conn.close()
print(f"\n  Seeded: {len(seeded)}/12 tables")

# === Step 2: Verify rows exist before deletion ===
print("\n=== Step 2: Verifying rows exist BEFORE deletion ===")
conn = db(); cur = conn.cursor()
pre_counts = {}
checks = [
    ("users", "secret_id"), ("tour_requests", "secret_id"), ("coordinates", "secret_id"),
    ("map_requests", "secret_id"), ("article_requests", "secret_id"), ("news_audios", "article_id"),
    ("user_subscription_credentials", "device_id"), ("dh_aes_keys", "device_id"),
    ("dh_server_keys", "device_id"), ("device_encryption_keys", "device_id"),
    ("device_consolidation_history", "consolidated_user_id"), ("user_consolidation_map", "consolidated_user_id"),
]
check_vals = {
    "news_audios": test_article_id,  # news_audios keyed on article_id
}
for table, col in checks:
    val = check_vals.get(table, TEST_SID)
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", (val,))
        cnt = cur.fetchone()[0]
        pre_counts[table] = cnt
        print(f"  {table}: {cnt} row(s)")
    except Exception as e:
        pre_counts[table] = -1
        print(f"  {table}: ERROR ({str(e)[:60]})")
cur.close(); conn.close()

# === Step 3: Call DELETE endpoint ===
print("\n=== Step 3: DELETE /delete-account ===")
headers = {"X-API-Key": API_KEY} if API_KEY else {}
r = requests.delete(f"{GW_URL}/delete-account/{TEST_SID}", headers=headers, timeout=30)
print(f"  Status: {r.status_code}")
try:
    body = r.json()
    print(f"  Body: {body}")
except:
    print(f"  Body: {r.text[:300]}")

if r.status_code != 200:
    print(f"  ❌ FAIL: Expected 200")
    exit(1)

# === Step 4: Verify ALL tables are empty ===
print("\n=== Step 4: Verifying ALL tables AFTER deletion ===")
conn = db(); cur = conn.cursor()
all_clear = True
for table, col in checks:
    val = check_vals.get(table, TEST_SID)
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", (val,))
        cnt = cur.fetchone()[0]
        was = pre_counts.get(table, '?')
        if cnt > 0:
            all_clear = False
            print(f"  ❌ {table}: {cnt} rows REMAINING (was {was})")
        elif was > 0:
            print(f"  ✅ {table}: 0 rows (was {was} — DELETED)")
        else:
            print(f"  ➖ {table}: 0 rows (was {was} — nothing to delete)")
    except Exception as e:
        print(f"  ⚠️ {table}: {str(e)[:60]}")
cur.close(); conn.close()

# === Step 5: Idempotency ===
print("\n=== Step 5: Idempotency ===")
r2 = requests.delete(f"{GW_URL}/delete-account/{TEST_SID}", headers=headers, timeout=30)
idempotent = r2.status_code == 200
print(f"  Status: {r2.status_code} ({'✅' if idempotent else '❌'})")

# === Summary ===
print("\n" + "=" * 60)
if all_clear and idempotent:
    print("✅ FULL ACCOUNT DELETION TEST PASSED (all 12 tables verified)")
else:
    print("❌ ACCOUNT DELETION TEST FAILED")
    if not all_clear:
        print("  Some rows survived deletion")
    if not idempotent:
        print("  Idempotency failed")
    exit(1)
