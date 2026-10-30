"""museum_story_refill.py — [LOCAL-832] Refill storyless museum stops from the
verified-work reserve before shipping fewer, or shipping them storyless.

THE PROBLEM. The D511 / LOCAL-487 story-quality gate (step 7a, PHASE 5.17 of
generate_tour_text) measures each museum stop against Michael's bar — at least
one story of >= 3 consecutive sentences, one subject, an action and something at
stake. When a stop fails, step 7a REGENERATES THE SAME STOP (rotating to the
next fact, forbidding rejected claims) and keeps the result only if it now
clears the bar; otherwise it keeps the original storyless prose. Nothing swaps
the stop for a DIFFERENT work. The Rijksmuseum has 789 canonical titles, so a
tour that ships 3/5 because two famous works happened to resist a story — while
hundreds of other verified works went untried — is never honest (LOCAL-828 /
828B live runs, Rijksmuseum, cheap arm: 5/5 stops storyless, cap=1 retried one,
the tour shipped the rest storyless).

THE FIX. A stop that is STILL storyless after step 7a's own retry is REPLACED by
the next verified work from the reserve (prominence-ranked = yield order) that is
not already a stop, the replacement is narrated and re-gated, and only a
replacement that CLEARS THE BAR is kept. Bounded to ROUNDS rounds; the honest
shortfall is the truth only once the reserve is exhausted.

This module is the PURE, unit-testable half: the selection logic. It decides —
with no network, no LLM, no mutation of caller state — WHICH storyless stops to
replace and WHICH reserve titles to try, respecting:

  * the cap: never try to improve more stops than are actually storyless, and
    never pull more reserve works than needed (cost cap — one generation per
    replaced stop);
  * de-duplication: a reserve title already used as a stop (case-insensitive) is
    never re-added, and each reserve title is handed out at most once across all
    rounds;
  * yield order: reserve titles are offered in the order the caller computed
    (the LOCAL-593/626/629 prominence/artworks-only/variety-capped order), the
    same order LOCAL-632's count reconcile draws from.

The caller (generate_tour_text._generate_tour_text_impl) owns the impure steps:
build a fresh POI for the chosen title, generate its description from the
already-fetched venue corpus (no new research fetch), re-gate it, and judge it on
Michael's bar — keeping it only if it clears. `plan_refill_round` is called once
per round with the stops that are STILL storyless and the titles not yet tried.

Public API:
  normalize_title(s) -> str
  stop_titles(stops) -> List[str]
  available_reserve(reserve, used_titles, tried_titles) -> List[str]
  plan_refill_round(storyless_idx, stops, reserve, *, tried_titles=(), cap=None)
      -> RefillPlan
  refill_log_line(venue, dropped, added) -> str
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "normalize_title",
    "stop_titles",
    "available_reserve",
    "plan_refill_round",
    "RefillAssignment",
    "RefillPlan",
    "refill_log_line",
    "DEFAULT_ROUNDS",
]

# [LOCAL-832] Michael's step 7: "repeat from #4", bounded. Two rounds of
# replacement after step 7a's own retry — enough to work through the next few
# reserve works for each storyless slot without unbounded spend.
DEFAULT_ROUNDS = 2


def normalize_title(s: Any) -> str:
    """Case/space-insensitive key for de-duplicating titles.

    Matches the spirit of shortfall_reconcile.candidate_title().lower() — a
    reserve work whose title already names a stop must not be re-added.
    """
    if isinstance(s, dict):
        s = s.get("name") or s.get("title") or ""
    return " ".join(str(s or "").split()).strip().lower()


def stop_titles(stops: Sequence) -> List[str]:
    """Titles of the current stops, as plain strings (POI dicts or bare strings)."""
    out: List[str] = []
    for p in stops or []:
        if isinstance(p, dict):
            out.append((p.get("name") or p.get("title") or "").strip())
        else:
            out.append(str(p or "").strip())
    return out


def available_reserve(
    reserve: Sequence,
    used_titles: Sequence[str] = (),
    tried_titles: Sequence[str] = (),
) -> List[str]:
    """Reserve titles, in yield order, that are neither a current stop nor already tried.

    De-duplicates within the reserve too (a title listed twice is offered once).
    ``used_titles`` are the current stop titles; ``tried_titles`` are reserve
    titles already handed out in an earlier round (or already attempted and
    rejected). Returns plain title strings.
    """
    blocked = {normalize_title(t) for t in used_titles if normalize_title(t)}
    blocked |= {normalize_title(t) for t in tried_titles if normalize_title(t)}
    out: List[str] = []
    seen: set = set()
    for c in reserve or []:
        t = c.get("name") or c.get("title") or "" if isinstance(c, dict) else str(c or "")
        t = t.strip()
        k = normalize_title(t)
        if not k or k in blocked or k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


@dataclass
class RefillAssignment:
    """One storyless stop paired with the reserve title proposed to replace it."""
    stop_index: int            # index into the caller's stop list
    old_title: str             # title of the storyless stop being replaced
    new_title: str             # verified reserve work to narrate in its place


@dataclass
class RefillPlan:
    """The plan for ONE refill round.

    ``assignments`` pairs each storyless stop (worst-first, by the caller's order)
    with the next distinct reserve title. ``unfilled`` are storyless stop indices
    for which the reserve had no remaining candidate — the honest-shortfall set
    once rounds are exhausted. ``tried_after`` is ``tried_titles`` plus every title
    proposed this round, ready to pass to the next round so no title is offered
    twice.
    """
    assignments: List[RefillAssignment] = field(default_factory=list)
    unfilled: List[int] = field(default_factory=list)
    tried_after: List[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return bool(self.assignments)


def plan_refill_round(
    storyless_idx: Sequence[int],
    stops: Sequence,
    reserve: Sequence,
    *,
    tried_titles: Sequence[str] = (),
    cap: Optional[int] = None,
) -> RefillPlan:
    """Plan replacements for ONE round. Pure — mutates nothing.

    ``storyless_idx`` is the set of stop indices STILL storyless after step 7a
    (the caller passes the up-to-date set each round). ``stops`` is the current
    stop list; ``reserve`` the ordered verified-work reserve. ``tried_titles`` are
    reserve titles already proposed in previous rounds (so this round does not
    repeat them). ``cap`` limits how many stops to refill this round (defaults to
    every storyless stop); the cost cap is implicit anyway — one reserve title per
    storyless stop.

    Returns a RefillPlan: storyless stops are taken in the ORDER GIVEN (the caller
    ranks them worst-first by the step-5 index, exactly as step 7a's own cap
    does), and each is paired with the next distinct available reserve title.
    Stops with no title left go to ``unfilled``.
    """
    idxs = [i for i in storyless_idx]
    if cap is not None:
        try:
            cap = max(0, int(cap))
        except (TypeError, ValueError):
            cap = None
        if cap is not None:
            idxs = idxs[:cap]

    titles = stop_titles(stops)
    used = list(titles)
    pool = available_reserve(reserve, used_titles=used, tried_titles=tried_titles)

    assignments: List[RefillAssignment] = []
    unfilled: List[int] = []
    proposed: List[str] = []
    pool_i = 0
    for si in idxs:
        old = titles[si] if 0 <= si < len(titles) else ""
        if pool_i < len(pool):
            new_t = pool[pool_i]
            pool_i += 1
            assignments.append(RefillAssignment(stop_index=si, old_title=old,
                                                new_title=new_t))
            proposed.append(new_t)
        else:
            unfilled.append(si)

    tried_after = list(tried_titles) + proposed
    return RefillPlan(assignments=assignments, unfilled=unfilled,
                      tried_after=tried_after)


def refill_log_line(venue: str, dropped: Any, added: Any) -> str:
    """The mandated LOCAL-832 log line.

    "[LOCAL-832] story-gate refill <venue> <dropped> → <added>"

    ``dropped`` / ``added`` may be a count or a title; both render inline so a
    single line reads either as a summary ("2 → 2") or a swap
    ("'The Milkmaid' → 'Woman Reading a Letter'").
    """
    def _fmt(x: Any) -> str:
        if isinstance(x, (list, tuple)):
            return ", ".join(f"'{str(t)}'" for t in x)
        if isinstance(x, str):
            return f"'{x}'"
        return str(x)

    return f"[LOCAL-832] story-gate refill {venue} {_fmt(dropped)} → {_fmt(added)}"
