**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-313
**Base:** storied
**Branch:** kiro/local313-dining-verification

# Restaurant tours produce nothing. We look for bistros in an encyclopedia.

Read `DECISIONS.md` **D162**, `SUBMISSION_LOCAL-281.md`, `stop_existence_gate.py`
(`_check_dining_existence`), `SUBMISSION_LOCAL-290.md` (the same bug, fixed for
geography).

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Production real row count stays **29**.

## The measurement

A 5-stop restaurant tour of Old Nice, requested this afternoon, produced **no
tour at all**:

```
[EXISTENCE-GATE] ENFORCE — 0/6 stops verified (0%), dropping 6 unverified
  [UNVERIFIED] 'La Rossettisserie'    — no evidence
  [UNVERIFIED] 'Le Safari'            — no evidence
  [UNVERIFIED] 'Chez Palmyre'         — no evidence
  [UNVERIFIED] 'Le Tire Bouchon'      — no evidence
  [UNVERIFIED] "Le Bistrot d'Antoine" — no evidence
  [UNVERIFIED] 'Le Vieux Four'        — no evidence
[LOCAL-245] EXISTENCE-GATE: tour SHORT — 0/5 stops, triggering replenishment
X All POIs were filtered out; cannot continue
FATAL: All generation attempts returned None
```

**The selector was right. Every one of those is a real, operating restaurant in
Vieux Nice.** LEAD verified externally:

- **Chez Palmyre** — 25-seat bistrot opened by Palmyre Moni in **1926**, taken
  over in 2010 by Vincent Verneveaux; Tripadvisor listing, France Today feature.
- **Le Bistrot d'Antoine** — 27 Rue de la Préfecture; **Gault&Millau** entry.

They fail because `_check_dining_existence` seeks tier-1 encyclopedia evidence —
Wikipedia and Wikidata. **Famous restaurants do not have Wikipedia articles.**
They have guide entries, review-site listings and press.

**This is D162 for the third time.** The Grant print in July (LEAD's own error,
eight days, real corpus deleted). Old Town of Menton and Corniche d'Or last night
(LOCAL-290, geographic path). Now every restaurant in Old Nice. Each time the
same shape: *we consulted a source that would not know, and treated silence as
proof of absence.*

## Scope

**Verify a restaurant against sources that list restaurants.**

Keep the tier-1 path — if a place *does* have a Wikipedia entry, that still
counts. Add fallbacks appropriate to the kind:

1. **A culinary/guide source** — Gault&Millau, Michelin, or equivalent structured
   listing.
2. **A mapping/POI source** with an address in the requested area — OpenStreetMap
   / Nominatim is free and well suited to "does this establishment exist at this
   address".
3. **Proximity still binds.** LOCAL-281 established that Le Chantecler in *Lyon*
   must fail a Nice tour. Whatever source confirms existence must also place it
   in the requested area.

**Order matters: cheapest and most reliable first, and stop on the first
confirmation.** Do not query four sources for a place the first one confirms.

## The line you must not cross

**Do not weaken the gate into a rubber stamp.** A fabricated restaurant name must
still fail. LOCAL-281's tests are the floor: an invented name fails, and a real
restaurant in the wrong city fails on proximity. Both must still hold — run those
tests and paste the output.

**Do not remove the dining kind** and treat restaurants as geographic areas. The
distinction is correct; only its evidence sources are wrong.

**Do not accept "the model says it exists".** The whole point of the gate is
independent evidence. An LLM asserting a restaurant is real is not a source.

## Verification

- All six restaurants above verify, each with the source that confirmed it.
- A fabricated name — e.g. `Le Restaurant Imaginaire` — still fails.
- A real restaurant in the wrong city still fails proximity.
- **Regenerate the 5-stop Old Nice restaurant tour.** It must produce a tour.
  Report stops requested/verified/delivered, words, cost, and copy it to
  `/Users/micha/Audioura/tours/`.
- Confirm museum and biking verification are unregressed: run one 2-stop Riviera
  and report delivery.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- Read the delivered tour as prose (D161).
- Rate limits: a 429 is a *search failure*, not "no data" (D220). Fail closed.
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria
- The six named restaurants verify, with per-source evidence.
- Fabricated and out-of-region cases still fail.
- A 5-stop Old Nice restaurant tour is actually produced.
- Museum and biking paths unregressed.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-313.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
