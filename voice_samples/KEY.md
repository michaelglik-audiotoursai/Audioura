# Audioura voice sample pack (LOCAL-567)

The same tour stops, read by every text-to-speech engine we can reach with the
keys already in the project. Files are labeled with **letters only** so you can
listen blind and pick what sounds best before seeing which engine (and price)
is behind each one.

## What's inside

Each engine read the identical spoken text (nav fields such as Address /
Coordinates / Type-Specialty / Specific Examples / Operational Details were
stripped exactly as the production TTS path does, via
`_strip_nav_fields_for_tts`).

Source text:
- **English** — Palais Lascaris museum tour, **Stop 1** (Violes gambe by
  William Turner) and **Stop 2** (Harpe by Naderman).
  (`origin/LOCAL-563-gemini-baseline:tests/fixtures/local563/runs/lascaris_run1.txt`)
- **Russian** — Nice walking tour, **Stop 1** (Замок Холм Ниццы).
  (`audio_tours` id 383, derived from tour 301; read-only)

File naming: `<LETTER>_<lang>_<stop>.mp3`, e.g. `A_en_stop1.mp3`, `D_ru_stop1.mp3`.
All files were re-encoded to a uniform 48 kbps mono MP3 so the whole pack fits in
one commit and every voice is auditioned at the same bitrate.

## How to listen

1. Play the English pairs first: compare `*_en_stop1.mp3` across letters A–H,
   then `*_en_stop2.mp3`. Listen for naturalness, pacing, and how it handles the
   proper nouns (Violes gambe, Naderman, Palais Lascaris).
2. Then compare the Russian: `*_ru_stop1.mp3` across the letters that have it
   (D, E, F, G). This is where the engine choice matters most — see the notes.
3. Jot down your favourites by letter, *then* read the key at the very bottom.

## What's NOT here, and why

- **Russian neural / generative / long-form from Polly**: Amazon Polly offers
  **only standard** voices for `ru-RU` (Tatyana, Maxim) — no neural, generative,
  or long-form engine exists for Russian. So the only Polly Russian sample is
  standard (label **D**). For a better Russian voice, the OpenAI engines (E/F/G)
  are the reachable upgrade.
- **Kokoro Russian**: Kokoro was run for **English only**, per the task.
- **Google Cloud TTS (Neural2 / WaveNet / Chirp 3 HD)**: **skipped — not
  callable** with existing credentials. There is no `gcloud` CLI,
  no `GOOGLE_APPLICATION_CREDENTIALS`, no Application Default Credentials file,
  and no Google service-account key in the project `.env`. The only Google key
  present is `GEMINI_API_KEY`, which is for the Gemini generative API, not Cloud
  Text-to-Speech (that API requires OAuth2 / ADC). No new accounts were created.

## Notes for your ear

- **A (Polly neural)** is today's production voice — the $0.15/tour baseline.
- **B (Polly generative)** and **C (Polly long-form)** are Polly's premium tiers.
- **E/F/G (OpenAI)** are the main alternatives; **E (tts-1)** is actually a touch
  *cheaper* per character than Polly neural while sounding more natural.
- **H (Kokoro)** is open source running on local CPU — essentially free to self-host.

Prices, measurements, and the full rationale are in `SUBMISSION_LOCAL-567.md`
at the repo root.

---

<!-- Scroll past here only after you've picked your favourites. -->

## BLIND KEY (spoilers below)

| Label | Engine | Model | Voice | Languages present |
|---|---|---|---|---|
| A | AWS Polly — neural | polly-neural | Joanna (en) | EN |
| B | AWS Polly — generative | polly-generative | Joanna (en) | EN |
| C | AWS Polly — long-form | polly-long-form | Ruth (en) | EN |
| D | AWS Polly — standard | polly-standard | Joanna (en), Tatyana (ru) | EN, RU |
| E | OpenAI — tts-1 | tts-1 | nova | EN, RU |
| F | OpenAI — tts-1-hd | tts-1-hd | nova | EN, RU |
| G | OpenAI — gpt-4o-mini-tts | gpt-4o-mini-tts | nova | EN, RU |
| H | Kokoro (open source, local CPU) | kokoro-82M | af_heart | EN |

Voice choices explained:
- Polly neural/generative use **Joanna** (the current production default voice).
- Polly long-form uses **Ruth** because Joanna has no long-form engine; Ruth
  supports neural, generative, and long-form, so it was the closest match.
- Polly standard uses **Joanna** (EN) and **Tatyana** (RU) — Tatyana is the only
  female `ru-RU` voice, and standard is the only engine Polly offers for Russian.
- OpenAI uses one natural voice (**nova**) across every model and both languages.
- Kokoro uses **af_heart**, a default English voice in the open-source model.
