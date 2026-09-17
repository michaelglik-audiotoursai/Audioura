# PLAY_UPLOAD.md — one-command Android upload to Play closed testing

Automates the manual Play Console upload (see `PLAY_BUILD_AND_UPLOAD_RUNBOOK.md`
for the full build steps). **Dry run is the default; nothing is uploaded without
`--apply`.**

## Quick start

```bash
# 1. Build on Ubuntu (writes audioura-release.aab to the shared folder):
cd /media/sf_audiotours && bash build_flutter_clean.sh

# 2. Dry run — runs every check, uploads nothing:
bash upload_play.sh --notes "What testers should know."

# 3. Publish (requires --apply and notes):
bash upload_play.sh --notes "What testers should know." --apply
```

Options: `--notes-file <path>` instead of `--notes`, `--aab <path>` to point at a
specific bundle (default `audioura-release.aab` in the repo root), `--track <name>`
if more than one closed track exists.

The script fails fast if: the AAB is missing, its version ≠ `pubspec.yaml`, it is
not signed with `CN=Mikhail Glik, O=Audioura LLC`, or the versionCode is already
used on Play (or already recorded in `BUILD_NUMBERS.md` as having reached Play —
a row that says e.g. "not uploaded to Play" or "never shipped" does NOT count).
On a real `--apply` commit it inserts the Android row **inside the `## Ledger`
table** (directly before the `NEXT` placeholder row, else after the last table
row), leaving every existing row — including `NEXT` — untouched, and prints the
exact `git commit` command — it never commits git itself.

## Auth — no key file

The script authenticates by **impersonating** a keyless service account
(`play-publisher@audiotours-migration.iam.gserviceaccount.com`); there is no
downloadable JSON key. You must be logged in as the account granted
`serviceAccountTokenCreator` on it:

```bash
gcloud auth login michael.glik@gmail.com
```

## One-time setup

Cloud side is already done (API enabled, keyless service account created,
`michael.glik@gmail.com` granted `roles/iam.serviceAccountTokenCreator` on that
service account only). **Michael must still invite the service account in Play
Console — a real API call returns 403 until this is done:**

1. Play Console → **Audioura**.
2. Left nav → **Users and permissions**.
3. **Invite new user**.
4. Email: `play-publisher@audiotours-migration.iam.gserviceaccount.com`
5. **Add app** → select **Audioura**.
6. App permissions: check **Release to testing tracks** and **View app information**.
7. **Invite user** / **Send invitation**.

(No project-level IAM role is needed and no key is created. To revoke access later:
remove the user in Play Console, and/or remove the token-creator binding with
`gcloud iam service-accounts remove-iam-policy-binding …`.)

## First-run local setup

`upload_play.sh` creates a local venv at `tools/.venv-play` (gitignored) and
installs the pinned deps from `tools/play_upload_requirements.txt` on first run.
Requires Python 3 and `keytool` (JDK) on PATH.
