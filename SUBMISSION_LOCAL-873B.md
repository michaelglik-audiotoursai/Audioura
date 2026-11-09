# SUBMISSION — LOCAL-873B: the escalated facts now reach the narration; thin is judged on the DELIVERED body; the wrong-ward Orientation and the đ-fold are fixed at source

**Branch:** `LOCAL-873B-thin-stop-fixes` (base: `LOCAL-873-thin-stop-search` = `1248985a`)
**Verified base:** `git merge-base --is-ancestor 1248985a HEAD` → exit 0.

LOCAL-873's escalation module was good — the root-cause analysis, the đ-fold, the page fetch, the cost cap. The delivered tour still failed Michael's bar. LEAD read every stop. This bounce fixes the four defects that survived into the delivered text.

---

## 1. The facts were found but not narrated (Book Street)

**What happened.** LOCAL-873 escalated Nguyễn Văn Bình Book Street and returned 13 sourced facts to the narrator. The *delivered* body still carried two content sentences. The log line that tells the story:

```
[LOCAL-855D] verify Nguyễn Văn Bình Book Street kept 1 dropped 15 -> grounded body
```

The post-assembly **user-stop fact-sheet verify** (`user_stop_verify.verify_user_stops_in_text`) judges each delivered sentence SUPPORTED/SENSORY/UNSUPPORTED against a fact sheet — and that fact sheet was built from the stop's *known fields plus one fresh Serper query*, **never the 13 escalation facts**. So every fact-rich sentence was judged UNSUPPORTED and dropped, and the stop fell back to a two-line grounded stub.

**The fix (two parts).**

1. **Carry the escalation facts to the verify.** A job-scoped `_THIN_FACTS_PER_STOP` map (in `generate_tour_text.py`, backed by `job_scoped_state` like the other per-job holders) records, by stop title, the facts LOCAL-873 found. `verify_user_stops_in_text` gained a `thin_facts_by_title` parameter and merges those facts into the fact sheet's `retrieved_sources` (up to 24, so a stop escalated to ≥5 facts has the evidence to keep ≥5 fact-traceable sentences). A sentence the narrator wrote *from* a fact is now judged SUPPORTED.

2. **A deterministic last-resort rebuild** (see §2) guarantees the floor even when the LLM narration came out thin regardless.

**Test.** `tests/test_local873b_thin_stop_fixes.py::TestBookStreetFactsReachNarration` feeds a Book-Street body plus its 13 facts through the real verify path (with an offline labeller that mimics the model judging against the fact sheet) and asserts **≥ 5 fact sentences survive** in the final text.

---

## 2. Thin is judged on the DELIVERED text too (Pier, City Hall) — `thin_stop_delivery.py` (new)

LOCAL-873 judged "thin" *before* narration (at the LOCAL-872C evidence point), so a stop that had ≥ 3 specifics there but came out thin after the gates was never caught. Bạch Đằng Pier (≈ 2 concrete facts delivered, the rest mood) and Ho Chi Minh City Hall (3 sentences) are exactly that case.

**The new module** runs as the **true last pass** (after the fact-sheet verify and the never-empty fill — so nothing can gut the body again):

- `count_delivered_specifics(body, facts)` counts the sourced specifics present in a delivered body. With no fact list it delegates to `thin_stop_search.count_specifics`, the **same metric the PASS check uses**, so the trigger and the acceptance never disagree.
- For a stop under **3 sourced specifics** or under **4 content sentences**: if we have no facts for it yet, it **escalates now** (`thin_stop_search.escalate_thin_stop`, the same ≈ $0.01/stop cost cap), then **rebuilds the body once** from the sourced facts — appending specific facts first (to cover the ≥ 3 specifics bar), then clean venue facts to reach a **5-sentence** fill target. The rebuild is **deterministic — no LLM for the rewrite**.
- Every candidate fact is **pre-filtered through the 855B user-stop scrub** (off-pin landmark / admin-geography), so only clean, on-pin facts are appended — no destructive re-scrub that would drop a good sourced fact. Truncated facts (trailing `…`, comma, dangling preposition) and facts that collide with the block field grammar (`Address: …`) are rejected or cleaned. Dedup against the existing body ignores the repeated venue-name and generic tokens, so a real new fact is not mistaken for a duplicate.

**Tests.** `TestPostNarrationThinCheck` — a thin delivered body is rebuilt to ≥ 3 specifics; a rich body is left byte-for-byte unchanged; a stop with no facts escalates once (cost ≤ $0.01); a `fact_filter` keeps an off-pin fact out of the rebuilt body.

---

## 3. The Orientation stated the wrong ward (Pier) — fixed at source + filtered

Pier pin `10.775263, 106.706880` is District 1, the downtown riverfront. The delivered Orientation read *"near the boundary of Thủ Dầu Một ward … the view toward Bình Mỹ across the Saigon River … this northern part of Ho Chi Minh City"* — places ≈ 25 km north. 855B dropped the same digression from the **body** but the phrasing on the **Orientation** line never matched.

**Source of the geography:** the model. There is no adjacent-ward lookup; the narrator invented the off-pin admin geography from parametric knowledge, and a late Orientation regeneration reintroduced it after the per-stop scrub.

**The fix.** The admin-geography filter (`_ADMIN_GEOGRAPHY_RE` in `user_stop_narration.py`) now catches the off-pin placement generically — a named off-pin ward (`Thủ Dầu Một`, `Bình Mỹ`, `Bình Dương`, diacritic-tolerant), a `boundary of <Proper> ward`, `adjacent/neighbouring wards`, and a cardinal placement of the stop within the city (`the northern/southern/… part of <City>`). It is applied to the **Orientation line** at the single final choke point `scrub_tour_text_user_stops`, which already scrubs the Orientation — the regex was the only gap.

**Test.** `TestWrongWardOrientation` — with the Pier pin, `scrub_user_stop_body` drops the ward/compass sentences, `scrub_tour_text_user_stops` strips them from the delivered Orientation, and an on-pin sentence ("…on the Saigon River in District 1") is kept.

---

## 4. The đ-fold at source

LOCAL-873's analysis (c) found that `user_stop_verify._fold` / `user_stop_narration._fold` leave `đ`/`Đ` intact (NFKD does not decompose `đ` — it is a distinct letter, not a combining mark), so `"Đằng"` folds to `đang`, every English `"Dang"` snippet is rejected, and D759's own retrieval keeps nothing for a đ-name. LOCAL-873 fixed it only inside the new module.

**The fix.** The **one shared `_fold`** (`user_stop_narration._fold`, imported by `user_stop_verify`) now folds `đ`/`Đ` → `d`/`D` **before** NFKD. `_fold("Bạch Đằng Pier") == "bach dang pier"`; the distinctive tokens are ASCII `['bach','dang','pier']`; an English `"Bach Dang Pier"` snippet is now accepted by the old `_snippet_names_venue` path (it was rejected before).

**Test.** `TestDjFoldAtSource` — the fold, the shared-helper identity (`user_stop_verify._fold is user_stop_narration._fold`), the ASCII tokens, and the old-path snippet acceptance.

---

## 5. Tests

`tests/test_local873b_thin_stop_fixes.py` — **13 tests, all pass**:

```
$ python3 -m pytest tests/test_local873b_thin_stop_fixes.py -q
13 passed
```

**No regressions** across the touched/related suites (last broad run, 213 passed):

```
$ python3 -m pytest tests/test_local873b_thin_stop_fixes.py tests/test_local873_thin_stop_search.py \
    tests/test_local855b_fixes.py tests/test_local855_user_stop_narration.py \
    tests/test_local855d_fact_sheet_verify.py tests/test_local855d_lead_review.py \
    tests/test_local862_user_stop_enrichment.py tests/test_local872_landmark_claim_gate.py \
    tests/test_local330_prolog_place_name.py test_local403_accented_title_snippet_delivery.py \
    test_local419_snippets_deliver_facts.py tests/test_local855e_d759_retrieval.py -q
213 passed
```

(The `test_local875` kind-words caching assertion is order-sensitive to a shared in-process/DB memo; it passes in isolation — `python3 -m pytest tests/test_local875_local_language.py -q` → 28 passed.)

A small, general **prolog-place** fix rode along: `_prolog_place` now strips a leading *descriptive, non-geocoding scope* segment (`"Saigon centre landmarks, Ho Chi Minh City, Vietnam"` → `"Ho Chi Minh City, Vietnam"`), keyed only on a trailing scope noun so real places (`Hyde Park, London`, `Tours, France`) are untouched — the opening no longer names the raw request scope. Covered by the existing 330/799/285/260 suites.

---

## 6. Live run — Michael's 10 stops, budget enforced

Own isolated DB only (`docker-compose.local873b-proof.yml`, project `local873b`, postgres on `:55974`), run in-process from this branch so it measures exactly this code, then torn down. The shared `audioura-*` containers, the shared dev DB and the live DB were never touched (D753).

```
TASK_BUDGET_ID=LOCAL-873B TASK_BUDGET_USD=0.30 … python3 run_local873b_live.py --saigon
```

**Result: PASS on every criterion.**

| PASS criterion | Result |
|---|---|
| Book Street ≥ 5 content sentences from its facts | **6** |
| Bạch Đằng Pier ≥ 3 sourced specifics in the delivered body | **5** |
| Ho Chi Minh City Hall ≥ 3 sourced specifics in the delivered body | **6** |
| No stop names Thủ Dầu Một, Bình Mỹ, Sydney, Utzon or "Saigon centre landmarks" | **0 of each** |
| No stop has fewer than 4 content sentences | **all ≥ 4** |
| Added cost reported | **$0.0792 / tour** |

Per-stop content sentence counts: Notre-Dame 11 · Post Office 11 · **Book Street 6** · Independence Palace 7 · War Remnants 7 · Opera House 9 · **City Hall 8** · Café Apartments 6 · **Bạch Đằng Pier 10** · Thi Bar 11.

**Added cost:** `$0.0792` per tour (LOCAL-873 pre-narration escalation + LOCAL-873B post-narration rebuild/escalation, each thin stop ≈ $0.004 of Serper + a cheap gpt-4.1-mini extraction, inside the ≈ $0.01/stop cap). **Task total `$0.2685` of the `$0.30` budget.**

The delivered tour is committed at `submission_artifacts/local873b/saigon_centre_landmarks_walking_tour.txt` (the tour text only). Run logs and meter logs (`_local873b_meterlogs/`) are git-ignored and never committed.

---

## 7. Files

| File | Change |
|---|---|
| `user_stop_narration.py` | `_fold` folds đ/Đ → d at source (the one shared helper); `_ADMIN_GEOGRAPHY_RE` extended to drop off-pin ward / adjacent-ward / cardinal-part placement from the Orientation |
| `user_stop_verify.py` | `verify_user_stops_in_text` gains `thin_facts_by_title`; merges the LOCAL-873 escalation facts into the fact sheet so fact-rich sentences survive |
| `thin_stop_delivery.py` | **new** — post-narration thin check on the delivered body: count sourced specifics, escalate-if-needed (≈ $0.01/stop), deterministic rebuild from pre-filtered facts |
| `generate_tour_text.py` | records escalation facts by title (`_THIN_FACTS_PER_STOP`), passes them to the verify, runs the post-narration thin check as the true last pass; `_prolog_place` strips a non-place scope segment |
| `tests/test_local873b_thin_stop_fixes.py` | **new** — 13 offline tests across all four fixes |
| `run_local873b_live.py` | **new** — the live 10-stop proof harness (own DB `:55974`, budget-gated) |
| `docker-compose.local873b-proof.yml` | **new** — own isolated proof DB |
| `.gitignore` | **+`_local873b_meterlogs/`** — run/meter logs never committed |
| `submission_artifacts/local873b/saigon_centre_landmarks_walking_tour.txt` | **new** — the delivered PASS tour (text only) |
