# STORIED_COMMUNICATION_04.MD

Opened 2026-09-23, continuing from `STORIED_COMMUNICATION_03.MD` (closed at 97 KB).
Volumes 01 and 02 are closed. **This is the live volume — maintain it here.**

## The rule for this file

Michael's questions verbatim and LEAD's final answers, chronological. **Questions and
conclusions only** — no tool output, no status chatter, no reasoning trace. If an
entry takes more than a minute to read it belongs in `DECISIONS.md` with a pointer
from here. Volume 01 reached 123 KB by ignoring this and became unsearchable; Volume
03 reached 97 KB the same way.

Append the exchange **before starting the next task**, not at session end — sessions
are killed and restarted by design (D252) and anything held only in context is lost.

---

## State at the moment this volume opened

**Tours.** Round 7's ten defects: four fixed and verified, four merged today, one
retired, one (LOCAL-528, anachronistic material on a part) completed but unreviewed.
Round 9 was generating — the first batch with every fix merged, same two venues as
rounds 7 and 8 so the comparison is clean.

**The one open quality problem.** Deterministic defects are fixed and stay fixed.
What survives is everything that requires knowing something about the world, and it
all scores CLEAN: Eiffel building Boston Logan, a church's dedication rendered as its
founder, Lindbergh landing on a jet bridge thirty years before jet bridges. LOCAL-527
now scores the first two; LOCAL-528 targets the third.

**Cost.** ~$0.21 per 4-stop tour, measured. **That excludes grounding** (~3.5c per
request, independent of tokens). LOCAL-533 will split them. Do not optimise before it
lands. Caching already works; the lever is hit rate (D581).

**Infrastructure.** Docker recovered by killing the backend process, not restarting
the app — data intact, 168 rows, and a factory reset must never be used because
`postgres_data` is a named volume the backup does not cover. The dispatcher now
requires an explicit allowlist and fails closed (D587) after releasing 35 tasks when
4 were intended.

**Open for Michael.** Hard drive chosen for active Docker/worktree work — he has dock
extensions, so no port-hub premium is needed. Subscribed untouched; Igor's E2E
(LOCAL-524) is the starting point, and it currently fails.

**Standing instruction as of the /clear:** finish round 9, run the Amazon-Q critique,
analyse it rather than trusting it, and **tell Michael when it comes back with nothing
left to fix.** Full detail in `REMINDER_NEXT_SESSION.md`.

---

## 2026-09-24 — GCloud or local Docker for Igor's enhancement?

**LEAD asked:** if you want Igor's enhancement on GCloud rather than just local
Docker, say so and I'll tell you what a TestFlight build needs — I'd want your
explicit go-ahead first, since it publishes.

**Michael:** *"only on local Docker before we approve the results of the Igor's
test."*

**Answer/action.** Recorded as **D591**. No GCloud deploy from `storied` HEAD and no
store build until he approves Igor's test results. Two tracked files said the
opposite — `HANDOFF_20260924_MORNING.md` ("Michael asked for it to ship with this
deploy") and `GCLOUD_STORIED_START_HERE.md` under BEFORE THIS DEPLOY — both written
before he was asked. Both corrected and pushed, because the Windows session reads
them at start and would otherwise have deployed unapproved work.

One trap worth naming: the tag `rc-pre-igor-20260923` looks like the clean
deploy-without-Igor point, but the MFA regex-hang fix `19358ae` lands *after* it.
Deploying the tag trades unapproved work for a known hang. There is no feature flag;
separating the two needs one, and Kiro writes it, not LEAD.

---

---
## 2026-10-01 — iOS 401 on Preview; Mac Mini disk full

**Michael:** "Please read your queue: Windows Claude updated GCloud, but I cannot run tests because of some security issue."

**LEAD:** Task `wdvrdayq0a`. The iPhone app was not a TestFlight build. It was the 09-24 tethered install from `install_to_iphone.sh`, which never passed `--dart-define=GATEWAY_API_KEY`. Local mode doesn't check the key; Preview rejects every call with 401. The Mac's key is correct (fp `1b56f014a180`); the 09-24 binaries contain no key; TestFlight 25/26 do. Fixed on storied @ `462e1df`: new `gateway_key_check.sh` refuses an empty or wrong key by fingerprint, and the install and release scripts use it. **To test now:** install TestFlight 26, or re-run `./install_to_iphone.sh` with the cable.

**Also:** Docker had been dead since 09-24 because the disk was full (140 MB free). The cause was 25 leaked Kiro CLI self-update downloads (~18 GB in `$TMPDIR/kiro-cli-download*`, several still mounted). Michael approved deleting them; 20 GB is now free and Docker is back up. They will build up again, about 1 GB per update attempt; the new SSD (pickup Sat 10-04) is the lasting fix.

**Michael (same day):** The new install connected. A Preview restaurant tour of "Boston Sail Loft, Boston, MA" (1 stop, en + ru) had good stories, but the stop was Union Oyster House. "Can you check?"

**LEAD:** Reproduced on the deployed code. The intent model read "Sail Loft" as a theme ("sailing locations") with venue_name null, although it said the scope is ONE BUILDING. The named restaurant was never a candidate, so the most famous waterfront restaurant won. Fix LOCAL-556 (storied @ `390af38`): a restaurant tour bounded by one building IS that restaurant, inserted as a stop the listener named. Local rerun gives Stop 1 = Boston Sail Loft (OSM-verified, grounded facts). Redeploy requested from GCloud_Storied: ClickUp `wdvrdayqby`.

**Michael (local):** "Restaurant Tour Of Buttermilk & Bourbon - Back Bay, Boston, MA" gave Grill 23 & Bar. "Fix the bug or explain why Grill 23 is right."

**LEAD:** A bug, and the same one by another route. The intent step made the branch label "Back Bay" the DISTRICT scope and dropped the restaurant, so the first fix (BUILDING scope only) never fired. LOCAL-556 r2 (`43b3ca3`) adds an intent field `named_places`, guarded so that only names literally in the request are accepted. End to end: Stop 1 = Buttermilk & Bourbon. Local container rebuilt; cloud redeploy request in `wdvrdayqby` updated to 43b3ca3.

**Michael:** Paid $20 for one week of Gemini, with only one cloud tour complained about. Can we have spent that, or is someone piggy-backing?

**LEAD:** Most likely our own use. Gemini bills mainly per *grounded search*: $0.035 each, and a tour issues up to ~30. The Mac Mini's ledger alone records $9.03 of grounding on 09-24 (22 local tours, Igor/Sycamore testing), avg $0.40 and max $1.09 per tour. The cloud Preview generator uses the same key, plus Windows-side test runs, which the Mac cannot see. The key has never been in git (checked full history; fingerprint `5dbce1c7de78`). Recommended: one key per machine/environment so the bill attributes itself, and check AI Studio / Cloud Console usage by day.

**Michael:** Two local Chart House tours, one with the stop he named (new user-stops feature) and one the original way. The first was better and longer. Both acceptable. He proposes promoting Storied to Stable and moving Subscribed into Preview, or perhaps keeping releases as they are?

**LEAD:** The original-way run researched "Chart House Restaurant" (the category word copied from "restaurant tour"): 423 chars of source vs 14,923, medium vs rich tier, story score 34 vs 46. Fixed (LOCAL-557 r3, `398f592`; renumbered from 556, which was taken). Release: **keep as is for now.** Promote Storied to Stable after (1) 398f592 is verified on Preview, (2) Michael decides whether today's test is the approval D591 waits for (user stops are local-only), (3) true per-tour cost including Gemini grounding is known, (4) the urgent cloud bugs (translation 404, edit save/corruption) are checked against the Storied stack. Subscribed goes to Preview only when there is a Subscribed build to test; moving it now would leave Storied fixes no staging track.

**Michael (4 items):** (1) why can't he just say "work your queue"; (2) approves today's test for GCloud and TestFlight, asks whether a Pixel 6 is a good Android test phone; (3) whether to keep Beta, a price formula ($0.25 + $0.25 × stops?), cheaper tours; (4) what "three urgent cloud bugs open" meant.

**LEAD:** (1) Now he can: the deploy task wdvrdayqby is rewritten self-contained and urgent (storied @ 9e24304, USER_STOPS_ENABLED=true on Preview). (2) D593 recorded. fix/local554 merged into storied; iOS 2.3.2 (27) uploaded to TestFlight, not distributed. Pixel 6 works but its updates end Oct 2026; prefer a Pixel 7 if close in price. (3) Measured real Storied cost: 1 stop ≈ $0.14 (OpenAI $0.035 + Gemini $0.105); 2–3 stops ≈ $0.45–0.50; audio not metered. About $5 of the $9 Gemini on 09-24 came from automated tests. Beta's cost has never been measured. Recommend retiring Beta as a product once Storied is Stable, with free = Storied 1-stop. (4) Correction: all three are FIXED and verified on Preview; ClickUp status was never closed. Translation is fixed on both tracks. Editing is fixed on Preview only, awaiting Michael's device re-test on tour 421 before Stable gets the routes.

**Michael:** Ordered a Pixel 7. Cost: only what testers/listeners cost matters; for a 5-stop tour including Polly, what's the average cost, and what does one translation add? Plan: test Storied on GCloud, then Storied → Stable and Subscribed → Preview. Curators should charge through us, and he wanted to take only 10%; if Apple and Google take a larger cut, what are the alternatives?

**LEAD:** 5 stops ≈ $1.00 (OpenAI ≈ $0.28, Gemini grounding ≈ $0.55, Polly neural ≈ $0.16 on ~10k spoken chars; standard voices ≈ $0.04). One translation ≈ +$0.35 (AWS Translate ≈ $0.17 + Polly ≈ $0.18). Store-fee alternatives: 15% tiers (Apple Small Business Program, Google first $1M), web checkout (US link-out) with Stripe Connect payouts, and a fee stated as "10% of what remains after the store." Rules are changing, so verify before building.

**Michael:** "Please create such page" (curator payment options for an advisor).

**LEAD:** Doc "Curator Payments Options": https://claude.ai/code/artifact/21b5f494-d7e3-4246-acf2-f43750ddd594. Recommendation: in-app purchase at the stores' 15% small-developer rate, Audioura 10% of the remainder (curator $7.65 on $10); on US iPhone also web checkout, where Apple currently charges 0% (curator $8.41). Skip Android link-out: Google charges up to 20% from Oct 1, 2026, more than Play Billing. Includes cost floor and advisor questions.

**Michael:** Ideas to minimise cost per tour per listener, e.g. Serper or Hugging Face models, assuming GCloud hosting is cheap.

**LEAD:** Ranked levers for a 5-stop tour (now ≈ $1.00): (1) replace Gemini grounded search ($0.55) with Serper, already wired in dining_corpus_harvester.py, plus a small model reading the results (≈ $0.03–0.05); (2) cache research per venue, so a repeat venue costs ≈ $0; (3) move the gate/check calls from gpt-4o to gpt-4o-mini-class models; 62 call sites use gpt-4o today (OpenAI $0.28 → ≈ $0.12); (4) open-source TTS (Kokoro) on Cloud Run CPU for English (Polly $0.16 → ≈ $0.02), keeping Polly for languages it lacks; (5) translation by small LLM instead of AWS Translate ($0.17 → ≈ $0.01). Target ≈ $0.20–0.25 per new tour. Self-hosting an LLM on GPU only pays at high volume; not now. Every swap needs an A/B on story score before it ships.

**Michael:** Do item 5 (LLM translation) first. Then: "All new development must be done in Subscribed, not Storied."

**LEAD:** Recorded as D594 (also in CLAUDE.md). `subscribed` is 1,485 commits behind storied, so LOCAL-558 (forward-merge, Kiro) runs first; it was dispatched 2026-10-02 12:00. LOCAL-559 (LLM translation behind TRANSLATION_ENGINE=aws|llm, default aws; fixes the silent 5,000-char truncation; starts from the deployed gcs-tr1 translation fix, which is on no branch line) is written and held until 558 is merged. Meanwhile the Windows session deployed storied v3 to Preview (b801d46, USER_STOPS on, Beta unchanged).

**LEAD (LOCAL-558/559 progress, 2026-10-02):** LOCAL-558 approved and merged: subscribed @ 632f673 contains storied. Tour tests 153 = 153; subscribed tests have the same 5 pre-existing LOCAL-142 failures as baseline; flutter analyze 34 = 34 errors. LOCAL-559 (LLM translation) reviewed: structure right, cost $0.0039 per 10-stop tour vs AWS ≈ $0.27, but the llm engine left "Directions:" lines in English (spoken to the listener). Bounced as LOCAL-559R: a prompt fix, a deterministic untranslated-line check with AWS fallback, and parallel stops (102 s → target < 30 s).

**LEAD (2026-10-02, LOCAL-559 approved):** LLM translation merged into subscribed @ 84944d8. Live, tour 301 (10 stops) → ru 28.6 s, $0.0046; → es 28.1 s, $0.0042. No English Directions/Orientation lines remain; the label renders as «Указания:». Kiro's cache-bypass temporarily changed original_tour_id on test rows; LEAD verified against the 16:26Z backup that all 190 pre-existing rows are identical. Engine default is still `aws`; switching the cloud needs a translation-service deploy from subscribed (a shared Beta/Storied service), Michael's call after he judges the Russian.

**Michael:** Side-by-side of old vs new translation for review; and start #3 (checker calls to gpt-4o-mini), verified by checking that stops where the old method found a discrepancy are still caught by the new one.

**LEAD:** Doc "Translation Old vs New": https://claude.ai/code/artifact/3194a1f5-c70f-4336-884a-55322554af3d. Finding: AWS reads best in Russian today; gpt-4o-mini gets place names wrong (Палац Ласкарис, Замок Холм) and leaves "Stop N:" in English, and a prompt fix does not help. gpt-4o (≈ $0.08 per 10 stops vs AWS ≈ $0.27) gets the names right and is arguably best in Spanish, where AWS mixes usted/tú. LLM translation stays switched off. #3 dispatched as LOCAL-560 (Kiro): inventory, then record 8+ real tours with today's models, replay every checker call on gpt-4o-mini, and switch a site only at 100% recall on recorded discrepancies. Found while writing it: TOUR_LLM_MODEL is unset everywhere, so many calls run on gpt-3.5-turbo.

**Michael:** Agrees AWS reads better; objects to the LLM's "orders" («откройте для себя») where AWS writes «вы обнаружите». The price win is huge: can it be corrected?

**LEAD:** Yes, by splitting the work. Experiments on stops 1–3: a guidebook-style instruction fixes the orders even on gpt-4o-mini; names need gpt-4o (one names-only call per tour, ≈ $0.006 for 3 stops, with Wikidata winning where it has a label); fixed structure (Stop N, Orientation, Directions labels) must be done by code, because mini breaks those rules. Estimated ≈ $0.02 per language per 10-stop tour vs AWS ≈ $0.27. Dispatched as LOCAL-561, with a blind X/Y/Z review (AWS / new design / gpt-4o-only) for Michael to judge.

**LEAD (2026-10-02, LOCAL-561 approved):** Guidebook translation merged into subscribed @ 47fe031, switch still off. Measured on 10-stop tour 301: guidebook design $0.016 per language (54–67 s); gpt-4o-only $0.08; AWS $0.276. LEAD corrected the blind review: the harness had shown AWS with an English "Stop N:" and Russian address labels the app never shows. Michael to judge X/Y/Z in TRANSLATION_REVIEW_LOCAL-561.md.

**LEAD (2026-10-02, LOCAL-560):** The Kiro session hit the 60-min limit after recording 8 real tours (every OpenAI call captured; no keys in the files; no DB rows written). LEAD committed the recordings and tour texts to LOCAL-560-checker-model @ fdbc779 and logged a TIMEOUT. Continued as LOCAL-560B: analysis and gpt-4o-mini replay from the recordings, committing after each step. Byproduct from the recordings: Boston Sail Loft cost $0.14 OpenAI + $0.42 Gemini grounding (12 searches) = $0.56 for a 1-of-4-stop tour.

**LEAD (2026-10-02, #3 result, LOCAL-560 merged into subscribed @ d92bbb7):** The $0.28 → $0.12 estimate was wrong. The verdict checkers were already on gpt-4o-mini, and switching the 3.5-turbo extractors saves 62% of only about $0.004 per tour. The real OpenAI cost is the gpt-4o stop WRITER ($2.17 of $3.29 across 8 tours). By Michael's rule two checkers were held on their old model (restaurant identity: recall 50%; geography scope: 75%); every miss is adjudicated in SUBMISSION_LOCAL-560.md. LEAD replayed all 10 intent calls: gpt-4o-mini differs on 9/10, mostly better (Buttermilk named; Palais Lascaris and the Newton church recognised as venues; 3.5 returned nothing usable for the church). Naming the venue switches on museum D1 verification, which is why Palais Lascaris cost more: more checking, not noise. New finding: the cost ledger undercounts OpenAI about 3x ($0.14 logged vs $0.41 on the wire); LOCAL-562 dispatched to fix it.

**LEAD (2026-10-02, LOCAL-562 merged, subscribed @ f5bc845):** The cost ledger now counts every OpenAI call at one choke point (per-tour scope, safe under parallel tours); a live Chart House run shows ledger = wire, $0.1437. Correction to LEAD's own figure: the undercount was about 1.8x ($0.145 logged vs $0.260 on the wire), not 3x; the $0.41 belonged to a different run. LEAD error: when advancing subscribed after LOCAL-560, the local branch was pointed at storied, so Kiro built LOCAL-562 on f192ff6. Merging origin/subscribed in was clean; local branch fixed. Recorded per-tour costs for 4-stop requests: OpenAI $0.14–0.41, Gemini $0.42–0.53, Polly metered separately (≈ $0.13 for 4 stops neural) → ≈ $0.70–1.10 per 4-stop tour.

**Michael:** Approved the Serper test, but Gemini spend is capped at $15 (account balance).

**LEAD:** The cap costs no coverage. The Gemini noise-floor runs double as the Gemini arm of the A/B (10 tours × 2 runs ≈ $9.60), and the Serper arm, the replay and the blind read spend no Gemini. LOCAL-563 (Gemini baseline) dispatched, with a hard stop before any tour once grounded requests reach $14. LEAD built SERPER_AB_ANSWER_KEY.json from primary pages: Sail Loft (since 1984, no reservations), Buttermilk (Santos, Feb 2017), Chart House (Gardiner Building 1763, Hancock's counting house), Sycamore (OPEN, chef David Punch), La Marée (closed 30 Sep 2020), Logan (Maj. Gen. Edward Lawrence Logan; opened 8 Sep 1923; renamed 1954). Correction: "Governor Channing Cox, Mayor Curley" (used as a Preview acceptance check) are NOT in Wikipedia's Logan history; they came from our own generated tour and are now "unverified", not "must".

**Michael:** Do not rely solely on Wikipedia. Audioura's value is looking through many, sometimes unknown, sources, then verifying them against high-reliability sources (Wikipedia, museums, museum associations, history).

**LEAD:** Agreed, and applied. (1) Logan: the Boston Globe (2023) confirms Mayor Curley at the 8 Sep 1923 dedication, a fact Wikipedia lacks, so it moves to "must". Governor Cox: still no source in three places, so it stays unverified. (2) The answer key now carries reliability tiers (high / medium / discovery / never-alone) and the principle. (3) Step 2 will score DISCOVERY: per engine, the count of facts that come from a less-known source AND are corroborated by a high-tier source, the number of distinct domains, and the share that is Wikipedia-only. A Serper that only re-finds Wikipedia should lose even if it matches Gemini on recall.

**LEAD (2026-10-02, LOCAL-563):** Gemini baseline complete: 10 tours × 2 runs, total Gemini $5.50 (157 grounded requests), well under the $14 cap, so a re-run budget remains. The Kiro session hit the 60-min limit at pair 10; LEAD committed the last pair (3af65a5). Analysis only (summary, noise floor, question list, facts by source tier, answer-key check) dispatched as LOCAL-563B; it makes no API calls.

**LEAD (2026-10-02, LOCAL-563B baseline analysis):** Noise floor: practicals are stable (reservation/price Δ 0); gates are noisy (specificity removals up to 8 per tour); named people up to ±4. Gemini rarely rests on Wikipedia alone (max 7%, Lascaris) but leans heavily on discovery-tier sites (up to 96%, Riviera). The answer key caught real production bugs: Chart House declared "permanently closed" in BOTH runs from a Weehawken NJ closure; Buttermilk & Bourbon "closed" in one run because "BarLola has closed; Buttermilk & Bourbon to replace it". Named-stop protection kept both stops, but a plain restaurant tour would silently drop them. "Governor Channing Cox" appears in both Logan runs with no source behind it. Dispatched LOCAL-564 (closure binding: place + subject; storied release fix) and LOCAL-565 (Serper step 2: replay the 157 questions, score recall / invented facts / discovery / answer key; zero Gemini spend; OpenAI cap $8).

**Michael (2026-10-02 night):** Billing screenshots (Cloud Billing, 30 days; AI Studio usage).

**LEAD:** The $20 Gemini top-up and the $41.87 spike on Sep 23 were our own runaway: 113 Kiro sessions started that day after the PAUSE was cleared on a 35-task backlog. D587 (allowlist) fixed it that evening; Gemini returned 402 PaymentRequired once the prepaid balance ran out. Since then the account runs at ≈ $1/day. No piggy-backing. Real per-tour cost, 4-stop tour (today's runs, accurate ledger): OpenAI $0.18–0.29, Gemini ≈ $0.04 (billing: $0.82 for 20 runs), Polly ≈ $0.15 neural → ≈ $0.40; a museum tour with D1 verification (Lascaris) ≈ $1.05. Reminder for 2026-10-03 added to PENDING_REMINDERS.md (budget alert). Break: PAUSE set, RELEASED empty, nothing armed; LOCAL-564 finished and awaits review tomorrow.

**Michael (2026-10-03 night):** Approves the new translation (all languages); drop Gemini optimisation; asks for ideas on the gpt-4o writer cost and on voices ("standard is bad"); wants a task running while he sleeps.

**LEAD:** D595 recorded; Subscribed translation-service set to TRANSLATION_ENGINE=llm (02aa094); the app's 8 languages are covered. Overnight, dispatched with hard caps: LOCAL-566 (where the writer money goes: input vs output, cacheable prompt prefix, duplicated passages, regenerations, museum D1; one content-neutral saving measured; proposals ranked) and LOCAL-567 (blind voice sample pack in every engine reachable with existing keys plus Kokoro, with verified prices, on the Desktop). PAUSE lifted for these two only. LOCAL-564 (closure fix) awaits LEAD review in the morning.

### 2026-10-03 — overnight (Storied_Tours)
**Michael:** "You also need to monitor this computer (mac mini) memory: it fills up and then everything breaks… for now you need constantly to monitor free memory and clean when needed."
**LEAD:** The breakage is disk, not RAM: swap (6.8 GB) lives on the 228 GB data volume. Added `.continuous_dev/disk_guard.sh` to the 5-minute launchd tick: logs free GB + swap; below 20 GB it removes only regenerable data (Xcode DerivedData, old iOS DeviceSupport, pip/brew/VS Code caches, Docker build cache + dangling images); below 8 GB after cleaning it writes DISK LOW to ALERTS.md. First run 17 → 25 GB free. The real fix is the SSD: move Docker data and worktrees onto it.
**Overnight outcome:** closure binding fixed (LOCAL-564 ×3, LOCAL-570 ×2, merged both branches); writer cost = retries, and keep-best/early-stop (LOCAL-569) merged behind flags (D596–D598); blind packs on the Desktop (voices, stories). OpenAI credits ran out 03:20; Michael topped up 16:5x.

### 2026-10-03 18:1x — tracks per machine; cost/time; is local Subscribed testing ready?
**Michael:** Windows Laptop Claude works Storied only (Beta frozen, rare fixes); Storied updates GCloud and gets ready for a test; a pass makes Storied Stable and Subscribed Preview. Subscribed will change a lot (thoughts tomorrow) and runs locally, not on GCloud. Storied fixes go to Windows Claude as ClickUp tasks in the Storied space. (1) Average biking and museum tour, before vs after the optimisation, time and money? (2) Am I ready to test Subscribed locally on the Mac Mini against GCloud Storied?
**LEAD:** Rule recorded in CLAUDE.md (dd929f4). First ClickUp deploy task: wdvrdayrdp (storied @ 5fda8bc: LOCAL-572 Wikidata-per-process bug + LOCAL-564/570 closures; needs pycountry).
(1) Nothing has changed cost by default yet — every saving is behind a switch awaiting Michael's blind reads. Today: biking 4-stop ≈ $0.38 (OpenAI $0.19–0.20 + Gemini ≈ $0.04 + Polly ≈ $0.15), 5.5–6.2 min; museum 4-stop ≈ $0.38 typical (Our Lady, 3.8–5.2 min) and ≈ $1.05–1.15 story-poor (Palais, ≈10 min). Measured options (n=1, 3 stops, Gemini off): museum early-stop −33% OpenAI; gpt-4.1 −26% across 4 tours; time barely moves (±10%). Kokoro voice is the biggest biking lever (−$0.15 of ≈$0.38). No biking tour was measured with options.
(2) Not yet. Local :5000/:5002 runs storied; Subscribed's options are off by default; the app's port is fixed at 5002, so a phone test of Subscribed means rebuilding the local stack from `subscribed` with the switches on (reversible).
