# SUBMISSION — LOCAL-768: Kokoro baked into the voice image (Subscribed speaks English with in-process Kokoro)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-768-kokoro-in-voice-image` · **Base:** `subscribed` @ `8c7be937`
**Code commit (WIP, LEAD-saved):** `19a64da2` — the 5 code files below.
**code_sha:** this submission's own commit (the commit that adds this file +
`SUBSCRIBED_GCLOUD_ENV.md`) on top of `19a64da2`; `8c7be937` is an ancestor of
HEAD (`git merge-base --is-ancestor 8c7be937 HEAD` ⇒ 0).

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

**Existing LOCAL-573 / 575 / 706 stay green.**

```
$ python3 -m pytest tests/test_local768_kokoro_in_image.py \
    tests/test_local573_kokoro_routing.py \
    tests/test_local575_kokoro_mp3_duration.py \
    test_local706_kokoro_pronunciation.py -q
37 passed, 1 skipped
```
(1 skipped = the misaki G2P round-trip, skipped when misaki is not importable in
the host python — unchanged from base.)

## 4. Build + `/health`

Built under both architectures from `Dockerfile.polly-tts-kokoro`
(`--build-arg GIT_SHA=$(git rev-parse HEAD)`). The model bake logged
`[LOCAL-573] Kokoro weights + voice packs baked into image.` and
`build_manifest` recorded the sha.

```
docker build --platform linux/amd64 -f Dockerfile.polly-tts-kokoro \
  --build-arg GIT_SHA=$(git rev-parse HEAD) -t polly-tts-kokoro .   # 2m14s
```

`/health` on the running container (both arch), run with
`-e TTS_ENGINE=kokoro -e KOKORO_URL= --cpus 2 --memory 4g -p 5281:5018`:

```json
{"status":"healthy","service":"polly_tts","polly_available":true,
 "tts_engine":"kokoro","kokoro_url":null,
 "kokoro_mode":"in_process","model_loaded":true,"ffmpeg_present":true}
```

**Image size:** ~**988 MB** compressed (single-platform manifest view) /
~**3.53 GB** uncompressed on disk (`docker image ls`, amd64, incl. attestation
layers). The weight bake is in the image — no download at runtime.

**Cold start to `/health` ready (native, 2 vCPU / 4 GiB): ~4.8 s** (weights
baked; warm-up is model load only, no download).

## 5. Measurements (2 vCPU / 4 GiB, 2,300-char English stop, Joanna → af_heart 24 kHz)

> **Honest caveat on architecture.** Cloud Run is amd64, so the task asks for
> `--platform linux/amd64`. On this Apple-silicon Mac an amd64 image runs under
> **QEMU emulation**, which inflates torch inference ~1.7× and is **not**
> representative of Cloud Run's native amd64 CPU. I report BOTH: the literal
> emulated-amd64 numbers, and a **native-arch** run as a realistic
> CPU-inference proxy (native ARM CPU ≈ native amd64 CPU far better than
> emulated amd64 does). Both are 2 vCPU / 4 GiB.

| Run | Arch | Cold | Warm-1 | Warm-2 | Tour stop (2,100 ch) |
|---|---|---|---|---|---|
| amd64 **emulated** (QEMU on ARM — inflated) | linux/amd64 | 261.7 s | 252.7 s | 266.6 s | 235.7 s |
| **native** (realistic CPU proxy) | arm64 | 158.1 s | 146.9 s | 161.1 s | 142.5 s |

**~150 s per 2,300-char stop at 2 vCPU** (native proxy; ~67 ms/char). This is
far slower than the Mac host's ~16.5 s **because the host uses the Apple GPU
(MPS) and Cloud Run has CPU only.** That is the headline operational fact: on
Cloud Run, in-process Kokoro is a **high-latency** render.

**Output MP3 matches the Mac's Kokoro** (`ffprobe /tmp/local768_stop.mp3`):
`codec=mp3, sample_rate=24000 Hz, channels=1 (mono), duration≈135.8 s`,
plays cleanly — exactly `kokoro_engine.target_sample_rate_for("Joanna") = 24000`,
voice `af_heart` (neural English female), the same shape as the host service.

## 6. Cost per stop vs Polly neural (show the arithmetic)

Cloud Run Tier-1 request-based pricing (active usage): **$0.000024 / vCPU-s**,
**$0.0000025 / GiB-s**, **$0.40 / 1M requests**
(source: cloud.google.com/run/pricing via dev.to/cloudchipr worked examples).
Polly **neural** = **$16.00 / 1M chars** (`cost_rates.POLLY_NEURAL_COST_PER_1M_CHARS`).

Per 2,300-char stop, 2 vCPU + 4 GiB:

| Item | Kokoro in-process (native, 155 s) | Kokoro in-process (emulated, 260 s) | Polly neural |
|---|---|---|---|
| CPU | 2 × $0.000024 × 155 = **$0.00744** | 2 × $0.000024 × 260 = $0.01248 | — |
| Memory | 4 × $0.0000025 × 155 = **$0.00155** | 4 × $0.0000025 × 260 = $0.00260 | — |
| Request | ~$0.0000004 | ~$0.0000004 | — |
| Chars | — | — | 2300 × $0.000016 = **$0.0368** |
| **Total / stop** | **≈ $0.0090** | ≈ $0.0151 | **≈ $0.0368** |

**In-process Kokoro is ~4× cheaper per stop than Polly neural** at the measured
155 s — and stays cheaper than Polly until a render exceeds **~630 s**
(break-even). Even the emulation-inflated 260 s is still cheaper than Polly.

**Conclusion — Michael is right on both counts, with one caveat:** in-process
Kokoro on Cloud Run is **cheaper** than Polly neural *and* (per D667) the nicer
voice. The real trade-off is **latency** (~150 s on 2 vCPU vs Polly's
sub-second), **not cost**. That drives the deploy settings: `--concurrency 1`
(a render pins the CPU), request timeout ≥ 300 s, `--min-instances 0` (cold
start is only ~5 s), and raising each caller's TTS HTTP read timeout to ≥ 300 s.
More vCPU cuts latency roughly linearly and raises per-second cost
proportionally, so cost/stop is ~flat in vCPU while latency improves — a lever
LEAD can pull if latency matters more than scale-to-zero.

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

- Own containers only (`local768-voice`, `-p 5281:5018`); the live `audioura-*`
  stack and **the host Kokoro on `:5181` were never touched** (confirmed `:5181`
  healthy throughout). No GCloud deploy, no DB writes. Budget: $0 Polly (English
  renders never hit Polly in the measurement).
- Mid-run, Docker Desktop crashed from Mac disk pressure (the known risk). The
  LEAD auto-restarted the Mac and committed this WIP (`19a64da2`) + pushed it
  before pruning the worktree; I recreated the worktree and re-verified tests
  green. All measurement evidence was captured before the crash. My Docker test
  images were pruned by the restart (nothing left to `docker image rm`).
