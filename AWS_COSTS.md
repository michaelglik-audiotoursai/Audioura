# AWS Polly & Translate — Real Cost per Tour (LOCAL-3495)

**Question (Michael, 2026-09-22):** *"The audio is done by AWS, the same way as
translation. Do you have data how much it costs?"*

This document answers it from **AWS list prices** and a **real tour artifact**
(`TOURS_FOR_REVIEW/round7/CHURCH_2.txt`, a 4-stop walking tour). No estimates —
every rate is cited to the AWS pricing page, and every character count is derived
by replaying the exact text-cleaning the code applies before it calls AWS.

> **Why `cost_ledger` looks wrong.** `tts_generate` averaging **$0.0008** and
> `translation_generate` averaging **$0.3213** do not reflect AWS charges:
> - The $0.0008 TTS figure is impossible for a ~9k-char tour at the neural rate
>   (that alone is ~$0.12). It is almost certainly the *LLM* legacy constant
>   `GPT35_TURBO_COST_PER_1K_TOKENS = 0.0008` (`cost_rates.py`) leaking into a
>   mislabeled row, or metering that never fired (the Polly meter is wrapped in a
>   non-fatal `try/except`, see `polly_tts_service.py`).
> - The $0.3213 `translation_generate` figure is **LLM** spend. **AWS Translate is
>   not metered anywhere** in `cost_ledger`. This document computes it for the
>   first time.

---

## 1. Region and account

- **Region we run in: `us-east-1`.** Hardcoded/defaulted in both AWS clients:
  - `polly_tts_service.py`: `region_name=os.getenv('AWS_REGION', 'us-east-1')`
  - `translation-service/translation_service.py`:
    `boto3.client('translate', region_name='us-east-1')` and
    `boto3.client('polly', region_name='us-east-1')` (region passed literally, no env override).
- All rates below are the **standard commercial `us-east-1` list prices**, which
  are AWS's uniform prices for Polly and Translate (they are not region-tiered in
  commercial regions; only **GovCloud** differs — Polly Standard $4.80, Neural
  $19.20 per 1M — and we do **not** run in GovCloud).
- **Free tier: cannot be confirmed from the codebase.** The Polly/Translate free
  tiers are per-account and time-boxed to the first 12 months (see rates below).
  Whether *this* AWS account is still inside that window requires AWS billing
  access I do not have. **If the account is >12 months old, the free tier no
  longer applies and every character is billed at the rates below.** Do not price
  the subscription assuming free-tier coverage.

---

## 2. Current AWS list prices (confirmed 2026-09-23)

### Amazon Polly — https://aws.amazon.com/polly/pricing/
| Voice class | Price | Free tier (first 12 months) |
|---|---|---|
| **Standard** | **$4.00 / 1M characters** | 5M chars/month |
| **Neural** | **$16.00 / 1M characters** | 1M chars/month |
| **Long-Form** | **$100.00 / 1M characters** | 500K chars/month |
| **Generative** | **$30.00 / 1M characters** | 100K chars/month |

Billed on characters submitted (including whitespace). Cached/replayed audio is free.

### Amazon Translate — https://aws.amazon.com/translate/pricing/
| Type | Price | Free tier (first 12 months) |
|---|---|---|
| **Standard Text Translation** | **$15.00 / 1M characters** | 2M chars/month |
| Real-Time Document (Text & HTML) | $30.00 / 1M characters (Docx) / $15.00 (Text/HTML) | none |
| Active Custom Translation | $60.00 / 1M characters | 500K chars/mo, 2 months |

We use **Standard Text Translation** ($15.00/1M) — `translate_text()` calls
`translate_client.translate_text(...)`, the real-time text API.

---

## 3. Which Polly voice class this codebase uses — **Neural** (read, not assumed)

**English tour generation** (the main pipeline) uses a **Neural** voice:

- `tour_generation_modernized.py` posts each stop to the Polly service with
  `"voice": "Joanna"`. (Note: the service reads the key `voice_id`, not `voice`,
  so this actually falls through to the default — which is also `Joanna`.)
- `polly_tts_service.py` then selects the engine:
  ```python
  NEURAL_VOICES = frozenset(['Joanna', 'Matthew', 'Amy', 'Brian'])
  engine = 'neural' if voice_id in NEURAL_VOICES else 'standard'
  ```
  `Joanna` ∈ `NEURAL_VOICES` ⟹ **`engine='neural'` ⟹ $16.00 / 1M**.

We do **not** use Long-Form or Generative voices — those strings never appear in
the code; `synthesize_speech` is only ever called with Standard/Neural engines.

**Caveat — the translation service uses a *different* (Standard) voice.** The
separate `translation-service/translation_service.py` calls
`polly_client.synthesize_speech(...)` **without an `Engine` argument** (defaults to
Standard) using per-language voices (`Lucia`, `Celine`, `Marlene`, `Tatyana`,
`Zhiyu`, `Seoyeon`, default `Joanna`). So **English audio is billed at the Neural
rate; translated audio is billed at the Standard rate.** Both figures are given below.

---

## 4. Characters actually sent to AWS (from the real artifact)

`CHURCH_2.txt` is **8,759 characters** on disk. But the code does not send the raw
file to Polly. The pipeline (a) splits it into 4 stops, then (b) strips the
non-narrated metadata lines — `Address:`, `Coordinates:`, `Type/Specialty:`,
`Specific Examples:`, `Operational Details:` — via `_strip_nav_fields_for_tts()`
before calling Polly. I replayed exactly that logic:

| Stop | Raw stop chars | After nav-strip (sent to Polly) |
|---|---|---|
| 1 — Nave | 2,882 | 2,611 |
| 2 — Pulpit | 1,814 | 1,538 |
| 3 — Altar | 1,625 | 1,400 |
| 4 — Narthex | 2,281 | 2,022 |
| **Total** | **8,602** | **7,571** |

- **7,571 characters** are submitted to **Polly** for the English tour (chunk-count
  accounted per `polly_tts_service.py`, which re-splits stops >2000 chars on word
  boundaries — this shaves a handful of separator characters vs. the raw 7,592).
- **8,602 characters** are submitted to **Translate** per language — translation
  runs on the *full* stop text (nav lines included; they are stripped *after*
  translation), per-stop, capped at 5,000 chars/call (none of these stops hit the cap).

---

## 5. Cost per tour

### English tour — TTS only (Neural)
```
7,571 chars × $16.00 / 1,000,000 = $0.1211
```
**≈ $0.121 to voice the English tour.** (For reference, if it were a Standard
voice: 7,571 × $4/1M = **$0.030**.)

> There is **no AWS "generate" cost** for the English tour text itself — the text
> is written by the LLM (tracked in `cost_ledger`), and the only AWS spend on the
> base tour is the Polly TTS above. So "cost to generate" (AWS side) = $0; the AWS
> cost is entirely in voicing.

### Each additional language (Translate + translated TTS)
Per language, the code does two AWS things: translate the text, then voice the
translation.

```
Translate:      8,602 chars × $15.00 / 1,000,000            = $0.1290
Translated TTS: 7,592 chars × $4.00  / 1,000,000 (Standard) = $0.0304
                                                    ─────────
Per additional language                                     = $0.1594
```
**≈ $0.159 per additional language.** (If the translated audio were switched to a
Neural voice to match English quality, the TTS part becomes 7,592 × $16/1M =
$0.1215, making it **≈ $0.251 per language**.)

---

## 6. Summary line

> **A 4-stop tour (`CHURCH_2.txt`) costs $0.00 in AWS to *generate* (text is LLM,
> tracked separately), $0.12 to *voice* (Polly Neural, 7,571 chars @ $16/1M), and
> $0.16 more per additional language (AWS Translate $0.129 + Standard-voice Polly
> $0.030).**

Rounded, all-in AWS per tour:
- **English only:** ~**$0.12**
- **English + 1 language:** ~**$0.28**
- **English + 6 languages** (es, fr, de, ru, zh, ko — the configured `voice_map`):
  $0.121 + 6 × $0.159 ≈ **$1.08**

---

## 7. What is verified vs. not

- **Verified:** rates (both AWS pricing pages, read 2026-09-23); region
  (`us-east-1`, from source); voice class (Neural for English, Standard for
  translations, from source); character counts (replayed the exact
  `_strip_nav_fields_for_tts` + stop-split + Polly chunking logic on the real file).
- **Not verified (needs AWS billing access):** whether this account is still in
  its first 12 months and thus free-tier eligible. If it is, monthly volume within
  the free-tier caps (Polly Neural 1M chars/mo, Translate 2M chars/mo) is $0 —
  roughly the first ~130 English tours/month and ~230 translations/month. Beyond
  the caps, or after month 12, the per-tour costs above apply in full. **Price the
  subscription on the paid rates, not the free tier.**

### Source rate table in the repo
`cost_rates.py` already hardcodes these exact rates
(`POLLY_NEURAL_COST_PER_1M_CHARS = 16.00`, `POLLY_STANDARD = 4.00`,
`AWS_TRANSLATE_COST_PER_1M_CHARS = 15.00`) and they **match** the live pricing
pages as of 2026-09-23. The gap is not the rate table — it is that the Polly meter
is best-effort (non-fatal `try/except`) and AWS Translate is never metered at all,
so `cost_ledger` does not reflect real AWS spend.
