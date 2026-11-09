# SUBMISSION — LOCAL-883: Strict grounding gate (D771)

**Branch:** `LOCAL-883-strict-grounding`  **Base (subscribed):** `a831ba0c`
**Budget:** `TASK_BUDGET_ID=LOCAL-883 TASK_BUDGET_USD=0.50` — warm proof used **$0.2575**.

Stop chasing individual false claims: every factual sentence now has to be backed
by the stop's own evidence, or it is dropped. Five cloud proofs in a row (waves
37–41) each fixed the last run's false claims and each produced new ones from the
narrator's memory (City Hall's 1945 "declaration of independence", a Pier
evacuation "from this very platform", an Eiffel Post Office, the Palace tank lost
again). Pattern gates cannot keep up — this changes the mechanism.

---

## 1. Strict grounding gate (`strict_grounding_gate.py`)

After narration and every existing gate, for each stop (landmark, user, business):

- **Split** the body into sentences; **mark** each FACTUAL (a date, number, named
  person, event, function, or "first/only/largest") or NON-FACTUAL (sensory,
  directional, reflective) with a deterministic cue list.
- **ONE `gpt-4.1-mini` call per stop** (temperature 0, JSON) is given the stop's
  own evidence bundle — its article(s), the 873 page facts, the 873 geo/name-gated
  snippets — and the factual sentences. For each it returns
  `SUPPORTED` / `CONTRADICTED` / `UNSUPPORTED` plus the supporting quote.
- **Keep** SUPPORTED. **Drop** CONTRADICTED. **Drop** UNSUPPORTED — unless the
  evidence itself frames it as a legend, then **disclose** it (D760). A sentence
  whose core fact is supported but which appends an unverified characterisation is
  UNSUPPORTED (the prompt requires *every* element to be in evidence).
- A stop that falls below **5 content sentences** is rebuilt from evidence only
  (the 873C narrated rebuild) and re-gated **once**.
- Logs `[LOCAL-883] grounding <stop>: K kept, C contradicted, U unsupported` and
  each dropped sentence. Cost **≤ $0.003/stop** (cap enforced; warm run spent
  ~$0.0015 total across 10 stops because most stops were already clean).

Wired in `generate_tour_text.generate_tour_text` between the LOCAL-880 defect pass
and the signature-story survival, so the gate judges the cleaned body and the
signature survival (below) runs after it.

## 2. The signature story survives as SUPPORTED

A signature story's `source_sentence` is a verified substring of the stop's own
evidence, so the gate classifies it SUPPORTED and keeps it. If it is ever dropped,
the existing `signature_story.ensure_signature_in_tour` regenerates the stop once
with the exact source sentence. **The Palace tank of 30 April 1975 ships** — see
the warm text, Stop 4.

## 3. Canonical resolver (`venue_canonical_resolver.py`)

A canonical label is accepted only when:

- it shares a **DISTINCTIVE** token with the user's name (not a kind/generic word);
  or
- the user's name is a **pure category** ("Cathedral", "City Hall", "Post Office",
  "Opera House") and the candidate is the **same kind within 150 m** — it shares a
  recognised venue kind **and** (when the candidate carries Wikidata P31) a P31 of
  that kind; or
- the user's **own link/pin** names it.

Otherwise there is no canonical (the resolver returns `None` and the caller keeps
the user's name). The resolver only ever returns a *label*; `itinerary_import`
uses it as `matched_name`/`canonical_aliases`, never as address/type — so a stop's
Orientation and Type/Specialty stay the user's own. Wave-41 leaks, now fixed:

| User name | Wave 41 (wrong) | Now |
|---|---|---|
| Book Street | "22 Gia Long Street" | **None** (shares only "street") |
| Café Apartments 42 | "The Reverie Saigon" | **None** (shares nothing) |
| Cathedral | "Paris Commune Square" | **None** (wrong P31 kind) |
| Thi Bar | "DDA Hotel 183 De Tham" | **None** → keeps "Gay bar", 224 Đề Thám |

`_build_around_query` now also fetches P31; a `kind → P31 QID` map is derived from
the venue-kind vocabulary (D769-safe, no place-name table).

## 4. Small items

- **"This narrow street is long"** — an orphan left when an unsourced measurement
  is removed. Extended the LOCAL-880C measured-magnitude mop-up: a linking verb +
  the removed-measurement sentinel + a lone dimension adjective at the sentence end
  ("is `<MAG>` long") drops the whole predicate → "This narrow street."
- **Dangling "Continue to City Hall"** — `walking_directions_guard` now flags a
  go-to cue (continue/head/proceed/make-your-way/walk/go to) whose destination is
  not the next stop, even when that place was dropped/reordered away (the
  arrival-cue pass could not see it); `ensure_walking_directions_lead_to_next`
  replaces it with the correct next-stop hand-off.
- **Cache re-validation log** — `landmark_wikipedia_evidence._cache_get` prints
  `[LOCAL-882] cache revalidate <name> @<pincell>: HIT/STALE/REJECT/negative …` on
  every warm-cache decision, so the cloud proof can see it (visible throughout the
  proof log).

## 5. Dedup keeps the richer block (`stop_title_dedup.py`)

A title collision ("War Remnants Museum" vs "War Remnants Museum.") used to keep
the FIRST block; a reordered/budget-starved run emitted a near-empty stub before
the real block, so the stub shipped and the content was dropped (a 1-sentence
stop). The dedup now keeps the first UNLESS it is a stub (< 40 prose chars) and the
later block has real body, in which case the richer block takes the slot. Two real
blocks, or a tie, keep the first (LOCAL-722 back-compat, 18/18 still pass).

---

## Proof — cloud parity + independent audit

`run_cloud_parity_proof_883.py` + `docker-compose.local883-proof.yml` (own DB on
`:55983`, D753; never the shared `audioura-*` containers). SHORT typed names →
the orchestrator quick path → the wave-40 pins; cache **seeded with the subscribed
base `a831ba0c`**, then a COLD run, then the PASS-checked WARM run on this branch.
After the warm run, **ONE independent `gpt-4.1` call** (not mini) audits the full
warm text against every stop's evidence and lists each unsupported factual claim.

**WARM — all cloud-parity criteria PASS** (`submission_artifacts/local883/saigon_warm.txt`):

```
[PASS] 10/10 stops delivered
[PASS] every stop ≥ 5 content sentences
[PASS] no banned wave-40 strings
[PASS] Palace states 30 April 1975 tank event
[PASS] Diệm named in full (Ngô Đình Diệm)
[PASS] City Hall is the Hôtel de Ville (1898-1909), not Gia Long Palace
[PASS] Post Office credited Foulhoux/Vildieu, Eiffel only as myth/earlier
[PASS] Opera House does not credit Ferret alone
[PASS] Stop 1 Directions is a real next-stop direction
```

**INDEPENDENT gpt-4.1 AUDIT — 0 unsupported claims → PASS**
(`submission_artifacts/local883/saigon_warm_audit.json`: `"unsupported": []`,
`"_model": "gpt-4.1"`).

Also verified in the warm text:
- Thi Bar stays a **Gay bar at 224 Đề Thám** (no canonical leak);
- City Hall is the **Hôtel de Ville → People's Committee** (no Gia Long, no 1945);
- no Pier evacuation; no Eiffel on the current Post Office;
- every stop ≥ 5 content sentences; the earlier banned strings stay absent.

`=== LOCAL-883 PASS === (meter $0.2575 of $0.50)`

---

## Tests

`tests/test_local883_strict_grounding.py` — 21 tests (factual cue floor; gate
keep/drop/disclose; tour-level gate + shortfall rebuild + cost cap; the four
wave-41 resolver leaks + distinctive/category/places/user-link acceptance; the
orphan "is long"; the dangling "Continue to X"; the cache-revalidate log line).

Full offline regression: **234 passed, 3 skipped** across the 883 / 882 / 882b /
882-landmark-own-event / 867 / 881 / 873c / 880 / 880c / 880-signature / d523 /
722 / 650 / 646 / 660 suites. No regressions.

## Files

- `strict_grounding_gate.py` (new) — the gate.
- `tests/test_local883_strict_grounding.py` (new) — the tests.
- `run_cloud_parity_proof_883.py`, `docker-compose.local883-proof.yml` (new) — the
  proof harness + independent audit + isolated DB.
- `generate_tour_text.py` — wired the gate in.
- `venue_canonical_resolver.py` — distinctive-token / category-P31 acceptance.
- `itinerary_import.py` — passes the user's link to the resolver.
- `spoken_text_hygiene.py` — orphan "is long".
- `walking_directions_guard.py` — dangling "Continue to X".
- `landmark_wikipedia_evidence.py` — cache-revalidate log line.
- `stop_title_dedup.py` — keep the richer block on a title collision.

Artifacts under `submission_artifacts/local883/`: `saigon_seed_base.txt`,
`saigon_cold.txt`, `saigon_warm.txt`, `saigon_warm_audit.json`. Run/meter logs are
**not** committed.
