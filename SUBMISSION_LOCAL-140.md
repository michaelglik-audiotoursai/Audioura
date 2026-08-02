##### READY FOR REVIEW

# SUBMISSION LOCAL-140: Translation Pricing Options

**Task:** Cost translations honestly and lay out pricing options — decide nothing  
**Branch:** kiro/local140-translation-pricing-options  
**Base:** subscribed  

---

## 1. Is the Second Translation Pass Avoidable?

**Yes.** Eliminating it saves ~44% of translation cost ($0.23 per translation).

### Code evidence

In `translation-service/translation_service.py`, `translate_tour_with_audio`
(lines 286–297), each stop is processed with two `self.translate_text()` calls:

```python
# Line 290 — full stop text for .txt file
translated_stop = self.translate_text(stop_text, target_language)

# Line 294 — nav-stripped text for Polly TTS
tts_text = self.translate_text(self._strip_nav_fields_for_tts(stop_text), target_language)
```

`_strip_nav_fields_for_tts` (lines 1199–1220) removes 5 field types:
Address, Coordinates, Type/Specialty, Specific Examples, Operational Details.
These represent only ~5–10% of stop text (measured: 220 of 2639 chars in
tour 14, stop 1). The remaining ~92% is translated identically in both calls.

### Why avoidable

The translated full text (from the first call) already contains the narrative
in the target language. The nav fields become translated labels
(`Type/Spécialité\xa0:`, `Exemples spécifiques\xa0:`, etc.) on individual
lines with predictable structure. These can be detected and stripped from the
already-translated text without a second API call.

Evidence from DB (tour 14 → French, `audio_tours.id=20`):
```
L 8: 'Type/Spécialité\xa0: Art religieux'          ← identifiable, strippable
L10: 'Exemples spécifiques\xa0: représentation...'  ← identifiable, strippable  
L12: 'Informations sur le musée\xa0: ouvert...'     ← identifiable, strippable
```

The existing `_restore_metadata_labels` method already contains logic
(`_is_translated_metadata`) to detect translated nav lines. Extending this
approach is straightforward.

### What would break

Nothing breaks in the TTS audio path. Risk: subtle translation quality
difference from missing context. In practice, AWS Translate processes
segment-by-segment; nav fields are self-contained lines that do not provide
meaningful context to narrative paragraphs.

### Savings

```
Mean current cost:       $0.5318
Second-pass cost:        $0.2327 (0.95/1.95 of translate API, which is 88% of total)
Cost after removal:      $0.2991
At ×5:                   $1.50 (vs $2.66 today)
```

---

## 2. Cache Hit Rate

### Ledger data

```sql
SELECT operation_type, cache_hit, COUNT(*), SUM(our_cost_usd)
FROM cost_ledger WHERE operation_type LIKE 'translation%'
GROUP BY operation_type, cache_hit;
```

Result:
```
translation_generate   | cache_hit=False | count=1 | $0.3720
translation_cache_hit  | cache_hit=True  | count=1 | $0.0000
```

**Insufficient data.** n=2. The cost_ledger started 2026-07-31 18:15 UTC;
11 of 12 translations pre-date it.

### Delivery tracking

No delivery-level counter exists. The `audio_tours` table stores translations
but does not track how many times each is downloaded. `tour_requests` has no
non-English rows. Amortised cost per *delivered* translation cannot be
computed from existing data.

---

## 3. Options Table

Delivered in `TRANSLATION_PRICING.md` at repo root. Ten options with worked
numbers, a multi-translation scenario, and break-even analysis for the
first-requester model. No recommendation disguised as a conclusion.

---

## 4. Changes Made

| File | Change |
|------|--------|
| `TRANSLATION_PRICING.md` | New file — analysis document (261 lines) |

---

## 5. API Spend

**$0.00.** All analysis derived from reading source code and querying existing
database rows. No translations, no LLM calls, no container operations.

---

## 6. Limitations

- **n=5 tours measured in LOCAL-135** — all museum tours, 8–10 stops. Nav
  field proportion may vary for other tour types (walking tours have less
  structured metadata).
- **Translation quality after single-pass** is theoretically equivalent but
  not proven. Would need A/B test or human review in multiple language pairs.
- **Delivery re-serve rate unknown** — no infrastructure to track it.
  Option 9 (first-requester model) cannot be implemented without new
  tracking.
- **The $0.2991 single-pass cost is calculated**, not measured end-to-end.
  The actual cost after implementation may differ by the stdev (~$0.05).

---

## 7. Commit

```
44e83c3 LOCAL-140: translation pricing options — analysis document, no code changes
```

`git rev-list --count subscribed..HEAD` = 1  
`git status --short` = clean
