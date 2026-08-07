##### READY FOR REVIEW

## LOCAL-353: Price and Reservation Sourcing from OSM

**Commit:** 61be3b0
**Branch:** kiro/local353-price-and-reservation
**Base:** storied

---

### Per-File Summary

| File | Change | Purpose |
|------|--------|---------|
| `osm_dining_facts.py` | +309 (new) | Overpass API query for restaurant OSM tags; parses opening_hours, payment:*, reservation, price_range; returns formatted details + source_text for gate |
| `practical_facts_gate.py` | +83/−5 | Extended: 24h colon times, payment/reservation claim types, OSM day abbreviations, `off` closure indicator |
| `generate_tour_text.py` | +34/−0 | Wires OSM dining facts into restaurant tour pipeline; replaces GPT-invented operational_details with sourced facts |
| `tests/test_local353_osm_dining_facts.py` | +308 (new) | 32-test suite covering extraction, gate integration, gate strictness, absence handling |

---

### Per-Venue Source Table (4 Target Stops)

| Venue | OSM ID | Sourceable Facts | Values | What Yields Nothing |
|-------|--------|-----------------|--------|---------------------|
| **La Merenda** | node/1130923412 | opening_hours, payment:cash, payment:credit_cards, payment:debit_cards | `Mo-Fr 12:00-13:45, 19:00-21:00;Sa-Su off`, Cash only | No price_range, no reservation |
| **Fenocchio** | node/2241158544 | opening_hours | `Mar-Nov 09:00-00:00` | No price_range, no reservation, no payment tags |
| **Le Safari** | node/439226955 | (none operational) | cuisine=regional only | No opening_hours, no price_range, no reservation, no payment restriction |
| **Acchiardo** | node/546559155 | (none operational) | — | No opening_hours, no price_range, no reservation, no payment restriction |

**Summary:** Of 4 stops, only La Merenda yields sourceable operational details (hours + cash only). Fenocchio yields seasonal hours. Le Safari and Acchiardo have no operational tags in OSM — their operational_details field is correctly left empty.

---

### Gate Behavior Evidence

**Sourced claim PASSES gate (La Merenda):**
```
Tour text: "Operational Details: Open Monday-Friday 12:00-13:45, 19:00-21:00, Saturday-Sunday off. Cash only"
Source text: OSM node 1130923412 tags (opening_hours + payment:credit_cards=no)
Gate result: claims detected, hours VERIFIED (12:00, 13:45, 19:00, 21:00 all in source), payment VERIFIED
```

**Unsourced claim still DROPPED (Le Safari):**
```
Tour text: "Operational Details: Open daily until late evening, cash only"
Source text: OSM node 439226955 tags (no opening_hours, no payment restriction)
Gate result: "late evening" DROPPED (no time in source), "cash only" DROPPED (no payment:credit_cards=no in source)
```

---

### Verbatim Test Evidence

```
$ python3 -m pytest tests/test_local36_practical_facts_qa.py tests/test_local91_corpus_provenance.py tests/test_local353_osm_dining_facts.py -q
..................................................................       [100%]
66 passed in 0.12s
```

---

### What Cannot Be Sourced (Honest Limitations)

1. **Price bands** — None of the 4 target restaurants have `price_range` in OSM. This tag is rare (<1% of restaurant nodes globally). No alternative source discovered that meets the gate's provenance requirement.

2. **Reservation info** — None of the 4 have `reservation` tags. The tag exists in OSM schema but is uncommonly populated for small restaurants.

3. **Fenocchio hours** — `Mar-Nov 09:00-00:00` is seasonal and the "current" caveat applies. OSM data may lag reality. The claim is still sourceable (the tag is there), but could be stale.

4. **Currency** — Not explicitly needed for the 4 Nice stops (no price values to denominate). The module derives country code from `addr:country` when present; for these venues it would be EUR context from France. No dollar/pound confusion possible.

5. **Price estimation from cuisine type** — Explicitly NOT done. The task brief forbids inventing a price band from cuisine or neighbourhood. The gate correctly rejects any such claim.

---

### Regeneration Required

**LEAD: A full pipeline run is needed** to produce a tour with OSM-sourced operational details passing the gate in production. I cannot run it (`OPENAI_API_KEY` not in environment). The gate integration is wired and tested offline, but end-to-end evidence requires regeneration.

---

### Museum bounds (D258)

Not affected by this change (restaurant-only scope). Existing values:
- 8-stop: **75.0**
- 4-stop: **81.2**

---

### Architectural Decision

The OSM query runs per-stop during tour generation (1 Overpass request per stop, rate-limited at 1/5s). For a 4-stop restaurant tour this adds ~20s. The alternative (batch query for all stops at once) was rejected because:
- The Overpass regex matching by name is already scoped to the city area
- Individual queries give per-stop source provenance (each gets its own OSM URL)
- Rate limiting is conservative (Overpass allows up to 2/10s)

**No container rebuilt. No rows in audio_tours modified. `git status --short` clean after commit.**
