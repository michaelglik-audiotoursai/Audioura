#!/usr/bin/env python3
"""story_survival.py — [LOCAL-832B] make a story the pass wrote reach the listener.

**THE DEFECT THIS EXISTS TO CLOSE.** The story pass (story_pass.py / LOCAL-490)
writes a finished 3–5-sentence story for a museum stop — one subject, an action,
a consequence — and reports `ok=True`. It is then appended to the per-stop
NARRATION prompt as "THE STORY FOR THIS STOP … you may adjust wording to flow
into the surrounding text." On the cheap arm (gpt-4.1-mini) the narration model
takes that permission and INTERLEAVES the story with physical description and
subject switches. The delivered prose names the same people, but the longest
CONSECUTIVE run about one subject drops to two or three sentences and the agency
and stakes verbs scatter out of it.

`story_opportunity_scan` (Michael's bar, D511 / LOCAL-487 step 7a) then reads the
delivered description and — correctly — reports `agency=0 stakes=0`: a run that
no longer carries an action and a consequence is exposition, not a story. So a
stop whose pass wrote a real story ships storyless, and every cheap-arm museum
tour reads story-less by the bar (LOCAL-828 / 828B, Rijks + Orsay, 0/5).

Traced 2026-10-30 on the 828B Rijksmuseum log: the pass wrote "Rembrandt van Rijn
was commissioned in 1642 …" (ok=True); the delivered Night Watch stop scans as
the longest run (3 sentences, Rembrandt) agency=0 stakes=0. The story was not
deleted by a gate and the scan did not read the wrong text — the narration merge
DISSOLVED it.

**THE FIX.** When the pass wrote a story that ITSELF clears the bar, and the
delivered description does NOT clear the bar, PREPEND the pass story as its own
leading block so it survives as a consecutive run the scan can see. The listener
hears the story first, then the description that was going to be delivered anyway.

This is deterministic and spends NOTHING — no LLM, no network. It never
manufactures a story: it only re-seats a story that was already written and
fact-checked, and only when the pass story clears Michael's own bar. If the pass
story does not clear the bar (e.g. a "gifted / donated" provenance with no
stakes), nothing is prepended — the stop is genuinely storyless and the LOCAL-832
reserve refill, or the honest shortfall, is the correct outcome, not a weak
prepend that fools the scanner.

This module is the PURE half: it decides WHETHER to prepend and RETURNS the new
text. The caller owns reading `poi['_story_pass']` and writing `description`.

Public API
----------
  clears_bar(text)                         -> bool
  story_survived(description, story_text)   -> bool   (delivered text clears the bar)
  repair_description(description, story)    -> RepairResult
  survival_log_line(stop_label, result)     -> str
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "clears_bar",
    "story_survived",
    "repair_description",
    "RepairResult",
    "survival_log_line",
]


def _scan():
    """Import the scan lazily so this module stays importable without it."""
    from story_opportunity_scan import measure, verdict
    return measure, verdict


def clears_bar(text: str) -> bool:
    """True when `text` clears Michael's story bar (``needs_additional_story`` False).

    Empty or placeholder text never clears the bar. Any scan error is treated as
    "does not clear" — the conservative answer, since a prepend only ever adds a
    story the pass already wrote and judged ok.
    """
    if not text or not str(text).strip():
        return False
    s = str(text).strip()
    if s.startswith("["):
        return False
    try:
        measure, verdict = _scan()
        return not verdict(measure(s)).get("needs_additional_story", True)
    except Exception:
        return False


def story_survived(description: str, story_text: str) -> bool:
    """Did the story the pass wrote survive into the delivered description?

    "Survived" means the delivered description ITSELF clears the bar. The
    `story_text` argument is accepted for symmetry and future heuristics; the
    decision rests on the delivered prose, because that is exactly what the
    downstream scan judges.
    """
    return clears_bar(description)


@dataclass
class RepairResult:
    """Outcome of a survival repair on one stop.

    ``changed``       — True when the description was rewritten (story prepended).
    ``description``   — the text to deliver (new when changed, original otherwise).
    ``reason``        — why the decision was made, for the log.
    ``story_clears``  — did the pass story clear the bar on its own?
    ``delivered_clears`` — did the ORIGINAL delivered description clear the bar?
    """
    changed: bool
    description: str
    reason: str
    story_clears: bool = False
    delivered_clears: bool = False


def _already_contains(description: str, story_text: str) -> bool:
    """Cheap guard: the delivered text already opens with (most of) the story.

    Prepending a block that is already sitting at the top would double the story.
    We compare the first sentence of the story, folded to lowercase words, against
    the opening of the description. A substantial overlap means the narration kept
    the story intact at the front — do not prepend again.
    """
    def _fold(s: str) -> str:
        return " ".join("".join(c.lower() for c in str(s) if c.isalnum() or c.isspace()).split())

    story_head = _fold(story_text)[:80]
    if not story_head:
        return False
    desc_head = _fold(description)[:200]
    # Require a run of the first several words to coincide, not just a word.
    words = story_head.split()
    probe = " ".join(words[:6])
    return bool(probe) and probe in desc_head


def repair_description(description: str, story: Optional[object]) -> RepairResult:
    """Decide whether to prepend the pass story, and return the text to deliver.

    ``story`` is the ``poi['_story_pass']`` dict (keys: ``story``, ``ok``) or a
    bare story string. The repair fires only when ALL of:

      * the pass produced an ``ok`` story with text;
      * that story CLEARS the bar on its own (so prepending it actually helps);
      * the delivered description does NOT already clear the bar (the merge lost
        it) — if the delivery already tells a story, nothing is done;
      * the description does not already open with the story (no double-telling).

    Otherwise the original description is returned unchanged. Never raises: on any
    internal error it returns the original text with a reason.
    """
    desc = description or ""
    try:
        if isinstance(story, dict):
            if not story.get("ok"):
                return RepairResult(False, desc, "no ok story from the pass")
            story_text = (story.get("story") or "").strip()
        else:
            story_text = (str(story or "")).strip()

        if not story_text:
            return RepairResult(False, desc, "story pass produced no text")

        # A placeholder / failed description is not something we repair — the
        # generation failed and a different path owns that.
        if not desc.strip() or desc.strip().startswith("["):
            return RepairResult(False, desc, "no usable delivered description")

        delivered_clears = clears_bar(desc)
        story_clears = clears_bar(story_text)

        if delivered_clears:
            return RepairResult(False, desc, "delivered prose already clears the bar",
                                story_clears=story_clears, delivered_clears=True)
        if not story_clears:
            # The pass story would not clear the bar either — prepending it would
            # not help and would only add words. Leave the stop genuinely
            # storyless for the reserve refill / honest shortfall to handle.
            return RepairResult(False, desc,
                                "pass story does not clear the bar on its own — "
                                "not prepending (reserve refill owns this stop)",
                                story_clears=False, delivered_clears=False)
        if _already_contains(desc, story_text):
            return RepairResult(False, desc,
                                "delivered prose already opens with the story",
                                story_clears=True, delivered_clears=False)

        # Prepend the story as its own leading block. A blank line keeps it a
        # distinct paragraph for the splitters and reads as a clean opening aloud.
        new_desc = story_text.rstrip() + "\n\n" + desc.lstrip()
        return RepairResult(True, new_desc,
                            "narration dissolved the story — prepended the pass "
                            "story as its own block so it survives into delivery",
                            story_clears=True, delivered_clears=False)
    except Exception as err:  # never lose the text
        return RepairResult(False, desc, f"repair skipped (non-fatal): "
                                         f"{type(err).__name__}: {err}")


def survival_log_line(stop_label: str, result: RepairResult) -> str:
    """The mandated LOCAL-832B log line for one stop's survival repair."""
    verb = "prepended pass story" if result.changed else "no change"
    return (f"[LOCAL-832B] story-survival {stop_label}: {verb} — {result.reason}")
