# credit_line worksheet — `TOUR_MFA_20260812_2030.txt`

Offline and deterministic — no LLM, no search, no cost.
Re-run with `python3 story_worksheet.py TOUR_MFA_20260812_2030.txt`.

`credit_line` is **the story keyword**: the person the story gets built
around, picked out of the stop's own sentences. A story keyword that is not a
person cannot produce a sentence tying a person to the object.

Handle states, for reading the ladders below:
**FLAT** established but carrying no stakes (the best place to attach a story) ·
**MENTIONED** named, barely used · **DANGLING** named once and dropped ·
**DEVELOPED** already carries the stop, so never a keyword.

---

## Stop 1 — Le Lézard aux plumes d’or (The Lizard with Golden Feathers)

### credit_line: **book**
`DERIVED` · via `story_opportunity_scan/MENTIONED`

| slot | value | status |
|---|---|---|
| `canonical_title` | Le Lézard aux plumes d’or | STRUCTURAL |
| `english_title` | The Lizard with Golden Feathers | STRUCTURAL |
| `artist` | Joan Miró | CLAIMED |
| `publisher` | Louis Broder | CLAIMED |
| `printed_by` | Mourlot Frères | CLAIMED |
| `medium` | Picasso, Miro, Dali: Unbound | STRUCTURAL |
| `venue` | Museum of Fine Arts, Boston | STRUCTURAL |
| `credit_line` | book | DERIVED |

<details><summary>the people this stop names, and why each was or was not chosen</summary>

| person named | state | sentences | struck off because |
|---|---|---|---|
| Le Lézard | MENTIONED | 6 | already the `canonical_title` slot |
| At Le Lézard | MENTIONED | 6 | starts with an article/preposition |
| Joan Miró | MENTIONED | 5 | already the `artist` slot |
| The Lizard | MENTIONED | 4 | already the `english_title` slot |
| Golden Feathers | MENTIONED | 4 | already the `english_title` slot |
| Au Soleil | MENTIONED | 2 | starts with an article/preposition |
| Louis Broder | MENTIONED | 2 | already the `publisher` slot |
| Fine Arts | MENTIONED | 2 | already the `venue` slot |
| Huntington Ave | DANGLING | 1 | — |
| The Picasso | DANGLING | 1 | starts with an article/preposition |
| In Gallery | DANGLING | 1 | starts with an article/preposition |
| Mourlot Frères | DANGLING | 1 | already the `printed_by` slot |
| Boris Fridman | DANGLING | 1 | — |

</details>

**One sentence tying this person to THIS object:**

> _(write it here)_

---

## Stop 2 — Moses and Monotheism

### credit_line: **Sigmund Freud**
`DERIVED` · via `story_opportunity_scan/FLAT`

| slot | value | status |
|---|---|---|
| `canonical_title` | Moses and Monotheism | STRUCTURAL |
| `english_title` | Moses and Monotheism | STRUCTURAL |
| `artist` | Salvador Dalí | CLAIMED |
| `publisher` | The Hogarth Press | CLAIMED |
| `printed_by` | — | ABSENT |
| `medium` | Picasso, Miro, Dali: Unbound | STRUCTURAL |
| `venue` | Museum of Fine Arts, Boston | STRUCTURAL |
| `credit_line` | Sigmund Freud | DERIVED |

<details><summary>the people this stop names, and why each was or was not chosen</summary>

| person named | state | sentences | struck off because |
|---|---|---|---|
| Salvador Dalí | FLAT | 6 | already the `artist` slot |
| Sigmund Freud **← chosen** | FLAT | 6 | — |
| The Hogarth Press | MENTIONED | 2 | already the `publisher` slot |
| Monotheism

Address | DANGLING | 1 | — |
| Huntington Ave | DANGLING | 1 | — |
| Torf Gallery | DANGLING | 1 | — |
| Fine Arts | DANGLING | 1 | already the `venue` slot |
| Au Soleil | DANGLING | 1 | starts with an article/preposition |

</details>

**One sentence tying this person to THIS object:**

> _(write it here)_

---

## Stop 3 — Au Soleil du Plafond

### credit_line: **Pierre Reverdy**
`DERIVED` · via `story_opportunity_scan/MENTIONED`

| slot | value | status |
|---|---|---|
| `canonical_title` | Au Soleil du Plafond | STRUCTURAL |
| `english_title` | — | ABSENT |
| `artist` | Juan Gris | CLAIMED |
| `publisher` | Tériade | CLAIMED |
| `printed_by` | — | ABSENT |
| `medium` | Picasso, Miro, Dali: Unbound | STRUCTURAL |
| `venue` | MFA, Boston, MA | STRUCTURAL |
| `credit_line` | Pierre Reverdy | DERIVED |

<details><summary>the people this stop names, and why each was or was not chosen</summary>

| person named | state | sentences | struck off because |
|---|---|---|---|
| Juan Gris | MENTIONED | 5 | already the `artist` slot |
| Au Soleil | MENTIONED | 2 | already the `canonical_title` slot |
| Pierre Reverdy **← chosen** | MENTIONED | 2 | — |
| Plafond

Address | DANGLING | 1 | — |
| Huntington Ave | DANGLING | 1 | — |
| Le Lézard | DANGLING | 1 | starts with an article/preposition |
| The Treat Page | DANGLING | 1 | starts with an article/preposition |

</details>

**One sentence tying this person to THIS object:**

> _(write it here)_

---

