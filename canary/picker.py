#!/usr/bin/env python3
"""canary/picker.py — stratified, never-repeating venue picker for LOCAL-611.

Every canary run tries THREE never-tried venues, one from each stratum:

  1. famous   — a well-known venue (>= FAMOUS_SITELINKS sitelinks). These are
                the venues a user is most likely to request; a regression here
                is the most visible.
  2. obscure  — a long-tail venue (<= OBSCURE_SITELINKS sitelinks), often with
                no English Wikipedia article. This is where the field defects
                came from: a venue type/record the pipeline had never seen.
  3. rotating — one of three sub-kinds, rotated by run index so all three are
                exercised over time:
                  (a) a venue with NO official site (P856 absent) — the
                      "no website to check" path;
                  (b) a venue in a non-English-speaking country — i18n / name
                      handling;
                  (c) a walking/biking city route, phrased
                      "<landmark> to <landmark>, <city>".

"Never repeated" is enforced by a tried-venue ledger (canary/tried_venues.jsonl):
every venue a run selects is appended, and the picker excludes any QID (or, for
synthesized routes, any route key) already present. The ledger is the memory
that makes "try a new tour all the time" literally true.

The picker is pure/offline: it operates on an in-memory pool (list of dicts as
produced by venue_pool.load_pool) and a tried set, so tests drive it with small
fixtures and need no network.
"""

from __future__ import annotations

import json
import os
import random
from typing import Dict, List, Optional, Sequence, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
TRIED_PATH = os.path.join(HERE, "tried_venues.jsonl")

FAMOUS_SITELINKS = int(os.environ.get("CANARY_FAMOUS_SITELINKS", "30"))
OBSCURE_SITELINKS = int(os.environ.get("CANARY_OBSCURE_SITELINKS", "5"))

# Countries whose primary language is English — used to pick a NON-English-
# country venue for the rotating stratum. Matched against the row's country
# label or country_qid. (A short, deliberately conservative list; anything not
# here counts as "non-English" for the rotation.)
ENGLISH_COUNTRY_LABELS = {
    "United States", "United States of America", "United Kingdom", "Canada",
    "Australia", "New Zealand", "Ireland", "Jamaica", "Bahamas", "Belize",
    "Guyana", "Barbados", "Trinidad and Tobago",
}
ENGLISH_COUNTRY_QIDS = {
    "Q30", "Q145", "Q16", "Q408", "Q664", "Q27", "Q766", "Q778", "Q242",
    "Q244", "Q734", "Q754",
}

STRATA = ("famous", "obscure", "rotating")
ROTATING_SUBKINDS = ("no_site", "non_english", "walking_route")


# --------------------------------------------------------------------------- #
# Tried-venue ledger
# --------------------------------------------------------------------------- #
def load_tried(path: str = TRIED_PATH) -> Set[str]:
    """Return the set of tried keys (QIDs and route keys) from the ledger."""
    keys: Set[str] = set()
    if not os.path.exists(path):
        return keys
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = rec.get("key")
            if k:
                keys.add(k)
    return keys


def record_tried(selections: Sequence[dict], path: str = TRIED_PATH) -> None:
    """Append selected venues to the tried ledger. Each selection must carry a
    'key' (QID for real venues, or a synthesized route key)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for sel in selections:
            rec = {
                "key": sel["key"],
                "stratum": sel.get("stratum"),
                "label": sel.get("label"),
                "country": sel.get("country"),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _is_english_country(row: dict) -> bool:
    return (
        row.get("country") in ENGLISH_COUNTRY_LABELS
        or row.get("country_qid") in ENGLISH_COUNTRY_QIDS
    )


def venue_location_string(row: dict) -> str:
    """Build the orchestrator 'location' string for a real venue row."""
    label = (row.get("label") or "").strip()
    city = (row.get("city") or "").strip()
    country = (row.get("country") or "").strip()
    parts = [p for p in (label, city, country) if p]
    return ", ".join(parts) if parts else label


def _usable(row: dict) -> bool:
    """A row must have a non-empty label to be a tour request."""
    return bool((row.get("label") or "").strip())


def _as_selection(row: dict, stratum: str, subkind: Optional[str] = None) -> dict:
    sel = {
        "key": row["qid"],
        "stratum": stratum,
        "label": row.get("label"),
        "city": row.get("city"),
        "country": row.get("country"),
        "country_qid": row.get("country_qid"),
        "sitelinks": row.get("sitelinks", 0),
        "has_site": row.get("has_site", False),
        "kind": row.get("kind"),
        "location": venue_location_string(row),
        "tour_type": "walking" if row.get("kind") == "street" else "",
    }
    if subkind:
        sel["subkind"] = subkind
    return sel


# --------------------------------------------------------------------------- #
# Walking-route synthesis (rotating sub-kind c)
# --------------------------------------------------------------------------- #
def _synth_walking_route(pool: List[dict], tried: Set[str], rng: random.Random) -> Optional[dict]:
    """Build a '<landmark> to <landmark>, <city>' route from two street/park
    venues in the same country. Route key is deterministic from its parts so it
    can be de-duplicated in the tried ledger."""
    cand = [r for r in pool if r.get("kind") in ("street", "park") and _usable(r)]
    # Group by country so the two landmarks are plausibly in one place.
    by_country: Dict[str, List[dict]] = {}
    for r in cand:
        by_country.setdefault(r.get("country_qid") or r.get("country") or "?", []).append(r)
    countries = [c for c, rs in by_country.items() if len(rs) >= 2]
    rng.shuffle(countries)
    for c in countries:
        rs = by_country[c][:]
        rng.shuffle(rs)
        a, b = rs[0], rs[1]
        city = (a.get("city") or b.get("city") or a.get("country") or "").strip()
        la, lb = (a.get("label") or "").strip(), (b.get("label") or "").strip()
        if not (la and lb and city):
            continue
        key = "route:" + "|".join(sorted([a["qid"], b["qid"]]))
        if key in tried:
            continue
        location = f"{la} to {lb}, {city}"
        return {
            "key": key,
            "stratum": "rotating",
            "subkind": "walking_route",
            "label": location,
            "city": city,
            "country": a.get("country"),
            "country_qid": a.get("country_qid"),
            "sitelinks": max(a.get("sitelinks", 0), b.get("sitelinks", 0)),
            "has_site": False,
            "kind": "route",
            "location": location,
            "tour_type": "walking",
        }
    return None


# --------------------------------------------------------------------------- #
# Stratum selectors
# --------------------------------------------------------------------------- #
def _pick_famous(pool, tried, exclude, rng):
    cand = [r for r in pool if _usable(r) and r["qid"] not in tried
            and r["qid"] not in exclude and r.get("sitelinks", 0) >= FAMOUS_SITELINKS]
    if not cand:
        return None
    return _as_selection(rng.choice(cand), "famous")


def _pick_obscure(pool, tried, exclude, rng):
    cand = [r for r in pool if _usable(r) and r["qid"] not in tried
            and r["qid"] not in exclude and r.get("sitelinks", 0) <= OBSCURE_SITELINKS]
    if not cand:
        return None
    return _as_selection(rng.choice(cand), "obscure")


def _pick_rotating(pool, tried, exclude, rng, subkind):
    if subkind == "walking_route":
        sel = _synth_walking_route(
            [r for r in pool if r["qid"] not in exclude], tried, rng)
        return sel
    if subkind == "no_site":
        cand = [r for r in pool if _usable(r) and r["qid"] not in tried
                and r["qid"] not in exclude and not r.get("has_site", False)]
    else:  # non_english
        cand = [r for r in pool if _usable(r) and r["qid"] not in tried
                and r["qid"] not in exclude and not _is_english_country(r)]
    if not cand:
        return None
    return _as_selection(rng.choice(cand), "rotating", subkind)


def _rotating_order(run_index: int) -> Tuple[str, ...]:
    """Rotate which sub-kind is tried FIRST by the run index, so all three are
    exercised over successive runs. Falls through to the others if the primary
    sub-kind has no eligible candidate."""
    start = run_index % len(ROTATING_SUBKINDS)
    return tuple(ROTATING_SUBKINDS[(start + i) % len(ROTATING_SUBKINDS)]
                 for i in range(len(ROTATING_SUBKINDS)))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def pick_new_venues(
    pool: List[dict],
    tried: Optional[Set[str]] = None,
    *,
    run_index: int = 0,
    seed: Optional[int] = None,
    n: int = 3,
) -> List[dict]:
    """Pick `n` never-tried venues across the strata (famous, obscure, rotating).

    * `tried` is a set of keys already used (QIDs and route keys). None → empty.
    * Selections never repeat a key in `tried`, and never repeat each other
      within this call (an `exclude` set grows as strata are filled).
    * Returns a list of selection dicts; each has a unique 'key', a 'location'
      string ready for the orchestrator, a 'tour_type', and the 'stratum'.

    The function is best-effort for breadth: if a stratum has no eligible
    candidate it is skipped rather than raising, but with a real pool all three
    fill. Order is deterministic given `seed`.
    """
    tried = set(tried or set())
    rng = random.Random(seed)
    exclude: Set[str] = set()
    out: List[dict] = []

    # 1. famous
    sel = _pick_famous(pool, tried, exclude, rng)
    if sel:
        out.append(sel)
        exclude.add(sel["key"])

    # 2. obscure
    sel = _pick_obscure(pool, tried, exclude, rng)
    if sel:
        out.append(sel)
        exclude.add(sel["key"])

    # 3. rotating (try the run-indexed sub-kind first, then the others)
    for subkind in _rotating_order(run_index):
        sel = _pick_rotating(pool, tried, exclude, rng, subkind)
        if sel:
            out.append(sel)
            exclude.add(sel["key"])
            break

    # If strata came up short (small/filtered pool), backfill with ANY untried
    # venue so a run still exercises `n` new venues when the pool allows it.
    if len(out) < n:
        backfill = [r for r in pool if _usable(r) and r["qid"] not in tried
                    and r["qid"] not in exclude]
        rng.shuffle(backfill)
        for r in backfill:
            if len(out) >= n:
                break
            sel = _as_selection(r, "backfill")
            out.append(sel)
            exclude.add(sel["key"])

    return out[:n]
