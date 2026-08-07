# My review — three 4-stop tours, current as of 07 Aug 05:00

**This supersedes `TOUR_REVIEW_3x4stop.md`.** Every number in that document has
moved, and two of its three tours have been regenerated. Read this one.

---

## Read this before the numbers

**Scores fell overnight, and that is the work succeeding, not failing.** Four
separate inflations came out:

```
groundedness defaulted to 1.00 when nothing was checked        D244
unmeasured stops capped at THIN instead of ADEQUATE            D245
phantom people counted as facts ('Treat Page', 'Old Nice')     LOCAL-333/339
59% of groundedness rested on 0 or 1 claim                     D258
facts were counted that the verifier could not even see        D259
```

Nothing about the tours got worse. The measurement stopped flattering them.

**At N=4 each stop is worth 25 points.** One weak stop costs 12.5. These are not
comparable to 8-stop figures.

---

## The three

| Tour | File | Base | Shape |
|---|---|---|---|
| **Museum** — Arts Asiatiques | `LOCAL336_museum_4stop.txt` | **81.2** | ADEQ, ADEQ, RICH, ADEQ |
| **Walking** — Vieux Nice | `LOCAL342_walking_4stop.txt` | **75.0** | THIN, ADEQ, RICH, ADEQ |
| **Restaurant** — Old Nice | `LOCAL343_restaurant_4stop.txt` | **56.2** | THIN, ADEQ, THIN, THIN |

All deliver 4 of 4 stops.

---

## Walking — 75.0, up from 50.0, and this is the night's real result

Last night this tour scored 50.0 with three zero-fact stops and told you Nice
Cathedral was Gothic. It is Baroque.

```
1. THIN       0 facts            Cours Saleya Market
2. ADEQUATE   3 facts  g=1.00    Castle Hill of Nice
3. RICH       8 facts  g=0.75    Palais Lascaris
4. ADEQUATE   4 facts  g=0.60    Place Rossetti
```

**The cause was retrieval, not writing.** We were holding 63 passages and 16 KB
of corpus about Palais Lascaris, filed under it as a *venue*, while the walking
tour asked for it as a *stop*. Nothing bridged the two. Palais Lascaris went
from **1 fact to 8** once it could see its own material.

**I fact-checked stop 3 against public sources and every claim holds:**

> "a 17th-century aristocratic building now transformed into a musical
> instrument museum… over 500 musical instruments… owned by the
> Vintimille-Lascaris family until 1802. In 1942, the city of Nice acquired the
> palace… opened its doors to the public in 1970 after extensive restoration."

17th-century ✓ · 500+ instruments ✓ · Vintimille-Lascaris to 1802 ✓ ·
city bought 1942 ✓ · opened 1970 ✓.

**That is the first fact-check tonight to come back entirely clean.** Worth
noting given I caught a fabrication in this same tour position last night.

**Still wrong, and worse than I first wrote:** stop 1, Cours Saleya Market, has
zero facts — and it contains a **second confirmed fabrication**:

> "**Named after the Marquis de Cours Saleya**, this market was once a hub for
> the trading of spices, textiles, and local produce."

There is no Marquis de Cours Saleya. The etymology is genuinely uncertain —
*soleiya* ("sunny" in Niçard), the salt trade (Nice was a salt-route hub and the
square held the salt warehouse), or the Saint-Pons abbey cellarer. The square
was "Lou Cours" until the 19th century. I checked before writing this.

**And we had the material.** Its corpus holds "2021: the city of Nice and its
heritage sites, including the Cours Saleya market, were designated as a
UNESCO…". The generator used that in the *orientation* and then ignored it in
the body, inventing an etymology instead.

**The invention cost nothing** — the stop scores 0 facts, identical to silence.
This is the second such case in this tour position; last night the same tour
called Nice Cathedral Gothic (it is Baroque). Your rule that fabrication should
cost 3x an omission has nothing to attach to, because nothing detects it.
Dispatched as LOCAL-345.

---

## Museum — 81.2, down from 87.5, correctly

```
1. ADEQUATE  15 facts  g=0.38    L'Armure d'Andô Naoyuki
2. ADEQUATE   4 facts  g=0.60    Statue de Bouddha
3. RICH       7 facts  g=0.50    La danse cosmique de Ganesh
4. ADEQUATE   3 facts  g=0.50    Kannon, le bodhisattva de la compassion
```

**The drop is stop 1 losing RICH.** Its groundedness fell 0.50 → 0.38, under the
0.40 floor — because we now check all fifteen of its facts instead of the
handful the verifier could previously see, and the newly-checked ones do not
trace to our sources.

**Making a fact checkable does not make it true.** The tour did not change; our
willingness to look did.

This is the third downward revision of a museum number I have given you
(96.9 → 71.9 → 87.5 → 81.2 across two nights). Every one has been inflation
coming out.

---

## Restaurant — 56.2, and still the weak category

```
1. THIN       1 fact   g=unmeasured   La Merenda
2. ADEQUATE   5 facts  g=0.33         Fenocchio
3. THIN       1 fact   g=0.00         Le Safari
4. THIN       2 facts  g=unmeasured   Le Tire Bouchon
```

**Good news: no contradicted stop.** Last night's version confidently stated
Chez Pipo was "established in 1926 as Chez Palmyre by Palmyre Moni". It was
founded in 1923 by a man called Pipo. That misattribution came from corpus
retrieval pulling a *different restaurant's* passages, and it has not recurred
since the retrieval fixes.

**Bad news, and you will hear it immediately.** Stop 3 opens:

> "**Renowned chef** introduced the world to the delectable pizzas of Le Safari
> before achieving three-star status."

The chef is not named. In an earlier run of this same venue the sentence read
"Franck Cerutti, a culinary master with three Michelin stars…". The name has
been dropped, leaving an anonymous subject and a missing article — "Renowned
chef introduced" rather than "A renowned chef". A listener is told someone
famous did something and never learns who.

I have not established whether a gate stripped the name as unverifiable or the
generator simply wrote it that way. It is the first thing I will look at.

---

## Where the three categories stand

**Museum is ready.** 81.2 at four stops, 75.0 at eight, no structural defects,
and the score now means something.

**Walking is fixed and I did not expect that.** It went from the worst category
to second in one change, and the change was to a lookup.

**Restaurants remain the problem.** Three of four stops have almost nothing to
say. Selection now finds real institutions — La Merenda, Fenocchio, Le Tire
Bouchon — but we hold little about them, and dining sources are thin where
museum catalogues are dense.

---

## What I would tell you if you asked what to do next

1. **Cours Saleya at zero facts** is the same shape as Palais Lascaris was. Look
   for the corpus before assuming the world is short of it — that has been the
   answer five times tonight.
2. **The unnamed chef** is user-visible and small.
3. **Restaurants need a different source strategy**, not more tuning. Your own
   two-question search produced ten usable threads where our pipeline produced a
   directory listing.

---

## Files

```
tours/LOCAL336_museum_4stop.txt        81.2
tours/LOCAL342_walking_4stop.txt       75.0
tours/LOCAL343_restaurant_4stop.txt    56.2
```
