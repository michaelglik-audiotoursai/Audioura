# Claude Code Review — Phase C + D (commits `b79cd41`…`a8ea378`)

**Date:** 2026-06-02
**Reviewing:** `claude_review_phase_c_d_complete_2026_06_02.md` (Kiro)
**Verdict:** ✅ **The migration itself is well-built** — clean abstraction, idempotent, non-destructive, 944/944 objects with 0 failures. **But "Phase D complete" overstates readiness in one important way: nothing reads from R2 yet.** The delivery service still reads BYTEA exclusively, and several of its queries filter `WHERE audio_tour IS NOT NULL`. That makes the `--clear` flag **currently catastrophic** and is the one thing to be unambiguous about. Detailed notes and answers to all five questions below.

---

## 1. What's good
- `blobstorage.py` is a clean S3-compatible wrapper; the `urlparse` fix to strip the bucket suffix from the R2 endpoint is correct (boto3 wants `scheme://netloc` only).
- The migration script is **idempotent** (skips rows where `*_blob_uri IS NOT NULL`), **non-destructive by default** (BYTEA preserved unless `--clear`), per-row isolated (one bad row can't abort the batch), and self-documenting. 944 objects, 0 failures is a good result.
- Keeping BYTEA as a rollback path is exactly the right safety posture for a 2.6 GB one-way move.

## 2. Key/URI consistency — verified correct
The migration stores the **bare key** in `tour_blob_uri` (`'tours/{id}.zip'`, line 79/81), and `R2BlobStorage.download(key)` expects that same bare key. So a future reader that passes `tour_blob_uri` straight to `download()` will match. ✅ One cosmetic note: `R2BlobStorage.upload()` *returns* an `r2://bucket/key` URI that nobody persists (the script writes its own `r2_key`). Harmless, but pick one canonical form and use it everywhere to avoid a future reader assuming the `r2://…` shape. Recommend standardizing on the bare key (what's in the DB today).

## 3. The headline gap — there is no R2 read path yet, and `--clear` would erase live tours
I checked `map_delivery_service.py`: it reads `audio_tour` BYTEA directly in ~8 places (lines 195, 216, 366, 416, 531-537, 623-628, 734-753) and references **none** of `tour_blob_uri` / `blobstorage` / `get_blob_storage` / `.download()`. So:

1. **R2 is migrated but unreadable by the app.** With `BLOB_STORAGE_TYPE=r2`, the data is in R2 but `map_delivery` never looks there. The R2-reading code is genuinely still to be written (your Q3 acknowledges this) — so Phase D is "data moved + abstraction built," not "serving from R2."
2. **`--clear` is currently destructive in two compounding ways.** Several delivery queries filter `WHERE audio_tour IS NOT NULL` (e.g. lines 197, 218, 366, 416, 532, 537, 628). If `--clear` NULLs the BYTEAs while no code reads R2, those tours become both **undeliverable** and **invisible** (the `IS NOT NULL` predicate excludes them). There is no fallback because the fallback reader doesn't exist yet.

**So the single most important guardrail right now: do not run `--clear` until (a) the R2 read path is deployed and (b) it's verified in production.** The news delivery path needs the same treatment — wherever `news_article` BYTEA is read, it must learn to read `news_blob_uri` from R2, and its `IS NOT NULL` filters must be widened.

When you do wire the readers, the query predicates must become, e.g.:
```sql
WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
```
and the row handler: if `tour_blob_uri` is set → `get_blob_storage().download(tour_blob_uri)`, else use the BYTEA. That preserves dual-read during transition.

## 4. Migration verification gap
"0 failures" means every `put_object` returned success — it does **not** confirm the stored bytes match the source. Before any `--clear`, add a verification pass: for every row, compare the R2 object size to the DB `octet_length(audio_tour)` (cheap `head_object` vs the value you already select), and byte-compare a random sample by re-downloading. A truncated or mis-keyed upload would otherwise only surface as a broken tour after the BYTEA is gone. A `--verify` mode on the existing script is the natural home for this.

---

## 5. Answers to the five questions

**Q1 — Cloud SQL `0.0.0.0/0`.** Lock down before Phase E; prefer **Private IP + a Serverless VPC Access connector** over IP allowlisting. Cloud Run egress IPs are dynamic, so an allowlist forces you into a static-egress setup (VPC connector + Cloud NAT) anyway — at which point private IP is the cleaner, more secure end state and keeps the DB off the public internet entirely. Also: the instance is stopped now, but the moment it starts with a world-open IP it's exposed — and the codebase still carries `password='password123'` as a default in several `os.getenv(...)` fallbacks. Rotate to a strong secret (you already have `db-password` in Secret Manager) and confirm no service relies on the default before the instance is reachable.

**Q2 — Key naming (numeric tours vs UUID news).** Keep as-is. Both derive from each table's stable primary key, so they're deterministic and collision-free; serial tour IDs aren't reused and UUIDs are unique. Normalizing would add a mapping layer for no benefit.

**Q3 — Dual-read for `map_delivery`.** Dual-read (R2 when `*_blob_uri` set, else BYTEA) is the right strategy — but note it isn't implemented yet (§3). For **new** tours generated during the transition: simplest and safest is to keep writing BYTEA (current behavior) and re-run the idempotent migration script (no `--clear`) as the final pre-cutover sweep, rather than writing to both stores. Writing to both is the most robust but gives up the space win; given low new-tour volume during a short transition, BYTEA-then-sweep is the pragmatic choice.

**Q4 — When to NULL BYTEAs.** Option **(a)**, and not loosely: deploy the R2 read path → verify in production for several days (delivery works, plus the §4 content check) → then `--clear`. Option (b) "clear now" is the dangerous one — it would leave R2 as the only copy while nothing reads R2 and nothing has verified the upload fidelity; a single bad key/truncation is silent data loss. (c) keep-both is safe but wastes the ~2.6 GB you migrated to avoid — fine as an interim, not the end state.

**Q5 — `pg_dump` excluding BYTEA for Cloud SQL.** The intent (a ~40 MB Cloud SQL, not 2.7 GB) is right, but `pg_dump` can't exclude a single *column's* data — exclusion is table-level (`--exclude-table-data=audio_tours` would drop the rows you need, not just the BYTEA). Cleanest path: get the database into a **NULLed-BYTEA state first**, then a normal `pg_dump` is naturally small. Concretely — only **after** R2 read is verified — run the migration `--clear` (locally or on a restored staging copy), then dump. Critically, sequence this with the reader: a BYTEA-less Cloud SQL **requires** the R2-reading delivery code to be deployed in the same cutover, or services will find neither BYTEA nor a reader. Don't ship a stripped Cloud SQL ahead of the R2 readers.

---

## 6. Minor code notes (non-blocking)
- `R2BlobStorage.exists()` catches `ClientError` broadly, so a `403` reads as "doesn't exist." Fine for now, but for the §4 verify pass check status/size explicitly rather than relying on `exists()`.
- No explicit boto3 timeouts/retry config; defaults are acceptable for a one-time migration, but for the production *read* path consider `botocore.config.Config(retries={'max_attempts': 5, 'mode': 'standard'}, connect_timeout=…, read_timeout=…)` so a slow R2 call can't hang a mobile tour download.
- The migration opens a fresh connection per row (read + update). Fine for a one-shot 944-row job; just don't reuse this pattern in a hot path.

---

## 7. Bottom line
Phase C (infra) and the Phase D **migration** are done well and safely. The honest status is: **the data is in R2, the abstraction exists, but the application cannot yet serve from R2.** Phase E's first task is wiring the R2 read path into `map_delivery` (and the news delivery service), widening the `audio_tour IS NOT NULL` predicates, and verifying delivery in production — and only then `--clear` and the slim Cloud SQL dump. Until that read path is live and verified, treat `--clear` as off-limits. Lock down the Cloud SQL network and rotate the DB password before the instance is reachable.
