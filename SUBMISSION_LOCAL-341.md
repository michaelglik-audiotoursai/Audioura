##### READY FOR REVIEW

**Commit:** `69931f6`
**Branch:** `kiro/local341-harvest-relevance`
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `harvest_relevance_gate.py` | **NEW** — Relevance gate module. `check_passage_relevance(passage, stop_title)` returns `(bool, reason)`. Lexical/structural: requires ≥1 distinctive content word (≥4 chars, not stop-word) from the stop title to appear word-boundary-matched in the passage. Folds U+2019→U+0027 and strips accents. `audit_stop_corpus_relevance(conn)` runs the gate over all existing rows. |
| `external_claim_verify.py` | Wired gate into `write_external_sources_to_stop_corpus`. Passages blocked by the gate are logged at WARNING level and skipped. |
| `verification_harvester.py` | Defense-in-depth: added gate check after existing `_passage_is_about_stop` filter. |
| `tests/test_local341_harvest_relevance.py` | 16 tests (12 unit, 4 DB integration). All pass. |

---

## Scope 1 — Relevance gate at harvest

**Gate design:** A passage must share at least one distinctive content word with the stop title. Content words are ≥4 characters, not in a stop-word list, matched on `\b` word boundaries after accent-folding and apostrophe normalisation.

**Why this works:** The Stade de France passage ("The stadium was inaugurated on 28 January 1998, with a friendly football match between France and Spain") shares zero words with "L'Armure d'Andô Naoyuki" — searched for `['armure', 'ando', 'naoyuki']`, found none. Trivially caught.

**Harder test case (not the Stade de France):** The Archives départementales du Gard passage for "Kannon à mille bras" — from persee.fr, a legitimate academic source, but the text is about archival transitions in a completely different department. Searched for `['kannon', 'mille', 'bras']`, found none. Also caught: Richard Long / MAMAC ("Opened on 21 June 1990" from Alamy stock photos — searched for `['richard', 'long', 'sculpture', 'marchant']`, found none).

**What it does NOT do:** Discard silently. Every failure is logged with stop_title, passage excerpt, URL, and the specific words searched for. The gate returns a reason string in both pass and fail cases.

---

## Scope 2 — Why museum objects were proposed as walking-tour stops

**Answer: HISTORICAL. Not live.**

The contaminated `stop_corpus` rows (venue "walking tour in Nice, france") were created on 2026-08-04 20:00:09 by `run_local221_external_verify.py`. Its `TOUR_VENUE_MAP` maps the key `'Nice'` to venue `'walking tour in Nice, france'`. Tours 21, 27, and 28 (all Asian Arts Museum tours) contain "nice" in their tour_name and matched this key — their museum stops (Kannon, L'Armure, Masque) were processed under the wrong venue.

The museum objects were never proposed as walking-tour stops by the generation pipeline. The current walking tour (id=12) proposes: Promenade des Anglais, Castle Hill, Albert 1st Gardens, Nice Opera House, Place Masséna, Cours Saleya Market, Old Town, Russian Orthodox Cathedral, Marc Chagall Museum, MAMAC — all walkable places.

Tour 71 (later walking tour) proposes: Place Masséna, Castle Hill, Cours Saleya, Nice Cathedral, Opéra de Nice, MAMAC, Russian Orthodox Cathedral — also all correct.

**Status: Historical mis-mapping in a one-time measurement script. Not a live defect.**

---

## Scope 3 — Blast radius

**Audit results (all 117 stop_corpus rows, 468 passages):**

| Metric | Count |
|--------|-------|
| Passages PASS | 343 |
| Passages FAIL | 125 |

**True contamination (passage provably about something else):**

| stop_title | venue_name | passage_text | source URL |
|-----------|-----------|-------------|-----------|
| L'Armure d'Andô Naoyuki | walking tour in Nice, france | "The stadium was inaugurated on 28 January 1998" | en.wikipedia.org/wiki/Stade_de_France |
| Kannon à mille bras | walking tour in Nice, france | "L'année 2002 aux Archives départementales du Gard" | persee.fr |
| Masque du vieillard Kojo | walking tour in Nice, france | "Le musée sera inauguré le 16 octobre 1998" (×2) | portail-savoirs.departement06.fr |
| Richard Long ou la sculpture en marchant | MAMAC | "Opened on 21 June 1990." | alamy.com/stock-photo |
| Villa Ephrussi de Rothschild | French Riviera walking area | "The State Library of Vorarlberg, built in 1907" | bltawards.com |
| Cap d'Antibes | French Riviera walking area | "potholes, the route along the river is easy (2.7 km)" | presse.explore-savoie.com (Savoie, not Antibes) |

**7 provably contaminated passages across 5-6 rows.**

**The remaining ~118 failures** are venue-level passages (Wikipedia articles about Palais Lascaris filed under individual instrument names, Chagall biography filed under painting titles, etc.). These are "absence of a relevance signal" cases — the passage is likely related but doesn't mention the specific object title. They are correctly flagged but NOT contamination.

**Duplicate rows:** 11 stop titles have multiple rows under different venue_names. Of those, the 3 walking-tour duplicates (Kannon, L'Armure, Masque) are contaminated. The restaurant duplicates (Acchiardo, Chez Palmyre, etc.) are legitimate rows harvested from different tour runs with valid passages. **3 of 11 duplicate-title groups are contaminated.**

---

## Evidence

```
stop_corpus rows: 117 (unchanged)
audio_tours rows: 153 (29 real, rest test — unchanged)
Museum 8-stop (DB tour 21) total_score: 95.5
Museum 8-stop groundedness: [0.60, 0.50, 0.50, 0.00, 0.50, 0.67, 1.00, 0.50]
```

Test run:
```
tests/test_local341_harvest_relevance.py — 16 passed in 0.16s
```

Gate catches the Stade de France row:
```
check_passage_relevance(
    "The stadium was inaugurated on 28 January 1998...",
    "L'Armure d'Andô Naoyuki"
) → (False, "no title words found in passage; searched for ['armure', 'ando', 'naoyuki'] in 104-char passage")
```

Gate passes the legitimate museum row:
```
check_passage_relevance(
    "L'armure d'Ando Naoyuki est une armure de samourai...",
    "L'Armure d'Ando Naoyuki"
) → (True, "full title substring match: 'l armure d ando naoyuki'")
```

---

## Limitations

1. **The gate is a necessary condition, not sufficient.** A passage that mentions "Kannon" in passing (e.g. "the museum also houses a Kannon à mille bras") would pass even if the passage is primarily about something else. This is deliberate: absence of signal ≠ proof of irrelevance (D162).

2. **125 of 468 passages fail the gate retroactively.** Most are venue-level passages that are useful context (building history filed under individual artworks). The gate is designed for harvest-time filtering of new passages, not retroactive deletion. Retroactive cleanup of venue-level passages is a separate decision.

3. **The gate does not examine the URL.** The Stade de France case would also be caught by URL inspection (wikipedia.org/wiki/Stade_de_France for a Japanese armour stop), but URL-based checks are fragile (many URLs don't describe their content). The lexical check is more general.

4. **Short titles with few distinctive words reduce gate effectiveness.** A stop titled "Port" (4 chars, 1 word) would match almost anything. The gate returns `True` with reason "no distinctive words in title; gate not applicable" when the title yields no content words.

5. **No fix applied for the historical venue-mapping bug.** `run_local221_external_verify.py` is a one-time measurement script that has already run. Its `TOUR_VENUE_MAP` is incorrect but the script is not part of the live pipeline. If it ever runs again, the relevance gate now blocks the contamination at write time.
