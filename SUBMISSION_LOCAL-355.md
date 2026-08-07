##### READY FOR REVIEW

**Task:** LOCAL-355 — Practical facts for all venue kinds  
**Branch:** `kiro/local355-practical-facts-all-venue-kinds`  
**Commits:**
```
c08630d LOCAL-355: Generalise OSM facts beyond dining to all venue kinds
c230a9f LOCAL-355: Integrate osm_venue_facts into museum/walking tour pipeline
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `osm_venue_facts.py` (NEW) | Generalised OSM facts module for all venue kinds: museums, galleries, parks, viewpoints, landmarks, historic sites, dining |
| `practical_facts_gate.py` | Gate now recognises `fee = no` in OSM source text as equivalent to "free" (1-line regex addition) |
| `generate_tour_text.py` | Pipeline integration: museum/walking tours query OSM for practical facts alongside dining |
| `tests/test_local355_osm_venue_facts.py` (NEW) | 53 tests covering all venue kinds, gate integration, backward compat, absence handling |

---

## Per-Venue Evidence Table (Measured from Live OSM Overpass API)

### RESTAURANT (dining) — LOCAL-353 reference

| Venue | OSM ID | opening_hours | payment | reservation | fee | Sentence |
|-------|--------|---------------|---------|-------------|-----|----------|
| **La Merenda** | node/1130923412 | `Mo-Fr 12:00-13:45, 19:00-21:00;Sa-Su off` | cash=yes, credit=no | ABSENT | — | "open Mo-Fr 12:00-13:45, 19:00-21:00,Sa-Su off. Cash only" |
| **Fenocchio** | node/2241158544 | present (rate-limited, confirmed in LOCAL-353) | ABSENT | ABSENT | — | (opening hours only) |

**Dining unchanged.** Same node IDs, same tag extraction, same sentence format.

### MUSEUM

| Venue | OSM ID | opening_hours | fee | fee_details | website | Sentence |
|-------|--------|---------------|-----|-------------|---------|----------|
| **Musée des Arts Asiatiques** | way/81023334 | `Mo-Su 10:00-17:00; Tu off` | `no` | — | arts-asiatiques.com | "Free admission, open Mo-Su 10:00-17:00, Tu off" |
| **Musée Marc Chagall** | way/140067117 | `10:00-18:00; Tu off; Nov-Apr We-Mo 10:00-17:00; Dec 24,Dec 31 10:00-16:00; Jan 01,May 01,Dec 25 off` | `yes` | From `description:en`: "Full rate : €8, Reduced rate : €6, Free: under 26" | musees-nationaux-alpesmaritimes.fr | (fee_details + hours) |
| **Musée Matisse** | way/1532948021 | ABSENT | `yes` | ABSENT | musee-matisse-nice.org | "Admission charged" |

### PARK / OUTDOOR

| Venue | OSM ID | opening_hours | fee | Sentence |
|-------|--------|---------------|-----|----------|
| **Colline du Château** (park) | way/19668745 | `Oct-Mar Mo-Su 08:30-18:00; Apr-Sep Mo-Su 08:30-20:00` | ABSENT | "open Oct-Mar Mo-Su 08:30-18:00, Apr-Sep Mo-Su 08:30-20:00" |
| **Colline du Château** (viewpoint nodes) | node/24630083, node/255000670 | ABSENT | ABSENT | (empty — no practical facts) |

### LANDMARK (no practical facts obtainable)

| Venue | OSM ID | What OSM has | Practical facts |
|-------|--------|-------------|-----------------|
| **Promenade des Anglais** | way/4099404 | highway=primary, name, speed | NONE |
| **Place Masséna** | way/38361599 | highway=residential, name | NONE |

These landmarks have no opening_hours, fee, or visitor-facing tags in OSM. The module correctly returns empty results (no sentence produced).

---

## Verbatim Sentences (as produced by module)

1. **Museum (free):** `"Free admission, open Mo-Su 10:00-17:00, Tu off"`
2. **Park (seasonal):** `"open Oct-Mar Mo-Su 08:30-18:00, Apr-Sep Mo-Su 08:30-20:00"`
3. **Dining (cash only):** `"open Mo-Fr 12:00-13:45, 19:00-21:00,Sa-Su off. Cash only"`

Format matches Michael's D264 ruling: one sentence, a band or fact plus the practical gotcha.

---

## Gate Audit Lines

### Sourced claim PASSING:
```
claim_type=hours, value="10:00-17:00"
source: "OSM way 81023334 tags:\n  opening_hours = Mo-Su 10:00-17:00; Tu off"
→ verify_claim_against_source returns True (time "10:00" found in source)
```

### Sourced admission PASSING (new: fee=no → free):
```
claim_type=admission, value="Free admission"
source: "OSM way 81023334 tags:\n  fee = no"
→ verify_claim_against_source returns True (regex `fee\s*=\s*no` matches)
```

### Unsourced claim DROPPED:
```
claim_type=hours, value="09:00-18:00"
source: "OSM way 81023334 tags:\n  name = Musée des Arts Asiatiques\n  tourism = museum"
→ verify_claim_against_source returns False (no "09" or "18" near hour context)
```

---

## Queue Advice Assessment

**OSM does not carry queue/crowd/wait-time data.** Searched tags across all 20 venue_corpus entries — no structured source provides this information.

Specific assessment:
- `queue_time`, `waiting_time`, `crowd_level` — not OSM tag keys
- Chagall's `description:en` mentions "Free: first Sunday" — this could imply busy but that is **inference**, not a stated fact about queues
- "Arrive early to beat the crowds" — classic filler, not sourced anywhere

**Result: Queue advice is NOT obtainable from structured sources. The module explicitly does not produce it.** If a museum's official site states "online booking skips the ticket line," that would be sourceable via the website path (LOCAL-34) — but none of our venues' websites carry this as structured data in OSM.

---

## Museum Bounds (D258)

No score movement expected because:
1. Museum stops that already had website-sourced visitor info (LOCAL-34/39) are NOT overwritten
2. OSM facts only fill in where no visitor info existed previously
3. The gate remains strict — no new unverified claims can appear

**Movement can only happen if regeneration produces different text.** Since `OPENAI_API_KEY` is not available, regeneration cannot be run. Museum bounds (8-stop 75.0, 4-stop 81.2) should hold because the only change is in the source provenance layer, not in the generated text itself.

**LEAD must regenerate to confirm.**

---

## Test Results

```
tests/test_local355_osm_venue_facts.py .......... 53 passed
tests/test_local353_osm_dining_facts.py .......... 32 passed
tests/test_local36_practical_facts_qa.py ......... 26 passed
─────────────────────────────────────────────────────────────
TOTAL                                             111 passed
```

---

## Limitations

1. **Regeneration required** — `OPENAI_API_KEY` not in environment. LEAD must regenerate museum tours with `DISABLE_TOUR_CACHE=1` and `DATABASE_URL` set to confirm OSM facts appear in output and bounds hold.

2. **Fenocchio rate-limited** — Overpass returned 504 on retry. Known from LOCAL-353 to be node/2241158544 with opening_hours. Not re-measured this session.

3. **Parc Phoenix** — Overpass also 504'd. Could not confirm tags. Added `park` hint path anyway; if it has relevant tags they'll be picked up.

4. **Queue advice** — Not obtainable from OSM or any structured source we have access to. This is an honest "no" rather than a limitation of the implementation.

5. **Walking tour stops** (Promenade, Place Masséna) — landmarks mapped as highways/roads in OSM carry no visitor-facing practical facts. The module correctly produces nothing for them.

6. **`osm_dining_facts.py` preserved** — Not modified. The old module remains importable for any other code that references it. The new `osm_venue_facts.py` exports backward-compat aliases. Pipeline (`generate_tour_text.py`) uses `osm_dining_facts` for dining (unchanged) and `osm_venue_facts` for museum/walking (new).
