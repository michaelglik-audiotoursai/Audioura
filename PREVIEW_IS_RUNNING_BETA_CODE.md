# Preview has never run Storied generation code — confirmed 2026-09-15

**Michael was right, and the cause is deeper than the gateway.** Answering his question:
"confirm what storied-api is actually deployed from."

## The one-line answer

**There is no Storied tour generator deployed at all.** `tour-orchestrator-storied` does
not generate text — it POSTs to another service, and that service is **Beta's**
`tour-generator`, which runs main's code. Every Preview tour is written by Beta.

## The chain, each link verified

```
storied-api.audioura.com
  -> api-gateway-storied          image api-gateway:v35        (built from MAIN)
     ORCHESTRATOR_URL = tour-orchestrator-storied
  -> tour-orchestrator-storied    image audioura:storied       TOUR_TRACK=storied
     TOUR_GENERATOR_URL = https://tour-generator-...           <-- BETA's service
  -> tour-generator               image audioura:v36           (built from MAIN)
     generate_tour_text.py is byte-identical to origin/main
```

`tour_orchestrator_service.py:671` in the deployed storied image:

```python
response = _authenticated_request("POST", f"{TOUR_GENERATOR_URL}/generate", ...)
```

It delegates. It does not generate.

## Proof by effect, not by reading

Generated one tour on Preview — `Promenade des Anglais, Nice`, job
`602f9d27-a67b-439d-befe-392bec414660`, tour **422**.

**The label is right:**

```
DB:            id=422 track=storied
/tours-near:   id=422 track='storied'   (via storied-api)
```

**And Beta's generator is what produced the text.** Cloud Run logs for the
**`tour-generator`** service, during that job:

```
2026-09-15T03:31:11Z  Orientation: Head southeast on Prom. des Anglais As you stroll
                      along the iconic Promenade des Anglais in Nice,...
2026-09-15T03:31:11Z  Type/Specialty: Luxury hotel
2026-09-15T03:31:19Z  GET /status/9fbdd96d-... 200
```

That is the tour text being written inside the **Beta** service, for a tour recorded as
`track='storied'`.

**So `track` is not lying about which service handled the request — it is lying about
which engine wrote the words.** For the Storied-vs-Beta comparison, that is the same
thing as lying.

## And the storied image is a month stale regardless

Even if the routing were fixed, `audioura:storied` is old:

| `generate_tour_text.py` | lines |
|---|---|
| `origin/main` | 1,874 |
| `origin/storied` (today) | **18,703** |
| inside `audioura:storied` | **13,531** |

13,531 lines matches commit **`a57dc507`, 2026-08-11** — *"LOCAL-411: rank and cap
snippets"*. So the storied image predates D556–D559 and roughly five thousand lines of
subsequent work. That copy is dead weight inside the image: it is never executed,
because the orchestrator delegates.

## What this means

**Preview and Stable are currently the same engine.** Any tester comparison made so far
compares Beta against Beta. The 8 tours around Nice reading `track='storied'` were all
Beta-generated.

This does not invalidate the `track` field itself — the field works and is worth having.
It invalidates the conclusion anyone would draw from it today.

## What has to change (NOT done here — needs Michael's approval to deploy)

1. **Build a Storied generator image from `storied`**, into the separate repo
   **`audioura-storied`**, never the shared `audioura` tag. STORIED-4 already established
   why: every service shares `audioura:vN` differing only by `CMD`, so a Storied build on
   that tag would ship Storied code into Beta on the next routine bump.
2. **Deploy `tour-generator-storied`** from that image.
3. **Repoint `tour-orchestrator-storied`**: `TOUR_GENERATOR_URL` → the new service.
   Also check `MODERNIZED_URL`, which today points at Beta's `tour-modernized` (v37) and
   has the same problem.
4. **Rebuild `audioura:storied`** for the orchestrator from current `storied`, so it is
   not a month behind.
5. **Verify by effect:** generate one tour on each track for the same venue and show the
   generator logs come from *different* services, plus a text difference. `track` alone
   is not evidence — tour 422 proves that.

`deploy_storied_service.sh` on branch `kiro/storied-4` was written for exactly this and
is `--dry-run` verified; it already supports `--repo-image`.

## Separately: the port Michael asked for

`8f5879f` (the `/user` registration fix, the `track` field, and the `cryptography`
dependency) was on `main` only. It is now ported to `storied` as
**`port/services-fixes-to-storied` @ `5b38605`**, based on `2c85717`, pushed.

One conflict, resolved deliberately: storied's `/tours-near` query carries
`is_test IS NOT TRUE` and `original_tour_id IS NULL`, which main has never had. **Those
filters were kept** — dropping them would make Storied start listing translations and
test tours. The main-side column-existence guard was kept too.

Not merged to `storied`. It has not been reviewed yet — `GCS-REVIEW-1` is reviewing the
`main` version of the same change.
