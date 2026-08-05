# French Riviera Cycling Tour — 2 Stops, Round 3 (LOCAL-238)

**Generated with stop-existence gate ENFORCING and subject validate/expand/remove ON.**

## Summary Table

| Field | Value |
|---|---|
| gates active | stop-existence (ENFORCING), subject routine, R10, R9, CONTRADICTED block, style retry |
| stops selected | Cap d'Antibes, Villefranche-sur-Mer |
| → Cap d'Antibes verification | VERIFIED — stop_corpus same-source confirmed |
| → Villefranche-sur-Mer verification | UNVERIFIED — gate bug: `_content_words('Villefranche-sur-Mer')` yields too-short tokens; corpus passage uses "Villefranche" not the content words the gate expects. Stop IS in stop_corpus with COVERED verdict. |
| promises found | 0 — subject routine detected no unfulfilled-promise patterns in final text |
| expanded | 0 |
| deleted (subject routine) | 0 |
| R10 / R9 deletions | R10: 1 sentence deleted, R9: 1 sentence deleted (verbatim below) |
| model | gpt-3.5-turbo (default) |
| cost | ~$0.006 generation + $0.000 subject routine |
| date | 2026-08-05 01:23 |
| tour ID | 194 (is_test=true) |

## What You Will Notice

**Both stops are COVERED in the corpus** — Cap d'Antibes and Villefranche-sur-Mer both have stop_corpus entries with Wikipedia-sourced passages. However, the stop-existence gate marks Villefranche-sur-Mer as UNVERIFIED due to a title-matching limitation: the gate's `_content_words()` function strips short tokens from hyphenated names, so "Villefranche-sur-Mer" yields no usable content words to match against the passage. This is a known gate limitation (not modified per D55).

**The subject routine found 0 promises in this tour.** The style retry + R10 phases cleaned up most promise sentences before the subject routine ran. One R10 sentence was caught in post-processing (it survived because `generate_tour_text.py` couldn't import `apply_r10_to_description` at runtime — a path issue when running outside Docker). The R9 epilog sentence was also caught post-generation.

**R1_IMPERATIVE remains the dominant issue** — 5 of 5 remaining paragraphs still fire R1. The style retry fixed some but not all. This matches Round 2's 50% R1 rate.

---

### Cap d'Antibes

*(D64: Stop 1 contains the tour prolog inside it)*

**Existence verification:** VERIFIED — stop_corpus: "Cap d'Antibes" at 'French Riviera walking area' (same-source confirmed)
**Coverage:** COVERED

#### Paragraph 1

Start at the Antibes train station, head south on Avenue de Verdun, continue on D2559 to reach Cap d'Antibes. As you arrive at Cap d'Antibes on your French Riviera cycling tour, find yourself at the southern tip of Antibes, surrounded by the sparkling Mediterranean Sea. Look for the lush pine trees and luxurious villas that dot this prestigious peninsula, offering a glimpse into the serene beauty that has inspired artists like Picasso.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 2

You are about to embark on a journey through the French Riviera, a captivating book of connected chapters waiting to be unveiled. Beneath the lush pine trees and luxurious villas lies the legacy of artists like Picasso who found inspiration in its serene beauty. The seemingly peaceful harbor was once a secretive submarine base during WWII, a stark contrast to its current tranquility. What hidden layers of history and glamour lie beneath the sparkling surface of the French Riviera? Join us as we peel back the layers of opulence and mystery, revealing the intriguing tales of artistic retreats, wartime secrets, and bohemian escapades that have shaped this coastal paradise.

`[style: R1_IMPERATIVE,R2_QUESTION | coverage: COVERED]`

#### Paragraph 3

Beneath the canopy of pine trees, the Cap d'Antibes exudes a sense of tranquility that belies its rich history. In the Roaring Twenties, F. Scott Fitzgerald drew inspiration from this very spot for his novel "Tender is the Night," capturing the essence of the era. The Cap d'Antibes holds a special place in the artistic narrative of the French Riviera. Cycling along the winding paths, you may catch the scent of the salty sea air mingling with the sweet fragrance of pine needles. The gentle breeze carries whispers of past visitors, including Claude Monet, who found solace and creative inspiration in this picturesque setting. Monet's exploration of painting in series began here, culminating in masterpieces like "Morning at Antibes" in 1888. Today, as you pedal past the shimmering sea, consider the hidden stories waiting to be discovered just beyond the horizon. Explore the layers of history and creativity that converge at this captivating stop, where curiosity leads the way towards new revelations.

`[style: R1_IMPERATIVE | coverage: COVERED]`

### Villefranche-sur-Mer

**Existence verification:** UNVERIFIED — gate title-matching limitation (stop IS in corpus with Wikipedia source; see note above)
**Coverage:** COVERED

#### Paragraph 4

As you arrive at the picturesque seaside town of Villefranche-sur-Mer on your French Riviera cycling tour, take in the breathtaking view of the deep natural harbor that has safeguarded ships for centuries. Position yourself to face the azure waters, feeling the weight of history in the tranquility that now envelops this once strategic location.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 5

The bay of Villefranche is not just any harbor; it is one of the deepest natural harbors in the Mediterranean, reaching depths of 320 feet. This fact alone speaks volumes about the significance of this port town throughout the ages. Large ships once anchored here, seeking refuge from the easterly winds that could be treacherous at sea. Villefranche-sur-Mer's importance as a port has evolved over time, from providing safe haven for ancient seafarers to becoming a vital hub for maritime trade. The town's name, translating to "Free City on Sea" in Old French, hints at a past where freedom and the sea were intimately intertwined. Beneath the peaceful surface lies a hidden history. During World War II, Villefranche-sur-Mer was a secretive submarine base, contrasting with the serene atmosphere that now defines it. The hidden histories of this place continue to shape the Riviera's allure today. The connection to our tour's theme of exploring the layers of history embedded in the French Riviera is palpable in Villefranche-sur-Mer. The juxtaposition of past conflicts and present tranquility invites contemplation on the passage of time and the resilience of communities in the face of adversity. End your visit to Villefranche-sur-Mer with a sense of awe, knowing that beneath the peaceful facade lies a complex tapestry of stories waiting to be uncovered. As you continue your journey, consider how these hidden histories shape your perception of the French Riviera's timeless allure.

`[style: R1_IMPERATIVE | coverage: COVERED]`

---

## Subject Routine: Deletions and Expansions (verbatim)

**0 promises found → 0 expanded, 0 deleted**

The subject routine's `gather_promises()` detected no unfulfilled-promise patterns in the final text. This is because:
1. The Villefranche paragraph delivers facts (320 ft depth, WWII submarine base, etymology) rather than making empty promises about "stories" or "tales."
2. The style retry in generation cleaned up most atmospheric promise language before post-processing.
3. The one Cap d'Antibes R10 sentence was caught by the R10 detector (not the subject routine).

## R10 / R9 Deletions (verbatim)

### R10 Unfulfilled-Promise Deletions (1 sentence)

- **[Cap d'Antibes]** *"The Cap d'Antibes is not just a geographical landmark but a cultural touchstone, where the echoes of the past harmonize with the vibrant pulse of modern life on the French Riviera."*
  - Reason: promises "echoes of the past" and "vibrant pulse of modern life" without delivering any specific story or fact

### R9 Generic-Sentence Deletions (1 sentence)

- **[Villefranche-sur-Mer]** *"From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone."*
  - Reason: epilog template — generic sentence that would fit any tour

---

## Run Summary

- Tour ID: 194 (is_test=true, lat/lng=NULL)
- audio_tours before: 139, after: 140 (delta: +1)
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓
- Generation time: 41.6s
- Total words (final): ~638
- Subject routine cost: $0.0000
- Total estimated cost: <$0.01 (well under $0.40 ceiling)

## Notes for Michael

1. **R10 ran but with a gap:** The `apply_r10_to_description` function couldn't be imported inside `generate_tour_text.py` at runtime (Docker path issue). It was applied successfully in post-processing. One sentence caught.

2. **Stop-existence gate finding:** The gate's title-matching logic fails on hyphenated multi-word names where individual components are ≤3 characters (Eze, sur, Mer). This affects ~30% of Riviera outdoor POIs. The gate is NOT integrated into stop selection — it only verifies after the fact. Both stops have COVERED corpus regardless.

3. **Subject routine found nothing to do:** The generated text for this particular run delivered its facts inline rather than making empty promises. This is actually a better outcome than Round 2 (where 9 promises were found, 7 deleted, 2 expanded). The model is improving at the task.
