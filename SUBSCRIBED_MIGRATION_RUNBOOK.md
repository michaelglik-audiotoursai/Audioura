# SUBSCRIBED_MIGRATION_RUNBOOK.md — migrations 010 → 050 on the shared Cloud SQL

**Task:** LOCAL-764 Task D · **Branch:** LOCAL-764-subscribed-cloud-readiness · **Base:** subscribed @ 1e740b0a
**Rulings:** D708 (Cloud SQL is SHARED by Beta/Storied/Subscribed; rows separated by `track`).

A dry-run report + apply runbook for `migration/sql/010 … 050`. Produced by
applying every file **twice** against a throwaway Postgres 15 container
(`local764-pg`, host port 55432, `-p local764`-style isolation) — **never the
shared DB**. Nothing was run against Cloud SQL by this task.

---

## 1. TL;DR for the operator

- All 43 migration files 010–050 apply **cleanly and idempotently** on a schema
  that already carries the storied base (001–009 + service self-heal), which the
  shared Cloud SQL does.
- **Two forward-only hazards** to respect (details in §4):
  - **024_price_tiers_6_7.sql is NOT re-runnable AFTER 026 has run.** Apply each
    migration exactly ONCE, in order. Re-running 024 after 026 fails with a CHECK
    violation (026 widened the tier range to 1..41 and added tiers 8..41; 024
    tries to re-narrow the CHECK to 1..7).
  - **033 / 034 (recovery-code) require the consolidation base tables**
    (`user_consolidation_map`, `device_consolidation_history`, `recovery_codes`)
    to exist first. They are created by the recovery/consolidation feature
    (service self-heal, pre-010), so they are already present on Cloud SQL. On a
    schema built from 010–050 alone they are missing and 033/034 error.
- **Mutating statements** (touch existing rows): 013 (backfills
  `device_entitlement`), 014 (admin level row), 038 (`DELETE` owner
  self-membership + grandfather free members), 041/043 (drop + replace the
  `audio_tours` name index). None deletes tour/user content; see §5 for the
  Beta/Storied blast radius.

---

## 2. Dry-run environment (reproducible)

```bash
# Scratch Postgres — isolated, spare port, NEVER the shared DB.
docker run -d --name local764-pg \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=postgres \
  -p 55432:5432 postgres:15
docker cp migration/sql local764-pg:/sql
bash local764_tooling/migration_dry_run.sh      # applies 010..050 TWICE
# teardown:
docker rm -f local764-pg
```

Apply order = `ls migration/sql/0[1-5]*.sql | sort`, i.e. numeric. The only
duplicate number is **021**, two independent, idempotent files; apply
`021_sync_offline_outbox.sql` then `021_tour_reviews.sql` (order is cosmetic —
neither references the other).

---

## 3. Dry-run result table (applied twice)

| File | Pass 1 | Pass 2 (idempotency) | Notes |
|---|---|---|---|
| 010_create_subscribed_database | ok | ok | bootstraps the whole base schema (IF NOT EXISTS / ON CONFLICT) |
| 011_add_newsletters_article_link | ok | ok | |
| 012_subscription_levels | ok | ok | creates `device_entitlement`, levels |
| **013_migrate_users_to_levels** | ok | ok | **MUTATING** — backfills `device_entitlement` from existing `users` (seed: 3 users → 3× l2) |
| **014_admin_level** | ok | ok | **MUTATING** — seeds an `admin` entitlement row |
| 015_l2_seats_queue | ok | ok | |
| 016_plan_display_level_codes | ok | ok | |
| 017_audio_tour_versions | ok | ok | |
| 018_audio_tours_source_version | ok | ok | |
| 019_tour_ratings | ok | ok | |
| 020_tour_listens | ok | ok | |
| 021_sync_offline_outbox | ok | ok | `sync_items`, `tour_review_sync` |
| 021_tour_reviews | ok | ok | `tour_reviews`, `review_helpful_votes` |
| 022_tour_price_tiers | ok | ok | tiers 1..5, CHECK 1..5 |
| 023_tour_downloads | ok | ok | |
| **024_price_tiers_6_7** | ok | **FAIL on re-run** | adds tiers 6,7; widens CHECK to 1..7. **Not idempotent after 026** — see §4.1 |
| 025_editor_score | ok | ok | |
| 026_price_ladder | ok | ok | tiers 8..41, widens CHECK to 1..41, `in_picker` flag |
| 027_content_rating | ok | ok | |
| 028_rescore_requested_version | ok | ok | |
| 029_communities | ok | ok | `communities`, `community_memberships`, `community_passes`, … |
| 030_document_acceptance | ok | ok | |
| 031_tour_unlock_consumption | ok | ok | |
| 032_tour_unlock_restore | ok | ok | |
| **033_recovery_code_portability** | **FAIL (base missing)** | ok¹ | needs `device_consolidation_history` — §4.2 |
| **034_recovery_code_lookup_selector** | **FAIL (base missing)** | ok¹ | needs `recovery_codes` — §4.2 |
| 035_community_tours | ok | ok | |
| 036_organiser_step_down | ok | ok | |
| 037_community_launch_window | ok | ok | adds `archived_reason` CHECK |
| **038_community_dollar_minimum_and_member_count** | ok | ok | **MUTATING** — `DELETE` owner self-membership; grandfather free members 30d; flip free→paid. No-op on clean data (0 memberships). §5 |
| 039_article_char_limit | ok | ok | |
| 040_short_title | ok | ok | |
| **041_tour_creator** | ok | ok | **MUTATING DDL** — adds `creator_user_id`; DROPs `uq_audio_tours_original_name`; adds non-unique `idx_audio_tours_name_creator`. §5 |
| 042_tour_reports | ok | ok | |
| **043_tour_track** | ok | ok | **MUTATING DDL** — adds `track`; DROPs `idx_audio_tours_name_creator`; adds `idx_audio_tours_name_creator_track`. §5 |
| 044_community_blocks | ok | ok | |
| 045_community_reports_triage | ok | ok | |
| 046_admin_moderation | ok | ok | |
| 047_reimbursement | ok | ok | |
| 048_community_release_cadence | ok | ok | |
| 049_organiser_audio_tours | ok | ok | |
| 050_community_episode_metadata | ok | ok | |

¹ 033/034 verified idempotent (applied twice, both clean) **after** the three
consolidation base tables were pre-created as the service self-heal does:
`user_consolidation_map`, `device_consolidation_history`, `recovery_codes`
(DDL from `recovery_code_service.py`). On Cloud SQL those already exist.

**Row counts — unchanged between Pass 1 and Pass 2** (idempotency holds for data):

| table | after Pass 1 + seed | after Pass 2 |
|---|---|---|
| users | 3 | 3 |
| audio_tours | 1 | 1 |
| plans | 9 | 9 |
| communities | 0 | 0 |
| community_memberships | 0 | 0 |
| tour_reviews | 0 | 0 |
| sync_items | 0 | 0 |

Post-run structural checks (verified):
- `audio_tours` has `creator_user_id` (041) and `track` (043).
- `uq_audio_tours_original_name` is **gone**; `idx_audio_tours_name_creator` is
  **gone** (superseded); only `idx_audio_tours_name_creator_track` remains.
- `device_entitlement` after 013+014: 3× `l2`, 1× `admin`.
- 55 tables in `public`.

---

## 4. Forward-only hazards

### 4.1 — 024 is not re-runnable after 026 (apply each migration ONCE)

`024_price_tiers_6_7.sql` runs:
```sql
ALTER TABLE price_tiers DROP CONSTRAINT IF EXISTS price_tiers_tier_check;
ALTER TABLE price_tiers ADD CONSTRAINT price_tiers_tier_check CHECK (tier >= 1 AND tier <= 7);
```
`026_price_ladder.sql` later inserts tiers **8..41** and widens the CHECK to
`1..41`. If 024 is then re-applied, re-adding `CHECK (tier <= 7)` fails:
`check constraint "price_tiers_tier_check" is violated by some row`.

**Operator rule:** apply the sequence forward-only, each file exactly once. The
individual files are internally idempotent; the *sequence* is not safe to replay
past 024 once 026 has run. A migration tracker table (recording applied
versions) is the right mechanism; absent one, apply the range once.

### 4.2 — 033 / 034 need the consolidation base tables

033/034 do `ALTER TABLE device_consolidation_history …` and
`… recovery_codes …`, assuming the tables exist. They are created by the
recovery/consolidation feature (`recovery_code_service.py` self-heal; pre-010
base). The shared Cloud SQL already has them. **Before applying 033/034 to any
schema built from 010 alone, ensure the base exists** (run the service once, or
apply origin/storied `migration/sql/001…009` + the self-heal). Verified: with
those three tables present, 033 and 034 apply cleanly twice.

---

## 5. Beta / Storied blast radius (shared DB, D708)

| Migration | Statement | Effect on Beta/Storied |
|---|---|---|
| 013 | INSERT backfill into `device_entitlement` | Additive. Gives existing Beta/Storied users an entitlement row; does not change `users` or tours. Safe. |
| 038 | `DELETE FROM community_memberships` (owner self-membership) + grandfather free members + flip free→paid | Touches COMMUNITY data only. Owner self-membership rows should never have existed (cleanup); free communities (demo book club) become paid with current members grandfathered 30 days. No tour/user deletion. Safe for Beta/Storied (they use the same community tables; the rule is intended). |
| 041 | DROP `uq_audio_tours_original_name`; ADD non-unique `idx_audio_tours_name_creator` | **Removes the global tour-name uniqueness.** After this, two creators (or two tracks) CAN hold the same `lower(tour_name)` — i.e. Beta *could* create a duplicate name. This is intended (D678): the orchestrator's save path no longer relies on the DB unique index; it scopes the "existing tour" lookup by `(lower(tour_name), creator_user_id)` in code. **Prerequisite: the orchestrator code change (D678) MUST be deployed before/with this migration**, or a same-name regenerate would insert a new row instead of versioning. LEAD applies 041 after the code is merged. |
| 043 | DROP `idx_audio_tours_name_creator`; ADD `idx_audio_tours_name_creator_track` | Extends the 041 lookup key with `track`. Fixes bug 432 (Beta and Storied tours with the same name + creator collapsing into one row). Requires the orchestrator's track-scoped lookup (self-heals the `track` column). Beta rows default `track='beta'` — correct for pre-Storied data. Safe. |

**Does 041 let Beta create duplicate names?** Yes at the DB level — the unique
index is gone. But Beta's *code* (post-D678) never relies on that index to
de-dup; it versions by creator. So in practice Beta does not produce duplicate
user-visible tours, provided the D678/D708 orchestrator code is deployed with
041/043. If 041 were applied WITHOUT that code, a same-name regenerate would
create a second row. **Apply order rule: code first (or together), then 041/043.**

---

## 6. Apply procedure (Cloud SQL)

```bash
# 0. BACKUP FIRST (shared DB — mandatory). Either an on-demand Cloud SQL backup:
gcloud sql backups create --instance=<INSTANCE> --project=<PROJECT> \
  --description="pre-LOCAL-764 010-050"
#    …or a logical dump of the subscribed-affected tables:
pg_dump "host=<CLOUD_SQL_HOST> dbname=<DB> user=<USER>" \
  -t audio_tours -t price_tiers -t communities -t community_memberships \
  -t device_entitlement -t recovery_codes -Fc -f pre_local764_010_050.dump

# 1. Confirm the consolidation base exists (required by 033/034):
psql "<DSN>" -c "\dt device_consolidation_history recovery_codes user_consolidation_map"

# 2. Deploy the orchestrator code (D678/D708 creator+track-scoped lookup) FIRST,
#    so 041/043 dropping the name index is safe. (Code deploy is out of scope of
#    this task; this is the ordering note for LEAD.)

# 3. Apply 010..050 forward-only, each exactly once, in numeric order
#    (021: sync_offline_outbox then tour_reviews). Stop on first error:
for f in $(ls migration/sql/0[1-5]*.sql | sort); do
  echo ">> $f"; psql "<DSN>" -v ON_ERROR_STOP=1 -f "$f" || { echo "STOP at $f"; break; }
done
```

### Verification query per migration (spot checks)

| Migration | Verify with |
|---|---|
| 010 | `SELECT count(*) FROM plans;` ≥ 3 seed rows |
| 012/013 | `SELECT level, count(*) FROM device_entitlement GROUP BY 1;` |
| 014 | `SELECT 1 FROM device_entitlement WHERE level='admin' LIMIT 1;` |
| 019 | `\d tour_ratings` |
| 021×2 | `\dt sync_items tour_review_sync tour_reviews review_helpful_votes` |
| 022/024/026 | `SELECT min(tier), max(tier) FROM price_tiers;` (expect 1 and 41 after 026) |
| 024 CHECK | `SELECT conname FROM pg_constraint WHERE conname='price_tiers_tier_check';` (CHECK 1..41 after 026) |
| 029 | `\dt communities community_memberships community_passes` |
| 033/034 | `\d recovery_codes` has `code_lookup` selector + partial unique index |
| 038 | `SELECT count(*) FROM community_memberships m JOIN communities c ON c.id=m.community_id AND c.owner_user_id=m.user_id;` = 0 (no owner self-membership) |
| 041 | `SELECT 1 FROM pg_indexes WHERE indexname='uq_audio_tours_original_name';` = **0 rows** (dropped); `creator_user_id` column present |
| 043 | `SELECT indexname FROM pg_indexes WHERE tablename='audio_tours' AND indexname='idx_audio_tours_name_creator_track';` = 1 row; `track` column present |
| 046/047 | `\dt admin_actions reimbursements` |
| 050 | `\d community_episodes` |

---

## 7. Rollback notes

- **Preferred:** restore the pre-change Cloud SQL backup / `pg_restore` the dump
  from §6 step 0. The schema changes are almost entirely additive, so a forward
  roll-forward fix is usually cleaner than a restore.
- **Per-migration reversibility (the DDL that is NOT purely additive):**
  - **041** — restore the dropped unique index exactly:
    `CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tours_original_name ON audio_tours(lower(tour_name)) WHERE original_tour_id IS NULL;`
    (only safe if no duplicate names exist yet — check first).
  - **043** — restore the 041 index:
    `CREATE INDEX IF NOT EXISTS idx_audio_tours_name_creator ON audio_tours(lower(tour_name), creator_user_id) WHERE original_tour_id IS NULL;`
    then drop `idx_audio_tours_name_creator_track` if desired.
  - **038** — the `DELETE` of owner self-membership and the free→paid flip are
    data mutations; there is no automatic reverse. Restore from backup if the
    grandfather window / paid flip must be undone.
  - **024/026** — CHECK-constraint widenings are reversible only if the rows fit
    the narrower range; after 026 added tiers 8..41 you CANNOT re-narrow to 1..7
    without deleting those rows first (this is the §4.1 hazard).
- Additive `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` migrations
  need no rollback to keep Beta/Storied working — the columns/tables they add are
  ignored by code paths that do not use them.

---

## 8. Safety statement

This dry run used a dedicated scratch container (`local764-pg`, port 55432) and
never connected to the shared Cloud SQL or any `audioura-*` stack. No GCloud
command was run. The container is torn down with `docker rm -f local764-pg`.
