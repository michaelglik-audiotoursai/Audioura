# GCP: Enable APIs for Kill-Switch Function Deployment

**Date:** June 2026  
**Project:** audiotours-migration  
**Purpose:** Enable required APIs so Kiro can deploy the kill-switch Cloud Run function  
**Owner:** Sir Michael (admin-level action only)  
**Estimated time:** 10 minutes (+ 3–5 minutes propagation)

---

## The Problem

Kiro is trying to deploy the kill-switch Cloud Run function but gets:

```
ERROR: (gcloud.functions.deploy) ... SERVICE_DISABLED: 
Service cloudfunctions.googleapis.com is not enabled on project audiotours-migration
```

**Root cause:** Required APIs are not enabled in the GCP project.

**Solution:** Enable 4 APIs in the Console (gcloud is unreliable for this).

---

## APIs to Enable

| API | Service | Status |
|---|---|---|
| Cloud Functions API | `cloudfunctions.googleapis.com` | ❌ Need to enable |
| Cloud Build API | `cloudbuild.googleapis.com` | ❌ Need to enable |
| Eventarc API | `eventarc.googleapis.com` | ❌ Need to enable |
| Artifact Registry API | `artifactregistry.googleapis.com` | ❌ Need to enable |
| Cloud Run Admin API | `run.googleapis.com` | ✅ Already enabled |
| Pub/Sub API | `pubsub.googleapis.com` | ✅ Already enabled |

---

## Step 1: Fastest Method — Use Activation Links (Recommended)

**Why this works:** When an API is disabled, error messages include a direct link to activate it. This is the fastest path.

### Option A: From Kiro's Error Message (Fastest)

If Kiro gets an error like:

```
ERROR: ... SERVICE_DISABLED: cloudfunctions.googleapis.com is not enabled
Visit this URL to enable it:
https://console.cloud.google.com/apis/library/cloudfunctions.googleapis.com?project=audiotours-migration
```

**Action:**
1. Copy that link from Kiro's error
2. Paste into your browser
3. Page shows the Cloud Functions API detail
4. Click the blue **"Enable"** button
5. Wait ~10 seconds for confirmation: **"API is enabled"** ✓

**Repeat for the other 3 APIs:**
- Cloud Build: `https://console.cloud.google.com/apis/library/cloudbuild.googleapis.com?project=audiotours-migration`
- Eventarc: `https://console.cloud.google.com/apis/library/eventarc.googleapis.com?project=audiotours-migration`
- Artifact Registry: `https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com?project=audiotours-migration`

---

### Option B: Manual — If No Error Links

1. Go to: https://console.cloud.google.com/apis/dashboard?project=audiotours-migration
2. Click **"Enable APIs and Services"** (blue button, top)
3. Search box appears → type: `Cloud Functions API`
4. Click on **Cloud Functions API** (first result)
5. Click the blue **"Enable"** button
6. Wait ~10 seconds — page will show **"API is enabled"** with a checkmark ✓
7. **Go back** (back button) to the APIs dashboard
8. **Repeat steps 2–7** for:
   - `Cloud Build API`
   - `Eventarc API`
   - `Artifact Registry API`

---

## Step 2: Wait for Propagation (Critical!)

**Why:** API activation takes 3–5 minutes to propagate across all GCP systems. Immediate retries fail because the system hasn't fully registered the activation yet.

**Action:**
- Enable all 4 APIs
- **Wait 3–5 minutes** (set a timer)
- Do not retry Kiro's deployment until the timer is done

---

## Step 3: Tell Kiro to Retry Deployment

**Message to Kiro:**
> "APIs enabled (Cloud Functions, Cloud Build, Eventarc, Artifact Registry). Retry the deploy once. If it still says SERVICE_DISABLED, wait another 2–3 minutes (propagation lag) and try again."

---

## Step 4: After Kiro's Successful Deployment

Once the kill-switch function deploys successfully, Kiro will provide you with:

**Kill-switch service account email:** (example) `billing-killswitch-sa@audiotours-migration.iam.gserviceaccount.com`

**Your next step:** Grant it Cloud Run Admin role (see `OWNER_ACTIONS_budget_and_credentials.md`, Step 4)

---

## Cost Impact: Cloud Build + Artifact Registry

### Cloud Build Costs

**Pricing:**
- **Free tier:** 120 build-minutes per day (resets daily)
- **Paid:** $0.003 per build-minute after free tier is exhausted

**For Kiro's function:**
- Typical Cloud Function build: 2–5 minutes
- **One-time cost:** ~$0 (within free tier) or ~$0.01–0.015 (if exceeds 120 min/day)
- **Estimate for single deploy:** **Negligible to free**

---

### Artifact Registry Costs

**Pricing:**
- **Free tier:** 50 GB stored per month (includes some data transfer)
- **Paid:** $0.40 per GB-month after 50 GB
- Artifact cleanup policies can auto-delete old images to save costs

**For Kiro's function:**
- Docker image size: ~200–500 MB (typical Cloud Function)
- **Monthly storage cost:** ~$0 (within free tier)
- **Estimate:** **Negligible to free**

---

### Total One-Time Cost for Kill-Switch Function

| Service | One-time cost | Ongoing cost |
|---|---|---|
| Cloud Functions API | Free (API enabling) | ~$0/month (scales to zero when idle) |
| Cloud Build | ~$0–0.02 | ~$0/month (only charges on builds) |
| Artifact Registry | Free (1st deploy) | ~$0/month (within free tier) |
| **Total** | **~$0–0.02** | **~$0/month** |

---

## Summary: Costs Are Negligible ✓

- **One-time:** Free to $0.02 (unlikely to exceed free tiers)
- **Ongoing:** Free (function scales to zero when idle; storage well within free tier)
- **No surprise charges:** Cloud Function itself scales to zero, Cloud Build only runs on deploy, Artifact Registry image is reused (no new builds unless code changes)

**Bottom line:** This is a one-time, essentially free setup. Costs only matter if Kiro redeploys frequently or the function runs 24/7 (which it doesn't — it's event-triggered).

---

## Verification Checklist

After enabling all 4 APIs:

- [ ] Cloud Functions API: Enabled ✓
- [ ] Cloud Build API: Enabled ✓
- [ ] Eventarc API: Enabled ✓
- [ ] Artifact Registry API: Enabled ✓
- [ ] Wait 3–5 minutes
- [ ] Kiro retries deploy → succeeds
- [ ] Kiro provides service account email
- [ ] You grant Cloud Run Admin role (Step 4)

---

## Troubleshooting

**Kiro still gets SERVICE_DISABLED after 5 minutes:**
- Wait another 2–3 minutes (propagation can take up to 10 minutes in rare cases)
- Kiro can try again

**"Enable" button is grayed out or missing:**
- Refresh the page (Ctrl+R / Cmd+R)
- Confirm you're on the right project: "audiotours-migration" (shown at top of console)

**Kiro's deploy still fails with a different error (e.g., "requires PERMISSION_DENIED"):**
- That's the next step (Step 4 in `OWNER_ACTIONS_budget_and_credentials.md`) — grant Cloud Run Admin role to the service account
- Not an API issue; all APIs are enabled

---

## Files

- `OWNER_ACTIONS_budget_and_credentials.md` — Budget + kill-switch IAM (Step 4)
- `KILL_SWITCH_TESTING_PROCEDURE.md` — Testing after deployment
- `GCP_ENABLE_APIS_FOR_KILL_SWITCH.md` — This file
