# Kill-Switch Testing Procedure (Option A: Manual Message Publishing)

**Date:** June 2026  
**Purpose:** Test the billing kill-switch without spending $300  
**Cost:** Free (uses test Pub/Sub messages only)

---

## Overview

This procedure tests the entire kill-switch system end-to-end:
1. Kiro deploys the kill-switch Cloud Run function
2. Sir Michael publishes a test message to the `billing-killswitch` Pub/Sub topic
3. The kill-switch function receives the message and responds (shuts down/throttles services)
4. We verify the function worked correctly

**No actual billing alerts needed — we simulate them with a test message.**

---

## Prerequisites

Before testing:
- ✅ Pub/Sub topic `billing-killswitch` exists
- ✅ Budget with alerts configured
- ⏳ Kiro has deployed the kill-switch Cloud Run function
- ⏳ Kiro has provided the kill-switch service account email
- ⏳ Sir Michael has granted Cloud Run Admin role to the service account (Step 4)

---

## Step 1: Kiro — Deploy Kill-Switch Function

**Owner:** Kiro Amazon-Q  
**Status:** Pending

**Deliverables:**
- [ ] Kill-switch Cloud Run function deployed
- [ ] Function subscribes to `projects/audiotours-migration/topics/billing-killswitch`
- [ ] Function responds to messages by stopping/throttling Cloud Run services
- [ ] Service account email provided to Sir Michael (e.g., `billing-killswitch-sa@audiotours-migration.iam.gserviceaccount.com`)

**Message from Sir Michael to Kiro:**
> "Kill-switch infrastructure ready. Topic: `projects/audiotours-migration/topics/billing-killswitch`. Deploy your function and provide the service account email for IAM permission grant."

---

## Step 2: Sir Michael — Grant IAM Permission

**Owner:** Sir Michael  
**Status:** Pending (after Kiro provides service account)

**Action:**
1. Go to: https://console.cloud.google.com/iam-admin/iam?project=audiotours-migration
2. Click **Grant Access**
3. **New principal:** Paste kill-switch service account email
4. **Role:** Search for and select `Cloud Run Admin`
5. Click **Save**

**Verification:**
- [ ] Service account has Cloud Run Admin role

---

## Step 3: Sir Michael — Publish Test Message

**Owner:** Sir Michael  
**Status:** Ready after Step 2

**Action:** Open a terminal and run:

```bash
gcloud pubsub topics publish projects/audiotours-migration/topics/billing-killswitch \
  --message '{"budgetDisplayName":"Audioura Monthly Spend","alertThresholdExceeded":90}'
```

**Expected output:**
```
messageIds:
- '123456789'
```

The message ID confirms the test message was published.

---

## Step 4: Sir Michael — Verify Kill-Switch Response

**Owner:** Sir Michael  
**Status:** Immediately after Step 3

**Check the kill-switch function logs:**

```bash
gcloud functions logs read billing-killswitch --limit 50
```

**Look for:**
- ✅ Function received the message
- ✅ Function identified the alert threshold (90%)
- ✅ Function executed kill-switch action (e.g., "Stopping service X")
- ✅ No errors in logs

**Example expected log output:**
```
2026-06-19 14:32:15.123 billing-killswitch  INFO: Received billing alert: threshold=90%
2026-06-19 14:32:16.456 billing-killswitch  INFO: Stopping service: tour-generation-modernized
2026-06-19 14:32:17.789 billing-killswitch  INFO: Kill-switch executed successfully
```

---

## Step 5: Sir Michael — Verify Service was Actually Stopped

**Owner:** Sir Michael  
**Status:** After Step 4

**Option A: Check Cloud Run console**
1. Go to: https://console.cloud.google.com/run?project=audiotours-migration
2. Verify the service that should have been stopped is now in "Stopped" state (or has 0 instances)

**Option B: Query via gcloud**
```bash
gcloud run services list --project audiotours-migration
```

Look for the stopped service in the output.

**Expected result:**
- ✅ Service was actually shut down by the kill-switch function
- ✅ No errors in Cloud Run logs

---

## Summary: Test Complete ✅

If all steps pass, the kill-switch system is working correctly:

| Component | Status |
|---|---|
| Pub/Sub topic | ✅ Delivers messages |
| Kill-switch function | ✅ Receives and processes messages |
| Cloud Run integration | ✅ Function can stop services |
| Logging | ✅ All actions logged and visible |

---

## Troubleshooting

**If Step 3 fails (message won't publish):**
- Check Pub/Sub API is enabled: `gcloud services list --enabled | grep pubsub`
- Check topic exists: `gcloud pubsub topics list`

**If Step 4 shows no logs:**
- Check function is deployed: `gcloud functions list --project audiotours-migration`
- Check function has Cloud Pub/Sub trigger: `gcloud functions describe billing-killswitch --gen2`

**If Step 5 shows service still running:**
- Check kill-switch function has Cloud Run Admin role (Step 2)
- Check kill-switch function logs for errors
- Verify the service name in the function's code matches actual service names

---

## Next Steps After Testing

Once testing passes:
1. ✅ Kill-switch is production-ready
2. ✅ Real billing alerts will now trigger automated shutdown
3. ✅ No manual spend cap needed — system is self-protecting at 50%, 90%, and 100%

**Cost protection:** Budget now has an automatic guardian.
