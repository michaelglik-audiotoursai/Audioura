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

- [Q19 — Should the billing layer move to `storied`? (LEAD-raised)](#q19)
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

<a name="q19"></a>
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
