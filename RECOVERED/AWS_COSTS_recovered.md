# AWS costs per tour — RECOVERED from a worker log, 2026-09-23

**Provenance, and why it matters.** LOCAL-495 ran overnight, researched this, and wrote
`AWS_COSTS.md`. It never committed, and `prune_worktrees.sh` then deleted the worktree —
so the file is gone. These figures are recovered from
`kiro_session_logs/LOCAL-495_20260923T001626.log`. **Treat as unverified** until re-run:
the reasoning is visible in the log but the artifact is not.

## Rates (list, us-east-1 — region confirmed in all three docker-compose files)

| service | rate | free tier |
|---|---|---|
| Polly **Standard** | $4.00 / 1M chars | 5M chars/month, first 12 months |
| Polly **Neural** | **$16.00 / 1M chars** | 1M chars/month, first 12 months |
| Polly Long-form | $100.00 / 1M chars | not used by this codebase |
| Polly Generative | $30.00 / 1M chars | not used by this codebase |
| Amazon **Translate** | $15.00 / 1M chars | 2M chars/month, first 12 months |

## What this codebase actually uses

**Neural, not standard.** English tours use voice `Joanna` (`VOICE_MAP['en']`), which is in
`polly_tts_service.py`'s `NEURAL_VOICES` set → **$16/1M chars, 4× the standard rate.**

Text is cleaned before Polly by `_strip_nav_fields_for_tts`, which removes the metadata
lines (Address, Coordinates, Type/Specialty, Specific Examples, Operational Details), so
the billed character count is lower than the raw file.

## The number Michael asked for

> **A 4-stop tour costs $0.00 on the AWS translate side** (English is authored, not
> translated), **$0.12 to voice** with Polly neural, and **about $0.16–$0.25 more per
> additional language** ($0.13 Translate + $0.03 standard-voice TTS, or +$0.12 if the
> translation is voiced neural).

## What this changes

**Audio is NOT negligible.** The `cost_ledger` `tts_generate` rows average **$0.0008**,
which is wrong by a factor of ~150. Real all-in for one English 4-stop tour:

```
  generation (measured today)   $0.16–0.19
  voicing (Polly neural)        $0.12
  ------------------------------------------
  total                         ~$0.28–0.31
```

**Voicing is roughly 40% of the cost of a tour**, which makes Michael's instinct right:
re-voicing only the stops whose text changed is worth the complexity, because re-voicing
all five is the expensive half.

**A cheap lever exists:** Joanna neural at $16/1M vs standard at $4/1M. Dropping to
standard voice would cut $0.12 to $0.03 — a quality decision, not an engineering one.
