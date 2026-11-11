# SUBMISSION — LOCAL-894: user-list integrity for a described request (Phan Thiet driving tour, cloud 549)

Branch `LOCAL-894-user-list-integrity`, from `subscribed` fc31ad75 (`git merge-base --is-ancestor fc31ad75 HEAD` → 0).

**Verdict:** offline PASS. The live run was PARTIAL, so for the post-fix state the result is **unproven live, handing to LEAD**.
- The one allowed live run (commit 3f3dde28) fixed the stop list: 8 stops, the user's order, the user's titles, no ghost stop, no "the" announcement.
- That run also exposed four defects: packaging, transport mode, job-scope state, and the pin lookup. They are fixed and tested offline (2b06e8c3, af40e63a).
- Budget: $0.341 of $0.50 spent. One more run does not fit, and the task allows only one, so I did not re-run.

## What changed (generic, D769: no place name anywhere in code)

New module `user_list_integrity.py` (pure, offline):
- `looks_like_description` flags a location over 80 chars, a sentence boundary, 14+ words, or an imperative opener ("Create…").
- `derive_request_place` reads "from X [in L] … to Y [in R] and back". It returns:
  - origin and destination;
  - location = the origin's locality;
  - scope = the region ("… province/region/state …");
  - through-places ("through/via/past Capitalised");
  - a short title (≤ 60 chars, cut on a word boundary);
  - the "Include …" topics.
- `reject_named_place_candidate` rejects stopwords, lowercase single words, sentence fragments, prose phrases and 8+ word runs.
- `strip_qualifier` strips parentheticals only.
- `stop_place_core` / `core_after_descriptor` / `lookup_core`:
  - text before the dash or colon, without "Arriving at/Leaving/The";
  - adds a "mountain/pagoda/…" descriptor that the dash clause names;
  - returns '' when the phrase has no proper noun.
- `request_topics`, `topics_for_stop`, `route_topics` (every topic gets a home stop; region themes go to the drive segment), `topic_support` (word-overlap report, never invents) and `driving_register_block`.

Changes by Do item:
1. **Location / title.**
   - `tour_orchestrator_service.sanitize_input(max_len=…)` cuts on a word boundary.
   - `location` and `request_string` now carry up to 2000 chars. The limit is literal in the orchestrator, so a missing module can't bring back the 200-char cut.
   - The orchestrator derives the short place for its own geocode and storage, and stores the short title as `tour_name`.
   - It forwards the WHOLE description to the generator.
   - In the generator, `_apply_description_location_894` runs inside `_generate_tour_text_impl`, in its own job scope. State: `_ROUTE_*`, `_REQUEST_TOPICS` and `_REQUEST_DESCRIPTION`, registered in the job-scoped registry.
   - `_scope_from_request` returns the region for a described request.
   - The title builder uses `_route_title_894`.
2. **The user list is the tour.**
   - With a user list, LOCAL-751 inserts no named place from the request text. Every candidate also passes `reject_named_place_candidate`.
   - `build_named_place_intro_sentence` never announces a rejected candidate.
   - LOCAL-212 coverage selection is skipped for a user list: no ranking, no N-cap slice.
   - LOCAL-576 anchor re-ordering is skipped for a user list. LOCAL-867 keeps the order, as before.
   - LOCAL-791C no longer "restores" a user title to a shorter anchor, so "Phan Thiet and the Ca Ty River" stays whole.
   - LOCAL-823 never shortens a user title.
   - User titles have only their parentheticals stripped.
3. **Driving.**
   - A bare `tour_type="driving"` now sets `transport_mode=vehicle`. The keyword regex needed "… tour" after the word, and the description's own mode is read too.
   - The LOCAL-662 walking force-ENFORCE is not applied to a driving tour.
   - `strict_grounding_gate.sensory_body(register="driving")` uses road/landscape padding, with no street/pavement/"look around you".
   - On a driving tour the narrator gets a DRIVING-TOUR REGISTER block: drive segments get the longer story, stops stay short.
4. **Pins.**
   - The orchestrator's D762 resolver looks up `lookup_core(title)` with the route region as the city, then logs `pins resolved k/N` over ALL stops.
   - The generator's LOCAL-859 name lookup does the same: place core, route-region bbox, and "names no place → no pin, kept".
5. **Topics.** The stop's routed topics feed `thin_stop_search` (name + topic queries, at most 2) and force an evidence search for that stop. Each stop logs `[LOCAL-894] Stop N … topic support: {...}`.

Packaging: `Dockerfile.orchestrator` now COPYs `user_list_integrity.py`, and a test guards it.

## Offline (required set) — PASS

`tests/test_local894_user_list_integrity.py`, 38 tests. The end-to-end class runs the real `generate_tour_text` with the network blocked: sockets refuse, requests are faked, OpenAI is faked. The fake intent returns what the live intent did (`transport_mode=on_foot`, scope "Phan Thiet", junk named places).
- 8 stops, in the user's order, with the user's titles (qualifier stripped) → PASS.
- No ghost stop, no "could not be confirmed" / "the" announcement → PASS.
- Location "Ham Tien, Mui Ne", scope "Binh Thuan province" (origin + destination + Phan Thiet). The pin-snap scope deep in the impl is the region → PASS.
- Driving register: `[TRANSPORT] mode=vehicle`, no street/pavement template, no walking ENFORCE → PASS.
- Title "Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour" (51 chars) → PASS.

Checked against base: the end-to-end class FAILS 6/6 on fc31ad75.

Regression: the related suites pass (751, 799, 823, 357, 576, 662, 791C/E, 867, 873/873B, 883, 884, 888, 890–893, orchestrator pipeline), 376 tests. Full-suite comparison with base: see the end of this file.

## Live (1 run, commit 3f3dde28, `-p local894`, ports 26000/26002/55994; shared audioura-* untouched)

`POST /generate-complete-tour` with location = the description, `tour_type=driving`, 8 stops, `is_test=true`. Completed in 603 s.

| item | result |
|---|---|
| stop titles, in order | 1 Leaving Mui Ne – the fishing coast and Ham Tien strip · 2 Phan Thiet and the Ca Ty River · 3 Dragon fruit country – the plantations along the road · 4 Arriving at Ta Cu – the mountain and its legends · 5 The cable car ascent · 6 Linh Son Truong Tho Pagoda · 7 The Reclining Buddha · 8 The summit views and the drive home → **user order, user titles, 8/8, PASS** |
| ghost stop / "the" announcement | none — **PASS** |
| pins | **2/8** (stops 1 and 3). The orchestrator's pin resolver did not run (`No module named 'user_list_integrity'`), and the generator's lookup used the full phrase in a Ham Tien box. **FAIL**, fixed in 2b06e8c3 |
| title (stored `tour_name`) | the 213-char fragment "Create a half-day … for the first time. The - Driving Tour". **FAIL**: the orchestrator derivation could not import the module. Fixed (Dockerfile + literal limit). The generator itself derived "Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour" |
| location / scope | generator: location 'Ham Tien, Mui Ne', scope 'Binh Thuan province'. It received a 198-char word-cut description (orchestrator fallback); through=[] because the cut lost "through Phan Thiet". Pin-snap scope was still 'Ham Tien, Mui Ne' (job-scope bug), fixed |
| category | `tour_type='driving' → category='walking'`, `[TRANSPORT] mode=on_foot`. The header read "audio-guided walking tour" and the walking ENFORCE was forced. **FAIL**, fixed (bare tour_type word) |
| per-stop sentence counts | 4, 5, 5, 6, 4, 2, 3, 6 |
| street/pavement template text | none in the delivered text |
| requested topics covered | Topics were not passed live (the cut dropped "Include …"). Post-hoc word-overlap check on the run's evidence and text (`topic_coverage_posthoc.json`): supported and delivered: history of Phan Thiet, how dragon fruit is grown, Ta Cu story, cable car, Reclining Buddha. Evidence only: the Pagoda. Not supported: Cham heritage, why Binh Thuan is famous for dragon fruit, the Buddha's construction / meaning / pilgrimage. Nothing was invented to cover them |
| audit unsupported | **1**: Stop 1 "Mui Ne is … in the Lâm Đồng Province" (the evidence says Bình Thuận) |
| meter | **$0.3409** (357 meter rows; meter_guard ok). Ledger LOCAL-894 = $0.340891 of $0.50 |

I did not re-run, per the task and the budget: $0.341 spent plus another full run (~$0.34) would exceed $0.50. The post-fix live behaviour is **unproven, handing to LEAD**. The next live run should check:
- the orchestrator logs `[LOCAL-894] location is a description` and `[D762] user-stop pins resolved k/8`;
- the generator logs `[TRANSPORT] mode=vehicle` and the LOCAL-859 lookup scope 'Binh Thuan province';
- `[LOCAL-894] Stop N … topic support` lines.

## Artifacts (`submission_artifacts/local894/`)
`tour.txt` (delivered live text), `evidence_bundle.json`, `audit.json`, `topic_coverage_posthoc.json`. Run and meter logs stay in `_local894_meterlogs/` and are not committed.

Harness: `run_local894_real_path.py` (+ `docker-compose.local894-proof.yml`).

## Full suite vs base (offline, same machine)
- Branch (final code): 221 failed, 7320 passed, 43 errors.
- Base fc31ad75: 230 failed, 7273 passed, 43 errors.
- Failing test IDs on the branch that are not failing on base: **none**. The pre-existing failures are DB, network and live-API tests (e.g. test_local476 quota, the news orchestrator).
