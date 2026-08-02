# Return Briefing

Written 2026-08-01 for Michael. Covers everything since Subscribed work
was cleared on 2026-07-31.

---

## 1. The headline

The tour-quality gate is cleared. Five independent runs on the isolated
verification stack scored mean 98.8, spread 20.6, worst 87.8. The base
score alone (per-stop substance, no callbacks) reaches 81–87 in every run
— well above 75 without needing the dominant-story mechanism at all.

Your field test is the next step. That is your call to make.

---

## 2. What changed while you were away

### Tour quality

The gate failed on the first measurement (mean 72.3, three runs). Two
fixes brought it home:

- **Factsheets were not reaching the prompt.** HTML parsing assigned
  metadata to the wrong section; the evidence log was being overwritten.
  Fixed: facts now verifiably arrive at the generation prompt.
- **Facts were not surviving into prose.** The binding block sat too early
  in the context window and got overridden by recency bias. Moved to
  final position; post-generation validator added with retry.

After those two fixes, the second measurement (five runs, isolated stack)
cleared the gate in every run.

### Subscribed

The Subscribed design document is written and locked. Six decisions (D1–D7)
are recorded. Key points settled:

- Pay-Per-Use: $10 credit top-ups, $2/month fee billed as subscription,
  cost × 5 pricing, hard stop at zero balance.
- Unlimited: $50/month, stops at $25 our cost.
- Free plan survives unchanged.
- Credits are consumable IAP; no auto-charge (Apple StoreKit rule). Reminder
  at $2 remaining.
- Build numbers are globally monotonic; next mobile build is 2.3.0+20.
- Payment provider: Apple IAP via RevenueCat, behind a PaymentProvider
  interface with a working fake until you create App Store Connect products.

No Subscribed *code* has shipped yet. The gate clearance and push to origin
were the precondition you set.

### Swipe personalisation

Stop-ordering by user preference is built (schema, service, beta-count
model). Two users at the same venue get different stop orders based on
swipe feedback. Cold start defaults to quality-only ordering. Disliked
classes are biased lower, never removed.

The route was unwired when originally built (register_preference_routes
defined but never called). That single missing line has since been added on
storied.

### Features found unwired

An audit of the entire codebase found 8 unwired features. Three have been
fixed:

- **Sharing** — Blueprint registered; POST /tour/share and GET /tour/<id>
  now return 200. Round trip confirmed. No charge to sender.
- **Referral** — Blueprint registered; create and redeem endpoints work.
  Abuse controls added (self-referral blocked, duplicate blocked, rate
  limit 10/60s).
- **Persona** — Blueprint registered; POST/GET /user/persona return 200.
  However, the mobile app stores persona locally in SharedPreferences and
  does not call this endpoint. Wired for future use only.

Still unwired (lower severity): spine quality scorer (wired as a gate with
threshold 2, max 1 retry — it never fires on real spines since all score
≥3), tour hook generator — CORRECTED 2026-08-02: the hook DOES become audio. generate_tour_text.py:6091 feeds it to a prolog prompt and the result opens Stop 1. The module is superseded, not a missing feature (see TOUR_HOOK_ANALYSIS.md), cost
reader (get_operation_cost is write-only), and two silent ImportError blocks
on cost ceiling health checks.

### Infrastructure and guards

- **Isolated verification stack** — separate docker-compose for tour quality
  (ports 5200/5202/5221) so tests cannot touch production data or shared
  containers.
- **Test mode over HTTP** — tours generated with is_test=true are excluded
  from tours-near queries. Only accepted when TOUR_TEST_MODE_ALLOW_REQUEST
  is true server-side.
- **Data-loss guards** — 5-minute table snapshots, row-loss alarm. These
  were added after tour 29 was deleted during autonomous operation and
  restored from disk.
- **Dead test cleanup** — no truly dead tests found; 41 import failures are
  missing pip packages, not removed code. Suite: 51 pass, 0 fail.
- **Spine quality gate** — threshold 2, max 1 retry, scoring failure warns
  but delivers. Worst-case cost: +$0.015 per retry.

---

## 3. What is broken right now

**Docker's build subsystem is hung on this machine.** A three-line Alpine
image times out after 180 seconds. Running containers stay healthy; the
problem is exclusively in the builder.

This was traced to resource exhaustion: 91% swap, 87 cached Docker images.

**What it blocks:** any task that needs to build or rebuild a container.
New service code cannot be deployed until the builder is fixed or the
machine is cleaned.

**What still works:** all currently running services, every host-side test,
the verification stack (already built), git operations, the Flutter app.

---

## 4. What needs you specifically

1. **Apple App Store Connect products.** The payment system is built behind
   a fake provider. Real IAP requires you to create the subscription and
   consumable products in App Store Connect. The enrollment guide is in the
   repo (APPLE_APP_STORE_ENROLLMENT_STEP_BY_STEP.md).

2. **The field test.** The gate is cleared on paper. Whether it is cleared
   *for your city, your venues, your standards* is your call. No one else
   can make it.

---

## 5. Decisions taken in your absence you may want to reverse

Filtered from 32 total — showing only those with product or money
consequences. All are reversible.

| # | Decision | Why it was made | How to undo |
|---|----------|-----------------|-------------|
| D2 | $2/month fee does NOT apply to Unlimited | Simplicity; $50 covers all | Add fee line to Unlimited tier config |
| D3 | Zero balance = hard stop, no negative from normal use | Prevents surprise bills | Allow grace period or overdraft |
| D4 | Unlimited cost-stop shows message + offers PPU switch | Transparency | Silent degradation or auto-upgrade |
| D5 | Free plan survives unchanged | Every existing user is on it | Sunset or limit free tier |
| D15 | Cost ceiling limits delivery, not spend (check after generation) | Cannot pre-compute cost accurately | Pre-check with estimate, reject before generating |
| D16 | "ppu" is the canonical tier identifier | Brevity as PK | Rename to "pay_per_use" in DB |
| D20 | $2/month fee must NOT be deducted from credits | Credits = usage only | Let fee draw from credit balance |
| D22 | Thin-corpus / 80-word rule stays | Measurement showed it enriches (39.7 vs 32.7 mean) | Remove rule from prompt |
| D23 | DELETE FROM audio_tours forbidden in task files | Tour 29 data loss | Relax if cleanup mechanism added |
| D24 | Shared containers stay built from storied; subscribed builds its own | Your phone depends on shared services | Merge container builds |

---

## 6. Open risks

- **Tour 29 deletion — cause never found.** The tour and its translations
  were deleted during autonomous operation. Data was restored from disk.
  Guards (snapshots, row-loss alarm, DELETE ban) prevent recurrence but do
  not explain what happened. (D23)

- **Translation costs 6× the tour it translates.** A fresh 15-stop tour
  costs $0.069. If translation scales similarly to the measured generation
  cost, a translated tour at ×5 pricing is $2+ to the user. At $10 credit
  balance, a user who translates five tours is empty. No pricing decision
  has been made here.

- **Docker builder hung.** Described above. Any new service deployment is
  blocked until resolved.

- **Referral redemption grants nothing.** The endpoint works; the reward is
  undefined. Building the reward without a pricing decision risks giving
  away something you did not intend.

- **Two silent ImportError blocks on cost ceiling monitor.** If the import
  fails, the health check returns {} and no one is told the ceiling has
  vanished. Controls are supposed to fail closed (D14); these fail open.

---

## Corrections to prior reporting

Three things you were told that turned out to be wrong:

**SQ4b callbacks were overstated.** You were told 6/8 stops had callbacks
(75%). The real count across three independent readings was 2, 0, and 1.
The inflated number came from substring matching — the counter matched title
words appearing anywhere in the text, not genuine narrative callbacks.
(D25)

**"Three user-facing features are unwired" was two.** The audit found
persona, sharing, and referral endpoints unwired. But the mobile app never
calls /user/persona — it stores persona locally in SharedPreferences. The
endpoint is wired now for future use, but it was not a user-facing gap.
The correct count of features users were actually missing: two (sharing and
referral).

**75 no longer requires the dominant story.** When the corpus had 6
canonical titles, the base score capped around 50 and the dominant-story
mechanism was the only path to 75. Corpus expansion raised the title count
to 8, which raised the base cap to 100. The gate is now reachable from
per-stop substance alone — and that is how all five passing runs achieved
it. (D26)

---

## Reference table

| Ref | Source |
|-----|--------|
| Gate measurement | SUBMISSION_LOCAL-100 |
| Gate failure (first attempt) | SUBMISSION_LOCAL-96 |
| Factsheets fix | SUBMISSION_LOCAL-97 |
| Facts-into-prose fix | SUBMISSION_LOCAL-98 |
| Verification stack | SUBMISSION_LOCAL-99 |
| Swipe preferences | SUBMISSION_LOCAL-101 |
| Dead test audit | SUBMISSION_LOCAL-102 |
| Test mode | SUBMISSION_LOCAL-103 |
| Unwired audit | SUBMISSION_LOCAL-108, UNWIRED_AUDIT.md |
| Sharing wired | SUBMISSION_LOCAL-110 |
| Spine quality gate | SUBMISSION_LOCAL-111 |
| Persona wired | SUBMISSION_LOCAL-113 |
| Referral wired | SUBMISSION_LOCAL-114 |
| Referral abuse controls | SUBMISSION_LOCAL-115 |
| Dominant story | SUBMISSION_LOCAL-95 |
| Subscribed design | SUBSCRIBED_DESIGN.md |
| All 32 decisions | DECISIONS.md |
| Docker failure | D32 |
| Data loss incident | D23 |
| Callback overstatement | D25 |
| Corpus expansion | D26 |

---

## Note on "the app" (added 2026-08-02)

Several claims in the record say what "the mobile app" does. That is
ambiguous here, because two branches carry different apps:

- `storied` — no swipe UI, no share button, no referral or persona screens
- `subscribed` — has the Wallet, paywall and swipe controls built this week

An audit run from `storied` will correctly report "no swipe UI exists" while
the same audit from `subscribed` reports the opposite. Both are true of
their branch. When reading any claim about the app, check which branch it
was made from.

This bit twice: `UNWIRED_AUDIT.md` overstated severity partly by assuming an
app caller existed, and the audit correcting it then understated the app by
reading only `storied`.

