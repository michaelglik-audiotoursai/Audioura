[tool] Reading tour_500.txt:1
[tool] status: Completed
Score: 4.5/10

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 2 | "the emotional complexity found in works like Vigée Le Brun's Self Portrait in a Straw Hat, which you have already encountered." | 5 (false continuity — references a stop not in this 3-stop tour) | High |
| 2 | "John Everett Millais chose to depict the drowning... he traveled outdoors to the Hogsmill River... Only after completing the riverbank did he return indoors to add the figure." | 2 (en plein air / outdoor-first story told twice within the same stop) | High |
| 2 | *Ophelia* by Millais is held at **Tate Britain**, not the National Gallery | 8 (wrong museum — factual red flag) | High |
| 3 | *The Supper at Emmaus* (Caravaggio) — attributing "Vigée Le Brun, whose outdoor compositions also explored the power of light" | 8 (invented claim — Vigée Le Brun is a portraitist, not known for outdoor light compositions) | High |
| 3 | "This tour highlights the influence and technique of Vigée Le Brun" | 6 / 8 (false conclusion — Vigée Le Brun is never a stop; artist absent from this tour) | High |
| 2 | "In 1601... Ciriaco Mattei paid 150 scudi" / Stop 3 provenance | 1 (acceptable collector story, but note the price-ledger framing drifts toward dry transactional filler) | Low |
| 3 | "achieved through Caravaggio's use of oil and tempera on canvas" | 8 (dubious — the work is oil on canvas; "tempera" claim sounds invented) | Medium |
| 2 | "Millais, a pivotal figure in chose to delve into" | — (broken sentence, missing words — production defect) | Medium |
| 1 | "Since its arrival... establishing itself as a central piece in the museum's collection." | 1 (weak institutional filler close; no named people/motive/consequence) | Low |
| 3 | "That's 3 stops in all." + restaurant line | 6 (conclusion is thin; the "Vigée Le Brun" summary is factually wrong rather than a real wrap-up) | Medium |

Note on criterion 3: hours and admission ARE spoken (Stop 2) — good, not a defect. The restaurant line is the last sentence — intentional, not flagged. Stop count (3) matches request — but it is never explicitly explained as by-request (minor, criterion 7).

Three highest-value code-level improvements:

1. **Enforce a "stops-in-this-tour" allow-list in the narration generator.** The text repeatedly references Vigée Le Brun's *Self Portrait in a Straw Hat* as "already encountered" and even summarizes the whole tour as being about Vigée Le Brun — an artist/work that is not one of the 3 stops. Pass the resolved stop list into the prompt/template and reject or strip any continuity or conclusion sentence that names a work/artist outside that set. This single fix removes three High-severity defects.

2. **Add a museum-ownership validation pass against a work→collection map.** *Ophelia* belongs to Tate Britain, yet it appears in a National Gallery tour. Before emitting a stop, cross-check the artwork's canonical holding institution against the tour's museum and fail/flag mismatches (criterion 8). This is the most damaging class of error for a listener physically standing in the gallery.

3. **De-duplicate per-stop story beats and constrain invented technical/provenance claims.** Within Stop 2 the en-plein-air/outdoor-first narrative is told twice, and Stop 3 asserts "oil and tempera on canvas" plus a fabricated Vigée Le Brun "outdoor compositions" link. Add a semantic dedup check across sentences within each stop and ground medium/technique/provenance assertions against a verified fact source (or mark them as low-confidence and drop), rather than letting the model free-associate connections between artists.
