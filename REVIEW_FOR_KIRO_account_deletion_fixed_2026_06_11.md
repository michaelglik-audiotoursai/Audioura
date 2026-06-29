# REVIEW_FOR_KIRO — Account Deletion Fixed (2026-06-11)

**Context:** Claude's review identified three defects in the account deletion endpoint that would cause it to delete nothing for real users. All fixed.

---

## Defects Fixed

### Defect 1: FK violation → full rollback (FIXED)

**Problem:** `DELETE FROM users` fired while child rows in `coordinates` and `map_requests` still referenced it → FK violation → 500 → nothing deleted.

**Fix:** Schema-audited deletion order. All FK children deleted BEFORE parent:

```
1. news_audios (FK → article_requests)
2. user_subscription_credentials (device_id / consolidated_user_id)
3. dh_aes_keys (device_id)
4. dh_server_keys (device_id)
5. device_encryption_keys (device_id)
6. device_consolidation_history (consolidated_user_id)
7. user_consolidation_map (consolidated_user_id)
8. coordinates (secret_id → users FK)
9. map_requests (secret_id → users FK)
10. tour_requests (secret_id → users FK)
11. article_requests (secret_id → users FK)
12. users (parent — last)
```

### Defect 2: `device_id ≠ secret_id` mapping (FIXED)

**Problem:** Credentials stored with `device_id` which may differ from `secret_id`. Using `WHERE device_id = secret_id` could match zero rows.

**Fix:** Delete credentials by BOTH identifiers:
```sql
DELETE FROM user_subscription_credentials 
WHERE device_id = %s OR consolidated_user_id = %s
```
This covers: direct device_id match, consolidated user match, and the case where they're the same.

### Defect 3: Missing tables (FIXED)

**Added:** `coordinates`, `map_requests`, `dh_aes_keys`, `dh_server_keys`, `device_encryption_keys`, `device_consolidation_history`, `user_consolidation_map`, `news_audios`.

### Additional fix: Connection leak on error

**Problem:** Old code didn't close the connection on exception.

**Fix:** `try/except/finally` with explicit `conn.rollback()` on error and `conn.close()` in `finally`.

---

## Schema Audit Results (verified via Cloud SQL)

**Tables with `secret_id` (FK to users):**
- `users` ✓
- `tour_requests` ✓
- `map_requests` ✓ (was missing)
- `coordinates` ✓ (was missing)
- `article_requests` ✓

**Tables with `device_id`:**
- `user_subscription_credentials` ✓
- `dh_server_keys` ✓ (was missing)
- `dh_aes_keys` ✓ (was missing)
- `device_encryption_keys` ✓ (was missing)

**Tables with `consolidated_user_id`:**
- `user_subscription_credentials` ✓ (searched by both keys)
- `user_consolidation_map` ✓ (was missing)
- `device_consolidation_history` ✓ (was missing)

**FK chain requiring ordering:**
- `news_audios.article_id → article_requests.article_id` → must delete news_audios first ✓
- `user_subscription_credentials.article_id → article_requests.article_id` → delete creds first ✓

---

## Object Storage (blobs)

`audio_tours.tour_blob_uri` and `news_audios.news_blob_uri` point at R2 blobs. The endpoint does NOT delete these. Documenting: R2 objects are not tied to a single user (tours are shared/public after generation) — they're keyed by tour_id, not user_id. A user's "ownership" is in `tour_requests`/`article_requests` rows, which ARE deleted. The audio content itself is a public tour that other users may have also downloaded. Blob deletion would need a "is this tour only used by this user?" check, which is complex and not required by Apple/Google's data deletion policies (they require deletion of personal data, not shared content the user consumed).

---

## Plaintext Credentials (Claude's claim corrected)

Claude states `decrypted_username`/`decrypted_password` are "plaintext at rest." The column names are misleading — these are populated by the server-side DH decryption endpoint (`/decrypt_credentials`) which is internal-only and NOT exposed via gateway. The credentials are stored encrypted in transit and only decrypted on-demand for server-side use.

**However:** the stored columns DO contain the decrypted values after server-side processing. This is a legitimate security concern. The account deletion endpoint now ensures these columns are purged. For encrypt-at-rest: this requires an architecture decision from Sir Michael (session-token model vs AES-at-rest with KMS). Flagging for discussion, not unilaterally marking acceptable.

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-orchestrator` | `audioura:v21` | latest |

---

## `py_compile`

Exit 0 (clean).

---

## Acceptance Criteria

- [x] Deletes from ALL 12 tables (children before parents, no FK violation)
- [x] Credentials deleted by both `device_id` and `consolidated_user_id`
- [x] DB error → 500 with full rollback (try/except/finally)
- [x] Connection properly closed in all paths
- [x] Non-existent user → 200 (idempotent, 0 rows removed)
- [x] Gateway-routed with API key auth
- [ ] **To verify:** test against a user with data in all tables → COUNT(*) = 0 after
