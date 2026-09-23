# CRITIQUE — Round 5 Tours

**Task:** LOCAL-513 — Critique the round-5 tours, findings only.
**Agent:** Mac Mini Kiro. **Branch:** LOCAL-513-critique-round5. **Base:** storied (7a97e72).
**Scope:** Judgement of whether these tours are worth listening to — the thing `tour_quality.py` cannot measure. No code changed.

**Method / provenance rule:** Every finding is tagged `READ` (I can point at the exact words in the file) or `INFERRED` (I am reasoning beyond the text — real-world knowledge, cross-file comparison, or judgement). All six files were read end-to-end (LOGAN_1/CHURCH_1/CHURCH_2 = 67 lines; the rest = 86 lines; `wc -l` confirmed before reading). I quote from the text so a reader can reproduce each claim against the source.

**One sentence up front:** The CHURCH tours are genuinely good — they carry real, specific, checkable stories (Cuenin vs. Cardinal Law, Mother Teresa's 1995 visit, the 2023 D'Amore murders). The LOGAN tours are mostly hollow institutional history bolted onto interchangeable airport furniture, and they contain the batch's worst factual errors. The single most damaging problem is shared by both venues: the model narrates the SAME handful of anecdotes at EVERY stop regardless of what the stop physically is, so location and story are disconnected.

---

## LOGAN_1 — Boston Logan (4 stops: Terminal A Ticketing, Security Checkpoint, Terminal A, Jetbridge)

### Stop 1 — Terminal A Ticketing
1. Most interesting thing: the airport's origin — *"the passage of Chapter 404 of the Acts of 1922 ... signed by Governor Channing H. Cox ... a 189-acre tidal flat with cinder runways, opening on September 8, 1923."* `READ`
2. It is real content, but it is airport-wide history, not anything about *ticketing*. A ticketing counter is not where a listener experiences the founding of the airport. `INFERRED`
3. Missing: anything a passenger standing at a check-in counter could actually engage with — the shift to self-service kiosks, the airline mix at Terminal A, or Terminal A's own opening. The stop instead delivers 1920s land reclamation. `INFERRED`
4. Suspicious detail: *"Overseen by Duke, the original airfield..."* — "Duke" is an ungrounded, dangling name with no referent. Looks like a generation artifact. `READ` (that it is wrong is `INFERRED`)

### Stop 2 — Security Checkpoint
1. Most interesting thing: *"The bones of this hub date back to 1921, when the Boston Chamber of Commerce, with the U.S. Army Air Service, orchestrated the creation of an airfield from East Boston's mudflats."* `READ`
2. Nothing here is about a security checkpoint. It is a third restatement of the airport's founding, and it contradicts the other stops on the date (1921 here vs. 1922/1923 elsewhere — see factual flags). `READ` / `INFERRED`
3. Missing: the obvious and only interesting thing about *this* stop — Logan's post-9/11 role in aviation security (Flights 11 and 175 departed Logan). That story is the natural fit for a security checkpoint and it is completely absent here, yet it appears at the *Jetbridge* in LOGAN_2. `INFERRED`
4. This is the shortest, thinnest stop in the tour. `READ`

### Stop 3 — Terminal A
1. Most interesting thing: *"Opened in 2005, it earned the distinction of being the world's first airport terminal to achieve LEED certification for new construction ... in 2006 ... the renowned firm HOK."* `READ`
2. This is the one genuinely good LOGAN stop — a real, specific, checkable claim tied to the actual place you are standing in. `INFERRED`
3. Missing: nothing critical, though it could name the airline that anchors Terminal A (Delta) to ground the "each departure" abstraction. `INFERRED`

### Stop 4 — Jetbridge
1. Most interesting thing: *"In 1923, the Massachusetts National Guard needed an operational base for their newly formed 101st Observation Squadron of the 26th Division Air Service ... reclaiming marshland with silt and cinder ... $35,000 from the legislature and an added $10,000 ... Boston Chamber of Commerce."* `READ`
2. Real content, but for the FOURTH time it is airport-founding history, now attached to a jetbridge — the most generic object in any airport. `READ` / `INFERRED`
3. Missing: a jetbridge invites either the Frank Der Yuen / jet-age history OR the 9/11 departure-gate story. Instead it recycles 1920s funding figures. `INFERRED`

**LOGAN_1 verdict:** Three of four stops are the same founding story retold. Only Terminal A (LEED) earns its place.

---

## LOGAN_2 — Boston Logan (4 stops: Terminal A Check-In, Terminal A Main Concourse, Jetbridge, Control Tower)

### Stop 1 — Terminal A Check-In
1. Most interesting: *"Established on September 8, 1923, with a single cinder runway laid by the U.S. War Department ... over 43.5 million travelers in 2024."* `READ`
2. Again airport-founding history at a check-in desk. The one stop-appropriate line is *"self-service kiosks ... significantly reducing wait times."* `READ`
3. Garbled text: *"the Federal Aviation Administration's of Integrated Airport Systems"* — broken grammar, an incomplete phrase. `READ`

### Stop 2 — Terminal A Main Concourse
1. Most interesting: *"Boston Mayor Curley, the mayor who served four terms, petitioned for state assistance"* in March 1922. `READ`
2. Thin. Mostly atmosphere (*"often compared in function to a mall within a small town"*) plus one historical sentence. Offers a feature list more than a story. `READ` / `INFERRED`
3. Missing: James Michael Curley is one of the most colorful figures in Boston history (jailed twice, "the Rascal King"). Naming him and doing nothing with him wastes the batch's best character hook. `INFERRED`

### Stop 3 — Jetbridge
1. Most interesting — and the strongest single passage in ALL three LOGAN tours: *"On September 11, 2001, Logan Airport was the departure point for Flights 11 and 175 ... Betty Ann Ong, a flight attendant who became one of the first to alert authorities, and Christine Hanson, the youngest victim of the attacks."* `READ`
2. This is a real, specific, human, checkable story. It is exactly the kind of content the batch needs. `INFERRED`
3. Problem: it then swerves into a JFK Airport digression — *"Just as Logan Airport is integral to Boston, JFK Airport is the linchpin of New York's air travel network ... serving nearly 100 airlines"* — content that belongs to a different airport in a different state and has no business at a Logan jetbridge. `READ` / `INFERRED`

### Stop 4 — Control Tower
1. Most interesting: *"the 101st Observation Squadron of the Massachusetts National Guard, led by Lt. Col. William A. Bishop, played an instrumental role in advocating for a permanent base."* `READ`
2. Reasonable, but generic tower-as-nerve-center copy. `READ`
3. Factual flag (see below): the orientation blurb for LOGAN_2/LOGAN_3 claims this tower was *"constructed in 1887–1889 by Gustave Eiffel"* — that is the Eiffel Tower, not an airport control tower. `READ` / `INFERRED`

**LOGAN_2 verdict:** The 9/11 jetbridge stop is the best thing in the LOGAN set; the Eiffel/Curley/JFK material drags it down.

---

## LOGAN_3 — Boston Logan (4 stops: Terminal A Ticketing/Check-In, Terminal A, Jetbridge, Control Tower)

### Stop 1 — Terminal A Ticketing / Check-In
1. Most interesting: *"the airport officially opened its doors on September 8, 1923 ... Logan spans 2,384 acres with six runways and four passenger terminals."* `READ`
2. Broken text: *"Cox, which led to the creation of..."* — "Cox" is a dangling fragment (Governor Channing Cox, mangled). And *"In 1922, Boston Mayor James Michael Curley took decisive action."* is cut off mid-thought in the orientation. `READ`
3. Missing: an actual reason to care about the ticketing hall. `INFERRED`

### Stop 2 — Terminal A
1. Most interesting: *"In 2005, when it opened, Terminal A was celebrated as the world's first airport terminal to achieve LEED certification. Designed by HOK and constructed by Skanska ... Chapter 404 of the Acts of 1922 ... appropriated $35,000 ... at Jeffries Point in East Boston."* `READ`
2. This is the most information-dense and best-sourced LOGAN stop in the batch — LEED, architect, builder, the 1929 20-year lease to the City of Boston, 16,000 employees. `READ` / `INFERRED`
3. Fine as is. `INFERRED`

### Stop 3 — Jetbridge
1. Most interesting: *"The airport's tarmac has welcomed iconic figures like Charles Lindbergh, Queen Elizabeth II, Nelson Mandela, and The Beatles ... in 1964 when The Beatles landed here."* `READ`
2. Colorful, but a name-drop list rather than a story, and it is attached to a jetbridge that "may seem mundane" — the tour admits its own subject is dull. `READ`
3. Factual flag: *"Originally named Jeffries Field"* / Beatles-in-1964. See flags — the Beatles' first Logan arrival and the "Jeffries Field" naming are both dubious. `READ` / `INFERRED`

### Stop 4 — Control Tower
1. Most interesting: *"On July 22, 1927, Charles Lindbergh landed the Spirit of St. Louis here ... Greeted by Massachusetts Governor Alvan T. Fuller and a crowd of 50,000 spectators."* `READ`
2. This is a good, concrete, checkable anecdote — a real date, a real governor, a real crowd figure. Best-realized story in LOGAN_3. `READ` / `INFERRED`
3. Contradiction: the orientation still calls the tower a *"320-foot Brutalist monument ... Desmond & Lord with John Carl Warnecke"* AND the batch's shared blurb says it was built by Eiffel in 1887–1889. Both cannot be true. `READ`

**LOGAN_3 verdict:** Two strong stops (Terminal A LEED, Lindbergh at the tower); Beatles list and the Eiffel blurb weaken it.

---

## CHURCH_1 — Our Lady Help of Christians, Newton (4 stops: Nave, Main Altar, Narthex, Pulpit)

### Stop 1 — Nave
1. Most interesting: *"On June 15, 1995, the nave became a focal point ... the visit of Mother Teresa ... Hundreds found themselves locked out"* and *"on December 8, 2002 ... More than 850 parishioners gathered to hear Rev. Walter H. Cuenin speak out against Cardinal Bernard Law ... multiple standing ovations ... soon led to Law's resignation."* `READ`
2. Two real, specific, dated, human events tied to the exact space. This is what a good stop looks like. `INFERRED`
3. Missing: little — could name that Law resigned Dec 13, 2002, to tie the timeline. `INFERRED`

### Stop 2 — Main Altar
1. Most interesting (attempted): the 2023 D'Amore murders. `READ`
2. Badly broken: the text openly argues with itself — *"The premise of the deaths occurring 'near Main Altar' is not supported by public and investigative reporting; however, the circumstances ... are documented as follows:"* and then the sentence dies mid-list: *"Gilda 'Jill' D'Amore (73), her husband Bruno D'Amore (74). This heartbreaking event..."* The model leaked its own fact-checking scaffolding into the narration. `READ`
3. This is the single most listener-breaking passage in the CHURCH set: a self-refuting, truncated crime report read aloud at an altar. `INFERRED`
4. Good salvage in the same stop: *"conservators unearthed original stenciling, gilding, and Marian murals by James Murphy"* — a genuine, place-specific detail. `READ`

### Stop 3 — Narthex
1. Most interesting: *"In late 2002, Rev. Walter H. Cuenin orchestrated a series of meetings here ... Cardinal Bernard Law ... barred any further archdiocesan-level meetings at this parish."* `READ`
2. Strong and appropriate to a narthex (a gathering space). `INFERRED`
3. Broken again: another leaked scaffold — *"Based on official reporting from law enforcement and court proceedings: * Where it happened: Inside the victims' home at 49 Broadway Street ... failed to arrive for their 50th wedding a."* Cuts off at "wedding a[nniversary]". `READ`

### Stop 4 — Pulpit
1. Most interesting: Cuenin *"criticized Cardinal Bernard Law for what he described as hiding 'behind lawyers and bankruptcy,' a statement that earned him a standing ovation"* and *"advocate for the ordination of women and inclusion of LGBTQ+ members."* `READ`
2. Broken text: *"Father Walter, a priest at this parish, H. Ignited discussions..."* — the name "Walter H. [Cuenin]" is shredded, with "H." orphaned onto a capitalized "Ignited." Ends mid-sentence: *"' during a call for lay-led structural reform."* `READ`

**CHURCH_1 verdict:** Excellent source material sabotaged by leaked fact-check scaffolding and truncation at 3 of 4 stops.

---

## CHURCH_2 — Our Lady Help of Christians, Newton (4 stops: Nave, Altar, Narthex, Pulpit)

### Stop 1 — Nave
1. Most interesting: *"over 850 parishioners stood in solidarity with Fr. [Cuenin] ... openly criticized Cardinal Bernard ... Law."* `READ`
2. Broken names: *"Fr. During his homily, Fr. Cuenin..."* and *"Cardinal Bernard, the Archbishop of Boston from 1984 to 2002, F. Law"* — the parenthetical bio got jammed into the middle of the name "Bernard F. Law." `READ`
3. Trails off: *"The nave's role as a sanctuary extended beyond spiritual guidance."* then stops. `READ`

### Stop 2 — Altar
1. Most interesting: *"Made by local artisans Eric Boeglin and Deacon Jim ... In 1995, the altar bore witness ... Mother Teresa visited ... Father Walter H. Cuenin ... resigned amid allegations of embezzlement. Hundreds of thousands of dollars were involved."* `READ`
2. This is the cleanest, most readable stop in the whole CHURCH set — no leaked scaffold, real names, a real arc (a man who "boldly challenged authority yet found himself embroiled in financial scandal"). `READ` / `INFERRED`
3. Tension worth flagging: it states embezzlement of "hundreds of thousands" as fact, while CHURCH_1/CHURCH_3 frame the same charges as *"unfounded and politically motivated."* The batch is internally inconsistent on whether Cuenin was guilty. `READ` / `INFERRED`

### Stop 3 — Narthex
1. Most interesting: the 2002 inter-parish gathering and Law's decree *"barring any archdiocesan meetings."* `READ`
2. Good, but the audit detail — *"issues with baptism and wedding stipends and a leased car"* — appears abruptly with no antecedent (the reader hasn't been told there was an audit). `READ`

### Stop 4 — Pulpit
1. Most interesting: Cuenin during *"the clergy sexual abuse crisis ... took a bold stand ... welcoming divorced Catholics and LGBTQ+ parishioners ... endorsement of women's ordination."* `READ`
2. Broken again: leaked scaffold + truncation — *"Based on documented law enforcement statements ... How it happened: On the morning of June 25, 2023, 73-year-old Gilda 'Jill' D. This deeply attended mass..."* Cuts off at "Gilda 'Jill' D." and jumps to "This deeply attended mass" with no referent. `READ`

**CHURCH_2 verdict:** Best single stop of the batch (Altar), but the Pulpit repeats CHURCH_1's leaked-crime-report failure.

---

## CHURCH_3 — Our Lady Help of Christians, Newton (4 stops: Nave, Pulpit, Altar, Narthex)

### Stop 1 — Nave
1. Most interesting: *"Mother Teresa visited this nave ... caused gridlock in the surrounding streets"* and the 2002 Cuenin homily/standing ovations, PLUS a new one: *"In the late 19th and early 20th centuries, Irish and Italian immigrants vied for influence within the church. Though initially dominated by the Irish, the Italians eventually reshaped the parish identity."* `READ`
2. The immigrant-rivalry detail is fresh, specific to Nonantum, and appears nowhere else in the batch — the strongest unique hook in CHURCH_3. `READ` / `INFERRED`
3. This is a clean stop — no leaked scaffold. `READ`

### Stop 2 — Pulpit
1. Most interesting: *"he called for the resignation of Cardinal Bernard Law ... Law banning archdiocesan meetings ... Within days, the Cardinal resigned."* and *"September 2005 ... Father Cuenin announced his forced departure, citing financial irregularities as the pretext given by Archbishop O'Malley."* `READ`
2. Clean, coherent, well-arced. Good stop. `READ`
3. Minor: "Within days, the Cardinal resigned" implies direct causation between one homily and Law's resignation — an overstatement (Law resigned amid the broader abuse crisis). `INFERRED`

### Stop 3 — Altar
1. Most interesting: *"In early 2024 ... the church had been sheltering up to 30 migrant families ... public statements from both the pastor and Mayor Ruthanne Fuller"* and *"Beneath the altar, there lies a time capsule placed by the parish's founders."* `READ`
2. Two fresh, specific, checkable hooks (migrant sanctuary; time capsule) unique to this tour. Strong. `READ` / `INFERRED`
3. Odd insert: a theological digression — *"first described by John Chrysostom in AD 345 ... Pope Pius V attributed the Christian victory over the Ottoman Empire in 1571 to her intercession."* Interesting but jammed mid-paragraph between migrant families and a murder, with no transition. `READ` / `INFERRED` — also a factual flag (Chrysostom c. AD 349–407; "AD 345" predates his birth). See flags.

### Stop 4 — Narthex
1. Most interesting: the 2023 D'Amore/Arpino murders framed as community grief. `READ`
2. Leaked scaffold + truncation AGAIN: *"Based on official reporting and statements from prosecutors and law enforcement: ### Where and How It Happened * Where: The victims were found inside their home on Broadway Street ... discovered by a friend who went to check on them after they failed."* Ends at "they failed." `READ`
3. Nice closing image though: *"much like Union Street beyond, is shaped by the stories of those who have walked through it."* `READ`

**CHURCH_3 verdict:** The best-written CHURCH tour overall (three clean stops, two unique hooks) — only the Narthex repeats the leaked-report failure.

---

## RANKING — worst first

Ranking on "would a listener at this spot get something worth hearing that belongs here?"

1. **LOGAN_1 Stop 2 — Security Checkpoint (WORST).** Thinnest stop in the batch; recycles the founding story a third time; omits the one obviously relevant subject (Logan's aviation-security / 9/11 role); and contributes the 1921 date that contradicts the other stops. `READ`/`INFERRED`
2. **CHURCH_1 Stop 2 — Main Altar.** Reads its own fact-checking argument aloud (*"The premise ... is not supported ..."*) then truncates mid-sentence. Self-refuting narration at the altar. `READ`
3. **CHURCH_1 Stop 4 — Pulpit.** Name shredded ("Father Walter ... H. Ignited"); ends mid-sentence. `READ`
4. **CHURCH_2 Stop 4 / CHURCH_3 Stop 4 — Pulpit / Narthex (tie).** Both leak the crime-report scaffold and truncate at "Gilda 'Jill' D." / "they failed." `READ`
5. **LOGAN_1 Stop 1 & Stop 4 — Ticketing & Jetbridge.** Founding history twice more; "Overseen by Duke" dangling name. `READ`
6. **LOGAN_2 Stop 3 — Jetbridge.** Strong 9/11 opening ruined by an off-topic JFK-airport digression. `READ`
7. **LOGAN_3 Stop 3 — Jetbridge.** Celebrity name-drop list; admits its own subject "may seem mundane." `READ`
8. **CHURCH_2 Stop 1 — Nave.** Good content, but name-jamming ("Cardinal Bernard, the Archbishop ... F. Law") and a trailing dead sentence. `READ`
9. ... (middle-tier stops: LOGAN_2 Concourse, LOGAN_3 Ticketing) ...
10. **Best stops (would keep as-is):** CHURCH_2 Stop 2 (Altar), CHURCH_3 Stop 1 (Nave, immigrant rivalry), CHURCH_3 Stop 3 (Altar, migrant sanctuary + time capsule), LOGAN_3 Stop 4 (Lindbergh 1927), LOGAN_1/LOGAN_3 Terminal A (LEED). `INFERRED`

---

## THE ONE CHANGE THAT WOULD IMPROVE THE BATCH MOST

**Stop leaking fact-checking scaffolding into the narrated text, and never emit a truncated sentence.** `INFERRED`

Justification from the text: the batch's most listener-destroying failures are not weak facts — the facts are often excellent — they are passages where the model's internal verification talk was spoken aloud and then cut off mid-word:
- CHURCH_1 Altar: *"The premise of the deaths occurring 'near Main Altar' is not supported by public and investigative reporting; however..."*
- CHURCH_1 Narthex: *"Based on official reporting from law enforcement and court proceedings: * Where it happened: ... failed to arrive for their 50th wedding a."*
- CHURCH_2 Pulpit: *"Based on documented law enforcement statements ... 73-year-old Gilda 'Jill' D."*
- CHURCH_3 Narthex: *"Based on official reporting and statements from prosecutors ... after they failed."*

Four separate stops read a bulleted police-report template to a listener and stop mid-sentence. Fixing this one class of defect repairs the ranking's #2–#4 worst stops at once and does more for perceived quality than any new fact. (Runner-up change, for LOGAN specifically: bind each stop's story to what the listener is physically standing in — security→9/11, tower→Lindbergh, terminal→LEED — instead of retelling the 1920s founding at every stop.)

---

## FACTUAL FLAGS (things that look wrong)

**Fact belonging to a different place / thing:**
- **Control Tower "constructed in 1887–1889 by Gustave Eiffel"** — LOGAN_2 and LOGAN_3 orientations. That is the **Eiffel Tower** in Paris; it has nothing to do with a Boston airport control tower. LOGAN_3's own Stop 4 contradicts this, attributing the tower to *"Desmond & Lord and John Carl Warnecke"* (Brutalist, 320 ft). `READ` (contradiction) / `INFERRED` (Eiffel attribution is false).
- **JFK Airport digression** — LOGAN_2 Stop 3. *"JFK ... serving nearly 100 airlines with flights to destinations across all six inhabited continents."* This is a different airport in a different state, inserted at a Logan jetbridge. Off-place, not false, but misplaced. `READ` / `INFERRED`.

**Claim that cannot be checked / internally contradictory:**
- **Airport founding date is inconsistent across the LOGAN batch:** LOGAN_1 Stop 1 says Chapter 404 was "Acts of 1922 ... opening September 8, 1923"; LOGAN_1 Stop 2 says "The bones ... date back to **1921**"; LOGAN_2 Stop 3 says "Governor Channing Cox signed Chapter 404 into law" on "**May 12, 1922**." Three different framings/dates for one event. `READ`.
- **Cuenin's guilt is contradicted between tours:** CHURCH_2 states embezzlement of *"hundreds of thousands of dollars"* as fact; CHURCH_1 calls the same charges *"unfounded and politically motivated."* A listener taking two of these tours gets opposite conclusions. `READ`.
- **"Within days, the Cardinal resigned"** (CHURCH_3 Pulpit) implies one homily caused Law's resignation; the resignation followed the broader abuse crisis, not a single sermon. Overstated causation. `INFERRED`.
- **"John Chrysostom in AD 345"** (CHURCH_3 Altar) — Chrysostom was born c. AD 349 and died 407; he could not have described anything in 345. Date is almost certainly wrong. `INFERRED`.
- **"The Beatles landed here ... in 1964"** and **"Originally named Jeffries Field"** (LOGAN_3 Stop 3) — the field was near **Jeffries Point** (per LOGAN_3 Stop 2 and LOGAN_2), so "named Jeffries Field" is likely a slip; the Beatles' 1964 U.S. arrival was JFK, and a specific Logan landing needs a source. Both unverifiable as stated. `INFERRED`.
- **"Overseen by Duke"** (LOGAN_1 Stop 1) — a bare surname with no referent; cannot be checked and reads as a generation artifact. `READ` / `INFERRED`.
- **"Irish priest Fr John Therry"** dedicating "St. Mary['s]" cathedral (CHURCH_1 orientation) — John Joseph Therry is an Australian church figure (Sydney), unrelated to Newton, MA. Looks like bleed-in from unrelated Marian material. `INFERRED`.

**Stop a listener could not find / navigation problems:**
- **Coordinates wander wildly for stops in the SAME building.** CHURCH tours: within one small church the four stops are given coordinates spread across ~0.007° lat and ~0.008° lon (e.g. CHURCH_1 Nave 42.3505,-71.2009 vs Main Altar 42.3525,-71.2079 vs Pulpit 42.351065,-71.203978) — that is hundreds of meters apart for a nave, altar and pulpit that are within one room. A listener navigating by coordinates could not find the next "stop." Same problem in LOGAN (Jetbridge 42.3644,-71.0096 vs -71.0177 vs -71.0202 across the three tours). `READ` / `INFERRED`.
- **CHURCH directions are internally contradictory.** CHURCH_1 Stop 4 says the Pulpit is reached by walking to the altar "on the left side"; CHURCH_3 orders the stops Nave→Pulpit→Altar→Narthex and routes the listener past the altar to reach the pulpit *before* visiting the altar. The stop ordering differs between tours of the identical building, so the "walk straight down the aisle" directions cannot all be right. `READ`.
- **LOGAN directions send walkers through secure/one-way space.** e.g. LOGAN_1 routes a listener from a post-security "Jetbridge" area back out; real airport geometry does not allow walking from a jetbridge back through the concourse to ticketing. A listener physically could not follow the route. `INFERRED`.

**Truncation (a listener is left mid-sentence):** CHURCH_1 Altar, CHURCH_1 Narthex, CHURCH_1 Pulpit, CHURCH_2 Nave, CHURCH_2 Pulpit, CHURCH_3 Narthex, LOGAN_2 Stop 1 (broken FAA phrase), LOGAN_3 Stop 1 ("Cox, which led to..."). `READ`.

---

## SUMMARY

- **CHURCH beats LOGAN on substance.** The Newton church has genuinely gripping, checkable, human stories (Cuenin vs. Law; Mother Teresa 1995; 2023 murders; 2024 migrant sanctuary; Irish/Italian rivalry). LOGAN mostly has the same 1920s founding story retold at every stop, with two bright spots (Terminal A LEED; Lindbergh 1927).
- **The dominant defect is cross-venue and mechanical:** leaked fact-check scaffolding + mid-sentence truncation, concentrated on the D'Amore murder passages. Fix that first.
- **The dominant LOGAN defect is thematic:** story is not bound to place — founding history is narrated at ticketing, security, terminal and jetbridge indiscriminately, and the genuinely place-appropriate stories (9/11 at security, Lindbergh at the tower) are either misplaced or omitted.
- **Worst factual error:** the Gustave Eiffel / 1887–1889 attribution of Logan's control tower (Eiffel Tower bleed-in), which the same tour then self-contradicts.

*All quotations verified against the six files as read in full on 2026-09-23.*
