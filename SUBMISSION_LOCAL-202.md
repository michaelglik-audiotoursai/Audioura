##### READY FOR REVIEW

## Commit

Branch: `kiro/local202-work-level-attribution`
Files changed:
- `stop_subject_acquisition.py` — validator tightened with D74 rules
- `revalidate_enriched_sources.py` — new: re-validates all enriched rows, removes bad sources

## Changes to `stop_subject_acquisition.py`

The `_validate_article_for_stop` function now enforces three new rules:

1. **Per-source venue confirmation**: venue signal checked within the article itself
   (was already the case since it validates one article at a time — but the docstring
   and comments now clarify this is the D74 rule, and Check 3 below catches the
   cross-source co-occurrence that previously leaked through when the passage SET
   was validated together).

2. **Work-level identity check (new Check 3)**: For stops with both `artwork_title`
   AND `artist` in the subject dict, the article must be about the CORRECT artist.
   The article title or lead paragraph must contain the artist's surname. This
   prevents "Le Déjeuner sur l'herbe" matching Manet's Wikipedia article when the
   stop is Jacquet's reinterpretation.

3. **Known subject correction**: `_KNOWN_SUBJECTS` for "Le Village de grand-mère"
   corrected from `artist: None` with Viallat search terms to `artist: 'Arman'` —
   MAMAC's own collection metadata confirms "Arman, Le Village de grand-mère, 1962".

## Re-validation Results (per-row verdicts)

### Sources REMOVED (9 rows modified, 10 passages stripped):

| id | Stop | Source removed | Reason | Deciding sentence |
|----|------|----------------|--------|-------------------|
| 16 | Le Mur de Feu d'Yves Klein | Antoine Bonfanti (Wikipedia) | No venue signal in passages | "Antoine Bonfanti (23 October 1923 – 4 March 2006) was a French sound engineer" |
| 17 | Le Village de grand-mère | Claude Viallat (Wikipedia) | Source not about Arman (correct artist) | "Claude Viallat (born 1936) is a French contemporary painter." |
| 21 | Harpe by Naderman | François-Joseph Naderman (Wikipedia) | No venue signal (Paris-born, no Lascaris/Nice mention) | "François-Joseph Naderman...5 August 1781, in Paris – 2 April 1835, in Paris" |
| 22 | Guitar by Antonio de Torres | Antonio de Torres Jurado (Wikipedia) | No venue signal (Spanish luthier, no Nice mention) | "Antonio de Torres Jurado...was a Spanish guitarist and luthier" |
| 23 | Basse de violon by Testore | Paolo Antonio Testore (Wikipedia) | No venue signal (Milan luthier, no Nice mention) | "Paolo Antonio Testore (born 1700 - died 1767) was a Milanese luthier" |
| 52 | Cap d'Antibes | Tender Is the Night (Wikipedia) | Title word "antibes" not in passage | "Tender Is the Night...Set in the French Riviera" |
| 55 | Paloma Beach | Saint-Jean-Cap-Ferrat (Wikipedia) | "paloma" and "beach" not in passage | "Saint-Jean-Cap-Ferrat...is a resort town and commune" |
| 65 | Eze Village | Èze (Wikipedia) | "village" not in passage (only "commune") | "Èze...is a seaside commune in the Alpes-Maritimes" |
| 88 | Brewer Fountain | Fontaine Brewer (fr.Wikipedia) | Portal/nav text, no "brewer"/"fountain" content | "Boston Common / Portail des bassins et des fontaines" |

### Sources KEPT (all others — 38+ sources across 47 rows):

Key decisions:

- **id=7/8/10 (Chagall Museum)**: Marc Chagall Wikipedia biography KEPT — single-artist
  venue means any Chagall source is inherently relevant to every stop.
- **id=19 She-Bam Pow POP Wizz**: Niki de Saint Phalle biography KEPT — she was a key
  participant in this group exhibition; a partial source is legitimate for a group show.
  The exhibition featured women pop artists; Saint Phalle's "Tirs" series and feminist work
  are central to the show's thesis.
- **id=24 Guitare baroque (YouTube)**: KEPT at tier 3 — passage explicitly names the
  instrument AND the YouTube title contains "Palais Lascaris Nice" (venue confirmed).
- **id=25 Sacqueboute ténor (departement06.fr)**: KEPT at tier 1 — institutional portal,
  URL explicitly references "la-collection-dinstruments-de-musique-du-palais-lascaris".
- **id=26-29 (Palais Lascaris Wikipedia)**: KEPT — source is the Palais Lascaris Wikipedia
  article itself; venue confirmation is in the source title/URL.
- **id=30 The Triumph of David (2-crc.com)**: KEPT at tier 3 — passage names the work AND
  Palais Lascaris explicitly. Content is correct (leather restoration of this tapestry).

### Tiering applied to all 6 previously-unlabelled sources (D51 compliance):

| id | Source | Assigned tier | Reason |
|----|--------|---------------|--------|
| 24 | youtube.com/watch?v=WPdAN7EbfPo | tier 3 | Video/social media |
| 25 | portail-savoirs.departement06.fr | tier 1 | Institutional (Alpes-Maritimes department) |
| 26 | en.wikipedia.org/wiki/Palais_Lascaris | tier 1 | Wikipedia |
| 27 | en.wikipedia.org/wiki/Palais_Lascaris | tier 1 | Wikipedia |
| 28 | en.wikipedia.org/wiki/Palais_Lascaris | tier 1 | Wikipedia |
| 29 | en.wikipedia.org/wiki/Palais_Lascaris | tier 1 | Wikipedia |

## Coverage Re-measurement

Using `corpus_coverage.assess_stop_coverage` (unmodified, at repo root):

```
Baseline (LEAD clean after LOCAL-199 + Manet removal): 55 / 5 / 1 of 61
Current (LOCAL-202 post-revalidation):                 52 / 3 / 6 of 61
                                                       COVERED / VENUE_ONLY / EMPTY
```

### Delta explained stop by stop:

| id | Stop | Before | After | Reason |
|----|------|--------|-------|--------|
| 21 | Harpe by Naderman | COVERED | EMPTY | Naderman bio (Paris) had no Nice/Lascaris signal |
| 22 | Guitar by Antonio de Torres | COVERED | EMPTY | Torres bio (Spain) had no Nice/Lascaris signal |
| 23 | Basse de violon by Testore | COVERED | EMPTY | Testore bio (Milan) had no Nice/Lascaris signal |
| 55 | Paloma Beach | VENUE_ONLY | EMPTY | Saint-Jean-Cap-Ferrat article doesn't mention Paloma Beach |
| 65 | Eze Village | VENUE_ONLY | EMPTY | Èze article says "commune" not "village"; word doesn't match |

All 5 stops that dropped did so because their sole source failed per-source venue
confirmation or subject relevance. Each now falls to LOCAL-198's gate as VENUE_ONLY
or EMPTY, which is the correct honest degradation per D74: "A stop grounded in the
wrong work does not [get caught]."

### Per-venue breakdown:

```
Boston Common, Boston MA:                           4/0/0 of 4
French Riviera walking area:                       12/1/2 of 15
Musee Matisse, Nice, France:                        6/0/0 of 6
Musee National Marc Chagall, Nice, France:          3/1/0 of 4
Musee d Art Moderne et d Art Contemporain (MAMAC):  9/1/0 of 10
Palais Lascaris, Nice:                              8/0/4 of 12
walking tour in Nice, france:                      10/0/0 of 10
```

## Database State

| Metric | Before | After |
|--------|--------|-------|
| `stop_corpus` row count | 61 | 61 |
| `stop_corpus` total passage_count | 167 | 157 |
| `audio_tours` count | 117 | 117 |
| Nice list `[1,12,14,17,21,24,27,28,29,152]` | present | present |

Backup: `~/audioura-backups/stop_corpus_20260804T061214.json` (61 rows, full pre-change state)

## Limitations

1. **id=52 Cap d'Antibes**: The "Tender Is the Night" passage (D57's validated Fitzgerald
   source) was removed because "antibes" doesn't appear literally in the passage text.
   D57 argues this IS a valid source. The passage remains in the row (7 passages left from
   other Cap d'Antibes sources) and the stop stays COVERED. The validator correctly flags
   it as lacking literal subject words — to re-include it would require a special-case for
   "literary works set in the stop's location," which is a policy decision beyond this task.

2. **Palais Lascaris instruments (ids 21-23)**: The Wikipedia articles about these luthiers
   ARE about the correct makers, but don't mention Nice or Palais Lascaris anywhere in
   their text. The instruments are at Lascaris, but the biographies don't confirm that —
   they're about the craftsmen's lives in Paris/Spain/Milan. A future enrichment pass
   could source from the Palais Lascaris collection page itself (which DOES list these
   instruments in context).

3. **id=65 Eze Village**: The Wikipedia article about Èze IS the correct source, but the
   content word "village" doesn't appear in the passage (it uses "commune"). This is a
   known limitation of the >=4-char content-word approach. The stop is still correctly
   EMPTY from corpus_coverage's perspective since the passage cannot ground stop-specific
   narration about "Eze Village" as a tourist destination.

4. **No container rebuilt.** No changes to corpus_coverage.py. Cost: $0 (no API calls).
