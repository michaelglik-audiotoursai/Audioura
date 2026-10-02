# Round 2 — regenerated with your CHURCH_tour_3 fixes (2026-09-18)

Six tours, four stops each. **Total $1.06.** All in this folder; round 1 is one level up.

| | round 1 | round 2 |
|---|---|---|
| church — dates / named people / stops | 13 / 6 / **3** | 9–13 / 5–6 / **4, 4, 4** |
| Logan — dates / named people | 4 / **0** | 3–4 / **0** |

## Your six comments — what happened

**1. "Founded in 1868 by St." — fixed.** Zero truncated-title fragments in any of the six.
Every gate split sentences on `(?<=[.!?])\s+` with no abbreviation guard, so `St. Mary's` became
two sentences and a gate dropped the half with the name. The old splitter shattered
`The Rev. Dr. J. F. Smith` into **five**. Five gate modules now route through an
abbreviation-safe splitter.

**2 & 4. Repeats — fixed, and the filter you remembered did exist.** It fired and then did
nothing: D534 reported *"Stop 2 / 3 / 4 repeat … will regenerate with them banned"*, then
`LOCAL-487` applied `cap=1` and retried only stop 3. Two of the three shipped their repeats and
that log line was false. Deletion is now applied to whatever the capped retries cannot reach —
free and safe, because the content still exists at the earlier stop. In round 2 it removed:

```
stop 2: Just days later, more than 850 parishioners filled the nave...
stop 3: ...the day of June 15, 1995, when Mother Teresa visited...
```

Matching is by **person + year**, not word overlap: *"Mother Teresa visited"* and *"Saint Mother
Teresa of Calcutta held a Mass here in June 1995"* share only 0.25 Jaccard but are one episode.

**3.** Unchanged — that stop was already doing its job.

**5. Added.** One line, keyed on the venue class so a church is offered other churches rather than
a generic suggestion. (`CHURCH_1` still shows the generic version — it generated before that fix.)

**6. Now present.** `CHURCH_1` stop 4: the 1870s crypt served as the worship space while the
parish raised funds for the upper church, **completed in 1881** — when, by whom, how long. That is
the causal chain (why it exists / who created it / who paid) reaching the listener.

**Also fixed:** all six tours deliver **4 stops**. Round 1's church lost one to a scope check that
ruled the Pulpit "outside the bounds of Our Lady Help of Christians" because it sits at the
church's own address.

---

## Logan is unchanged, and it is the one thing you have not ruled on

**Zero named people in all three, again.** The causal chain finds the material — Mayor Curley's
1922 petition, Governor Cox signing Chapter 404, the 1969–73 tower by Desmond & Lord with
Yamasaki, Perini as builder — and it is seeded onto the stops. Then `LOCAL-472` strips it:

```
UNGROUNDED entity stop='Security Checkpoint' entity='Boston Logan International Airport'
UNGROUNDED entity stop='Control Tower'        entity='Boston Logan'
```

It is deleting **the airport's own name at the airport's own control tower**, 5–7 times per tour.
A building part cannot satisfy "this entity is concretely linked to this stop".

Not one of Curley, Cox, Yamasaki, Perini, Jeffries, Wood Island or Neptune Road appears in any of
the three delivered tours.

**This is D579 and it is your call, because LOCAL-472 is the anti-fabrication gate** — the one
D564 said must not be weakened, and part of why the Los Angeles archbishop was an exception rather
than the norm. My proposal stays narrow: **exempt only facts seeded with sources, keep the gate at
full strength on anything the writer invents.** That is not weakening it; it is stopping it from
auditing evidence we already grounded.

## Still open, smaller

- The closing says *"That's 4 stops and 2 kilometres"* for four stops **inside one church**.
  Distance logic written for places in an area, applied to parts of a building (D578 family).
