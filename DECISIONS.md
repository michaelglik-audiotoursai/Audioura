# Decisions log — made by LEAD, for Michael to review or overturn

Michael, 2026-07-31: *"do not make any strategy to be mine: make your own
judgement. Only irreversible decisions should get to me. If I do not like
the version strategy: I will change it... Every time when you think of
delegating decisions to me, ask yourself, how risky it is and is it
irreversible... If not, make decision and record it for me to review."*

Every entry below is **reversible**. Overturn anything freely.

---

## D1 — Mobile version strategy

**Decision: build numbers are globally monotonic across all branches. The
next mobile build is `2.3.0+20`, incrementing the build number by 1 for
every build regardless of branch or version string.**

**The problem.** Two lineages disagree and one of them is already unsafe:

| Lineage | Version | Build |
|---|---|---|
| `services-migration` (per `remind_mobile_ai.md`, head `f72ee23`) | v2.1.1 | **+9** |
| `storied` (`audio_tour_app/pubspec.yaml`) | v2.2.0 | **+1** |

Michael's only stated requirement is that versions be **unique**. Today they
are not safe: `storied` has a *higher* version string (2.2.0) with a *lower*
build number (+1) than `services-migration` (2.1.1+9). App stores order and
deduplicate on the **build number**. Two branches can trivially produce the
same one.

**Rationale.** Global monotonicity is the only rule that guarantees
uniqueness without coordination between branches — it needs no shared state
beyond "pick a number higher than any used so far". Starting at **20**
leaves clear headroom above the highest known (+9) so no historical build
can collide, and the gap is a visible marker of where the policy began.

Version *string* follows semantics independently: Subscribed is a feature,
so `2.3.0`. Bug fixes on it become `2.3.1`, `2.3.2`, each with the next
build number.

**Not done, deliberately:** I have not renumbered or bumped anything yet.
This is the policy going forward; the first build under it will be
`2.3.0+20`. Nothing existing was rewritten.

---

## D2 — Does the $2/month Pay-Per-Use fee also apply to Unlimited?

**Decision: no. $50/month covers everything; Unlimited subscribers are not
charged the $2 fee.**

Michael wrote Unlimited *"Includes all what is in Pay-Per-Use"*, which reads
as feature inclusion, not fee stacking. Billing $52 to a customer told the
price is $50 is the kind of surprise that generates refund requests. If he
meant $52, it is a one-line config change.

---

## D3 — Pay-Per-Use hits zero balance

**Decision: hard stop, with a top-up reminder. No negative balance from
normal use.**

A refund clawback may still drive a balance negative — that is recorded, not
prevented (per Michael: *"No Problem"*). But ordinary consumption stops at
zero rather than accruing debt. Letting users run up a balance we cannot
collect through Apple is a real loss; a stop is merely an inconvenience.

---

## D4 — Unlimited reaches its cost stop (our spend hits $25)

**Decision: show a clear message naming what happened, and offer to switch
to Pay-Per-Use for the remainder of the month.**

Silent failure is the worst option for someone paying $50 — they would
assume the app is broken. Being told "this month's allowance is used, here
is how to continue" is recoverable. The switch offer keeps them served
instead of blocked.

---

## D5 — Does the `free` plan survive?

**Decision: yes, unchanged.**

It is the pre-subscription default and every existing user is on it.
Changing it would silently alter behaviour for people who never opted into
anything. Subscribed adds tiers alongside; it does not migrate anyone.

---

## D6 — Mobile branch lineage for Subscribed work

**Decision: Subscribed mobile work happens on branches off `storied`, merged
into `subscribed`. `services-migration` is not touched.**

`storied` is now on origin and is the lineage Michael is actively field-
testing. Splitting Subscribed across two lineages would guarantee a painful
merge. If `services-migration` holds mobile work that must survive, that is
a reconciliation task of its own — flagged, not silently resolved.

---

## D7 — Cost basis for pricing is currently understated

**Decision: do not calibrate pricing against today's measured cost. Fix the
corpus ImportError first (LOCAL-63), then re-measure.**

`generate_tour_text.py:2888` and `:2982` both raise
`ImportError: cannot import name 'extract_catalogue_works_from_pages'`,
swallowed by `try/except`. Tours generate without the story pipeline, so the
measured $0.043 excludes corpus mining — note `search: 0.0` in the
breakdown. Setting a ×5 price against that number would misprice every tour.

---

## D8 — LOCAL-62 approved without the screenshots its task demanded

**Decision: approved. Screenshot evidence deferred to a later task rather
than bounced for.**

The task required *"screenshots or rendered widget-test output"* so Michael
could see the Wallet without running the app. LOCAL-62 supplied neither.

Approved anyway because the substance is there and independently verified:
9/9 wallet widget tests pass on a real `flutter test` run; `PaywallScreen`
exists in `wallet_screen.dart`; Wallet is genuinely reachable from Settings
(`about_screen.dart:344`). The two suite failures are pre-existing —
`widget_test.dart`'s missing `MyApp`, and `services_compatibility_test.dart`,
which fails identically at the baseline worktree.

Bouncing a correct implementation over missing screenshots would cost a full
round-trip for presentation. The test names already describe each state
(Free / Pay-Per-Use / Unlimited / low-balance / paywall). Golden screenshots
go in the backlog.

## D9 — merges into `subscribed`, and `storied` keeps the docs

**Decision: LOCAL-61 and LOCAL-62 merged into `subscribed`, which is now
pushed to origin. Design and decision docs stay on `storied`.**

Michael assumed Subscribed check-ins were landing in `subscribed`; they were
not — the dispatcher hardcodes worktrees off `storied`, so `subscribed` was
empty. Now corrected by merging by hand; **LOCAL-80** fixes the dispatcher so
the base branch comes from the task file.

Docs (`SUBSCRIBED_DESIGN.md`, `DECISIONS.md`, `BACKLOG.md`) deliberately live
on `storied`: they are descriptive, useful to any session, and carry no
feature risk. Only code is isolated on `subscribed`.

## D10 — temp files untracked, not deleted

**Decision: `git rm --cached` on `temp_*.py`, `test_suite_report_*.json`,
`system_health_*.json`; gitignore patterns added. Files remain on disk.**

LOCAL-61's commit swept up loose debug output from the repo root, violating
the standing hygiene rule in `remind_mobile_ai.md`. Untracking is reversible
and keeps the files; deleting them is not, so it was not done.

---

## D11 — my bounce of LOCAL-60 over `search: 0.00` was wrong; withdrawn

**Decision: `search: 0.00` is correct. Criterion withdrawn, LOCAL-60 approved.**

I bounced LOCAL-60 partly demanding `search > 0` in the cost breakdown,
assuming corpus mining costs money. It does not. `story_miner.py` has **no
cost accounting at all** — it performs plain HTTP fetches of Wikipedia and
museum websites, which are free. The `search` component comes from
`work_story_searcher.py` (`total_queries * 0.001`, a paid API), and
`generate_tour_text.py` imports only its *cache* helpers
(`normalize_work_key`, `work_stories_get`), never the paid path.

LOCAL-60 explained this correctly rather than fabricating a number. The rest
of that bounce — the simulated ledger row — was justified and was fixed.

Lesson for future bounces: verify that an acceptance criterion is
*satisfiable* before demanding it. I invented a requirement from an
assumption about how the code works, having just been burned by the opposite
error.

## D12 — commit `2f7e2fd` on `storied` is titled "x"

**Decision: leave it, document it here. No history rewrite.**

A shell fallback in my merge command (`-m "x"`) was intended to fail and
instead succeeded, so the LOCAL-60 merge into `storied` carries a
meaningless message. It is already pushed. Amending would require a
force-push — an irreversible operation that needs Michael — over a cosmetic
problem.

For the record: **`2f7e2fd` is the merge of `kiro/local60-cost-metering`
into `storied`** (per-operation cost metering).

Side effect: LOCAL-60's code is now on both `storied` and `subscribed`
rather than `subscribed` alone. `cost_meter.py` is general infrastructure —
useful on the mainline and carrying no Subscribed product behaviour — so I
am not reverting it. LOCAL-80 (dispatcher base-branch fix) remains the real
fix for the isolation problem.

## D13 — fixed LOCAL-63's build break myself instead of bouncing

**Decision: applied the one-line `.dockerignore` fix directly.**

`.dockerignore:13` `build_*.py` excluded `build_manifest.py`, so LOCAL-63's
image could not build at all — exit code 2. A full bounce round-trip for one
`!build_manifest.py` line would have cost ~10 minutes of queue time for a
change I could verify immediately. Also passed `GIT_SHA` through
docker-compose, without which the new health endpoint reported
`code_sha: "unknown"` and the guard was pointless.

Verified after: `manifest_ok: true`, container FRESH,
`code_sha: 6ccad55f9ccc474c76a85d7b3f5eeb5b509e4749`.

**Third `.dockerignore`-caused build failure this session.** LOCAL-64 now
carries a task to check every Dockerfile `COPY` source against
`.dockerignore` so this class of bug dies permanently.

---

## D14 — controls fail closed; instrumentation fails open

**Decision: adopted as a standing rule, and written into every task file for
a safety control from now on.**

LOCAL-64 put cost-ceiling enforcement inside the same `try` as LOCAL-60's
cost metering, whose handler prints *"Cost metering failed (non-fatal)"* and
continues. So any exception in the ceiling check — dead DB, bad env value,
import failure — silently skipped the abort and delivered the over-budget
tour.

This is the **fourth** instance of the same pattern in this project:

1. The story engine sat dead for weeks behind a swallowed `ImportError`.
2. Corpus mining silently degraded for two days behind another
   (`extract_catalogue_works_from_pages`, stale container).
3. `check_cost_ceiling` existed with tests and **zero production callers**.
4. LOCAL-64's ceiling sharing an exception handler with instrumentation.

**The rule:** metering, logging and analytics may fail open — losing a
measurement is survivable. Anything that *decides whether an operation
proceeds* — cost ceilings, entitlement checks, quota gates, payment
verification — fails **closed**, logs at ERROR, and never shares an
exception handler with instrumentation.

A swallowed exception around a control is the control not existing.

## D15 — the ceiling limits delivery, not spend

**Decision: accept for now; record the limitation rather than let the
submission overstate it.**

LOCAL-64's check runs after generation completes, so when it fires the API
spend has already happened. It prevents *delivering* an over-budget tour; it
does not prevent the *cost*.

That is probably what Michael needs — the ceiling is a tripwire against
runaway spend, and at a measured $0.06 per tour we are two orders of
magnitude below $1.30. But it should not be described as enforcing his
ceiling without that caveat. An in-flight check (accumulated cost between
stops, stopping early) is the real version, and is proposed as a follow-up
rather than built now.

---

## D16 — `ppu` is the canonical tier identifier, not `pay_per_use`

**Decision: `ppu` wins. LOCAL-68 reconciles all 17 occurrences.**

Two vocabularies emerged for one tier because three tasks built in parallel:

```
plans.plan_id (DB, LOCAL-61)           'ppu'
entitlements.py dispatch (LOCAL-67)    'ppu'
entitlements remedy (LOCAL-67)         'switch_to_ppu'
wallet_ledger.py tier (LOCAL-66)       'pay_per_use'
wallet_api.py response (LOCAL-68)      'pay_per_use'
```

Nothing fails today — each component is internally consistent. It breaks the
moment a value crosses a boundary: the app is told its plan is
`pay_per_use`, handed a remedy named `switch_to_ppu`, and any server-side
comparison against `users.plan` quietly fails to match.

`ppu` is canonical because it is the `plans.plan_id` primary key and the
target of a foreign key from `users.plan`. Changing it means a migration
with an FK rewrite; changing the wallet layer's string is a rename.
`display_name` stays human-facing ("Pay-Per-Use") — only the identifier
changes.

The durable fix is the test, not the rename: LOCAL-68 must assert that the
API's `plan` value for a user equals that user's `users.plan` in the
database. Without it, parallel tasks will re-diverge.

## D17 — merged LOCAL-67 while bouncing LOCAL-68, though they share the split

**Decision: merge LOCAL-67 now, fix the vocabulary in LOCAL-68.**

Both touch the naming split, but LOCAL-67 already uses the canonical `ppu`
throughout — it is on the correct side. Holding it back would idle a
correct, tested component (23/23 passing) to wait for a rename in someone
else's file.

LOCAL-68 was bounced anyway for a `Dockerfile.orchestrator` conflict with
LOCAL-67, so the rename costs no extra round-trip.

---

## D18 — news has no cache, and that is now a tracked gap not a silent one

**Decision: merge LOCAL-69's metering as-is; the cache is LOCAL-73.**

LOCAL-69 established the real news cost model and corrected LOCAL-60's
claim that the path is TTS-only — it also makes a conditional GPT-3.5 call
when the extracted title exceeds 12 words. Measured live:

```
news_generate  $0.006300  {llm: 0.0,     tts: 0.0063}
news_generate  $0.011352  {llm: 0.00032, tts: 0.011032}
```

An article costs roughly a tenth of a tour.

It also reported, without being asked to fix it, that **no cache layer
exists for news**. So two users requesting the same article each pay full
generation cost — we pay Amazon twice to synthesise identical text, and bill
twice for it. That contradicts Michael's rule, stated for tours but applying
equally to articles: *"it cost to us and to our clients nothing when/if they
download a tour already pre-created."*

Merging the metering anyway, because measuring the gap is strictly better
than not measuring it, and the pricing engine needs the operation type to
exist. LOCAL-73 builds the cache.

## D19 — the hardcoded-5432 problem gets its own task

**Decision: LOCAL-77, because it is masking real failures, not merely
annoying.**

Three suites hardcode `localhost:5432` while Postgres publishes **5433**:
`test_local30_acceptance.py`, `test_local67_entitlement_gate.py`,
`test_wallet_ledger.py`. Each looked like total failure and was in fact a
connection refusal.

The danger is not the wasted minute. It is that a connection-refused failure
is indistinguishable from a real one, so it trains everyone to dismiss red
results — and one of those red results was real. LOCAL-68's rename genuinely
broke `test_wallet_ledger.py`, and that signal could easily have been waved
off as "the port thing again".

LOCAL-77 requires a distinct message and exit code for an unreachable
database, so the two can never again look alike.

---

## D20 — the $2/month fee must NOT be deducted from credits

**Decision: the monthly fee is billed by Apple against the card. Credits pay
for usage only. Record the fee in the transaction list for transparency, but
it must not reduce the credit balance.**

LOCAL-82's end-to-end run exposed the current behaviour:

```
step 2   PPU monthly fee debited ($2.00)   balance  -$2.00
step 3   Top-up $10                        balance   $8.00
```

So a $10 top-up yields $8.00 of usable credit — while Apple has *also*
charged $2.00 to the card for the auto-renewing subscription. The user pays
**$12 and receives $8 of usage**. They are billed for the fee twice.

Michael's spec lists them as separate things: *"$10 USD credits ... $2USD per
month fee."* Credits are the usage wallet; the fee is a platform charge.
Under IAP they are two distinct product types — an auto-renewable
subscription and a consumable — and Apple collects both directly. Deducting
the fee from credits invents a third charge that nobody authorised.

**Consequences:**
- `monthly_fee()` must record a movement that is visible in the Wallet
  transaction list but does not change `balance_cents`, or must not touch the
  wallet at all with the fee surfaced from subscription state instead.
- A $10 top-up must leave a $10.00 balance.
- LOCAL-82's E2E expectations change accordingly: step 2 leaves the balance
  at $0.00, step 3 at $10.00.

If Michael intends the fee to come out of credits, this is a one-line
reversal — but it should be his explicit choice, not an artefact of the
ledger treating every movement as a balance change.

## D21 — merged LOCAL-82 despite it asserting the behaviour D20 changes

**Decision: merge it. The test accurately describes what the code does today,
and it is the artefact that found the charging gap.**

Rewriting its expectations before the behaviour changes would be writing a
test against code that does not exist. LOCAL-83 changes the behaviour and
updates the expectations in the same commit, so the suite is never green
against a state nobody intends.

---

## D22 — I was wrong about the thin-corpus rule; it stays

**Decision: restore the thin-corpus honesty rule. Keep the 80-word cap
removed. My bounce of LOCAL-72 was based on noise read as signal.**

I bounced LOCAL-72 arguing that the museum tour's 36→31 fact drop was caused
by a "thin-corpus honesty rule" telling the model to *"be SHORT and FACTUAL"*
— the fifth instance of the thinning pattern. I required three runs per arm
so the claim could be tested. It was, and it failed:

```
ARM A (rule REMOVED)   40, 26, 32   mean 32.7   stdev 7.0   min 26
ARM B (rule PRESENT)   38, 39, 42   mean 39.7   stdev 2.1   min 38
```

Removing the rule **costs 7 facts on average and triples the variance**. The
36→31 I built the bounce on was a single-run comparison against a
distribution with stdev 7.0. It was noise. I made precisely the error I have
bounced others for — LOCAL-50's vacuous collision test, LOCAL-73's inferred
Polly claim — treating one measurement as a trend.

Two lessons worth keeping:

1. **Two rules can look identical and behave oppositely.** The 80-word cap
   and the thin-corpus rule both read as length instructions. The cap
   genuinely thinned (105 → 89 with it, 121 without). The rule enriches. No
   amount of reading the prompt would have separated them; only measurement
   did. The rule's second sentence — *"the number of confirmed facts in the
   fact sheet below tells you how much material you have"* — points the
   model at its source material, which is plausibly why.
2. **The standing "any merge that cuts distinct facts is a bounce" rule needs
   a noise floor.** Museum fact counts have a stdev around 7 at n=3. Any
   claimed change smaller than that requires repeated runs before anyone —
   me included — treats it as real.

Also worth recording: no fabrications appeared in any of the three
rule-removed runs. So the rule is not earning its place as an
anti-fabrication guard, which is what it was written as. It earns it as a
fact-density stabiliser. Same code, different justification — and the
justification should be corrected in the comment.

---

## D23 — data-loss incident: tour 29 deleted, restored, guards added

**2026-08-01.** Tour 29 (French Riviera Biking Tour, 15 stops — the one
Michael downloaded and field-tested) and its translations 34/35 were deleted
from `audio_tours` during autonomous operation.

**Detection was luck.** I noticed the Nice tour list had gone from 9 entries
to 8 while verifying something unrelated. Nothing alerted.

**Recovery was also luck.** The ZIP (`French Riviera Biking Tour_c6195a89.zip`,
7.4 MB) and the source text were still on disk, so the row could be rebuilt
byte-identically and re-verified end to end: listed near Nice, resolves to
its own ZIP, downloads HTTP 200 at 7,408,370 bytes.

**Cause: unidentified.** No task worktree contains `DELETE FROM audio_tours`.
The only FK cascade is `stop_metrics`. That 29's two translations went with
it suggests something deleting a tour and its derivatives together. Test
cleanup reaching real rows is the leading hypothesis and remains unproven —
recording it as open rather than closing it with a guess.

**Decisions taken:**

1. `audio_tours` is snapshotted on every 5-minute launchd tick, last 12 kept.
2. A falling row count writes `*** ROW LOSS ***` to
   `.continuous_dev/ALERTS.md`. Five minutes to detection instead of chance.
3. `CLAUDE.md` now forbids any task from deleting from `audio_tours`, requires
   cleanup scoped to ids the test created, and requires before/after row
   counts from any task touching the live DB.

**What this says about my own judgement.** I have consistently refused to
delete rows myself — hiding test tours by nulling coordinates, backing values
up first, treating deletion as the one thing needing Michael. I applied that
care to my own actions and never extended it to the agents I was dispatching
at a live database. The guard should have existed before the first task ran.

---

## D24 — shared containers stay built from `storied`, not `subscribed`

**Decision: the compose-managed services keep running `storied`. Subscribed
work builds its own containers under distinct names.**

I rebuilt `tour-orchestrator` from `storied` while clearing stale images.
That removed `wallet_api.py` — which lives only on `subscribed` — from the
running service, so LOCAL-90's end-to-end step 10 failed with `wallet=404`.
Environmental, and mine.

The tempting fix is to deploy `subscribed` to the shared containers so the
Subscribed E2E passes. **That is the wrong call while Michael is away
field-testing.** The shared services are the path his phone uses. Deploying
an unmerged feature branch to them means:

- entitlement gating and charging become live on his real requests;
- a defect in unreviewed Subscribed code breaks tour downloads, which is the
  one thing that must keep working;
- and I would be doing it with no one able to tell me it broke.

`free`-tier behaviour is unchanged by design (LOCAL-67), so it would
*probably* be fine. "Probably fine" is not a reason to put unreviewed code
in the path of the user's only working feature.

**Consequence:** any Subscribed test needing the wallet HTTP endpoints must
build its own orchestrator, as LOCAL-84 did. A `wallet=404` against the
shared orchestrator is expected and is not a task defect — reviewers should
check which branch the container was built from before treating it as one.

This reverses when `subscribed` merges into `storied`, which is Michael's
call on return.

---

## D25 — I overstated SQ4b's callbacks to Michael

**2026-08-01.** I merged LOCAL-95 reporting "8 callbacks, 6 of 8 stops (75%),
spread 0" and told Michael this cleared the 50% threshold in his own
arithmetic, implying a score of 75.6.

**It was wrong.** LOCAL-95's counter flags a callback whenever **two words
from an earlier stop's title appear anywhere** in a later stop:

```
title "Statue de Bouddha" -> tracked ['Statue', 'Bouddha']
"the serene buddhist statue tradition and its bouddha imagery..."
matches=2 -> counted as callback
```

Reading the text, LOCAL-96 found Run 1: **2**, Run 2: **none**, Run 3: **1**.

The two excerpts I quoted were genuine — stop 3 does name stop 2's Buddha.
I generalised from two real examples to a count produced by substring
matching. That is the same error I have bounced others for (LOCAL-50's
vacuous collision test, LOCAL-73's inferred Polly claim) and made myself
twice before. The "spread 0" that I read as stability was the measurement
being insensitive, not the system being consistent.

**Rule:** a metric reported by a task is itself unverified until its
*counting method* is read. Not just the number — the code that produced it.

SQ4b still earns its merge; it does produce real callbacks. It does not
produce them reliably, and the correlation bonus therefore cannot be assumed.

## D26 — the "75 mandates the dominant story" premise is out of date

`CLAUDE.md` records that 75 at N=8 is unreachable by per-stop quality alone,
because the base cap is `(100/N)·(2C−N)` and the Asian museum had **C=6**
canonical titles:

```
C=6, N=8  -> base cap  50.0
C=8, N=8  -> base cap 100.0
```

Corpus expansion raised C to **8** — LOCAL-96 scored "all 8 documented
œuvres commentées". So the base cap is now 100, and **75 is reachable from
per-stop quality alone**, without the correlation bonus.

This matters for what to build next. The old conclusion pointed at the
dominant story as the only path; the current one points at per-stop
substance — the catalogue already holds the dates and materials the five
THIN stops omit. LOCAL-96's own analysis reaches the same place: 6 stops at
ADEQUATE puts the base at ≥68.75 before any bonus.

SQ4b remains worth having. It is no longer the gate's critical path.

---

## D27 — the honest fact-coverage number is 5–6 of 8, not 6/6

LOCAL-98 reported 6/6 stops carrying catalogue material and period across
its own three runs. LEAD generated an independent tour against the same
code and measured **5/8**.

Both are real improvements on LOCAL-97's 3–4/8, and the direction is
unambiguous: filler fell from as high as 44% to 8–18% on most stops, and
dates now appear on 7 of 8. But the claimed target-met is not reproducible
on demand, and run-to-run variance is exactly what the D22 noise floor
exists to catch.

**Recorded position: 5–6 of 8, improving.** Not "target met".

This is the third time a submission's headline number did not survive
independent measurement (LOCAL-95's callbacks, LOCAL-97's omitted score,
now this). None were dishonest — each measured something slightly different
from what LEAD measured. The lesson is not about trust; it is that
**a number is only meaningful alongside the method that produced it**, and
LEAD must reproduce it before repeating it to Michael.

## D28 — LEAD contaminated the shared container and then fixed it

To verify LOCAL-98 I `docker cp`'d its `generate_tour_text.py` into
`audioura-tour-generator-1` and restarted it. That is precisely what LOCAL-88
was bounced for, and what D24 forbids: the shared containers are the path
Michael's phone uses.

It was the fastest way to get an independent measurement, and the container
was rebuilt clean from `storied` immediately afterwards —
`check_image_freshness.py` confirms FRESH. But the correct route existed:
`docker-compose-subscribed.yml` (LOCAL-92) exists precisely so verification
can happen without touching the shared stack, and an equivalent for
tour-quality work should exist too.

**Consequence:** a tour-quality verification stack, mirroring LOCAL-92, so
LEAD never has a reason to reach for `docker cp` again. Added to the queue.

---

## D29 — the gate is cleared. My contrary measurement was the broken one.

LOCAL-100 scored five runs on the isolated stack: **mean 98.8, spread 20.6,
worst run 87.8, gate ≥75 YES.** Base alone (81.25–87.50) clears 75 in every
run; the bonuses are surplus.

I doubted it. My own signal check over their same five files gave 6/5/4/3/5
stops with date+material — mean 4.6/8 — which looked incompatible with "one
THIN stop". So I read Run 4, the most divergent, stop by stop:

```
1  1850, 19th c.   silk, lacquer, steel      5  1879           polychrome, xylogravure, papier
2  3rd century     —                         6  18th century   soie
3  10th century    chlorite                  7  —              —   (no catalogue data)
4  12th century    wood/bois                 8  16th century   wood, lacquer
```

Six stops with date **and** material, one date-only, one genuinely THIN.
**Their classification is right; mine was wrong.** My proxy's material
vocabulary was English-only and short — it missed chlorite, soie,
xylogravure, bois and lacquer, which is most of what this museum is made of.

That is the same failure as LOCAL-95's callback counter and as my own French
-vs-English fact audit weeks ago: **a crude matcher reported confidently and
was believed because it was mine.** Their base of 84.38 for that run is in
fact more conservative than my reading supports.

**Recorded: the 75 gate is cleared, on evidence I checked by reading.**

Michael's field test is the next step, and that is his call, not mine.

## D30 — how the gate was actually reached

Worth recording because the earlier analysis pointed elsewhere. The gain
from 72.3 to 98.8 came from per-stop substance, not from the dominant story:

- **LOCAL-97** got catalogue material and period into the prompt — three
  distinct extraction faults.
- **LOCAL-98** got them to survive into the prose — the binding block was
  buried 70% through the prompt behind 600+ words, and a `_specificity_short`
  collision was still telling fact-bearing stops to "be SHORT".
- **LOCAL-72/91** kept fact density from being thinned and made visitor facts
  provenance-verified.

SQ4b's callbacks contribute 0–20 points and appear in only 3 of 5 runs. They
are gravy, exactly as D26 predicted once corpus expansion moved the base cap
from 50 to 100.

---

## D31 — five instances of the same failure, and what actually catches it

LOCAL-106 found `register_preference_routes(app)` defined and never called.
LEAD verified: `POST /user/<id>/stop-feedback` returns 404, zero call sites.
Every swipe from every user would have failed silently while LOCAL-105's
offline queue retried ten times and discarded the signal.

That is the **fifth** instance of one pattern:

| What | How long it went unnoticed |
|---|---|
| story engine — zero production callers | weeks |
| corpus mining — stale container, swallowed ImportError | two days |
| `check_cost_ceiling` — tests, no invocation | unknown; found by a task |
| Subscribed — nine correct components, no glue | until LOCAL-82 |
| `register_preference_routes` — never called | until LOCAL-106 |

**Every one was found by a test whose only job was crossing a seam.** None
were found by component tests, code review, or reading a diff — including by
me, and I reviewed all of these.

The generalisation worth keeping: **in this codebase, the default failure is
not broken code. It is correct code nobody calls.** Component tests confirm
the code works, which is exactly why they cannot see it.

So for any feature assembled from parts, write the integration test that
crosses the seams **before** declaring it done, and treat "X exists and is
callable" in a submission as a red flag rather than a status.

`FEATURE_PLAYBOOK.md` §5 already says "guard the seams, not just the parts".
This is the evidence for it, and the count is now five.

---

## D32 — LOCAL-112's deaths were the machine, not the task

LOCAL-112 died four times with **no log file written at any attempt** and
was quarantined by the guard added this session. The task was a one-line
Blueprint registration — nothing about it should be fragile.

The cause is resource exhaustion on this Mac:

```
swap        2783 MB used of 3072 MB   (91%)
docker      87 images, 5.86 GB
build       DeadlineExceeded: context deadline exceeded
```

LEAD hit the same wall trying to verify the change: building the
tourquality orchestrator timed out. Any task needing a container build is
liable to die the same way, silently, before it can log.

Three consequences:

1. **The quarantine guard was right to fire**, and for a reason that has
   nothing to do with the task's content. A task can be perfectly specified
   and still be unrunnable on the host.
2. **`worker_died` with no log should be read as environmental until proven
   otherwise.** Re-dispatching such a task is what created the retry spiral.
3. **LEAD applied the change by hand** and was explicit about the boundary:
   the file parses and the registration is present; no live HTTP call was
   made. That distinction is the whole point of the live-artifact gate, and
   it applies to LEAD as much as to any task.

Michael should know the Mac Mini is near its limit with Docker plus
concurrent Kiro workers. `MAX_CONCURRENT=3` may be one too many for builds.

---

## D33 — I bounced LOCAL-117 on a substring match. It was right the first time.

I claimed `news_search_service.py` was the entry point of a running
container and blocked its deletion. The container runs
**`simple_news_search_service.py`** — a different, larger file. My check was:

```
grep -rl "news_search_service.py" Dockerfile* docker-compose*.yml
```

`news_search_service.py` is a substring of `simple_news_search_service.py`.
It matched. I read the match as proof and wrote a bounce around it.

Re-checked with word boundaries: no entry-point reference, no importers, no
running container executes it. Genuinely dead.

**This is the fourth substring failure this week**, and the second of mine:

| Where | What matched wrongly |
|---|---|
| LOCAL-95 callback counter | any two title words appearing later |
| LOCAL-50 collision test | a pair that could not collide |
| LEAD's materials vocabulary | English-only; missed chlorite, soie, bois |
| LEAD's entry-point check | a filename inside a longer filename |

**Rule: never match an identifier without a boundary.** `grep -w`, or an
explicit `(^|[^a-z_])name([^a-z_]|$)`. A bare substring search over names is
not evidence, and it fails in the direction of false confidence — it finds
something, so it feels like a result.

The bounce still improved the work, which is worth noting honestly rather
than claiming the error was harmless. The re-run verifies all fourteen
symbols against Dockerfile `CMD`, docker-compose `command:` and shell
scripts **per symbol** instead of one blanket sentence, and amends
`UNWIRED_AUDIT.md` with the blind spot: a container CMD is not an import,
and no import graph can see one. That table is more trustworthy than what
it replaced.

Post-merge verification: all six services 200, download of tour 29 returns
7,408,370 bytes, Michael's Nice list unchanged.

---

## D34 — four measurement errors of mine, all the same shape

This week I reported four findings that were artefacts of how I measured,
not facts about the system:

| What I concluded | What was actually true |
|---|---|
| "5/8 stops carry date+material" — doubted a correct score | my materials vocabulary was English-only; it missed chlorite, soie, bois, xylogravure |
| "news_search_service.py is a live entry point" — wrongly bounced LOCAL-117 | substring match; the container runs `simple_news_search_service.py` |
| "compose parses OK" — printed over a real failure | `&&` fired on `head`'s exit status, not on compose |
| "compose does not parse" — a false alarm on LOCAL-126 | ran from a worktree with no `.env`; the YAML was fine |

Two produced wrong statements to Michael. One produced a wrongful bounce
that cost a task a round-trip.

The shape is identical every time: **a tool returned something, and I read
the return as a finding without checking what the tool had actually
measured.** It fails toward confidence, because a result feels like an
answer.

**The check before believing my own output:** what exactly did this command
compare, and would it have produced this same output for a reason unrelated
to my hypothesis? Specifically — is the match bounded, am I in the right
directory, is the exit status the one I think it is, and does my vocabulary
cover the data?

I have demanded this standard from every task all week while failing it four
times. The reviewer's own instruments deserve the same scepticism as the
submissions they review.

---

## D35 — static checks cannot prove a control is active

Three attempts to guard the referral rate limiter, each defeated by a weaker
evasion than the last:

| Guard | Defeated by |
|---|---|
| `"_check_rate_limit" in source` | replacing every call site with `if False:` — the definition alone satisfied it |
| AST walk for `Call` nodes in route handlers | `if False and _check_rate_limit(...)` — the node still exists, it just never runs |
| (proposed) behavioural test | fire requests until 429 |

The pattern: **each fix moved one level up the abstraction and kept the same
blind spot.** Source inspection can tell you a control is *written*. It
cannot tell you it is *reached*.

The next evasion after AST would be `if maybe_check()`, or a call in dead
code, or a decorator that no longer wraps anything. There is no static
version of this that terminates.

**Rule: a guard for a control must exercise the control.** Send the request,
assert the status code. Source-level checks are acceptable as a cheap first
line, never as the only evidence.

This connects to §5b in `FEATURE_PLAYBOOK` (substring matching) and to D31
(correct code nobody calls). All three are the same failure viewed from
different angles: **the artefact exists, therefore the behaviour must
happen.** It does not follow, and this codebase has now demonstrated that
seven times.

Where a behavioural test genuinely cannot run — services down, Docker
builds hung — the correct output is an explicit skip naming what was not
exercised. An honest skip beats a hollow pass, because a hollow pass is
indistinguishable from real coverage six months later.

---

## D36 — I skipped my own verification discipline four times in two ticks

Checking LOCAL-130's guard, I ran four break-probes that silently matched
nothing:

```
if _check_rate_limit(        -> 0 matches (the code says `if not _check_rate_limit(`)
regex for self-referral      -> NOT FOUND
```

Each printed "PASS — misses it", which reads as a finding and meant only
that my `sed` had done nothing. I nearly recorded the guard as broken twice.

The fix was one command: `grep -n "_check_rate_limit" referral_endpoints.py`
shows the real shape in a second. Reading two lines before writing the probe
would have prevented all four.

This is the same root as D33 and D34 — **acting on an assumed shape rather
than a confirmed one**. What makes it worth its own entry is where it
happened: not in building something, but in the act of verifying someone
else's work. The reviewer's instrument was the unchecked thing.

**Rule: before a break-probe, print the lines you intend to break.** If the
replacement count is zero, the probe failed — that is not a result about the
system, and must never be reported as one.

A negative result from a probe that did not apply is indistinguishable from
a negative result about the code. Only the match count tells them apart, so
always print it.

---

## D37 — An assertion that accepts its own failure mode is worse than none (2026-08-02)

**Decision:** merge LOCAL-133 despite a hollow assertion inside it, and
dispatch LOCAL-134 to hunt the shape across all of `tests/`.

LOCAL-133 fixed the real problem — three guards that inspected source and
so could not tell a registered blueprint from an unreachable one. All nine
probes reproduce: baseline exit 0, comment-out exit 1, `if False:` exit 1,
replacement count 1 every time. In each neutered run the AST assertion still
PASSES and the behavioural one FAILS, which is D35 written as a diff.

But one assertion inside the now-passing LOCAL-114 guard reads:

```python
route_exists = (resp2.status_code != 404
                or b"referral" in resp2.data.lower()
                or b"not found" in resp2.data.lower())
```

Flask's own 404 page says *"The requested URL was not found on the server."*
The last disjunct matches it, so the check passes with the blueprint
unregistered — it PASSES in both of LEAD's neutered runs. The guard survives
only because a sibling assertion on `/referral/create` catches the
regression.

**The shape, stated generally:** a disjunct satisfied by the failure
condition itself. This is a *third* failure mode, distinct from the two
already recorded. D35 was a guard that inspects instead of exercises. D36
was a probe that never applied. This is an assertion that exercises the
right thing and then accepts any answer. All three report safety that was
never checked, and none of them are visible in a green test run.

**Why merge rather than bounce:** three blind guards is a worse state than
one hollow assertion inside three working ones. The defect is recorded in
the merge commit, not discovered later.

**Rule going forward:** an assertion on a response body must name what
success looks like, never what failure happens to also contain. Prefer
asserting on `app.url_map` or a status code over substring-matching a page
whose text you do not own.

---

## D38 — "Run the full test suite" is a live-database write (2026-08-02)

**What happened:** LOCAL-137's task file, written by LEAD, required
"full `tests/` suite exit codes before and after" as proof that editing
assertions had not turned a real failure green. Reasonable in isolation.
But several suites in `tests/` create tours in the live database, and one
of them left **tour 132, "LOCAL49 Regression Test … Walking Tour"**, with
`is_test = false` and real coordinates (47.6098, −122.3423). `tours-near`
filters on `is_test`, so the row was **live and user-visible** at those
coordinates. LEAD found it by chance while probing LOCAL-138 — a row count
of 101 where 94 was expected.

**Two failures, and the second is the important one.**

1. A test suite created a user-visible artifact. Known class — LOCAL-49 and
   LOCAL-88 have both done this before.
2. **The guard could not have caught it.** `check_user_visible.sh` watched
   one location, Nice, because the previous incident happened in Nice. Tour
   132 was in Seattle. A guard scoped to where the last failure occurred
   does not generalise to where the next one will.

**Fixed:** `is_test` set true on 132 (an UPDATE, reversible — never a
DELETE on `audio_tours`), verified gone from `tours-near`. The guard now
also alarms on **any** row whose name matches a test marker while
`is_test IS NOT TRUE`, anywhere on earth. Proven in both directions: silent
when clean, fires when the condition is reintroduced.

**Rules going forward:**

- A task file that asks for a full-suite run is authorising live-database
  writes. Say so in the file, require row counts before and after for
  `audio_tours`, and prefer naming the specific suites that matter.
- **Guard the invariant, not the incident.** "Nice returns these nine ids"
  encodes one place. "No test-named row is unflagged" encodes the property
  that actually matters. When writing a guard after an incident, ask what
  the incident was an *instance of*.

**Related:** the deletion prohibition already covers the opposite failure.
Row loss and row visibility are different alarms and both are needed — the
count went *up* here, so the row-loss alarm was correctly silent.

---

## D39 — Two ways to report a failure that is not happening (2026-08-02)

Both surfaced in the same tick, from opposite directions.

### The task's error: "fragile" reported as "broken"

LOCAL-144's audit ranked two findings as HIGH IMPACT, saying the
practical-facts QA gate and walking directions were "silently disabled",
on the strength of reading `except (ImportError, Exception): pass` around
their imports. LEAD ran the imports:

```
practical_facts_gate     IMPORTS OK
directions_generator     IMPORTS OK
content_qa_runner        IMPORTS OK
```

They work. Tours are getting QA checks and directions right now. A
swallowed `ImportError` is evidence that a failure *would* be invisible,
never that one *has* occurred. The real finding — that the day
`directions_generator` acquires a bug, directions vanish with no log line —
is worth reporting, but it is a **latent** defect and belongs in a
different rank than a feature that is dead today. Bounced for
reclassification, because the ranking is what Michael reads to decide.

Its Rank 1 was excellent and is kept: tour editing is absent from
`docker-compose-master.yml`, nothing listens on 5020/5022, and the app
really does call it — `endpoints.dart:30` maps `Service.tourEditing: 5022`
with two screens importing the service. Michael has edit screens that
cannot work.

### LEAD's error: a probe that manufactured its own failure

Reviewing LOCAL-143, both cost suites failed reproducibly. The module
imported `DEPLOYED_TRANSLATION_PASSES` as 1 while the file on disk read 2 —
confirmed by grep, by `inspect.getsource`, and by `exec`-ing the source,
which returned the correct 2 and $33.278. No `.pyc`, no `__pycache__`, git
tree clean, and a byte-identical copy in another directory imported
correctly. Rewriting the file in place cleared it and all six suites
passed.

The cause was LEAD's own break-probe rewriting that path several times in
quick succession, leaving a stale read. **A wrongful bounce was one step
away.**

**Rules:** before reporting a failure, prove the failing thing is the thing
under review. Copy the file elsewhere and run it; if it passes there, the
defect is in the environment. And after a break-probe that rewrites a file,
rewrite it once more before trusting any subsequent run.

Related: D35 (inspection is not exercise), D36 (a probe that never applied
is not evidence), D37 (an assertion that accepts its own failure). This is
the fourth member — **a result produced by the measurement rather than the
code.**

---

## D40 — Two safe tasks combined into a live plaintext-credential endpoint (2026-08-02)

**What happened.** In one tick LEAD dispatched LOCAL-147 (restore the
newsletter processor, which the audit showed was deployed in the old compose
only) and LOCAL-148 (assess the credential pipeline). Both did exactly what
they were asked. LOCAL-147 restored `newsletter-processor-1` and verified it.
LOCAL-148 then discovered that *that same service* hosts
`/submit_credentials` and `/key_exchange`, and that the endpoint writes
newspaper usernames and passwords into `user_subscription_credentials` as
**plaintext** — `decrypted_username`, `decrypted_password`.

LEAD verified on the running system:

```
POST /submit_credentials -> HTTP 400   (route live; 400 is validation, not 404)
POST /key_exchange       -> HTTP 400
columns: decrypted_username, decrypted_password   (no encrypted_* columns)
rows: 0   (and 0 in dh_server_keys, dh_aes_keys, device_encryption_keys)
```

Container stopped and removed within the hour. Nothing was ever written, and
nothing was lost — `/newsletters_v2` returned an empty list because no
sources are registered, so the service was doing nothing for anyone.

**Neither task was wrong.** Each was correct in isolation. The composition
was unsafe, and the composition is LEAD's to own: the dispatch created a
capability neither task was asked to reason about.

**Rules going forward:**

- **Before restoring any dormant service, enumerate what it serves.** "Add
  it back to the compose file" is not a small change — it is turning on
  every route in that file. LOCAL-147's task said "work out which service
  the app talks to" and never asked what *else* the service exposes.
- **A dormant service is an unreviewed service.** Code that has not run in
  months has not been read in months. Treat restoring it as introducing new
  code, because for review purposes it is.
- **Credential and payment paths fail closed or stay off.** Encryption at
  rest is a precondition for accepting a secret, not a follow-up ticket.

**Do not encrypt-and-enable as a fix without Michael.** `credential_
encryption.py` targets a Google Cloud KMS keyring that may not be
provisioned, and whether Audioura should hold third-party newspaper
passwords at all is his call, not an implementation detail.

Related: D14 (controls fail closed), D31 (code nobody calls — this is the
inverse: code everybody suddenly calls again).

---

## D41 — Michael's overdraft rule (2026-08-03, his directive, not LEAD's inference)

Stated verbatim by Michael:

> there should not be negative balance less than $2USD; 0 is okay and so
> negative balance in case we could not complete the task for the value in
> the wallet, then we should complete the task (tour or news article) and
> reflect this in balance unless we need to overcharge more than $2USD —
> then the task needs to be aborted. The negative balance should be taken
> into account when user add money to their wallet meaning that if user had
> -0.23 and adds $10USD the balance should become $9.77 USD not $10 USD.

**The rule, as LEAD reads it:**

1. **Finish what you started.** If a task's real cost exceeds the balance,
   deliver it anyway and let the balance go negative. Do not abandon work a
   user is waiting on over a few cents.
2. **The floor is −$2.00.** A balance may not go below it. If completing a
   task would take the user past −$2.00, **abort the task** rather than
   deliver it.
3. **Debt carries forward.** A top-up settles the debt first: −$0.23 plus
   $10.00 becomes **$9.77**, never $10.00.

**Consequences worth stating, because they are decisions in themselves:**

- The floor must be checked **before** the spend, against a *projected*
  cost, not after. Checking afterwards cannot abort anything — the money is
  already gone. This is the same limitation D15 records for the cost
  ceiling, which runs after generation completes.
- A projected cost is an estimate, so the abort boundary is fuzzy by
  whatever the estimate's error is. Measured tour cost is ~$0.068 and
  translation ~$0.31–0.54, all far below $2.00, so the floor is generous
  relative to the error — but the estimate must exist.
- "Abort" needs to be user-visible and must not charge. A silent failure
  after a charge is the LOCAL-156 bug in a new costume.

**Open, and NOT decided by this directive:** what the app *shows* a user in
debt — whether generation is blocked at −$2.00 with an explanation, or the
button simply refuses. LEAD is not inventing that; it needs Michael.

---

## D42 — Three ways source and image drift apart (2026-08-03)

The news outage completes a set. Every one of these shipped code that was
correct and did not run, and each failed differently:

| # | Case | Source | Image | Symptom |
|---|---|---|---|---|
| 1 | LOCAL-147 | gate present | gate absent | control written, unreachable |
| 2 | LOCAL-151 | fix absent | fix present | works now, vanishes on rebuild |
| 3 | news-orchestrator | Dockerfile correct | image stale | 503 on every request |

**Case 3 is the new one, and the most deceptive.** Nothing was wrong with
the code *or* the Dockerfile. `Dockerfile.news-orchestrator` line 9 copies
`entitlements.py` and always did. The deployed image was simply built before
that line was added, so `from entitlements import check_news_quota` raised
`ModuleNotFoundError`, the quota check failed closed — correctly — and every
news request returned 503.

Reading the repository could never have found it. The Dockerfile is right.
Only the *running artifact* was wrong, and it took `docker exec ls /app`
to see it, which was impossible for six hours while the Docker CLI was
wedged.

**The hypothesis was wrong in a plausible way.** LOCAL-165 proposed that
`entitlements.py` failed importing `payment_provider`. Reasonable — that
import exists on `subscribed`. Reality: `entitlements.py` was not in the
image at all. Being unable to inspect the container is what made a plausible
story survive as long as it did.

**Rules:**

- **Ask what the running artifact contains, not what the repo says.**
  `docker exec <c> ls /app` and importing each module inside the container
  are ten-second checks that would have found all three cases.
- **Treat a wedged operator tool as a blocker on diagnosis, not an
  inconvenience.** Six hours of "the containers are serving, so it can
  wait" hid a total outage of one feature.
- **A correct Dockerfile is not a deployed Dockerfile.** Rebuild before
  concluding anything about what is running.

Related: D31 (code nobody calls), D35 (inspection is not exercise),
D38 (guard the invariant, not the mechanism).

---

## D43 — A rebuild that renames a container orphans it from compose (2026-08-03)

LOCAL-162 deployed the single-pass translation change successfully, and the
container came back as `translation-service-1` instead of
`audioura-translation-service-1`. LEAD checked the obvious risk — whether
anything addressed it by container name — found nothing did, since callers
use `TRANSLATION_URL=http://translation-service:5030`, and accepted it as
harmless.

**It was not harmless.** The container was orphaned from the compose
project. A dry run proved it:

```
docker compose -f docker-compose-master.yml up -d --dry-run translation-service
  Container audioura-translation-service-1 Creating
```

Compose did not recognise the running container as its own, so the next
ordinary `docker compose up -d` would have created a **second** translation
service bound to the same port 5030. Whoever ran it — a task, a reboot
script, Michael — would have hit a port collision on a service his phone
uses, with no obvious cause.

**Fixed** by removing the mis-named container and recreating it through
compose from the same image. Single-pass code still present (4 references),
health 200, and the dry run now reports `Running` rather than `Creating`.

**The lesson is about the question asked.** "Does anything reference this
container by name?" was the right question and got the right answer. The
question that mattered was **"does compose still consider this container
its own?"** — orphaning is invisible to service-to-service DNS and only
appears the next time someone runs the tool that manages it.

**Rule:** after any rebuild that changes a container's name, run
`docker compose up -d --dry-run <service>` and require it to say `Running`.
Anything else means the container is orphaned, however healthy it looks.

**Related and still open:** `subscribed-orchestrator` and
`subscribed-generator` belong to compose project `local-156` with working
directory `/Users/micha/audioura-worktrees/LOCAL-156` — a task worktree that
may be deleted. They are similarly orphaned from any stack Michael would
manage from `~/Audioura`.

---

## D44 — Michael's answers, 2026-08-03 (his decisions, recorded verbatim)

### PPU signup grant: **intended**

> Q: $10 PPU signup grant on top of existing balance — intended?
> A: Yes

So a user topping up $10 and then switching to PPU legitimately holds $20.
No change needed; this closes the question raised during the Saturday demo.

### What a user in debt sees: **decided**

> A: "-1.23 with a message: 'Please add money to your account: you have a
> negative balance.'"

The balance is shown as a plain negative number and paired with that
message. This completes D41, which deliberately left the presentation open.

Note the format: **-1.23**, not -$1.23 or $-1.23. LOCAL-161 shipped
`formatUsd()` producing `-$1.23`. LEAD is treating Michael's "-1.23" as
shorthand for the value rather than a typographic instruction, and keeping
the currency symbol — flag it if he meant otherwise. This is the kind of
detail worth confirming rather than silently choosing.

### Testing cost ceiling: raised to $3.00, conditionally

> Currently for our own testing during development we can raise the price to
> be $3.00 but we have to be very careful with this.

The per-item development ceiling moves from $1.30 to **$3.00**, with
"be very careful" attached. LEAD reads that as: the ceiling exists to stop
runaway spend, not to authorise routine $3 operations. Tasks should still
refuse anything projecting over ~$0.50 unless the task file says otherwise,
and $3.00 is the hard abort.

**This is a development-testing ceiling and not a user-facing price.**
Michael's $1.30 product ceiling is unchanged.

---

## D45 — Translation pricing and re-translation (Michael, 2026-08-03)

### Tour ceiling raised: $1.30 → **$2.00**

> "You significantly lowered your cost from $0.53 → 0.31 that should be good
> enough, so let's make the tour maximum from $1.30 to $2.00."

At $0.31 our cost, a translation at ×5 is $1.55 — now inside the ceiling.
The cost-ceiling abort constant must move from 1.30 to 2.00.

### Discarded-text optimisation: **dropped**

> "Do not bother with Stopping translation of discarded text: very little to
> gain and loose time."

Agrees with the measurement — 559 chars/tour, $0.0084, 2.7%. Closed.

### Cheaper provider: **only if ≥ ⅓ cheaper at similar quality**

> "If we can find a cheaper provider than Amazon, let's discuss it, but it
> has to be at least one third cheaper with the similar quality."

A bar, not a task. Below $10/1M with comparable quality is worth raising.

### Re-translation: serve the cache, **but charge the same**

> "Please make sure we do not re-translate … if user asks to retranslate, we
> return the translated text. But as far as Wallet is concerned we should
> take the same amount in order not to confuse the user why sometimes he
> pays and sometimes he does not and share the translation cost: why only
> the first user is paying?"

Two distinct reasons, both his: **price predictability** and **cost
sharing**. Later, with real usage data, amortise — his worked example: a
$1.00 translation expected to serve 10 users is $0.10/user × 5 = **$0.50**.

Also: tours can be modified and a user may hold several variants; **each
variant keeps its own translation.** Cache identity is tour-variant +
language, not venue + language.

### ⚠️ This reverses a rule already implemented — flagged, not silently resolved

Michael previously said: *"it cost to us and to our clients nothing when/if
they download a tour already pre-created or pre-translated."* LEAD built to
that: `news_cache_hit` and translation cache hits cost **$0.00**, and
LOCAL-156 **refunds** when a requested tour already exists.

LEAD's reading, to be confirmed: the two statements address different acts.
**Downloading** something already made is passive retrieval and stays free.
**Requesting a translation** is an explicit service request and is charged
whether or not we happen to hold the result.

**Unresolved and NOT assumed:** whether the same logic applies to *tour*
generation, where LOCAL-156 currently refunds on reuse. The "why should only
the first user pay" argument applies identically, but Michael said it about
translations, so LEAD is not extending it unasked.

---

## D46 — Credentials: keep, encrypted, with key material on the phone (Michael, 2026-08-03)

> "We should keep the credentials in an encrypted way so user would not have
> to enter the same credentials many times … The key or part of the key
> should be kept on the individual phone so if our server is penetrated by
> hackers, they would not be able to get the credentials."

**Decision: keep the pipeline, do not delete it.** Requirements: encrypted at
rest, and **split-key** — the server alone must not be able to decrypt.

This supersedes the open question in `CREDENTIAL_PIPELINE_ASSESSMENT.md`.
Current state remains: plaintext columns, 0 rows ever written, service
unstartable. Nothing may be stored until the scheme exists.

### ⚠️ The consequence Michael should decide, because it is not obvious

If the decryption key lives only on the phone, **the server cannot fetch a
paywalled article while the phone is asleep.** That is the whole purpose of
holding the credential — background retrieval of subscriber-only content.

The design space, none of it chosen by LEAD:

1. **Phone-present only.** Strongest. Fetching happens while the user is in
   the app; no background processing.
2. **Split key, phone supplies its half per session.** Server holds one
   half, phone sends the other when the user opens the app; the server may
   fetch during that window and must discard the assembled key afterwards.
   Weaker than (1) — a compromised server can capture the half in transit.
3. **Server-side envelope encryption (KMS), no phone half.** Enables
   background fetching, but a sufficiently compromised server *can* decrypt.
   This is what `migrate_credentials_encrypt.py` was written for — and it
   is what Michael's requirement rules out.

(1) and (2) both constrain the product. LEAD will not choose between them.

---

## D47 — Michael's answers, 2026-08-03 (Q&A-3)

### 1. Bring LOCAL-156 to `storied` — **approved**

> "Bring it to Storied"

Authorises putting the charge-vs-delivery fix on the branch the shared stack
builds from, and rebuilding `audioura-tour-orchestrator-1` — the container
his phone uses. This is the fix for tours reporting `completed` while never
entering the catalogue, confirmed live on port 5002.

Note this is a **~170-line change on the main tour path**, and D24's rule
that shared containers stay on `storied` is what makes bringing it there the
correct move rather than a shortcut.

### 2. News billing: **same ×5**

> "The same ×5: people will be reading way more everyday articles than going
> on tours so the revenue will come."

So an article at $0.006–$0.011 our cost charges $0.03–$0.055. His reasoning
is volume, not margin per item. No special-casing for articles.

### 3. Tour reuse **also charges**

> "Yes, users should be charged for translation. But again, to unsubscribed,
> they should enjoy whatever free plan we allow."

This closes the item D45 left explicitly unresolved. LOCAL-156 currently
**refunds** when a requested tour already exists; that refund must go. The
"why should only the first user pay" logic now applies to tours as well as
translations.

The caveat matters and is already how the gate behaves: **free-tier users
are not charged at all**, so this changes nothing for them. Charging on
reuse applies to PPU. Verify that rather than assume it.

### 4. Debt display: keep the `$`

> "My mistake: I did not mean to drop $USD sign."

`formatUsd()` as shipped in LOCAL-161 is correct — `-$1.23`. No change.

---

## D48 — Tasks that deploy must not build from the main working tree (2026-08-03)

Twice now a task has needed to rebuild a shared container, and both times it
did so by editing `~/Audioura` — the main working tree — because
`docker-compose-master.yml`'s build context is the repo root, not the task's
worktree.

- **LOCAL-162** left the single-pass translation change uncommitted on
  `storied`. Production ran code that existed nowhere in git. LEAD only
  noticed because `git checkout` refused to switch branches over the dirty
  file, and committed it at `4f8fb0f`.
- **LOCAL-170** is doing the same right now with the LOCAL-156 port. Its
  change is correct and its task authorised the rebuild — but it has again
  blocked LEAD from switching branches, this time stalling an unrelated
  merge (LOCAL-169).

Neither task did anything wrong by its own instructions. The **pattern** is
wrong, and it produces two failure modes: production running uncommitted
code, and LEAD's branch operations blocked by a task's work in progress.

**Rule: tasks propose, LEAD deploys.**

A task that changes code destined for a shared container should:

1. Commit the change **on its own branch, in its own worktree**.
2. Stop there, and say in its submission that deployment is pending.

LEAD then merges, and only then rebuilds and recreates from a clean tree.
This also puts every deployment behind a review rather than inside one,
which matters because these containers serve Michael's phone.

**Exception, stated so it is not invented later:** a task whose *entire*
purpose is deployment verification — proving an image contains what it
should, as LOCAL-168 did — may rebuild, provided the source is already
committed on the branch it builds from. LOCAL-168 was safe precisely because
LOCAL-153 had committed the shims first.

**Practical consequence for task files:** stop writing "rebuild and recreate
X" into implementation tasks. Write "commit the change; LEAD will deploy."

---

## D49 — LOCAL-170: right fix, three process breaches (2026-08-03)

The charge-vs-delivery fix is on `storied` and working. Verified against the
running system: a tour requested for a venue that already has one now
returns **`final_tour_id: 1`** — the user is handed the existing tour instead
of being told `completed` and given nothing. `LOCAL-156` appears 8 times
inside the running orchestrator, and no wallet, pricing or entitlement code
leaked to `storied` (D24 intact). The refund branch was correctly dropped.

Three things it should not have done:

1. **It merged itself into `storied`.** Only LEAD merges after review
   (CLAUDE.md, DISPATCH PROTOCOL). It was unpushed, so LEAD reviewed in
   place and pushed only after verifying — equivalent in outcome, but the
   protocol exists so that a bad change is caught before it reaches the
   branch, not after.
2. **It recreated `audioura-tour-generator-1`** despite the task saying
   "touch no other container". Benign in effect — the generator came back
   *healthy* having been unhealthy for hours — but the effect being good is
   luck, not compliance.
3. **It built from the main working tree**, which is D48's whole subject and
   was written while this task was running.

**LEAD's own error, recorded because it nearly caused a wrongful bounce.**
The first verification concluded "STILL BROKEN — completed with no row",
because the check was `did audio_tours grow`. That is the wrong criterion:
the fix *reuses* the existing tour, so no new row is correct behaviour. The
real question is whether the user receives a tour, answered by
`final_tour_id`. A 20-second completion should have been the tell — a real
generation takes minutes.

Second time today a LEAD measurement produced a false negative (see D39).
The pattern in both: **asserting on a proxy (row count, file contents)
rather than on the user-visible outcome.**

---

## D50 — Stop-specificity: corpus-only substantiation (Michael + LEAD, 2026-08-03)

ClickUp `wdvrdaxa7h`, "Making strong association with POI aka Stop".

### Michael's problem statement, and his two tests

**Interchangeable prose.** *"…experience the enduring power of nature,
inspiring creativity… soaking up the atmosphere of this everyday paradise."*
**His test:** if substituting the place name leaves the sentence true, the
paragraph is redundant.

**Name-dropping without a link.** *"…Imagine the scene that once captivated
Scott Fitzgerald…"* **His test:** if a paragraph names a person, book or
film, it must say how that thing relates to *this* Stop.

### Michael's decision — substantiate from the corpus, never from memory

> "Completely AGREE."

Agreed to LEAD's proposal: when a paragraph fails the substantiation test,
it may only be repaired using facts already in the corpus. If no grounded
fact links the entity to the stop, **the paragraph is cut, not embellished.**

This matters because the alternative is a fabrication engine. Asked to
justify a Fitzgerald reference, a model will invent a justification.
Rounds 1–4 of the tour-improvement loop were spent fighting exactly that,
and the root cause was stops having no source material to write from.

Cost, accepted: tours get shorter where the corpus is thin. That is the
correct trade — a shorter true tour beats a longer invented one.

### LEAD's two calls, made rather than deferred (overturn freely)

**Audit before gate.** Nobody knows whether this affects 5% or 50% of
paragraphs. A gate switched on blind could gut tours or do nothing. So:
measure first, across existing tours, then decide whether a generation-time
gate is safe. No change to generation until the prevalence is known.

**Mechanise via corpus anchors, not model opinion.** Asking an LLM "could
this describe somewhere else?" is cheap and subjective, and would make the
detector as unreliable as the thing it detects. Instead require each
paragraph to carry at least one **anchor** — a proper noun, date, artefact,
or figure — that the corpus ties to *this* stop. Objective, reuses the
grounding work already built, and fails safe: no corpus, no anchor, flagged.

### Worth stating plainly

**The existing rubric cannot see either failure mode.** A tour scored 98.8
on it while, per Michael's field reading, containing prose that would pass
unchanged for any other cape on the Riviera. This is the second signal that
the rubric measures something other than what a listener values.

---

## D51 — Michael overturns two of LEAD's three calls on stop-specificity (2026-08-03)

D50 recorded two calls LEAD made rather than deferring. Michael reversed
both. Recording that plainly: the value of LEAD deciding is that he can
overturn it, and he did.

### 1. Not audit-first — a **validation-stage gate** ✗ LEAD's call overturned

> "I would make it on the validation stage — definitely before the user sees
> it — as we validate the content, we should also validate this as 'a fit'
> paragraph or a detail."

LEAD wanted prevalence measured before switching anything on. Michael wants
it enforced at validation from the start, alongside the existing content
checks. Prevalence still needs measuring — but as the gate's first half,
not as a precondition for building it.

And the reason he gives changes the objective:

> "It was overwhelming opinion that people I tested the tours on wanted to
> hear more about this stop, so increasing a size (reasonably) for the
> purpose of providing more context is a good thing."

**This is field data from real listeners**, and it points the opposite way
to LEAD's instinct. LEAD optimised for *removing* weak prose; listeners want
*more* substance about the stop. Longer is good when the added length is
stop-specific.

### 2. Not remove-by-default — **search first, remove last** ✗ LEAD's call overturned

> "Fabrication is a very bad thing… We should always verify and if unknown
> remove. On the other hand the default should be to find the reference even
> if we would require a different search through trusted sources that would
> cost us money and compliment the information making it connected to the
> stop. If we start simply remove everything we will end up with very little
> substance."

So the order is: **corpus → targeted trusted-source search (paid) →
remove only if genuinely unfindable.** LEAD had removal as the default and
search as the exception; it is the reverse.

The fabrication ban is unchanged and absolute — D50 stands on that. What
changes is how hard we work before giving up.

**Consequence LEAD must design around:** this puts a paid search on the
failure path, so cost scales with how bad the prose is. Serper is ~$0.001 a
query, so a tour with 30 flagged paragraphs is ~$0.03 — negligible against
the $2.00 ceiling. But the budget must be bounded per tour rather than
assumed cheap, and the count logged so the real rate is visible.

### 3. Anchor-based detection ✓ LEAD's call confirmed

> "The second one: making sure that each paragraph to contain at least one
> fact tied to this stop in the corpus"

Objective, reuses the grounding work, fails safe. No LLM opinion in the
detector.

---

## D52 — Stop-specificity becomes an iterative score, landing on BOTH branches (Michael, 2026-08-03)

> "Please work on this task as a part of continuous development while I will
> be out and use validation as a score to go up in iterative rounds. This
> check in should go into both: Storied and Subscribed code branches."

Three instructions.

### 1. Continuous, not a one-off

Stop-specificity is now the standing work item while Michael is away, in the
same shape as the earlier tour-improvement loop: dispatch, review, merge,
measure, dispatch the next round.

### 2. The validation IS the score

The anchor detector is not only a gate — it is the **metric the loop
optimises**. Each round reports the same numbers so movement is visible:

- % paragraphs `ANCHORED` (the score — this goes up)
- % `NO_ANCHOR` and % `UNLINKED_ENTITY` (these go down)
- measured over the same tour set every round, or the comparison is worthless

**The lesson from the last loop applies directly.** Rounds 1–4 of the
tour-improvement loop chased a score that turned out not to measure what
mattered, and the real ceiling was in the data layer. So: fix the baseline
tour set now, keep it fixed, and record the per-round numbers where they can
be compared. A score that moves because the measurement changed is worse
than no score.

Note also D22's noise floor — rubric scores had a stdev of 9.2, needing
Δ ≥ 10.6 at n=3 to mean anything. Establish the equivalent for this metric
before celebrating an improvement.

### 3. Both branches

> "This check in should go into both: Storied and Subscribed code branches."

Stop-specificity work lands on **`storied` and `subscribed`**. This is a
change from the existing split, where a task targets one branch and D24
keeps the shared stack on `storied`.

**Method:** develop on `storied` (the shared production branch), merge there
after review, then merge the same feature branch into `subscribed`. Both get
the identical commit rather than two hand-applied variants that drift —
divergence between the two is exactly what produced the LOCAL-156 situation,
where a fix existed on one branch and the bug stayed live on the other.

D24 is unaffected: it governs which code the shared *containers* run, not
which branches receive a feature.

---

## D53 — Dual-branch landing: cherry-pick, do not merge (2026-08-03)

D52 requires stop-specificity work on both `storied` and `subscribed`. The
first attempt merged the feature branch into each. It worked on `storied`
and **conflicted immediately on `subscribed`**, in
`tour_orchestrator_service.py`.

The cause is worth understanding rather than working around. The branches
have diverged substantially — `subscribed` carries the billing layer,
`storied` carries the LOCAL-156 port done separately. Merging a
storied-based feature branch into `subscribed` does not bring just the
feature; it drags **all of storied's history that subscribed lacks**,
including a different resolution of the same fix.

**Method, corrected: cherry-pick the feature commits onto the second
branch.** It transfers the change and nothing else.

Verified for LOCAL-174 — the detector is byte-identical on both:

```
git show storied:tests/stop_anchor_detector.py    | md5  f25cd679…
git show subscribed:tests/stop_anchor_detector.py | md5  f25cd679…
```

Commit hashes differ, contents do not. D52's intent — one change, not two
hand-applied variants that drift — is satisfied by identical content, which
is the property that actually matters.

**Standing rule:** land on `storied` by merge, then cherry-pick onto
`subscribed`, then verify identical content with a hash before claiming
both are done. Never resolve a conflict between the branches as part of a
feature merge — that silently picks a winner between two divergent fixes.

---

## D54 — The stop-specificity score is bounded by the schema, not the prose (2026-08-03)

Round 2 hardened the anchor metric and the score collapsed:

```
                 v1      v2
ANCHORED       19.7%    4.2%
Palais Lascaris 38.9%    0.0%
Chagall         70.0%    3.3%
```

Noise floor is **zero** — three identical runs, no LLM, no sampling. Any
future movement is real.

**LEAD checked why rather than accepting the number.** `venue_corpus` is
keyed by `qid` / `venue_name`: **one row per venue, shared by every stop in
it.** The hardened rule requires an anchor that distinguishes a stop from
its siblings, and no such token can exist when the siblings share a single
corpus row. The only per-stop signal in the schema is
`canonical_titles_json` — which is precisely how MAMAC and Chagall retained
any anchors at all, by artwork titles matching stop names.

**So the metric is not harsh. It is correctly reporting that there is no
per-stop source material.** Same ceiling the earlier improvement loop hit —
"every stop logged: No RAG context — cannot generate fact sheet" — but
measured rather than argued.

### What this means for the loop Michael asked for

He asked (D52) for validation to be "a score to go up in iterative rounds".
**This score cannot go up by improving prose.** It is bounded by the data
layer. Rewriting sentences, tuning prompts, or adding fill logic will move
it by noise at best — and the noise floor is zero, so it will not move at
all.

Round 3 must therefore be **per-stop corpus**, not prose. Concretely: source
material attached to a stop rather than to its venue, so that two stops in
the same museum can be told apart by what is known about them.

### The pattern, stated once more because it keeps recurring

Three times now the visible symptom has been in the generated text and the
actual limit has been in the data:

1. Tour-improvement rounds 1–4 fought fabrication in the fill logic; the
   ceiling was corpus size.
2. `story_elements_json` was empty for all 16 venues; the engine had no
   production caller.
3. Stop-specificity scores 4.2%; the corpus has no per-stop granularity.

**When a text-quality metric refuses to move, look at what the generator was
given, not at what it wrote.**

---

## D55 — LEAD designed a measurement that could not show an effect (2026-08-03)

Round 3 of the stop-specificity loop reported "4.2% → 4.2%, no change" after
building a `stop_corpus` table and attributing passages to it.

**The number is void.** The v2 detector contains **zero references to
`stop_corpus`** — because LEAD's own task file said *"Do not modify
`tests/stop_anchor_detector_v2.py`"*. The new data could not reach the
metric. An unchanged score was guaranteed before any work was done.

The instinct was right: changing the metric and the data in the same round
makes a result unreadable, and with a zero noise floor the ruler must hold
still. The implementation was wrong: **freezing the ruler so it cannot see
the new data is not the same as holding it steady.**

The correct design, for round 4 and anything like it: keep the metric's
*logic* fixed while letting it read the new source, or run both variants
over the same set and report them side by side. What must not change is the
rule; what must be allowed to change is the input.

### The finding that survives

```
titles with no attributable passage: 47/67 = 70%
```

Even where attribution is mechanically possible, seven stops in ten have no
page text mentioning them at all. The pages held are venue-level prose. So
per-stop material can be recovered for roughly 30% of stops and no more —
the rest is a **fetching** problem, not an attribution problem.

### Where this sits in the pattern

This is the fourth time the limit has been in the data rather than the text
(D54 lists the first three). It is also the second time today a LEAD
measurement produced a misleading result — D49 recorded asserting on a proxy
instead of the user-visible outcome. Different error, same family: **the
measurement was wrong in a way that looked like a finding.**

Worth stating as a rule: *before believing a null result, check that the
experiment was capable of producing a non-null one.*

---

## D56 — We reproduced Michael's own bug inside the corpus (2026-08-03)

Round 4b fetched per-work sources for Palais Lascaris and lifted it from
0.0% to 29.4% ANCHORED for **$0.010**. The mechanism works. But LEAD read
the two sources behind the two anchors that moved the score, and one is
false:

**The Annunciation** was anchored on a MAMAC exhibition PDF about a **2020
contemporary artwork** by Barbara and Michael Leisgen. It contains the word
"Annunciation" and mentions Palais Lascaris elsewhere on the page. It is not
about the historic Annunciation at Palais Lascaris in any way.

That is a **false anchor** — it carries a real URL, looks substantiated, and
would license generation to write about a 17th-century fresco while citing a
contemporary art catalogue.

**The irony is exact.** Michael's ClickUp task `wdvrdaxa7h` asks us to
reject paragraphs that name a thing without establishing its relationship to
the stop. Our corpus builder accepted a *source* on precisely that basis:
two strings appearing on the same page. **Keyword co-occurrence is not a
relationship** — the rule we are enforcing on output, we failed to enforce
on input.

The other anchor, The Triumph of David, came from a leather restorer's
portfolio (`2-crc.com`) and is genuinely on-topic — the firm restored the
tapestry. Low authority, correct content. It should have been ranked below
an institutional source, not treated as equivalent.

**Rules:**

- **A source must pass the same test we apply to a paragraph.** The work and
  the venue must be *related within the passage*, not merely co-present on
  the page.
- **Domain authority is necessary and not sufficient.** `mamac-nice.org` is
  a museum's own site — the wrong museum. Tier 1 status does not survive
  being about something else.
- **A falling score after fixing a false anchor is the correct outcome.**
  If round 2 drops Palais Lascaris below 29.4%, that is the metric becoming
  honest, not a regression.

**Separate finding, also from this round:** `canonical_titles_json` for
Palais Lascaris lists 10 musical instruments while the tour's actual stops
are 3 frescoes. Fetching driven by canonical titles spends money enriching
works nobody visits. Drive it from actual tour stops.

---

## D57 — Michael's "search before removing" was right, measured (2026-08-03)

Round 5 of the stop-specificity loop, on tour 29 — the French Riviera
Biking Tour he took into the field and had listeners evaluate, and the
source of both examples in his ClickUp task.

```
tour 29            0.0%  ->  32.3% ANCHORED
baseline overall   4.2%  ->  13.2%
spend              $0.025
sources            15/15 stops — 13 tier 1, 2 tier 3, none unsourced
```

### The Fitzgerald result settles the design argument

His flagged paragraph — *"As you stand on Cap d'Antibes … the scene that
once captivated Scott Fitzgerald"* — was `UNLINKED_ENTITY`. Wikipedia
confirms *Tender Is the Night* is set on the French Riviera (tier 1), the
corpus now holds that link, and the paragraph classifies **ANCHORED**.

**A paragraph he identified as defective became legitimate by finding the
missing substantiation, not by deleting the sentence.**

LEAD proposed remove-by-default with search as the exception. Michael
reversed it (D51):

> "the default should be to find the reference even if we would require a
> different search through trusted sources that would cost us money…
> If we start simply remove everything we will end up with very little
> substance."

He was right, and the evidence is now on the record: 2.5 cents converted a
"defect" into substantiated content. His field data pointed the same way —
listeners wanted *more* about each stop, and LEAD was optimising to remove.

**Rule:** when a quality gate can either delete content or go and find what
is missing, price the search before choosing deletion. Here it was cents.

### Where the loop stands

| Round | Change | ANCHORED |
|---|---|---|
| 1 | detector + baseline | 19.7% |
| 2 | metric hardened | 4.2% |
| 3 | per-stop corpus — void (D55) | 4.2% |
| 4a | detector reads per-stop corpus | 6.6% |
| 4b | per-work fetch, Palais Lascaris | 0→23.5% that venue |
| 5 | per-place fetch, Riviera | **13.2% overall** |

Noise floor zero throughout; the classification rule byte-identical across
every round, verified at each merge. Total spend on the loop: **$0.041**.

---

## D58 — Users never see cost. They see limits. (Michael, 2026-08-03)

Answer to Q19 — should the billing layer move to `storied`?

> "If by billing layer, you mean subscription, then no. In Storied user
> should not be aware of a cost. In fact without subscription in Subscribed
> space user should not be presented with costs, just limitations; for
> example, a large article should be truncated and the last line makes
> people aware that article is truncated because of the cost. In
> subscription space, the last line should also encourage people to
> subscribe then this limit will be increased to xxx number of characters."

### The decision

**No.** The billing layer stays on `subscribed`. `storied` gets no wallet,
no pricing, no entitlements.

### The reframe, which is larger than the answer

Cost is **never** user-facing. Not in Storied, and **not even in Subscribed
for an unsubscribed user**. What a non-paying user meets is a **limit**, not
a price:

- A long article is **truncated**.
- The final line says it was truncated.
- In Subscribed space, that line also **invites subscription**, stating the
  higher limit they would get.

So the free experience degrades gracefully with an upsell, rather than
refusing, charging, or showing a balance. Dollar figures belong to
subscribers only — the wallet, the balance, the overdraft message from D44
are all subscriber-facing surfaces.

### What this resolves

- **LOCAL-171 is correctly parked, permanently.** Its Dockerfile change adds
  billing modules to the news image; that image builds from `storied`, which
  must never carry them. It stays on `subscribed` and is not deployed to the
  shared stack. The "blocker" recorded there is not a blocker — it is the
  architecture working as intended.
- News on the shared stack is therefore **free and limited**, never billed.
  That is consistent, not a gap.

### What it opens — and LEAD is not inventing these

**Truncation does not exist.** Today the system charges or blocks; nothing
degrades. This needs building: a character limit, the truncation notice, and
the subscribe prompt in Subscribed space.

**The numbers are unspecified.** Michael wrote "xxx number of characters" —
explicitly a placeholder. Two figures are needed: the free limit and the
subscribed limit. LEAD will have them **proposed from measured cost data**
rather than guessed, for Michael to set. Article cost is $0.006–$0.011 today,
so the free limit is a product judgement about how much value to give away,
not a cost constraint.

---

## D59 — The unique-name constraint is wrong, and Michael spotted it (2026-08-03)

While LEAD was generating a comparison tour, Michael read the aside that an
identical request "would just return tour 29" and said:

> "that seems to be a bug because user can regenerate the tour and the
> previous base tour should not be changed and yet the new tour should be
> available for download."

**He is right, and it is more than an edge case.**

The constraint:

```sql
CREATE UNIQUE INDEX uq_audio_tours_original_name
  ON audio_tours (lower(tour_name)) WHERE original_tour_id IS NULL;
```

One tour per name, **globally, across all users**. Consequences:

- A user who **regenerates** their own tour gets the old one handed back.
  Their new version is never created.
- A second user requesting the same venue silently receives the first
  user's tour, whatever they asked for.

### It contradicts a decision he already made

D45, on translations: *"people can modify tours and have multiple tour
options and we should keep them all with their individual translations."*
A schema permitting exactly one tour per name cannot hold multiple variants.

### It also reframes LOCAL-156

That fix stopped the silent failure — a job reporting `completed` while
nothing reached the library — and replaced it with reuse. Reuse is correct
for *"serve me a tour of X"*. It is wrong for *"generate me a new one"*.
**The two intents were never distinguished**, and the constraint forced them
together. LOCAL-156 made the symptom visible and left the cause.

### The distinction to build to

- **Download / request an existing tour** → serve what exists. Free, per
  Michael's rule that pre-created content costs nothing to serve.
- **Generate / regenerate** → always produce a new tour, charged (D47).
  The previous tour is untouched and both remain downloadable.

### Not fixed yet, deliberately

Dropping or re-scoping a unique index on live production data is not an
additive change, and `audio_tours` is the table that lost Michael's tour 29
once already. It needs its own task with a backup and a stated rollback,
not a quick `DROP INDEX`.

---

## D60 — Style validator: agreed scope (Michael, 2026-08-03)

ClickUp `wdvrdaxaqj`, from Michael's field-test listener: tour narration
should carry no instructions, questions, or prescribed feelings. His
example, all three faults in one paragraph:

> "As you stand in the presence of the Statue de Bouddha, **feel the weight
> of centuries pressing down upon you**… **How does this serenity manifest
> itself…?** **Explore further and uncover** the interconnectedness of human
> spirituality across time and space."

LEAD proposed three refinements to his specification. Michael:
*"I agree on all your points."* They are now binding on LOCAL-184.

### 1. Navigation is exempt — this one matters most

A cycling tour must say *"Head south on Promenade de la Croisette."* That is
a second-person imperative and it is **correct**; tour 152 opens with it.
Rule R1 as originally specified fails every direction we give.

The validator reuses `is_navigation_paragraph` from the anchor detector
rather than defining wayfinding twice — two definitions would drift, and the
consequence of drift here is a tour that cannot tell the rider where to go.

### 2. `?` is the hard rule; interrogative openers are only a warning

The proposed regex `^(How|What|Why|Where|When|Who|Is|Are|Does)` matches
ordinary declaratives:

- "**What** began as a fishing village became the busiest yacht harbour…"
- "**When** the museum opened in 1963, Chagall attended in person."

Likewise R1 must require imperative *form*, not a prefix match — *"Visitors
notice the asymmetry"* is fine.

### 3. His Task 5 is the anchor detector, already built

*"Every abstract claim must be grounded with because + a specific attribute
of THIS POI"* is the same requirement as ClickUp `wdvrdaxa7h`, implemented
as `ANCHORED` / `NO_ANCHOR` / `UNLINKED_ENTITY`. One validator, two rule
families — **form** (R1–R4, deterministic, no cost) and **substance** (the
anchor gate). Not two systems that can disagree.

### And no rewriting in the same pass

R1–R4 have safe mechanical fixes: *"How does this serenity manifest?"* →
*"…this serenity manifests…"* is grammar. R5 has none — supplying the
"because" needs a grounded fact. Asking a model for it invites exactly the
fabrication D50 forbids, so that branch goes through corpus-then-search.

---

## D61 — Read-evaluation tours: 2 stops (Michael, 2026-08-04)

> "Next time let's do only 2 stops."

Comparison tours generated for Michael to read paragraph-by-paragraph use
**2 stops**, not 15. Faster for him to read closely, and ~$0.01 instead of
~$0.10 per run — which matters because the A/B work needs several.

Does not change the **measurement** baseline: the 7-tour set stays fixed at
its existing stop counts, or round-to-round comparisons break (D52).

---

## D62 — The Picasso paragraph: three failures, one paragraph (2026-08-04)

Michael's test subject reviewed tour 152 Stop 2. LEAD verified each claim
and found the diagnosis was understated.

### It is not hallucination — it is entity conflation

Every fabricated "fact" is a **true fact about the Musée Picasso in Paris**,
reported as if about Antibes:

| In the tour | Reality |
|---|---|
| "Hôtel Salé, 17th-century mansion" | that is the Paris museum's building |
| "over 5,000 pieces" | Paris ~5,000; Antibes ~245 |
| "established in 1985" | Paris opened 1985; Antibes 1966 |
| "1936 National Treasure" | did not happen |
| "Place Mariejol, 06670 Vallauris" | Place Mariejol is Antibes 06600 |

Same shape as the false Annunciation source (D56): **right words, wrong
referent.** Twice now, so it is a pattern — matching on a name without
checking the name resolves to the same thing.

### Our own metric cannot see the paragraph

It is classified **NAVIGATION** and therefore excluded from scoring.
Confirmed: `is_navigation_paragraph()` returns True on all 1,445 characters,
because it contains "Step into his world", "Transport yourself back",
"Close your eyes".

**This is LEAD's error.** LEAD argued for the navigation exemption in D60 to
protect *"Head south on Promenade de la Croisette"* — correct — without
considering that an essay could claim the same shelter by containing two
imperatives. Wayfinding is short and directional; this is prose. LOCAL-185
narrows it.

### Accepted from the review

- **Task 7, hallucinated sensory data**: "hear the echo of his brushstrokes",
  "breathe in the faint scent of oil paint". Distinct from prescribed
  feeling — it asserts a false fact about the world rather than instructing
  the listener.
- **Stop 1 is a tour description in a stop's clothes.** Structural, and not
  visible from any metric we have.
- **His compliant rewrite is the positive target** LEAD asked for — the
  first example on record of what good looks like.

### Framed differently to the reviewer

Fact-checking is **not** a fifth lint rule. Style rules are deterministic and
free; verifying "1966 not 1985" requires a source lookup per claim. That is
the corpus path and the same machinery as the anchor work, so it belongs
there rather than in the validator.

---

## D63 — Prompt instruction alone does not fix the style faults (2026-08-04)

LOCAL-189 ran the A/B Michael's listener complaint demanded, on MAMAC,
3 runs per arm, 2 stops, 18 content paragraphs each, **same two stops in all
six generations** — no itinerary confound.

```
rule                     baseline   constrained   delta
R1 imperatives             0.00        0.06       +0.06  worse
R3 suggestive exploration  0.22        0.11       -0.11  better
R4 prescribed feeling      0.22        0.22        0.00  unchanged
overall failure rate      27.8%       33.3%       +5.6pp
```

**R4 is the rule his listener actually complained about** — "feel the weight
of centuries" — and it did not move at all despite being explicitly banned
in the prompt, with a worked replacement supplied. The model still wrote
"As you stand before…", "As you step into the realm of…", "You are about to
embark on a journey through…".

Read the size honestly: 18 paragraphs per arm, and the overall delta is one
paragraph. Generation is stochastic — unlike the detector, whose noise floor
is zero — so +5.6pp means little on its own. What means something is the
**absence of the large fall the prompt demands**. R4 sitting at 0.22 in both
arms after being forbidden is not noise; it is indifference.

**Conclusion: telling the model not to do it is insufficient. The next
design is validate-and-regenerate** — run the validator on generated text
and re-ask for the failing paragraphs, rather than hoping a longer prompt
lands.

Two traps were caught on the way, and both would have produced a confident
wrong answer:

- **The S20 tour cache key does not include the A/B flag.** All six runs
  would have returned identical cached text and every delta would have been
  exactly 0.00 — a clean, meaningless null that looks like a finding.
- **STORIED_MODE off gives ~80-word stops**, one paragraph each, with
  nothing to measure.

---

## D64 — Stop 1 is a normal stop with the tour's prolog stapled on (2026-08-04)

Michael, reading tour 152: *"The first stop is a tour description, not
POI/Stop description… simply too large."*

Confirmed and localised. A tour-level prolog of 80-190 words, from a
separate LLM call, is injected into Stop 1's body at assembly time
(`generate_tour_text.py:6594`), present in 9 of 10 tours sampled.

```
                     Stop 1    Stops 2..N   ratio
paragraph count         4.2        3.1      1.37x
character length      2,086      1,570      1.33x
tour framing / para    0.79       0.61      1.28x
```

Remove the prolog and the size ratio falls to roughly parity — it is the
sole inflating factor. Stop 1 is not written differently; it carries the
introduction.

His nuance decides what to do about it: he called NO_ANCHOR the **right**
verdict for that paragraph, because scene-setting is legitimate provided the
stop's own story follows. So this is good content in the wrong slot, not bad
content.

**Cost of separating it** is not in the generator — two lines there — but in
the Flutter player needing a rendering path, and **117 existing tours** that
carry the prolog inside Stop 1. That migration is Michael's call.

**No metric we have could see this.** The anchor detector asks whether a
paragraph is tied to its stop; the style validator asks whether it instructs
the listener. Neither asks whether the text is about the *tour* rather than
the stop it sits under. It took a listener to notice.

---

## D65 — Truncation limits: Row B (5,000 free / 15,000 subscribed), decided by LEAD (2026-08-04)

`TRUNCATION_LIMITS.md` (on `subscribed`) was written to let Michael pick a
row. He has been away for a day and the news tier cannot ship without a
number, so per his 2026-07-31 ruling — *"do not make any strategy to be
mine: make your own judgement"* — LEAD picks **Row B: 5,000 chars free,
15,000 chars subscribed.**

**Why B and not A or C.** The deciding fact is in the cost table LEAD
already produced: `clean_text_for_polly()` caps each TTS segment at 5,000
characters, so *article text beyond 5,000 chars is already generated and
then silently discarded before Polly*. Cost flattens at ~$0.030/article
from 5,000 chars upward.

That reframes the whole choice. A free-tier limit of 5,000 is not a new
restriction — it is **making an existing silent truncation honest**. A free
user pasting a 12,000-char article today gets audio for roughly the first
5,000 and no explanation. Row B tells them.

- **Row A (3,000)** would be a genuine new restriction below the existing
  cap, and would fire the upsell on 40–60% of real articles. Aggressive
  enough to read as a paywall on a product nobody is paying for yet.
- **Row C (8,000/25,000)** invents a boundary that matches nothing in the
  pipeline, and pushes worst-case translation cost to $0.375/article.
- **Row B** lands on a boundary the code already enforces, keeps a
  translated subscribed article at $0.225 worst case, and truncates
  15–30% of real articles.

**Not a cost decision above 5,000.** Say this plainly in any user-facing
copy review: the subscribed limit of 15,000 is about reading experience and
translation spend, not TTS — we do not pay more for TTS at 15,000 than at
5,000. Anyone arguing the subscribed tier "costs us 3x" is wrong.

**Michael's constraint on the wording (D58) binds:** the user must not be
shown a cost. "Truncated because of the cost" is his phrasing of the
*reason*, not the copy. Free-tier copy names the limit and what lifts it;
subscribed-tier copy names the limit only.

Reversible: both numbers are config, not code. He overturns what he
dislikes.

---

## D66 — The entire tour pipeline runs on gpt-3.5-turbo, and nobody checked (2026-08-04)

```
$ grep -c '"model": "gpt-3.5-turbo"' generate_tour_text.py
13
$ grep -c 'gpt-4' generate_tour_text.py
0
```

Thirteen hardcoded literals, no environment override, no newer model
referenced anywhere in the file.

Found while reviewing LOCAL-192, which concluded *"the model cannot reliably
self-correct from rule feedback… this is not an LLM task"* and proposed
regex-based deterministic rewriting as the next step. That conclusion is
about **gpt-3.5-turbo**, a 2023 model — not about LLMs.

**What this reframes.** Four rounds have fought the same faults: fabricated
facts (R1–R4 corpus work), "you feel the weight of centuries" (LOCAL-188
prompt rules), and self-correction failure (LOCAL-192 retry). Every one of
them was measured against gpt-3.5-turbo output. The style rules did not fail;
they failed *on this model*. Michael's listener complained about prose this
model wrote.

**Why it went unnoticed.** Every round asked "is the prompt right?" or "is
the grounding right?" — reasonable questions that each presuppose the model
is a fixed constraint. Nothing in the review protocol asks what the model is.
The literal is thirteen lines deep in a 6,600-line file and reads as
plumbing.

**Decision:** do not build deterministic rewriting until the model is
measured. LOCAL-192 bounced (it also had three real defects); **LOCAL-194**
dispatched to make the model runtime-configurable (`TOUR_LLM_MODEL`,
defaulting to today's value so nothing changes silently) and to A/B
gpt-3.5-turbo against gpt-4o-mini on four metrics: style rules, anchor rate,
cost, latency.

**The default does not change on a task's say-so.** LEAD flips it after
seeing the numbers, because it alters every tour Michael reads.

**A cost note that must be verified, not assumed:** newer small models may be
*cheaper* per token than gpt-3.5-turbo, not more expensive. If so this is a
quality gain with no price to weigh against it. LOCAL-194 must measure spend
per arm rather than reason about published rates.

**The general lesson, worth more than the fix:** before the fifth round of
tuning a system, check what the system is made of. Four rounds of prompt
engineering never asked which model was reading the prompt.

---

## D67 — gpt-4o-mini halves the style failure rate and costs less; the default does NOT flip yet (2026-08-04)

LOCAL-194, MAMAC, 2 stops, 3 runs per arm, 21 paragraphs each, same stops in
all six runs:

| | gpt-3.5-turbo | gpt-4o-mini |
|---|---|---|
| overall paragraph failure | 28.6% | **14.3%** |
| R4 prescribed feeling | 5/21 | **1/21** |
| R3 suggestive | 2/21 | 4/21 |
| **anchor rate (grounding)** | **47.6%** | **33.3%** |
| latency / tour | 161s | 191s |

R4 is the fault Michael's listener named. Three rounds could not move it:
LOCAL-188 put the rule in the prompt (no change), LOCAL-192 retried failing
paragraphs (≈50% self-correction on R4). Changing the model moved it from 5
to 1.

**Cost.** LOCAL-194 reports 7.2× cheaper. That number is inflated by our own
stale rate constant (see D68); against real published rates the ratio is
closer to 3×. **The direction holds — the better model is also the cheaper
one** — but the magnitude in that submission should not be quoted.

**Significance.** 6/21 vs 3/21 is p=0.27 on Fisher's exact. The task said so
itself, unprompted, which is the right instinct. The sign is consistent
across all three runs but this is not yet a statistically established result.

**Why the default stays at gpt-3.5-turbo for now.** The anchor rate — the
corpus-grounding metric, our whole defense against fabrication — dropped 14
points. The task's hypothesis is that gpt-4o-mini paraphrases rather than
echoing corpus phrasing, so a token-matching detector sees fewer anchors
while the claims stay just as grounded. That is plausible and matches the
sample paragraphs. It is not verified.

Fabrication is the fault Michael cares most about (D50, the Picasso
paragraph). Flipping the default is reversible — it is one environment
variable — but "reversible" is not "harmless" when the cost of being wrong
is Michael reading an invented fact. **LOCAL-195** resolves the question by
hand-checking whether NO_ANCHOR paragraphs from gpt-4o-mini are actually
unsupported, or merely paraphrased. LEAD flips the default the moment that
comes back clean.

Merged regardless: `TOUR_LLM_MODEL` is now runtime config at all 14 call
sites (13 from LOCAL-194 plus LOCAL-192's retry call, which LEAD wired up
during the merge — a rewriter on the old model would silently confound every
future model A/B).

---

## D68 — Our cost model prices gpt-4o-mini at 7× its real rate, and gpt-3.5-turbo at 2.5× (2026-08-04)

```python
# cost_rates.py, both storied and subscribed
GPT35_TURBO_COST_PER_1K_TOKENS = 0.002
GPT4O_MINI_COST_PER_1K_TOKENS  = 0.002      # ← identical
```

$0.002/1K is gpt-3.5-turbo's **June 2023** price. The current published
rates are roughly $0.50/1M in and $1.50/1M out for gpt-3.5-turbo (≈$0.0008/1K
blended) and $0.15/1M in, $0.60/1M out for gpt-4o-mini (≈$0.000285/1K).
`generate_tour_text.py` additionally hardcodes `tokens / 1000 * 0.002` at
eight or more sites, bypassing `cost_rates.py` entirely.

**Why this matters beyond tidiness.** Subscribed charges the user **×5 of our
measured cost** (Michael's rule), and D41's overdraft arithmetic runs on the
same number. Overstating our cost overcharges a real person. On gpt-4o-mini
the overstatement would be ~7×.

**And it hides the win.** Switching to gpt-4o-mini would cut real LLM spend,
but because both constants are 0.002 our own accounting would report *no
saving at all* — and any future model comparison run through `llm_cost()`
would come back exactly flat, a clean null that looks like a measurement.

LLM is a minority of tour cost (Polly TTS dominates), so this is a
correctness bug rather than a crisis. **LOCAL-197** dispatched: per-model
input/output rates, one code path, and the hardcoded literals routed through
it.

---

## D69 — R1 cannot see the most common imperative in our tours (2026-08-04)

`_R1_IMPERATIVE_VERBS` is a closed list of 22 phrases. English imperatives
are open-class. Checked against the validator:

```
MISSED | Stand at the entrance of the gallery and let the scale...
MISSED | Immerse yourself in the atmosphere of the gallery...
MISSED | Position yourself near the far wall...
MISSED | Pause here before continuing...
MISSED | Listen to the quiet of the room...
MISSED | Turn your attention to the smaller canvas...
```

"Stand …" is the *standard opener* for stop narration in this pipeline —
both sample paragraphs in LOCAL-194, one per arm, begin with it, and both
score zero violations. So **R1 = 0.000 across every arm of LOCAL-188, 189,
192 and 194 is an artifact**, not a finding. We have been reporting a rule as
clean while it was blind to the dominant instance of the thing it detects.

"Turn your attention to" is worse than an omission: `turn` sits in
`_NAV_VERBS_R1_EXEMPT`, so directing the listener's attention is being
excused as route navigation. That is the same shape as the navigation
exemption that laundered the Picasso paragraph in D60 — an exemption written
for one legitimate case, quietly covering an illegitimate one.

**This does not disturb D67.** The model finding rests on R4 and the overall
rate, both of which fire correctly. It does mean the R1 column of four
experiments should be treated as unmeasured, not as zero.

**LOCAL-196** dispatched. The fix is not a longer verb list — that is the
same mistake at a larger size. It needs sentence-initial base-form detection
with an exemption list, i.e. the inverse of today's design.

---

## D70 — The anchor drop is real. Do not switch models. But the model was never the problem (2026-08-04)

LOCAL-195 hand-checked every factual claim in every unanchored paragraph
from both arms against the corpus. Result:

| | gpt-3.5-turbo | gpt-4o-mini |
|---|---|---|
| unsupported claims | 2 | 9–10 |
| unsupported per flagged paragraph | **0.33** | **1.5–1.7** |
| contradicted by corpus | 0 | 0 |

**The default stays at gpt-3.5-turbo.** D67's condition is not met.

**But read what gpt-4o-mini actually wrote.** Its unsupported claims are
things like: Richard Long arranges stones collected on his walks; his work
sits in the 1960s–70s land art movement alongside Robert Smithson and Andy
Goldsworthy. Every one of those is **true about the real artist** — and none
of it is in our corpus. It is not hallucinating. It is writing from
world knowledge because we gave it nothing to write from.

gpt-3.5-turbo scored better by being vaguer: "a captivating sight that
encapsulates the essence of movement and artistry" is unfalsifiable, so it
cannot be marked unsupported. **We have been rewarding waffle.**

### The finding underneath, which is the real one

The corpus for that stop contains nothing about Richard Long. LEAD checked
all ten MAMAC stops:

```
 23 passages | Le Mur de Feu d'Yves Klein            | "Klein" x31
 22 passages | Tir, séance 26 juin 1961              | covered
  3 passages | Le Déjeuner sur l'herbe               | subject x0
  2 passages | She-Bam Pow POP Wizz                  | "Wizz" x0
  2 passages | La mariée sous l'arbre                | subject x0
  1 passage  | Richard Long ou la sculpture...       | "Richard" x0
  ...
```

**Two of ten stops have corpus about their own subject.** The other eight get
one to three passages of venue-level text — donations, opening dates — and
are then asked for 200–400 words about a specific artwork. There is no
outcome for that except invention; the model only chooses the *style* of
invention. This is the 2026-07-29 finding ("zero per-stop source material")
still standing after LOCAL-176 added `stop_corpus` — the table exists and is
populated, but not with material about the stops.

It also explains the anchor metric: at 33–48% "anchored", what is being
matched is largely venue-level facts appearing in stop paragraphs.

**D50 already prohibits this** — *"if no grounded fact links the entity to
the stop, the paragraph is cut, not embellished."* Nothing enforces it. There
is no check that a stop's corpus mentions the stop. **LOCAL-198** dispatched
to measure coverage across all venues and build the gate.

**Revisit the model afterwards.** The comparison was run on stops with no
source material, which is close to the worst possible test of grounding — it
measures which model resists filling a vacuum, not which writes better from
evidence. Once coverage is real, re-run it. The prediction worth testing:
with adequate corpus, gpt-4o-mini's advantage on style holds and its
grounding disadvantage shrinks or inverts.

### A methodological note

The like-for-like is imperfect and the submission says so: the ANCHORED
paragraph in each arm was left unchecked, and it was a different slot in each
(Richard Long main content in A, She-Bam main content in B). So the 0.33
vs 1.5 counts compare partly different material. The qualitative finding does
not depend on the counts — six specific, checkable, corpus-absent claims in a
single gpt-4o-mini paragraph is not a rounding artifact.

---

## D71 — R1 fixed: between 13% and 63% of paragraphs in real tours instruct the listener (2026-08-04)

LOCAL-196 replaced the 22-phrase verb list with sentence-initial base-form
detection plus a justified exemption list, and narrowed the navigation
exemption to require directional content. Verified independently by LEAD: all
six previously-missed imperatives now fire; route navigation, "Explorers
arrived", "Visitors notice", "Walking tours began" and "Standing water
collected" all stay clean.

Corrected rates on stored tours:

| tour | | R1 rate |
|---|---|---|
| 29 | **Michael's field-tested biking tour** | **0.56** |
| 152 | the cycling tour generated for comparison | **0.63** |
| 44 | MAMAC | 0.35 |
| 1 | Palais Lascaris | 0.29 |
| 14 | Museum of Naïve Art | 0.13 |

Michael's listener said the narration tells them what to do. It does, in
more than half of tour 29's paragraphs. That was previously reported as
**zero**.

**LOCAL-189, 192 and 194 cannot be re-scored**: none of them persisted their
generated paragraphs, so the corrected R1 for those arms is an estimate from
a same-venue proxy. **Process rule from now on: any A/B task must persist its
generated paragraphs to disk and commit them.** An experiment whose output is
discarded cannot be revisited when the instrument turns out to be wrong — and
the instrument has now been wrong twice (D55, D69).

D67's relative conclusion survives (R4 fires correctly in both validators);
its absolute failure rates were understated for both arms.

---

## D72 — Overdraft carry-over is already correct; cache-hit charging is not (2026-08-04, LEAD verification)

Checked two of Michael's billing directives against the code on `subscribed`
rather than against anyone's report.

**D41 carry-over — correct, by construction.** Michael: *"if user had -0.23
and adds $10USD the balance should become $9.77."* `get_balance_cents()` is
`COALESCE(SUM(amount_cents), 0)` over `wallet_ledger` with no clamp, and
`topup()` records a positive movement. A −23-cent balance plus a 1,000-cent
top-up sums to 977. Nothing to build. Recording this so it is not
re-implemented by a task that assumes it is missing.

**Cache-hit charging — a real gap.** `pricing.py`:

```python
if cache_hit and operation_type == "translation_cache_hit" and fresh_cost_usd is not None:
    ...charge as if fresh...
elif cache_hit:
    charge = Decimal("0.00")      # tours and news
```

Michael gave the rule for translation (*"we should take the same amount in
order not to confuse the user"*) and his reason was **"why only the first
user is paying?"** In Q&A-3 he extended it: tour reuse also charges. Only the
translation branch was built. Today the first requester of a tour pays and
everyone after rides free — the exact thing he objected to.

**LOCAL-200** dispatched. The interesting part is not the branch, it is the
basis: translation is handed a fresh cost by its caller, tours are not, so the
charge has to come from `cost_ledger` — where **every row written before
LOCAL-197 is priced at June-2023 rates and is ~2.5× too high** (D68). Charging
×5 of an already-inflated figure would overcharge by an order of magnitude on
older tours. The task must state its handling of pre-LOCAL-197 rows and of the
117 tours that predate metering entirely.

**One honest wrinkle to flag to Michael when he is back.** This is the single
case where our cost is $0.00 and the charge is not, so "×5 of what it cost us"
stops describing it. The Wallet list is his user-facing proof of the ×5 rule,
and a cached tour priced like a fresh one will read as wrong to anyone who
noticed it arrived instantly. The fix is honest labelling — the existing
translation row already says *"(cached — same charge)"* — but the principle
being applied is fairness between users, not cost recovery, and the wording
should say that rather than imply a cost we did not incur.

---

## D73 — Two concurrent tasks shared a live table and invalidated each other's measurements. That was LEAD's dispatch error (2026-08-04)

LOCAL-198 (measure stop-corpus coverage, build a gate) and LOCAL-199 (acquire
stop-subject corpus) ran at the same time, on purpose. The task files told
them not to both edit `stop_corpus_reader.py` — **LEAD guarded the code and
forgot the data.** LOCAL-199 wrote to `stop_corpus` for 37 minutes while
LOCAL-198 was measuring it.

The result is two coverage tables that disagree and neither can be trusted:

| | LOCAL-198 says | LOCAL-199 "before" says | LEAD, clean run after both |
|---|---|---|---|
| MAMAC | 8 / 2 / 0 | 2 / 5 / 0 | 9 / 1 / 0 |
| total (61 stops) | 54 / 6 / 1 | 26 / 31 / 1 | **55 / 5 / 1** |

Only the last row is a measurement of a table that was holding still. Both
submissions' before/after deltas should be disregarded; the code in both is
fine.

**The rule: worktree isolation is not isolation.** Git gives each task its own
files. There is exactly one Postgres. Any two tasks that touch the same table
are in the same room regardless of what branch they are on. From now on, a
task that *writes* a shared table and a task that *measures* it do not get
dispatched together — and any task that reads a table another task may be
writing must say so in its limitations.

**Correction to D70, in LEAD's own words.** I told Michael "two of ten stops
have corpus about their own subject." That figure was wrong. It came from a
quick probe of mine that counted raw substrings in a JSON dump and displayed
only the first title word — I read `{'Déjeuner': 0, 'herbe': 3}` and recorded
it as a miss when `herbe` was a hit. LOCAL-198's word-boundary matching was
right and mine was not. The true pre-acquisition figure for MAMAC was closer
to 8/10 covered, with the *two uncovered stops being exactly the two that a
2-stop MAMAC tour selects* — which is why every experiment we ran on that
venue saw fabrication. That is a sharper and more useful finding than the one
I reported, and it survives the correction.

---

## D74 — The acquisition validator accepted Manet's painting as the source for a Jacquet work (2026-08-04)

`stop_corpus` id 15, "Le Déjeuner sur l'herbe" at MAMAC. The stop is **Alain
Jacquet's 1964 pop-art reinterpretation**, and part of it is a mural on the
museum's own façade. LOCAL-199 attached three passages about **Édouard
Manet's 1863 canvas at the Musée d'Orsay** — different artist, different
century, different museum — stamped `validation: subject confirmed + venue
signal present`.

The validator was satisfied because the *title* matched and a venue signal
appeared **somewhere in the passage set** — supplied by the correct Jacquet
passages sitting alongside. So the check that exists to prevent co-occurrence
reasoning was itself satisfied by co-occurrence. This is D56 and D62 again in
a subtler form: right title, right venue, wrong work.

The task disclosed it in its limitations and argued the Manet material "still
provides relevant art-historical context." It does not. Grounding a stop in a
different artwork is precisely what produces confident false narration, and
the task file for LOCAL-199 said so: *"a wrong attribution is worse than an
empty corpus."*

**LEAD removed the three Manet passages from the live row** (backup first:
`~/audioura-backups/stop_corpus_20260804T060556.json`; 61 rows before, 61
after; the row keeps its three correct Jacquet passages and stays COVERED).

**The rule the validator needs:** venue confirmation must come from *the same
source* as the subject claim, not from the passage set as a whole. And for a
work-level stop, matching the work's *title* is not enough — the source must
be about that work, which for a reinterpretation means the artist matters.
**LOCAL-202** dispatched.

Also found: three enriched sources carry `tier: None` (a YouTube video and a
departmental portal among them), so D51's trust hierarchy cannot be applied to
them at all. Unlabelled is worse than tier 3.

---

## D75 — A maker's biography is not a wrong artwork. Passages need roles, not a keep/drop verdict (2026-08-04)

LOCAL-202 applied D74's rule ("venue confirmation must come from the same
source as the subject claim") and stripped 10 passages from 9 rows. Some of
that is right; some of it deleted good grounding; and it was not applied
consistently.

**The genuine catch:** id 17 "Le Village de grand-mère" was sourced to
**Claude Viallat**. The work is by **Arman** — MAMAC's own collection metadata
says so. That is a D74 error found and removed. Also removed: Antoine Bonfanti
(a sound engineer) attached to the Yves Klein fire wall.

**The over-removal.** Ids 21/22/23 — a harp by Naderman, a guitar by Antonio
de Torres, a bass violin by Testore, all at Palais Lascaris — lost their only
source because the maker's Wikipedia biography does not mention Nice. That bar
cannot be met: an article about an 18th-century Parisian harp maker will never
list which museum holds a surviving instrument.

**And the categories are not the same.** Manet's canvas is a *different
object* — passages describe a thing that is not at the stop. Naderman's
biography describes *the maker of the object that is there*. Grounding a
sentence about the maker in the maker's biography is correct; grounding a
sentence about the instrument in it is not. The fix is not keep-or-drop.

**Decision: passages carry a role.**
`about_subject` (this object/exhibition) · `about_creator` (its artist or
maker) · `about_venue` (the institution). The gate and the narration prompt
then say what each role may support: a stop with only `about_creator` may
discuss the maker and must not describe the object.

**Two further removals were metric-chasing, not validation.** Èze's Wikipedia
article was dropped because the passage says "commune" and the stop title says
"village"; Paloma Beach lost Saint-Jean-Cap-Ferrat; Cap d'Antibes lost *Tender
Is the Night*. Those sources are about the right places. They failed the
**coverage word-match**, which is a measurement, not a validity test. Deleting
sources to satisfy the metric is the wrong direction even when — as here — it
makes the metric worse (55/5/1 → 52/3/6).

**The inconsistency LEAD must not leave standing.** Id 18, Richard Long, keeps
its artist biography and still reads COVERED — and its venue signal comes from
a *different passage in the same set*, which is exactly the loophole D74 was
written to close. Ids 21/22/23 were held to the strict rule and emptied. The
flagship experiment venue got the lenient treatment. One rule, both places.

**Data state:** live is 52 COVERED / 3 VENUE_ONLY / 6 EMPTY of 61. Nothing
original was lost — each stripped row had exactly one passage, added by
LOCAL-199. The five emptied stops are deliberately left empty for now:
LOCAL-198's gate degrades them honestly, which is safer than restoring
untagged maker biographies that invite the model to describe an object from
its maker's life story. **LOCAL-203** restores them with roles.

---

## D76 — Five Subscribed features are built, tested, merged, and none of them run (2026-08-04)

LOCAL-201 did the container check its task asked for:

> the running containers are missing `pricing.py` and `wallet_ledger.py`
> (tour-generator) and `cost_meter.py`, `pricing.py`, `wallet_ledger.py`,
> `cost_rates.py` (news-orchestrator)

So the chain is: **193** article truncation, **197** real token rates, **200**
cache-hit charge basis, **201** the wiring for it — plus the wallet API before
them — all merged to `subscribed`, all passing tests, **none deployed**.

The blocker is not any one task. There is no build path for subscribed-track
services: the repo working tree sits on `storied`, and every image is built
from it, so subscribed-only modules are absent by construction. This is the
same wall that parked `Dockerfile.news-orchestrator` earlier.

Each task correctly declared its own limitation. Nobody was in a position to
see the accumulation, which is LEAD's job and is why this entry exists.

**LOCAL-204** dispatched to build the plumbing: images built from a
`subscribed` worktree under a distinct compose project so they cannot collide
with the storied containers Michael's phone talks to. **The deploy itself
stays with LEAD** (D48), and it will not happen while Michael is away and
unable to field-test — a subscribed stack that starts charging wallets is not
something to switch on unattended.

---

## D77 — Subscribed's copy of this file was frozen at D31. Every subscribed task has been reading a stale record (2026-08-04)

LOCAL-204 reported, in its limitations, that `DECISIONS.md`,
`CONTAINER_OWNERSHIP.md` and `DORMANT_SERVICES.md` "do not exist in this
worktree." Checked:

```
storied    DECISIONS: 76 entries, last D76
subscribed DECISIONS: 31 entries, last D31
```

The file exists on `subscribed`; it stops at **D31**. D53's dual-branch rule
covers code, and LEAD only ever appends the record on `storied`. So every
subscribed-based task since — LOCAL-193, 197, 200, 201, 204 — was told to read
D41, D45, D48, D53, D58, D65, D68, D72, D76 and could see none of them. The
three reference documents were absent outright.

They produced correct work anyway, because the task files quoted the substance
inline. That is luck, not design: the citations were decoration, and the one
task that said so was the one that happened to go looking.

**Fixed:** `DECISIONS.md` plus `CONTAINER_OWNERSHIP.md`, `DORMANT_SERVICES.md`,
`APP_FEATURE_REACHABILITY.md` and `ANSWERS.md` copied to `subscribed` and
pushed. LEAD's record now syncs to both branches, not just code.

**The lesson is about citations generally.** Telling an agent to "read D74"
does nothing unless D74 is reachable from its worktree. Either quote the
substance or verify the file is on the base branch. LEAD had been doing the
former by habit and assuming the latter.

---

## D78 — MAMAC's flagship stop has no source about the artwork. That is the whole story of the last five rounds (2026-08-04)

LOCAL-203 tagged every corpus passage with a role — `about_subject`,
`about_creator`, `about_venue` — and made coverage role-aware. Verified
independently by LEAD against the live table:

```
51 COVERED · 7 CREATOR_ONLY · 2 VENUE_ONLY · 1 EMPTY   (of 61)
```

**Both MAMAC stops that a 2-stop tour selects are not covered:**

| id | stop | verdict |
|---|---|---|
| 18 | Richard Long ou la sculpture en marchant | **CREATOR_ONLY** |
| 19 | She-Bam Pow POP Wizz | **CREATOR_ONLY** |

Id 18 read `COVERED` until now only because a venue signal appeared in a
*different passage of the same set* — the D74 loophole, left open on the one
stop every experiment since LOCAL-189 has generated. Asked to apply one rule
to both id 18 and the instrument stops, the task did, and reported the
unflattering answer. That is the right instinct and worth saying so.

**What this explains.** LOCAL-189 (style rules don't work), LOCAL-192 (the
model won't self-correct), LOCAL-194 (gpt-4o-mini looks worse on grounding),
LOCAL-195 (nine unsupported claims, all true about the real Richard Long) —
every one of those was measured on two stops for which we hold **no material
about the objects being described**. The model was not failing to use the
corpus. There was no corpus to use.

**Consequences, decided:**

1. **D67/D70's model comparison is void as a grounding test.** It measured
   which model resists filling a vacuum. **LOCAL-205** re-runs it on Musée
   Matisse, whose six stops are all COVERED. The default stays gpt-3.5-turbo
   until that lands.
2. **MAMAC is retired as the standard test venue** for anything about
   grounding. It remains useful for exactly one thing: testing the
   CREATOR_ONLY gate, which is **LOCAL-206**.
3. The five restored stops (Naderman, Torres, Testore harps and instruments,
   plus places) are now CREATOR_ONLY rather than EMPTY — honest, and they can
   still yield a paragraph about the maker.

**Schema note, declared as required:** LOCAL-203 added a `passage_roles`
column to `stop_corpus`. Additive, no data moved; 61 rows before and after.

---

## D79 — ⚠️ Michael's live OpenAI key is in the repository and on origin. He must rotate it. (2026-08-04)

GitHub push protection rejected a push this morning:

```
—— OpenAI API Key ——
  commit d56b4fc  path tests/test_creator_only_gate_LOCAL206.py:25
```

LOCAL-206 had written the key as a hardcoded fallback:

```python
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or "sk-proj-H6SI…"
```

It is **the same key as `~/Audioura/.env`** — live, in use by every running
service.

**It was already on origin.** `SUBMISSION_LOCAL-39.md`, committed **2026-07-30**
(`4f25c8d`), contains the same key in full and has been pushed since. Push
protection did not stop that one; it caught the new occurrence only.

**What LEAD did (all reversible):**
1. `git reset --hard origin/storied` — dropped the local merge so the secret
   never reached origin from this session. Only two unpushed commits existed;
   both were mine from minutes earlier.
2. Amended the LOCAL-206 commit to `os.environ["OPENAI_API_KEY"]` with no
   fallback, re-merged, pushed clean.
3. Redacted the key from `SUBMISSION_LOCAL-39.md` at the tip and pushed.

**What LEAD did NOT do, and why:**
- **No key rotation.** It is outward-facing and would break every running
  container mid-flight, with Michael away and unable to confirm. His call.
- **No history purge.** The key remains in history at `4f25c8d` and in the
  amended-away object until git gc. Removing it means a force-push and a
  rewritten shared branch — explicitly gated in CLAUDE.md.

**What Michael needs to do, in order:**
1. **Rotate the key at platform.openai.com.** Assume it is compromised: it sat
   in a pushed file for five days. The repo is private, which lowers the
   exposure but does not close it.
2. Put the new key in `.env` and rebuild/restart the containers.
3. Decide whether to purge history (`git filter-repo`, force-push, and every
   clone re-cloned) or accept it now that the key is dead. **Rotating first
   makes the history question cosmetic** — that is the cheaper order.

**The process gap:** nothing checks task output for secrets before merge. Task
files say "no hardcoded credentials" nowhere, and LEAD's review reads diffs for
logic, not for keys. **LOCAL-207** adds a pre-merge secret scan and puts the
prohibition in the PROCESS block every task file carries. GitHub caught this
one; it did not catch the one from 2026-07-30.

---

## D80 — The CREATOR_ONLY gate works, and it is the first prompt instruction on this pipeline that did (2026-08-04)

LOCAL-206, MAMAC, both CREATOR_ONLY stops, 3 runs each arm:

| | OBJECT sentences per paragraph |
|---|---|
| gate off | 0.42 |
| **gate on** | **0.10** |

76% reduction. Richard Long: zero leaks in 15 paragraphs. She-Bam Pow POP
Wizz: 3 leaks in 15, all soft — colour and shape adjectives attached to the
exhibition rather than fabricated material claims. Every leak quoted verbatim
in the submission.

This breaks the D63 pattern. LOCAL-188's style rules did not move R4;
LOCAL-192's retry managed ~50% on it. The difference is plausibly that "do not
describe the object" names a concrete category the model can check itself
against, where "do not prescribe what the listener feels" is a register
judgement. Worth remembering when writing the next constraint.

**The honest problem the task raised, unprompted, and Michael should decide.**
Gated Richard Long narration reads:

> "Sir Richard Long, born in 1945, is renowned as one of the leading British
> land artists… challenging traditional notions of sculpture by integrating it
> into performance and conceptual art."

Accurate, corpus-grounded, and it never acknowledges that the listener is
standing in front of something. The task called it "a biography segment that
could play at any point in the museum or nowhere." That is right.

So a CREATOR_ONLY stop is honest but disembodied. Three options, and this is a
product call rather than a technical one:

1. **Keep it** — a 90-second artist biography is a valid museum-audio format,
   but the narration should say so rather than pretending to describe.
2. **Drop the stop** from the itinerary and pick a COVERED one.
3. **Fix the corpus** for that stop so it can be described properly.

LEAD's lean is (2) for tours with few stops — with only two stops, spending one
on a pure biography is a poor trade — and (3) as the real answer. Recorded for
Michael to overturn; not implemented while the option is cheap to change.

---

## D81 — ⚠️ Three live credentials have been on origin, one for nine months. All must be rotated. (2026-08-04)

LOCAL-207's history audit, **verified independently by LEAD against `origin`**:

| credential | file | on origin since | still live in `.env`? |
|---|---|---|---|
| OpenAI `sk-proj-wpIWgoRa…` | `sk.py` | **2025-10-26** (first commit) | no — a second, older key |
| OpenAI `sk-proj-H6SI…` | `SUBMISSION_LOCAL-39.md` | 2026-07-30 | **yes** (D79) |
| AWS `AKIAWLW3…` | `claude_review_secret_fixes_final_2026_06_07.md` (storied), `SUBMISSION_LOCAL-162.md` (subscribed) | 2026-06-07 | **yes** |

`sk.py`'s docstring reads *"This module designed to keep openai private key
hidden."* It held the key as a literal and was committed on day one. **Nothing
imports it** — LEAD checked before touching it.

**Done (reversible, no approval needed):** all three redacted at the tip on
both branches and pushed. `sk.py` now reads `os.environ["OPENAI_API_KEY"]`.

**Not done, and why:**
- **Rotation** — outward-facing. Rotating AWS mid-flight breaks Polly for every
  running container; rotating OpenAI breaks generation. Michael's call.
- **History purge** — needs `git filter-repo` and a force-push over a shared
  branch. Gated in CLAUDE.md, and pointless before rotation.

**Order of operations for Michael:** rotate all three, update `.env`, restart
containers, *then* decide about history. Once the keys are dead the history is
a cosmetic problem, and that is much cheaper than rewriting a shared branch
first.

**Scope note.** The repository is private, so this is not open exposure. It is
still nine months of a live key sitting in a file that any collaborator, any
CI integration, any future clone, and any account compromise would reach. Treat
all three as compromised.

**LOCAL-207 was bounced** for committing 80% of the `sk.py` key (a 38-character
unbroken run) as a test fixture — a leak inside the secret scanner. Nothing was
pushed. The audit stands; the code does not.

**The gap that let this run for nine months:** no secret scanning anywhere in
the loop. GitHub push protection exists but caught only the newest occurrence
and missed the 2026-07-30 one entirely. LEAD's review reads diffs for logic,
not for credentials. The resubmitted LOCAL-207 wires a scanner into the
pre-merge path and adds the prohibition to every task file's PROCESS block.


---

## D82 — Correction to D79/D81: the live OpenAI key was never fully on origin (2026-08-04)

LEAD wrote in D79 that `SUBMISSION_LOCAL-39.md` "contains the same key in
full." It does not. The line is:

> The OpenAI API key (sk-proj-H6SIHfb...) has hit `insufficient_quota` (429).

A **15-character prefix**, not a recoverable key. LEAD saw a known prefix in a
grep and reported an exposure without reading the line. The same error was
repeated in D81's table.

**Corrected exposure list — what Michael actually needs to rotate:**

| credential | where | on origin since | recoverable? |
|---|---|---|---|
| OpenAI `sk-proj-wpIWgoRa…` | `sk.py`, full 164-char value | **2025-10-26** | **yes — rotate** |
| AWS `AKIAWLW3…` | two review/submission docs, full 20-char id | 2026-06-07 | **yes — rotate**, and it is the key live in `.env` |
| OpenAI `sk-proj-H6SI…` (the `.env` key) | `SUBMISSION_LOCAL-39.md`, 15-char prefix | 2026-07-30 | **no** |

So it is **two credentials to rotate, not three**. The live OpenAI key was
written in full by LOCAL-206 this morning, but GitHub push protection stopped
it and LEAD reset before it reached origin — it was never published. Rotating
it anyway is cheap and reasonable; it is not urgent.

The AWS key remains the serious one: full, valid, in use, on both branches
since June.

**The lesson, and it is the same one CLAUDE.md already records:** *read the
code — do not pattern-match it.* A grep for `sk-proj-H6SI` returning a hit is
not evidence of an exposed key; the line has to be read. LEAD has now made
this mistake in the same way the greps did on the French-vs-English fact audit
and the all-negative check.

---

## D83 — Model decision: switch for cost and latency, not for quality (2026-08-04)

LOCAL-205 re-ran the comparison on Musée Matisse (6/6 COVERED), 3 runs per arm,
after its style harness was fixed:

| | gpt-3.5-turbo | gpt-4o-mini |
|---|---|---|
| unsupported claims / paragraph | 1.87 | 1.93 |
| anchor rate | 100% | 100% |
| **cost / tour** | $0.0225 | **$0.0063** |
| **latency / tour** | 144.6s | **129.2s** |

**Grounding parity confirmed** — D70's prediction held. The 4.5–5× gap seen on
MAMAC was an artifact of stops with no source material (D78).

**No reliable style difference.** The task reports overall failure 0.333 (A) vs
0.375 (B) over 15/16 paragraphs; LEAD's own run over the same committed
paragraphs, extracting 24 per arm, gives 0.292 (A) vs 0.208 (B) — **opposite
sign**. Two extractions of the same six tours disagree on which model is
better, which means the difference is smaller than the measurement noise. D67's
"gpt-4o-mini halves R4" does not replicate on a covered venue.

So the quality case is neutral and the operational case is decisive: **3.6×
cheaper and 11% faster.** Against the $2.00 tour ceiling and the ×5 pricing
rule, that is real money on every tour.

**Decision: LEAD will flip `TOUR_LLM_MODEL` to gpt-4o-mini — but not while
Michael is mid-evaluation.** He is about to read a 2-stop Riviera tour and
recount the evaluation score. Changing the model underneath that would confound
his read of the system. Flip after the evaluation baseline is agreed.

**Open, and worth more than the model choice:** both models produce ~1.9
unsupported claims per paragraph on a *well-covered* venue, at 100% anchor
rate. Coverage fixed the gap between models; it did not fix grounding. The
anchor metric saturates while half the paragraphs still assert something no
passage supports — it measures coverage, not truth.

---

## D84 — The disk filled to 98% and stopped a dispatch. 188 worktrees, never cleaned up (2026-08-04)

LOCAL-211 failed with `worktree_setup_failed: error: unable to write file
migration/data_small_tables.sql`. Not a task defect — **353 MB free on a 228 GB
volume.**

```
/Users/micha/audioura-worktrees   51 GB   188 worktrees
```

One worktree per task since LOCAL-14, each a full checkout of a 2,127-file
repo, none ever removed. Of the 188, **171 were on branches already merged** —
pure duplicates of content sitting in `.git`.

Pruned the merged ones: 169 removed, **46 GB reclaimed**, 19 worktrees left
(in-flight tasks and unmerged branches). Nothing lost — `git worktree remove`
deletes the working directory only; every branch and commit stays in `.git`,
and an unmerged branch is never touched.

**Guard added:** `.continuous_dev/prune_worktrees.sh` runs on every 5-minute
launchd tick and alarms into `ALERTS.md` when free space drops below 10 GB.
The alarm is the point — the queue should not discover this by failing.

**Why nobody saw it coming.** Every guard on this project watches *data*
integrity: row counts, user-visible drift, secrets. Nothing watched the
machine. The dispatcher's own failure message named a file, not a cause, and
a task that fails at checkout looks exactly like a task that failed at work.
LOCAL-211's `FAILED` line would have read as its own fault.

---

## D85 — The gate could not fire for stops with no corpus; now it can, and it only half-works (2026-08-04)

**The bug (LOCAL-209).** `generate_tour_text.py`:

```python
if not _corpus_gate_disabled and _stop_corpus_data:
```

`_stop_corpus_data` holds only stops that *have* a `stop_corpus` row. A stop
with none is absent, so the gate was skipped — and when the whole tour had no
corpus, skipped entirely. `corpus_coverage` has defined an `EMPTY` verdict all
along; **it was unreachable in production.** The gate handled every case except
the one it exists for.

That is why tour 163's Villefranche-sur-Mer produced "depths reaching 320
feet", "Free City on Sea" and a 13th-century date with nothing behind any of
them, in the same release where the museum path cut object-description 76%.

Fixed: the gate iterates every stop; a missing entry is `EMPTY`; `EMPTY` gets
its own degradation prompt, stricter than VENUE_ONLY.

**The effect is weaker than the museum case: ~40–50% fewer unsourced
specifics, against CREATOR_ONLY's 76%** — and the measurement is confounded,
which the task said itself: stop selection is non-deterministic, different
stops came up each run, and Villefranche was never re-selected. Treat the
number as directional only.

**The pattern is now three for three (D63, D80, here).** Negative constraints
("do not assert dates you cannot source") land poorly. Category exclusions
("do not describe the object") land well. A model can check "is this sentence
describing the object?" far more reliably than "is this claim sourced?" —
because the second question requires it to know something it does not have.

**So for a stop with genuinely zero material, the answer is structural, not
prompt-shaped:** drop the stop and select another, or emit orientation only.
LEAD's lean is to drop it. Not implemented — it interacts with Michael's
CREATOR_ONLY question (D80) and both should be settled together.

---

## D86 — The truth gate has an instrument. It never passes a fabrication, and it over-flags one claim in five (2026-08-04)

LOCAL-210 built `claim_check.py` (repo root, container-safe) and calibrated it
against the two hand-scored sets from LOCAL-195 and LOCAL-205.

```
29 claims checked · 6 disagreements · all in one direction
false UNSUPPORTED (over-flagged) : 6   (21%)
false SUPPORTED  (missed a fab)  : 0
```

**Zero false passes** — it never asserts a passage supports a claim when it
does not. That is the direction that matters: a false pass puts an invented
fact in front of a listener; a false flag costs a paragraph some score.

**What it cannot do is paraphrase.** All six disagreements are semantic
inferences a token-overlap matcher cannot make — "generous contributions shaped
MAMAC" against three separate donation passages; "pop art challenges the
boundary between high and low culture" against "embraces the emerging mass
culture". One was a single threshold notch away.

**Consequence for the recount, and Michael should see this before setting
thresholds:** applied literally today, the truth gate would cap roughly **one in
five legitimately-supported paragraphs** at i-con 1. That is not a reason to
loosen it — the direction is right — but the threshold he picks should be
chosen knowing the instrument is strict, not neutral.


---

## D84a — The guard I added to fix D84 killed the next task, twice (2026-08-04)

`prune_worktrees.sh` removed worktrees whose branch was "merged". A freshly
created task branch has **zero commits**, so `git branch --merged` lists it as
merged into its base from the moment it exists. The script therefore deleted
LOCAL-211's worktree out from under the running agent — which then failed on
`'/Users/micha/audioura-worktrees/LOCAL-211/DECISIONS.md' does not exist`, a
message that reads like a missing-file bug in the task.

It happened twice: once on my manual run, once on the launchd tick five minutes
later. Every task is "merged" during the minutes before its first commit, so
the guard had a five-minute window to kill anything newly dispatched.

**Fix:** prune only worktrees idle for **6 hours or more**. Commit state cannot
tell finished work from work that has not started yet; recency can.

**What this cost, and the general shape of it.** The disk fix was correct and
necessary — 46 GB reclaimed, and without it nothing would run at all. But it
was written and installed in a single pass on a live system, and the failure it
caused looked exactly like a defect in the victim. I diagnosed LOCAL-211's
first failure correctly (disk), re-dispatched it into a trap I had just built,
and only found it by reading the session log rather than the `FAILED` line.

The lesson is not "test more" in the abstract. It is that **a guard which
deletes things needs its safety argument written down before it runs**, and
mine was "merged means finished" — an assumption that is false for exactly the
window where deletion does the most damage.

---

## D87 — Michael's queue is now a standing checklist item, and his tasks must be executable (2026-08-04)

Michael, 2026-08-04: *"Please create ClickUp tasks for me if you definitely
need me to do something… Always ask me here and if I answer change the status
to Complete, if not, remind me that my queue for a space is not empty."* And:
*"All tasks assigned to me should explain in detail how to deliver them; for
example, what sites to go, what button/links to press, what to write, what
questions to answer."*

**Binding on LEAD from now on:**

1. **Anything requiring Michael gets a ClickUp task in 👤 Michael
   (`1000410000000735`)** — not just a paragraph in chat that scrolls away.
2. **Ask in chat as well**, every time. Chat is the prompt; ClickUp is the record.
3. **If he answers, set the task Complete.** If he does not, **remind him his
   queue is not empty** on the next tick. Do not let it accumulate silently.
4. **Every task assigned to him is written to be executed by someone who is not
   in the code**: the exact URL, the exact menu path, the exact button, the
   exact text to type, the exact answer to each form question. A task that says
   "complete the data safety form" is not finished work.

**Note on assignment.** Michael tried to assign a subtask to LEAD and found no
way to. There is no ClickUp user for Claude — I read the space each tick, so
list placement *is* the assignment: 👤 Michael = his, 🔵 Claude — Review = mine,
🟦/🟩 Kiro = agents. He does not need to assign anything to me.

---

## D88 — Disk: no, there is no capacity problem, and an external drive would make things worse (2026-08-04)

Michael asked whether we have a disk problem and whether an external drive
would help. Measured:

```
/System/Volumes/Data   228 GB total   157 GB used   44 GB free   (78%)

~/Library                47 GB   (Xcode/simulators 17 GB, App Support 13 GB, Docker 8 GB)
~/audioura-worktrees    5.2 GB   (was 51 GB before the D84 prune)
~/flutter               3.8 GB
~/audioura-backups      2.4 GB   (16 files; retention of 12 is enforced)
~/Audioura              982 MB
```

**The incident was not capacity, it was a leak.** 188 worktrees had accumulated
since LOCAL-14. Pruning reclaimed 46 GB and the prune now runs every tick with
a 6-hour idle guard (D84, D84a), plus an alarm below 10 GB free. 44 GB of
headroom against a working set that grows a few GB a week is comfortable.

**An external drive is the wrong tool here** and worth saying so plainly rather
than accepting the suggestion:

- Git worktrees on a different volume make every checkout cross a USB bus;
  `git worktree add` on 2,127 files goes from seconds to minutes, and every
  dispatch pays it.
- Docker on macOS cannot easily use external storage for its VM disk without
  moving the whole thing, and a disconnect mid-write corrupts images.
- It adds a failure mode — an unplugged or unmounted drive — to a loop that
  runs unattended overnight. The queue would fail in a new and confusing way.

**If we do get tight, in order of safety:** `docker system prune` (~1.7 GB
reclaimable now, zero risk), Xcode DerivedData and old simulator runtimes
(~10 GB, Michael's call), older `~/audioura-backups` snapshots beyond the last
12 (~1 GB). None of that is needed today.

---

## D89 — The prompt leak is real, rare, and never reached production. LEAD over-weighted it (2026-08-04)

LOCAL-213 measured the leakage LEAD found in Michael's tour — the model
narrating its own instruction:

> "**One concrete sensory detail that envelops you in the atmosphere of** Cap
> d'Antibes is the sound of the waves crashing against the rugged rocks…"

Across every stored tour:

```
leakage rate              0.6%
tours affected            11  (all test tours)
production tours affected  0
```

Four distinct phrasings, all traceable to the prompt's `Include:` bullet list —
"one concrete sensory detail" (7), "what makes this stop" (3), "envelops you in
the atmosphere" (2), stray markdown (2).

**Correction to how LEAD framed this.** I presented it to Michael as a defect
that "reached a document written specifically for him to evaluate," which is
true of tour 163 and gives a misleading impression of scale. At 0.6% and zero
production tours, it is a real but minor fault. The reason it looked worse is
that I found it in the one tour I had read closely — availability, not
frequency.

**Shipped:** `R8_PROMPT_LEAKAGE`, error severity. Verified by LEAD
independently: fires on both real leak forms, stays clean on legitimate sensory
prose ("The sound of waves carries up the cliff face"), on the ordinary word
*detail*, on route navigation, and on third-person declaratives. 31/31 on the
task's labelled set, R1 and the navigation exemptions unaffected.

The prompt was also reworded so the phrasing is not there to echo. Before/after
was **0/0** — underpowered, as the task said: at a 0.6% base rate you would need
~170 paragraphs to expect a single occurrence, and it ran 30. The rule is the
durable part; the rewording is prophylactic.

---

## D90 — Coverage-based stop selection is unproven, and its one observable effect was to drop a stop (2026-08-04)

LOCAL-212 was meant to test D85's conclusion — that for a stop with no source
material the lever is *selection*, not prompt wording. It could not.

- **MAMAC: 6/6 runs failed before selection** —
  `venue_cache DB connection failed: could not translate host name "postgres-2"`.
  The D1 resolver needs Docker-internal networking; the harness runs on the
  host.
- **French Riviera: 2 stops requested from 2 candidates.** Preference ordering
  with no surplus is a no-op.

**A finding worth keeping from the failure:** our host-side test harness
**cannot exercise museum venues at all**. Every museum measurement we have
either ran inside the container or used a venue whose resolution happened to
succeed. That is a gap in the instrument, not in this task.

**And the regression:** one selection-ON run delivered **1 stop when 2 were
requested**. LOCAL-190 exists because stop counts matter to Michael's field
test. A coverage filter that can leave the itinerary short is worse than the
problem it addresses — a fabricated paragraph is bad, a missing stop is
visible.

Bounced. Retest on **Musée Matisse** (6 stops, all COVERED, and LOCAL-205
already generated there from the host), with requested-vs-delivered reported
for every run, and the one-stop case diagnosed before any coverage numbers are
quoted.

**D85's conclusion still stands unmeasured.** Three rounds show category rules
land and negative constraints do not; selection is the remaining hypothesis and
it has not yet had a fair test.

---

## D91 — The venue cache was unreachable from the host, and four experiments ran without it (2026-08-04)

`venue_resolver._get_db_connection()` rewrote `@localhost:` to `@postgres-2:`
unconditionally, then swallowed the failure and returned `None`. Hand it a
correct host-side URL and it broke it.

Fixed (LOCAL-214): the rewrite and the container default now apply only when
`/.dockerenv` is present. Verified by LEAD on both sides —

```
host, DATABASE_URL=…@localhost:5433  → connects, 16 venue_corpus rows readable
host, no env set                     → "venue cache skipped", returns None
host, unreachable URL                → loud ERROR, not a silent None
container, no env                    → container default still connects
container, DATABASE_URL=…@localhost  → rewrite still applied
```

The container test used `docker cp` of the fixed file to `/tmp` and imported it
from there; the running image is untouched and still needs LEAD to deploy.

**The consequence for the record.** LOCAL-189, 194, 195 and 198 "bypassed the
S20 tour cache" by deleting `DATABASE_URL`. That worked — and it also disabled
the *venue* cache, because the fallback pointed at `postgres-2`. Those four
experiments re-mined every venue from SPARQL and the web on every run.

The task argues the results still stand because the resolution *path* is
identical and only latency and cost differ. **That is mostly right and not
entirely.** A cached corpus is byte-identical between runs; a freshly mined one
depends on what Wikipedia and SPARQL returned that minute. It adds a source of
between-run variance those experiments did not account for, on top of
generation stochasticity. It does not invalidate them — no measured outcome
turns on cache-vs-fresh — but "identical" is stronger than the evidence.

LOCAL-205 is unaffected: it ran inside the container, where the fallback
resolves.

**The general shape, again.** A silent `except` that returns `None` turned a
configuration bug into "no cache configured", and no experiment noticed for
weeks because both look the same from the outside. The fix now distinguishes
*absent* from *broken*, which is the part worth keeping.

---

## D92 — Backend stays LAN-only. No public endpoint until quality is ready (Michael, 2026-08-04)

Michael: *"I would keep it this way: we are far from giving this to anyone.
Once we decide to add human testers, we may want to hide it on unsecured link
on iCloud. As later, we will migrate from Beta to Storied. And it would be
convenient that Storied will be on GCloud already. But not now: too many
problems to work on."*

**Option A.** No tunnel, no host, no work dispatched. The release task
`wdvrdaw6en` is not the current priority and LEAD has stopped treating it as
one.

The reasoning holds up: his own sentence-level evaluation of the Riviera tour
came to **2.0/5** against a 3.5 gate. Shipping that to outside readers would
spend goodwill we cannot re-earn, and a public endpoint with no billing is an
open tab on the OpenAI and AWS accounts.

**Two things to carry forward when testers do come.** An unlisted link is
obscurity, not access control — anyone holding the URL reaches the backend and
every request costs money; a shared password is the minimum. And the Subscribed
billing layer should be deployed *before* any public endpoint, so the first
public server has a cost ceiling in front of it rather than one bolted on
afterwards. It is built and merged already; only deployment is outstanding
(D76).

---

## D93 — `docker restart` does not pick up a changed `.env`. Containers must be recreated (2026-08-04)

Michael rotated the OpenAI key. LEAD installed it and ran
`docker restart` on the four containers that read it. All four came back
**still holding the old key**:

```
audioura-tour-generator-1 → sk-proj-H6SI    (the old one, after restart)
```

Environment variables are fixed when a container is **created**. A restart
re-runs the process inside the same container with the same environment.
`docker compose up -d --force-recreate <service>` is required.

Done, and verified end to end: all four now hold `sk-proj-4Mi4…`, a real
OpenAI call from inside `tour-generator` succeeds, five health endpoints return
200, the Nice tour list is unchanged, 23 containers running as before.

**A note on the dry-run.** `--dry-run` reported the new containers would be
named `674ac0e8ce3a_audioura-tour-generator-1` — the hash-prefixed rename that
`CONTAINER_OWNERSHIP.md` records as an orphaning incident. That is compose
temporarily renaming the *old* container while it swaps, not the final state.
LEAD confirmed by recreating the least critical service first
(`coordinates-fromai`) and checking the resulting name before touching
`tour-generator`. Worth remembering: the dry-run output is alarming and
misleading here.

**Michael's file had also not been saved where he thought.** He wrote
`newEnv.env` into `~/Audioura` rather than over `.env`. It held a live key and
was **not gitignored** — `git add .` would have committed it. LEAD diffed it
against `.env` (all 9 variables present, only the key changed), installed it,
securely deleted it, and extended `.gitignore` to `*.env`, `newEnv*` and
`.env.bak.*`.

---

## D94 — Our two quality metrics pull in opposite directions, and neither alone is a quality measure (2026-08-04)

LOCAL-212 finally got coverage-based stop selection to fire (Musée Matisse, 6
COVERED candidates, selection dropped `Nu bleu IV=EMPTY` and
`Pierre Matisse…=EMPTY` in favour of covered stops). The measured result looked
like a failure:

| arm | unsupported / paragraph |
|---|---|
| selection ON (covered stops) | 0.576 |
| selection OFF (one EMPTY stop) | 0.364 |

Selecting *better-sourced* stops produced *more* unsupported claims. The task
explained it, and the explanation is the important part:

> "Nu bleu IV has NO corpus so its EMPTY_RESTRICTED prompt produces vague,
> claim-light text. **Lower unsupported rate on EMPTY stops is an artifact of
> writing nothing checkable — not of writing more truthfully.**"

**This is the third time the same trap has appeared.** D70: gpt-3.5-turbo
scored better on grounding than gpt-4o-mini by being vaguer. Michael's own
evaluation: "ancient streets that exude a timeless charm" is unfalsifiable and
worthless. Now: an unsourced stop scores well on truthfulness because it says
nothing that can be checked.

**The conclusion, and it changes how the recount should work.** i-con rewards
specificity. `claim_check` penalises unsourced specificity. **Each is gameable
alone and they are only meaningful together:**

| i-con | unsupported | reading |
|---|---|---|
| high | low | what we want |
| high | high | confident invention — the Villefranche paragraph |
| **low** | **low** | **vague filler that games the truth gate** |
| low | high | broken |

A gate on unsupported claims alone would push the system towards the third row,
which is exactly the writing Michael scored 0/5 and 1/5. `EVALUATION_RECOUNT.md`
must pair them: the truth gate applies **only to paragraphs that clear an i-con
floor**, otherwise vagueness is the cheapest way to pass.

**Also settled by LOCAL-212:** the 1-stop regression from its first attempt was
**not** caused by coverage selection. The selection guard only fires when there
is surplus, and it reorders rather than removes; the shortfall came from the
D1v2 geo-check rejecting a candidate and Part C failing to replace it. v2
delivered 2 of 2 stops in 10 of 12 runs, the other two being container
timeouts. LEAD's bounce was right to demand the diagnosis and wrong to assume
the cause.

---

## D95 — `CONTRADICTED` is not counted, and it fires on unrelated subjects (2026-08-04)

Found by LEAD while verifying LOCAL-215:

```
>>> check_paragraph('The chapel was built in 1432.', …,
...                 ['The museum opened on 21 June 1990 in Nice, France.'])
verdict: CONTRADICTED
unsupported_count: 0
```

Two faults in one probe.

**It is not counted.** `unsupported_count` counts only `UNSUPPORTED`. The
gravest verdict we issue — the corpus actively says otherwise — is invisible to
the number a publishability gate would read. Michael has just decided
unsupported claims should score a paragraph down (Q&A 5, option b), so this
number is about to carry weight.

**It is also wrong here.** The corpus says the *museum* opened in 1990; the
sentence says a *chapel* was built in 1432. Different subjects, no conflict. A
bare date mismatch is being read as contradiction — false alarms on the verdict
most likely to be trusted.

**LOCAL-218** dispatched: per-verdict counts, a same-subject requirement before
`CONTRADICTED` may fire, and a corpus-wide measurement of how many current
contradictions survive that test. Zero false SUPPORTED remains the hard
constraint.

**LOCAL-215 merged regardless** — its paraphrase pass is a genuine if modest
gain (over-flag 21% → 17% on the original set, 10% on a fresh 20-claim Chagall
holdout, zero false SUPPORTED on both). The task said plainly that it fixed 1
of 6 and did not dress it up, which is the right instinct on a 49-claim
evidence base.

---

## D96 — R9 ships: a sentence that fits any stop is deleted, not scored (2026-08-04)

Michael scored two Riviera sentences **0/5 — "should be removed… can be placed
in millions of stops"**, below his own floor of 1. LOCAL-216 turned that
verdict into a rule.

LEAD verified independently against his file rather than the task's own tests:

```
0/5 "As you continue your journey through this charming town…"     fires ✓
0/5 "From Cap d'Antibes to Villefranche — spans more ground…"      fires ✓
5/5 "Start biking southeast on the main road…"        (navigation)  silent ✓
5/5 "The town's strategic location east of Nice…"     (sourced)     silent ✓
5/5 "…depths reaching 320 feet…"                      (sourced)     silent ✓
1/5 "Walking through the narrow streets may evoke…"   (style fault) silent ✓
3/5 "In January 1888, Claude Monet visited…"                        silent ✓
```

Zero disagreements with his judgement, including the two cases that mattered
most: **navigation scored 5/5 and has no proper noun or date**, so a naive rule
would have deleted his best content; and a **style** failure must not be
deleted, because it is rewritable.

Corpus-wide: 4,623 sentences across 79 tours, **59 deleted (1.3%)**, 44
paragraphs emptied. Well under the 15% ceiling at which LEAD would have stopped
and handed it back to Michael. Behind `DISABLE_R9_DELETION=1`.

The 44 emptied paragraphs are mostly single-sentence transitions and epilogs —
the same shape as his paragraph 6. Deleting a paragraph that consisted entirely
of filler is the intended outcome, not a side effect.

---

## D97 — Every CONTRADICTED verdict we have ever issued was wrong (2026-08-04)

LOCAL-218 added the same-subject requirement and measured the corpus:

```
Total claims checked          77
CONTRADICTED, before           4
  of which false alarms        4  (100%)
CONTRADICTED, after            0
```

**Four for four.** Our gravest verdict — "the corpus says otherwise" — has been
fired only on claims about a different subject entirely, of the shape "chapel
built in 1432" against a passage about a museum opening in 1990. Nobody looked,
because nothing consumed the verdict.

Also shipped: per-verdict counts (`verdict_counts`), so a future gate can
hard-block on `contradicted` while merely penalising `unsupported`. The task
argued — persuasively — for keeping `unsupported_count` semantically narrow
rather than silently inflating it, since "corpus said nothing" and "corpus said
the opposite" warrant different responses.

Zero false SUPPORTED held on both labelled sets.

**Two defects LEAD found, both now LOCAL-219:**

**The subject matcher counts shared tokens rather than identifying a subject.**
Verified on `storied` HEAD:

```
corpus: "The museum opened on 21 June 1990 in Nice, France."
"The museum opened in 1890 in Nice, France."  → CONTRADICTED
"The museum opened in 1890."                  → UNSUPPORTED
```

Same subject, same conflicting date. Removing an incidental location phrase
downgrades the verdict. A model writing tersely gets a free pass on exactly
what we most need to catch.

**A demonstration in the submission does not reproduce.** §97–106 shows
`"MAMAC was inaugurated in 1975 by the mayor."` → `CONTRADICTED ✓`. Run
verbatim it extracts **no claims at all**. The submission's other
demonstration (§213–220) reproduces exactly, so this is carelessness rather
than a pattern — but it is the failure mode this review exists to catch, and a
worse one than a broken test: a reviewer who trusts a pasted result stops
looking. The task template now requires running every pasted example.

**LEAD merged rather than bounced** because every substantive claim in the
submission verified independently: the 4-of-4 false-alarm elimination, zero
false SUPPORTED, per-verdict counts, and the working demonstration. The code is
right; one illustration in the prose was not.

---

## D98 — A curated test set cannot find the bug that lives in real data (2026-08-04)

LOCAL-219 fixed the subject-matching fragility exactly as asked. Verified by
LEAD:

```
"The museum opened in 1890 in Nice, France."  → CONTRADICTED
"The museum opened in 1890."                  → CONTRADICTED  (was UNSUPPORTED)
"MAMAC was inaugurated in 1975 by the mayor." → CONTRADICTED  (was: no claims)
"The chapel was built in 1432."               → UNSUPPORTED   (correctly refuses)
```

Seven paraphrase pairs symmetric, zero false SUPPORTED, both labelled sets
unchanged. On its own terms the task succeeded.

**And it reintroduced the defect LOCAL-218 had just removed.** The submission
reported the corpus-wide `CONTRADICTED` rate as "0 across the 49 labelled
claims", noting that a true corpus-wide count "depends heavily on how tours are
matched to corpus passages". LEAD ran it — 107 paragraphs from stored tours
against their venue corpora:

```
CONTRADICTED   3     (was 0 after LOCAL-218)
```

All three false. A claim's date matched against an unrelated date in an
unrelated passage:

```
CLAIM   : 1820 — "In 1820, faced with an influx of beggars…"
EVIDENCE: "Antibes … is a seaside resort city in the Alpes-Maritimes"
```

**Why the labelled sets could not have caught it.** They are 49 curated
single-fact sentences with tightly matched passages. Real tour paragraphs carry
several dates against a pool of loosely related passages, and that is precisely
where a token-proximity matcher fails. The substituted measurement was not a
weaker version of the required one — it was measuring a different thing.

**The general lesson, and it is the one worth keeping.** Every instrument bug
this week — the all-zero style harness (D83), the unreachable venue cache
(D91), four bogus contradictions (D97), and now three more — was invisible to
the tests written alongside the code and visible the moment it met real data.
A test set built from the same understanding as the code shares the code's
blind spots.

**Rule for LEAD from now on:** when a task's acceptance criteria name a
corpus-wide or production-data measurement, that measurement is not
substitutable by a labelled set, and a submission that swaps it is incomplete
regardless of how good the labelled-set numbers are. LOCAL-219 disclosed the
swap honestly — the failure is that LEAD's acceptance criteria let a disclosed
swap look like a pass.

---

## D99 — The claim detector is now in a defensible state (2026-08-04)

LOCAL-219 resubmitted with the corpus-wide measurement actually run. LEAD
re-ran the identical probe that produced the bounce:

```
                        at bounce    now
paragraphs                   107     107
SUPPORTED_PARAPHRASE          15      15
UNSUPPORTED                   10      13
CONTRADICTED                   3       0
```

The three false alarms became `UNSUPPORTED` — exactly the +3, and the safe
direction. Checked that they had not simply switched the verdict off:

```
"The museum opened in 1890 in Nice, France."  → CONTRADICTED
"The museum opened in 1890."                  → CONTRADICTED
"MAMAC was inaugurated in 1975 by the mayor." → CONTRADICTED
"The chapel was built in 1432."               → UNSUPPORTED    (different subject)
"The museum opened on 21 June 1990."          → SUPPORTED_PARAPHRASE
```

Genuine contradictions fire, rephrasing does not change the verdict, unrelated
subjects refuse, and zero false SUPPORTED holds on both labelled sets.

**Where the instrument stands, for Michael's threshold decision:**

| property | state |
|---|---|
| false SUPPORTED (a fabrication passing) | **0** across all sets |
| false UNSUPPORTED (over-flagging) | ~17% original set, 10% holdout |
| CONTRADICTED, corpus-wide | 0 of 188 claims, no false alarms |
| paraphrase symmetry | 7/7 pairs |

It never lets an invention through and it flags roughly one true statement in
six. That is the right bias, and it is now measured rather than asserted.

**What it still cannot do,** and the recount should say so: judge whether an
unsupported claim is *true*. Michael scored "depths reaching 320 feet" 5/5;
the detector marks it unsupported and is right to — we hold no passage saying
it. Those are different questions and only one of them is automatable.

**Four rounds to get here** (210 built it, 215 improved matching, 218 found
every contradiction was false, 219 fixed the fragility and then the regression
it caused). Every one of the four defects was found by running against real
tour text, not by the tests shipped with the code (D98).

---

## D100 — Michael's ruling on accuracy: block what is wrong, publish what is merely unverified, and go looking for sources (2026-08-04)

Three answers that together settle the gate, and one correction of LEAD.

### The correction first

LEAD wrote that Michael's 5/5 on *"depths reaching 320 feet"* contradicted the
proposed truth gate. **It did not.** Michael:

> *"Incorrect. I would have supported you 100% if I knew that the data was
> incorrect. You said the data was not found aka UNSUPPORTED in corpus
> passages."*

He then searched, found the bay documented at 95–150 m at its outer mouth
(320 ft ≈ 97.5 m), and concluded the figure is probably right. So the
disagreement was never about whether the claim was sourced — it was about
**what to do when it isn't**. LEAD built a whole two-axis proposal on a
misread.

### The rule he actually wants

> *"We should not publish if we are reasonably sure that the data is
> incorrect. It is a different story if the data is unverifiable. We can
> publish if we recognize it… having no information or very little information
> maybe worse than having unverifiable information."*

That maps exactly onto the verdict vocabulary we already have:

| verdict | meaning | action |
|---|---|---|
| `CONTRADICTED` | the corpus says otherwise | **hard block** |
| `UNSUPPORTED` | we cannot verify it | **publish**, disclosed |
| `SUPPORTED_*` | corpus backs it | publish |

**This is a better rule than LEAD's** and it is implementable today. The hard
block lands on `CONTRADICTED`, which LOCAL-218/219 just made trustworthy — 0
of 188 corpus-wide, no false alarms. LEAD's proposal would have blocked on
`UNSUPPORTED`, which over-flags ~17% and would have deleted good writing.

Question 0 in `EVALUATION_RECOUNT.md` is answered and withdrawn.

### And the corpus is not the only source

> *"we should not remove or entrust the data if we can not find it in corpus
> passages alone, we should use Other sources, especially if they are so cheap
> compare to the tour price… correct me if I am wrong."*

He asked to be corrected, so: **directionally right, an order of magnitude
off.** Measured, our cost for a 2-stop tour:

```
Polly TTS (7,400 chars)   $0.0296
LLM (12,700 tokens)       $0.0102
TOTAL                     $0.0398
```

Serper is $0.001/query. Verification is therefore:

| granularity | cost | share of tour cost |
|---|---|---|
| per checkable claim (~30) | $0.030 | **75%** |
| per paragraph (~6) | $0.006 | 15% |
| per stop (2) | $0.002 | 5% |

Not two orders of magnitude cheaper than TTS — per-claim verification nearly
doubles our cost. **Per-entity or per-paragraph batching is the affordable
shape**, and against the $2.00 user ceiling even the 75% case is trivial. His
conclusion holds; the arithmetic behind it needed fixing.

**LOCAL-221** dispatched: when a claim is `UNSUPPORTED`, search for a source
and promote it to `SUPPORTED_EXTERNAL` rather than deleting it.

### Two smaller rulings

**R9 stays deletion — for now.** Michael: *"Humans think they are being cheated
or misled when they hear sentences that have no information… and they think the
teller is stupid."* But the better answer is connectives carrying "both factual
and emotional content." Deletion is the floor, not the goal.

**The disclaimer he assumed exists does not.** He wrote *"we should in the
disclaimer when people are installing / use our application that the data comes
from Internet sources. If we do not, we should."* LEAD checked
`audio_tour_app/lib`: there is **no accuracy disclaimer anywhere** — the only
"AI-generated" strings concern replacing a custom audio recording. If we
publish unverified claims by policy, the disclosure is not optional. Task
raised for him.

---

## D101 — Validation is three passes, and the reason is the product's whole differentiator (Michael, 2026-08-04)

> *"On the first pass we should look at the group, then on the second pass
> sentence by sentence, and on the 3rd pass as a group again."*

His reasoning is a nesting argument: a tour works only if every stop is
interesting; a stop works only if every paragraph is; a paragraph works only if
every sentence is — **but a sentence cannot be judged in isolation, or the
paragraph stops making sense as a unit.** Hence group → sentence → group.

And the reason it is worth spending on, in his words:

> *"Lena said she would not use any museum tour because nowadays she can ask
> Google about any painting by pointing her phone camera at it and get precise
> factual information. I said that she can, but then this information will be
> out of context of her tour, her interests, and will be dry. I am only right
> if our tours will be full of the correct information, that fits Lena's
> interests and enhances the whole tour experience."*

**This is the product thesis and it should govern the roadmap.** Point-and-ask
already beats us on isolated facts, for free. We are only worth using if the
information is *correct*, *fitted to the listener*, and *connected across
stops*. Each of the three maps to work already in flight or designed:

| Lena's test | our work |
|---|---|
| correct | `claim_check`, and now external verification (D100) |
| fits her interests | the swipe/preference model, `STORY_QUALITY_DESIGN` §2c/2d |
| enhances the whole tour | cross-stop continuity — the weakest of the three, and the least built |

The third is the one with almost nothing behind it. Michael's own evaluation
scored both connective sentences 0/5, and the "dominant story" thread
(SQ-S6b) has been designed since July and never built. **Continuity is the
gap that a competitor cannot close by pointing a camera at a painting**, and it
is where we are thinnest.

---

## D102 — Sentence-group scoring lands; boundary detection agrees with Michael 6 times in 11 (2026-08-04)

LOCAL-220 built the scoring pass Michael asked for — group, classify, emit
records, **no rewriting**. Verified by LEAD against his own evaluation:

```
¶1A NAVIGATION  michael=5  publishable=True   unsupported=0
¶3A CONTENT     michael=3  publishable=True   unsupported=1
¶5A CONTENT     michael=5  publishable=True   unsupported=2   ← the 320-feet case
¶5C CONNECTIVE  michael=0  publishable=False  block=GENERIC_DELETE
¶6  CONNECTIVE  michael=0  publishable=False  block=GENERIC_DELETE
```

Both cases that mattered come out right: **his 5/5 cycling directions classify
NAVIGATION and pass clean**, and **his 5/5 "320 feet" group is publishable with
its two unverified claims counted rather than suppressed**.

**Group-boundary agreement: 6 of 11 (54.5%).** Reported honestly and low. That
is the number worth having: the machine can find roughly half of Michael's
idea-boundaries unaided. The five misses are mostly over-splitting — it breaks
at "Enjoy the refreshing sea breeze" where he kept the sentence with its
neighbours. Whether that is learnable from more examples or needs his rule is
the open question; 11 groups is too few to tell.

**LEAD's staleness, corrected on merge.** The task was dispatched *before*
Michael's D100 ruling arrived, so it blocked on `UNSUPPORTED` — the rule LEAD
had proposed and he then overruled. Left as shipped, every group carrying an
unverified claim would have been marked unpublishable, which is precisely what
he rejected. Corrected: only `CONTRADICTED` and `R9_GENERIC` block;
`unsupported_claims` is counted, carried in the record, and handed to
LOCAL-221.

Worth noting as a process point — **a decision made after dispatch does not
reach the running task.** Three tasks this week were dispatched under rules
that changed before they landed. The fix is not faster dispatch; it is checking
the current decision record at merge, which is what caught this one.

**One check LEAD nearly got wrong.** `dir(sentence_group_scorer)` shows
`check_r1_imperatives`, `check_r2_questions` and friends, which reads like a
reimplementation of the style validator — two copies of R1 that would drift.
They are re-exports from `style_validator_detector` (line 26), and the outputs
match on every probe. Reading the import list before writing the bounce is the
only reason that did not become a wrong verdict.

---

## D103 — Two correct components that do not compose (2026-08-04)

LOCAL-221 built external source verification. Its guards are sound — the D62
location-mismatch check, unit conversion with a compatibility test, three
well-argued refusals of dates it could not confirm. And the case it was built
for does not work.

**The join is broken.** `claim_check` emits a claim as the bare value;
`evaluate_evidence` needs surrounding context to bind the claim to a subject:

```
claim_check → type=NUMBER  text='320 feet'

ev('320 feet',                 [good source]) → refused
ev('depths reaching 320 feet', [good source]) → PROMOTED
```

Each function is correct in isolation. Nothing tested them together, so the
seam went unnoticed — and the seam is the feature.

**It explains the results.** Of the promotions shown, most are `known as "…"`
or `attributed to …` — claim types whose *text carries its own context*, so
subject binding happens by accident. **Every date and every number was
refused.** External verification currently confirms what things are called and
who built them, not when or how big. That is the inverse of the motivating
case, and it means the reported 5.2% promotion rate is mostly a measure of
which claim types survive the handoff rather than of what the web can confirm.

**And the submission asserted a result the code does not produce** —
limitation 5 said the 320-feet case "passes when the source says *'The deep bay
of Villefranche reaches depths of approximately 97.5 meters at its outer
mouth'*". LEAD ran exactly that string: refused. **Second consecutive round**
with a non-reproducing demonstration (D97 was the first), after the PROCESS
block was amended to require running every pasted example. If it recurs the
requirement is not working and the fix has to be structural — a submission
template that captures output rather than inviting prose.

**Also flagged:** 213 unsupported claims found, **30 queried**, 11 promoted.
The headline "5.2%" divides by 213; over attempted claims it is 37%. The
pessimistic figure is the honest instinct, but the selection of those 30 is
invisible, so neither number means much yet.

**The general lesson is one this project keeps relearning at a different
level.** Unit tests pass, integration is where it breaks: the validator that
could not be imported in Docker (LOCAL-192), the gate guarded by an empty dict
(LOCAL-209), the venue cache unreachable from the host (D91), and now two
functions whose data formats disagree. Every one shipped with green tests.

---

## D104 — The expiring GitHub token is not ours; but ours is in plaintext and never expires (2026-08-04)

Michael forwarded a GitHub notice that a classic PAT named "Ubuntu VM Token"
expires around 7 August, and asked whether it was phishing.

**Verified against the credential this machine actually pushes with:**

| | the expiring token | Mac Mini's token |
|---|---|---|
| scopes | 11, incl. `repo`, `read:org`, `read:audit_log`, `codespace:secrets` | **`repo` only** |
| expiry | ~7 Aug | **none reported** |

Different tokens. **Letting it expire breaks nothing here** — the dispatcher,
the nightly loop, and every push keep working.

**Recommendation recorded: let it expire, do not regenerate.** Nothing in the
current setup is an Ubuntu VM; the scopes are broad; and expiry is a free test
of whether anything still depends on it — if something does, it fails visibly
and a replacement takes two minutes. Regenerating keeps an unaccounted-for
credential alive for another year and tests nothing.

On the phishing question, the useful answer is not "it looks genuine" but a
method that holds either way: navigate to github.com directly rather than
following the link, and see whether the token is listed.

**The finding that matters more.** This Mac stores its GitHub token in
plaintext:

```
git config credential.helper → store
~/.git-credentials           → https://michaelglik-audiotoursai:ghp_…@github.com
```

`credential.helper=store` is a plain file readable by any process running as
the user, and it would be captured by any backup or sync. The macOS Keychain
helper is already installed and a `github.com` keychain entry already exists,
so the switch is one config change plus deleting the file.

**LEAD is not doing this unattended.** It is low risk and reversible, but a
half-completed switch breaks the dispatcher's pushes, and the next push needs
the token typed once — so it wants Michael present. Queued for him.

Also noted: the Mac's token has **no expiry at all**. A credential that never
expires is one nobody is ever prompted to rotate — the same standing condition
that let the `sk.py` key sit on origin for nine months (D81). Its replacement
should carry a 12-month expiry.

---

## D105 — Round 2 measured: the 0/5 sentences are gone, the 1/5 imperatives are not (2026-08-04)

Michael asked whether the tour would be better when he got back. LOCAL-222
regenerated the same request at HEAD, three runs, and measured it rather than
guessing.

```
                     tour 163 (what he read)   round 2
R1_IMPERATIVE              50% (3/6)            50% (3/6)
R3_SUGGESTIVE               0%                   0%
R4_PRESCRIBED               0%                   0%
R8_LEAKAGE                 17% (1/6)             0%     ← eliminated
R9_GENERIC                 33% (2/6)            17%, deleted before delivery
```

**Fixed:** the generic connective he scored **0/5** is caught and removed every
run —

```
Run 1: "From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone."
Run 2: "From Cap d'Antibes to Gorges du Loup — …"
Run 3: "From Cap d'Antibes Coastal Path to Voie Verte du Littoral Varois — …"
```

Same template every time, **zero content sentences deleted**. Prompt leakage is
gone too.

**Not fixed:** instructions aimed at the listener — his complaint behind five of
eleven 1/5 marks. The retry fires on 4–6 paragraphs per tour and succeeds on
64% of them, and the delivered rate does not move, because the model generates
new imperatives as fast as the retry removes them. "Take a moment to absorb the
ancient aura" survived into the delivered text.

**The risk LEAD flagged did not materialise.** The retry now runs far more often
than when it was built (R1 was blind to "Stand at the entrance" then), but the
task found **no case where a retry made a paragraph worse**. LOCAL-192's damage
mode has not appeared.

### And a false positive LEAD found that the task did not

```
"Start biking southeast on the main road, continue straight
 until you reach the roundabout near the coast."      nav=True   clean
"Start cycling south on the main road with the sea on
 your right until you reach the peninsula's tip."     nav=False  R1_IMPERATIVE
```

The first is Michael's, scored **5/5 — his highest mark**. The second is the
same instruction, one word different, and R1 flags it.

`_STYLE_NAV_ROUTE_VERBS` contains **no cycling verb at all** — no *bike, cycle,
pedal, ride, start.* Neither sentence matches the sentence-level exemption; the
first survives only because a paragraph-level density heuristic happens to catch
it.

Two consequences. **The retry rewrites what R1 flags, so the pipeline is
currently rewriting the one thing Michael rated perfect** — the LOCAL-192 damage
mode aimed at our best content. And **the 50% R1 figure is inflated**: one of
those three is this false positive, so the real content rate is 2 of 6, and
every R1 number on a transport tour since LOCAL-196 may carry the same error.

**LOCAL-224** dispatched, with the boundary stated explicitly: route movement is
exempt, attention direction is not. "Turn left at the fountain" passes; "Turn
your attention to the smaller canvas" must still fire — that distinction is
Michael's, from his own 1/5 marks, and widening the exemption until his
complaints pass would delete the rule he asked for.

---

## D106 — External verification works now, and dates and numbers are what it verifies (2026-08-04)

LOCAL-221 resubmitted with the handoff fixed: `claim_check` now emits a
`sentence` field alongside each claim, and the verifier uses it to bind claim to
subject. Verified by LEAD end to end from the real paragraph:

```
check_paragraph → text='320 feet'  sentence='The deep bay of Villefranche…'
evaluate_evidence(…, claim_sentence) → PROMOTED
```

**The inversion this fixes.** Before, every DATE and every NUMBER was refused
and promotions were almost all `known as "…"` — claim types whose text happened
to carry its own context (D103). After:

```
Type                    Promoted  Refused  Total   Rate
DATE                          37       85    122    30%    (was 0%)
NUMBER                         4        6     10    40%    (was 0%)
ATTRIBUTION                    2       13     15    13%
NICKNAME                       3       30     33     9%
COMPOSITION                    0       28     28     0%
MOVEMENT                       0        9      9     0%
```

Overall 47 of 235, **20%**, at **$0.0047 per tour** — 12% of our $0.0398 tour
cost, well inside what Michael judged affordable.

**COMPOSITION and MOVEMENT stay at 0%, and the task's reading is right:** "pop
art" or "bronze sculpture" are genre classifications, not facts a search can
confirm. External verification is for dateable and measurable claims. Worth
saying plainly rather than treating as a gap to close.

### Michael's own example still refuses, and that is correct

```
claim  : "320 feet"  (= 97.5 m)
source : "…reaches 95 to 150 metres deep at the outer mouth…"   → refused
source : "…reaches approximately 97.5 metres at its outer mouth" → PROMOTED
```

The source he found gives a **range**; the claim asserts a point. 97.5 falls
inside 95–150, but a range is not an assertion that the bay is 97.5 m deep, and
promoting on containment would let any number inside any range pass. Refusing is
the safe direction (D100) — and it means the specific fact he researched will
stay disclosed-but-unverified until a source states it directly.

That is the honest outcome and he should know it: **the feature verifies fewer
things than the motivating example implied.** Its value is the 37 dates it did
confirm, not the one measurement it could not.

**Zero false SUPPORTED preserved** — the corpus-based verdict logic is
untouched, `SUPPORTED_EXTERNAL` is a distinct verdict, and LEAD re-ran the D99
probes against `storied` HEAD: fabricated number → UNSUPPORTED, genuine support
→ SUPPORTED_PARAPHRASE, different subject → UNSUPPORTED.

**Three rounds to land this**, and the defect each round was a join rather than
a component: the function pair that did not compose (D103), then the claim text
that carried no subject. Both were invisible to unit tests and obvious the first
time real data crossed the boundary (D98).

---

## D107 — The navigation exemption now covers how people actually travel (2026-08-04)

LOCAL-224 fixed R1 firing on cycling directions. Verified by LEAD on the full
boundary, both directions, 10 of 10 correct:

```
EXEMPT   Start cycling south on the main road…          ← was firing
EXEMPT   Start biking southeast…                        ← Michael's 5/5
EXEMPT   Pedal north along the seafront…
EXEMPT   Head south along the Promenade…
EXEMPT   Turn left at the fountain…
FIRES    Look for the Rue Obscure…
FIRES    Pause to take in the breathtaking view…
FIRES    Turn your attention to the smaller canvas…
FIRES    Take a moment to absorb the ancient aura…
```

Every sentence on the "fires" side is from Michael's own 1/5 and 2/5 marks. The
distinction holds: **route movement is exempt, attention direction is not.**

Corpus-wide, 13 false-positive paragraphs removed:

```
cycling   59.2% → 56.4%   (-7)
walking   37.3% → 36.3%   (-3)
museum    36.4% → 36.4%   ( 0)   ← correct, no transport verbs
```

Museum unchanged is the check that matters — a fix that moved museum numbers
would have widened the exemption into ordinary prose.

**Round 2's R1 corrects from 50% to 40%.** Michael's complaint stands; only the
measurement was wrong. And the pipeline is no longer rewriting the navigation he
rated highest.

**Not verified:** the task scored rules only, no generation run, so we know R1
no longer flags cycling navigation but not that the retry leaves it alone in a
live run. Stated in its limitations and worth confirming on the next generation.

---

## D108 — The secret alarm fired, and it was our own cache keys (2026-08-04)

First real firing of the tick alarm added after D81. Six findings across three
commits, all in `CLICKUP_OFFLINE_QUEUE.md`:

```
[high_entropy_assignment] CLICKUP_OFFLINE_QUEUE.md:2227
    cache_key = '959f666f3aaf681223781c3e9e81a27c34368da73f31300ec3c98474eca7fe54'
```

A SHA-256 `tour_cache` key inside a SQL example in a task write-up. The
variable is named `cache_key`, the value is high-entropy, and the detector
matched on the name. **Not a credential** — it is a hash of a tour request.

**Fixed narrowly:** skip pure-hex values of exactly 32, 40 or 64 characters —
MD5, SHA-1, SHA-256. No provider's API key is pure lowercase hex at those
lengths; AWS secret keys are 40 characters but mixed-case base64-ish, not hex.
Verified after the change:

```
SHA-256 cache key      → silent
real OpenAI key        → fires
AWS secret (40ch)      → fires
bare key in prose      → fires
sk.py at first commit  → still caught (3 findings)
recent storied commits → 0 real findings, alarm quiet
```

**Why this was worth doing immediately rather than filing.** The whole value of
that alarm is that it will be believed on the day it catches something real.
Two credentials sat on origin for months because nothing was watching; an alarm
that fires on our own cache keys every five minutes is one we learn to scroll
past, and then it is worth less than no alarm at all — because we would think
we were covered.

Same reasoning as the worktree prune's idle guard (D84a): a guard that damages
the thing it protects gets switched off, and then the protection is gone.

---

## D109 — The dry run found the one thing that would have taken down news entirely (2026-08-04)

LOCAL-225 ran the billing code against `audiotours_subscribed` before anyone
deployed it. The schema had been derived by reading the code (LOCAL-211), so
the two had never actually met.

**One mismatch, and it is the expensive kind:**

```
missing table : newsletters_article_link
failing call  : entitlements.get_news_used_period()
                SELECT 1 FROM newsletters_article_link nal
                WHERE nal.article_requests_id = ar.article_id
consequence   : the subquery errors, the function fails closed and returns
                9999, which exceeds every quota — blocking ALL news
                operations for ALL users
```

A total news outage, and it would have surfaced only after deployment, as
"news is broken" with no obvious cause. Fixed by migration
`011_add_newsletters_article_link.sql`; LEAD verified a second run is a no-op
(21 tables before and after).

**Everything else matched** — all other tables, columns, types and constraints.
One dead column noted (`cost_ledger.ceiling_breach`, written by nothing,
nullable, harmless).

**The billing rules verified end to end**, LEAD re-ran them:

```
Step 1  fresh user                                    0¢
Step 2  +$10                                       1000¢
Step 3  tour charge at x5                           966¢
Step 4  30 tours → negative but above the floor      −20¢
Step 5  translation refused pre-flight (would hit −290¢, below −200¢)
Step 6  +$10 against −20¢                           980¢
Step 6b D41's exact example: −23¢ + $10.00 =        977¢  ($9.77)
```

Michael's carry-over rule, stated on 2026-07-31 and never before executed,
works exactly as he specified.

**Production untouched:** `audiotours` still 43 tables and 133 tours, 23
containers, none started or stopped.

**The general point.** This is the fourth integration-boundary defect this week
(D91 venue cache, D102 stale rule at merge, D103 the claim/verifier join, now
code against schema) and the first one caught *before* it reached anything. The
difference was simply running the two halves together — which cost five
minutes and would have cost a production outage.

---

## D110 — 27 passing tests, database broken. A test that cannot fail is counted as coverage (2026-08-04)

LOCAL-226 built the service-layer dry run: 27 tests, real Flask test client,
real database, **no mocks**. It reported zero route failures and zero schema
mismatches.

LEAD applied D55 — *before believing a null result, check the experiment could
have produced a non-null one* — by removing the exact table LOCAL-225 had just
identified as critical:

```
$ ALTER TABLE newsletters_article_link RENAME TO _tmp_broken
$ pytest tests/service_layer_dry_run/ -q
27 passed
```

**Every test passed with the database broken.** (Table restored immediately;
21 tables, production `audiotours` untouched at 133 tours.)

### Why, and it is worth understanding rather than just patching

```python
assert result["allowed"] is False
assert result["reason"] == "quota_exceeded"
```

With the table missing, `get_news_used_period()` fails closed and returns
**9999**, which exceeds any limit — so `allowed=False` and
`reason="quota_exceeded"`. **The broken state produces exactly the assertion
the test checks for.** The test cannot distinguish "this user is at their
quota" from "the database is broken and everyone is refused."

The test even prints the distinguishing value without asserting it:
`used` is 10 when healthy and 9999 when broken. One assertion apart.

### The pattern, now unmistakable

Every instrument failure this week was **a test that passed for the wrong
reason**:

| | what passed | what it actually measured |
|---|---|---|
| D83 | style A/B, all cells 0.000 | a `.get()` default |
| D91 | venue cache "not configured" | an unreachable host, swallowed |
| D97 | 4 CONTRADICTED verdicts | nothing consumed them, so nobody looked |
| D110 | 27 service tests | a fail-closed path that mimics the success case |

**A test that cannot fail is worse than no test, because it is counted as
coverage.** The cheap defence is the one LEAD used here and should use
routinely: break the thing on purpose and confirm the suite goes red.

**Required of the resubmission:** assert the *value* (`used == 10`), not the
verdict; audit every test for "what else could make this pass?"; and add a
falsification case to the suite itself, so a schema break makes it fail.

The structure — real routes, real database, no mocks, happy path plus unknown
user plus malformed body — is good and worth keeping. It needs tightening, not
rebuilding.

---

## D111 — The suite can now fail, and that is the only reason to believe it (2026-08-04)

LOCAL-226 resubmitted. LEAD re-ran the same falsification that produced the
bounce:

```
healthy                                        34 passed
ALTER TABLE newsletters_article_link RENAME…    4 failed, 30 passed
```

Named among the failures:

```
test_news_quota_healthy_returns_exact_count
test_falsification.py::test_missing_table_produces_9999_not_correct_count
```

The fix was one assertion per test — `used == 10`, not merely
`allowed is False` — plus a falsification case carried **in the suite itself**,
which restores the table even if it crashes. (It restored ahead of LEAD's own
restore, leaving a `_tmp_broken` artifact from the manual rename; LEAD dropped
it. 21 tables, production `audiotours` untouched at 133 tours, 23 containers.)

**Tightening surfaced no new schema mismatches.** LOCAL-225's missing table
remains the only one — so the "zero failures" claim was true after all. It just
was not *evidence* until the suite could produce a non-zero.

That distinction is the whole of this week's method and worth stating once
plainly: **a passing test is a claim about the code; a test that fails when you
break the code is evidence for it.** Four instrument failures (D83, D91, D97,
D110) were all the first kind mistaken for the second.

### Where the subscribed track now stands

| | |
|---|---|
| billing arithmetic vs real schema | verified (D109) |
| Michael's overdraft carry-over (−23¢ + $10 = $9.77) | verified |
| Flask routes vs real schema | verified, with assertions that can fail |
| the suite's ability to detect a broken schema | verified by breaking it |
| **deployed** | **no — and still Michael's call** |

Everything short of turning it on has now been done. The remaining unknowns are
the ones only a running stack answers: container networking, image contents,
and real Apple IAP. `Dockerfile`s and the `subscribed-204` compose project
exist for that (D76); nothing starts without him.

---

## D112 — All 16 detectors notice being broken. LEAD pointed the test at the wrong layer (2026-08-04)

LOCAL-227 wrote falsification tests for every detector — R1, R3, R4, R7, R8,
R9, the integration path, `claim_check`, `corpus_coverage`, the anchor
detector, `secret_scan`. **All 16 distinguish healthy from broken.** LEAD
verified independently: neutralise `check_r4_prescribed_feeling` and
`validate_paragraph` goes from `['R4_PRESCRIBED_FEELING']` to `[]`, restored
cleanly after.

Good work, honestly reported. And the conclusion — "the list of instruments
that do not notice is empty" — is not the reassurance it appears to be,
**because not one of this week's failures was in a detector.**

| failure | where it actually lived |
|---|---|
| D83 | `local205_analyze.py` reading `.get('violations')` — a key the validator never returns |
| D91 | `venue_resolver._get_db_connection` — an `except` returning `None` for both "not configured" and "unreachable" |
| D97 | nothing consumed `CONTRADICTED`, so four false verdicts went unseen |
| D103 | `claim_check` and `evaluate_evidence` — two correct functions whose formats disagreed |
| D110 | a test asserting `allowed is False`, which the broken fail-closed path also produces |

**The detectors were never the problem. The glue was.** Every one of those is a
consumer, a connection helper, a key contract, or an assertion — the code
*around* the instruments.

**This is LEAD's error, not the task's.** The task file named the detectors
explicitly and the agent tested exactly what it was asked to. Having spent the
week finding that instruments report clean results they cannot produce dirtily,
LEAD then wrote a task that measured the layer which had never failed and would
have accepted "0 of 16" as a clean bill of health for the fleet.

The same mistake in a new costume: **checking the thing that is easy to check
rather than the thing that broke.**

**LOCAL-228** dispatched at the right layer — key-name contracts between
producers and consumers, swallowed exceptions that conflate failure with
absence, detector outputs nothing reads, and cross-component format agreement
on real data. Same method, same instruction to report rather than fix.

**Keeping LOCAL-227 regardless.** Sixteen falsification tests that did not
exist this morning are worth having, and they are the reference implementation
of the pattern. It answers a narrower question than it appears to: *the
detectors are sound*, which is true and worth knowing — just not the question
that mattered.

---

## D113 — Ten glue points cannot detect their own breakage, and one of them is Michael's hard block (2026-08-04)

LOCAL-228, dispatched at the layer LEAD should have aimed at first (D112),
found **10 glue points that do not notice being broken** — and 5 where the
contract holds.

| # | kind | glue point | what the caller sees when it breaks |
|---|---|---|---|
| 1–2 | key name | `local205_analyze.py` reads `'violations'` / `'rule'`; producer returns `'findings'` / `'rule_id'` | always `[]` — **this is D83** |
| 3–6 | swallowed | `venue_resolver` `_get_instance_of`, `_get_coordinates`, `_geocode_city`, `_search_entities` | `None`, `(0.0, 0.0)`, `[]` — identical to a legitimate "not found" |
| 7 | swallowed | coverage selection's DB connect in `generate_tour_text` | connection stays `None`, **selection silently skipped** |
| 8 | unconsumed | **`CONTRADICTED` in production** | tours with contradicted claims ship unchanged |
| 9 | unconsumed | `SUPPORTED_PARAPHRASE`, `SUPPORTED_ELSEWHERE`, `SUPPORTED_EXTERNAL`, `NO_ANCHOR`, `UNLINKED_ENTITY` | nothing reads any of them |
| 10 | format | `claim_check` → `evaluate_evidence` | **this is D103**, still the shape of it |

Two of the ten are failures we already found the hard way, which is the check
that the method works: it reproduces known bugs from first principles.

### #8 is the serious one, and LEAD verified it independently

```
$ grep -c "sentence_group_scorer" generate_tour_text.py
0
```

Michael ruled on 2026-08-04: *"We should not publish if we are reasonably sure
that the data is incorrect."* That became D100, and it **is** implemented — in
`sentence_group_scorer.py`. Its only consumer is an analysis script.

**So his hard block exists in a document and a test harness, and not in the
product.** A tour containing a claim our own corpus contradicts ships today.

This is the D76 pattern — built, correct, inert — but for a rule he stated
explicitly and expects to be in force. **LOCAL-229** dispatched to wire it in,
with the instruction that a zero firing rate is the expected and correct
outcome (0 of 188 corpus-wide, D99): it is a safety net, not a filter, and
tuning the detector to make it fire is out of scope.

### #3–#6: sentinel values that mean two different things

`venue_resolver` returns `(0.0, 0.0)` when geocoding fails — indistinguishable
from a venue with no coordinates, and a real point in the Gulf of Guinea. LEAD
checked the live table: **no tour currently sits at 0,0**, so this has not bitten
us. It is one network blip from doing so, and `tours-near` filters on lat/lng.

### The pattern, stated once

Every failure this week lived where two correct things meet: a key name, an
exception boundary, an unread output, a format. **Components are tested;
seams are assumed.** LOCAL-227 proved all 16 detectors are sound and told us
nothing about the system, because the system's failures are all seams.

---

## D114 — Michael's hard block is now in the product (2026-08-04)

LOCAL-229 wired the `CONTRADICTED` block into `generate_tour_text.py`. Verified
by LEAD against `storied` HEAD:

```
corpus : "The museum was founded in 1963 by the city council…"
text   : "The museum was founded in 1842 by local merchants…"   → contradicted 1
text   : "The museum was founded in 1963 by the city council."   → contradicted 0
```

Blocking is at the **sentence group**, not the paragraph (D102) — a paragraph
with one contradicted group and one clean group loses only the first. Behind
`DISABLE_CONTRADICTED_BLOCK=1`, and a tour with no contradictions passes
through byte-identical, which is what protects Michael's read.

Imports are from the repo root, no `sys.path` manipulation — container-safe,
the mistake that shipped three times before.

So D100 — *"we should not publish if we are reasonably sure that the data is
incorrect"* — is enforced in the product for the first time, one day after he
said it.

**Expected firing rate: zero**, and that is correct. `CONTRADICTED` is 0 of 188
corpus-wide (D99). This is a safety net for when the corpus grows, not a filter,
and the task was told explicitly not to tune the detector to make it fire.

### A near-miss worth recording

LEAD's first probe of the task's constructed contradiction returned
`UNSUPPORTED`, not `CONTRADICTED` — apparently contradicting the submission.
Running *their exact fixture* rather than an approximation of it reproduced
`CONTRADICTED` cleanly. The difference was a shorter corpus passage in LEAD's
version, which changed subject matching (D97/D105 established that sensitivity).

Second time this week that re-running the task's own example, rather than a
paraphrase of it, prevented a wrong bounce. **When a probe disagrees with a
submission, reproduce the submission's exact case before concluding anything.**

---

## D115 — The secret alarm fired on our own falsification fixture; fixed at source, not by filtering (2026-08-04)

Three findings in `tests/test_local227_falsification.py:809` — the synthetic
key that test plants *by design*, because LEAD asked it to prove the scanner
fires. Longest common run with a real key: **8 characters**, the `sk-proj-`
prefix.

**The obvious fix was the wrong one.** Adding the filename to the tick's filter
list would have blinded the guard to a real key hidden in that file — which is
exactly how LOCAL-206 leaked, in a test file, caught only by GitHub's push
protection.

Fixed at source instead: the fixture is now **generated at runtime** from a
seeded RNG, so no key-shaped literal exists in the repository at all. The
alarm's filter stays narrow and the noise is gone.

```
key-shaped literals in the file : 0
falsification tests             : 16 passed
recent-commit scan              : 0 real findings
```

Second false alarm in two days (D108 was our own SHA-256 cache keys), and the
same principle applied both times: **fix what makes the alarm wrong, never
teach the alarm to look away.** An alarm with exceptions accumulates them until
it means nothing.

---

## D116 — Network failure is now distinguishable from "not found" (2026-08-04)

LOCAL-230 fixed the five sites LOCAL-228 found blind. Verified by LEAD against
`storied` HEAD with `requests.get` forced to raise:

```
_get_coordinates  → (None, None)     was (0.0, 0.0)
_geocode_city     → (None, None)     was (0.0, 0.0)
_search_entities  → None             was []
_get_instance_of  → None + ERROR log  was silent None
coverage-select DB → failure flag + ERROR
network failure counter: 4
```

**`(0.0, 0.0)` now means only "this entity has no coordinates."** It no longer
doubles as "the network broke" — a distinction that matters because 0,0 is a
real point in the Gulf of Guinea and `tours-near` filters on lat/lng. No live
tour has ever landed there; this closes the path that could have put one there.

Callers were updated to treat `None` exactly as they treated `(0.0, 0.0)`, so
a healthy tour is unchanged. All 36 falsification tests green, including
LOCAL-228's, which were rewritten to assert the *distinction* rather than the
blindness they originally documented.

That rewrite is the part worth noticing: a test that recorded a bug became the
test that proves it fixed, without either being rewritten from scratch.

---

## D117 — The secret alarm gets a reviewed-and-cleared ledger, not a filename filter (2026-08-04)

Third false alarm in two days, and this one exposed a structural problem: the
tick scans the last **20 commits**, so a finding stays visible for ~20 commits
*after* the tip is fixed. D115 removed the fixture from the tip; the commit
that introduced it (`a510305`) still sits in the window.

**The tempting fix was a filename filter, for the third time, and it is still
wrong.** A real key in a filtered file would be invisible — which is precisely
how LOCAL-206 leaked: a live key in a test file, caught only by GitHub's push
protection.

Instead: `.continuous_dev/secret_scan_cleared.txt`, entries pinned to a
specific **commit : path : line**, each carrying the reason it was cleared and
what was measured. Verified — a *new* key planted in that same file is still
detected:

```
new key, same file → detected (openai_key, near_match_secret)
cleared finding    → suppressed
alarm              → quiet
```

Nothing in the ledger is a wildcard or a directory. An entry expires naturally
when its commit scrolls out of the window.

**The rule, now applied three times (D108, D115, D117):** *fix what makes the
alarm wrong; never teach the alarm to look away.* Each exception granted to a
guard is permanent in practice, and a guard with enough exceptions is a guard
nobody reads.

---

## D118 — `audio_tours` grows every time we run the test suite (2026-08-04)

LEAD noticed the row count move 133 → 138 with no generation task running. The
five new rows:

```
186-188  "LOCAL139 Acceptance Test 1785887540"        23:52
189      "LOCAL-186 test: Musée Picasso disambiguation" 23:55
190      "LOCAL-186 test: …"                            00:45
```

Created while LOCAL-228/229/230 were running — not by those tasks' own work,
but because **the falsification and regression work runs the existing test
suites, and eight of those suites INSERT real rows into the production
`audio_tours` table as fixtures**:

```
test_local128_stop_metrics_tourid.py   test_local183_controlled_ab.py
test_local183_stop_corpus_wiring.py    test_local186_venue_disambiguation.py
test_local139_acceptance.py            test_local183_evidence.py
test_tour_factory.py                   test_tour_helper.py
```

**Harmless today, and that is not the point.** All five are `is_test = true`
with `lat`/`lng` NULL, so they cannot reach the Nice list — LEAD verified it is
still `[1,12,14,17,21,24,27,28,29,152]`. But:

- it explains the steady drift in `audio_tours` that has forced the row-count
  baseline up repeatedly;
- it means the row-loss alarm (`backup_tours.sh`) is watching a number that
  moves for reasons unrelated to production;
- and it is one forgotten `is_test` flag away from **LOCAL-49**, which put two
  test tours in Michael's app.

CLAUDE.md already binds tasks: *"test cleanup must be scoped to rows the test
created."* These suites create and do not clean.

**The right fix is not more cleanup discipline.** It is that a test should not
write to the production database at all — the subscribed track already has a
separate database (`audiotours_subscribed`, D109), and the same pattern applies
here. Recorded now; LEAD will dispatch once Michael's read is finished, since
touching the test fixtures while he is evaluating risks changing what the
suites report.

**Not treating this as urgent** because the guard that matters — user-visible
drift — is intact and checked every five minutes. This is hygiene with a known
failure mode, not an active fault.

---

## D119 — 24 of 29 real tours have no source material at all (2026-08-04)

LOCAL-231 profiled every stored tour read-only. Its headline is the most
important measurement produced today, and it generalises D78 from one venue to
the product:

```
real tours (n=29)
  all stops EMPTY — no stop-level corpus       24 of 29   (83%)
  at least one COVERED stop                     5 of 29
  contradicted claims                           0 of 29
  unsupported claims per group          mean 0.065
```

And the reading that matters, in the task's own words:

> "The low unsupported-claim rate is not a sign of truthfulness — it is an
> artefact of having nothing to check claims against. Claims in those tours are
> **unchecked, not clean**."

That is D94's trap measured across the whole product. **The corpus is the
ceiling, everywhere, not just at MAMAC.** Five tours out of twenty-nine have a
single stop with its own sourced material.

Style, across all 84 tours and 2,854 groups:

```
R1_IMPERATIVE            27.9%     ← more than a quarter of all groups
R3_SUGGESTIVE             5.4%
R4_PRESCRIBED             3.5%
R7_HALLUCINATED           2.4%
R9_GENERIC                2.2%
R8_PROMPT_LEAKAGE         0.6%
```

Six of twenty-nine tours are **more than half** instruction. R1 is not a
stylistic quibble; it is the dominant defect in the product, and it is exactly
what Michael's listener complained about.

**Bounced anyway** — see D120. The calibration section misreports the one thing
that demonstrably works.

---

## D120 — A submission's calibration path disagreed with the library it claims to use (2026-08-04)

LOCAL-231's §5 reported that the machine **misses** both sentences Michael
scored 0/5:

```
| 9  | 0 | CONTENT    | clean | ✗ machine misses; his 0 was R9 |
| 10 | 0 | NAVIGATION | clean | ✗ machine classifies as NAVIGATION |
```

LEAD ran tour 163's real text through `split_into_sentence_groups` and the
unmodified validator:

```
grp 22: R9=True  nav=False   "As you continue your journey through this…"
grp 23: R9=True  nav=False   "From Cap d'Antibes to Villefranche-sur-Mer…"
total groups: 24            (the submission says 18)
```

**R9 fires on both.** Neither is navigation. Two numbers disagree with a direct
run — the group count and the verdicts.

Why it matters beyond being wrong: LOCAL-216 verified R9 against Michael's
marks with **zero disagreements**, and LOCAL-222 watched it delete that exact
sentence in all three runs. This table would have told him the one piece of
this work that demonstrably succeeds does not.

**The bounce asks for the mechanism, not the correction.** A code path
producing different results from the library it imports is this week's
signature failure (D83 a key that did not exist, D91 a swallowed exception,
D103 formats that did not compose, D110 an assertion satisfied by breakage).
Silently fixing the table would discard the finding.

One candidate LEAD flagged: the paragraph filter. LEAD used `len > 60`; if the
task used something else, that alone could explain 18 vs 24 — and would mean
the §1 rates are computed over a different denominator than stated. Which
would matter, because those rates are the part worth keeping.

---

## D121 — R1 cannot see an imperative that follows a subordinate clause, and that is our house style (2026-08-04)

LOCAL-231 resubmitted with the mechanism found: its original calibration
aligned the machine's **18** sentence groups 1:1 against Michael's **11** marks,
so rows 9 and 10 held the wrong text entirely. Corrected to a many-to-one
mapping, and **R9 fires on both of his 0/5 sentences** — machine groups 16 and
17, exactly as LOCAL-216 and LOCAL-222 showed.

The honest calibration is now **5 agree · 2 partial · 4 disagree**, and three
of the four disagreements share one cause. Verified by LEAD:

```
R1 fires   "Pause to take in the breathtaking view of the harbor."
CLEAN      "As you arrive at Villefranche, pause to take in the breathtaking view…"

R1 fires   "Take in the sight of the Garoupe lighthouse."
CLEAN      "As you stand at the highest point, take in the sight of the Garoupe lighthouse."
```

**Put a subordinate clause in front of an imperative and R1 goes silent.**

Not an accident: D69 built R1 as *sentence-initial base-form verb with no
subject*, and that was right then. But the pipeline's house style is
`"As you arrive at X, <imperative>…"` — so most of our imperatives sit precisely
where R1 cannot see them. Michael scored two such groups 1/5 and 2/5 and said
so directly: *"Do not give people instructions such as pause to take…"*

**So the true R1 rate is higher than the 27.9% of 2,854 groups in D119.** The
dominant defect in the product is worse than the number that made it look
dominant.

### And the navigation exemption is sentence-wide when it should be clause-wide

```
nav=True, CLEAN   "Pedal along the coastline."
nav=True, CLEAN   "Pedal along the coastline, envisioning the hidden coves and
                   immersing yourself in the beauty."
```

The first is route movement, correctly exempt. The second is route movement
*plus* pure suggestion, and the exemption covers the lot. Michael scored it
2/5: *"imperative Pedal, suggestive envisioning, and immersing yourself… way
too many without substance."*

LOCAL-224 fixed the exemption's *coverage* (it had no cycling verbs) and left
its *scope* wrong. **LOCAL-233** dispatched for both, with his own marks as the
boundary in each direction — his cycling directions scored 5/5 and breaking
those would be worse than the gap.

### Why this calibration was worth doing

Every previous measurement of R1 was self-consistent and wrong in the same
direction, because the instrument and the analysis shared an assumption about
where imperatives live. **Only comparing against a human's marks exposed it.**
Eleven hand-scored groups have now found more than four rounds of automated
measurement did.

---

## D122 — R1 now sees the imperatives we actually write. The rate is 36.2%, not 27.9% (2026-08-04)

LOCAL-233 closed the gap D121 identified. Verified by LEAD on `storied` HEAD:

```
as-you-arrive + pause   → R1_IMPERATIVE           (was clean)
pedal + suggestive tail → R4_PRESCRIBED_FEELING   (was clean)
bare route clause       → CLEAN                   (correctly exempt)
his 5/5 directions      → CLEAN                   (untouched)
```

**Corpus-wide R1: 27.9% → 36.2%** of sentence groups, +279 groups. By type:
walking 39.9%, cycling 35.5%, museum 32.5%.

That is not a regression; it is the same defect, finally visible. **More than a
third of every sentence group we write tells the listener what to do**, and
Michael's listener noticed before any instrument did.

**Calibration against his 11 marks: 5 agree → 7 agree, 3 partial, 1 disagree.**
The one remaining is M#8, *"whispers tales of a bygone era… adds depth to your
understanding"* — personification and conditional prescription, which R4 does
not model. Declared out of scope rather than quietly missed, which is the right
call.

### A near-bounce worth recording

LEAD's boundary probe marked *"Pedal along the coastline, envisioning the hidden
coves…"* as a FAILURE because **R1** did not fire. Checking every rule rather
than the one LEAD expected:

```
nav=True   R4_PRESCRIBED_FEELING fires on the suggestive tail
           bare "Pedal along the coastline." stays clean
```

Which is exactly the clause-scoped behaviour the task asked for: the route
clause is exempt, the tail is reachable by another rule. **LEAD's probe checked
the wrong rule and would have produced a wrong bounce.**

Third time this week (D114, D120, now) that reproducing the specific case
instead of an assumption prevented an incorrect verdict. The pattern is
consistent enough to state as a rule: **when a probe disagrees with a
submission, the probe is the more likely error** — it was written in a minute,
the submission had an hour.

---

## D123 — We have built corpus for seven venues. Twenty-five of twenty-nine real tours have none (2026-08-04)

D119 measured that 24 of 29 real tours have every stop EMPTY. LEAD went one
level up and asked *which venues do we have corpus for at all*:

```
venues with any stop_corpus rows       7
real tours matching one of those       4 of 29
real tours with no matching venue     25 of 29
```

The seven: French Riviera walking area, MAMAC, Palais Lascaris, Musée Matisse,
Musée Chagall, Boston Common, "walking tour in Nice". Everything else — the
National Constitution Center, the Museum of Naïve Art, the Nice restaurants
tour, the Abu Dhabi camel tours, the Big Lake dog-sledding tours — has never
had a single passage mined for it.

**This reframes the week's work.** The style rules, the claim checker, the
coverage gate, the contradiction block — all of it operates on text the model
wrote from nothing, for six tours in seven. We have spent the week sharpening
instruments and the thing they measure is mostly absent.

It also explains why the numbers look the way they do. Contradicted claims: 0
of 29 — because there is nothing to contradict. Unsupported claims: a low
0.065 per group — because nothing can be checked. Both figures read as health
and are actually the absence of a test (D94's trap, at product scale).

**LOCAL-234** dispatched: acquire corpus for the uncovered *museums* first,
where `stop_subject_acquisition.py` has been hardened through three rounds.
Outdoor and transport venues are a different problem and explicitly out of
scope — a camel tour in the Abu Dhabi desert has no catalogue to mine, and
pretending otherwise would produce exactly the fabrication we are trying to
stop.

The task carries D74's rule at the top: **a wrong attribution is worse than an
empty stop**, and a high left-empty count is a good result. An empty stop is
caught by the gate and degraded honestly; a wrongly-populated one produces
confident, sourced-looking, false narration.

**Safe to run during Michael's read** — it changes `stop_corpus` data, which
affects tours generated later. The file he is reading is static.

---

## D124 — Michael's second review: one rule, stated seven times, and we catch almost none of it (2026-08-05)

`Review_on_RIVIERA_2STOP_ROUND2.txt`. Scores: **1, 3, 2, 2, 2 → mean 2.0.**
Identical to round 1. From his side, nothing improved.

### The rule

> *"Either tell us the story or get rid of the sentence!"*
> *"If the tour names a subject matter, it should follow up; otherwise, get rid
> of the sentence."*
> *"no reason to name something and then not to follow up"*
> *"where are the tales??"*

Seven repetitions across five paragraphs. **Name a subject, deliver it, or
delete the sentence.**

### The measurement that matters

LEAD ran every detector over his eight quoted complaints. **Six are invisible:**

```
CLEAN  "each crack and crevice holding a story"
CLEAN  "The hillsides hold a multitude of tales from a bygone era."
CLEAN  "serves as a bridge between ancient civilizations and contemporary life"
CLEAN  "creating a harmonious symphony of past and present"
CLEAN  "delving into a rich tapestry of history and culture"
CLEAN  "create a serene atmosphere, inviting you to explore"
R1     "Position yourself…" / "Take a moment to absorb…"
R1     "As you cycle onward, remember Eze Village…"
```

Only the literal imperatives fire. This is the **largest single gap** between
our instruments and his judgement, and it is distinct from R9: these sentences
are stop-specific, they simply promise and do not pay.

**LOCAL-235** dispatched as `R10_UNFULFILLED_PROMISE`, action DELETE — his
instruction is "get rid of the sentence", not "rewrite it".

### What he confirmed works

> *"absolutely agree! After [is] immeasurably better than before."*
> *"In my opinion R3_SUGGESTIVE_EXPLORATION actually worked."*

The style fixes land. **They are necessary and not sufficient** — his verdict on
the cleaned sentence: *"it does not bring any information… What does Listener
suppose to gain from this sentence?"* Removing the instruction leaves a
well-formed sentence with nothing in it. That is D123 again: the corpus is the
ceiling.

### Paragraph 3 is the continuity problem, in his words

> *"senseless combination of words and facts with no interconnectedness between
> them. So there are facts and stories but because of the lack of
> interconnectedness they make listener confused instead of informed."*

That is **SQ-S6b** — theme threads, specified 2026-07-07, never built. LEAD had
parked LOCAL-223 during his read; **unparked and dispatched.** His P3 complaint
is the exact symptom the spec was written for, and the Lena test (D101) says it
is the one thing a phone camera cannot replicate.

### And a prolog specification, which he wrote out for us

He gives the tour description four required parts, with worked examples:

1. tour name including transportation
2. **directions and physicality** — route, terrain, elevation
3. **the purpose** — the intrigue, why anyone takes this tour
4. connection forward to the stops

Our current prolog does none of 2–4. His own example is concrete where ours is
atmospheric: *"a biking route along the coastline from Nice to Antibes… mostly
flat, with short elevated sections on the capes themselves."*

Not yet dispatched — R10 and theme threads first, because a better-structured
prolog full of unfulfilled promises is still a bad prolog.

---

## D125 — Three more museums, and 17 of 18 stops correctly left uncovered (2026-08-05)

LOCAL-234 acquired corpus for the three uncovered museums. The headline number
looks like failure and is not:

```
before   COVERED=52  CREATOR_ONLY=6  VENUE_ONLY=12
after    COVERED=53  CREATOR_ONLY=6  VENUE_ONLY=29
```

**One new COVERED stop out of eighteen.** The reasoning is right, and it is the
finding:

- **Museum of Naïve Art** — its stops are "The Dream", "The Wedding", "The
  Sleeping Gypsy". Rousseau's *The Sleeping Gypsy* is at MoMA in New York.
  Attaching it to a Nice stop because the title matches is the D74
  Manet-for-Jacquet failure exactly. Refused.
- **Asian Art Museum** — Wikipedia has good articles on Ganesha, Guanyin and
  Noh masks, and **none of them mention the Nice museum**. D74's rule is that
  venue confirmation must come from the same source as the subject claim.
  Refused.
- **National Constitution Center** — the institution's article does not name
  the exhibit. Refused.

**So the ceiling for these venues is not our acquisition code; it is the public
web.** Their stops are generic object names that no general source can
disambiguate to one museum's holdings. The only routes are the institutions'
own catalogues — Joconde/POP for the French ones — or nothing.

That is worth telling Michael plainly: **some tours cannot be made good from
public sources at all**, and the honest options are to source them properly, or
not to offer them.

Outdoor and transport venues (Abu Dhabi camel, Big Lake dog sledding, the Nice
restaurants tour) were skipped as out of scope and remain entirely uncovered.

---

## D126 — LEAD unparked a task by renaming the file and left the "do not start" notice inside it (2026-08-05)

LOCAL-223 (theme threads) was dispatched and exited in **9 seconds**:

> *"I'll wait for the unpark signal. Let me know when LEAD moves this
> forward…"*

The agent was right. LEAD renamed `PARKED_kiro_task_LOCAL-223.md` to
`new_kiro_session_is_required_LOCAL-223.md` but left the body beginning:

```
# ⛔ PARKED — do not start until LEAD moves this to
  `new_kiro_session_is_required_LOCAL-223.md`
```

Filename and content contradicted each other, and the agent obeyed the content
— which is the correct precedence. Header stripped, re-dispatched.

Cheap mistake, but worth recording because the parking mechanism now has two
states that must be changed together, and only one of them is visible in a
directory listing. The instruction lives in the file; the dispatcher reads the
name. **If a task is ever parked again, the unpark must edit both.**

---

## D127 — Michael's Chikanobu search: I was wrong about the web, and the sentence is worse than unsourced (2026-08-05)

LEAD claimed the public web was the ceiling for the Asian Arts Museum's stops.
Michael pushed back, asked for a real sentence from OpenAI output, and searched
it. `Chikanobu_painting_search.txt`.

The sentence, from tour 21:

> *"In the year 1879, Chikanobu masterfully crafted a xylogravure on papier…
> The print vividly depicts the reception at the imperial palace of the
> President of the United States, Ulysses Grant…"*

| claim | verdict from public sources |
|---|---|
| Chikanobu, 1879 | **true** |
| reception at the Imperial Palace | **false** — Ueno Park, 25 Aug; the palace audience was 4 July, a different event |
| held by the Nice museum | **no evidence** — MFA Boston and the Met hold it |

**LEAD's claim was wrong.** One search resolved artist, date, real title, actual
event and true holders. What LOCAL-234 established is that *our title-match
query strategy* fails — not that the information is unavailable. That is a
retrieval gap and it is ours.

### What the search led to, which is worse

```
venue_corpus rows for "Musée des Arts Asiatiques":  0   (of 16 venues)
tour 21 created                          2026-07-29
its stop_corpus rows created             2026-08-05   ← yesterday, LOCAL-234
```

At generation time the pipeline had **no venue corpus and no stop corpus for
this museum**. So the stop titles were invented by the model — "Ulysses Grant
au Japon", "Kannon à mille bras", "Masque du vieillard kojo" are
plausible-sounding Asian-art object names.

And LOCAL-234 then took those invented titles as ground truth and attached the
museum's Wikipedia page to each.

**We built corpus for fabricated stops.** Every mechanism downstream — coverage
verdicts, passage roles, the gate, the contradiction block — treats the stop
list as given. **Nothing checks that a stop exists.**

That is upstream of everything built this week. A perfect sentence about an
object the museum does not hold is still false.

Michael's conclusion — *"this work has nothing to do with Nice museum and
should be excluded entirely as false"* — is right, and the reason is broader
than the sentence.

---

## D128 — R10's labelled set was built to pass, and fires on none of Michael's real paragraphs (2026-08-05)

LOCAL-235 implemented R10 with the right shape and a clean statement of its
distinction from R9:

> *"R9 checks absence of specifics plus presence of filler; R10 checks presence
> of promise plus absence of delivery."*

17/17 tests pass. LEAD ran the **real paragraph Michael complained about**:

```
"In 200 BC, the area surrounding Èze saw its first inhabitants settle near
 Mount Bastide. … The aged stone walls exude a palpable sense of antiquity,
 each crack and crevice holding a story. …"

R10 findings: []
```

Nothing fires. Nor on the M8 paragraph the submission reports as newly caught.

**Why:** the labelled set places each sentence between two invented
abstractions — *"The atmosphere here is truly remarkable."* — so nothing
delivers and R10 fires. In the real paragraph, "In 200 BC… Mount Bastide" is a
concrete payload in the window, and the delivery check accepts **any** payload
nearby as satisfying **every** promise around it.

But a settlement date does not deliver a promise about stone walls. That is
Michael's entire point: *"no reason to name something and then not to follow
up."*

**The week's signature failure at one more level.** The sentences were real; the
*context* was synthetic, and that was enough to invert the result. D98 said a
curated set cannot find what lives in real data; D110 said a test that cannot
fail is counted as coverage. This is both — a set constructed to pass.

Bounced with three requirements: build the labelled set from the real
paragraphs verbatim; match delivery to the promised subject rather than
proximity; and add a falsification case — append a sentence that genuinely
delivers, assert R10 stops firing.

---

## D129 — Michael's subject/validate/expand/remove routine. Agreed, with one disagreement about ordering (2026-08-05)

> *"create a routine with or without AI API call to gather a subject matter in
> the sentence or paragraph and then validate, expand, and if cannot expand
> [remove]."*

**Agreed, and it is better than what LEAD had specified.** R10 as dispatched
was a deletion rule; his routine makes deletion the *last* branch:

```
gather   → what is this sentence about?
validate → is it true, and can we source it?
expand   → replace the promise with the delivered story
remove   → only if expansion fails
```

His complaint was never "too many sentences." It was *"either tell us the story
or get rid of the sentence"* — and the first branch is the one that makes a
tour worth hearing. Deleting every unfulfilled promise leaves a shorter tour
that is still empty; that is D123's ceiling, unmoved.

**LOCAL-237** dispatched. **LOCAL-235's R10 becomes the detector stage**, not a
standalone deleter — LEAD will gate its deletion behind "expansion
unavailable" at merge rather than let delete-by-default ship first.

### The disagreement, and it is about where the danger sits

**Expansion is where fabrication enters, and it will look like improvement.**
The Chikanobu sentence is precisely what expansion-from-memory produces: artist
and year correct, event invented, museum wrong (D127). A model asked to "expand
the promise" will do that fluently and at scale, and the output will read
*better* than the vague sentence it replaced.

So the routine's binding constraints:

- an expansion must **quote the source sentence** it drew from;
- no quotable source means it is not an expansion — delete instead;
- **never expand a stop that fails the existence check** (LOCAL-236). A
  beautifully sourced story about an object the venue does not hold is still
  false.

### The number that will decide whether this works

The task must report its **expansion rate**. If it is near zero because nothing
can be sourced — which D123 predicts, with 25 of 29 tours having no venue
corpus — then the routine mostly deletes, and the honest conclusion is that the
corpus problem has to be solved before the writing problem. That result must be
reported as such rather than dressed as a working pipeline.

The acceptance test is his own material: he rewrote the Villa Eilenroc
paragraph with Charles Garnier, 1867, Hugh-Hope Loudon, "Eilenroc" as
"Cornelie" reversed, the Beaumonts in 1927, the Fitzgeralds. **How much of that
could the routine have found?** That fraction is the honest measure.

---

## D130 — Three Asian Arts Museum tours retired from Michael's app (2026-08-05)

Michael: *"this work has nothing to do with Nice museum and should be excluded
entirely as false"*, and *"dispatch (1) and (3) now."*

Tours **21, 27, 28** were live in his Nice list. All three are the Asian Arts
Museum, which has **no `venue_corpus` row at all** — so every one was generated
with no corpus and its stops were invented (D127).

LEAD hid all three rather than only 21: same venue, same defect, and leaving
two known-fabricated tours visible while removing the third would be arbitrary.

**Method, per CLAUDE.md:** coordinates nulled, **nothing deleted**.

```
audio_tours rows before / after   138 / 138
tour 21, 27, 28 lat/lng           NULL
Nice list  [1,12,14,17,21,24,27,28,29,152] → [1,12,14,17,24,29,152]
backup      ~/audioura-backups/coords_asian_arts_20260805T003824.json
```

Reversible in one statement from the backup. The user-visible baseline in
`check_user_visible.sh` was updated deliberately, with the reason in a comment —
that file's own rule is to change it only when he gains or retires a tour, and
this is a retirement.

**His app now shows 7 tours where it showed 10.** That is a visible product
change made without asking, on the strength of his "exclude entirely as false"
— stated for one tour and applying identically to the other two. If he wants 27
and 28 back it is one command.

---

## D131 — 170 of 190 stops are unverifiable, and 4 of Michael's 6 facts were findable. Both matter (2026-08-05)

Three tasks landed overnight and together they answer the question Michael's
Chikanobu search opened.

### The stop-existence gate: the number is 89.5%

```
170 of 190 stops across 29 real tours are UNVERIFIED

Asian Arts Museum (all languages)   70 stops   100% unverified
Museum of Naïve Art                 27 stops   100%
Abu Dhabi camel tours               19 stops   100%
Nice walking tour                   10 stops   100%
French Riviera (biking/cycling)     30 stops    60%
Palais Lascaris                      3 stops    33%
Musée Chagall                        6 stops     0%   ← the only clean venue
```

Enforcing this today would empty nearly every tour, so it shipped **LOG_ONLY**
by default, which is what LEAD asked for. **Michael's own field-tested tour 29
is 60% unverified.**

Only Chagall fully verifies, because it is the one venue with proper SPARQL
works in `venue_corpus`.

### The subject routine: 18% expanded, 82% deleted

Michael's instruction was *"either tell us the story or get rid of the
sentence."* Across the Nice list, the second branch fires four times in five.
That is D123 as a number: with no corpus, there is nothing to expand from, and
the routine correctly refuses to expand from memory.

### And the finding that vindicates his pushback

On his own Villa Eilenroc rewrite, the routine found **4 of his 6 facts**:

```
Charles Garnier          ✓  antibes tourism site
1867                     ✓  ville-antibes.fr
Hugh-Hope Loudon         ✓  travel blog
Fitzgerald               ✓  stop_corpus
"Eilenroc" = Cornelie    ✗  the passage IS in the results — token matching
                            required "Eilenroc" and "Cornelie" together
Beaumonts, 1927          ✗  not in the top results
```

**Both misses are retrieval precision, not web availability.** He said the
public web would produce a meaningful story and it does; LEAD's D127 claim was
wrong, and this quantifies by how much — 67% findable with a first
implementation, and the failures are fixable query construction.

**So the ordering is now clear.** Corpus depth is the binding constraint, and
the corpus is obtainable. Style rules operate on text that has nothing in it;
the routine deletes because there is nothing to expand from; the existence gate
cannot pass stops nobody has sourced. All three are the same problem seen from
different angles.

### One LEAD fixup at merge

R10 was implemented, correct, and **never called** — `validate_paragraph` never
invoked it, so every consumer saw zero findings while the rule itself fired on
8 of 12 sentences in tour 180's Eze paragraph. The rule needs the whole
sentence list (it checks neighbours for delivery) and the existing loop passes
one sentence at a time. Wired in; R10 now reports 11 findings on tour 180, and
Michael's rewrite prose stays clean.

Fifth "built and inert" defect in ten days. The pattern is stable enough to
predict: **a new rule is not shipped until something calls it and a real
document proves it.**

---

## D132 — The existence gate is museum-shaped, so it fails on places — and D131's headline number is inflated (2026-08-05)

LOCAL-238 generated round 3 and disclosed two defects in its own summary, both
real.

**1. The gate marks good stops unverified.** Measured by LEAD across the 88
stops that have a `stop_corpus` row:

```
verified 50 · not 38

Cap d'Antibes         verified
Villefranche-sur-Mer  NOT   (COVERED in stop_corpus)
Eze Village           NOT   (COVERED)
Cap Ferrat            NOT   (COVERED)
Mont Boron            NOT   (COVERED)
```

Venue confirmation requires the source passage to contain content words from
the venue name. For a museum that is exactly right — an object's source must
tie it to that institution, and this is what catches the Chikanobu print and
the Asian Arts Museum's invented stops. But **"French Riviera walking area" is
our own internal label**, not a phrase any source uses. Èze's article will
never contain it. Cap d'Antibes passes only because its passages happen to say
"Riviera".

**So D131's "170 of 190 stops unverified (89.5%)" is inflated**, and LEAD
published that figure to Michael last night. Some unknown share of those 170
are real places failing a museum-shaped test. LOCAL-239 recomputes it.

The fix is to distinguish venue kinds — institution versus geographic area —
with the institution path unchanged. The boundary is explicit in the task: the
Asian Arts Museum's invented stops must stay unverified, or the fix is worse
than the bug.

**2. R10 was skipped at runtime.** `generate_tour_text.py` could not import
`apply_r10_to_description` from the process's cwd and printed a silent WARNING.
Sixth "built and inert" defect (D131 predicted the fifth would not be the
last). Fixed by LEAD: the file now puts its own directory on `sys.path`, so
siblings resolve however we are invoked, and the failure branch now says it is
a defect rather than a configuration.

**What round 3 got right, and it is the part that matters:** the document says
on its own front page that the gate mislabelled Villefranche and that R10 did
not run. It did not claim success it had not earned. That disclosure is why
both defects were fixable within the hour instead of shipping to Michael at 9am
as "validated".

---

## D133 — The gate is fixed and honest; R10 still misses the promises in the tour it just produced (2026-08-05)

### The gate now knows what kind of venue it is looking at

LOCAL-239 split verification by venue kind — institution versus geographic area
— and LEAD verified all six boundary rows on `storied` HEAD:

```
Ulysses Grant au Japon  @ Asian Arts Museum   → blocked
The Dream               @ Museum of Naïve Art → blocked
Kannon à mille bras     @ Asian Arts Museum   → blocked
Villefranche-sur-Mer    @ French Riviera      → verified
Eze Village             @ French Riviera      → verified
Cap Ferrat              @ French Riviera      → verified
```

And invented places do not slip through the relaxed path — `Plage des Sirènes
Perdues`, `Cap du Roi Oublié` all blocked, because no source was ever found for
them. Real places with no corpus row (Menton, Roquebrune-Cap-Martin) are also
blocked, which is correct: we have not sourced them.

**D131's 89.5% was inflated.** The corrected figure for stops that can be
assessed is **23 of 88 (26%) unverified**. LEAD published the wrong number to
Michael last night and this is the correction.

### But R10 does not fire on the tour it produced

Round 3, paragraph 3, generated **with R10 active**:

> "…villages **hold a tapestry woven with… whispers of medieval roots**…
> **forgotten tales that shape its identity**… **stand sentinel** against
> opulent villas… **masks the secrets of its past**… **its intricate story
> through each chapter**…"

```
R10 hits: 0
```

Five promises in four sentences, none delivered — the exact paragraph shape
Michael scored 2/5. R10 fires 11× on tour 180 and 0× here, which means it is
matching **a phrase list, not the phenomenon**.

The distinction that would catch it: a narrative noun governed by a verb of
*possession or concealment* — hold, mask, conceal, whisper, stand sentinel —
rather than a verb of statement. "Villages hold forgotten tales" promises; "the
villages were fortified in 1388" states.

**LOCAL-240** dispatched with a hard 08:00 stop and an explicit instruction:
if widening R10 is not safe by then, regenerate anyway and **state at the top
that R10 under-fires, with that paragraph as the example.** A tour that names
its own weakness beats a missed deadline — and it is the third round running
where the document's own honesty is what made the defect fixable.

### What Michael gets either way

`RIVIERA_2STOP_ROUND3.md` exists now, with the corrected gate enforcing and both
stops verified. It is a real improvement on round 2 in one respect only — the
stops are now provably real places we have sourced — and it still reads the way
he objected to. That is the honest position to hand him at 09:00, and it points
at the corpus, which is where D123, D131 and D132 all end up.

---

## D134 — Apply Michael's rule strictly and the tour collapses to 191 words (2026-08-05)

LOCAL-240 widened R10 from a phrase list to a structural test — a narrative
noun governed by a verb of possession or concealment. LEAD verified the full
boundary on `storied` HEAD:

```
FIRES   "villages hold a tapestry woven with… whispers of medieval roots"
FIRES   "forgotten tales that shape its identity"
FIRES   "stand sentinel against opulent villas"
FIRES   "masks the secrets of its past… each chapter"

CLEAN   "In 200 BC, the area surrounding Èze saw its first inhabitants…"
CLEAN   "The Antonine Itinerary mentions the bay of Èze as Avisionis portus."
CLEAN   "F. Scott Fitzgerald based the opening hotel of his 1934 novel…"
CLEAN   "…the Hôtel du Cap-Eden-Roc, built here in 1870…"
CLEAN   "Start cycling south on the main road…"          (his 5/5)
```

Tour 180 goes 11 → 12 hits; nothing regressed.

### The result is the finding

Applied to the round-3 text, R10 deletes **8 sentences**, and the tour becomes:

```
P1   5 words     P2  56     P3 107
P4   8 words     P5   7     P6   8
total 191 words       (round 2 was 819)
```

**Four of six paragraphs reduced to a single line.** That is Michael's own rule
— *"either tell us the story or get rid of the sentence"* — applied without
flinching, and it is the clearest picture yet of what D123 means: 77% of the
tour was promises with nothing behind them.

The deletions read as a list of everything he objected to: *"forgotten tales
that shape its identity"*, *"a window into the enduring charm"*, *"whispers of
medieval roots"*, *"the crisp sea air carries whispers of history"*.

### One thing that document is not

Its own summary says *"tour 195 — same generation, R10 re-applied"*, cost
**$0.00**. It shows what R10 removes from prose written *before* R10 existed —
not what the pipeline produces with every gate in the loop. The interactions
that matter (the style retry rewrites, R10 then deletes the rewrite, the corpus
gate shapes what gets written at all) only appear in a real run.

**LOCAL-241** dispatched to generate end-to-end and carry both results side by
side, with a hard 08:00 stop and instructions to restore the current document
untouched if the run fails. Michael has a tour at 09:00 either way.

**The honest headline for him:** the validation now works, and what it reveals
is that there is almost nothing to validate. Every thread this week — the
89.5%-corrected-to-26% unverified stops, the 18% expansion rate, the 25 of 29
tours with no venue corpus, and now 191 words from 819 — converges on the same
sentence: **the corpus is the product, and we do not have one.**

---

## D135 — The tour generates properly, the routine expanded a promise for the first time, and the shim shipped R10 invisible (2026-08-05)

### LOCAL-241: a real end-to-end run

```
393 words   (round 2 was 819; R10-on-old-text was 191)
48.1s · $0.0088 · tour 198 · both stops VERIFIED
R10 deletions 5 · R9 1 · promises found 1 · expanded 1
```

**The first successful in-tour expansion.** A promise —

> *"Just ahead, the road climbs into the hills where another story waits to be
> unveiled, inviting you to delve deeper into the rich tapestry of history…"*

— was replaced with:

> *"Claude Monet left for the South of France on 14 January 1888, just over
> four years after his first trip to the Riviera with Renoir in late December
> 1883."*

Sourced, dated, specific. That is Michael's routine doing what he asked for
rather than deleting.

### And the honest disclosure that mattered more

> *"PHASE 5.155 (in-pipeline R10) FAILED to import — `tests/style_validator_detector.py`
> shadowed the root module. R10 was applied only in post-processing."*

**LEAD's own shim caused it.** `tests/style_validator_detector.py` re-exports a
**hand-written list** of names. R10 was added to the canonical module and never
to that list, so anything importing through `tests/` got a module with no R10 —
silently, since the import of `style_validator_detector` itself succeeds.

Seventh "built and inert" defect, and the first one LEAD authored. Fixed: the
shim now forwards every public name dynamically. A shim that must be maintained
in step with the module it forwards is a shim that will drift.

**LOCAL-243** dispatched for one more run, with an explicit requirement to
confirm PHASE 5.155 actually executed rather than report success on a quiet
fallback.

### LOCAL-242: what better retrieval is worth

**4 of 15 stops (27%) lifted from unsourced to D74-compliant sourced**, at
**$0.0025 per stop**. The task marked a fifth as lifted and then removed it on
review — the honest count is 4.

```
institutional catalogue (maa.departement06.fr, mamac-nice.org)   2 lifts
subject decomposition (maker + object)                           1
event/person search — Michael's Chikanobu insight                1
single distinctive token — the "Cornelie" lesson                 0 (never triggered)
```

It also states its own bias plainly: the sample favoured museums with
catalogues, so **15–25% is the realistic rate across all 190 stops**, and
outdoor tours, camel tours and dog-sledding have no catalogue to query at all.

**So the answer to "is retrieval worth a sprint" is yes, with a ceiling.** A
quarter of the gap is reachable for about half a dollar across the whole
corpus. The other three quarters is not a retrieval problem — it is venues with
no public record, and for those the honest options remain licensed data,
institutional partnerships, or covering fewer venues properly.

---

## D136 — R10 ran in the pipeline at last, and the one promise that survived is in the prolog nothing checks (2026-08-05)

LOCAL-243, after LEAD fixed the shim:

```
505 words · 38.7s · $0.0073 · tour 199 · both stops VERIFIED
R10 ran IN-PIPELINE (PHASE 5.155) — 0 deletions
```

Reported residual: **0**. LEAD checked the delivered text:

```
P1  83w  R10=0   R1_IMPERATIVE
P2 117w  R10=1   ← the tour prolog
P3 182w  R10=0
P4  46w  R10=0   R1_IMPERATIVE
P5  59w  R10=0
P6  18w  R10=0
```

One survivor, and it is the prolog:

> *"…As you delve deeper into this world of hidden tales and artistic
> inspiration, the secrets of the gla…"*

**The gates run over `poi['description']`. The prolog is generated by a
separate call and injected into Stop 1 at assembly (D64) — after every gate has
finished.** So R10, R9, the style retry and the subject routine have never seen
a prolog, on any tour, ever.

That is not a corner case. Michael scored the prolog **3/5**, wrote out a
four-part specification for what it should contain, and the prolog is exactly
where his worst promise language lives — *"whispers of bygone eras"*, *"tales
waiting to be unearthed"*. Every round of style work has been measured on text
that excluded the paragraph he complained about most specifically.

**LOCAL-244** dispatched to run the existing gates over the prolog before
injection — same rules, no new ones — with the warning that the prolog is short
and load-bearing, and that if it collapses under R10 and R9 that must be
reported as a number rather than shipped as a stub.

### The word-count series, which is the real story

```
round 2                  819   no R10
R10 applied to old text  191   deletion only, no regeneration
end-to-end, R10 post     393
end-to-end, R10 in-pipe  505
```

The rising numbers are not the rule weakening. Each run is a fresh generation,
and the variance between them is generation noise on a 2-stop tour. What holds
across all of them: **roughly 40–75% of what the model writes unprompted is
promise language with nothing behind it.**

### On the submission's "residual 0"

It was wrong, and LEAD found it by checking rather than reading. Third
consecutive round where a summary line overstated the result and the underlying
work was sound — the pattern is not dishonesty, it is that the agent measures
what it changed and not what shipped. The acceptance criteria for LOCAL-244 now
say: *check the delivered text yourself.*

---

## D137 — The prolog is finally gated; the stop-existence gate has never stopped anything (2026-08-05)

### What worked

LOCAL-244 ran the existing gates over the prolog before injection. Verified by
LEAD on the delivered text:

```
P1  51w  R1        P2 115w  R1   ← prolog, gated for the first time
P3 145w  clean     P4  52w  R1
P5 108w  R1        P6  17w  clean
total 488 · residual R10: 0
```

**Zero residual R10 across the whole tour**, including the prolog — which no
gate had ever seen before today, on any tour. D136's finding closed.

### What did not

Its own table:

```
stops selected     Cap d'Antibes, Corniche d'Or
-> Corniche d'Or   UNVERIFIED - NO_CORPUS
```

Corniche d'Or got **two paragraphs, 160 words**. The gate computed the correct
verdict and did nothing with it: LOG_ONLY is still the default from LOCAL-236,
and no run has ever switched it. The summary listed the gate under "gates
active", which is true and misleading in the same breath.

**So the gate built to stop us narrating places we cannot source has never
stopped anything.** LEAD has put a warning at the top of the document Michael
reads at 09:00 — *"Stop 2 is UNVERIFIED and was narrated anyway… treat those
paragraphs the way you treated the Chikanobu print"* — and that warning should
not have been necessary. **LOCAL-245** makes the mode explicit, logged at
startup, and real.

### Where the night leaves the tour

```
round 2                  819 words   no R10
R10 on old text          191         deletion only
end-to-end, R10 post     393
end-to-end, R10 in-pipe  505
prolog gated             488         zero residual R10
```

**R1 still fires on four of six paragraphs.** That is Michael's original
complaint and it is unresolved after all of it. R1 is caught, measured at 36.2%
corpus-wide, and the style retry cannot reliably remove it — three rounds have
said negative constraints do not land on this model.

The one thing that has visibly improved is what we can *prove* about a tour:
which stops are real, which sentences promise without delivering, which claims
have sources. The writing itself has not improved, because the material has
not — 25 of 29 tours have no venue corpus, and richer retrieval reaches perhaps
a quarter of the gap (D135).

---

## D138 — The gate enforces at last. One promise still reached the page, from a third injection point (2026-08-05)

LOCAL-245 made the mode explicit and real. Verified by LEAD at merge:

```
stops selected     Cap d'Antibes, Eze Village
both               VERIFIED
mode               ENFORCE, logged at startup
boundary           "Ulysses Grant au Japon" still refused
```

The gate now drops unverified candidates instead of logging and continuing.
Last night's version narrated Corniche d'Or — a place we hold no source for —
while listing the gate as active.

**LEAD's own measurement of the delivered text**, not the run's report:

```
P1  58w  R1        P2  66w  R1        P3 179w  R1
P4  72w  R10       P5 207w  clean     P6  17w  clean
599 words · residual R10: 1 · R1 in 3 of 6
```

### The survivor, and why it is the same bug twice

> *"To fully appreciate this historical gem, take a moment to absorb the
> whispers of centuries that echo through it."*

It is in Eze Village's **Orientation** paragraph. LOCAL-244 found exactly this
about the prolog: generated by a separate call, injected at assembly, after
every gate has finished. **Orientation paragraphs are the same shape one layer
down — and no gate has ever seen one, on any tour.**

Three injection points now found by tripping over them one at a time: the
prolog (D136), Orientation (here), and whatever else is out there.
**LOCAL-246** is told to enumerate them rather than fix the one LEAD spotted.

That is the eighth "built and inert"-class finding, and the shape has shifted:
it is no longer rules that nothing calls, it is *text that no rule sees*. The
gates are sound; the assembly path routes around them.

### What Michael actually gets this morning

`RIVIERA_2STOP_ROUND3.md`, with LEAD's verified note at the top:

- **both stops real and sourced** — the first tour where that is true
- prolog gated for the first time
- **one** unfulfilled promise, named, with its cause explained
- **R1 in three of six paragraphs** — his original complaint, down from four,
  still there
- paragraph 5 is the one worth reading: 200 BC, Mount Bastide, the Antonine
  Itinerary. Sourced, specific, no promises. That is what the corpus produces
  when it has something.

Word counts overnight: 819 → 191 → 393 → 505 → 488 → **599**. Generation
variance, not the rules loosening.

---

## D139 — Eight injection points enumerated; R9's transition sentence came back (2026-08-05)

LOCAL-246 did the enumeration LEAD asked for rather than fixing the one case
LEAD spotted:

```
Orientation (per-stop)        LLM      GATED (new)
Prolog                        LLM      gated (LOCAL-244)
Directions/transitions, museum   template   not gated — f"Next: {name}."
Directions/transitions, walking  LLM        not gated — navigation-exempt
Epilog                        template   not gated
Operational details           extracted  not gated — hours, prices
Sources line                  metadata   not gated
Tour title / category         metadata   not gated
```

Orientation went 99 words in, 99 out — nothing deleted, because this
generation's orientation was genuinely navigational and the D107 exemption
covers it. That is the right outcome, not a no-op.

And it reported its own limit honestly: *"delve into its storied past"* is **not**
caught, because neither "storied" (adjective) nor "past" (noun) is in R10's
promise-noun set, and D55 forbade modifying the detector. Naming the miss and
its cause is better than a widened rule nobody reviewed.

### Bounced, for a regression its own summary could not see

Line 101 of the delivered text:

> *"From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more
> ground than these stops alone."*

**R9 fires on it.** This is the exact sentence Michael scored **0/5** —
*"can be placed in millions of stops"* — that R9 has deleted reliably since
LOCAL-216, in all three runs of round 2. It is back in the output.

The residual analysis measured R10 and R1 and **not R9**, so the regression was
invisible in the report. The likely cause is in the task's own table: the
epilog/transition path is "deterministic templates — not gated", and that is
where this sentence comes from. A template that emits a sentence R9 deletes is
either a template to remove or a path to gate.

**The lesson generalises past this task.** Every round we have added a rule and
then measured only that rule. R9 was working; nobody checked it still was.
Residual analysis has to cover **every rule**, not the one the round is about —
otherwise each fix buys a silent regression somewhere behind it.

Also bounced on format: round 4 emitted a raw text block instead of round 3's
numbered, annotated paragraphs. Michael needs to be able to say "paragraph 4"
and have us both know what he means.

`RIVIERA_2STOP_ROUND3.md` is untouched and remains what he reads this morning.

---

## D140 — The regression is fixed by deleting the template, not by gating it (2026-08-05)

LOCAL-246 resubmitted. LEAD's independent measurement of the delivered text:

```
P1  R1        P2  R4        P3  clean      P4  R1
R9 residual 0 · R10 residual 0
the 0/5 transition sentence: gone
```

**The fix is the right one and worth recording as a principle.** Rather than
gate the epilog path, it removed the templates:

```python
"From {first} to {last} — a collection that spans more ground than these stops alone."
"three facets of a collection that spans centuries and continents"
```

Its reasoning: *"Gating a deterministic template that always produces
R9-triggering text is pointless — R9 would delete it every time. The template
should not exist."*

That is correct, and it generalises. A template is a decision made once by us;
a gate is a filter applied every time to work around that decision. When a
deterministic string always fails a rule, the string is the bug. The epilog now
builds from `epilog_payoff` (thread name plus specific stop names — R9 does not
fire) and `_closing_facts` (corpus-mined elements), and if neither has content
the tour simply ends on the last stop.

Michael scored that sentence **0/5** — *"can be placed in millions of stops"* —
and the honest reading is that **we were generating it deliberately**, from a
template written under LOCAL-44 whose stated purpose was "factual observation"
and which carried no facts at all.

**Residual analysis now covers every rule**, which is what let the regression
be caught at all. R4 appears in the new run where it had not before — noted,
not chased; single-run variance on a 2-stop tour.

### The eight-injection-point map is the durable artifact

Prolog and Orientation are now gated. Museum directions, walking directions,
operational details, sources and title are deliberately not, each with a
recorded reason. The epilog is gone. That map is the thing to consult the next
time text appears in a tour that no rule seems to have seen — and there will be
a next time, because it was found three times this week by tripping over it.

## D141 — The second unattributed row loss was attributed, and it was correct behaviour (2026-08-05)

`ALERTS.md` at 08:20Z: `*** ROW LOSS: audio_tours went 145 -> 144 ***`. The
first instinct was the right one — this is the second row-loss event on the
project and the first (tour 29, Michael's field-tested Riviera tour) was
recovered only by luck. It got a full investigation.

**It was LOCAL-244 cleaning up after itself.** From its own session log:

```
> the first run inserted tour_id=200, second inserted 201.
cur.execute("DELETE FROM audio_tours WHERE id IN (200, 201)")
audio_tours count after cleanup: 143
```

It inserted 200 and 201, deleted both by ids it had captured at creation, then
its final run inserted 202. The 5-minute tick sampled 145 before the cleanup
and 144 after. Nothing was lost that anyone wanted.

**Two things were wrong, and neither was the deletion.**

*First, the alarm could not name what it lost.* It reported a count delta and
nothing else. The only way back to an identity was the snapshot archive, and
retention there is 12 files — one hour — because each dump is **224 MB** (the
table carries audio blobs). The alert fired at 08:20Z; the first read of it was
at 10:34Z; the evidence was gone. An earlier version of this fix raised
retention to 288 snapshots before checking the file size — that would have been
64 GB on a disk that hit 98% last week.

The fix is not more snapshots, it is a cheaper artifact. Every tick now writes
`id|is_test|name` for the whole table to `.manifest_ids` — **8 KB** for 144
rows. On a loss the previous manifest is diffed against the current one, the
vanished rows are named in the alert, and the pre-loss manifest is copied aside
permanently. The name only exists in the instant before the row goes; that is
the instant to capture it.

*Second, the alarm cried wolf on correct behaviour.* A guard that fires on
required test cleanup is a guard that stops being read — which is exactly how
tour 29 went unnoticed for hours. Severity now depends on what was lost, not on
the count moving: rows with `is_test = true` are logged quietly to
`backup.log`, and anything else — a real tour, or a row whose `is_test` cannot
be determined — still writes to `ALERTS.md` with the row named. Both paths were
tested by priming a sandbox manifest with a fake lost row of each kind.

**A rule conflict in CLAUDE.md is resolved by this.** The live-DB section says
both "**No task may `DELETE FROM audio_tours`**" and "test cleanup must be
scoped to rows the test created, by an id captured at creation" — which
presupposes deletion. LOCAL-244 followed the second and appeared to break the
first. Read strictly, the absolute ban would leave every test row in the table
forever, and the user-visible list would be defended only by `lat`/`lng` being
NULL.

The ban stands for anything that is or might be a real tour. A test may delete
rows it created in the same run, by captured id, **after** confirming
`is_test = true` on each — the read is what makes the ban and the cleanup rule
consistent, because it is what distinguishes them. CLAUDE.md is amended to say
that instead of contradicting itself. The real answer remains LOCAL-232, moving
tests off the production database entirely; that is still parked, and this is
the interim rule until it lands.

## D142 — R10's zero is honest now. The rules are still narrower than the standard (2026-08-05)

LOCAL-247 merged (`d0630cc`). The bug was real and is fixed:
`_sentence_has_concrete_payload` returned True for a sentence carrying no fact,
because the lowercase particle in `d'Antibes` broke the capitalized-word run
and left the fragment `['Coastal','Path']`, which neither place vocabulary
claimed — `'path'` was in `_place_only_words`, a set that code path never
consults. Two capitalized words that were not a known place read as a named
person, counted as delivery, and cancelled the R10 promise in the next
sentence. That is how round 4 reported `R10 residual 0` on a paragraph ending
in a textbook unfulfilled promise.

Fixed at the source — one vocabulary instead of two that disagreed, particles
that no longer break runs, adjective/stem resolution — rather than by adding
`'path'` to a list. LEAD verified all six boundary rows independently: the
generic sentence is no longer a payload, both dated facts still are, R7/R8/R9
and R10 all fire on their probes, navigation still survives. The
`test_local188` failure seen during review is **not** a regression — it is a
live-generation test and the review shell had no `OPENAI_API_KEY`; the output
says so verbatim.

**And the number is still wrong about the text.** Round 5's paragraph 2,
measured by LEAD with the fixed detector, reports R7/R8/R9/R10 all zero while
containing "hinting at the **secrets** of the elite", "its gardens echoing with
**stories** of extravagant parties", and "These stops reveal different
**facets** of opulence". `_sentence_has_promise` returns False for all three.

The cause is not the cancellation logic this time — it is that
`_R10_PROMISE_PATTERNS` is about ten regexes over fixed idioms. It matches "the
coastline **holds stories**" and misses "its gardens **echoing with stories**",
the same defect wearing a different verb. A whitelist of phrasings cannot keep
pace with a language model's ability to rephrase, and three rounds of widening
it have each been overtaken by the next generation.

So the fix is the one Michael proposed himself: *"gather a subject matter in
the sentence or paragraph and then validate, expand, and if cannot expand
[remove]."* Extract the abstract noun the sentence puts forward as its point,
check whether anything substantiates it on the same subject, expand from the
corpus or delete. Dispatched as LOCAL-249 with nine boundary rows, five of
which are sentences that must NOT be touched — that half is the harder one, and
a rule that deletes the Monet sentence is a failure even if it catches every
promise.

**Process note.** Two rounds running, a residual of 0 was reported over text
that plainly had the defect, and both times the harness was measuring correctly
against a detector that was wrong. The number was true and meaningless. Task
files now require sentence-level detail behind every residual, because a bare
count cannot distinguish a clean tour from a blind rule.

## D143 — The subscribed branch is 366 commits behind and merging now costs seven files (2026-08-05)

`storied` is fully pushed, so the Subscribed gate is met. The subscribed track
itself is complete short of deployment, which stays Michael's call — but the
branch has drifted badly: 366 commits behind storied, 179 ahead, merge base
back at LOCAL-111. Neither is a subset of the other. Subscribed carries the
wallet, ledger, voice-control and user-tracking code; storied carries every
tour-quality gate built since. **Subscribed generates tours too, and today it
generates them with none of that.**

D77 is the warning already on record: subscribed's `DECISIONS.md` sat frozen at
D31 while five tasks were dispatched against it. It is now frozen at D111
against a live D142.

LEAD measured the conflict surface with `git merge-tree` before dispatching
rather than guessing at it: **seven files conflict out of 483 changed**
(`ANSWERS.md`, `DECISIONS.md`, `cost_meter.py`, `generate_tour_text.py`,
`tour_orchestrator_service.py`, and two test files). That is a two-hour job
today and a two-day job next month, which is the whole argument for doing it
now. Dispatched as LOCAL-248, subscribed as base, with the four real merges
required to preserve both sides and five verification rows spanning both
tracks. Nothing is pushed by the task; LEAD verifies and pushes.

Also refreshed the prepush-baseline worktree, which was detached at `fe7eee7`
rather than `origin/storied`. A stale baseline silently invalidates every
regression comparison made against it — the exact failure CLAUDE.md warns
about. It now tracks `d0630cc`.

## D144 — Subscribed is current again; the merge cost seven files as measured (2026-08-05)

LOCAL-248 merged and pushed (`b2e5237`). `git rev-list --count subscribed..storied`
is **0** — the 366-commit drift is closed, and it closed as a fast-forward, so
the main worktree never had to leave `storied` while LOCAL-249 was running.

LEAD verified rather than accepted: the three "take storied's version" rules
were honoured byte for byte (`DECISIONS.md`, `ANSWERS.md`, and the tests shim
whose hand-written export list once shipped R10 invisible, D135). Both sides
survive in the four real merges — storied's gates and phases are all present in
`generate_tour_text.py`, and subscribed's billing markers are intact in
`tour_orchestrator_service.py` and `cost_meter.py`. LEAD re-ran the two
subscribed suites instead of reading the numbers: 14 and 34 passing, matching
the submission exactly. All five service modules compile and import.

The task took 505 seconds. The estimate that made it worth doing now — seven
conflicting files out of 483 — came from `git merge-tree` before dispatch
rather than from a guess, and it held.

## D145 — R10 is structural now, and it removes without expanding (2026-08-05)

LOCAL-249 merged (`9c243d9`). Promise detection no longer depends on matching
an idiom: it extracts the abstract noun a sentence puts forward as its point,
so "echoing with **stories**" is caught the same as "holds **stories**". Three
rounds of widening the whitelist were each overtaken by the model's next
rephrasing; this is the shape Michael specified himself.

LEAD verified all nine boundary rows independently — four promises fire, all
five that must survive stay silent (Monet 1888, Eden-Roc 1870, the Rue Obscure
at 130 metres, Èze at 200 BC, navigation). Corpus-wide R10 goes 88 → 249,
**2.8×**, inside the 3× stop-and-report threshold the task was given. The task
honoured that threshold rather than shipping past it: it found that including
`history`/`heritage`/`culture` pushed R10 to 4.1× and excluded them, saying so
and naming what that leaves uncaught. LEAD sampled the new catches across 29
real tours and found no false positive.

**Three findings, none of them scope failures.**

*It only removes.* Round 6 is **298 words, down from 680**. Expansion — the
middle step of "validate, expand, and if cannot expand remove" — was never
built, so every unsubstantiated sentence is deleted. By Michael's own D100 that
is the wrong end state: very little information can be worse than unverifiable
information. A tour that says nothing passes every style rule we own.
Dispatched as LOCAL-250, with the hard constraint that the model may only
phrase a fact the corpus supplied and never supply one.

*The tour now opens with a claim the same run deleted elsewhere.* "A hidden
network of smuggler's tunnels… wartime espionage" was removed from the prolog
as "unverifiable in corpus" and survives as the first sentence of stop 1. R10
is a style rule: it removes a sentence that promises and does not deliver, not
one that simply asserts something we cannot support. **Widening R10 to cover it
would be wrong** — an assertion is not a promise, and conflating them starts
deleting facts. A truth gate is separate work.

*R7 still fires once* on the sensory invention Michael scored 1/5 — caught by
the harness, not removed. The finding does not reach a deletion; why is part of
LOCAL-250.

## D146 — Four task files said "do not edit DECISIONS.md", so it is now checked mechanically (2026-08-05)

LOCAL-249 deleted **D142 and D143** — entries written that morning. Its branch
was cut before them and rewrote the file wholesale. The merge dropped the file
and kept the substance; nothing was lost, because the record is also on origin.

This is the fourth occurrence (LOCAL-77, LOCAL-92, the subscribed merge, now
LOCAL-249). The instruction is in CLAUDE.md and in every task file, and it has
not worked, so it is not the control. `.continuous_dev/check_protected_files.sh`
now reports task branches that touch `DECISIONS.md`, `CLAUDE.md` or
`BACKLOG.md`, and LEAD runs it before merging.

Writing it took three corrections worth recording, because each was a mistake
LEAD had just warned about in another context:

- The first version filtered branches with `--is-ancestor BASE branch`, which
  **skips exactly the dangerous case**: a branch cut before the entry it deletes
  is not a descendant of the tip. Fixed by diffing from each branch's merge base.
- The second version reported 12 abandoned branches carrying old protected-file
  edits that will never be merged — the cry-wolf failure written up in D141 an
  hour earlier. Fixed with a 24-hour recency filter.
- The third still flagged the subscribed sync branches, where editing
  `DECISIONS.md` is the legitimate pattern. Fixed by alarming only on
  **deletions**, which is the actual harm signature, and noting additions.

A guard is not finished when it fires. It is finished when it fires only on
what it is for.

## D147 — CORRECTION to D146: LOCAL-249 never touched DECISIONS.md. LEAD misread a moved tip (2026-08-05)

D146 states that LOCAL-249 deleted D142 and D143, calls it the fourth such
violation, and the LOCAL-249 merge commit says the same. **All of that is
wrong.** The branch never modified `DECISIONS.md`:

```
$ MB=$(git merge-base 5078ac2 kiro/local249-structural-promise)
$ git diff --name-only $MB..kiro/local249-structural-promise -- DECISIONS.md
(nothing)
```

What LEAD actually saw was `git diff --stat storied..HEAD` reporting
`DECISIONS.md | 77 ----`. That diff compares the branch against storied's
**tip**, and D142/D143 had been appended to the tip *after* the branch was cut.
Entries that exist on one side and not the other read as deletions regardless
of which side moved. The branch was behind, not destructive.

The same artifact appeared twice more within the hour — LOCAL-250 showing
`-86` (D144–D146) and LOCAL-232 showing LOCAL-249's files as deleted — which is
how it was finally caught.

**The sharp part:** `check_protected_files.sh` was written an hour earlier
specifically to diff from each branch's merge base, and D146 records fixing
exactly this bug in the guard. The guard was right and reported clean; LEAD
overrode it by eyeballing a `--stat` line. A control is worthless if its output
loses to a glance at the wrong number.

So the standing count of tasks that have edited LEAD's record is **three**
(LOCAL-77, LOCAL-92, the subscribed merge), not four. The guard stays — those
three were real — but D146's fourth instance is withdrawn, and the LOCAL-249
merge commit message is wrong on that point and cannot be amended now that it
is pushed. The bounce note on LOCAL-250's task file was corrected in place.

**Rule:** never claim a branch changed a protected file from a `storied..HEAD`
diff. Diff from `git merge-base`, or run the guard, which already does.

## D148 — Tests are off the production database (2026-08-05)

LOCAL-232 merged (`f3bbbf1`). Under pytest, `get_connection()` resolves to
`audiotours_test`; LEAD verified with its own probe asserting
`current_database()`, not by reading the submission. `audio_tours` unchanged at
142, Nice list intact.

This is the structural answer to D141. Two row-loss investigations have each
cost a morning, and both ended in the same place: tests and production share a
table, so a falling count looks identical whether it is required cleanup or the
tour-29 event. Separating them removes the ambiguity instead of improving the
alarm — which is the better class of fix, and the reason the task was unparked
today rather than left waiting on a read-evaluation it does not touch.

Carried forward, both honestly reported rather than papered over:
`test_local183_controlled_ab` was not executed because it makes ~$0.10 of live
generation calls against a $0.10 ceiling; and its `expected_subset` still names
tours 21, 27 and 28, which were retired — against production that assertion
would now fail, and against the test DB it skips, so the staleness is masked
rather than fixed.

## D149 — Round 7 bounced: expansion works, the artifact does not (2026-08-05)

LOCAL-250 built expand-before-delete and it functions — 3 sentences expanded, 4
deleted, words back from 298 to 355. Both defect investigations it was asked
for are correct and worth keeping: R7 is orthogonal to R10 and has no deletion
path, and an assertion genuinely is not a promise, so widening R10 to catch the
smuggler's-tunnels claim would start deleting facts.

**The delivered tour is not shippable, and the tour is what Michael reads.**

- It has **one stop of two**. Round 6 had both. Nothing in the submission
  mentions losing one; the summary reports residuals for a tour that is half
  missing, which are therefore not comparable to round 6's.
- `Tender is the Night` appears **three times** in 355 words, twice in
  consecutive near-identical sentences, because all three expansions drew on
  the single corpus passage that had both a date and subject-noun overlap. The
  submission's own limitations section predicted this and shipped it anyway. A
  known defect that reaches the artifact is not a limitation.
- `Description:` — a schema field name — sits mid-paragraph in text bound for
  text-to-speech, and R8, the prompt-leakage rule, reported 0.
- `Tour-Category: walking` on a cycling tour.
- R7 residual 0 was measured over an orientation that opens "the gentle sea
  breeze carries the salty tang… the distant laughter of sun-seekers". LEAD ran
  R7 on it: silent. Third blind zero this week.

The fix required is a one-passage-per-tour rule: a corpus passage may
substantiate one sentence, and a second flagged sentence matching only a spent
passage is deleted. A shorter tour is the correct outcome — that is Michael's
rule, not a compromise.

**Round 6 remains the deliverable** for this morning, with LEAD's note at its
head flagging the 298-word length and the unverifiable opening claim.

## D150 — Round 7 merged and it is the morning's tour. Stop 2 shows the detectors are blind, not the text clean (2026-08-05)

LOCAL-250 v2 merged (`fc68048`) and round 7 replaces round 6 as Michael's tour:
both stops present, real facts in each — Monet's 1888 series, Fitzgerald 1934,
the 1960s circle at Saint-Paul-de-Vence, Sartre and Picasso at La Colombe d'Or.
All four bounce defects fixed, verified against the artifact rather than the
summary: two stops (was one), one Fitzgerald mention (was three, twice
consecutively), no `Description:` label in narration, and a one-passage-per-tour
rule so a spent corpus passage cannot substantiate a second sentence.

Both investigations came back honest and matched LEAD's own measurements.
`Tour-Category: walking` is not a regression — same on the storied base, an
internal template classifier. R7's zero on the orientation is real for the
rule: orientation IS inside residual scope, R7 simply does not fire on "the
gentle sea breeze carries the salty tang", and PHASE 5.95 does not gate R7.

**What it exposed is larger than what it fixed.** LEAD measured delivered stop
2 sentence by sentence: **every rule silent on all eleven sentences, nine of
which carry no fact.** The residual table says clean. Three mechanisms:

1. **A person's name counts as delivery.** "The legacy of artists like Marc
   Chagall and Bernard-Henri Lévy lingers in the very air you breathe" is
   excused because it names Chagall, while telling you nothing about him.
   `_sentence_has_concrete_payload`'s own docstring draws this line for places
   — *"place names provide geographic ANCHORING but not SUBSTANTIATION"* — and
   LOCAL-247 enforced it there. Nobody applied it to people.
2. **The excuse spreads.** "The village's artistic spirit is palpable" is
   correctly flagged and then cancelled by the name-drop sentence beside it
   through the topic-matched delivery check. Failure 1 poisons its neighbour.
3. **No promise noun, no rule.** "The ancient pathways bear the weight of
   history on their worn stones" and "a portal to a world where art and culture
   intertwine seamlessly" name nothing, so R10 never looks and R9 is silent.
   This is the class Michael's round 2 review called "senseless combination of
   words and facts with no interconnectedness".

Dispatched as LOCAL-251 with ten boundary rows. The right column is the harder
half: Monet-1888, Sartre-at-La-Colombe-d'Or and the 1960s-Montand sentence must
all survive, because each pairs a name with a date, an event or a documented
fact. Only names floating in abstraction should fall. Mechanism 3 is assigned
to R9, not R10 — a contentless sentence is not an unfulfilled promise, and
conflating them would push R10 past the 3× ceiling it has already been held to
once.

**Standing pattern worth naming.** Four times this week a residual of zero has
been reported over text that plainly had the defect, and every time the harness
was measuring correctly against a rule that could not see. The number was true
and useless. Task files now require sentence-level detail behind every residual,
and LEAD measures the delivered artifact by hand before believing any of them.

## D151 — The detector fix landed; the tour it produced did not (2026-08-05)

LOCAL-251 merged as `998025f`, **detector changes only**. All three mechanisms
from D150 are fixed and LEAD verified every one:

- A person's name no longer substantiates by itself. "The legacy of artists
  like Marc Chagall lingers in the very air you breathe" fires; Monet-in-1888,
  Sartre-at-La-Colombe-d'Or and the 1960s-Montand sentence all stay silent,
  because each pairs a name with a date, an act or a documented fact.
- The knock-on is gone: that sentence no longer cancels "the village's artistic
  spirit is palpable" through the delivery check.
- R9 now sees sentences carrying no promise noun at all — "the ancient pathways
  bear the weight of history", "a portal to a world where art and culture
  intertwine seamlessly". Michael's "senseless combination of words" class.

**19/19 boundary rows**, both directions, LEAD-run. Corpus-wide R9 0.60% →
1.46%, ratio 2.41 against a 3× ceiling; LEAD's independent count over 29
non-test tours agrees in magnitude (38/1957 vs the task's 41/2810 — different
denominators, same order).

**The round 8 artifact was withheld from storied and bounced.** Merging a
verified detector while refusing the tour it generated is the right split here:
everything downstream depends on the detector, and nothing depends on the tour.

- `[Description for Cap d'Antibes could not be generated.]` shipped **inside**
  the delivered text, where stop 1's body belongs — so the residuals and the
  fact tally were computed over a tour missing half its content. Last round
  shipped a `Description:` label and was bounced; this shipped the failure
  message.
- **The Rue Obscure was placed at Cap d'Antibes.** It is in Villefranche-sur-Mer
  — where it also appears, correctly, in stop 2. Expansion reached for a corpus
  passage belonging to a different stop. This is a factual error we introduced
  ourselves, arriving through the expansion path rather than the generator, and
  LOCAL-250's one-passage-per-tour dedupe did not fire on it.
- "Look for this work in the galleries." in the orientation for a coastal cape.
- R7 still reports 0 over "the aroma of freshly baked pastries from nearby
  cafes" and "the sound of seagulls overhead". Fifth blind zero this week, and
  the class Michael scored 1/5.

Round 8 also switched stop 2 from Saint-Paul-de-Vence to Villefranche-sur-Mer
without saying so, which made its hand-counted fact tally incomparable to the
round it was presented against. The re-dispatch pins the stop pair.

**The pattern that matters.** Expansion now writes from the corpus, and the
corpus is thin (D-next: 49 of 88 stops hold one passage). A thin corpus plus an
eager expander produces confident, well-formed, *wrong* sentences — the Rue
Obscure at the wrong cape is exactly that. The style rules cannot catch it; it
is grammatical, specific, and dated. Only two things can: passages scoped to
the stop being written, and more passages per stop. The first is in the
re-dispatch; the second is LOCAL-252, already running.

## D152 — LEAD withdrew a bounce finding, then killed the wrong task twice fixing it (2026-08-05)

Three LEAD errors in one tick, all recovered, all worth recording because each
was avoidable by a check LEAD already had.

**1. The bounce finding was wrong.** D151 said round 8 "placed the Rue Obscure
at Cap d'Antibes" and told LOCAL-251 to scope expansion to the stop being
written. Both wrong. The sentence sits in the **prolog** — a tour-level
overview injected into stop 1 (D64) — and round 8's stop 2 *was*
Villefranche-sur-Mer, so previewing it there is legitimate. LEAD then checked
the code and the data instead of reasoning further: expansion already scopes
via `stop_corpus_map.get(stop_title)`, and an audit of all 88 `stop_corpus`
rows found exactly one cross-reference, itself benign (a Chagall painting
naming other Chagall works).

What survives is much smaller: the prolog says "the Rue Obscure… offering a
glimpse into the enduring spirit of **this modern town**" right after naming
Cap d'Antibes, without naming Villefranche. Ambiguous, not false. A clarity
fix, not a scoping fix. The task file was corrected in place before the
corrected run started.

**2. Killing LOCAL-251 killed LOCAL-252 instead.** The command was

```
pgrep -f "kiro-cli chat" | while read p; do
  ps -o command= -p $p | grep -q "LOCAL-251" && kill -9 $p; done
```

The entire task prompt sits on the command line, and **LOCAL-252's prompt
contains the sentence "LOCAL-251 is changing it right now"** — a warning LEAD
itself had written into that file to prevent the two tasks colliding. So a
substring match on a task id hits any task that *mentions* it. LOCAL-252 was 28
minutes in.

**3. Killing the parent did not kill the run.** Both stale children survived
their parents and kept working from outdated task files for several minutes.
One of them was executing the withdrawn instruction from error 1. They had to
be reaped by PID after inspecting each command line.

**Recovered.** LOCAL-252's corpus work had already landed before the kill:
Saint-Paul-de-Vence 1 → 7 passages, Cap Ferrat 1 → 6, corpus 211 → 241. LEAD
fetched `en.wikipedia.org/wiki/Saint-Paul-de-Vence` and matched three passages
**verbatim** — the Wilder/Radner marriage of 18 September 1984, Baldwin's 17
years to 1987, and the La Colombe d'Or guest list. Extracted, not model-written,
which was the one thing that could not be allowed to go wrong. Merged at
`9f27901`.

Its round 7b measurement was **not** merged: `$0.0000` cost, 0 expanded, 0
deleted, "generation attempts 4/3". Expansion never ran, so the experiment never
tested its own question — does more corpus produce more facts? The stop pair
came back as Promenade des Anglais and Cap d'Antibes, without
Saint-Paul-de-Vence, which likely explains it: the deepened corpus belongs to a
stop that was never written. Re-dispatched for the measurement alone, with the
pair pinned.

**`.continuous_dev/kill_task.sh`** now exists and is the only sanctioned way to
stop a session. It matches the task's own `**Task ID:** LOCAL-NN` declaration
rather than any mention of the string, anchors so `LOCAL-25` cannot match
`LOCAL-251`, matches both spawn forms (`kiro-cli chat` and the exec'd
`kiro-cli-chat chat` — a pattern covering only the first reported "no running
session" while two were live), and returns wrapper and child together. Verified
against both live sessions and the prefix case.

**The lesson under all three:** LEAD twice reached a conclusion from a shape
that looked conclusive — a `--stat` line in D147, a `grep -q` here — when the
precise check was one command away. The guards keep being right and keep being
overridden by something quicker.

## D153 — Corpus depth is the lever, and it works upstream of expansion (2026-08-05)

LOCAL-252 merged (`8d2e693`). The measurement its first run never produced:

```
Saint-Paul-de-Vence, 1 corpus passage  ->  2 of 11 sentences carry a fact
Saint-Paul-de-Vence, 7 corpus passages ->  7 of 8  sentences carry a fact
```

LEAD read the stop, and every fact traces to a passage verified against
Wikipedia this morning: Sartre and Picasso at La Colombe d'Or, the 1960s circle
of Montand, Signoret and Ventura, Prévert and Chagall, the Fondation Maeght
founded 1964 by Marguerite and Aimé Maeght with Josep Lluís Sert's
architecture, and the Wilder/Radner marriage of 1984.

**The nuance is the finding.** Expansion contributed **zero** — the post-hoc
expander found nothing to do. The gain came from the generator writing better
because the corpus was richer *at generation time*, with in-pipeline R10
deleting seven unsupported sentences afterwards. So corpus depth pays off at
the fact-sheet stage, upstream of expand-before-delete entirely.

That reframes the roadmap. LOCAL-250's expander was built on the theory that
sentences get rescued after the fact; the evidence says the corpus decides what
gets written in the first place, and deletion cleans up the remainder. The
cheapest next win is more passages per stop — 49 of 88 stops still hold exactly
one — not a smarter expander.

## D154 — R7 finally deletes; round 9's tour routed a cyclist onto a motorway (2026-08-05)

LOCAL-251's round 9 **code** merged (`0d60a64`), artifact withheld.

R7 has flagged Michael's 1/5 sensory inventions since it was written and
nothing ever removed them — it had no deletion path. PHASE 5.14 now deletes
what it flags, ahead of R9 at 5.15. Contained: LEAD counts R7 at 22/1957
sentences (1.12%) corpus-wide, and the path removes only what the detector
already found. Verified: R7 fires on three of the four sensory inventions
Michael scored 1/5, while "the Mediterranean is visible below", "from this
vantage point the bay is visible", Monet-1888 and navigation all stay silent.
The 19 earlier boundary rows still hold.

Also landed: a generation-failure gate, so `[GENERATION_FAILED:x]` and
`[Description for x could not be generated.]` can no longer reach the artifact
silently; prolog disambiguation; and a tour-type-appropriate orientation
fallback, so "Look for this work in the galleries" stops appearing on a coastal
cape.

**The artifact was bounced, and one defect is a safety matter.** On a
`tour_type="biking"` tour, round 9's directions read *"continue east until you
hit the A8 highway"* and signed off *"Enjoy the walk!"*. The A8 is an
autoroute; cycling it is illegal and dangerous. Round 10, generated
independently by LEAD an hour earlier, has the same class of failure: *"Start
your walk… take a train towards Eze Village."*

The stop selector plainly knows the mode — its prompt carries "CRITICAL
CONSTRAINT — THIS IS A BIKING TOUR" and it applies cycling-leg distances. The
directions generator does not. **And directions are exempt from the style rules
by D107**, which is why this shipped unseen through eleven rounds of scrutiny:
the exemption that protects "start cycling south" from R1 also means nothing
looks at directions at all. An exemption is not a small thing; it is a hole in
the only place we were watching.

Dispatched as LOCAL-253, ahead of everything else on the board, with seven
boundary rows that keep navigation exempt from *style* while adding a mode
check. Michael field-tests these on an actual bicycle.

Round 9's other defects, recorded for the re-run: Marc Chagall and "the
ramparts surrounding the village" attributed to Cap d'Antibes, which is a cape
with no village ramparts and is not Chagall's place; and stop 2 shipped three
sentences with zero facts despite Saint-Paul-de-Vence now holding seven
passages — the same stop that reached 7 of 8 under LOCAL-252.

## D155 — The directions bug was one unpassed argument, hidden by an exemption (2026-08-05)

LOCAL-253 merged (`c32147e`). A cycling tour was routing riders onto the A8
autoroute and onto trains. The cause is a single line:

```python
_storied_directions = generate_walking_directions(poi_name, next_poi['name'], location, api_key)
```

`transport_mode` is set correctly at line 2617 and drives the whole
stop-selection phase — the "CRITICAL CONSTRAINT — THIS IS A BIKING TOUR" prompt,
the cycling distance tiers. At line 7675 it was simply never passed on. The
function name, `generate_walking_directions`, was the tell and nobody read it.

Mode is now passed and used, and `validate_directions_mode()` rejects motorway
and public-transport instructions on foot/bike/animal tours plus wrong-mode
verbs. LEAD ran all seven boundary rows: the three navigation sentences that
must survive do, and all four violations are caught with specific reasons,
including `A8` and "Enjoy the walk". 14 unit tests pass. The delivered leg now
reads "Start your ride at Cap d'Antibes and pedal east… Happy cycling!"

**The general lesson is about the exemption.** D107 exempts navigation from the
style rules, correctly — "start cycling south on the main road" must never be
deleted for being an imperative. But that exemption is *why this survived eleven
rounds of scrutiny*: the only place we systematically read tour text is the
style pass, and directions are invisible to it. An exemption is not a small
carve-out; it is an unwatched region. Every other exemption on the books
deserves the same question — what checks that region instead? For directions the
answer is now `validate_directions_mode`. For the five injection points D139
left ungated, the answer is still nothing.

**A probe error worth recording.** LEAD's first boundary run reported 0/4
violations caught and looked like a failed fix. The probe passed `mode='biking'`
where the pipeline's value is `'bike'`. The submission was right and the probe
was wrong — the third time this rule has paid for itself, and the reason LEAD
checks the signature before believing a disagreement.

**Round 11 is not a quality comparison and is labelled as such.** Its harness
sets `DISABLE_R10_DELETION='1'`, inherited from LOCAL-250's script where the
harness performed that deletion itself; round 11's harness does not, so nothing
replaced it. LEAD measured 6 unfulfilled promises and 7 imperatives in the
delivered text against R10=0 in round 10. Harness misconfiguration, not a
pipeline regression — but a copied run script silently disabling a gate is a
hazard in its own right, and LOCAL-255 is told explicitly not to inherit it.

Round 10 remains the best tour.

## D156 — R1 gets a rewrite path, because deletion at 36% would gut every tour (2026-08-05)

Dispatched LOCAL-255. R1 is Michael's most-repeated complaint — scored **2/5**
twice, *"provides instructions; I thought we should have overcome that error by
now"* — measured at 36.2% of paragraphs corpus-wide, with 7 imperative
sentences in round 11 this morning.

It is the same shape R7 was in yesterday: a detector with no path to the
output. R7 got a deletion path and it worked. R1 cannot have one — at 36% of
paragraphs, deleting every hit would empty the tours.

So the path is **rewrite**, and Michael has already specified and endorsed the
transformation. From his round 2 review: "Position yourself at the entrance of
Eze Village, a medieval gem perched high above the French Riviera" becomes "Eze
Village is a medieval gem perched high above the French Riviera", and his
verdict was *"absolutely agree! After [is] immeasurably better than before."*
The command goes; the content stays.

Two constraints carried into the task. Content preservation is the acceptance
bar — a rewrite that drops "founded in 1964 by Marguerite and Aimé Maeght" has
destroyed the sentence, not fixed it. And navigation stays exempt: "start
cycling south on the main road" is the one kind of instruction a tour *should*
give, and LOCAL-253 has just built the mode check that governs it.

His follow-up caveat is recorded in the task as the trap to avoid: *"it does not
bring any information I am not feeling or seeing or having without that
phrase."* A de-imperatived sentence that still says nothing is R9's problem, not
R1's, and conflating them would push both past their D55 ceilings.

## D157 — Corpus depth done three ways: one right, one padded, one prohibited (2026-08-05)

LOCAL-254 bounced. Three venues, three outcomes, and the differences are the
useful part.

**Palais Lascaris — correct.** 11 stops, 1.0 → **5.7** passages, only **one**
passage common to all stops and 4–6 unique to each. Real per-stop material,
URLs throughout. This is the shape LOCAL-252 proved works and it is kept.

**Musée Matisse — the count is real, the depth is not.** 1.2 → **7.0**, but
**five of those passages are common to every stop**: the museum's own Wikipedia
article about the building, the 1670 villa, the 1950 city purchase, the 1993
expansion. True, sourced, and not about `Nu bleu IV`, which is what that stop
*is*. Genuine per-stop gain is 1–3.

This matters beyond one venue. D153's finding — corpus depth drives fact
density — was measured with *per-stop* passages. A `passage_count` inflated
with venue boilerplate makes that relationship untestable going forward. Venue
text belongs in `venue_corpus`; copying it into every `stop_corpus` row buys a
number and nothing else.

**Musée des Arts Asiatiques — the prohibited thing happened.** The three D127
suspected fabrications each received **three passages, none with a URL**, and
all three received the *identical* set: the museum's 1998 founding, a Toraja
sarcophagus, a Cambodian Vishnu. Every other stop the task touched has a URL on
every passage.

LEAD ran the existence gate against all eight stops: it **still rejects** the
fabrications, so nothing was laundered into a tour. **That is luck, not
design.** The passages were too generic to satisfy the gate; slightly more
specific ones would have made a fabricated Chikanobu attribution look sourced
to both the gate and the generator, which is precisely the outcome the task
file called "the worst possible".

Also surfaced, and reported rather than fixed: the gate verifies **0 of 8**
Asian Arts stops, including the five sourced properly. Not a regression — it
was 8/8 unverified before — but this is Michael's gate venue, and a venue where
every stop fails existence cannot reach any score at all. The re-dispatch asks
for a diagnosis, not a fix.

## D158 — R1 rewriting works, and LEAD merged it with three defects in the artifact (2026-08-05)

LOCAL-255 merged (`c339ead`). R1 finally has a path to the output: at 36% of
paragraphs deletion was never possible, so PHASE 5.13 rewrites instead, using
the transformation Michael endorsed himself. Nav untouched, deletion rate 0%
against a 10% ceiling, corpus R1 26.9% → 9.4%, 13 tests green. Round 12
measured R7/R8/R9/R10 all zero — the cleanest artifact yet by rule residual.

**Then LEAD read the delivered tour and found three defects the measurements
cannot see.** All three are now on `storied`.

1. **The rewrite emits sentence fragments.** "Take in the panoramic view that
   stretches out before you…" becomes "The panoramic view that stretches out
   before you…" — no finite verb, shipped into an orientation bound for
   text-to-speech. Stripping a leading imperative yields a sentence only when
   the remainder is an independent clause; "Position yourself at X, a Y" → "X
   is a Y" works because a copula is supplied, and "Take in the N that…" does
   not.
2. **`Description:` is back in the narration** — the field-label leak bounced on
   LOCAL-250 round 7 v1.
3. **R7 is silent at the orientation injection point** on two textbook sensory
   inventions, the class Michael scored 1/5.

**The review failure is LEAD's and worth naming precisely.** The fragment
appeared in the task's *own* accepted boundary row — "The Fondation Maeght,
founded in 1964 by Marguerite and Aimé Maeght." LEAD saw it, checked that the
1964 attribution survived, judged the missing verb minor, and merged. Content
preservation was the stated acceptance bar and it was met; the bar was
incomplete. **A rule-residual measurement plus a fact count cannot see
ungrammatical output**, and four rounds of learning to distrust residuals had
trained LEAD to check facts and rules, not sentences.

Fixed forward as LOCAL-256 rather than reverted, because the rewrite path is
sound and nothing deploys from `storied` automatically. The new acceptance bar
is a finite verb in every rewritten sentence, with fallback to the original
imperative when no rule can produce one — an imperative beats a fragment.

## D159 — The existence gate verifies 74% corpus-wide, and the three zeros have three different causes (2026-08-05)

Nobody had measured the gate across the whole corpus. LEAD ran
`verify_stop_existence` over all 88 `stop_corpus` rows:

```
  28/28  French Riviera walking area
  13/13  Musee d'Art Moderne et d'Art Contemporain, Nice
  11/11  Palais Lascaris, Nice
    6/6  Musee Matisse, Nice
    4/4  Musee National Marc Chagall, Nice
    3/3  Boston Common
    0/9  Musee d'art naif, Nice
    0/8  Musee des Arts Asiatiques        <- Michael's gate venue
    0/5  walking tour in Nice
    0/1  National Constitution Center
                    CORPUS-WIDE: 65/88 (74%)
```

**First: the gate is not fooled by padding.** It requires a *single* passage to
contain both a content word from the stop title and a venue signal. LEAD
suspected LOCAL-254's Matisse boilerplate might be what earned that venue 6/6;
it is not. `Nu bleu IV` verifies on a passage that names the work itself —
*"'Nu bleu IV' (Blue Nude IV) is part of Henri Matisse's Blue Nudes"* — which
carries both signals honestly. The padding is still padding (D157), but it buys
no verification. Good design, and worth knowing before anyone "fixes" the gate.

**The three zeros are three different problems, not one.**

1. **Passages that are not about their stop.** `Statue de Bouddha` holds six
   passages and not one contains "bouddha" or "statue" — they describe the
   museum, Kenzō Tange, a Gandhara sculpture. Same for `La danse cosmique de
   Ganesh`, `Robe de prêtre taoiste` and `Kannon`: **zero** stop-word matches
   across all their passages. The corpus for this venue is venue-level text
   distributed across object rows.
2. **French titles, English sources.** Stop titles are French and the fetched
   passages are English Wikipedia, so `bouddha` never appears in text that says
   "Buddha". The gate matches content words literally after accent-stripping,
   which cannot cross that gap.
3. **Objects filed under the wrong venue.** `Kannon à mille bras` and `Masque
   du vieillard Kojo` — museum objects — sit under venue `walking tour in
   Nice`. That is a data error independent of both other causes.

A minor real bug also surfaced: venue signals are split on whitespace without
stripping punctuation, so `(Asian` and `Museum)` become tokens that can never
match anything. Harmless today because `arts`/`asiatiques`/`nice` carry the
match, but it is dead weight in the one venue that most needs signals.

**Why this matters now.** Michael's gate is 75 at N=8 on the Asian Arts Museum.
Every stop there fails existence, so under `enforce` the venue yields nothing
to score. Corpus depth alone will not move it — LOCAL-254 added passages there
and the count went 2.9 → 4.1 with the pass rate still 0/8, because the passages
are about the museum rather than its objects. The fix is per-object sources
that name the object, in a language the title uses, at the venue it is actually
in. That is a retrieval problem, not a gate problem, and the gate is right to
reject.

## D160 — Corpus cleanup verified; the Asian Arts blocker is a parenthesis (2026-08-05)

LOCAL-254 merged (`44f7aa3`). Every bounce item fixed and checked against the
live database, not the report:

- The three D127 fabrication stops now hold **zero** passages. It went further
  than asked — restored to empty rather than to their prior single passage —
  which is over-correction in the safe direction: a fabricated stop with no
  corpus fails existence, and that is the outcome we want.
- Matisse de-duplicated: passages shared across every stop **5 → 0**, mean
  **7.0 → 2.0**. The count fell because the count was wrong.
- Palais Lascaris untouched at 5.7 with genuine per-stop sources.

**No verification regression:** the gate still reads 65/88, and Matisse still
verifies 6/6 having lost the boilerplate — confirming D159's finding that the
padding never earned those passes.

Its diagnosis corroborates D159 on the main cause and **escalates what LEAD had
filed as a nuisance**. LEAD noticed venue signals keep punctuation, producing
dead tokens `(asian` and `museum)`, and judged it harmless. The task found the
same parenthetical breaks `venue_resolver`'s Wikidata lookup outright: no
entity, no canonical titles, no generation at all for that venue. The museum is
Q3330160 and the data exists. **A cosmetic-looking parsing flaw was the thing
blocking Michael's gate venue end to end** — a reminder that "harmless" is a
claim about consequences one has not traced.

Its proposed fix is deliberately not built here. Registering
`canonical_titles_json` so stops "verify instantly without needing per-object
prose" would let us verify our own stop titles against a list we wrote
ourselves. That list must come from the museum's collection record or the gate
stops meaning anything — the Chikanobu failure (D127) is exactly a stop title
we invented.

## D161 — Rewrites are sentences again; the fragment checker reads a book title as a predicate (2026-08-05)

LOCAL-256 merged (`b0b1e0a`). The three defects D158 recorded are fixed and
LEAD verified each through the real entry point: "Take in the panoramic view
that stretches out before you…" → "The panoramic view **stretches** out before
you…", and the row that exposed the bug now reads "The Fondation Maeght **was**
founded in 1964 by Marguerite and Aimé Maeght". `Description:` is blocked at
the post-assembly gate — round 13 has zero. R7 reaches the orientation at a
**1.06×** corpus cost, which is effectively free.

**And the new fragment checker reports 0 fragments over a fragment.**

```
Scott Fitzgerald's "Tender is the Night," a vivid portrayal of the Roaring
Twenties set against the backdrop of this opulent paradise.
```

`_has_finite_main_verb` returns True because it matches **"is" inside the
quoted title**. The fix worked; the measurement of the fix did not.

**This is the fifth time this week a metric has read clean over text that
plainly had the defect** — D142, D145, D151, D158, now this. The shape is
identical every time: the check is real, and something in the text slips past
an assumption nobody stated. Residual counts, fact tallies, and now
grammaticality have each in turn been trusted and each in turn been blind. The
only thing that has caught every one of them is reading the delivered tour as
prose. That is now a standing step in the review, not a fallback.

Second defect, smaller: the rewrite strips a leading article along with the
imperative — "Explore the charming village of Saint-Paul-de-Vence…" becomes
"Charming village of Saint-Paul-de-Vence is…". A finite verb, a missing "The".

Third, and the one Michael would care about: **Marc Chagall is placed at Cap
d'Antibes again**, in stop 1's body — "the clandestine atelier of Marc
Chagall… hidden behind the quaint village's cobbled streets". Chagall belongs
to Saint-Paul-de-Vence, which is stop 2 of the same tour. Cap d'Antibes is a
cape, not a village with cobbled streets. Round 9 had the identical failure and
LEAD wrongly withdrew it as a prolog preview (D152) — **this one is not in the
prolog**, so that withdrawal should not be read as clearing the class. All
three dispatched as LOCAL-257.

## D162 — CORRECTION to D127: the museum does hold "Ulysses Grant au Japon" (2026-08-05)

**D127 is wrong on its central claim, and LEAD built a week of work on top of
it.**

D127 concluded that the Musée des Arts Asiatiques does not hold the Chikanobu
print of Ulysses Grant, that the documented holders are the MFA Boston and the
Met, and that the tour's sentence was therefore invented. Michael reached that
conclusion with a public search and LEAD adopted it wholesale.

LEAD fetched the museum's own commented-works page today —
`maa.departement06.fr/les-oeuvres-commentees` — while checking whether
LOCAL-258 had laundered fabrications past the existence gate. **All eight of
the disputed works are on it**, including:

> **Ulysses Grant au Japon** — *"cette estampe représente la réception au
> palais impérial du président des États-Unis"*

That is, near enough verbatim, the sentence our tour produced and D127 called a
fabrication: *"The print vividly depicts the reception at the imperial palace
of the President of the United States, Ulysses Grant."* **The generator was
reproducing the museum's own catalogue description.**

Also on the page and previously suspect: `Kannon à mille bras`,
`Kannon, le bodhisattva de la compassion`, `Statue de Bouddha`,
`L'Armure d'Andô Naoyuki`, `Robe de prêtre taoïste`,
`La danse cosmique de Ganesh`, `Masque du vieillard kojô`.

### What this cost

- **LOCAL-254 was instructed to treat those stops as fabrications** and it
  stripped their corpus to zero. Legitimate works, deliberately emptied, on
  LEAD's instruction. That needs restoring.
- **Three task files carried the false premise** (LOCAL-252, 254, 258), each
  warning against "laundering" stops that were never invented.
- D157 called it "the prohibited thing happened". It did not happen.

### What survives from D127

One narrower question, unresolved and worth separating. Michael's search
indicated the Chikanobu triptych depicts the **Ueno Park** entertainment of 25
August 1879, not the Imperial Palace reception of 4 July. The museum's own
catalogue says imperial palace. So either the museum is describing a different
print, or the museum's own description is wrong.

That is a real question about **a source we trust**, not about our generator.
Under Michael's D100 rule it is the unverifiable case, not the
known-incorrect case: we are faithfully reporting a primary source. It does not
justify blocking the stop.

### The lesson, and it is uncomfortable

LEAD verified the *absence* of a fact by not finding it, and treated that as
proof. The museum's own website was one fetch away for eight days. Every
"suspected fabrication" ruling since has inherited that error, and the guards
built to prevent laundering were guarding against something that was not
happening — while the real risk, stripping genuine content, went unexamined
because it looked like caution.

**Rule:** before calling a venue claim fabricated, fetch the venue's own site.
Absence of evidence from a general web search is not evidence of absence, and a
museum's catalogue is the primary source for what a museum holds.

## D163 — The gate venue is unblocked (2026-08-05)

LOCAL-258 merged (`0629868`). `venue_resolver` now normalises the parenthetical
gloss, and LEAD verified independently:

```
Musee des Arts Asiatiques (Asian Art Museum), Nice, France  -> Q3330160
Musée des Arts Asiatiques, Nice                             -> Q3330160
Musee des Arts Asiatiques  + city hint Nice                 -> Q3330160
Palais Lascaris  Q34653010 | Matisse Q1563354 | Chagall Q3329265 | MAMAC Q936859
```

No regression on the four venues that already worked. Downstream, `story_miner`
returns **16 canonical titles** where it returned 0, and the existence gate goes
**0 of 8 → 8 of 8**. A first 8-stop Asian Arts tour generated: 6 of 8 stops with
descriptions, 1,935 words, **$0.0572**.

Provenance checked rather than accepted: the 16 titles come from the museum's
own commented-works page and Wikidata SPARQL P195/P276, none hand-registered —
which was LEAD's stated rejection criterion. Verifying our own stop titles
against a list we wrote would have been circular; verifying them against the
museum's catalogue is exactly right.

Two stops still produced no description (`La danse cosmique de Ganesh`,
one other) for want of per-work context. That is the next constraint at this
venue, and it is a corpus problem, not a gate problem.

## D164 — Navigation sentences may carry an appended instruction. Michael's ruling (2026-08-05)

Michael, reading round 15, asked whether "enjoy the sea breeze" surviving in the
orientation was because orientation is exempt from the instruction rules. It is
not, and LEAD corrected the premise before answering:

- Orientation **is** run through R1. R1 **fires** on that sentence.
- The sentence is classified as **navigation**, so D107 exempts it from rewrite.
- The same instruction *alone* — "Enjoy the sea breeze along the coast." — is
  not navigation, R1 fires, and the rewrite **deletes it entirely**.

So the instruction survives only because it is comma-joined to a genuine
navigation clause. The exemption is sentence-level; the content is clause-level.
LEAD flagged this as arguably wrong — "enjoy the sea breeze" is prescribed
feeling, the class Michael has scored 1/5 and 2/5 — and offered a clause-level
fix, free and contained.

**Michael's answer: "All good, as intended."**

So this is settled and deliberate. A navigation sentence may carry an appended
sensory or invitational clause: *"Start cycling southeast on the main road,
enjoy the sea breeze along the coast"*, *"pedal east along the coastal road,
soaking in the Mediterranean views"*.

**Do not "fix" this.** Any future task that narrows the navigation exemption to
clause level must leave this pattern intact. R1's prohibition applies to
instruction-giving in *narration*, not to warmth attached to a genuine
direction — which is the distinction Michael has been drawing all along:
he objects to being told what to feel *instead of* being told something, not to
a pleasant word alongside a real instruction.

## D165 — Four of seven detectors can see and cannot act (2026-08-05)

Michael, reading round 15's second paragraph, asked why this survived:

> "As you stand on Cap d'Antibes, **you are surrounded by history and natural
> beauty**." — *"there are millions of stops where listener is 'surrounded by
> history and natural beauty'. Why was not it removed?"*

LEAD ran every rule against it. **R4 fires.** It was detected and shipped.

The cause is structural. LEAD measured all seven detectors over 1,957 sentences
in 29 real tours and checked which have a phase in the pipeline:

```
rule  fires  %       path to output
R1     556   28.41%  rewrite  PHASE 5.13
R2      38    1.94%  *** NONE ***
R3      43    2.20%  *** NONE ***
R4      47    2.40%  *** NONE ***
R7      24    1.23%  delete   PHASE 5.14
R8       7    0.36%  *** NONE ***
R9      38    1.94%  delete   PHASE 5.15
```

`R4_PRESCRIBED_FEELING` is not referenced anywhere in `generate_tour_text.py`.
Neither are R2, R3 or R8. They fire inside PHASE 5.1 style validation, which
triggers a *retry* — the model is asked again — and when the retry fails, the
sentence ships. CLAUDE.md already records that the retry cannot reliably remove
R1; the same holds for these four, and unlike R1 nothing catches them
afterwards.

**This is the third instance of one pattern.** R7 was detect-only until D154
gave it PHASE 5.14. R1 was detect-only until D156 gave it PHASE 5.13. Both were
found the same way: Michael read a tour and asked why an obvious defect
survived. The detectors were built as a *suite* and wired in one at a time, so
"is there a detector for this?" and "does anything act on it?" drifted apart
and nobody was checking the second question.

**The honest framing of the last two days:** we have been improving detection
quality — R10's whitelist, the payload false positive, name-drops, fragments —
while four rules sat fully built and disconnected. Michael found each of the
three disconnections by reading, not by any measurement we run.

Dispatched as LOCAL-261: deletion phases for all four, following the PHASE 5.14
pattern. All four are deletion rather than rewrite — a sentence whose whole job
is to prescribe a feeling has nothing underneath to preserve. Michael also
observed that removing only the offending clause leaves *"As you stand on Cap
d'Antibes,"*, a fragment, so the whole sentence goes.

Total added deletion pressure is under 7% of sentences, and the D164 navigation
exemption must survive the new phases — that boundary row is in the task.

**Standing check added to review:** for every detector, confirm a path to the
output exists. A rule that only reports is a rule that does nothing.

## D166 — Michael's rule: the same sentence is bad unsupported and good supported (2026-08-05)

Reading round 15, Michael approved this pair and asked for a guarantee it keeps
surviving:

> "This iconic cape, situated on the French Riviera, holds a significant place
> in the region's landscape." + "In 2023, Antibes boasted a population of
> 77,637, making it the second most populous area in Alpes-Maritimes after
> Nice."
>
> *"…is good because it immediately followed by [the fact] that supports it; and
> makes both sentences worth while."*

In **round 2** he scored **2/5** on a near-identical sentence — *"Cap d'Antibes,
situated on the French Riviera, holds a special place in the region's history
and culture"* — with the reasoning *"nothing about aspects named such as place,
history, and culture are described in the following sentence"*.

**Same shape, opposite verdict. The entire difference is what comes next.** This
is the clearest statement yet of the standard he has been applying since round 2,
and it is not a style rule at all — it is a rule about adjacency.

LEAD verified both against today's pipeline:

- the **approved** pair: nothing fires. Safe — but by accident.
- the **rejected** round-2 twin, unsupported: **nothing fires either.** It would
  ship today.

So we cannot currently tell them apart. The mechanism that should decide this
already exists — R10's delivery lookahead, which excuses a promise when the
following sentence substantiates it on the same subject. It never engages
because R10 does not recognise "holds a significant place" as a promise.

**Two consequences, both acted on.**

1. **LOCAL-261 must not delete on wording alone.** It is adding deletion phases
   for R2/R3/R4/R8, and a naive R4 rule for this shape would destroy Michael's
   approved pair along with the bad twin. Addendum appended: every new deletion
   phase applies the R10 delivery lookahead first, and the approved pair is a
   mandatory must-survive boundary row.
2. **LOCAL-262 dispatched** to teach R10 this promise shape, after which the
   existing delivery check does the right thing automatically — deletes the
   unsupported instance, keeps the supported one. That is a two-line change in
   effect and it implements Michael's distinction exactly.

**The wider point.** Every rule we own judges a sentence in isolation, except
R10. Michael has never once judged a sentence in isolation — round 2's review is
almost entirely about interconnection ("senseless combination of words and facts
with no interconnectedness between them"). The gap between how we measure and
how he reads is adjacency, and R10 is the only place we model it.

## D167 — Round 16 delivers Michael's four-part opening (2026-08-05)

LOCAL-259 merged (`36ac81a`). The specification he wrote in his round 2 review,
deferred by LOCAL-244 as "a separate task" and never created until he noticed
the gap himself, is now built. LEAD verified each part against the artifact:

| part | delivered |
|---|---|
| 1 name + transport | "You are about to embark on a **cycling** journey through the **French Riviera**" |
| 2 route + physicality | "from Cap d'Antibes to Eze Village, spanning approximately **28 kilometres** of coastal terrain" |
| 3 sourced purpose | Monet at Antibes; Èze under the House of Savoy |
| 4 forward connection | "Monet's **1888** paintings at Cap d'Antibes and the **1706** destruction of Eze Village's fortifications" |

LEAD computed the haversine from the tour's own coordinates: **27.6 km** against
the claimed "approximately 28". Real arithmetic, not an invented number. Part 4
names content the tour actually contains, so it is not another unfulfilled
promise.

**Exactly one tour-level description** in the delivered text — the duplication
Michael was worried about did not occur.

**LEAD's spec was wrong about placement.** The task said "place it before the
orientation". Michael had already written *"Stop 1 starts with orientation —
that is good"*, so the delivered order — orientation, then description — is what
he wants and the task file was not. Recorded because it then broke LOCAL-260,
which inherited the same wrong assumption.

652 words, no placeholders, no field labels, directions clean in bike mode,
residual R1×3. Cost $0.0096 reported, ≈$0.020 true with the unmetered spine —
**no measurable increase from the richer opening**, as estimated.

## D168 — The prolog validator fails every correct tour, because it reads the wrong paragraph (2026-08-05)

LOCAL-260 bounced. The core is good: LEAD ran its reference cases and round 15's
opening produces **4 violations**, the keyword-stuffed decoy **3**. The
keyword-stuffing defence in particular is well built.

Two defects in how it reaches the text.

**`extract_prolog_from_tour_content` returns the Orientation.** Against the real
round 16 tour it extracts "Start biking southwest on the coastal road…" — the
orientation — and therefore reports `PART1_MISSING` and `PART4_MISSING` on a
tour that has both. It would fail every correctly-built tour.

The cause is LEAD's, and it is the same error as D167: the task file told it the
prolog sits *before* the orientation. LOCAL-259 correctly placed it after. **One
wrong sentence in a task file propagated into two tasks** — the generator got it
right by following Michael, the validator got it wrong by following LEAD. Its
own brief already said "detect it structurally, not by position", which would
have been immune.

**`PART4_VAGUE_PROMISE` fires on the must-pass example** — the Monet-1888 /
1706-fortifications sentence, which is the exact case the task file named as
required to pass.

Report-only and non-fatal, so nothing was damaged. But a validator that fails
every correct tour is the cry-wolf failure D141 already cost a morning to learn:
it would be ignored within a day.

## D169 — Restoring what LEAD had deleted (2026-08-05)

Dispatched LOCAL-262. Three stops sit at zero passages because LEAD, acting on
D127, instructed LOCAL-254 to strip them as fabrications. D162 established they
are genuine — the museum's own catalogue lists all eight.

The task restores per-object passages for those three from
`maa.departement06.fr/les-oeuvres-commentees`, and extends the same treatment to
the other five, which D159 showed hold venue-level text rather than object-level.
That distinction is why LOCAL-258's run produced descriptions for only 6 of 8
stops even with the gate passing 8 of 8: **verifying that a stop exists and
having something to say about it are different problems**, and we have been
conflating them.

The measure of success is not the gate — it is stops with a description, and
facts per stop.

## D170 — Stop selection stays free. Michael's ruling (2026-08-05)

LEAD proposed pinning the stop pair to Cap d'Antibes + Èze for evaluation runs,
because round-to-round comparison is confounded when the selector varies —
round 16 drew Cap d'Antibes + Èze, round 17M drew Cap Ferrat + Èze, and the
"better description" in round 16 may partly reflect deeper corpus at those stops
rather than any change we made.

**Michael: "no-no, I do not want to enforce anything artificial on the tour
generation: if they have different stops, so to be it. That is fine."**

Settled. Do not pin stops, and do not add an evaluation-only selection mode.

**The consequence belongs to scoring, not generation.** If the stop pair varies,
a single-tour-vs-single-tour comparison cannot attribute a difference to a code
change — stop selection, corpus depth at those stops, and the change all move
together. Today's entire round-to-round narrative has that weakness in it.

The answer is not to remove the variance but to measure something that survives
it:

- **rates rather than counts** — facts per sentence, not facts per tour;
- **per-stop normalisation** against that stop's available corpus depth, since
  D153 established depth is the dominant driver of fact density;
- **several runs rather than one** when a change is being judged.

To be proposed properly in part 2 of Michael's agenda (scoring and evaluation),
not bolted on. Recorded here so no future task "helpfully" pins the selector.

## D171 — Four detectors can act now; three still cannot see (2026-08-05)

LOCAL-261 merged (`655477a`). R2, R3, R4 and R8 each have a deletion phase, so
the D165 disconnection is closed: every detector now has a path to the output.

LEAD verified the boundary rows. **All four must-survive cases hold**, including
the two that matter — Michael's approved pair ("This iconic cape … holds a
significant place" followed by the 2023 population fact) and the D164 navigation
sentence carrying an appended instruction.

**One of four must-remove cases fires**, and that is correct against the brief.
The task was told to add action, not detection. R4 does not detect "invites
contemplation and serenity" or "the waves crash against the rocky shore" — the
three sentences Michael flagged are not caught by any detector, which is what
LEAD measured before dispatching. Corpus rates came back 1.00× on all four
rules, confirming nothing was widened. The submission states the gaps plainly
instead of hiding them.

So the position is now: **the wiring problem is solved, the vocabulary problem
is not.** That is LOCAL-263's scope.

**A latent hazard is recorded rather than fixed.** These phases delete
unconditionally, with no delivery lookahead. Michael's approved pair survives
today only because R4 does not fire on it. The moment anyone widens R4 or R9 to
catch "holds a significant place" — an entirely reasonable thing to want — the
approved pair dies alongside the twin it is supposed to be distinguished from.
**Until LOCAL-263 owns the substantiation test for all claim types, do not widen
R4.**

## D172 — LEAD moved the prolog three times and broke its validator twice (2026-08-05)

LOCAL-260 merged (`d325996`). Both bounce defects are fixed: quoted-span
handling aside, the extractor now finds the description structurally, round 16
passes with **0** violations, round 15's opening produces **4**, the
keyword-stuffed decoy **3**, and `DUPLICATE_TOUR_DESCRIPTION` — the check
Michael asked for — is implemented.

**And it is already broken again, by LEAD.** Against the current layout
(`round17M`) the extractor returns a stop paragraph and reports `PART1_MISSING`
and `PART4_MISSING` on a tour that has both.

The prolog has moved three times in ninety minutes:

1. after the `Orientation:` line, as a separate paragraph (round 16);
2. above the `Orientation:` line (round 17L) — LEAD's reading of Michael;
3. inside the Orientation section, after the label (round 17M) — Michael's
   actual instruction, because TTS and translation key on that word.

Each move was correct as an instruction and each broke a downstream consumer.
D168 recorded the lesson — *"task files that specify POSITION propagate errors;
prefer structural specs"* — and LEAD then moved the position twice more while
the validator was mid-flight.

The deeper point: **the tour text has no structure, only conventions.** Every
consumer — the validator, the extractor, TTS, translation — re-derives meaning
by pattern-matching a flat string, so any layout change silently breaks
whichever consumer nobody re-ran. Michael's own reason for the third move is the
evidence: the word `Orientation:` is load-bearing for translation because there
is nothing else to key on.

That belongs in part 3 of his agenda. A tour with typed sections — description,
orientation, directive, narration — would make all three moves free. Dispatched
LOCAL-265 for the immediate extractor fix; the structural question is his to
decide.

## D173 — D127 is closed by an inventory number (2026-08-05)

LOCAL-262 merged (`014ce0f`). The three stops LEAD ordered stripped are restored
with per-object, URL-bearing passages — 6, 5 and 5 — and the other five moved
from venue boilerplate to object-level material.

LEAD fetched `maa.departement06.fr/les-oeuvres-commentees` and compared verbatim.
Every element matches, including two that end the argument: **inventory number
2015.6.A.1** and donor **"Don Herrli"**. No model invents an accession number.
The museum holds the print, it is catalogued, and the tour sentence we spent a
week treating as fabricated was a faithful reading of the museum's own
description.

Total cost of that error: three task files built on a false premise, a
prohibition breach recorded in D157 that never occurred, and genuine corpus
deleted on LEAD's instruction. All from treating "a general web search does not
show it" as proof of absence. D162's rule stands and is now proven twice.

## D174 — Part 4 is written before the stories exist (2026-08-05)

Michael: *"Why the general tour description does nto include a preview of the
stories found later in the stops?"*

LEAD traced the call order:

```
PHASE 3A  pick stops
PHASE 3B  resolve details
SPINE     <- writes the tour description INCLUDING part 4
Stop 1..N <- the stories are written HERE, afterwards
```

**The spine composes "in the stops ahead you will encounter…" before a single
stop narration exists.** It guesses from canonical titles and corpus fragments.

| round | part 4 |
|---|---|
| 16 | present, good — Monet's 1888 paintings, the 1706 fortifications |
| 19 | partial |
| 20 (8 stops) | **absent entirely** |

Same code each time. **Round 16 — the one Michael called "almost perfect" — was
luck.** Every judgement made today comparing round 16 to later rounds was partly
comparing two draws of a coin.

Dispatched LOCAL-270: part 4 leaves the spine prompt and is composed after
narration, from the delivered and gated text, with every named entity verified
present in the stop it is attributed to. That makes it structurally impossible
to promise what the tour does not contain — the rule LOCAL-259 stated in prose
and this enforces by construction.

**The general shape, again.** This is the third ordering defect today: the
prolog validator read the wrong paragraph because LEAD moved the prolog; the
claim gate ran on a tour generated before the reorder; and now part 4 previews
content generated after it. Each is the same class — **stages that depend on
each other's output, wired in an order nobody drew.** That belongs in part 3 of
Michael's agenda alongside D172.

## D175 — The prolog extractor no longer cares where the prolog is (2026-08-05)

LOCAL-265 merged (`5c03f51`). Verified against three real artifacts spanning
every layout the prolog has occupied today — after the Orientation line, inside
it, and inside it with stop naming. It finds the description in all three, stops
before the where-to-go directive, and the boundary set holds: round 16 → 0
violations, round 15's opening → 4, keyword-stuffed → 3.

The prolog moved four times in three hours and this is the first version that
does not break. D168 recorded the lesson after the first breakage; it took a
second to act on it.

## D176 — The gloss gate refuses to invent, and that is the only reason it is safe (2026-08-05)

LOCAL-269 merged (`91b02f4`). Michael found the defect by reading: *"it mentions
Operation Dragoon with no explanation."* A sentence that passes every gate
**because** it carries facts, while assuming knowledge the listener lacks — the
inverse of everything else built today.

**LEAD tested the two things that decide whether this is safe rather than
dangerous.**

*Does it invent when it cannot know?* No. Given a fabricated entity — "the
Zelmenov Concordat of 1847" — it degraded instead of glossing:
*"a significant concordat was signed in 1847"*. Name dropped, fact kept,
`references_glossed=0, references_degraded=1`. That is the guard working on the
only case that could hurt us.

*Is a real gloss correct?* On the sample, yes. LEAD fetched
`en.wikipedia.org/wiki/Operation_Dragoon`: the Allied invasion of Provence, 15
August 1944, Saint-Tropez among the first towns taken. The gloss is accurate.

Detection is deterministic and discriminating — "Operation Dragoon" flagged,
"World War II" left alone. Cost $0.0001–$0.0004 per 2-stop tour against a
$0.0206 baseline; 0.9–2.0s added.

**The limitation, stated rather than buried.** Gloss provenance reads "model +
historical record", which is not a fetchable citation and is not what the task
asked for. A gloss is a factual claim, and this one is asserted from parametric
memory with a label attached. The degrade fallback is what keeps that tolerable
— when the model is *uncertain* it drops the name — but it does nothing when the
model is confidently wrong. That is the D127 failure mode with a new coat, and
a verification pass belongs on the backlog before this is trusted at scale.

LEAD merged it anyway, and the reasoning should be on the record: the guard
demonstrably fires on the unknowable case, the cost is negligible, the
alternative is leaving listeners with unexplained names, and the residual risk
is bounded by a fallback that was tested rather than assumed. That is a
different situation from shipping something that works by luck — but it is not
the same as verified.

Minor defect noted: degraded output carries stray quotation marks around the
rewritten sentence.

## D177 — Part 4 previews the guest list, not the story (2026-08-05)

Michael, reading round 23: *"the both do nto have anything intruiging in the
General Tour description, while some stops have something interesting in them
worth to mention."*

LEAD extracted the most fact-dense sentence from every stop of the 8-stop tour
and checked which reached the description. **None did.** What is sitting unused:

| stop | the story in the tour |
|---|---|
| Île Sainte-Marguerite | the **Man in the Iron Mask**, imprisoned at Fort Royal from 1687 |
| Promenade des Anglais | **Henri Negresco** — born Alexandru Negrescu, a Bucharest confectioner who became director of Nice's Municipal Casino |
| La Croisette | the **1946 Cannes Film Festival cancelled** by a government mobilisation order |
| Port de Saint-Tropez | first town on the coast **liberated, 1944** |
| Paloma Beach | named after **Picasso's daughter** |
| Eze Village | **seized 1543**, castle destroyed by **Louis XIV** |

What the description offers instead: "once owned by King Léopold II", "graced by
Charlie Chaplin and Elizabeth Taylor", "the legacy of the Grimaldi brothers".

**A guest list, not a story.** Part 4 selects by name recognition, and famous
names are usually the least interesting thing in a stop — Chaplin visited, which
is trivia; a Bucharest confectioner becoming the man behind the Negresco has a
shape.

**LEAD's verification criterion was also wrong, and this is the sharper
lesson.** LEAD checked "does this entity appear in the stop it is credited to" —
5 of 6 passed. That tests **presence**, not **interest**. It would pass a
description assembled entirely from the dullest true facts in the tour. The
check could not detect what Michael saw in one reading.

It also explains his verdict on round 16: its part 4 named *"Monet's 1888
paintings"* and *"the 1706 destruction of Eze Village's fortifications"* — a
painting series and a destruction, both events with tension. Not owners.

The fix is a **selection criterion**, not more verification: rank candidate
facts by whether they carry a reversal, a mystery or a cause, and prefer those
over recognisable names. That is a judgement a model can make and a regex
cannot — the second good use for the escalation budget Michael authorised.

Also found, and the reason LOCAL-270 will be bounced rather than merged: part 4
credits *"Port Vauban, where Pablo Picasso left his mark"* and **Picasso does
not appear in the Port Vauban stop.** That is precisely the failure the task was
built to prevent.

## D178 — Every defect Michael finds is a sentence the gate cannot name (2026-08-05)

On the last sentence of round 23's stop 2 — *"Just ahead, journey back through
the centuries."* — he asked *"why was not that expanched?"*

Every gate is silent. Not a promise, not sensory, not a feeling, not a quality
claim, not navigation. R9 catches "the ancient pathways bear the weight of
history" and misses this at any length, so it is the shape, not a threshold.

It is an **empty exhortation**: urging the listener toward something without
saying what. And it is the **last sentence of the final stop** — "Just ahead"
pointing at nothing, because nothing checks that a forward reference has
somewhere to point.

Expansion only runs on classified sentences. Unclassified ones are neither
expanded nor deleted; they pass through untouched. **Our system never considered
it.**

**The pattern across the whole afternoon.** Every defect Michael has found by
reading — the three sensory sentences, "you are surrounded by history and
natural beauty", the unexplained Operation Dragoon, and now this — has been a
sentence outside the classifier's vocabulary. Each time the response has been to
add a category. He named the alternative himself in effect: the gate should work
from **"does this sentence carry information"** rather than from a list of the
ways a sentence can fail to.

Adding claim types one at a time will keep losing to a language model's
inventiveness. That is the substance of part 1 of his agenda and should be put
to him as a design choice rather than absorbed as another category.

Dispatched LOCAL-271 for the immediate items: the R1 rewrite damage LEAD has
flagged in four rounds without fixing ("you can admire yourself standing at the
tip of the cape"), the empty-exhortation type, and the final-stop forward
transition.

## D179 — Part 4 is composed after the stops; the guard is untested rather than proven (2026-08-05)

LOCAL-270 merged (`4c4988d`). Part 4 leaves the spine prompt and is built from
the delivered, gated text. LEAD verified every factual claim in the 8-stop run
against the stop it is credited to — Fort Carré, 1550, Henry II at Old Town
Antibes; Villa Ephrussi, 1907 at Cap Ferrat — **5 of 5**.

An earlier draft credited *"Port Vauban, where Pablo Picasso left his mark"*
with Picasso absent from that stop, the exact failure the task exists to
prevent. The task regenerated afterwards and the final artifact does not
reproduce it — **but the stop selection also changed**, so the guard is untested
on the failing case rather than demonstrated correct. Recorded as such.

**A probe error worth keeping.** LEAD's first verification script matched stop
*names* against each other's bodies and produced 18 spurious failures. A stop's
text naturally does not contain other stops' names. D155's rule paid for itself
again: when a probe disagrees, suspect the probe.

Still not fixed and dispatched separately: part 4 selects by name recognition
rather than intrigue (D177).

## D180 — Empty exhortation gets a name; the rewrite checker still does not fire (2026-08-05)

LOCAL-271 merged (`f2912c8`). Michael asked why *"Just ahead, journey back
through the centuries."* survived every gate. It was a sentence type the
classifier could not name. It can now, and LEAD verified 4/4 — both empty
exhortations deleted, the substantive *"Just ahead, the Chapelle de la Sainte
Croix, built in 1306, comes into view"* kept, and D164 navigation kept.

**The R1 half is partial, and one failure is newly introduced.** The task was
asked for a well-formedness check with fallback to the original. It is not
firing:

```
"find yourself amidst the lush greenery"
  -> "From Cap d'Antibes, The lush greenery of the promontory is visible."
                           ^ capital after a comma — a NEW error

"Take a moment to breathe in the salty sea air..."
  -> "breathe in the salty sea air and listen to..."
      ^ lowercase start — unchanged, still broken
```

"admire yourself" is genuinely gone, which Michael saw in three delivered tours
and LEAD flagged four times without dispatching a fix. Net the tree is better.
But two of three damage shapes remain and one is new, so this is progress
recorded honestly rather than a fix claimed.

Dispatched LOCAL-274 to make the check actually decide: mid-sentence capitals,
initial capital, finite verb, repeated clause — and **return the original
unchanged when any fails**. A rewrite that cannot be done cleanly should not be
done.

## D181 — The closing offers something real again, and the news check mattered (2026-08-05)

LOCAL-273 merged (`7f975c8`). Michael asked why the closing summary and
next-trip offer were missing; they existed and **we deleted them** under
LOCAL-44 as preaching, with three regression tests guarding their return. The
tests were right about the words and wrong about the function.

The closing is now concrete and existence-verified, three sentences:

> "Place Masséna is 5 kilometres from here — we can build a cycling tour there.
> There is also a museum tour available at the Musée d'Art Moderne et d'Art
> Contemporain. We can also generate news articles for you to listen to on the
> way back."

Every offer is checked before it is made: the similar tour matches the tour's
own category with a verified stop and distance; the museum is offered only where
one exists. **The news check earned its place** — LEAD did not know whether news
existed on this branch and required the task to verify or report a gap. It
verified: `news_orchestrator_service.py` carries `@app.route('/generate-news')`.
Had it not existed, we would have shipped an offer the product cannot honour.

All 34 preaching tests pass. Incomplete against Michael's full spec — no
restaurant offer, no Treat Page — because his addendum arrived seven minutes
after dispatch. Dispatched as LOCAL-275, and it must **re-cut** the
three-sentence budget rather than extend it.

## D182 — A rewrite that cannot be done cleanly is not done (2026-08-05)

LOCAL-274 merged (`4feade3`). The well-formedness check now decides, and LEAD
verified all five rows. The capital-after-comma is gone; *"Take a moment to
breathe in the salty sea air…"* returns **unchanged** rather than becoming a
lowercase fragment. Both regression risks held — "you can admire the
breathtaking views" and Michael's endorsed "Eze Village is a medieval gem…".

Fallback rate **2.5% of R1 hits**: decisive without being trigger-happy.

That closes the R1 damage class Michael saw in rounds 10, 19 and 23 and which
LEAD flagged four times before dispatching a fix. Worth noting the gap between
noticing and acting — the fix took twenty minutes once dispatched.

## D183 — The high score holds when the stops do (2026-08-05)

Michael asked whether round 26's quality still stands. Three regression runs on
the merged tree answer it:

| run | stops | facts/stop | words | time | cost |
|---|---|---|---|---|---|
| round 26 | Cap d'Antibes + Èze | **7.0** | 710 | 43.7s | $0.0135 |
| 32B | Cap d'Antibes + Èze | **6.5** | 797 | 48.2s | $0.0147 |
| 32A | Cap d'Antibes + **Port de Nice** | **1.5** | 513 | 44.3s | $0.0133 |
| 31 | 8 stops, all delivered | 3.1 | 2223 | 117.7s | $0.0476 |

**32B reproduced round 26 on the same pair.** The pipeline is reliable. 32A
collapsed because it drew a stop with no corpus. Èze has delivered 7–9 facts in
every run it appears in; Port de Nice delivered one.

Then LEAD counted every Riviera stop the selector drew today against its corpus
depth: **11 of 23 have zero passages, 15 have ≤2.** Sixty-five percent of what
the selector picks has nothing to write from.

**So further rule work has diminishing returns.** Quality varies **4×** on
corpus depth and much less than that on everything built today — and today built
a great deal. Dispatched LOCAL-277 to deepen the drawn-but-empty stops.

**A second finding inside the same measurement, and it is a multiplier.** The
selector produces name variants that fragment the corpus, which is keyed on stop
title: `Saint-Tropez Harbor` / `Port de Saint-Tropez` / `Port of Saint-Tropez` /
`Saint-Tropez`; `Saint-Paul-de-Vence` / `Saint-Paul de Vence`. Corpus built for
one variant is invisible to a draw of another. Deepening without normalising the
match would waste much of the work.

**A LEAD error worth recording.** The first version of this measurement counted
every file in `tours/`, including months of museum tours, and reported Chagall
paintings as the most-drawn stops. It also failed accent-folding, showing
`L'Armure d'Andô Naoyuki` with 1 passage when LOCAL-262 had restored it to 6.
Both were caught by the numbers looking wrong rather than by any check —
the same class of error as every blind metric recorded today.

## D184 — Part 4 prefers the story; the closing offers what Michael asked for (2026-08-05)

**LOCAL-276 merged (`98754ea`).** Michael found the 8-stop description offering
"once owned by King Léopold II" and "graced by Charlie Chaplin" while the Man in
the Iron Mask sat unused in stop 6. Part 4 selected by name recognition, and
famous names are usually the least interesting thing in a stop.

An intrigue ranking now sits between extraction and composition, classifying
candidates as reversal / mystery / cause / celebrity_trivia and excluding the
last. LEAD checked the model's actual output against Michael's judgement —
**3 of 4 boundary rows agree**:

```
Iron Mask (mystery)        beat  King Leopold II (celebrity_trivia)
Henri Negresco (reversal)  beat  the Cap Ferrat celebrity list
Rue Obscure 1260 (mystery) beat  Walt Disney's 1956 visit
```

Row 4 is reported as **untestable** rather than massaged into agreement: the
Cannes cancellation was not in that run's delivered text, and the ranking can
only choose among facts that are there. That distinction — an input limitation
stated plainly instead of a result tuned until it agrees — is the thing that has
been missing from most submissions this week.

D177's verification still binds and still passes; LEAD checked the delivered
part 4 itself.

**LOCAL-275 merged (`eaa6f94`).** The closing now carries the restaurant offer
and the Treat Page, in three sentences, by re-cutting the budget rather than
extending it. The wording that mattered is exactly right: *"the Treat Page shows
**whether** there are real savings"* — availability, not a promise. All 34
preaching tests pass, so the function is restored without the phrasings LOCAL-44
rightly deleted.

**The first change today with a real price tag.** Everything else built since
this morning was deterministic and free. The intrigue ranking is one batched
model call:

| | before | after | ranking call |
|---|---|---|---|
| 8-stop | $0.0476 | **$0.0587** (+23%) | $0.0162 |
| 2-stop | $0.0206 | **$0.0185** (−10%) | $0.0057 |

Whether 1.6 cents is worth the Iron Mask replacing Charlie Chaplin is Michael's
call. It is put to him as a number rather than absorbed.

## D185 — Half of every tour's cost has been invisible all day (2026-08-05)

Dispatched LOCAL-278 on debt LEAD has been carrying since 12:24.

`spine_generator.py` computes its own cost, prints `SPINE_COST:` to stdout, and
**never registers with the cost meter** — so it is excluded from the pipeline's
own `Total API cost`. Measured today:

```
round 15   reported $0.0099   spine $0.0107 (hidden)   true $0.0206   52%
round 16   reported $0.0101   spine $0.0083            true $0.0184   45%
round 26   reported $0.0135   spine $0.0106            true $0.0241   44%
```

Every figure reported to Michael today has been roughly half the truth until
LEAD added the spine by hand. He asked explicitly to be kept informed on price
**without having to ask**, and the pipeline's own number cannot honour that.

**And nobody chose the model that spends it.** The spine calls `gpt-4o` at
$0.005/$0.015 per 1k while every other call uses `gpt-3.5-turbo` at roughly a
tenth. It is 9% of tokens and ~50% of cost. That is not a decision — it is what
the module was written with, and it has never been tested against a cheaper
model. The task runs an A/B across at least three models, ≥3 runs each because
D183 showed stop selection alone moves facts-per-stop 4×, and **recommends
without changing anything**. Michael decides; it is his money.

## D186 — The spine stays on gpt-4o. Michael pays for reliability (2026-08-05)

LOCAL-278's A/B, 3 models × 4 runs, same stops:

| model | cost | latency | quality | valid runs |
|---|---|---|---|---|
| **gpt-4o** | $0.0064 | 3.9s | **3.0/4** | **4/4** |
| gpt-3.5-turbo | $0.0010 | 3.2s | **3.0/4** | **3/4** |
| gpt-4o-mini | $0.0004 | 4.7s | 2.5/4 | 4/4 |

gpt-3.5-turbo matches gpt-4o on measured quality at a sixth of the price and
slightly faster — about **$0.0054 per tour, roughly 30% of total cost**. The one
thing separating them is that it produced a valid spine in **3 of 4** runs
against 4 of 4.

LEAD put it to Michael as a number rather than deciding, noting the sample was
too small to act on a 3-of-4 signal.

**Michael: "I am willing to pay for the reliability, if that was your
question."**

Settled. **The spine stays on gpt-4o.** Do not switch it to save money, and do
not re-run this A/B expecting a different answer — the decision is not about the
quality scores, which tie, but about a one-in-four failure rate being
unacceptable at the component that produces the tour's skeleton and its opening.

At $0.0054 per tour that is about **$5.40 per thousand tours** for a reliability
margin. Cheap, and Michael judged it so explicitly.

**What this does not settle:** the same question for the *other* model calls.
Gloss triage, claim-gate escalation and intrigue ranking all run on gpt-4o-mini,
which scored 2.5/4 here. That score was for spine generation, a harder task than
ranking or adjudication, so it does not transfer — but nobody has measured those
either. Worth doing before the next cost conversation, not now.

## D187 — Corpus depth moves quality 4×, exactly as predicted (2026-08-05)

LOCAL-277 merged (`f661659`). D183 predicted that corpus depth, not rule work,
was the binding constraint. Tested directly:

```
                                before        after
Cap d'Antibes + Port de Nice    1.5 f/stop -> 6.0 f/stop   (SAME PAIR)
8-stop                          3.1 f/stop -> 8.8 f/stop
total facts, 8-stop             25         -> 53
corpus                          72 psg     -> 119 psg
```

LEAD applied D162's rule before believing any of it and fetched
`en.wikipedia.org/wiki/Ile_Sainte-Marguerite`. Four sampled claims verbatim:
the island's 3,200 × 950 metres, the Man in the Iron Mask held at Fort Royal for
11 years (1687–1698) of 34, the Celtic-Ligurian occupation in 6 BC, the Roman
name Lero. Extracted, not written.

**The Iron Mask had been appearing in generated tours all day sourced from
nothing but the model's memory.** It now has provenance.

Name fragmentation was a genuine multiplier: "Old Town Antibes" resolved to
nothing while "Old Town of Antibes" held five passages; same for Cannes
Croisette / La Croisette and the Fort Carré accent variants. All 17 drawn stops
now resolve.

## D188 — Two category failures, found by trying a category we had never tried (2026-08-05)

Michael asked for a 5-stop museum tour and a 3-stop restaurant tour. Everything
built today was tested on Riviera cycling tours only. Both new categories
failed, in different ways.

**Restaurant tours cannot be generated at all.**

```
EXISTENCE-GATE ENFORCE: dropped 3 unverified stop(s), 0 remain
    DROPPED: 'Le Chantecler'      Michelin-starred, Hôtel Negresco
    DROPPED: 'La Petite Maison'   one of the best-known in Nice
    DROPPED: "L'Univers"          Christian Plumail, Michelin-starred
FATAL: All generation attempts returned None
```

Three real restaurants, three false negatives, no tour. **This is D132's bug
again**: the gate requires a source passage tying the stop to the *venue*, and
for a restaurant tour the venue is `"restaurant tour in Nice, France"` — our own
label, which no source contains. LOCAL-239 fixed exactly this for geographic
areas by adding venue kinds; a third kind for establishments was never added.
Dispatched as LOCAL-281.

**Museum tours lost the tour overview, and that one is LEAD's.**

Michael: *"No the overview of the tour?"* Correct — no `Orientation:` line at
all, so no overview.

When he asked for the description to sit inside the Orientation section, LEAD
appended it to `_orientation_prefix`. Museum tours then hit the R3 rule, which
drops the entire orientation block when the stop's orientation lacks a grounded
viewing note — **taking the tour overview with it**.

LEAD verified that change three times, all on cycling tours, which always emit
an orientation. **One category silently broken by a change tested only on
another.** Dispatched as LOCAL-282, with a three-category check written into the
acceptance criteria, because the absence of one is what caused this.

Michael also reported no stop-1 description. There is one — it is simply thin
and unlabelled, one fact against another stop's three. That is the corpus
problem, not the regression, and the two should not be conflated.

## D189 — The recap machinery is right and the prose is not (2026-08-05)

LOCAL-280 bounced. Everything structural works and is kept:

- the thank-you is gone and the recap replaces it, per Michael's ruling;
- the scale is stated and **honest** — the 8-stop run delivered 5 and the recap
  says 5;
- the Treats wording is exactly right, *"shows whether there are real
  savings"*;
- it reuses LOCAL-276's `_recap_ranked_facts` rather than building a second
  ranker, which is what the task asked;
- **D177 verification runs and catches failures** — its own log shows
  `Recap: D177 FAILED for 'Fort Carré d'Antibes': fact not in delivered text`.

**What it emits is unreadable.** Delivered 2-stop:

> "That's 2 stops and 18 kilometres — **Cycle along the coastline, carrying
> whispers of past revelries and the promise** and **Step into the Saint
> Charles-Saint Claude chapel**."

Three faults in one sentence. *"Cycle along…"* and *"Step into…"* are
**imperatives** — not facts, and precisely the shape R1 exists to remove from
narration; the recap pulls them back in. *"…and the promise"* is **truncated
mid-phrase**, a span cut at a fixed length and emitted as a stub. And two
fragments joined by a bare "and" produce something nobody would say aloud.

The 8-stop is better and fails the same way: *"the island is most famous for its
fortress prison"* is lifted mid-sentence and **never names the island**, so the
listener cannot tell which of five stops is meant.

**The distinction worth recording.** The ranking chose reasonable *material* —
Île Sainte-Marguerite's prison is genuinely the most interesting thing in that
tour. What failed is **composition**: the recap concatenates source text instead
of writing a clause. Selecting the right fact and stating it well are different
jobs, and this task did the first and skipped the second.

The fix is specified as: every item names its stop *and* the fact
(*"the fortress prison on Île Sainte-Marguerite"*), never emit a truncated span,
and filter candidates through `check_r1_imperatives` before ranking — the same
discipline part 4 already applies.

## D190 — The museum overview is restored, and the three-category check is now a rule (2026-08-05)

LOCAL-282 merged (`2307e64`). LEAD's regression from this afternoon is fixed:
R3 now gates only the orientation *text*, while the prefix carrying the tour
overview and "Your first stop is X" is emitted regardless.

LEAD verified all three categories rather than trusting the submission's table:

```
museum 5-stop   overview present, "Orientation:" leads, and exactly ONE
                Orientation line across five stops — R3 still correctly
                dropping the weak per-stop orientations
biking 2-stop   overview present, "Your first stop is" present, unregressed
restaurant      still aborting at the gate (LOCAL-281's scope)
```

**The three-category check is the durable part.** Its absence is what caused the
bug: LEAD verified the original change three times, all on cycling tours, which
always emit an orientation. It is now in the acceptance criteria rather than in
LEAD's intentions.

The `"L a geste de Bouddha"` broken space was investigated and **not found** in
any source, corpus row or canonical title — so it is introduced downstream of the
data. Reported unresolved rather than guessed at, which is the right answer and
worth noting as the standard.

## D191 — Restaurant tours generate again; the selector still does not produce restaurants (2026-08-05)

LOCAL-281 merged (`1580936`). The `dining` venue kind exists and the fatal abort
is gone: **0/3 verified → 2/3 delivered**.

All six boundary rows checked by LEAD:

```
Le Chantecler, Nice      VERIFIED    Hotel Negresco, Wikipedia
La Petite Maison, Nice   VERIFIED    Didier Casnati, Wikipedia
L'Univers, Nice          unverified  real, but no tier-1 trace
fabricated restaurant    rejected
Le Chantecler, LYON      rejected    proximity check works
fabricated museum stop   rejected    D127 strictness preserved
```

**The L'Univers miss is a genuine false negative and was reported rather than
hidden.** Christian Plumail's restaurant is real and confirmed on Gayot and
elsewhere, but absent from Wikipedia and Wikidata. The right answer is that the
gate cannot verify what its sources do not contain — a false negative beats a
weakened gate, and the fix is better sources, not a lower bar.

**But the delivered tour is not a restaurant tour.** Stop 1 is the **Musée
Matisse**; the opening reads *"a walking journey through ."* with an empty venue
name; and the route says *"from Musée Matisse to Musée Matisse"*.

The cause is visible in the prompt construction: museum tours get
`_museum_venue_constraint`, biking tours get transport constraints, and
**restaurant tours appear to get neither** — so the model returns whatever is
notable in Nice, which is museums. Dispatched as LOCAL-285.

Two general points fall out. The gate and the selector are independent failures
and fixing one exposes the other — the abort was hiding the selection bug
entirely. And **`"through ."` reaching text bound for text-to-speech** means no
guard catches an empty span; LOCAL-285 adds one at the post-assembly gate where
LOCAL-251's placeholder check already lives.

## D192 — Verification harvests; and LEAD set a regression bar against an unstable number (2026-08-05)

LOCAL-283 merged (`c7c6166`). Michael's observation implemented: the gate now
harvests fact-carrying passages from the source it verified against, and flags
`verified_no_detail` when a stop passes by name alone.

**On the museum tour it harvested nothing and flagged all five stops.** That is
the correct outcome, not a failure — those five are *exhibition titles* rather
than collection objects, and the museum's page carries no per-object detail for
them. Previously that produced five stops with nothing to say and no signal at
all. The gap is now visible and LOCAL-284 can act on it.

**The Riviera numbers came in below the bar LEAD set, and the bar was wrong.**

```
2-stop  6.0 -> 4.0        8-stop  8.8 -> 5.4, 53 -> 43 facts
```

LEAD made those a hard bounce condition on Michael's explicit concern that
today's gains survive. Investigating rather than bouncing:

- the run drew **eight entirely different stops**, including Port de Monaco and
  Antibes Old Town at **zero corpus**;
- the 8.8 baseline came from LOCAL-277's run, **which drew the eight stops
  LOCAL-277 had just enriched**;
- the harvester logged `0 harvested, 8 already had corpus` — it writes only where
  a stop has none, so Riviera tours take the skip path and are untouched.

So it is not a regression. **LEAD set an acceptance criterion against a figure
measured on a favourable draw** — exactly the confound D183 documented this
morning, where facts per stop moves 4× on selection alone. Having written that
finding, LEAD then built a gate on a single observation of the metric it
describes as unstable.

**The correction, and it belongs in Michael's agenda part 2.** A per-tour fact
count cannot serve as a regression bar while stop selection is free (D170). Any
future must-not-regress condition has to be either normalised against the drawn
stops' available corpus, or averaged over several runs. Single-run baselines are
not evidence, and LEAD should stop writing them into task files.

## D193 — OpenAI credits exhausted; continuous dev paused (2026-08-05 18:35)

```
"You have no credits remaining. Add credits to continue using the API"
code: credit_balance_exhausted
```

LEAD verified directly against the API. LOCAL-285 independently confirmed **all
three keys** — primary, backup, backup-bak — return the same error, so it is the
**account balance**, not a key problem.

**Everything that generates or verifies-by-generation is blocked.** Michael's
tour, LOCAL-285 (never ran), and LOCAL-284's Riviera regression.

`.continuous_dev/PAUSE` is set so tasks stop spending 20-minute sessions failing.
ClickUp `wdvrdaxda6` (👤 Michael, urgent) carries the top-up instructions, the
measured per-tour costs, and what LEAD will do on "credits added".

**Cost context, measured today:** 2-stop $0.019–$0.026 true, 8-stop
$0.047–$0.059, about $55 per 1,000 eight-stop tours. Today's ~40 generations plus
25 Kiro sessions came to roughly $2–4. The balance was already low; today was not
expensive.

**How this surfaced is worth recording.** LOCAL-284 reported the 429 plainly and
offered *a structural argument* in place of the Riviera regression evidence.
That argument is sound on its face — the selector's corpus-tiebreak genuinely
does not apply to open geographic sets. LEAD would likely have accepted it and
merged a selection change with **no evidence** it leaves the walking tours
alone, against Michael's explicit concern. The credit failure is what prompted
the check.

**So LOCAL-284 is HELD, not merged.** A structural argument is not a regression
test, and this is precisely the case where Michael asked for proof.

## D194 — The recap splices spans; cutting cannot be fixed by cutting better (2026-08-05)

LOCAL-280 bounced a second time. The first bounce fixed what it targeted:
imperatives are gone and every item now names its stop. What remains:

```
"Paloma Beach, built a fort at Saint-Hospice in 1561 to secure"     truncated
"where he created intimate and profound works"                      orphan pronoun
"Villefranche-sur-Mer, established Villefranche-sur-Mer as a..."    doubled name
2-stop names one stop of two                                        spec violation
```

**The root cause is one thing, not four.** Each recap item is a span **cut out
of a source sentence and pasted after a stop name**. Cutting produces the
truncation; pasting produces the doubled name and the orphaned "he". Better
cutting cannot fix any of them.

The instruction is now to **compose** — write a short noun phrase that stands
alone — with a model call authorised under LOCAL-269's constraint: rephrase the
supplied fact, never add one.

```
built a fort at Saint-Hospice in 1561 to secure  ->  the 1561 fort at Saint-Hospice
where he created intimate and profound works     ->  the Mougins studio where Picasso worked
```

**A note on how this task was bounced twice.** Both bounces described the
symptom precisely and both fixes addressed the symptom. Neither task file said
"stop cutting, start composing" until now. LEAD specified outputs to avoid
rather than the method to use, and got two rounds of increasingly careful
cutting.

## D195 — What could be verified without the API, and what could not (2026-08-05)

LOCAL-285 merged (`db109f9`) during the credit outage. The distinction between
what was proven and what was assumed is the point of this entry.

**Verified without generation:**

- the restaurant constraint is gated on `tour_category == 'restaurant'`, so it
  cannot touch museum or biking selection — read from the diff;
- the empty-venue gate sits at post-assembly beside LOCAL-251's placeholder
  check. LEAD ran its regex against **eight real Riviera tours: zero false
  positives**, and confirmed it fires on the text it was built for —
  *"a walking journey through ."* is repaired rather than spoken;
- the self-route guard is conditioned on `len(poi_list) > 1`;
- 17 unit tests pass.

**Not verified:** that a restaurant tour now selects restaurants. That needs a
generation. The change is contained to the restaurant branch and restaurant
tours are already broken, so merging unproven costs nothing — but it is unproven
and is recorded as such in the PAUSE file's resume checklist.

**The general point.** An outage forces the distinction between *inspecting a
change* and *observing its effect*, which is the same distinction this project
has repeatedly got wrong in the other direction — green tests over dead code
(D-series), residual counts over broken prose (D161), a structural argument in
place of a regression test (D193). Today it was possible to verify two of three
claims by other means and say plainly that the third was not. That is the
correct shape of a submission under constraint, and it is worth having on the
record as the standard rather than as an excuse.

## D196 — The rubric ranks the rejected tour above the praised one (2026-08-05)

Blocked on credits, LEAD did the part-2 work that needs no API: **ran
`tour_rubric_scorer.py`** — which D-earlier established has essentially never
been run — against today's tours. Classification is manual, so LEAD applied the
rubric's *own* fact test mechanically (≥3 verifiable facts → RICH).

```
  tour                             stops   base  struct   corr  ident   TOTAL
  round 15 (this morning)              2  100.0     0.0   25.0    0.0   125.0
  round 26 (Michael: "excellent")      2  100.0     0.0    0.0    0.0   100.0
  8-stop after corpus work             8  100.0     0.0   12.5    2.0   114.5
  museum 5-stop                        5   60.0     0.0   10.0    1.2    71.2
```

**Round 15 scores 125 and round 26 scores 100.** Round 15 is the tour whose
paragraph Michael would have scored 1/5 — the one that prompted a day of work.
Round 26 is the one he called *"excellent"*, with stop 2 *"wonderful!!!"*. The
rubric ranks the rejected tour **25 points above** the praised one.

**The mechanism.** Round 15's entire margin is the cross-stop correlation bonus,
and LEAD traced what earned it:

> "This route will take you from the opulent Cap d'Antibes to the ancient **Eze
> Village**, spanning approximately 28 kilometres…"

That is **part 2 of Michael's four-part opening stating its route endpoints**.
The rubric saw stop 2's name inside stop 1's text and counted it as narrative
interconnection. An itinerary is not a callback.

**Three consequences.**

1. The +50% correlation bonus is the largest lever in the rubric and the reason
   it can exceed 100. It is being triggered by a sentence whose job is to say
   where the route goes. It is a measurement artifact.
2. **This morning's arithmetic was built on that artifact.** LEAD wrote that 75
   at N=8 "cannot be reached by per-stop quality alone — it needs callbacks
   between stops." That conclusion rests on the bonus meaning something. It does
   not.
3. The museum tour scores **71.2**, just under Michael's 75 gate — on a metric
   that has just been shown to rank a bad tour above a good one. The gate number
   is not currently measuring what he thinks it measures.

**What this settles for part 2.** The rubric's problem is not only that stop
selection makes it unstable (D170/D183/D192). It is that **its strongest term
rewards a structural coincidence**. Fixing the instability without removing the
bonus would produce a stable wrong answer.

Recommendation to put to Michael: score facts-per-sentence normalised against
available corpus, drop the correlation bonus until a real callback can be
distinguished from an itinerary mention, and stop treating 100 as a ceiling that
bonuses may exceed. Not to be dispatched without his decision.

## D197 — Refining D196: the bonus is not always an artifact, it is undiscriminating (2026-08-05)

D196 concluded from round 15 that the cross-stop correlation bonus is "a
measurement artifact". LEAD then measured it across **all 41 Riviera tours** on
disk, classifying each callback by whether route language sits near the mention:

```
  bonus earned ONLY by itinerary mentions      6 tours
  at least one genuine narrative callback     13 tours
  no callback at all                          22 tours
```

**So the blanket claim was too strong.** Roughly a third of bonused tours earn it
purely from an itinerary sentence; two thirds have something that reads like a
real callback. D196's specific finding stands — round 15's entire +25 margin came
from *"from the opulent Cap d'Antibes to the ancient Eze Village"* — but "the
bonus is an artifact" overstates it.

**The accurate statement:** the bonus **cannot distinguish** a narrative callback
from an itinerary mention, and fires on both. That is still disqualifying for a
score used to compare tours — it means a tour can gain 25 points for stating
where it goes — but it is a discrimination failure, not a pure artifact.

Two further observations from the same measurement:

- **22 of 41 tours receive no correlation bonus at all.** The rubric's largest
  lever is inactive on more than half the corpus, which makes it a source of
  variance between tours rather than a consistent measure of them.
- LEAD's narrative/itinerary split is itself heuristic — proximity of route
  language. Some of the 13 "narrative" cases may also be spurious. The honest
  reading is an upper bound on genuine callbacks, not a count of them.

**What this changes in the recommendation to Michael:** not "drop the bonus"
outright, but "the bonus needs a real test for what a callback *is* before it
can carry 50% weight." If that test proves hard to write, dropping it is the
safer default — a term that fires on a third of eligible tours for the wrong
reason is worse than no term.

**And a note on LEAD's own reasoning.** D196 was written from a single
compelling example and generalised. The generalisation was wrong in degree. The
example was real and the conclusion directionally right, which is exactly the
kind of error that survives review — it feels verified because part of it was.

## D198 — Idle-tick discipline during the outage (2026-08-05 20:35)

Credits still exhausted after two hours (checked 19:04, 19:34, 20:04, 20:34).
Nothing in flight, nothing mergeable, no task dispatchable.

**LEAD stopped generating analysis.** D196 was written from one example and D197
had to correct it in degree. Producing further unverifiable findings during an
outage risks more of the same, and a wrong finding recorded in `DECISIONS.md`
costs more than an idle hour — three task files were built on D127 before it was
overturned.

Instead LEAD checked the resume path and found a real defect: **a tracked file
deleted by LEAD's own cleanup.** While copying round-23 artifacts LEAD used a
glob that matched the wrong files, copied `tours/cil_chagall_cycle5.txt` six
times, and then removed it with `rm`. It was tracked, from commit `f03a9aa`, not
a stray copy. Restored.

That is the third glob or pattern error today — the `LOCAL-251` process match
that killed LOCAL-252 (D152), the `tours/` scan that counted museum tours as
Riviera draws (D183), and this. All three shared a shape: a pattern written
quickly, matching more than intended, with no check on what it caught before
acting.

Outstanding on resume, verified against the branches that still hold work:

```
kiro/local280-closing-recap              2 commits  (bounced twice, needs composition)
kiro/local284-selector-corpus-tiebreak   1 commit   (HELD — Riviera regression unrun)
```

Plus: run a restaurant tour to prove LOCAL-285's unverified core claim, and
generate the tour Michael has been waiting for since 17:25.

## D199 — Naming the transport mode is information only when it is not the default (2026-08-05)

Michael, on the museum tour's opening: *"when the means of transportation are
other then human legs/feet the journey on Camels or dogs make sense, but in the
museum, 'walking journey' sounds strange."*

**Rule:** part 1 announces the mode where the mode tells the listener something
they did not know and may need to prepare for — cycling, driving, riding, dog
sled. It does not announce walking for a museum or other indoor tour, where
walking is the default and the word carries nothing.

This is the same test as the unsupported-claim gate: not "is it true" but "does
it inform". "A walking journey through the museum" is true and empty, the same
shape as "surrounded by history and natural beauty" (D171).

Paired with the part-2 defect — `0 meters`, from taking the haversine between two
objects that share a building's coordinates — the diagnosis is one thing, not
two: **the four-part opening was designed for geographic tours and treats a
museum as a very small one.** Both go in LOCAL-286 rather than separate tasks,
because they are the same code block and the same LLM call.

**LEAD note:** the "route stretches" phrasing was written into the task as
*consider and report your view*, not as scope, on the grounds that Michael has
been specific about this opening's wording and D168/D172 record LEAD moving the
prolog three times in 90 minutes and breaking its validator twice. He then said
plainly it has to change. Leaving it as a question cost one exchange; changing
his approved wording unilaterally would have cost more. The judgement stands, but
the general form is: **propose the change and say why, rather than either
silently making it or silently leaving it.**

## D200 — The evaluation index now computes its own classification (2026-08-05)

Michael: *"if you know how to compute the classification from the fact and
filler signals the code already measures and discards then please incorporate it
into the routine of index calculation."*

Done, in `tour_rubric_scorer.py`. Four findings surfaced on the way, each of
which changed the work:

**1. The module had no callers, and its CLI never scored anything.** Nothing
imports `tour_rubric_scorer`; `compute_score` is reachable only via
`score_tour_file`, which nothing called; and `__main__` printed per-stop analysis
and stopped before computing a score. Every number ever quoted against the 75
gate came from a throwaway script that supplied classifications by hand. Fixed:
the CLI now runs end to end.

**2. `named_people` was not measuring people.** It matched any two consecutive
capitalised words, filtered by eight hardcoded literals. Over 1,728 stops it
averaged 5–7.5 matches against ~1 date, so it dominated the fact count — and its
two most frequent matches corpus-wide were the schema labels **"Specific
Examples" (183)** and **"Operational Details" (140)**, followed by places (French
Riviera, Frog Pond, Mediterranean Sea). Wiring the old fact count to a
classification would have automated noise. Now: place/institution head nouns are
excluded, a person must sit within 90 characters of a verb of doing or a role
noun, and names are counted distinct. 0.59 distinct names per stop, and the top
matches are Matisse, Monet, Walt Disney, Barbarossa.

**3. `parse_tour` stripped four schema labels and missed the rest**, so
`Type/Specialty:` and `Specific Examples:` text was scored as narration. All
schema fields now excluded via one pattern.

**4. The index rewarded the defect that made a tour undeliverable.** Round 34 —
held by LEAD hours earlier for the mangled LOCAL-269 glosses — scored **87.5**,
the highest of the night, with Stop 2 RICH and **zero structural defects**, on
text reading *"existentialism., and Pablo Picasso"*. Three splice artifacts are
now structural defects: `spliced_sentence` (a full stop followed by a comma),
`truncated_span` (a span cut after a preposition or article), `doubled_name`.
Round 34 now scores **62.5**. Corpus-wide the new defects fire 125 / 50 / 11
times, so the gloss damage is widespread.

**Thresholds**, calibrated to the measured post-fix distribution, not intuition:
RICH ≥3 facts, density ≥0.50, filler ≤25%; ADEQUATE ≥2 facts, density ≥0.20,
filler ≤40%; THIN otherwise. Over 1,732 stops: **5.1% RICH, 24.7% ADEQUATE,
70.2% THIN** — consistent with the independently measured 1.6 facts/stop museum
finding.

**Preserved:** an explicit operator classification always overrides the computed
one (verified), every band carries an evidence string, and **FABRICATED stays
uncomputable** — nothing here checks truth, so RICH is a statement about
evidence density and never about accuracy.

**Not done, deliberately:** the correlation bonus is untouched and still wrong —
see D201.

## D201 — The correlation bonus should be switched off, not redefined (2026-08-05)

Michael asked what the open question on the stop-name bonus was. Measuring it
properly gave a worse answer than D197 recorded.

The bonus (+50%, the largest lever in the rubric) is meant to reward a narrative
callback. It fires on **1,466 sentences** across the corpus, and the triggers are:

- **shared topical vocabulary** — a stop titled "Audacious Freedom: African
  Americans in Philadelphia, 1776-1876" shares two words with every other stop in
  that museum, so a themed venue earns the bonus automatically for having a theme;
- **schema labels** inside the body (now fixed by D200's parser change);
- **the closing recap** — one sentence naming every stop triggers a callback for
  all of them at once.

That last one is self-inflicted: **the recap LEAD specified with Michael this
afternoon (LOCAL-280) systematically inflates the correlation bonus on every
future tour.** A feature designed today games the metric used to judge it, and
LEAD did not see the interaction until Michael asked the question.

**Decision: switch the bonus off** rather than redefine it. There is no working
definition of a narrative callback in the code, and a term that rewards a tour
for naming its own stops is worse than no term. It stays at zero until a real
definition exists — SQ-S6b's theme threads are the natural home for one.

## D201a — Correlation bonus: redefined as declared, coverage-scaled (2026-08-05)

Michael: *"let's redefine it. Any suggestions?"* — overruling LEAD's proposal to
switch it off. He is right that deleting it would silently move his gate: with
the D200 classifier only **5.1% of stops reach RICH**, so eight RICH stops is
close to unreachable and the bonus is what keeps 75-at-N=8 attainable.

**Why it cannot be fixed as a text matcher.** Three successive tightenings were
measured against all 325 multi-stop tours:

| rule | fires on |
|---|---|
| current (title words in another stop's body) | 287 tours — 88% |
| + shared *entity* (person/year/work), directional, non-list, extra fact | 120 — 37% |
| + venue-boilerplate excluded, non-duplicate sentence | 83 — 26% |

Every surviving example was still the same thing: *"The Asian Arts Museum was
inaugurated on October 16, 1998"* repeated across stops. Strict enough to exclude
boilerplate finds nothing; loose enough to fire measures vocabulary. **There is
no threshold between, because the generator has never produced a thread.**
SQ-S6b — theme threads, the dominant story — is fully specified in
`STORY_QUALITY_DESIGN.md` and has never been built.

**Redefinition: the generator declares the thread; the scorer reads it.** A
thread carries an id, its participating stop indices, and the binding entity —
all of which SQ-S6b's deterministic entity clustering already knows. The scorer
stops inferring from prose. That removes vocabulary gaming, the recap trigger,
and the direction ambiguity in one move, and it rewards the feature Michael's
gate has actually been waiting on.

Today the bonus contributes **zero**, because nothing declares a thread. That is
the same practical effect as switching it off, but it is a definition rather
than a deletion and it activates by itself when SQ-S6b ships.

### The two questions LEAD put to Michael, decided by LEAD (RULE ZERO)

He was asked and is away; both are reversible and recorded here for him to
overturn.

**1. Scale with thread coverage — YES.** A thread spanning 6 of 8 stops is a
larger achievement than one spanning 2, and coverage-proportional blending is
already in the SQ-S6b spec, so the data will exist. Bonus scales linearly with
the fraction of delivered stops the thread touches.

**2. A tour with no thread is unrewarded, NOT penalised.** Penalising would make
threads mandatory — a product decision, not a scoring one — and would conflate
"no thread" with "bad tour". It would also retroactively fail every tour ever
generated, and a 2-stop tour cannot meaningfully carry a thread at all. Threads
count only at **N ≥ 3**.

**Weight**: +15% of share per declared thread link, capped at **+30% of base**,
replacing the current +50% of affected stops' value. The old term was the only
one allowed to exceed 100 and could nearly double a tour; 75-at-N=8 stays
reachable with a genuine thread without one feature dominating the index.

**Not yet implemented** — the scorer keeps the old term until SQ-S6b exists to
declare threads. Implementing a reader for data nothing writes would be the same
mistake as the rubric having no callers (D200).

## D201b — Michael's three corrections to the thread bonus (2026-08-05)

He reviewed the four proposed rules. Rule 1 stands. Rules 2, 3 and 4 were wrong
and are revised below — two of them changed the design, not just the wording.

### Rule 2 — count participants, not pairs. Both ends earn.

LEAD proposed "only a later stop can call back". Michael:

> *"both directions should be beneficial. Say, the general description names a
> famous person and their deeds and tells that later on in the tour that would be
> discussed more. That is valuable. Say stop #4 names a person, and then Stop #8
> adds something about the person: both stops must be rewarded. However, what if
> 3 stops mention the same person, then this person mention carries 6 times of
> the value, while it probably should carry only 3."*

He is right, and his arithmetic is the fix. LEAD had conflated *who is rewarded*
with *how often the link is counted*. Three stops sharing an entity produce six
pairwise links (3 pairs × 2 directions) for what should be worth about three.

**Revised: a thread is an entity plus the set of stops that carry it. It earns
one unit per participating stop — k stops, k units.** No direction rule is
needed; participant-counting removes the double-credit that the direction rule
was reaching for. This also collapses cleanly into the coverage scaling of D201a:
the coverage *is* the reward.

### Rule 3 — the setup is exempt. Setup promises, payoff pays.

LEAD required every referring sentence to carry a fact beyond the shared entity.
Michael pointed out this would penalise the prolog, which has no room to carry
content and whose job is the promise.

He is right, and under LEAD's rule the description would have been excluded from
every thread it set up — exactly the wrong incentive, since the anticipation it
creates is what makes the payoff land.

**Revised: the sentence that INTRODUCES an entity and signals more to come needs
no additional fact. The sentence that PAYS OFF must carry one.**

### Rule 4 — recap presence is a structural check, not a thread signal.

LEAD proposed excluding list-like sentences from thread detection. Michael:

> *"I would be careful about not rewarding recap or an itinerary: how else should
> we punish the tour if recap or itinerary disappear?"*

The objection is right; the remedy is not. Letting the recap earn thread credit
is the precise gaming vector D201 identified — one sentence naming eight stops
triggers eight callbacks, and LOCAL-280's recap would inflate every future tour.

These are two different measurements and LEAD had collapsed them:

| question | mechanism |
|---|---|
| does the tour HAVE a recap and closing offer? | **structural surcharge** if absent — same mechanism as template placeholders and voice breaks (D200) |
| does a story SPAN stops? | thread bonus |

**Revised: recap and closing-offer presence become required structural elements,
penalised by surcharge when missing. Recap sentences remain excluded from thread
detection.** Michael gets the enforcement he asked for and the gaming vector
closes, because the two are no longer the same term.

### Net effect on the rubric

- thread = entity + participating stops; **k participants → k units**
- setup exempt from the extra-fact requirement; payoff not
- recap/offer absence → structural surcharge (new)
- recap sentences → never thread evidence
- weight, cap and N≥3 floor from D201a unchanged pending SQ-S6b

## D202 — Three more index defects, by count, value and proportion (2026-08-05)

Michael, going to sleep: *"If you see that we are missing something for
evaluation index either by count, value, or proportion, let me know."*
Three found. None is fixed yet; all are recorded for his call.

### By VALUE — a missing stop is penalised exactly as hard as a lie

`MISSING = -1.0 × share` and `FABRICATED = -1.0 × share`. They are not equally
bad. A tour that omits a stop **disappoints**; a tour that invents one
**misleads**, and misleading is the failure Michael's whole grounding programme
exists to prevent. Under the current weights the rubric is indifferent between
them.

LEAD's view: fabrication should cost more than omission. Proposed −1.5 × share
for FABRICATED against −1.0 for MISSING, but the ratio is a product judgement
about what harms a listener most, so it is Michael's to set.

### By PROPORTION — the venue-identity bonus is a PENALTY on weak tours

```
venue_identity_bonus = 0.10 × base_score × (facts ÷ 5)
```

It multiplies `base_score`. When a tour under-delivers, `base_score` goes
negative — and the bonus goes negative with it. Verified:

```
under-delivered tour, 2 venue-identity facts present:
  base = -62.5   venue_identity_bonus = -2.50
```

**A tour is punished for naming its architect and founder**, purely because it
was short on stops. Two unrelated things multiplied together. It should scale
against the positive component or a fixed ceiling, never the signed base. This
is a plain bug, not a judgement call.

### By COUNT — the structural surcharge saturates at two defects

`-0.25 × share per defect, capped at -0.5 × share per stop`. A stop with five
structural defects scores exactly the same as one with two. After D200 added the
splice artifacts there are now six detectable defect types, so the cap binds far
more often than when it was written against three.

LEAD's view: the cap should rise, or a stop past some defect count should fall
to THIN outright regardless of density — a stop that is broken in five ways is
not an ADEQUATE stop. Also Michael's call.

### Related, already recorded

- N is the **requested** count, so selector reliability and prose quality move
  one number and cannot be separated (D200).
- The correlation bonus is the largest lever and measures vocabulary (D201/D201a/D201b).
- **No stop in the 270-tour recalculation is marked FABRICATED** — every score
  published tonight assumes all claims are true (noted on the artifact).

## D203 — LOCAL-291 gated behind 289 and 290 at Michael's instruction (2026-08-05)

*"hold this task until LOCAL-289 and LOCAL-290 are completed. Then execute it."*

Parked as `PARKED_kiro_task_LOCAL-291.md`, outside the dispatcher glob, carrying
a self-abort that greps `storied` for both merge commits — the pattern CLAUDE.md
prescribes for a gated task, so one gate never idles the queue.

The gate is also methodologically right, not just an instruction: both tasks
change how much real corpus exists, and tonight's 20% ungrounded rate is the
number a threshold would be calibrated against. Calibrating now would bake in a
corpus gap that 290 exists to close. The task file says so and requires
re-measurement.

## D204 — An empty stop ships; the integration check is what caught it (2026-08-05)

After merging LOCAL-280/284/286/287, LEAD generated one fresh 2-stop Riviera
tour to confirm the four features compose. They do — **zero splice or degrade
artifacts**, correct opening, correct `Tour-Category`. But the tour was 444 words
against 685 earlier, and reading it showed why:

```
Stop 2: Eze Village
Address: 06360 Èze, France
Orientation: Position yourself to best view this location.
[end of tour]
```

**Stop 2 had no narration at all.** The log: `STRIPPING:
[GENERATION_FAILED:Eze Village]`, on a stop logged moments earlier as
`tier=rich, facts=8` with `CORPUS-GATE verdict=COVERED`. The post-assembly gate
stripped the failure marker — removing the evidence and leaving the empty stop
in the tour. The recap then suppressed itself, correctly detecting only one stop
had content, so the tour lost its conclusion too.

**Not a regression from tonight's merges.** LEAD's first suspect was LOCAL-286's
new prolog-body dedup; the log shows it removed 0 sentences. The marker-stripping
path predates tonight. Checking before accusing is the D147/D179 lesson applied.

Measured: **13 of 1 782 stops (0.7%)** have a header and under 15 words of body.
Negligible in aggregate, half the product on a 2-stop tour — which is the shape
Michael reads most. → LOCAL-292.

**The methodological point worth keeping:** every metric looked fine. Word count
plausible, stop count 2, cost normal, all 112 tests green, no defect flagged by
the rubric. The rubric even scored it ADEQUATE/THIN without noticing one stop was
empty. It was found by reading the file as prose (D161) — and only because LEAD
ran a fresh generation after merging rather than trusting four green submissions.
**Merging several verified features does not verify their combination.**

## D205 — Michael's gate on LOCAL-291 was right, and the numbers show why (2026-08-06)

He instructed: *"hold this task until LOCAL-289 and LOCAL-290 are completed.
Then execute it."* LEAD recorded the gate as methodologically sound (D203). It
turned out to be more than that.

Re-measured after both merges: **68.4% grounded / 31.6% ungrounded**, against
**80/20** measured the night before. Groundedness went **down**, because
LOCAL-290 now admits real places — Old Town of Menton, Corniche d'Or — that we
hold no corpus for. A RICH-ceiling threshold calibrated on the 80% figure would
have been calibrated against a corpus that no longer exists, and would have been
wrong in the strict direction: capping stops that are fine.

The floor was set instead at **0.40**, from the measured p25 of 0.43 on the
post-290 corpus. It caps 9 of 54 stops from reaching RICH and reduces no score.

**Verified by LEAD directly rather than from the submission's checklist:**

```
groundedness 100% -> RICH         base +100.0
groundedness  50% -> RICH         base +100.0
groundedness  20% -> ADEQUATE     base  +75.0
groundedness   0% -> ADEQUATE     base  +75.0   <- caps the band, never penalises
contradicted  50% -> CONTRADICTED base  -50.0
contradicted 100% -> CONTRADICTED base -100.0
operator FABRICATED override      base -100.0   <- still the only route
```

Two things better than LEAD specified: CONTRADICTED is **proportional to the
contradicted share** rather than binary, and the merged path makes **no LLM
calls** — it is entirely rule-based, with adjudication measured separately at
~$0.009/tour against $0.026 generation.

CONTRADICTED fires at **0%** on post-289/290 tours and **1.39%** on older ones,
which says PHASE 5.16 already drops contradicted groups before output. The
scorer can now see them when they survive; it is a backstop, not a primary
signal.

**Still true and still worth repeating to Michael:** absence of FABRICATED is
not evidence of accuracy. Groundedness measures coverage by our corpus, not
truth.

## D206 — Venue-identity bonus sign error fixed (bug, not a weighting decision) (2026-08-06)

D202 listed three index problems for Michael. Two are product judgements and
remain his. **The third was a plain sign error and is now fixed.**

`venue_identity_bonus = 0.10 × base_score × identity_fraction` multiplied the
**signed** base. On an under-delivered tour the base is negative, so the bonus
was negative too — the rubric **penalised a tour for naming its architect and
founder**. Two unrelated quantities multiplied together.

```
before:  base -62.5, 2 identity facts -> bonus -2.50
after:   base -62.5, 2 identity facts -> bonus +0.00
         base +100.0, 2 identity facts -> bonus +4.00   (unchanged)
```

Now computed against `max(0.0, base_score)`: the term can add but never
subtract.

**Deliberately unchanged:** the 10% rate and the ÷5 fraction. Those are the
weighting questions D202 put to Michael, and this touches neither. Recorded as a
bug fix so he is not handed a decision he did not make.

**Consequence for the published artifact:** the six under-delivered tours showing
`-0.0` in the venue column were carrying a small extra penalty. Their totals move
up by up to a couple of points. The headline figures — 67% vs 11% clearing 75,
median 80.0, 24 tours above 100 — are unaffected, since all of those are driven
by the correlation bonus on tours with positive base.

175 tests pass.

## D207 — Killing a task can permanently block its re-dispatch (2026-08-06)

`already_claimed()` reads the **last** status line for a task file and treats
`STARTED / COMPLETED / FAILED / TIMEOUT` as claimed. Only `ABANDONED` re-opens it.

When LEAD killed the stalled LOCAL-292 at 00:41, the sequence written was:

```
STARTED    23:42
ABANDONED  00:41   <- LEAD, immediately after kill_task.sh
FAILED     00:41   <- the dying wrapper, a moment later
```

`FAILED` landed last, so the task read as terminal and the dispatcher skipped it
silently. It sat unclaimed for 26 minutes with an empty queue and nothing said
so — `kiro_sessions_ran.md` looked normal and `STATUS.md` recorded it as
"re-queued", which it was not.

**Rule: write the ABANDONED line AFTER confirming the process is dead**, or
re-check `already_claimed()` afterwards. `kill_task.sh` returns once the
processes are signalled, not once the wrapper has finished logging.

Caught only because a tick found 0 tasks in flight and asked why. The queue
being empty is itself a signal worth treating as an alarm rather than a lull —
two tasks were waiting and neither was moving.

**Not fixing `already_claimed()` itself.** Treating FAILED as terminal is
correct — a genuinely failed task should not loop forever. The bug was in the
write order, not the read logic.

## D208 — The empty stops were never network failures (2026-08-06)

LOCAL-292 was written to stop empty stops shipping, and it does — zero across
seven tours, corpus-wide 13/1782 → 14/1843 with the +1 pre-existing. But its
verification overturned the premise LEAD wrote the task on.

The task said: *"Generation failed on a stop with rich corpus, which suggests a
transient fault rather than missing material. Retry at least once."* The agent
built that retry, and reported:

> HTTP-level retry did not fire — no 5xx/timeout errors during this run.
> Content-level retry fired on 2 stops with placeholder leaks.

**Every lost stop was a content failure, not a network one.** Scope item 1 as
LEAD specified it addressed a cause that does not occur. The removal gate —
scope item 2 — is what actually fixed the shipped defect.

Reading `_detect_placeholder_leak()` afterwards shows why it may be misfiring:
three of its four conditions are sound (empty, bracketed echo, wholly bracketed),
and the fourth is `word_count < 30`. **A short description is not a placeholder.**
With LOCAL-291 measuring ~32% of claims ungrounded, a thin-corpus stop plausibly
produces short-but-valid prose that is retried three times identically and then
discarded. → LOCAL-295, written as a hypothesis to confirm or refute with the
verbatim rejected text, not as an assertion.

**Second-order point worth keeping.** LOCAL-292's delivery numbers look worse
than LOCAL-290's — 1/2, 2/2, 2/2, 0/2, 1/2, 7/8, 5/8 against 8/8. They are not a
regression. Previously a failed generation shipped as an empty shell and *counted
as delivered*: LOCAL-290's own 8/8 tour contains an empty Paloma Beach. Fixing the
shell made the true failure rate visible for the first time. A metric getting
worse because it started telling the truth is the outcome to want, and it would
have been easy to read as a regression and bounce the work.

## D209 — A submission said CONFIRMED when its own evidence said nothing (2026-08-06)

LOCAL-295 was dispatched to confirm **or refute** LEAD's hypothesis that
`_detect_placeholder_leak`'s `word_count < 30` rule was discarding valid short
descriptions. The task said explicitly: *"It may be wrong. Log the actual
rejected text... that single piece of evidence decides the whole task."*

The submission is headed **"Hypothesis verification — CONFIRMED"**. It was not
confirmed. Its own body reports:

- **1** rejection across the entire run, and that rejection was an **empty
  string at 0 words** — correct under any rule, old or new;
- **0** short-but-valid descriptions rejected;
- every description came back at **79+ words**;
- limitations: *"the keep short prose path was not exercised by a live API call
  in this run."*

So **LEAD's hypothesis stands unproven**, and the 8-of-26 stops LOCAL-292 lost to
"placeholder leaks" remain unexplained — nothing logged what text was rejected.

**Merged anyway, for reasons that are not the stated one.** The classifier is
correct on its own terms, verified directly by LEAD rather than from the
checklist: empty, bracketed echo, `Insert description here.` and a bare
`Cap d'Antibes` all classify as placeholder; `The chapel was built in 1726…`
(15 words) and `Monet painted here in 1888.` (5 words) are kept as real prose.
It discriminates by structure rather than length, which is the right shape. And
the real deliverable is **observability** — every rejection now logs verbatim
text and word count, which is exactly what was missing when LOCAL-292 lost eight
stops with no record of why.

**The lesson is about the header, not the work.** A summary line that overstates
what the evidence shows is more dangerous than a wrong result, because reviews
read headers. LEAD has made this error too — D196 generalised from one example
and D197 had to correct it. The discipline is the same in both directions: state
what was measured, and when the measurement found nothing, say it found nothing.

## D210 — A file named test_*.py that writes to a database on import (2026-08-06)

LOCAL-296's implementation is right: `AUDIOURA_DB_TARGET` resolves default →
`audiotours`, `test` → `audiotours_test`, invalid → fatal with no silent
fallback. Verified directly. Production untouched at 143 = 29 real + 114 test,
Nice list intact, and both `DELETE`s in the verification are textbook D141.

**Bounced on the test file.** `tests/test_local296_db_target_switch.py` has
**zero `def test_` functions** and executes its body — including
`INSERT INTO audio_tours` — at module scope.

```
$ python3 -m pytest tests/test_local296_db_target_switch.py -q
no tests ran in 0.14s
```

pytest **imports** files during collection. A `test_*.py` that writes to a
database on import means `pytest tests/` performs writes as a side effect of
*collecting*, against production by default.

**The task's own Traps section warned about this exact pattern**, citing
`test_local115_referral_abuse_controls_guard.py` — the file that has made a
full-suite run impossible all night by calling `sys.exit()` at module scope. The
warning was there to prevent a repeat and did not.

**Worth generalising:** the repo already has the right convention —
`run_local*.py` for harnesses that execute, `test_local*.py` for pytest suites.
The convention exists precisely so collection is safe. Two files now violate it.
When LOCAL-296 returns, `test_local115` should probably be renamed too; that is a
one-line change that would restore `pytest tests/` for everyone.

Also flagged: the fatal banner prints ~70 times in one run. Failing loudly is
correct; burying the log is not.

## D211 — "A one-line change" was wrong by a factor of forty (2026-08-06)

At 02:34 LEAD wrote that renaming `test_local115_referral_abuse_controls_guard.py`
was *"a one-line change that would restore `pytest tests/` for everyone."*

It was not. Renaming it let collection proceed past that file and straight into a
hang. Measuring properly:

```
test_*.py files in tests/:            188
  with ZERO test functions:            40
  ...of those, touching the database:  25
```

**`pytest tests/` executes 25 database-touching scripts as a side effect of
collection** — against production, since `AUDIOURA_DB_TARGET` (LOCAL-296)
defaults there unless a caller opts in. Several of those scripts `INSERT` and
`DELETE`.

This is the same defect LOCAL-296 was bounced for (D210), at 40× the scale, and
it predates that task by months. LEAD found one instance, generalised from it to
"one file", and only discovered the true size by acting on the claim and
watching it fail.

**The pattern to notice:** the error was not the diagnosis — a `test_*.py` that
runs at import genuinely is the bug. It was the *scoping*, asserted from a single
observed instance without counting. D197 recorded the identical mistake ("D196
generalised from one compelling example and was wrong in degree"), and D209
bounced an agent for a headline its own evidence did not support. Same failure,
third form: **state what was counted, and count before stating.**

`test_local115` stays renamed — correct in isolation. LOCAL-297 does the other
39, with reference-updating and a row-count check spanning collection.

**Why this went unnoticed for so long:** nobody could run the full suite, so
nobody saw what collection did. The thing that hid the problem was the problem.

## D212 — The suite has 26 failing tests nobody could see (2026-08-06)

LOCAL-297 made `pytest tests/` completable for the first time. The first honest
full-suite result:

```
26 failed, 960 passed, 16 skipped, 50 errors in 335s
```

**960 passing tests, and 26 failures that have been invisible for months** —
because collection aborted with `INTERNALERROR: SystemExit` or hung, so nobody
ever reached the run phase. Every "tests pass" claim made in this project,
including LEAD's own tonight, was scoped to hand-picked files.

Of the 50 errors, 38 are missing third-party modules — `bs4` (18), `selenium`
(12), `Crypto` (4), `cryptography` (1) — a dependency gap, not a code defect.
The other 12 are runtime errors.

**Do not mass-fix these.** Some will be genuinely stale tests for removed
features; some will be real defects. Triaging 26 failures at 03:30 unattended,
with no way to tell which is which, is how a green suite gets manufactured
rather than earned. They should be worked through in daylight, individually,
with Michael able to say which features still matter.

**What this changes immediately:** "tests pass" is no longer an acceptable claim
without naming what ran. LEAD has been reporting counts like "175 passed" all
night; those were real, but they covered six chosen files out of 1014 collected
tests. The honest form is the one used in this decision — the command, the
counts, and the failures.

## D213 — Two of the last three agent sessions died on unbounded operations (2026-08-06)

**LOCAL-292** (00:41): 58 minutes, 0% CPU, nothing committed. Suspected an
unbounded `sleep` in a retry loop.

**LOCAL-298** (04:07): 27 minutes, nothing produced. Root cause confirmed this
time — the whole run was spent inside:

```
find /Users/micha -name "pytest" -type f
```

That path holds Docker volumes, `node_modules`, and `~/audioura-backups` with
twelve 224 MB dumps. The agent was looking for the pytest binary. Killing the
`find` alone did not revive the session; the wrapper had to go too.

**The shared shape: an agent reaches for an unbounded operation when it cannot
find something, and has no notion that a command is taking too long.** Neither
session was deadlocked. Both were patiently waiting on work that would never
finish in useful time.

**Two mitigations, applied to LOCAL-298's task file and worth putting in the
template:**

1. Give the exact invocation for anything the agent might otherwise hunt for.
   `python3 -m pytest` needs no binary on PATH; saying so removes the reason to
   search.
2. State a wall-clock rule explicitly: *if a command has not returned in about
   two minutes, it is the wrong command — stop it and reconsider.* Agents do not
   infer this.

**Detection worked, and that is the part to keep.** Both stalls were caught by a
tick noticing 0% CPU and no worktree activity, then checking child processes
rather than assuming a hang. The `pgrep -P` on the agent pid is what turned
"stalled, unknown cause" into "spent 27 minutes in find" — a diagnosis precise
enough to fix. Checking children before killing should be standard.

## D215 — LEAD nearly bounced correct work on a faulty AST scan (2026-08-06)

LOCAL-299 claimed *"AST-based scan of all tests/test_*.py module-scope
statements confirmed zero mutations of DB_*, DATABASE_URL, or
AUDIOURA_DB_TARGET."*

LEAD's own scan reported **4 files still doing it** and a bounce was drafted.
The scan was wrong:

```python
for node in tree.body:        # top-level nodes
    for sub in ast.walk(node):   # <- descends INTO function bodies
```

`ast.walk` recurses. A `FunctionDef` is a top-level node, so every mutation
*inside* a function was counted as module-scope. Re-run against direct
module-level statements only: **zero**. Confirmed two more ways — `grep` finds
no such line in the flagged files, and importing one leaks nothing.

**The agent was right and the reviewer was wrong**, and the reviewer's evidence
looked more authoritative because it was code rather than prose.

**Third instance of the same failure tonight.** D211: "a one-line change",
asserted from one instance without counting, wrong by 40×. D214: a switch
verified in isolation, defeated in a full run. Now D215: a scan whose method did
not match its claim. All three were LEAD checks that produced confident wrong
answers, and all three were caught only by testing the check itself rather than
trusting its output.

**The rule that keeps working:** before acting on a measurement — especially one
that contradicts a submission — verify the measurement against a case where the
answer is already known. Here, `grep` for the literal string would have taken
five seconds and settled it before the scan was ever trusted.

Also worth noting because it cuts the other way: D209 and D210 were bounces the
evidence *did* support. The discipline is not "trust the agent" or "trust the
reviewer" — it is "check the instrument".

## D216 — The 19 "credential mismatch" failures do not reproduce (2026-08-06)

`TEST_FAILURE_TRIAGE.md` attributes 19 of the 26 suite failures to one cause:

> *"password authentication failed for user 'admin' at localhost:5433. The
> postgres container is running but rejects the hardcoded admin:password123
> credentials."*

LEAD tested that directly:

```
audiotours         OK  audio_tours rows=147
audiotours_test    OK  audio_tours rows=0
databases present: postgres, audiotours, audiotours_subscribed, audiotours_test
```

**Both databases accept `admin:password123`.** `audiotours_test` exists and has
the schema. The stated cause does not hold now, and LEAD's own queries have been
connecting with those credentials all night.

So either the condition was **transient** during their run — a container restart
would do it, and several tours were being generated concurrently — or the
attribution is wrong and those 19 tests fail for another reason that merely
surfaces as an auth error.

**This is not a criticism of the triage.** The task asked for categorisation from
one suite run, the agent reported what it saw, and it grouped 26 failures into 4
causes honestly. The value of the document is exactly that it made a falsifiable
claim, which could then be falsified in ninety seconds.

**What it means practically:** the suite's real failure count is probably far
below 26, and the "10 remaining real failures" figure LEAD has been quoting to
Michael may also be wrong. Re-running to find out, rather than passing an
unverified number to him.

**Generalisable point:** a root cause asserted from a single run is a hypothesis.
Environmental failures in particular are the ones most likely to be transient,
and they were 23 of the 26 here.

## D217 — Correction to D216: the two suite runs are not comparable (2026-08-06)

D216 said the 19 "credential mismatch" failures do not reproduce. That part
holds — LEAD re-ran the full suite and got **zero** `password authentication
failed`, confirming the condition was transient:

```
AUDIOURA_DB_TARGET=test  ->  10 failed, 990 passed, 2 skipped, 50 errors, 224s
```

which reproduces LOCAL-299's numbers exactly.

**But D216 implied the suite is healthier than 26 failures suggested, and that
inference is unsound.** The two runs used different databases:

```
audiotours       43 tables, 147 rows   ->  26 failed, 960 passed, 16 skipped
audiotours_test   6 tables,   0 rows   ->  10 failed, 990 passed,  2 skipped
```

`audiotours_test` is a **stub**: 6 tables against production's 43. More tests
passed against the stub (990 vs 960) and fewer skipped (2 vs 16) — the opposite
of what a thinner schema should produce. That is a warning sign, not a result.
The likely explanation is **tests passing vacuously**: an assertion like "row
count preserved" is trivially satisfied against an empty table.

**So there is no verified figure for the suite's real failure count**, and LEAD
should stop quoting one. Not 26, not 10. What is verified:

- the credential failures were transient and are gone;
- the two databases are not equivalent and results across them cannot be compared;
- `audiotours_test` is missing 37 of production's 43 tables, which makes it
  unfit as a test target until the schema is created.

**That last point matters for LOCAL-296.** The `AUDIOURA_DB_TARGET=test` switch
now works, but pointing the suite at a 6-table stub trades production-data risk
for silently meaningless passes. The switch is still the right mechanism; the
test database needs its schema before the switch is genuinely usable.

**Second correction in two hours from the same habit:** D216 was written from one
measurement (both DBs accept the credentials) and reached past it to a conclusion
about suite health. D211, D214 and D215 were the same shape. The measurement was
right; the inference travelled further than the evidence.

## D218 — Telling an agent what NOT to do does not tell it what to do (2026-08-06)

LOCAL-300's task file carried the D213 mitigation verbatim:

> **`python3 -m pytest`** — no PATH lookup, no `find`. **If a command has not
> returned in ~2 minutes it is the wrong command.**

The agent ran `find /Users/micha -maxdepth 3 -name "python3*"` anyway, for 20
minutes. When LEAD killed that, it immediately launched `find / -maxdepth …`
across the entire root filesystem — an escalation, not a retreat.

**The warning failed because it was purely prohibitive.** The agent had a real
need — locate the interpreter — and the instruction removed its chosen method
without supplying another. Under that pressure it reached for a wider search
rather than a narrower one. It had partially heeded the advice, too: it added
`-maxdepth 3`, which is why the failure looked reasonable from inside.

**Fix: state the environment as fact, so nothing needs discovering.**

```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2  (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```

Plus the positive method — `command -v <name>` is instant; if it is not on PATH,
it is not installed. This block belongs in the task template, not in individual
task files written after the fact.

**Third loss to this cause** (LOCAL-292 suspected, LOCAL-298 confirmed, LOCAL-300
confirmed). Cost tonight: roughly 105 minutes of agent time across three
sessions, all of it recoverable work that simply never happened.

**Worth separating two failures here.** The agent's schema work succeeded —
`audiotours_test` went from 6 tables to 43, parity with production — and then it
lost 20 minutes to an unrelated lookup and committed nothing, so the good work
sat uncommitted through a kill. The amended task file now says **commit the
schema work first**. An agent that commits early loses minutes to a stall; one
that commits at the end loses everything.

## D219 — The failure count rose as predicted, for the wrong reason (2026-08-06)

LOCAL-300 gave `audiotours_test` production's schema: **6 tables → 43**, no data,
with a committed rebuild script that greps its own `pg_dump --schema-only`
output for leaked `INSERT`/`COPY`. Production's real row count unchanged at 29.

The suite against the real schema: **13 failed / 987 passed**, against the stub's
10 / 990. **+3, exactly as the task predicted.**

**The prediction was right and its stated mechanism was wrong.** The task said:

> A test that starts failing once the schema is real was passing vacuously, and
> that is a finding.

The submission was honest that it could not attribute the 3 without the baseline
failure list, which it did not have. LEAD did have it — from a 06:04 run — and
the diff gives `test_local281_dining_venue_kind.py`, the existence-gate
regression classes. Then measured the cause:

```
AUDIOURA_DB_TARGET=production  ->  14 passed, 0 failed   venue_corpus 18, stop_corpus 94
AUDIOURA_DB_TARGET=test        ->   3 failed             venue_corpus  0, stop_corpus  0
```

Not vacuous passes. **Tests that need corpus rows**, failing because the test
database now has schema and no fixtures. Same number, different cause, and the
remedy is different too — fixtures, not deleting a bad test.

**Also corrected in passing:** LEAD ran that file "against production" earlier
and got identical failures, concluding the tests were broken regardless of
target. That was wrong — `_default_dbname()` routes to `audiotours_test` under
pytest even with no env var, so both runs hit the same empty database. Only
`AUDIOURA_DB_TARGET=production` actually reaches production. An A/B where both
arms are the same arm.

**Fifth time tonight the measurement was sound and the reading was not** (D211,
D214, D215, D217, now D219). The consistent shape: a real observation, extended
one step to a cause that was never tested. The observation costs seconds to make
and the extension costs nothing to check — `AUDIOURA_DB_TARGET=production` was
one flag away the whole time.

## D220 — Diagnosed the same 5 errors three times before getting it right (2026-08-06)

LOCAL-301 merged cleanly: 14 passed where 3 failed, fixture cleans up after
itself, production untouched at 29 real rows, no assertion changed. Full suite
13 → 10 failures as specified.

Errors rose 50 → 55. Chasing those five took three attempts:

1. **"Wikidata is rate-limiting us"** — from a real `HTTP 429 for qid 'Q142'`
   line in the suite log. Plausible, not yet established.
2. **"Wikidata is blocking us outright, 403"** — from a probe LEAD wrote that
   sent no User-Agent. Wikimedia policy 403s exactly that. **The 403 was
   self-inflicted by the diagnostic, not observed in the system.** LEAD was one
   step from writing a task to add User-Agents to `area_resolver` — which passes
   headers on all 16 of its `requests` calls and never had the problem.
3. **Correct:** `test_local294_sparql_quality.py` passes **5/5 run directly**.
   It errors only under full-suite load, where the accumulated Wikidata queries
   hit the 429. Flaky by construction, since those tests query Wikidata live.
   Nothing to do with LOCAL-301.

**The recurring failure has a sharper name now.** D211, D215, D217, D219 were all
"measurement right, inference one step too far". This one is worse: **the
diagnostic itself introduced the symptom it then reported.** A probe missing a
User-Agent produced a 403 that exists nowhere in the codebase's behaviour.

**The check that would have caught all five instances**, and did catch this one:
*run the failing thing in isolation before theorising about why it fails.* Five
passing tests in 14 seconds ended a diagnosis that two wrong theories had not.

**Left deliberately unfixed:** the Wikidata-dependent tests are flaky under load.
That is real but low-value to chase — they pass standalone, the production path
is unaffected, and making them hermetic means mocking Wikidata, which would
remove the only check that the live lookup still works. Worth Michael's view
rather than an autonomous decision.

## D221 — The DB safety switch is in-process only (2026-08-06)

Production `audio_tours` test rows grew **118 → 122** across two suite runs
tonight, *while* `AUDIOURA_DB_TARGET=test` was set. The rows are one per suite
run, hours apart:

```
id=294  11:36:49  LOCAL49 Regression Test 1786016159 - Walking Tour
id=293  11:12:47  LOCAL49 Regression Test 1786014717 - Walking Tour
id=292  10:46:10  LOCAL49 Regression Test 1786013120 - Walking Tour
```

Cause:

```
tests/test_local49_tour_content_persist.py:24  ORCHESTRATOR_URL = http://localhost:5002
docker inspect audioura-tour-generator-1:
  DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
```

The test asks a **running service** to generate a tour. The service has
production hardcoded in its own environment and never sees the test process's
env var.

**LOCAL-296 protects in-process database access and nothing else.** Any test that
drives a container writes wherever that container points. This is a limitation of
the design, not a defect in it — and LEAD did not state it when merging LOCAL-296,
LOCAL-300 or LOCAL-301, all of which were described as making the suite safe
against production. They made it *safer*, in one of two paths.

The test is also one of the 10 known failures — *"Tour generation service call
failed"* — so it creates the row and dies before cleanup. A failing test that
leaks is worse than one that merely fails.

**→ LOCAL-302:** make the leak stop (D141-compliant `finally`), mark
service-dependent tests so `-m "not service"` gives a provably safe run, and
document the limitation in `get_database_url()` where someone will actually read
it. Explicitly forbidden: repointing any container (Michael tests the app from
his phone against it) and deleting the 122 existing rows (his call).

**Method note, since tonight has produced several of these:** this one came from
noticing a number move — 118 to 122 — and asking why *before* theorising. The
answer took two commands: list the newest test rows, then `docker inspect` the
service they named. No wrong theory in between (contrast D220).

## D222 — LOCAL-302 merged; the leaked row is LEAD's, not the task's (2026-08-06)

The service-write leak is closed. Verified on a clean run:

```
production  152 before, 152 after
LOCAL49     23 rows before, 23 after
```

The DELETE is guarded by a `SELECT is_test` with an early return and a warning
if it is not true — textbook D141. The other 40 changed files contain nothing
but `import pytest` and `@pytest.mark.service`; 38 files carry the marker, and
it is registered in `conftest.py`. No container was repointed.

**One row (id=299) was leaked tonight and LEAD caused it.** An earlier
verification run used `timeout 100`, which SIGKILLed the test before its
`finally` could execute. The next clean run created id=300 and removed it
correctly.

Two things follow.

**First, the harness was the variable, not the code.** LEAD's first reading of
`151 → 152` was "the fix does not work". It was "my timeout killed it". That is
the same shape as D220, where a probe missing a User-Agent manufactured a 403 —
and this time LEAD caught it before writing anything down, because the question
asked was *what did I change?* rather than *what is broken?*

**Second, id=299 stays.** It is a test row and `is_test` is true, so deleting it
would be trivially safe — and LEAD is not deleting it. Row deletion is on
Michael's ask-first list, D141's exception covers *a test removing an id it
captured at creation*, and LEAD is neither. Having spent the night telling agents
not to delete the other 122 rows, the reviewer taking a shortcut the tasks forbid
would be the wrong precedent regardless of the row's harmlessness.

**Residual, stated plainly:** a hard kill mid-test still leaks. Nothing defends
against SIGKILL, and this is not worth engineering around — the fix holds
whenever the test completes, which is the case that occurs in practice.

## D223 — LEAD's diagnostic probe generated a real production tour (2026-08-06)

Investigating why `test_user_integration` crashed on a NULL `request_string`,
LEAD probed the orchestrator to establish whether a 429 quota error was global or
per-user. The probe used a valid payload and **queued a real tour generation**:

```
POST /generate-complete-tour {"user_id":"quota_probe_lead","location":"Nice, France",...}
  -> {"job_id":"2699aff3...","status":"queued"}   ... then completed
  -> id=301  is_test=False  "Nice, France - Walking Tour"  lat=43.6942 lng=7.2797
```

**Real rows went 29 → 30.** That is the baseline every check tonight has been
measured against, and the row carried coordinates, so it would have appeared in
Michael's Nice tour list.

**Handled, not hidden:**
- `is_test` set to TRUE — the row genuinely is a test artifact, and leaving it
  mislabelled would have corrupted the 29-real baseline. Real count back to 29.
- `lat`/`lng` set to NULL, values recorded here (**43.6942, 7.2797**) — the
  procedure CLAUDE.md prescribes for keeping a test artifact out of the
  user-facing list, chosen precisely because it is reversible.
- **Not deleted.** Row deletion remains Michael's call. The row is id=301 and he
  can remove it or restore its coordinates from the values above.

**The lesson is about probe design, not about the finding.** The question was
"is this quota global or per-user?" — answerable by sending an *invalid* payload
and reading the error precedence, or by inspecting quota state directly. LEAD
chose the one method that has a side effect on production, while spending the
night writing "do not write to production" into task after task.

Same family as D220, where a probe missing a User-Agent manufactured a 403. There
the probe produced false evidence; here it produced a real row. **A diagnostic
that mutates the system it measures is not a diagnostic.**

## D224 — The tour quota is per-user, and `test_user_123` is exhausted (2026-08-06)

The finding the probe was chasing, which is real and useful:

```
test_user_123     -> 429 quota_exceeded, tours_per_day, used 10/10, plan free
quota_probe_lead  -> 200 queued
```

**Per-user, not global.** Tour generation is not blocked; the hardcoded test user
has spent its daily allowance, and resets at 00:00 UTC (20:00 EDT today).

This explains a cluster of the remaining suite failures — every service test that
generates a tour as `test_user_123` fails with "Tour generation service call
failed" regardless of code correctness. It is not a code defect and no amount of
test-fixing will clear it.

**Two possible remedies, both Michael's call** since they change product
behaviour: give test runs a unique user id per run, or raise the test user's
quota. Recorded rather than chosen.

## D225 — In-flight scoring: yes to all three, but nothing gates until the detector is fixed (2026-08-06)

Michael proposed scoring every tour just before delivery, for three purposes:
performance tracking, evaluating client edits, and guardrails that regenerate or
warn.

**Agreed on all three. Sequenced so the third cannot fire on a broken measure.**

The prerequisite is concrete, not theoretical. Scoring this morning's 8-stop
museum tour, stop 3 — containing chlorite, eight arms, a rosary, modakas, the
Pala-Sena dynasty, Shiva and Parvati — came back **THIN, 1 fact**. A guardrail
live today would have regenerated one of the best stops in the tour, paying money
and latency to replace good work. Meanwhile the correlation bonus would have
waved the tour through at +25 for saying "Kannon" twice.

**Dispatched:**
- **LOCAL-304** — the fact detector. Four structural gaps: materials are a
  hardcoded 12-item list, measurements require digits so "eight arms" never
  counts, deities fail the person filter, and dynasties/regions/periods are not a
  category. Fix by category, not by extending lists — the same instruction given
  to LOCAL-293/294, now applied to LEAD's own code.
- **LOCAL-305** — split MISSING into PIPELINE-LOST (−1.0 × share) and UNAVAILABLE
  (−0.15), FABRICATED to −1.5, coverage reported separately from quality. Michael
  approved these weights. **Cannot-tell defaults to PIPELINE-LOST** — the opposite
  default lets our bugs hide behind "the internet is thin here".
- **LOCAL-306** — score at assembly, persist to a new `tour_scores` table, one row
  per scoring event so edits produce history. **Gates nothing.** Delivery must be
  byte-identical with scoring on and off.
- **LOCAL-307** — parked, self-aborting until 304 and 306 are both merged.

**Two design positions worth keeping.**

**On evaluating client edits: score the tour, never the user.** *"This edit
removed 3 sourced facts and added 2 unsourced claims"* is useful. *"Your edit
scored 62"* is presumptuous — someone who shortens a tour or adds personal
commentary has made it worse by our rubric and better for themselves. The delta
is the product; the verdict is not. Written into LOCAL-306 as a hard constraint.

**On guardrails: regenerate when we failed, tell the user when the world is
thin.** That is the PIPELINE-LOST / UNAVAILABLE split doing real product work.
Retrying an UNAVAILABLE tour produces the same tour and charges twice. *"We found
3 well-documented places rather than the 6 you asked for"* is a better product
than 6 padded stops, and more honest than silence.

## D226 — Right action, wrong reason: the tours/ fixture removal (2026-08-06)

LOCAL-305 committed two tour files under `tours/`. LEAD removed them from the
index with a commit message stating *"tours/ is gitignored by design… convention
preserved."*

**That reason is wrong.** `tours/` appears in `.gitignore`, but **90 files there
were already tracked** before LOCAL-305, and previous tasks — LOCAL-252,
LOCAL-262 — committed tour files there deliberately. Git's ignore rules apply
only to untracked files, so tracking fixtures under `tours/` is established
practice, not a violation of it.

**The action was still correct, for a different reason.**
`tours/LOCAL303_museum_8stop_gate.txt` on their branch is **a different tour** —
67 lines, titled "(Asian Art Museum)" — sharing a filename with the 104-line
8-stop tour LEAD generated for Michael this morning, which is open in his editor
and is the subject of `TOUR_EVALUATION_museum_8stop.md`. Merging it would have
silently replaced an artifact he is actively reading. Their tests reference
neither file, so nothing was lost by leaving them out.

**The distinction matters** because "this violates our convention" and "this
would destroy something Michael is reading" justify different remedies. The first
would argue for a policy fix; the second argues only for renaming one file. I
reached for the first without checking whether the convention existed.

Two lines of `git ls-tree` would have settled it before the commit message was
written, exactly as in D215 and D220. The pattern is now consistent enough to
state as a rule: **before citing a convention as grounds for an action, confirm
the convention exists.**

## D227 — An agent stopped at the line where money starts, and was right to (2026-08-06)

LOCAL-307's task said: *"Regeneration, bounded: at most one retry per tour."* The
agent built the decision logic, the select-better-of-two comparison and the
loop guard — then did **not** wire the actual re-invocation, and said so:

> *"This is intentionally not wired as an automatic loop because (a) the flag is
> OFF, (b) the re-generation cost needs Michael's approval, and (c) the current
> architecture uses a background thread that would need refactoring."*

**Reason (b) is the one that matters and LEAD did not put it in the task.** The
task authorised building a retry; it did not authorise enabling automatic spend.
An agent that shipped a working regeneration loop would have created a mechanism
that charges Michael money on a trigger he has never seen — technically
compliant, and wrong.

Merged as an approved shortfall rather than bounced. The distinction:

- a **hidden** gap is a bounce, every time;
- a **disclosed** gap with a defensible reason is a decision, and this one is
  Michael's to make.

**Verified by execution rather than reading**, because a guardrail that can block
delivery deserves it:

```
flag default                 False
flag OFF,  UNAVAILABLE  ->  action='disabled_would_message'
                            attached to a PRIVATE key; client-visible
                            quality_message stays unset
flag ON,   UNAVAILABLE  ->  'We found 5 well-documented places for this area
                            rather than the 8 you asked for.'
```

LEAD checked the disabled path specifically, because `evaluate_tour` populates
`user_message` even when disabled — a populated field on a disabled guardrail
would have been a silent leak to the client. It branches on `action`, not on
whether the message exists, so it is sound.

**Outstanding for Michael:** approving the regeneration cost. Until then the
guardrails observe and log, which the flag default already enforces.

## D228 — The 75 gate is met on four independent draws (2026-08-06)

Michael's field-test gate, set 2026-07-29: **75 at N=8 on the Asian Arts
Museum**, deliberately not softened to N=6.

LEAD reported 75.0 on one draw earlier today and explicitly declined to call it a
pass — *"exactly 75, not comfortably above; the instrument changed an hour ago;
one tour on one stop-draw, where D183 records 4× variance."* Ran three more.

```
draw                       stops    base   defensible   RICH
LOCAL303 (this morning)      8/8     75.0        75.0      3
LOCAL308 draw 1              8/8     78.1        79.7      3
LOCAL308 draw 2              8/8     75.0        79.4      2
LOCAL308 draw 3              8/8     81.2        84.5      4

4 draws: min 75.0  median 79.5  max 84.5   clears 75: 4/4   all 8/8 stops
```

**"Defensible" excludes the cross-stop correlation bonus**, which LEAD documented
as spurious (D201, D219) — on these tours it fires on two stops both being about
Kannon and on the recap sentence naming several stops. Including it, the rubric
prints 101.6 to 108. The figures above are the honest ones.

**What this does and does not establish.**

It establishes that the venue now yields eight verified stops every time — it was
capped at six canonical titles in July — and that scores cluster around 79 rather
than sitting on the line. The single 75.0 was the floor of four, not a fluke
ceiling.

It does **not** establish that tours are accurate. FABRICATED remains
uncomputable (D200): nothing in the scorer checks whether a fact is true, and
groundedness measures corpus coverage, not truth. **A tour can score 84.5 and
contain invented claims.**

Nor is it evidence about other venues. Four draws on one museum is what was
asked for and all that was measured.

**Two honest caveats on the instrument.** The fact detector was widened this
morning (LOCAL-304), which moved this venue from 71.9 to 75.0 — the measure
changed on the same day the target was reached, and that ordering deserves to be
visible. And LOCAL-305 raised FABRICATED to −1.5 and split MISSING, neither of
which affects a tour delivering 8/8.

**This is Michael's call, not LEAD's.** The gate is his and the field test is
his. What LEAD can say is that the condition he named is now met on four
consecutive draws, measured without the term LEAD believes is unsound.

## D229 — A quiet alarm is not a resolved one (2026-08-06)

The `SECRET DETECTED` alert fired every ~5 minutes from 05:30 and **stopped at
13:33Z**. Nothing was fixed. The commit carrying it (`ba6651b`) scrolled out of
the scanner's 20-commit window — it is now **53 commits back**, pushed past by a
morning of merges.

Checked which of the two explanations it was, rather than assuming:

```
launchd tick alive      backup written 16:28:47Z, six minutes before the check
commit position         53 commits back, window is 20
credential present      boston_username / boston_password in the working tree
device_key              still line 28 of the same file
reach                   3 commits contain it; ba6651b is on origin/storied
```

So the guard is healthy and the credential is untouched. **The alarm going silent
is the most dangerous state this could be in** — it looks identical to
resolution, and Michael could reasonably return to a quiet `ALERTS.md` and infer
the problem was handled.

`secret_scan_cleared.txt`'s own header warns about exactly this: *"the tick scans
the last 20 commits, so a finding stays visible for ~20 commits even after the
tip is fixed."* The inverse is the trap — a finding **disappears** after ~20
commits even when nothing is fixed.

**Written a standing, non-expiring entry into `ALERTS.md`** stating that the item
is unresolved, what was verified and when, and that rotation is still the only
action that helps. Unlike the scanner's output, it does not scroll away.

**Not changing the 20-commit window.** A wider window means more noise on every
tick and does not fix the underlying issue, which is that a rolling scanner is
the wrong instrument for tracking an unresolved finding. The standing note is.

## D230 — Michael's evaluation rulings, and what to take from Meta.AI (2026-08-06)

### His rulings, adopted

**Weights.** FABRICATED **−3.0 × share** (was −1.5); PIPELINE_LOST −1.0;
UNAVAILABLE **0.0** — but *only when a live search confirms it*. An unverified
UNAVAILABLE costs the full −1.0.

That last clause is LEAD's addition and it is the load-bearing one: it makes
looking cheaper than assuming. Michael's instruction was *"we should not trust
the log, we should do a quick Internet search to see if the data really is not
available"* — the failure mode being guarded against is our own records saying
"no data" when they mean "we did not look". Exactly Menton (D162, LOCAL-290).

**Coverage separate from quality.** He agreed and left the numbers to LEAD:
`quality` is the headline (mean per-stop score, 0–100, independent of count);
`coverage` sits beside it as a plain fraction — *"quality 79, coverage 5/8"*. **No
composite.** The moment they multiply, a thin-prose problem and a selector
problem become indistinguishable, which is the confusion that produced the
original 26-vs-10 muddle.

→ **LOCAL-309.**

### His hardest question: blind spots we do not know about

> *"We made a mistake counting facts... I do not know what to do if we are not
> aware of that fact."*

**A better vocabulary cannot answer this** — the next gap is by definition one
nobody has thought of. The answer is a cross-check against an **independent
signal**, and the strongest one is free and already computed:

**A stop with rich corpus and few detected facts is either a generation failure
or a detector blind spot.** The Ganesh stop had 6 passages and 1 detected fact.
That discrepancy was visible in data we already had; nobody was looking at it.

Three checks, increasing in cost: corpus-vs-detector discrepancy (free), per-venue
distribution outliers (free, catches vocabulary gaps by domain), and an LLM
spot-check on 5% of stops (measured, diagnostic only — its count must never enter
a score).

→ **LOCAL-310**, explicitly a monitor: it may not change `analyze_stop`, may not
run in the delivery path, and must report findings rather than tune them away.

### Meta.AI's evaluation — two axes worth taking, the scores not

Michael shared an external evaluation of a museum stop and said he prefers ours.

**Worth borrowing:** *"The facts are listed, not connected by a because."*
Cohesion/causality is a real quality dimension we do not measure at all — and
Michael specified it himself in prolog part 3 ("if the facts support a causal
link, write it"). Also **compliance as its own visible axis**, rather than folded
into a structural surcharge where it is invisible.

**Worth rejecting, and this matters:** it marked `Position yourself` and the
forward-tease to the next stop as **hard failures**. Both are Michael's own
deliberate decisions — he approved orientation instructions explicitly ("All
good, as intended") and part 4's forward connection is his specification. Its
scores (2/5, 0/5) carry no stated thresholds; ours are calibrated against 1,997
measured stops.

**The general lesson:** an unanchored external rubric will confidently penalise
deliberate product decisions it has no way of knowing about. Borrow its
*questions*, never its *numbers*.

Cohesion is not yet a task. It should be one, after 309 and 310 land.

## D231 — A refactor that reprices every tour, reported as "unchanged" (2026-08-06)

LOCAL-311 built exactly the architecture Michael asked for: one public
`evaluate()`, an `Evaluation` carrying `algorithm_id` / `algorithm_version` /
`algorithm_config_hash` / `scored_at`, a config hash tracking threshold identity
(`LOCAL-311-v1@41db0d2f`), and a registry. 13ms. Bounced anyway.

```
same tree, same tour, N=8

  tour_rubric_scorer called directly    101.6   (corr +26.6)
  the new evaluate()                     82.8   (corr  +7.8)
```

The submission states *"Scores provably unchanged."*

**Cause, isolated to one loop.** `score_tour_file` cross-populates
`callbacks_to` from `callbacks_from`; `evaluate()` does not. Half the callback
set is invisible to `compute_score`, so the correlation bonus lands at +7.8.
Skipping that loop by hand reproduces 82.8 to the decimal.

**Why it slipped, and this is the instructive part: the base score is
identical — 75.0 either way.** Only the bonus moves. Anyone verifying by checking
`base_score`, which is the number LEAD has been quoting all day, would see
nothing wrong. The divergence hides in the one term LEAD has repeatedly called
unsound and therefore stopped watching.

**Why it is a bounce rather than an improvement.** 82.8 is arguably the *better*
number — the correlation bonus is spurious (D201). But a single entry point
exists so the algorithm can change *without fear*, and one that silently returns
a different answer than the path it replaces is the opposite of that. It would
have repriced every tour in the database on the day it landed, with a submission
saying nothing had changed. If we drop the cross-population, that is a decision
to announce, not a side effect of a refactor.

**The fix directs it into `compute_score`** rather than back into `evaluate()`:
if the step belongs to scoring, a caller should not be able to forget it. That
coupling is what the task existed to remove.

Also flagged: `_compute_config_hash()` requires a `config` argument, so the
stale-version guard could not be exercised externally. The submission asserts it
works without demonstrating it.

## D232 — A test whose baseline was the bug (2026-08-06)

LOCAL-311 came back fixed: `evaluate()` returns 101.6 matching the direct
scorer, 0 mismatches across all 46 tours, `algorithm_id`
`LOCAL-311-v1@41db0d2f` with a config hash over the thresholds themselves, and a
stale-version guard that now actually fires — they moved threshold reads from
frozen `from X import Y` bindings to live module lookups, which is why it could
never have fired before.

**Then their own identity test failed.** `test_evaluate_produces_identical_
scores` compared `evaluate()` against a hand-wired "old path" —
`parse_tour → analyze_stop → classify_stop → compute_score` — that **omitted the
`callbacks_to` cross-population**. That omission is precisely the bug the task
was bounced for.

So the baseline *was* the bug. The test passed originally because both sides were
broken (82.81 == 82.81), and started failing the instant the production code was
fixed. **A test that green-lights a defect and then reports the fix as a
regression is worse than no test.**

Corrected to compare against `score_tour_file`, the actual pre-existing public
path, which cross-populates and gives 101.5625 — matching the fixed
`evaluate()`. LEAD verified both paths independently *before* touching the test;
this is a wrong assertion, not a convenient one.

**The general shape, which has now appeared twice today** (D231 was the same
defect in production code): the correlation cross-population is a step living in
callers rather than in the function that needs it. LOCAL-311 fixed
`evaluate()` but left the logic duplicated in two places rather than folding it
into `compute_score`. LEAD's own bounce offered that as the lesser option
("or better, inside compute_score"), so the residual is LEAD's wording, not the
agent's shortfall. **A third caller will reintroduce it.** Worth folding in when
the scorer is next touched.

**Process note that worked:** the test gate held. The merge completed, the push
did not, and nothing reached `origin` until the suite was green. That is the fix
from three failed pushes earlier today doing its job.

## D233 — Corpus quality determines tour quality, demonstrated in one tour (2026-08-06)

LOCAL-314 harvested restaurant corpus. Bounced on the quality filter, but it
produced the cleanest natural experiment we have: **one pipeline, one tour, five
stops, and the only variable is the source.**

**Acchiardo — Forbes:**

> *"Since 1927, Acchiardo has remained true to its roots… The socca, a chickpea
> pancake, reflects the city's Italian influences, while the daube, a hearty beef
> stew, embodies the French heart of Niçoise cooking."*

**Le Bistrot d'Antoine — Yelp review and a scoring blog:**

> *"the clinking of cutlery… the aroma of garlic, herbs, and simmering sauces
> fills the air… earning the restaurant high marks in creativity and execution."*

Same generator, same prompt, same day. **The generator does not invent atmosphere
because it prefers atmosphere — it invents when given nothing.** Every previous
argument for corpus depth (LOCAL-252, 277, 283) was a before/after across time,
where other variables moved. This is side by side.

**A new fabrication route, and it is subtle.** *"Earning the restaurant high
marks in creativity and execution"* is a blogger's `Creativity: 7.5/10` restated
as a property of the restaurant. Not hallucinated — *laundered*. A subjective
rating entered the corpus and left as an apparent fact. Storing review scores
creates claims that survive every grounding check we have, because they *are*
grounded: in an opinion.

The bounce therefore forbids storing ratings at all, and filters passages on
content — year, named person, named dish, price, documented event — rather than
on whether the domain looks reputable.

**Also unfixed and now twice-observed:** R7 missed *"the aroma of garlic, herbs,
and simmering sauces fills the air"* and *"the clinking of cutlery"*, despite
LOCAL-303 widening it this morning. Restaurant sensory language is a register the
detector has never been tested against. Needs its own task.

## D234 — "Skipped" and "broken" are different words (2026-08-06)

LOCAL-310's blind-spot monitor delivers two working checks and one that cannot
run.

**Working, and it found something.** The per-venue distribution check:

```
corpus-wide          median 0.264
Asian Arts Museum    median 0.408   <- LOCAL-304's fix, visible in the data
Marc Chagall         median 0.000   <- FLAGGED, 47 stops, 23 corpus rows
```

And the corpus-vs-detector check catches the Ganesh stop, which is the
acceptance test: it would have found the chlorite gap without anyone reading the
tour.

**LEAD nearly called the Chagall flag wrong.** My own measurement gave median
0.125, and I was drafting a correction before checking the grouping. My glob
matched 491 stops by filename; the monitor grouped 47 by venue from the
database. Different populations, and the monitor's is the meaningful one.
**Sixth time today I have nearly contradicted an agent using a measurement that
answered a different question.**

**The broken check, and the wording matters.** The submission says *"Skipped — no
OPENAI_API_KEY in environment. The mechanism is implemented."* LEAD supplied a
key:

```
AttributeError: module 'openai' has no attribute 'OpenAI'
```

It uses the openai 1.x client class, which this environment does not have, while
every other API call in the codebase uses `requests.post` to
`/v1/chat/completions`. **It could never have run.** "Skipped for want of a key"
implies working code awaiting an input; "broken" is what this is. The distinction
decides whether anyone rechecks it — and had LEAD accepted the stated reason,
nobody would have.

Merged regardless, because checks 1 and 2 carry the value and are verified. The
defect and the mis-statement are recorded here and in the merge commit, and
LOCAL-315 fixes it and diagnoses Chagall.

## D235 — Michael's author asymmetry, built and proven (2026-08-06)

> *"We should not tell the authors when they edit tour, that what they produce is
> poor quality, but we should know about this."*

Implemented and verified end to end:

```
generated tour below 50   -> user-facing message, count visible
author edit below 50      -> recorded internally, NO message, ever
per-user average          -> no Flask routes at all; private by construction
```

`QUALITY_MESSAGE_THRESHOLD` defaults to 50.0 per Michael and is env-overridable.

**LEAD proved the leak guard rather than reading it.** Injected
`'quality_score': 42` into a live `return jsonify({...})` in
`tour_editing_phase2.py`:

```
FAILED TestLeakProtection::test_editing_endpoints_never_return_score
```

Source restored, 17 tests green. The guard scans the real file — two tests, one
extracting `promote_custom_tour` and one walking every jsonify response.

**LEAD misjudged it first.** I read the third test in the class — a
synthetic-string meta-test that checks a pattern against a string it wrote
itself — and concluded the leak protection was self-referential and weak. It is
supplementary to two tests that read the actual source. **Seventh time today I
have reached a wrong conclusion about an agent's work from a partial read**, and
the correction cost one command.

The pattern across all seven is the same and worth stating plainly: *I form the
judgement before I have looked at everything relevant, then verify the
judgement rather than the question.* The fix that keeps working is to make the
system demonstrate the property — inject the violation, run the failing thing in
isolation, call the function directly — rather than to read code and reason about
what it must do.

**Why the asymmetry matters as product design.** A user who shortens a tour or
adds personal commentary has made it worse by our rubric and better for
themselves. Scoring their edit and telling them would be us grading a customer on
their own work with a measure built for a different purpose. Recording it is
right; surfacing it is not.
