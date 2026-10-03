# SUBMISSION — LOCAL-564

**A closure reported for a DIFFERENT restaurant (or a DIFFERENT subject) must not drop a live one.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-564-closure-binding`
- **Base:** `storied` (f192ff6) — release fix (D594: merge to storied, forward-merge into subscribed)
- **Merge-base check:** `git merge-base --is-ancestor f192ff6 HEAD` → exit 0 ✓

---

## The defect (LOCAL-563 Gemini baseline)

Two OPEN Boston restaurants were dropped by the closure probe, each on a notice that was not
about them:

| Venue (Boston) | Snippet it was dropped on | Why it was wrong |
|---|---|---|
| **Chart House** | *"Chart House, a riverfront staple in **Weehawken, New Jersey**, has closed as of May 14. A Mastro's Steakhouse is planned for the site."* | **Wrong city.** Notice is Weehawken NJ; the stop is Boston MA. |
| **Buttermilk & Bourbon** | *"**BarLola** in Boston's Back Bay Has Closed; **Buttermilk & Bourbon to Replace It** …"* | **Wrong subject.** BarLola closed; Buttermilk is the *successor* named by "to Replace It". |

The pre-fix `closure_scan` (D543 city key + D544 same-sentence rule) bound both:

- **Chart House:** D543's city key was `city.split(',')[0].split()[-1]`. The pipeline passes the
  whole request — `"restaurant tour of Chart House, Boston, MA"` → first comma-segment
  `"restaurant tour of Chart House"` → last word **"house"**, which is in the Weehawken snippet.
  City check passed on the venue's own name; name + "has closed" shared the sentence → **bound (wrong)**.
- **Buttermilk:** city "boston" matched and name + "Has Closed" shared the sentence (D544 satisfied),
  so it bound BarLola's closure to Buttermilk → **bound (wrong)**.

Both tours only delivered because the listener named the venue (LOCAL-556/557 protection). In a
plain "restaurant tour of Boston" a live venue is silently dropped — the Michael's Sycamore bug
(D544) again.

---

## The fix (`restaurant_practicals.py`)

Deterministic. No keyword list beyond the closure markers that already exist (D476). A closure is
accepted only when **BOTH** hold; otherwise the venue is kept and a
`[LOCAL-564] closure REJECTED (<reason>)` line is logged.

### 1. Place match — `_place_contradicted` / `_parse_stop_place` / `_geo_vocab`
The snippet (or title/URL) must not name a US state or country that **contradicts** the stop's.
The stop's city/region is parsed from the location string the pipeline already has
(`"… Chart House, Boston, MA"` → city `Boston`, state `Massachusetts`). The US-state and country
vocabulary comes from **pycountry** (D476 — a library/dataset, not a hand list), 57 US subdivisions
and 249 countries. Two-letter state abbreviations only count in press form (uppercase, standalone:
`Weehawken, NJ`) so lowercase prose words like "in"/"or"/"me" are never read as Indiana/Oregon/Maine.

### 2. Subject match — `_closure_binds` / `_SUCCESSOR_MARKERS`
In the clause carrying the closure marker, the venue must be the **subject that closed**: it appears
*before* the marker in the same clause, with no other business name between them. Clauses are split
on sentence punctuation **and semicolons** (a semicolon joins two independent businesses:
`"BarLola … Has Closed; Buttermilk & Bourbon to Replace It"`). Replacement/successor phrasing
(`to replace`, `taking over`, `in the former`, `replaces`, …) binds the closure to the OTHER name.
A cross-clause `"<Venue>. Permanently closed."` is honoured only when the marker clause is a bare
status fragment with no subject of its own, so a listicle headline about another restaurant does
not condemn every venue it lists.

Degradation is safe (D541): if pycountry is missing the geo maps are empty and place-match becomes
"no contradiction found" — the direction that *keeps* a stop rather than dropping it.

---

## Acceptance

### Unit tests — `tests/test_local564_closure_binding.py`

RED BEFORE: the pre-fix `restaurant_practicals.py` has no `_closure_binds`, and the old
`closure_scan` bound both shipped snippets (verified against `origin/storied`). GREEN AFTER:

```
[LOCAL-564] closure binding — place + subject match

  -- _closure_binds: place-match + subject-match --
  OK  Chart House — Weehawken NJ notice, stop is Boston MA
        binds=False expect=False  reason='wrong place: names New Jersey, stop is in Massachusetts'
  OK  Buttermilk & Bourbon — BarLola closed, Buttermilk is the successor
        binds=False expect=False  reason='closure predicated of another business, not the venue'
  OK  Chart House Boston genuinely closed
        binds=True expect=True  reason='bound'
  OK  Sycamore in Newton Centre genuinely closed
        binds=True expect=True  reason='bound'
  OK  Newton listicle — headline closure is a different restaurant
        binds=False expect=False  reason='closure predicated of another business, not the venue'
  OK  La Marée Monaco — real 2020 closure
        binds=True expect=True  reason='bound'

  -- closure_scan end-to-end (stubbed SERP) --
  OK  closure_scan('Chart House') -> closed=False expect=False
  OK  closure_scan('Buttermilk & Bourbon') -> closed=False expect=False
  OK  closure_scan('La Marée') -> closed=True expect=True

ALL TESTS PASSED
```

Covers every case the ticket named: the two shipped defects (red→green), the two genuine closures
("Chart House Boston has closed", "Sycamore in Newton Centre … permanently closed"), the D544 Newton
listicle (not closed), and La Marée's real 2020 closure (still closed).

### Tour re-runs — `generate_tour_text`, no DB rows (live SERP + OpenAI/Gemini)

Logs saved to `tours/local564_runs/`; full tour text in `tours/local564_boston.txt` and
`tours/local564_charthouse.txt`. `DISABLE_TOUR_CACHE=1`, `DATABASE_URL` unset.

**1) "restaurant tour, Boston, MA", 4 stops — 4 delivered, 0 dropped**

```
Detected tour category: RESTAURANT
  [LOCAL-564] closure REJECTED (wrong place: names Texas, stop is in Massachusetts) for 'Union Oyster House' — kept live: Union Oyster House, a Boston landmark … is being sold to a Texas family.
  [LOCAL-564] closure REJECTED (wrong place: names Illinois, stop is in Massachusetts) for 'The Capital Grille' — kept live: The Capital Grille is closing its Skokie, Illinois location…
  [LOCAL-564] closure REJECTED (wrong place: names California, stop is in Massachusetts) for 'The Capital Grille' — kept live: THE CAPITAL GRILLE - CLOSED - … Los Angeles, CA …
  [LOCAL-564] closure REJECTED (wrong place: names District of Columbia, stop is in Massachusetts) for 'Toro' — kept live: TORO TORO - CLOSED - … Washington, DC …
  [D538] Practicals acquired for 4/4 stop(s)
Stop 1: Union Oyster House
Stop 2: The Capital Grille
Stop 3: Toro
Stop 4: Neptune Oyster
```

**2) "Chart House, Boston, MA", 1 stop — 1 delivered, 0 dropped (the exact defect venue)**

The exact shipped snippet is rejected on live data:

```
Detected tour category: RESTAURANT
  [LOCAL-564] closure REJECTED (wrong place: names New Jersey, stop is in Massachusetts) for 'Chart House' — kept live: Chart House, a riverfront staple in Weehawken, New Jersey, has closed as of May 14. A Mastro's Steakhouse is planned for…
  [LOCAL-564] closure REJECTED (wrong place: names New Jersey, stop is in Massachusetts) for 'Chart House' — kept live: CHART HOUSE - CLOSED - … Weehawken, NJ 07086 …
  [D538] 'Chart House' via serp(32)+openai: hours=Daily 4:00 PM - 6:00 PM …, price_band=$30 and under
  [D538] Practicals acquired for 1/1 stop(s)
Stop 1: Chart House
```

**No live venue dropped in either run.** `[DROPPED]` appears nowhere in either log.

### Storied suites

`python3 run_tests.py` → **318 passed, 45 failed (of 363)**. The 45 failures are pre-existing and
environmental, none on this change's surface:
- missing host modules (`wallet_ledger`, `bs4`, `Crypto`, selenium), macOS Python 3.9 vs 3.12 syntax,
  and live network/DB/Nominatim rate-limit timeouts (e.g. `test_local313_dining_nominatim` passes
  10/10 when run standalone).
- The only tests touching this change — `test_local564_closure_binding.py` (new),
  `test_d539_closure_regression.py`, `test_d538_restaurant_practicals.py` — **all pass**. The D538
  live suite shows the `[LOCAL-564]` guard keeping an open Cipriani Monte Carlo whose snippet carried
  a co-occurring "Permanently closed" about another business.

---

## Changed files
- `restaurant_practicals.py` — `_closure_binds`, `_place_contradicted`, `_parse_stop_place`,
  `_geo_vocab`, `_SUCCESSOR_MARKERS`; `closure_scan` now requires place + subject match and logs
  `[LOCAL-564] closure REJECTED (<reason>)`.
- `tests/test_local564_closure_binding.py` — new.
- `requirements_generator.txt` — pin `pycountry==24.6.1`.
- `tours/local564_boston.txt`, `tours/local564_charthouse.txt`, `tours/local564_runs/*.log` — run evidence.

## Must-not — honoured
No GCloud deploy. No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md,
.continuous_dev/STATUS.md. Nothing deleted from audio_tours.
