# SUBMISSION — Yury's Beta bugs

Branch: `fix/yuri-audio-and-map` (cut from `main` = Beta)
Session: `Beta_Bugs`, 2026-08-17
Reporter: Yury Makedonov (`101707192`), ClickUp DM channel `2ky4d0u8-919`, 2026-08-15
Yury's tour: **"Toronto Ravines And Other Green Spaces"** (not present on this machine)

---

## BETA-1 — two audios play concurrently — `wdvrdaxmq2`

### Verdict: `CONFIRMED`

Reproduced against a real generated tour, not by inspection alone.

### Where it actually lives — not where the task assumed

The task said *"Likely area: the audio player controller in `audio_tour_app/lib/`"*.
**That is not where the bug is.** The tour player is a thin wrapper: `tour_player_screen.dart`
loads `index.html` from the tour folder into an `InAppWebView`. The stop list, the
`<audio>` elements and their numbering are **generated HTML shipped inside each tour**,
produced by the Python generator. No Dart change was needed or made.

### Root cause

Every generated tour page registers this listener
(`tour_generation_modernized.py:262-272`, and the same block in
`translation-service/translation_service.py`):

```js
audioElements.forEach((audio, index) => {
    audio.addEventListener('play', function() {
        currentStopIndex = index;      // records which stop is playing
    });                                // ...and nothing else
});
```

It records the current stop but never pauses the others. Independent HTML5 `<audio>`
elements play concurrently by default, so tapping play on a second stop leaves the
first one running.

Logic that *does* pause the others exists only in `window.playAudio()`, which is
reachable **through voice control only** — not from the native `<audio controls>` play
button Yury tapped. That is why the bug is invisible to voice users.

This is an omission against an existing convention, not a design choice. The correct
pattern is already present in `translation_service.py` (its other generator),
`build_web_page.py`, `news_processor_service.py`, `multi_tour_app_builder.py`,
`simple_app_builder.py` and `tracked_app_builder.py`. Only the main generator lacked it.

### The fix

Commit `144ca98`. Five lines in each of two generators, copying the established pattern:

```js
audio.addEventListener('play', function() {
    audioElements.forEach((otherAudio, otherIndex) => {
        if (otherIndex !== index && !otherAudio.paused) {
            otherAudio.pause();
        }
    });
    currentStopIndex = index;
});
```

### How it was proved — before/after on a real run

Artifact: `tours/test_walking_tour_boston_walking_401641c9.zip`, a genuine 3-stop tour
with its real MP3s — unmodified. Run in headless Chrome with
`--autoplay-policy=no-user-gesture-required`, matching the app's
`mediaPlaybackRequiresUserGesture: false` (`tour_player_screen.dart:94`).

The probe calls `.play()` on stop 1, waits 800 ms, calls `.play()` on stop 3, then reads
the `paused` state of every element. Tapping the native play button does exactly this.

| | audio1 | audio2 | audio3 | concurrent |
|---|---|---|---|---|
| **Before** (shipped generator) | PLAYING | PAUSED | PLAYING | **2** |
| **After** (fixed generator) | PAUSED | PAUSED | PLAYING | **1** |

The "after" page was produced by calling the patched
`generate_html_with_external_audio()` itself, inside the service's own container — not
by hand-editing HTML.

Per §6, the failing direction is real: the identical probe returns `CONCURRENT_COUNT=2`
against the unfixed generator and `1` against the fixed one, so the check genuinely
distinguishes the two trees.

### Acceptance criteria

1. **Met** — starting stop B while A plays pauses A; one stream at a time.
2. **Met by construction** — the listener is symmetric across all elements, so direction
   (forward/backward) is irrelevant. Re-tapping the already-playing stop is a no-op
   because the guard skips `otherIndex === index`.
3. **Met** — pause/resume untouched; only a pause of *other* elements was added.
4. **Not applicable** — there is no background playback or lock-screen integration;
   audio is `<audio>` inside a WebView. Nothing in that path was modified.

### ⚠️ Deployment consequence — read before asking Yury to retest

The fix is in the **generator**, so it applies to **newly generated tours only**.
Tours already downloaded to a device keep the HTML they shipped with. Yury's existing
"Toronto Ravines And Other Green Spaces" tour will **still play two audios** after this
change.

**Yury must generate a NEW tour to verify.** Retesting the old tour will look like the
fix failed. A Flutter-side JS injection would have fixed already-downloaded tours too;
Michael chose generator-only on 2026-08-17.

---

## BETA-2 — audio/map numbering off by one — `wdvrdaxmq3`

### Verdict: `UNPROVEN — could not reproduce on available data`

Not `NOT REPRODUCIBLE`: I could not obtain the tour Yury used, so his claim is neither
confirmed nor refuted. Handed to Michael for device verification.

### What was ruled out

**The briefing's hypothesis is wrong.** It suggested *"the map counts 'your location' as
pin #1 while the audio list starts at the first real stop."* The code does not do this.
The user's position is drawn as an **unnumbered blue dot** in a separate marker
(`tour_map_screen.dart:360-373`) and is never part of the numbered POI list. It cannot
shift the numbering.

That also answers the second half of his report directly: the current location has no
number **by design**, not by accident.

### What the numbering actually does

For a healthy tour the three systems agree, verified on the Boston walking tour:

| source | value |
|---|---|
| HTML heading | `Freedom Trail: Audio 1` |
| audio file | `audio_1.mp3` |
| map button | `openMap(1)` |
| map pin | `1` |

`_loadPois()` walks `audio_1.txt`, `audio_2.txt`, … and sets each POI's `index` to the
**file number** (`tour_map_screen.dart:63-88`).

### The one real mechanism that can desynchronise them

`_parsePoi()` returns `null` when a stop's `.txt` has no `Coordinates:` line
(`tour_map_screen.dart:113`). Those stops are silently dropped from the map, but the
survivors **keep their original file numbers**. The map therefore shows *gaps*, never a
renumbering — e.g. pins `1, 4, 5` for a 5-stop tour.

Compounding it: when the map is opened from a stop whose POI was dropped,
`_focusPoi()` cannot find that index and falls back to the POI **nearest the user**,
highlighting it orange (`tour_map_screen.dart:187-208`). Opening the map from "Audio 1"
on a tour where stop 1 has no coordinates would highlight a *different* pin — which is a
plausible route to "Audio 1 corresponds to point #2".

### Why it could not be confirmed here

- Yury's Toronto tour is not on this machine, and the local Postgres is not running.
- Across 80 archived tours, every tour with partial coordinates had them on **stop 1
  only** (all indoor museum tours) — the opposite shape from what Yury describes.
- The highlight logic depends on real GPS, which an emulator cannot meaningfully supply.

### What to check on a real device

1. Open Yury's tour, tap the 🚶 map button on **Audio 1**.
2. On the map, read the pin numbers left to right. **Is any number missing?**
3. If pin `1` is absent, the cause is confirmed: `audio_1.txt` has no `Coordinates:`
   line, so stop 1 was dropped and the orange highlight fell through to another pin.
4. Cross-check by unzipping that tour and grepping each `audio_N.txt` for `Coordinates:`.

**Prediction to falsify:** at least one stop in that tour has no `Coordinates:` line, and
the missing pin numbers correspond exactly to those stops.

### Open question for Michael — not assumed, not implemented

Yury's *"I expect my current location on a map has a number e.g. #0"* is a **suggestion**,
not a defect. Per §8 it was left alone and is Michael's call.

---

## Separate finding — not one of Yury's bugs

**`generate_tour_text.py:10` imports a module that is not tracked in git.**

```python
from enhanced_tour_templates_fixed import get_enhanced_tour_template, validate_enhanced_poi_knowledge
```

Only `enhanced_tour_templates.py` is tracked on this branch; `enhanced_tour_templates_fixed.py`
is untracked. The import resolves solely because an untracked duplicate happens to sit in
this working directory — the two files are byte-identical here (sha256 `b63c45df…`).

**On a clean checkout of `fix/yuri-audio-and-map` — or of `main` — `tour-generator` will
not start.** It crash-loops with `ModuleNotFoundError`. Confirmed by direct observation
during this session.

It also collides with §8's "do not create `_fixed` files": the code *requires* a `_fixed`
module the ground rules forbid committing. The clean repair is to import
`enhanced_tour_templates` and drop the duplicate, but that is a services change unrelated
to Yury's report, so it was **flagged only, not fixed**, per Michael's instruction.

Note `origin/storied` tracks a *different* 9,428-byte `enhanced_tour_templates_fixed.py`.
Restoring this file from `storied` would silently downgrade the templates. It must be
restored from `enhanced_tour_templates.py`, not from `storied`.

---

## Environment notes

- Services rebuilt from this branch per §0; `tour-generator` healthy on `:5000`.
- `docker-compose up -d` (whole stack) collides with nine long-running containers on this
  machine. Use `up -d --no-deps tour-generator`. **Never** run the suggested
  `--remove-orphans`: it would destroy those nine containers.
- The uncommitted `.dockerignore` exception `!requirements*.txt` is **load-bearing** —
  the Dockerfile does `COPY requirements_generator.txt`. It is still uncommitted.
- `flutter pub get` rewrites `pubspec.lock` and the macOS/Windows plugin registrants.
  Those were reverted and are **not** part of this commit.
- `kiro-cli` is not installed on this machine, so the work was done directly rather than
  dispatched (§5 permits this).
