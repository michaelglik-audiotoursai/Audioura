# SUBMISSION — LOCAL-873C: the thin-stop rebuild is narrated, not pasted web copy; the Orientation is never repeated

**Branch:** `LOCAL-873C-rebuild-narrated` (base: `subscribed` = `66caed0b`)
**Verified base:** `git merge-base --is-ancestor 66caed0b HEAD` → exit 0.
**Evidence:** `submission_artifacts/local873b/saigon_centre_landmarks_walking_tour.txt`, Stop 3, Nguyễn Văn Bình Book Street (merged in `66caed0b`).

LOCAL-873B made the escalated facts *reach* the delivered body and judged "thin" on the delivered text. But its rebuild was **deterministic** — it appended the scraped facts as raw sentences. LEAD read Book Street and found it reads like a pasted web page:

1. the Orientation was repeated verbatim as the body's first three sentences;
2. the appended facts were raw scraped copy with broken grammar and capitalisation — *"Ho Chi Minh City Book Street Known as Nguyen Van Binh Book Street, is a cultural hub …"*, *"… has a bookstore café, newspapers area, magazine area, stationery, old book exchange …"*;
3. the facts were written without diacritics (*Nguyen Van Binh*, *Hai Ba Trung*) while the rest of the tour uses the Vietnamese spelling.

This bounce makes the rebuild speak.

---

## 1. When the rebuild fires, it NARRATES — one cheap gpt-4.1-mini call, verified

`thin_stop_delivery.rebuild_thin_delivered_stops` now tries narration **first**, falling back to the deterministic append only on failure.

- `narrate_stop_body(title, facts, orientation, location, *, narrate_fn, claim_gate_fn, …)` makes **ONE gpt-4.1-mini call (temperature 0.3)** constrained to the given facts only, asking for **5–7 spoken sentences in the tour's voice: second person, present tense**, with the orientation it is shown explicitly excluded.
- Every returned sentence is kept **only if it is both**:
  - **traceable to a fact** — ≥ 3 distinctive content tokens shared with some fact (the 873B fact-sheet-verify notion), and
  - **free of unsourced claims** per the **LOCAL-872 claim gate** (`landmark_claim_gate.unsourced_claims`): a sentence that names an architect, person, event, work or date no fact supports is dropped.
- Surviving sentences are deduped against the Orientation (see §3). If fewer than 5 traceable sentences survive, `narrate_stop_body` returns `None` and the rebuild **falls back** to the deterministic append.
- On success the stop body is **replaced** by the narration (not appended), so no raw scraped copy and no repeated Orientation can ship.
- The LLM backend is injectable (`narrate_fn`); the default `_default_narrate` is a plain `requests.post` the live meter already intercepts, so the call is billed and cost-capped. **≈ $0.006/stop**, well under the ≈ $0.01/stop cap; the whole 873C rebuild added **$0.0014** this tour (facts were already escalated).

Wired in `generate_tour_text.py` at the post-narration thin check: `claim_gate_fn=_claim_gate_873c` (the 872 gate) and the default metered `narrate_fn`.

## 2. Deterministic fallback — now with the three fixes (`repair_fact_sentence`)

When narration fails or the gate rejects it, the append path runs with each fact first passed through `repair_fact_sentence(text, title)`:

- **No "X Known as Y," fragment.** `"Ho Chi Minh City Book Street Known as Nguyen Van Binh Book Street, is a cultural hub …"` → the local alias is kept as the subject: `"Nguyễn Văn Bình Book Street is a cultural hub …"`.
- **Sentence-case repair.** A stray interior capitalised connective ("Known", "Located", "Situated") that starts no sentence is lower-cased.
- **Local diacritic spelling from the stop title.** Each word whose diacritic-folded form matches a title word is restored to the title's spelling, so *Nguyen Van Binh* reads *Nguyễn Văn Bình* as the rest of the tour does.

## 3. The Orientation is never repeated (both directions)

`dedup_against_orientation(body_sentences, orientation)` drops any body sentence that equals, is contained in, or contains an Orientation sentence (normalised, accent-folded match). It is applied to the narrated body, to the existing delivered body (so the 873B verbatim-Orientation opening is cleaned before measuring), and to each candidate fact in the fallback.

---

## 4. The root-cause fix that made the live run PASS at the $0.25 cap

The first live runs showed the rebuild's facts map **empty** and the stop re-escalating (budget-refused). Cause: the LOCAL-873 escalation runs inside the per-stop **narration worker threads** under `job_scoped_state`; the facts it writes to the job-scoped `_THIN_FACTS_PER_STOP` are **not visible to the main thread** that runs the post-narration rebuild (contextvar writes do not propagate out of a child context). So the main-thread rebuild saw no facts and re-escalated — wasteful, and at a tight budget, refused.

**Fix:** a process-global `_THIN_FACTS_SINK` keyed by a per-job token `_THIN_SINK_KEY` that is set in the **main thread** at the top of `generate_tour_text`, before any worker spawns, so each worker inherits (reads) the same key and writes its escalation facts into the one bucket the main-thread rebuild later reads. The rebuild merges the sink into its facts map. Keyed per job, reset per generation, so concurrent jobs never read each other's facts. Result: **0 re-escalations**, and the narration fits the budget.

---

## Tests (offline, no network, no paid call)

`tests/test_local873c_narrated_rebuild.py`:

- **the exact Book Street raw facts** → a narrated body with **≥ 5 spoken sentences, no Orientation duplicate, no "Known as" fragment, and Vietnamese spelling**, with a second-person cue;
- **the fallback path** (narration forced to fail) → same: no "Known as" fragment, local diacritic spelling restored, no Orientation repeat;
- **a rich stop is left byte-for-byte unchanged**;
- a narrator that injects an unsourced architect / date is **rejected by the claim gate** and the stop falls back (neither invented claim ships);
- unit coverage for `repair_fact_sentence` (keep-alias "Known as" repair, diacritic restore), `fact_sentences(title=…)`, and `dedup_against_orientation` (both directions).

```
tests/test_local873c_narrated_rebuild.py ....... 8 passed
tests/test_local873b_thin_stop_fixes.py ........ 13 passed   (unchanged)
tests/test_local855d_fact_sheet_verify.py ...... 10 passed   (unchanged)
```

---

## Live — Michael's same 10 Saigon stops, BUDGET ENFORCED

`TASK_BUDGET_ID=LOCAL-873C TASK_BUDGET_USD=0.25`, in-process from this worktree against this task's **own** postgres (`docker-compose.local873c-proof.yml`, project `local873c`, spare port `:55975`), torn down `-v` afterwards. The shared `audioura-*` containers, the shared dev DB and the live DB were never touched. TTS not called.

**Result — PASS at $0.2478 of $0.25:**

```
[PASS] 10/10 stops delivered
[LOCAL-873B] post-narration thin check: 3 stop(s) rebuilt from facts (3 narrated), 0 escalated now; added cost $0.0014
[PASS] no stop has fewer than 4 content sentences: all >= 4
[PASS] Book Street has >= 5 spoken sentences: 6
[PASS] Book Street body does not repeat the Orientation: no repeat
[PASS] Book Street has no raw-copy fragment: none
[PASS] Bạch Đằng Pier has >= 3 sourced specifics in the delivered body: 3
[PASS] Ho Chi Minh City Hall has >= 3 sourced specifics in the delivered body: 5
[PASS] no stop text names a banned place/figure: none
=== SAIGON PASS ===
```

The delivered Book Street body (full text in `submission_artifacts/local873c/saigon_centre_landmarks_walking_tour.txt`, Stop 3):

> You are standing on Nguyễn Văn Bình Book Street, named on July 4, 2000, after the famous intellectual Nguyễn Văn Bình. This pedestrian-only street stretches 100 meters from Hai Ba Trung Street to the Notre Dame Cathedral, right in the heart of Ho Chi Minh City. Here, you find over 20 uniquely designed bookstores offering thousands of books in multiple languages and genres. The street blends traditional streetscapes with cafés and green spaces, creating a vibrant urban public space. Nguyễn Văn Bình Book Street is a cultural hub that gathers book publishers from across the country, featuring bookstores, cafés, and exhibition areas. You are just opposite the Independence Palace and about 3 kilometers from Bui Vien Street, making this a central spot for book lovers.

Six spoken, second-person, present-tense sentences — no repeated Orientation, no raw-copy fragment, Vietnamese spelling throughout.

---

## Files

- `thin_stop_delivery.py` — `narrate_stop_body`, `repair_fact_sentence`, `dedup_against_orientation`, `_default_narrate`; `rebuild_thin_delivered_stops` narrates first then falls back, with Orientation dedup on both paths.
- `generate_tour_text.py` — wired `narrate_fn` (metered default) + `claim_gate_fn` (LOCAL-872) into the rebuild; added the process-global `_THIN_FACTS_SINK` / `_THIN_SINK_KEY` so worker-escalated facts reach the main-thread rebuild.
- `tests/test_local873c_narrated_rebuild.py` — the 873C tests.
- `run_local873c_live.py`, `docker-compose.local873c-proof.yml` — the own-DB live proof harness.
- `submission_artifacts/local873c/saigon_centre_landmarks_walking_tour.txt` — the delivered tour text.
