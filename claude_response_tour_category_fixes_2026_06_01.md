# Claude Review — Tour Category Fixes + Test Findings (Services)
**Date:** 2026-06-01
**Reviewing:** `claude_review_tour_category_fixes_2026_06_01.md` (Kiro Amazon-Q), commits `9d0ce76` + `06ba427`
**Scope:** Services side only

---

## TL;DR

Kiro's two commits are **correct, well-reasoned, and verified in the committed code** — but they fix only the **icon/template classification** symptom. That is *one* of the four things you reported, and it is **not the most important one**.

- **Test #2 (walking icons):** ✅ Genuinely fixed. Approve.
- **Test #1 (Thoreau's Bedroom attributed to The Old Manse):** ❌ **Not addressed.** This is a *factual-accuracy* bug, not a category bug. The verification you asked about (`_validate_museum_stop_descriptions`, "PHASE 5.5b") **does exist and was almost certainly called — but it let the bad stop through because of a pre-filter gap.** Details below.
- **Tests #3 and #4 (newsletter: 2 of 5 downloaded; wrong article text):** ❌ Not touched by these commits at all. Separate pipeline, separate investigation needed.

So the answer to your direct question — *"Don't we have verification for each exhibit? Was it called?"* — is: **yes we have it, yes it ran, and it has a hole that this exact case falls through.**

---

## 1. The category fix (Kiro) — verified, approve

I read the live `_classify_tour_category` (generate_tour_text.py:293-331). It matches the document exactly: an `explicit_walking_phrases` check now runs **first**, before restaurant and museum. For your Portsmouth string ("walking tour in Portsmouth… with a stop at Strawbery Banke Museum") this correctly returns `walking`, so every stop gets the walking-person icon instead of a single museum icon. The S15 path (`_EXPLICIT_NON_MUSEUM_TOUR_RE`) already neutralised the museum venue-name, and the fallback now agrees. Good.

The Medfield fix (`or keyword in tour_type_lower` on the museum check) is also correct and addresses the inverse case.

**Minor notes (non-blocking):**
- `'walk in'` as an explicit-walking phrase is broad — it will match any location containing the substring "walk in" (e.g. "boardwalk in…", "catwalk in…", "walk-in clinic tour"). Low risk given your inputs, but consider word-boundary matching (`re.search(r'\bwalk(ing)? (tour|in)\b', …)`) instead of `in` substring tests.
- Answering Kiro's review questions: (Q1/Q3) yes, give restaurant the same explicit-phrase priority as walking for symmetry — "restaurant tour near the MFA" should be `restaurant`; cheap to add. (Q2) "walking tour of the MFA" → `walking` is acceptable for icons; don't over-engineer. (Q4) **Yes — having mobile send `tour_type="auto"` and letting services classify is the right long-term design.** Mobile keyword-guessing is the root of this whole class of bugs; every fix here is compensating for a guess the client shouldn't be making.

**But note what this fix is and isn't:** it changes which *icon/template* a tour uses. It does nothing about whether the *content* of a stop is factually correct. Test #1 is the latter.

---

## 2. Test #1 — the real bug Kiro did not fix

### What you saw
"the old manse house-museum, Concord, MA", 4 stops. Stop 2 = **"Thoreau's Bedroom"** with Thoreau's bed and personal artifacts — which are at the **Concord Museum**, not The Old Manse. The category was correct (museum, S15-forced). The *facts* were wrong.

### Was verification called? Yes.
`generate_tour_text.py:1456-1460` runs PHASE 5.5b for exactly this kind of tour:

```python
if tour_category == 'museum' and _museum_venue_name:
    poi_list = _validate_museum_stop_descriptions(poi_list, _museum_venue_name, headers)
```

`_validate_museum_stop_descriptions` is a genuine fact-checker: for suspect stops it asks GPT *"Does this description refer to content physically located INSIDE 'The Old Manse', or a DIFFERENT institution / fabricated exhibit?"* and removes the ones that aren't. That is precisely the guard you're asking about. It ran. It just never *checked* "Thoreau's Bedroom".

### Why it missed it — the pre-filter gap
To save API cost, the function only sends a stop to the GPT fact-check if a cheap pre-filter, `_is_suspect()`, flags it (generate_tour_text.py:359-370). `_is_suspect` returns **True only when the stop *name* contains an institutional marker word**:

```python
_INSTITUTION_MARKERS = {'museum','gallery','institute','society','foundation','university','college','library'}
def _is_suspect(stop_name):
    name_words = set(re.findall(r'[a-z]+', stop_name.lower()))
    if not (name_words & _INSTITUTION_MARKERS):
        return False  # no institutional marker — treated as a harmless room/exhibit
    ...
```

**"Thoreau's Bedroom" contains none of those marker words**, so `_is_suspect` returns `False`, the stop is bucketed as "clean", and it bypasses the GPT fact-check entirely (generate_tour_text.py:415-416). The pre-filter's stated assumption — *"no institutional marker → probably a room/exhibit [and therefore safe]"* — is exactly backwards for this failure mode: a misattributed exhibit from *another* museum looks like an innocent room name. The check is good at catching "stop is a whole different **institution**" and blind to "stop is a real exhibit that lives in a **different** museum."

### Recommended fix (services)
The cheap name-only pre-filter is the weak link. Options, cheapest first:

1. **Lower the bar for "suspect" on single-venue museum tours.** When `_museum_venue_name` is set and the tour is venue-locked, the per-stop GPT description check is worth running on *every* non-zero stop, not just institution-named ones. For a 4-stop tour that's 3 cheap `gpt-3.5-turbo`, 60-token calls — negligible cost for the accuracy you need. This single change would have caught Thoreau's Bedroom.
2. **Add proper-noun / person-name detection to `_is_suspect`** (e.g. a stop named after a person — "Thoreau", "Emerson" — whose artifacts are commonly housed elsewhere). Weaker and more heuristic than option 1.
3. **Have the description-generation prompt assert venue containment up front** ("every stop MUST be physically inside The Old Manse; do not include artifacts housed at other institutions"), so the model is less likely to introduce the error in the first place. Do this *in addition to* the post-check, not instead.

I'd ship option 1 (and 3). It directly closes the hole and keeps the existing remove-stop machinery.

---

## 3. Tests #3 and #4 — newsletter pipeline, not addressed

Neither commit touches the newsletter/news-article services, so these remain open:

- **#3 — "download all 5 in Russian" produced only 2.** This is a download/translation-pipeline count mismatch (partial completion). The iOS black-screen on Refresh is, as you say, a mobile/iOS-AQ concern — but **"2 of 5" is a services symptom** (articles silently dropped, or per-article translation failing without surfacing an error). Worth checking `news_processor_service.py` / `news_generator_service.py` for per-article error swallowing and whether the "5 found" count and the "downloadable" count come from the same source of truth.
- **#4 — generated article text differs from the source URL.** `https://www.reloadnyc.com/r/ab1715bb?m=…` is a **tracking/redirect link**, not a canonical article URL. The extractor most likely followed the redirect to a different landing target (or grabbed boilerplate / a different article from the newsletter index) rather than the specific content you copied. This points at the URL-resolution / content-extraction step, not translation.

I did not dig into `log_iphone_06012026_2045.txt` / `_2058.txt` yet — say the word and I'll trace both through the services logs and pin the exact drop points. They're a different subsystem from the category work and deserve their own pass.

---

## 4. Bottom line for Kiro

Approve `9d0ce76` + `06ba427` as a correct fix **for the icon symptom (#2)** — with the minor `walk in` boundary nit. But please **do not consider test #1 resolved**: the category was never the problem there; the exhibit fact-check has a pre-filter blind spot that let a real-but-misattributed exhibit through. Recommend running the PHASE 5.5b GPT description check on **all** stops of a single-venue museum tour (option 1, §2). Tests #3/#4 are a separate newsletter-pipeline investigation that these commits don't touch.
