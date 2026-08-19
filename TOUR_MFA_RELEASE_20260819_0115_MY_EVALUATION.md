# My evaluation of `TOUR_MFA_RELEASE_20260819_0115.txt`

**Written before reading yours, so the comparison is worth something.** Generated
2026-08-19 01:15 on the final overnight code — all seven of your steps wired, plus the
D474 extraction. Cost $0.18, 208 seconds, 5,997 characters, 3 stops.

---

## The one-paragraph version

**It is clean and it is not a story.** Three sessions ago the tours were breaking in
public — subjectless sentences, a publisher spliced into the middle of a noun phrase,
fabricated collaborators. Those are gone from this text. What is left is competent museum
copy with a person's name in it, and by your own bar **none of the three stops contains a
story.** The reason is now visible and it is not the prompt: **there are no stakes in the
material we retrieve.**

---

## Scores, mine and the machine's

| stop | index | historic | detail | social | words | story by your bar? |
|---|---|---|---|---|---|---|
| 1 Le Lézard aux plumes d'or | **24** | 12 | 15 | 69 | 140 | **no** |
| 2 Au Soleil du Plafond | **41** | 24 | 22 | 53 | 143 | **no** |
| 3 Moses and Monotheism | **28** | 24 | 29 | 60 | 249 | **no** |

The in-run index reported 38.7. The offline scorer says 31. **Do not read either as a
verdict on the night's work** — D484 measured a single-run sd of 4.9, and the sibling run
three minutes earlier scored 48.0 on identical code.

---

## Stop by stop

### Stop 2 is the best one, and it is the only one with an arc

> *"Tragically, Gris passed away in 1927, leaving behind an incomplete vision. However,
> their collaboration was posthumously realized in 1955…"*

Someone begins something, dies, and other people finish it 28 years later. That is a
beginning, a reversal and an ending, and it is the only place in the tour where anything
is at stake for anybody. It scores highest (41) and it deserves to.

**What it still lacks:** *who* finished it and *why they bothered*. Tériade and Reverdy
did that, and the text says only "was posthumously realized" — the passive that removes
the people. The one human act in the tour is reported without an actor.

### Stop 3 has the best idea and no protagonist

> *"controversially proposed that Moses was not a Hebrew but an Egyptian — a theory that
> upended traditional religious narratives."*

Genuinely interesting, and correctly attributed to the 1939 text rather than to the Dalí
edition — the misattribution you have objected to most is not here. But the stakes belong
to **an idea**, not to a person doing something. Nobody risks anything.

**And it lost the best sentence in the exhibition.** Two runs earlier, on the same code,
stop 3 opened:

> *"In 1938, Salvador Dalí met Sigmund Freud in London and sketched his portrait."*

A meeting, a date, a place, two named people, an action. That is your 1967-destroyed-edition
standard. It is **not in this run** — the material supports it, the pipeline found it once
and lost it. That is the variance problem doing real damage, not just moving a number.

At 249 words it is also 75% longer than the other two, without being 75% better.

### Stop 1 is the weakest, and a gate is why

> *"The generous gift of this work to the museum further enriches the collection…"*

**Boris Fridman has been deleted from his own sentence.** The unglossed-reference gate
degraded his name out, leaving an agentless abstraction. The donor — a collector who chose
this work and chose this museum, which is exactly your Fact → Stop → Exhibition chain — is
now "the generous gift".

The gate was right that he was unexplained. Removing him was the wrong repair. Its index of
24 is the lowest in the tour and this is most of the reason.

---

## What is measurably better than yesterday

- **No structural corruption.** No subjectless sentence, no gloss inside a noun phrase, no
  stray markdown. All three were live in tours generated earlier tonight and each was
  fixed (LOCAL-492).
- **The Hogarth Press claim is correct where it appears** and absent where it does not
  belong.
- **Dates hold together.** Gris 1927, work realized 1955, Freud 1939, Dalí 1974 — mutually
  consistent and correctly ordered.
- **Every stop names its object.** `detail == 0` on 0 of 3; that was a standing failure.

## What is still wrong, in the order I would fix it

1. **The passive voice is eating the actors.** "was posthumously realized", "the generous
   gift", "was instrumental in bringing the project to fruition". Every one of these had a
   named human in it upstream. No gate objects to a passive, and the story dies in it.
2. **Stop 1's orientation is 180 words and spoils stops 2 and 3** — it tells you about
   Torf's patronage and Freud's monotheism before you have looked at the first object.
3. **Evaluative filler is back**: *transformative* ×3, *vibrant* ×3, *revolutioniz-* ×3,
   *profound* ×2. The story pass bans these; the surrounding description prompt does not.
4. **The closing line summarises the gallery's donor, not the art**: "Collector Torf's
   patronage makes rare collaborations accessible."
5. **3 stops delivered against 4 requested** — unchanged and unexplained.

---

## The finding that matters more than any of the above

**With the story isolated in its own pass, the bottleneck is visibly the material.**

The pass now writes the best story the snippets allow. The detector still refuses all three
stops, and its reason is exactly right:

> *"someone is described, but nothing is risked, refused or lost. That is exposition, not a
> story."*

I checked: **there are no stakes in the retrieved material for any stop.** Not "the model
failed to use them" — they are not there. No prompt can produce them without inventing, and
an invention in the story pass would land **upstream of every gate we have**.

So the next work is **retrieval, not prompting.** Six rounds have gone into prompt shape
against a shortage of material. Step 3.4's replenishment loop never fired tonight because
these stops are not thin by *character count* — they are thin *in kind*. The floor measures
volume; what is missing is conflict.

---

## The question I could not answer for you

**Two of your own definitions of "story" disagree, and picking between them is a product
decision, not an engineering one.**

- **Your step 3**: *"Story is connecting a fact with the stop with the exhibition or museum
  or with the city or with the country"* — a chain ACROSS entities.
- **Your bar in the scanner**: THREE consecutive sentences about **ONE** person, carrying
  an action and something at stake.

A sentence each about the publisher, the printer and the donor satisfies the first
completely and the second not at all — the detector calls it a list of credits. I have
aimed the generator at both (one protagonist held for three sentences, *then* the chain
outward), but when the material only supports one of them, **which do you want?**

Stop 2 of this tour is the chain. Stop 3 of the 01:07 run was the protagonist. They read
very differently aloud, and I do not think it is my call which is the product.

---

## How to regenerate or compare

```bash
cd ~/Audioura
python3 run_full_tour_release_check.py          # this tour, ~$0.18, ~3.5 min
STORY_PASS_ENABLED=0 python3 run_full_tour_release_check.py   # without the D474 pass
```

Sibling runs on identical code, for the variance: `TOUR_MFA_RELEASE_20260819_0107.txt`,
`_0112.txt`. The A/B on the story pass is in `AB_STORY_PASS.log`.
