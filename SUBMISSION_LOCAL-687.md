# SUBMISSION — LOCAL-687: Content rating (General / Mature / Not allowed) + review queue (D656)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-687-content-rating` (from `subscribed` = `1512dddc`)
**Base verified:** `git merge-base --is-ancestor 1512dddc HEAD` → exit 0.

Status: **implemented and live-tested on the dev DB. Not deployed** — the running
`audioura-map-delivery-1` container still has the old code; LEAD deploys
`map_delivery/app.py`. One real tour (id 368) is flagged mature/pending and is
**left pending for LEAD review**.

---

## Why (D656, Michael 2026-10-14)
Every tour gets a content rating like a movie rating, decided by a model (not a
bad-word list — those flag "class", "Assisi", "Scunthorpe"):
- **general** — listed for everyone.
- **mature** — strong language, alcohol-focused, crime, gambling, nightlife,
  casinos. Listed ONLY to confirmed-18+ listeners.
- **not_allowed** — sexual services / adult entertainment, explicit sex, hate,
  encouraging illegal acts. Never listed.

Anything not clearly general waits for human review before public listing.

---

## What shipped (commit-by-commit)

| Commit | What |
|--------|------|
| `37e599c6` | `migration/sql/027_content_rating.sql` + `tour_content_rating.py` |
| `4f33b077` | listing rules in `map_delivery/app.py` (all four endpoints) |
| `8c487b05` | `review_queue.py` |
| `5277f289` | `tests/test_local687_content_rating.py` |
| `5004090f` | app: 18+ Settings toggle, chip, 403 message, build bump 47→48 |

### 1. Migration `027_content_rating.sql` (additive, idempotent)
Adds to `audio_tours`: `content_rating VARCHAR(16)` (CHECK in
general|mature|not_allowed; NULL = not rated), `content_rating_reason TEXT`,
`review_status VARCHAR(16)` (CHECK in pending|approved|rejected; NULL = no review
needed), `content_rated_at TIMESTAMPTZ`, and a partial index on
`(content_rating, review_status)`. All `ADD COLUMN IF NOT EXISTS` /
`CREATE INDEX IF NOT EXISTS` — re-running only emits skip NOTICEs.

### 2. `tour_content_rating.py` (repo root, modelled on `tour_editor_score.py`)
Reads a tour's text, asks `gpt-4.1-mini` (JSON, temperature 0) for
`{rating, reason}` against the three definitions. `--tour ID`, `--backfill`
(originals with `content_rating` NULL), `--rescore`, `--dry-run`.
- `general` → `review_status` NULL (lists immediately).
- `mature` | `not_allowed` → `review_status` `'pending'` (held for review).
- An off-menu model answer fails SAFE (never silently general).
- Translations are not rated; they inherit the original's rating (the backfill
  only touches originals; `--tour` on a translation rates its original).

### 3. Listing rules — `map_delivery/app.py` (the canonical, deployed service)
Follows the LOCAL-685 pattern (`_editor_scores`/`_prior_for`, cached schema
probes). New helpers: `_has_content_rating_column` (cached; absent → fails open
to old behaviour, never a 500), `_content_rating_select` (COALESCE from the
`orig` self-join so a **translation inherits** its original's rating + review
status), `_adult_requested(args)`, `_content_visible(rating, status, adult)`,
`_content_rating_field` (NULL→general), `_row_with_rating` (pads pre-687 rows so
the unpack arity stays fixed).

Applied to **/tours-near, /search-tours, /tour-by-code, /tour-info**:
- hide `not_allowed`; hide `review_status` pending|rejected; hide `mature`
  unless the request carries `adult=1`;
- `/tour-by-code` of a **mature** tour without `adult=1` → **403
  `{"error":"age_restricted"}`**; of a **hidden** tour → **404**;
- `/tour-info` of a tour that would not list → **404**;
- NULL `content_rating` behaves as **general** (old tours keep working);
- each tour payload gains `content_rating`.

### 4. `review_queue.py` (repo root)
`python3 review_queue.py list | approve ID | reject ID "reason"`. `list` prints
id, name, rating, the model's reason, and the first 600 chars of the tour text.
`approve` → `review_status='approved'` (lists per its rating; a mature tour then
shows to confirmed-18+ listeners). `reject` → `review_status='rejected'`
(stays hidden) and stores the reason. DB-only; no model calls; no DELETEs.

### 5. App (`audio_tour_app`)
- Settings toggle **"Show 18+ tours (I am 18 or older)"** (AppBar action +
  dialog), stored per device under `home_show_adult` (default off).
- Sent as `&adult=1` on `/tours-near`, `/search-tours`, `/tour-by-code`.
- A small **"18+"** chip on mature tours in the tour dialog and the List view.
- A **403 age_restricted** on a share code shows: *"This tour is for adults
  (18+). Turn on 18+ tours in Settings to open it."* (and does not fall back to
  a location search — the code was valid, just gated).
- Build number bumped **2.4.14+47 → +48**. `flutter analyze`: 0 errors.

---

## Tests — `tests/test_local687_content_rating.py` (21, all green; no paid calls)
`python3 -m pytest tests/test_local687_content_rating.py -q` → **21 passed**.
- Each rating → the right `review_status` (general→NULL, mature/not_allowed→pending);
  the model is mocked.
- Listing filters through the REAL endpoints via a scripted fake cursor:
  not_allowed/pending/rejected hidden; mature hidden without `adult=1`, shown with it.
- `/tour-by-code` → 200 (general / mature+adult), 403 age_restricted (mature, no
  adult), 404 (not_allowed / pending).
- Translation inherits the original's rating (asserts the COALESCE fragment +
  the resolved-mature gate).
- `review_queue approve` makes a pending mature tour visible with `adult=1`
  (via `_content_visible`, the exact endpoint predicate).
- **Break-the-filter → red:** `BrokenFilterGoesRedTest`, plus I verified live by
  patching `_content_visible` to list `not_allowed` → 2 tests went red, then
  restored → green.

**No new regressions.** The 19 failures in `test_local671/666/657` exist on the
base too (stale 20-column fixtures predating LOCAL-677); I compared the failing
set base-vs-branch and it is identical.

---

## Live test (dev DB `audiotours`, `localhost:5433` via `development-postgres-2-1`)
- Migration 027 applied: `audio_tours` row count **475 before = 475 after**
  (additive); 4 columns + index added; re-apply idempotent (skip NOTICEs).
- `tour_content_rating.py --backfill --dry-run` on the 27 visible originals:

```
  id  rating        reason (abbreviated)                                   tour
   1  general       factual descriptions of Baroque artworks               Palais Lascaris, Nice
   2  general       factual overview of Abu Dhabi                           Camel Tour, Abu Dhabi
   3  general       camel racing / desert culture                          Camelback riding, Abu Dhabi
   4  general       camel tours overview                                    Camel tour, Abu Dhabi
   5  general       camel farms, culture, nature                           Camelback riding, Abu Dhabi
   6  general       dog sledding culture/history                          dog ridding tour, Big Lake AK
   8  general       dog sledding history                                   dog ridding tour, Big Lake AK
  10  general       Constitutional Convention                             National Constitution Center
  12  general       factual Nice walking tour                             walking tour in Nice
  14  general       artworks + emotional context                         Museum Of Naïve Art, Nice
  17  general       restaurants + local culture                          restaurants tour, old Nice
  24  general       Marc Chagall art/religion                            Musée Marc Chagall, Nice
  29  general       French Riviera guided tour                           French Riviera Biking Tour
 152  general       French Riviera cycling                               French Riviera cycling tour
 308  general       history/culture/art                                  biking tour in Norwood MA
 339  general       Cimiez district history                              walking tour, Cimiez, Nice
 365  general       Boston landmarks                                     Faneuil Hall Marketplace
 366  general       local restaurants                                    Restaurant tour, Newton MA
 367  general       restaurants overview                                 Newton Centre dining walk
 368  MATURE  [pending]  restaurant+bar, emphasis on alcohol (extensive wine selection), adult dining   Buttermilk & Bourbon, Back Bay
 370  general       restaurant history                                   restaurant tour, Boston MA
 372  general       Chart House restaurant                               chart house restaurant, Boston
 388  general       Boston landmarks                                     biking tour, Crystal Lake loop
 399  general       art + history museum                                 McMullen Museum of Art
 400  general       art + mythology museum                               Harvard Art Museums
 402  general       art + cultural heritage                              Vietnam National Fine Arts Museum
 557  general       political history, factual                           Boston mass-politics walk
27 tour(s): general=26 mature=1 not_allowed=0 (1 -> pending review); ~$0.0306 (dry run)
```

- Real backfill run: same result. **1 tour became hidden** — **id 368
  "Buttermilk & Bourbon"** (restaurant/bar), rated **mature → pending**,
  correctly flagged for its alcohol focus. **Left pending for LEAD review**;
  every other original is general and lists unchanged. 0 not_allowed.
- `is_test` fixtures created to exercise the gate (never visible to Michael's
  app — the `is_test IS NOT TRUE` filter excludes them): id **686** mature/approved
  (+ share code `L687MATA`), **687** mature/pending, **688** not_allowed/pending
  (+ share code `L687NA`), **689** general, **690** a `ru` translation of 686
  (own rating NULL). Nothing DELETEd.
- Verified against my updated `app.py` on spare port **5599** pointed at the dev DB:
  - `/tour-by-code/L687MATA` → **403 age_restricted** (no adult), **200** (adult=1).
  - `/tour-by-code/L687NA` (not_allowed, adult=1) → **404**.
  - `/tour-info/688` (not_allowed) → **404**; `/tour-info/689` (general) → **200**.
  - `/tour-info/690` (translation, own rating NULL) **inherits mature**: → **404**
    (no adult), **200** (adult=1), payload `content_rating: mature`.
  - `review_queue list` → the 3 pending with name/rating/reason/600-char preview;
    `approve 687` → approved (then `/tour-info/687?adult=1` → 200);
    `reject 688` → rejected (stays 404).

---

## For LEAD — two lines to add to `.continuous_dev/autonomy_tick.sh`
Per PROCESS this task does **not** edit `.continuous_dev/*`. Add the
content-rating backfill beside the LOCAL-685 editor-score step, using the same
`guard` wrapper the other steps use (DB on localhost:5433; the script's default
`DATABASE_URL` already points there). Place it just before the dispatcher line
(`/usr/bin/python3 "$REPO/kiro_dispatcher.py" ...`):

```sh
# --- Rate any unrated originals' content (LOCAL-687). general lists; mature/not_allowed wait for review_queue.py. ---
guard 900 /usr/bin/python3 "$REPO/tour_content_rating.py" --backfill >> "$LOG" 2>&1
```

(If editor-score runs as its own tick line, put this on the line directly after
it. 900 s matches the longest guarded steps; a backfill of a handful of new
originals costs a few cents and finishes in seconds.)

LEAD also: deploy the updated `map_delivery/app.py`, review the pending queue
(`python3 review_queue.py list`) — currently **id 368** — and build the app from
the bumped pubspec (`+48`).

---

## Files
- `migration/sql/027_content_rating.sql` (new)
- `tour_content_rating.py` (new)
- `review_queue.py` (new)
- `map_delivery/app.py` (listing rules on all four endpoints)
- `tests/test_local687_content_rating.py` (new, 21 tests)
- `audio_tour_app/lib/screens/home_screen.dart` (18+ toggle, chip, 403 message)
- `audio_tour_app/pubspec.yaml` (build 47→48)

Not edited: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, `.continuous_dev/*`.
