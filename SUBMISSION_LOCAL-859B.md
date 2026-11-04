# SUBMISSION — LOCAL-859B

**Resolve real share.google links via the place name and Knowledge-Graph id Google now redirects to**

- **Base:** subscribed (contains `e92e94ce` = LOCAL-859). `git merge-base --is-ancestor e92e94ce HEAD` → exit 0.
- **Branch:** `LOCAL-859B-share-google-kg`

---

## Problem

LOCAL-859 assumed `share.google/<id>` eventually lands on a `/maps/place` URL
carrying `@lat,lng`. GCloud_Storied_1 probed Michael's **real** links (request
`ef0cee57`, 2026-11-03; ClickUp `wdvrdazc6c`) and found Google changed the flow
again. The chain today is:

1. `share.google/<id>` → **302** → `www.google.com/share.google?q=<id>`
2. → **301** → `www.google.com/search?kgmid=<KG id>&q=<place name>&source=sh/x/(loc|kp)/…`
3. → a JS-only search page.

- **HEAD stops at hop 2**, so the resolver must follow with **GET**.
- No `/maps/place`, `@lat,lng`, `!3d!4d`, `0x…:0x…` or ftid appears anywhere in
  the HTTP response — the old coordinate-in-URL path is gone.
- Thi Bar → `kgmid=/g/11c…` with `source=…/loc` (a local place).
- Rambutan → `kgmid=/m/0fs6v` with `source=…/kp`, which is the **fruit** — the
  typed stop name, not `q`, is the venue.

So every share.google link resolved to no coordinate, and user pins fell back to
the city centroid.

## Fix

The share.google link now carries what we need in the **canonical search URL**:
the place NAME in `q` and the Knowledge-Graph id in `kgmid`. We read those and do
**not** fetch the JS page.

### `user_stop_input.py`

- **`parse_kg_search_url(url) -> (q, kgmid, source)`** — reads the hop-2
  `google.com/search?kgmid=…&q=…&source=…` URL (string only, no network). A bare
  share id in `?q=<id>` (a digit-bearing space-free token) is rejected; a real
  place word like `Rambutan` is kept.
- **`kg_confidence(kgmid, source) -> "high" | "low"`**:
  - `/g/` **and** `source` contains `loc` (and not `kp`) → **HIGH**.
  - `/m/` (a Freebase topic), or `source` contains `kp`, or a `/g/` with no `loc`
    source, or nothing → **LOW** (conservative).
- **`resolve_share_link_kg(url, *, resolve, log)`** — follows the chain with GET
  (injected `resolve`, default `default_resolver`), reads `q`/`kgmid`/`source`
  from the final URL, computes confidence, and returns
  `{q, kgmid, source, confidence, lat, lng, final_url}`. A classic `/maps/place`
  short link that still carries a coordinate wins outright. Emits exactly one
  `[LOCAL-859B]` line; never raises.
- **`parse_user_stop`** now surfaces `kg_q`, `kgmid`, `kg_source`,
  `kg_confidence` on the stop dict (`how='share_kg'`) when the share link resolved
  to the KG search page without a coordinate.
- **Logging** — the share id is truncated to 4 chars (`thib…`) everywhere,
  including the pre-existing LOCAL-859 `unresolved (…)` line. **The full share id
  is never logged** (it is public).

### `generate_tour_text.py` (forced-stops / user-stops wiring)

For each user stop a share link could not resolve to a coordinate:

- **HIGH** (`/g/`+`loc`) → look up **`kg_q`** (Google's own place name, usually
  with address/district) via `name_lookup_in_bbox` (Serper `/places`), reusing
  LOCAL-859's bbox **and** 25 km radius guard. A hit is stamped
  `coord_source='user_share_link_kg'`, `coord_confidence='kg_place'` — treated
  like a user pin.
- **LOW** (`/m/` or `kp`), or a HIGH that found no in-box match → ignore `q`
  (it may be the topic/fruit) and look up the **typed stop NAME**
  (`coord_source='user_name_lookup'`, the LOCAL-859 fallback).
- No in-box match → the stop keeps **no coordinate** and is announced. **Never
  the centroid.**

`user_share_link_kg` is recognised as a user pin alongside `user_share_link` /
`user_name_lookup` in `pin_snap._is_user_pin`, in the centroid-fix exclusion
guard, and in the Phase-3B coordinate-merge preservation.

## Tests — `tests/test_local859b_share_google_kg.py` (21 tests, offline)

- KG search-URL parsing for both shapes (`/g/`+`loc`, `/m/`+`kp`); hop-1
  `share.google?q=<id>` and a bare-id `q` are not mistaken for a place name.
- Confidence gate: `/g/`+`loc` → HIGH; `/m/`, `kp`, or a `/g/` without `loc` →
  LOW.
- Mocked GET chain for both shapes; `resolve_share_link_kg` returns the
  structured dict and the `[LOCAL-859B]` line.
- **HEAD-vs-GET**: a HEAD-only resolver stops at hop 2 (no `kgmid`); GET reaches
  the search URL.
- **No-network / requests absent** → degrades to the typed-name path, no KG
  fields, never a crash, never the centroid.
- The **full share id is never logged** (4-char truncation asserted).

```
$ python3 -m pytest tests/test_local859b_share_google_kg.py -q
21 passed

$ python3 -m pytest tests/test_local859_share_google_resolve.py \
      tests/test_local859b_share_google_kg.py \
      tests/test_local852_user_stops_safe.py \
      tests/test_local855e_user_pin_and_address.py \
      test_local858_hcmc_pins.py -q
85 passed

$ python3 -m pytest tests/ -q -k "pin_snap or 855 or 859 or 852 or 858"
196 passed, 18 skipped
```

## Live proof — `run_local859b_live.py` (BUDGET ENFORCED)

`TASK_BUDGET_ID=LOCAL-859B TASK_BUDGET_USD=0.15`, own meter dir
`./_local859b_meterlogs` (D753 Mac-local no-mount; never the shared/live DB,
never the shared `audioura-*` containers).

- **PART 0 — LIVE share.google flow.** HEAD follows to hop 2
  (`www.google.com/share.google?q=<id>`, no `kgmid`); GET follows further
  (an invalid id lands on `share.google/error`). Confirms the flow the fix
  targets is the one live today, and that **GET is required**. A genuine valid
  short link can only be minted by clicking "Share" in a browser on Google Maps,
  which this Mac-local worktree cannot do (and must never read/write the live
  DB), so PART A drives the resolver through a captured copy of the exact live
  chain for the two real shapes — the ticket's stated alternative.
- **PART A — resolver direct, both shapes.**
  - Thi Bar `/g/`+`loc` → **HIGH**, `q='Thi Bar Saigon, Ngô Thời Nhiệm,
    District 3'` looked up via **live Serper `/places`** → `10.767660,106.693960`
    = **0 m** from the real venue. `PASS`
  - Rambutan `/m/`+`kp` → **LOW**, `q` (the fruit) ignored. `PASS`
- **PART B — one 3-stop user-stops tour** (Thi Bar Saigon, Acoustic Bar, An Spa):
  - Acoustic Bar → **0 m** to venue
  - Thi Bar Saigon → **0 m** to venue
  - An Spa → name lookup returned an "An Spa" (Serper score 1.00) at
    10.750916,106.638130, **~3.6 km from the target I used (10.7820,106.6935)**.
    **This does NOT meet the ticket's PASS rule** (within 50 m, or announced with
    no pin). It is not the centroid and not another city, but it is a likely
    wrong branch (the name "An Spa" is ambiguous and the typed name was all the
    lookup had). My target coordinate was itself carried over from LOCAL-859's
    harness and is not independently verified, so the true error is unconfirmed.
    **Open issue / follow-up:** name-only lookup cannot disambiguate chain-like
    names; a real An Spa share link (or the street from the listener) is needed.
  - **No pin on the centroid.**

**Coverage caveat.** The Part B share links were synthetic ids, so they landed on
`share.google/error` and every stop went through the LOCAL-859 typed-name path.
The tour therefore did **not** exercise the new KG-gated branch in
`generate_tour_text.py`. That branch is covered only by Part A (captured-chain
resolver + live Serper lookup) and by unit tests; it has **not** been run
end-to-end in a tour. I could not mint real share.google links from this
worktree.

```
  PART A (resolver direct: /g/+loc HIGH q-pin ≤50 m, /m/+kp LOW): PASS
  PART B (no centroid): no centroid; Acoustic/Thi Bar 0 m; An Spa ~3.6 km -> FAILS the ≤50 m-or-announced rule
  BUDGET ($0.0210 ≤ $0.15):                                       PASS
```

Also observed: in one run the HIGH `q` lookup for Thi Bar returned NO MATCH in
box (the lookup is not fully deterministic across runs); the wiring then falls
back to the typed name, which found it.

Representative `[LOCAL-859B]` lines (share id always truncated to 4 chars):

```
[LOCAL-859B] share link thib… → q='Thi Bar Saigon, Ngô Thời Nhiệm, District 3' kgmid=/g/11c5qd9z source=loc → q→name_lookup (high)
[LOCAL-859B] share link ramb… → q='Rambutan' kgmid=/m/0fs6v source=kp → typed_name→name_lookup (low)   (after the log fix in this commit)
```

## Process / safety

- Committed only source + tests + this submission on `LOCAL-859B-share-google-kg`
  (no `git add -A`). **Run logs, generated tour files and meter logs are never
  committed.** No full share.google id is written into the repo.
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`. No `DELETE`, no live DB
  writes, no shared-container changes.

### Files changed
- `user_stop_input.py` — KG parsing, confidence gate, `resolve_share_link_kg`,
  KG fields on the stop dict, share-id redaction in logs.
- `generate_tour_text.py` — confidence-gated KG q-lookup wiring + `user_share_link_kg` user-pin recognition.
- `pin_snap.py` — `user_share_link_kg` recognised as a user pin.
- `tests/test_local859b_share_google_kg.py` — new (21 tests).
- `run_local859b_live.py` — new, budget-enforced live proof.
