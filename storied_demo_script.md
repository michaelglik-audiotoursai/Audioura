# Storied Demo Script — Tester Onboarding Walkthrough

Step-by-step guide for testers experiencing the Storied v2.2.0 features for the first time.

---

## Prerequisites

- App installed from TestFlight (iOS) or Play Store closed test (Android)
- Internet connection (tours require API calls)
- ~10 minutes for full walkthrough

---

## Demo Steps

### Step 1: Fresh Launch — Persona Selection (Feature 3)

1. Open the app for the first time (or clear data)
2. You'll see: **"What brings you here?"** with 4 options:
   - 🎨 Art Lover
   - 📚 History Buff
   - 👨‍👩‍👧 Family
   - 🌟 First-Time Visitor
3. Select **"Art Lover"**
4. ✅ Verify: You proceed to the main screen without errors

---

### Step 2: Generate a Tour — Richer Stories (Features 1 & 2)

1. Tap "Generate Tour"
2. Enter: **"Musée National Marc Chagall, Nice"**
3. Select: **Museum tour, 10 stops**
4. Wait for generation (~60 seconds)
5. ✅ Verify:
   - Tour starts with an **Introduction** paragraph (this is the tour hook)
   - Each stop has a distinct narrative tone
   - No two stops use the same opening sentence
   - No clichéd phrases like "vibrant colors and dreamlike imagery"

---

### Step 3: Listen to Tour — Personalization (Feature 3)

1. Play the generated tour
2. ✅ Verify:
   - Art-related details are emphasized (you selected Art Lover)
   - The narrative feels focused on aesthetics and artistic significance
3. (Optional) Change persona to "History Buff" in settings, generate same tour again
4. ✅ Verify: Descriptions now emphasize historical context over artistic analysis

---

### Step 4: Share the Tour (Feature 4)

1. After generation, tap **Share**
2. ✅ Verify: A short link appears (e.g. `audioura.io/tour/abc12345`)
3. Copy the link and open it in a browser
4. ✅ Verify: The full tour text displays in the browser

---

### Step 5: Invite a Friend — Referral (Feature 4)

1. Go to Settings → "Invite a Friend"
2. ✅ Verify: A 6-character referral code is displayed
3. The code is always the same (deterministic per user)
4. (Simulation) If another tester enters your code during their onboarding → attribution is recorded

---

### Step 6: Verify Attestation (Feature 5 — Background)

1. This feature is invisible to users
2. Check service logs (ask developer) for `ATTESTATION LOG:` lines
3. ✅ Verify: Token is logged on each API request
4. ✅ Verify: No request was blocked (log_only mode)

---

## Expected Costs

Each tour generation costs approximately **$0.07–$0.15**. The Storied pipeline adds spine generation and fact sheet lookups on top of the Beta cost.

---

## Known Issues (Expected)

- Perspective layers (Artist's View, etc.) are **NOT** present — these are deferred to New Architecture
- Attestation never blocks — this is intentional for the Aug 1 tester build
- Referral rewards are not yet active — codes are generated but no discount is applied

---

## Reporting Issues

If something doesn't work as described:
1. Note the exact step number
2. Screenshot any error messages
3. Report to Michael with the step number and screenshot
