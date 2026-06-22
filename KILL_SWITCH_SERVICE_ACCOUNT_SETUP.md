# Kill-Switch: Dedicated Service Account Setup & Testing

**Date:** June 2026  
**Purpose:** Create isolated, limited service account for kill-switch function (principle of least privilege)  
**Owner:** Sir Michael (SA creation + IAM) + Kiro (redeploy + test)

---

## Why Dedicated Service Account?

**Current (dangerous):** Kill-switch runs as Cloud Run's default service account → has broad permissions.

**Better (this doc):** Kill-switch runs as `killswitch-sa@audiotours-migration.iam.gserviceaccount.com` with **only** `roles/run.developer` (update services, set max-instances) → if the function is compromised, the attacker can only control Cloud Run services, not other GCP resources.

**Principle:** Least privilege isolation.

---

## Step 1: Create Dedicated Service Account (Sir Michael)

**Console:** https://console.cloud.google.com/iam-admin/serviceaccounts?project=audiotours-migration

### Action 1.1: Create the SA

1. Go to **IAM & Admin → Service Accounts**
2. Click **+ Create Service Account**
3. **Service account name:** `killswitch-sa`
4. **Service account ID:** (auto-fills as `killswitch-sa@audiotours-migration.iam.gserviceaccount.com`)
5. **Description:** `Service account for billing kill-switch function. Limited to Cloud Run developer role only.`
6. Click **Create and Continue**
7. **Grant this service account access to project:**
   - Click **+ Grant Role**
   - **Role:** Search for `roles/run.developer` (NOT `roles/run.admin`)
   - Click to select it
   - Click **Continue**
8. Click **Done**

**Result:** Service account `killswitch-sa@audiotours-migration.iam.gserviceaccount.com` created with `roles/run.developer`

---

### Action 1.2: Verify Role is Correct

1. Go to **IAM & Admin → IAM**
2. Look for `killswitch-sa@audiotours-migration.iam.gserviceaccount.com` in the members list
3. Verify it has role: **Cloud Run Developer** (not Admin)

✅ **Done:** Isolated service account is ready.

---

## Step 2: Tell Kiro to Redeploy with New Service Account (Message to Kiro)

> "Service account `killswitch-sa@audiotours-migration.iam.gserviceaccount.com` is ready. 
> 
> Please redeploy the kill-switch function with this service account:
> 
> ```bash
> gcloud functions deploy billing-killswitch \
>   --gen2 \
>   --project=audiotours-migration \
>   --region=us-central1 \
>   --service-account=killswitch-sa@audiotours-migration.iam.gserviceaccount.com \
>   [... other flags ...]
> ```
> 
> After redeploy, it will run as `killswitch-sa` with `roles/run.developer` permissions (limited to Cloud Run operations)."

---

## Step 3: Sir Michael — Verify Role After Redeploy

After Kiro confirms redeploy is done:

1. Go to **Cloud Functions:** https://console.cloud.google.com/functions?project=audiotours-migration
2. Click on **billing-killswitch** function
3. Go to **Runtime settings** or **Permissions**
4. Verify **Service account:** Shows `killswitch-sa@audiotours-migration.iam.gserviceaccount.com`
5. Go to **IAM & Admin → IAM**
6. Confirm `killswitch-sa` has role: **Cloud Run Developer** (not Admin)

✅ **Verification complete.** Function is running with limited permissions.

---

## Step 4: Test the Kill-Switch (Kiro Executes)

**Purpose:** Confirm the kill-switch function actually stops services when it receives a billing alert.

**Message to Kiro:**

> "Please run the kill-switch function test:
> 
> 1. **Publish a fake billing alert** to the Pub/Sub topic:
> ```bash
> gcloud pubsub topics publish projects/audiotours-migration/topics/billing-killswitch \
>   --message '{\"budgetDisplayName\":\"Audioura Monthly Spend\",\"alertThresholdExceeded\":100}'
> ```
>
> 2. **Watch the function logs:**
> ```bash
> gcloud functions logs read billing-killswitch --gen2 --limit 50
> ```
> Look for: Function received message, executed kill-switch action, no errors.
>
> 3. **Verify the function set max-instances=0 on services:**
> ```bash
> gcloud run services list --project=audiotours-migration
> ```
> Check if any service shows: Instances = 0 or \"Scaled to zero\"
>
> 4. **Restore the services** (undo the kill-switch):
> ```bash
> gcloud run services update [SERVICE_NAME] \
>   --project=audiotours-migration \
>   --max-instances=100  # or your normal limit
> ```
> Repeat for each service that was scaled to zero.
>
> 5. **Report back:**
> - Did the function execute successfully?
> - Did it actually set max-instances=0 on the targeted services?
> - Any errors in the logs?
>
> A kill-switch that hasn't been fired is not a verified kill-switch. This test confirms it works."

---

## Step 5: Sir Michael — Close Out the Kill-Switch Task

Once Kiro reports the test results:

**If test PASSED:**
- ✅ Service account isolated with limited role
- ✅ Function deployed with correct SA
- ✅ Function executed successfully on test message
- ✅ Services were actually scaled to zero
- ✅ Kill-switch is production-ready

**Update ClickUp task status:** `Complete`

**If test FAILED:**
- Debug the function logs
- Verify role was granted (roles/run.developer allows max-instances updates)
- Retry the test

---

## Summary: What Gets Deployed

| Component | Details |
|---|---|
| **Service Account** | `killswitch-sa@audiotours-migration.iam.gserviceaccount.com` |
| **Role** | `roles/run.developer` (NOT full admin) |
| **What it can do** | Update Cloud Run services, set max-instances, manage traffic |
| **What it can't do** | Delete services, modify GCP IAM, access databases, change secrets |
| **Function** | `billing-killswitch` (Cloud Function Gen2) |
| **Trigger** | Pub/Sub topic `projects/audiotours-migration/topics/billing-killswitch` |
| **Test** | Fake budget alert message → function scales services to zero → manually restore |

---

## Files

- `OWNER_ACTIONS_budget_and_credentials.md` — Budget + Pub/Sub setup
- `GCP_ENABLE_APIS_FOR_KILL_SWITCH.md` — API enablement
- `KILL_SWITCH_TESTING_PROCEDURE.md` — Manual message publishing test
- `KILL_SWITCH_SERVICE_ACCOUNT_SETUP.md` — This file (SA + least-privilege role)

---

## Related ClickUp Tasks

- **Kiro:** Deploy kill-switch Cloud Run function (with new SA)
- **Sir Michael:** Test kill-switch (verify role + run fake message test)
- **Sir Michael:** Kill-switch task — complete (after test passes)
