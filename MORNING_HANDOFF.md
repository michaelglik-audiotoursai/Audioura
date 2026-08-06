# Morning handoff — 6 August 2026

Overnight: **14 merges, 26 decisions (D200–D224)**, `storied` fully pushed at
`ea49085`. Production real tour count **29, unchanged all night**; Nice list
`[1,12,14,17,24,29,152]` intact.

`STATUS.md` is 2,010 lines. This is the short version.

---

## 1. Seven things need you. Two are urgent.

### ⚠️ URGENT — a credential is in git history and pushed to GitHub

`tests/run_mobile_decryption.py:58-59` holds `boston_username` /
`boston_password`, labelled *"Boston Globe credentials"*. They are AES ciphertext
with **random IVs**, so they came from a real encryption run — and **the
`device_key` that decrypts them is on line 28 of the same file.**

Introduced in commit `0e2ed2e`, long before last night; it resurfaced because a
rename put the file back in the secret scanner's 20-commit window. The alert has
been re-firing every ~5 minutes since 05:30, deliberately not suppressed.

**If those are real, rotate them.** Rotation is the only step that helps once
something is pushed; a history rewrite afterwards is secondary and is yours to
authorise. I did not decrypt them and did not rewrite history.

*(The other two flagged strings on lines 32-33 are synthetic — their IV is
literally `00112233…eeff`. Cleared, with evidence, in `secret_scan_cleared.txt`.)*

### ⚠️ URGENT-ish — I created a production tour row by accident

`id=301`, *"Nice, France - Walking Tour"*, 13:09:43Z. A diagnostic probe of mine
queued a real generation while I was testing whether a quota error was global or
per-user. Real rows went 29 → 30.

Handled reversibly: `is_test` set TRUE (back to 29), `lat`/`lng` NULLed so it
stays out of your Nice list. **Original coordinates: `43.6942, 7.2797`.**
**Not deleted** — delete it, or restore those coordinates if you want the tour.

My error, and a bad one: I spent the night writing "do not write to production"
into task files and then used the one probe method with a side effect. Recorded
as D223.

### The five judgement calls

| # | Question | My view |
|---|---|---|
| 1 | `MISSING` and `FABRICATED` both cost −1.0 × share. Omitting a stop disappoints; inventing one misleads. | Fabrication should cost more. The ratio is a product call about listener harm — yours. |
| 2 | Structural surcharge saturates at 2 defects. D200 added three more defect types, so it now binds routinely. | Raise the cap, or drop a stop to THIN past some defect count. |
| 3 | Should events be tour stops? The landmark filter now admits "Nice Carnival", "Siege of Nice", "2016 Nice truck attack" — real, in-area, correctly typed. | Genuinely unclear. The 33 logged unknown P31 types are the evidence to decide from. |
| 4 | 124 test rows sit in production `audio_tours` against 29 real. New writes are stopped; clearing the backlog is a deletion. | Worth clearing, but deletion is yours. |
| 5 | Test tours run as hardcoded `test_user_123`, now at **10/10 daily quota**, resetting 00:00 UTC. This alone fails a cluster of suite tests — not a code defect. | Unique user id per run, or raise that user's quota. Either changes product behaviour. |

---

## 2. What got fixed

**Tour quality** — the work you were reading last night:

- gloss composition (LOCAL-287) and its degrade path (LOCAL-289): no more
  `"existentialism., and Pablo Picasso"` or `"shaping 's landscape"`
- museum opening (LOCAL-286): no "walking journey" indoors, no "0 meters",
  `Tour-Category` correct, R7 now gates the prolog
- closing recap (LOCAL-280, four rounds): *"That's 5 stops and 106 kilometres —
  Cap d'Antibes, where Scott Fitzgerald depicted the Roaring Twenties…"*
- stop selection (LOCAL-290): **Old Town of Menton and Corniche d'Or now verify.**
  Your instinct was right — the Riviera never ran out of places; we were
  rejecting real ones for absence from our own corpus. 8-stop delivery went from
  5/8 to 8/8.
- empty stops removed rather than shipped as address-only shells (LOCAL-292)

**The evaluation index** — now computes its own classification, with
groundedness as a RICH ceiling and CONTRADICTED scored proportionally. Note the
caveat you should keep: **no stop in the 270-tour artifact is marked
FABRICATED**, so every score there assumes all claims are true.

**Test infrastructure** — `pytest tests/` runs for the first time in months
(1014 tests collected). Collection no longer executes database scripts. Tests can
target `audiotours_test`, which now has real schema.

---

## 3. What I got wrong

Worth your scepticism when reading my other claims:

- **Five times** a measurement was sound and my inference went one step past it
  (D211, D214, D215, D217, D219). Once I was wrong by 40×.
- **Twice** a diagnostic I wrote manufactured the symptom it reported — a probe
  missing a User-Agent produced a "403" that existed nowhere in the code (D220),
  and the probe above created a real tour (D223).
- I described the DB safety switch as making the suite safe against production.
  It covers in-process access only; service-driven tests bypass it entirely
  (D221). I should have said so when merging, not after seeing rows appear.
- I nearly bounced correct work on a faulty AST scan (D215).

The check that caught most of these, and that I should reach for first: **run the
failing thing in isolation, and ask what I changed, before theorising.**

---

## 4. Where things stand

Queue empty, nothing in flight, nothing invented to fill it. Ten suite failures
remain, catalogued in `TEST_FAILURE_TRIAGE.md` — several are the quota issue in
row 5 above and will clear on their own at 00:00 UTC.

No tour has been generated for you to read since round 34. Say the word and I
will run one on the current pipeline — every fix above is merged, so it should
read considerably better than the one you last saw.
