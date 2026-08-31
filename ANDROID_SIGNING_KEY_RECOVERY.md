# Android upload key — backup and recovery

**This document contains no secrets.** It tells you where the Android signing key lives
and how to restore it. The key material itself is in Google Cloud Secret Manager.

**Why this matters:** without the upload key you cannot publish an update to
`com.audioura.audiotours`. Depending on whether Play App Signing is enabled, losing it is
either an annoyance or unrecoverable — see *"How bad is losing it"* below.

---

## What the key is

| | |
|---|---|
| package | `com.audioura.audiotours` |
| alias | `audioura` |
| created | 2026-06-25 |
| valid until | **2053-11-10** |
| algorithm | SHA256withRSA |
| **SHA-1** | `14:A9:69:EA:CC:50:CD:DF:66:F2:36:0F:A9:E2:01:1A:5A:D1:40:A5` |
| **SHA-256** | `B3:AB:E5:FB:0E:C3:19:9A:05:A1:58:2C:21:A8:22:21:0F:A5:5F:DC:38:87:E2:5C:7D:42:25:13:51:ED:3A:64` |

**Those fingerprints are the identity check.** After any restore, compare against them. If
they do not match, the restored key is not the upload key and Google will reject the AAB.

## Where it lives

| copy | location | notes |
|---|---|---|
| **working** | `audio_tour_app/android/app/audioura-upload.jks` | gitignored (`android/.gitignore:14`), never committed |
| **working** | `audio_tour_app/android/key.properties` | gitignored (`android/.gitignore:12`), holds the passwords |
| **backup 1** | GCP Secret Manager `android-upload-keystore` | base64 of the `.jks` |
| **backup 1** | GCP Secret Manager `android-key-properties` | the properties file verbatim |
| **backup 2** | ⚠️ **not yet created — Michael to do** | see *"Second custodian"* |

Project: `audiotours-migration`. Both secrets are labelled `app=audioura,type=signing`:

```bash
gcloud secrets list --filter="labels.type=signing"
```

---

## RESTORE PROCEDURE

Run from the repo root. Requires `gcloud` authenticated against `audiotours-migration`.

```bash
# 1. Restore the keystore
gcloud secrets versions access latest --secret=android-upload-keystore \
  | base64 -d > audio_tour_app/android/app/audioura-upload.jks

# 2. Restore the passwords
gcloud secrets versions access latest --secret=android-key-properties \
  > audio_tour_app/android/key.properties

# 3. VERIFY — do not skip this
cd audio_tour_app/android
SP=$(grep '^storePassword=' key.properties | cut -d= -f2-)
AL=$(grep '^keyAlias=' key.properties | cut -d= -f2-)
keytool -list -v -keystore app/audioura-upload.jks -alias "$AL" -storepass "$SP" \
  | grep -E "SHA1:|SHA256:"
```

Step 3 must print the two fingerprints in the table above. **If it does not, stop** — do
not attempt an upload with a key that does not match.

`base64 -d` is GNU; on macOS use `base64 -D` (or `base64 --decode`, which works on both).

### Verified working

Round-tripped on 2026-08-31: restored from Secret Manager into a scratch directory,
confirmed **byte-identical** to the working copy, opened it with the restored password,
and both fingerprints matched. A backup that has never been restored from is not a
backup — re-run this check if the secrets are ever rotated.

---

## How bad is losing it

**Check first: Play Console → Test and release → App integrity → App signing.**
(It is *not* under a "Setup" menu; the console was reorganised.)

| Play App Signing | consequence of losing the key | recovery |
|---|---|---|
| **enabled** | Google holds the real signing key; this `.jks` is only the *upload* key | request an upload key reset through Play Console — annoying, recoverable |
| **not enabled** | this `.jks` **is** the app's identity | **unrecoverable.** New package name, new listing, all installs and reviews orphaned |

**This is worth confirming and recording here**, because it decides how much ceremony the
backup deserves. As of 2026-08-31 it has not been confirmed either way.

## Second custodian — still to do

Secret Manager sits inside the same Google account that a billing lapse or lockout would
take with it. **One copy in one blast radius is not a backup.** Recommended: an encrypted
archive attached to the password-manager entry for `michael.glik@audioura.com`, which is
the existing convention for this project.

Two independent custodians, not two copies in one place.

## Rules

- **Never commit the key.** `key.properties`, `*.jks` and `*.keystore` are gitignored;
  confirmed 2026-08-31 that none has ever been committed on any branch.
- **Never generate a replacement** to work around a missing key. A different key means
  Play rejects the upload as a different app. If the key cannot be found, stop and use
  the reset path above.
- **Never attach it to ClickUp.** Shared workspace, attachments visible to everyone with
  access, not a secret store.
- The Ubuntu build VM gets the key because `build_flutter_clean.sh` does `cp -r` of
  `audio_tour_app` from the shared folder, which copies gitignored files. If that script
  ever changes to a git-based copy, **the key will silently stop being present** and
  release builds will fail at `validateSigningRelease`.

## If you are reading this because the laptop died

1. Clone the repo. The key will **not** come with it — it is gitignored by design.
2. Run the restore procedure above.
3. Verify the fingerprints.
4. Recreate the second custodian copy, since you have just proved why it matters.
