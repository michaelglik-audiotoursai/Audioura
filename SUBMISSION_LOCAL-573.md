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
