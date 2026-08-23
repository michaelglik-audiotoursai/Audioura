# Evaluation — the challenge loop, and which story to use

**123 Serper + 37 Gemini · ~$0.345 · 184s.** All 37 stories with their evidence: `ADJUDICATED_STORIES.md`.

## 1. What the loop did to the claims

| verdict | count | meaning |
|---|---|---|
| CONFIRMED | **94** | a retrieved source supports it |
| CORRECTED | **9** | Gemini's round-1 claim was wrong and it said so |
| DISPUTED | **32** | two sources genuinely disagree — kept as material |
| UNATTESTED | **143** | nothing retrieved supports it |

**143 of 278 claims (51%) had no retrieved support.** That is the number that matters. Round 1 asserted them all with equal confidence, and without the challenge step every one would have reached a listener indistinguishable from the confirmed ones.

**11 of 37 stories tell a disagreement out loud**, as you asked:

> *While one source records a publication date of 1948, other records place its official release in Paris in 1955.*  
> *Sources disagree on the timeline: some records date initial plates to 1967 while others place the edition entirely in 1971.*

## 2. Serper is not useless — its job changed

In D507 Serper was asked to *answer the question* and returned 2 eventful of 37. Here it *supplies the evidence a claim is judged against*, and on that job it produced **17 to 24 relevant sentences per credit_line** — enough to confirm 94 claims and correct 9.

The division of labour that fell out of this: **Gemini narrates, retrieval adjudicates.** Neither does the other's job well. Asking Serper for a story gets catalogue prose; trusting Gemini unchallenged gets confident invention.

## 3. Which story to use

Ranked by: material kind first, then confirmed claims, then whether it tells a disagreement, then fewest unattested.

### Le Lézard aux plumes d’or (The Lizard with Golden Feathers)

**Recommended: credit_line 10.2** — kind `active`, 4 confirmed, 4 unattested

> In 1967, Joan Miró and printer Celestin completed a first edition of lithographs to accompany a poem written by Miró for publisher Louis Broder. Shortly after printing, Miró and Broder discovered an error in the paper that distorted the lithographs. While the 1967 first edition was largely lost or abandoned, individual surviving plates from that run still surface in collections today. Miró went back to work to produce a different, completed edition, which Broder published on Rives paper in 1971.

### Au Soleil du Plafond

**Recommended: credit_line 3.1** — kind `eventful`, 5 confirmed, 5 unattested

> In 1916 or 1917, art dealer Léonce Rosenberg commissioned a collaborative book titled *Au Soleil du Plafond*, pairing twenty poems by Pierre Reverdy with illustrations by Juan Gris. The project stalled during World War I and remained unfinished when Gris died in 1927, leaving behind eleven gouaches (though one record describes him as having completed half of the twenty planned illustrations). The son kept the eleven gouaches as his father had left them until publisher Tériade (Éditions Verve) finally brought the work to realization in 1955. For that release, printer Mourlot Frères produced the eleven lithographs after Gris's original compositions to accompany Reverdy's text.

### Moses and Monotheism

**Recommended: credit_line 2.1** — kind `eventful`, 2 confirmed, 4 unattested

> In 1939, only months before his death, Sigmund Freud published *Moses and Monotheism*, his final and most controversial book. Decades later, Salvador Dalí produced an illustrated edition containing Freud's text accompanied by ten engravings and additional drawings. While some records date Dalí's portfolio to 1974, other sources date its publication to 1975.

## 4. My reservations, plainly

**Le Lézard's best story is still weak.** Its top candidate is `active`, not `eventful`, and it contains *"printer Celestin"* — a name that appears in no source I can find and which the adjudicator let through as CONFIRMED. The loop reduced invention; it did not eliminate it.

**Au Soleil is genuinely good and was always going to be.** Rosenberg commissioning it, the war stalling it, Gris dead at forty with eleven of twenty done, the son keeping the gouaches, Tériade reviving it. Every load-bearing fact confirmed against a source, and the 1948/1955 disagreement told rather than hidden.

**A quarter of the claims are unattested and the story still gets written.** The prompt tells Gemini to drop them, and mostly it does — but nothing mechanically enforces it. A gate that checks the delivered story against the CONFIRMED list is the obvious next guard, and it does not exist.

## 5. How production should decide

The order the evidence supports:

1. **Generate the credit_line list** from the stop's own prose (D503) — cheap, no API calls.
2. **One Gemini round per credit_line, sources captured** (D508). Cap it: the top 3-4 credit_lines by seed rank, not all 12-16. Cost is ~$0.006 each.
3. **Challenge the checkable claims** with Serper queries built from the claim's terms (D509). ~4 queries per credit_line, $0.004.
4. **Adjudicate and write** in one Gemini call against the retrieved evidence.
5. **Select** on: `eventful` beats `active`; more CONFIRMED beats fewer; a told disagreement is a bonus, not a penalty; any story whose sentences are not traceable to a CONFIRMED or CORRECTED claim is rejected.

**Cost per stop at this shape: about $0.05.** A four-stop tour is $0.20 — against the ~$0.16 a tour already costs to generate. That is affordable and the measurements above are what it buys.

**What I would NOT do yet:** wire this into production. The `Celestin` case shows a fabricated name surviving the loop and being marked CONFIRMED. Until a mechanical check binds each delivered sentence to an adjudicated claim, this is a strong research pipeline and not a safe generator.
