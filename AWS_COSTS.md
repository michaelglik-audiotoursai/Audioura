# AWS Polly + Translate — real cost per tour

**Task:** LOCAL-515. **Author:** Mac Mini Kiro (Amazon's agent). **Date:** 2026-09-23.
**Question (Michael, 2026-09-22):** *"The audio is done by AWS, the same way as
translation. Do you have data how much it costs?"*

Short answer: **yes, and the AWS side is not tracked anywhere.** The `cost_ledger`
`tts_generate` rows average **$0.0008**, which is wrong by ~150× — a 4-stop tour voices for
about **$0.12**. Every figure below is computed from a real artifact
(`TOURS_FOR_REVIEW/round7/CHURCH_2.txt`) and the exact code path, with each rate cited to
its AWS pricing page.

---

## 1. Current AWS list prices (per unit)

**Region we actually run in: `us-east-1`.** Confirmed in code, not assumed —
`polly_tts_service.py:48` (`region_name=os.getenv('AWS_REGION', 'us-east-1')`),
`translation-service/translation_service.py:25-26` (`region_name='us-east-1'` for both the
`translate` and `polly` clients), and `AWS_DEFAULT_REGION=us-east-1` in every compose file
(`docker-compose.yml`, `docker-compose-master.yml`, `docker-compose-beta-local.yml`).

### Amazon Polly
Source: <https://aws.amazon.com/polly/pricing/> (read 2026-09-23). Polly pricing is a flat
per-character rate that is the same across standard commercial regions including
`us-east-1` (the page quotes a single global rate; only AWS GovCloud (US) differs, at
$4.80 / $19.20).

| Voice class | List price | In this codebase? |
|---|---|---|
| **Standard** | **$4.00 per 1M characters** | Used only by the translation service's `generate_audio` (no `Engine` set → Polly default = standard) |
| **Neural** | **$16.00 per 1M characters** | **Yes — primary English path.** Voice `Joanna` is neural |
| **Long-Form** | $100.00 per 1M characters | **Not used** |
| **Generative** | $30.00 per 1M characters | **Not used** |

### Amazon Translate
Source: <https://aws.amazon.com/translate/pricing/> (read 2026-09-23).

| Translation type | List price |
|---|---|
| **Standard Text Translation** | **$15.00 per 1M characters** (incl. white space) |
| Real-Time Document Translation (Docx) | $30.00 per 1M characters |
| Active Custom Translation | $60.00 per 1M characters |

This codebase uses **Standard Text Translation** (`translate_client.translate_text`,
`translation_service.py`), so the rate that applies is **$15.00 / 1M chars**.

### Free tier — applies to a *new* account, cannot confirm for *this* account
From the same two pricing pages (read 2026-09-23):

- **Polly:** Standard = 5M chars/month (ongoing); Neural = 1M chars/month for the **first
  12 months**; Long-Form = 500K/month, Generative = 100K/month (both first 12 months).
- **Translate:** 2M chars/month for the **first 12 months** from your first translation
  request.

**I cannot confirm from the codebase whether this account is still inside those windows**
(the 12-month Neural/Translate clocks may have expired, and the account ID is not in the
repo). If pricing a subscription, price at the **full list rate** and treat any free tier
as a temporary discount, not a floor. Confirmed rates above; free-tier eligibility for this
specific account is **not confirmed** — do not build it into the price.

---

## 2. Which Polly voice class this codebase uses

**Neural.** Read from code, not assumed:

- `polly_tts_service.py:65` — `NEURAL_VOICES = frozenset(['Joanna', 'Matthew', 'Amy', 'Brian'])`
- `polly_tts_service.py:83` — `engine = 'neural' if voice_id in NEURAL_VOICES else 'standard'`
- The default and English voice is **`Joanna`** (`polly_tts_service.py:74`), and every
  caller of the main pipeline passes `Joanna`:
  `tour_generation_modernized.py:373`, `map_delivery_service.py:831,930`,
  `news_processor_service.py:200`, `tour_editing_phase2.py:1230`.

`Joanna ∈ NEURAL_VOICES`, so the English tour path bills at the **neural rate, $16/1M —
4× standard.**

Caveat on the translation service: `translation-service/translation_service.py:200-203`
calls `synthesize_speech(...)` **without an `Engine` argument**, so Polly falls back to the
**standard** engine ($4/1M) for translated audio, and it truncates each stop at
`text[:3000]`. That is a different, older code path from the main generator; both are
documented below.

---

## 3. Cost per (English) tour — computed from CHURCH_2.txt

The artifact is a 4-stop walking tour. The pipeline
(`tour_generation_modernized.py`) does two things that change the billable count:

1. `parse_tour_content_to_modernized` splits on `\n\s*Stop\s+(\d+):` and **drops the title
   block** before "Stop 1:" (it is never voiced).
2. `_strip_nav_fields_for_tts` removes the five metadata lines (`Address`, `Coordinates`,
   `Type/Specialty`, `Specific Examples`, `Operational Details`) from each stop before the
   text is POSTed to Polly. It **keeps** the stop name, `Orientation`, `Directions`, all
   narrative paragraphs, and the trailing "That's 4 stops…" summary.

I replicated that exact logic against the file:

| Stop | Stop content (chars) | Sent to Polly after nav-strip (chars) |
|---|---|---|
| 1 Nave | 2,882 | 2,621 |
| 2 Pulpit | 1,814 | 1,538 |
| 3 Altar | 1,625 | 1,400 |
| 4 Narthex | 2,281 | 2,033 |
| **Total** | **8,602** | **7,592** |

(Raw file is 8,759 chars; 157 chars of title/separator are dropped and not voiced.)

**Polly neural, 7,592 chars × $16.00 / 1,000,000 = $0.1215 per tour.**

Reference points (not the deployed path): standard voice would be
7,592 × $4/1M = **$0.0304**; long-form would be $0.759; generative $0.228.

---

## 4. Cost per translated tour (each additional language)

A translated tour needs (a) Amazon Translate on the text and (b) its own TTS audio.

**Translate basis = 8,602 chars.** The translation service translates the **full** stop
text — `self.translate_text(stop_text, target_language)`
(`translation_service.py:291`) — i.e. *including* the nav-field lines, then strips them
only for the TTS payload. So Translate bills on the full 8,602 chars, while Polly bills on
the stripped 7,592.

- **Amazon Translate:** 8,602 × $15.00 / 1,000,000 = **$0.1290**
- **TTS of the translated text:**
  - If voiced **neural** (matching the English path): 7,592 × $16/1M = **$0.1215**
  - If voiced **standard** (what the translation service's `generate_audio` actually does,
    no `Engine` set): 7,592 × $4/1M = **$0.0304**

**Per additional language, all-in:**

| TTS engine for the translation | Translate | + TTS | = per language |
|---|---|---|---|
| Neural (parity with English) | $0.1290 | $0.1215 | **$0.2505** |
| Standard (current translation-service code) | $0.1290 | $0.0304 | **$0.1594** |

Note: the translation service truncates each stop at 3,000 chars before Polly
(`text[:3000]`); no stop here exceeds that, so it does not change this tour's numbers.

---

## 5. Summary line

> **A 4-stop tour costs ~$0.16–0.19 to generate (LLM, from `cost_ledger`), $0.12 to voice
> (Polly neural), and ~$0.16–$0.25 more per additional language ($0.13 Amazon Translate +
> $0.03 standard-voice TTS, or +$0.12 if the translation is voiced neural like English).**

- **$X generate** = LLM text generation, tracked in `cost_ledger`, **not** an AWS Polly/
  Translate cost. Latest measured figures (`FEATURE_PLAYBOOK.md`: $0.050 mean all-sizes,
  $0.068 museum N=8; recent runs $0.16–0.19 for a full storied pipeline). This is context,
  not a rate I re-derived here — the AWS side is what was missing.
- **$Y voice = $0.1215** (Polly neural, 7,592 chars) — this is the AWS number that was
  untracked.
- **$Z per extra language = $0.1594 standard / $0.2505 neural** (Translate on 8,602 +
  TTS on 7,592).

---

## What this changes for pricing

1. **Audio is not negligible.** The ledger's $0.0008 `tts_generate` average is wrong by
   ~150×. Voicing (~$0.12) is roughly 40% of an English tour's all-in cost. Michael's
   instinct to re-voice only the stops whose text changed is economically right — re-voicing
   all four stops is the expensive half.
2. **A cheap lever exists.** Joanna neural is $16/1M vs standard $4/1M. Dropping English to
   a standard voice cuts voicing from $0.12 to $0.03 — a voice-quality decision, not an
   engineering one.
3. **Translate ≠ the $0.3213 in the ledger.** That $0.3213 `translation_generate` figure is
   LLM spend. Amazon Translate for this tour is **$0.129**, separate and previously
   unrecorded.

## Verification & limits

- Rates: quoted verbatim from the two AWS pricing pages cited above, read 2026-09-23.
- Character counts: computed by replaying the exact `parse_tour_content_to_modernized` +
  `_strip_nav_fields_for_tts` logic on `TOURS_FOR_REVIEW/round7/CHURCH_2.txt`.
- **Not confirmed:** free-tier eligibility for this specific AWS account (12-month windows
  may have lapsed; account ID not in repo). Priced everything at full list rate to be safe.
- **Not confirmed:** the $X generation figure is cited from existing repo measurements
  (`cost_ledger` / `FEATURE_PLAYBOOK.md`), not re-measured in this task — the AWS side was
  the gap this task closes.
