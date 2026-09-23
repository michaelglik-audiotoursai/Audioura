#!/usr/bin/env python3
"""user_stops_validate.py — LOCAL-521. Judge a user's stop list BEFORE generating.

A user can type anything into the "stops" box. LOCAL-481 already ruled that a stop
must be a real, named, findable place, and `place_shape.classify_stop_name` plus
`geo_refutation` exist to judge that. `venue_parts.resolve_part_instances` knows
whether a venue actually HAS a given part. This module runs those three judges over
a user-supplied list, once, before a single token is spent generating.

WHY THIS LAYER. The existing checks run mid-generation, on POIs the pipeline itself
produced. Nothing vets what the *listener* typed. So today a user asking for
"Audio Guide", "Restaurants", or "Sistine Chapel Ceiling" at a Newton church gets
either a nonsense stop or a silent drop. Neither tells the person anything.

THE RULING WE SHIP UNDER — Michael's D577: *"we ship what we cannot verify, we do
not ship what we can refute."* So the verdict is three-valued, never binary:

    rejected  — we can REFUTE it. A format ("Audio Guide"), a category
                ("Restaurants"), or a place the geography contradicts (Sistine
                Chapel Ceiling, 6,700 km from Newton). These do not generate.
    warning   — plausible, but we could not CONFIRM it. A place the venue does not
                appear to have, or a name we simply cannot corroborate. It STILL
                generates; the listener is told our confidence is low.
    ok        — a real, named place, with nothing against it.

Every stop carries a `reason` a person can read. **Nothing is dropped silently**
(acceptance #4): a rejected stop is returned in the result with its reason, for the
caller to show the user — the caller decides whether to substitute, drop-with-notice,
or ask the user to rename. The listener is TOLD, not silently overruled.

DETERMINISTIC CORE, INJECTED EDGES. place_shape is pure string logic. geo_refutation
takes an injected geocoder (no network of its own, tests run offline). venue_parts
takes an injected `ask_grounded`. When an edge dependency is absent, that particular
check is SKIPPED (never turned into a rejection) — an unavailable verifier cannot
refute anything, and unverified ships (D577).
"""

from __future__ import annotations

# ── Verdicts ────────────────────────────────────────────────────────────────────
OK = "ok"              # a real, named place with nothing against it
WARNING = "warning"    # plausible but unconfirmed — still generates, hedged
REJECTED = "rejected"  # refutable — a format, a category, or geography contradicts it

# Order for "worst verdict wins" when several checks weigh in on one stop.
_SEVERITY = {OK: 0, WARNING: 1, REJECTED: 2}


def _worse(a, b):
    """Return the more severe of two verdicts."""
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


# ── place_shape: is the NAME a place at all? (deterministic, always available) ────
def _classify_shape(name):
    """Wrap place_shape.classify_stop_name, degrading to 'place' if unavailable.

    place_shape is pure-Python string logic with no dependencies, so it should
    always import; the guard mirrors generate_tour_text.py's own fallback so this
    module never hard-fails on an incomplete checkout.
    """
    try:
        from place_shape import classify_stop_name
    except Exception:
        return {"is_place": True, "shape": "place", "reason": ""}
    try:
        return classify_stop_name(name)
    except Exception:
        return {"is_place": True, "shape": "place", "reason": ""}


def validate_one(
    stop_name,
    *,
    anchor=None,
    geocoder=None,
    venue_name=None,
    location=None,
    part_instances=None,
    refute_km=None,
):
    """Judge ONE user-supplied stop name. Returns a dict::

        {"stop": str, "verdict": "ok"|"warning"|"rejected", "reason": str,
         "checks": {<check>: <detail>}}

    Arguments (all keyword-only except the name):
      anchor         (lat, lng) of the tour venue — enables the geography check.
      geocoder       name -> (lat, lng) | None. Injected; no network here.
      venue_name,
      location       used only to phrase the venue-part reason.
      part_instances the {part: {"count", "names", "access"}} map from
                     venue_parts.resolve_part_instances, if the caller already has
                     it. When provided, a stop the venue reports zero of is flagged.
      refute_km      distance threshold override for geo_refutation.

    The verdict is the WORST of the checks that ran. A check with a missing
    dependency simply does not run — it can never manufacture a rejection.
    """
    name = (stop_name or "").strip()
    checks = {}

    if not name:
        return {"stop": stop_name, "verdict": REJECTED,
                "reason": "empty stop name — a stop must name a place",
                "checks": {"shape": "empty"}}

    verdict = OK
    reason = "names a specific place"

    # 1. SHAPE — a format or a category is refutable from the words alone.
    shape = _classify_shape(name)
    checks["shape"] = shape.get("shape", "place")
    if not shape.get("is_place", True):
        # 'format' -> "Audio Guide"; 'category' -> "Restaurants". Both rejected.
        return {"stop": name, "verdict": REJECTED,
                "reason": shape.get("reason", "not a place"),
                "checks": checks}

    # 2. GEOGRAPHY — a named place the venue's location contradicts is refuted
    #    (the D564 Sistine Chapel case). Only runs with an anchor AND a geocoder;
    #    an absent geocoder cannot refute anything, so the stop is not penalised.
    if anchor and geocoder:
        try:
            import geo_refutation as gr
            kwargs = {}
            if refute_km is not None:
                kwargs["refute_km"] = refute_km
            far = gr.refute_stop_by_distance(name, anchor, geocoder, **kwargs)
        except Exception:
            far = None
        if far:
            checks["geo"] = {"resolved_as": far["resolved_as"], "km": far["km"]}
            return {"stop": name, "verdict": REJECTED,
                    "reason": (f"'{name}' geocodes to {far['resolved_as']}, "
                               f"{far['km']} km from the venue — too far to be this "
                               f"stop"),
                    "checks": checks}
        checks["geo"] = "not refuted by distance"

    # 3. VENUE-PART — a plausible name the venue does not appear to HAVE is a
    #    WARNING, not a rejection: we could not confirm it, and unconfirmed ships
    #    (D577). resolve_part_instances reports count == 0 for a part the venue
    #    lacks; count == 0 here means "the venue has none of these".
    if part_instances:
        info = _lookup_part(part_instances, name)
        if info is not None:
            cnt = info.get("count")
            if cnt == 0:
                checks["venue_part"] = "venue reports none"
                verdict = _worse(verdict, WARNING)
                reason = (f"the venue does not appear to have '{name}' — generating "
                          f"anyway, but flagged as unconfirmed")
            else:
                checks["venue_part"] = f"venue reports count={cnt}"

    return {"stop": name, "verdict": verdict, "reason": reason, "checks": checks}


def _lookup_part(part_instances, name):
    """Case-insensitive lookup of a stop name in a part_instances map."""
    if not isinstance(part_instances, dict):
        return None
    folded = name.strip().lower()
    for k, v in part_instances.items():
        if str(k).strip().lower() == folded and isinstance(v, dict):
            return v
    return None


def validate_stops(
    stop_names,
    *,
    anchor=None,
    geocoder=None,
    venue_name=None,
    location=None,
    part_instances=None,
    refute_km=None,
):
    """Judge a WHOLE user stop list. Returns a dict::

        {"stops": [<per-stop result>, ...],
         "ok": [...names...], "warning": [...], "rejected": [...],
         "summary": "N ok, M warning, K rejected"}

    Every input stop appears exactly once in `stops`, in input order, with its
    verdict and human-readable reason. Nothing is dropped silently (acceptance #4):
    the rejected list names every refused stop and why.
    """
    results = []
    for s in (stop_names or []):
        results.append(validate_one(
            s,
            anchor=anchor,
            geocoder=geocoder,
            venue_name=venue_name,
            location=location,
            part_instances=part_instances,
            refute_km=refute_km,
        ))
    buckets = {OK: [], WARNING: [], REJECTED: []}
    for r in results:
        buckets[r["verdict"]].append(r["stop"])
    return {
        "stops": results,
        "ok": buckets[OK],
        "warning": buckets[WARNING],
        "rejected": buckets[REJECTED],
        "summary": (f"{len(buckets[OK])} ok, {len(buckets[WARNING])} warning, "
                    f"{len(buckets[REJECTED])} rejected"),
    }


def generatable(result):
    """The stops that should GO to generation: everything not refuted.

    A warning still generates (D577) — only rejected stops are held back. Takes the
    dict from `validate_stops`, returns the list of stop names in input order.
    """
    return [r["stop"] for r in result.get("stops", []) if r["verdict"] != REJECTED]
