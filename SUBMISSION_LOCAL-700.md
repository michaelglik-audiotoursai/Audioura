# SUBMISSION — LOCAL-700: Communities UX round 1 (Michael's Pixel-4 review)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-700-communities-ux` (from `subscribed`, base `ac7f1adf`)
**Design:** D657 / D658 (+ addenda) — in-app communities; owner-hosted audio + Audioura-made tours
**Builds on:** LOCAL-690 (`user-tracking/communities_api.py`, the app's community screens)

## Scope
Round 1 of the Communities UX from Michael's Pixel-4 review (2026-10-15): the four
sections of the ticket. The second content kind (tours made with Audioura for a
community) is only described in TEXT here — the feature itself is a later task.

## What was built

### §1 — Community description (both content kinds) + close warning
`CommunityCopy` (new, in `communities_models.dart`, Flutter-free) carries the copy so it
is one source of truth and unit-testable:
- `aboutContent` / `createIntro` describe BOTH kinds plainly:
  - **Your own audio** — MP3 links or an RSS feed you host; Audioura plays it, does not
    store it and does not check it; it stays yours.
  - **Tours made with Audioura** for your community — generated on the Generate tab,
    checked by Audioura (content rating, like any generated/edited tour), shown only to
    members.
- `closeWarning` — "Once members have joined, a community cannot be closed. You can step
  down as organiser." Shown on About and on the Create form (above the button).

### §2 — Join from the Communities screen
A **"Have an invite code?"** field + **Join** button on the About → Communities screen and
on the My communities list, both using the SAME resolver as Home search
(`CommunitiesService.resolveByCode`). Unknown code → "No community with that code";
otherwise the community page opens (its own join-framing for a non-member, content for a
member).

### §3 — Who can create a community (plan-gated, enforced server-side)
Creating requires the **free plan or above** — not the default Introduction level.
- **App:** `CreateCommunityScreen._checkPlan()` reads `EntitlementsService.me().level`;
  `l1` (Introduction) shows an explanation + a **Your plan** button (→ `PlanScreen`), not
  the form.
- **Server:** `POST /communities` now reads `device_entitlement.level` (the same column
  the entitlements API uses) and returns **403 `plan_required`** (with the device `level`)
  when the owner is on `l1`. The app gate can never be bypassed by a crafted request.

### §4 — The Create form
- **Required fields** marked with a red `*` (name, description, organiser name, rules; plus
  latitude/longitude only when Listed). The **Create** button is enabled only when all
  required fields are filled AND the Organiser Terms are accepted (pure helpers
  `CommunityCopy.requiredFieldsFilled` / `createEnabled`, so the gate is unit-tested).
- **Pre-fill** every field with friendly, lightly-humorous sample text — a pool of ≥ 8
  variants each (names, descriptions, organiser names, bios, rules, contacts), chosen at
  random — and a **unique** generated name ("The Wandering Owls of &lt;place&gt;" + a short
  suffix if taken). `GET /communities/name-available?name=` (case- and space-insensitive,
  trimmed) is checked on every name change (debounced 450 ms) with a ✓ / ✗ suffix icon and
  a "Taken — try another name." line.
- **Removed the RSS feed URL field** from Create (content is added per tour on the Generate
  tab).
- **Invite tools** (`CommunityInviteTools`) shown after creation AND always on the
  organiser's community page: the **invite code** with **Copy**, **Share**, **Email** and
  **Regenerate code**.
  - **Email** opens the device mail composer (mailto with subject + body, share-sheet
    fallback) pre-filled with the community name + description, the organiser name, how to
    get Audioura (`https://audioura.com` until store links exist), and "open Audioura →
    Search → type the code &lt;code&gt;". It never claims the email was sent.
  - **Regenerate** rotates the code server-side; the **old code stops working** (by-code →
    404), existing members unaffected.
- The §1 close warning is shown above the Create button.

## Server changes (`user-tracking/communities_api.py`)
- `_owner_level(cur, user_id)` + `_plan_allows_create(level)` — the create gate reads
  `device_entitlement.level` (default `l1`); free plan or above (`!= 'l1'`) may create.
- `_normalize_name` + `_name_is_available(cur, name)` — case/space-insensitive, trimmed
  (`lower(regexp_replace(btrim(name), '\s+', ' ', 'g'))`); a disabled community does not
  reserve its name.
- `create_community`: plan gate (403 `plan_required`) → unique-name (409 `name_taken`) →
  create.
- `GET /communities/name-available?name=` → `{name, available}`.
- `POST /communities/<id>/regenerate-code` (owner only; 404 unknown, 403 non-owner, 400
  missing owner id) → `{join_code, invite_message}`; the old code is replaced in the row.
- `_community_page` now includes `join_code` + `invite_message` **for the owner only**, so
  the organiser's page can always show the invite tools.

## Tests
### Server — `tests/test_local700_communities_ux.py` (14 tests, all pass)
- name-available: true for a free name; false once taken; **case/space-insensitive**;
  blank → unavailable; a disabled community does not reserve its name.
- plan gate: refused for Introduction (no row → `l1`) and explicit `l1` (403
  `plan_required`); allowed for free (`l2`) and paid (`l4`); duplicate name 409 (incl.
  case-insensitive).
- regenerate: owner only; the **old code 404s**, the **new code resolves**; unknown
  community 404; missing owner id 400.

### Server — `tests/test_local690_communities.py` (27 tests, still pass)
The create gate is new behaviour; the 690 `_create` helper now seeds its TEST owner at
`l2` (and cleanup removes those `device_entitlement` rows). No production code was weakened
to keep them green.

### Dart — `audio_tour_app/test/communities_service_test.dart` (+ new groups) and
`audio_tour_app/test/communities_ux_widget_test.dart` (new) — 31 tests, all pass
- §1 copy names both content kinds + close warning.
- §4 prefill pools each have ≥ 8 non-empty variants; `uniqueName` shape; `emailInviteBody`
  **always contains the code and the install line** (and name/description/organiser).
- §4 required-field gating + `createEnabled` (terms required; a known-taken name blocks).
- Widget: §2 join-by-code field + Join button on the Communities screen; §1 both kinds +
  warning render; §3 Create is plan-gated (shows **Your plan**) on Introduction; §4 **no
  RSS feed URL field**.

`flutter analyze` on all changed app + test files: **No issues found.**

## Build
App build number bumped **53 → 54** (`audio_tour_app/pubspec.yaml`, `2.4.18+54`).

## Process
Own containers only; no DECISIONS/CLAUDE/BACKLOG/WORK_QUEUE/.continuous_dev edits.
Committed per step; pushed `origin LOCAL-700-communities-ux`.
