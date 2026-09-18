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
