**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-315
**Base:** storied
**Branch:** kiro/local315-monitor-llm-and-chagall

# The LLM spot-check cannot run, and Chagall scores zero.

Read `SUBMISSION_LOCAL-310.md`, `blindspot_monitor.py`, `generate_tour_text.py`
(how this codebase actually calls the OpenAI API).

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.40**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Production real row count stays **29**.

## Two things, both found by LEAD running the monitor

### 1. `run_llm_spot_check` cannot execute

LOCAL-310 reported it *"Skipped — no OPENAI_API_KEY in environment. The
mechanism is implemented."* LEAD supplied a key and ran it:

```
File "blindspot_monitor.py", line 349, in _count_facts_with_llm
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
AttributeError: module 'openai' has no attribute 'OpenAI'
```

It uses the openai 1.x client class. This environment has no such attribute, and
**every other API call in this codebase uses**
`requests.post("https://api.openai.com/v1/chat/completions", ...)`. Follow that
pattern — it is proven here and needs no new dependency.

Then **actually run it** and report: sample size, per-stop divergence, total
cost. The task budget was $0.05 per full corpus run at 5% sampling.

**The divergence direction is the finding.** Scattered disagreement is noise;
the LLM systematically finding *more* facts than the detector on a category of
stop is a blind spot. Say which you observe, and if it is neither, say that.

### 2. Musée National Marc Chagall: median density 0.000

Check 2 flagged it against a corpus median of 0.264:

```
Marc Chagall        47 stops   median 0.000   mean 0.066   23 corpus rows
Asian Arts Museum   48 stops   median 0.408   mean 0.440   40 corpus rows
```

**Determine which of two causes it is, and do not guess:**

- **Detector blind spot** — Chagall stops are painting descriptions, and the
  detector may not recognise painting vocabulary the way it now recognises
  sculpture (chlorite, schist). If painting dates, media (oil on canvas,
  gouache), dimensions or commission history are present but uncounted, that is
  the same class of gap LOCAL-304 fixed for Asian art.
- **Genuinely thin corpus** — 23 rows against Asian Arts' 40. If the passages
  simply do not contain dated, attributable facts, the stops are correctly
  scored and the answer is corpus work, not detector work.

Read at least five zero-fact Chagall stops and their corpus passages side by
side. **Report which cause it is with the evidence.** Do not fix it in this
task — the two remedies are different and each deserves its own change.

## The line you must not cross

**Do not change `analyze_stop` or any threshold.** LOCAL-310 was explicitly a
monitor; this task keeps that boundary. If you find a blind spot, that is a
finding for a follow-up.

**Do not let the monitor run in the delivery path.** Offline analysis only.

**Report "no blind spot found" if that is the answer.** A negative result from a
working check is worth more than a positive one from a broken check.

## Verification
- The spot-check runs end to end; sample size, divergence and cost reported.
- Chagall diagnosed as blind-spot or thin-corpus, with five stops and their
  passages shown.
- No change to `analyze_stop` or thresholds; monitor stays offline.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). 429 = failure, not a result (D220).

## Acceptance criteria
- `run_llm_spot_check` executes using the codebase's own API pattern.
- Cost within $0.05; divergence direction stated.
- Chagall cause identified with evidence, not fixed.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-315.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
