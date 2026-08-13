# BASE — read before your first git command

Your worktree is already checked out at the correct base: **storied = 9951f3f**.

Create your branch from **HEAD**:

    git checkout -b <branch-name>

**Never branch from `origin/anything`.** `origin/storied` is many commits
behind local `storied` — local is held unpushed behind a field-test gate.
Branching from origin silently puts your work on a stale tree, and every
live run you make there measures old code (D358).

Verify before you commit: `git merge-base --is-ancestor 9951f3f HEAD`
must exit 0. If it does not, you are on the wrong base — fix it first.

---

**Task ID:** LOCAL-428

# LOCAL-428 — a check that deletes good content is worse than no check

## RESUME — a previous attempt was killed mid-flight; its work is still in your worktree

An earlier run of this task was terminated by LEAD **by accident** at 227s (SIGTERM,
not a fault of the work). Its uncommitted output is still in your worktree and you
should **build on it, not restart**:

- `generate_tour_text.py` — module-scope `check_part4_attribution(part4_text, stop_data)`
  and `should_inject_venue_snippet(...)`, with the Part 4 loop already calling the
  former and the `([] if True else ...)` gate removed
- `tests/test_local428_part4_attribution.py` — imports both from production (good)

**It is not finished.** `python3 -m pytest tests/test_local428_part4_attribution.py`
currently gives **6 passed, 2 failed**, and the two failures are the two cases this
task exists to get right:

```
FAILED TestCheckPart4Attribution::test_prompt_worked_example_passes
FAILED TestCheckPart4Attribution::test_d373_misattribution_fails
```

Read the existing implementation, fix the clause-attribution logic until both pass,
then continue with the rest of the task below. Nothing is committed yet.

## BASE

Branch off `storied`. Own worktree. Submission to `SUBMISSION_LOCAL-428.md` in YOUR
worktree. **Do NOT edit** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
`.continuous_dev/STATUS.md`.

LOCAL-427 (`62f126c`) is **merged**, and one part of it is **gated off** at `c000810`.
Read **D376** and **D375** in `DECISIONS.md` before planning. LOCAL-427's retry/backoff
and page cache in `exhibition_checklist.py` are good and are not in scope here — do
not touch them.

## Part 1 — the Part 4 cross-reference validator is wrong, and it deletes Part 4

LOCAL-427 added a check that Part 4's "\<fact\> at \<stop name\>" attributions point at
the right stop. The intent is right — D373 recorded a real bug where Moses and
Monotheism content was attributed to "Au Soleil du Plafond". The implementation is
not: it finds the stop name, takes a **±80 character window**, collects every 4-digit
year in that window, and fails if a year is not in that stop's own description.

A Part 4 is 1–2 sentences and max 50 words, and the prompt **requires** one fact from
each of at least two stops. Both dates therefore land inside both windows, and each
one looks misattributed to the other stop. Measured against the prompt's own worked
example in `generate_tour_text.py`:

```
In the stops ahead, you will encounter Monet's 1888 paintings at Cap d'Antibes
and the 1706 destruction of Eze Village's fortifications.

FAIL: date '1706' attributed to 'Cap d'Antibes' but belongs to a different stop
FAIL: date '1888' attributed to 'Eze Village'   but belongs to a different stop
```

Both windows spanned the whole sentence. And a Part 4 verification failure **omits
Part 4 entirely** (`_p4_success` else-branch) — so the check silently deletes the
cross-stop callbacks the rubric awards **+50%** for, which CLAUDE.md records as the
only route to 75 at N=8.

The block is currently gated off with `for _p4s in ([] if True else _p4_stop_data)`.

**What to do:**

1. Scope the check to the actual attachment, not a character window. Part 4's own
   rule is `"<fact> at <stop name>"` — split the text into clauses at stop-name
   boundaries so a date belongs to the nearest *preceding* stop mention, or parse the
   `at <stop name>` construction directly. A window that can contain two stop names
   is by construction unable to attribute anything.
2. **Lift it to module scope** as a named function (e.g.
   `check_part4_attribution(part4_text, stop_data) -> list[str]`) and call it from the
   Part 4 loop. It is currently ~1300 lines inside `generate_tour_text` and unreachable
   from any test — that is why it shipped broken.
3. Remove the `([] if True else ...)` gate once the function is correct.
4. Test both directions with the real function, not a copy:
   - the prompt's worked example above → **passes** (no false positive)
   - D373's actual bug, Moses-content attributed to "Au Soleil du Plafond" → **fails**

## Part 2 — the venue-snippet injection is unbound

LOCAL-427 injects the venue exhibition page as the first verification snippet when the
source is the venue rather than a third party. The submission claimed neutralisation
evidence for it, but the test it cited exercises `verify_stop_claims` given a snippet
list — it does not exercise the code that *builds* that list. LEAD neutralised the
injection in place (`if (False and _exhibition_checklist_result ...`) and **all 68
tests still passed**. This is D277's failure mode in a new shape: the test covers the
consumer, not the change.

Bind it. The decision "is this source the venue, and should its page text lead the
snippet list?" belongs at module scope where a test can call it. Neutralise it in
place and paste the red output (D242 #1).

## Part 3 — still open from LOCAL-427's acceptance

- **No live run has yet sourced works from mfa.org.** 427 backed off correctly across
  9 attempts over 60s and mfa.org still returned 429 every time. The page cache does
  not help while we have never received a 200. Try again — from a cold session, and
  if it still 429s, report that plainly rather than lowering any bar.
- **Boris Fridman is still stripped** in the delivered text, because airmail.news does
  not contain the credit line and mfa.org does. Broder and Mourlot Frères now survive.
  Fridman is the remaining half of the D373 measurable goal.
- **Do not lower the verifier's bar.** Unchanged from 427.

## Binding (D242 #1, D277)

- Every behaviour change must be reachable from a test **through the production
  symbol**. No mirrors, no `inspect.getsource` string assertions, no testing a
  downstream consumer and calling it coverage of the change.
- **Neutralise each change in place — keep the symbol so imports still resolve — and
  paste the red output.** "All tests still pass with the change disabled" is a failed
  submission, not a passing one.

## Acceptance

- The prompt's worked example passes attribution; D373's real misattribution fails it
- Both new module-scope functions go red when neutralised, with pasted output
- `python3 run_tests.py` — no NEW failures against the D375 baseline of **203/238**
  (all 35 existing failures are pre-existing; verify, do not assume)
- **Control (D302/D326): Palais 4/4, dates intact** — run it. LOCAL-427 asserted the
  Palais was "structurally unaffected" while changing Part 4 composition and museum
  coordinate emission, both of which the Palais tour goes through. That reasoning was
  wrong; the control is not optional.

## PROCESS — you are not done until all of this is true

1. `git rev-list --count storied..HEAD` is **≥ 1**. `exit=0` with no commits is a
   failed run.
2. `SUBMISSION_LOCAL-428.md` exists with the red output for each change, the Part 4
   attribution results both directions, and the Palais control output.
3. If you could not prove something, write **"unproven, handing to LEAD"**.
4. Push your branch before you stop.
