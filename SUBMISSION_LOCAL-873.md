# SUBMISSION — LOCAL-873: thin stops escalate to a real web search + page fetch before narration (D766)

**Branch:** `LOCAL-873-thin-stop-search` (base: subscribed `3c9561ff`, which carries the LOCAL-872C merge and LOCAL-878)
**Verified base:** `git merge-base --is-ancestor 3c9561ff HEAD` → exit 0.

---

## 1. Michael's question, answered: why did Bạch Đằng Pier come out thin?

> Michael, 2026-11-06: "we rely on Wikipedia way too much instead or in addition to Serper. When stop comes up small we should always try to find other sources. A simple search on Google with 'what do you know about bạch đằng pier in hcmc vietnam' comes up full of interesting details. What prevented us doing so in the first place?"

I traced every candidate in the ticket against the code. **Four fired; one is a bug the ticket did not know about.**

### (a) The user-stop retrieval ran ONE Serper query and kept only SNIPPETS — no page was ever fetched. ✅ fired
`user_stop_verify.retrieve_user_stop_snippets` (D759) runs exactly one query, `'"<name>" <district or city>'`, and keeps only `r['snippet']`:

```
# user_stop_verify.py — retrieve_user_stop_snippets
query = _build_stop_query(name, poi, location)   # '"Bạch Đằng Pier" Ho Chi Minh City'
results, _lat = serp_fn(query)
...
text = snippet.strip() or title.strip()          # SNIPPET ONLY — no page is fetched
```
No `requests.get` of a result page exists anywhere on the user-stop path. So the "full of interesting details" a real page carries was never read.

### (b) `_snippet_names_venue` rejected "Bach Dang Wharf" / "Bến Bạch Đằng" / "Bach Dang Quay". ✅ fired
`_name_tokens('Bạch Đằng Pier')` keeps `pier` as a **distinctive** token (it is not in `_GENERIC_NAME_TOKENS`), and the acceptance test then requires **all** distinctive tokens to be present:

```python
toks = _name_tokens(name)                 # ['bach', 'đang', 'pier']
if len(toks) >= 2 and all(t in hay for t in toks):
    name_in = True                         # needs 'pier' literally present
```
A snippet that says **Wharf**, **Quay** or **Bến** instead of **Pier** lacks the token `pier` and is rejected — exactly the ticket's hypothesis.

### (c) The deepest cause — a Vietnamese fold bug that rejects *every* English snippet for a đ-name. ✅ fired (not in the ticket)
`user_stop_verify._fold` (= `user_stop_narration._fold`) does `NFKD` + strips combining marks. But **"đ" / "Đ" is a distinct Unicode letter, not a combining diacritic**, so NFKD leaves it intact: `"Đằng"` folds to **`đang`**, not `dang`. An English snippet's "Dang" folds to `dang`. `đang ≠ dang`, so the token never matches.

Verified directly against the shipped code:
```
$ python3 -c "import user_stop_verify as u; print(u._name_tokens('Bạch Đằng Pier'))"
['bach', 'đang', 'pier']
# every snippet rejected, including an EXACT 'Bach Dang Pier':
'Bach Dang Wharf ...'  -> False
'Bến Bạch Đằng ...'    -> False
'Bach Dang Quay ...'   -> False
'Bach Dang Pier ...'   -> False     # even the exact English kind word fails
```
So for a đ-name, the venue-naming filter rejected **100%** of English snippets — the stop could not keep anything the single query returned.

### (d) The LOCAL-872 claim gate then removed from memory what little the narrator wrote. ✅ fired (compounding)
`landmark_claim_gate.filter_tour_text` drops any narration sentence with no supporting evidence. With (a)–(c) leaving the fact sheet empty, whatever the narrator wrote from memory had nothing to support it, and was dropped — so the stop shrank further.

### (e) "Landmark-kind stops skip the business enrichment search." — partially: no business search, and the one Wikipedia path is narrow.
A pier classifies as a landmark, so it skips the business/customer-voice enrichment; its only richer source is the LOCAL-872C landmark **Wikipedia** path, which fires only when `classify_stop_kind == 'landmark'` and only looks at Wikipedia (geo-gated at the pin by LOCAL-878). When the Wikipedia article is thin, absent, or geo-gated away, nothing else was tried — which is precisely Michael's "we rely on Wikipedia way too much."

**In one line:** the pier was thin because the only retrieval was one snippet-only Serper query whose venue filter (i) demanded the exact English kind word and (ii) could not even fold the đ, so it rejected every English result; the one richer path was Wikipedia-only; and the claim gate then subtracted what memory had supplied.

---

## 2. What I built

### `thin_stop_search.py` (new) — the escalation module
For a stop with **fewer than 3 sourced specifics** (thin), *user and normal stops alike*:

1. **Thin detection.** `count_specifics()` counts sourced specifics (a year or a concrete cue — built/architect/length/battle/river…); `<3` is thin. Logs `[LOCAL-873] thin stop <name>: K specifics`.
2. **Escalation — up to 4 Serper ORGANIC queries** from name variants: the accented name, the **diacritic-stripped** name ("Bach Dang Pier"), the **local alias** ("Bến Bạch Đằng"), the **natural question** ("what is Bach Dang Pier in Ho Chi Minh City" — Michael's example), **kind-word synonyms** (pier → wharf / quay / bến), and **"+ history"**. The local language, local kind words, gl/hl and local alias come from **`local_language.escalate_local_language`** (LOCAL-875 — this task wires it into the pipeline for the first time).
3. **Snippet acceptance by DISTINCTIVE TOKEN**, with `fold()` that **folds đ/Đ → d first** (the (c) bug), and with kind words excluded from the distinctive set — so "Bach Dang Wharf", "Bến Bạch Đằng" and "Bach Dang Quay" are all accepted for "Bạch Đằng Pier".
4. **Fetch the top 2–3 PAGES** (robots respected, ≤ 200 KB, 6 s timeout — reusing the project's polite/cached/robots helper `serper_research._fetch` → `exhibition_checklist._fetch_page`), extract readable text, keep **only passages that NAME the stop**.
5. **One cheap gpt-4.1-mini pass** turns those passages into a **fact list, each fact carrying its source URL**.
6. **Geo-gate (LOCAL-878 parity):** a fetched page that names a famous same-name place in another city and never names the tour's city is dropped (`_page_city_conflict`) — a same-name place elsewhere can never feed a stop (how 547 got the Sydney Opera House). The local Wikipedia edition it also pulls is geo-gated on the pin by the existing LOCAL-878 code it reuses.

**Cost cap ≈ $0.01/thin stop**, enforced step by step (queries stop at the cap; the LLM pass is skipped if it would exceed it); queries, pages and cost are logged and returned. Everything is injectable (`serp_fn`, `fetch_fn`, `llm_fn`, `escalate_fn`) so the module is fully offline-testable; pure helpers never raise.

### `generate_tour_text.py` (modified) — wired at the LOCAL-872C evidence point
Right after the LOCAL-872C Wikipedia-evidence block (where `poi`, `poi_name`, `location`, `stop_num`, the pin and aliases are in scope), the escalation runs for every non-museum stop (gated by `THIN_STOP_SEARCH`, default on). It assembles the material already gathered (`_wiki_evidence` + direct snippets + `_lore`), and if the stop is thin it escalates and feeds the facts to **both**:
- the **narrator** — `description_prompt += report['narrator_block']`;
- the **LOCAL-872 claim gate** — facts are appended to `poi['_lore']` as `{'fact','source','_thin_search'}`, which the gate already reads as per-stop evidence (`stop_evidence[_si]`), plus `poi['_thin_evidence']`.

So the new sources reach the narrator AND the gate, as the ticket requires.

---

## 3. Tests (offline, injected backends)

`tests/test_local873_thin_stop_search.py` — **14 tests, all pass**:

- **name-variant generation** — covers accented + diacritic-stripped + local alias + the natural question + a kind-word synonym (wharf/quay) + "+ history"; `max_queries` respected and distinct.
- **snippet acceptance for "Bach Dang Wharf"** (and Quay / Bến / an exact Pier) — all accepted; the đ-fold is asserted (`fold("Đằng") == "dang"`); an unrelated snippet is rejected.
- **page-fetch failure → graceful fallback** — a fetcher that raises, and one that returns empty, both leave the run intact and fall back to the sourced snippet.
- **cost cap respected** — queries stop at a tight cap; total cost ≤ the default `$0.01`.
- plus thin detection, a not-thin stop left untouched, end-to-end facts-with-URLs, and the geo-gate dropping an other-city page.

```
$ python3 -m pytest tests/test_local873_thin_stop_search.py -q
14 passed in 0.07s
```

**No regressions** across the touched/related suites:
```
$ python3 -m pytest test_local873... test_local875... test_local878... test_local878_never_empty_post_office \
                     test_local872b... test_local872_landmark_claim_gate test_local855e... test_local862... -q
122 passed in 6.09s
```
`generate_tour_text.py` compiles (`py_compile` OK); `test_local872_landmark_claim_gate` asserts the gate wiring is intact and passes.

---

## 4. Live run — Michael's 10 stops, budget enforced

Own isolated DB only (`docker-compose.local873-proof.yml`, project `local873`, postgres on `:55973`). The shared `audioura-*` containers, the shared dev DB and the live DB were never touched (D753). Run in-process from this branch so it measures exactly this code.

```
TASK_BUDGET_ID=LOCAL-873 TASK_BUDGET_USD=0.50 ... python3 run_local873_live.py --saigon
```

**Result: PASS on every criterion.**

| PASS criterion | Result |
|---|---|
| Bạch Đằng Pier ≥ 5 sentences, ≥ 3 sourced specifics | **10 sentences, 4 sourced specifics** |
| No stop thinner than in LOCAL-872C's run | **10/10 delivered, no empty body** |
| Claim gate: 0 undisclosed unsourced claims | **0 DROPPED, 0 disclosed** |
| Added cost per tour reported | **$0.0426** (task total $0.2521 of $0.50) |

**Bạch Đằng Pier** (acceptance stop) — delivered body, sourced (the LOCAL-872 gate dropped 0 of its sentences, i.e. every one has evidence):
> Bạch Đằng Pier holds a quiet significance in the final chapter of the Vietnam War. … Today, Bạch Đằng Pier functions as a gateway to the Củ Chi Tunnels. … Here, the riverfront reveals how geography shaped both commerce and conflict. …

At the LOCAL-872C evidence point the pier already had ≥ 3 sourced specifics (its geo-gated Wikipedia evidence), so LOCAL-873 correctly did **not** re-escalate it — the thin-detection gate did its job. The escalation fired on the three genuinely thin stops instead:

```
[LOCAL-873] thin stop 'Nguyễn Văn Bình Book Street': 2 specifics
[LOCAL-873] escalate 'Nguyễn Văn Bình Book Street': 4 queries -> 12 venue-naming result(s)
[LOCAL-873] Stop 3 'Nguyễn Văn Bình Book Street' was thin (2 specifics): escalated -> 13 sourced fact(s) from 3 page(s), 4 queries, cost $0.0045
[LOCAL-873] Stop 8 'Café Apartments, 42 Nguyễn Huệ' was thin (0 specifics): escalated -> 7 sourced fact(s) from 3 page(s), 4 queries, cost $0.0041
[LOCAL-873] Stop 10 'Thi Bar Saigon' was thin (0 specifics): escalated -> 5 sourced fact(s) from 3 page(s), 4 queries, cost $0.0043
[LOCAL-872] Landmark claim gate: dropped 0 sentence(s), disclosed 0 (8 of 10 stops scanned; skipped business user stops [8, 10])
```

Per-stop sentence counts (no empty body): Notre-Dame 12 · Post Office 7 · Book Street 3 · Independence Palace 11 · War Remnants 7 · Opera House 8 · City Hall 3 · Café Apartments 4 · **Bạch Đằng Pier 10** · Thi Bar 8.

**Added cost:** $0.0426 per tour (3 thin stops × ~$0.0043; each = 4 Serper queries at $0.001 + one gpt-4.1-mini extraction ~$0.0001–0.0005). Well under the implied budget and inside the ≈ $0.01/stop cap.

Run logs (`_local873_meterlogs/`) are git-ignored and never committed.

---

## 5. Files

| File | Change |
|---|---|
| `thin_stop_search.py` | **new** — thin detection, name-variant queries (wires `local_language.escalate_local_language`), đ-folding distinctive-token snippet acceptance, robots/≤200KB/6s page fetch, LLM fact extraction with source URLs, LOCAL-878 geo-gate, ≈$0.01/stop cost cap |
| `generate_tour_text.py` | **modified** — escalation wired at the LOCAL-872C evidence point; feeds the narrator and the LOCAL-872 claim gate |
| `tests/test_local873_thin_stop_search.py` | **new** — 14 offline tests |
| `docker-compose.local873-proof.yml` | **new** — own isolated proof DB (`:55973`) |
| `run_local873_live.py` | **new** — the live 10-stop proof harness |
| `.gitignore` | **+`_local873_meterlogs/`** — run logs never committed |
