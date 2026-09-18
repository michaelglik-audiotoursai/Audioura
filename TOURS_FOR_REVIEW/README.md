# Six tours for review — 2026-09-18

Generated with the D571 venue-parts chain (Q1 what is this / Q2 what does that kind consist of /
Q3 which parts does this one have), with stops **selected by story and ordered by walk**.

Open the `.txt` files in VS Code. **Read the church tours first — they work. The Logan tours do
not, and I know why.**

| file | stops | cost | length |
|---|---|---|---|
| `CHURCH_tour_1.txt` | Nave · Stained Glass · Altar *(Pulpit deleted — see below)* | $0.1612 | 7.6k |
| `CHURCH_tour_2.txt` | Nave · Stained Glass · Altar · Crypt | $0.1939 | 10.0k |
| `CHURCH_tour_3.txt` | Nave · Stained Glass · Altar · Side Chapels | $0.2636 | 10.3k |
| `LOGAN_tour_1.txt` | Check-In Hall · Security · Jetbridge · Control Tower | $0.1175 | 6.3k |
| `LOGAN_tour_2.txt` | Check-In Hall · Security · Concourse · Control Tower | $0.1227 | 6.9k |
| `LOGAN_tour_3.txt` | Check-In Hall · Security · Jetbridge · Control Tower | $0.1611 | 8.4k |

**Total for all six: $1.02.** Stop selection is now stable across runs, unlike the old path (D570).

---

## The verdict, measured

| | dates cited | named people |
|---|---|---|
| church 1 / 2 / 3 | 13 / 9 / 11 | **5 / 2 / 4** |
| Logan 1 / 2 / 3 | 2 / 2 / 0 | **0 / 0 / 0** |

**The church tours have human history. The Logan tours have none at all.**

### The church worked

Real, specific, and about *this* building: the 1881 Irish immigrant workers and the anti-Catholic
prejudice they faced; Voice of the Faithful meeting here 2002–2005 after the Boston clergy
scandal; the 2005 overnight sit-in against Father Walter Cuenin's removal.

**And D567's wrong-facts bug vanished** — with every stop inside one building there is no sibling
parish to misattribute Cuenin to, and he is now correctly placed here. A geographic-refutation scan
(D577) over all six tours found **zero refuted claims**.

### Logan did not, and the approach is why

> *"The Control Tower serves as the airport's nerve center… 2,384 acres, featuring six runways and
> four passenger terminals… an emblem of precision… the complex dance of technology and human
> expertise."*

That is the glossary tour Michael predicted. **A church's parts carry human history — who preached
from this pulpit, who paid for that window. An airport's parts are machinery.** Logan's stories
(Kuraly, the 1968 Maverick Street Mothers, Richard Reid, Wood Island Park — the tour 423 material
Michael liked) attach to **events at the airport**, not to **parts of the airport**.

**The immediate cause is a gap I left.** `venue_parts.py` contains both story questions —
`venue_story_prompt` (why was it built, who paid, who designed, what is it the largest of) and
`part_story_prompt` (Michael's own: *who came to this part, what did they do, what were they hoping
to achieve*) — and **neither is wired into generation**: `grep -c` in `generate_tour_text.py`
returns **0**. The chain currently picks good stops and then lets the ordinary corpus machinery
write them, which for "Control Tower" returns an infrastructure fact sheet.

So the Logan result is **not evidence the approach fails** — it is evidence that half of it is not
plugged in yet.

---

## Known defects visible in these files

1. **A stop was deleted for being inside its own building** (D578). Church 1 lost the Pulpit:
   *"the Pulpit is located at 573 Washington St, Newton, MA — outside the bounds of Our Lady Help
   of Christians."* That is the church's own address. Third gate to break on building parts, after
   centroid collapse (D572) and the missing indoor descriptor (D576).
2. **A truncated sentence ships** in `LOGAN_tour_3.txt`: *"the hustle and hum of over 43.Boston
   Logan spans 2,384 acres"* — a number was cut and two sentences ran together.
3. **`LOCAL-472` correctly flagged a generic paragraph** ("applicable to any historic church") and
   *deleted* the stop. Under D577 the right response is to hedge and keep.

---

# UPDATE — your causal chain, tested (2026-09-18)

You objected that ranking parts by "which is most interesting" was either venue-specific or
directionless, and proposed instead:

> *Building tour → what was the reason/cause for this building to exist → who created it →
> who paid for it → who visited it*

**Nothing was hardcoded for St Nicholas** — the old ranking was one generic prompt with the venue
name interpolated. But your deeper objection was right: one opaque judgement call is not a *path*.
Your ordering is causal, so each link can be inspected and each can be seen to succeed or fail.

## Your chain works. Measured on Logan, where parts-first found nothing.

Five grounded questions, 8–29 sources each:

| material | parts-first (3 tours) | your causal chain |
|---|---|---|
| **Wood Island Park**, the Olmsted park demolished for Runway 15R/33L | absent | **found** |
| **Neptune Road** residents displaced by Massport | absent | **found** |
| **Edward Lawrence Logan**, who the airport is named for | absent | **7 mentions** |
| East Boston / Reid / protests | absent | 13 / 4 / 4 |
| **named people in the delivered tour** | **0, 0, 0** | — |

That is the tour-423 material you liked, and parts-ranking could never reach it: asking what is
interesting about a control tower returns machinery; asking why the airport exists returns the
neighbourhood it destroyed.

## But the delivered tour barely improved, and I found exactly why

`LOGAN_storyfirst_1.txt` — dates 5 vs 4, one mention of Edward Lawrence Logan, one of East Boston.
**Wood Island Park and Neptune Road never reached the text.**

```
poi_list = [_new_poi(_n) for _n in _vp_stops]      # generate_tour_text.py:6476
```

**Only the stop NAMES are handed on.** The chain computes ~25,000 characters of sourced story
material, uses it to choose and order the stops, and then **throws it away**. The prose stage then
re-researches each stop from its name alone — and "Control Tower", researched by name, gives
2,384 acres and six runways.

**So the chain is proven and the handoff is missing.** This is the same shape as the earlier gap
where the story questions existed but were never called: the material is found, then dropped on the
floor between selection and writing.

**The next step is one specific thing:** feed the chain's text into each stop's corpus instead of
discarding it, so the writer starts from Wood Island Park rather than from the word "Control Tower".
