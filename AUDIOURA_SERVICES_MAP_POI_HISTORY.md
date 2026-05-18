# Audioura Services — Map POI Workstream
**Started:** May 15, 2026 (Session 11)
**Branch:** Newsletters
**Predecessor archive:** `AUDIOURA_SERVICES_SESSION_HISTORY_2026_05.md` (closed workstream; **do not load by default** into new sessions — only load if a specific debugging task crosses into tour-generation or translation internals)

This document is the portable carry-forward context for the map POI workstream. Paste it into a fresh session if more changes are needed — it should give a new Claude enough context to be useful without re-reading the closed-workstream history.

---

## Carry-forward facts from the closed workstream (Sessions 1–10)

Six structural facts from May 9–17 work are still load-bearing here. Everything else from that period — PHASE 3A/3B architecture, museum venue constraints, `_is_suspect` threshold tuning, file truncation recovery, translation hallucination fixes — is archived and not relevant to map work.

### 1. Service topology (Docker)

| Service | Container | Port | Role |
|---|---|---|---|
| `tour-orchestrator` | `development-tour-orchestrator-1` | 5002 | Mobile-facing; coordinates the pipeline; stores result in DB |
| `tour-generation-modernized` | `tour-generation-modernized-1` | 5021 | Splits assembled tour text into per-stop chunks; **generates `index.html`**; calls TTS; builds final ZIP |
| `translation-service` | `translation-service-1` | 5030 | Translates tour text and re-renders HTML/audio for non-EN languages |
| `polly-tts` | `polly-tts-1` | 5018 | AWS Polly wrapper |
| `tour-generator` | `development-tour-generator-1` | 5000 | Runs `generate_tour_text.py`; OpenAI calls (not touched by map work) |

### 2. Tour ZIP layout

Every delivered ZIP contains:
- `index.html` — the player UI loaded by Flutter's `flutter_inappwebview` WebView. **This is where map buttons live.**
- `audio_1.mp3 … audio_N.mp3` — TTS output, one per stop.
- `audio_1.txt … audio_N.txt` — per-stop metadata including the `Coordinates:` line used for map availability.
- `tour_content.txt` — assembled tour text.
- `manifest.json`, `service-worker.js` — PWA scaffolding.

### 3. Modernized vs legacy HTML paths in `translation_service.py`

There are two HTML rendering paths in translation, and **they behave differently for map buttons**:
- **`_create_mobile_compatible_zip()`** (~line 1140) — modernized path. Reuses the original English `index.html` and only edits `<h1>`–`<h6>` and `<p>` text via `h.clear(); h.append(NavigableString(...))`. Buttons that are siblings of the headings survive untouched.
- **`_generate_translated_html()`** (~line 1280) — legacy embedded-audio path. Regenerates HTML from scratch. **Would lose any baked-in buttons** unless the generator code is updated to emit them.

### 4. The `Coordinates:` keyword must stay in English in all `audio_N.txt` files

This was the Session 6 rule. `_NAV_LABEL_RE` matches all 5 nav-field labels; `_restore_metadata_labels` extracts the English `Coordinates:` / `Address:` lines from the original text and prepends them on top of the translated stop body. Tours 229 (ru) and 231 (zh) were affected before this fix. The map feature depends on this rule continuing to hold.

### 5. Deploy pattern

```bash
docker cp <file>.py <container>:/app/<file>.py
docker restart <container>
```

No container rebuild needed. After mobile confirms a bundle works, commit on the `Newsletters` branch.

### 6. Git state

Branch is `Newsletters`. Last pre-workstream commit `dc89045`. User has explicitly asked NOT to commit before mobile testing confirms each fix works end-to-end.

---

## Session 11 — A#55: Per-stop map buttons in `index.html` (May 15–17)

### Request (from iOS Amazon-Q, May 15)

Document: `services_request_a55_map_handler.md`.

The Audioura iOS app plays tours by loading `index.html` from the tour ZIP inside a `flutter_inappwebview` WebView. The app already has a full-screen map (`TourMapScreen`) that can open focused on any specific stop — it just needs to know which stop number to focus on. The request: add a map icon button next to each stop's audio player in the HTML; tapping it calls back to Flutter via `window.flutter_inappwebview.callHandler('openMap', {stop: N})`, and Flutter opens the map focused on stop N.

The contract is fire-and-forget: JS calls Flutter, Flutter does the work, no return value. Stop numbers are 1-based and match `audio_N.txt` numbering. Buttons are only added for stops that have coordinates. The `Coordinates:` keyword must stay in English in all `audio_N.txt` files (Session 6 rule, already enforced).

### Answers to iOS Amazon-Q's three questions

**Q1 (HTML structure around each stop's audio player):** in `tour_generation_modernized.generate_html_with_external_audio()` each stop is wrapped as `<div class="audio-item"><h3>Title: Audio N</h3><audio>…</audio></div>`. Room to add the button next to `<audio>` or after `<h3>`.

**Q2 (when is `index.html` generated):** once at tour creation time as a static string. Stop number can be hardcoded into the `onclick` — no JS loop needed at page load.

**Q3 (translated tours):** the modernized translation path (`_create_mobile_compatible_zip()`) reuses the original HTML and only edits heading and paragraph text — buttons survive untouched. The separate legacy `_generate_translated_html()` (~line 1280) regenerates HTML from scratch and would lose any baked-in buttons. Both paths need the button code if the bake-in design is kept.

### Three implementation suggestions (all accepted by Services Amazon-Q)

1. **Don't put the button inside the `<h3>` tag.** The translation path does `h.clear()` then `h.append(NavigableString(translated_text))` on every `h1`–`h6` — that wipes out any child elements, including a button. Put the button as a sibling of the `<h3>` (after it, inside the `audio-item` div), not inside it. Otherwise translated tours lose their map buttons.

2. **Use a single JS helper instead of inline `onclick`.** Inline `onclick="window.flutter_inappwebview.callHandler(...)"` works but is fragile (the browser or Android case will throw if `flutter_inappwebview` is undefined). One helper at the top of the page is cleaner and safer:

    ```html
    <script>
    function openMap(stopNum) {
      if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
        window.flutter_inappwebview.callHandler('openMap', {stop: stopNum});
      }
      // Silently noop in browsers / Android without handler — matches iOS doc's Rule 5
    }
    </script>
    ```

    Each button becomes `<button onclick="openMap(3)" …>🗺</button>`. Less duplicated code per stop, harmless on non-iOS platforms.

3. **Use the structured data, not a regex over text.** The request doc suggests checking `audio_N.txt` for `Coordinates:` to decide whether to render the button. In services we have the actual `poi['coordinates']` field — checking `if poi.get('coordinates')` is more reliable and matches the museum-tour rule (only stop 1 has coords, per `coords_eligible` logic). No regex over text needed.

### Minor concern: coordinate-detection regex on iOS

The request doc cites the iOS detection regex as `Coordinates:\s*[-\d.]+\s*,[-\d.]+` (no whitespace permitted after the comma). Services emits `Coordinates: 42.3294, -71.1922` (space after the comma). Likely the live regex is `,\s*` and the doc is a transcription drift, but worth verifying in iOS source — if the doc reflects what's in code, walking-tour stops 2+ will fail to be detected as map-eligible. Flagged in the Android compat doc.

### Open questions

**OQ-1 — RESOLVED (2026-05-18): Option B chosen.** Buttons are baked into `index.html`
at tour generation time by services. User explicitly instructed Services Amazon-Q to
build the map buttons, which constitutes the decision to take Option B over Option C.
Legacy tours (pre-600e0cd) will have no buttons — graceful degradation, not a crash.
See `services_response_a55_review_findings.md` for full rationale.

For reference, the three options that were under discussion:

- **A.** Polling-timer fallback for tours without buttons — leaves dead code paths on mobile, bifurcates UX between old and new tours.
- **B.** ✅ CHOSEN — Bake buttons into `index.html` at generation time. Services emits buttons; Flutter registers handler. Legacy tours have no buttons (graceful degradation).
- **C.** Flutter injects buttons at load time via `evaluateJavascript` — single mechanism for legacy and new tours, removes button-baking from services scope entirely.

**OQ-2 — Android compatibility.** The request doc's Rule 5 ("Works on iOS only") is misleading. `flutter_inappwebview.callHandler` is cross-platform; `addJavaScriptHandler` is plain Dart in `tour_player_screen.dart`. Whatever Android builds from that Dart, the handler runs on Android too. For Android to work without additional services-side or HTML changes, Android Amazon-Q must confirm: (1) Android uses the same `tour_player_screen.dart`; (2) Android has an equivalent map screen accepting `focusStopIndex`; (3) Android's WebView is `flutter_inappwebview` (not `webview_flutter`). All three appear present in the current Flutter codebase but need explicit confirmation before merge.

See `services_response_a55_android_compat.md` for the full cross-platform notes sent back to iOS Amazon-Q.

### State of fixes after Session 11

Nothing deployed yet. Services-side changes to `tour_generation_modernized.py` and `translation_service.py` are pending until OQ-1 (legacy tour strategy) is resolved. If Option C is chosen, services side has nothing to do beyond confirming `Coordinates:` stays English in translated `audio_N.txt` files (already true since Session 6).

---

## How to verify a map-related fix

1. Generate a new walking tour (English) via `POST /generate-complete-tour` on `localhost:5002`.
2. Poll `/status/<job_id>` until `completed` or `error`.
3. Extract the ZIP and confirm `index.html` contains either baked-in `openMap(N)` buttons next to each stop with coordinates (if Option A or B from OQ-1), OR no buttons at all (if Option C, where Flutter injects them).
4. Confirm `audio_N.txt` files contain `Coordinates: <lat>, <lon>` in English for stops that should be map-eligible.
5. Open the tour on iOS — tap a map icon for stop N — `TourMapScreen` should open centered on stop N with N's marker highlighted.
6. Repeat on Android — same behavior expected.
7. Generate a translated version (e.g. `"language": "ru"`) and verify buttons still appear and `Coordinates:` is still in English in `audio_N.txt`.
8. Open a museum tour — only stop 1 should have a button (other stops have no coordinates by `coords_eligible` logic).

---

## Files worth reading first in a new session

If a new Claude needs to understand this workstream, read in this order:

1. `services_request_a55_map_handler.md` — iOS Amazon-Q's original request and contract.
2. `services_response_a55_android_compat.md` — Services-side cross-platform / legacy-tour follow-up sent back to iOS.
3. `session11_a55_map_handler_draft.md` — Session 11 draft (mostly subsumed by this doc; kept for reference).
4. `tour_generation_modernized.py` — `generate_html_with_external_audio()` is where button baking would live for new tours.
5. `translation_service.py` — `_create_mobile_compatible_zip()` (modernized path, ~line 1140) and `_generate_translated_html()` (legacy path, ~line 1280).
6. `audio_tour_app/lib/screens/tour_player_screen.dart` — where the `openMap` handler registration would land.
7. `audio_tour_app/lib/screens/tour_map_screen.dart` — Flutter map target for `focusStopIndex`.

Do **not** load `AUDIOURA_SERVICES_SESSION_HISTORY_2026_05.md` by default — it covers a closed workstream and the only facts that survived are already in this doc's "Carry-forward facts" section. Reach for it only if a specific bug crosses back into tour-generation or translation internals.
