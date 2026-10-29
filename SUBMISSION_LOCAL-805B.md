# SUBMISSION — LOCAL-805B: "Massage and spa near Ben Thanh Market" delivered 2 of 3 while the map has dozens of spas

**Base:** subscribed @ `38a2ddbb` — `git merge-base --is-ancestor 38a2ddbb HEAD` exits 0 (verified before commit).
**Branch:** `LOCAL-805B-places-count`

## The defect

On the PLACES path, "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh
City" (3) delivered only **2 of 3** real spas (LOCAL-805 live run: CiCi International
Spa + The Spa by SOLÉA). The LOCAL-805 note blamed "the LLM spa pool was thin" — but
on the places path the stops come from **Serper Places**, and Serper lists **ten**
real, open spas within ~0.6 km of Ben Thanh Market. So the shortfall was a **filter
dropping real, open, in-scope spas**, not a thin pool. (P1 b1 had the same 1–2/3
shortfall; LOCAL-802 already added a ×2 widen, which did not help because the drop
happens before the widen can see the candidates.)

## Reproduced OFFLINE with the recorded Serper payload

Recorded the raw Serper Places response **once** (2026-10-29, 3 queries × 1 credit =
~$0.006) for the ticket's scope/`ll` and traced every candidate's fate through the
real places-path filters (`scratch/record_benthanh_spa.py`,
`scratch/trace_bind.py`; raw JSON in `scratch/benthanh_spa_serper.json`, embedded in
the unit test). Serper returns ten spas, all in **Bến Thành / District 1**, within
~0.6 km of the market.

### Candidate fate (scope-bind, live condition: landmark geocode gives a point but **no bbox**)

| # | Serper spa | addr town (old parse) | ≤1.5 km? | BEFORE | AFTER |
|---|------------|-----------------------|----------|--------|-------|
| 1 | .Haisalon The Spa | ben thanh | 0.22 km | keep | keep |
| 2 | **AN's spa 2 - DTC Branch** | **"p"** (noise) | 0.45 km | **DROP** | **keep** |
| 3 | **Norah Spa** | **"street"** (noise) | 0.40 km | **DROP** | **keep** |
| 4 | AnNam Spa – Thu Khoa Huan | ben thanh | 0.16 km | keep | keep |
| 5 | CiCi International Spa | ben thanh | 0.26 km | keep | keep |
| 6 | The Spa by SOLÉA | ben thanh | 0.27 km | keep | keep |
| 7 | La Maison Spa Saigon | ben thanh | 0.08 km | keep | keep |
| 8 | AN's spa 3 - NTB Branch | ben thanh | 0.49 km | keep | keep |
| 9 | Mộc Kim Spa 2 – Ben Thanh | ben thanh | 0.60 km | keep | keep |
| 10 | Laboho Spa | ben thanh | 0.36 km | keep | keep |

**BEFORE: 8/10 bound in scope. AFTER: 10/10.** (The other candidate-path filters
downstream — PHASE 3C address guard, the junk-title guard, D538-closed, same-building
dedup, the "is this really a spa" cuisine/existence check — kept all ten; the ONLY
stage that dropped real spas was scope-bind.)

## Root cause — `places_search._bind_in_scope`'s TOWN-NAME MISMATCH guard

LOCAL-786 added a guard: a record whose address names a town **different** from the
scope's town, **and** which falls outside the geocoded bbox, is rejected. For a
`<business> near <LANDMARK>` request the landmark geocode (Nominatim) returns a point
with **no bounding box** (confirmed in the recording — `boundingbox` absent), so the
guard, not a bbox, decides scope.

The town is read by `_address_town`, which took the **second comma-part** of the
Serper address as the town. Two of the ten spas carry a **noise segment** there,
because Vietnamese addresses put a ward/street marker between the street and the ward:

- `AN's spa 2` → `"12 Đặng Trần Côn, P, Bến Thành, Hồ Chí Minh 700000, Vietnam"` → `"p"` (a truncated *Phường* ward prefix)
- `Norah Spa` → `"114 Lê Thị Hồng Gấm, Street, Bến Thành, Hồ Chí Minh 700000, Vietnam"` → `"street"` (a literal tail on the road)

So their "town" read as `"p"` / `"street"` ≠ the scope town `"ben thanh market"`, and
with no bbox the guard **dropped two real, open, in-scope spas**. The real locality
("Bến Thành") sits in the *third* comma-part. `_parse_address_components` had the same
bug (it set `address.city = parts[1]`), so even the structured read reported `"p"`.

This is exactly why **"coffee near Boston Common" delivered 3/3** in the same
LOCAL-805 run: US addresses ("…, Norwood, MA 02062") have the town cleanly in
`parts[1]`, so the guard never misfired on them.

## The fix — `places_search.py` (one file)

`_address_town` / `_parse_address_components` no longer take the second comma-part
blindly. New shared helpers pick the **first genuine locality** comma-part after the
street, skipping a noise segment:

- `_ADDR_NON_TOWN_TOKENS` — street-type words (`street`, `st`, `road`, `avenue`, …)
  and bare Vietnamese admin-unit prefixes (`p`/`phuong` ward, `q`/`quan` district,
  `tp` city, `x`/`xa` commune, `tt`).
- `_is_locality_part(part)` — False for a pure number/postcode, a single-letter prefix
  (`"P"`), or a noise token.
- `_first_locality_part(parts)` — the first `parts[1:]` part that is a real locality.

`_parse_address_components` now sets `city`/`suburb` from the first locality part;
`_address_town` reads a structured `city` only when it is itself a locality (so a
record whose `city` was stamped from the noise segment no longer reports it), then
falls back to the same raw-address scan. Result: `"Bến Thành"` for both spas →
they bind → N stops are delivered. The guard still fires on a genuinely different
town (LOCAL-786 Byblos/Norwood).

Nothing else changed — no new filter, no loosened radius, no widened scope. The fix
is a parse correction so the existing guard judges the real town.

## Unit test — `tests/test_local805b_places_count.py` (14 tests, all pass)
```
python3 -m pytest tests/test_local805b_places_count.py -q      # 14 passed
```
Embeds the recorded Serper payload and proves, offline:
- the two noise addresses now parse to `"ben thanh"` (not `"p"`/`"street"`); a clean
  Vietnamese address and a US address (`"norwood"`) are unchanged;
- `_parse_address_components` sets `city` to the real locality for the VN address and
  still `"Norwood"` for the US one;
- **all ten** real spas bind in scope with a landmark centre and **no bbox** (was 8),
  and the two previously-dropped spas (AN's spa 2, Norah Spa) are specifically recovered;
- `business_replenish_candidates` delivers **N=3**, the pool holds ≥8, and the full
  `replenish_with_escalation` ladder delivers 3;
- **LOCAL-786 preserved**: a genuine Norwood place is still rejected on a West Roxbury
  scope; a West Roxbury street-only place is still kept.

### Regression (only NEW failures count)
```
805 / 788B / 791 / 802 / 783 / 786 :  171 passed
779 / 779B / 788 / 788B / 784 / 800 :  153 passed
```
Pre-existing failures on the base (NOT introduced here, and in a module I did not
touch): `tests/test_local351_us_address_parsing.py` (2 parenthetical-parse cases in
`area_resolver._parse_location`) — identical on the clean base, the same two the
LOCAL-805 submission documented.

## Live — OWN isolated container, `RESEARCH_BACKEND=serper`, Gemini OFF, cap $0.40

Own postgres `local805b-postgres` on own network `local805b_net`, the
`audioura-tour-generator:latest` image with **this worktree mounted** (so the run
measures THIS code). The 14 shared `audioura-*` containers were never touched; the
isolated stack was torn down afterwards (verified: 14 audioura-* still running, 0
local805b remain). Cheap arm (gpt-4.1-mini + serper; Gemini credit depleted per LEAD
note). 1 tour. `run_local805_container.py 0`.

**"Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City" (3)** —
routed to the PLACES path; centre = Ben Thanh Market (10.7725, 106.6980):

| stop | real spa | km from Ben Thanh Market |
|------|----------|--------------------------|
| **AN's spa 2 - DTC Branch** | ✅ | **0.42** ← the spa the old town-parse DROPPED |
| CiCi International Spa | ✅ | 0.24 |
| .Haisalon The Spa | ✅ | 0.60 |

**Delivered 3/3 real spas** (was 2/3), all within ≤0.6 km of the landmark; the
landmark itself is not a stop. Stop 1 is AN's spa 2 — one of the two spas the
town-mismatch guard previously dropped — direct live proof of the fix.

**Total paid-API spend $0.3224 < $0.40 cap** (LiveRunMeter, all providers combined):
openai $0.2864 + serper $0.0360, gemini $0. Stored as ONE additive `is_test` row in
the ISOLATED DB (id=1). No live DB written. No `DELETE`.

## Files
- `places_search.py` — `_ADDR_NON_TOWN_TOKENS`, `_is_locality_part`,
  `_first_locality_part`; `_parse_address_components` city/suburb from the first
  locality part; `_address_town` skips the noise segment.
- `tests/test_local805b_places_count.py` (new, 14 tests).
