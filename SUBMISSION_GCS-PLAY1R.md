# SUBMISSION — GCS-PLAY1R

**Agent:** Services Kiro
**Branch:** `gcs-play1-android-upload` (bounce of GCS-PLAY1, fixed in place)
**Base:** `storied` = `7f2dd03`
**Branch tip before fix:** `c6a6ebb`
**Base check:** `git merge-base --is-ancestor 7f2dd03 HEAD` → exit 0 ✓

Two ledger defects in `tools/play_upload.py`, both reproduced by LEAD, are fixed.
Surgical scope: only `tools/play_upload.py`, `tools/tests/`, and `PLAY_UPLOAD.md`
wording were touched. `BUILD_NUMBERS.md` in the repo is **unchanged**. Uploaded
nothing; committed no Play edit; no Google Cloud changes.

---

## Defect 1 — ledger row appended outside the table  (`append_build_numbers_row`)

**Was:** opened `BUILD_NUMBERS.md` in `"a"` mode and wrote `"\n" + row + "\n"`, so the
row landed at the end of the file — after the closing prose paragraphs, outside any
table (LEAD saw the 26 row land after the Apple `MinimumOSVersion` paragraph).

**Now:** the row is inserted **inside the `## Ledger` table**:
- the function locates the `## Ledger` heading and the table rows in that section
  (bounded by the next `## ` heading);
- if a `NEXT` placeholder row is present (outcome cell equals `NEXT` after stripping
  `**`), the new row is inserted **directly before** it;
- otherwise the row is placed **after the last table row** of the section;
- **no existing row is modified**, including the `NEXT` placeholder — bumping `NEXT`
  stays the operator's choice;
- the file is read/written as UTF-8 with `newline=""` and re-joined with the file's
  **existing line ending** (the real ledger is CRLF; that is preserved, including on
  the inserted line);
- if there is no `## Ledger` heading, or the section has no table, it **raises
  `UploadError` with a clear message and leaves the file untouched** — it never
  appends blindly.

## Defect 2 — duplicate guard misreads "not uploaded"  (`build_numbers_has_android_upload`)

**Was:** any Android row whose outcome merely contained the substring `"upload"` was
treated as uploaded, so `| 23 | Android | … not uploaded to Play … |` would wrongly
refuse build 23.

**Now (exact rule, also stated in a code comment):** a row counts as uploaded only
if, after lower-casing and stripping `*` markdown, its outcome
- **contains** `"uploaded to play"` **or** `"shipped to play"`, **and**
- does **not** contain `"not uploaded"` **or** `"never shipped"`.

Matching is case-insensitive and ignores `**` emphasis.

---

## Acceptance criteria

### 1. Append against a verbatim copy of the real `BUILD_NUMBERS.md`
Fixture committed at `tools/tests/BUILD_NUMBERS.fixture.md` — a **byte-identical**
copy of the repo `BUILD_NUMBERS.md` (5444 bytes, CRLF; verified byte-for-byte).

- `test_append_inserts_before_next_placeholder_on_real_ledger`: the 26 Android row
  lands **immediately before** the `27 NEXT` row; exactly one line is added; removing
  the inserted line reproduces the original file **byte-identically** (endings
  included); the inserted line ends with `\r\n`.
- `test_append_no_ledger_table_errors_and_leaves_file_unchanged`: a file with no
  `## Ledger` table → `UploadError` mentioning "ledger", and the file bytes are
  unchanged.

### 2. Duplicate guard on the same fixture
`test_duplicate_guard_on_real_ledger` and `test_duplicate_guard_true_after_fixed_append`:
- Android **20** (`**shipped to Play closed testing**`) → **uploaded** ✓
- Android **22** (`never shipped`) → **not uploaded** ✓
- Android **23** (`not uploaded to Play`) → **not uploaded** ✓
- Android **26** (absent) → **not uploaded** ✓
- after the fixed append writes the 26 row → **uploaded** ✓

### 3. Tests + mutation proof
- **23 tests pass** (`py -m pytest tools/tests -q` → `23 passed`).
  - Prior total was 19. The previously-19th test `test_append_build_numbers_row`
    asserted the old blind-append contract against a header-only file with no
    `## Ledger` section; under the corrected contract that must now error, so the
    test was **updated in place** to use a minimal valid `## Ledger` table (still one
    test). Four new tests were added (the two append tests and two duplicate-guard
    tests above), giving 19 → 23.
- **Mutation proof still holds:** stubbing `check_version_not_used` to a no-op makes
  `run_upload(--apply)` proceed to commit a duplicate `26` — verified with a
  throwaway test that then failed with `DID NOT RAISE UploadError`. The throwaway
  file was deleted (not committed). The committed guard
  `test_removing_duplicate_check_would_be_caught` continues to document this.

### 4. Real dry run / repo `BUILD_NUMBERS.md`
- Repo `BUILD_NUMBERS.md` is **unchanged** (not in `git status`).
- The dry-run path reaches the expected **403** during the edit lifecycle
  (`edits.insert` / track resolution → `_translate_api_error`), which runs **before**
  any ledger interaction. `append_build_numbers_row` runs only after a real `--apply`
  commit, never in a dry run; `build_numbers_has_android_upload` returns the same
  answer for build 26 (absent in the ledger) before and after this change. So the
  dry-run behavior is unchanged by these edits.
- **Note:** no `audioura-release.aab` is present in this worktree and the live dry run
  needs gcloud impersonation + network, which is out of scope for this bounce
  ("upload nothing, no Google Cloud changes"). LEAD already verified the +26 signer/
  version-OK-then-403 dry run on GCS-PLAY1; nothing in this fix alters that pre-403
  flow. If a re-verification is desired, run from the repo root:
  `py tools/play_upload.py --notes "…"` (dry run is the default).

---

## Files changed
- `tools/play_upload.py` — Defect 1 and Defect 2 fixes.
- `tools/tests/test_play_upload.py` — updated one existing append test; added four tests.
- `tools/tests/BUILD_NUMBERS.fixture.md` — new, byte-identical copy of the real ledger.
- `PLAY_UPLOAD.md` — wording updated to describe insert-inside-table and the stricter
  duplicate rule.

Untouched as required: `BUILD_NUMBERS.md`, `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
`.continuous_dev/STATUS.md`, `GCLOUD_STORIED_START_HERE.md`.

## Blocking questions
None.
