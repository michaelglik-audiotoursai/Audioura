# Share email samples — LOCAL-710 / D672

These subjects and bodies are produced **by the real code** — not hand-written.
They are the verbatim output of `test/share_email_samples_test.dart`
(`buildShareSubject` / `buildShareMessage` / `buildCommunityInviteMessage` /
`CommunityCopy.emailInviteBody` in `lib/utils/share_code.dart` and
`lib/services/communities_models.dart`).

Each tour uses its **real** name and stops, read read-only from the local DB
(`audiotours`: `audio_tours` + `shared_tours`):

| Share code | Server tour | Real name (verbatim) | Stops | First stop (name — address) | Paid |
|---|---|---|---|---|---|
| `FFush25U` | 365 | `Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market and a stop at the Samuel Adams statue and a stop at the Boston Massacre site - Walking Tour` | 3 | Quincy Market — 4 S Market St, Boston, MA 02109 | Free |
| `Wo8Oj8lA` | 557 | `Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA - walking Tour` | 5 | Old State House — 206 Washington St, Boston, MA 02109 | `price_tier 3` → **$4.99** |
| `FFush25U` (as a community tour) | 365 | same Faneuil Hall tour, shown as shared from community **2 "Demo Boston Walkers"** (community 2 has no tours in this DB, so its real member/name facts are used with the Faneuil Hall tour's real stops) | 3 | Quincy Market — 4 S Market St, Boston, MA 02109 | Free |
| community **2** + **1** invites | — | "Demo Boston Walkers" / "Demo Book Club — The Art of War" (0 members, no tours — real DB settings) | — | — | §4 |

To regenerate:

```
cd audio_tour_app
flutter test test/share_email_samples_test.dart --plain-name 'PRINT SAMPLES'
```

---

## 1. Free tour — `FFush25U` (Faneuil Hall)

**Subject:**

```
A Boston walking tour for you
```

**Body:**

```
Welcome to my free tour "Faneuil Hall Marketplace — Walking Tour" on Audioura.

Hands-free audio: press play and walk.

3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)
```

---

## 2. Paid tour — `Wo8Oj8lA` ($4.99)

**Subject:**

```
A Boston walking tour for you
```

**Body:**

```
Welcome to my tour "Walking tour in Boston dedicated to Massachusetts politics and current affairs — Walking Tour" on Audioura.

Hands-free audio: press play and walk.

5 stops, starting at Old State House (206 Washington St, Boston, MA 02109).

https://audioura.com/t/Wo8Oj8lA

(Or open Audioura, tap Search and paste Wo8Oj8lA.)

The tour price is $4.99.
```

The price line is **last**, exactly as D672 requires.

> Note: this tour's stored name is a long descriptive sentence with no short
> place lede, so `shortTourTitle` keeps the sentence and only normalises the
> `- walking Tour` suffix to ` — Walking Tour`. It never invents a shorter name.

---

## 3. Community tour — from "Demo Boston Walkers" (community 2)

**Subject:**

```
A Boston walking tour for you
```

**Body:**

```
Welcome to my tour "Faneuil Hall Marketplace — Walking Tour" from the Demo Boston Walkers community on Audioura.

Hands-free audio: press play and walk.

3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)

Join the Demo Boston Walkers community in Audioura to download it.
```

---

## 4. Community invites — LOCAL-710B / D672 addenda 1 + 2 (self-explaining)

Michael did not like the invite opening with `A demo PAID community:`. The
invite now **explains itself**: a standard sentence about what a community is,
the organiser's own description as an `About this community:` paragraph, the
restriction lines generated from the community's **real settings** (each only
when it applies), the organiser + member count, an optional tour line (the
picked tour, else the latest), and finally the join link + code.

Both demo communities' settings are read **read-only** from the local DB
(`communities`, `community_passes`/`community_pass_products`):

| Community | Paid | Visibility | Waiver | Rules | Cheapest pass | Members | Tours |
|---|---|---|---|---|---|---|---|
| **2 — Demo Boston Walkers** | yes | listed | no | "Members only. Share the invite code with friends who joined." | **$5 / week** | 0 | none |
| **1 — Demo Book Club — The Art of War** | yes | private | no | "Be kind in discussions. One chapter per week." | **$1 / month** | 0 | none |

Neither community has any tours (`audio_tours.community_id` is NULL for every
row), so — per D672 — **the tour line is left out** for both real invites. A
picked/latest-tour sample follows as a labelled **fixture**.

### 4a. Community 2 — "Demo Boston Walkers" (paid · listed · rules · 0 members · no tours)

**Subject:**

```
Join "Demo Boston Walkers" on Audioura
```

**Email body** (`CommunityCopy.emailInviteBody`):

```
You are invited to join "Demo Boston Walkers" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

About this community: A demo PAID community: weekly walking stories around Boston. Try a pass with TEST PURCHASE.

Membership is paid: a pass starts at $5 for week, bought in the app.

Anyone can find it in Audioura's Search.

Rules: Members only. Share the invite code with friends who joined.

Community tours download only for members.

Organiser: Michael (demo)

https://audioura.com/t/0tdZGgXg

(Or open Audioura, tap Search and paste 0tdZGgXg.)
```

Listed → the "Anyone can find it in Audioura's Search." line (no private line);
no waiver → no waiver line; 0 members → no member-count line; no tours → no tour
line.

### 4b. Community 1 — "Demo Book Club — The Art of War" (paid · private · rules · 0 members · no tours)

**Subject:**

```
Join "Demo Book Club — The Art of War" on Audioura
```

**Email body:**

```
You are invited to join "Demo Book Club — The Art of War" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

About this community: A demo free community: listen to Sun Tzu's The Art of War together, one chapter a week.

Membership is paid: a pass starts at $1 for month, bought in the app.

It is private: only people with an invite can join.

Rules: Be kind in discussions. One chapter per week.

Community tours download only for members.

Organiser: Michael (demo)

https://audioura.com/t/1v7UDLsL

(Or open Audioura, tap Search and paste 1v7UDLsL.)
```

Private → the "It is private …" line (no listed line).

> Note: community 1's **description** still says "A demo free community", but its
> real `is_paid` flag is **true** and it offers a $1/month pass — the restriction
> line is generated from the real setting, not the prose, so it correctly reads
> "Membership is paid". (The demo seed text is stale; the invite is data-driven.)

### 4c. Community 2 with a latest tour — **FIXTURE**

No community has a real tour in this DB, so this sample is a **labelled
fixture**: community 2's real settings plus a latest tour. In production the
tour's 8-char code comes from the existing share endpoint
(`TourShareService.share(audioTourId)`); here `TourFix1` is a fixture code.

**Email body:**

```
You are invited to join "Demo Boston Walkers" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

About this community: A demo PAID community: weekly walking stories around Boston. Try a pass with TEST PURCHASE.

Membership is paid: a pass starts at $5 for week, bought in the app.

Anyone can find it in Audioura's Search.

Rules: Members only. Share the invite code with friends who joined.

Community tours download only for members.

Organiser: Michael (demo)

Latest tour: "Faneuil Hall Marketplace — Walking Tour", 3 stops: https://audioura.com/t/TourFix1

https://audioura.com/t/0tdZGgXg

(Or open Audioura, tap Search and paste 0tdZGgXg.)
```

When the organiser **picks** a specific tour instead of the latest, the label
is `Tour:` rather than `Latest tour:` — everything else is identical. At
**2+ members** a single `<N> members.` line appears after the organiser line.

