# SUBMISSION — LOCAL-768: Kokoro baked into the voice image (Subscribed speaks English with in-process Kokoro)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-768-kokoro-in-voice-image` · **Base:** `subscribed` @ `46adfa2f`
**code_sha:** this submission's own commit on the branch; the WIP (`LOCAL-768 WIP
saved by LEAD` + the earlier SUBMISSION commit) was **rebased onto the current
`subscribed` tip `46adfa2f`** so the base note's gate holds:
`git merge-base --is-ancestor 46adfa2f HEAD` ⇒ **0** (verified this session).
The original WIP had branched from `8c7be937` (3 commits behind `subscribed`,
before the meter-baking commits `173db1c3`/`4a96f3d8`/`46adfa2f`); the rebase
applied cleanly with no conflicts.

---

## 1. What this does (D667, LEAD ruling)

Michael: *"Why can we not deploy Kokoro, which is free on Google Cloud? … not
only Kokoro is cheaper, it is significantly nicer voice."* Then: *"I hate to add
the complexity of an additional container."*

**LEAD ruling honoured: NO separate Kokoro service.** Kokoro runs **in-process
inside the voice service** (`polly_tts_service.py`) — the r1 mode the code
already had: `TTS_ENGINE=kokoro` with `KOKORO_URL=''` (empty) loads
`kokoro_engine` in-process, `warmup()`s at start, renders English there, and
falls back to Polly on any error; every non-English voice stays Polly. The Mac
keeps its host-native Kokoro on `:5181` (faster there — Apple GPU). **Only the
GCloud image changes.**

The new image **`Dockerfile.polly-tts-kokoro`** is the SAME voice service
(same `polly_tts_service.py`, port 5018, `/synthesize`, `/health`, `/meter`,
cost modules, pronunciation aid) with the Kokoro engine deps added and the
**model weights + both voice packs baked into the image layer** (no cold-start
download). **The plain Polly image `Dockerfile.polly-tts` is unchanged** — Beta
keeps speaking Polly.

## 2. Files changed (named; never `git add -A`)

| File | Δ | What |
|---|---|---|
| `polly_tts_service.py` | +28 | `/health` now also reports `kokoro_mode` (`in_process`/`host`/None), `model_loaded`, `ffmpeg_present` — all soft so the Polly default never breaks. Render paths unchanged. |
| `kokoro_engine.py` | +21 | `model_loaded()` (read-only: is the in-process pipeline loaded) and `ffmpeg_present()` (is ffmpeg on PATH) for `/health`. |
| `Dockerfile.polly-tts-kokoro` | +120 (new) | voice image + Kokoro: `python:3.11-slim`, `espeak-ng`/`ffmpeg`/`libsndfile1`, `torch==2.8.0` (CPU wheel), `numpy==2.2.6`, `kokoro==0.9.4`, `misaki[en]==0.9.4`, `phonemizer-fork==3.3.2`, `espeakng-loader==0.2.4`, `soundfile==0.14.0`; copies each module one at a time (+`download_kokoro_weights.py`); bakes the model via `download_kokoro_weights.py`; `TTS_ENGINE=kokoro`, `KOKORO_URL=`. |
| `tests/test_local768_kokoro_in_image.py` | +262 (new) | 7 tests (below). |
| `measure_local768_kokoro.py` | +90 (new) | not shipped — measurement harness hitting `/synthesize` (the same endpoint the orchestrator uses; no `/render` service). |
| `SUBSCRIBED_GCLOUD_ENV.md` | edited | new §8b `polly-tts-subscribed` + the list of Subscribed vars to re-point; stale "No/Polly-only Kokoro" notes in §5/§8 corrected. |

`Dockerfile.polly-tts` (Beta, Polly-only) **not touched**. Every module the new
Dockerfile copies one-by-one is listed in it.

## 3. Tests

Red → green. The 4 `/health` tests were RED on the base (the keys `kokoro_mode`,
`model_loaded`, `ffmpeg_present` did not exist) and pass after the `/health`
enhancement; the 3 render/routing tests pin the in-process contract the image
relies on.

`tests/test_local768_kokoro_in_image.py` (7):
- `test_inprocess_english_render_no_host_no_polly` — English + empty `KOKORO_URL` renders in-process, **no** host HTTP call, **no** Polly, metered engine=kokoro $0.
- `test_inprocess_nonenglish_stays_polly` — Russian (Tatyana) → Polly.
- `test_inprocess_failure_falls_back_to_polly` — in-process encoder raises → Polly (tour never loses audio).
- `test_health_inprocess_reports_engine_mode_model_ffmpeg` — reports engine/mode/model/ffmpeg.
- `test_health_inprocess_model_not_loaded_reports_false` — reports False honestly.
- `test_health_host_mode_reported_when_kokoro_url_set` — mode `host`, model not loaded in this instance.
- `test_health_polly_default_unchanged_fields_present` — Polly default keeps its fields; kokoro off.

**RED proof (this session):** running the 7 LOCAL-768 tests against the base
`polly_tts_service.py` (`git show 46adfa2f:polly_tts_service.py`) gives
**4 failed, 3 passed** — the 4 `/health` tests fail with `KeyError: 'kokoro_mode'`
because the base `/health` lacks the new keys. After the enhancement all 7 pass.

**Existing LOCAL-573 / 575 Kokoro tests stay green** (there is no
`test_local706_*` file in this tree; the LOCAL-706 pronunciation markup is
exercised inside the LOCAL-573 routing tests):

```
$ python3 -m pytest tests/test_local768_kokoro_in_image.py \
    tests/test_local573_kokoro_routing.py \
    tests/test_local575_kokoro_mp3_duration.py -v
...
25 passed in 1.41s
```
(7 LOCAL-768 + 10 LOCAL-573 + 5 LOCAL-575 = 25, all green on Python 3.9 host.)

## 4. Build + `/health`

Built this session from `Dockerfile.polly-tts-kokoro` with
`--build-arg GIT_SHA=$(git rev-parse HEAD)`. The model bake logged
`[LOCAL-573] Kokoro weights + voice packs baked into image.` and
`build_manifest` recorded the sha (`[build_manifest] Wrote ... 7 files`).

```
docker build --platform linux/amd64 -f Dockerfile.polly-tts-kokoro \
  --build-arg GIT_SHA=$(git rev-parse HEAD) -t polly-tts-kokoro:local768 .   # real 1m58s
```

Disk discipline (task rule): `df -g /System/Volumes/Data` showed **21 GB free**
before the amd64 build and **17 GB** before the native-arch reference build —
both ≥ 15 GB. One image tag was kept at a time (`docker image rm` the previous
before building the next); `docker builder prune -f` ran after each build.

`/health` on the running container, run with
`-e TTS_ENGINE=kokoro -e KOKORO_URL= --cpus 2 --memory 4g -p 5281:5018`:

```json
{"status":"healthy","service":"polly_tts","polly_available":true,
 "tts_engine":"kokoro","kokoro_url":null,
 "kokoro_mode":"in_process","model_loaded":true,"ffmpeg_present":true}
```

**Image size (deployable):** `docker image inspect --format {{.Size}}` =
**~0.92 GB** (amd64) / **0.83 GB** (arm64 ref). (`docker images` lists a larger
`3.12 GB` figure for the arm64 build — that view attributes shared
build/attestation layers in the containerd store; the inspect size is the real
image.) Either way the image is **under 1 GB** — the CPU torch wheel + slim base
kept it far below the ~3 GB of the first (disk-filling) attempt. Weights are in
the layer: **no download at runtime.**

**Cold start to `/health` ready (model loaded), 2 vCPU / 4 GiB:**
**5.6 s emulated amd64**, **4.0 s native arm64** (weights baked ⇒ warm-up is a
model load only, no network).

## 5. Measurements (2 vCPU / 4 GiB, 2,300-char English stop, Joanna → af_heart 24 kHz)

> **Honest caveat on architecture.** Cloud Run is amd64, so the task asks for
> `--platform linux/amd64`. On this Apple-silicon Mac an amd64 image runs under
> **QEMU emulation**, which inflates torch inference and is **not**
> representative of Cloud Run's native amd64 CPU. I report BOTH: the literal
> emulated-amd64 numbers, and a **native-arch (arm64)** run as a realistic
> CPU-inference proxy (native ARM CPU tracks native amd64 CPU far better than
> emulated amd64 does). Both images are byte-identical in output. All runs
> 2 vCPU / 4 GiB unless noted.

2,300-char English stop, voice Joanna → Kokoro `af_heart` 24 kHz:

| Run | Arch | Cold | Warm-1 | Warm-2 |
|---|---|---|---|---|
| amd64 **emulated** (QEMU on ARM — inflated) | linux/amd64 | 262.86 s | 259.02 s | 270.02 s |
| **native** (realistic CPU proxy) | arm64 | 147.21 s | 146.52 s | 153.70 s |

4-stop tour (native arm64, 2 vCPU), texts of 2,100 / 2,600 / 1,900 / 2,800 chars:

| Stop | Chars | Seconds |
|---|---|---|
| 1 | 2,100 | 132.35 |
| 2 | 2,600 | 163.36 |
| 3 | 1,900 | 126.15 |
| 4 | 2,800 | 179.55 |
| **Tour total** | **9,400** | **601.42 s** |

**CPU scaling** (native arm64, warm, 2,300-char stop) — the inference is
CPU-bound and scales almost linearly, which is the main deploy lever:

| vCPU | Warm s/stop |
|---|---|
| 2 | ~147 |
| 4 | 70.3 |
| 8 | 45.0 |

**~147 s per 2,300-char stop at 2 vCPU** (native proxy), dropping to ~45 s at
8 vCPU. This is far slower than the Mac host's ~16.5 s **because the host uses
the Apple GPU (MPS) and Cloud Run has CPU only.** That is the headline
operational fact: on Cloud Run, in-process Kokoro is a **high-latency** render,
and acceptable per-stop latency needs ≥ 4–8 vCPU.

**Output MP3 matches the Mac's Kokoro** (`ffprobe /tmp/local768_stop.mp3`,
identical bytes from both arches — 814,796 bytes):
`codec=mp3, sample_rate=24000 Hz, channels=1 (mono), duration≈135.79 s`,
plays cleanly — exactly `kokoro_engine.target_sample_rate_for("Joanna") = 24000`,
voice `af_heart` (neural English female), the same shape as the host service.

## 6. Cost per stop vs Polly neural (show the arithmetic)

Cloud Run Tier-1 request-based pricing (active usage): **$0.000024 / vCPU-s**,
**$0.0000025 / GiB-s**, **$0.40 / 1M requests**
(source: cloud.google.com/run/pricing). Polly **neural** = **$16.00 / 1M chars**
(`cost_rates.POLLY_NEURAL_COST_PER_CHAR = $0.000016`).

Polly neural for one 2,300-char stop = 2300 × $0.000016 = **$0.03680**.
Kokoro's per-char cost is **$0** (local CPU render); its cost is Cloud Run
compute only. Arithmetic per stop (cost = vCPU×sec×$0.000024 +
4 GiB×sec×$0.0000025 + 1 req×$0.0000004), using the native-proxy warm seconds:

| vCPU | sec/stop | CPU $ | Mem $ | Req $ | **Total $/stop** | vs Polly |
|---|---|---|---|---|---|---|
| 2 | 147.0 | 0.007056 | 0.001470 | 0.0000004 | **$0.008526** | 0.23× |
| 4 | 70.3 | 0.006749 | 0.000703 | 0.0000004 | **$0.007452** | 0.20× |
| 8 | 45.0 | 0.008640 | 0.000450 | 0.0000004 | **$0.009090** | 0.25× |
| amd64 emulated | 260 | 0.012480 | 0.002600 | 0.0000004 | $0.015080 | 0.41× |

**In-process Kokoro is ~4–5× cheaper per stop than Polly neural** across 2–8
vCPU (cost/stop is nearly flat because more vCPUs finish proportionally faster);
**4 vCPU is both the cheapest and ~2× faster than 2 vCPU.** Even the
emulation-inflated 260 s is still ~2.4× cheaper than Polly. Break-even vs Polly
at 2 vCPU + 4 GiB is a render of **~630 s** — far beyond any real stop.

4-stop tour (9,400 chars), native 2 vCPU, 601 s:
Cloud Run **$0.0349** vs Polly neural 9400 × $0.000016 = **$0.1504** — ~4.3×
cheaper.

**Conclusion — Michael is right on both counts, with one caveat:** in-process
Kokoro on Cloud Run is **cheaper** than Polly neural *and* (per D667) the nicer
voice. The real trade-off is **latency** (~45–147 s depending on vCPU vs Polly's
sub-second), **not cost**. That drives the deploy settings: `--concurrency 1`
(a render pins the CPU), request timeout ≥ 300 s, `--min-instances 0` (cold
start is only ~5 s), raising each caller's TTS HTTP read timeout to ≥ 300 s, and
**preferring 4 vCPU** (cheapest and ~2× faster than 2). More vCPU cuts latency
roughly linearly while cost/stop stays ~flat — the lever LEAD can pull if
latency matters more than scale-to-zero.

## 7. `SUBSCRIBED_GCLOUD_ENV.md`

New **§8b polly-tts-subscribed**: image `Dockerfile.polly-tts-kokoro`, port 5018,
`TTS_ENGINE=kokoro`, **`KOKORO_URL=''` (empty, required)**, 2 vCPU / 4 GiB,
`--concurrency 1`, request timeout ≥ 300 s, `--min-instances 0`, AWS Polly
secrets for fallback, `/health` readiness gate
(`model_loaded && ffmpeg_present`). The Subscribed services that call the voice
service over **`POLLY_TTS_URL`** — **tour-editing-subscribed**,
**tour-generator-subscribed** (`tour_generation_modernized.py`),
**custom-audio-subscribed**, **news-processor-subscribed** — must re-point
`POLLY_TTS_URL` at `polly-tts-subscribed` (NOT Beta's `polly-tts`, which stays
Polly). Stale §5/§8 "No/Polly-only Kokoro" notes corrected to say they are each
service's inline default; the English voice a listener hears is set by
`polly-tts-subscribed`.

## 8. Live-test discipline / housekeeping

- Own containers only (`local768-voice` / `local768-voice-arm` / `l768bench`,
  `-p 5281/5282/5283:5018`); the live `audioura-*` stack and **the host Kokoro
  on `:5181` were never touched**. No GCloud deploy, no DB writes. Budget: **$0**
  Polly — every English measurement render used the in-process encoder and never
  hit Polly (`model_loaded:true`, `kokoro_mode:in_process`); the Polly-fallback
  path is proven by the unit test, not a live paid call.
- **Disk discipline honoured:** `df -g` ≥ 15 GB verified before each `docker
  build` (21 GB then 17 GB free); one image tag at a time; `docker builder
  prune -f` after each build. Never `docker system prune` / `docker container
  prune` (would remove the shared stack). All test images were removed with
  `docker image rm` and the builder cache pruned at the end.
- This WIP (from the earlier disk-full run) was continued, not restarted: the
  two existing branch commits were rebased onto the current `subscribed` tip
  `46adfa2f` (clean, no conflicts), tests re-verified green, and all
  measurements re-run from scratch on freshly built images this session.
