"""shortfall_reconcile.py — [LOCAL-632] Deliver N stops when the corpus has N.

A famous museum must deliver the number of stops the listener asked for whenever
its verified candidate list holds at least that many works. The Rijksmuseum
(tour 499, *Night Watch* / *Milkmaid* / *Jewish Bride* …) and the Courtauld
(tour 485) each shipped 2 stops against 3 requested — an impossible shortfall on
corpus grounds. Candidates were lost between selection and delivery (a gate drop,
a merge, a conclusion miscount) and nothing pulled a replacement back in.

This module is the deterministic reconciliation lever, pure and unit-testable:

  reconcile_to_n(selected, reserve, requested) -> (final, shortfall)
      Backfill ``selected`` from the ordered ``reserve`` of verified candidates
      (never inventing) until it reaches ``requested``, de-duplicated by title.
      Returns the final list (capped at ``requested``) and a ``shortfall`` dict
      describing any residual gap.

  shortfall_log_line(requested, delivered, reasons) -> str
      The one standard log line the task mandates:
      "[LOCAL-632] shortfall: requested=N delivered=M reasons=[…]".

No network, no LLM, no DB — the caller supplies the already-verified candidate
reserve. Order-preserving.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = ["candidate_title", "reconcile_to_n", "shortfall_log_line"]


def candidate_title(c: Any, title_key: str = "name") -> str:
    """Best-effort title of a candidate (POI dict, work dict, or bare string)."""
    if isinstance(c, dict):
        return (c.get(title_key) or c.get("name") or c.get("title") or "").strip()
    return str(c or "").strip()


def reconcile_to_n(
    selected: Sequence,
    reserve: Sequence,
    requested: Optional[int],
    *,
    title_key: str = "name",
) -> Tuple[List, Dict]:
    """Backfill ``selected`` toward ``requested`` from the verified ``reserve``.

    ``selected`` is the current (possibly short) delivered list; ``reserve`` is the
    ordered list of ALL verified candidates for the venue (selection order:
    prominence-ranked, artworks-only, variety-capped — whatever the caller already
    computed). Replacement draws from ``reserve`` IN ORDER, skipping any candidate
    whose title already appears in ``selected`` (case-insensitive), until the list
    reaches ``requested`` or the reserve is exhausted.

    Returns ``(final, shortfall)``:
      * ``final`` — ``selected`` plus pulled-in replacements, capped at
        ``requested`` (when requested is a positive int); order preserved, the
        originals first then replacements in reserve order.
      * ``shortfall`` — ``{}`` when ``len(final) >= requested`` (the ask was met),
        else ``{'requested': N, 'delivered': M, 'reasons': [...]}`` describing the
        residual gap (the reserve could not supply enough DISTINCT verified works).

    Pure and deterministic. Never invents a candidate; a residual shortfall is
    reported honestly rather than padded.
    """
    final: List = list(selected or [])
    try:
        req = int(requested) if requested is not None else 0
    except (TypeError, ValueError):
        req = 0

    seen = {candidate_title(c, title_key).lower() for c in final
            if candidate_title(c, title_key)}

    if req > 0 and len(final) < req:
        for c in (reserve or []):
            if len(final) >= req:
                break
            t = candidate_title(c, title_key)
            if not t:
                continue
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            final.append(c)

    # Cap at the request when we have one (never over-deliver from the reserve).
    if req > 0 and len(final) > req:
        final = final[:req]

    shortfall: Dict = {}
    if req > 0 and len(final) < req:
        reasons = []
        n_reserve = len(reserve or [])
        if n_reserve <= len(selected or []):
            reasons.append("no verified replacement candidates in reserve")
        else:
            reasons.append(
                f"reserve exhausted after de-duplication "
                f"({n_reserve} verified candidate(s), {len(final)} distinct kept)")
        shortfall = {
            "requested": req,
            "delivered": len(final),
            "reasons": reasons,
        }
    return final, shortfall


def shortfall_log_line(requested: int, delivered: int,
                       reasons: Optional[Sequence[str]] = None) -> str:
    """The mandated LOCAL-632 shortfall log line.

    "[LOCAL-632] shortfall: requested=N delivered=M reasons=[r1; r2]"
    """
    rs = "; ".join(str(r) for r in (reasons or []) if str(r).strip())
    return (f"[LOCAL-632] shortfall: requested={requested} "
            f"delivered={delivered} reasons=[{rs}]")
