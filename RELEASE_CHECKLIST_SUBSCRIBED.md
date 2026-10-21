# Subscribed release plan: Local → Preview → first public release
_LEAD keeps this current. Created 2026-10-15 as a gate checklist; rewritten 2026-10-21 as an ordered plan (D687, corrected the
same day by Michael → D687 addendum 1, D688). Conversation log: `SUBSCRIBED_COMMUNICATION_01.MD`._

**The goal.** Release Audioura to the public and start earning **as soon as possible**. The release is **Subscribed**: today it is
local only, on the Mac Mini. It goes to Preview on GCloud, then to the first public release on both stores, with real payments.

**Fixed rules (Michael, 2026-10-21):**
- **Only Subscribed goes to Production.** It caps cost: Free seats are limited to 100, and every other plan is paid. Storied and Beta
  have no user limit and no payment plans, so a public launch of either could bankrupt Audioura LLC. They stay on testing tracks.
- **No Nov 1 deadline.** Our builds already target the accepted SDK level (API 36), and Play Console shows no warning (D687 add. 1).
- **A paid tour is paid for each download** (D660 stands, D688). Deleting a tour means buying it again, like a lost bag. A lost or
  replaced phone restores its Listen page with the recovery code, at no charge (D660 addendum).
- **Michael leaves for Vietnam ~Oct 28.** Anything that needs him at a store console or a phone at home goes before that date.

---

## PHASE 0: now (Oct 21–27), all in parallel

**Michael**
| # | what | time | unblocks |
|---|---|---|---|
| M1 | **Apple products** (wdvrdayuf3): 11 products + the $1 pass `audioura.pass.usd1`, tours **Consumable**. Also create **one Sandbox tester** (App Store Connect → Users and Access → Sandbox → +, a new email such as glikfamily+sandbox1@gmail.com) | 30 min | Apple test purchases (L4) |
| M2 | **Google payments:** check the payments-profile verification in Play Console (W-9 review, bank test deposit). Create the Play service account (wdvrdayzyj). Add your Gmail as a license tester (Settings → License testing) | 15 min | Google products + test purchases |
| M3 | **Register the DMCA agent** at copyright.gov (≈$6, ≈15 min): Audioura LLC, 44 Sharpe Rd, Newton Centre, MA 02459, info@audioura.com | 15 min | publishing the Terms |
| M4 | **Review Subscribed + Communities**, step by step: `SUBSCRIBED_REVIEW_PLAN.md` | 60–75 min | approving Preview |
| M5 | **Legal final read**: LEAD posts the final texts with your per-download rule applied → you say "publish" | 30 min | Preview (D661) |

**LEAD (Kiro tasks + LEAD review)**
| # | what | why |
|---|---|---|
| L1 | **Legal finals (B):** the joined drafts from Oct 20 (Terms 5, Privacy 5, Guide 5, Organiser 2, Refunds, Content Policy) rewritten for pay-per-download, then into `legal/*.md` and the website pages, ready to publish | M5 |
| L2 | **App Store-required code** (lawyer items 2, 9, 10): block a member / organiser in communities; a first-run notice that tours are informational, not navigation, with the matching Terms text; "history of crime" Mature vs instructions Not-listed, in the rater | Apple rejects without blocking (Guideline 1.2) |
| L3 | **Same-name collision across tracks** (wdvrdaz108): proven fixed on `subscribed` with a red test | before GCloud |
| L4 | **Real store path, locally:** when M1 is done, set the local stack to verify real Apple sandbox purchases (`IAP_VERIFY_MODE=apple`, the verifier exists); limit price pickers to products that exist (`in_picker`); then sandbox-test every product type on the iPhone | revenue path proven |
| L5 | **GCloud move package** for the Windows session: migrations 022–042 with row counts, secrets by name, user-api + plans (daily limits on GCloud), Polly, the rater with its key, a budget alert first | Preview |
| L6 | App Store age-rating answers and review notes (demo community code + a TEST tour) | submission |

## PHASE 1: Subscribed → Preview on GCloud
**Gate:** policies published (M5 + M3) and Michael says "Subscribed approved for Preview" (M4).
1. LEAD publishes the legal pages; Michael pastes the Privacy + Terms URLs into both stores.
2. GCloud_Storied deploys the L5 package; LEAD and GCloud_Storied run a smoke test on GCloud (a tour is generated, rated before listing, downloaded and played; plan limits are enforced).
3. Official builds: iOS from the Mac → TestFlight; Android from Windows → Play **internal/closed testing**. Before that upload, the Play App Signing SHA-256 goes into `assetlinks.json`.
4. Testers invited.

## PHASE 2: real money reaches the bank
**Test-purchase matrix:** every product type on both stores:
- each plan (Introduction → $10 Pack → Curator; renew; lapse);
- a community pass of each length;
- a paid tour (buy, download, delete, buy again);
- the lost-phone restore with the recovery code;
- a refund that removes access.

| store | test money (no bank) | real money (bank proven) |
|---|---|---|
| Apple | Sandbox tester on any dev/TestFlight build, as soon as M1 + L4 are done | only after the App Store release: Michael buys the $1 pass himself on day 1, then checks Payments and Financial Reports |
| Google | license tester, as soon as the products exist | **before launch:** on the internal-testing track, an account that is NOT a license tester pays with a real card. That is a real charge, visible in the Play payments report; then refund it |

## PHASE 3: first public release
1. Preview feedback is closed → Subscribed becomes Stable.
2. App Store submission (L6) and Play Production, both with Subscribed. The Free plan's seat cap (100) and the daily paid limit are verified on GCloud first.
3. Store URLs go into `website/t/index.html`; testers become users.
4. Later: Kokoro voice on GCloud (cost first); payouts to guides/organisers before the first one is owed.

---

## Done
- ✅ Keys rotated (wdvrdaxaw9, 2026-10-20).
- ✅ Pixel-7 quick test of the official Storied app passed (Michael, 2026-10-21): download, generate, news articles on GCloud.
- ✅ Content Policy approved (D656 add. 2) and true in code locally (LOCAL-724/724B @ 46301f3d).
- ✅ Organiser Terms, Terms and Refunds approved on Oct 20. Their re-download sentences now follow D688 (L1).
- ✅ Listener-only daily limit (LOCAL-723); duplicate-stop and link-text fixes (LOCAL-721/722).
