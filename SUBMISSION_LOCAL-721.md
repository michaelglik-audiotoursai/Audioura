# SUBMISSION — LOCAL-721: Website link text becomes a stop ("Explore this painting in our virtual tour")

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-721-link-text-titles`
**Base:** `subscribed` = `7a5c411f` (`git merge-base --is-ancestor 7a5c411f HEAD` → exit 0 ✓)
**code_sha:** `4e3c1f5daa306093920a5f59c8fd057eea4b2622`

---

## Problem

Four fresh 6-stop tours of "Courtauld Gallery, London" (museum, `DISABLE_TOUR_CACHE=1`,
`DISABLE_STOP_POOL=1`, Subscribed settings; writers gpt-4.1 / Haiku 5.5 / Sonnet 5.5 /
Opus 5.5) ALL delivered two stops titled **"Explore this sculpture in our virtual tour"**
and **"Explore this painting in our virtual tour"**. The phrase appears ~80× per generation
log, so it lives in the venue corpus / candidate-works list — it is the anchor text of the
link that wraps each work's image on the Courtauld site, scraped in as if it were a work
title. In the Claude runs it also tripped `D3(e) No duplicate stops` and `D3(c) boilerplate
shingles` and the tour was refused.

## Root cause

Candidate work titles are taken from venue pages via the LOCAL-629/630 "documented works"
and LOCAL-653 site/canonical candidate paths. Every intake path funnels through one shared,
pure predicate — `junk_title_guard.is_junk_page_title` (used by `site_candidate_guard`,
`exhibition_site_first` ×2, and `artwork_selection_guard.enforce_artworks_only` step 1b).
That predicate rejected chrome separators (`«`/`|`/spaced dash), bare nav labels, section
leads, and the venue-with-filler shape — but a call-to-action sentence
("Explore this painting in our virtual tour") has none of those shapes, so it sailed
through and became a stop.

## Fix (generic, no Courtauld hard-coding)

Added a call-to-action reject as **rule 5** of `is_junk_page_title`
(`junk_title_guard.py`). A CTA is an instruction ABOUT the website, not a thing on a wall.
Two venue-agnostic signatures:

- **(a) imperative visitor-action opener** — the title STARTS with a STRONG CTA verb
  (`explore / discover / browse / book / buy / learn / join / donate / subscribe / shop /
  plan / download / sign / view / visit / read …`) FOLLOWED by an instruction connective
  (`this / our / your / us / more / now / up / online / in / to our|the|a / tickets /
  the tour|video|app|collection|newsletter|catalogue …`). The follow-on requirement is
  what keeps a one-word noun ("Explosion") or a verb-then-content-noun / verb-then-"of"
  title ("View of Verona", "Visit of the Queen of Sheba") safe.
- **(b) website/marketing OBJECT phrase anywhere** — `virtual tour(s)`, `online
  collection/shop/store/tour/exhibition`, `gift/museum/online shop`, `buy/book tickets`,
  `book now/online/your visit`, `download the app`, `shop the catalogue/collection`,
  `create your own gallery`, `join and support`, e-newsletter / mailing list.

Weak verbs that genuinely open real work titles (`take / make / give / create / start /
find / see / build / get`) are deliberately **not** in the strong list — they reject only
when a website OBJECT (b) is also present. So "Take Your Son, Sir!" and "Giving Alms"
survive, while "Create your own gallery" is still caught (by the object rule).

Because the rule lives in the one shared predicate, it holds on every intake path
(documented-works, site/canonical, exhibition site-first) and for any venue — not just
Courtauld.

**Files changed**
- `junk_title_guard.py` — `_CTA_VERB_STRONG`, `_CTA_IMPERATIVE_RE`, `_CTA_OBJECT_RE`,
  `_is_call_to_action_title()`, wired as rule 5 of `is_junk_page_title`.
- `test_local721_cta_link_text.py` — new unit tests (below).
- `.gitignore` — ignore `.local721_live/` (captured live env with secrets; never committed).

## Preferring the real title when the CTA is a link next to a work

The CTA anchor text and the real work title are already SEPARATE candidate entries in the
venue corpus (the Courtauld list carries both "A Bar at the Folies-Bergère" AND
"Explore this painting in our virtual tour"). Rejecting the CTA entry at intake therefore
leaves the real work title in the candidate set to be selected — which is exactly what the
live run shows (the six selected stops are all real works). No separate "promote the
sibling" step is needed; dropping the CTA yields the real title.

## Unit tests — `test_local721_cta_link_text.py`

```
python3 -m pytest test_local721_cta_link_text.py -q
7 passed in 0.18s
```

- **TestCTALinkTextRejected** — the two literal Courtauld strings + the sibling
  ("Explore this piece of furniture in our virtual tour") + other Courtauld CTA candidates
  (Join and Support, Create your own gallery, Shop the catalogue, Gallery Virtual Tours) +
  14 generic CTA phrases (Book tickets, Learn more, Plan your visit, View in 3D,
  Subscribe to our newsletter, …) — all REJECTED, for Courtauld and for Rijksmuseum.
- **TestRealTitlesSurvive** — the 5 named real titles (incl. verb-opening **"Explosion"**)
  + 11 verb-opening / imperative-looking real titles (**"Take Your Son, Sir!"**,
  "Giving Alms", "Reading the Letter", **"View of Verona"**, "View of Delft",
  **"Visit of the Queen of Sheba to Solomon"**, "Visitation", "Discovery of Honey by
  Bacchus", "Start of the Hunt") + descriptive titles — all KEPT.
- **TestFilterSplitsCTA** — `filter_out_junk_titles` keeps the works, drops the CTA with
  `_reject_reason="junk_page_title"`.

## Regression suites

```
python3 -m pytest test_local632_junk_and_shortfall.py test_local653_site_candidates.py \
                  test_local630_venue_truth.py test_local721_cta_link_text.py -q
74 passed

python3 -m pytest test_local629_selection_diversity.py test_local636_national_gallery.py \
                  test_local639_collection_holders.py test_local669_grounded_highlights.py -q
52 passed, 1 skipped
```

## Live test — own container, no phones

- Built `local721-gen` from `Dockerfile.generator`; the image `COPY`s the working-tree
  `*.py`, so the CTA fix is baked in (verified inside the image:
  `is_junk_page_title('Explore this painting in our virtual tour') → True`,
  `is_junk_page_title('Explosion') → False`).
- `docker run --rm --name local721-gen -p 5099:5000 --network development_default`, env
  copied from `audioura-tour-generator-1` + `DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1`,
  meter mounts (`_meter` ro, `meterlogs` rw). **No `docker compose -p audioura`; the
  `audioura-*` containers were never touched or renamed** — `audioura-tour-generator-1`
  stayed `Up … (healthy)` on 5000 throughout. Container + image removed after the run.
- `POST /generate {"location":"Courtauld Gallery, London","tour_type":"museum",
  "total_stops":6}` → job `e31dc7a4-6c58-429d-9d4c-18e9c8d22b99`.

**Selected stops (LOCAL-212) — NO CTA text:**

1. Self-Portrait with Bandaged Ear
2. Christ and the Woman Taken in Adultery
3. Footed Bowl with the Crucifixion
4. Ambroise Vollard
5. A Bar at the Folies-Bergère
6. Landscape with the Flight into Egypt

The CTA strings (`Explore this painting / sculpture / piece of furniture in our virtual
tour`, `Create your own gallery`, `Join and Support`, `Shop the catalogue`) were dropped
at intake — the LOCAL-653 canonical-set junk reject line names each of them — and appear
**nowhere** in the final Selected or Dropped lists. In the LEAD's failing runs they were
SELECTED as stops; here they are gone.

**Tour-level outcome:** the job ended `error / factual_integrity`. This is unrelated to the
CTA fix: in my isolated container every OSM Overpass lookup raised `ConnectionError`, and
the template base writer (no Claude) tripped `D3(e) No duplicate stops` / `D3(c) shingles`
on the two "Landscape with the Flight into Egypt" duplicates — exactly the D3(e) refusal
the LEAD already observed on the Claude runs. No CTA stop was involved in the refusal.

**Meter cost:** `$0.769801` (`[COST_METER] FRESH | tour_generate | $0.769801`) — under the
$1.50 budget.

**`audio_tours` row count:** 498 before / 498 after — calling `/generate` directly writes
no `audio_tours` rows, as expected.

## Process compliance

- Branched from HEAD (`subscribed` = 7a5c411f); verified `git merge-base --is-ancestor
  7a5c411f HEAD` → 0. Did not branch from `origin/*`.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, or `.continuous_dev/`.
- No phones; no `audioura-*` containers touched. Captured live env kept in gitignored
  `.local721_live/` (never committed).
