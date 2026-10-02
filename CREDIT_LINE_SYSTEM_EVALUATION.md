# System evaluation — 37 credit_lines, two engines, and one serious finding

**37 Serper + 37 Gemini = 74 retrievals · ~$0.259 · 142s.** Budget $13; used 2%.

Raw evidence: **`CREDIT_LINE_RAW_RESULTS.md`** — 3,730 lines, every result, every sentence, every gate verdict.

## 1. THE FINDING: Gemini reproduced a story you already ruled unattested

On Le Lézard aux plumes d'or, Gemini returned — in **eight separately-worded answers** — the story of a 1967 edition destroyed over a paper-chemistry defect and reprinted in 1971:

> *Broder and Miró discovered a paper manufacturing defect that caused chemical reactions and altered the ink colors.*  
> *Because of this flaw, Broder and Miró made the decision to abandon the 1967 run and destroy the printed sheets.*  
> *Broder made the costly decision to reject and destroy the entire defective print run rather than release a substandard edition.*

**This is D366, 2026-08-11, verbatim.** You produced that story by hand, LEAD checked it against 67 snippets, and the ruling was:

> *"Of the 67 snippets we hold for that stop, ZERO contain 'scrap', 'destroy', 'bleed' or 'chemistry'; four describe 1967 sheets that plainly still exist and are for sale."*

**Re-measured today on fresh retrieval: 0 of 117 Le Lézard snippets mention destruction, defect, scrapping, chemicals or abandonment.** Serper returned **zero eventful material** for that stop across all 16 credit_lines. Gemini returned the dramatic story eight times.

**Only 2 of 37 Gemini answers carried a bracketed source at all**, despite the prompt demanding one per fact and offering `NO RELIABLE INFORMATION` as an out. It used that out once.

This is your own standing rule from D366, now demonstrated on a second model:

> *"A confident, well-written falsehood about a named person is the worst output this pipeline can produce, because no listener can detect it."*

**And the relevance gate cannot catch it.** The sentences name Miró and Broder correctly, concern the right work, and pass cleanly. Relevance is not veracity. What would catch it is D366's own ruling — **verification must gate selection, not follow it** — and that is not built.

## 2. The two engines are opposites, and the reason matters

| | inert | active | eventful |
|---|---|---|---|
| Serper (compiled keywords) | 26 | 9 | **2** |
| Gemini (your question verbatim) | 9 | 10 | **18** |

Read naively that says Gemini wins 18–2. Read with section 1, it says **Gemini produces narrative on demand whether or not the narrative exists.** Serper's 2 eventful verdicts are both Au Soleil, and both are the Gris death — which is real, corroborated across independent sources, and in the raw file.

**Serper's silence on Le Lézard is not failure. It is the correct answer.** The material genuinely is catalogue prose; that is D492's finding, and it holds.

## 3. Per stop

| stop | Serper eventful | Gemini eventful | verdict |
|---|---|---|---|
| Le Lézard aux plumes d’or (The | 0/16 | 8/16 | Gemini fabricating; Serper correctly silent |
| Au Soleil du Plafond | 2/12 | 10/12 | both real — Gris dies 1927, 11 of 20 done, Tériade revives 1955 |
| Moses and Monotheism | 0/9 | 0/9 | neither found an event; the 1938 Freud meeting is only `active` |

**Au Soleil is corroborated by both engines independently** — Serper from museum and dealer pages, Gemini from search. Same year, same age, same count of completed illustrations. That is the cross-model agreement D482 wanted, and it is the first time we have seen it.

## 4. The Serper encoding

37 unique queries from 37 credit_lines — no duplicates, unlike D504's run where a quarter collided. The compiled form works as designed:

```
"Au Soleil du Plafond" Reverdy Gris why linked
"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 revolutionized
```

But **the credit_line barely moves the result.** All 16 Le Lézard queries share `"work" Mourlot Broder Fridman why 1971` and differ only in a trailing content word, so they return near-identical documents. The agents dominate. That is why Serper's Le Lézard column is flat.

Gemini's questions were all 37 distinct and it responded differently to each — the question form USES the credit_line, the keyword form mostly does not.

## 5. What I conclude

1. **Your D366 framing is right for Gemini and the compiled form is right for Serper.** Both confirmed.
2. **Gemini cannot be trusted unverified.** It reproduced, unprompted and eight times over, the precise fabrication you caught by hand a fortnight ago. Wiring it into production without verification-before-selection would ship that story to a listener.
3. **Verification-gating selection (D366's amendment) is now the highest item on the list.** It outranks more retrieval; we have plenty of material and no way to tell true from invented.
4. **The credit_line needs to reach the Serper query harder** — right now the agents crowd it out.

Nothing wired into production from this run.
