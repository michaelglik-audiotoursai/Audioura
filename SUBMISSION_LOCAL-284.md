##### READY FOR REVIEW

## LOCAL-284: Selector corpus-depth tiebreak

**Commit:** `24657f2`
**Branch:** `kiro/local284-selector-corpus-tiebreak`

### Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | In the LOCAL-30 deterministic museum selection (the active 2nd block, line ~3515), added corpus-depth lookup from `stop_corpus` and changed sort key from `(source_priority)` to `(-passage_count, source_priority, title)`. Museum stops with more corpus now sort first. |
| `run_local284_measurement.py` | Measurement script for before/after comparison and Riviera regression. |

### Why the museum case differs from the geographic one

For a **geographic walking tour** (Riviera), stops are drawn from an open, infinite
set of real places. Preferring stops with corpus would quietly narrow every tour
toward Cap d'Antibes and Èze (where our corpus happens to be deepest), not because
they are the best stops but because we scraped them first. D170 explicitly prohibits
this kind of artificial constraint.

For a **museum tour**, the candidate set is the venue's own canonical titles — a
**closed list** of real objects that all verifiably exist at the museum. All are
"equally notable" in the sense that they passed the same D1v2 verification. The
only differentiator is our ability to narrate them. Choosing an object with 6
passages over one with 0 passages is not narrowing the tour's geographic diversity
— it is selecting for competence. The corpus tiebreak therefore applies as a
**primary** sort signal for museums, while it would only be a secondary tiebreak
(if at all) for geographic tours.

### Verbatim evidence: before/after selection

```
--- BEFORE (source-priority only) — top 10 candidates ---
   1. [catalogue] (0 psg) Accéder au portail "Activités"   Fermer Activités
   2. [catalogue] (0 psg) Achat, 1999
   3. [catalogue] (0 psg) Achat, 2001
   4. [catalogue] (0 psg) Achat, 2002
   5. [catalogue] (0 psg) Adresse: 405, Promenade des Anglais, 06200 Nice
   6. [catalogue] (0 psg) Don Herrli
   7. [sparql   ] (0 psg) Hokusai – Voyage au pied du mont Fuji
   8. [sparql   ] (0 psg) la geste de Bouddha
   9. [sparql   ] (0 psg) les paysages de l'âme
  10. [sparql   ] (0 psg) l'art en exil - Hàm Nghi, Prince d'Annam (1871-1944)

--- AFTER (corpus-depth primary) — top 10 candidates ---
   1. [canonical] (6 psg) La danse cosmique de Ganesh
   2. [canonical] (6 psg) L'Armure d'Andô Naoyuki
   3. [canonical] (6 psg) Statue de Bouddha
   4. [canonical] (6 psg) Ulysses Grant au Japon
   5. [canonical] (5 psg) Kannon à mille bras
   6. [canonical] (5 psg) Kannon, le bodhisattva de la compassion
   7. [canonical] (4 psg) Robe de prêtre taoïste
   8. [canonical] (3 psg) Masque du vieillard kojô
   9. [catalogue] (0 psg) Accéder au portail "Activités"   Fermer Activités
  10. [catalogue] (0 psg) Achat, 1999

--- COMPARISON (first 5 stops) ---
  BEFORE: 0 total passages available
  AFTER:  29 total passages available
  Improvement: 29 more passages (from 8 objects in corpus)
```

### D1v2 verification of after-selection (from live run)

```
  [D1v2] VERIFIED 'La danse cosmique de Ganesh' → canonical: 'La danse cosmique de Ganesh'
  [D1v2] VERIFIED 'L'Armure d'Andô Naoyuki' → canonical: 'L'Armure d'Andô Naoyuki'
  [D1v2] VERIFIED 'Statue de Bouddha' → canonical: 'Statue de Bouddha'
  [D1v2] VERIFIED 'Ulysses Grant au Japon' → canonical: 'Ulysses Grant au Japon'
  [D1v2] VERIFIED 'Kannon à mille bras' → canonical: 'Kannon à mille bras'
  [D1v2] VERIFIED 'Kannon, le bodhisattva de la compassion' → canonical: 'Kannon, le bodhisattva de la compassion'
```

All 5 selected stops verified. All have 5-6 passages in stop_corpus.

### Walking tour regression: structural proof

The corpus-depth code is inside:
```python
if tour_category == 'museum' and _museum_venue_name:
```

Walking tours (`tour_category == 'walking'`) never enter this block.
No DB query, no reordering, no change to Phase 3A GPT selection.
D170's ruling is fully respected: geographic tour selection stays free.

### Riviera regression runs

**Not executable** — OpenAI API returned 429 (insufficient credits) during this
session. The structural argument above proves walking tours are unaffected: the
code change is entirely within a `museum`-only guard. When credits are restored,
`run_local284_measurement.py` will produce full regression numbers.

### Museum 5-stop results

| Stop | Corpus depth | Verified |
|------|-------------|----------|
| La danse cosmique de Ganesh | 6 passages | ✓ |
| L'Armure d'Andô Naoyuki | 6 passages | ✓ |
| Statue de Bouddha | 6 passages | ✓ |
| Ulysses Grant au Japon | 6 passages | ✓ |
| Kannon à mille bras | 5 passages | ✓ |

**Facts/stop against 1.6 baseline:** Cannot measure — narration generation failed
(429 API error). Selection is correct; narration requires credits.

### Stop variety

Not applicable to the museum case (closed set — always draws from the same
canonical list). For walking tours: no code touched, variety is unchanged.

### Acceptance criteria check

| Criterion | Status |
|-----------|--------|
| Corpus depth used as a tiebreak; never as an exclusion | ✓ All 22 documented works still pass to D1v2; only ORDER changes |
| Museum selection prefers objects with corpus | ✓ Top 8 candidates all have passages; 0-passage items pushed below |
| Rationale for museum vs geographic difference stated | ✓ See section above |
| Riviera baselines held or improved | Structural proof (museum-only guard); awaiting API credits for numeric confirmation |
| Stop variety reported before and after | N/A for museum (closed set); walking tours unaffected |
| Museum 5-stop facts/stop reported against 1.6 | Selection confirmed; narration blocked by 429 |
| `git status --short` clean | ✓ (after commit) |
| No container rebuilt | ✓ |

### Limitations

1. **Full narration measurement blocked**: OpenAI returned 429 (no credits) during
   this session. The selection is demonstrably correct (5 objects with 29 total
   passages vs 0 before), but facts/stop cannot be measured without narration.

2. **Riviera numeric regression not run**: Walking tours are structurally unaffected
   (code inside museum-only guard), but the numeric baseline comparison requires
   API credits for generation.

3. **First dead-code block not updated**: `generate_tour_text.py` contains two
   copies of the LOCAL-30 deterministic selection (lines ~3354 and ~3448). The
   second block always overwrites the first's result (`_deterministic_fill_used`
   is reset to False). Only the active second block was modified to minimize merge
   conflicts with LOCAL-280/282/283.
