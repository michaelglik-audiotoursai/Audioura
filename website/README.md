# audioura.com share-link website (LOCAL-709 / D671)

These static files make `https://audioura.com/t/<CODE>` work:

- **With Audioura installed** → the OS opens the app (Android App Links / iOS
  Universal Links), which lands on Home → Search with the code filled in and the
  search already run.
- **Without the app** → this landing page appeals to the visitor and sends them
  to the right store, carrying the code so the app can pick it up after install
  (Android Install Referrer; iOS clipboard).

> **Publishing is Michael's / LEAD's step.** This directory lives in the repo
> only. Nothing here is pushed to audioura.com by the task.

## Files

| File | Purpose |
|------|---------|
| `.well-known/apple-app-site-association` | iOS Universal Links. JSON, **no file extension**. Declares appID `4HGRU6TKGQ.com.audioura.audiotours` handling paths `/t/*`. |
| `.well-known/assetlinks.json` | Android App Links. Declares package `com.audioura.audiotours` and the signing SHA-256 fingerprints allowed to verify the domain. |
| `t/index.html` | The landing page. Self-contained: no external scripts, no fonts, no tracking. Reads the code from the path and the tour name from `?n=`. Shows the name, an appeal, the code with a Copy button, and the store button(s). Works at 360px. |
| `_redirects` | Rewrites every `/t/<CODE>` to `/t/index.html` (status 200, URL preserved) so the page can read the code. |
| `_headers` | Serves both `.well-known` files as `Content-Type: application/json` (required for verification). |
| `screenshots/` | Landing-page screenshots at 390px and 1280px. |

## Before it works — two things to fill in

### 1. Play App Signing fingerprint (`assetlinks.json`)

`assetlinks.json` currently lists exactly ONE fingerprint — the **real** one, so
the published file is valid as-is:

1. `E6:2F:E3:…:62:28` — the **real** SHA-256 of the keystore that signs our
   release APK today (the project debug keystore at
   `audio_tour_app/android/app/debug.keystore`; verified against the built
   `app-release.apk` with `apksigner verify --print-certs`). This makes App
   Links verify for the APKs we sideload now.

Once the app is on Google Play, Play re-signs it with Google's own key, so that
key's fingerprint must ALSO be listed or App Links break for Play installs.

**Before uploading, add the Play App Signing SHA-256 as a SECOND array entry**
in the same colon-separated upper-case hex format (`^([0-9A-F]{2}:){31}[0-9A-F]{2}$`).

**Where to find it:** Play Console → **Test and release → App integrity → App
signing** → copy the **SHA-256 certificate fingerprint**.

The `sha256_cert_fingerprints` array should then read:

```json
"sha256_cert_fingerprints": [
  "E6:2F:E3:27:9B:67:F4:79:BD:78:6A:DD:0E:CC:9A:44:0E:61:46:3E:1A:E8:00:33:14:D9:F4:D5:C8:46:62:28",
  "<PASTE HERE>"
]
```

Do NOT commit a placeholder into `assetlinks.json`: a non-hex string risks
Android rejecting the whole statement. The file in the repo must hold only real
fingerprints; add the second one at upload time.

### 2. Store URLs (`t/index.html`)

Neither listing is public yet (both 404 on 2026-10-18). At the top of the page's
`<script>` there is ONE constant block:

```js
var STORE_URLS = {
  android: "",   // e.g. https://play.google.com/store/apps/details?id=com.audioura.audiotours
  ios: ""        // e.g. https://apps.apple.com/app/idXXXXXXXXXX
};
```

While a URL is empty, that store button reads **"Coming soon to Google Play /
the App Store"** and is disabled; the code and Copy button still work. Fill each
URL in at release — the page adds `&referrer=audioura_code%3D<CODE>` to the
Android URL automatically.

## Upload steps — Cloudflare Pages

The home page already lives on audioura.com (Cloudflare). Add these files to the
SAME Pages project so they sit at the site root:

1. Put the contents of this `website/` directory at the **root** of the Pages
   project (so paths resolve to `/.well-known/…`, `/t/…`, `/_redirects`,
   `/_headers`). Do **not** nest them under a subfolder.
2. Deploy (push to the Pages-connected branch, or drag-and-drop in the
   Cloudflare dashboard → Workers & Pages → the audioura.com project → Create
   deployment).
3. Verify after deploy:
   - `https://audioura.com/.well-known/assetlinks.json` returns the JSON with
     `Content-Type: application/json`.
   - `https://audioura.com/.well-known/apple-app-site-association` returns JSON
     (no extension, `Content-Type: application/json`).
   - `https://audioura.com/t/TESTCODE1?n=Hello` renders the page with the code
     `TESTCODE1` and headline "Hello".
4. Domain verification can take time: Android re-checks assetlinks periodically;
   iOS fetches the AASA on install/update. Until the files are live, the app's
   `autoVerify` / `applinks` will not verify and links fall back to this page in
   a browser — expected.

## Testing locally

Pure parsing logic has Node tests:

```bash
cd website/tests && node landing_page.test.js
```

Validate the association files are well-formed JSON:

```bash
python3 -m json.tool website/.well-known/assetlinks.json
python3 -m json.tool website/.well-known/apple-app-site-association
```

Preview the page (the path-based code needs a server, or use the `#` fallback):

```bash
cd website && python3 -m http.server 8000
# then open http://localhost:8000/t/index.html#/t/FFush25U?n=The%20Freedom%20Trail
```
