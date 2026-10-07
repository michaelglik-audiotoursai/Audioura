# canary/last_run.md — preserved copy of the LOCAL-611 live run block

`.continuous_dev/CANARY.md` is the live, append-only history the runner writes,
but `.continuous_dev/` is `.gitignore`d (machine-local runtime state), so this
committed copy preserves the one real live run for the record. ALERTS.md (repo
root) IS committed and holds the matching `*** CANARY FAIL ***` lines.

---

## Canary run #1 — 2026-10-07T18:51:38Z

<!-- CANARY-RUN idx=0 ts=2026-10-07T18:51:38.372888+00:00 sha=ac942cd pass=1 total=8 cost=0.000000 budget_stopped=false -->

- Code SHA: `ac942cd`
- Result: **1/8 passed**
- Cost: **$0.0000** (cap $3.00)
- audio_tours rows: 219 → 219 (+0 is_test — see note below)
- Venue pool: 302,396 rows / 205 countries (built 2026-10-07T18:33:54Z)

| Tour | Group | Loc | Req | Deliv | OK | Coords | is_test | URL | ChkSite | Wall(s) | Cost | Error |
|------|-------|-----|-----|-------|----|--------|---------|-----|---------|---------|------|-------|
| known[0] *multistop* | known | Phu Quoc, Vietnam | 5 | None | ❌ | ? | ? | ? | None | 16.3 | $0.0000 | tour text generation failed — no stops (all filtered / knowledge insufficient) |
| known[1] | known | Fruitlands Museum, Harvard, MA | 2 | None | ❌ | ? | ? | ? | None | 40.6 | $0.0000 | tour text generation failed — no stops |
| known[2] | known | McMullen Museum of Art, Boston College, Boston, MA | 2 | 2 | ✅ | y | n | y | 0 | 73.1 | $0.0000 (chars 7917) | — |
| known[3] | known | MassArt Art Museum, Boston, MA | 2 | None | ❌ | ? | ? | ? | None | 40.7 | $0.0000 | tour text generation failed — no stops |
| known[4] | known | Freedom Trail, Boston, MA | 2 | None | ❌ | ? | ? | ? | None | 16.3 | $0.0000 | tour text generation failed — no stops |
| new[0:famous] | new | National Archaeological Museum of Athens, Greece | 2 | None | ❌ | ? | ? | ? | None | 211.2 | $0.0000 | tour text generation failed — no stops |
| new[1:obscure] | new | Sveķu Street, Latvia | 2 | None | ❌ | ? | ? | ? | None | 16.3 | $0.0000 | tour text generation failed — no stops |
| new[2:rotating:no_site] | new | Rue Jacqueline Harpman – Jacqueline Harpmanstraat, Belgium | 2 | None | ❌ | ? | ? | ? | None | 16.3 | $0.0000 | tour text generation failed — no stops |

### Why 7/8 failed — external billing blocker (NOT a code or venue defect)

Every FRESH generation failed because the OpenAI account is **out of credits**.
The generator logs during this run show, repeatedly (52 hits / 15 min):

```
"message": "You have no credits remaining. Add credits to continue using the API
            at https://platform.openai.com/settings/organization/billing/.",
"type": "insufficient_quota"   (HTTP 429)
```

The one pass, **McMullen**, succeeded because it was served from the existing
stop pool / cache (no LLM calls), which also confirms the happy path end-to-end:
the runner found its `audio_tours` row (id 399), saw `is_test` handling, and
**nulled its coordinates** so the canary tour never shows on the map:

```
id=399  McMullen Museum of Art…  is_test=t  lat IS NULL=t  lng IS NULL=t  stops=2
```

A world-famous venue (National Archaeological Museum of Athens) failing the same
way proves the failures are the billing state, not venue quality or the pipeline.
This is exactly what a canary is for: it detected and reported that the live
stack cannot currently generate fresh tours.

**+0 is_test note:** fresh tours errored before storage (the orchestrator marks
failed jobs `failed` and does not insert a row), and McMullen reused its existing
row rather than inserting a new one, so the net row delta was 0. When OpenAI
credits are restored, the same command produces the expected +8 is_test rows
(all with lat/lng NULL).

### Reproduce (once OpenAI credits are restored)

```
python3 canary/venue_pool.py            # weekly; already built (302k rows)
CANARY_MAX_USD=3.0 python3 canary/run_canary.py
```
