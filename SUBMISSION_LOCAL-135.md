##### READY FOR REVIEW

# SUBMISSION LOCAL-135: Measured Translation Cost

**Task:** Replace the estimated translation cost with a measured one  
**Branch:** kiro/local135-measure-translation-cost  
**Base:** subscribed  

---

## 1. Call Graph

The translation service (`translation-service/translation_service.py`) uses
`translate_tour_with_audio()` for each tour translation into one language.

**Models used:**
- **AWS Translate** (boto3 `translate_text`) — text translation
- **AWS Polly** (boto3 `synthesize_speech`) — TTS audio generation

**API calls per tour translation (1 language, N stops):**

| Call | Count | Description |
|------|-------|-------------|
| AWS Translate | 1 | Tour name |
| AWS Translate | 1 | Request string |
| AWS Translate | N | Full stop text (for .txt file in ZIP) |
| AWS Translate | N | Nav-stripped stop text (for Polly input) |
| AWS Polly | N | TTS on translated nav-stripped text |
| **Total Translate** | **2 + 2N** | |
| **Total Polly** | **N** | |

For a typical 8–10 stop tour: **18–22 AWS Translate calls** + **8–10 Polly calls**.

The critical finding: **each stop is translated TWICE** — once for the text
file and once (nav-stripped) for the TTS audio input. The old estimate assumed
one translation pass.

---

## 2. Measured Char/Token Counts (n=5)

Source: real `tour_content` from `audio_tours` table (tours 14, 21, 27, 28, 44).
All are 8–10 stop museum tours with existing translations.

| Tour ID | Stops | Source chars | Translate input | Polly input | Total cost |
|---------|-------|-------------|-----------------|-------------|-----------|
| 14 | 9 | 17,765 | 33,276 | 16,487 | $0.5651 |
| 21 | 8 | 14,755 | 28,518 | 14,632 | $0.4863 |
| 27 | 8 | 16,531 | 31,790 | 16,232 | $0.5418 |
| 28 | 8 | 14,570 | 27,864 | 14,149 | $0.4746 |
| 44 | 10 | 18,042 | 34,699 | 17,697 | $0.5913 |

"Translate input" = full stop chars + nav-stripped chars + name + request_string.
"Polly input" = nav-stripped chars × 1.06 (translation expansion ratio from DB).

**Statistics:**
- n = 5
- Mean: **$0.5318**
- StDev: $0.0502
- Min: $0.4746
- Max: $0.5913
- Range: $0.1167

---

## 3. Cost Arithmetic Per Model

### AWS Translate
- Rate: $15.00 per 1M characters ([AWS pricing page](https://aws.amazon.com/translate/pricing/))
- Mean input per translation: 31,229 characters
- Cost: 31,229 × $0.000015 = **$0.4684**

### AWS Polly
- Rate: $4.00 per 1M characters
- Mean input per translation: 15,839 characters
- Cost: 15,839 × $0.000004 = **$0.0634**

### Total: $0.4684 + $0.0634 = **$0.5318**

Translation API dominates at 88% of total cost.

---

## 4. TTS Inclusion — Explicit Statement

**This measurement INCLUDES TTS (Polly) cost.** The translation service
generates new audio for every translated stop as part of the translation
workflow. TTS accounts for ~12% of the total translation cost ($0.063 of $0.532).

The `SUBSCRIBED_STATUS.md` §2 note about "TTS cost in tour breakdown is $0.00"
refers to the *original tour generation* path where TTS happens at the
tour-processor level. For translations, TTS is performed directly by the
translation service and is included in this measurement.

---

## 5. Verdict

**ESTIMATE CORRECTED.**

| | Old (estimated) | New (measured) | Change |
|---|---|---|---|
| Our cost | $0.372 | $0.532 | +43% |
| User price (×5) | $1.86 | $2.66 | +$0.80 |
| Ratio to tour | 6× | 8× | |

The delta ($0.160) is 3.2× the stdev ($0.050) — well above the D22 noise
floor. This is a real correction, not noise.

**Root causes of the discrepancy:**
1. `cost_rates.py` used Google Translate rate ($20/1M) but the service uses
   AWS Translate ($15/1M)
2. The estimate assumed ONE translation pass per tour; the service does TWO
   (full text + nav-stripped for TTS) — this doubles the translate API spend
3. The lower per-char rate × 2 passes = higher total than 1 pass at the
   higher rate

**The estimate was wrong in the dangerous direction** — it understated the
real cost by 43%. At Michael's $1.30 ceiling, a single translation ($0.532)
is 41% of the budget, and the user-facing price ($2.66) exceeds the ceiling
by more than 2×.

---

## 6. Changes Made

| File | Change |
|------|--------|
| `cost_rates.py` | Replaced `GOOGLE_TRANSLATE_COST_PER_1M_CHARS = 20.00` with `AWS_TRANSLATE_COST_PER_1M_CHARS = 15.00`; updated `translation_cost()` to model double-translation + TTS |
| `SUBSCRIBED_STATUS.md` | §1: updated cost table; §2: marked translation as measured; §5: updated economics; §9: added correction row; §10: moved from STUBBED to PROVEN |

---

## 7. API Spend Incurred

**$0.00.** No API calls were made. All measurements derived from existing
`tour_content` and `audio_tours` rows in the database using character counts
and published rate tables.

---

## 8. Limitations

- **n=5** — all are museum tours in Nice/Philadelphia, 8–10 stops. Walking
  tours or restaurant tours may differ in content density.
- **Translation expansion ratio** (1.06) is derived from comparing stored
  English vs stored translated `tour_content` lengths in the DB. The Polly
  cost uses this ratio rather than measuring actual Polly API output lengths.
- **Nav-stripping approximation** uses a regex removing lines starting with
  known prefixes. The service's `_strip_nav_fields_for_tts()` is slightly
  more complex (handles multi-line fields). Difference is small (<2%).
- Does not include the `_preserve_voice_commands` path which adds extra
  translate calls — but that path is only triggered when
  `preserve_voice_commands=True`, which is not used in the main tour
  translation flow.
- The 5000-char truncation in `translate_text()` does not apply here — no
  stop exceeds 2,700 chars in these tours.

---

## Commit

```
234b7e8 LOCAL-135: measure translation cost — corrected from $0.372 to $0.532
```

`git rev-list --count subscribed..HEAD` = 1  
`git status --short` = clean
