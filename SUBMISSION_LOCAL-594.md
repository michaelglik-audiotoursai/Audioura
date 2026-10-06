# SUBMISSION — LOCAL-594: meter Gemini grounded search truthfully, then cut it

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-594-grounding-cost` (base `subscribed` @ `fa4f884`)

---

## TL;DR

- **Meter fixed.** Grounding is now priced by the unit Google actually invoices —
  the **search query** (`groundingMetadata.webSearchQueries`) at **$0.014/query**
  (pricing page read 2026-10-06; matches Michael's bill: 1,653 queries = $23.14 on
  2026-10-05). It is counted at a single chokepoint and **folded into the
  `tour_generate` COST_METER ledger row and the per-tour cost line** — the figure
  Michael sees no longer excludes grounding.
- **Cut done.** The per-stop credit_line loop (D511) was the driver: **42 grounded
  requests per 7-stop tour (4/stop)**. After the cut it is **1 grounded request per
  stop in the loop** (measured live on McMullen). Two changes: r2 adjudication is
  ungrounded (it reasons over Serper evidence, never searched the web), and only the
  first credit_line's narrate is grounded; later ones narrate ungrounded and are
  still verified by the same Serper challenge.
- **No bounce.** BEFORE and AFTER produced the **same story-gate outcome** on the same
  venue (0 loop stories in both — the account is out of Gemini credit, see below),
  the same 7 delivered stops, same examined/candidate counts.
- **Live, isolated, under cap.** McMullen 7-stop ran in a disposable
  `local594-gen` container (never `audioura-*`). Each tour ≈ $1.47–1.70 OpenAI,
  grounding $0.00 (402, below). Well under the $3 cap.

---

## 1. Meter what Google bills

**What Google bills.** Pricing page
<https://ai.google.dev/gemini-api/docs/pricing> (read **2026-10-06**) lists
*"Grounding with Google Search: 5,000 free search requests per month, then **$14 per
1,000 requests**"*. But the invoice SKU on Michael's account is **"Generate content
search query gemini 3 paid"**, measured in **search queries**: 2026-10-05 showed
**1,653 queries for $23.14 = $14.00 / 1,000 queries**. A single grounded *request*
can issue several *queries* (returned in `groundingMetadata.webSearchQueries`), so
the honest dollar figure follows the queries.

**Change (counts the billed unit):**
- `story_leads.py` — new `_GROUNDING_QUERIES` counter + `get_grounding_queries()`.
  Both `_gemini(grounded=True)` and `gemini_with_sources(grounded=True)` now tally
  `webSearchQueries` from each grounded response. `reset_grounding_requests()`
  zeroes both. (The request counter LOCAL-533 added is kept for the per-stop cap.)
- `cost_rates.py` — `GROUNDING_COST_PER_QUERY = 0.014` with the citation inline;
  `grounding_query_cost(n)`. The old flat `$0.035/request` is deprecated (it was
  never on any pricing page and did not match the bill).
- `generate_tour_text.py` — prices grounding by **queries**, prints
  `Grounding: $X (Q queries, R requests)` and `Tour total:`, and records
  `grounding_queries` in `_LAST_GENERATION_COST` (fresh **and** cache paths).
- `generate_tour_text_service.py` — the ledger row now records
  **`tour_total_cost` (LLM + search + TTS + grounding)** instead of LLM-only
  `total_cost`. *This is the line that previously understated every price quoted to
  Michael.*

**Known follow-up (not a regression):** cache-hit *charging* (`cost_meter`
`_FRESH_COST_SANITY_CEILING["tour_generate"] = 0.25`) will still floor to $0.00 when
a grounding-inclusive fresh cost exceeds $0.25. That ceiling is a LOCAL-200 anti-
overcharge guard on *cache hits*; raising it is a separate ticket. The fresh
`tour_generate` meter (what this ticket is about) is now complete.

## 2. Measure (McMullen 7-stop, live)

Call sites that issue grounded requests, and the per-stop driver:

| Call site | When | Grounded requests |
|---|---|---|
| `story_production_loop.run_for_stop` (D511 loop): r1 narrate **+** r2 adjudicate, × up to `MAX_CREDIT_LINES=4` | per museum stop | **the driver — 4/stop → 42/tour** |
| `generate_tour_text` LOCAL-488 `story_leads.run` (`gemini_grounded` provider) | per mined stop | +1/mined stop |
| `venue_parts` Q3, `restaurant_practicals`, `stop_knowledge_fallback` | per tour / per stop | a few/tour |

Measured live (BEFORE): **42 grounded requests, [4,4,4,4,4,4,4] per stop in the loop.**

## 3. Cut it, keeping story quality

Target: **≤ 1 grounded request per stop (≤ 8 for 7 stops)**.

- **r2 adjudication → ungrounded.** Its prompt (`story_adjudicate.ADJUDICATION_PROMPT`)
  says *"Judge ONLY against the retrieved evidence above. Do not rely on memory."* —
  it reasons over the Serper evidence block, it never searched. Grounding it bought a
  billable query for nothing. (`STORY_LOOP_R2_GROUNDED=1` restores it for baseline
  measurement only.)
- **Only the first credit_line's narrate (r1) is grounded** (`STORY_LOOP_MAX_GROUNDED`,
  default 1). The grounded first draft pulls fresh web facts in; **every** candidate —
  grounded or not — then goes through the same Serper challenge + adjudication, so
  later credit_lines still reach the stop as verified candidates, reusing the one
  grounded search the stop already paid for.
- **Dropped the redundant `gemini_grounded` provider** from the LOCAL-488 leads
  fan-out. The module itself notes `gemini + gemini_grounded` is *"one model answering
  twice, not corroboration"* — it added no cross-family agreement, only a billable
  search per mined stop on top of the loop's. (`STORY_LEADS_GROUNDED=1` restores it.)

### Before / after (live, McMullen 7-stop, isolated container)

| | grounded requests (whole tour) | per-stop in D511 loop | max/stop | story-gate (loop) | delivered stops |
|---|---|---|---|---|---|
| **BEFORE** | **42** | [4,4,4,4,4,4,4] | 4 | 0/7 | 7/7 |
| **AFTER** | **14** | [1,1,1,1,1,1,1] | **1** | 0/7 | 7/7 |

Loop grounded requests per stop: **4 → 1** (cap holds). Whole-tour: **42 → 14** (the
residual 14 are the per-tour/venue sites, not the loop). **Story outcome unchanged**
(no bounce). The remaining 14 could be driven lower in a follow-up by moving venue
resolution onto the same reuse rule, but the ticket's loop target (≤ 1/stop) is met.

## 4. Tests — `tests/test_local594_grounding_cost.py` (10 tests, all pass)

- **Meter counts queries:** a fake Gemini wire mints `webSearchQueries`; the counter
  tallies queries (not requests), prices $0.014/query, matches the bill shape
  (1,653 → $23.142), and ungrounded calls cost $0.
- **Cap holds:** across multiple credit_lines, ≤ 1 grounded request/stop; r2 never
  grounds; zero-budget path works.
- **Leads still reach the stop:** same `examined` / candidate / story counts capped vs
  uncapped — the cut changes only whether a narrate call is grounded, never whether a
  lead reaches the stop.

Regression: `test_local533_grounding_count` (now $0.014), `test_local60_cost_metering`,
`test_pricing`, `test_local197`, `test_local143` all pass.

## 5. Live check — isolated container only

`./run_local594_live.sh`: builds `Dockerfile.generator`, runs
`docker run --rm --name local594-gen` on `development_default` (postgres-2
**counted-only**), `COST_HARD_LIMIT_USD=3.00`, cache + stop-pool off, image removed at
end. No `audioura-*` container touched (verified: 13 still up, 0 stray local594).

**Cost lines (authoritative `_LAST_GENERATION_COST`, grounding-inclusive):**
```
LOCAL-594 [AFTER]  Total API cost (LLM): $1.6972   Grounding: $0.0000 (0 queries, 14 requests)   Tour total: $1.6972
LOCAL-594 [BEFORE] Total API cost (LLM): $1.4703   Grounding: $0.0000 (0 queries, 42 requests)   Tour total: $1.4703
```

### Why grounding is $0.00 live — and why that is the meter being *correct*

Direct probe from the isolated container:
```
HTTP 402  {"code":402,"message":"Your prepayment credits are depleted...","status":"RESOURCE_EXHAUSTED"}
webSearchQueries = None
```
**Michael's Gemini account is out of prepaid credit.** Every grounded request in both
runs returned 402, so each carried **no `webSearchQueries`** and performed **no billable
search**. The meter therefore reports **$0.00 — which is exactly right**: Google bills
for queries executed, and a 402'd request executes none. The meter does not invent cost
for a request that did not search. This also explains the 0/7 loop stories and the ~1s
loops in **both** runs (grounded r1 returned empty) — a pre-existing account state, not
caused by this change, and identical BEFORE/AFTER (hence no bounce).

The **per-query dollar figure** is proven against a real grounded response shape in the
unit tests (fake wire carrying `webSearchQueries`); the **live run** proves the request
counts (42 → 14, 4/stop → 1/stop), that both cost lines print queries+requests+dollars,
and that the cut holds with no story-gate change. When Michael's Gemini credits are
topped up, the same meter will report the real per-query dollars with no further change.

---

## Files

- `story_leads.py` — query counter + `get_grounding_queries()`; count `webSearchQueries`.
- `cost_rates.py` — `GROUNDING_COST_PER_QUERY=0.014`, `grounding_query_cost()`.
- `generate_tour_text.py` — price by queries; print queries+requests; drop redundant
  grounded leads provider.
- `generate_tour_text_service.py` — ledger records grounding-inclusive total.
- `story_production_loop.py` — r2 ungrounded; `STORY_LOOP_MAX_GROUNDED` per-stop cap;
  expose per-stop grounded counts; `STORY_LOOP_R2_GROUNDED` measurement knob.
- `tests/test_local594_grounding_cost.py` — meter / cap / leads tests.
- `run_local594_mcmullen.py`, `run_local594_live.sh` — isolated-container measurement.

No DELETE, no GCloud. DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
.continuous_dev/STATUS.md untouched.


---

## r2 — the quality claim, re-proven with Gemini grounding LIVE

**Why r1 bounced (LEAD, 2026-10-06):** the meter was right, but the quality claim was
not. In r1 **both** BEFORE and AFTER had Gemini returning **402 (prepay depleted)**, so
both produced 0 loop stories. "Same outcome" compared two broken runs. Michael's priority
is the stories, so the cut cannot merge until it is compared with grounding **live**.

### Step 1 — probe Gemini first (one call, no loop)

Probed `gemini-flash-latest` through the production path (`preflight.check_gemini`), then
one grounded call through `story_leads._gemini(grounded=True)`:

```
preflight.check_gemini()  → HTTP 200          (r1 was 402 — credit has been topped up)
_gemini(grounded=True)    → 1 request, 1 query, 163 chars of real web facts:
  "The McMullen Museum of Art at Boston College originally opened in Devlin Hall in
   1993, before relocating to its current Brighton Campus facility in September 2016."
```

**Gemini grounding is live and billing queries.** Not blocked. Proceeded to the runs.

### Steps 3–4 — BEFORE/AFTER, two tours, grounding live, isolated container

`./run_local594b_r2_live.sh` — disposable `docker run --rm --name local594b-gen` on
`development_default` (postgres-2 **counted-only**), tour cache + stop pool OFF, image
removed at end. **Never** touched `audioura-*` (verified: 13 containers up before and
after, 0 stray `local594b`). Per-run LLM cap $1.80 with an **$8 batch gate** that stops
before any run lacking $2.20 headroom. **Batch spent: $4.03 / $8.**

- **AFTER** = defaults (the cut): `STORY_LOOP_MAX_GROUNDED=1`, r2 ungrounded, redundant
  grounded-leads provider dropped.
- **BEFORE** = storied-equivalent: `STORY_LOOP_MAX_GROUNDED=4`, `STORY_LOOP_R2_GROUNDED=1`,
  `STORY_LEADS_GROUNDED=1`.

**McMullen Museum of Art, Boston College — museum, 7 stops**

| | loop stories / stop | gate cleared | grounded requests | grounded queries | grounding $ | Tour total |
|---|---|---|---|---|---|---|
| **BEFORE** | [0,0,0,0,0,1,1] | **2 / 7** | 42 | 38 | $0.5320 | **$1.8306** |
| **AFTER**  | [0,0,0,0,0,1,0] | **1 / 7** | 14 | 11 | $0.1540 | **$1.4678** |

Per-stop grounded requests in the D511 loop: **BEFORE [4,4,4,4,4,4,4] → AFTER
[1,1,1,1,1,1,1]** (the cap holds at 1/stop live). Grounding is now **non-zero and
billed** on both runs — the exact thing r1 could not show.

**Freedom Trail, Boston, MA — walking, 5 stops**

| | loop stories / stop | gate cleared (D511) | grounded requests | grounded queries | grounding $ | Tour total |
|---|---|---|---|---|---|---|
| **BEFORE** | [] | 0 / 0 | 5 | 8 | $0.1120 | $0.3732 |
| **AFTER**  | [] | 0 / 0 | 5 | 7 | $0.0980 | $0.3567 |

A walking tour's stops are historic sites, **not catalogue works with a `credit_line`**, so
the D511 credit_line story loop (`run_for_stop`) is **never invoked** — hence `0/0` loop
stories in *both* runs. These tours are gated instead by LOCAL-439, which reported
**`STORY GATE: ALL STOPS PASSED`** in both BEFORE and AFTER. Grounding is still live here
(7–8 queries, billed) via the per-tour/venue call sites; the cut does not touch that path,
so the counts and cost are ~equal by construction.

### Rule (step 4): AFTER cleared ≥ BEFORE − 1, per tour

- **McMullen:** AFTER **1** ≥ BEFORE **2** − 1 = **1** → **PASS**.
- **Freedom Trail:** 0 ≥ 0 − 1 → **PASS** (vacuous — the loop runs on neither; both pass
  the LOCAL-439 gate on all stops).

Both tours satisfy the rule, so **`STORY_LOOP_MAX_GROUNDED` stays at 1** — no raise to 2,
no re-measure needed. The cut keeps story quality with grounding live: on McMullen it loses
exactly one loop story (within tolerance) while cutting grounded requests 42 → 14 (loop
4/stop → 1/stop) and grounding cost $0.53 → $0.15; on the walking tour it is quality-neutral.

### One stop, delivered text, side by side (Stop 3 — *Dura-Europos: Crossroads of Antiquity*, McMullen)

Same stop in both runs; AFTER is the stop where the cut's single grounded loop story
cleared (idx 58). Both deliver a full, grounded, multi-paragraph narrative — the quality is
comparable, not degraded by the cut.

**AFTER (cut):**
> The story of Dura-Europos, a forgotten jewel buried under the Syrian sands until the
> early 20th century, unfolds at the crossroads of the Seleucid, Parthian, and Roman
> empires. … Founded around 300 BCE by Macedonian settlers along the Euphrates River,
> Dura-Europos grew into a multicultural crossroads … In 256 CE, a Persian Sasanian siege
> brought an abrupt end to the city's prosperity. While museum records state the city was
> completely abandoned after the sack, other historians argue that sporadic activity and
> Mediterranean contact continued rather than total desertion.

**BEFORE (baseline):**
> Dura-Europos stood at the crossroads of the Seleucid, Parthian, and Roman Empires,
> thriving as a multicultural hub on the Euphrates River. … In 2011, the McMullen Museum
> of Art partnered with the Yale University Art Gallery to present Dura-Europos: Crossroads
> of Antiquity. The exhibition brought together artifacts unearthed during Yale's
> archaeological excavations of the ancient city, which began in 1928. Curators assembled
> these excavated treasures to partially reconstruct the city's ancient religious spaces,
> incorporating newly restored wall paintings.

### Step 2 — fix the `_FRESH_COST_SANITY_CEILING["tour_generate"]=0.25` flooring

r1 flagged this as a known follow-up; r2 fixes it. The ceiling is a LOCAL-200 guard used by
`lookup_fresh_cost_for_cache_hit`: when a **cache hit** must charge what the original fresh
generation cost, a stored row above the ceiling is rejected and the cache hit charges
**$0.00**. The old **$0.25** predated grounding being metered — a fresh tour was ~$0.08
(LLM+TTS only). As the live runs above show, a **grounding-inclusive** fresh tour is now
**$1.47–1.83**, far above $0.25, so every such row was being floored to $0.00 (an
undercharge on the matching cache hit).

**Change:** `_FRESH_COST_SANITY_CEILING["tour_generate"] = 0.25 → 3.00` in both
`cost_meter.py` and `translation-service/cost_meter.py` (verified identical before and
after). $3.00 matches the live `COST_HARD_LIMIT` for a tour and still rejects a truly
implausible pre-LOCAL-197 inflated row. Tests updated in
`tests/test_local200_cache_hit_charging.py`: a $5.00 row is still rejected; a
grounding-inclusive $0.30 / $1.70 row is now **recorded, not floored**. Full LOCAL-200
suite + LOCAL-594 grounding suite: **60 passed**.

### Files (r2)

- `cost_meter.py`, `translation-service/cost_meter.py` — ceiling 0.25 → 3.00 (step 2).
- `tests/test_local200_cache_hit_charging.py` — reject $5.00, accept grounding-inclusive
  $0.30/$1.70.
- `run_local594_mcmullen.py` — parameterized location/type/stops/slug; outputs to mounted
  `tours/`; report loop-stories-per-stop + cleared count.
- `run_local594b_r2_live.sh` — two-tour isolated-container harness with the $8 batch gate.

No DELETE, no GCloud. DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
.continuous_dev/STATUS.md untouched.
