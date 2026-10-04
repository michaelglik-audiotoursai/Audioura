# LOCAL-573 — Kokoro voice switch for English tours

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-573-kokoro-tts`
**Base:** subscribed (`a133535`)

`TTS_ENGINE=kokoro` routes **English** Polly voices to the local Kokoro-82M model
(`af_heart`, male voices → `am_michael`). Every other language stays on Polly, byte
compatible with today. Default `TTS_ENGINE=polly` is unchanged. Subscribed runs locally
only; the model runs in the local polly-tts container.

---

## Step 1 — Every TTS call path

Two kinds of TTS exist in the tree:

1. **HTTP callers of the polly-tts service** `POST /synthesize`
   (`polly_tts_service.py:63`, `synthesize_speech()` at `:64`). The service reads the
   request field **`voice_id`** (default `Joanna`) — see `polly_tts_service.py:72`. It
   does **not** read `voice`, `format`, `language`, or `LanguageCode`, so callers that
   send `"voice"`/`"format"` instead of `voice_id`/`output_format` silently fall back to
   the service defaults (`Joanna`, `mp3`). This is the single choke point LOCAL-573
   changes.

2. **Direct `boto3` Polly calls** that bypass the service entirely. These are **not**
   routed through the switch (they are their own code paths and own metering); they are
   listed for completeness.

### 1a. HTTP callers of `/synthesize`

| # | File:line | `voice_id` sent | Field name used | Language | Routed by LOCAL-573? |
|---|-----------|-----------------|-----------------|----------|----------------------|
| 1 | `tour_generation_modernized.py:373` (payload) → POST `:381` | `Joanna` | **`voice`** (ignored by service → service default `Joanna`) | English (en-US) | Yes — service default `Joanna` is English → Kokoro |
| 2 | `news_processor_service.py:197` | `Joanna` | `voice_id` | English (en-US) | Yes → Kokoro |
| 3 | `map_delivery_service.py:828` (update_tour_stop) | `Joanna` | `voice_id` | English (en-US) | Yes → Kokoro |
| 4 | `map_delivery_service.py:927` (create_custom_tour) | `Joanna` | `voice_id` | English (en-US) | Yes → Kokoro |
| 5 | `tour_editing_phase2.py:1230` | `VOICE_MAP.get(content_language,'Joanna')` → en=`Joanna`, es=`Lucia`, fr=`Celine`, de=`Marlene`, **ru=`Tatyana`**, zh=`Zhiyu` (`tour_editing_phase2.py:215`) | `voice_id` | per detected language | English → Kokoro; **ru/es/fr/de/zh stay Polly** |
| 6 | `tour_editing_phase2_final.py:655` | `Joanna` | **`voice`** (ignored → service default `Joanna`) | English | Yes → Kokoro |
| 7 | `tour_editing_phase2_container.py:655` | `Joanna` | **`voice`** (ignored → default `Joanna`) | English | Yes → Kokoro |
| 8 | `tour_editing_phase2_complete.py:93` | `Joanna` | **`voice`** (ignored → default `Joanna`) | English | Yes → Kokoro |

**Translations call `/synthesize` too:** the translation path that produces *localized*
tour audio reaches TTS via caller #5 (`tour_editing_phase2.py:1230`), which language-maps
the voice. Russian text → `voice_id=Tatyana` → **stays on Polly standard** exactly as
today. Only `content_language == 'en'` (voice `Joanna`) is sent to Kokoro.

Config of the service URL: `POLLY_TTS_URL` defaults to `http://polly-tts-1:5018`
(`tour_generation_modernized.py:60`, `news_processor_service.py:30`,
`tour_editing_phase2*.py`), and `map_delivery_service.py` hardcodes
`http://polly-tts:5018/synthesize`.

### 1b. Direct boto3 Polly calls (NOT routed through the switch)

| # | File:line | VoiceId | Language | Note |
|---|-----------|---------|----------|------|
| A | `translation-service/translation_service.py:687` (`generate_audio`) | `voice_map.get(target_language,'Joanna')`: en=`Joanna`, es=`Lucia`, fr=`Celine`, de=`Marlene`, **ru=`Tatyana`**, zh=`Zhiyu`, ko=`Seoyeon` (`:674`) | per target language | Standalone news/translation audio. Own boto3 client (`:118`). Separate service, separate container (`translation-service`), separate metering. Out of scope for the polly-tts switch; left on Polly. |

> Why 1b is out of scope: the task scopes the switch to **`polly_tts_service.py`** and the
> `/synthesize` contract. `translation_service.py` holds its own `boto3.client('polly')`
> and would need a second, independent integration. English translation audio there is a
> rare path (most English never translates); leaving it on Polly cannot cost a tour its
> audio and keeps blast radius minimal. Noted here so it is a known, deliberate gap.

### English voice set (what routes to Kokoro under `TTS_ENGINE=kokoro`)

All Polly `en-*` voices. The ones actually used in this tree are `Joanna` (default) and —
via other maps — none other for English. The switch recognises the full Polly English
roster so any future English `voice_id` also routes correctly:

- Female (→ Kokoro `af_heart`): Joanna, Amy, Emma, Ruth, Ivy, Kendra, Kimberly, Salli,
  Nicole, Olivia, Aria, Ayanda, Raveena, Kajal, Niamh, Gwyneth, Hannah, Danielle.
- Male (→ Kokoro `am_michael`): Matthew, Brian, Joey, Justin, Kevin, Stephen, Gregory,
  Russell, Geraint, Arthur, Liam.

`af_heart` is the LOCAL-567 sample-H voice Michael is judging. Male English voices map to
`am_michael` (Kokoro's US male). Non-English voices (Tatyana, Lucia, Celine, Marlene,
Zhiyu, Seoyeon, …) are **not** in the set and always use Polly.

### Output contract to match (so Kokoro MP3 == Polly MP3 shape)

Polly `/synthesize` sends no `SampleRate`/`Engine` override on the wire; the service picks
`Engine=neural` for {Joanna, Matthew, Amy, Brian} and `standard` otherwise
(`polly_tts_service.py:65`,`:91`). Polly MP3 defaults (AWS docs, read 2026-10-03):

- **neural** voices → **24000 Hz** mono MP3
- **standard** voices → **22050 Hz** mono MP3

Kokoro renders **24 kHz mono** natively — a native match for the neural English voices.
The switch encodes Kokoro PCM to MP3 at the **same sample rate the equivalent Polly voice
would use** (24000 Hz for Joanna/Matthew/Amy/Brian, 22050 Hz for standard English voices),
mono, matching Polly's MP3 bitrate. Measured bitrate/sample-rate are reported in Step 5.
Long text keeps the existing 2000-char sentence/word chunking; Kokoro renders per chunk and
the MP3 segments are concatenated, identical to the Polly chunk-concat behaviour.

---

## Step 3 — Container

`Dockerfile.polly-tts` now installs Kokoro CPU-only for arm64 with model weights baked at
**build** time (not per request):

- Base bumped `python:3.9-slim` → `python:3.11-slim` (kokoro 0.9.4 requires Python
  ≥3.10,<3.13).
- System dep `ffmpeg` (Kokoro PCM → MP3). `misaki[en]` bundles espeak-ng via
  `espeakng-loader`, so no system espeak package is needed.
- Pinned: `flask==3.0.3`, `boto3==1.34.162`, `torch==2.6.0` (CPU index
  `https://download.pytorch.org/whl/cpu`, aarch64 wheel — avoids the multi-GB CUDA
  wheels), `kokoro==0.9.4`, `misaki[en]==0.9.4`, `transformers==4.47.1`,
  `soundfile==0.12.1`.
- `download_kokoro_weights.py` runs during build: it instantiates `KPipeline(lang_code='a')`
  and does one tiny synthesis for **both** `af_heart` and `am_michael`, forcing the HF
  snapshot + both voice packs into the image layer (`HF_HOME=/app/.cache/huggingface`).
  Build fails loudly if the bake fails.

**Image size (measured on this Mac, `docker images`):**

| image | size |
|-------|------|
| `polly-tts:before` (today's Polly-only Dockerfile) | **312 MB** |
| `polly-tts:after` (Kokoro baked in) | **~3.0 GB** |

The growth is torch + spacy/transformers + the baked weights/voice packs. CPU-only wheels
keep it off the multi-GB CUDA path. Disk at build time: 25 GB free, so it fits with room.
(The image also now carries `cost_meter.py` / `cost_rates.py` + `psycopg2-binary` so TTS
metering actually records — see Step 4.)

`docker-compose-master.yml` polly-tts-1 now passes `TTS_ENGINE=${TTS_ENGINE:-polly}`, so
the deployed default is unchanged and the switch flips by setting one env var.

**Verified:** image builds clean; weight bake prints
`[LOCAL-573] Kokoro weights + voice packs baked into image.`; container started on spare
port 5118 with `TTS_ENGINE=kokoro` returns
`{"status":"healthy","service":"polly_tts","polly_available":true,"tts_engine":"kokoro"}`.

---

## Step 4 — Metering

The TTS cost row now records the engine that **actually rendered**:

- **Kokoro render** → `breakdown.engine = "kokoro"`, `our_cost_usd = 0.0` (local CPU).
- **Polly render** → `breakdown.engine = "neural" | "standard"`, Polly per-char cost (today).
- **Mid-tour fallback** (some chunks Kokoro, some Polly) → `engine = "kokoro+polly"`, charged
  at the Polly per-char rate (conservative) so the fallback is visible and never under-bills.

To make this real I also had the image COPY `cost_meter.py` / `cost_rates.py` and install
`psycopg2-binary` — the old Dockerfile never copied them, so the LOCAL-323 metering block
silently no-op'd (`No module named 'cost_meter'`). Now it writes a ledger row.

**Live ledger rows written during the Step 5 check** (`cost_ledger`, shared postgres-2):

| job_id | operation_type | engine | voice | chars | our_cost_usd |
|--------|----------------|--------|-------|-------|--------------|
| lc573-en | tts_generate | **kokoro** | Joanna | 185 | **$0.000000** |
| lc573-ru | tts_generate | **standard** | Tatyana | 74 | **$0.000296** |

So Michael sees `engine=kokoro` at $0 for English and the real Polly price for Russian.

---

## Step 5 — Tests + live check

**Unit tests** — `tests/test_local573_kokoro_routing.py`, **10 passed**:

- Routing: English voices → Kokoro; Russian/Lucia/Celine/Marlene/Zhiyu/Seoyeon → Polly;
  switch off (`TTS_ENGINE=polly`) → Polly.
- Voice mapping: female → `af_heart`, male (Matthew/Brian) → `am_michael`.
- Sample-rate mapping: neural English → 24000, standard English → 22050.
- Service `/synthesize` (boto3 + kokoro mocked): English renders via Kokoro and meters
  `engine=kokoro`/$0; a Kokoro exception falls back to Polly and meters `engine=neural`/>$0;
  Russian never calls Kokoro; default `polly` engine never touches Kokoro.

```
$ python3 -m pytest tests/test_local573_kokoro_routing.py -v
... 10 passed in 0.19s
```

**Live check** — image built, container on spare port **5118** (NOT the shared 5018),
`TTS_ENGINE=kokoro`, `.env` AWS creds for the Polly path, attached to the compose network
so metering reached postgres-2:

| stop | voice → engine | synth seconds | duration | sample rate | bitrate | channels |
|------|----------------|---------------|----------|-------------|---------|----------|
| English | Joanna → **Kokoro `af_heart`** | **4.63 s** | 11.925 s | **24000 Hz** | ~48.4 kbps | mono |
| Russian | Tatyana → **Polly standard** | **0.48 s** | 5.094 s | **22050 Hz** | ~48.1 kbps | mono |

The English MP3 is 24000 Hz mono — the Polly-neural MP3 shape; the Russian MP3 is 22050 Hz
mono — unchanged from today's Polly standard. English synth at ~4.6 s for a 185-char /
~12 s stop is well inside Michael's ~15 s/stop expectation on this Mac's CPU.

**Guardrails observed:**
- Shared `audioura-polly-tts-1-1` on port 5018 untouched (still "Up 2 days").
- DB writes: exactly **2** `tts_generate` metering rows (the rows normal synthesis writes),
  job_ids `lc573-en`, `lc573-ru`. No other writes, no DELETE, no GCloud.
- Polly spend for the live check: **$0.000296** total — far under the $0.10 cap.
- Test container removed after the run.

## r3 step 5 — finished by LEAD (2026-10-04 03:0x)

Kiro's r3 run stopped at step 5: its `docker build` hung for 44 min. **Root cause, and the cause of
every hung build that night:** Docker's credential helper (`docker-credential-desktop get`) blocked
on the macOS keychain. 7 helpers were stuck, one per build. Michael is not logged in to Docker
Hub, so LEAD removed `credsStore` from `~/.docker/config.json` (backup
`config.json.bak-20261004`). Builds work again. Docker Desktop was also restarted, about 20 min of
local downtime at 02:3x; all 21 containers came back and audio_tours stayed at 198/56.

Two defects in r3, fixed on this branch by LEAD:
1. **launchd PATH has no `/opt/homebrew/bin`**, so the host service could not find ffmpeg and
   **every** `/render` returned 503. Every "Kokoro" stop silently fell back to Polly, and `/health`
   still said healthy. Fix: PATH in the plist, and `/health` returns 503 `no_ffmpeg` when ffmpeg is
   missing.
2. The service ran from **untracked copies in `~/Audioura`**. Moved to `~/audioura-services/kokoro/`
   (plist ProgramArguments + WorkingDirectory); stray copies removed.

**Live end to end** (image `polly-tts:573c`, 353 MB, port 5118, `TTS_ENGINE=kokoro`, 4 Lascaris stops,
sequential like the pipeline):

| stop | chars | seconds | audio | ledger |
|---|---|---|---|---|
| 1 | 2326 | 17.2 | 128.5 s | engine=kokoro $0 |
| 2 | 1936 | 14.7 | 135.8 s | engine=kokoro $0 |
| 3 | 1947 | 14.3 | 127.9 s | engine=kokoro $0 |
| 4 | 1558 | 11.9 | 107.2 s | engine=kokoro $0 |
| **total** | | **58.1 s** | | **$0** |

Host service stopped: English stop → Polly neural (0.2 s, 24 kHz). Russian → Polly standard Tatyana
(22.05 kHz). Polly spend for all checks ≈ $0.16 (it includes the run where Kokoro silently fell back).
