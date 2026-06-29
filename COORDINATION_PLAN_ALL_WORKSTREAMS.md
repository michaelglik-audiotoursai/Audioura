# Audioura Phase E: Coordination Plan for All Three Amazon-Q Workstreams

**Date:** June 4, 2026  
**Scope:** Kiro (backend/GCloud), Mobile-AQ (Flutter), Sir Michael (domain/email)  
**Hub:** Cloudflare (free DNS + email forwarding + Pages)

---

## The Three Parallel Workstreams at a Glance

| Workstream | Owner | Critical Tasks | Blocker | Timeline |
|---|---|---|---|---|
| **Backend (K1–K9)** | Kiro | K1 (REST status endpoint), K2–K3 (hardening), K6–K8 (deploy) | None | 2–3 weeks |
| **Mobile App (M1–M4)** | Mobile-AQ | M1 (orchestrator routing), M4 (build/test) | K1 for M2 | Parallel with Kiro |
| **Domain/Email (S1–S2, D1–D3)** | Sir Michael (you) | D1 (Cloudflare DNS), D2 (email), S2 (Cloud SQL lockdown) | K8 for S2 | 1–2 days (upfront), then wait-and-watch |

---

## YOUR ACTION ITEMS (Sir Michael) — In Order

### **PHASE 1: IMMEDIATE (Today — ~2 hours)**

#### **Action 1.1: Verify GCP secrets are correct**

Kiro is deploying services that depend on:
- `openai-api-key` ✅ (already in Secret Manager)
- `aws-access-key-id` ✅ (already in Secret Manager)
- `aws-secret-access-key` ✅ (already in Secret Manager)
- `r2-access-key-id` ⏳ (just re-added without newlines)
- `r2-secret-access-key` ⏳ (just re-added without newlines)

**Your step:** After you add the R2 secrets via the Google Cloud Console (the one Kiro asked you to do), confirm:
```bash
gcloud secrets list
# You should see all 5 secrets with "Latest version" timestamps
```

**Expected output:** All 5 secrets listed. No errors.

**What this unblocks:** Kiro can deploy services immediately (K1 and on).

---

#### **Action 1.2: Move audioura.com DNS to Cloudflare (the free hub)**

**What:** Point your domain registrar (Network Solutions) to Cloudflare's nameservers. This gives you free DNS, email forwarding, and Pages hosting in one place.

**Steps:**

1. **Create a Cloudflare account** (free)
   - Go to: https://dash.cloudflare.com/sign-up
   - Email: `glikfamily@gmail.com`
   - Create account

2. **Add your domain to Cloudflare**
   - In Cloudflare dashboard: **Websites → Add a site**
   - Enter: `audioura.com`
   - Select **Free plan**
   - Cloudflare will show you two nameservers (e.g., `ns1.cloudflare.com`, `ns2.cloudflare.com`)
   - **Copy these nameserver addresses**

3. **Update Network Solutions (your registrar)**
   - Go to: Network Solutions → Your domains → `audioura.com` → Manage → Nameservers
   - Replace Network Solutions' nameservers with Cloudflare's two nameservers
   - Save
   - **Wait 5–15 minutes** for DNS to propagate (you'll see a green checkmark in Cloudflare when it's live)

4. **Verify DNS is live**
   - In Cloudflare dashboard: You should see a green checkmark: "Nameserver change detected"
   - Or run: `nslookup audioura.com` (should resolve)

**Estimated time:** 10–15 minutes (plus propagation wait)

**Billing:** Free (Cloudflare's free plan covers DNS)

**What this unblocks:** Email routing (D2) + Pages hosting (D3) + API domain routing (D1, when Kiro is ready)

---

### **PHASE 2: EMAIL SETUP (Today or tomorrow — ~30 min)**

#### **Action 2.1: Choose email solution**

**Option A: Google Workspace (~$7/month) — RECOMMENDED**
- Full send+receive for both `michael.glik@audioura.com` and `info@audioura.com`
- One $7/month seat; `info@` is a free alias
- Clean, professional, no SMTP relay juggling

**Option B: Cloudflare Email Routing + free SMTP relay ($0/month)**
- Forwarding only (receive → `audio.tours.ai@gmail.com`)
- For send-as, use Brevo free SMTP relay
- More moving parts, but free

**Your choice for this plan:** Option A (Google Workspace). We'll detail Option B at the end if you change your mind.

---

#### **Action 2.2: Set up Google Workspace (if choosing Option A)**

1. **Sign up for Google Workspace**
   - Go to: https://workspace.google.com
   - Click **Get Started** → select **Business Starter** ($7/user/month, annual)
   - Sign in with your Google account (`glikfamily@gmail.com`)

2. **Verify your domain (`audioura.com`)**
   - Google will ask you to add a TXT record to prove you own the domain
   - In Cloudflare dashboard: **DNS → Records → Add record**
     - **Type:** TXT
     - **Name:** `audioura.com` (or `@`)
     - **Content:** (Google provides this — copy it exactly)
     - **Save**
   - Back in Google Workspace setup: Click **Verify** (wait a few minutes for DNS to update)

3. **Create your Workspace user**
   - **First name:** Michael
   - **Last name:** Glik
   - **Email:** `michael.glik@audioura.com`
   - **Temporary password:** (Google generates one; you'll change it)

4. **Add `info@` as an alias**
   - In Google Workspace admin: **Directory → Users**
   - Click your user (`michael.glik@`)
   - **User information → Email aliases → Add alias**
   - **Alias:** `info@audioura.com`
   - **Save**

5. **Set up Send-as in Gmail**
   - (Optional) If you want to use your regular Gmail (`audio.tours.ai@`) to send/receive as `michael.glik@` and `info@`:
   - In Gmail settings: **Accounts → Send mail as** → **Add another email**
   - Add `michael.glik@audioura.com` → verify via Google Workspace
   - Then add `info@audioura.com` (same verification)
   - Now replies from Gmail show `From: michael.glik@` or `From: info@` (your choice)

**Estimated time:** 20–30 minutes (plus DNS propagation)

**Billing:** ~$7/month for one Workspace user (annual commitment ~$84/year)

**Result:** Both `michael.glik@audioura.com` and `info@audioura.com` are fully functional for send + receive.

---

### **PHASE 3: API DOMAIN (D1) — Wait for Kiro, then one step**

#### **Action 3.1: Add `api.audioura.com` → Cloud Run gateway (happens when Kiro is ready)**

**When:** After Kiro completes **K9** and gives you the Cloud Run gateway URL.

**The URL Kiro will give you:** Either:
- A short Cloud Run URL: `https://tour-orchestrator-abc123xyz.us-central1.run.app`
- Or (if he uses Cloud Run domain mapping): He'll tell you the IP/target

**Your step:**
1. In Cloudflare dashboard: **DNS → Records → Add record**
   - **Type:** CNAME (or A if it's an IP)
   - **Name:** `api`
   - **Target:** (Kiro's Cloud Run URL or IP)
   - **Proxy status:** Proxied (orange cloud) — this gives you free TLS
   - **Save**

2. **Verify it works:**
   ```bash
   curl https://api.audioura.com/health
   # Should return 200 + { "status": "healthy" } (or Kiro's gateway health response)
   ```

**Estimated time:** 2 minutes

**Billing:** Free (Cloudflare proxying)

**What this enables:** Mobile app can use `https://api.audioura.com` instead of the Cloud Run URL.

---

### **PHASE 4: MARKETING PAGE (D3) — Optional, anytime**

#### **Action 4.1: Host a simple static page at `www.audioura.com` (optional)**

**When:** Anytime before you submit to App Store / Play Store. Not blocking for testing.

**What:** A one-page site with:
- App blurb
- "Download on the App Store" badge
- "Get it on Google Play" badge

**How:** You pick one of these free hosts (all include free TLS):
- **Cloudflare Pages** (easiest if you're already in Cloudflare)
- **GitHub Pages**
- **Netlify**
- **Vercel**

**Simple example (using Cloudflare Pages):**

1. Create a file `index.html`:
   ```html
   <!DOCTYPE html>
   <html>
   <head>
     <title>Audioura</title>
     <style>
       body { font-family: -apple-system, sans-serif; text-align: center; padding: 40px; }
       img { max-width: 150px; margin: 20px; }
     </style>
   </head>
   <body>
     <h1>Audioura</h1>
     <p>Explore tours by walking around.</p>
     
     <p>
       <a href="https://apps.apple.com/...">
         <img src="https://tools.applemediaservices.com/api/badges/download-on-the-app-store/black/en-us" alt="App Store">
       </a>
       <a href="https://play.google.com/store/apps/details?id=...">
         <img src="https://play.google.com/intl/en_us/badges/static/images/badges/en_badge_web_generic.png" alt="Play Store">
       </a>
     </p>
   </body>
   </html>
   ```
   (Get the badge images from Apple App Store marketing guidelines + Google Play badge generator)

2. In Cloudflare Pages: **Create → Connect to Git** (or **Upload directly**)
   - Upload your `index.html`
   - Cloudflare will give you a URL like `audioura-123.pages.dev`

3. In Cloudflare DNS: **Add a CNAME record**
   - **Name:** `www`
   - **Target:** `audioura-123.pages.dev`
   - **Proxied:** Yes
   - **Save**

4. Verify: `https://www.audioura.com` loads your page

**Estimated time:** 15–30 minutes (depending on store badge fetching)

**Billing:** Free

---

### **PHASE 5: CLOUD SQL LOCKDOWN (S2) — Wait for Kiro's K8**

#### **Action 5.1: Remove the public `0.0.0.0/0` from Cloud SQL**

**When:** After Kiro confirms he's completed **K8** (native Cloud Run ↔ Cloud SQL connector).

**Your step:**

1. Go to: https://console.cloud.google.com/sql/instances?project=audiotours-migration

2. Click **audioura-db** instance

3. **Connections → Networking**

4. Find the authorized network `0.0.0.0/0` (the one that allows public access)

5. **Delete it** (click the trash icon)

6. **Save**

**Result:** Cloud SQL is no longer publicly accessible. Services reach it only via the Cloud Run connector (zero public exposure).

**Estimated time:** 2 minutes

**Billing:** Free (the native connector doesn't charge)

---

## Parallel Workstream Timeline

### **What Kiro is doing (in parallel with you)**

```
Day 1-2:        K1 (REST status endpoint) + K2-K3 (hardening)
  ↓
  └─→ Unblocks Mobile-AQ to do M1 (routing) immediately
  
Day 2-3:        K4 (secrets) + K5 (cleanup) + K6-K7 (deploy news)
  └─→ Unblocks S1 (you approve deploys)

Day 3-4:        K8 (Cloud SQL lockdown)
  └─→ Unblocks S2 (you remove 0.0.0.0/0)

Day 4-5:        K9 (gateway domain config)
  └─→ Unblocks D1 (you point api.audioura.com)
```

### **What Mobile-AQ is doing (in parallel)**

```
Day 1-2:        M1 (route generation through orchestrator) — can start NOW
  ↓
  └─→ Unblocks testing: "Generate a tour on cellular"

Day 3:          M4 (build/test on Android)
  ↓
  └─→ Mobile app ready for cloud testing

Day 4+:         M2 (switch status writes to REST) — waits for K1 contract
  └─→ Then M3 (cleanup)
```

---

## Your Timeline (Sir Michael)

| Time | Action | Blocker | Next |
|---|---|---|---|
| **Today** | 1.1: Verify secrets; 1.2: Move DNS to Cloudflare | None | Kiro starts deploying |
| **Today/Tomorrow** | 2.1–2.2: Set up Google Workspace email | None | Ready for contact requests |
| **Wait (2–3 weeks)** | Kiro does K1–K9 | — | — |
| **When Kiro says K8 done** | 5.1: Remove Cloud SQL `0.0.0.0/0` | K8 completion | DB fully locked down |
| **When Kiro says K9 done** | 3.1: Add `api.audioura.com` → Cloud Run | K9 completion | Mobile app can use `https://api.audioura.com` |
| **Anytime (optional)** | 4.1: Create marketing page + `www.audioura.com` | None | Ready for App Store / Play Store submissions |

---

## Exact Coordinates for the Cloudflare + Google Workspace Setup

### **Cloudflare Setup Checklist**

- [ ] Sign up for Cloudflare (free): https://dash.cloudflare.com/sign-up
- [ ] Add `audioura.com` to Cloudflare
- [ ] Copy Cloudflare nameservers
- [ ] Go to Network Solutions → Update nameservers → Save
- [ ] Wait for DNS propagation (5–15 min)
- [ ] Verify green checkmark in Cloudflare dashboard

### **Google Workspace Setup Checklist**

- [ ] Sign up for Google Workspace Business Starter (~$7/mo): https://workspace.google.com
- [ ] Verify `audioura.com` via TXT record (add in Cloudflare DNS)
- [ ] Create user `michael.glik@audioura.com`
- [ ] Add alias `info@audioura.com` to the same user
- [ ] (Optional) Set up Send-as in Gmail

### **DNS Records You'll Create in Cloudflare**

```
Type    Name    Target/Content              Proxied
────────────────────────────────────────────────────
CNAME   api     tour-orchestrator-*.run.app  Proxied (add after K9)
CNAME   www     audioura-*.pages.dev         Proxied (add after D3)
TXT     @       (Google Workspace verify)    Not proxied
MX      @       (Google Workspace MX)        Not proxied
```

---

## What to Tell Each Amazon-Q Now

### **Tell Kiro:**
> "GCP secrets verified. Cloudflare DNS live. Ready for K1 through K9. When K8 is done, I'll lock down Cloud SQL. When K9 is done, give me the gateway target so I can point api.audioura.com."

### **Tell Mobile-AQ:**
> "Kiro is starting. You can begin M1 immediately (no blocker). Test URL will be the Cloud Run URL; full `https://api.audioura.com` when I've set up DNS (after Kiro's K9)."

### **Tell iOS (once iOS team is ready):**
> "Build the same commit of `services-migration` that Mobile uses after M1. No Dart changes from iOS — shared `lib/` only. Run parity smoke tests (local + cloud generation off-WiFi)."

---

## Billing Summary

| Item | Cost | Note |
|---|---|---|
| Cloudflare | Free | DNS, Email Routing (forward), Pages, TLS |
| Google Workspace (1 user) | ~$7/month (~$84/year annual) | Covers both `michael.glik@` and `info@` aliases |
| audioura.com domain | ~$10–15/year | Network Solutions (keep existing or transfer) |
| Google Cloud (Kiro's services) | ~$50–100/month | Cloud Run + Cloud SQL (test volume) |
| **Total** | ~**$150–200/month** | Reasonable for a small app backend |

---

## FAQ

**Q: Do I need to transfer audioura.com from Network Solutions to Cloudflare?**
A: No. Keep it at Network Solutions (or any registrar). Just point the nameservers to Cloudflare. You own the domain; Cloudflare manages DNS.

**Q: Can I use Cloudflare Email Routing instead of Google Workspace?**
A: Yes, if you only care about receiving email at `info@audioura.com` forwarded to Gmail. For sending/replying *as* `info@audioura.com`, you'd need to set up Brevo's free SMTP relay in Gmail. It's free but more fiddly. Google Workspace is cleaner.

**Q: When can I test the full cloud flow?**
A: After M1 lands (mobile routes generation through the gateway) and Kiro's K1 + gateway are live, you can test by: (1) setting Server IP in the app to Kiro's Cloud Run URL, (2) going off WiFi (cellular), (3) generating a tour. Expect it to work once K2–K3 hardening is done.

**Q: What if something goes wrong with DNS?**
A: DNS propagates slowly (5–15 min). If `https://api.audioura.com` doesn't resolve immediately: wait, then run `nslookup api.audioura.com` to check. If it still doesn't resolve after 30 min, check that the CNAME record in Cloudflare is correct.

---

## Next Steps

1. ✅ **Right now:** Verify GCP secrets → Move DNS to Cloudflare (Actions 1.1–1.2)
2. ✅ **Today/tomorrow:** Set up Google Workspace email (Action 2.1–2.2)
3. ⏳ **Wait:** Kiro deploys services (K1–K9)
4. ⏳ **When K8 done:** Lock down Cloud SQL (Action 5.1)
5. ⏳ **When K9 done:** Add `api.audioura.com` DNS record (Action 3.1)
6. 📅 **Anytime:** Create marketing page (Action 4.1)

---

**Status:** Ready to coordinate. Tell Kiro and Mobile-AQ to start; you handle the domain/email setup today.
