# SUBMISSION — LOCAL-845 (two small leftovers)

**Branch:** `LOCAL-845-leftovers`
**Base:** subscribed (`85c0b323`, contains `526fee34`) — `git merge-base --is-ancestor 85c0b323 HEAD` → 0, `git merge-base --is-ancestor 526fee34 HEAD` → 0.

Two field leftovers, fixed, tested from the exact strings, and proven on a
budget-enforced live run.

---

## 1. Provider guard — a restaurant passed the activity-provider guard

**Evidence.** LOCAL-835B live (`reports/local835b/gen_835b_final.log`): "Scuba
diving courses in Nha Trang, Vietnam" kept **Nha Trang Xua** (Nhà hàng Nha Trang
Xưa, a well-known restaurant in a heritage house) as a dive provider.

**Root cause.** The activity-provider guard
(`category_match_guard.candidate_is_activity_provider`) classifies a candidate
from its own carried name/type. "Nha Trang Xua" reached the guard with a
name/type that carries **no English food word**, so `classify_place` returned
`None` → UNKNOWN → the guard kept it (it never drops a place it cannot classify).
The name-only classifier had no evidence that it is a restaurant.

**Fix** (`category_match_guard.py`):

1. **Local-language food words.** Added `"nha hang"` and `"quan"` to
   `_FOOD_VENUE_WORDS`, so the full local name "Nhà hàng Nha Trang Xưa" / a
   "Quán …" venue classifies as food from its **name alone** (folded,
   accent-stripped). Whole-word matched, so "Quang …" is not a false hit.

2. **Cheap category resolver for the UNKNOWN tail.** `candidate_is_activity_provider`
   and `filter_off_category_activity` take an optional
   `category_resolver: name -> category text`. When the first pass would return
   `None` (no class signal from the candidate's own fields), the resolver is
   called **once** with the candidate's title; its category is re-classified:
   a restaurant/café/bar result → **off-category (False)**; anything still
   unknown → **None (kept)** — never drop on no evidence. The resolver is only
   ever reached on the unknown tail, so a stop already decided by its own type
   costs nothing.

3. **`serper_category_resolver(scope)` factory.** Builds the resolver on ONE
   Serper Places lookup per name via `places_search.places_search` (identical
   `(query, ll)` is 24 h-cached → a name already verified on the map during
   generation is a CACHE HIT and bills nothing; otherwise it is the single extra
   lookup the ticket allows, ≈ $0.002). Memoized per tour. Never raises.

**Wiring** (`generate_tour_text.py`): the resolver is passed at the primary
post-discovery activity guard (`_foca835`, the request/scope are in hand) and at
the FINAL pre-narration pass (`_foca835f`, the last net before narration), so a
restaurant that arrives via any ADD/KEEP path is caught.

Decision table (non-food activity-provider request):

| candidate signal | verdict |
|---|---|
| name/type has the activity word or a provider noun | keep (provider) |
| name/type is a food/drink class (incl. "nhà hàng"/"quán") | **drop** |
| name/type is a generic landmark / lodging | drop (unless named anchor) |
| **no signal; resolver → restaurant/café/bar** | **drop** (LOCAL-845) |
| no signal; resolver → unknown / Serper off | keep |

## 2. Olympia D1v2 — a famous work dropped on the live canonical set

**Evidence.** LEAD Mac run after 826B (Orsay, real cache):
`[D1v2] DROPPED 'Olympia' — no canonical title match`.

**Root cause (reproduced on the real cached Q23402 rows).** Before D1v2
verification, `generate_tour_text._verify_works_v2` prunes the canonical set of
any title whose normalized form is a **substring** of a longer title ("prefer
longer forms") — intended to drop truncated SITE EXTRACTIONS. The real Orsay set
(300 works) carries three works: **"Olympia"** (Manet), **"A Modern Olympia"**
and **"Une moderne Olympia"** (Cézanne). `"olympia"` is a (non-prefix) substring
of the two longer siblings, so the prune **deleted the bare "Olympia"** from the
matchable set. The candidate "Olympia" then had only the longer siblings to
match, which the LOCAL-826 specificity gate correctly rejects as distinct works
→ `DROPPED`.

The LOCAL-826B unit test never caught this because it manually replaced
`"Olympia"` with `"Olympia (toile)"` in the set — it never exercised the prune
that deletes "Olympia" while keeping the siblings.

**Fix** (`story_miner.py` + `generate_tour_text.py`): new
`story_miner.is_distinct_shorter_work(shorter_norm, longer_norm)` (with
`_is_subject_word` / `_SUBJECT_STOP_WORDS`). A shorter substring is a **distinct
sibling work** — keep it — when it is **not a left-anchored prefix** of the
longer AND the longer adds a distinctive **SUBJECT** word (not a stopword, not a
descriptor/medium/material, not a year). Wired into the prune loop: a title is
only removed when it is NOT a distinct shorter work.

* `"Olympia"` ⊄-prefix `"A Modern Olympia"`, extra subject word `"modern"` →
  **distinct, kept** → VERIFIED.
* `"The Adoration"` **is a prefix** of `"The Adoration of the Magi"` → genuine
  truncation → still pruned.
* `"Olympia"` → `"Olympia (toile)"` extra word `"toile"` is a descriptor → same
  work → still pruned (LOCAL-34 enrichment preserved).
* `"Une moderne Olympia"` stays its own work (`A Modern Olympia`), never folds
  into bare Olympia.

Reproduction on the real fixture (`tests/fixtures/local826b/q23402_venue_works_cache.json`, 300 works):

```
OLD prune: 'Olympia' removed → match_candidate_to_canonical('Olympia') = None  (DROPPED)
NEW prune: 'Olympia' kept    → VERIFIED 'Olympia' ; 'Une moderne Olympia' → 'A Modern Olympia'
```

---

## 3. Tests — from the exact strings

`test_local845_leftovers.py` (19 tests, all pass):

* **Nha Trang Xua** — scuba request is a provider request; the Vietnamese name
  classifies as food; the bare name is UNKNOWN (kept) without a resolver and
  **off-category** with a resolver returning "Vietnamese restaurant"; the
  resolver is only called on the unknown tail (a decided dive centre is never
  sent); unknown-after-lookup is kept; `filter_off_category_activity` drops the
  restaurant and keeps the dive centres; a food request is a no-op.
* **Olympia** — `is_distinct_shorter_work` on the exact strings; prefix
  truncation not distinct; descriptor-enriched same work; end-to-end on the real
  cached Q23402 set: OLD prune drops Olympia, NEW keeps and VERIFIES it, "Une
  moderne Olympia" stays distinct, a genuine truncation ("The Church") is still
  pruned; wiring sanity.

```
python3 -m pytest test_local845_leftovers.py -q
→ 19 passed
```

Regression — the guard/canon/matcher suites stay green:

```
python3 -m pytest test_local845_leftovers.py \
  tests/test_local835_activity_on_category.py tests/test_local835b_guard_every_path.py \
  test_local843_activity_yield.py tests/test_local791b_names_category.py \
  tests/test_local791_vietnam_round2.py tests/test_local830_category_scoped_reuse.py \
  test_local826_canon_and_shortfall.py test_local826b_cached_canon_and_stop4.py \
  tests/test_local577_museum_refill.py test_w4_matcher.py test_contained_regression.py \
  test_local583_documented_works.py tests/test_local372_book_word_drop.py \
  test_local618_subentity_venue.py test_local667_title_split.py -q
→ 240 passed
```

**Pre-existing failure (NOT this change):**
`test_local589_canonical_set_chrome_free.py::test_corpus_canonical_set_has_no_chrome_and_keeps_shows`
fails about a "Lua Kobayashi" exhibit re-admit on the cached exhibit-museum path.
Verified pre-existing by stashing the three source files and re-running on base
`85c0b323` — it fails identically. Unrelated to the provider guard / canonical
prune.

---

## 4. Live — BUDGET ENFORCED

`run_local845_live.py`, Mac-local, cheap arm, pool OFF, budget enforced
(`TASK_BUDGET_ID=LOCAL-845 TASK_BUDGET_USD=0.50`, `LiveRunMeter` reserve gate +
per-task JSON ledger). Documented no-mount diagnostic (writes its meter log under
`./_local845_meterlogs`, `METER_MOUNT_GUARD=0`): never writes the shared/live DB,
never touches the shared `audioura-*` containers.

```
CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
STORY_PASS_MODEL=gpt-4.1   NARRATION_MODEL=gpt-4.1-mini
RESEARCH_BACKEND=serper    SERP_PROVIDER=serper    DISABLE_STOP_POOL=1
```

**Scuba diving courses in Nha Trang, Vietnam (4)** — **4/4, PASS (no restaurant)**
1. Vietnam Diving and Training Nha Trang  2. Rainbow Divers  3. Sailing Club
Divers  4. Nha Trang Fun Divers — all dive providers; **Nha Trang Xua absent**.

**Orsay Museum, Paris, France (5)** — **5/5, Olympia VERIFIED.** The D1v2 lines:

```
[D1v2] VERIFIED 'L'Origine du monde' → canonical: 'L'Origine du monde'
[D1v2] VERIFIED 'Le Déjeuner sur l'herbe' → canonical: 'Le Dejeuner sur l'herbe'
[D1v2] VERIFIED 'Bal du moulin de la Galette' → canonical: 'Bal du moulin de la Galette'
[D1v2] VERIFIED 'Olympia' → canonical: 'Olympia'
[D1v2] VERIFIED 'La Nuit étoilée' → canonical: 'La Nuit étoilée'
[D1v2] VERIFIED 'L'Église d'Auvers-sur-Oise' → canonical: 'L'église d'auvers-sur-oise'
[D1v2] VERIFIED 'La Naissance de Vénus' → canonical: 'La Naissance de Vénus'
[D1v2] VERIFIED 'Un enterrement à Ornans' → canonical: 'Un enterrement à Ornans'
[D1v2] VERIFIED 'Arrangement en gris et noir n°1' → canonical: 'La mère de l'artiste'
[D1v2] VERIFIED 'L'Absinthe' → canonical: 'L'Absinthe'
```

`[D1v2] VERIFIED 'Olympia' → canonical: 'Olympia'` — previously
`[D1v2] DROPPED 'Olympia' — no canonical title match`.

**Cost.** `LiveRunMeter` all-providers total **$0.3849 < $0.50** (openai
$0.2872, serper $0.0580, gemini_tokens $0.0397, preflight $0.1088); status-200
Serper metered $0.1640. The `COST_METER` postgres-2 DB error in the log is
expected and harmless on the Mac-local no-mount diagnostic — it never writes the
live DB.

---

## 5. Files changed

* `category_match_guard.py` — Vietnamese food words; `category_resolver` param on
  `candidate_is_activity_provider` + `filter_off_category_activity`; new
  `serper_category_resolver(scope)` factory.
* `story_miner.py` — `is_distinct_shorter_work` + `_is_subject_word` /
  `_SUBJECT_STOP_WORDS`.
* `generate_tour_text.py` — the "prefer longer forms" prune skips a distinct
  shorter work; the resolver is wired at the post-discovery and final
  pre-narration activity guards.
* `test_local845_leftovers.py` — new tests (19).
* `run_local845_live.py` — the budget-enforced live proof.

Only these files are committed (`git add` by path, never `git add -A`). The live
run's generated tour `.txt`/`.json`, `_local845_meterlogs/`, and
`reports_local845_live.log` are NOT committed; incidental run-rewrites of tracked
debug dumps were reverted.
