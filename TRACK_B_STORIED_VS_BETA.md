# Track B — Storied vs Beta selector, end to end

**Written 2026-08-11 by LEAD, for execution in a SEPARATE Claude session.**
See "How to run this" at the bottom — the recommendation is deliberately not
"do it in the current thread".

---

## Goal, in Michael's words

> "I need to have an ability to let testers in Storied as well as to Beta. On
> Mobile app side for Cloud option there should be a new select box: **Storied vs.
> Beta** (Beta is what we have now and it is the only option now; Storied is what
> we will have once we finish this release) so my testers and myself can **compare
> the tours quality generated on Beta and Storied.**"

The product requirement is **comparison**. Every design decision below is judged by
whether it makes a side-by-side comparison of the same venue on both tracks easy.

---

## 1. Mobile (Android + iOS)

- In the **Cloud** option, add a selector: **Beta** (default, current behaviour) and
  **Storied**.
- The choice determines the **base URL** the app posts generation requests to.
- Persist it in app settings so a tester does not re-pick it every time, and show
  it somewhere always-visible during a session — a tester comparing two tours must
  never be unsure which track produced the one they are hearing. A small label on
  the tour list and on the player is enough.
- Store the track on the **generated tour record** so it survives the session: a
  tour listed a week later must still say which track made it.

**Do not** make Storied the default until Michael says so.

---

## 2. Routing

Two endpoints, one per track. The app sends to one or the other; nothing else in
the request changes. Keep the request/response contract **identical** across
tracks — if they diverge, comparison stops being like-for-like and the whole
exercise loses its meaning.

---

## 3. Database — recommendation: ONE Postgres, with a discriminator

Michael asked whether one repository can hold both. **Yes, and it is the better
choice.**

- Add a column `track` (or `environment`) to `audio_tours` — enum/text,
  `'beta' | 'storied'`, **NOT NULL DEFAULT 'beta'** so every existing row is
  correct without a backfill.
- Add the same discriminator to any table that hangs off a tour and is compared
  (e.g. `stop_metrics`).
- Index it alongside whatever the tour-list query already filters on.

**Why one DB rather than two:**
- Comparison becomes a `WHERE track = …` instead of a cross-database join. That is
  the entire point of the feature.
- One schema to migrate, one backup to keep, one set of credentials.
- The existing `backup_tours.sh` guard and row-count alerting keep working
  unchanged.

**The risk, stated honestly:** a Storied bug can now touch rows a Beta tester
depends on. Mitigate by rule, not by hope — the standing DB rules already forbid
`DELETE FROM audio_tours` (CLAUDE.md), every write is additive, and the 5-minutely
snapshot with `*** ROW LOSS ***` alerting stays on. If Michael would rather have
physical separation, two databases also work; it costs a second backup path and
makes comparison queries awkward.

**This is an additive schema change**, which CLAUDE.md permits without asking —
but it must be **declared** in the submission, with row counts before and after.

---

## 4. GCloud — two services, one data plane

- Duplicate the generation service so each track has its own deployment, its own
  image tag, and its own logs. They must be independently deployable: the point of
  Beta is that it does not move while Storied churns.
- Both talk to the **same** Postgres, writing their own `track` value.
- Keep resource sizing modest for Storied initially — it is a tester track, not
  production load.

---

## 5. Acceptance

- A tester can switch Beta ↔ Storied in the app and see, for the same venue, two
  tours that are clearly labelled and separately stored.
- The Beta path is **byte-for-byte unchanged** in behaviour. This is the one hard
  requirement: Beta is the control in the comparison, so any drift in it invalidates
  every comparison a tester makes.
- A single SQL query returns both tours for a venue side by side.
- Rollback is one setting change in the app (pick Beta) plus not deploying Storied.

---

## How to run this — LEAD's recommendation

**Use a separate Claude session, not the tour-quality thread.** Reasons:

1. **Different codebases.** This is mobile (Kotlin/Swift or Flutter) plus GCloud
   infra plus a schema migration. The tour-quality thread is deep in
   `generate_tour_text.py` prose logic. Sharing a session means both carry each
   other's context for no benefit.
2. **Cost.** Michael's own usage panel: *94% of usage was at >150k context* and
   *72% came from sessions active 8+ hours*. A long session is the expensive thing.
   Two focused sessions cost less than one that holds both.
3. **They are genuinely independent.** Track B does not need the story pipeline to
   work; Track A does not need the selector. Neither blocks the other.
4. **CLAUDE.md already has the shape for it** — `Mobile Kiro` on the Windows
   laptop, one branch per task, GitHub as the only sync channel.

**What the new session needs:** `cd ~/Audioura && bash restart.sh`, then this file.
It contains the full requirement; nothing needs carrying over from the tour thread.

**One coordination rule:** Track B changes the DB schema and the deployment
topology. Track A regenerates tours against that DB constantly. **Track B should
declare the migration in `DECISIONS.md` before applying it**, so a tour-thread run
that suddenly sees a new column knows why.
