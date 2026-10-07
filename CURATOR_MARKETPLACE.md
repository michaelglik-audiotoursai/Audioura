# Curator marketplace — design of record (D624, 2026-10-07, LEAD; Michael may overturn any number)

Answers Michael's Q1–Q4 of 2026-10-07. Nothing here is built yet. The money-handling steps in §1
and §4 need Michael's own accounts (outward-facing).

## 1. Enabling purchases (packs now, tours later)
**Apple**, done by Michael in App Store Connect as glikfamily@gmail.com:
1. **Agreements, Tax, and Banking:** accept the **Paid Apps Agreement**, add the bank account, and
   complete the tax forms. No in-app purchase works until it is "Active".
2. Enroll in the **App Store Small Business Program** (commission 15% instead of 30% while revenue
   is under $1M a year).
3. Create two **Consumable** in-app purchases, with ids that match the app exactly:
   - `audioura.pack.l3`: "$10 Pack", $9.99 (or the nearest price point);
   - `audioura.round.l4`: "Curator", $24.99.
   Each needs a display name, a description and a review screenshot.
4. Create a **Sandbox tester** (a fresh email address) to test buying without paying.
5. Submit the in-app purchases **together with an app build** for review.
Server: `IAP_VERIFY_MODE=apple`, `APPLE_IAP_ENVIRONMENT=Sandbox` locally, and `Production` at
release (already built in LOCAL-598/598B).

**Google** (later; Android buttons are hidden): a Play Console payments profile, then the same
two products as "managed products", and server verification through the Play Developer API.

## 2. Displaying a tour for sale
- A Curator marks one of their own tours **For sale** and picks a **price tier** (§3).
- Buyers see it in search, "near me" and shared links, with a **price badge**. **Stop 1 is a free
  preview** (the opening section and the first stop), and the other stops are locked until
  bought.
- **Buy** uses an in-app purchase. Apple requires its own payment system for digital content used
  in the app (App Review Guideline 3.1.1), so curator sales also go through Apple and Google.
- Per-tour products can't be created on the fly, so the app ships a fixed set of **consumable
  price-tier products** (`audioura.tour.t1` … `t5`). The server records which tour a given
  verified transaction unlocked, for which device. A replayed transaction never unlocks twice
  (the same mechanism as LOCAL-598).
- A bought tour stays the buyer's permanently. If the curator later edits it, the buyer gets the
  edit (LOCAL-606 replaces in place).

## 3. Price tiers and what the curator receives (shown on the "Sell this tour" screen)
Michael, 2026-10-07: **Audioura takes 10%.** The store takes its fee first (15% under the Small
Business Program; 30% if not enrolled), and Audioura's 10% is taken from what remains.

| Tier | Buyer pays | Store fee (15%) | Remaining | Audioura (10% of remaining) | **Curator gets** |
|---|---|---|---|---|---|
| T1 | $1.99 | $0.30 | $1.69 | $0.17 | **$1.52** |
| T2 | $2.99 | $0.45 | $2.54 | $0.25 | **$2.29** |
| T3 | $4.99 | $0.75 | $4.24 | $0.42 | **$3.82** |
| T4 | $7.99 | $1.20 | $6.79 | $0.68 | **$6.11** |
| T5 | $9.99 | $1.50 | $8.49 | $0.85 | **$7.64** |

The curator receives ≈ 76.5% of the list price (≈ 63% if the store fee is 30%).

The screen says: "You receive about $X per sale. Sales taxes and VAT, where the store collects
them, come off before the split, so the amount can be a little lower in some countries." The split
(10%) and the tiers are rows in a table, not code. Michael sets them.

## 4. Paying curators
- Apple and Google pay **Audioura**, monthly, net of their fee (Apple pays within about 45 days of
  the end of each fiscal month).
- Audioura pays curators through **Stripe Connect (Express)**, set up by Michael. Stripe collects
  the curator's identity, bank details and tax forms (for example US 1099s), so Audioura stores
  **only a Stripe account id**. This keeps the anonymous-device rule for everyone except
  curators who choose to be paid.
- **Schedule:** monthly, after the store's payment for that month has arrived. Minimum payout
  $25 (the rest rolls over). A 30-day hold covers store refunds and chargebacks.
- **In-app curator ledger:** sales per tour, pending vs paid, and the next payout date.

## Build order once Michael confirms the numbers
- **LOCAL-6xx a:** the for-sale flag, tiers table, free Stop 1 preview, locked stops, and the
  tier-product purchase that unlocks one tour.
- **LOCAL-6xx b:** the curator ledger and payout calculation, with Stripe left as a stub until
  Michael's account exists.
- **Michael:** the Paid Apps Agreement, tier products, Stripe account and Small Business Program.
