# System evaluation — the real query mechanism, and two production bugs it exposed

**30 Serper + 3 Gemini = 33 retrievals · ~$0.042.** Raw evidence: `MATRIX_RAW_RESULTS.md`.

## 0. I had the wrong mechanism, and you caught it

D504/D505 used a `build_query()` I wrote that afternoon — `<artist> "<title>" <event-term>`. The real mechanism is `work_story_searcher.synthesize_queries`, LOCAL-406 extended by LOCAL-423, and its shape is **your own**, recorded as D366 on 2026-08-11:

> *"The query is framed for a standing visitor, not for a catalogue: 'What story can be told to visitors of {exhibition} about {work}, {credit_line}?' Ours ask '"Le Lézard aux plumes d'or" Joan Miró'. That difference is the whole reason our queries return auction listings."*

It reads eleven matrix fields and asks WHY, not WHAT. I bypassed it without checking whether it existed. Everything in D504/D505 about seeds still stands; the queries built from them do not.

## 1. Two production bugs, both live, both found by using the real path

### Bug 1 — LOCAL-423 has never run in production

`synthesize_queries` gates your two visitor-framed queries on `exhibition_name`. The stop record never carried it. **D426 diagnosed this on 2026-08-13 and it was still true nine days later**; `printer` and `collaborator` were missing too. Measured on Au Soleil du Plafond:

```
production stop record ->  4 queries, none naming a person but the artist
full matrix            -> 15 queries, incl. the donor's motive, the
                          collaboration's reason, the printer's workshop
```

Fixed: the record now carries `exhibition_name`, `printer`, `printed_by`, `collaborator`, `donor`, `local_title`.

### Bug 2 — every Gemini call has been truncated to ~60 characters

`story_leads._gemini` sets `maxOutputTokens: 600`. Current Gemini models spend that budget on **internal reasoning first**. Measured today:

```
maxOutputTokens 600   finishReason=MAX_TOKENS  thoughts=582  answer=56 chars
maxOutputTokens 4000  finishReason=STOP        thoughts=812  answer=751 chars
4000, thinking off    finishReason=STOP        thoughts=0    answer=720 chars
```

**This is why step 4 has reported `0 leads with cross-model agreement` on every run.** There was nothing to agree with — the second model's answer was being cut off mid-sentence. It also means D505's "Gemini lost decisively" was measuring a bug, not a model, and I withdraw it.

Fixed: 4000 tokens, thinking disabled, and all response parts joined rather than `parts[0]`.

### The effect, immediately

Gemini went from **0 of 3 stops eventful** (truncated) to **3 of 3**. Its Au Soleil answer, in full, is the story:

> The project was originally planned around 1916–1917 by the art dealer Léonce Rosenberg as a collaboration between Juan Gris and poet Pierre Reverdy.
> 
> The original plan called for Gris to create a corresponding illustration for each of Reverdy's twenty poems.
> 
> The initial effort was left incomplete because Gris died in 1927 at age 40, having completed only eleven of the intended illustrations.
> 
> Nearly thirty years after Gris's death, the publisher Tériade revived and reconceived the unfinished project in collaboration with Reverdy.
> 
> The book was finally published posthumously in 1955 as a tribute to Gris by Reverdy and Tériade.

Tériade, the 11 lithographs, 1927, 1955 — every load-bearing fact, and the MFA object record could not supply any of them.

## 2. Serper on matrix queries

| stop | queries | eventful | active | inert |
|---|---|---|---|---|
| Le Lézard aux plumes d’or (The Liz | 14 | **0** | 5 | 8 |
| Au Soleil du Plafond | 8 | **3** | 2 | 3 |
| Moses and Monotheism | 8 | **1** | 0 | 7 |

Fewer eventful verdicts than the seed queries produced — but the seed run's count included the false positives the relevance gate later removed, and these queries are asking a different question. What matters more: the matrix queries surface **named agents** the seed queries never reached — `Mourlot workshop history` returned the founding of the press in 1852, and `Sigmund Freud Salvador Dalí` returned the 1938 London meeting.

## 3. What I would conclude

1. **Your D366 framing was right and has never been tested**, because the field it depends on was never wired. It is wired now.
2. **Step 4 has never worked.** Not a design problem — a token budget.
3. **The two engines are complementary, not rivals.** Serper returns documents that name people; Gemini, given the whole matrix and asked your question, returns a narrative. Au Soleil's story came out of Gemini whole.
4. **Still nothing wired into production** beyond the two bug fixes, which are both in production paths and both reversible.
