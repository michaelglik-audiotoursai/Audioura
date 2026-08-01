# Apple IAP Setup — What Michael Needs To Do

Everything in this doc requires your App Store Connect account. Nobody else
can do it. The code is ready and waiting — you just need to create the
products and flip the switch.

---

## Step 1: Create Products in App Store Connect

Go to **App Store Connect → Your App → In-App Purchases**.

Create these three products:

| Product ID | Type | Price | Duration |
|---|---|---|---|
| `com.audioura.ppu_monthly` | Auto-Renewable Subscription | $2.00/month | 1 month |
| `com.audioura.unlimited_monthly` | Auto-Renewable Subscription | $50.00/month | 1 month |
| `com.audioura.credit_topup_10` | Consumable | $9.99 (Apple rounds) | one-time |

For the subscriptions:
- Create a **Subscription Group** called "Audioura Plans"
- Add both subscriptions to it (Apple requires a group)
- Set `com.audioura.unlimited_monthly` as **higher level** so users can upgrade seamlessly

For the consumable:
- No group needed
- Apple rounds $10 to $9.99 — that's fine, we credit the full $10.00 internally

**Approval:** Apple reviews IAPs. Subscriptions need a description of what they unlock.
Use: "Unlimited audio tour generation and premium features" for both.

---

## Step 2: Set Up RevenueCat

1. Go to https://app.revenuecat.com and create an **Audioura** project.
2. Under **App Settings**, add your iOS app:
   - Bundle ID: `com.glikfamily.audioura`
   - Shared Secret: copy from App Store Connect → App → App Information → App-Specific Shared Secret
3. Under **Entitlements**, create one called `premium`
4. Under **Offerings**, create a "default" offering with both subscriptions and the consumable
5. Under **Webhooks**:
   - URL: `https://api.audioura.com/webhooks/revenuecat`
   - Authorization: generate a random secret string (you'll need this later)

---

## Step 3: Create a Sandbox Tester

In App Store Connect → Users and Access → Sandbox:
1. Create a sandbox Apple ID (use a throwaway email)
2. On your iPhone: Settings → App Store → Sandbox Account → sign in with it
3. Sandbox subscriptions renew every 5 minutes instead of monthly — perfect for testing

---

## Step 4: Set Environment Variables

On the server (wherever Docker runs), set these:

```bash
export PAYMENT_PROVIDER=revenuecat
export REVENUECAT_API_KEY=<your RevenueCat REST API key>
export REVENUECAT_WEBHOOK_SECRET=<the random string from Step 2.5>
```

Until you set `PAYMENT_PROVIDER=revenuecat`, the system uses the fake provider.
No real money flows. Switching back is just removing that env var.

---

## Step 5: Flip From Fake to Real

In `docker-compose-subscribed.yml` (or whichever compose file you deploy from), add:

```yaml
environment:
  - PAYMENT_PROVIDER=revenuecat
  - REVENUECAT_API_KEY=your_key_here
  - REVENUECAT_WEBHOOK_SECRET=your_secret_here
```

Then rebuild:
```bash
docker compose -f docker-compose-subscribed.yml up -d --build
```

---

## Step 6: Test the Full Loop

1. Install the app with your sandbox tester signed in
2. Subscribe to PPU ($2/month)
3. Verify: Wallet shows $10.00 balance
4. Generate a tour
5. Verify: balance drops by ~$0.35
6. Check server logs for `[REVENUECAT] Processed RENEWAL`
7. Wait 5 minutes — sandbox auto-renews
8. Verify: no balance change on renewal (D20 — monthly fee doesn't deduct from credits)

---

## What Each Env Var Does

| Variable | What it does | Where to get it |
|---|---|---|
| `PAYMENT_PROVIDER` | `fake` (default) or `revenuecat` — controls which provider is active | Your choice |
| `REVENUECAT_API_KEY` | Authenticates our server-side API calls to RevenueCat | RevenueCat dashboard → API Keys |
| `REVENUECAT_WEBHOOK_SECRET` | Verifies incoming webhooks are really from RevenueCat | You set it in RevenueCat dashboard |

---

## What's Already Done (You Don't Need to Touch)

- ✅ `PaymentProvider` interface (abstract)
- ✅ `FakePaymentProvider` (testing, fully functional)
- ✅ `RevenueCatPaymentProvider` (real implementation, needs your keys)
- ✅ Webhook endpoint at `/webhooks/revenuecat` (idempotent, verified)
- ✅ Wallet ledger with idempotency keys (no double-crediting)
- ✅ Low-balance reminder (never auto-charges — Apple rule)
- ✅ Refund clawback handling (balance can go negative — your ruling)
- ✅ The mobile app's Wallet UI (connected, showing live data)
- ✅ Cost metering per operation type
- ✅ Entitlement gating at the orchestrator

---

## Timeline Estimate

| Step | Time | Blocking? |
|---|---|---|
| Create App Store Connect products | 15 min | Yes — Apple reviews in 24-48h |
| RevenueCat project setup | 20 min | No |
| Sandbox tester | 5 min | No |
| Set env vars + rebuild | 5 min | No |
| End-to-end test with sandbox | 30 min | No |

**Total: ~1 hour of your time**, plus waiting for Apple's IAP review.

---

## If Something Goes Wrong

- **Webhook not arriving:** Check RevenueCat dashboard → Webhooks → Recent deliveries.
  Verify the URL is correct and the secret matches.
- **Purchase fails on device:** Check the sandbox tester is signed in properly.
  Sandbox products only work with sandbox accounts.
- **"Not configured" from webhook:** `PAYMENT_PROVIDER` env var isn't set to `revenuecat`.
- **Balance not changing:** Check the orchestrator logs for `[REVENUECAT]` entries.
  Any error there will say what failed.

To switch back to fake mode at any time:
```bash
unset PAYMENT_PROVIDER
# or set it to "fake"
export PAYMENT_PROVIDER=fake
```
Rebuild containers. All charges stop. Existing subscription state in the DB is preserved.
