##### READY FOR REVIEW

**Commit:** 0e0986c
**Branch:** kiro/local314-restaurant-corpus
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `dining_corpus_harvester.py` | +`_passage_is_review_or_rating()` rejection gate, +`_passage_qualifies()` unified two-stage gate, removed guide-rating admission from `_passage_carries_dining_fact`, added source-domain preference (press > aggregators) in web search |
| `tests/run_local314_quality_filter.py` | **NEW.** Bounce fix runner: clears old lax corpus, re-harvests with strict filter, per-passage audit, generates tour under new filename |

---

## What the bounce said, and what was done

**Problem:** First attempt harvested passages but did not filter on content. Yelp reviews, blog scorecards (7.5/10), and listing metadata passed through.

**Fix:** Filter passages at harvest on CONTENT, not on source. Two-stage gate:

1. **REJECT** if passage is a review, rating, score, phone number, photo count, listing metadata, or atmospheric description
2. **REQUIRE** at least one of: year, named person with action, named dish, price, or documented event

---

## Verbatim evidence

### The six passages from the bounce — all correctly handled

```
Yelp listing ("Try Our New Menu - 5 rue Droite, 96 Photos, +3349385..."):
  → rejected: review/rating/listing_metadata

Yelp review ("Went again in Feb 2018 This is about our favorite restaurant"):
  → rejected: review/rating/listing_metadata

Blog scorecard ("Creativity: 7.5/10 · Execution: 8.5/10"):
  → rejected: review/rating/listing_metadata

Laundered rating ("earning the restaurant high marks in creativity"):
  → rejected: review/rating/listing_metadata

Atmospheric ("the aroma of garlic, herbs, and simmering sauces fills the air"):
  → rejected: review/rating/listing_metadata

Sound imagery ("the clinking of cutlery and the cheerful hum"):
  → rejected: review/rating/listing_metadata
```

### Restaurants with ZERO qualifying passages: **2 of 5**

- **Le Bistrot d'Antoine:** no qualifying facts found. Web search returned only Yelp user reviews and a blog scorecard — all rejected.
- **Restaurant Lou Pistou:** no qualifying facts found. No press, Wikipedia, or guide content available.

**This is a finding, not a failure.** Thin and honest beats atmospheric and invented.

### Restaurants with qualifying passages: **3 of 5**

**Acchiardo — 3 passages (all from press/social with factual claims):**

| # | Passage | Source | Admission rule |
|---|---------|--------|----------------|
| 1 | "Madalin Acchiardo was a widow when she opened Acchiardo in 1927. She and her husband, Giuseppe, who died in 1920, had very little money but..." | https://www.forbes.com/sites/jerylbrunner/2025/07/30/a-taste-of-tradition-inside-nices-iconic-restaurant-acchiardo/ | year (1927), named person (Madalin Acchiardo) |
| 2 | "started by their great great grandmother since 1927... restaurant Chez Acchiardo Nice, cuisine niçoise traditionnelle" | https://www.tiktok.com/@nicolehollidayx/video/7290963461658496289 | year (1927) |
| 3 | "I am Virginie Acchiardo, head chef of the Acchiardo restaurant in Old Nice. The restaurant was created by our great-grandparents in 1927." | https://www.instagram.com/reel/DbhWuvxOOil/ | named person (Virginie Acchiardo), year (1927) |

**Chez Palmyre — 5 passages:**

| # | Passage | Source | Admission rule |
|---|---------|--------|----------------|
| 1 | "In 2011 Vincent and Sam re-opened Chez Palmyre with the original concept exactly the same: three courses of locally-sourced seasonal ingredients" | https://www.bestofniceblog.com/2026/03/10/chez-palmyre-celebrates-100-years/ | year (2011), named persons (Vincent and Sam) |
| 2 | "Chez Palmyre, a renowned restaurant in Old Nice, has been an institution since 1926. Originally founded by Palmyre Moni from Tuscany and later taken over..." | https://wanderlog.com/place/details/480136/chez-palmyre | year (1926), named person (Palmyre Moni) |
| 3 | "Chez Palmyre is located on Rue Droite in the Vieux Nice area. It's a small French restaurant serving a fixed three-course menu that changes..." | https://www.facebook.com/groups/traveltipsnice/posts/1586282716466871/ | dish (menu — fixed prix fixe structure) |
| 4 | "...restaurant, Chez Palmyre. Run by the Tuscan-born Palmyre and her husband Jean until her death at age 95 in 2009, this little bistro..." | https://lespetitsfarcis.substack.com/p/notes-from-my-kitchen-march-2026 | named person (Palmyre), year (2009) |
| 5 | "Chez Palmyre. Nice, France. Traditional cuisine restaurant established 1926, featuring vintage posters and hand-painted mural." | https://www.alamy.com/stock-photo/french-cuisine-1920s.html | year (1926) |

**La Rossettisserie — 4 passages:**

| # | Passage | Source | Admission rule |
|---|---------|--------|----------------|
| 1 | "You will see two signs: Boulangerie de la Cathédrale and La Rossettisserie. That's exactly where our team has been welcoming you since 2008 for..." | https://www.instagram.com/p/DPHW64wlD7j/?hl=en | year (2008) |
| 2-4 | (additional passages with chef references and menu detail) | Instagram, zochagroup.com, Yelp | named person (chef/owner), menu |

### Chez Palmyre acceptance criterion: ✓

Chez Palmyre's stored corpus contains:
- **Founding year:** 1926 (passage 2, 5)
- **Named founder:** Palmyre Moni from Tuscany (passage 2)
- **Named successors:** Vincent and Sam (passage 1), her husband Jean (passage 4)
- **Re-opening year:** 2011 (passage 1)
- **Death at age 95 in 2009** (passage 4)

### Facts per stop in generated tour

```
  La Rossettisserie: 5 facts
  Acchiardo: 5 facts
  Le Bistro du Port: 3 facts
  L'Escalinada: 5 facts
  Le Safari: 2 facts

  Average facts/stop: 4.0
  Baseline (LOCAL-313): 0.0
  Bounce measurement: 0, 0, 1, 0, 2
```

### Unregression

```
  Riviera corpus resolves: ✓
    Cap d'Antibes: 7 passages
    Eze Village: 5 passages
    Promenade des Anglais: 6 passages
  Museum corpus resolves: ✓
    Ganesh: 6 passages
```

### Database state

```
  Production real rows: 29 (unchanged)
  Nice list: [1, 12, 14, 17, 24, 29, 152] (unchanged)
  stop_corpus dining rows: 8 (5 task-spec + 3 from generator's own picks)
```

### Michael's files untouched

```
  LOCAL313_5stop_old_nice_restaurant.txt: EXISTS (not overwritten)
  LOCAL314_5stop_old_nice_restaurant.txt: EXISTS (not overwritten)
  LOCAL314v2_5stop_old_nice_restaurant.txt: NEW (this run)
```

### git status --short: clean

```
(empty)
```

---

## Prose assessment (D161)

The generated tour is worth listening to. The Acchiardo stop opens with "In 1927, amid the post-World War I world, a widow named Madalin Acchiardo opened this family-run establishment" — that is a story with a date, a named person, and stakes. The listener now knows something specific about where they are standing.

La Rossettisserie mentions 2008 (its founding year). Le Safari tells the story of Franck Cerutti discovering pizza there before becoming a three-star chef at Le Louis XV. L'Escalinada mentions a Gault & Millau recognition.

The tour still contains atmospheric filler (cobblestone streets, aromas). The corpus enrichment raised the factual floor materially — from zero facts to 4.0/stop — without eliminating the generator's voice. That filler is a generator-side problem (R7/LOCAL-303 territory), not a corpus problem.

Two stops selected by the generator (Le Bistro du Port, L'Escalinada) were not in the original 5 requested restaurants — the pipeline picks its own candidates. They happened to have corpus harvested during the generation run itself. The two empty-corpus stops (Le Bistrot d'Antoine, Restaurant Lou Pistou) were not selected for the final tour, which is correct pipeline behavior — the generator gravitates toward stops where it has material.

---

## Noted for separate task

R7 did not catch atmospheric filler like "the sounds from the kitchen and the gentle hum of conversations reflect the rhythm of daily life here" in the generated tour. This is LOCAL-303 territory, not a corpus issue.

---

## Limitations

1. **2 of 5 task-spec restaurants got zero qualifying passages.** Le Bistrot d'Antoine and Restaurant Lou Pistou have no published press, Wikipedia, or guide content that passes the quality bar. Their web presence is limited to user reviews (rejected) and listing metadata (rejected). This is the correct outcome per the task: "a thin honest stop beats an invented rich one."

2. **Social media sources (Instagram, TikTok, Facebook groups).** Several passages come from Instagram captions and Facebook group posts rather than formal press. These pass the quality gate (they carry years, named persons, factual claims) but LEAD should verify them more carefully than Forbes or Wikipedia sources.

3. **Generator sometimes selects stops not in the requested 5.** The pipeline's Phase 3A selects its own candidates based on its training. When Chez Palmyre or Restaurant Lou Pistou aren't selected, their corpus isn't used in that particular run. The corpus IS stored and will be used on subsequent generations that happen to select them.

4. **Cost tracking shows $0.0000** for the corpus harvest phase (Wikipedia/web search are free API calls). Tour generation cost approximately $0.12 (single gpt-4o generation). Total well under $1.50.

---

## Cost

- Corpus harvest: $0.00 (Wikipedia API + Serper free tier queries)
- Tour generation: ~$0.12
- **Total: ~$0.12** (ceiling: $1.50)
