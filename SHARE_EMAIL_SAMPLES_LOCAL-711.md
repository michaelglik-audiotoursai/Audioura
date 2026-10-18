# Share email samples — LOCAL-711 / D673

Generated verbatim by `audio_tour_app/test/share_email_samples_test.dart`
(`flutter test test/share_email_samples_test.dart --plain-name 'PRINT SAMPLES'`),
built from the real DB tour names + stops. This supersedes
`SHARE_EMAIL_SAMPLES_LOCAL-710.md` by adding, per D673:

1. **Server short titles** in the title + subject. The two tours shown carry the
   short titles `tour_short_title.py` produced in the LOCAL-711 live run
   (read-only, one gpt-4o-mini call each — see `SUBMISSION_LOCAL-711.md`):
   - tour 365 → **Faneuil Hall Marketplace — Walking Tour**
   - tour 557 → **Massachusetts Politics — Walking Tour**
   Where the server has no short_title the app falls back to `shortTourTitle()`.
2. The **translation offer line** in every share email and community invite,
   right after "Hands-free audio: press play and walk." (after the explanation
   sentence in the invite, which has no hands-free line):
   > Prefer another language? Audioura plays it in yours: just pick your language and listen.

---

## FREE — FFush25U (Faneuil Hall)

**SUBJECT:** A Boston walking tour for you

```
Welcome to my free tour "Faneuil Hall Marketplace — Walking Tour" on Audioura.

Hands-free audio: press play and walk.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)
```

## PAID — Wo8Oj8lA ($4.99)

**SUBJECT:** A Boston walking tour for you

```
Welcome to my tour "Massachusetts Politics — Walking Tour" on Audioura.

Hands-free audio: press play and walk.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

5 stops, starting at Old State House (206 Washington St, Boston, MA 02109).

https://audioura.com/t/Wo8Oj8lA

(Or open Audioura, tap Search and paste Wo8Oj8lA.)

The tour price is $4.99.
```

## COMMUNITY — from "Demo Boston Walkers" (community 2)

**SUBJECT:** A Boston walking tour for you

```
Welcome to my tour "Faneuil Hall Marketplace — Walking Tour" from the Demo Boston Walkers community on Audioura.

Hands-free audio: press play and walk.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).

https://audioura.com/t/FFush25U

(Or open Audioura, tap Search and paste FFush25U.)

Join the Demo Boston Walkers community in Audioura to download it.
```

## COMMUNITY 2 INVITE — "Demo Boston Walkers" (0 members, no tours)

**SUBJECT:** Join "Demo Boston Walkers" on Audioura

```
You are invited to join "Demo Boston Walkers" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

About this community: A demo PAID community: weekly walking stories around Boston. Try a pass with TEST PURCHASE.

Membership is paid: a pass starts at $5 for a week, bought in the app.
Anyone can find it in Audioura's Search.
Rules: Members only. Share the invite code with friends who joined.
Community tours download only for members.

Organiser: Michael (demo)

Join here: https://audioura.com/t/0tdZGgXg

(Or open Audioura, tap Search and paste 0tdZGgXg.)
```

## COMMUNITY 1 INVITE — "Demo Book Club — The Art of War" (0 members, no tours)

**SUBJECT:** Join "Demo Book Club — The Art of War" on Audioura

```
You are invited to join "Demo Book Club — The Art of War" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

About this community: A demo free community: listen to Sun Tzu's The Art of War together, one chapter a week.

Membership is paid: a pass starts at $1 for a month, bought in the app.
It is private: only people with an invite can join.
Rules: Be kind in discussions. One chapter per week.
Community tours download only for members.

Organiser: Michael (demo)

Join here: https://audioura.com/t/1v7UDLsL

(Or open Audioura, tap Search and paste 1v7UDLsL.)
```

## COMMUNITY 2 INVITE WITH LATEST TOUR (FIXTURE — no real community tour in DB)

```
You are invited to join "Demo Boston Walkers" on Audioura.

A community on Audioura is a group that listens together: the organiser publishes tours for its members, and each new one appears in their Listen page.

Prefer another language? Audioura plays it in yours: just pick your language and listen.

About this community: A demo PAID community: weekly walking stories around Boston. Try a pass with TEST PURCHASE.

Membership is paid: a pass starts at $5 for a week, bought in the app.
Anyone can find it in Audioura's Search.
Rules: Members only. Share the invite code with friends who joined.
Community tours download only for members.

Organiser: Michael (demo)

Latest tour: "Faneuil Hall Marketplace — Walking Tour", 3 stops: https://audioura.com/t/TourFix1

Join here: https://audioura.com/t/0tdZGgXg

(Or open Audioura, tap Search and paste 0tdZGgXg.)
```
