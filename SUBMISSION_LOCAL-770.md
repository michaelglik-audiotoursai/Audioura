# SUBMISSION — LOCAL-770: Subscribed also lists the best Stable tours (editor_score ≥ 7.2) — read-only, no copies

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-770-subscribed-shows-best-stable` · **Base:** `subscribed` @ `257dfef7`
**Base gate:** `git merge-base --is-ancestor 257dfef7 HEAD` ⇒ **0** (verified this session). Branch created from HEAD of the already-checked-out `subscribed` worktree, never from `origin/*`.

---

## 1. What this does (Michael, 2026-10-26 ~00:05; LEAD ruling)

Michael: *"Letting Subscribed also show Storied's free tours … I want it but only where the rating is above 7.2 … having seen and downloaded bad tours is not very good first impression."*

**Design: a LISTING FILTER, never a copy.** No row is copied, moved or deleted. When the Subscribed map-delivery (`DELIVERY_TRACK_FILTER=subscribed`) has **`SUBSCRIBED_STABLE_MIN_SCORE`** set (e.g. `7.2`), its list endpoints additionally surface an **ORIGINAL** Stable tour — `track IN ('beta','storied')` or NULL — whose `editor_score >= threshold`, plus that original's translations. Env **unset = feature OFF = today's subscribed-only behaviour**.

Stable is untouched: its own map-delivery never reads `editor_score` (verified — no reference), so scoring Stable rows changes nothing a Stable listener sees.

---

## 2. The change — one helper, both listing paths

All of it lives in **`map_delivery/app.py`** in the single helper that already builds the track clause, so every listing path that applies the track filter gets the new behaviour for free.

- **`_track_filter_clause(cur, req)` — `map_delivery/app.py:605`** (rewritten). Unchanged for every non-subscribed deployment and for the subscribed deployment with the env unset: it still returns `" AND COALESCE(t.track,'beta') = %s", [trk]`. When `trk == 'subscribed'` **and** `SUBSCRIBED_STABLE_MIN_SCORE` is set **and** the `editor_score` column exists, it widens to:

  ```sql
  AND ( COALESCE(t.track,'beta') = %s                              -- its own track
        OR ( COALESCE(t.track,'beta') IN ('beta','storied')        -- a Stable original…
             AND COALESCE(orig.editor_score, t.editor_score) IS NOT NULL
             AND COALESCE(orig.editor_score, t.editor_score) >= %s -- …scored ≥ threshold
             AND COALESCE(<is_paid_select>, FALSE) = FALSE ) )      -- …and FREE
  ```
  params `[trk, min_score]`.

- **New helpers above it:**
  - `_subscribed_stable_min_score()` — `app.py:591` — reads `SUBSCRIBED_STABLE_MIN_SCORE`; blank/non-numeric ⇒ `None` ⇒ feature off.
  - `_has_editor_score_column(cur)` — `app.py:574` — guarded column probe (cached), modelled on the existing `_has_track_column` / `_has_is_paid_column`; an older schema without the column simply skips the Stable branch (no 500).

- **Translations follow their original's score** via `COALESCE(orig.editor_score, t.editor_score)` — the SAME `orig` self-join (`LEFT JOIN audio_tours orig ON orig.id = t.original_tour_id`, `_ORIGINAL_LANGUAGE_JOIN`) the rating / price / content-rating gates already use. A translation's own `editor_score` is always NULL; it is judged by its original's score.

### Paths that apply the track filter (so they get the new behaviour)

Only the two **list** endpoints apply the track filter, so they are the only two that needed touching. Both already carry the `orig` self-join:

| Endpoint | Line | Notes |
|---|---|---|
| `GET /tours-near/<lat>/<lng>` (`get_tours_near_location`) | call at `app.py:2167` | Originals only (`t.original_tour_id IS NULL`), so `orig` is NULL and the score reduces to `t.editor_score`. |
| `GET /search-tours` (`search_tours`) | call at `app.py:2824` | Surfaces translations too, so the `COALESCE(orig.editor_score, t.editor_score)` inheritance is live here (proven below). |

### Paths that are track-agnostic (correctly unchanged)

The remaining map-delivery paths serve a single tour **by id** and never applied a track filter, so a Stable tour that the list now surfaces is already reachable through them with no change:

- `GET /download-tour/<id>` (`download_tour`, `app.py:2342`) — fetches by id; downloadable.
- `GET /tour-info/<id>` (`get_tour_info`, `app.py:2651`) — detail by id.
- `GET /tour-by-code/<code>` (`get_tour_by_code`, `app.py:42`) — resolves a share code to one id.
- `GET /tour/<id>/preview-audio`, `/tour/<id>/score-explanation`, `/tour/<id>/match` — by id.

So a listed Stable original **and its translations are downloadable** with no extra work: the download path never discriminated on track.

---

## 3. Guardrails honoured

- **Paid Stable row is never listed.** A Stable row with `is_paid` true is excluded by the `COALESCE(<is_paid>, FALSE) = FALSE` arm. (`is_paid` is a GENERATED column = `price_tier IS NOT NULL`; the branch reads it through `_is_paid_select`, which already inherits an original's paid flag for translations.) Proven live: paid tours 557 (7.9) and 749 (7.6) are excluded despite being ≥ 7.2.
- **All existing gates still apply** on top of the new branch: content rating / `review_status` (`not_allowed` / `pending` / `rejected` hidden), community visibility (D707), and the Free/Paid home filter. Proven by tests `beta_73_notallowed` / `beta_73_pending` not listed.
- **Stop pool / name reuse (D713/D714) untouched.** This task changes only listing/serving; nothing in generation reads `SUBSCRIBED_STABLE_MIN_SCORE`.
- **Fails open to today's behaviour.** Env unset, or `editor_score` column absent, ⇒ byte-for-byte the historic subscribed-only query.

---

## 4. Scoring tool — `tour_editor_score.py`

Stable originals must HAVE a score for the gate to surface them. Added, without changing the scoring rubric or the columns it writes:

- **`--track beta,storied`** — scopes `--backfill` (and the count below) to specific tracks via `COALESCE(track,'beta') IN (...)`, so the Subscribed one-time scoring touches only Stable originals and leaves Subscribed rows alone. `--backfill` already scored only visible originals with **no** score; `--track` narrows that set.
- **`--count-min-score N`** — **READ-ONLY** count (no model call, no write) of how many visible originals already score ≥ N, how many are still unscored, and the total visible — a safe dry-run before turning the feature on. New helpers `_parse_tracks` / `_track_scope_sql`.
- Writes remain exactly `editor_score` / `editor_score_detail` / `editor_scored_at` (migration 025). Translations are never scored.

Verified against the local `audiotours` DB:
```
$ tour_editor_score.py --count-min-score 7.2 --track beta,storied
[count-min-score track=beta,storied] visible originals: 36; scored >= 7.2: 12; still unscored: 0 (read-only, nothing written)
$ tour_editor_score.py --backfill --track beta,storied --dry-run
0 tour(s); tokens in 0, out 0; ~$0.0000 (dry run, nothing written)
```

**Cost (measured, gpt-4.1, 3 runs/tour — from SUBMISSION_LOCAL-688.md, tour 557 = 7,821 in + 943 out tokens): ≈ $0.0232 per tour.** For ~300 originals ≈ **$6.96** total (less if many already scored — the dry-run count tells you). Documented in `SUBSCRIBED_GCLOUD_ENV.md` §4.

---

## 5. Tests — `tests/test_local770_subscribed_lists_best_stable.py` (10, all green)

Isolated throwaway schema (`tests/_isolated_db.py` — `CREATE TABLE LIKE … INCLUDING ALL`, `DROP SCHEMA … CASCADE` teardown, before/after `public` row-count proof). The deployed `map_delivery/app.py` is loaded via importlib and driven through its own Flask test client. **No DELETE anywhere; zero production writes (proof printed).**

Behavioural (seeded one tour per scenario at Boston coords, drives real routes):
- env **unset** ⇒ `/tours-near` and `/search-tours` list **only** the subscribed row (today's behaviour).
- env **7.2** ⇒ the 7.3 beta **and** storied originals appear on **both** endpoints; the 7.3 beta's **translation** appears on `/search-tours` (follows original's score).
- excluded at 7.2: `7.1` (below bar), NULL score (unscored), paid (`price_tier` set), `not_allowed`, `pending` review.
- the subscribed own row is listed with and without the env (unaffected).

Helper-contract unit tests (against the clone's cursor): min-score parser (blank/garbage ⇒ None), subscribed-env-off = plain equality (no `editor_score` in SQL), subscribed-env-on widens (params `["subscribed", 7.2]`, SQL names `editor_score` and `'beta','storied'`), a `beta` filter never widens even with the env set, no track filter ⇒ `("", [])`.

```
tests/test_local770_subscribed_lists_best_stable.py ..........  10 passed
[LOCAL-770] public row counts before/after … OK — zero shared/production writes.
```

Existing suites still green: `test_local737_track_subscribed.py`, `test_local685_editor_score.py`, `test_local727_track_name_key.py` ⇒ **34 passed** together with the new file.

---

## 6. Live test — own containers only (`-p local770`, spare ports), no GCloud

Built my own image `local770-map-delivery` and ran two throwaway containers against the host `audiotours` DB (`host.docker.internal:5433`), `DELIVERY_TRACK_FILTER=subscribed`. Never `-p audioura`; `audioura-*` untouched; containers removed after.

| Container | Port | `SUBSCRIBED_STABLE_MIN_SCORE` | `GET /tours-near/42.3601/-71.0589?radius=60` |
|---|---|---|---|
| `local770-md-off` | 5905 | unset | **total = 0** (no `subscribed` rows exist near Boston → today's behaviour) |
| `local770-md-72` | 5906 | `7.2` | **total = 3** — ids 370 (8.0), 388 (7.8), 746 (7.6), all FREE |

- **Paid excluded live:** 557 (7.9, paid) and 749 (7.6, paid) are **absent** from the 7.2 result despite being ≥ 7.2 — free-only proven.
- **Translation follows original live:** `/search-tours?pattern=Boston` on the 7.2 container returned id **389** ("велосипедный тур по кругу от Crystal Lake", the Russian translation of 388) at rating **7.8** — inheriting its original 388's score.
- **Read-only confirmed:** `audio_tours` originals/scored/≥7.2 = `36 / 36 / 12` **before == after** the live reads. No `tour_editor_score.py` write was run; **budget spent = $0** (≤ $0.50 cap honoured).

---

## 7. Files changed (committed explicitly — no `git add -A`)

- `map_delivery/app.py` — `_track_filter_clause` widened + `_subscribed_stable_min_score` / `_has_editor_score_column` helpers.
- `tour_editor_score.py` — `--track`, `--count-min-score`, `_parse_tracks` / `_track_scope_sql`.
- `SUBSCRIBED_GCLOUD_ENV.md` — §4 `SUBSCRIBED_STABLE_MIN_SCORE` row + one-time scoring step + measured cost.
- `tests/test_local770_subscribed_lists_best_stable.py` — new (10 tests).

**Not edited:** DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md. No `DELETE` of any kind. No GCloud action.

---

## 8. For LEAD

- Set `SUBSCRIBED_STABLE_MIN_SCORE=7.2` on **map-delivery-subscribed** only (leave unset ⇒ feature off).
- Run the one-time scoring once against Cloud SQL (dry-run count first, then `--backfill --track beta,storied`); ensure migration 025 is applied. ~$6.96 for ~300 originals, writes only `editor_score*`.
- The feature is a pure listing filter; it needs no app change and no migration of its own.
