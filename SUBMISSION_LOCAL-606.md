# SUBMISSION — LOCAL-606: a regenerated tour replaces stale stored content (D622)

**Branch:** `LOCAL-606-regenerate-replaces-stale`
**Base:** `subscribed` @ `ecf1c27` (verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

## Problem

`tour_orchestrator_service.store_audio_tour` deduped on
`lower(tour_name) WHERE original_tour_id IS NULL` (the LOCAL-156 unique index).
When a tour name already existed, it only did:

```
[LOCAL-156] Tour already exists (id=400). Incrementing number_requested; no new row needed.
```

So every **improved regeneration** of an existing tour name was discarded and the
stale content re-served. Harvard Art Museums (#400) kept its alphabetical,
pre-fix stops even after a corrected 6-stop text passed QA. This defeated every
content fix for any venue a user had asked about before.

## Rule implemented (D622)

In `store_audio_tour`'s existing-row branch:

- A **fresh/newly-assembled** delivery whose `tour_content` **differs** from the
  stored row (or where stored content was NULL) **replaces** the row's
  `tour_content`, `audio_tour` (ZIP blob), `zip_filename` and `stops_count`, and
  sets `lat`/`lng` **only if they are NULL** — all in a **single transaction**.
- Before replacing, the old row's `tour_content`, `zip_filename`, `stops_count`,
  `lat`, `lng` are archived into a new additive table
  `audio_tour_versions(tour_id, version_no, …, replaced_at, replaced_by_job)`,
  and the old ZIP on disk is renamed `<name>.v<N>.zip` — **never deleted**, so
  every replacement is reversible.
- Translations (`original_tour_id = this id`) are flagged
  `translation_stale = TRUE` so the next translation request regenerates them;
  they are not deleted.
- A **byte-identical** cache hit keeps the pre-606 behaviour: increment
  `number_requested`, no version row, no replacement.
- The **tour id and the share code stay the same** (we `UPDATE` the same row and
  never touch `shared_tours`), so curator links keep working and point at the
  improved tour.

### Files changed / added

| File | Change |
|------|--------|
| `tour_orchestrator_service.py` | Replace-on-change in the existing-row branch; new helpers `_ensure_versioning_objects` (self-healing DDL) and `_rename_superseded_zip`; `store_audio_tour` gains an optional `job_id` (recorded as `replaced_by_job`). |
| `migration/sql/017_audio_tour_versions.sql` | Explicit additive migration for `audio_tour_versions` + `audio_tours.translation_stale` (same objects the self-healing code creates). |
| `restore_tour_version.py` | Restore helper (`--dry-run` default / `--apply`). |
| `tests/test_local606_replace_on_change.py` | Five isolated tests. |
| `live_local606_driver.py` | In-container live-proof driver. |

Self-healing DDL mirrors the existing pattern in this function (audio_tour /
lat / number_requested / track / tour_kind): additive and idempotent, so the
code works on Cloud SQL, Mac Mini local dev, a fresh checkout, or a throwaway
test schema whether or not migration 017 has been applied.

## Restore helper

```
python3 restore_tour_version.py <tour_id> <version_no> --dry-run   # default
python3 restore_tour_version.py <tour_id> <version_no> --apply
```

`--dry-run` prints the exact current→restored field diff and touches nothing.
`--apply` snapshots the **current** row content as a new version first (so the
restore is itself reversible), then updates the live row in one transaction and
renames the archived ZIP back. No DELETE; id and share code untouched.
**It was not applied** against the live tour.

## Tests (throwaway schema, zero production writes)

`tests/test_local606_replace_on_change.py` drives `store_audio_tour` and
`restore_tour_version` **in-process** against a private throwaway schema via
`tests/_isolated_db.py` (`PGOPTIONS=-c search_path=<schema>,public`). Teardown
`DROP SCHEMA … CASCADE` and asserts `public` row counts identical before/after.

Cases: (1) differing text replaces the row, archives version 1 and renames the
old ZIP to `.v1.zip`; (2) byte-identical text only increments; (3) translations
flagged stale; (4) share code / tour id unchanged across replacement;
(5) restore `--apply` puts the old content back.

```
$ python3 -m pytest tests/test_local606_replace_on_change.py -v
tests/test_local606_replace_on_change.py::ReplaceOnChangeTest::test_1_new_text_replaces_and_archives_and_renames_zip PASSED
tests/test_local606_replace_on_change.py::ReplaceOnChangeTest::test_2_identical_text_only_increments PASSED
tests/test_local606_replace_on_change.py::ReplaceOnChangeTest::test_3_translations_flagged_stale PASSED
tests/test_local606_replace_on_change.py::ReplaceOnChangeTest::test_4_share_code_unchanged PASSED
tests/test_local606_replace_on_change.py::ReplaceOnChangeTest::test_5_restore_reverses_replacement PASSED
========================= 5 passed, 1 warning in 0.53s =========================

[LOCAL-606] public row counts before/after (must be identical):
  public.audio_tours          before=0        after=0
  public.shared_tours         before=0        after=0
[LOCAL-606] OK — zero shared/production writes.
```

## Live run (my own container only, cap $1)

- Built `local606-orch:latest` from this worktree (`Dockerfile.orchestrator`).
- Ran `docker run --rm --name local606-orch` on the shared `development_default`
  network, pointed at the real `audiotours` DB. **No `audioura-*` container was
  touched**; the only container used was `local606-orch` (now removed).
- `live_local606_driver.py` stored a **fresh `is_test` tour** (`lat/lng` NULL),
  then regenerated it with different text and a different stop count.
- **No LLM/TTS was called** (texts supplied directly), so the run cost ~$0, well
  under the $1 cap.

Result:

```
audio_tours COUNT BEFORE: 206
[gen1] inserted  id=401  stops=4  lat=None lng=None is_test=True
[gen2] replaced  existing_tour_id=401

=== LIVE ROW (after replace) id=401 ===
  tour_content : 'Generation two: improved 6-stop text after corrective.'
  zip_filename : 'local606_live_v2.zip'
  stops_count  : 6
  lat/lng      : None/None

=== ARCHIVED VERSION ROW for tour_id=401 ===
  v1: content='Generation one: alphabetical pre-fix stops (4).'
      zip='local606_live_v1.v1.zip' stops=4 lat/lng=None/None
      job=local606-live-gen2

[disk] old ZIP renamed to .v1.zip: True; original gone: True
audio_tours COUNT AFTER: 207  (delta=1, expected +1)
```

Restore demonstrated against the live tour (dry-run, **not applied**):

```
$ python3 restore_tour_version.py 401 1 --dry-run
RESTORE tour_id=401  version_no=1
  tour_content : 'Generation two: improved 6-stop text after corrective.'
               -> 'Generation one: alphabetical pre-fix stops (4).'
  stops_count  : 6 -> 4
  id and share code: UNCHANGED
[DRY-RUN] No changes written.
```

### Safety invariants verified

- New tour got **id=401** — the first id > 400, so **no Michael id (≤ 400)** was
  reused or modified. The only `audio_tour_versions.tour_id` is 401.
- `is_test = TRUE`, `lat/lng` NULL, as required.
- `audio_tours` row count: **206 → 207 (+1)** for the one new test tour.
- **No DELETE** anywhere; **no GCloud**; the superseded ZIP was renamed, not
  removed.

## Commits

| SHA | Step |
|-----|------|
| `4875050` | Replace-on-change rule in `store_audio_tour` + migration 017 |
| `360797d` | `restore_tour_version.py` helper |
| `806aad5` | Tests (throwaway schema, 5 passed) |
| `6f3b8fb` | Live-proof driver |
