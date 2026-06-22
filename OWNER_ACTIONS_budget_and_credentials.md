# Owner Actions: Budget & Kill-Switch Setup

**Date:** June 2026  
**Project:** Audioura (audiotours-migration GCP project)  
**Purpose:** Create spending backstop and unblock Kiro's kill-switch function

---

## Overview

The kill-switch function (deployed by Kiro) needs:
1. A **Pub/Sub topic** to receive billing alerts
2. A **budget with alerts** that publishes to that topic when spend hits thresholds
3. **IAM permissions** so the kill-switch service account can shut down Cloud Run services

This runbook covers all owner-level GCP Console actions.

---

## Step 1: Enable Required APIs ✅ COMPLETED

**Why:** Cloud Billing API is needed to create budgets; Cloud Run Admin API lets the kill-switch function manage Cloud Run services.

✅ Cloud Billing API enabled  
✅ Cloud Run Admin API enabled

**Cost:** Free (APIs themselves don't charge; the *services* they manage do)

---

## Step 2: Create Pub/Sub Topic ✅ COMPLETED

**Why:** This topic receives billing alerts and triggers the kill-switch function.

**Result:** Topic `billing-killswitch` created  
**Full name:** `projects/audiotours-migration/topics/billing-killswitch`  
**Cost:** Free (Pub/Sub charges per message; alert messages are rare)

---

## Step 3: Create Budget with Alerts ✅ COMPLETED

**Why:** Defines a ~$300/mo spending limit and publishes alerts at 50%, 90%, and 100%.

**Results:**
- Budget name: `Audioura Monthly Spend`
- Amount: $300/month
- Alert thresholds: 50% ($150), 90% ($270), 100% ($300)
- Email notifications: ✅ enabled (michael.glik@gmail.com)
- Pub/Sub topic connected: ✅ `projects/audiotours-migration/topics/billing-killswitch`

**Cost:** Free (budgets don't charge)

---

## Step 4: Grant IAM Permissions (PENDING — after Kiro deploys)

**When:** After Kiro deploys the kill-switch Cloud Run function and gives you the service account name.

**Example service account:** `billing-killswitch-sa@audiotours-migration.iam.gserviceaccount.com`

1. Go to: https://console.cloud.google.com/iam-admin/iam?project=audiotours-migration
2. Click **Grant Access**
3. **New principals:** Paste the kill-switch service account email
4. **Assign roles:**
   - `Cloud Run Admin` (allows stopping/updating Cloud Run services)
5. Click **Save**

**Result:** Kill-switch function can now manage Cloud Run services

---

## Step 5: Communicate with Kiro ✅ READY

**Message to send to Kiro:**
> "Billing kill-switch infrastructure is ready:
> - Cloud Billing API + Cloud Run Admin API enabled
> - Pub/Sub topic created: `projects/audiotours-migration/topics/billing-killswitch`
> - Budget set to $300/mo with alerts at 50/90/100%
>
> Wire your kill-switch function to subscribe to this topic. Once deployed, provide the service account email so I can grant it Cloud Run Admin role."

---

## Verification Checklist

- [x] Cloud Billing API enabled
- [x] Cloud Run Admin API enabled
- [x] Pub/Sub topic `billing-killswitch` created
- [x] Budget `Audioura Monthly Spend` at $300/mo
- [x] Alert thresholds at 50%, 90%, 100% connected to topic
- [x] Email notifications configured: michael.glik@gmail.com
- [ ] Kill-switch function deployed (Kiro)
- [ ] Kill-switch service account granted Cloud Run Admin role

---

## Costs

| Item | Cost | Notes |
|---|---|---|
| Cloud Billing API | Free | API access only; services charge separately |
| Pub/Sub topic | ~$0.01–0.10/mo | Alert messages are rare; minimal cost |
| Budget | Free | Budgets themselves don't charge |
| **Total** | **~$0.10/mo** | Negligible |

---

## Rollback / Cleanup

If you need to remove:
1. **Budget:** Billing → Budgets → Delete
2. **Pub/Sub topic:** Pub/Sub → Topics → Delete
3. **API:** APIs & Services → Disable

No data loss; services can be re-enabled anytime.
