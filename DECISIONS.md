# Decisions log — made by LEAD, for Michael to review or overturn

Michael, 2026-07-31: *"do not make any strategy to be mine: make your own
judgement. Only irreversible decisions should get to me. If I do not like
the version strategy: I will change it... Every time when you think of
delegating decisions to me, ask yourself, how risky it is and is it
irreversible... If not, make decision and record it for me to review."*

Every entry below is **reversible**. Overturn anything freely.

---

## D1 — Mobile version strategy

**Decision: build numbers are globally monotonic across all branches. The
next mobile build is `2.3.0+20`, incrementing the build number by 1 for
every build regardless of branch or version string.**

**The problem.** Two lineages disagree and one of them is already unsafe:

| Lineage | Version | Build |
|---|---|---|
| `services-migration` (per `remind_mobile_ai.md`, head `f72ee23`) | v2.1.1 | **+9** |
| `storied` (`audio_tour_app/pubspec.yaml`) | v2.2.0 | **+1** |

Michael's only stated requirement is that versions be **unique**. Today they
are not safe: `storied` has a *higher* version string (2.2.0) with a *lower*
build number (+1) than `services-migration` (2.1.1+9). App stores order and
deduplicate on the **build number**. Two branches can trivially produce the
same one.

**Rationale.** Global monotonicity is the only rule that guarantees
uniqueness without coordination between branches — it needs no shared state
beyond "pick a number higher than any used so far". Starting at **20**
leaves clear headroom above the highest known (+9) so no historical build
can collide, and the gap is a visible marker of where the policy began.

Version *string* follows semantics independently: Subscribed is a feature,
so `2.3.0`. Bug fixes on it become `2.3.1`, `2.3.2`, each with the next
build number.

**Not done, deliberately:** I have not renumbered or bumped anything yet.
This is the policy going forward; the first build under it will be
`2.3.0+20`. Nothing existing was rewritten.

---

## D2 — Does the $2/month Pay-Per-Use fee also apply to Unlimited?

**Decision: no. $50/month covers everything; Unlimited subscribers are not
charged the $2 fee.**

Michael wrote Unlimited *"Includes all what is in Pay-Per-Use"*, which reads
as feature inclusion, not fee stacking. Billing $52 to a customer told the
price is $50 is the kind of surprise that generates refund requests. If he
meant $52, it is a one-line config change.

---

## D3 — Pay-Per-Use hits zero balance

**Decision: hard stop, with a top-up reminder. No negative balance from
normal use.**

A refund clawback may still drive a balance negative — that is recorded, not
prevented (per Michael: *"No Problem"*). But ordinary consumption stops at
zero rather than accruing debt. Letting users run up a balance we cannot
collect through Apple is a real loss; a stop is merely an inconvenience.

---

## D4 — Unlimited reaches its cost stop (our spend hits $25)

**Decision: show a clear message naming what happened, and offer to switch
to Pay-Per-Use for the remainder of the month.**

Silent failure is the worst option for someone paying $50 — they would
assume the app is broken. Being told "this month's allowance is used, here
is how to continue" is recoverable. The switch offer keeps them served
instead of blocked.

---

## D5 — Does the `free` plan survive?

**Decision: yes, unchanged.**

It is the pre-subscription default and every existing user is on it.
Changing it would silently alter behaviour for people who never opted into
anything. Subscribed adds tiers alongside; it does not migrate anyone.

---

## D6 — Mobile branch lineage for Subscribed work

**Decision: Subscribed mobile work happens on branches off `storied`, merged
into `subscribed`. `services-migration` is not touched.**

`storied` is now on origin and is the lineage Michael is actively field-
testing. Splitting Subscribed across two lineages would guarantee a painful
merge. If `services-migration` holds mobile work that must survive, that is
a reconciliation task of its own — flagged, not silently resolved.

---

## D7 — Cost basis for pricing is currently understated

**Decision: do not calibrate pricing against today's measured cost. Fix the
corpus ImportError first (LOCAL-63), then re-measure.**

`generate_tour_text.py:2888` and `:2982` both raise
`ImportError: cannot import name 'extract_catalogue_works_from_pages'`,
swallowed by `try/except`. Tours generate without the story pipeline, so the
measured $0.043 excludes corpus mining — note `search: 0.0` in the
breakdown. Setting a ×5 price against that number would misprice every tour.
