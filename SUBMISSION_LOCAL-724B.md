# SUBMISSION — LOCAL-724B: the rater belongs in the image, and a failed rating must not list

**Branch:** `LOCAL-724B-rating-in-image`
**code_sha:** `8f45d7196fa64665b4db0e7c63973eb9bd1c9b00` (`8f45d719`)
**Base:** subscribed `7f4e360d` — `git merge-base --is-ancestor 7f4e360d HEAD` → exit 0 (verified).
Built on LOCAL-724 `00c5c3e6` (`origin/LOCAL-724-content-rating-truth`); that commit has `7f4e360d` as its ancestor.

## What was wrong (LEAD bounce of LOCAL-724 @ 00c5c3e6)

Items 1+2 of LOCAL-724 ("rate in the serving path, before listing") were true on the
host but FALSE in the real containers:

1. **`Dockerfile.orchestrator` did not COPY `tour_content_rating.py`.** It copies sources
   one-by-one; the rater was not in the list. In the built image
   `import tour_content_rating` raised, the `except` printed, and the store committed the
   tour UNRATED → `content_rating` NULL → listed as General. LOCAL-724's live proof imported
   the module on the *host* (`live_local724_proof.py`), so it never saw this.
2. **A new tour that could not be rated was still listable.** When `rate_tour_row` returned
   None (no key / model error), the new-tour path left the row unrated = General.
3. **The orchestrator had no OpenAI key** (D673 kept keys out of it).
4. The launchd backfill's re-rate hand-off had no test.

## The fixes

### Defect 1 — put the rater in the image, and make it work against the shipped SDK
- `Dockerfile.orchestrator`: `COPY tour_content_rating.py /app/`.
- `requirements_orchestrator.txt`: add `openai==0.27.0` — the orchestrator now needs the SDK
  to rate (D685). Pinned to the version the rest of the stack ships.
- `tour_content_rating.classify` is now **SDK-tolerant**, mirroring `tour_editor_score.judge`
  (LOCAL-692B): try the modern `from openai import OpenAI`, fall back to the legacy
  `openai.ChatCompletion.create`. **This is essential** — both the orchestrator image and the
  generator/tour-editing image ship the LEGACY openai SDK (verified in-container below: no
  `OpenAI` class, has `ChatCompletion`). Without the fallback the rater raises, `rate_tour_row`
  returns None, and every tour is held — items 1+2 stay false.
- The image that runs `tour_editing_phase2.py` is `audioura-tour-generator` (built from
  `Dockerfile.generator`, which does `COPY *.py`), so it already contains the rater — verified
  in-container.

### Defect 2 — hold a tour that cannot be rated
`store_audio_tour`'s new-tour path: when `rate_tour_row` returns None, it now calls
`tour_content_rating.clear_rating(cur, id)` → `content_rating` NULL + `review_status 'pending'`,
exactly as the edit path does, BEFORE the commit. The listing layer hides `pending`, so an
unratable new tour is **not** listable; the launchd backfill rates it later. Short text
(< 200 chars) lands here too: held, the backfill decides.

### Defect 3 — give the orchestrator (and tour-editing) the key (D685)
`docker-compose.subscribed-local.yml`: added `- OPENAI_API_KEY=${OPENAI_API_KEY}` to
`tour-orchestrator` and to `tour-editing-phase2` (which also rates, in `promote_custom_tour`),
each with a comment citing D685. `docker compose -f docker-compose-master.yml -f
docker-compose.subscribed-local.yml config` validates.

### Defect 4 — the backfill re-rate hand-off
`tour_content_rating.main() --backfill` selects `content_rating IS NULL` (a held row —
NULL rating + pending status — qualifies), and writes `review_status = review_status_for(rating)`,
which is `None` for `general` → resets `pending` to NULL → listable. A test drives the real
`main()` and asserts both halves.

## In-container proof (D684)

Own compose project `-p local724b` (`docker-compose.local724b-proof.yml`), OWN postgres volume
on spare port **55434**, orchestrator/editing on **55002/55022**, map-delivery on **55005**.
No host mounts; **never** `-p audioura`, never touched `audioura-*`. The isolated postgres uses
`md5` auth because the orchestrator image pins `psycopg2-binary==2.9.1` whose bundled libpq
predates SCRAM (postgres:15 defaults to scram-sha-256).

**PROOF A — `import tour_content_rating` works in the image (both images):**
```
# RUNNING orchestrator container
$ docker compose -p local724b ... exec tour-orchestrator python -c "import tour_content_rating; print(tour_content_rating.__file__)"
IN-CONTAINER IMPORT OK: /app/tour_content_rating.py

# orchestrator image at the committed SHA
image .git_sha=8f45d719
in-image import OK: /app/tour_content_rating.py

# generator / tour-editing image
RATER OK in editing image: /app/tour_content_rating.py

# both images ship the LEGACY openai SDK → the SDK-tolerant fallback is required
orchestrator image:  has OpenAI: False   has ChatCompletion: True
editing image:       has OpenAI: False   has ChatCompletion: True
```

**PROOF B — a stored tour is RATED before it could appear in /tours-near (real key):**
```
[LOCAL-724] rated tour 3 general (1 window(s))
STORE_ACTION=inserted
ROW id=3 content_rating='general' review_status=None listable=True
RESULT rated: PASS (a new tour is RATED before it can list)
```
The rating is written in the same transaction that makes the row listable, so the committed
row already carries `content_rating`.

**PROOF C — OPENAI blanked → a new tour is HELD, not listed (defect 2):**
```
Inserted new tour: LOCAL724B Proof held ba666df5 (is_test=False)
[LOCAL-724] rate_tour_row: rating tour 4 failed, left for backfill: You didn't provide an API key...
STORE_ACTION=inserted
ROW id=4 content_rating=None review_status='pending' listable=False
RESULT held: PASS (OPENAI blanked -> new tour HELD, not listable)
```

**Final isolated DB state** (then torn down with `down -v`; no `local724b` containers remain):
```
 id | content_rating | review_status | is_test |              name
----+----------------+---------------+---------+--------------------------------
  1 | general        |               | f       | LOCAL724B Proof rated dbb22084
  2 | general        |               | f       | LOCAL724B Proof rated 1ce8732d
  3 | general        |               | f       | LOCAL724B Proof rated 4cec10c6
  4 |                | pending       | f       | LOCAL724B Proof held ba666df5
```
Rows 1–3 (rated) are listable; row 4 (OPENAI blanked) is held and not listable.

**Spend:** 3 real `gpt-4.1-mini` rating calls (rows 1–3), a few hundred tokens each ≈ **well under
$0.01** — far below the $1 budget. Proof C made no paid call (no key).

## Tests

`python3 -m pytest tests/test_local724_content_policy_truth.py tests/test_local724b_store_holds_unratable.py -q`
→ **19 passed**.

Hermetic suite `tests/test_local724_content_policy_truth.py` (18, no DB, no paid call):
- `SdkTolerantClassifyTest` — classify falls back to legacy `ChatCompletion` when the modern
  `OpenAI` class is absent (defect 1).
- `BackfillReRateHandoffTest` — the backfill SELECT filters `content_rating IS NULL` and a
  general re-rate writes `review_status = NULL`, un-holding the tour (defect 4).
- `HeldWhenUnratableContractTest` — `rate_tour_row` → None then `clear_rating` holds the row;
  the real listing predicate hides it (defect 2).
- `RateBeforeListingRedTest` — **RED**: skipping the rater leaves NULL/NULL, which lists as
  general; the guard then fails, proving the green tests are not vacuous.
- (plus the original item 3 / item 1+2 / item 4 / item 5 tests, unchanged).

Isolated-DB `tests/test_local724b_store_holds_unratable.py` (1, throwaway schema `t724b`, dropped
on teardown, public row counts asserted unchanged, no paid call — `rate_tour_row` monkeypatched
to None): proves defect 2 **end to end through the real `store_audio_tour`** — an unratable new
tour is stored held (NULL + pending) and is NOT listable via the real
`map_delivery.app._content_visible`.

Note: `tests/test_local606_replace_on_change.py` shows 4 failures, but they are **pre-existing on
the clean base `00c5c3e6`** (verified by `git stash` → run → `git stash pop`) — a different
ticket's isolated-DB fixture in this worktree's DB state, not caused by this change.

## Files changed
- `Dockerfile.orchestrator` — COPY the rater.
- `requirements_orchestrator.txt` — add `openai==0.27.0`.
- `tour_content_rating.py` — SDK-tolerant `classify()`.
- `tour_orchestrator_service.py` — hold a new tour that cannot be rated.
- `docker-compose.subscribed-local.yml` — `OPENAI_API_KEY` on orchestrator + tour-editing (D685).
- `tests/test_local724_content_policy_truth.py` — 3 new tests (defects 1, 2, 4).
- `tests/test_local724b_store_holds_unratable.py` — new isolated-DB hold proof (defect 2).
- `docker-compose.local724b-proof.yml`, `tests/in_container_proof_724b.py` — D684 proof harness.

Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
STORIED_COMMUNICATION_04.MD, or review_queue.py. ClickUp status unchanged.
