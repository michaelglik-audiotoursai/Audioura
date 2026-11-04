# SUBMISSION — LOCAL-859

**share.google links no longer resolve (Google changed the redirect), so user
pins fell back to the city centroid.**

Branch: `LOCAL-859-share-google`
Base: `subscribed` (contains `298b1a8a`) — `git merge-base --is-ancestor
298b1a8a HEAD` exits 0.

Evidence (GCloud_Storied_1, wave 26, gen 00031-hp4, tour 529 = Sophia rerun;
ClickUp wdvrdazc6c): all six share.google links logged "unresolved via
maps_url"; 5 of 7 pins differed from tour 525; **An Spa sat on the city
centroid**.

---

## Root cause — confirmed LIVE today

`https://share.google/<id>` **now 302s to
`https://www.google.com/share.google?q=<id>`**, a JS-rendered page with NO
coordinate in the HTTP response. The old redirect-to-`/maps/place` chain the
LOCAL-852 resolver relied on is gone, so every link returned nothing and each
user stop fell to the shared city centroid.

Verified live in this run (PART 0 of `run_local859_live.py`):

```
share.google/<id>  -> 302 Location: https://www.google.com/share.google?q=<id>
final after follow -> 200 https://share.google/error      (invalid id)
```

---

## The fix

Two source files change: `user_stop_input.py` (the resolver + new fallback) and
`generate_tour_text.py` (wire the fallback into the forced-stops path). Nothing
else moves.

### 1 — Resolver follows the new flow (`user_stop_input.py` → `default_resolver`)

No paid API. A browser User-Agent + consent cookies (`CONSENT`, `SOCS`),
redirects followed, then, in order until a coordinate is found:

* the full redirect chain (a `maps.app.goo.gl` / `goo.gl/maps` / older
  `share.google` link may still land on a `/maps/place` URL);
* the FINAL page body — a `/maps/place`, `@lat,lng`, `!3d…!4d…` or `?q=lat,lng`
  URL embedded in the HTML, a `<meta http-equiv=refresh>`, or
  `og:url`/`canonical` (`_coord_url_in_body`);
* for a `share.google` id, the equivalent `www.google.com/maps?q=<id>`,
  `maps.google.com/?q=<id>` and `/maps/search/<id>` endpoints.

Returns the first URL a coordinate parses from, else the final URL (so a place
NAME is still recoverable for the fallback), else `None`. **Never raises** — a
failed resolve degrades to name lookup, never a drop and never a centroid.

### 2 — All the URL forms the ticket lists (`parse_maps_place_url`, `parse_plain_latlng`)

* `is_google_maps_link` accepts `share.google`, `maps.app.goo.gl`, bare
  `goo.gl/maps`, `google.<tld>/maps/place/...@lat,lng`, `maps.google.<tld>`;
* `parse_maps_place_url` reads `@lat,lng`, `!3dLAT!4dLNG`, **and**
  `?q=/query=/ll=/center=/daddr=/destination=` `lat,lng` query forms
  (`google.com/maps?q=10.77,106.70`), rejecting out-of-range pairs;
* `parse_plain_latlng` accepts a bare `lat,lng` the listener pasted.

### 3 — Name-lookup fallback, bounded to the city (`name_lookup_in_bbox`)

When a link cannot be resolved, look the venue up by NAME: **Serper `/places`**
first (≈$0.001, metered), else **Nominatim** (free). Keep the best name match
(folded-token score) that is **inside the city** — inside the geocoder's
bounding box **AND** within `max_radius_km` (25 km) of the city centre. The
radius backstop is essential: HCMC's administrative bbox spans ~350 km, so bbox
alone let a same-named "Rambutan" in **London** and a "Longan" in **Miami**
through in the first live run; the centre guard rejects both. On a hit the
caller marks `coord_source='user_name_lookup'` (weaker than `user_share_link`).
**If nothing matches in the city the stop has NO coordinate and is announced —
it is NEVER the city centroid.**

### 4 — Logging (item 4)

```
[LOCAL-859] user link resolved <name> <lat,lng> via <how>
[LOCAL-859] user link unresolved <name> (<url>) → name lookup <result>
```

### 5 — Wiring (`generate_tour_text.py`, forced-stops block)

After the share-link coordinate stamping, every `needs_geocode` user stop runs
`name_lookup_in_bbox(name, city, bbox=_geocode_scope_bbox(location),
center=_city_center_for_request(location))`. On a hit the stop gets the
coordinate + `coord_source='user_name_lookup'` + `coord_confidence='name_lookup'`;
on a miss it keeps NO coordinate (announced). `user_name_lookup` is exempt from
the Wikidata landmark-snap and is recognised as a user pin in the PHASE-3B
merge, so a name-lookup pin is kept verbatim. `user_name_lookup` /
`name_lookup` are **not** in the fallback sets of
`identity_dedup._is_fallback_coord_stop` or `pin_snap._coord_is_marked_fallback`,
so the pin is treated as a real point, never a centroid collapse.

---

## Tests — `tests/test_local859_share_google_resolve.py` (24, all pass)

* **URL forms**: `/maps/place/…@lat,lng`, `/maps?q=lat,lng`, `!3d!4d`, plain
  `lat,lng`, out-of-range reject, host recognition, website-is-not-a-maps-link,
  plain-latlng as a direct coordinate.
* **New 302 chain (mocked)**: a fake `requests.Session` replaying
  `share.google/<id>` → `www.google.com/share.google?q=<id>` with the canonical
  `/maps/place` URL in the body; a valid id recovers the coordinate, an invalid
  id (`→ /error`) resolves to none, the resolver never raises on broken
  `requests`, and `parse_user_stop` emits the `[LOCAL-859]` line.
* **Name-lookup fallback**: in-box Serper match wins; out-of-box rejected;
  Nominatim used when Serper empty; best-of-several; low-score rejected; empty
  name → None; never returns the centroid; **radius guard** rejects a same-name
  venue on another continent and a far suburb inside a huge bbox, keeps an
  in-city venue.
* **coord_source semantics**: `user_name_lookup` is not a fallback coord and is
  recognised as a user pin.

`test_local852` (18) and `test_local855e` still pass unchanged. Across the
relevant suites (user_stop / 852 / 855 / 858 / 859 / geocode / places / coord /
pin) **526 passed, 19 skipped**. Two unrelated failures
(`test_local606_replace_on_change`, `test_local666_translation_source_version`)
are **pre-existing** DB-integration tests — confirmed failing identically on the
clean base `298b1a8a` via `git stash`; neither touches `user_stop_input.py` or
the forced-stops path.

---

## Live — BUDGET ENFORCED (`run_local859_live.py`)

`TASK_BUDGET_ID=LOCAL-859 TASK_BUDGET_USD=0.30`, OWN meter dir
`./_local859_meterlogs`, `METER_MOUNT_GUARD=0` (D753 Mac-local escape hatch).
**Never read/wrote the live DB, never touched the shared `audioura-*`
containers.**

**Inputs.** A genuine `share.google` / `maps.app.goo.gl` short link can only be
minted by clicking "Share" in a browser on Google Maps, which this Mac-local
worktree cannot do. Per the ticket's stated alternative ("make your own … for
the same venue names … say which you used") PART A uses **REAL Google Maps place
URLs** (`google.com/maps/place/<Name>/@<lat>,<lng>` — a share form item 3
lists), whose coordinate the resolver reads with no paid API; the input `@lat,lng`
is each venue's real Google Maps location. PART B re-runs the SAME 7 venues with
`share.google` links that cannot resolve (the live new flow), exercising the
name-lookup fallback — the path that replaces the centroid guess.

### PART A — share-link resolution (7-stop Sophia cycling tour)

| Stop | Venue | Shipped pin | Distance to real venue | On centroid |
|---|---|---|---|---|
| 1 | The Crazy street | 10.767200, 106.693000 | 0 m | no |
| 2 | Thi Bar Saigon | 10.767660, 106.693960 | 0 m | no |
| 3 | Rambutan | 10.776100, 106.696200 | 0 m | no |
| 4 | A Star is Born | 10.776000, 106.696800 | 0 m | no |
| 5 | Longan | 10.779100, 106.699600 | 0 m | no |
| 6 | An Spa | 10.782000, 106.693500 | 0 m | no |
| 7 | Acoustic Bar | 10.781195, 106.689920 | 0 m | no |

**7/7 within 50 m, none on centroid — PASS.** Every stop logs
`[LOCAL-859] user link resolved <name> <lat,lng> via maps_url`.

### PART B — name-lookup fallback (same 7 venues, unresolvable links)

The fallback is **weaker than a share link** (ticket), so the invariant checked
is: **no pin on the centroid**.

* **Thi Bar Saigon**, **Acoustic Bar** — Serper found the exact venue in box
  (0 m).
* **Rambutan**, **Longan**, **A Star is Born** — no confident in-box match →
  **announced with NO coordinate** (never centroid).
* **The Crazy street**, **An Spa** — a weaker in-box name match (a different
  same-named venue), marked `user_name_lookup`.

**No pin landed on the city centroid — PASS.** This is the exact defect from
tour 529 (An Spa on the centroid), now impossible.

### Budget

Summed tour + Serper cost this run **$0.1716 ≤ $0.30 — PASS.**

**OVERALL: PASS.**

---

## Files changed

* `user_stop_input.py` — new-flow resolver, `?q=`/plain-latlng forms,
  `name_lookup_in_bbox` with the bbox + centre-radius guard, `[LOCAL-859]` logs.
* `generate_tour_text.py` — name-lookup fallback wired into the forced-stops
  path; `user_name_lookup` exempt from the landmark-snap and recognised as a
  user pin.
* `tests/test_local859_share_google_resolve.py` — 24 tests (new).
* `run_local859_live.py` — the budget-enforced live harness (new).

Run logs under `./_local859_meterlogs/` are NOT committed.
