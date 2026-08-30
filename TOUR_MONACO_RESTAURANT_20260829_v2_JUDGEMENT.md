# Judgement — Restaurant tour in Monaco, 3 of 3 with stories (D548/D549)

**2026-08-29.** Tour: `TOUR_MONACO_RESTAURANT_20260829_v2.md`.
**Le Louis XV – Alain Ducasse · Le Grill · La Montgolfière.** 897 words.

---

## Michael's blocker, answered

> *"The major thing to fix is to add stories about people; without them we can not go to release
> and mobile testing. I do not understand why it is difficult … Gemini have no problems to come up
> with the stories, and yet, the system does not add them. Why??"*

**Three reasons. The third is the one that mattered and it invalidated all my earlier testing.**

### 1. We were asking Gemini about a museum object

`_gemini_facts()` hardcoded the museum system prompt and the `Object:` / `Museum:` framing for
every stop. For Elsa it sent:

> *"You supply factual reference material about ONE **museum object** … Object: Elsa, Museum:
> Restaurant tour in Monaco … maker, materials, dimensions, provenance"*

Gemini answered honestly and uselessly, the result was scored thin and discarded. Now focus-aware.

### 2. Retrieved episodes were offered as context, never required

They went in as search snippets, where `rank_and_cap_snippets` can score them `usable=0` and drop
them, and the prompt called them "reference material". The practicals had the identical problem and
only became reliable once stated as a **requirement**. `story_prompt_block()` now says: tell at
least one, name the person, give the date, say what came of it — and add nothing not listed.

### 3. **Gemini had never once run inside the container**

```
from story_leads import gemini_with_sources
  →  FileNotFoundError: '/app/.env'
```

`story_leads.py` opened `.env` **unconditionally at module import**. `.env` is in `.dockerignore`
— correctly, secrets do not belong in an image — so the import **raised inside the container**.
Every caller wraps it in `try/except`, so the failure was swallowed and the code fell back to
OpenAI+web.

**This is why my testing kept saying the fix worked.** I was verifying on the host, where `.env`
exists, and shipping to a container where the code path did not exist at all. The key was present,
the prompts were right, the wiring was right — and the module died on import before any of it
mattered. `.env` is now loaded if present and skipped if not.

## The result

| stop | hours | booking | price | cuisine | story |
|---|---|---|---|---|---|
| Le Louis XV | ✅ | ✅ | ✅ | ✅ | Rainier III's 1987 ultimatum, beaten in 33 months |
| Le Grill | ✅ | ✅ | ✅ | ✅ | Ducasse's start at Pavillon Landais, 1972 |
| La Montgolfière | ✅ | ✅ | ✅ | ✅ | Henri & Fabienne Geraci, 2 June 2011 |

**All four practical facts on all three stops** — up from 1 of 3 in the previous version — and a
named person with a date in every stop. Robuchon was dropped before the spine was written, so the
tour never mentions it.

The Le Louis XV story is Michael's own Gemini anecdote, retrieved independently and told properly:
the dare, the deadline, the stakes, and beating it by fifteen months.

## Honest limits

1. **The story gate still passes only 1 of 3.** Le Grill and La Montgolfière have a named person
   and a date but not a three-sentence arc with a consequence. They are better than descriptions
   and short of stories.
2. **Le Grill's lore came from `openai+web`, not Gemini** — Gemini returned thin for that venue.
   The escalation is working as designed; the coverage is not uniform.
3. **`closure_scan` remains the weakest component** — three false positives across the week
   (La Salière on a Florida snippet, Café de Paris once). It did not misfire this run. The corpus
   lookup and the Gemini check have produced none. **It should be demoted to advisory.**
4. **La Montgolfière is 200 words**, below the floor — replenished stops still arrive without the
   corpus material an originally-selected stop receives.

## Recommendation

**This is ready for the mobile test**, with (3) as the one thing I would fix first afterwards.

For the phone: **server IP `192.168.0.136`**, and request a location you have not generated —
`tour_cache` is keyed on (location, type, stop count) and will answer instantly from cache instead
of exercising the pipeline.

## The pattern worth carrying into Subscribed

**Ten failures this week, every one the same shape: correct code running nowhere that mattered.**
Museum-gated blocks, a data file that never entered the image, a city compared by equality, an
import that never applied, an edit that deleted a function, and finally a module that died on
import inside the container while passing every test on the host.

**Every one was hidden by a `try/except` that turned a hard failure into a silent downgrade, and
every one was found by reading tour output rather than by a green suite.** The practice that
actually catches them: **run the thing in the container it ships to, and show the log line where
the code fired.**
