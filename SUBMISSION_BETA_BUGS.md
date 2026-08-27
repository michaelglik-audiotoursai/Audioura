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

Commits `144ca98` and `84e6054`. Five lines in each of **four** generators, copying the
established pattern.

The scope grew after the first commit: a systematic audit of every
`addEventListener('play'` across the Python generators found the same omission in
`single_file_app_builder.py` (the builder used by `tour-processor`, the local
docker-compose path) and in `tour_editing_phase2.py` (the live editing service, which
regenerates a tour's HTML after an edit and would otherwise have reintroduced the bug).
Two remaining offenders, `tour_editing_phase2_container.py` and `_final.py`, are
unreferenced duplicates and were left alone.

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

### Shipped — verified on device and live in production

| | |
|---|---|
| verified by Michael, on device | English, **Chinese and Russian** — one audio at a time |
| verified on the local Beta stack | before `CONCURRENT_COUNT=2` → after `1`, both from freshly generated tours |
| merged to `main` | `34397e2`, pushed |
| forward-merged to `storied` | `afae00d..0ac89b3`, pushed with Michael's authorisation; `[LOCAL-323]` verified intact |
| deployed to GCloud | `tour-modernized` → `audioura:v32`, revision `tour-modernized-00008-fsn` |
| rollback | `./deploy_tour_modernized.sh --rollback` (previous image `v8` untouched) |
| mobile build | **not required** — no Dart changed, so no version bump, no store upload |

Still open: Yury's own confirmation on `wdvrdaxmq2`.

**A correction worth recording.** During this work I warned that `translation-service`
still carried the bug in production and that translated tours would be affected. **That
was wrong**, and Michael's Chinese and Russian tests disproved it. The buggy block at
`translation_service.py:1553` sits in `_generate_translated_html`, which is **defined but
never called** — dead code. The live path is `_create_english_format_html` (`:785`),
whose listener already paused the other elements before any of this work. My warning came
from reading a function without checking whether anything invokes it — the same mistake
that produced the `enhanced_tour_templates_fixed` incident recorded below. No
`translation-service` deploy was needed.

---

## BETA-2 — audio/map numbering off by one — `wdvrdaxmq3`

### Verdict: `WORKS AS DESIGNED — but genuinely misleading`

**Resolved 2026-08-17.** Michael reproduced it on his own phone using Yury's tour. An
earlier revision of this document recorded `UNPROVEN`; that is superseded.

**The numbering was never wrong.** Stops 1 and 2 in Yury's tour sit so close together
that **pin 1 is completely hidden underneath pin 2**. Zoomed out, the first visible pin
reads `2`, so the sequence looks shifted by one. Yury's inference was entirely
reasonable from what was on screen — he reported a real problem, just not the one it
appeared to be.

### Why the pins overlap — two stacked defects

`tour_map_screen.dart` already carries logic meant to prevent exactly this
(`_applyCoordJitter`, `:90-109`). It fails twice.

**1. It only fires on *exactly identical* coordinates.**

```dart
final key = '${pois[i].coords.latitude},${pois[i].coords.longitude}';
```

A string key, so only byte-identical pairs are separated. Two stops 11 m apart are not
"identical" and receive no offset at all.

| tour in the archive | stops | distance | jitter fires? |
|---|---|---|---|
| Chagall, Nice | 4 & 5 | 0.0 m | yes — exact match |
| **Davis Square, Somerville** | **2 & 3** | **11.1 m** | **no — slips through** |

**2. Even when it fires, the offset is invisible.**

The step is `0.00008°` = **8.9 m**. Markers are 36 px. At the map's `initialZoom: 14`
one marker covers **249 m** of ground, so 8.9 m is **1.3 pixels** — roughly **28× too
small**.

| zoom | ground covered by a 36 px marker | 8.9 m jitter, in px | separate? |
|---|---|---|---|
| 14 (default) | 249 m | 1.3 | no |
| 17 | 31 m | 10.3 | no |
| 18 | 16 m | 20.6 | no |
| 19 | 8 m | 41.2 | yes |

Pins only come apart at **zoom 19**, matching both Yury's and Michael's experience that
you must zoom in extremely far.

### ❌ The obvious fix is wrong

Do **not** simply enlarge the jitter. Separating pins at zoom 14 would mean displacing
them ~250 m, and the map would then be **lying about where the stops are**. Any fix must
keep pin positions truthful.

### The agreed fix — Storied release, not Beta

Tracked as **`wdvrdaxnc5`**. Stops that would visually overlap merge into a **single pin
carrying both numbers** (e.g. `1-2`), which **splits back into individual pins as the
user zooms in**. Clustering is by *screen distance*, not ground distance, since whether
two pins collide depends entirely on zoom.

Michael's reasoning for the design: it removes the ambiguity Yury reported, and it also
tells the listener something true and useful — that these two stops are right next to
each other — while still resolving to exact positions when zoomed in.

**No Beta change.** It is a display issue rather than a broken tour, and the fix touches
the map screen enough to belong in a proper release. It is also mobile Dart, so shipping
it needs an app build and a `versionCode` bump.

### Still unfixed, and separate from the above

`_parsePoi()` returns `null` when a stop's `.txt` has no `Coordinates:` line
(`tour_map_screen.dart:113`). Those stops are dropped from the map while the survivors
**keep their original numbers**, producing real *gaps* — pins `1, 4, 5` for a 5-stop
tour. This is a genuine latent defect. It is **not** what Yury hit (his stops all have
coordinates), and it remains unaddressed.

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

### Open question for Michael — not assumed, not implemented

Yury's *"I expect my current location on a map has a number e.g. #0"* is a **suggestion**,
not a defect. Per §8 it was left alone and is Michael's call.

---

## BETA-3 — tour mislabelled "Museum Tour" — `wdvrdaxmub` (Storied, deferred)

### Verdict: `CONFIRMED` (cosmetic) — deferred to the Storied release, no Beta change

Third report from the same DM. Michael's hypothesis was put to the test rather than
accepted, at his request.

**Cause — confirmed.** `audio_tour_app/lib/screens/tour_generator_screen.dart:112`
defaults `tourType` to `'museum'` when the request contains none of
`walking`/`walk`/`museum`/`park`/`exhibit`. Yury's *"Toronto Ravines And Other Green
Spaces"* says "green spaces", not "parks", so it fell through to that default.

**Functionality is not lost — verified by execution, not by reading.**
`get_coordinate_requirement(location, tour_type)` accepts `tour_type` but **never reads
it**; the decision is regex on the *location string*:

| location | tour_type | requirement |
|---|---|---|
| Toronto Ravines And Other Green Spaces | `museum` | `ALL_STOPS` |
| Toronto Ravines And Other Green Spaces | `walking` | `ALL_STOPS` |
| Museum of Fine Arts Boston | `museum` | `FIRST_STOP_ONLY` |

Identical either way, so Yury's tour got per-stop coordinates and a working map. Museum
tours in the archive carry stop-1-only coordinates because their **location** matched a
single-building pattern, not because of the label.

The wrong label costs only: the visible wording, a 🏛️ instead of 🚶 map icon, and a
museum-flavoured narration prompt (Yury judged the content relevant).

**But it is not harmless in general.** Storied's own comment records that the `'museum'`
default caused transport tours to produce *"museum stops 25 miles away"*. Yury's tour got
off lightly. If a report ever arrives where the label costs real functionality, that is a
higher-severity bug than this one.

**Already fixed on `storied`** (`utils/tour_request_parser.dart`, `[LOCAL-358]`/`[LOCAL-363]`):
the default became `''` — an honest "no signal" — with tests asserting it. Deferred
accordingly; `main` must not move while Storied churns.

---

## BETA-4 — stop coordinates are LLM-guessed and unvalidated — `wdvrdaxqjn`

### Verdict: `CONFIRMED` — fixed, deployed, awaiting a device check

Yury's reports #3 and #4: stop #6 plotted over Central Islands, and every pin offset.

**Root cause.** Stop coordinates were never looked up anywhere. The model that writes the
tour text emitted a `Coordinates:` line from memory, and nothing checked it. The decisive
evidence needs no external ground truth: the live service placed *"Leslie Spit parking"*
and *"Tommy Thompson Park entrance"* — the same physical place — **1.3 km apart**. A
geocoder cannot be self-inconsistent like that.

**The fix.** `geocode_stops.py`, called from `tour_generation_modernized.py` right after the
tour text is parsed, so both `audio_N.txt` (which the map reads) and the HTML map buttons
get corrected values. Each stop gathers up to three independent estimates — the model's own
coordinate, `name + city`, and the full address — and a coordinate is replaced only when two
agree within 200 m.

Measured over 40 stops in 8 cities against Wikidata: median error **87 m → 46 m**, worst
1,616 m → 558 m, **zero regressions**. High-confidence stops average 26 m; low-confidence
303 m, and every error over 500 m is in the low-confidence group.

**Shipped** in `audioura:v33` (2026-08-20).

**Limits, deliberately not hidden.** It cannot resolve names the model invents — *"Leslie
Spit parking"* is a description, not a place — and OSM has no car parks mapped near Tommy
Thompson Park at all. The cure is `wdvrdaxqtf` in Storied.

**Still open:** confirmation that a real pin lands where the place is, on a device. See
`wdvrdaxvvv`.

---

## BETA-5 — latitude and longitude reversed — `wdvrdaxqte`

### Verdict: `CONFIRMED` — fixed in `16140ec`, deployed and verified in production

Worse than any other coordinate defect found: a 1 km error is an annoyance, this made the
whole tour unusable. Madagascar tours were written **longitude-first**, putting every stop
~9,900 km away in the Indian Ocean off Somalia.

`geocode_stops.py` could not repair it, and that was not a flaw in it. Its plausibility
guard is anchored on the median of the tour's own stops — when every stop is mirrored, the
anchor is in the wrong ocean too, and the *correct* geocoded answers are then discarded as
implausible. The guard reasoned correctly from poisoned input.

**The fix.** Two checks, cheapest first: latitude outside ±90 is impossible; then compare the
tour against its own city and reverse the whole tour if a majority of stops are 10× closer
swapped. The subtle part was **ordering** — it must run *before* the plausibility anchor is
computed, for the reason above.

### Deployed and verified — 2026-08-27

`audioura:v34`, revision `tour-modernized-00010-84r`, replacing `v33`. Authorised by Michael
in advance.

Verification was run against the **deployed image**, not the source tree:

| check | result |
|---|---|
| image contains `fix_reversed_coordinates` | `True` — the deploy script's own guard only checks the audio fix, so this is manual |
| reversed tour through production `/process` | 9,900 km → **4.2 km**; read from the delivered ZIP's `audio_N.txt` |
| reversal logged | `[GEOCODE] REVERSED COORDINATES: 3 of 3 stops` in Cloud Run logs |
| Sydney / Kyoto / Boston / correct-Antananarivo controls | all `action: none` |
| Sydney end-to-end through production | stayed in Sydney, no `REVERSED` log line |
| **red test** — repair stubbed out | **9,900.0 km** vs 4.4 km shipped |

The controls mattered most: the real risk of this deploy was a *correct* tour being wrongly
"corrected". None was.

**The defect is intermittent.** A fresh Antananarivo generation on 2026-08-27 produced
correctly-ordered coordinates unprompted. A correct Madagascar tour therefore proves
nothing — verification must use deliberately reversed input, which is what the above does.

### Found during verification, filed not fixed

`city_from_address()` returned `'Madagascar'` — the country, not the city — so the anchor was
a country centroid. It is wrong on **8 of 12** real address shapes, because `_COUNTRIES`
(`geocode_stops.py:169`) is a hardcoded 16-country allowlist. A second, independent bug in
`_clean_component()` (`geocode_stops.py:182`) matches `[A-Z]{2}` for state codes, so
three-letter Australian states (`NSW`, `QLD`, `VIC`) survive and `Sydney NSW 2000` is
returned as the city.

Impact was **measured rather than assumed, and is close to nil**: Nominatim resolves the
country-qualified and city-qualified query forms identically (0.00 km apart on three tested
pairs), and correct tours in Brazil, India, Kenya and Turkey — all anchored on country
centroids — produced no false positives. The docstring's claim that `Sydney NSW 2000` causes
a 12.75 km error **does not reproduce today**; that number should not be repeated as fact.

Filed as `wdvrdaxvvt`, low priority. It is a correctness-of-intent problem, not an accuracy
loss — the concern is that the reversal anchor is coarser than designed everywhere outside
16 countries, which erodes a safety margin nobody would know had been weakened.

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
