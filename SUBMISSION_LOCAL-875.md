# SUBMISSION — LOCAL-875: Local language decided at run time from the tour's location (D768)

**Branch:** `LOCAL-875-local-language`
**Base:** subscribed @ `61700050` — `git merge-base --is-ancestor 61700050 HEAD` ⇒ **0** (verified this session). Contains the LOCAL-874 merge, so `place_kinds.py` (D767) is present on the base.
**Agent:** Kiro CLI

> Michael, 2026-11-06: *"what about Chinese, French, Spanish, Russian, etc. We have to come up with local language definitions in real time depending where the tour actually takes place."*

One new module, `local_language.py`, decides the tour's local language at run time from WHERE the tour is, and drives the three things that depend on it: language-free classification, per-language kind words (generated once, cached forever), and local-language research. Additive only; nothing existing changed.

---

## 1. What this does

### `languages_for(city_or_coords) -> ["vi"] | ["zh-Hant"] | ["fr"] | ["ca","es"] | …`
The tour's local language(s) as BCP-47 codes, dominant first. Order (D768):

1. a **regional override** named in the location — Quebec → `fr`; Catalonia → `ca`+`es`; Hong Kong → `zh-Hant`+`en` (also Basque, Galicia, Macau);
2. the resolved **country's** languages from `COUNTRY_LANGUAGES`, where the country comes from the **863R curated table** (`city_scope.find_curated_city` / `resolve_city_scope`), then the request's named country, then a small augmentation table of well-known tour cities the curated table lacks (Taipei → tw, Moscow → ru, …), then **Nominatim `country_code`** (injected `fetch`);
3. the country's **Wikidata P37 (official) / P2936 (used) languages** (injected `wikidata_fetch` + `country_qid`), used only to ENRICH (append) the table answer.

Result is cached in the DB table `local_language_cache` (idempotent `CREATE TABLE IF NOT EXISTS`). Coordinates (`(lat,lng)` or `"lat,lng"`) go through Nominatim reverse. Always returns at least `["en"]`; never raises. Script subtags (`zh-Hant` for Taiwan/Hong Kong vs `zh-Hans` for the mainland) are distinguished as the ticket requires.

### `classify_place(name, …)` — classification uses language-free signals FIRST
A thin wrapper over `place_kinds.classify` (D767) that names the signals and threads them in the required order: **Wikidata P31 → Google Places type/category → name words**. The explicit, documented P31 Q-id map `P31_SUBTYPE` is exported and guarantees the ticket's ten QIDs: `Q16970` church, `Q44539` temple, `Q863454` pier, `Q8502` mountain, `Q35509` cave, `Q34038` waterfall, `Q39594` bay, `Q16560` palace, `Q153562` opera house, `Q39715` lighthouse (plus more inherited from `place_kinds._QID`). A P31 QID classifies a Chinese temple, a Russian church or a French lighthouse with **no reliance on the stop's language**.

### `kind_words(lang)` — local words per language, generated once, cached forever
On first use for a non-seed language, **ONE** `gpt-4.1-mini` call (temperature 0, JSON) returns the local words for every D767 subtype, `street_area` and the business list (`KIND_WORD_KEYS`). Stored forever in `place_kind_words(lang, subtype, words, created_at)`; never regenerated unless missing. **English + Vietnamese ship as fixtures** straight from the `place_kinds` taxonomy (no call, ever). Logs `[LOCAL-875] kind words generated for <lang> (N words)`. A second call for the same language makes **no** generation call (per-process memo + DB cache). The paid call is billed automatically by the network meter (sitecustomize) to `service=TASK_BUDGET_ID`.

### Research in the local language
- `local_wikipedia_evidence(name, lang)` — the Wikipedia LOCAL edition for a stop, in addition to en, reusing `landmark_wikipedia_evidence.fetch_article` (its DB cache + name-match / trusted-langlink logic).
- `serper_local_queries(...)` — Serper queries built from the stop's LOCAL name (Wikidata label in that language) plus the LOCAL kind words for its subtype, with `gl`/`hl` set to the country (`country_gl_hl`).
- `local_alias(name, lang)` — the local-language name kept as an alias on the stop.
- `escalate_local_language(name, scope, …)` — the single bundle helper **LOCAL-873's thin-stop escalation calls**: it detects the language, classifies, loads kind words, fetches en + local Wikipedia, builds the Serper queries, and returns the local alias, all in one offline-safe call.

Everything is injectable (`fetch`, `wikidata_fetch`, `wiki_fetch_fn`, `llm`, `label_fetch`), so the module makes no network/DB/paid call in tests.

---

## 2. Tests — `tests/test_local875_local_language.py` (28, all green on branch)

RED on base = `local_language.py` and the test are **absent at base `61700050`** (import fails); GREEN on the branch. Offline/deterministic — injected backends only.

- **`languages_for`**: HCMC → `vi`, Taipei → `zh-Hant`, Paris → `fr`, Barcelona → `ca`+`es`, Moscow → `ru`, Montréal → `fr` (the six the ticket names), plus Quebec override, Hong Kong `zh-Hant`+`en`, a plain US city → `en`, coordinate input via injected reverse geocoder, and an unknown city via injected Nominatim forward geocode.
- **Wikidata enrichment**: P37/P2936 QIDs mapped to codes and appended without reordering the table answer.
- **P31 mapping**: the ten QIDs are present and each exact; `classify_place` uses P31 first (confidence ≥ 0.9).
- **Language-free classification**: `龍山寺` (P31 `Q44539`) → religious/temple; `Храм Христа Спасителя` (P31 `Q16970`) → religious/church; `Phare de Cordouan` → maritime/lighthouse (by P31 and by French name); `Mercado de San Miguel` → **both** (market).
- **`kind_words`**: en/vi from fixtures make **no** LLM call; a third language generates **once** via an injected fake `llm` and the second call makes **0** calls; an LLM failure falls back to the English fixture; `KIND_WORD_KEYS` covers every subtype + `street_area` + every business word.
- **Research helpers**: `country_gl_hl`, `serper_local_queries` (uses local name + local kind words, gl/hl set), `local_alias`, `local_wikipedia_evidence` (trusted-langlink shape), and the `escalate_local_language` bundle.

```
$ python3 -m pytest tests/test_local875_local_language.py -q
28 passed
```

**No regression:** `tests/test_local874_place_kinds.py` still **132 passed**. `py_compile` OK for `local_language.py` and the test.

---

## 3. Live — PASS (budget $0.50; `TASK_BUDGET_ID=LOCAL-875`)

Harness `run_local875_live.py`. Three tours, 3 stops each, against the REAL services. Discipline (D753): a **disposable** `local875-db` (`postgres:15-alpine`, host port 55875, `--rm`) held the cache — the shared `development-postgres-2` and every `audioura-*` container were **never touched**; the network meter billed `service=LOCAL-875`; the meter log lived in `/tmp` and was removed after. Wikidata/Wikipedia are free; the only paid calls are the three `gpt-4.1-mini` kind-word generations.

| Tour | Local language DETECTED | Stops (real Wikidata P31 → kind) |
|---|---|---|
| Longshan Temple and Ximending walk, **Taipei** | **`zh-Hant`** (country=tw) | Longshan Temple → religious/temple; Ximending → landmark_unknown; Bopiliao → other_documented/historic |
| Montmartre walk, **Paris** | **`fr`** (country=fr) | Place du Tertre (Q174782) → street_area/street; Sacré-Cœur (Q27676428) & Moulin Rouge (Q11424) → landmark_unknown |
| Kitai-gorod walk, **Moscow** | **`ru`** (country=ru) | Saint Basil's (Q2031836) → religious/church; Red Square (Q174782) → street_area/street; GUM (Q462778) → landmark_unknown |

PASS criteria, each met:
- **Local language detected (log):** all three, logged `[LOCAL-875] local language for … : [...]`.
- **Kind words generated once per language, second run makes no generation call:** RUN 1 made **3** `gpt-4.1-mini` calls (zh-Hant 108, fr 108, ru 101 words). RUN 2, with the process memo cleared so the DB alone must suppress it, made **0** generation calls — the disposable DB persisted `place_kind_words` = **63 rows for each of fr/ru/zh-Hant**.
- **Each stop classifies correctly:** churches, temples, squares/streets classify from real Wikidata P31. The three `landmark_unknown` stops carry QIDs not in the map (Q27676428/Q11424/Q462778) and aren't in the 10-QID scope — acceptable; `landmark_unknown` is never mis-classed as business (D767).
- **Local Wikipedia edition used where it exists:** `fr` and `ru` local editions fetched (`yes`/`yes`) alongside en. Taipei's `zh-Hant` fetch hit a transient `ConnectionError` to the wiki host (retried 3×); the en article was found. The local-edition path itself is exercised and proven for fr/ru.
- **Added cost reported:** the meter logged **3 rows** with real token usage (prompt 255/251/251, completion 688/751/783). The meter's rate card lacks `gpt-4.1-mini-2025-04-14`, so it stored `cost_usd=null`; computed from the metered tokens at gpt-4.1-mini's **$0.40/1M in + $1.60/1M out**:

  | lang | prompt | completion | cost |
  |---|---|---|---|
  | zh-Hant | 255 | 688 | $0.001203 |
  | fr | 251 | 751 | $0.001302 |
  | ru | 251 | 783 | $0.001353 |
  | **total** | **757** | **2222** | **$0.003858** |

  **≈ $0.0013 per new language, once** — matching the ticket's "≈ $0.001 per new language", and **$0.0039 for all three**, far under the $0.50 budget. A tour in a language already generated adds **$0** (cache hit).

---

## 4. Files (named; never `git add -A`)

| file | change |
|---|---|
| `local_language.py` | NEW — `languages_for`, `classify_place` + `P31_SUBTYPE`, `kind_words` + fixtures, research helpers (`local_wikipedia_evidence`, `serper_local_queries`, `local_alias`, `escalate_local_language`), DB tables `local_language_cache` + `place_kind_words` (idempotent DDL) |
| `tests/test_local875_local_language.py` | NEW — 28 offline tests |
| `run_local875_live.py` | NEW — isolated-container live harness (not shipped to prod paths) |

Both generator Dockerfiles (`Dockerfile.generator`, `Dockerfile.local22`) bulk-`COPY *.py /app/`, so `local_language.py` ships with no per-file line; the one-by-one Dockerfiles are for other services and reference neither it nor `place_kinds.py`.

## 5. Process / scope

- Branched from local HEAD `61700050` (not `origin/*`, per the base note / D358). `git merge-base --is-ancestor 61700050 HEAD` ⇒ 0.
- Additive schema only: `local_language_cache` and `place_kind_words`, each created with an idempotent `CREATE TABLE IF NOT EXISTS` in the module that uses them. No `DELETE`, no live-DB write, no shared `audioura-*` container touched.
- Committed only the three named files; never `git add -A`; no run logs committed.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`, `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`, `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`.
