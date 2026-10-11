# SUBMISSION — LOCAL-672: Reviews from paid listeners (Verified listener, text reviews, moderation, curator reply)

**Branch:** `LOCAL-672-verified-reviews` (from `subscribed` @ `70a0bf83`, which contains LOCAL-670B)
**Agent:** Mac Mini Kiro
**Builds on:** LOCAL-670/670B `tour_ratings` (1–10, the 7.5 prior, the median after 3 ratings, the ≥2-listened-stops gate — D647, D650).

LEAD's "Reviews #4": buyer ratings marked **"Verified listener"**; an optional **short text review** checked before it shows; the curator may **reply once**; paid tours **rank by rating × number of ratings**. Plus Michael's Amazon-style addendum: **rating distribution bars**, **"helpful" votes**, **review sort/filter**, and a **ranking weight** that favours verified and recent ratings.

Everything here is **additive**. No existing column type/default changed; no row deleted; the LOCAL-670 shown-score rule (D647) is untouched. All new DB objects are created by both an explicit migration and self-healing DDL in the service, so the code works whether or not the migration has run.

---

## What was delivered (mapped to the ticket)

### 1. Verified ratings — `tour_ratings.verified BOOLEAN` (additive)
- A rating is **verified** when its author has a store-verified `purchases` row that unlocked **this** tour. The direct form matches a `product` of `tour_<id>` (the per-tour unlock the pricing tiers will produce).
- **D624 fallback** (per-tour mapping pending Michael's tiers): a non-refunded **level** purchase (`l1`/`l2`/`l3`/`l4…`) **plus** a download/generation record for the tour also counts as verified — a paying user who actually unlocked the tour.
- The flag is computed and written **at rating time** inside `tour_rating_service.record_rating` (self-healing `ADD COLUMN IF NOT EXISTS` first, so the write never fails on an un-migrated DB).
- **Refund un-verifies:** `tour_reviews_service.recompute_verified_for_user()` recomputes every one of a user's ratings; a `raw_status` containing `refund`/`revoke`/`chargeback` no longer qualifies, flipping the rating back to unverified.
- **Paid vs free counting:** on a **paid** tour only verified ratings count toward the **shown** score; on a **free** tour all download-gated ratings count (LOCAL-670 rule), verified ones marked. The score *rule* (prior/median, D647) is unchanged — only the input set differs on a paid tour.

### 2. Text reviews with a moderation queue — `tour_reviews`
- Optional, ≤ 500 chars, attached to the user's rating (you must rate before you review).
- `review_status` = `pending | approved | rejected`. The **auto-check** (`moderate_text`) holds a review as `pending` with a reason when it contains **profanity**, a **URL**, or **contact info** (email/phone); otherwise `approved`. No human is needed to approve; the `pending` queue is visible to LEAD via `GET /reviews/pending` and resolvable via `POST /review/<id>/moderate`.
- `GET /tour/<id>/reviews` returns **approved reviews only**, each with the rating, date, "Verified listener" when verified, helpful count, and the approved curator reply.

### 3. Curator reply — one per review
- Only the tour's creator may reply, **once**, ≤ 300 chars, through the **same auto-check**. A flagged reply is held `pending` and not shown until approved.
- **Creator resolution** (`resolve_tour_creator`): an optional future `audio_tours.creator_user_id` column if present, else the **earliest `tour_requests.secret_id`** for the tour (the user who first generated it).

### 4 & 11. Ranking — Bayesian list-ORDER key only
- `rank_score = (C·7.5 + Σ wᵢ·ratingᵢ) / (C + Σ wᵢ)` with **C = 3**, so one 10 does not top the list.
- Weights (item 11): verified **1.0**, unverified **0.5**; and an extra **×0.5** for a rating **older than 12 months** OR made **before the tour's current version** (LOCAL-657 version date).
- This is **ordering only** — the **shown** score stays D647. Implemented identically in `tour_reviews_service.rank_score` and (self-contained, since it deploys as its own image) in `map_delivery/app.py`; a test asserts the two stay in lock-step.
- `tours-near` and `search-tours` accept `?sort=top_rated` and order by `rank_score` (ties → distance / popularity).

### 5. Protection
- A **creator cannot rate or review** their own tour (`record_rating` / `submit_review` raise).
- A **refunded** purchase un-verifies its rating (item 1).
- Ratings from users who **never downloaded** the tour can never be verified, so they never count toward a paid tour's shown score (the ticket's "ignored"); the LOCAL-670 allow-and-log behaviour for free tours is preserved.

### 6. App (Flutter), build bumped to `2.4.8+37`
- `ReviewsSection` ("Reviews (n)") in the tour dialog: expands to the distribution bars, a sort control, and the review list.
- **"Verified listener"** badge on verified reviews (`VerifiedListenerBadge`).
- After a rating, an optional **"Add a short review"** dialog (`showAddReviewDialog`); a `pending` result tells the user it is being checked.
- Home **"Top rated"** sort toggle → `?sort=top_rated`, remembered per device.

### 8. Rating distribution
- Five bands **9–10, 7–8, 5–6, 3–4, 1–2** as horizontal bars with percentages, under the score, from **verified ratings on paid tours** and **all counted ratings on free tours**. Server: `GET /tour/<id>/distribution` and the `rating_distribution` field on map-delivery tour payloads. App: tappable bars.

### 9. "Helpful" votes — `review_helpful_votes`
- One vote per `(user, review)`; the count is shown ("12 people found this helpful"). A user **cannot vote on their own review**. `POST /review/<id>/helpful`.

### 10. Review sorting & filtering
- **Top** (helpful votes, then verified, then recency), **Most recent**, **Critical** (≤ 6 first); and a **band filter** (tap a bar). Server `?sort=` and `?band=`; app sort chips + tappable bars.

### D650 — per-stop thumbs stay internal
- No per-stop thumbs are shown to listeners/curators or used in any score, ranking, or review UI. This change touches only the per-TOUR rating + reviews.

---

## Files

**Backend (Python)**
- `migration/sql/021_tour_reviews.sql` — additive `tour_ratings.verified`, `tour_reviews`, `review_helpful_votes` (idempotent).
- `tour_reviews_service.py` (new) — moderation, verified logic, review CRUD, curator reply, helpful votes, reads with sort/filter, distribution, Bayesian ranking, the moderation queue, and the Flask routes.
- `tour_rating_service.py` — `record_rating` now writes the verified flag and enforces the creator protection (lazy import of the reviews service to avoid a cycle).
- `tour_orchestrator_service.py` — registers the review routes beside the rating routes (defensive; a missing module 404s reviews only).
- `Dockerfile.orchestrator` — copies `tour_reviews_service.py`.
- `map_delivery/app.py` — verified-aware counting, `rank_score`, `compute_distribution`, the `_rating_payload` helper, `?sort=top_rated` on `tours-near`/`search-tours`, and the extra response fields (`verified_count`, `is_paid`, `rank_score`, `rating_distribution`).

**App (Flutter)**
- `audio_tour_app/lib/services/tour_reviews_service.dart` (new) — models + API calls.
- `audio_tour_app/lib/widgets/reviews_section.dart` (new) — `ReviewsSection`, `VerifiedListenerBadge`, `showAddReviewDialog`.
- `audio_tour_app/lib/screens/home_screen.dart` — reviews section in the tour dialog, add-review after rating, Top-rated sort toggle.
- `audio_tour_app/pubspec.yaml` — `2.4.8+36` → `2.4.8+37`.

**Tests**
- `tests/test_local672_verified_reviews.py` (new) — 26 tests.

---

## New / changed HTTP endpoints (orchestrator, :5002)
| Method | Path | Purpose |
|---|---|---|
| GET  | `/tour/<id>/reviews?sort=&band=` | approved reviews (verified-first), with reply + helpful count |
| POST | `/tour/<id>/review` | submit/replace a ≤500-char review (auto-checked) |
| GET  | `/tour/<id>/distribution` | five-band rating distribution |
| POST | `/review/<id>/reply` | the single curator reply (creator only, ≤300, auto-checked) |
| POST | `/review/<id>/helpful` | one helpful vote (not your own) |
| GET  | `/reviews/pending` | the LEAD moderation queue |
| POST | `/review/<id>/moderate` | LEAD approve/reject a held item |

Map-delivery (:5005) `tours-near` / `search-tours` / `tour-info` / `tour-by-code` additionally carry `verified_count`, `is_paid`, `rank_score`, `rating_distribution`, and honour `?sort=top_rated`.

---

## Key decisions
- **Paid vs free with no price flag yet.** D624's per-tour unlock mapping is pending Michael's tiers, so there is no per-tour `is_paid` today. `is_paid_tour` / `_is_paid_select` read an optional `audio_tours.is_paid` column **if it exists**, else default **FALSE** (free). This keeps today's behaviour exactly LOCAL-670's, and flips paid tours to verified-only counting automatically the moment the column arrives — no code change.
- **Creator link.** No creator column exists on `audio_tours`; the earliest `tour_requests` row is the most reliable creator signal available, and an optional `creator_user_id` column is honoured first for when one is added.
- **Two copies of the rank/score rule.** `map_delivery/` deploys as its own image and cannot import the root module (the same constraint LOCAL-670 documented for `compute_rating`), so the rule is duplicated and a test pins the two together.
- **Moderation never silently rejects.** The auto-check only *approves* or *holds* (`pending`); rejection is a human action from the queue. Contact-info is checked before URL so an email classifies as `contact`, not `url`.
- **Self-healing + migration.** Every new object has identical self-healing DDL in the service and an explicit `021` migration, matching the LOCAL-670 pattern.

---

## Verification
- **pytest:** `tests/test_local672_verified_reviews.py` → **26 passed**. LOCAL-670 + 670B → **25 passed** (no regression). Combined run: **51 passed**.
- **Migration 021:** applied twice on `audiotours_test` via psycopg2 — valid and idempotent; `tour_ratings.verified`, `tour_reviews`, `review_helpful_votes` all present.
- **flutter analyze:** the two new Dart files → **0 issues**; `home_screen.dart` shows only pre-existing lints.
- **flutter build ios --no-codesign:** **✓ Built `Runner.app` (37.4 MB)** — not installed.
- **Test safety:** every test row uses `user_id`/`secret_id` LIKE `'TEST-672-%'`, deleted only by exact key after re-checking the prefix. Post-run count of `TEST-672-%` rows across all touched tables: **0**.

## Constraints honoured
- No paid API calls. DB changes additive and declared. Own containers only — no `audioura-*` container replaced, no GCloud. `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md` untouched. Branch created from `subscribed @ 70a0bf83` (verified `git merge-base --is-ancestor 70a0bf83 HEAD` → 0).
