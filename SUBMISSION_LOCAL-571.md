# SUBMISSION — LOCAL-571: Writer model blind test (gpt-4o vs gpt-4.1)

**Branch:** `LOCAL-571-writer-model` (base: subscribed = `006f727`)
**Agent:** Mac Mini Kiro
**Default model: UNCHANGED.** No DB writes beyond normal generation. No GCloud.

---

## TL;DR

- **Step 1 (price check): DONE.** gpt-4.1 is ~20% cheaper than gpt-4o on both
  input and output, added to `cost_rates.py` from OpenAI's official page.
- **Step 2 (measure): BLOCKED after 1 of 8 cells** by OpenAI **credit
  exhaustion** on the only available key. One cell (`Palais_A`, gpt-4o) completed
  with full real data; the gpt-4.1 arm never produced a tour.
- **Step 3 (blind pack): built, but single-arm only** — a blind A/B pair needs
  both arms; only arm A exists, so the pack is honest about that rather than
  fabricating a B.
- **Step 4 (recommendation): below**, stated with the real n (writer cost is a
  measured gpt-4o number plus a price-only gpt-4.1 projection; quality A/B is
  **not** measured).

The measurement harness is correct and **resumable**: the moment the OpenAI
account has credits, re-running `python3 run_local571_measure.py` finishes the
remaining 7 cells and `python3 build_local571_blind_pack.py` rebuilds a full
blind pack. Nothing else needs to change.

---

## Step 1 — Price check (committed)

Source: **https://platform.openai.com/docs/pricing** (OpenAI's own page), read
**2026-10-03**. Standard (short-context) rates per 1M tokens:

| Model   | Input | Cached input | Output |
|---------|-------|--------------|--------|
| gpt-4o  | $2.50 | $1.25        | $10.00 |
| gpt-4.1 | $2.00 | $0.50        | $8.00  |

gpt-4.1 is **20% cheaper on input** (2.00 vs 2.50), **20% cheaper on output**
(8.00 vs 10.00), and much cheaper on cached input (0.50 vs 1.25). Added to
`cost_rates.py` `LLM_RATES` in the same form as `gpt-4o`, with the source URL and
read-date inline. `cached_input_per_1m` is recorded for provenance only — the
pipeline does not price prompt-cache hits separately (`llm_cost()` reads only
input/output), so the existing cost math is unchanged. Verified:
`_resolve_model_rates` maps `gpt-4.1` → 2.00/8.00 and the dated wire name
`gpt-4.1-2025-04-14` → 2.00/8.00 (substring), while `gpt-4o`, `gpt-4o-mini`, and
`gpt-3.5-turbo` are untouched.

**Model availability:** gpt-4.1 **is** available to this key — a live
`chat/completions` call returned HTTP 200 with wire model `gpt-4.1-2025-04-14`
(gpt-4o → `gpt-4o-2024-08-06`). So the task does **not** require stopping for
unavailability; it is blocked purely by account credits (below).

---

## Step 2 — Measurement (harness complete; run blocked by credits)

### Design (`run_local571_measure.py`)
- 4 requests × 2 arms = 8 cells, **3 stops** each, **D261 host env**, **Gemini
  off** (GEMINI_API_KEY/GOOGLE_API_KEY empty before import), **LOCAL-569 flags
  OFF** in both arms (never set).
  - A = `TOUR_STORY_MODEL=gpt-4o` (ship default), B = `TOUR_STORY_MODEL=gpt-4.1`.
  - Requests: `Palais Lascaris, Nice, France` (museum), `Museum of Fine Arts,
    Boston, MA` (museum), `restaurant tour of Boston, MA` (restaurant), `walking
    tour of Old Nice, France` (walking).
- **OpenAI cap $5 cumulative**, enforced with a per-cell headroom guard; resumes
  from `summary.json` and skips cells already complete; never DELETEs; records
  `audio_tours` before/after.
- **Writer isolation:** the per-tour cost accumulator aggregates *all* OpenAI
  calls into one bucket (writer + gates). The gates run gpt-4o-mini; the writer
  (story pass) runs the arm's `TOUR_STORY_MODEL`. The harness wraps
  `cost_accumulator.add_llm_usage` to tally USD + calls **per wire-model**, then
  attributes the arm's story model (matched by substring, excluding `-mini`) as
  the writer. This cleanly separates writer spend from gate spend.

### What completed: `Palais_A` (arm A, gpt-4o, museum, 3 stops) — REAL DATA

| Metric | Value |
|---|---|
| Stops delivered | 3 / 3 |
| **Writer calls (gpt-4o)** | **38** |
| **Writer $ (gpt-4o)** | **$0.7242** (input 241,589 tok, output 12,027 tok) |
| Non-writer LLM | gpt-4o-mini: 50 calls $0.0054; gpt-3.5-turbo: 3 calls $0.0020 |
| All LLM calls | 91 |
| LLM breakdown $ | $0.73166 (search $0, grounding $0 — Gemini off) |
| **Tour total $** | **$0.73166** |
| `[LOCAL-569]` attempts logged | 27 across stops |
| Shipped story_count by stop | {1: 0, 2: 2, 3: 1} |
| `[LOCAL-432]` story retries | 22 |
| `[LOCAL-235]` R10 | 1 sentence deleted (1 stop) |
| `[LOCAL-472]` specificity | 0 paragraphs removed, 3 ungrounded entities |
| `[LOCAL-229]` contradicted block | 3 blocked-stop lines, 3 groups blocked |
| `tour_quality.score_tour` | **clean=False**, defects=`['dangling_reference']` |
| score_tour metrics | dates=21, named_people=2, chars=5876 |
| Wall time | 276 s |

The one quality defect: Stop 3 opens with a dangling pronoun ("His donation…"
before Naderman is named) — a referent-ordering defect in the gpt-4o writer's
output. This is a gpt-4o observation; whether gpt-4.1 avoids it is exactly what
the blocked arm would have shown.

The writer isolation worked: on this tour the **writer was 99% of LLM cost**
($0.7242 of $0.7317), consistent with the D596 "81%+" observation (higher here
because Gemini is off and the story retry fired 22 times).

### Why the other 7 cells have no data — OpenAI credit exhaustion (hard blocker)

The single OpenAI key (`.env` → `/Users/micha/Audioura/.env`, identical to the
shell env key — no alternative key exists) ran out of credits **mid-run**. At
task start both models returned HTTP 200 and `Palais_A` generated fully; then
every subsequent call returned:

```
HTTP 429  {"type":"insufficient_quota","code":"credit_balance_exhausted",
           "message":"You have no credits remaining..."}
```

Each failed cell 429s at the intent-analysis phase and produces an empty/thin
tour (0 stops, no `.txt`). I confirmed the blocker is persistent and
unresolvable by me:
- Retried immediately, after 20 s, and in six spaced attempts over ~6 minutes —
  `credit_balance_exhausted` every time.
- A brief window showed HTTP 200 and `MFA_A` started, but credits depleted again
  within ~4 writer calls, yielding a degraded 1-stop tour; the harness now
  correctly treats a credit-starved cell as **incomplete** (ok requires 3 stops
  AND no quota-429 in the log) so it is retried, not cached.
- No second API key is available to switch to, and I cannot add credits.

This is logged in `summary.json` under `blocked`
(`{"before":"MFA_A","detail":"429 credit_balance_exhausted"}`) and every cell's
`.log` is in `LOCAL571_measure/`.

**To finish:** add credits to the OpenAI account, then
`python3 run_local571_measure.py` (resumes the 7 remaining cells under the same
$5 cap) and `python3 build_local571_blind_pack.py`.

---

## Step 3 — Blind pack (`~/Desktop/Audioura_model_blind/`)

The builder emits, for each request with **both** arms, `<name>_P.txt` /
`<name>_Q.txt` with the P/Q letter assigned at random per request and the mapping
in `KEY.md` after exactly 60 blank lines. No model names appear in any tour text
(verified). Because only `Palais_A` exists, there are **no blind pairs**: the one
available text is written as `Palais_SINGLE_A.txt` and `KEY.md` states plainly
that arm B (gpt-4.1) is missing due to credit exhaustion. The other three
requests have no text in either arm. The pack does **not** fabricate the missing
arm — a blind comparison with n=0 pairs would be worse than none.

---

## Step 4 — Recommendation (honest n)

**On cost:** gpt-4.1 is a clear ~20% price reduction on the writer, which is the
dominant LLM cost of a tour (99% on the one measured tour; 81%+ per D596). On the
one measured tour the gpt-4o writer cost **$0.7242** (tour total $0.7317). At the
*same* token counts gpt-4.1 would cost **$0.5794** (tour total ≈ $0.5868) — a
$0.1448 (20.0%) writer saving, which is simply the rate ratio. **This is a
price-only projection, not a measurement:** gpt-4.1 may use a different number of
input/output tokens and may trigger a different number of `[LOCAL-432]` story
retries (gpt-4o needed 22 here), and the writer makes ~38 calls per museum tour,
so the real per-tour delta could be larger or smaller than 20%. **On quality:**
nothing is measured — the gpt-4.1 arm never ran, so I cannot say whether gpt-4.1
fabricates more or less, trips the `[LOCAL-235]/[LOCAL-472]/[LOCAL-229]` gates
more or less, or sustains story_count better or worse than gpt-4o's shipped
{0,2,1} here (which already left a dangling-reference defect). **Recommendation:**
gpt-4.1 is promising enough on price to be worth a real A/B — but with **n = 1
cell measured and 0 blind pairs**, there is no quality evidence yet, so **do not
switch the default**. Finish the eight-cell run when credits are available, read
the blind pack, and decide on quality parity then. The default stays `gpt-4o`.

---

## Process / safety

- `git add` + `git commit` after each step; pushed to
  `origin/LOCAL-571-writer-model` with `-u`. `git rev-list --count
  subscribed..HEAD` ≥ 1 at every step. Branch verified on base `006f727`
  (`git merge-base --is-ancestor 006f727 HEAD` exits 0).
- **Default model unchanged.** Only `cost_rates.py` (price table) and new
  measurement/pack scripts were added.
- **`audio_tours` before = 198 (max_id 384); after = 198 (max_id 384)** — zero
  rows inserted (the in-process `generate_tour_text()` path does not call
  `store_audio_tour`). Nothing to null; no lat/lng backup needed; nothing
  DELETEd.
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  `.continuous_dev/STATUS.md`. Incidental debug dumps the generator overwrote
  (`openai_simple_debug.txt`, `prompt_dump_stop1.txt`) were reverted.
