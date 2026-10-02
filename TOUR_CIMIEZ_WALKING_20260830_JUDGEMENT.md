# Judgement — Walking tour, Cimiez District: 6 of 6, and one stop that should not be there

**2026-08-30.** Tour: `TOUR_CIMIEZ_WALKING_20260830.md`. 1,918 words, story gate **4 of 6**.

---

## Michael's two complaints, both answered

### "Asked for 6 stops but got back only 4. Why?"

The scope check was **right**: it removed Villa Léopolda (Villefranche-sur-Mer) and the Matisse
Chapel (Vence), both genuinely outside Cimiez. **What was missing was the recovery** —
replenishment existed and worked, but had `restaurant` hard-coded, so a walking tour that lost
stops had nothing to replace them with.

Now general. **6 of 6 delivered, 6/6 within scope.**

### "I do not hear good stories for each stop"

**You were right, and the gate agreed: 2 of 6 passed.** Your follow-up — *"actually stop 3 is
excellent"* — was also right, and both fit the same number.

The cause was the same guard. **Not one story-retrieval line appeared in that run**, because the
lore fetch also sat inside the restaurant branch. Gemini had the material all along: the 1543 siege
of the monastery, Saint Pontius in the Cemenelum arena, Fray Marcos de Niza who left Nice and
explored the American Southwest.

This run: **46 Gemini facts across 6 stops**, 45 of them high-confidence. Story gate **4 of 6**.

> *"In 1546, a pivotal moment unfolded when Franciscan friars negotiated a property swap with the
> Benedictine monks of Saint-Pons Abbey, acquiring a small chapel…"*
> *"From 1974 to 2010, the Nice Jazz Festival brought new life to these ruins, where the music of
> the era resonated among the ancient stones."*

**Why that instruction was misread, since it matters for future ones.** You said *"restaurants
only"* and gave museums as the reason. I implemented the literal words and took walking tours out
along with museums. Restaurants and places now both get the story question; **museums remain
excluded on a separate path** — the protection you asked for is intact and was never at risk.

## The defect in this run: Villa Léopolda is back

**`PHASE 5.6: 6/6 stop(s) within scope`** — but Villa Léopolda **is in Villefranche-sur-Mer**, not
Cimiez. The previous run removed it with `conf=high` and this one kept it.

**The scope check is not deterministic**, and this time it passed a stop it had correctly rejected
before. It is a per-stop LLM judgement with no memory between runs, so a stop deleted yesterday can
return today.

That is worth fixing at the same place the closure problem was fixed: **a stop rejected for being
outside the requested area is a fact about geography, not an opinion** — it belongs in a corpus like
`known_closed_venues.json`, so a rejection sticks. Villa Léopolda's own text in this tour gives it
away: *"between 1929 and 1931, on land once belonging to King Leopold II of Belgium"* — accurate,
and about a villa the listener would have to leave the district to see.

## Also worth noting

- **The proposer's prompt now warns** that a famous place in the next town is the commonest
  mistake — exactly what put Villa Léopolda in the candidate list. It did not prevent Phase 3A from
  proposing it, because Phase 3A uses a different prompt.
- **Two stops still fail the story gate** — Musée Marc Chagall and Musée National du Sport — despite
  7 and 8 retrieved facts each. The material arrived; the narration did not build a three-sentence
  arc from it. Same shape as the earlier restaurant work before the "tell two episodes properly"
  instruction, which is restaurant-only.
- **Practicals stay restaurant-only**, correctly: opening hours and a price band are meaningless for
  a Roman ruin.

## Recommendation

**Usable, with one edit: drop or replace Villa Léopolda.** It is a real place with real stories, but
it is not in Cimiez and a listener walking the district cannot reach it.

**Next, in order:**
1. **Make scope rejections stick** — a per-run LLM judgement lets a correctly-deleted stop return.
2. **Extend "tell two episodes properly" beyond restaurants** — it is what took the restaurant tour
   from headlines to stories, and the two failing museums here would benefit identically.
3. `closure_scan` — still three false positives against zero unique true positives. Demote to
   advisory.
