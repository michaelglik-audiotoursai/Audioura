[tool] Reading tour_551.txt:1
[tool] status: Completed
# Audio Tour Review: National Gallery, London (tour_551.txt)

**Score: 6.5/10**

A competent, listenable three-stop tour that leads with works and artists and keeps good emotional register. It is undermined by one serious factual red flag: *The Supper at Emmaus* did **not** go to Cardinal Scipione Borghese or stay in the Borghese collection — the London version's provenance story is confused. Stop 2 is thin (missing birth facts, missing the famous Suffragette slashing — a genuine theft/attack story the owner explicitly welcomes), and admission hours are plausible but the closing time phrasing is loose.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "passed into the hands of Cardinal Scipione Borghese and stayed in the Borghese collection in Rome" | 8 — invented/wrong provenance (the Mattei London version did not enter the Borghese collection) | High |
| 1 | "In 1601, the Roman nobleman Ciriaco Mattei commissioned Caravaggio..." | 1 — borderline dry provenance; acceptable as minority story but lacks motive/consequence | Low |
| 2 | "In 1688, 'The Toilet of Venus' was inherited by the Duchess bringing this masterpiece into the renowned Alba collection." | 1 — leads with dry collection-transfer filler, not the work/artist; no named person or motive | Medium |
| 2 | (absent) no mention of the 1914 Suffragette (Mary Richardson) slashing | 1 — misses the welcome theft/attack-and-recovery human story the brief prizes | Medium |
| 2 | (absent) Velázquez's life "at that moment" / critical reception | 1 — artist-life and critics' voice omitted | Medium |
| 3 | "nestled between the counties and Essex" | 8 — garbled text, missing county name (Suffolk); reads as broken/invented | Medium |
| 1 | "open daily from 10:00 to 6:00" | 3 — hours spoken (good) but closing phrased loosely; NG closes 18:00 and Fri 21:00, not stated | Low |
| — | "That's 3 stops in all." + reflective paragraph | 7 — stop count stated but shortness never explained as by-request | Low |

Notes in favor: hours and admission are spoken (criterion 3 met), admission "free" is correct for the National Gallery (criterion 8 — price correct), no URLs or source lists (criterion 4 met), the restaurant offer is correctly the final sentence only (criterion 5 fine), no repeated story across stops (criterion 2 met), and there is a genuine thematic conclusion (criterion 6 met). All three works genuinely hang at the National Gallery (criterion 8 — no misattributed-museum defect).

## Three highest-value code-level improvements

1. **Add a provenance/claims fact-check gate keyed to the specific object, not the artist.** The Borghese error happened because the generator attached a generic "famous Caravaggio → Borghese" association to the London Mattei picture. Introduce a per-artwork validation step that cross-checks any named collector/collection claim against the specific accession record before it reaches narration, and drops unverifiable provenance rather than fabricating a chain.

2. **Detect and repair dropped-span text artifacts.** "nestled between the counties and Essex" is a template slot that lost its value (Suffolk). Add a post-generation lint that flags sentences with dangling connectors ("between X and", "the counties and") and empty noun slots, failing the stop until the gap is filled.

3. **Enforce a per-stop "lead with work + artist-life + reception + human story" completeness check.** Stop 2 passed through with no artist-life beat, no critical reception, and omitted the signature Suffragette-attack story. Add a rubric scorer per stop that requires those elements (and prefers a named-person/motive/consequence story when one exists for the work) and demotes stops that lead with dry collection-transfer dates.
