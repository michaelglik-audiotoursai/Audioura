#!/usr/bin/env python3
"""pass_dump.py — LOCAL-654: per-pass before/after dumps behind an env var.

Set ``LOCAL654_DUMP=1`` (optionally ``LOCAL654_DUMP_DIR=/path``) to have each
instrumented post-narration pass record the text it received and the text it
produced, together with any NEW mid-clause collision the pass introduced — a
lowercase word running straight into a capitalised word with no sentence
punctuation between them (the "…into Thousands…" shape). Off by default and
free: when the env var is unset, ``dump_pass`` returns the output untouched and
does no work.

This is diagnostic scaffolding only. It never mutates the text and never raises.
"""
from __future__ import annotations

import os
import re
from typing import Optional

__all__ = ["enabled", "collisions", "dump_pass"]

# A mid-clause collision: a lowercase word (3+ letters) directly followed by a
# single space and a Capitalised word (2+ letters), with NO sentence-ending
# punctuation (. ! ? :) or comma on the lowercase word. Excludes the normal case
# where the capitalised word legitimately continues a clause after a real break.
_COLLISION_RE = re.compile(r"(?<![.!?:,;])\b([a-z]{3,})\s([A-Z][a-z]{2,})")

# Capitalised words that legitimately follow a lowercase word mid-clause: these
# are not collisions (proper-noun objects, place names, etc.). We only FLAG when
# the capitalised word is a common sentence-starter noun/verb, i.e. it reads like
# the start of a dropped-into next sentence. To stay a pure diagnostic we flag
# ALL and let the human read context — false positives here cost nothing.


def enabled() -> bool:
    return os.environ.get("LOCAL654_DUMP", "") not in ("", "0", "false", "False")


def collisions(text: str):
    """Return [(lowercase, Capitalised, context), …] for the collision shape."""
    out = []
    for m in _COLLISION_RE.finditer(text or ""):
        s = max(0, m.start() - 45)
        out.append((m.group(1), m.group(2), (text[s:m.end() + 45]).replace("\n", " ")))
    return out


_DIR = None


def _dir() -> str:
    global _DIR
    if _DIR is None:
        _DIR = os.environ.get("LOCAL654_DUMP_DIR", "/tmp/local654_dump")
        try:
            os.makedirs(_DIR, exist_ok=True)
        except Exception:
            _DIR = "/tmp"
    return _DIR


_SEQ = 0


def dump_pass(name: str, before: str, after: str) -> str:
    """Record a pass's before/after text and any NEW collisions it introduced.

    Returns ``after`` unchanged so call sites can wrap a pass transparently:
        complete_tour = dump_pass("LOCAL-626 date", prev, complete_tour)
    No-op (returns ``after``) when LOCAL654_DUMP is unset.
    """
    if not enabled():
        return after
    global _SEQ
    _SEQ += 1
    try:
        before_c = {(a, b) for a, b, _ in collisions(before)}
        after_cols = collisions(after)
        new_cols = [c for c in after_cols if (c[0], c[1]) not in before_c]
        tag = "  **NEW COLLISION**" if new_cols else ""
        line = (f"[dump {_SEQ:02d}] {name}: "
                f"len {len(before)}->{len(after)}, "
                f"collisions {len(collisions(before))}->{len(after_cols)}{tag}")
        print("  " + line)
        for lw, cap, ctx in new_cols:
            print(f"      NEW: '{lw} {cap}'  …{ctx}…")
        path = os.path.join(_dir(), f"{_SEQ:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', name)}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=== PASS: {name} ===\n\n--- BEFORE ---\n{before}\n\n"
                    f"--- AFTER ---\n{after}\n\n--- NEW COLLISIONS ---\n")
            for lw, cap, ctx in new_cols:
                f.write(f"'{lw} {cap}'  …{ctx}…\n")
    except Exception as e:  # diagnostic must never break a run
        print(f"  [pass_dump] non-fatal: {e}")
    return after
