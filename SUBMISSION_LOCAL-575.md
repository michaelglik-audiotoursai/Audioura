# SUBMISSION — LOCAL-575: Kokoro MP3s report only the first chunk's duration

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-575-kokoro-mp3-duration` (base: subscribed `0242af3`)
**Date:** 2026-10-04

## Summary

Kokoro tour MP3s longer than one chunk reported only the **first chunk's**
duration in their MP3 header, so the mobile player's timer ran out early while
audio kept playing (Michael's field test on tour 388: *"The time goes to 0 from
-2:01 and continues for some time."*). This fixes the encoder so a multi-chunk
stop produces **one MP3 with one header describing the whole duration**, repairs
the two affected tours in place, and redeploys both the host Kokoro service and
the `polly-tts` container.

## Root cause

Stops over 2,000 chars are split into chunks by `polly_tts_service.py`
(`/synthesize`). Each Kokoro chunk was encoded to its **own** MP3 — ffmpeg writes
a Xing/Info header per encode — and the chunks were **byte-concatenated**
(`b''.join`). An MP3 player trusts the **first** Xing header, which describes only
the first chunk, so the reported duration was far short of the real total.

Polly's raw MP3 frames carry **no** Xing header, so byte-concatenated Polly audio
is counted frame-by-frame and plays correctly — which is why only Kokoro tours
showed the defect.

Measured on tour 388 (reproduced exactly from the DB blob, matches LEAD's table):

| file | header (before) | real | Xing/Info |
|---|---|---|---|
| audio_1.mp3 | 121.2 s | **203.8 s** | 2 |
| audio_2.mp3 | 98.1 s | 98.1 s | 1 |
| audio_3.mp3 | 121.5 s | **146.6 s** | 2 |
| audio_4.mp3 | 122.4 s | **141.7 s** | 2 |

## The fix (code)

**`kokoro_engine.py`** — three shared helpers (ffmpeg, same 24 kHz/22050 Hz mono
and same bitrate as today):
- `decode_mp3_to_pcm(mp3, sample_rate)` — MP3 → raw s16le mono PCM.
- `encode_pcm_to_mp3(pcm, sample_rate)` — raw PCM → one MP3 (one Xing header).
- `combine_mp3_chunks(chunks, voice_id)` — decode every chunk to PCM,
  concatenate, encode **once**. A single chunk is returned unchanged (no
  needless re-encode). Because any chunk (Kokoro *or* Polly) decodes to PCM, the
  **mixed-fallback** case produces one correct header too.

**`polly_tts_service.py`** (`/synthesize`):
- **Host path** (default, `KOKORO_URL` set): render the **whole** stop in a
  single `/render` call. The host's `synthesize_to_mp3` already concatenates its
  internal Kokoro PCM chunks and encodes once, so the result is one MP3 with one
  correct header. (polly-tts's 2,000-char split exists only for Polly's
  per-request limit; the host has no such limit.) On any host failure it falls
  back to Polly's split — raw frames, no Xing bug.
- **In-process path** (`KOKORO_URL` unset, off-container where ffmpeg exists):
  per-chunk render, then `combine_mp3_chunks` at the PCM level whenever any chunk
  was Kokoro (handles mixed Polly fallback). Pure-Polly stays byte-for-byte
  (`b''.join`). If the combine can't run (no ffmpeg), the whole stop is
  re-rendered on Polly so a broken multi-header file is never shipped.

The host service `kokoro_host_service.py` needed **no change** — it already does
one PCM-concat-then-single-encode per request.

## Test (red → green)

`tests/test_local575_kokoro_mp3_duration.py` (ffmpeg + ffprobe + mutagen):
- Characterises the defect: byte-concatenated per-chunk MP3s have a header ≈ the
  first chunk and ≥N Xing headers.
- Proves the fix: `combine_mp3_chunks` and a **4,500-char** `/synthesize` request
  (in-process path) each yield **one** header whose duration equals the real
  decoded (ffprobe) duration **within 1 %**; mixed Kokoro+Polly also within 1 %.

Verified **RED** on subscribed HEAD (the 4 fix tests fail — `combine_mp3_chunks`
absent; the e2e output shows 3 Xing headers) and **GREEN** after (5/5 pass). The
existing `tests/test_local573_kokoro_routing.py` still passes 13/13.

Live proof after deploy (real model, not a stub):
- Host `/render`, 4,600 chars → 1 Xing, header 239.064 s vs real 239.000 s.
- Container `/synthesize`, 5,200 chars → 1 Xing, header 299.376 s vs real
  299.325 s.

## Tour repair (388 + 389), in place

Backed up the original ZIPs to `tours/_backup_local575/` **first**:
`tour_388_55ba052f.zip` (the broken English/Kokoro tour) and `tour_389_ru.zip`
(the Russian translation). The authoritative audio is the `audio_tour` **bytea**
in `audio_tours`; the on-disk `~/Audioura/tours/…55ba052f.zip` copy was updated
to match.

**Tour 388** — rewrote the three multi-header files losslessly with
`ffmpeg -i in.mp3 -c:a copy -write_xing 1 out.mp3` (audio frames untouched; only
the Xing header rewritten). Re-zipped preserving the original 12-member order,
`unzip -t` clean, wrote the ZIP back to `audio_tours.id=388` (UPDATE, DB
round-trip md5 identical).

| file | header before | header after | real | within 1 % | PCM md5 before==after |
|---|---|---|---|---|---|
| audio_1.mp3 | 121.2 s | 203.808 s | 203.784 s | ✅ | ✅ identical |
| audio_2.mp3 | 98.14 s | 98.136 s (unchanged) | 98.075 s | ✅ | ✅ identical |
| audio_3.mp3 | 121.46 s | 146.616 s | 146.592 s | ✅ | ✅ identical |
| audio_4.mp3 | 122.45 s | 141.672 s | 141.687 s | ✅ | ✅ identical |

**Tour 389** (Russian / Polly, `original_tour_id=388`) — checked: all four files
already header==real (ratio 1.000, **0** Xing headers). Polly audio, no defect,
**no change** needed.

**Row counts (no DELETE):** `audio_tours` = **200 before == 200 after**. The only
write was one `UPDATE` of tour 388's `audio_tour` blob
(3,378,557 → 3,367,770 bytes).

## Deploy

- **Host service:** copied `kokoro_engine.py` (with `combine_mp3_chunks`) and
  `kokoro_host_service.py` to `/Users/micha/audioura-services/kokoro/` (the path
  in the `com.audioura.kokoro` launchd plist), cleared stale bytecode, then
  `launchctl kickstart -k gui/$(id -u)/com.audioura.kokoro`. `/health` →
  `healthy`, `pipeline_ready`, ffmpeg found.
- **polly-tts:** the `docker-compose.subscribed-local.yml` override builds
  polly-tts from `/Users/micha/audioura-subscribed-local` with
  `TTS_ENGINE=kokoro` + `KOKORO_URL=http://host.docker.internal:5181/render`.
  Its `polly_tts_service.py` / `kokoro_engine.py` were byte-identical to base
  `0242af3`, so the two fixed files were copied in (fix only, no regression),
  then rebuilt with the exact override command (no plain compose build):
  ```
  docker compose -p audioura -f docker-compose-master.yml \
    -f docker-compose.subscribed-local.yml up -d --no-deps --build polly-tts-1
  ```
  Container Up/healthy, `TTS_ENGINE=kokoro`, fix baked into `/app`.

No GCloud. No `audio_tours` DELETE.

## Files changed (git)

- `kokoro_engine.py` — PCM decode/encode + `combine_mp3_chunks`.
- `polly_tts_service.py` — whole-text host render; PCM-level recombine for the
  in-process path; Polly re-render guard.
- `tests/test_local575_kokoro_mp3_duration.py` — new.
- `tours/_backup_local575/tour_388_55ba052f.zip`, `tour_389_ru.zip` — originals.

Commits on `LOCAL-575-kokoro-mp3-duration`:
1. `a9edb39` — fix + test.
2. `6029794` — original ZIP backups.
3. (this) — submission notes.
