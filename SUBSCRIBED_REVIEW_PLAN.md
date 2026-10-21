# Subscribed + Communities: Michael's review plan
_LEAD keeps this current. Created 2026-10-21. About 60–75 min, in one sitting or in three parts (A–C, D–F, G–I)._

**Devices.**
- **iPhone = the organiser.**
- **Pixel-4 = the member.**
- Both run the latest Subscribed build, server mode **Local**.
- Leave the Pixel-7 on the official Play build (D676).

**Purchases are TEST PURCHASES on the local stack:** no money moves and no store dialog appears. Real store purchases are a separate test (`RELEASE_CHECKLIST_SUBSCRIBED.md`, Phase 2).

**How to report.** Write remarks as you go, in chat or as a ClickUp comment, one line each. Start each with the step number, e.g. "D3: countdown not shown". LEAD turns each remark into a task within the hour. When something works, a ✅ next to the step number is enough.

---

## Before you start (LEAD, ≈10 min, done before you pick up the phones)
- [ ] Install the latest `subscribed` build on the iPhone (over Wi-Fi) and the Pixel-4. Version shown in About.
- [ ] Point both phones' Local server at the Mac's current address, **192.168.0.187**. The app's default is .136, and the address changed after the Oct 20 reboot.
- [ ] Set plans: iPhone = Curator (can create and sell); Pixel-4 = Free (L2), so the member side sees a normal listener.
- [ ] Prepare one demo community with 3 MP3 episodes hosted outside Audioura, so you can join an existing one as well as create your own.
- [ ] Prepare a server-side "test member" LEAD can add, so the 2-paying-members launch bar can be reached with only two phones.

## A. Your plan (both phones, 5 min)
1. About → Your plan: does it show the plan name, what it allows (tours per day/month, stops), and plain upgrade buttons?
2. Buy the **$10 Pack** (TEST PURCHASE) on the Pixel-4. Does the plan change at once, with the new allowance shown?
3. Open a long news article on the Free plan: do you see the "Shortened to about 1½ pages…" note under the article, and hear the spoken sentence at the end (D670)?

## B. Paid tour, pay-per-download (Pixel-4, 5 min)
1. Find a priced tour on the map. Stop 1 plays free as a preview.
2. Buy & Download (TEST PURCHASE). The whole tour plays offline (airplane mode).
3. Delete it. Does the calm confirmation appear: *"Are you sure you want to delete this paid tour? Downloading it again will require another purchase."*?
4. Try to download it again: it must ask you to buy again.
5. About → Recovery code: is the code shown, with a short explanation that it restores your Listen page on a new phone?

## C. Create a community (iPhone, organiser, 10 min)
1. Generate tab → **Community**. Required fields are marked, and a playful unique name is pre-filled.
2. Pass price: the minimum is **$1**, there is no "Free" option, and the lengths are exactly **day / week / month / year**.
3. Listed vs Private: a Listed community needs a location. Turning on a waiver forces Private.
4. Create. You get an **invite code** with Copy / Share / Email / Regenerate, plus the warning that a community with members cannot be closed.
5. The **countdown** shows on the community page: "168 h left to get 2 paid members — 0 of 2 so far" (D664).
6. Add 2 episodes as MP3 links (title + link; no RSS field). Do they play from the community page?
7. Generate one **community tour** on the Generate tab, members-only. Is it charged to the organiser's allowance and content-rated like any tour?

## D. Join as a member (Pixel-4, 10 min)
1. Type the invite code into the **Home search box**. The community page opens with its passes and **member count**.
2. Buy the **$1 / week** pass (TEST PURCHASE). The community appears in the **Listen** tab beside My tours.
3. Community tours carry a small **community label**; ⋯ → **Origin** shows the community and organiser.
4. Play an episode and the community tour. Are new community tours downloaded for you, or offered with a Download button (D675)?
5. Back on the iPhone: did the member count go to **1 of 2**? Does the countdown still show?
6. Organiser tries to buy a pass to their own community: it must be refused (the organiser is not a member, D665).

## E. Launch, expiry, closing (LEAD edits a few database dates, you look, 10 min)
**The server clock is never changed.** LEAD edits single date fields in the database, only for the test community and the
Pixel-4's test membership. Then LEAD runs the matching server job once by hand: the same jobs the 5-minute tick runs hourly or
daily. Every edit is shown to you before and after.
1. LEAD adds a server-side test member. The community shows **launched** (`communities.launched_at` is stamped) and the countdown disappears for good.
2. LEAD sets the Pixel-4 pass's `community_memberships.expires_at` to one minute ago, then runs the reminders job
   (`/communities/reminders/run`). Expected on the Pixel-4:
   - downloaded audio still plays;
   - a **new** episode is blocked;
   - you are reminded to renew;
   - nothing is charged automatically.
3. On a second, empty test community, LEAD sets `communities.launch_deadline` to one minute ago and runs the launch-window job.
   Its code then says **"This community has closed"**.
4. Below 2 members, the weekly "needs at least 2 members" warning (D666) appears. LEAD shows you where, using the same kind of date edit.
5. Afterwards LEAD restores the original dates, so nothing stays changed.

## F. Organiser steps down (iPhone, 5 min)
1. Step down → offer the community to a member → accept on the Pixel-4. The Pixel-4 becomes organiser.
2. Without a successor, the community stops taking new members and members keep everything (D663).

## G. Safety (both phones, 5 min)
1. ⋯ → **Report** on a tour: a short form, and a confirmation that it was sent. LEAD shows you the row in the server's report list.
2. Settings → **Show 18+ tours**: off by default; turning it on asks you to confirm you are 18+. Mature tours then appear on the map.
3. A tour you edit is rated again before it shows (LEAD confirms on the server).

## H. Share links (iPhone → Pixel-4, 5 min)
1. Share a tour and share a community invite by email. Does the link open the app on the other phone (or the store if the app is absent)?
2. Does the email wording read well, with the member count ("12 members")?

## I. Your verdict (2 min)
- Anything that would embarrass us in front of a tester?
- What must change before Preview, and what can wait for after the public release?
- Say **"Subscribed approved for Preview"** when it is good enough. That, plus the published policies, starts the GCloud move (D661).
