# Claude Review — Kiro Launch-Gates Hand-Back (2026-06-11)

**Reviewing:** `REVIEW_FOR_KIRO_launch_gates_2026_06_11.md`
**Lane:** Services only (gateway + DB + Cloud Run). **Author:** Claude (independent reviewer).
**Verdict:** **Account deletion is NOT done — it is both incomplete and broken.** It will throw a foreign-key
violation and roll back (delete nothing) for any real user. Regex + gateway route + max-instances check out.
Two deferrals rest on a factually wrong claim. Details + next tasks below.

---

## Verified TRUE ✅

1. **Classification regex is plural-only.** `generate_tour_text.py:55–58` matches `libraries|churches|schools|…|buildings|branches|historic houses|fire stations` — plural forms only. Claim confirmed.
2. **Gateway route exists.** `gateway_routes.yaml:155–159` adds `/delete-account/<secret_id>` → `orchestrator`, `methods:[DELETE]`, `auth: api_key`. Present and API-key-gated as required.
3. **Max-instances set.** The six-service table is a reasonable hard concurrency cap. (Note: Kiro's prose says "5 concurrent tours × \$1.10" but the orchestrator cap is **10**, so worst-case tour burn is ~\$11, not \$5.50 — fix the number, not the config.)

---

## BROKEN / FALSE ❌ — Account deletion (`tour_orchestrator_service.py:1543`)

Kiro reported "✅ purges all user data (credentials, tours, articles, user record)." The code deletes only **four** tables: `user_subscription_credentials` (by `device_id`), `tour_requests`, `article_requests`, `users`. Three defects, the first is launch-blocking.

### Defect 1 — FK violation → full rollback → deletes NOTHING (launch-blocking)

The schema has these FKs to `users(secret_id)`, **none with `ON DELETE CASCADE`**:

```
coordinates.secret_id    → users(secret_id)     -- NOT deleted by Kiro
map_requests.secret_id   → users(secret_id)     -- NOT deleted by Kiro
tour_requests.secret_id  → users(secret_id)     -- deleted ✓
article_requests.secret_id → users(secret_id)   -- deleted ✓
```

The endpoint never deletes `coordinates` or `map_requests`. So `DELETE FROM users` fires while child rows still
reference it → **foreign-key violation → exception → 500 → transaction rolls back → nothing is deleted.** Any user
who has ever generated a tour (writes `coordinates`/`map_requests`) cannot be deleted. The "fail-closed, no partial
wipe" design is working exactly as intended — it just means the whole delete fails.

Secondary FK risk on the same path: `news_audios.article_id → article_requests(article_id)` (no cascade). If any
`news_audios` row references this user's articles, `DELETE FROM article_requests` also throws before we even reach
`users`.

### Defect 2 — Most-sensitive data likely survives: `device_id` ≠ `secret_id`

Line 1568: `DELETE FROM user_subscription_credentials WHERE device_id = %s` is passed the **`secret_id`** value.
But `users` is keyed on `secret_id`, while `user_subscription_credentials` is keyed on `device_id` and carries its
own `consolidated_user_id` — a **separate identifier namespace** (there are whole consolidation tables:
`user_consolidation_map`, `device_consolidation_history`, and per-device `dh_*`/`device_encryption_keys`). Unless the
app uses the identical string for both, this `WHERE` matches **zero rows** and the user's third-party newspaper
logins — stored as `decrypted_username` / `decrypted_password` — **remain after "delete account."** This is the
worst-case privacy miss the spec explicitly called out. **Confirm the `device_id`↔`secret_id`↔`consolidated_user_id`
mapping before trusting any credential delete.**

### Defect 3 — Tables and blobs never touched

Not deleted at all: `coordinates`, `map_requests`, `device_encryption_keys`, `dh_aes_keys`, `dh_server_keys`,
`newsletter_server_keys`, `user_consolidation_map`, `device_consolidation_history`. Also unaddressed: object storage
— `audio_tours.tour_blob_uri` and `news_audios.news_blob_uri` point at GCS/R2 blobs that the privacy policy promises
to delete. The spec's instruction ("grep the schema for **every** table keyed on `secret_id`/`device_id`, and delete
the blobs too") was not carried out.

---

## Deferrals — assessment

| Item | Kiro's call | My assessment |
|------|-------------|---------------|
| **App attestation (Part 1, server)** | "Needs Mobile-AQ first" | Partly right — Play Integrity needs app tokens. **But** the server scaffold (`/attest-nonce` + verify middleware + `ATTESTATION_ENFORCED=false` log-only toggle) can and should be built **now, in parallel**, per the spec. Don't wait for Mobile to start. |
| **Budget alert + kill-switch** | "Operator action only" | Half right. Budget + Pub/Sub creation needs Sir Michael in GCP Console. **But the kill-switch Cloud Function (sets cost services to `--max-instances=0` on the 100% trigger) is Kiro's to write and deploy.** Max-instances is only one leg of the three-leg backstop (cap + budget + kill-switch); ship the other two. |
| **Plaintext credentials** | "Already DH-encrypted, acceptable" | **Factually wrong.** The table stores `decrypted_username` / `decrypted_password` (plaintext at rest) — this is the exact column the launch checklist §3 flags. DH protects data *in transit*, not at rest. This is an owner-flagged fix (session-token model or encrypt-at-rest), not something to silently mark acceptable. Needs a real fix or explicit owner sign-off. |
| **DB-down→503 test (B1/T4)** + **tour-quota tests** | "Operator-assisted, pre-launch" | These were explicit asks and were **not run**: `test_news_quota_integration.py --test-db-down` (mandatory), `test_tour_quota_integration.py` (gate + `--run-generate` + `--check-rollback`). Run them against a test DB or state the concrete blocker. |
| **Cloud Tasks `maxAttempts`** | "API not enabled, queue not created" | Legit *if* Cloud Tasks isn't deployed — but that itself is a flag: prod `GENERATION_MODE='cloud_tasks'` requires the queue. Either the queue isn't created (so prod is on thread-fallback — confirm intended) or it needs creating + then verify `maxAttempts == MAX_TASK_ATTEMPTS`. |

---

## Next tasks for Kiro (priority order)

1. **Fix account deletion — make it actually complete (P0, launch-blocking).**
   - Audit the schema and delete **every** table keyed on `secret_id` or `device_id`, children before parents. At minimum add: `coordinates`, `map_requests`, `device_encryption_keys`, `dh_aes_keys`, `dh_server_keys`, `newsletter_server_keys`, and the consolidation tables.
   - **Resolve the identifier mapping first:** how do `secret_id`, `device_id`, and `consolidated_user_id` relate? Delete credentials by the **correct** key (likely join through `consolidated_user_id`/the device→user map), not by assuming `device_id == secret_id`.
   - Wrap in one explicit transaction with `try/except → conn.rollback()` and a `finally` that closes the connection (current code leaks the connection on error).
   - Delete object-storage blobs (`tour_blob_uri`, `news_blob_uri`) or document, in writing, that they auto-expire.
   - Re-test against a user that has tours, coordinates, map requests, articles, news, and saved credentials → every table returns `COUNT(*) = 0` and the call returns `200`.

2. **Correct the `decrypted_*` plaintext-credential posture (P0/P1).** Either implement the session-token model / encrypt-at-rest, or get explicit owner sign-off to launch with it — do not mark "acceptable" unilaterally.

3. **Attestation server scaffold, log-only (P1).** Build `/attest-nonce` + verification middleware + `ATTESTATION_ENFORCED` toggle now (default false). Lets the gateway validate Android/iOS tokens the moment Mobile-AQ emits them.

4. **Kill-switch Cloud Function (P1).** Write + deploy the function that drops cost services to `--max-instances=0` on the budget-100% Pub/Sub trigger. Hand Sir Michael the exact Console steps for budget + Pub/Sub creation.

5. **Run the verification gates (P1).** `test_news_quota_integration.py --test-db-down` (mandatory DB-down→503), `test_tour_quota_integration.py` (gates + `--run-generate` single-count + `--check-rollback`). Report pass/fail with output.

6. **Cloud Tasks (P2).** Confirm whether the queue is meant to exist for launch; if so, create it and verify `maxAttempts == MAX_TASK_ATTEMPTS`; if not, confirm prod runs thread-fallback intentionally.

7. **Cosmetic:** fix the "\$5.50" burn-rate figure (orchestrator cap is 10, not 5).

---

## Acceptance (restate before claiming deletion done)

- `DELETE /delete-account/<sid>` for a user with rows across **all** personal tables → `200`, and `SELECT COUNT(*)` on every such table (incl. credentials, coordinates, map_requests, dh/encryption keys) returns **0**.
- Non-existent `sid` → still `200` (idempotent).
- Forced DB error mid-delete → `500` **and full rollback** (verified, not assumed).
- Stored audio/tour blobs for the user are gone (or documented as auto-expiring).
- Reachable via `api.audioura.com` with the API key; `401` without. (Also confirm the gateway substitutes the `{secret_id}` upstream param — the route mixes `<secret_id>` and `{secret_id}` syntaxes; verify it forwards the real id, not a literal.)
