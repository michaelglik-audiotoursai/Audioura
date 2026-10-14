#!/usr/bin/env python3
"""
Personal "Match %" for listeners (LOCAL-689) — FREE, deterministic, no model call.

Michael, 2026-10-14: "Match 82% — strong on history, which you like; light on
people stories." The number and its two reasons come from three things that
already exist in the database:

  1. The listener's swipe-preference vector
     (user_class_prefs.pref_details / pref_historic / pref_social, each in [0,1],
      written by swipe_preference_service.py from like/dislike swipes).
  2. The tour's story CHARACTER — the mean of its per-stop class distribution
     (stop_metrics.class_details / class_historic / class_social, each stop's
      three values sum to ~1).
  3. The tour's EVALUATED score (audio_tours.editor_score, 5.0–8.0, D655/LOCAL-685).

This module is pure arithmetic on those inputs. It performs NO I/O and NO model
call, so it is trivially deterministic and unit-testable with known vectors.
The map-delivery service (map_delivery/app.py) reads the three inputs from the
database — resolving a translation to its ORIGINAL tour for both the metrics and
the score — and calls compute_match() here.

────────────────────────────────────────────────────────────────────────────
THE FORMULA (documented here and in SUBMISSION_LOCAL-689.md)
────────────────────────────────────────────────────────────────────────────
Let the three story classes be k ∈ {details, historic, social}.

  • Tour character c_k   — mean of class_k over the tour's stops, renormalised so
                           Σ c_k = 1. c_k ∈ [0,1].
  • Taste weight  w_k    — the listener's preference centred at the neutral 0.5:
                               w_k = pref_k − 0.5,     w_k ∈ [−0.5, +0.5]
                           w_k > 0 means "likes class k", w_k < 0 "dislikes it".
  • Alignment     A      — how much the tour's mix leans toward liked classes:
                               A = Σ c_k · w_k,        A ∈ [−0.5, +0.5]
                           (bounded because Σ c_k = 1 and each w_k ∈ [−0.5,0.5]).
                           Mapped into [0,1]:   align = clamp(0.5 + A, 0, 1).
                           A perfectly neutral listener (all pref = 0.5) gets
                           align = 0.5 for every tour — personalisation is off,
                           which is exactly the cold-start intent.
  • Quality       q      — the evaluated score normalised to [0,1]:
                               q = clamp((editor_score − 5.0) / 3.0, 0, 1)
                           (5.0 → 0, 8.0 → 1). Missing score falls back to the
                           flat 7.5 the rest of the service uses (q = 0.833…).

  MATCH % = round( 100 · (W_TASTE · align + W_QUALITY · q) )

with W_TASTE = 0.75 and W_QUALITY = 0.25 — taste dominates because this is a
PERSONAL match, quality only nudges. The result is an integer in [0, 100].

────────────────────────────────────────────────────────────────────────────
COLD START / <5 SWIPES
────────────────────────────────────────────────────────────────────────────
A listener with fewer than MIN_SWIPES (5) swipes has no trustworthy vector, so
compute_match() returns {match_percent: None, reasons: [], cold_start: True}.
The caller surfaces {match_percent: null, reason: "Swipe a few stops to get
matches"}.
"""

from decimal import Decimal

# ─── Tunables (documented above) ─────────────────────────────────────────────
MIN_SWIPES = 5            # below this, no match is shown
W_TASTE = 0.75            # weight of preference alignment in the blend
W_QUALITY = 0.25          # weight of the evaluated score in the blend
EDITOR_SCORE_FLOOR = 5.0  # editor_score domain is [5.0, 8.0] (D655)
EDITOR_SCORE_CEIL = 8.0
EDITOR_SCORE_FALLBACK = 7.5  # the flat prior the service uses when unscored

# The three story classes, in display order, with their human labels. The label
# is what appears in a reason phrase ("strong on history, which you like").
CLASSES = (
    ('details', 'details'),
    ('historic', 'history'),
    ('social', 'people stories'),
)

NO_MATCH_REASON = "Swipe a few stops to get matches"


def _f(x, default=0.0):
    """Coerce a value (float, int, Decimal, str, None) to float. None → default."""
    if x is None:
        return float(default)
    if isinstance(x, Decimal):
        return float(x)
    return float(x)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def aggregate_tour_character(stop_rows):
    """Mean per-stop class distribution → one (details, historic, social) vector
    that sums to 1.

    stop_rows: iterable of (class_details, class_historic, class_social) triples
    (values may be float / Decimal / None). Rows that are entirely None/zero are
    skipped. Returns a dict {details, historic, social}. With no usable rows the
    tour has no character and we return an even split {1/3, 1/3, 1/3} — a neutral
    tour that neither helps nor hurts any taste.
    """
    sums = {'details': 0.0, 'historic': 0.0, 'social': 0.0}
    n = 0
    for row in stop_rows:
        d, h, s = _f(row[0]), _f(row[1]), _f(row[2])
        total = d + h + s
        if total <= 0:
            continue
        # Normalise each stop to sum 1 before averaging so a stop with slightly
        # off-sum raw metrics does not dominate.
        sums['details'] += d / total
        sums['historic'] += h / total
        sums['social'] += s / total
        n += 1
    if n == 0:
        return {'details': 1.0 / 3, 'historic': 1.0 / 3, 'social': 1.0 / 3}
    mean = {k: v / n for k, v in sums.items()}
    # Renormalise (floating error) so Σ = 1 exactly enough.
    tot = sum(mean.values()) or 1.0
    return {k: v / tot for k, v in mean.items()}


def _quality_factor(editor_score):
    """editor_score (5.0–8.0, or None) → q ∈ [0,1]."""
    s = _f(editor_score, EDITOR_SCORE_FALLBACK)
    q = (s - EDITOR_SCORE_FLOOR) / (EDITOR_SCORE_CEIL - EDITOR_SCORE_FLOOR)
    return _clamp(q, 0.0, 1.0)


def _reasons(character, prefs):
    """Two short phrases explaining the match, deterministically.

    Reason 1 describes what the tour is STRONG on — its dominant class (largest
    character share), tie-broken by the fixed CLASSES order. If the listener
    likes that class (pref ≥ 0.5) → "strong on history, which you like";
    otherwise it is stated plainly → "heavy on history, which you swipe past".
    "Strong on X" is therefore only ever said about a class the tour genuinely
    emphasises, never about a 10%-share class that merely had the least-negative
    taste weight.

    Reason 2 describes what the LISTENER is missing: among the classes they like
    (pref ≥ 0.5) that are not already named, the one with the smallest character
    share → "light on people stories" (only when the share is below an even 1/3
    split, otherwise "and people stories too"). If the listener likes nothing
    they are missing, reason 2 names the next class the tour leans on, or is
    omitted so a single honest reason stands alone.

    Ties broken by the fixed CLASSES display order (details < history < social)
    so the output is fully deterministic.
    """
    order = {name: i for i, (name, _) in enumerate(CLASSES)}
    label = dict(CLASSES)

    # Per-class facts: character share c_k, taste weight w_k = pref_k − 0.5.
    rows = []  # (name, c_k, w_k)
    for name, _ in CLASSES:
        rows.append((name, character[name], prefs[name] - 0.5))

    reasons = []
    used = set()

    # ── Reason 1 — what the tour is strong on. ───────────────────────────────
    # Take the tour's DOMINANT class (largest share). If the listener likes it
    # (w ≥ 0) say so explicitly; otherwise state it plainly. "Strong on X" is
    # only ever said about a class the tour genuinely emphasises, never about a
    # 10%-share class that merely had the least-negative taste weight.
    dominant = sorted(rows, key=lambda t: (-t[1], order[t[0]]))[0]
    dname, dshare, dweight = dominant
    if dweight >= 0.0:
        reasons.append(f"strong on {label[dname]}, which you like")
    else:
        reasons.append(f"heavy on {label[dname]}, which you swipe past")
    used.add(dname)

    # ── Reason 2 — a liked class (pref ≥ 0.5) the tour is LIGHT on. ───────────
    liked_light = [t for t in rows if t[0] not in used and t[2] >= 0.0]
    if liked_light:
        # Smallest character share = what the listener is most missing.
        liked_light.sort(key=lambda t: (t[1], order[t[0]]))
        name, share, _w = liked_light[0]
        if share < (1.0 / 3):              # below an even split → genuinely light
            reasons.append(f"light on {label[name]}")
        else:
            reasons.append(f"and {label[name]} too")
    else:
        # The listener likes nothing they are missing. Mention the next class
        # the tour leans on, factually.
        remaining = sorted((t for t in rows if t[0] not in used),
                           key=lambda t: (-t[1], order[t[0]]))
        if remaining and remaining[0][1] > 0.15:
            reasons.append(f"some {label[remaining[0][0]]}")
        # else: a single reason is enough.

    return reasons


def compute_match(prefs, swipe_count, character, editor_score):
    """The one public entry point. Pure function — deterministic, no I/O.

    Parameters
    ----------
    prefs : dict | None
        {details, historic, social} preference values in [0,1]. None → cold.
    swipe_count : int
        Number of swipes the listener has recorded. < MIN_SWIPES → cold start.
    character : dict
        {details, historic, social} tour character (see aggregate_tour_character).
    editor_score : float | Decimal | None
        The governing tour's evaluated score (5.0–8.0) or None (→ fallback 7.5).

    Returns
    -------
    dict
        Cold start:  {"match_percent": None, "reasons": [], "cold_start": True}
        Otherwise:   {"match_percent": int 0..100, "reasons": [str, str],
                      "cold_start": False}
    """
    if prefs is None or swipe_count is None or int(swipe_count) < MIN_SWIPES:
        return {"match_percent": None, "reasons": [], "cold_start": True}

    p = {
        'details': _clamp(_f(prefs.get('details'), 0.5), 0.0, 1.0),
        'historic': _clamp(_f(prefs.get('historic'), 0.5), 0.0, 1.0),
        'social': _clamp(_f(prefs.get('social'), 0.5), 0.0, 1.0),
    }
    c = {
        'details': _f(character.get('details')),
        'historic': _f(character.get('historic')),
        'social': _f(character.get('social')),
    }
    # Defensive renormalise of the character vector.
    ctot = c['details'] + c['historic'] + c['social']
    if ctot <= 0:
        c = {'details': 1.0 / 3, 'historic': 1.0 / 3, 'social': 1.0 / 3}
    else:
        c = {k: v / ctot for k, v in c.items()}

    alignment = sum(c[k] * (p[k] - 0.5) for k in c)        # [-0.5, 0.5]
    align = _clamp(0.5 + alignment, 0.0, 1.0)              # [0, 1]
    q = _quality_factor(editor_score)                      # [0, 1]

    blended = W_TASTE * align + W_QUALITY * q              # [0, 1]
    match_percent = int(round(100.0 * blended))
    match_percent = int(_clamp(match_percent, 0, 100))

    return {
        "match_percent": match_percent,
        "reasons": _reasons(c, p),
        "cold_start": False,
    }
