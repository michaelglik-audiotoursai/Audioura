# My review — three 4-stop tours

Generated 6 August 2026, ~23:40, on `storied` @ `872c562` — after tonight's
fixes to the fact detector, groundedness, selection and enrichment.

---

## Read this before the numbers

**At N=4 each stop is worth 25 points.** One THIN stop costs 12.5. These scores
swing far harder than the 8-stop museum (75.0) or 5-stop restaurant (55.0), and
**they are not comparable to them.** A 4-stop tour with two weak stops looks
catastrophic beside an 8-stop tour with four.

**Second: the scores fell three times tonight and are still an upper bound.**
Groundedness was defaulting to "perfect" whenever corpus wasn't loaded, and the
default path never loaded it. The museum went 81.2 → 78.1 → 75.0 as that came
out. Nothing regressed; the measurement got honest.

---

## The three

| Tour | Stops | Base | Shape |
|---|---|---|---|
| **Museum** — Arts Asiatiques | 4/4 | **87.5** | RICH, ADEQUATE, RICH, ADEQUATE |
| **Restaurant** — Old Nice | 4/4 | **62.5** | THIN, THIN, THIN, RICH |
| **Walking** — Vieux Nice | 4/4 | **50.0** | THIN, THIN, THIN, THIN |

All three delivered every stop asked for. That is new — a month ago the Riviera
was returning 5 of 8.

---

## Museum — 87.5. Read this one first.

The best tour we have produced, and I believe the number.

```
1. RICH      15 facts / 9 sentences    L'Armure d'Andô Naoyuki
2. ADEQUATE   4 facts / 10 sentences   Statue de Bouddha
3. RICH       7 facts / 10 sentences   La danse cosmique de Ganesh
4. ADEQUATE   4 facts / 8 sentences    Kannon, le bodhisattva de la compassion
```

Fifteen facts on the armour stop. Every stop has corpus behind it and measured
groundedness of 0.50 — meaning half of what it asserts is traceable to our
sources, which is the highest honest figure we have recorded.

**Why it beats the 8-stop version (75.0):** four stops instead of eight means we
only use the four best-documented objects. The 8-stop version has to reach for
`Robe de prêtre taoïste` and `Masque du vieillard kojô`, which are thin. This is
not the tour getting better — it is the venue's depth being respected. **The
lesson for the product: at this venue, four stops is the honest capacity.**

---

## Restaurant — 62.5, and the RICH stop is wrong

```
1. THIN     0 facts / 7 sentences    L'Escalinada
2. THIN     0 facts / 1 sentence     La Tapenade
3. THIN     1 fact  / 2 sentences    Lou Pilha Leva
4. RICH     8 facts / 10 sentences   Chez Pipo
```

**Stop 4 is the only strong stop and its facts belong to a different
restaurant.** It says:

> "Chez Pipo… **Established in 1926 as Chez Palmyre by Palmyre Moni**, the
> founder from Tuscany, **from Tuscany**, this iconic eatery…"

I checked. **Chez Pipo was founded in 1923 by a man called Pipo, at 13 rue
Bavastro.** Chez Palmyre is a different restaurant entirely — it was stop 2 of
the previous tour, and its corpus has bled into this stop.

This matters more than the score. **Groundedness reported 1.00 for that stop** —
because the facts *are* in our corpus, just filed under the wrong venue. So our
verification says "fully grounded" about a stop that misattributes another
business's founding story. Grounded against the wrong source still reads as
grounded, and nothing currently catches it.

Note also `"from Tuscany, from Tuscany"` — a duplicated phrase, the gloss-splice
family again.

**Stop 2 is one sentence long.** That should not ship.

---

## Walking — 50.0, and it contains a fabrication

```
1. THIN   0 facts / 3 sentences   Cours Saleya
2. THIN   1 fact  / 4 sentences   Palais Lascaris
3. THIN   0 facts / 2 sentences   Nice Cathedral
4. THIN   0 facts / 3 sentences   Place Rossetti
```

Three stops with **zero** facts. Two to four sentences each — 879 words for a
whole tour, against the museum's 1,372.

Stop 3 in full:

> "As you approach Nice Cathedral… you'll be struck by its grand façade… The
> intricate details of the **Gothic architecture, including the rose window and
> imposing spire**… the soft sound of church bells fills the air… The delicate
> tracery of the windows and the intricate stonework speak of centuries past."

**Nice Cathedral is Baroque, not Gothic.** Built 1650–1685, consecrated 1699,
bell tower 1731–1757. I verified this rather than assuming it.

**The index scored that stop THIN — zero facts.** So the fabrication cost us
nothing. Your ruling is that a fabricated stop should cost three times an
omitted one; here an invented architectural style was treated as an *absence* of
content. **The rubric cannot distinguish "said nothing" from "said something
false"**, and this is the first time I have caught it doing so on a delivered
tour.

The rest is atmosphere with no content: bells, chatter, tracery, "centuries
past". This is what a stop looks like when the generator has nothing and writes
anyway.

---

## What is fixed, and visible here

- **The opening reads correctly.** "You are about to embark on a walking journey
  through Vieux Nice, France" — not "through a walking tour in Vieux Nice". That
  was your complaint; LOCAL-330 took three rounds.
- **No `Treat Page` in any stop's fact count.** It was being counted as a named
  person on every tour with a closing offer.
- **No French material terms** leaking into English narration.
- **Every stop requested was delivered**, in all three tours.

---

## What these tours say about where we are

**The museum is ready.** 87.5 at N=4, 75.0 at N=8, all stops delivered, no
structural defects I can find. If you want to ship one category, it is this one.

**Restaurants are not.** Three of four stops have nothing to say, and the fourth
is confidently wrong about which business it is describing. The selection fix
worked — Chez Pipo and Lou Pilha Leva are real institutions — but we still have
no material about them, and when the generator has no material it borrows from
whatever corpus is nearest.

**Walking tours are the weakest and I had not measured them before tonight.**
Cours Saleya, Nice Cathedral and Place Rossetti are among the most documented
places in the city. Producing zero facts about them is not a data problem — it
is a pipeline problem, and I do not yet know where it is.

---

## Two defects that are mine to fix next

1. **Cross-stop corpus contamination** (restaurant stop 4). Facts from one
   venue's corpus attributed to another. Groundedness cannot see it because the
   claim *is* grounded — in the wrong place.
2. **Fabrication scored as absence** (walking stop 3). A false claim and an
   empty stop produce the same score. Your 3× ruling has nothing to apply to
   because nothing detects the fabrication.

Neither is dispatched yet. Both are more important than any remaining score
tuning, and the second one is the reason I would not yet trust a high score on a
tour I had not read.

---

## Files

```
tours/LOCAL336_museum_4stop.txt        1,372 words
tours/LOCAL336_restaurant_4stop.txt    1,084 words
tours/LOCAL336_walking_4stop.txt         879 words
```

---

## ⚠️ Correction — added after publishing, 6 Aug ~23:55

**The restaurant tour's 62.5 is inflated and the honest number is lower.**
Re-examining stop 4 after writing this review:

```
named_people = ['At Chez Pipo', 'Chez Palmyre', 'Old Nice',
                'Palmyre Moni', 'The Socca']
```

Only `Palmyre Moni` is a person. The other four — a preposition-prefixed stop
title, another venue, a place, and a dish — are counted as facts. So the "8
facts" that made this the tour's only RICH stop include roughly four phantoms.

**And the misattribution has a second cause I got wrong above.** I wrote that
Chez Palmyre's corpus "bled into" this stop. In fact `Chez Pipo` has **its own
10-passage corpus row**, and the scorer never found it — the tour's venue string
is `restaurant tour in Old Nice (Vieux Nice), France` while the corpus row is
filed under `Old Nice, Nice, France`, so the venue-scoped lookup misses. The
stop reports `groundedness = None` despite having ten passages available.

That makes the Chez Pipo failure worse, not better: **we hold the correct
material about Chez Pipo and used a different restaurant's story instead.**

Both are dispatched as LOCAL-339. The museum (87.5) and walking (50.0) figures
are unaffected by this — the phantom people appear on the restaurant stop.
