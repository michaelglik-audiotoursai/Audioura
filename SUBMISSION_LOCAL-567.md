# SUBMISSION — LOCAL-567: Voice sample pack

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-567-voice-samples` (base: `subscribed` = `02aa094`)
**Date:** 2026-10-03

## Goal

Render the same tour stops in every TTS voice we can buy with the project's
existing keys (plus a local open-source model), blind-labeled so Michael can
pick by ear, with a verified price table and measurements. Michael's prompt:
Polly neural ≈ $0.15 per 4-stop tour is the next cost, "standard is bad" —
what else is there?

## TL;DR answer for Michael

- **Yes, there are cheaper neural-quality options than Polly neural.**
  OpenAI **tts-1** is slightly cheaper per character ($0.1425 vs $0.1520 per
  4-stop tour) and sounds more natural. **gpt-4o-mini-tts** is in the same ballpark
  (~$0.157/tour) and is the most expressive.
- **Self-hosted Kokoro is essentially free** (~$0.0019 per 4-stop tour of CPU on
  Cloud Run) — the trade is you run and maintain it.
- **Russian is the real constraint.** Amazon Polly offers **only standard** voices
  for Russian — no neural/generative/long-form exists for `ru-RU`. For a good
  Russian voice the reachable upgrade is OpenAI (E/F/G in the pack).
- Listen blind first: `voice_samples/` → `KEY.md` (instructions on top, key at
  the bottom). The same pack is on the Desktop at
  `~/Desktop/Audioura_voice_samples/`.

## The samples (blind labels)

20 MP3s in `voice_samples/`, named `<LETTER>_<lang>_<stop>.mp3`. Every engine
read the identical spoken text; nav fields were stripped using the same
`_strip_nav_fields_for_tts` logic as production (drops Address, Coordinates,
Type/Specialty, Specific Examples, Operational Details).

| Label | Engine | Files |
|---|---|---|
| A | AWS Polly neural (Joanna) | en stop1, en stop2 |
| B | AWS Polly generative (Joanna) | en stop1, en stop2 |
| C | AWS Polly long-form (Ruth) | en stop1, en stop2 |
| D | AWS Polly standard (Joanna en, Tatyana ru) | en stop1, en stop2, ru stop1 |
| E | OpenAI tts-1 (nova) | en stop1, en stop2, ru stop1 |
| F | OpenAI tts-1-hd (nova) | en stop1, en stop2, ru stop1 |
| G | OpenAI gpt-4o-mini-tts (nova) | en stop1, en stop2, ru stop1 |
| H | Kokoro open-source, local CPU (af_heart) | en stop1, en stop2 |

Source text:
- English — Palais Lascaris tour stops 1 & 2
  (`origin/LOCAL-563-gemini-baseline:tests/fixtures/local563/runs/lascaris_run1.txt`).
- Russian — tour 383 stop 1 (`audio_tours` id 383, derived from tour 301;
  read-only, no writes/deletes).

Character counts (after stripping): EN stop1 = 2,295; EN stop2 = 1,905
(4,200 for the two English stops); RU stop1 = 1,874.

## Price table (verified from official pricing pages)

Sources:
- AWS Polly pricing — https://aws.amazon.com/polly/pricing/
  (Standard $4.00, Neural $16.00, Generative $30.00, Long-Form $100.00 per 1M chars)
- OpenAI pricing — https://platform.openai.com/docs/pricing and
  https://platform.openai.com/docs/guides/text-to-speech
  (tts-1 $15.00/1M chars, tts-1-hd $30.00/1M chars; gpt-4o-mini-tts is token-billed,
  OpenAI's own stated estimate ~$0.015/minute of audio)
- Google Cloud Run pricing — https://cloud.google.com/run/pricing
  (Tier-1: $0.000024 / vCPU-second, $0.0000025 / GiB-second), used only to
  estimate the cost of self-hosting Kokoro.

A "4-stop tour" is taken as **9,500 spoken characters** (task reference).
"One translation" is costed on our measured Russian stop (1,874 chars).

| Label | Engine | Unit price | $ / 4-stop tour (9,500 chars) | $ / one translation stop (1,874 chars) |
|---|---|---|---:|---:|
| A | AWS Polly neural | $16 / 1M chars | $0.1520 | $0.0300 |
| B | AWS Polly generative | $30 / 1M chars | $0.2850 | $0.0562 |
| C | AWS Polly long-form | $100 / 1M chars | $0.9500 | $0.1874 |
| D | AWS Polly standard | $4 / 1M chars | $0.0380 | $0.0075 |
| E | OpenAI tts-1 | $15 / 1M chars | $0.1425 | $0.0281 |
| F | OpenAI tts-1-hd | $30 / 1M chars | $0.2850 | $0.0562 |
| G | OpenAI gpt-4o-mini-tts | ~$0.015 / min audio (token-billed) | $0.1572 | $0.0310 |
| H | Kokoro (self-host, Cloud Run 1 vCPU + 2 GiB) | compute-time only | $0.001911 | $0.000377 |

Notes:
- gpt-4o-mini-tts is **not** billed per character; it is billed on text+audio
  tokens. OpenAI's own guidance gives a composite estimate of ~$0.015/min of
  audio, which is what the tour/translation figures above use (scaled by our
  measured audio-seconds-per-character).
- Kokoro has no per-character list price — it is open source. The figures are a
  **CPU-time estimate** on Cloud Run from the measured synthesis time, assuming a
  1 vCPU + 2 GiB instance at Tier-1 rates. Real self-host cost also includes
  idle/min-instance time, which this does not model.

## Measurements (per sample)

Real-time factor = audio seconds / synthesis seconds (higher = faster to render).

| Label | Engine | Voice | Lang/Stop | Chars | Audio (s) | Synth (s) | RTF |
|---|---|---|---|---:|---:|---:|---:|
| A | Polly neural | Joanna | en/stop1 | 2295 | 140.6 | 2.41 | 58.4x |
| A | Polly neural | Joanna | en/stop2 | 1905 | 121.6 | 1.97 | 61.7x |
| B | Polly generative | Joanna | en/stop1 | 2295 | 146.7 | 29.85 | 4.9x |
| B | Polly generative | Joanna | en/stop2 | 1905 | 124.2 | 24.97 | 5.0x |
| C | Polly long-form | Ruth | en/stop1 | 2295 | 164.6 | 17.34 | 9.5x |
| C | Polly long-form | Ruth | en/stop2 | 1905 | 141.9 | 15.37 | 9.2x |
| D | Polly standard | Joanna | en/stop1 | 2295 | 138.6 | 1.84 | 75.3x |
| D | Polly standard | Joanna | en/stop2 | 1905 | 118.4 | 1.45 | 81.6x |
| D | Polly standard | Tatyana | ru/stop1 | 1874 | 126.9 | 0.93 | 136.4x |
| E | OpenAI tts-1 | nova | en/stop1 | 2295 | 145.1 | 7.77 | 18.7x |
| E | OpenAI tts-1 | nova | en/stop2 | 1905 | 125.6 | 5.46 | 23.0x |
| E | OpenAI tts-1 | nova | ru/stop1 | 1874 | 125.5 | 5.71 | 22.0x |
| F | OpenAI tts-1-hd | nova | en/stop1 | 2295 | 145.4 | 12.98 | 11.2x |
| F | OpenAI tts-1-hd | nova | en/stop2 | 1905 | 124.1 | 11.84 | 10.5x |
| F | OpenAI tts-1-hd | nova | ru/stop1 | 1874 | 125.3 | 11.87 | 10.6x |
| G | OpenAI gpt-4o-mini-tts | nova | en/stop1 | 2295 | 144.2 | 23.70 | 6.1x |
| G | OpenAI gpt-4o-mini-tts | nova | en/stop2 | 1905 | 117.2 | 18.44 | 6.4x |
| G | OpenAI gpt-4o-mini-tts | nova | ru/stop1 | 1874 | 139.1 | 36.06 | 3.9x |
| H | Kokoro (local CPU) | af_heart | en/stop1 | 2295 | 147.8 | 15.55 | 9.5x |
| H | Kokoro (local CPU) | af_heart | en/stop2 | 1905 | 130.3 | 13.52 | 9.6x |

(Synthesis time is wall-clock for a single request on this Mac mini / over the
network for the cloud engines; treat as indicative, not a benchmark. Kokoro ran
on local CPU.)

## Actual spend this run

Billed on characters actually submitted (English 4,200 chars + Russian 1,874
chars where applicable):

| Engine | Chars sent | Est. cost |
|---|---:|---:|
| A Polly neural | 4,200 | $0.0672 |
| B Polly generative | 4,200 | $0.1260 |
| C Polly long-form | 4,200 | $0.4200 |
| D Polly standard | 6,074 | $0.0243 |
| E OpenAI tts-1 | 6,074 | $0.0911 |
| F OpenAI tts-1-hd | 6,074 | $0.1822 |
| G OpenAI gpt-4o-mini-tts | 6,074 | $0.1001 |
| H Kokoro (CPU) | 4,200 | $0.0008 |
| **Total** | | **≈ $1.01** |

Well under the $3.00 cap.

## Engines skipped (and why)

- **Google Cloud TTS (Neural2 / WaveNet / Chirp 3 HD)** — **not callable** with
  existing credentials. Verified: no `gcloud` CLI, `GOOGLE_APPLICATION_CREDENTIALS`
  unset, no ADC file at `~/.config/gcloud/application_default_credentials.json`,
  and no Google service-account key in the project `.env`. The only Google key is
  `GEMINI_API_KEY` (Gemini generative API, which does not authenticate Cloud
  Text-to-Speech — that needs OAuth2 / ADC). No new account was created.
- **Polly neural / generative / long-form for Russian** — Polly offers only
  standard voices for `ru-RU` (Tatyana, Maxim). Documented in `KEY.md`.
- **Kokoro Russian** — English only, per the task.

## Method / reproducibility

Render scripts and intermediate files live under `/tmp/local567/` (not committed):
`prep_text.py` (nav-field stripping + stop extraction), `probe_polly.py`,
`render_polly.py`, `render_openai.py`, `render_kokoro.py`, `common.py`,
`normalize.py`, `tables.py`, and `measurements.jsonl` (raw per-sample metrics).
MP3s were re-encoded to a uniform 48 kbps mono so the pack is 16 MB (< 20 MB cap)
and every voice is auditioned at the same bitrate.

## Constraints honoured

- No GCloud deploy; no changes to the TTS service.
- `audio_tours` read-only — tour 383 was only SELECTed; no writes or deletes.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  `.continuous_dev/STATUS.md`.
- Branch cut from HEAD (`02aa094`), not from `origin/*`; `git add` + commit after
  every engine.
