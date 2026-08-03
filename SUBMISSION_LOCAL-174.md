##### READY FOR REVIEW

## LOCAL-174: Stop-Anchor Detector

**Commit:** `422f856` on branch `kiro/local174-stop-anchor-detector`
**Base:** `storied`

### Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `tests/stop_anchor_detector.py` | +949 | Detector + prevalence report |

### What it does

Classifies every paragraph in a tour stop as:
- **ANCHORED** — contains a proper noun, date, or entity that the venue corpus ties to this stop
- **NO_ANCHOR** — no stop-tied fact at all (Michael's "interchangeable prose" failure mode)
- **UNLINKED_ENTITY** — names a person/work/title that the corpus does not connect to this stop (Michael's "name-dropping without a link" failure mode)

Detection is deterministic and reproducible — no LLM opinion in the detector (D51.3).

### Sanity check: Michael's examples

**Example 1** (generic Cap d'Antibes prose):
> "Cycling on the French Riviera, stop at Cap d'Antibes to experience the enduring power of nature, inspiring creativity and stimulating the imagination while admiring panoramic views and soaking up the atmosphere of this everyday paradise."

**Result: NO_ANCHOR ✓** — Geographic self-references (Cap d'Antibes, Riviera) correctly filtered as substitutable place names per Michael's test.

**Example 2** (Fitzgerald name-drop):
> "As you stand on Cap d'Antibes with Mediterranean sea stretching out before you Imagine the scene that once captivated Scott Fitzgerald inspiring the setting of his timeless novels."

**Result: UNLINKED_ENTITY ✓** — "Scott Fitzgerald" extracted as proper noun; corpus has no entry linking Fitzgerald to Cap d'Antibes. (He genuinely lived there, but our corpus doesn't know it — exactly the intended behavior per D50/D51.)

### Prevalence report (7 tours, 218 paragraphs)

| Tour | Corpus | ANCHORED | NO_ANCHOR | UNLINKED |
|------|--------|----------|-----------|----------|
| 1: Palais Lascaris (museum) | YES | 38.9% | 22.2% | 38.9% |
| 29: French Riviera Biking | YES (thin) | 0.0% | 34.4% | 65.6% |
| 12: Nice walking tour | NO | 0.0% | 37.7% | 62.3% |
| 24: Chagall museum | YES (rich) | 70.0% | 20.0% | 10.0% |
| 14: Naïve Art museum | NO | 0.0% | 60.4% | 39.6% |
| 46: Boston Common | YES (thin) | 0.0% | 16.7% | 83.3% |
| 44: MAMAC Nice | YES (rich) | 88.2% | 5.9% | 5.9% |
| **GRAND TOTAL** | | **19.7%** | **34.9%** | **45.4%** |

### Key finding: prevalence is HIGH — **80.3% of all paragraphs fail the anchor test**

The detector flags the vast majority of content. This is a finding that changes gate design:
- Tours with rich corpus (MAMAC 88%, Chagall 70% anchored) pass well
- Tours without corpus match get 0% anchored — everything flagged
- Walking/distributed tours have thin or no corpus per-stop, so the anchor test flags ~100%
- **A validation gate at these rates would reject most existing tours**

### Sample ANCHORED paragraphs (named anchors for human judgment)

| Tour | Stop | Anchor | Quality |
|------|------|--------|---------|
| Palais Lascaris | Triumph of David | "Palais Lascaris" (corpus_mention) | WEAK — venue name is self-referential |
| Palais Lascaris | Triumph of David | "Baroque" (corpus_mention) | WEAK — generic art term in corpus |
| Palais Lascaris | Annunciation | "Christ" (corpus_mention) | WEAK — religious term, not stop-specific fact |
| Chagall | Abraham et les trois anges | "Marc Chagall" (corpus_mention) | MEDIUM — artist name, expected |
| MAMAC | Le Village de grand-mère | "Niki de Saint Phalle" (corpus_mention) | STRONG — specific artist for this work |

**Honest assessment of ANCHORED quality:** Many "anchored" paragraphs match on weak tokens (venue name, art period terms, religious figures) that appear in the corpus by coincidence rather than because the paragraph contains a stop-specific fact. The anchor test is necessary but not sufficient — a stronger version would require the anchor to be a *distinguishing* fact, not merely a word that appears in both corpus and paragraph.

### False-positive discussion

1. **ANCHORED but human-generic:** "As you enter the Palais Lascaris, make your way to the Grand Salon" — anchored on "Palais Lascaris" appearing in corpus, but the sentence is wayfinding, not stop-specific storytelling.

2. **UNLINKED_ENTITY but actually valid:** "David" and "Goliath" flagged as UNLINKED for The Triumph of David stop — these ARE the painting's subject but the corpus happens not to mention them by name (corpus describes instruments, not paintings). The painting's subject matter is genuinely specific to this stop.

3. **NO_ANCHOR but stop-specific:** Physical descriptions ("The painting showcases Raquel in a moment of quiet contemplation") — specific to this artwork but lacks named entities the corpus would contain.

### Database verification

- `audio_tours` row count before: **108**
- `audio_tours` row count after: **108**
- Read-only: no INSERT, UPDATE, or DELETE executed

### Constraints honored

- ⛔ No generation changes
- ⛔ No container rebuilds/recreations/restarts
- ⛔ No paid searches
- ⛔ No DELETE FROM anything
- ⛔ DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched

### Limitations

1. **Corpus availability determines everything.** Tours without a matching `venue_corpus` entry get 0% ANCHORED regardless of actual content quality. The detector measures "can we substantiate from our corpus" not "is this paragraph generic."

2. **Per-stop corpus matching is approximate.** For museum tours, story elements are matched to stops by title-word overlap. For walking tours with no per-stop corpus entries, all paragraphs are compared against the general area corpus (which is thin for most areas).

3. **Entity extraction is heuristic.** Uses capitalization-based proper noun detection — will miss entities in non-Latin scripts, will produce false positives on sentence-initial words and generic terms.

4. **The "corpus_mention" anchor type is weak.** Finding a word from the paragraph somewhere in the corpus text (substring match) does not prove the corpus *ties that entity to this stop*. A stricter test would require co-occurrence within a narrow context window.

5. **Implication for gate design (D51.1):** At 80% failure rate, a blocking gate would reject most existing tours. Options: (a) enforce only on storied-mode tours with rich corpus, (b) lower threshold to NO_ANCHOR-only (ignoring UNLINKED_ENTITY), (c) require corpus enrichment (LOCAL-175 search-based remedy) before gating.
