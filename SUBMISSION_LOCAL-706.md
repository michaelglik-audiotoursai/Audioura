# SUBMISSION — LOCAL-706: Foreign-name pronunciation in the Kokoro voice path (D667)

**Agent:** Mac Mini Kiro  **Branch:** `LOCAL-706-kokoro-pronunciation`  **Base:** `subscribed` (9e6d761c)
**Ticket:** D667 — Michael prefers the free Kokoro voice (the Mac stack's English default,
`TTS_ENGINE=kokoro`, rendered whole on the host service via
`polly_tts_service._render_whole_via_host`). LOCAL-692B's Vietnamese-name aid was applied
**only in the Polly path** (SSML), so real English tours reached Kokoro with the raw
diacritic names — and Kokoro's G2P (misaki) cannot pronounce them.

---

## 1. The problem, proven

Kokoro's front-end is the **misaki** grapheme-to-phoneme engine. A bare Vietnamese
diacritic name tokenises to the **unknown-phoneme marker** — nothing the voice can say:

```
Nguyễn Gia Trí  ->  misaki phonemes:  ❓ ❓ ❓
Nguyễn Sáng     ->  misaki phonemes:  ❓ ❓
Tô Ngọc Vân     ->  misaki phonemes:  ❓ ❓ ❓
```

(Reproduced with the real `misaki.en.G2P(lang_code='a')` in `~/kokoro-venv`, the exact
pipeline the host service loads.)

## 2. What was built

misaki accepts an **inline pronunciation markup** — `[grapheme](/IPA/)` — and uses the
slash-delimited IPA verbatim as the token's phonemes (confirmed by reading
`misaki/en.py` `preprocess()` / `tokenize()` in the installed 0.9.4, and by round-tripping
every lexicon IPA through the real G2P). This is Kokoro's own equivalent of Polly's
`<phoneme>`/`<sub>` split, so the fix mirrors LOCAL-692B in Kokoro's form.

| File | Change |
|---|---|
| `pronunciation_lexicon.json` | **NEW generic lexicon** (not Vietnamese-only): per entry `language`, `written`, `ipa` (misaki US-English phonemes for Kokoro), `respelling`, `variants`, `sources`. Seeded with the 7 verified HCMC names. French/Russian/etc. are added here later with no code change. |
| `vietnamese_name_aid.py` | Loads the JSON on import and overlays it onto the in-code `LEXICON` (soft/fail-safe). New `kokoro_pronunciation()` / `to_kokoro()`: wrap the **first mention** of each known name in `[name](/IPA/)` when IPA is present, else substitute the verified English **respelling** for the spoken text. New `kokoro_ipa` attribute keeps misaki IPA **separate** from Polly's `<phoneme>` alphabet. The Polly SSML path and the narration text are **byte-for-byte unchanged**. |
| `polly_tts_service.py` | New `_maybe_kokoro_markup()`, wired into **`_render_whole_via_host`** (the host path Michael uses) and the in-process Kokoro fallback. Only the **audio request string** is annotated; the stored/visible tour TEXT is untouched. Fail-open: with the aid missing or on any error, the original text is sent, so Kokoro renders exactly as before. |
| `test_local706_kokoro_pronunciation.py` | **13 unit tests** — lexicon load/overlay, first-mention markup, respelling fallback, no-name passthrough, visible-text-unchanged, **Polly path non-regression** (asserts misaki IPA never leaks into Polly SSML), service wiring, and the **real-misaki round-trip** for every lexicon IPA. |
| `Dockerfile.local706-eval`, `run_local706_eval.py` | Evaluation harness (own disposable image/containers only; never `audioura-*`). |

**The visible/printed tour text never changes** — only the string handed to the TTS
engine. No `(say: …)` and no markup is ever read aloud (misaki consumes the markup; it is
not spoken).

## 3. Host service — nothing for LEAD to deploy on the host

The Kokoro **host service** (`~/audioura-services/kokoro/kokoro_host_service.py`, launchd
`com.audioura.kokoro`) needs **no change**: it already passes the request text straight to
`kokoro_engine.synthesize_to_mp3` → misaki, which parses `[name](/IPA/)` natively. The
repo copies of `kokoro_host_service.py` / `kokoro_engine.py` are unchanged.

**One deploy note for LEAD:** the production `Dockerfile.polly-tts` must add the two files
the aid needs to the image (the import is fail-open, so without them the service simply
runs as before — no pronunciation):

```dockerfile
COPY vietnamese_name_aid.py .
COPY pronunciation_lexicon.json .
```

That is the only production deploy delta. (`Dockerfile.local706-eval` already has these two
lines and was used for the evaluation.)

## 4. Evaluation — real path, HCMC tour 697

Rendered tour **697** (HCMC Museum of Fine Arts, 5 stops) through the **real** path —
my own disposable polly-tts container (`TTS_ENGINE=kokoro`,
`KOKORO_URL=http://host.docker.internal:5181/render`) → the **live Kokoro host service on
:5181** (`/health` = healthy, pipeline_ready, ffmpeg present). No Polly calls (English
voice → Kokoro). Containers `local706-after` (:5718) and `local706-before` (:5719) were my
own images, torn down after; no `audioura-*` container was touched.

**How each of the three names renders** (misaki phonemes, the real host G2P):

| Name | BEFORE (bare → host) | Sent to host AFTER | AFTER phonemes |
|---|---|---|---|
| Nguyễn Gia Trí | `❓ ❓ ❓` | `[Nguyễn Gia Trí](/ˈwɪn ˈʒɑ ˈʧi/)` | `ˈwɪn ˈʒɑ ˈʧi` |
| Nguyễn Sáng | `❓ ❓` | `[Nguyễn Sáng](/ˈwɪn ˈsɑŋ/)` | `ˈwɪn ˈsɑŋ` |
| Tô Ngọc Vân | `❓ ❓ ❓` | `[Tô Ngọc Vân](/ˈtO ˈnɑk ˈvʌn/)` | `ˈtO ˈnɑk ˈvʌn` |

**After-MP3 for Michael:** `tours/local706_mp3/HCMC697_after_FULL.mp3` — the 5 stops
combined with the project's PCM-combine encoder (one correct header), **479.95 s**, 2.88 MB.
Per-stop after-MP3s are alongside it; the before set is in `tours/local706_mp3_before/`.
Stops 4 & 5 (no target names) are **byte-identical** before/after; stops 1–3 (the three
names) differ — the expected, name-only signal.

## 5. Tests

```
# full suite with the real misaki G2P (kokoro-venv)
~/kokoro-venv/bin/python -m unittest test_local706_kokoro_pronunciation   # 13 tests, OK (ServiceWiring skipped: no boto3 here)
# full suite with boto3 present (system python3)
python3 -m unittest test_local706_kokoro_pronunciation                    # 13 tests, OK (misaki round-trip skipped: no misaki here)
# non-regression
~/kokoro-venv/bin/python -m unittest test_local692_artist_stories         # 28 tests, OK
```

Between the two interpreters every test executes at least once (misaki round-trip in the
venv, service wiring under system python3).

## 6. Safety / scope

- Default-safe & fail-open on both TTS paths: no name present, aid missing, or any error →
  the engine receives the original text and renders exactly as today.
- Polly path unchanged (guarded by a test): misaki IPA is kept in a separate `kokoro_ipa`
  field and never reaches Polly's `<phoneme>`.
- Own containers only; no `audioura-*` touched; no host-service edit; no
  DECISIONS/CLAUDE/BACKLOG/WORK_QUEUE/.continuous_dev edits.
