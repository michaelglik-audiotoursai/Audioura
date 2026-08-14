# The two stories, verbatim — judge them yourself

Stop 2, *Moses and Monotheism*, MFA. Both runs live, 2026-08-14, minutes apart.
Nothing below is edited, trimmed or paraphrased. My scores are at the bottom, on
purpose — read the stories first.

The ONLY difference between the runs is the `credit_line` (story keyword).
Everything else — the ladder, the sourceable set, the chosen subject (Salvador
Dalí) — came out byte-identical.

---

## PHRASE

**credit_line:** `The convergence of narrative and imagery in this exhibit`

```
In 1938, Salvador Dalí, a devoted follower of Sigmund Freud, met the psychoanalyst in London when Dalí was 34 and Freud was 81. This encounter was the only meeting between the surrealist artist and the father of psychoanalysis. Decades later, in 1974-75, Dalí created "Moses and Monotheism," a work that reflects his ongoing engagement with psychoanalytic themes. The piece was made during this period, showcasing Dalí's continued exploration of complex ideas.
```

460 characters · 4 sentences · corpus 3885 chars from 5 kept snippets (of 46 retrieved)

**Sources it was allowed to use:** `academia.edu`, `artnet.com`, `academia.edu`, `artic.edu`, `archive.org`

---

## BASELINE

**credit_line:** `Sigmund Freud`

```
In July of 1938, Salvador Dalí, at the age of 34, had his first and only encounter with Sigmund Freud, who was 81, at Freud’s home in London. Dalí, a devoted admirer of Freud, found the meeting to be a fittingly bizarre experience. Years later, in 1974, Dalí created illustrations for Freud's "Moses and Monotheism." The illustrations were part of a series printed for the text.
```

378 characters · 3 sentences · corpus 984 chars from 5 kept snippets (of 47 retrieved)

**Sources it was allowed to use:** `freud.org.uk`, `openculture.com`, `freud.org.uk`, `freud.org.uk`, `mfa.org`

---

## The material the BASELINE arm was written from

This is the whole corpus — the writer may use nothing else. On disk at
`story_lab_state/pipe_moses_and_monotheism.txt`.

```
When Dalí met Freud - London. Salvador Dalí's first and only encounter with Sigmund Freud was fittingly bizarre. The pair met on 19 July 1938 at Freud's home in London, as a ...
When Salvador Dali Met Sigmund Freud, and Changed .... Salvador Dalí, who considered himself a devoted follower of Freud. took place in July of 1938, at Freud's home in London. Freud was 81, Dali 34.
Freud, Dalí and the Metamorphosis of Narcissus. Salvador Dalí was a passionate admirer of Sigmund Freud and finally met him in London on July 19th 1938. This year 2018 marks the 80th anniversary of this event ...
When Dalí met Freud - London. The surrealist icon met with the father of psychoanalysis on 19 July 1938. · Salvador Dalí's first and only encounter with Sigmund Freud was ...
Advance Exhibition Schedule | Museum of Fine Arts Boston. Picasso, Miró, Dali: Unbound ... Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...
```

**The PHRASE arm's corpus is gone, and that is a defect, not an omission.**
`story_pipeline.run_stop` writes the corpus to a path keyed only on the stop title,
so the baseline run overwrote the phrase run's copy eleven minutes later. Two runs of
the same stop cannot both be inspected afterwards. Worth fixing before we run more
comparisons — right now every A/B destroys half its own evidence.

---

## My scores — read after, not before

| | credit_line | index | Historic | Detail | Social | validate |
|---|---|---|---|---|---|---|
| PHRASE | The convergence of narrative and imagery in  | **67** | 44 | 0 | 42 | TRUE_TO_SOURCES |
| BASELINE | Sigmund Freud | **57** | 51 | 6 | 45 | TRUE_TO_SOURCES |

Both passed grounding with zero ungrounded sentences, so `validate_story` says
every sentence in both traces to the corpus.

`valuation_index` = sentences + agency verbs + stakes markers + groundedness.
It has no penalty for vagueness. That is my read of why it put PHRASE ahead; you
may disagree, which is the point of putting the text above the numbers.
