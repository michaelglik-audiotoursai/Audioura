##### READY FOR REVIEW

**Commit:** `e63de74c80b397a8e2dad83c53423101ae223967`
**Branch:** `kiro/local354-price-band-from-guides`
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `guide_price_band.py` | New module. Lookup registry for Le Fooding and Gault&Millau guide prices; threshold derivation (ceil to next €10 above guide high); sentence combiner per Michael's format; gate source text builder. |
| `practical_facts_gate.py` | Added `_PRICE_BAND_PATTERN` regex, `price_band` claim type in `_parse_info_text_into_claims`, `_verify_price_band` verification function. Gate checks guide provenance + range + threshold match. |
| `generate_tour_text.py` | Integrated `guide_price_band.get_dining_sentence()` into the LOCAL-353 restaurant pipeline section. Combines guide price with OSM payment into one operational sentence per stop. |
| `tests/test_local354_guide_price_band.py` | 34 tests: threshold derivation (7), guide lookup (5), sentence combination (5), gate integration (2), gate strictness (4), absence handling (3), source text format (5), full API (3). |

---

## Per-venue table

| Venue | Guide | Value found | Derived threshold | Combined sentence |
|-------|-------|-------------|-------------------|-------------------|
| **La Merenda** | Le Fooding | "À la carte €31-43" | under €50 | "An average dinner or lunch would cost under €50 but credit cards are not accepted" |
| **Le Safari** | Gault&Millau | "Indicative price per person (excl. drinks) 32 to 55" | under €60 | "An average dinner or lunch would cost under €60" |
| **Fenocchio** | Gault&Millau (Artisan listing) | Ice cream parlour — no per-person meal budget published | **NONE — silence** | (empty) |
| **Acchiardo** | NOT LISTED | Not on Le Fooding, Gault&Millau, or Michelin Guide | **NONE — silence** | (empty) |

---

## Verbatim evidence from guides

### Le Fooding — La Merenda
- URL: https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6
- Page states: `prices: €36 to €50` (listing tag) and `PRICE: À la carte €31-43` (review text)
- "Payment by card not accepted" (corroborates OSM payment:credit_cards=no)

### Gault&Millau — Le Safari
- URL: https://fr.gaultmillau.com/en/restaurants/le-safari
- Page states: `Budget (€) Indicative price per person (excl. drinks) 32 to 55`
- Menu: "Menu à 32 €32 / Menu à 38 €38 / Menu à 43 €43 / Menu à 55 €55"

### Gault&Millau — Fenocchio
- URL: https://fr.my.gaultmillau.com/en/artisans/glacier-fenocchio
- Listed under "Artisans" (glacier) — NOT restaurants. No meal budget.

### Gault&Millau — Acchiardo
- Searched: not listed. Not in their Nice 2026 restaurant guide.
- Michelin Guide: no listing for Acchiardo.
- Le Fooding: no listing for Acchiardo.

---

## Gate audit lines

**Sourced price PASSING:**
```
price_band | An average dinner or lunch would cost under €50 but credit cards are not accepted | https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6 | VERIFIED
```

**Unsourced price DROPPED:**
```
price_band | An average dinner or lunch would cost under €40 | (no source) | DROPPED — no source content
```

**Inflated threshold DROPPED:**
```
price_band | An average dinner or lunch would cost under €100 | https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6 | DROPPED — not supported by source
```

---

## The combined sentence for La Merenda (verbatim)

> An average dinner or lunch would cost under €50 but credit cards are not accepted

---

## Regeneration required

**I cannot run regeneration.** `OPENAI_API_KEY` is not in my environment.
LEAD must run the pipeline with:
```bash
DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours python3 generate_tour_text.py ...
```
to produce tours with the new combined sentences.

---

## Museum bounds as properties (D258)

8-stop: **75.0** | 4-stop: **81.2**

---

## Limitations

1. **Static registry, not live scraping.** The guide prices are recorded from the live pages as of 2026-08-07. If Le Fooding or Gault&Millau change their published prices, the registry needs manual update. This is intentional — scraping would violate rate/ToS concerns and introduce failure modes.

2. **Two venues have no guide price.** Fenocchio (ice cream, not a restaurant-with-budget) and Acchiardo (simply unlisted on all three guides) correctly emit silence. If a guide lists them in future, the registry can be extended.

3. **Payment fact still requires OSM.** The combined sentence's "credit cards are not accepted" depends on LOCAL-353's OSM query finding `payment:credit_cards=no`. If that tag is ever removed from OSM, the payment half of the sentence will not appear (silence is correct).

4. **No container rebuild.** All changes are in Python source files and tests. No docker-compose or Dockerfile changes.
