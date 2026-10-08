# SUBMISSION — LOCAL-629

**An art museum's stops are its ARTWORKS (not events in its halls), artists vary,
and the conclusion never re-tells a stop.**

Branch: `LOCAL-629-selection-diversity` (from `subscribed` @ `384eab8`).
Base check: `git merge-base --is-ancestor 384eab8 HEAD` → exit 0.

---

## What was wrong (from the evidence)

- **Belvedere, tour 492 (Kiro 3/10):** all three stops were "the Austrian State
  Treaty was signed in this hall" — diplomatic EVENTS. They reach the tour
  because Wikidata **P276 ("location")** returns an event whose location is the
  venue, and the deterministic selector trusts a `sparql_confirmed` row as a
  *work* without ever asking **what KIND** of thing it is. LOCAL-626 stops the
  VENUE becoming a stop and LOCAL-625 stops a ROOM, but an event, a room of state
  or the building still slipped through.
- **Uffizi, tour 489:** 3 of 3 stops were Leonardo — the signature-first sort
  piled the single most-prominent artist into every slot.
- **Van Gogh Museum, tour 491 (Kiro 6.5):** the conclusion re-told Stop 1 and
  added a "discovered in 2013" factoid; the hours were never spoken. Trace of the
  LOCAL-628 one-shot run of the same venue (`local628_vangogh_run.log`) shows the
  cause for hours: the request arrived as `tour_type='walking'` (category was
  forced to `museum` only later, inside the impl), so the wrapper's preflight gate
  — which fired only for `tour_type=='museum'` — was **skipped** (`preflight
  calls:0`), and the famous museum's hours were never fetched.

---

## Item 1 — Artworks only, for art museums

New pure module **`artwork_selection_guard.py`**:

- `is_artwork_instance(P31)` / `is_nonartwork_instance(P31)` — Wikidata
  instance-of QID sets. Artwork classes (painting Q3305213, sculpture Q860861,
  drawing, print, work of art, statue, fresco, decorative-arts object, …) vs
  non-artwork classes (**peace treaty Q625298**, treaty, signing/coronation,
  battle, conference; **building Q41176, architectural structure, palace Q16560,
  façade; room Q180516, hall**).
- `looks_like_event_title(title)` — multilingual (EN/DE/FR/IT/ES) fallback for
  when P31 is absent: "…treaty", "signing of…", "Staatsvertrag",
  "Signing of the Austrian State Treaty", plus building/façade/staircase titles.
- `work_has_creator(entry)` — P170 creator / `creators` list / "attributed to…".
- `enforce_artworks_only(works, venue, is_art_museum)` → `(kept, dropped)`:
  rejects a known non-artwork P31 whatever the label says; rejects an
  event/architecture title; rejects rooms and the venue itself (reusing
  `room_candidate_guard`); and requires every surviving art-museum stop to be a
  Wikidata **work with a creator/attribution** (an entry with no artwork P31
  **and** no creator is dropped). Each dropped entry carries a `_reject_reason`.

Wired into `generate_tour_text.py` (`_apply_artwork_guards`, called on the
deterministic documented-works list AFTER the prominence sort and BEFORE
truncation, at both museum selection sites). SPARQL `_det_documented` entries now
carry `instance_of` / `creator` / `creator_qid`. `venue_resolver`
`build_canonical_titles_from_works` also drops non-artwork P31 classes and event
titles, so the R4/canonical paths are covered. Rejected candidates are replaced
from the rest of the catalogue (the guard runs before the `*2` take, so the next
real works fill the freed slots).

### Belvedere candidate list, before → after (LIVE, tour 494)

The deterministic set after the guards (43 varied artworks) **led with**
`The Kiss` (Klimt), `Madonna del Prato` (Raphael), `Death and the Maiden`
(Schiele) — the signature works, no treaty, no Marble Hall, no building. On the
**Orangerie** live run the guard logged the before/after explicitly:

```
[LOCAL-629] candidate works BEFORE artworks-only (172): [... 'Claude Monet. Exposition
  rétrospective', 'Manet', 'Richard Jackson, Wall Painting', '26e exposition canine de
  Paris', ...]
[LOCAL-629] artworks-only dropped 39: [('26e exposition canine de Paris',
  'no_artwork_class_and_no_creator'), ('Claude Monet. Exposition rétrospective', ...),
  ('Manet', ...), ('Richard Jackson, Wall Painting', ...), ... ]  (exhibitions / events)
[LOCAL-629] candidate works AFTER guards (14): ['Portrait de Madame Cézanne', 'Antonia',
  'Red Boats at Argenteuil', ...]   # 14 works across 14 different artists
```

(Unit test exercises the exact Belvedere list including the Austrian State Treaty
`P31=Q625298`, the Marble Hall `P31=Q180516`, and the Upper Belvedere
`P31=Q16560` — all dropped; the four artworks kept.)

---

## Item 2 — Artist variety

`cap_artist_variety(works, n_stops)` — at most **ceil(n/3)** works by any one
artist (3 stops → 1 each → three different artists; 6 stops → ≤2 each). It runs on
the already-ranked list, so **signature-first still decides which work of a given
artist leads** (the top Leonardo keeps its slot; the extra Leonardos are the ones
dropped). A one-/few-artist venue is detected (`distinct_artists == 1` or
`distinct_artists * cap < n_stops`) and left untouched, so a Van Gogh / Matisse
house museum is never stranded.

Live: the Orangerie's 119 variety-cap drops left **14 works across 14 artists**;
the Belvedere and Orangerie delivered tours each used **three different artists**.

---

## Item 3 — The conclusion never re-tells a stop

The LLM thematic-conclusion validator (`tour_conclusion._thematic_draft_ok`) only
checked that claims were *supported* by the delivered text — but a re-told stop
fact IS in that text, so a re-narrating draft passed (the Van Gogh "discovered in
2013" case). Added **`_conclusion_renarrates_stop(draft)`**: a deterministic
detector that fails a draft carrying a stop-body fact — a 4-digit year or month
date, a measurement/dimension (`55.5 cm`, `oil on canvas`), an inventory/catalogue
number (`F 370`, `s0017V1962`), or an event factoid bound to a year
(`unveiled … in 2013`). Wired into `_thematic_draft_ok`, so a re-narrating draft
is rejected and the deterministic **thematic** template (thread + meaning + at
most one NAMED example) ships. The single example may be NAMED, never
re-narrated — Michael's rule: the conclusion is about the theme and the common
elements.

Live conclusions (both thematic, no re-narration):
- Belvedere: *"Together, these stops explore the interplay of life, death, and the
  natural world through the lens of different artistic expressions…"*
- Orangerie: *"This tour highlights the influence of Monet's water garden,
  illustrating how his exploration of light and atmosphere resonates through the
  works of other artists…"*

---

## Item 4 — Hours for the Van Gogh Museum

**Trace:** the wrapper's LOCAL-603 preflight gate fired only when
`tour_type == 'museum'`. Van Gogh arrived as `walking` (category forced to museum
later), so the preflight was skipped (`calls:0`) and the hours were never fetched;
then the "hours not spoken" guard said nothing because the preflight had not
confirmed them unpublished.

**Fix (two parts):**
1. **Run the preflight for any single-venue request** — museum `tour_type` OR a
   location whose first segment carries a venue word
   (`_preflight_venue_from_location`). The Belvedere/Orangerie live runs confirm
   it now fires: `[LOCAL-603] preflight venue='Belvedere Museum' status=open
   hours=y admission=y`.
2. **Actually SPEAK the known hours.** The live run surfaced the deeper gap: the
   hours were KNOWN (preflight + site both returned `Tuesday to Sunday, 11 AM–6
   PM; €65`) but landed only in a non-spoken **`Museum Information:` field line**,
   which the audio and the critique strip — so nothing was spoken.
   `practical_facts_gate.ensure_spoken_hours_line(text, hours, admission)` injects
   a real spoken sentence into the Stop-1 opening when the hours are known but the
   PROSE speaks none; `tour_speaks_hours_in_prose` first strips field lines so a
   time inside a field label no longer counts as spoken. Wired into the every-path
   delivery guard, fed from the grounded preflight (daily/closed-day reconciled).
   When hours are genuinely unknown, nothing is said (LOCAL-627); a museum this
   famous now speaks them.

---

## Item 5 — Tests (one per item, on real candidate lists)

New: **`test_local629_selection_diversity.py`** — item 1 on the real Belvedere
list (treaty + hall + building dropped, four artworks kept); item 2 on the real
Uffizi list (ceil(3/3)=1 → Botticelli/Leonardo/Titian, signature-first keeps the
leading Leonardo; 6-stop caps at 2 each; single-artist Van Gogh venue not
stranded); item 3 (re-narrating drafts rejected, thematic accepted, deterministic
rebuild is itself thematic); item 4 (published hours spoken even when only in a
field line; honest line only when the preflight confirms unpublished; no false
claim otherwise).

### Re-run of the named suites (exit codes)

| Suite | Result | Exit |
|---|---|---|
| `tests/test_local60* 61* 62*` | 378 passed | **0** |
| `test_local62[0-8]*` + `tests/test_lead_double_conclusion.py` | 149 passed | **0** |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | **0** |
| `test_local629_selection_diversity.py` | 13 passed | **0** |

---

## Item 6 — Live (own container, cache + pool OFF, STOP_EDITOR=1, HARD CAP $1.50)

Own container: `docker run --rm --name local629-gen -p 5099:5099 --network
development_default -v <worktree>:/app …` (branch code mounted at `/app`), DB
`postgres-2:5432` (`development-postgres-2-1`), **tour cache OFF
(`DISABLE_TOUR_CACHE=1`), stop pool OFF (`DISABLE_STOP_POOL=1`),
`STOP_EDITOR=1`**. No `audioura-*` container was built, renamed, replaced or
touched. Rows: additive `is_test=true` only; **no DELETE**. HARD CAP $1.50 with
the reserve gate (`spend + $0.90 ≤ $1.50`).

**audio_tours row count: 298 → 300** (additive; two `is_test` rows 493, 494).

### Musée de l'Orangerie, Paris (never generated) — tour 493, DELIVERED
- Stops (three different artists, all artworks): **Portrait de Madame Cézanne**
  (Cézanne) · **Antonia** (Modigliani) · **Red Boats at Argenteuil** (Monet).
- 172 candidates → guard dropped 39 non-artworks (exhibition/event titles) and
  variety-capped 119 → 14 works across 14 artists.
- Conclusion: thematic (Monet's water garden influence), no re-narration.
- `critique.sh 493 3` → **Kiro 6.5/10** (`submission_artifacts/local629/critique_493.md`).
- Cost: tour total **$0.67** (metered).

### Belvedere Museum, Vienna — tour 494, DELIVERED
- Stops (three different artists, all artworks; no treaty / room / building):
  **Madonna del Prato** (Raphael) · **Death and the Maiden** (Egon Schiele) ·
  **The Plain of Auvers** (Van Gogh).
- Preflight ran: `status=open hours=y admission=y`; admission verified from
  `belvedere.at` in the practical-facts audit.
- Conclusion: thematic (life / death / nature), no re-narration.
- `critique.sh 494 3` → **Kiro 6.5/10** (`submission_artifacts/local629/critique_494.md`).
- Cost: tour total **$0.76** (metered). Combined ≈ **$1.44 < $1.50 cap**.

The first Belvedere attempt (bare `"Belvedere, Vienna, Austria"`) resolved to
`scope_precision='CITY'` with **no venue_name**, took Phase 3A (which returned the
palace buildings), and BLOCKER4b correctly refused the scattered city-wide result
(no tour, $0.016). Re-running with the resolvable `"Belvedere Museum, Vienna"`
engaged the deterministic museum path and the LOCAL-629 guards.

**Target Kiro ≥ 7 — honestly NOT reached live (both 6.5):** the critiques confirm
the LOCAL-629 fixes landed — both tours are **work-and-artist led, with varied
artists and a real thematic conclusion** (no event/room/building stop, no
single-artist monotony, no re-narrated stop). Both are held at 6.5 by defects
**outside LOCAL-629's scope**: cross-stop theme repetition and dry
accession/exhibition filler (criteria 1, 2), and — the one in-scope item — the
Belvedere critique's "no hours/admission spoken" (criterion 3, High). That hours
gap was traced to the known hours living only in a non-spoken field line and is
**fixed after the live runs** (`ensure_spoken_hours_line`, unit-tested); re-running
to re-confirm Kiro ≥ 7 would be a 3rd/4th live tour and would breach both the
"at most 2 tours" instruction and the $1.50 cap, so it is reported honestly rather
than breaching the gate.

---

## Files

- `artwork_selection_guard.py` — NEW: items 1 & 2 (pure, unit-tested).
- `generate_tour_text.py` — `_is_art_museum`, `_apply_artwork_guards`; SPARQL det
  entries carry class/creator; widened preflight gate; spoken-hours injection.
- `venue_resolver.py` — canonical-title builder drops non-artwork P31 / event
  titles.
- `tour_conclusion.py` — `_conclusion_renarrates_stop` (item 3).
- `practical_facts_gate.py` — `ensure_spoken_hours_line` /
  `tour_speaks_hours_in_prose` (item 4).
- `test_local629_selection_diversity.py` — NEW: one test per item (13 tests).
- `run_local629_container.py` — NEW: isolated live runner.
- `submission_artifacts/local629/` — critiques + spoken-text of tours 493, 494.
