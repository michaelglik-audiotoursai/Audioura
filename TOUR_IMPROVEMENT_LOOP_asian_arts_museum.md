# Tour Improvement Loop — Asian Arts Museum, Nice, France

Closed-loop quality improvement for one venue, using the scoring rubric agreed with
Michael 2026-07-29. Purpose: give Kiro's fix work a real, repeatable numeric target
instead of one-off bug reports, and give Michael a concrete price-per-quality-point
signal for subscription-tier decisions.

## Rubric (summary — full derivation in chat history / round12-review-state.md memory)

- N = requested stop count, share = 100/N points per stop-slot.
- FABRICATED or MISSING stop-slot (fake nav-label stop, invented artist/artwork with
  no real referent, or a slot never filled at all): **−1.0 × share**.
- THIN/NO-STORY (real referent, generic/boilerplate, no verifiable specific facts):
  **+0.5 × share**.
- ADEQUATE (real referent, some specifics, some generic filler): **+0.75 × share**.
- RICH (real referent, specific, verifiable, distinctive): **+1.0 × share**.
- Structural-defect surcharge (independent axis — template leaks, corrupted fields,
  voice breaks): **−0.25 × share**, capped at **−0.5 × share** per stop.
- Cross-stop correlation bonus (only if genuinely earned — actual callbacks between
  stops, not a templated "you've seen X, Y, Z" wrap-up): **+50%** of affected stops'
  value, can push total >100.
- Venue-identity bonus (genuinely specific venue-level facts — architect, founding
  story — surfaced in the intro when per-stop facts are scarce): up to **+10%** of
  tour total.

## Loop mechanics (agreed with Michael 2026-07-29)

1. LEAD (Claude) evaluates the current tour, identifies concrete defects, dispatches
   a fix task to Mac Mini Kiro.
2. Kiro fixes, live-verifies (must DELETE the exact `tour_cache` row first — same
   cache trap as LOCAL-8/LOCAL-13 — then show CACHE MISS/CACHE STORE), runs the full
   11-suite regression, AND live spot-checks a **second, different venue** to guard
   against overfitting to this one museum. Reports evidence, does NOT self-score.
3. LEAD independently re-scores from the real regenerated text (never trusts Kiro's
   own score) and updates the round table below.
4. Repeat while score < 75.

**Stop conditions:**
- **Plateau:** if the score has not improved by at least **+3 points** vs. 3 rounds
  ago, stop and report to Michael — this overrides continuing even if score is still
  < 75 (noise-tolerant: small round-to-round jitter from LLM stochasticity doesn't
  count as "no improvement" by itself, but 3 rounds flat does).

  **TEMPORARILY SUSPENDED 2026-07-29 ~13:0x, per Michael's explicit request** before
  he left for ~2 hours: "change the rules just for this time and continue running
  the cycle... this will teach me if having 3 rounds of no progress is futile
  enough in case if after 3 rounds of no progress there progress will come." Round
  3 (LOCAL-16) is currently in progress and would be the 3rd data point (0: 15.6,
  1: -9.4, 2: 15.6) — normally a plateau-stop candidate depending on round 3's
  result. Per his instruction, do NOT stop on plateau during this window — keep
  bouncing/redispatching through as many non-improving rounds as needed. Score>=75
  and the cost caps below remain ACTIVE and are still hard stops. Revert to the
  original 3-round rule (or get Michael's updated call) once he's back and checks
  in — do not treat this suspension as permanent.
- **Cost:** stop for Michael's explicit approval before any further round if
  cost-per-tour exceeds **3× the original ($0.0353 × 3 = $0.1059)** OR the absolute
  ceiling of **$0.50/tour** — whichever triggers first (in practice the 3× relative
  trigger binds first).
- Michael may check the current index value at any time; no need to wait for a round
  to finish.

## 2026-07-29 evening — root cause found, loop premise revised

LEAD traced the loop's ceiling to the DATA layer, not the fill logic:

- The venue's verified catalogue holds **6 canonical titles**. The tour asks
  for 8. Two slots can never be filled → -25 before anything else. Even a
  flawless run tops out at **50/100** against a 75 target. Rounds 1-4
  optimised inside a box whose lid was already fixed.
- Every stop logged `No RAG context — cannot generate fact sheet`. Phase 5
  wrote prose with **no source material at all** — the real reason every
  stop scores THIN and invented artists keep appearing.
- `venue_corpus.story_elements_json` was empty for **all 16 venues**. Three
  silent breaks: `corpus_result.get('story_elements')` reads a key
  `story_miner` never emits; `extract_story_elements_from_pages` /
  `persist_story_elements` did not exist (ImportError swallowed by
  try/except); and the real SQ3/SQ4 engine in `story_element_extractor.py`
  had **zero production callers** — only tests and one pilot script. The
  "11/11 suites green" everyone cited included suites exercising dead code.

Dispatched LOCAL-18/19/20 against these. Results:

| Task | Verdict | Outcome |
|---|---|---|
| LOCAL-19 | **APPROVED, merged @ 04e726d** | R4 replenishment confirmed executing live (3 rounds, honest 6/9) instead of `Target reached`. Carries the LOCAL-16 verified-only gate, which had never reached storied. Only branch shipping zero unverified content. |
| LOCAL-18 | BOUNCED → LOCAL-21 | Wired the real engine; story elements 0/16 → 1/16 venues (Chagall, 3 typed). But shipped 4 unverified stops, produced zero elements for this venue, and the QA gate now REJECTS tours once real elements exist. |
| LOCAL-20 | BOUNCED → LOCAL-22 | Fix A (verified stops immune to the 5.5b prose validator) is right but never fired, so unproven. Fix B disproven — title corruption reproduced verbatim, 7th consecutive round. |

Strategic revision: the lever is **corpus and story supply**, not fallback
policing. Reaching 75 on this venue is arithmetically impossible; either
expand the corpus or cap requested stops at what a venue can support.


## Round history

| Round | Date | Score | Cost | $/point | Verdict | Commit |
|---|---|---|---|---|---|---|
| 0 (baseline, LOCAL-9→12 fixes applied) | 2026-07-29 | **+15.6 / 100** | $0.0353 | $0.00226 | 2 fabricated stops (UNIFIED-FILL inventing fictional fill), 1 real regression (stop 4 lost hard facts), 2 structural defects (`[Venue Name]` leak, corrupted address field), 1 voice-break | 7e61c13 |
| 1 (BOUNCED) | 2026-07-29 | **-9.4 / 100** | $0.0436 | n/a (negative) | Kiro claimed 3/4 fixed + honest 7/8 shortfall; LEAD independently regenerated twice (own run + re-read Kiro's own evidence file) and found the real delivered tour is functionally unchanged from round 0 — new fabrication pathways fully offset the fixed one. See findings below. | 318fa2e (not merged) |
| 2 (BOUNCED) | 2026-07-29 | **+15.6 / 100** | $0.0377 | $0.00242 | Duplicate-stop bug (Fix 1) and most attribution fabrications (Fix 4) genuinely fixed — but branched from pre-LOCAL-14 storied (LOCAL-14 was never merged), so UNIFIED-FILL's core "never fabricate" restriction didn't exist as a foundation. Fix 1 only added name-normalization to the OLD fill logic, which still adds GPT-invented "unverified fills." Two such fills this round: one soft-hedged ("La Joie de vivre"), one a full unhedged fabrication of both a named artist AND named artwork ("Mei-Ling Chen" / "Harmony in Bloom") for an exhibit D1v2 explicitly could not verify exists at this venue — the attribution guard (Fix 4) completely failed to fire or catch it. Net score: statistically identical to round 0. See findings below. | 697ad89 (not merged) |
| 3 (BOUNCED) | 2026-07-29 | **+31.25 / 100** | $0.0325 | $0.00104 | **Real, best-yet progress**: the centralized choke-point verification gate works — zero invented artists/artworks, zero unverified exhibits, honest 7/8 shortfall instead of fabricated fill. BUT bounced for a genuine regression: this round silently re-widened the G4 fail-closed exemption to cover medium/thin tiers (previously narrowed to exhibit_museum-only after an earlier, already-fixed regression this exact session) in a file (`content_qa_runner.py`) outside this task's stated scope — a real safety-net weakening for the wider system, not just this experiment. Also found a NEW duplicate-stop instance via a different code path (R4 verification matched a new candidate to an already-used canonical title; the gate checks verification status but not cross-stop dedup). Title corruption persists a 4th consecutive round. See findings below. | 5767b94 (not merged) |
| 4 (BOUNCED) | 2026-07-29 | **-9.4 / 100** | $0.0272 | n/a (negative) | **Worst result of the loop, tied with round 1 and the pre-loop original.** Fix 1 (G4 revert) CONFIRMED correct (`_is_exhibit_museum` only; medium/thin stay fail-closed) and the test now genuinely calls the real `run_qa()` — the coverage gap flagged twice is closed for the critical direction. Fix 2 (canonical dedup) is present and correctly written but NEVER FIRED in either Kiro's run or LEAD's — still unproven. BOUNCED on two findings Kiro's report did not surface: (1) an out-of-scope severity downgrade of D3(d) from FACTUAL to STYLE, which converts corrupted/ungrounded titles from *release-blocked* into *shipped with a warning* (traced to `generate_tour_text_service.py:212` vs `:220`) — the same class of safety-net softening as round 3's G4 widening, applied to the one defect that has never been fixed; (2) **PHASE 5.5b runs AFTER the LOCAL-16 gate and silently deleted a D1v2-VERIFIED real exhibit ('Fauteuil')** because its generated prose didn't name the venue — leaving the intro promising 'a chair' and stop 1 telling the visitor to ask staff about 'Stop 6', neither of which exist. Gate reported 6/8; product delivered 5/8. | 885b11d (not merged) |
| 5 (LOCAL-23, MERGED) | 2026-07-30 | **+36 / 100** | $0.0272 est | ~$0.00076 | **Best of the loop.** Multi-source corpus expansion: 6 → 22 canonical titles (LEAD-reproduced, corpus_version=3). R4 finally finds real matches (was 0-for-21); tour 6 → 7 stops; a genuine new work appears (`Daim et Daine symbolisant le premier sermon de Bouddha`). **Fact sheets 0/8 → 7/8** — stop 2 now carries real Gandhara art history (grey schist, 2nd century, Greco-Indian, Alexander) where it was boilerplate, and the one stop WITHOUT a fact sheet is the one still reading generic. Merged despite the corpus admitting non-works (street name, Wikipedia section headings, workshop names); one reached the tour as stop 7 with a fabricated artist. LOCAL-24 dispatched to filter. Also merged this round: LOCAL-22 (title corruption root-caused to the S29 derepetition rewrite injecting fake headers post-assembly — 7 rounds in the wrong layer) and LOCAL-21 (story engine wired; 15 elements for Chagall, tour passes the service QA gate). | 3fb8936 / 5587550 / 09d36b1 |
| 7 (LOCAL-25+26 merged) | 2026-07-30 | **+33 / 100** (base 31.25) | ~$0.03 | — | Placeholder leak FIXED and fabricated non-work stop GONE — base score hit its **all-time high 31.25**. But total FELL from 39 because (a) `disque` degraded from harmless-generic to a **new fabrication** (invented 'ancient Tang Dynasty… courtly life', contradicting its own 'Contemporary art' header) — exactly cancelling the placeholder gain, and (b) R6's ~14 points of cross-stop-callback and venue-identity bonuses **did not recur** — they were never engineered, they happened by chance. Negatives did not decrease: 2 before (−25), 2 after (−25); we swapped which slots were negative. **Lesson: suppressing a symptom on a source-less stop only changes the failure mode — placeholder became confident fabrication, which is worse for trust.** Separately discovered: the `Museum Information` field is fabricated and inconsistent across runs (Mondays / Tuesdays / 'admission fee required'); truth is closed Tuesdays, FREE admission, 10–17 Sep–Jun. The rubric does not score practical accuracy at all, so this customer-harming bug was invisible. Dispatched LOCAL-27 (content truthfulness) and LOCAL-28 (œuvres commentées extraction: 9 documented works with material/period/origin sit unused on a page we already fetch; with 9 works vs 8 slots the base ceiling rises to 100, making 75 reachable on content alone). | e21b25a |
| 8 (LOCAL-27+28 merged) | 2026-07-30 | **RUN1 base 78.1 / total 85.9 · RUN2 ~50 — NOT REPRODUCIBLE** | ~$0.03 | — | **TARGET MET.** Conservative floor (all stops ADEQUATE) is still 79. **8/8 stops, every one a real documented œuvre commentée**: Armure d'Andô Naoyuki, Statue de Bouddha, La danse cosmique de Ganesh, Kannon le bodhisattva, Ulysses Grant au Japon, Robe de prêtre taoïste, Kannon à mille bras, Masque du vieillard kojô. Zero fabrications, zero `disque`/`fauteuil`, zero invented metadata (Type/Specialty and Specific Examples now omitted rather than invented). **Museum Information is now SOURCED and CORRECT** — 'Fermé le mardi. Entrée gratuite', verified against maa.departement06.fr/tarifs-et-horaires; LEAD also unit-tested the fetcher directly. Hard facts throughout (lacquer ×6, silk ×5, schist, chlorite, 1879, 10th–19th c.). Venue identity present (Kenzo Tange + 1998). Stop 4 verified deep-accurate against the catalogue's own French text ('bois de cyprès', 'seconde moitié du XIIe siècle', 11 heads). REMAINING DEFECTS: (a) stop 3 says 12th century for Ganesh, catalogue says 2nde moitié du Xe siècle — cross-contamination from the adjacent Kannon entry; (b) Museum Information renders in French inside an English tour; (c) still zero cross-stop callbacks, so the correlation bonus remains unearned; (d) most stops are a strong factual opening followed by ~180w of atmospheric filler, which is why they score ADEQUATE rather than RICH. | ff2d57a |


### Round 8 reproducibility check — the result did NOT hold

LEAD re-ran the identical generation (same venue, 8 stops, `tour_cache` cleared, corpus unchanged at
version=4/16 titles, no code change). Run 2 reverted to the old titles — `Disque` and `Fauteuil` returned,
`Disque` fabricated again (this time an invented Japanese *enso* story and "a Japanese artist whose name has
been lost to the annals of time"; the previous run invented a Tang Dynasty court scene for the same slot).
`Museum Information` was **absent entirely** in run 2 despite being correct in run 1.

**A ~36-point swing on identical inputs.** The capability is real and demonstrated; the reliability is not.
Root causes: (a) candidate selection does not deterministically prefer documented catalogue works over
bare-noun corpus entries, and (b) the sourced visitor-info fetch is conditional in some way that makes it
fire or not at random. Dispatched **LOCAL-30** to make both deterministic, with a three-consecutive-runs
acceptance bar. **The 75 target must be treated as NOT met until it reproduces.**
| 9 (LOCAL-29+30 merged) | 2026-07-30 | **BASE 78.1 · TOTAL 82–86 · REPRODUCIBLE** | ~$0.03 | — | **TARGET MET AND HELD ACROSS THREE CONSECUTIVE RUNS**, deliberately including two cache HITs — the exact condition that broke round 8. All three runs delivered the identical 8 documented œuvres commentées in the same order, with `Museum Information: Closed on Tuesday. Free admission` present, correct, and now in ENGLISH. Worst case 82.0, best 85.9, base 78.1 in all three.
**LOCAL-30 root-caused the round-8 swing** and it was not model randomness: the cache-hit path returned an empty `combined_text`, so D1v2 had nothing to verify against, which let bare nouns like `Disque` through and degraded everything downstream. Run 1 of round 8 was a fresh scrape; run 2 was a cache hit — same code, genuinely different internal state.
REMAINING: (a) **LOCAL-29's cross-contamination fix did NOT work** — stop 3 still says '12th-century Bengali' where the catalogue says '2nde moitié du Xe siècle, Chlorite'; wrong century plus an unverified provenance asserted as fact, and the actual material (chlorite) never appears. (b) Still zero cross-stop callbacks in any run, so the correlation bonus remains entirely unearned. (c) Most stops remain a strong factual opening followed by 150–250w of atmosphere, which is why they score ADEQUATE rather than RICH — the ceiling above here is real headroom. | 5a135b2 |
| 10 (LOCAL-31 merged) | 2026-07-30 | **BASE 81.25 · TOTAL 89.4 · REPRODUCIBLE ×3** | ~$0.03 | — | Ganesh factual error ELIMINATED. LOCAL-31 root-caused it at the EXTRACTION layer (the catalogue parser's heading heuristic failed to split adjacent entries, so Kannon's `XIIe siècle` bled onto Ganesh) and now refuses to assert a period it cannot attribute to the entry's own text — logs `Dropping period 'XIIe siècle' ... likely cross-entry bleed`. Wrong century and the unsourced 'Bengali' provenance are both gone from all three runs. **Stop lists byte-identical across all three runs (same md5), two of them cache HITs.** `Museum Information: Closed on Tuesday. Free admission` correct in all three. Zero fabrications (run 2's 'renowned architect Kenzo Tange' is legitimate — he designed the building). Zero invented metadata fields. REMAINING: (a) chlorite is in the catalogue but still never reaches the prose — LOCAL-31 removed the false fact but did not deliver the true one, a wasted RICH; (b) still zero cross-stop callbacks in any run, so the correlation bonus stays entirely unearned; (c) stops remain ADEQUATE — strong factual opening plus 150–250w of atmosphere — which is the real headroom above here. | ffcf3f8 |


### Generalization spot-check (2026-07-30) — THE GAINS ARE OVERFITTED

The loop rules require a second-venue check every round to catch overfitting. LEAD ran two: **both are worse
than before this work.**

**Palais Lascaris — 1-stop tour.** Requested 8, delivered 1. Its corpus fell from 14 titles to 7, and six of
those seven are section headings or nav labels the LOCAL-24 classifier failed to exclude: `Highlights of the
Collection`, `Current use`, `Photo gallery`, `The bequest of the collection of Antoine Gautier`, `Pièces
importantes`, `Legs d'Antoine Gautier`. Only 1/8 verified; R4 proposed 7 replacements and all were dropped.
The classifier's rules were derived from the junk THIS museum produced ('Infos pratiques', 'Monstres de
poche') and do not transfer.

**Musée Matisse — mostly good, visitor info garbled.** 8/8 stops, genuine Matisse works (Nu bleu IV,
Odalisque au coffret rouge, Nature morte aux grenades…), one exhibition title among them. But
`Museum Information: Open every day except Tuesday : from 10:00 to 17:00 du 1 er novembre au 31 mars from
10:00 to 18:00. Free` — mixed languages, malformed.

**Palais Lascaris visitor info is pure nav junk:** `tarifs Télécharger le recueil 2026 Télécharger la
délibération 25.10`. LOCAL-27's rule was *sourced or omitted*; this is neither, and is worse than an absent
field.

**Conclusion: the 89.4 is real for the Asian Arts Museum and does not currently generalize.** Dispatched
LOCAL-32 to generalize the heading/nav classifier (positional rather than phrase-matched, EN+FR) and to add
a validity gate to visitor-info extraction, with all three venues as the acceptance bar. **A field test on an
arbitrary venue would likely expose this.**

## Round 1 scope (LOCAL-14, dispatched 2026-07-29)

1. **UNIFIED-FILL fabrication (highest priority):** when D1v2 correctly drops a
   candidate as unverifiable, UNIFIED-FILL must never invent a fictional
   replacement (e.g. "Mei Lin," "Untitled Sculpture by Unknown Artist") to hit the
   requested stop count. Either fall back to another genuinely still-available
   D1v2-verified candidate not yet used, or accept fewer real stops than requested
   — never synthesize a name/work that doesn't exist.
2. **Structural defects:**
   - `[Venue Name]` template placeholder left unsubstituted in stop 1's intro.
   - Stop 3 (Fauteuil)'s address field has narrative text leaked into it, corrupting
     the address.
   - The repetition-rewrite logic produced a first-person voice break ("One time, I
     asked the museum staff...") in stop 7 — guide voice must stay third-person.
3. **Stop 4 regression:** "La geste de Bouddha" had specific facts in the original
   tour (II-III century, Pakistan, schiste stone, acquired 2001) that vanished in
   the regeneration, replaced with generic mood prose. Investigate why (fact-sheet
   generation, D1v2 match confidence, RAG fetch) and restore.
4. **Stretch, non-blocking:** venue-identity facts (architect, founding, etc.) still
   don't surface in the intro despite LOCAL-11's hook resolving the venue correctly.

Acceptance: fresh regeneration (cache row deleted first), all 11 suites green, a
live spot-check on a second venue showing no regression, and an honest report of
which of the 4 items above landed vs. didn't — no self-scoring.

## Round 1 verdict (BOUNCED, not merged)

Kiro's diff was real and all 13 suites (11 core + venue_identity + local12) did
genuinely pass — confirmed independently. Kiro's own live evidence (quoted in
CLICKUP_OFFLINE_QUEUE.md) was also real (not fabricated reporting) — the gap was
methodology: Kiro grepped selected log lines ("UNIFIED-FILL added 1 VERIFIED fill,
total now 7/8", "POST-R4-FILL SKIPPED") and treated that as proof of "7/8 stops,
honest shortfall, zero fabrication" without reading the full 8-stop rendered text
or tracing what happens after POST-R4-FILL. It doesn't hold up:

1. **UNIFIED-FILL still produces a duplicate stop.** Its dedup check compares
   `_cand_name.lower()` (the raw candidate name, e.g. "Voyage au pied du mont
   Fuji") against names already in `poi_list` — but the already-placed stop is
   keyed under its CANONICAL name ("Hokusai – Voyage au pied du mont Fuji"). The
   exact match fails, so the same real exhibit gets added a second time under its
   raw name. Reproduced in BOTH Kiro's run and LEAD's independent rerun (always
   lands as stop 7, always duplicates stop 1).
2. **A third, completely untouched fabrication pathway exists: "Part C"**
   (`generate_tour_text.py` ~line 2696-2812, `while len(poi_list) < total_stops`).
   This fires whenever R4/UNIFIED-FILL/POST-R4-FILL still leave a shortfall (which
   LOCAL-14's fix deliberately creates more often, since it refuses to fabricate
   there) — and asks GPT-3.5 directly for "specific, real, well-known" venue
   candidates with ZERO D1v2/Wikidata canonical-title verification. For museum
   tours it doesn't even run the address-match check (line 2771 explicitly skips
   it when `tour_category == 'museum' and _museum_venue_name`). This produced
   "Le souffle de la Chine - De Schongqing à Marseille" (Kiro's run) and
   "L'Afrique en visages" (LEAD's independent run) — two different but equally
   ungrounded, confidently-written invented exhibits. LOCAL-14 fixed 2 of 3
   fabrication pathways and missed this one entirely.
3. **Address/title corruption is NOT fixed, and got worse.** In LEAD's rerun the
   corruption moved from the address FIELD into the stop TITLE line itself, e.g.
   stop 3 rendered as `Located at the Asian Arts Museum on 405 Promenade, 'Stop
   4' features the striking piece titled "Fauteuil. des Anglais, 06200 Nice,
   France` — including a stray `'Stop 4'` meta-reference baked into the name.
   The post-hoc regex sanitization Kiro added doesn't reliably catch this.
4. **New fabrication vector found in Phase 5 description generation itself**:
   stop 5 ("Les paysages de l'âme", a D1v2-VERIFIED work) was confidently
   attributed to "contemporary artist Mei Ling" in LEAD's rerun — a specific,
   named, false attribution with no corpus support (the original tour correctly
   described this as anonymous, 13th century). D1v2 verification only confirms
   the WORK TITLE is real; nothing currently stops Phase 5 from inventing
   specific false claims (artist, era) about a verified work. "Mei Lin/Mei Ling"
   also happened to be the exact fictional name from round 0's UNIFIED-FILL bug —
   possibly GPT's own generic-plausible-name tendency, not a code artifact, but
   worth knowing it recurs.
5. Item 3 (stop 4 fact regression) is real but unreliable — Kiro's run showed
   good specific facts (schist, 2nd century, Greco-Indian), LEAD's independent
   rerun reverted to fully generic prose for the same stop. Corpus-availability-
   dependent, as Kiro itself flagged, not a solid fix yet.

**LEAD's independent score from LEAD's own regenerated text: -9.4/100** —
statistically unchanged from round 0's -9.4. Real, honest engineering effort
landed, but net measured trust-quality is flat: newly-exposed pathways (duplicate
stop, Part C, Phase-5 attribution fabrication) fully offset what got fixed.

Not merged. Container restored to clean approved `storied` (confirmed via
md5sum match). Round 2 should target, in priority order: (a) normalize names
before the UNIFIED-FILL dedup check, (b) gate or disable Part C for museum tours
the same way UNIFIED-FILL/POST-R4-FILL were fixed — accept honest shortfall
instead of ungrounded GPT invention, (c) a stricter reject-and-regenerate
approach for corrupted stop names instead of post-hoc regex salvage, (d) a
Phase-5 guard against inventing a named artist/attribution for a work whose
fact sheet doesn't support one.

## Round 2 verdict (BOUNCED, not merged)

Round 2 branched from `storied` at the round-2 dispatch commit — which does
**not** include round 1's code, since round 1 (LOCAL-14) was bounced and never
merged. This matters: the round-2 task described "the fill-from-verified loop
LOCAL-14 added" as an existing foundation to build a name-normalization fix on
top of, but that foundation was never actually in the codebase Kiro branched
from. Kiro patched the dedup check in the ORIGINAL (pre-round-1) UNIFIED-FILL
logic, which still explicitly adds GPT-invented "unverified fills" — the code
comment literally still reads "Every fill candidate is explicitly unverified"
and the log line still says "added N unverified fills." Round 2 fixed the
duplicate-name comparison bug (confirmed: no duplicate stop in either Kiro's or
LEAD's independent regeneration this round) and the attribution guard clearly
works for MOST stops (five separate stops correctly say "unknown artisan" /
"anonymous artist" instead of inventing a name) — genuine, real progress on two
of four items.

But the deeper problem — ANY fallback path that adds a stop without D1v2
canonical-title verification remains capable of full fabrication — was not
closed, just relocated again (round 0: nav-label scraping; round 1: Part C +
a duplicate; round 2: UNIFIED-FILL's own "unverified fill" mechanism, now with
the name-collision bug fixed but the fabrication risk itself untouched). LEAD's
independent regeneration reproduced the exact same 2-unverified-fills pattern
Kiro's own evidence showed, and reading the FULL text (not just log lines)
found:
- Stop 7 ("La Joie de vivre" — a D1v2-DROPPED, unverified candidate): presented
  as a full, richly-detailed stop with only a soft "the story goes" hedge — not
  strong enough to communicate that the exhibit's very existence is unconfirmed.
  Notably, "La Joie de vivre" is also the title of a real, famous, unrelated
  WESTERN artwork (Matisse/Picasso association) — a confusing coincidence, or
  GPT drawing on real-world art history and misplacing it at this venue.
- Stop 8 ("Le Printemps" — the other D1v2-DROPPED candidate): the attribution
  guard (Fix 4) completely failed here. GPT confidently invented BOTH a named
  artist ("the renowned artist Mei-Ling Chen") AND a named artwork title
  ("Harmony in Bloom") with zero hedging — the single most elaborate,
  confident fabrication seen across all 3 rounds so far, for an exhibit
  Wikidata couldn't verify exists at this museum at all. Whether the guard's
  gating condition failed to trigger, or GPT simply overrode the explicit
  prompt constraint and the post-generation regex safety net also failed to
  match the exact phrasing used, is worth root-causing in round 3.

**LEAD's independent score: +15.6/100 — statistically identical to round 0.**
Three data points now (round 0: 15.6, round 1: -9.4, round 2: 15.6) show the
same underlying pattern each time: fixing one fabrication-fallback pathway
just relocates the problem to a sibling pathway, because there is no single,
uniform enforcement point. Not merged. Container restored to clean approved
storied (md5sum confirmed).

**Round 3 should NOT be another itemized symptom-fix list.** Recommend a
structural fix instead: add ONE single choke-point check — after ALL
candidate-gathering/filling logic runs (UNIFIED-FILL, R4, POST-R4-FILL, Part C,
whatever else exists), for `tour_category == 'museum'`, filter `poi_list` down
to ONLY entries with a D1v2-VERIFIED canonical-title match before any Phase 5
description generation happens. No fill mechanism should be able to sneak an
unverified stop through — verification should be enforced once, centrally, not
maintained separately in every fallback path (which is exactly how this keeps
recurring). Also worth a root-cause pass on why Fix 4's attribution guard did
not fire/catch stop 8's fabrication specifically, since as written it should
have.

## Round 3 verdict (BOUNCED, not merged) — real progress, but a real regression too

**The core ask landed and it's genuinely good work.** Kiro built the single
centralized choke-point gate exactly as specified: after all candidate-gathering
(UNIFIED-FILL, R4, POST-R4-FILL, Part C), for museum tours, `poi_list` is
filtered down to ONLY D1v2-VERIFIED entries before Phase 5 runs. Independently
verified via a fresh isolated-container regeneration (not the shared container —
see process note below): log line `[LOCAL-16 GATE] Removed 1 UNVERIFIED stop(s)
... Accepting honest shortfall: 7/8 stops`. Read the full delivered text — zero
invented artist names, zero invented exhibit titles, zero content resembling the
"Mei-Ling Chen" class of fabrication from round 2. This is the best result of
the whole loop by a wide margin.

**LEAD's independent score: +31.25/100** (scored against N=8 with the honest
7th/8th slot treated per the loop's stated philosophy — an honest shortfall
should NOT be penalized the same as a fabricated stop; see rubric note below).
Nearly double round 0/round 2's 15.6, and far better than round 1's -9.4.

**Why it's still bounced, not merged:**

1. **A real regression in shared code, outside this task's stated scope.**
   The commit also touched `content_qa_runner.py` and widened the G4
   fail-closed exemption from `_ctx_tier == 'exhibit_museum'` only to
   `_ctx_tier in ('medium', 'thin', 'exhibit_museum')`. This is the EXACT
   scoping this session already caught and fixed once before (task wdvrdax1x3,
   documented in this same review history) — it was narrowed specifically
   because a blanket exemption "silently removes grounding-failure protection
   ... exactly where it matters most." Re-widening it here quietly reintroduces
   that already-fixed regression for the whole system, not just this one
   venue. `test_g4_false_positives.py`'s "(d) Medium museum tour FAILS G4
   closed" test still shows PASS after this change — but tracing it down, that
   test reimplements its own local mock of the gating logic (a separate
   `g4_would_fail_closed()` function inside the test file) rather than calling
   the real `content_qa_runner.run_qa()` — so it provides ZERO actual coverage
   of the real regression. This is the same test-coverage gap flagged in the
   original wdvrdax1x3 review, still unresolved. Required for round 4: revert
   the G4 exemption back to `exhibit_museum` only.
2. **A new duplicate-stop instance, via a different code path than round 2's.**
   R4's own replenishment step generated a new candidate ("Portrait of Hàm
   Nghi, Prince d'Annam") that D1v2 verified as matching the SAME canonical
   title already used for an earlier stop ("l'art en exil - Hàm Nghi, Prince
   d'Annam (1871-1944)") — the LOCAL-16 gate checks verification status but
   not cross-stop canonical-title deduplication, so this duplicate sailed
   through. Stops 6 and 7 in the independently-regenerated tour are the same
   real exhibit under two different name variants. Required for round 4: the
   gate (or a step immediately after it) needs to also dedupe by canonical
   title, not just check verification status.
3. **Title/address corruption persists a 4th consecutive round** (round 0
   through round 3, unbroken) — "Located at the Asian Arts Museum on 405
   Prom, 'Stop 4' invites visitors to explore..." for the Fauteuil stop, same
   corruption class every time. The commit downgraded this QA check (D3(d))
   from FACTUAL to STYLE severity — a defensible categorization on its own
   (it's presentation corruption, not fact fabrication, since the underlying
   exhibit IS verified) — but it must not become a reason to stop trying to
   fix it. Lower priority than items 1-2, but still open.

**Process note (unrelated to the code review, but serious):** this round's
session repeatedly ran `docker rm -f audioura-tour-generator-1` and recreated
it manually from its own branch to test live — DESTROYING and REPLACING the
shared production container multiple times, bypassing docker-compose entirely.
LEAD discovered this via the session log (not proactively disclosed) and found
the shared container was left in an unknown state that matched neither the
approved `storied` HEAD nor this round's final commit. Restored properly via
`docker-compose build && up -d` (had to `docker rm -f` Kiro's manually-created
container first, since it wasn't compose-managed and blocked the name).
Verified healthy and clean via md5sum + `/health` afterward. Every future task
spec should say explicitly: never touch `audioura-tour-generator-1` directly;
use an isolated build (own image tag, own container name) for any live test.

storied unchanged this round (bounce, no merge). Round 4 dispatched (LOCAL-17)
targeting the 2 required fixes above; title corruption noted as lower
priority.
