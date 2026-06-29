# Claude Review — Account Deletion Verified + Next Tasks (Kiro, 2026-06-11)

**Reviewing:** Kiro's full 12-table deletion test result.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** **Account deletion is verified and closed.** The privacy-critical path is now proven, not claimed. One tiny residual (2 consolidation tables still not seeded) is optional. Prioritized next tasks below.

---

## Deletion — verified ✅

This run fixed the gap from last time. The sensitive tables were actually seeded and confirmed purged:
- `user_subscription_credentials` 1 → 0 (plaintext `decrypted_username`/`decrypted_password` gone)
- `dh_aes_keys`, `dh_server_keys` (private keys), `device_encryption_keys` 1 → 0
- `news_audios` 1 → 0
- `rows_removed: 10` matches the seeded count; idempotent re-delete → 200; FK order clean.

That was the one thing standing between "claimed" and "proven." It's now proven. Good.

**Residual (optional, not a blocker):** the 2 consolidation tables (`device_consolidation_history`, `user_consolidation_map`) were again not seeded — your seed script looked for `old_device_id`/`device_id`, but those tables key on **`consolidated_user_id`** (both have it; that's what the endpoint deletes by). So their DELETEs are valid SQL and won't error, but they remain un-exercised with a real row. Risk is low because: the column exists, and these tables only hold rows if multi-device consolidation is actually used. To fully close it: seed each with `consolidated_user_id = <test sid>` and confirm 1 → 0. Also confirm whether `secret_id` ever equals `consolidated_user_id` in production (edge C) — if consolidation isn't live, this is moot.

---

## Next tasks (priority order)

### 1. Run the DB-down → 503 test (mandatory, overdue)
`test_news_quota_integration.py --test-db-down` (T4) is the mandatory launch gate and still hasn't been reported as run. It's quick. Run it, confirm news returns **503** (not 500/200) when the DB is unreachable, and report the output. While you're there, confirm Cloud Tasks: does the queue exist for launch? If yes, verify `maxAttempts == MAX_TASK_ATTEMPTS`; if no, confirm prod is intentionally on thread-fallback.

### 2. Attestation server scaffold (log-only) — Mobile is done and waiting
The app side shipped and is approved (`v2.1.1+8`); the gateway side is the missing half of the v1 security gate. Build it now in **log-only** mode so nothing breaks:
- `/attest-nonce` endpoint + verification middleware + `ATTESTATION_ENFORCED=false` toggle.
- Validate Android tokens against Play Integrity and iOS against App Attest; log pass/fail, don't reject yet.
- **Nonce contract (agree with Mobile before you ever flip enforcement on):** the gateway must hash the **raw received HTTP body bytes** — do **not** re-parse and re-serialize the JSON. The app computes the nonce over the exact bytes it sends, so a raw-bytes hash matches; a re-serialized hash will false-`403` on key-order differences.

### 3. Kill-switch Cloud Function code — when the topic exists
Sir Michael is creating the budget + Pub/Sub topic in the Console (see `OWNER_ACTIONS_budget_and_credentials_2026_06_11.md`). Once he gives you the topic name, write + deploy the function that sets the cost-bearing Cloud Run services to `--max-instances=0` on the budget-exceeded message (surgical, **not** a full billing disable). Test it by publishing a fake over-budget message.

### 4. Blob / privacy-policy alignment (close the open item)
Check `PRIVACY_POLICY.html`: if it promises deleting "your tours/content," leaving the user's R2 tour blobs contradicts it. Either align the policy wording (tours are shared/public content) or delete the user's private blobs on account deletion. Document the final decision so it's defensible at review.

### 5. (Optional) Encrypt-at-rest decision follow-through
The `decrypted_*` plaintext-at-rest fix awaits Sir Michael's direction (session-token vs KMS envelope encryption — covered in the owner doc). Deletion now purges these columns, so it's no longer a hard blocker, but keep it on the checklist; when the decision lands, implementation is yours.

---

## Bottom line

Deletion is done — well verified this time. **Next up: run the mandatory DB-down test (#1), then build the log-only attestation scaffold (#2)** since Mobile's already waiting on it. #3 and #4 follow as the topic name and privacy-policy check come in.
