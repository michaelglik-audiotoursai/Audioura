# Judgement — French Riviera biking tour, 5 requested, **2 delivered**

**2026-08-27**, build `18fcd07`. Tour: `TOUR_RIVIERA_BIKING_20260827.md`.
Requested: `"Biking tour in French Riviera with a stop at Hippodrome de la Cote d'Azur starting from Nice, France"`, **5 stops**.

---

## Verdict: do not accept. Three of five stops were deleted, and nothing told the listener.

This is a bad tour, and it is bad in a way worth understanding: **every fix made yesterday was on
the museum and exhibition path.** This request took the walking/biking path, which has none of
that protection. The Palais Lascaris result did not transfer.

| | |
|---|---|
| Stops requested | 5 |
| **Stops delivered** | **2** |
| Listener told about the shortfall | ❌ **nothing** |
| Both stops probably the same racecourse | ⚠️ yes — see below |
| Cost / time | $0.1244 · 26,106 tokens · 3m 37s |

---

## The causal chain, traced end to end

**1. The request was misread at the very first step.** Two strippers ran in sequence:

```
[BLOCKER1] Stripped 'tour'          → "Biking  in French Riviera with a stop at Hippodrome..."
[LOCAL-46] Stripped transport words → "in French Riviera with a stop at Hippodrome..."
[Bug2Fix]  tour_type='biking' suppressed for intent analysis
```

The intent model was then asked what this tour is about, having been shown a sentence with the
word *Biking* removed **and** with the explicit `tour_type='biking'` withheld. It answered
`"poi_type": "horse racing tracks"`.

**That is the whole disaster in one line.** The request names ONE hippodrome as a stop on a
Riviera bike ride. The system concluded the tour is *about hippodromes*.

*(The transport mode itself survived — `[TRANSPORT] mode=bike, keyword=bike, intent=on_foot` — because
`_detect_transport_mode` reads the original string. So the prose says "cycle". Only the SUBJECT
was lost.)*

**2. Phase 3A duly returned five racecourses**, four of which I can find no evidence for:

```
Hippodrome de la Cote d'Azur   @ Mandelieu-la-Napoule   ← real, but WRONG ADDRESS (it is in Cagnes-sur-Mer)
Hippodrome de la Plage         @ Cagnes-sur-Mer         ← almost certainly the real one, renamed
Hippodrome de la Siagne        @ Mandelieu-la-Napoule
Hippodrome de la Turbie        @ La Turbie
Hippodrome de Beaulieu-sur-Mer @ Beaulieu-sur-Mer
```

The existence gate agreed and was ignored: `EXISTENCE-GATE LOG_ONLY — 3/5 verified, 2 would be
dropped`, with `[UNVERIFIED] 'Hippodrome de la Plage' — no evidence`. **It is in LOG_ONLY mode, so
it dropped nothing.** The stop it could not verify is one of the two that shipped.

**3. Then the scope check deleted three of them** — and this is the second-order bug:

```
X SCOPE-CHECK REMOVED 'Hippodrome de la Siagne'        — outside 'Hippodrome de la Cote d'Azur'
X SCOPE-CHECK REMOVED 'Hippodrome de la Turbie'        — outside 'Hippodrome de la Cote d'Azur'
X SCOPE-CHECK REMOVED 'Hippodrome de Beaulieu-sur-Mer' — outside 'Hippodrome de la Cote d'Azur'
```

**The Hippodrome was treated as the tour's boundary rather than as one stop inside it.** The
request says "*with a stop at* Hippodrome de la Cote d'Azur" — it is a waypoint on a French
Riviera ride. The scope resolver made it the container, so every other stop was correctly judged
"outside" it and removed. The logic is sound; the premise was wrong.

**4. And the listener is told none of this.**

```
[LOCAL-394] Stop count invariant: OK (2 selected == 2 delivered)
```

**This is D530 exactly, on a different path.** `LOCAL-394` compares SELECTED against DELIVERED, so
it reports OK on a tour that lost 60% of its stops. D530 fixed this for the exhibition path by
adding `_LAST_STOP_COUNT_NOTICE` and the `⚠️ LISTENER ASKED FOR N STOPS` line — **neither fires
here.** There is no shortfall message anywhere in this run. A listener asking for a 5-stop ride
gets 2 and is told nothing.

---

## What the tour actually says

**Both stops are almost certainly the same racecourse.** Stop 1 "Hippodrome de la Cote d'Azur" is
given the address *2 Avenue Paul Delorme, Mandelieu-la-Napoule*; the real Hippodrome de la Côte
d'Azur is in **Cagnes-sur-Mer**. Stop 2 "Hippodrome de la Plage" is placed at *Avenue de la Plage,
Cagnes-sur-Mer* — which is where the real one is. So the tour appears to send the rider 21 km from
a wrong address to the right one, under a different name, and calls it two stops.

**One fabrication was caught and dropped**, which is the system working:

```
[LOCAL-229] BLOCKED Stop 1: claim='1960 ... officially opened in December 1[9]60'
            contradicted_by='with temporary facilities in 1952' → DROPPED
```

**Yesterday's D535 fixes did apply and are visible.** The opening is two sentences and does not
pre-tell the stops. No "as you reflect…" instruction appears. The prose says *cycle*, not *walk*.
Those were not the problem here.

**A cosmetic but misleading log line:** `GEO-CHECK: all 5 stops within walking distance (max leg
42.26 km, total 90.74 km)` — this is a bike tour, and the message is hardcoded to say "walking".
The check itself used the bike limits (`_TRANSPORT_TOTAL_HARD_KM[transport_mode]`), so the verdict
is not wrong, only the wording. A 42 km leg is still a lot to present without comment.

---

## Fixes, in the order I would do them

1. **Do not strip the subject out of the request.** `[BLOCKER1]` and `[LOCAL-46]` strip words to
   help *area resolution*, and the stripped string is then reused for *intent*. Intent must see
   the original sentence. This one change fixes the poi_type error at its source.
2. **"with a stop at X" makes X a waypoint, not a scope.** The scope resolver must not promote a
   named stop to the tour's boundary. Until then, any request phrased this way loses every other
   stop.
3. **Extend D530's shortfall notice to every path.** It exists and works; it is wired only to the
   exhibition branch. A listener who asks for 5 and gets 2 must be told, whatever the tour type.
4. **`LOCAL-394` should compare REQUESTED against delivered**, not selected against delivered. It
   has now reported OK on two tours that lost most of their stops (D530's, and this one).
5. **Consider turning the existence gate off LOG_ONLY for non-museum tours.** It correctly flagged
   `Hippodrome de la Plage` as having no evidence, and that stop shipped.
6. Cosmetic: the GEO-CHECK "walking distance" wording.

**What I did not do:** I have not attempted these. They are a day's work on a path none of
yesterday's changes touched, and shipping half of them untested is how the guard-that-cannot-fail
problems started. **The honest position is that the biking path is roughly where the museum path
was before yesterday.**

**No score.** A 2-stop tour against a 5-stop request is not a quality measurement; it is a
delivery failure.
