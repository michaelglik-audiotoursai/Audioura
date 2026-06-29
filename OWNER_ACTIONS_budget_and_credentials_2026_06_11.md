# Owner Actions — Spend Backstop + Credential-Storage Decision (2026-06-11)

For Sir Michael. Two items that need you, not the agents.
**Part 1:** how to build the GCP spend backstop (budget + Pub/Sub), and how big the budget should be.
**Part 2:** session-token vs AES-at-rest/KMS for the stored newspaper logins — current standard, trade-offs, recommendation.

Project: `audiotours-migration` · Region: `us-central1`.

---

# Part 1 — Spend Backstop

## How the pieces fit (and one important design choice)

A GCP **budget does not cap spend** — by itself it only emails you when costs cross a threshold, and the alert can lag **~20–30 minutes** after the money is already spent. To actually *stop* spend you need three parts wired together:

```
Budget (threshold) ──publishes──▶ Pub/Sub topic ──triggers──▶ Cloud Function ──acts──▶ stops cost services
```

**Design choice — surgical kill, not nuclear.** There are two things the function can do when it fires:

- **(A) Set `--max-instances=0` on the cost-bearing Cloud Run services** (orchestrator, generators, translation, news). This freezes new tour/news/translation work but **leaves Cloud SQL, the gateway, and your data running**. Recovery = set the limits back. **This is the one to use.** It matches Kiro's plan.
- **(B) Disable billing on the whole project** (unlink the billing account). This is the "nuclear option" — it shuts down **everything, including the database**, and recovery is messier with some risk to running services. Only worth it as a last-resort second layer.

Recommendation: ship **(A)** as the backstop. Optionally add **(B)** at a higher threshold (e.g. 150%) as a final catch. The `max-instances` caps Kiro already set (orchestrator=10, others=5) bound the *burn rate* in the meantime, so even during the alert lag the damage is limited.

## Your part vs. Kiro's part

| Step | Who | Where |
|------|-----|-------|
| Enable Cloud Billing API + Cloud Run Admin API | You | Console — APIs & Services |
| Create the Pub/Sub topic | You | Console — Pub/Sub |
| Create the budget + attach the topic | You | Console — Billing |
| Grant the function's service account permissions | You | Console — IAM |
| Write + deploy the Cloud Function (the logic) | **Kiro** | code/deploy |

You do the Console wiring; Kiro writes the function that reads the budget message and calls the Cloud Run Admin API. Hand Kiro the **topic name** once you've made it.

## Step-by-step (Console)

**1. Enable APIs.** Console → *APIs & Services → Enable APIs* → enable **Cloud Billing API** and **Cloud Run Admin API** (and **Cloud Functions / Cloud Run** if not already on).

**2. Create the Pub/Sub topic.** Console → *Pub/Sub → Topics → Create topic*. Name it `billing-killswitch`. Leave defaults (no schema). Create.

**3. Create the budget and connect the topic.** Console → *Billing → Budgets & alerts → Create budget*.
   - **Scope:** This billing account → narrow **Projects** to `audiotours-migration` (so the budget tracks only this project). Optionally scope to specific services later.
   - **Amount:** set the monthly amount (see sizing below).
   - **Thresholds:** set alert rules at **50%, 90%, 100%** of the budget (add a **150%** line too if you'll also use the nuclear option). "Actual" spend (not forecasted) for the kill action.
   - **Manage notifications:** check **"Connect a Pub/Sub topic to this budget"** and select `billing-killswitch`. (Leave the email recipients on too — you still want the email.)
   - Save.

**4. Permissions for the function (after Kiro tells you its service account).** Console → *IAM* → grant that service account:
   - **Cloud Run Admin** (`roles/run.admin`) — to set max-instances on the services. Plus **Service Account User** on the runtime SA if required.
   - Only if you also wire the nuclear option: **Project Billing Manager** (`roles/billing.projectManager`) — to disable billing.

**5. Test.** Kiro can publish a fake budget message to the topic (`costAmount > budgetAmount`) and confirm the function flips the services to `max-instances=0`, then restores them. Don't wait for a real overspend to find out it works.

> `gcloud` equivalents exist for every step if you prefer the CLI, but the Console path above is the simplest for a one-time setup.

## How big should the budget be?

The budget is a **safety ceiling, not a spending target.** Size it well above normal usage (so it never false-trips during a legitimate interest-test bump) but low enough that a runaway is capped at *hundreds*, not *thousands*, of dollars.

**Your cost shape (interest-test launch):**

- **Fixed / always-on:** Cloud SQL Postgres (small instance) ≈ **$30–50/mo**; Cloud Run scales to zero so idle ≈ $0; logging/Secret Manager a few dollars. Call baseline **~$40–60/mo**.
- **Variable:** ~**$1.10 per tour** (OpenAI text + Polly neural TTS + compute), plus extra Polly/Translate per translated language. With a free tier of 1 tour/day and a handful of testers, **real expected spend is well under ~$100/mo.**
- **Worst case (the reason the backstop exists):** if quota is bypassed before attestation is enforced, the `max-instances=5` generator cap still allows on the order of ~100 tours/hour ≈ **~$100+/hour** of runaway. That's what you're capping.

**Recommendation: set the monthly budget to $300**, with alerts at 50% ($150) / 90% ($270) / 100% ($300 → kill-switch fires).
- Why $300: it's ~3–5× your realistic monthly spend, so normal testing and modest growth never trip it; yet a runaway is stopped after a few hundred dollars rather than running into the thousands overnight. Round and easy to reason about.
- **Tighter option ($150)** if you want minimum risk during a pure interest test and don't expect much legitimate volume — just watch for false trips if testing ramps.
- **Looser option ($500)** once attestation enforcement + quotas are proven in production and you want fewer interruptions.

Revisit the number after the first month of real data. The kill-switch is the protection; the dollar figure just sets where it triggers.

---

# Part 2 — Credential Storage: Session-Token vs. AES-at-Rest/KMS

**The problem being solved:** Audioura stores users' **third-party newspaper/subscription logins** so the server can log in and fetch articles. Today those sit in `user_subscription_credentials.decrypted_username` / `decrypted_password` as **plaintext at rest** in Postgres. A database dump or backup leak exposes real user passwords — the highest-liability data you hold. Both options below fix that; they fix it differently.

## Option A — Encrypt-at-rest with KMS (envelope encryption)

You keep storing the password, but encrypted. The standard pattern is **envelope encryption**: generate a random 256-bit data key (DEK), encrypt the username/password locally with **AES-256-GCM**, then encrypt the DEK with a master key held in **Cloud KMS** (or AWS KMS). Store the ciphertext + the KMS-wrapped DEK. Decrypt on demand, server-side, only when you need to log in.

**Pluses**
- You still hold the actual password, so you can log into sites that offer **no API/OAuth** (most newspapers).
- Small migration from today's model — encrypt the existing columns, decrypt at point of use.
- A stolen DB/backup is useless without KMS access; keys are rotatable and access is audit-logged.
- Well-understood, widely deployed, satisfies "encrypted at rest" for review.

**Minuses**
- You remain **custodian of the user's real password** — the underlying liability doesn't go away; you've just locked the drawer.
- The app server can still decrypt to plaintext in memory, so a fully compromised server + KMS access still leaks.
- Key management/rotation overhead; you must also stop writing `decrypted_*` to logs.

## Option B — Session-token model (don't store the password)

Authenticate once, then persist a **session token / cookie / OAuth token** that grants access — ideally short-lived with a refresh token — instead of the password. Use the provider's OAuth where it exists.

**Pluses**
- You **never persist the user's actual password** → far smaller breach blast radius and liability.
- Tokens are **scoped, expirable, and revocable**; a leaked token is bounded and can be killed.
- Matches the modern standard: *don't store credentials you don't own.*

**Minuses**
- Only works if the third party supports **OAuth or reusable sessions** — many subscription sites **don't**, which forces you back toward password storage.
- Sessions expire → you must build re-auth/refresh flows (more complexity).
- You often still need the password at **initial** login, so you must handle it transiently and never persist it.

## What's the current industry standard?

Two-tier, and they aren't mutually exclusive:

1. **Preferred:** don't store third-party passwords at all — use **OAuth / token exchange** (the session-token model). This is the default best practice whenever the provider supports it.
2. **When you must hold credentials** (provider has no OAuth — the common newspaper case): store them with **envelope encryption backed by a managed KMS** (AES-256-GCM + KMS-wrapped DEK), with tight IAM, audit logging, and key rotation. **Plaintext or app-managed static keys are not acceptable.**

## Recommendation for Audioura

Most newspaper/subscription sites don't offer OAuth, so a pure session-token model isn't realistic across the board. Practical path:

- **Now (unblocks launch):** migrate the `decrypted_*` columns from plaintext to **envelope encryption with Cloud KMS** (Option A). This removes the worst risk quickly and is the smallest change. Stop logging decrypted values at the same time.
- **Next (where the site allows it):** move to **storing the session cookie/token** rather than the password (Option B), and encrypt those tokens with KMS too. Use the password only transiently to re-establish a session, never persisted.
- **End state = hybrid:** rarely-needed encrypted password as fallback + encrypted session tokens for day-to-day access. Minimize how often the real password is touched.

In short: **KMS envelope encryption is the must-do for launch; session tokens are the better long-term target for sites that support them.** Decide the launch scope (KMS-encrypt now), and Kiro can implement it; the longer-term token work can follow.

---

## Sources

- [Disable billing usage with notifications — Google Cloud](https://docs.cloud.google.com/billing/docs/how-to/disable-billing-with-notifications)
- [Set up programmatic budget notifications — Google Cloud](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications)
- [Create, edit, or delete budgets and budget alerts — Google Cloud](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Set maximum instances for services — Cloud Run](https://docs.cloud.google.com/run/docs/configuring/max-instances)
- [Cloud SQL pricing — Google Cloud](https://cloud.google.com/sql/pricing)
- [OpenAI API pricing](https://openai.com/api/pricing/)
- [Amazon Polly pricing](https://aws.amazon.com/polly/pricing/)
- [Securing credentials with AWS Secrets Manager and KMS (envelope encryption pattern)](https://dev.to/truc3651/securing-your-credentials-with-aws-secrets-manager-and-kms-a-complete-guide-4m54)
