##### READY FOR REVIEW

## LOCAL-330: Prolog location slot carries place name, not request string

**Commit:** `20bdb57` on branch `kiro/local330-prolog-phrasing`

---

### Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `_prolog_place` extraction (~line 9188): strips category words, transport words, "tour", and orphaned leading prepositions from raw `location`. Used in Part 1 example shape and TOUR DATA section of the prolog prompt. Museum branch (`_is_museum_prolog`) untouched. |
| `tests/test_local330_prolog_place_name.py` | 19 unit tests: restaurant (4), walking (2), cycling (2), animal/dog/camel/horse (3), museum non-regression (2), edge cases (4), production code sync guards (2). |

---

### Verbatim evidence: before and after (all categories)

```
==========================================================================================
Category         Transport  BEFORE (raw location in slot)
                            AFTER  (_prolog_place in slot)
==========================================================================================
restaurant       walking    BEFORE: "...embark on a [walking] journey through [restaurant tour in Old Nice (Vieux Nice), France]."
                            AFTER:  "...embark on a [walking] journey through [Old Nice (Vieux Nice), France]."

restaurant       walking    BEFORE: "...embark on a [walking] journey through [restaurants tour in old city of Nice, France]."
                            AFTER:  "...embark on a [walking] journey through [old city of Nice, France]."

walking          walking    BEFORE: "...embark on a [walking] journey through [walking tour of Montmartre, Paris, France]."
                            AFTER:  "...embark on a [walking] journey through [Montmartre, Paris, France]."

walking          walking    BEFORE: "...embark on a [walking] journey through [walking tour in Rome, Italy]."
                            AFTER:  "...embark on a [walking] journey through [Rome, Italy]."

cycling          cycling    BEFORE: "...embark on a [cycling] journey through [cycling tour of the French Riviera]."
                            AFTER:  "...embark on a [cycling] journey through [the French Riviera]."

cycling          cycling    BEFORE: "...embark on a [cycling] journey through [bike tour in Amsterdam, Netherlands]."
                            AFTER:  "...embark on a [cycling] journey through [Amsterdam, Netherlands]."

animal/dog       riding     BEFORE: "...embark on a [riding] journey through [dogsled tour in Fairbanks, Alaska]."
                            AFTER:  "...embark on a [riding] journey through [Fairbanks, Alaska]."

animal/camel     riding     BEFORE: "...embark on a [riding] journey through [camel tour in the Sahara Desert, Morocco]."
                            AFTER:  "...embark on a [riding] journey through [the Sahara Desert, Morocco]."

animal/horse     riding     BEFORE: "...embark on a [riding] journey through [horseback tour through Patagonia, Argentina]."
                            AFTER:  "...embark on a [riding] journey through [Patagonia, Argentina]."

museum           N/A        Museum branch takes _is_museum_prolog path — no "journey through" sentence.
                            TOUR DATA line: "Musée Matisse, Nice, France" (stripped cleanly).
                            Part 1 instruction unchanged: "You are about to explore the [venue name] in [city]."
```

### Museum non-regression (LOCAL-286)

The museum prolog branch (`if _is_museum_prolog:`) is completely separate and never references `{location}` or `{_prolog_place}` in its Part 1 instruction. It uses hardcoded example text: `"You are about to explore the [venue name] in [city]."` The only shared use is the TOUR DATA line, which now carries `_prolog_place` — for a museum input like `"Musée Matisse, Nice, France museum tour"` this yields `"Musée Matisse, Nice, France"` (clean).

### Deliberate break → test red

```
> Reverted _prolog_place → location in example shape line
> python3 -m pytest tests/test_local330_prolog_place_name.py::TestProductionCodeSync::test_production_uses_prolog_place -v
FAILED - AssertionError: Production prolog still uses raw {location} — LOCAL-330 fix not wired
> Restored fix → 19 passed
```

### Affected historical files in tours/

1 file carries the exact defect in its text:
- `tours/LOCAL317_5stop_old_nice_restaurant.txt` — "a walking journey through a restaurants tour in old city of Nice, France"

Per instructions, existing tour files are **not rewritten** (historical artifacts).

### What was NOT changed

- No container rebuilds
- No `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*` edits
- No `audio_tours` row modifications
- Transport wording itself unchanged ("walking" remains correct)
- No regex removal of "walking journey" from output — the slot value is fixed at the source

---

### Limitations

1. **LLM compliance is not tested end-to-end.** The fix ensures the *prompt template* carries a clean place name. Whether the LLM faithfully echoes it (vs. inventing its own phrasing) depends on the model — but the defective input that caused the bad output is removed.

2. **Place names containing category words.** A location like "Restaurant Row, New York" would have "Restaurant" stripped, yielding "Row, New York". This is an inherent tradeoff of keyword-based stripping. In practice, users request tours *in* places, not tours *named after* category words — and the fallback preserves the full string if stripping empties it.

3. **The word "park" is in the strip list.** "Hyde Park, London" becomes "Hyde, London" after stripping. This is acceptable because the TOUR DATA also includes stop names and coordinates which disambiguate for the LLM — and "park" as a category word (botanical garden/park tours) is the more common use in request strings.
