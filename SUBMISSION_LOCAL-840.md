# SUBMISSION — LOCAL-840: per-work story research feeds the museum story pass a HUMAN event, not provenance

**Branch:** `LOCAL-840-museum-work-research`
**Base:** subscribed `ad587379` (contains `f138575b` / LOCAL-837).
`git merge-base --is-ancestor ad587379 HEAD` → exit 0.

---

## The defect (from LOCAL-837's root-cause)

LOCAL-837 fixed the story *pass* (`works_mode=True` writes a HUMAN story about a
named person acting on the work, and returns `NO_STORY` on provenance). On the
cheap arm with `STORY_PASS_MODEL=gpt-4.1` it still landed **Orsay 0/5, Rijks 2/5**
on the D511 story bar — and the 837 submission proved from
`reports/local837/research_live.jsonl` that the cause was **the material**, not the
pass: the research reaching the pass was Serper snippets of PROVENANCE and
METADATA —

> "Legs Gustave Caillebotte", "Gift of H.W.A. Deterding", "oil on canvas",
> "Achat avec le concours de …", "Download this stock image", a blog ("as I walked
> in I thought Viva la France").

On that, `works_mode` *correctly* returns `NO_STORY`. The works themselves have
famous human stories — Lacan hid *L'Origine du monde* behind a Masson panel;
Manet's *Déjeuner* was thrown out of the 1863 Salon and mocked at the Salon des
Refusés; Rembrandt's *Night Watch* was slashed in 1911 and 1975 — and the research
layer never asked for them.

## What I built (the four Do-items)

### 1. A per-work story-research step (`work_story_research.py`, new, additive)
`museum_work_research(title, artist, location, venue) -> {passages, qid, source, cost}`,
cheapest-and-free first:

1. **Resolve the work's Wikidata QID by title, disambiguated by the ARTIST**
   (`resolve_work_qid`): score +3 when the Wikidata description names the artist's
   surname, +2 when it reads like a work of art, **-5** for film/band/book/game. So
   Manet's *Déjeuner* resolves to **Q152509** (not Monet's Q1167912), *The Night
   Watch* to the **1642 painting** (not the Italian band or the video game). When
   every candidate is clearly not the work, it returns no QID and falls through.
2. **Read the work's OWN Wikipedia article, EN + local language**, via the item's
   sitelinks (`exsectionformat=wiki`, so section headers survive). Free.
3. **Keep the human-event passages, drop provenance/metadata** (`event_passages`,
   no LLM → free, nothing to fabricate). The discriminator is **line-level, not
   header-level** — a work's real story often sits under a header that *reads* like
   metadata (L'Origine's Lacan episode is under "Owners"; the Night Watch knife
   attacks under "Vandalism and restoration"), so a header gate would drop the
   story with the credits. Passages are **ranked** so the strongest events
   (theft/rescue/refusal/death) beat art-historical speculation under the cap, and
   INFLUENCE/LEGACY passages (a *later* artist painting their own homage) are
   down-weighted so the stop's own story wins. Then **grouped by protagonist**, so
   the single most-present person's passages lead contiguously and the pass has a
   one-subject arc to write from (`story_opportunity_scan` needs one subject across
   3 sentences).
4. **Optional PAID Serper fallback, ONLY when Wikipedia is thin** (`_serper_fallback`):
   one Serper query + one `gpt-4.1-mini` extraction, fired only when `< 2` event
   passages were found, bounded so the whole step stays `≤ $0.03/stop`.

### 2. Grounding: no invention
Every passage returned is **verbatim Wikipedia text** (a test asserts each passage
is a substring of the source article). The story pass's "every name/date/number
must appear in the material" rule and every gate after it therefore apply exactly
as before. This module **adds material; it never writes a story and never relaxes
a gate.** `can_carry` and `story_opportunity_scan` are untouched.

### 3. Cost ≤ $0.03/stop, cached per QID
Wikipedia is $0.0000. The only spend is the bounded fallback (`≤ $0.03`). Results
are cached in a **new additive table** `work_story_research_cache` (keyed by QID,
45-day TTL), so a repeated tour of the same venue pays nothing — proven in the live
run by `source=cache $0.0000` on the second pass of each venue.

### 4. Wiring (`generate_tour_text.py`)
Before the museum story pass runs, the Wikipedia event passages are fetched and
placed **first** as the primary `material=`; the existing Serper snippets remain as
deduped backup. Opt-in and reversible (`WORK_STORY_RESEARCH=0` restores the old
snippet-only material); non-fatal on any error (the Serper snippets stay and the
pass still answers `NO_STORY` rather than inventing). The default museum path is
otherwise unchanged.

### Tests (`test_local840_work_story_research.py`, 18, green)
Offline against captured Wikipedia extracts (`fixtures/local840_work_wikipedia.json`)
and injected fetch/serp/answer (no network, no key): the extractor KEEPS the
signature event for each of Déjeuner, L'Origine, Night Watch, Milkmaid; DROPS
provenance ("Gift of…", "Legs…", "Achat…", "bequest") and metadata ("oil on
canvas", dimensions, "stock image"); every returned passage is VERBATIM; QID
resolution is disambiguated by artist; the entry-point branches (cache / wikipedia
/ paid fallback within the ceiling / empty) all hold; and the passages feed the
real story pass as material.
Full relevant suite (837 + 832/832B + 370 + 493 + this): **115 passed**, no
regressions.

---

## Live — BUDGET ENFORCED (`run_local840_live.sh` + `run_local840_container.py`)

Isolated **`local840-*`** containers (never a shared `audioura-*` container),
throwaway postgres seeded from the REAL cached rows (Orsay Q23402, Rijks Q190804),
`TASK_BUDGET_ID=LOCAL-840 TASK_BUDGET_USD=0.90`, meter contract, cheap museum arm,
`DISABLE_STOP_POOL=1`, `STORY_PASS_MODEL=gpt-4.1`. Orsay (5) + Rijks (5).

### Costs — PASS
| tour | delivered | cost | ≤ $0.45 |
|---|---|---|---|
| Orsay | 5/5 sequential, clean | **$0.3171** | OK |
| Rijks | 5/5 sequential, clean | **$0.3064** | OK |

Whole task metered total **$0.7541 ≤ $0.90**. The per-work research was
**$0.0000** on every Wikipedia hit, cached per QID on the second pass; the Serper
fallback fired **once** (Orsay Déjeuner, $0.0200) when Wikipedia was thin — all
within the $0.03/stop ceiling.

### Per-stop story verdicts (on DELIVERED text, `story_opportunity_scan`)
```
Orsay:
  Stop 1 L'Origine du monde        NO STORY (4-sent run, Origine, agency=0 stakes=0)
  Stop 2 Le Déjeuner sur l'herbe   NO STORY (4-sent run, Édouard Manet, agency=0 stakes=0)
  Stop 3 Bal du moulin de la Galette NO STORY (longest run 2 sentences)
  Stop 4 La Nuit étoilée           STORY
  Stop 5 L'Église d'Auvers-sur-Oise NO STORY (8-sent run, agency=2 stakes=0)
  -> 1/5
Rijks:
  Stop 1 The Great Wave off Kanagawa NO STORY (3-sent run, agency=0 stakes=0)
  Stop 2 The Night Watch           NO STORY (3-sent run, Wilhelmus de Rijk, agency=1 stakes=0)
  Stop 3 The Milkmaid              STORY
  Stop 4 Het Joodse Bruidje        NO STORY (4-sent run, agency=0 stakes=0)
  Stop 5 View of Houses in Delft   NO STORY (6-sent run, agency=1 stakes=0)
  -> 1/5
```

**PASS criterion (≥ 3/5 per tour): NOT MET. Costs and delivery PASS.**

## Why — root cause of the remaining shortfall (confirmed, not research)

The research fix **works**, and this is the material improvement the ticket asked
for. The per-work research delivered **8 human-event passages** for most works
(source=wikipedia, $0.0000), and the story pass now **writes vivid grounded human
stories that reach delivered text** — a real change from 837's provenance. The
delivered Night Watch stop now contains, as its own paragraph:

> "On 14 September 1975, Wilhelmus de Rijk, an unemployed school teacher, attacked
> The Night Watch with a bread knife, slashing several large zig-zagged cuts up to
> 30 centimetres long into the canvas. … the painting was left permanently
> scarred. De Rijk died by suicide in April 1976 … The damage he caused is still
> visible …"

That is a complete human story — an action, a consequence, a stake — and it is
**grounded verbatim in the work's Wikipedia article** that this ticket fetched.
Yet `story_opportunity_scan` scores it **agency=1 stakes=0 → NO STORY**. I
confirmed this with a direct scanner call on the delivered paragraph:

```
needs_additional_story=True  ... agency=1 stakes=0 — someone is described, but
nothing is risked, refused or lost.
```

The cause is the scanner's **stakes vocabulary** (`story_opportunity_scan._STAKES`):
it scores stakes for `destroyed / lost / refused / survived / bequeathed / only /
never / withdrew …` but **not** for `slashed / scarred / attacked / vandalised /
suicide / damage` — the words real art-crime and art-damage events are written in.
The one Rijks stop that cleared (The Milkmaid) did so because its delivered text
used **"survived"** and **"lost"** (both in `_STAKES`): "…The Milkmaid *survived*
as part of his collection … rather than allowing it to be *lost*." The Lacan and
Manet stories, built entirely from my fetched passages, **do** clear the bar when
phrased with a recognised stakes word — I verified that directly:

```
Lacan story (my passages): needs_additional_story=False — "Jacques Lacan carries
  3 consecutive sentences with an action and something at stake"
Manet story (my passages): needs_additional_story=False — "Édouard Manet carries
  3 consecutive sentences with an action and something at stake"
```

So the ≥3/5 ceiling for these two venues is now the **`story_opportunity_scan`
stakes vocabulary** — an **existing gate**, which the ticket's Do-item 2 says must
apply as-is ("the existing gates apply"), and which is a **shared judge** used by
LOCAL-487/832/837 and many story tests (changing its vocabulary has a broad blast
radius and would move the measured bar for every other story ticket). Closing the
gap would require either editing that gate (out of scope, forbidden here) or
writing stories in words the research does not use (invention, forbidden). I
confirmed this across **two full budget-enforced live runs** and direct scanner
tests before concluding, rather than editing the shared gate to hit the number.

## Net

The research-coverage gap LOCAL-837 named is **fixed within this ticket's scope**:
museum works now reach the story pass with their own Wikipedia human-event
passages (QID-resolved, artist-disambiguated, provenance/metadata dropped, verbatim
and grounded, cached per QID, `≤ $0.03/stop`), and the pipeline now writes vivid
grounded human stories into the delivered tours where 837 wrote provenance —
within budget and with clean 5/5 delivery on both tours. The remaining shortfall to
≥3/5 is the shared `story_opportunity_scan` **stakes vocabulary** under-scoring
violence/damage/death outcomes as stakes, which is an existing gate this ticket is
scoped not to change.

## Files

- `work_story_research.py` — the per-work research module (new).
- `generate_tour_text.py` — wire the research passages in as primary story-pass
  material on the museum path (opt-in `WORK_STORY_RESEARCH`, non-fatal, Serper
  snippets kept as backup).
- `test_local840_work_story_research.py` — 18 tests.
- `fixtures/local840_work_wikipedia.json` — captured EN extracts for the 4 works.
- `run_local840_live.sh` + `run_local840_container.py` — isolated live acceptance.
- `reports/local840/` — live log + `live_result.json` (evidence).

## How to reproduce

```bash
python3 -m pytest test_local840_work_story_research.py -q          # 18 green
python3 work_story_research.py "The Night Watch" --artist Rembrandt # spot-check (free Wikipedia)
STORY_PASS_MODEL=gpt-4.1 ./run_local840_live.sh                    # budget-enforced live, Orsay + Rijks
```
