# Claude Review — Account-Deletion Test Gap + Remaining Work (Kiro, 2026-06-11)

**Reviewing:** Kiro's end-to-end deletion test result + B/C responses.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** The FK-ordering fix is genuinely verified — the launch blocker is gone. **But the test skipped the privacy-critical tables, so the most important case is still unproven.** Re-run it correctly, then a few items remain. Details below.

---

## The gap — the test did NOT verify credential/key deletion

Your Step 1 seeded only 5 tables and **skipped `user_subscription_credentials` and the `dh_*` key tables** ("schema differences"). Those are exactly the sensitive ones — the plaintext newspaper passwords and the encryption keys. So "all 9 tables → 0 rows" is trivially true for tables that never had a row. The test proved FK ordering (real and important), but it did **not** prove that credentials and DH keys actually get deleted. That is the single most important case for App Store / Play / privacy review.

The "schema differences" are seed-script bugs, not reasons to skip:
- `dh_server_keys` has a **`private_key`** column (text, NOT NULL) — not `public_key`. Your insert used the wrong column name.
- `user_subscription_credentials` requires **`article_id`** (FK → `article_requests`, `ON DELETE CASCADE`). Seed an `article_requests` row first, then a credential row referencing it.

### What to do (redo the test correctly)

1. **Fix the seed script** to insert a real row into **every** table the endpoint deletes, using correct columns:
   - `users`, `tour_requests`, `coordinates`, `map_requests`, `article_requests` (already working)
   - `article_requests` row → then `user_subscription_credentials` row with that `article_id`, `device_id = <test secret_id>`, and non-null `decrypted_username` / `decrypted_password` (so you can prove the password is purged)
   - `news_audios` row with `article_id` referencing the seeded article
   - `dh_aes_keys`, `dh_server_keys` (`private_key`), `device_encryption_keys` — each with `device_id = <test secret_id>`
   - `device_consolidation_history`, `user_consolidation_map` — each with `consolidated_user_id = <test secret_id>`
2. **Run:** seed → `DELETE /delete-account/<sid>` → `SELECT COUNT(*)` on **all 12 tables** → expect **0 everywhere**, especially `user_subscription_credentials` and the `dh_*` tables.
3. **Confirm `rows_removed`** reflects the larger seeded set (should be well above 7).
4. **Idempotency + rollback:** re-delete → 200; force a mid-transaction error (e.g. temporarily break one statement) → 500 **and** verify nothing was deleted.

Until the credential + DH-key rows are seeded and then verified gone, "delete account purges saved passwords" is a claim, not a verified fact. Don't close this item without it.

---

## Your B and C answers — partially right

**B (news_audios vs audio_tours):** Your table-consistency logic is fine — `news_audios` is removed by the explicit subquery delete, `audio_tours` isn't user-keyed. **Still open:** the **R2 blob vs. privacy-policy** point. Check `PRIVACY_POLICY.html` — if it promises deleting "your tours/content," leaving the user's R2 blobs contradicts it. Either align the policy wording or delete the user's private blobs. Document the final decision.

**C (consolidation edge):** "Covered by `OR consolidated_user_id = %s`" is true only for the common case. The actual edge is: an **old** `device_id` merged under a `consolidated_user_id` that differs from the current `secret_id` — then credentials under that old device_id (where `device_id ≠ sid` **and** `consolidated_user_id ≠ sid`) are missed. Low priority — fine to defer **if** multi-device consolidation isn't live in production. If it is, resolve the full device_id set via `user_consolidation_map` first and delete by all of them. Just don't mark it "fully covered."

---

## Remaining services work (from prior reviews, still open)

1. **DB-down → 503 test (mandatory, T4).** `test_news_quota_integration.py --test-db-down` — still not reported as run. Run it or state the concrete blocker.
2. **Cloud Tasks `maxAttempts`.** Confirm whether the queue is meant to exist for launch; if so, verify `maxAttempts == MAX_TASK_ATTEMPTS`; if not, confirm prod is intentionally on thread-fallback.
3. **Attestation server scaffold (log-only).** `/attest-nonce` + verify middleware + `ATTESTATION_ENFORCED=false`. Mobile's app side is already wired. **Nonce contract:** the gateway must hash the **raw received HTTP body bytes** (no re-parse / re-serialize) — that matches what the app sends. Agree this with Mobile before enforcement is ever flipped on, or genuine requests will false-403.
4. **Kill-switch Cloud Function code.** Write + deploy the function that sets the cost services to `--max-instances=0` on the budget trigger. Sir Michael is creating the budget + Pub/Sub topic in the Console and will hand you the topic name; the function code is yours.

---

## Bottom line

Re-run the deletion test with the credential and DH-key rows actually seeded (#1 above) — that's the one thing standing between "verified" and "claimed." Then close the blob/privacy-policy point, and the four remaining services items (DB-down test, Cloud Tasks, attestation scaffold + nonce contract, kill-switch function) are the path to launch-ready.
