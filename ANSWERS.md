# Answers to Michael's questions

**Purpose:** Michael's questions get buried under status output in the
terminal. This file is the durable index. Newest first. Every entry has a
date, the question verbatim, and the short answer with a pointer to detail.

Open it in VS Code: `code ~/Audioura/ANSWERS.md`

**Every entry carries the time it was asked, so it can be located against
the terminal scroll.**

**Rule for LEAD:** when Michael asks a real question, the answer goes here
*as well as* in chat, before the next status dump buries it.

---

## Contents

- [Q-2026-08-16-4 — How to ask a side question without derailing the session](#q202608164)
- [Q-2026-08-16-3 — Is the Beta briefing pushed so Windows can fetch it?](#q202608163)
- [Q-2026-08-16-2 — After /clear + restart, can the validator work continue?](#q202608162)
- [Q-2026-08-16-1 — Did LEAD start working on Yuri's bugs? Should I clear?](#q202608161)
- [Q-2026-08-14-4 — What are the three independent scores for section 1?](#q202608144)
- [Q-2026-08-14-3 — Can the validator pass a good story and catch a false one?](#q202608143)
- [Q-2026-08-14-2 — Is our TRUE_TO_SOURCES verdict worth anything?](#q202608142)
- [Q-2026-08-14-1 — Why is stop 1 silent when the material is there?](#q202608141)
- [Q24 — Are the docker services working correctly now? Were they broken before?](#q24)
- [Q23 — Are we ready to continue working on the Storied release? **Answered: yes, pushed**](#q23)
- [Q22 — Explain "the fleet can't be verified by asking it"](#q22)
- [Q21 — Why did my tour generation fail completely?](#q21)
- [Q20 — Status while you were away, 2026-08-04 (LEAD-raised: 2 credentials need rotating)](#q20)
- [Q19 — Should the billing layer move to `storied`? **Answered: No**](#q19)
- [Q18 — Translation pricing: what is $2.71 for, can it be cheaper?](#q18)
- [Q17 — What is the credential pipeline, for whom, for what?](#q17)
- [Q16 — Can I add field-experiment tasks? Is ClickUp working?](#q16)
- [Q15 — What is the current Audioura version number?](#q15)
- [Q14 — How do I see the wallet screen on the Mac Mini?](#q14)
- [Q13 — How do I install on my iPhone? Ask you or Kiro?](#q13)
- [Q12 — Where is the APK to copy to an Android phone?](#q12)
- [Q11 — News generation fixed; but its billing cannot run (RESOLVED/open)](#q11)
- [Q10 — Tours silently vanish in production for existing venues (LEAD-raised)](#q10)
- [Q9 — News generation is broken in production (LEAD-raised)](#q9)
- [Q8 — Was development actually suspended?](#q8)
- [Q7 — Mobile builds: Windows for Android, then iPhone?](#q7)
- [Q6 — How can I see the Subscribed billing? App or services?](#q6)
- [Q5 — Who pays the bill for a "real request debiting real money"?](#q5)
- [Q4 — What is the builder that hung?](#q4)
- [Q3 — What does the $0.53 translation cost consist of?](#q3)
- [Q2 — Why am I suddenly getting permission requests from Kiro?](#q2)
- [Q1 — What has been done over the three days?](#q1)

---

## Code map — clickable

**How to use these in VS Code:** in the editor, **Cmd+Click** the link. In the preview
(**Cmd+Shift+V**) a single click works. Plain text like `story_validator.py:85` is only
clickable in a terminal, never in a markdown file — that is why the earlier version
highlighted but did nothing.

Line numbers drift as files change. If a link lands in the wrong place, the function
name is still right — search for it.

### The story gate (D450–D455)

- [`named_people()`](story_validator.py#L85) — who counts as a person. Fixed four ways: `World War` and `Maresfield Gardens` were people, a bare surname was nobody, and `Salvador Dalí` + a later `Dalí` were two humans
- [`classify()`](story_validator.py#L169) — UNFALSIFIABLE / CHECKABLE / UNCHECKED_FACTUAL
- [`open_question()`](story_validator.py#L210) — asks *who did it*, never *did X do it*
- [`contradiction_check()`](story_validator.py#L215) — SUPPORTED / CONTRADICTED / NO_USABLE_EVIDENCE
- [`validate()`](story_validator.py#L313) — the gate itself

### Michael's four routines (D445)

- [`request_to_ai()`](request_and_structure.py#L98) — routine 1, builds the query from the matrix
- [`structure_ai_output()`](request_and_structure.py#L198) — routine 4, the >5-sentences summarise rule
- [`ask_openai()`](michaels_chain.py#L51) — routine 2, calls the model
- [`main()`](michaels_chain.py#L66) — runs all four in his order and prints every stage

### The matrix and the story keyword (D441)

- [`build_matrix()`](interrogation_matrix.py#L637) — the interrogation matrix
- [`_pick_credit_line()`](interrogation_matrix.py#L418) — picks the story keyword; the exclude list is why stop 1 got `book` instead of Louis Broder
- [`extract_stops()`](interrogation_matrix.py#L96) — splits a tour into stops

### Scoring (D451)

- [`evaluate_story()`](evaluate_story.py#L401) — the three independent 0–100 axes
- [`_score_historic()`](evaluate_story.py#L221) — dates and consequence; `fled` now counts as a state change
- [`_score_detail()`](evaluate_story.py#L259) — material, count, process, dimension
- [`_score_social()`](evaluate_story.py#L300) — people, emotions, conduct
- [`_count_distinct_people()`](evaluate_story.py#L190) — delegates to `named_people()`

### Lead generation and verification (D440, D446)

- [`verify()`](story_leads.py#L214) — one narrow search per claim, two at most
- [`_principal()`](story_leads.py#L193) — the named party a claim is *about*
- [`_gemini()`](story_leads.py#L91) — Gemini, with `grounded=True` for Google Search grounding
- [`available_providers()`](story_leads.py#L133) — every provider we have a key for

### The old description gate (D447 — backwards for stories, correct for descriptions)

- [`validate_story()`](validate_story.py#L442) — must-be-confirmed; use for DESCRIPTIONS, not stories
- [`split_sentences()`](story_opportunity_scan.py#L126) — could not split after a quotation mark until 2026-08-14

### Tools

- [`story_trace.py`](story_trace.py) — every routine's input and output for one stop, offline, free
- [`story_worksheet.py`](story_worksheet.py) — the credit_line worksheet
- [`story_pipeline.py`](story_pipeline.py) — the retrieve-then-write chain
- [`STORY_GATE_TIERS.md`](STORY_GATE_TIERS.md) — the tier spec and measurement set
- [`STORIED_COMMUNICATION_03.MD`](STORIED_COMMUNICATION_03.MD) — the conversation
- [`DECISIONS.md`](DECISIONS.md) — the rulings and their evidence

---

<a name="q24"></a>
## Q24 — "Are the docker services working correctly now? Were they broken before?" (asked 2026-08-12, ~17:10 EDT)

**Yes to both.** Two more services were stale beyond the one that broke your tour, and
three "unhealthy" flags turned out to be false alarms.

- **`tour-editing-phase2`** was running the *same* pre-LOCAL-4xx generator code that
  broke your tour. It pins `image: audioura-tour-generator:latest` with no build of its
  own, so rebuilding the image did not touch it — a container keeps its old image until
  recreated.
- **`tour-orchestrator`** 1,865 lines vs the repo's 2,017; **`tour-generation-modernized-1`**
  539 vs 554. Both rebuilt.
- **`map-delivery`, `tour-processor`, `voice-control`** have shown `unhealthy` with a
  failing streak of **23,594** — because their healthcheck runs `curl`, which is not
  installed in those images. All three answer `HTTP 200` fine.

All 12 comparable services now match the repo; all 8 health endpoints return 200.
Detail: **D412**. The fix for the underlying blindness is dispatched as **LOCAL-452**.

---

<a name="q23"></a>
## Q23 — "Are we ready to continue working on the Storied release?" (asked 2026-08-12, ~17:25 EDT)

**Yes — and as of 18:0x the release is pushed.**

Your gate (2026-07-29): the iPhone field test proceeds once the internal score reaches
**75 at N=8 on the Asian Arts Museum**. Regenerated on current code in the rebuilt
container: **81.2**, up from the previous 75.0, with real margin instead of none.

```
tours/LOCAL320_museum_8stop_GATE_ce61b01.txt
Musée des Arts Asiatiques, Nice · 8 stops · 15,309 chars · 500s
base score 81.2 · container code_sha ce61b01 · now committed
```

`storied` pushed to origin: `55b2753..aef068e`. That included merging Track B's work
from the Windows machine, where both machines had independently allocated **D347** —
Track A keeps D347–D414, Track B renumbered to D415/D416, and Track B now allocates from
D500 up.

**Next: the iPhone field test.**

---

<a name="q22"></a>
## Q22 — "Explain 'the fleet can't be verified by asking it; it has to be diffed'" (asked 2026-08-12, ~17:30 EDT)

**20 of 21 services cannot tell you what code they are running.** Only
`Dockerfile.generator` accepts a `GIT_SHA` build arg, writes `/app/.git_sha`, and reports
it via `/health`. Every other service answers `unknown` or has no such file.

That is why stale code hid for over a week. `docker ps` said `Up 8 days`, `/health` said
`healthy`, and `code_sha: unknown` reads like a missing label, not a warning — while the
container ran 6,796 lines against the repo's 15,011.

Checking it required, per service: read the build context from `docker-compose-master.yml`,
find the real source file that context copies, and `md5` it against the container's copy.
That audit produced **five false positives** on its first pass, because a `find` by
basename matched the wrong `app.py` for five services that build from their own
subdirectories. An audit that is easy to get wrong is not a control.

**Dispatched as LOCAL-452:** `GIT_SHA` in all 20 remaining Dockerfiles, `code_sha` in
every `/health`, a `verify_fleet.sh` that prints service / reported sha / HEAD /
MATCH-STALE in one command, and a fix for the three `curl` healthchecks. Detail: **D410**,
**D412**.

---

<a name="q21"></a>
## Q21 — "Why did my tour generation fail completely?" (asked 2026-08-12, ~16:35 EDT)

**The pipeline was fine. The deployment was three years of drift.** Three separate
faults, all fixed at `742b355`:

1. **The container was not running your code** — 6,796 lines vs the repo's 15,011, with
   zero `LOCAL-4xx` markers. Anything generated through the app or port 5000 ran
   pre-LOCAL-4xx code with no exhibition checklist and no story chain.
2. **A `tests/` import that kills the container mid-run.**
   `style_validator_detector.py:33` imports `db_connection` from `tests/`, which
   `Dockerfile.generator` never copies. It blows up **at 138 seconds**, after every
   expensive phase is paid for. On the host it works, because `tests/` is on disk — same
   code, different filesystem, which is why LEAD's runs kept passing and yours did not.
3. **`db_connection.py` defaults to `localhost:5433` from inside the container** — the
   host's port mapping, closed there.

Result after the fixes: `SUCCESS 5651 chars in 156.9s`, 75.0 base at N=3, through the
same path your app uses.

**One thing worth knowing:** `beats_in_delivered_text=0`, which appears on every stop of
every run, is a **broken gauge** — it counts three consecutive ≥5-letter words copied
*verbatim* from a search snippet, so good prose scores 0 by construction. `LOCAL-388`
measures the same thing correctly and reported 8/8. Any conclusion resting on that
counter is void. Detail: **D410**.

---

<a name="q19"></a>
<a name="q20"></a>
## Q20 — "Please let me know the status" (asked 2026-08-04, ~08:35 EDT)

**Short answer:** 24 tasks reviewed overnight, 19 merged, 5 bounced. Two
findings need you: **two live credentials must be rotated**, and the tour
pipeline's real ceiling turned out to be the corpus, not the prompt.

### 1. Rotate two credentials (D81, corrected by D82)

| credential | where | on origin since | recoverable |
|---|---|---|---|
| OpenAI `sk-proj-wpIWgoRa…` | `sk.py`, full value | **2025-10-26** | **yes — rotate** |
| AWS `AKIAWLW3…` | two review docs, both branches; **this is the key in your `.env`** | 2026-06-07 | **yes — rotate** |

Redacted at the tip on both branches. Not rotated — that is outward-facing and
would break Polly for every running container. Not purged from history — that
needs a force-push. **Rotate → update `.env` → restart → then decide about
history.** Once the keys are dead the history is cosmetic.

A third item I reported yesterday was **wrong**: `SUBMISSION_LOCAL-39.md`
holds a 15-character prefix of your live OpenAI key, not the key. I saw a grep
hit and did not read the line. Corrected in D82.

### 2. The tour ceiling was never the prompt (D78)

Five rounds fought fabrication in the prompt and the model. The cause was that
**the two MAMAC stops every experiment used have no source material about the
artworks** — we hold artist biographies and nothing describing the objects.
The model was not failing to use the corpus; there was no corpus to use.

Corpus now: **51 COVERED · 7 CREATOR_ONLY · 2 VENUE_ONLY · 1 EMPTY** of 61 stops.

### 3. Model choice: switch for cost, not quality (D83)

On a properly covered venue the two models are equivalent on grounding
(1.87 vs 1.93 unsupported claims/paragraph) and indistinguishable on style.
gpt-4o-mini is **3.6x cheaper and 11% faster**. I will flip it *after* your
evaluation baseline is agreed, not underneath it.

### 4. Subscribed: five features built, none running (D76)

Truncation, real token rates, cache-hit charging and its wiring are all merged
and green on `subscribed`, and none of them execute — every image builds from
the `storied` working tree. LOCAL-204 built the path (project
`subscribed-204`, ports 5200/5202/5212, database `audiotours_subscribed`).
**Nothing is deployed**; a stack that starts charging wallets is not something
to switch on while you cannot field-test.

### 5. Two decisions waiting on you

- **CREATOR_ONLY stops** (D80): the gate cuts object-description 76%, but a
  gated stop reads as a detached artist biography that never acknowledges you
  are standing in front of something. With 2 stops, spending one on that is a
  poor trade. My lean: drop the stop, fix the corpus.
- **Truncation limits** (D65): I picked 5,000 free / 15,000 subscribed. Both
  are config; overturn freely.


## Q19 — [LEAD-raised] Should the billing layer move to `storied`?

**Found:** 2026-08-03, 17:15 EDT. **Needs Michael's decision.**

News billing is written, proven correct, and **cannot be deployed.**

`Dockerfile.news-orchestrator` now copies the four billing modules it needs.
But those modules exist only on `subscribed`:

```
wallet_ledger     storied NO    subscribed yes
pricing           storied NO    subscribed yes
payment_provider  storied NO    subscribed yes
projected_costs   storied NO    subscribed yes
```

and `news-orchestrator-1` builds with `context: .` from `~/Audioura`, which
is checked out on `storied`. A build from there fails outright — no such
file. That is worse than today, where the image builds and merely cannot
bill.

**The decision:** bring the billing layer to `storied`?

- **For:** it is the only way news billing (or wallet routes) can ever reach
  the shared containers, since D24 keeps those on `storied`. You already
  approved the same move for the LOCAL-156 fix.
- **Against:** materially bigger than one bug fix. It puts unreleased
  billing code on the branch your phone's containers build from. Until Apple
  products exist nobody can pay anyway, so there is no revenue lost by
  waiting.

LEAD has parked it rather than decide: this is about what runs on your
phone's stack, not a reversible implementation choice.


<a name="q18"></a>
## Q18 — Translation pricing: what is the $2.71 for, and can it be cheaper?

**Asked:** 2026-08-03, 14:20 EDT.

**$2.71 is one tour translated into one language** — a complete tour of
~16,300 characters and 8–10 stops rendered into e.g. Russian, audio
included. Not per stop, not per user.

**Already down to $1.55** as of 13:30 today (single-pass deployed):

| | our cost | user pays at ×5 |
|---|---|---|
| Saturday | $0.543 | $2.71 |
| **Now** | **$0.310** | **$1.55** |

Remaining split: **AWS Translate $0.245 (79%)**, **Polly TTS $0.066 (21%)**.

**Three ways lower, measured not guessed:**

1. **Stop translating discarded text — real but small.**
   `_restore_metadata_labels` throws away translated Address/Coordinates
   lines and restores English, because the app parses them by exact English
   match. Measured across 5 tours: **559 chars/tour, $0.0084, 2.7%** of the
   bill.
2. **Translate is 79% — the only big lever.** A cheaper provider than AWS's
   $15/1M, or translating narration only and never structured fields. The
   second changes what the user receives, so it is a product decision.
3. **Best lever costs nothing: don't re-translate.** Cache hits are already
   $0.00 and verified. Ten users wanting the same Russian tour cost $0.31
   once. Economics improve with usage, not cheaper APIs.

**On development cost** — today's verification runs cost about **$0.35**.
The $3.00 development ceiling is recorded as a **hard abort, not a licence**
(D44); tasks still refuse anything projecting over ~$0.50 unless their task
file says otherwise. The $1.30 product ceiling is unchanged.

---

<a name="q17"></a>
## Q17 — What is the credential pipeline, for whom, for what?

**Asked:** 2026-08-03, 14:20 EDT. *(Previous phrasing was jargon — apologies.)*

- **Whose credentials:** the user's own newspaper logins — Boston Globe and
  similar.
- **What for:** paywalled articles. A user pastes a subscriber-only link;
  without their login we retrieve the paywall, not the text. With it we
  fetch the real article and turn it into audio.
- **Why it exists:** it is the distinguishing value of the **$50/month
  Unlimited tier** — unrestricted content.
- **State:** your app already ships the screens that collect these logins.
  There is **no working server behind them**, and the server code that
  exists stores passwords in **plaintext**. Nothing has ever been stored
  (0 rows) and the service cannot start.

**The decision:** should Audioura hold users' third-party newspaper
passwords at all? Yes → real encryption before anything is stored. No →
delete the code and remove those screens. It is a liability question more
than a technical one.

---

<a name="q16"></a>
## Q16 — Can I add tasks from my field experiments? Is ClickUp working?

**Asked:** 2026-08-03, 09:25 EDT.

**Yes, please.** Two routes, both fine:

- **ClickUp** → 🔵 Claude — Review list. LEAD decomposes into Kiro tasks.
- **Just say it in chat.** Faster; LEAD writes the task files directly.

**ClickUp is working** — verified 2026-08-03 09:40 by querying the workspace:
four spaces returned (Beta/MVP, Storied, Subscribed, New Architecture).

Field findings are the most valuable input available. Tour quality has been
steered the whole time by an **internal rubric no real listener has ever
validated** — it moved 72.3 → 98.8 on that scale, and if your listeners
disagree, the rubric is wrong.

---

<a name="q15"></a>
## Q15 — What is the current Audioura version number?

**Asked:** 2026-08-03, 09:25 EDT. **Answer changed since asking.**

**`2.3.0+20`.**

When asked it was `2.2.0+1` — **stale**, unchanged through all of this work,
so builds could not be told apart on a device. Bumped per D1 (build numbers
globally monotonic). Verified in the built binary, not just the source:

```
aapt2 dump badging → versionCode='20' versionName='2.3.0'
```

---

<a name="q14"></a>
## Q14 — How do I see the wallet screen on the Mac Mini?

**Asked:** 2026-08-03, 09:25 EDT.

```bash
cd ~/Audioura && git checkout subscribed
cd audio_tour_app
flutter run -t lib/main_wallet_proof.dart -d chrome \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136
```

Opens the wallet in Chrome against the **live** subscribed stack — real
balance, real top-ups, real charges. LEAD can run it for you instead.

Already demonstrated this way: balance $0.00 → $10.00 after a real top-up,
and $10.00 → $9.92 after generating a real tour.

---

<a name="q13"></a>
## Q13 — How do I install on my iPhone once it is attached? Ask you or Kiro?

**Asked:** 2026-08-03, 09:25 EDT.

**Ask LEAD, not Kiro.** Kiro runs headless and cannot drive Xcode's signing
UI or respond to a trust prompt on the phone.

The flow: plug in and unlock the iPhone → LEAD runs `flutter devices` to
confirm it is seen → `flutter run -d <device-id>` with the debug flags.
Xcode needs a signing team selected once — that click is yours. Repeatable
afterwards.

**Caveat:** nothing has run on a phone yet. Expect the first install to be a
debugging session rather than a demo.

---

<a name="q12"></a>
## Q12 — Where is the APK to copy to an Android phone?

**Asked:** 2026-08-03, 09:25 EDT.

```
/Users/micha/Desktop/audioura-wallet-debug-2.3.0+20.apk     158 MB
```

Built with the wallet flags, so it points at the live subscribed stack on
port 5102.

When first asked there was **no APK anywhere on disk** — the earlier one was
built inside a task worktree's `build/` directory, which is not committed
(correctly; a 158 MB binary does not belong in git) and had been cleaned.
Rebuilt to the Desktop so it is findable.

**Not verified on a device.** `flutter devices` here shows only macOS,
Chrome and an iPhone — no Android target on this machine.


<a name="q11"></a>
## Q11 — [RESOLVED by LEAD] News generation is working again

**Fixed:** 2026-08-03, 13:05 EDT, after Michael authorised the Docker restart.

**News article generation was returning HTTP 503 to every request. It now
returns 200.**

```
before   {"allowed":false,"error":"quota_check_failed"}   HTTP 503
after    {"article_id":"...","message":"News article processed successfully"}   HTTP 200
```

**The cause was not the published hypothesis.** LOCAL-165 proposed that
`entitlements.py` failed to import `payment_provider`. With the CLI working,
the truth was simpler: **`entitlements.py` was not in the image at all.**
`Dockerfile.news-orchestrator` line 9 copies it — the deployed image was
built before that line existed. The Dockerfile was already correct; only the
image was stale. A rebuild took 4 seconds.

Nothing else was touched: 23 containers before and after, `audio_tours` 107,
`wallet_ledger` 217, credentials 0, Nice list unchanged.

### But billing still cannot run there

The rebuilt container holds exactly three Python files, and none of the
billing modules:

```
cost_meter    MISSING      wallet_ledger  MISSING
pricing       MISSING      cost_rates     MISSING
```

So the news billing code LOCAL-165 proved correct — cost metered, wallet
debited, cache hits free, the −$2.00 floor honoured — **cannot execute in
production.** A generated article is delivered and nothing is metered or
charged. Confirmed: a real article generated with cost_ledger empty
afterwards.

That is D31 once more — correct code with no way to be reached — and it is
a revenue hole rather than an outage. **This needs Michael's decision**,
because article pricing (~$0.006–$0.011 our cost) may not warrant the ×5
multiplier used for tours.


<a name="q10"></a>
## Q10 — [LEAD-raised] Tours silently vanish in production for venues that already exist

**Found:** 2026-08-03, 12:40 EDT. **Needs Michael's decision.**

LEAD generated a tour against the **shared stack on 5002 — the one your
phone uses**. Result:

```
job status        completed
audio_tours row   NEVER CREATED   (107 before, 107 after)
```

The venue already had a tour (id=1, your real Palais Lascaris tour from
2026-07-22), the insert hit a unique-name index, the exception was
swallowed, and the job reported success anyway. **The user is told their
tour is ready and it never appears in their library.**

This is the same defect LOCAL-156 fixed on Saturday — but that fix lives on
`subscribed`:

```
grep -c LOCAL-156 tour_orchestrator_service.py
  storied      0      <- what the shared stack runs
  subscribed  16      <- where the fix is
```

On the shared stack there is no wallet, so **no money is lost** — the harm
is a user asking for a tour, being told it succeeded, and getting nothing.

**What LEAD needs from Michael:** whether to bring the LOCAL-156 fix onto
`storied` and rebuild the shared orchestrator. That touches the container
your phone depends on, and it is blocked anyway while the Docker CLI is
wedged. Two reasons this is your call, not LEAD's.

**Cost note, disclosed:** this probe spent about **$0.017** of real
OpenAI/AWS money generating a 2-stop tour on production. A cheaper probe
would have sufficed; LEAD used a full generation where a lighter check
would have answered the question.


<a name="q9"></a>
## Q9 — [LEAD-raised] News article generation is broken in production

**Found:** 2026-08-03, 12:10 EDT. **Needs Michael's decision.**

**Every news article request returns HTTP 503.** Confirmed by direct probe:

```
POST /generate-news {"article_text":..., "secret_id":...}
  -> {"allowed":false,"error":"quota_check_failed"}   HTTP 503
```

Users cannot generate articles at all. The billing code behind it is
correct and proven — real cost metered at $0.008264, wallet debited, cache
hits free, D41's floor enforced — but nothing reaches it.

**The cause is unverified.** The hypothesis is a stale container image
missing `payment_provider.py`, but LEAD could not confirm it: `docker exec`
hangs because the Docker CLI is wedged. The shared containers run `storied`
code while that import landed on `subscribed`, so the explanation may not
hold as stated.

**What LEAD needs from Michael:**

1. **Is news generation used today?** If your app exposes it, this is a live
   outage. If it is unreleased, it is merely undeployed.
2. **The Docker Desktop restart.** The CLI has been wedged since 07:40. It
   is now blocking diagnosis of this outage, not just the 44% translation
   saving. A restart takes ~1 minute and briefly stops all 23 containers.


<a name="q8"></a>
## Q8 — Was development actually suspended as I asked?

**Asked:** 2026-08-03, 09:25 EDT (Monday morning).

**Yes, with one caveat, stated plainly.**

`PAUSE` was set the moment you asked. From then until 06:35 Monday: no new
work dispatched, nothing merged, no code changed. Health checked every 30
minutes, one line reported each time.

**The caveat:** LOCAL-156 was already running when you asked — it started at
23:17, minutes before. `PAUSE` stops new dispatch; it does not kill work in
flight. I let it finish rather than kill it mid-run. Exactly one session ran
during the window, and nothing from it was merged until Monday morning.

At 06:35 I judged "until morning" satisfied and resumed. If you would rather
I wait for your explicit word than read the clock, say so and I will.


<a name="q7"></a>
## Q7 — Mobile builds: Windows for Android, then iPhone?

**Asked:** 2026-08-02, 23:35 EDT — repeated 2026-08-03, 09:25 EDT.

> Should I engage Flutter builds on Windows computer as I always did before
> so I can build on Android, develop tasks for Mac Mini Kiro and then build
> on iPhone or you would recommend a different set of actions? I want
> tomorrow to see the wallet and see how it changes when I get a tour.

**Short answer: you do not need Windows, and you do not need a phone to see
the wallet working. The build problem is already solved; the only missing
piece is a device to run it on.**

### What changed overnight

- The **debug APK now builds on the Mac Mini** — 156.6 MB, wallet UI
  included, pointed at the subscribed stack. `flutter doctor` here is clean:
  Flutter 3.41.6, Android SDK 34, Xcode 26.4.
- The **wallet screen has actually rendered** with a live balance from the
  server, and updated from $0.00 to $10.00 after a real top-up. Not on a
  phone — on macOS/Chrome — but the same Dart, service layer and HTTP.

### Recommendation, in order

1. **See it today, no phone needed.** The wallet screen runs on this machine
   in Chrome against the live stack. You can watch the balance change in
   minutes. This is the fastest path to the thing you asked for.
2. **Build on the Mac Mini, not Windows.** It has Flutter, Android SDK and
   Xcode, and the `subscribed` branch with the wallet UI is already checked
   out beside the server. Windows adds branch syncing, USB, and IP confusion
   for no benefit — that confusion already produced one wrong IP in our docs.
3. **The real gap is a device.** `flutter devices` here shows only macOS,
   Chrome and an iPhone — no Android device or emulator. So:
   - **Android phone:** plug it in, or copy the APK across, and install.
   - **iPhone:** Xcode is here, but signing and the attached device need
     your hands.

### The one-line trick that avoids touching your live server

The subscribed stack already serves the entire wallet API on **port 5102**.
The app build takes `--dart-define=WALLET_DEBUG_PORT=5102`, which is inert
unless passed. So a debug build reaches a complete wallet server and
**nothing your phone currently depends on is modified.** No server rebuild.

### Honest caveat

Nothing has run on a phone yet. Expect the first device install to be a
debugging session rather than a demo.

---

<a name="q6"></a>
## Q6 — How can I see the Subscribed billing? App or services?

**Asked:** 2026-08-02, 22:58 EDT.

Services only at the time; **now also on screen** via desktop/Chrome.
Demonstrated live: the three plans exactly as specified (Free, PPU $2,
Unlimited $50), a $10 top-up, idempotency (same receipt twice does not
double-credit), the transaction ledger, and a tour charge.

Detail: `SUBSCRIBED_STATUS.md`.

---

<a name="q5"></a>
## Q5 — Who pays the bill, and how much, and why?

**Asked:** 2026-08-02, 23:12 EDT. This corrected sloppy wording of mine.

Two different kinds of money, which I had wrongly collapsed into one:

| | Amount | Real? | Who pays |
|---|---|---|---|
| OpenAI + AWS usage | **$0.016824** | **Yes** | You, on your API accounts |
| Wallet deduction | $0.08 | No | Nobody — internal credits |

The wallet used `FakePaymentProvider`. No card, Apple never contacted. The
$0.08 is $0.016824 × 5, deducted from a balance I invented minutes earlier.

What the demo proves is that the **plumbing** is real, not that anyone can
pay you. Real payment still needs the App Store products created.

---

<a name="q4"></a>
## Q4 — What is the builder that hung?

**Asked:** 2026-08-02, 22:30 EDT. **Resolved** 22:52 EDT.

**BuildKit v0.31.2**, a separate daemon from the one running your
containers — which is why builds were dead while 21 containers stayed
healthy for days.

Fixed by `docker buildx prune`. A trivial build went from timing out at 180s
to `exit=0 in 1.3s`; a real orchestrator image built in 5.5s. Reclaimable
cache was only 24.58 kB, so it was **wedged, not full**. If it recurs, try
`docker buildx prune` first — it is cheap and touches nothing running.

I skipped the Docker Desktop restart you also approved, because it was no
longer needed and would have taken 21 containers down for nothing.

**Second incident, also resolved.** The Docker *management API* wedged
separately on 2026-08-03 07:40 — `docker ps` timed out while every container
served normally. It hid a total outage of news generation for six hours,
because `docker exec` was the only way to see inside the container.
**Michael authorised a Docker Desktop restart at 12:55; CLI responsive in 20
seconds, all 23 containers recovered, nothing lost.**

---

<a name="q3"></a>
## Q3 — What does the $0.53 translation cost consist of?

**Asked:** 2026-08-02, 22:22 EDT.

Per tour into one language, mean 16,300 source characters:

| | chars sent | rate | cost |
|---|---|---|---|
| AWS Translate | 31,785 | $15 / 1M | **$0.477** |
| AWS Polly (TTS) | 16,414 | $4 / 1M | **$0.066** |
| | | | **$0.543** |

Translate is 88% of it. The old $0.372 was wrong twice: it used Google's
$20/1M when the code calls AWS at $15/1M, and it assumed one pass. The
service translates **every stop twice** — once for the text file, once
nav-stripped for the audio.

**44% is removable, and as of 2026-08-03 13:30 it is DEPLOYED and
measured in production**, not projected:

```
API calls   12  (2+N)   instead of 22  (2+2N)
cost        $0.3433     instead of $0.6004      -42.8%
fallbacks   none — every stop took the single-pass path
```

So a translation costs **$0.31, not $0.54** — **$1.55 rather than $2.71** at
×5. **Still above your $1.30 ceiling**, so the pricing decision below stands;
only the numbers improved.

Verified inside the running container, not just built:
`docker exec translation-service-1 grep -c LOCAL-142 …` → 4.

Detail: `TRANSLATION_PRICING.md` on the `subscribed` branch.

---

<a name="q2"></a>
## Q2 — Why am I suddenly getting permission requests from Kiro?

**Asked:** 2026-08-02, 21:10 EDT.

**They are macOS prompts, not Kiro's and not Claude Code's.** Neither
`--trust-all-tools` nor `bypassPermissions` can suppress them — different
layer.

**I caused the volume.** 46 Kiro sessions launched that day, 13 after 18:00,
four at 20:36 — 29 minutes before your screenshot. Each launch that touches
another app's data can re-trigger the consent dialog.

Recommendation: **Allow** — it is your own tool, and granting once should
stop the prompts. Declining is safe for tour generation and code work; the
likely casualty is ClickUp MCP, which we already work around.

---

<a name="q1"></a>
## Q1 — What has been done over the three days?

**Asked:** 2026-08-02, 21:45 EDT.

138 commits on `storied`, 104 on `subscribed`, 138 Kiro sessions, both
branches fully pushed.

**Built:** Subscribed billing end to end — cost metering, wallet ledger,
pricing, entitlement gate, tier switching, RevenueCat provider, Flutter
wallet UI.

**Found broken:** translation costing 43% more than booked; tour editing
with no server behind it; custom audio pointing at a service implementing a
different API; the Unlimited tier's credential pipeline with a client and no
server; six cases of correct code with no caller.

**My mistakes:** opened a plaintext-credential endpoint for 25 minutes (0
rows written); claimed tour editing worked after checking 2 of 6 routes;
nearly bounced a correct task over a failure my own probe created.

---

## Should I be suspicious of Kiro asking for Downloads and Documents access?
*(2026-08-06)*

**My recommendation: revoke both.** System Settings → Privacy & Security → Files
and Folders → Kiro. The need was spurious, and revoking is cheap to test — if
something legitimately requires it, it will ask again, and that prompt would be
worth scrutinising because it couldn't be explained by a stray `find`.

**Why it happened, and it was not malice.** Three Kiro sessions overnight ran
whole-home-directory scans between 03:36 and 06:40 — `find /Users/micha -name
"pytest"`, then `find /Users/micha -maxdepth 3 -name "python3*"`, then
`find / -maxdepth …`. I killed all three (D213, D218). macOS prompts for
Downloads and Documents exactly when a process traverses them. The agent was
hunting for the `python3` binary because it was not on PATH, and it widened the
search each time I removed its method without supplying another.

**What I could not prove.** I cannot read `TCC.db` (macOS protects it) and the
unified log had nothing retained, so the link between those scans and your
prompts is inference from timing and mechanism, not proof. It is a strong fit —
right window, no other plausible trigger, no task that needed those folders, and
no agent output referencing either path — but I did not watch it happen.

**Why it is still worth acting on.** Kiro runs with `--trust-all-tools`, so it
never asks before acting; it decided on its own to scan your home directory three
separate times; and the grant is persistent, not per-session. Every future Kiro
session can now read anything in Downloads and Documents. That matters more than
usual here because this repo already has one credential sitting in pushed git
history — an agent with home-directory read access *and* push access is a
combination worth being deliberate about.

**The cause is fixed.** Every task file since LOCAL-300 states `/usr/bin/python3`
as fact plus a no-`find` rule, and LOCAL-300 completed on its first attempt with
no scanning. Nothing queued needs access beyond the repo.

---

<a name="q202608141"></a>
## Q-2026-08-14-1 — Why is stop 1 silent when the material is there?

Its `credit_line` — the story keyword, the person a story gets built around — is the
common noun **"book"**. Every person the stop names is struck off the ladder for
already occupying another matrix slot: Miró is the `artist`, Mourlot the `printed_by`,
and Louis Broder — the publisher the whole story is about — the `publisher`.

Proven, not inferred: with the real exclude list `_pick_credit_line` returns
`('book', MENTIONED)`; drop `publisher` alone and the same call returns
`('Louis Broder', MENTIONED)`. **The better the matrix does its job, the worse the
keyword gets.** Not fixed — see D442 for why removing the exclusion needs a
same-people/same-event redundancy check first. Evidence: D441, D442.

<a name="q202608142"></a>
## Q-2026-08-14-2 — Is our "TRUE_TO_SOURCES" verdict worth anything?

**Less than its name suggests, and for two independent reasons.**

`validate_story` asks only whether a capitalised token or a year appears in the source
text. So it cannot see an invented place, an invented number, or a reversed fact — all
four of these PASS against a corpus containing "1974":

```
GROUNDED   ...illustrated the work in Barcelona.
GROUNDED   ...illustrated the work on the surface of the moon.
GROUNDED   ...illustrated the work using 47 copper plates.
GROUNDED   ...refused to illustrate the work.
```

And its gradient runs backwards for stories: a sentence carrying no new name and no new
year *cannot* fail, so **the vaguer the sentence, the safer it is.** Of Gemini's 30
sentences it flagged 5 and all five were true.

Separately, `story_pipeline` was reporting `STORY` for output `story_writer` had already
REJECTED — the writer's verdict was computed and then discarded. Fixed. Evidence: D444,
D447, D448.

<a name="q202608143"></a>
## Q-2026-08-14-3 — Can the validator be made to pass a good story and catch a false one?

**Partly, and the honest answer is "better, not finished."** `story_validator.py`
implements Michael's D450 gate: a story is rejected only when a source names a
DIFFERENT answer to the same question, never for being unconfirmed.

Measured over three runs each:

```
Gemini section 1 (true, good)                     PASSES         3/3   as required
"Leonard Woolf accompanied Dalí…" (false)         CONTRADICTED   3/3   as required
"Stefan Zweig accompanied Dalí…" (true)           SUPPORTED      3/3
"Boris Fridman gave Le Lézard… to the MFA" (true) CONTRADICTED   3/3   WRONG
```

The first three are what Michael asked for. **The fourth is a false rejection and it is
not solved:** the open question drifts to Alexander Calder's *Lizard*, the actor never
appears, and absence is read as refutation. A relevance guard was added and did not fix
it. So the gate is trustworthy when the search lands on the right subject and untrustworthy
when it does not, and it cannot yet tell those two cases apart.

Also fixed en route, shared by both instruments: `World War` and `Maresfield Gardens`
were classified as PEOPLE, a bare surname was classified as nobody (so "Dalí sketches
Freud" scored zero multi-person sentences), and "Salvador Dalí" plus a later "Dalí"
counted as two humans. Evidence: D450, D451.

<a name="q202608144"></a>
## Q-2026-08-14-4 — What are the three independent scores for Gemini's section 1?

```
historic  31     dates and the consequence of acts
detail     0     facts broken into facts — material, count, process, dimension
social    50     people, their emotions and their conduct toward each other
```

Independent 0–100, not a total. The reading is honest: the passage is a scene between
two men (social), anchored on one date and one state change — Freud fleeing Vienna
(historic) — and says nothing whatever about the physical object (detail 0).

Both `historic` and `social` were undercounted before today. `fled` scored no state
change while `destroy` did, so exile read as no event; and `admired`, `considers`,
`sketches`, `remarks` were absent from the social verbs even though D450 names emotions
and friendships as the axis. Evidence: D449, D451.

---

<a name="q202608161"></a>
## Q-2026-08-16-1 — Did LEAD start working on Yuri's bugs? Should the session be cleared?

**No. Zero mobile files were touched** — verified: `git log --name-only` over the last
six hours contains no path under `audio_tour_app/`.

What was done: located the two reports (they are ClickUp **DMs**, channel
`2ky4d0u8-919`, not tasks — which is why every list and keyword search missed them),
created an isolated worktree `~/audioura-worktrees/beta-mobile` on branch
`beta/yuri-bugs`, wrote `BETA_MOBILE_START_HERE.md`, and named the session in
`CLAUDE.md`. No mobile code was read or changed.

**This is exactly the confusion that produced the `ASK:` / `SIDE:` convention**
(Q-2026-08-16-4). The question was "where is the bug filed"; LEAD answered it as a
work item.

**On clearing: yes, clear now.** This session is long and long sessions are the
expensive kind against the weekly ceiling. Everything is committed. See
Q-2026-08-16-2 for exactly what a fresh session recovers.

<a name="q202608162"></a>
## Q-2026-08-16-2 — After `/clear` + `restart`, can the validator work continue?

**Yes, and nothing of substance is held only in context.** A fresh session recovers it
by reading, in this order:

```
bash restart.sh                  git state, row counts, queue, scores
DECISIONS.md   D440 -> D458      the whole story-gate thread, with evidence
STORY_GATE_TIERS.md              the tier spec and the measurement set
STORIED_COMMUNICATION_03.MD      the conversation, Michael's words verbatim
QUESTIONS.MD / ANSWERS.MD        the indexed questions
```

The code is committed too: `story_validator.py` (the D450 gate),
`michaels_chain.py` (his four routines), `story_trace.py`, `story_worksheet.py`, and
the repaired `evaluate_story.py`.

**Where the work stands, so the next session does not have to re-derive it:** the gate
passes the good story and catches the known hallucination, but **coverage is 13%** and
one true obscure claim is still falsely rejected. The binding constraint is not the
threshold — it is that grounded generation returns per-sentence citations at **83%**
coverage against our 13% (D458), so the architecture is the next move, not question
formation.

<a name="q202608163"></a>
## Q-2026-08-16-3 — Is the Beta briefing pushed so the Windows machine can fetch it?

**Yes.** `beta/yuri-bugs` is on origin at `2d0d92a` and
`git show origin/beta/yuri-bugs:BETA_MOBILE_START_HERE.md` reads back correctly.

From Windows: `git fetch origin && git checkout beta/yuri-bugs`.

**But there is a second half Michael did not ask about and needs to know.**
`storied` has **51 unpushed commits**, which is *all* of the validator work — D440–D458,
`story_validator.py`, `STORY_GATE_TIERS.md`, both conversation files. **None of it is
reachable from Windows.** The push is gated on the iPhone field test (a standing rule),
and today's commits are lab tooling rather than tour-pipeline changes, so the gate's
original reason does not obviously apply to them. **LEAD did not push `storied`** —
Michael's call, and it is one command either way.

<a name="q202608164"></a>
## Q-2026-08-16-4 — How to ask a side question without derailing the session

Two prefixes, usable alone or together, now recorded in `CLAUDE.md`:

- **`ASK:`** — answer only. No tool calls, no files changed, nothing committed. If it
  cannot be answered without investigating, say so and stop.
- **`SIDE:`** — a different topic from the current thread; logged under its own heading
  so the threads stay separable.

`ASK SIDE: where did Yuri file that bug?` would have produced one paragraph and no
worktree.

Without a prefix, RULE ZERO still applies — act, do not stall. **LEAD also carries an
obligation:** if a message might be a question rather than a task, and acting would
create files, branches or commits, say so in one line first. A question mistaken for a
task costs tokens and muddles the record; a task mistaken for a question costs one round
trip.

<a name="q202608171"></a>
## Q-2026-08-17-1 — Verify the Beta forward-merge on Storied (ClickUp `wdvrdaxnbw`)

**Merged clean, nothing damaged, and the one open item is fixed and live.**
`git merge origin/storied` → **11 files, 1468 insertions, zero deletions** — the shape of
the diff is the proof: no existing Storied file was modified or removed. Safety tag
`pre-beta-merge-20260817` = `e56be4c`. Merge base `afae00d`, as the task said. Local was
64 unpushed, not the 51 in `BRANCH_MODEL.md` — the extra 13 are LEAD session commits.

| ask | outcome |
|---|---|
| `.dockerignore` conflict | resolution correct. `!*_fixed.py` preserved — and it matters more than stated: `build_*.py` excludes `build_web_page_fixed.py`, so that line is the only thing keeping `tour-processor` buildable. `!requirements*.txt` now duplicated; harmless. |
| `[LOCAL-323]` cost attribution | intact — 5 refs, signature and the `args=(...)` thread call unchanged. |
| regression suites | `test_sq4_merge.py` ALL PASSED · `test_palais_fix_lead_fixture.py` 23/23. |
| `build_web_page_fixed.py:183` | **live, not dead code** — fixed as `a1f5d9f`, live-verified. |

**The liveness trace, because "is it dead code" was the whole question:**
`Dockerfile.tour-processor` COPYs it → `text_to_index_fixed.py:6` imports `generate_website`
→ `tour_generation_service.py:48` imports that → `CMD python tour_generation_service.py`
→ `audioura-tour-processor-1` running, `/health` 200. Image rebuilt, container recreated,
and the fix read back **from inside the container**, not from the source tree.

**A grep lied again (D242 check 3).** `build_web_page.py` already had the pause pattern at
:205–208 written as `other.pause()`; searching for `otherAudio.pause()` reported it absent.

**Not pushed.** Local `storied` is 66 ahead of `origin/storied`, still behind the iPhone
field-test gate; the fix touches a Storied-only file so it owes `main` nothing. No
`storied` → `main` merge made or proposed.

---

# 2026-08-18 — validator session (D466–D482)

**A181. Are good stories being dismissed as inaccurate without evidence? — YES, and the
first case was proven.** `local413_run_output.log`: the temporal gate rejected a true Juan
Gris / Pierre Reverdy collaboration on the claim that Gris "died in 1887". He died 1927.
Three defects: `(?:died|d\.?)` matched the final `d` of "published"; a partial snippet
shadowed the correct `_KNOWN_DATES`; a publication year was read as the interaction year.
[D466] · [`temporal_coherence_gate.py`](temporal_coherence_gate.py)

**A182. Delivered tours cannot show false rejections.** They contain only survivors. The
evidence lives in run drop logs. `gate_fp_probe.py` was built on the wrong premise and the
finding is recorded rather than the tool discarded. [D466]

**A183. Is Michael's described algorithm what the code does? — No.** 15 matrix fields not
8; `medium` = physical medium, `venue` = three fields, `credit_line` = provenance string
that LOCAL-406 parses `donor`/`printer` out of. Serper.dev is the only retrieval engine;
Gemini has zero production importers. `evaluate_story`/`story_validator` are not in the
live generator. Story-worthiness selection and the retry loop do not exist.
[`STORY_BASELINE.md`](STORY_BASELINE.md)

**A184. Why did the iteration curve plateau? — The metric, not the material.**
`valuation_index` had no term for the object; groundedness penalised specificity. Raising
the snippet cap moved `detail` 0→29 while the index FELL 61→50. [D467] ·
[`evaluate_story.py:342`](evaluate_story.py#L342)

**A185. Fixing the index moved the stories.** Object detail became first-class, sentences
past the third stopped being free, groundedness became an additive tiebreak. Best story
47 → 54 → 63 → 64 over four rounds. [D468] · `test_local468`

**A186. We ranked for one definition of "story" and scored on another.** 7 of 80 snippets
carried a stakes marker, 2 of 20 survived the cap, and the best line in the pool never
reached the writer. `_STAKES` is now imported by both ranker and scorer so they cannot
drift. [D469] · [`snippet_ranker.py`](snippet_ranker.py)

**A187. Is Storied ready for release? — No.** Full tour: lab 64 vs production 36. Hogarth
fabrication shipped; stop 2 was two sentences because a gate correctly deleted a false
claim and nothing replaced it. [D472] · `TOUR_MFA_RELEASE_20260818_1514.txt`

**A188. The retry loop works — and it teaches the model to evade the gate.** Worst stop
21→32, detail 13→33. Then, told not to repeat *or rephrase* a rejected claim, the model
nominalised the verb and shipped the same falsehood. Prohibitions now ban the assertion.
[D474, D476] · `generate_tour_text.py` PHASE 5.17

**A189. Anything regenerating after the gate chain must re-run the chain.** The retry was
checked by three fact gates and escaped every style gate. [D477]

**A190. The gates were producing broken English.** `_is_well_known` returned False for
Miró and Dalí but True for Picasso (no accent folding), so Miró was degraded out of a
sentence about his own book; the possessive guard tested the same ASCII literal twice.
[D475] · [`unglossed_reference_gate.py`](unglossed_reference_gate.py)

**A191. One fabrication escaped one gate in three grammatical forms on three runs.**
Passive (caught), active (D473), em-dash parenthetical (D478). Enumerating patterns loses
to a generative model. Also `[A-Z]` cannot match `É` — the D243 accent lesson, **fourth
time in one day**.

**A192. Misattribution ≠ hallucination, and it decides which gate catches what.** The
Hogarth Press is real and did publish Freud's 1939 edition; attributing the 1974 Dalí
edition to it is a misattribution. An entity-presence check cannot see it. **The
role-claim gate's narrow corpus is load-bearing — widening it would break it.** [D482]

**A193. A single tour run is a sample, not a measurement.** The same code scores 36–50.
Report mean and range over ≥3 runs. Final state: **45.7 mean, range 43–48.** [D480, D482]

**A194. What did today cost? ~$3.13** OpenAI + SERP (16 tours ≈ $2.59, lab ≈ $0.54);
$1.94 estimated because variance-run cost lines were grepped away. **`cost_ledger`
under-reports host-side work ~20×** — it showed $0.1110.

**A195. Why the instruments keep lying: three siblings ask the same question and only the
newest is right.** The org gate folded accents; `check_person_grounded` and
`_agent_in_text` did not. `story_validator._NAME_SPAN` used the accented capital class;
its three siblings used bare `[A-Z]`. Each was fixed correctly by whoever had just been
bitten, and nothing carried it sideways. Fix: **one primitive**
([`text_fold.py`](text_fold.py)) that every entity-vs-corpus comparison calls, plus a
**table-driven** suite so a new gate inherits every probe. [D483]

**A196. The word-boundary hunt came back EMPTY — the bugs were in the `in` comparisons.**
All 42 compiled regexes in the chain were swept mechanically; none matches inside a longer
word. `_agent_in_text('Ars', 'Arsenal Gallery')` returned True because it was a plain
substring test, not a regex. An audit scoped to "every regex" would have missed all of it.
[D483]

**A197. A gate needs a TRUE set, not only a FALSE set — and here is what that buys.**
`check_org_grounded` exempted any name *containing* a famous museum's, so `Tate Modern
Press`, `The Met Foundation` and `Louvre Editions` grounded for free against a corpus
naming none of them. Inventing a publishing arm for a real museum was the one fabrication
shape guaranteed to pass. The false-rejection half fails loudly and got fixed four times in
one day; this half fails silently and nobody had looked. [D483, STORY_GATE_TIERS.md m.6]

**A198. A gate that cannot SEE an entity reports success, not a miss.**
`_PERSON_MULTI_WORD` is gate 5.158's extractor and was blind to `É`, so "Édouard Manet"
was never recognised as a person and never checked for grounding. The cost was an
inspection, not a drop. [D483]

**A199. OpenAI credits are exhausted (2026-08-18 21:49).** Three measurement runs failed
at the first API call — `credit_balance_exhausted`, nothing spent. **No tour can be
generated at all until credits are added**, which is Michael's billing action. Consequence
for the record: **45.7 (A193) is stale and must not be re-quoted** — these were
gate-behaviour changes and their end-to-end effect is unmeasured. [D483]

**A200. All seven of Michael's steps are wired (2026-08-19).** Five modules got their
first production caller: [`evaluate_story`](evaluate_story.py),
[`story_opportunity_scan`](story_opportunity_scan.py), [`story_leads`](story_leads.py),
`corpus_coverage`'s action half, and the new [`story_pass.py`](story_pass.py). The gap was
integration, not invention — which is why the lab scored 64 and production 43. [D485]

**A201. THE limiting factor is the MATERIAL, not the prompt.** With the story isolated in
its own pass, it writes the best story the snippets allow and the detector still refuses
it: *"someone is described, but nothing is risked, refused or lost."* **No stakes exist in
the retrieved material for any stop.** No prompt can add them without inventing, and an
invention in the story pass lands **upstream of every gate**. Six rounds of prompt work
were spent on a shortage of material. **Next work is retrieval.** [D485]

**A202. Two of Michael's own definitions of "story" disagree, and it is his ruling.**
Step 3 says a chain ACROSS entities (fact → stop → exhibition); the scanner's bar says
THREE consecutive sentences about ONE person with action and stakes. A sentence each about
publisher, printer and donor satisfies the first and is "a list of credits" to the second.
The generator now aims at both; which governs when they conflict is a product question.
[D485]

**A203. Step 3.4 never fired: these stops are thin in KIND, not in volume.** The
replenishment floor measures characters; every stop cleared it. What is missing is stakes.
A volume floor cannot detect that. [D485]

**A204. `gemini` + `gemini_grounded` is ONE model answering twice.** The first live
fan-out reported exactly one "cross-model agreement" and that was it — a model counted as
its own corroboration, the error `story_leads`' own docstring warns about. Agreement is
now counted by model FAMILY. [D485, LOCAL-488]

## Code map — added 2026-08-19
- [`SEVEN_POINTS_PLAN.md`](SEVEN_POINTS_PLAN.md) — what each of the 7 steps needed
- [`story_pass.py`](story_pass.py) — D474: the story as its own pass over its own object
- [`story_index_pass.py`](story_index_pass.py) — step 5, report-only valuation index
- [`story_worthiness.py`](story_worthiness.py) — step 2, which stops earn mining
- [`story_replenish.py`](story_replenish.py) — step 3.4, capped "learn more" round
- [`story_focus_fact.py`](story_focus_fact.py) — step 7b, the rotation, named-agent first
- [`OPENAI_CREDIT_LOG.md`](OPENAI_CREDIT_LOG.md) — top-ups, outages, burn rate

## Code map — added 2026-08-18
- [`STORY_BASELINE.md`](STORY_BASELINE.md) — what the pipeline actually does, with links
- [`story_iteration_chart.py`](story_iteration_chart.py) — the retry loop in the lab
- [`STORY_ITERATION_CHART.md`](STORY_ITERATION_CHART.md) — score over iterations
- [`gate_fp_probe.py`](gate_fp_probe.py) — false-rejection probe (premise flawed, see A182)
- [`run_full_tour_release_check.py`](run_full_tour_release_check.py) — full tour + per-stop scores
- `VARIANCE_{CLEAN,CONTROL,WIDENED}.log` — the three A/B arms
- [`text_fold.py`](text_fold.py) — THE accent-fold + whole-word primitive for the gate chain
- [`test_local483_gate_fold_and_boundary.py`](test_local483_gate_fold_and_boundary.py) — the gate chain audited as a class
- `LOCAL483_REMEASURE.log` — the three blocked runs (`credit_balance_exhausted`)
