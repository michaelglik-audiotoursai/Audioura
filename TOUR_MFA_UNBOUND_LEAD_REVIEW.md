# LEAD review — `TOUR_MFA_UNBOUND_prefix.txt`

Generated 2026-08-10, `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`,
8 stops requested, live run, everything through LOCAL-368 merged (369 and 370 not
in it). Scored **68.75**, 8/8 delivered, classes RICH / ADEQUATE / THIN / THIN /
THIN / THIN / RICH / ADEQUATE.

Written before seeing Michael's review, so we can compare independently.

---

## 1. The verdict in one line

**Every stop is the wrong object, and separately, the prose has defects that
would still be there if the objects were right.** Those are two different
machines failing, and it is worth keeping them apart — fixing selection will not
fix the writing.

---

## 2. Selection — already diagnosed, already dispatched (D284 / LOCAL-370)

Not one of the eight stops is in the exhibition. The show is *livres d'artiste* —
illustrated books by Picasso, Miró and Dalí. The tour delivers Egyptian
sculpture, a Thomas Cole landscape, a Nubian exhibition and a bronze equestrian
statue on the museum's lawn.

The stops are alphabetical — Adam, Adoration, An Italian, Ancient, Ankhhaf,
Appeal, April. That ordering is the fingerprint of an index scrape.

Four stacked causes, measured, all in LOCAL-370. I will not repeat them here
except for the one that matters most: **R4 replenishment backfilled seven
venue-wide works** after D1v2 correctly rejected the garbage. Honest degradation
was defeated by a code path nobody had scoped.

**Skip to §3 — that part is known. What follows is new.**

---

## 3. The spine worked, and it found Michael's own idea unprompted

This is the most interesting thing in the artifact and it is easy to miss under
the selection failure.

A theme thread emerged, was promised in the Orientation, and was paid off in the
Epilog:

> Orientation: *"This tour delves into Francis Bartlett's Legacy in Art
> Acquisition, showcasing how his donations funded the acquisition of significant
> pieces…"*
>
> Epilog: *"…you have followed the thread of Francis Bartlett's Legacy in Art
> Acquisition."*

So `theme_thread_discoverer` + `spine_generator` are functioning end to end. That
is real and worth banking.

**And note what the thread is about: a donor.** Given a museum corpus and no
instruction, the system independently selected *provenance and philanthropy* as
the most connective story available. That is Michael's Thread B, arrived at
without being asked. It is decent evidence that LOCAL-369's direction is right
rather than a personal preference.

**But the thread is asserted more than it is earned.** It is genuinely present in
Stop 1 (collection founders) and Stop 6 (*"Bartlett's generous donation made this
acquisition possible"*). It is absent from Stops 2, 3, 4, 5, 7. Stop 8 gestures
at it — *"the enduring influence of early donations"* — without naming anything.

So the spine promises a thread that five of eight stops do not carry. A listener
who is paying attention will notice the promise was not kept. **Coverage-
proportional degradation is specified in SQ-S6b and is evidently not enforcing
here** — worth a task once selection is fixed, because measuring it against a
tour of wrong objects would be measuring noise.

---

## 4. Sentence-level breakage — the clearest new finding

Multiple sentences are not grammatical English. These are not stylistic
quibbles; they are the kind of thing a listener hears immediately, and TTS will
read them aloud verbatim.

**Stock phrase grafted onto a sentence that cannot host it:**

> Stop 3: *"The 'Adoration of the Shepherds' and consider the museum's dedication
> to showcasing diverse narratives through early donations like this painting
> **stretches out before you**."*

This is the second tour in which `stretches out before you` appears bolted onto a
sentence it does not fit. The Palais Lascaris run on the same day produced:

> *"This remarkable piece with an understanding of its historical context
> **stretches out before you**."*

Two different tours, two different venues, same template. **This is a
generalisable defect, not a one-off** — some phase is appending a stock closing
clause to an already-complete or already-broken sentence. Worth its own task; it
is cheap to find because the phrase is a literal string.

**Appositive injection producing nonsense:**

> Stop 1: *"The Museum of Fine Arts, **the largest collection outside Japan**,
> Boston, boasts a remarkable collection of Japanese art…"*

The fact ("largest collection outside Japan") has been inserted into the middle
of the institution's name. The sentence now says the museum *is* the largest
collection outside Japan, located in Boston, which is both ungrammatical and
false as phrased.

> Stop 7: *"Dallin's masterpiece, recognized with a gold medal at the Paris Salon,
> **the 1909 award for artistic excellence, in 1909**, holds deep historical
> significance…"*

Nested appositive, and 1909 appears twice.

**Dangling connective:**

> Stop 2: *"The acquisition of this piece **through** underscores the museum's
> commitment…"*

A word is missing after "through" — the injection slot was filled with nothing
and the sentence shipped anyway.

**"Before" used as a spatial cue where it makes no sense:**

> Stop 5: *"**Before** the exhibit 'Ancient Nubia Now,' the artifacts displayed
> include…"*
>
> Stop 7: *"**Before** this iconic piece, the museum's commitment to preserving
> and celebrating diverse cultural narratives … is evident."*

The second is a non-sequitur — standing before a statue does not make a
commitment evident.

**Common cause worth naming:** every one of these is a *fact-injection site*
where the injected material was not integrated into the host sentence. The
grammar breaks at the seam. That points at the injection templates, not the LLM's
fluency — and it means a validator could catch most of them structurally.

---

## 5. Fact-grafting: the right fact attached to the wrong object

Distinct from selection. Even given a correct stop, the wrong facts are landing
on it.

**Stop 8 — the clearest case.**

> *"The painting 'April 1957 (Celestial Blue)' captures the essence of a dark blue
> pigment created by the paint maker Diesbach in Berlin in 1704."*

This is the invention story of **Prussian blue**. It has been attached to a 1957
painting because both concern a blue. "Celestial blue" is not Prussian blue, and
a painting made in 1957 does not "capture the essence" of a 1704 pigment
invention. The entire stop is about pigment history; the painting is never
described. **No artist is named.**

**Stop 2 — no artist at all.**

> *"'Adam and Eve' stands as a significant work of art created for Pope Leo X's
> triumphal entrance into Florence, Italy, in 1515."*

Provenance context is given, Dürer is named as the *source of inspiration*, and
the actual painter is never identified. A listener standing in front of the work
cannot learn who made it.

**Stops 1 and 5 are not works.** "The Japanese" is a truncated title — almost
certainly a gallery or garden name cut short. "Ancient Nubia Now" is *an
exhibition*, described as an exhibit inside a tour that is itself supposed to be
an exhibition. A stop whose subject is another exhibition is a category error the
stop-existence gate did not catch.

---

## 6. Smaller, still user-facing

- **Opening hours are malformed:** *"Closed on Wednesday. 10:00–05:00"*. Should be
  10:00–17:00. As written it reads as a seven-hour overnight window.
- **Museum Information appears only on Stop 1** and nowhere else. Either it
  belongs once at the top or on every stop; appearing once mid-structure looks
  like a bug.
- **The Epilog recap mixes stop names with description fragments:**

  > *"That's 8 stops — The Japanese, **Western collections influenced by Eastern
  > art**, Adoration of the Shepherds, **Mengs' light and shadow evoke intimacy**,
  > and Appeal to the Great Spirit, **bronze statue symbolizes reverence and
  > heritage**."*

  Three of the six items are not stop names. It also says "8 stops" then lists
  six things. This reads as machine output and would sound worse aloud.
- **The commercial lands with no transition:** the Treat Page and news-article
  pitch follow the recap immediately. After a tour about a donor's legacy, the
  jump to local discounts is abrupt.
- **Directions are content-free** — *"Continue through Museum of Fine Arts,
  Boston — next is Adam and Eve."* For a museum tour, gallery or floor would be
  the useful unit. Stop 7 is actually *outside* the building (the statue is on the
  lawn) and the directions do not say so.

---

## 7. What I would fix, in order

1. **LOCAL-370** (in flight) — selection. Nothing else can be judged fairly until
   the stops are the right objects.
2. **The injection-seam grammar.** New task. `stretches out before you` is a
   literal string appearing across venues; the appositive and dangling-connective
   breakage share the same root. A structural validator at the seam would catch
   most of it, and the empty-sentence work (LOCAL-356) is the natural home.
3. **Fact-grafting guard.** A pigment's 1704 invention should not attach to a 1957
   painting. There is a date-plausibility check available almost free: if an
   injected fact's date precedes the work's date by centuries, it is context, not
   description — and it must not be the stop's opening claim.
4. **Artist must be named.** Two of eight stops never say who made the work. For a
   museum tour that is a floor requirement, not a nicety.
5. **Thread coverage.** Only after 1–4: the spine promised a thread five of eight
   stops did not carry. SQ-S6b specifies coverage-proportional degradation; it is
   not enforcing.

---

## 8. Where I most want Michael's disagreement

- **Is 3 stops acceptable?** Once selection is fixed, this request yields three
  real works. I have been asserting that three honest stops beat eight invented
  ones. Michael stood in that show — is a three-stop tour worth opening the app
  for, or does it need the thread and the context to feel like a tour rather than
  three labels read aloud?
- **Stop 7 is outside the building.** *Appeal to the Great Spirit* stands on the
  Huntington Avenue lawn. Should an interior museum tour ever include an exterior
  work, or is that a scope violation?
- **The donor thread emerged on its own.** Given that, is provenance the right
  default spine for museum tours generally, or was it only compelling here because
  Bartlett happens to connect otherwise unrelated objects?
