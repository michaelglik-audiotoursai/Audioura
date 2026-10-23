# SUBMISSION — LOCAL-740 (Review fixes: links without https://, paid-tour delete warning, recovery code that survives a lost phone)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-740-review-small-fixes`
**Base:** `subscribed` @ `58782f8f` (verified `git merge-base --is-ancestor 58782f8f HEAD` → 0)
**code_sha:** _(the tip commit of this branch — see `git log -1` on `LOCAL-740-review-small-fixes`)_

Addresses Michael's review (2026-10-22), items **A3b**, **B3**, **B5**, **B5b**.

---

## A3b — Links without a scheme are accepted

**Was:** Generate → Newsletter refused `en.wikipedia.org/wiki/Boston` with "Invalid URL" because the code gated on `!url.startsWith('http')`.

**Now:** One shared, unit-tested helper `normalizeUrlInput` (in `lib/utils/url_input.dart`) trims the input and prepends `https://` when there is no scheme; `http://` / `https://` links pass through unchanged. The Newsletter field on Generate (`_processNewsletterUrl` in `tour_generator_screen.dart`) normalizes each line through it, then checks shape with `looksLikeUrl` (host with a dot) instead of the old scheme gate.

- The Newsletter field is the only listener-typed URL input; the other `newsletter_url` path (`home_screen._processNewsletterWithUrl`) consumes server-stored URLs, and the About "cloud base URL" is a dev/debug config — both left unchanged.

---

## B3 — Paid-tour delete warning now appears on every delete path

### Root cause
The delete-confirmation copy (`DeleteTourPrompt`, LOCAL-693) was correct and already wired into the single-delete path, keyed on `DeleteTourPrompt.isPaidTour(tour)` (`is_paid == true || price_tier > 0`). The warning never showed because the **saved record was stamped `is_paid: false`** at download time.

`TourDownloadService._stampPaidSnapshot` decided paid-ness with **`is_paid == true` only** — it ignored `price_tier`. Map-delivery rows carry the price inline as `price_tier` / `price_label`, and a tour unlocked via the pay-per-download / `tour_unlocks` path reaches the save without an explicit `is_paid:true`. So Michael's $5 "Massachusetts politics" walking tour was saved `is_paid:false`, and the delete path then treated it as free → no warning. (Re-download still asked to pay, because the server, not the local flag, gates that — which is why the two disagreed.)

### Fix
1. `_stampPaidSnapshot` now mirrors the rest of the app: **`isPaid = is_paid == true || price_tier > 0`**, and additionally **consults `TourPricingService.unlockState(serverId)`** as a fallback — if the server says the tour is paid (even when the inline row didn't), it stamps it paid and follows the server's `unlocked` flag. This also correctly reveals a `tour_unlocks`-purchased tour whose inline row lacked the flag. (`lib/services/tour_download_service.dart`)
2. **"Delete all"** now carries the warning too. Added pure, unit-tested `DeleteTourPrompt.decideDeleteAll(tours)` + `paidCount(tours)`; when any tour in the batch is paid, the body reads: _"Delete all N tours? This cannot be undone. M of them are paid tours — downloading them again will require another purchase."_ Wired into `_deleteAllTours` (`my_tours_screen.dart`). A free-only batch keeps the plain "Delete All Tours".
3. **Single delete** already rendered `DeleteTourPrompt.decide(..., isPaid: isPaidTour(tour))` — unchanged; it now works because the record is stamped correctly.
4. **Swipe delete:** there is no `Dismissible`/swipe-to-delete widget anywhere in the app, so the two delete entry points on Listen are single-delete and delete-all; both now warn.

Free tours keep today's behaviour on every path.

---

## B5 — Recovery code screen tells you to keep it off the phone, and helps you do so

In `lib/screens/recovery_code_screen.dart`:
- **Off-phone text** (always visible): _"Keep this code outside this phone, for example email it to yourself. If this phone is lost, stolen or broken, the code restores your Listen page on a new phone: your tours, paid tours and articles."_
- **Buttons:** Copy (existing) + **Email it to myself** + **Share**.
  - "Email it to myself" opens the device mail composer via `url_launcher` with a `mailto:` built by `recoveryEmailUri(code)` (`lib/utils/recovery_code.dart`): subject **"My Audioura recovery code"**, the code in the body. The app only *opens* the composer — it never sends mail itself, so the code never leaves the phone through us.
  - "Share" hands the code to the OS share sheet via `share_plus`.
- **Under "New code":** _"Replaces your code. The old code stops working. Use it if someone else saw your code."_

---

## B5b — Offer the recovery code after the first download

- New pure decision module `lib/utils/first_download_offer.dart` (`decideFirstDownloadOffer`): show **once** on the first finished download (any tour or article); if the listener taps **"Later"**, ask **again after the 3rd download**, then **never**; and **never on the same day** as the first-purchase offer.
- `maybeOfferRecoveryCodeAfterDownload(context)` in `recovery_code_screen.dart` is the thin SharedPreferences wrapper (keys: `recovery_download_count`, `recovery_download_offer_shown`/`_later`/`_done`, and the shared `recovery_offer_last_day`). The existing first-purchase offer (`maybeOfferRecoveryCode`) now also stamps `recovery_offer_last_day`, so the two coordinate the one-nudge-a-day rule.
- Dialog: **"Save your recovery code"** — _"You'll build up tours and articles in your own language on your Listen page; if your phone is lost, this code brings them back."_ with **[Create my code]** and **[Later]**.
- Wired at download-complete: `home_screen._downloadTour` (tour) and `tour_generator_screen._downloadAndSaveNews` (article; skips the auto-open when it offers, so the two never fight over the navigator). Fully guarded — a storage hiccup never blocks a download.

---

## Tests

New / extended, all green:
- `test/url_input_test.dart` — bare domain, domain + path (the review case), http (unchanged), https (unchanged), spaces, `www.`, non-http scheme, null/blank; plus `looksLikeUrl`.
- `test/delete_tour_prompt_test.dart` — added `decideDeleteAll` (paid-batch warns, free-batch plain, `paidCount`) and a **RED group**: a paid tour (single + delete-all) must carry the re-purchase warning.
- `test/recovery_code_test.dart` — off-phone text; Copy / Email it to myself / Share + New-code explanation (via a `@visibleForTesting` `initialCode` seam); `recoveryEmailUri` / `recoveryShareBody` / subject carry the code (**the email intent carries the code**).
- `test/first_download_offer_test.dart` — once, again-after-3rd-if-Later, then never, done, and same-day rules.

### Red test proof
Temporarily forcing `DeleteTourPrompt.decideDeleteAll` to treat every batch as free (`paid = 0`) turns the two RED-group assertions red (`-2`); reverted cleanly and all pass again. (The widget wording for a paid tour is identical to the single-delete path, which is also asserted red.)

### Baseline
- `flutter analyze` on every touched file: **0 errors** (`url_input.dart`, `first_download_offer.dart`, `recovery_code.dart`, `recovery_code_screen.dart`, `delete_tour_prompt.dart`, `tour_download_service.dart` all clean; the two large screens show only pre-existing info/warning lints, none on the changed lines).
- Full suite: **`+847 -7`** (was `+828 -7` at `58782f8f`). The **7 baseline failures are unchanged** — 6 in `local109_swipe_e2e_test.dart` and 1 in `storied_compat_screens_404_test.dart`, all live-server tests (`SocketException: Connection refused`) needing a running backend; confirmed identical by re-running with my changes stashed.

## Live test
No live simulator run was required for these review fixes (pure logic + widget wording, covered by unit/widget tests). **$0.00 spent.** No server change. No `-p audioura`/`audioura-*` containers touched.

## Files changed
- `lib/utils/url_input.dart` (new)
- `lib/utils/first_download_offer.dart` (new)
- `lib/utils/recovery_code.dart`
- `lib/screens/recovery_code_screen.dart`
- `lib/screens/tour_generator_screen.dart`
- `lib/screens/home_screen.dart`
- `lib/screens/my_tours_screen.dart`
- `lib/services/tour_download_service.dart`
- `lib/widgets/delete_tour_prompt.dart`
- `test/url_input_test.dart` (new), `test/first_download_offer_test.dart` (new)
- `test/delete_tour_prompt_test.dart`, `test/recovery_code_test.dart`

No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
