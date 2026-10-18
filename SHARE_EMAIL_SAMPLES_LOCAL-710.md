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
| community **2** invite | — | "Demo Boston Walkers" (0 members in the DB) | — | — | — |

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

## 4. Community 2 invite ("Demo Boston Walkers", 0 members)

Community 2 has **0 members** in the DB, so — per D672 — there is **no member
count line** (shown only at 2 or more).

**Subject:**

```
Join "Demo Boston Walkers" on Audioura
```

**Share message** (`buildCommunityInviteMessage`):

```
Join "Demo Boston Walkers" on Audioura.

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)
```

**Email body** (`CommunityCopy.emailInviteBody`, no description/organiser given):

```
Join "Demo Boston Walkers" on Audioura.

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)
```

The "How to get Audioura" and "(App Store / Google Play links coming soon.)"
lines are gone — the join link already leads to the store.

For reference, the same invite at **12 members** (from the test golden) adds a
single member-count line after the opening:

```
Join "Demo Boston Walkers" on Audioura.

12 members.

https://audioura.com/t/AzuwQYnf

(Or open Audioura, tap Search and paste AzuwQYnf.)
```
