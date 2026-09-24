# Handoff — morning of 2026-09-24

Tracked in git on purpose. `.continuous_dev/STATUS.md` is **gitignored**, so nothing
written there reaches the Windows machine. This file is the cross-machine channel
(CLAUDE.md: "a branch that is not pushed does not exist to the other machine").

---

## ⛔ FIRST: OPENAI CREDITS ARE EXHAUSTED (as of 2026-09-24 00:46 EDT)

```
"You have no credits remaining. Add credits to continue using the API"
"code": "credit_balance_exhausted"
```

**Your E2E will fail at the first generation call until Michael tops up the account**
(platform.openai.com → billing). This is not a code fault and not something the deploy
can work around. Confirm credits before you spend time debugging a failed tour.

## FOR THE GCLOUD DEPLOY SESSION — read this before you deploy

**A regex was hanging every large-museum generation. It is fixed on `storied`; make
sure your deploy includes it.**

`story_miner.extract_venue_identity` applied five groups of sentence-scoped patterns
(`[^.]*` on both sides of an alternation, ending in `\.`) to the **entire** venue
corpus. Museum of Fine Arts, Boston builds a 689,968-character corpus and the engine
backtracks exponentially. Three end-to-end runs died there last night, at 100% CPU.

Confirmed with `py-spy dump` against the live container:

```
extract_venue_identity (story_miner.py:2778)   -> four minutes later, 2795
generate_tour_text (generate_tour_text.py:17491)
```

**The symptom does not look like a hang.** The generator's event loop is saturated, so
the orchestrator's trivial status polls time out and the job is reported as a failed
generation. If your E2E picks a big museum and reports *"status polling failed"*, this
is what you are looking at — not a dead service.

Two changes, both on `storied`:
- `story_miner.py` — match per sentence, skip units over 2000 chars. **This is the fix.**
- `tour_orchestrator_service.py` — `_MAX_CONSECUTIVE_POLL_FAILURES` 6 → 30 plus a hard
  20-minute ceiling. Correct on its own merits, but it treats the symptom.

**Pick at least one large museum in the E2E.** Small venues never showed this — five of
six round-11 tours generated fine.

## ⛔ Igor's user-stops work is LOCAL DOCKER ONLY — DO NOT DEPLOY IT (D591)

**Michael, 2026-09-24, asked directly whether it should go to GCloud:** *"only on
local Docker before we approve the results of the Igor's test."* **This supersedes the
earlier line in this file that said it ships with this deploy.** That line was written
before he was asked; it is wrong and it is struck.

**So: no GCloud deploy from `storied` HEAD, and no TestFlight/Play build carrying
`1bb087e`, until Michael approves Igor's test results.**

Note the tag `rc-pre-igor-20260923` is **not** a way around this — the
catastrophic-backtracking fix `19358ae` lands *after* the tag, so deploying the tag
brings the MFA hang back. There is no env flag on the feature today. If the regex fix
must reach GCloud before Igor's test is approved, a kill switch has to be built first
(Kiro writes it, LEAD reviews it).

Everything below describes what the feature does, so you know what you are holding.

A stop the listener names in the request ("…with a stop at X") is now marked
`user_explicit`, survives D1v2 verification, and is exempt from the verified-only
gate. If it cannot be verified at the venue it comes back with `verified=False` and
the narration hedges, rather than being silently swapped for something else.

**Stop SELECTION is proven by effect; stop DELIVERY is not.** On the real request
through the service:

```
[LOCAL-212] Selected: ['Sons of Liberty Bowl', 'the Sargent Murals',
                       'Watson and the Shark by Copley']
[LOCAL-212] Dropped:  ['Ancient Nubia Now', "Sargent's Daughters", ...]
```

3 of 3 requested stops, against a baseline of 0. Four separate bugs stood between the
listener and their stops, each hiding the next:

1. the waypoint block was skipped on **both** bypass paths — the root cause, and why
   this looked non-deterministic run to run;
2. D1v2 verification discarded whatever survived;
3. the restore re-added a work D1v2 had already kept under its canonical title, so
   the same object appeared twice;
4. coverage selection ranked the survivors out of the tour by yield score.

**No tour has been delivered end to end with all four fixes.** metmuseum.org has
returned 429 for over an hour (it is fetched because "Watson and the Shark by Copley"
hangs in both museums), so narration fails and the tour cannot be assembled. External,
unrelated to the fixes, and it will not affect a GCloud run against a different venue.

So: treat user-named stops as selected-correctly but not yet delivered-and-verified.

## Tag: `rc-pre-igor-20260923`

Marks the tree the round-10 evidence was gathered against, **before** Igor's
user-stops work. Michael chose to merge Igor's fix into `storied` anyway so it ships
with this deploy; the tag exists so a failure can be bisected without archaeology.

## Quality evidence — round 11, six venues

Round 10 was two Boston venues, both clean, and read as "ship it". Six venues read
differently:

| venue | stops | clean | notes |
|---|---|---|---|
| CHURCH_1 (Newton MA) | 4 | yes | |
| STNICHOLAS (Nice, FR) | 4 | yes | non-English venues are NOT categorically broken |
| FANEUIL (Boston) | 4 | no | `bare_death` |
| LOGAN_1 (Boston) | 4 | no | was a FALSE POSITIVE, fixed — see below |
| RIVIERA (Nice, FR) | 3 of 4 | no | `thin`, `truncated` ("order of L") |
| LASCARIS (Nice, FR) | — | **did not generate** | French corpus vs English candidate titles |

**Two clean, two defective, one thin, one dead.** `n=2` was not evidence.

Palais Lascaris is the one to know about: `CLAUDE.md` STEP 11 uses it as the install
smoke test and expects ~10,000 chars. It clean-fails — the corpus is French, the
candidate works come back in English, the canonical match is exact, all six drop.
That is standing check #4 (D243) one level worse: not accents, language.

## Defect checks now GATE generation (this is new)

Until last night `tour_quality` had no caller in the generation path — `grep -c
"tour_quality" generate_tour_text.py` returned **0**. Every "gate" was post-hoc
measurement. `generate_tour_text.py` now scores the assembled tour and regenerates the
offending section **once** before packing and caching. A cache hit is neither re-scored
nor regenerated.

If a tour comes back with a defect recorded and a retry logged, that is the new
behaviour working, not a fault.

## One false positive was shipped and fixed the same night

`numeric_conflict` flagged Logan's "2,384 acres" as contradicting **JFK's** "5,200
acres" — two different airports. `_AIRPORT_NAME` does not match a bare acronym, so
"JFK" resolved to the venue. Since the checks now gate, a false positive spends money
rewriting correct content. Fixed; verified both directions (round 9's real
12M-vs-43.5M still fires; 1 hit across 56 files).

Its own false-positive survey had passed over 48 files, because round 11 did not exist
yet.

## Cost — the number moved because measurement improved, not spend

A 4-stop tour bills ~**$0.31–$0.62**, not the ~$0.21 previously reported. The old
figure summed OpenAI call sites only; Google Search grounding bills ~$0.035 per
REQUEST and appeared in no number anyone read. Round 10: LOGAN_1 $0.3083 (4 grounding
requests), CHURCH_1 $0.6182 (10). The 2.5× spread between two same-sized tours is
entirely request count and nobody has examined it.

Caching keys on `SHA256(accent-folded location | tour_type | stop BUCKET)`; buckets are
≤3 / 4–6 / 7–10 / 11+. So 4, 5 and 6 stops share one paid generation; 6 and 7 do not.
Venue identity is string normalisation only — no fuzzy or coordinate matching, by
deliberate decision.

## Production DB

35 test tours that were **visible in the app** (`is_test=true` with lat/lng set) had
their coordinates NULLed, backed up first to
`.continuous_dev/hidden_tour_coords_20260924.csv`. Row count 178 before and after —
nothing deleted. Seven rows with real venue names were left alone for Michael.
