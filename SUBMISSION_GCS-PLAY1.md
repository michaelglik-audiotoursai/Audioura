# SUBMISSION — GCS-PLAY1: one-command Android upload to Play closed testing

**Agent:** Services Kiro · **Base:** storied (`7f2dd03`) · **Branch:** `gcs-play1-android-upload`
**ClickUp:** none yet (LEAD files it). Requested by Michael, 2026-09-17.

**Nothing was uploaded to Play and no Play edit was committed.** Build 26's upload
remains Michael's to trigger with `--apply` after his Play Console invite.

---

## What was built

| File | Purpose |
|---|---|
| `upload_play.sh` | Bash wrapper (matches `upload_testflight.sh`: `set -euo pipefail`, fail fast). Creates the local venv, installs pinned deps, calls the Python tool. **Dry run by default.** |
| `tools/play_upload.py` | All logic: checks, keyless-impersonation auth, the `edits.*` lifecycle, dry-run, ledger append, CLI. Import-safe (offline tests import it). |
| `tools/aab_manifest.py` | Dependency-free reader of `versionCode`/`versionName` straight from the AAB's protobuf `AndroidManifest.xml` (no bundletool, no protobuf runtime). |
| `tools/play_upload_requirements.txt` | Pinned `google-api-python-client==2.198.0`, `google-auth==2.40.3`. Installed into `tools/.venv-play` (gitignored), never globally. |
| `tools/tests/test_play_upload.py` | 19 offline tests with the Play API fully mocked. |
| `PLAY_UPLOAD.md` | 3–6 line quick-start + the exact Play Console invite click-steps. |
| `PLAY_BUILD_AND_UPLOAD_RUNBOOK.md` | Added a pointer to the automation at the top. |
| `.gitattributes` | `*.sh text eol=lf` (scripts stay LF on Windows). |
| `.gitignore` | Ignore `tools/.venv-play/` and `.pytest_cache/`. |

Usage: `bash upload_play.sh [--apply] [--notes "<text>" | --notes-file <path>] [--aab <path>] [--track <name>]`

---

## Command semantics (per LEAD's design decisions)

1. **No downloadable key.** Auth is short-lived impersonation:
   `gcloud auth print-access-token --impersonate-service-account=play-publisher@… --scopes=…androidpublisher`,
   fed to the client as `google.oauth2.credentials.Credentials`. No JSON key is created or read.
2. **Dry run is default;** `--apply` required to commit. Dry run does `edits.insert` → skips
   `bundles.upload` → `edits.validate` (best-effort) → **`edits.delete`**. Never commits.
3. **Track resolved at runtime** from `edits.tracks.list` (production/beta/internal filtered out).
   More than one closed track → requires `--track`.
4. **Checks, each fail-fast:** (1) AAB exists; version read *from the AAB itself* must equal
   `pubspec.yaml`; (2) signer must be `CN=Mikhail Glik, O=Audioura LLC`, debug refused; (3) the
   versionCode must not already be on any Play track **and** must not be recorded as an uploaded
   Android row in `BUILD_NUMBERS.md`; (4) on `--apply`: insert → upload → `tracks.update`
   (`name="<versionName> (<versionCode>)"`, notes in `en-US`, `status=completed`) → commit, then
   print the Console URL; (5) on commit only, append the Android row to `BUILD_NUMBERS.md` and
   **print** the exact `git add … && git commit …` (the script never git-commits).

---

## One-time setup performed (reversible)

All three, and only these three, Google Cloud changes were made in `audiotours-migration`:

1. **Enabled the API** — `gcloud services enable androidpublisher.googleapis.com`
   → `Operation "…acat.p2-60899077572-…" finished successfully.`
2. **Created the keyless service account** —
   `gcloud iam service-accounts create play-publisher --display-name "Play Console publisher (no key)"`
   → `Created service account [play-publisher].`
3. **Granted token-creator on that SA only** (no project role) —
   `gcloud iam service-accounts add-iam-policy-binding play-publisher@… --member "user:michael.glik@gmail.com" --role "roles/iam.serviceAccountTokenCreator"`
   → policy now lists `user:michael.glik@gmail.com` with `roles/iam.serviceAccountTokenCreator`.

No project-level role granted. No key created. No deploy. No `DELETE` of any resource.

**Reversal if needed:** delete the SA (`gcloud iam service-accounts delete play-publisher@…`), which
removes the binding with it; and disable the API (`gcloud services disable androidpublisher.googleapis.com`).

### Play Console access — Michael must still do this (cannot be done from here)

Play Console → **Audioura** → **Users and permissions** → **Invite new user** →
`play-publisher@audiotours-migration.iam.gserviceaccount.com` → add app **Audioura** →
**Release to testing tracks** + **View app information** → send. Until then, a real API call 403s
(proven below). Steps are also written into `PLAY_UPLOAD.md`.

---

## Acceptance criteria — evidence

### 1. Offline tests with the API mocked — **PASS (19/19)**

`py -m pytest tools/tests -q` → `19 passed`. Covered: happy path commits with the right release
name/notes/track; duplicate versionCode refused (on-track and via ledger); debug signature refused;
pubspec mismatch refused; **dry run never calls `edits.commit`** (asserts no `commit`/`bundles.upload`
and that the edit is deleted).

**Duplicate-check mutation proof (required):** temporarily replacing the body of
`check_version_not_used` with `return` turned **4 tests red**, including
`test_apply_refuses_duplicate_before_upload` (which otherwise wrongly reached `edits.commit`):

```
FAILED tools/tests/test_play_upload.py::test_duplicate_versioncode_on_track_refused
FAILED tools/tests/test_play_upload.py::test_duplicate_versioncode_in_ledger_refused
FAILED tools/tests/test_play_upload.py::test_removing_duplicate_check_would_be_caught
FAILED tools/tests/test_play_upload.py::test_apply_refuses_duplicate_before_upload
4 failed, 15 passed
```

Restored → `19 passed`.

### 2. Signer + version checks run for real against today's `audioura-release.aab` (+26) — **PASS**

The bundle is a build artifact (gitignored `*.aab`); it is not in the repo tree but was located in
the shared build folder at `C:\Users\micha\eclipse-workspace\AudioTours\development\audioura-release.aab`
(dated 2026-09-17). Run through the tool's own check functions:

```
version ok: 2.3.2 + 26          # read from the AAB's protobuf manifest, equals pubspec 2.3.2+26
signer ok: CN=Mikhail Glik, O=Audioura LLC
```

`keytool -printcert -jarfile …` on the real bundle:
```
Owner: CN=Mikhail Glik, OU=Audioura, O=Audioura LLC, L=Newton, ST=Massachusetts, C=US
Valid from: Thu Jun 25 22:33:30 EDT 2026 until: Mon Nov 10 21:33:30 EST 2053
```
Debug-signature refusal is exercised by `test_signer_refuses_debug`.

> **Note on the AAB parser:** my first field-number guesses for the aapt XML proto were wrong and the
> parser failed on the real bundle — caught precisely because criterion #2 runs against the real
> artifact. Corrected against the live proto (element name = field 3; `versionCode`/`versionName`
> read from each attribute's plain-text value field). Now reads `2.3.2+26` correctly, and the
> synthetic-manifest unit test was updated to match the real schema.

### 3. Token path works; real API call 403s until the invite — **PASS**

- `gcloud auth print-access-token --impersonate-service-account=play-publisher@… --scopes=…androidpublisher`
  → **succeeds, token length 1024** (token value never printed).
- Full dry run against the real AAB (`bash upload_play.sh --notes "…" --aab …`) reached the API and
  returned the exact expected 403:

```
[ok] AAB version 2.3.2+26 matches pubspec
[ok] signer is CN=Mikhail Glik, O=Audioura LLC
[ok] impersonated access token acquired (length 1024)
ERROR: Play API returned 403 (The caller does not have permission).
<HttpError 403 when requesting
 https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.audioura.audiotours/edits?alt=json
 returned "The caller does not have permission".>
```

This proves the plumbing end-to-end up to authorization. It clears once Michael completes the Play
Console invite.

### 4. `BUILD_NUMBERS.md` unchanged by any test or dry run — **PASS**

`git status --short BUILD_NUMBERS.md` and `git diff --stat BUILD_NUMBERS.md` are both empty after all
runs. The ledger is only ever written by the script on a real `--apply` commit; the append format is
verified by `test_append_build_numbers_row`.

---

## Environment notes / decisions

- **Windows/Git Bash:** `encoding="utf-8"` on every file open; `*.sh` pinned LF via `.gitattributes`;
  `upload_play.sh` locates a venv Python under both `Scripts/` (Windows) and `bin/` (Ubuntu/Mac), and
  `get_access_token` resolves `gcloud.cmd` via `shutil.which` (Python `subprocess` can't exec the
  `.cmd` shim by bare name — fixed).
- **No bundletool dependency:** the version check parses the AAB's protobuf manifest directly, so the
  check needs nothing but Python and works identically on this laptop and on Ubuntu.
- Pinned dependency versions (exact `==`) for reproducibility; installed only into the local
  gitignored venv.

## Blocking questions / handoff

- **None blocking the build.** The only remaining step before build 26 can actually ship is Michael's
  one-time Play Console invite of the service account (criterion #3's 403 is the proof this is the last
  gate). After that: `bash upload_play.sh --notes "…" --apply` from the folder holding
  `audioura-release.aab`, then run the printed `git commit` for the `BUILD_NUMBERS.md` row.
- Per PROCESS, this branch is committed and pushed but **not merged**.
