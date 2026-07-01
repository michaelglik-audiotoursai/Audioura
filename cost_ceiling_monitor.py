"""
Cost Ceiling Monitor — per-tour cost guard for Storied pipeline.
=================================================================
Task [S67]: check_cost_ceiling(total_cost, tour_category, storied_mode)
Logs costs, never aborts. A tour over $0.15 is logged, not failed.
"""
import logging

logger = logging.getLogger(__name__)

COST_CEILING = 0.15  # Hardcoded ceiling for Storied tours


def check_cost_ceiling(total_cost: float, tour_category: str, storied_mode: bool) -> dict:
    """Check if a tour's total cost exceeds the ceiling.

    The ceiling only applies when storied_mode=True.
    NEVER aborts the tour — log only.

    Args:
        total_cost: Total API cost for the tour generation.
        tour_category: The tour category (museum, walking, etc.).
        storied_mode: Whether STORIED_MODE is active.

    Returns:
        dict with keys:
            exceeded: bool — True if over ceiling AND storied_mode is True
            cost: float — the input cost
            ceiling: float — the threshold
    """
    result = {
        "exceeded": False,
        "cost": total_cost,
        "ceiling": COST_CEILING,
    }

    if not storied_mode:
        # Ceiling does not apply to non-Storied tours
        logger.info(f"COST OK: ${total_cost:.4f} (ceiling not applied — storied_mode=false)")
        return result

    if total_cost > COST_CEILING:
        result["exceeded"] = True
        logger.warning(
            f"COST CEILING EXCEEDED: ${total_cost:.4f} > ${COST_CEILING:.4f} "
            f"(category={tour_category})"
        )
        print(
            f"COST CEILING EXCEEDED: ${total_cost:.4f} > ${COST_CEILING:.4f} "
            f"(category={tour_category})"
        )
    else:
        logger.info(f"COST OK: ${total_cost:.4f} <= ${COST_CEILING:.4f} (category={tour_category})")
        print(f"COST OK: ${total_cost:.4f} (category={tour_category})")

    return result
