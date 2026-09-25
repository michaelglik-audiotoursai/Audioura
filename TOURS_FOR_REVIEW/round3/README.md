# Round 3 — ready for review, 2026-09-20 13:57

Six tours in this folder. **$1.04 total.** Three church, three Logan, four stops each.

## Read these two first

- **`LOGAN_1.txt`** — the first Logan tour in any round that carries real people.
- **`CHURCH_2.txt`** — the strongest church tour (12 dates, 4 named people).

## What changed since round 2

| | round 2 | round 3 |
|---|---|---|
| Logan — named people | **0, 0, 0** | **2, 0, 1** |
| Logan — dates | 4, 4, 3 | 5, 6, 7 |
| church — stops delivered | 4, 4, 4 | 4, 4, 4 |

Logan now reaches the listener with **Governor Channing Cox**, **Mayor James Michael Curley**,
**Jeffries Point** and the **East Boston mudflats** the airport was built on.

### The cause was not what LEAD said twice

Two wrong diagnoses are worth recording, because both cost a full round of tours:

1. **"The anti-fabrication gate is eating the stories."** It was not. `LOCAL-472` was deleting
   filler — *"every piece of luggage contains a narrative"* — which is correct behaviour and
   exactly the prose Michael objected to. Michael was asked to rule on loosening that gate; the
   ruling was never needed and the gate was never touched.
2. **"The fact extraction is too noisy to use."** Genuinely true — markdown headings became
   "facts", sentences were cut at line breaks and at `U.S.` — and fixing it changed nothing.

**The actual cause, found with a one-line trace rather than an argument:** `_lore` is seeded onto
the stops right after selection, but `poi_list` is rebuilt at several later points and every
rebuild makes fresh dicts. The writer saw **`lore_facts=0` on every stop while 24 facts had been
seeded.** The material was never in front of it. The lore is now re-attached at the point of use,
which survives any rebuild.

**The lesson: trace before theorising.** One instrument would have refuted both hypotheses in a
minute and saved two rounds of generation.

## Known defects still present

1. **Mangled fragments survive.** `LOGAN_1.txt`: *"reflects the strategic foresight that once
   engaged of Public Works"* — a phrase cut mid-clause. The abbreviation fix closed one source of
   this; something else is still cutting inside a sentence rather than between sentences.
2. **Logan is not yet reliable.** 2, 0, 1 named people across three runs — better than 0, 0, 0 but
   the middle run still has none, so the chain material is reaching the page only sometimes.
   Expect one good tour in three rather than three good tours.
3. `CHURCH_3.txt` has 1 named person against 4 in the other two — same unevenness.

## Still open, needing Michael

- Nothing blocking. The `LOCAL-472` decision that was pending is **withdrawn** — the gate was
  innocent.
