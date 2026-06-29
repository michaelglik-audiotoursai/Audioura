# Audioura — Build & Play Upload Runbook

How to produce a signed Android App Bundle (`.aab`) and upload it to Google Play. Keep this for every future release.

App: **Audioura** · Package: **com.audioura.audiotours** · Build machine: **Ubuntu (VirtualBox)** · Shared folder: **/media/sf_audiotours** (= Windows `…\AudioTours\development`)

---

## One-time setup (already done — for reference / disaster recovery)

**Signing key.** The release is signed with an upload keystore created once:

```
cd /media/sf_audiotours/audio_tour_app/android/app
keytool -genkey -v -keystore audioura-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias audioura
```

- Keystore file: `audio_tour_app/android/app/audioura-upload.jks`
- Alias: `audioura`
- Certificate: `CN=Mikhail Glik, O=Audioura LLC` (RSA 2048, valid to 2053)

**`key.properties`** at `audio_tour_app/android/key.properties` (tells Gradle where the key is):

```
storePassword=<your password>
keyPassword=<your password>
keyAlias=audioura
storeFile=audioura-upload.jks
```

> ⚠️ **BACK THIS UP.** Copy `audioura-upload.jks` + the password into your password manager and a separate drive. With Play App Signing the upload key is resettable; without it, a lost key means you can never update the app. `key.properties` and `*.jks` are gitignored — never commit them.

---

## Every release — build steps

**1. Bump the version** in `audio_tour_app/pubspec.yaml` (the `version:` line, e.g. `2.1.1+18` → `2.1.1+19`). Play rejects a bundle whose versionCode isn't higher than the last upload.

**2. Pre-flight** (confirms the build source is current and your key is wired in) — in `/media/sf_audiotours`:

```
grep -c appbundle build_flutter_clean.sh                        # >= 1
grep -c audioura-release.aab build_flutter_clean.sh             # >= 1
grep applicationId audio_tour_app/android/app/build.gradle.kts  # com.audioura.audiotours
grep key.properties .gitignore                                   # a match (keeps key out of git)
ls audio_tour_app/android/app/audioura-upload.jks                # the keystore exists
ls audio_tour_app/android/key.properties                         # the properties exist
```

If any are missing, `git pull` in this folder, then re-check.

**3. Build:**

```
bash build_flutter_clean.sh
```

Watch for: `✓ Built …app-release.aab`, `✅ AAB copied to: /media/sf_audiotours/audioura-release.aab`, and **no** keystore/password or "Unresolved reference" errors.

**4. Locate the bundle.** It is **NOT** under `audio_tour_app/build/…` (that's the VM's temp dir). The script copies it out to the shared folder:

- **Windows:** `…\AudioTours\development\audioura-release.aab`
- **Ubuntu:** `/media/sf_audiotours/audioura-release.aab`

**5. Verify the signer** (confirm your real key, not the debug key):

```
keytool -printcert -jarfile /media/sf_audiotours/audioura-release.aab
```

Expect `Owner: CN=Mikhail Glik, O=Audioura LLC` — NOT `CN=Android Debug`.

---

## Upload to Google Play

1. Play Console → **Audioura** → **Test and release → Testing → Closed testing**.
2. **Create new release.**
3. If prompted, **accept Play App Signing** (recommended — Google holds the signing key; your `.jks` is the resettable upload key).
4. **Upload** `audioura-release.aab`.
5. Add **Release name** (e.g. `2.1.1 (18)`) and **Release notes** (see `PLAY_RELEASE_NOTES_v2.1.1+18.md`).
6. Confirm **testers** (email list or Google Group) and **countries/regions**.
7. **Review release → Start rollout to Closed testing.**

---

## Must be green before the release passes review (one-time, no build needed)

- **Developer identity verification** (Play Console left nav) — can take a day or two; start early.
- **App content** declarations: Data safety ✅, Target audience 13+ ✅, Ads = No ✅, Financial = No ✅, Health = No ✅, **Government = No**, **Advertising ID = No**, **News-apps** answer, **IARC content rating** questionnaire, **Privacy policy URL** (`https://audioura.com/privacy`).
- **Store listing** assets (in `store_assets/play/`): app icon 512×512, feature graphic 1024×500, 9 phone screenshots (1080×2160), short + full description (from `AUDIOURA_BETA_LAUNCH_KIT.md`).

---

## Quick troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Unresolved reference: util / io` in build.gradle.kts | Kotlin DSL scoping — needs `import java.util.Properties` + `import java.io.FileInputStream` at top, use unqualified `Properties()` / `FileInputStream(...)`. |
| Build signs with `CN=Android Debug` | `key.properties` not found/at wrong path → Gradle fell back to debug. It must be at `audio_tour_app/android/key.properties`. |
| Can't find the `.aab` | It's in the shared folder root (`…\development\audioura-release.aab`), not in `audio_tour_app/build/`. |
| Play: "versionCode already used" | Bump `version:` in `pubspec.yaml` and rebuild. |
| App 401s on cloud after install | The baked `GATEWAY_API_KEY` is wrong/empty in `build_secrets.env`. The gateway is correct; fix the app key, never open the gateway. |
