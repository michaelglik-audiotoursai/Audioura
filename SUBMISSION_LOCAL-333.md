##### READY FOR REVIEW

**Commit:** b72aff1  
**Branch:** kiro/local333-fact-detector-nonmuseum  
**Base:** storied (2 commits ahead)

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | 3 fixes: closing offer strip in `parse_tour`, stop-title exclusion + partial-name dedup in `analyze_stop` |
| `tests/test_local333_fact_detector_nonmuseum.py` | 14 new tests for the three bounce-fix classes |

---

## What was fixed

Three false-positive classes eliminated — **no vocabulary lists added**, all fixes use the tour's own structure:

### 1. Closing offer excluded from fact counting
The "That's N stops …" boilerplate is appended after the last stop header. `parse_tour` folded it into the last stop's body. Now detected by regex `^That'?s\s+\d+\s+stops?\b` and all content from that point forward is stripped.

### 2. Stop titles excluded from people set
After person detection completes, any candidate whose lowercased form matches a stop title (or a capitalised sub-phrase within a title) is removed. This eliminates `La Voglia`, `Le Safari`, `Chez Palmyre`, `La Rossettisserie`, `Arts Asiatiques` — all venue names that the structural model would otherwise accept via the appositive pattern.

### 3. Partial name deduplication
After detection, names where one's token set is a strict subset of another's are folded into the fuller form. Eliminates `Kenzo` when `Kenzo Tange` is present; `Chef Dominique Le` when `Dominique Le Stanc` is present.

---

## Verbatim evidence

### Three false-positive cases — now zero phantom people

```
$ python3 -c "..."   # (full verification script inline)

# Treat Page:
Last stop body contains 'Treat Page': False

# La Voglia/Le Safari/Chez Palmyre stop titles:
Stop 5: La Voglia — people=['Vittorio Agnoletto'], facts=3
  (La Voglia, Le Safari, Chez Palmyre all absent from people lists)

# Arts Asiatiques:
test_arts_asiatiques_is_stop_title PASSED
```

### Five correct cases from bounce still pass

```
clinking glasses: people=[], facts=0                    ✓ correct
Nice coastal city: people=[], facts=0                   ✓ correct  
Cours Saleya: people=[]                                 ✓ correct
Chikanobu: people=['Toyohara Chikanobu']                ✓ correct
Cerutti: people=['Franck Cerutti']                      ✓ correct
```

### Restaurant tour rescored

```
LOCAL318 Restaurant: 66.3 (base score, no corpus)
  Stop 1: La Rossettisserie — people=[], facts=0
  Stop 2: Acchiardo — people=['Madalin Acchiardo','Virginie Acchiardo'], facts=4
  Stop 3: Chez Palmyre — people=['Palmyre Moni'], facts=2
  Stop 4: Le Safari — people=['Franck Cerutti','Nadim Beyrouti'], facts=3
  Stop 5: La Voglia — people=['Vittorio Agnoletto'], facts=3
```

Le Safari moved from 0 to 3 facts (from first commit). No inflation — phantom people removed.

### Museum 8-stop rescored

```
Museum 8-stop: 107.9 (base score, no corpus)
  Total: 7 people mentions, 43 facts across 8 stops (avg 5.4/stop)
  BEFORE bounce fix: 7 people, 43 facts — IDENTICAL. No regression.
```

**Note:** These scores are from this branch which predates LOCAL-331 merge. The bounce notes that LEAD saw 81.2/65.0 from this tree vs 78.1/60.0 on current storied — that gap is LOCAL-331, not this change. Reported honestly.

---

## Reader-vs-detector gap table

| Tour | Stop | Title | Reader count | Detector | Gap | Notes |
|------|------|-------|:---:|:---:|:---:|-------|
| LOCAL318 | 1 | La Rossettisserie | 0 | 0 | 0 | Pure atmosphere, no verifiable facts |
| LOCAL318 | 2 | Acchiardo | 5 | 4 | -1 | Reader: +Giuseppe (mentioned but no context verb) |
| LOCAL318 | 3 | Chez Palmyre | 3 | 2 | -1 | Reader: +"Vincent and Sam" (first-name-only, not extracted) |
| LOCAL318 | 4 | Le Safari | 4 | 3 | -1 | Reader: +"Palestinian-Niçois" (nationality fact for Beyrouti) |
| LOCAL318 | 5 | La Voglia | 4 | 3 | -1 | Reader: +"27th G8 meeting in Genoa" (year caught, meeting not) |
| LOCAL317 | 1 | La Petite Maison | 1 | 1 | 0 | Nicole Rubi only factual element |
| LOCAL317 | 2 | Le Bistro du Port | 0 | 0 | 0 | Generic atmosphere only |
| LOCAL317 | 3 | Olive & Artichaut | 0 | 0 | 0 | Generic atmosphere only |
| LOCAL317 | 4 | Restaurant Acchiardo | 1 | 1 | 0 | "The Acchiardo" family reference |
| LOCAL317 | 5 | Chez Palmyre | 0 | 0 | 0 | Generic atmosphere only |

**Summary:** Detector under-counts by ~1 fact on content-rich stops (-1 gap on 4/10 stops). This is acceptable — the under-counted facts are edge cases (first-name-only people, nationality adjectives, event references without explicit pattern). The detector does NOT over-count on any stop.

---

## Test results

```
$ python3 -m pytest tests/test_local333_fact_detector_nonmuseum.py -v
========================== 27 passed in 0.09s ==============================
```

---

## Limitations

1. **Single-name people** ("Giuseppe", "Vincent and Sam") are not detected by the multi-word `_PROPER_PHRASE_RE`. This is a deliberate tradeoff — single capitalised words generate too many false positives.

2. **"The Acchiardo"** is detected as a person in LOCAL317 Stop 4 — it's a family reference with a determiner that happens to match the title-before-name pattern. Harmless (1 fact either way) but technically a false positive.

3. **Nationality-as-fact** ("Palestinian-Niçois") is not counted. The detector has no pattern for demonyms as factual claims about a person.

4. **Event references** ("the 27th G8 meeting in Genoa") — the year 2001 is caught, but "G8 meeting" as a distinct fact is not. Would require an event-detection pattern.

5. **Branch predates LOCAL-331** — reported scores (66.3 restaurant, 107.9 museum) will differ from current storied due to that merge, not this change.
