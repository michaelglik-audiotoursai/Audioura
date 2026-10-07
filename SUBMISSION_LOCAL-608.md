# SUBMISSION — LOCAL-608: backport today's listener-facing release fixes to `storied`

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-608-storied-backport` (created from `storied` @ `354da34`)
**Base:** `storied` = `354da34` — verified `git merge-base --is-ancestor 354da34 HEAD` → exit 0.
**No GCloud deploy. No DELETE.** (LEAD files the ClickUp deploy task after review.)

GCloud runs `storied`. Four listener-facing defects Michael hit today are fixed only
on `subscribed`; each is backported here with the smallest diff that applies to
storied's code, one commit per item, each with a test red on `354da34` and green
after.

## Commits (one per item)

```
0dd1c46 LOCAL-608 (D617 item 10): 'check the website' at most once tour-wide
3b44a38 LOCAL-608 (G4): corrective action for ungrounded prolog/epilog sentences
a480273 LOCAL-608 (D612 r3): judge venue coherence by stop address in contained tours
86fd97c LOCAL-608 (D617): strip URLs/Sources from spoken text in the live packer
```

`git rev-list --count 354da34..HEAD` = **5** (4 fixes + this submission).

---

## Item 1 — D617: URLs / "Sources" block read aloud (`86fd97c`)

**Defect.** The LIVE packer `tour_generation_modernized.parse_tour_content_to_modernized`
writes each stop's spoken `audio_N.txt` **verbatim**, so the venue's own-page URLs
and the trailing `Sources (the museum's own pages):` block were read aloud by TTS.
LOCAL-602 r2 had put the strip in `break_text_to_pois.py`, which the live path never
calls.

**Backport of subscribed `2b5706c`:**
- `spoken_text_hygiene.py`: ported `strip_sources_and_urls` + `SOURCES_HEADING_RE` +
  `URL_RE` (+ the orphan-line tidy regex), and exported them in `__all__`.
  *(Did NOT port `strip_degenerate_from_to_recap` — that is D617 item 12, out of scope.)*
- `tour_generation_modernized.py`: call `strip_sources_and_urls` on each stop's text
  inside the packer, logging `[D617] stop N: stripped {...}`.
- `Dockerfile.modernized`: `COPY spoken_text_hygiene.py /app/` so the live container
  has the module.

**Test** `test_local608_d617_no_urls_spoken.py` — 4 tests. RED on `354da34`
(`strip_sources_and_urls` absent; packer leaves URL/Sources in). GREEN after.

---

## Item 2 — D612 r3: venue coherence judged by address, not prose (`a480273`)

**Defect.** Check 11 (venue coherence) counted a stop as "drifted" whenever its prose
named another museum. In an **address-contained** tour (all stops at the venue's own
address), provenance mentions ("lent by the Prado", "catalogued at the Uffizi") are
not drift — the stop *is* at the venue. **Harvard Art Museums was refused 4/6** on
exactly those provenance mentions.

**Backport of subscribed `5943569`** (`content_qa_runner.py`, check 11): a stop whose
own `Address:` matches the tour's address set is exempt from the foreign-venue drift
count, in a contained tour.

**Test** `test_local608_d612r3_contained_provenance.py` — 2 tests.
- A contained Harvard-style tour whose stops name Rijksmuseum / Prado / Uffizi /
  Hermitage / Rodin (4/6 drift — Harvard's exact refusal; names chosen to share no
  words with "Harvard Art Museums") → **FAIL on `354da34`, PASS after**.
- Guard: a non-contained tour (different addresses) with majority foreign venue
  mentions still FAILS, before and after.

---

## Item 3 — G4 corrective action (`3b44a38`)

**Defect.** When the only factual failure was G4 — specific prolog/epilog orientation
sentences that trace to no story element — the whole tour was discarded, even though
its stops were sound. And Stop 1's **sourced** opening section (built from the venue's
own pages / Wikipedia) was not counted as an element, so a legitimate restatement
("from Devlin Hall to Brighton") failed G4 on every McMullen reuse.

**Backport of subscribed `ba5afb9` + `2649a3e`:**
- `content_qa_runner.py`:
  - Stop 1's opening-section paragraphs now count as elements a prolog claim may
    trace to (`ba5afb9`). Fabrications that appear in neither the elements nor the
    opening section still fail.
  - Expose module-level `G4_UNGROUNDED_SENTENCES` — the **full text** of each
    ungrounded prolog/epilog sentence (`2649a3e`), appended at all three ungrounded
    branches (no matched element / proper-noun miss / causal-verb miss).
- `generate_tour_text_service.py`:
  - When the ONLY factual failure is G4 and every recorded sentence is still present,
    **remove just those sentences and re-run QA** (LOCAL-423 rule) instead of
    discarding the tour.
  - **Write the corrected text back** to the delivered temp file, so what passed QA
    is what the listener gets.
  - **Save rejected texts to `tours/qa_failed/`** before discarding (spec item 4),
    best-effort and non-fatal.

**Test** `test_local608_g4_corrective.py` — 3 tests. RED on `354da34`
(`G4_UNGROUNDED_SENTENCES` is `AttributeError`; the Devlin-Hall prolog claim FAILS
G4). GREEN after. The two mechanisms the service's corrective loop relies on are
asserted directly: (a) the opening section grounds the restated claim; (b) a genuinely
fabricated claim is recorded verbatim in `G4_UNGROUNDED_SENTENCES` (so
`tour_text.replace(sentence, '')` works). The service wiring itself is additionally
exercised by the live run.

---

## Item 4 — "check the website" at most once; "Admission is free." (`0dd1c46`)

### 4a — "check the website" at most once, tour-wide — PORTED (`78e36e2`)

**Defect.** Hours/admission are spoken when the venue publishes them; when a field is
unpublished the tour points at the venue site, but that pointer must appear **at most
once** across the whole tour. On the overview path the overview narration and the
Stop-1 opening section can each emit one, so a 1-stop overview said it twice.

**Backport of subscribed `78e36e2`:**
- `practical_facts_gate.py`: ported `collapse_website_pointers` +
  `is_website_pointer_sentence` + `_WEBSITE_POINTER_SENT_RE` (keep the FIRST pointer,
  drop later duplicates; a sentence that also states a real fact never matches and is
  left alone).
- `generate_tour_text.py`: collapse on the overview return (`_assemble_overview_tour_text`)
  and on the assembled `complete_tour`, right after the D523 spoken-text hygiene pass.

**Test** `tests/test_local602_r2_check_website_once.py` — 7 tests (ported verbatim;
exercises `practical_facts_gate` only, so fully portable). RED on `354da34` (functions
absent). GREEN after.

### 4b — "Admission is free." wording — NOT PORTABLE (`8673fc8`)

Subscribed `8673fc8` fixes `about_museum_stop._compose_admission_sentence` so a noun
phrase from the source ("Free admission (…)") is spoken as "Admission is free."
rather than "Admission is Free admission (…)".

**This cannot be ported to storied:** `about_museum_stop.py` **does not exist** on
`storied` and is referenced nowhere in the tree. The "Admission is {body}" composition
the fix targets has no code path here — storied's overview builds its practical
sentence in `museum_overview._verified_facts_line`, which keeps the verified admission
text **verbatim** under `According to the museum's website (<domain>, <as_of>): …`,
never re-labelling it "Admission is …". So the specific "Admission is Free admission (…)"
defect `8673fc8` repairs does not occur on storied. Per the ticket's instruction
("where a subscribed fix depends on a subscribed-only module, adapt it or say clearly
in the submission that it can't be ported"), it is documented here rather than forced.

---

## Re-run of the required storied test suites

Clean tree at HEAD (`0dd1c46`). Scripts run with `python3 <file>`; pytest files with
`python3 -m pytest`. (`test_sq4_merge.py`, `test_palais_fix_lead_fixture.py` and
`test_g4_false_positives.py` self-exit at import — they are standalone scripts, not
pytest modules — so they are run as scripts.)

| Suite | Result | Exit |
|---|---|---|
| `test_sq4_merge.py` (script) | ALL TESTS PASSED | 0 |
| `test_palais_fix_lead_fixture.py` (script) | All tests passed (23/23) | 0 |
| `tests/test_local593_*` (5 files) | 30 passed | 0 |
| `test_g4_false_positives.py` (script) | ALL PASS (incl. G4 fail-closed scoping) | 0 |
| `test_local40_explain_what_you_name.py` | 13 passed | 0 |
| `tests/test_local36_practical_facts_qa.py` | 26 passed | 0 |
| `tests/test_local85_venue_coherence.py` | 2 failed, 6 passed | **1** |
| **New** `test_local608_d617_no_urls_spoken.py` | 4 passed | 0 |
| **New** `test_local608_d612r3_contained_provenance.py` | 2 passed | 0 |
| **New** `test_local608_g4_corrective.py` | 3 passed | 0 |
| **New** `tests/test_local602_r2_check_website_once.py` | 7 passed | 0 |

### The two `test_local85` failures are the intended effect of D612 r3 — and identical on `subscribed`

`tests/test_local85_venue_coherence.py::TestVenueCoherenceFail::test_majority_stops_reference_wrong_museum`
and `::test_all_stops_reference_different_museum` fail after this backport.

This is **not a backport error.** The test helper `_make_museum_tour` gives **every
stop the same `Address: 123 Rue Test, Nice`**, which D612 r3 now (correctly) treats as
an address-contained tour, so the intentional "drift" the two tests inject is exempted
and the expected FAIL no longer fires. Verified faithful to `subscribed`:

- `git show subscribed:content_qa_runner.py` run against these two tests **fails them
  identically** (same assertion, same two tests).
- `subscribed` never modified `tests/test_local85_venue_coherence.py` — it is unchanged
  since `e774697`, and uses the same shared address fixture.

So the D612 r3 behavior change makes these two stale-fixture tests a known casualty on
**both** branches; the backport reproduces subscribed exactly. (Updating the
`test_local85` fixtures to use distinct per-stop addresses would be a separate test-fix
ticket, not part of this backport's "smallest diff that applies" mandate.)

---

## Live isolated container run (built from this branch only)

**Harvard Art Museums, Cambridge, MA — museum — 7 stops — hard cap $1.50.**

Launched a throwaway container that mounts THIS worktree over `/app` (so this branch's
code runs), reusing the `audioura-tour-generator` image for its baked dependencies and
the `development_default` network for DB/service access; env injected via `--env-file`
from `audioura-tour-generator-1` (DATABASE_URL → postgres-2, keys), plus the acceptance
switches:

```
docker run --rm --name local608-gen \
  --network development_default \
  --env-file <redacted env of audioura-tour-generator-1> \
  -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e COST_HARD_LIMIT_USD=1.50 \
  -v <worktree>:/app -w /app \
  audioura-tour-generator \
  python3 run_local608_container.py
```

**Isolation — no `audioura-*` container was touched, renamed or rebuilt:**
`audioura-tour-generator-1` was `running healthy` **before and after**; `local608-gen`
was `--rm` and auto-removed; the temp env-file (secrets) was deleted after the run.

### Result

```
OUTCOME: TOUR DELIVERED — 19558 chars, 7 stops
   Stop 1: The Infant Bacchus Entrusted to the Nymphs of Nysa; The Death of Echo and Narcissus
   Stop 2: Jeanne-Antoinette Poisson, Marquise de Pompadour
   Stop 3: At the Milliner's
   Stop 4: Augustine-Modeste-Hortense Reiset
   Stop 5: Grazing Horses IV
   Stop 6: The Chimera
   Stop 7: A Sea-Spell
```

**BLOCKER 3 lines** (content-QA factual gate, re-run on the delivered text):
```
BLOCKER 3 line 1 — PASS checks:          15
BLOCKER 3 line 2 — style FAIL checks:    5
BLOCKER 3 line 3 — FACTUAL FAIL checks:  1
```
The FACTUAL=1 is G4 **fail-closed**: this acceptance harness re-runs BLOCKER 3 on the
finished text *without* passing in-memory `story_elements` (the same pattern as the
existing `run_local593_container.py`), so G4 fails closed — it is not a factual error
in the delivered tour.

**G4 corrective lines:**
```
(none — no ungrounded prolog/epilog sentence needed removing this run)
```
No prolog/epilog sentence was ungrounded this run, so the corrective action had nothing
to remove. **Note on coverage:** the service-level corrective loop + write-back live in
`generate_tour_text_service.generate_tour_async`; this direct-`generate_tour_text`
harness (like `run_local593_container.py`) does not drive that service path, so the
corrective lines are exercised by `test_local608_g4_corrective.py` rather than by this
live run.

**D617 — no `http` / `www.` / `Sources` block in the spoken `audio_*.txt`:**
The modernized parser produced 7 spoken files; the strip fired on stop 7:
```
[D617] stop 7: stripped {'urls': 0, 'sources_blocks': 1} from spoken text
```
Precise grep over the 7 spoken `audio_*.txt`:
```
URLs  (https?://|www\.)                 : 0
'Sources:'/'Source:' heading or block   : 0   (grep ^[ \t]*[Ss]ources?[ \t]*[:(] → no match)
```
The Sources block the generator folds after the last stop was removed before it could
be spoken; the only remaining lowercase word "sources" is ordinary prose ("classical
sources described only in fragments"), not a URL or a Sources block.

**Tour total:**
```
Tour total: $0.9919  cache_hit=False  wall_time=1458.5s
```
Under the $1.50 cap.

The acceptance harness `run_local608_container.py` is committed with this submission.

---

## Files changed

| File | Item |
|---|---|
| `spoken_text_hygiene.py` | D617 strip + regexes |
| `tour_generation_modernized.py` | D617 packer call |
| `Dockerfile.modernized` | D617 COPY line |
| `content_qa_runner.py` | D612 r3 + G4 (opening-section elements, `G4_UNGROUNDED_SENTENCES`) |
| `generate_tour_text_service.py` | G4 corrective loop + write-back + `tours/qa_failed/` |
| `practical_facts_gate.py` | website-pointer collapse |
| `generate_tour_text.py` | website-pointer collapse call sites |
| `test_local608_d617_no_urls_spoken.py` | new test |
| `test_local608_d612r3_contained_provenance.py` | new test |
| `test_local608_g4_corrective.py` | new test |
| `tests/test_local602_r2_check_website_once.py` | ported test |
| `run_local608_container.py` | live acceptance harness |
| `SUBMISSION_LOCAL-608.md` | this document |

Not edited (per PROCESS): `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
`.continuous_dev/STATUS.md`.
