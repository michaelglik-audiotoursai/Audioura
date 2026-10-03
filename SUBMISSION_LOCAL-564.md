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

---

## r2 — whole-name match replaces the "no place named" rejection

### Why r1 bounced
r1 ended `_closure_binds` with `return False, 'closure names no place matching the stop'`
(restaurant_practicals.py:621). That rule **regressed the case that matters most**: a shuttered
restaurant whose closure notice named no place was *kept live*, sending a listener to a closed
door.

| stop | snippet | r1 | r2 |
|---|---|---|---|
| `Neptune Oyster, Boston, MA` | `Neptune Oyster has permanently closed after 20 years.` | kept live ✗ | **closed ✓** |
| same | title `Neptune Oyster - Boston - Yelp`, url `yelp.com/biz/neptune-oyster-boston`, snippet `63 Salem St. Permanently closed.` | kept ✗ | **closed ✓** |

In the Boston live log, line 621 was actually covering a **substring** match: `Del Toro has closed`
and `Toro Mexican Street Food … West Hartford` both matched the venue `Toro`. r2 fixes the
substring match itself and removes 621.

### What changed (restaurant_practicals.py)
1. **Whole-name match** — `_whole_name_spans` / `_whole_name_at`. The venue matches only as the
   complete proper name: the token directly before must not be a capitalised word joined to it
   (`Del Toro`, `El Toro`), and the token directly after must not continue it (`Toro Mexican Street
   Food`, `Toro Toro`). Leading articles (`the/le/la/les/el`) stay allowed. The stop's own
   city/state/country words are exempt as *locators*, so `Chart House Boston` and `La Marée Monaco`
   still match. Deterministic, no keyword list.
2. **Line-621 deleted.** No place contradiction + a subject match now binds. The place gate is the
   Chart House / Weehawken state-contradiction only.
3. **Title/URL as subject for a bare status fragment** — `_title_starts_with_venue` + a new branch:
   when the marker clause is a bare fragment (`Permanently closed.`) and the snippet names no
   subject, bind when the **title starts with the venue** (whole-name) AND the title or URL slug
   names the stop's city, with nothing contradicting the place. Binds the Yelp case.

### Tests — `tests/test_local564_closure_binding.py`
Added, over the existing cases:
- Neptune `has permanently closed after 20 years` → closed (Boston, MA)
- Neptune Yelp listing (bare fragment + title/slug subject) → closed
- `Del Toro has closed` vs venue `Toro` → kept (preceding capitalised word joins the name)
- `Toro Mexican Street Food … West Hartford, has closed` vs `Toro` → kept (following word continues)
- `TORO TORO - CLOSED - … Washington, DC` vs `Toro` → kept (place contradiction)

**RED on r1 (678a0a8)** for the two Neptune cases, run against `git show 678a0a8:restaurant_practicals.py`:
```
RED (regression): Neptune plain (expect closed) -> binds=False expect=True | closure names no place matching the stop
RED (regression): Neptune Yelp  (expect closed) -> binds=False expect=True | no closure marker predicated of the venue
```
**GREEN after** — `python3 tests/test_local564_closure_binding.py` → `ALL TESTS PASSED` (exit 0),
all 11 `_closure_binds` cases + 6 stubbed-SERP `closure_scan` scenarios (incl. Neptune plain,
Neptune Yelp, and `Del Toro`→Toro kept).

### Regression suites (step 5) — both exit 0
```
python3 tests/test_d538_restaurant_practicals.py   → ALL TESTS PASSED   (D538_EXIT=0)
python3 tests/test_d539_closure_regression.py      → ALL TESTS PASSED   (D539_EXIT=0)
```
D539 still closes `La Marée Monaco. Permanently closed.`; D538 still keeps the open Cipriani Monte
Carlo whose snippet carried a co-occurring "Permanently closed" about another business.

### Live check (step 6) — Serper only, no OpenAI narration (well under the $1 cap)
`closure_scan` on the Boston 4 stops (`GENERATION_TIER=plus`, `SERP_API_KEY` set,
`SERPER`/OpenAI narration not invoked). Log: `tours/local564_runs/r2_boston_closure_probe.log`.
The two substring cases from the brief appear in live form and are correctly rejected:
```
[LOCAL-564] closure REJECTED (venue is not the subject of the closure notice) for 'Toro' — kept live: … Toro ... Permanently Closed. North End …
[LOCAL-564] closure REJECTED (closure predicated of another business, not the venue) for 'Toro' — kept live: … they're permanently closed ☹️ …
RESULT Union Oyster House: closed=False
RESULT The Capital Grille: closed=False
RESULT Toro: closed=False
RESULT Neptune Oyster: closed=False
```
(Neptune is open in reality — live SERP returns no closure for it; the Neptune "permanently closed"
snippets in the suite are the regression fixtures from the brief.)

### Finding for LEAD — a consequence of deleting line 621 (not in the r2 test matrix)
Deleting 621 means **any whole-name subject closure that names only a *town* (no US state / no
country token) now binds**, including a *different-city branch of a chain*. The place gate is
state/country contradiction only, and these snippets carry no state token, so nothing contradicts:

```
RESULT The Capital Grille: closed=True  evidence=The Capital Grille at the Beverly Center has closed …   (Beverly Center = Los Angeles; no state token)
RESULT Chart House:        closed=True  evidence=Chart House, a longtime Scottsdale staple since 1984, has permanently closed …   (Scottsdale = Arizona; no state token)
```
Serper ordering is non-deterministic, so a given live run may or may not surface such a snippet
first — i.e. the brief-as-specified can still drop a live Boston chain restaurant, the exact failure
class LOCAL-564 exists to prevent. The two *headline defect* snippets are still safely rejected
(the Weehawken **New Jersey** snippet by state contradiction; verified). I implemented 621's
deletion exactly as instructed and did **not** reintroduce it (that would re-break Neptune). Flagging
for a decision: the durable fix is a town→region signal so a town that is not the stop's — paired
with the stop's city being absent — contradicts the place, without a keyword list and without the
blanket "no place named" drop. Out of r2 scope; raising it rather than shipping it silently.

### Changed files (r2)
- `restaurant_practicals.py` — `_whole_name_spans`, `_whole_name_at`, `_title_starts_with_venue`;
  `_closure_binds` reworked (whole-name subject match, line-621 removed, title/URL subject branch).
- `tests/test_local564_closure_binding.py` — Neptune + Toro cases, r2 docstring.
- `tours/local564_runs/r2_boston_closure_probe.log` — live evidence.
