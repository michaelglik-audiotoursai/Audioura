# LOCAL-424 — The verifier extracts zero claims; and switch the story pass to GPT-4o

## Highest priority. Branch off `storied`. Read the BASE block at the top first.

LOCAL-423 is **merged** — its entity disambiguation, contradiction detection and
query shape all work, and LEAD confirmed them live. Two things are broken, and one
decision from Michael needs implementing.

## 1. `extract_claims()` returns nothing — the verifier verifies nothing

Measured by LEAD on a real delivered story from the gpt-4o run:

```python
from story_verifier import extract_claims
story = ("Louis Broder, a visionary publisher known for his dedication to the livre "
         "d'artiste, commissioned Miro for this project. ... The lithographs were "
         "printed by the renowned Mourlot Freres ... Boris Fridman, a dedicated "
         "collector of artist books, generously donated this work to the Museum of "
         "Fine Arts, Boston. His gift enhances the museum's extensive collection of "
         "Surrealist-era printed works.")
extract_claims(story)   # -> 0
```

**Five sentences, at least six checkable assertions, zero claims extracted.** In the
live runs it reported `claims=1` on one story and 0 here — so
`STORY VERIFICATION: ALL STOPS PASSED` was printing over stories nobody checked.

**LEAD has already added a stop-gap** (`D369`): `claims_extracted == 0` is now
forced to FAIL with reason `VACUOUS: 0 claims extracted`. That prevents the
false green. **It does not fix extraction — you do.**

### What a claim is, for this purpose
Anything a visitor could check and find wrong:
- **attribution** — X commissioned / printed / published / donated Y
- **role or description of a person or house** — "a visionary publisher known for…",
  "a printing house famous for…", "a dedicated collector of…"
- **quantity, date, material, place** — 40 lithographs, 1971, vellum, Paris
- **institutional claims** — "enhances the museum's extensive collection of
  Surrealist-era printed works"

That last kind is the most dangerous and the current extractor misses it entirely:
it sounds like colour and is actually an assertion about a real museum's holdings.

### Acceptance for this part
- `extract_claims()` on the story above returns **≥6** claims — paste the list
- Every claim carries the subject it is about, so verification can match it
- A test with that exact story text, red against current `storied`

## 2. The tests do not bind to the production call site — again

Neutralising the call site (`_sv_result = None and verify_story_candidate(...)`)
while leaving `story_verifier.py` fully intact:

```
18 passed
```

All eighteen. This is the same gap LOCAL-422 was built to close, reopened one round
later. Use 422's pattern — `tests/test_local422_call_site_binding.py` is the model
to copy, and `resolve_final_description` shows the shape: extract the decision so a
test can call it directly.

**LEAD verifies by keeping `story_verifier.py` untouched and neutralising only the
call site in `generate_tour_text.py`. Helper-only tests do not count.**

## 3. Michael's decision: GPT-4o for the story pass only — ✅ ALREADY DONE BY LEAD

**DO NOT IMPLEMENT THIS. LEAD committed it before dispatching you** (2026-08-11 22:2x).
It is described below for context only. Touching it again will collide.

What landed in `generate_tour_text.py`:
- module-scope `story_pass_model()` → `os.environ.get("TOUR_STORY_MODEL", "gpt-4o")`
- the per-stop `description_data["model"]` calls it (one dict, reused across all retries)
- `_tour_llm_cost(tokens, model=...)` — the story pass is now priced at the model it
  actually called. LEAD found this second edit was required: without it a gpt-4o call
  bills at gpt-3.5 rates and Subscribed charges 5× the understatement.
- `test_d370_story_pass_model.py`, 7 tests, bound to the production call site by `ast`
  (both edits verified red when reverted)

**Your job for the story model is only to USE it:** run the eval with
`TOUR_STORY_MODEL` unset (it now defaults to gpt-4o) and report the cost you observe.

---

_Original text, for context:_

**Michael approved this after seeing the evidence** — implement it properly.

| | story gate |
|---|---|
| gpt-3.5 | 0–2 sentences, **FAILED** |
| gpt-4o, story pass only | **PASSED**, `story_count=5, entities_ok=True, thesis_ok=True` |

**It must be the narrow switch.** LEAD set `TOUR_LLM_MODEL=gpt-4o` globally and the
tour **failed to generate at all** — gpt-4o read the POI-discovery prompt as "find
art venues in Boston", returned six different museums, and `BLOCKER4b` correctly
rejected it. The upstream phases are tuned to gpt-3.5's literalism.

LEAD's experimental patch (not committed) was:

```python
"model": os.environ.get("TOUR_STORY_MODEL") or os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
```

at the per-stop description call. Make that real: `TOUR_STORY_MODEL` defaults to
**gpt-4o**, everything else stays on gpt-3.5. Document it in the task's submission,
not in CLAUDE.md.

**Cost measured:** $0.0111/tour with gpt-4o on the story pass vs ~$0.003–0.005 on
gpt-3.5. 2–3× on a sub-cent line, negligible beside SERP. Report your own figure.

## 4. Also seen twice, report but do not fix here

`prose_llm_extract_works` returned **1 work instead of 3** on two consecutive runs,
so both gpt-4o tours delivered a single stop. Structured extraction returns 0 on
both `storied` and 423's tree (expected post-418 — it falls through to prose). This
is extraction variance, unrelated to the story model. **Say what you observe; do not
fix it here** — it needs its own task.

## Acceptance — live, delivered text only (D284/D312)

- `extract_claims()` returns ≥6 on the quoted story; test red against `storied`
- Call-site binding proven by neutralisation for `verify_story_candidate` — paste
  the red output
- **Two consecutive** runs of the committed `run_mfa_unbound_eval.py` with
  `TOUR_STORY_MODEL` in effect, each stop carrying a story of ≥3 sentences with
  every claim mapped to a source URL
- At least one claim **rejected** as unsourced — with real extraction working, a run
  that rejects nothing is a run where verification is still not working
- No stop reports `VACUOUS`
- Report the observed work-extraction count per run (item 4)

**Control (D302/D326):** Palais 4/4, dates intact.

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`.

## PROCESS
- Branch `kiro/local424-verify-what-you-claim-to-verify` off `storied`, from
  **HEAD** — never `origin/storied` (D358).
- **Commit early and often** (D352).
- Write `SUBMISSION_LOCAL-424.md`, citing only files your own run produced.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
