##### READY FOR REVIEW

## Commit

Branch: `kiro/local203-passage-roles`
Base: `storied`

Files changed:
- `passage_role_tagger.py` — new: assigns `about_subject` / `about_creator` / `about_venue` role per passage
- `corpus_coverage.py` — role-aware `assess_stop_coverage()` with `CREATOR_ONLY` verdict
- `generate_tour_text.py` — gate handles `CREATOR_ONLY`; prompt restricts to maker discussion only
- `stop_corpus_reader.py` — passes `passage_roles` through to coverage + prompt formatting

## What was done

1. **Schema**: Added `passage_roles` JSONB column to `stop_corpus` (array parallel to `passages_json`).

2. **Role tagging**: Every passage now carries a role decided by reading its content:
   - `about_subject` — describes the object, place, or exhibition at this stop
   - `about_creator` — biographical content about the maker/artist
   - `about_venue` — institutional/museum-level information
   - `null` — doesn't belong (wrong entity or unrelated content)

3. **Restorations**: Restored 5 rows emptied by LOCAL-202 where the role makes the source legitimate:
   - ids 21, 22, 23 (Naderman, Torres, Testore biographies → `about_creator`)
   - id 55 (Paloma Beach / Saint-Jean-Cap-Ferrat → `about_subject`)
   - id 65 (Eze Village / Èze commune → `about_subject`)
   - id 52 (Cap d'Antibes: restored the Tender Is the Night passage → `about_subject`)

4. **NOT restored** (wrong-entity errors that stay out):
   - id 17: Claude Viallat on "Le Village de grand-mère" (correct artist is Arman)
   - id 16: Antoine Bonfanti on "Le Mur de Feu d'Yves Klein" (sound engineer, not artist)

5. **Id 18 resolved under the same rule as 21/22/23**:
   - Richard Long's Wikipedia biography → `about_creator` (2 passages)
   - MAMAC Donations passage → `about_venue` (1 passage)
   - Links-only passage → `null` (1 passage)
   - **Verdict: CREATOR_ONLY** — no passage describes the specific artwork at MAMAC.
   - The "venue signal" that made it COVERED before came from the Donations passage (a DIFFERENT source), which is exactly the loophole D74 closed. One rule now applies to both id 18 and ids 21/22/23.

6. **Coverage is role-aware**: `assess_stop_coverage()` now accepts `passage_roles` and returns `CREATOR_ONLY` when the only valid roles are `about_creator`. The legacy word-match path remains for backwards compatibility when roles aren't available.

7. **Gate and prompt honour the role**:
   - `CREATOR_ONLY` stops get a prompt that says: "You may discuss the maker's biography and significance but must NOT describe the physical object."
   - `format_passages_for_prompt` annotates each passage with `[ROLE: about_creator]` / `[ROLE: about_subject]` so the model knows what content it may draw from for what purpose.

## Prompt language (CREATOR_ONLY restriction)

```
CORPUS GATE: CREATOR_ONLY (D75 enforcement — LOCAL-203):
The corpus for this stop contains information about the MAKER/ARTIST of "{poi_name}",
but does NOT contain verified information about the specific object/artwork itself.

YOU MAY:
- Discuss the artist's or maker's biography, career, and significance
- Mention their techniques, style, and historical context — IF stated in the passages
- Note that this maker created the work at this stop

YOU MUST NOT:
- Describe the object's appearance, dimensions, materials, or condition
- Claim what the visitor will see at this specific stop
- Invent details about the physical work from your training data
- State facts about the object that are not in the provided passages

Ground all claims about the maker in the passages provided. Do not describe the object.
```

## Coverage measurement

**Baseline (LOCAL-202 state, before this task):**
```
52 COVERED / 3 VENUE_ONLY / 6 EMPTY of 61
```

**After LOCAL-203 (role-aware):**
```
51 COVERED / 7 CREATOR_ONLY / 2 VENUE_ONLY / 1 EMPTY of 61
```

### Delta explained per stop:

| id | Stop | Before (LOCAL-202) | After (LOCAL-203) | Reason |
|----|------|-------------------|-------------------|--------|
| 18 | Richard Long ou la sculpture en marchant | COVERED | CREATOR_ONLY | Only creator bio; venue signal was from a different source (D74 loophole) |
| 21 | Harpe by Naderman (Paris, 1780) | EMPTY | CREATOR_ONLY | Restored maker bio with `about_creator` role |
| 22 | Guitar by Antonio de Torres (Almeria, 1884) | EMPTY | CREATOR_ONLY | Restored maker bio with `about_creator` role |
| 23 | Basse de violon by Paolo Antonio Testore (Milan, 1696) | EMPTY | CREATOR_ONLY | Restored maker bio with `about_creator` role |
| 55 | Paloma Beach | EMPTY | COVERED | Restored Saint-Jean-Cap-Ferrat passage (IS about this place) |
| 65 | Eze Village | EMPTY | COVERED | Restored Èze commune passage (IS about Eze Village) |
| 52 | Cap d'Antibes | COVERED | COVERED | Restored Tender Is the Night (novel set here); was already COVERED |
| 7 | Abraham et les trois anges | COVERED → VENUE_ONLY | CREATOR_ONLY | Chagall bio passages are about the creator, not this specific painting |
| 8 | L'Arche de Noé | COVERED → VENUE_ONLY | CREATOR_ONLY | Same — Chagall bio, not this specific painting |
| 19 | She-Bam Pow POP Wizz | COVERED | CREATOR_ONLY | Niki de Saint Phalle bio, not this specific group exhibition |
| 11 | Donations and deposits | VENUE_ONLY | VENUE_ONLY | Unchanged — venue-level by definition |
| 12 | Donations et dépôts | VENUE_ONLY | VENUE_ONLY | Unchanged — venue-level by definition |
| 31 | The Annunciation | EMPTY | EMPTY | Unchanged — no passages |

Net effect: 3 fewer COVERED (18, 7→already was, 8→already was), but the ones that moved are *honestly* classified — they never had about_subject content. 5 EMPTY→{CREATOR_ONLY, COVERED} via restoration.

## Database state

| Metric | Before (LOCAL-202) | After (LOCAL-203) |
|--------|-------------------|-------------------|
| `stop_corpus` rows | 61 | 61 |
| Total passage_count | 157 | 163 |
| `audio_tours` count | 117 | 117 |
| Nice list | `[1,12,14,17,21,24,27,28,29,152]` | `[1,12,14,17,21,24,27,28,29,152]` |

Backup: `~/audioura-backups/stop_corpus_20260804T063700_pre203.json` (61 rows, pre-change state)

## Verification: passages read and role decided (≥10 passages, ≥4 venues)

### 1. id=18, passage[0] — MAMAC — role: `about_creator`
> "Sir Richard Julian Long (born 2 June 1945) is an English sculptor, painter, photographer, and one of the best-known British land artists. Long is the only artist to have been short-listed four times for the Turner Prize."

**Deciding sentence:** "is an English sculptor" — biographical identification of the person, not description of a specific work at MAMAC.

### 2. id=18, passage[3] — MAMAC — role: `about_venue`
> "== Donations and deposits == Since the opening, Yves Klein has a room which displays approximately twenty of his works, several of them belonging to the permanent collection of the museum. In October 2001, Niki de Saint Phalle bequeathed a large part..."

**Deciding sentence:** "Since the opening...permanent collection of the museum" — describes the museum's institutional history, not the Richard Long artwork.

### 3. id=21, passage[0] — Palais Lascaris — role: `about_creator`
> "François-Joseph Naderman (French pronunciation: [...]; 5 August 1781, in Paris – 2 April 1835, in Paris) was a classical harpist, teacher and composer, the eldest son of the well-known eighteenth century harp maker Jean Henri Naderman."

**Deciding sentence:** "was a classical harpist, teacher and composer" — biographical identification. Describes the MAKER, not the harp at Lascaris.

### 4. id=22, passage[0] — Palais Lascaris — role: `about_creator`
> "Antonio de Torres Jurado (13 June 1817 – 19 November 1892) was a Spanish guitarist and luthier, and 'the most important Spanish guitar maker of the 19th century.' It is with his designs that the first recognizably modern classical guitars are to be seen."

**Deciding sentence:** "was a Spanish guitarist and luthier" — maker biography. Does not describe the specific 1884 guitar at Lascaris.

### 5. id=7, passage[0] — Chagall Museum — role: `about_creator`
> "Marc Chagall (en russe : Марк Захарович Шагал...), est un peintre et graveur né le 7 juillet 1887 à Liozna..."

**Deciding sentence:** "est un peintre et graveur né le..." — biographical opening. Does not describe "Abraham et les trois anges" the specific painting.

### 6. id=52, passage[0] — French Riviera — role: `about_subject`
> "Le cap d'Antibes désigne communément une presqu'île située au sud d'Antibes et à l'est de Juan-les-Pins, sur la Côte d'Azur en France."

**Deciding sentence:** "Le cap d'Antibes désigne communément une presqu'île" — directly describes the geographic location that IS the stop subject.

### 7. id=52, passage[7] — French Riviera — role: `about_subject`
> "Tender Is the Night is the fourth and final novel completed by American writer F. Scott Fitzgerald. Set in the French Riviera during the twilight of the Jazz Age..."

**Deciding sentence:** "Set in the French Riviera" — the novel is set at Cap d'Antibes; a passage about a literary work set at this location enriches the stop subject.

### 8. id=65, passage[0] — French Riviera — role: `about_subject`
> "Èze (French pronunciation: [ɛːz]...) is a seaside commune in the Alpes-Maritimes department... It is located on the French Riviera, 8.5 km to the northeast of Nice..."

**Deciding sentence:** "Èze...is a seaside commune" — directly describes the place. The word "commune" vs "village" is terminology; the article IS about Eze Village.

### 9. id=55, passage[0] — French Riviera — role: `about_subject`
> "Saint-Jean-Cap-Ferrat... is a resort town and commune in the Alpes-Maritimes department..."

**Deciding sentence:** Walking tour geography — Paloma Beach is on the Saint-Jean-Cap-Ferrat commune. The passage describes the location that contains this beach.

### 10. id=24, passage[0] — Palais Lascaris — role: `about_subject`
> "... baroque guitar by Giovanni Tesler (Ancona, 1618). Our guide also played a copy of a clarinet made by Jacques François Simiot..."

**Deciding sentence:** "baroque guitar by Giovanni Tesler (Ancona, 1618)" — explicitly names THIS specific instrument in the Lascaris collection.

### 11. id=16, passage[9] — MAMAC — role: `about_subject`
> "Yves Klein réalise sa première Peinture de feu en 1957 dans le jardin de la galerie Colette Allendy à Paris le soir du vernissage."

**Deciding sentence:** "Peinture de feu" — directly references the fire painting technique that IS the Mur de Feu artwork. About the subject work.

### 12. id=16, passage[2] — MAMAC — role: `about_creator`
> "Yves Klein est un artiste français, né le 28 avril 1928 à Nice et mort le 6 juin 1962 à Paris. En 1954, il se tourne définitivement vers l'art."

**Deciding sentence:** "est un artiste français, né le..." — biographical identification of Klein the artist, not description of the Mur de Feu specifically.

### 13. id=85, passage[0] — Boston Common — role: `about_subject`
> "Soldiers' and Sailors' Monument peut faire référence à..."

**Deciding sentence:** Names the monument itself — this IS the stop subject on Boston Common.

## Ambiguous cases noted

- **id=19 She-Bam Pow POP Wizz** (CREATOR_ONLY): The Niki de Saint Phalle biography is classified `about_creator`. This is a group exhibition — Saint Phalle was a participant, not the sole subject. However, no passage describes the specific exhibition itself. Verdict honestly: CREATOR_ONLY.

- **id=16 passages 0-1** (Bonfanti, role=null): These are about a sound engineer — wrong entity entirely. They get `null` role and are excluded from generation. They remain in the DB (D75: "do not delete a source to improve a metric") but marked as not belonging.

## Cost

$0.00 — no API calls. All work is local classification and DB updates.

## Limitations

1. **Id 18 is CREATOR_ONLY.** MAMAC's flagship experiment stop has no verified corpus about the *specific Richard Long artwork*. This explains why four rounds of generation produced fabrication findings: the model was inventing object-level claims from a creator biography. The CREATOR_ONLY gate now prevents this. To make it COVERED, someone would need to source a passage that describes the specific Long installation at MAMAC.

2. **Unclassified passages remain.** 41 passages got `null` role (primarily: Bonfanti wrong-entity passages on id=16, list-of-works passages on Chagall, and La Cambra/Ben passages that describe a different MAMAC artwork). These are not deleted from the DB but are excluded from the coverage verdict. A future pass could clean them.

3. **No container rebuilt.** The `passage_roles` column addition and tagger run operate on the live DB directly via `tests/db_connection.py`. The tour-generator container image does NOT have the new column schema cached — when the gate runs inside Docker, it will still work (the new `passage_roles` parameter to `assess_stop_coverage` defaults to `None`, falling back to the legacy word-match path). Role-aware verdicts take effect only when `stop_corpus_reader.py` passes the roles through (which requires the column to exist on the live DB — it does).

4. **Single-artist venue exception.** Chagall Museum ids 7 and 8 show CREATOR_ONLY because their passages are Chagall biographies. At a single-artist museum, the creator's biography IS relevant to every stop — but the *role* is still `about_creator`, not `about_subject`. The gate respects this: it allows discussing Chagall's life but not inventing details about "Abraham et les trois anges" the specific painting.
