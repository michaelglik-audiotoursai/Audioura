"""museum_fallback_stops.py — LOCAL-667.

When a real museum has a thin Wikidata catalogue AND the thin-source verification
(thin_wikidata_fallback) still cannot reach the requested stop count, the honest
answer is not "1 of 5". A museum tour has legitimate stops beyond individually
catalogued artworks:

  * the HISTORIC BUILDING itself — the Ho Chi Minh City Museum of Fine Arts
    occupies the Hui Bon Hoa mansion (1929-1934), a highlight in its own right;
  * NAMED COLLECTION AREAS — lacquer, silk painting, Champa sculpture, Óc Eo
    antiquities — the groupings a visitor actually walks through.

Both are REAL stops when the work list is thin. The LOCAL-632 shortfall line is
then only for what is TRULY left after these are added.

HONESTY CONTRACT (same as every other path): nothing is invented. A building stop
is produced only when the corpus (the museum's own pages + Wikipedia, already
fetched) names the building or its architecture; a collection-area stop is
produced only when the corpus actually names that medium/area at this museum. A
keyword that does not appear in the corpus never becomes a stop.

These stops are typed (`_stop_kind` = 'building' / 'collection_area') and carry
`verified=True` with a corpus-grounded evidence record, so the museum
verified-only gate (LOCAL-16) keeps them, and the assembler renders them as area
/ building stops — never as artworks (no artist, no year, no "oil on canvas").

Pure/deterministic given the corpus text; unit-tested in
tests/test_local667_building_stops.py.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence


def _norm(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return " ".join(stripped.split())


# Collection-area / medium vocabulary. Each entry is (canonical area label, the
# accent-stripped keywords that signal it). A term becomes a stop ONLY if one of
# its keywords is present in the venue corpus — the vocabulary is just the lens.
_AREA_VOCAB = [
    ("Lacquer painting", ["lacquer", "son mai"]),
    ("Silk painting", ["silk painting", "silk paintings", "on silk", "lua"]),
    ("Oil painting", ["oil painting", "oil paintings", "oil on canvas"]),
    ("Woodblock prints", ["woodblock", "woodcut", "dong ho"]),
    ("Champa sculpture", ["champa", "cham sculpture", "cham art"]),
    ("Óc Eo antiquities", ["oc eo", "funan"]),
    ("Khmer sculpture", ["khmer"]),
    ("Ceramics", ["ceramic", "ceramics", "porcelain", "pottery"]),
    ("Buddhist sculpture", ["buddhist sculpture", "buddha statue", "bodhisattva"]),
    ("Contemporary art", ["contemporary art", "modern art gallery"]),
    ("Folk art", ["folk art", "folk painting"]),
    ("Bronze sculpture", ["bronze sculpture", "bronze statue"]),
    ("Stone sculpture", ["stone sculpture", "stone carving"]),
]

# Architecture / building signal words. The building is a legitimate stop when the
# corpus describes it as a building of note (mansion, villa, architect, built in …,
# colonial architecture, heritage building, etc.).
_BUILDING_SIGNALS = [
    "mansion", "villa", "palace", "chateau", "architect", "architecture",
    "colonial", "heritage building", "historic building", "built in",
    "constructed in", "art deco", "neoclassical", "facade", "edifice",
    "former residence", "listed building",
]

# A building proper-name pattern: a capitalised multi-word name followed by one of
# {mansion, villa, palace, residence, house, building}. Captures "Hui Bon Hoa
# mansion", "Diethelm villa", etc. — grounded, taken from the corpus verbatim.
_BUILDING_NAME_RE = re.compile(
    r"\b([A-ZÀ-Ý][\w'’.-]*(?:\s+[A-ZÀ-Ý][\w'’.-]*){0,3})\s+"
    r"(mansion|villa|palace|residence|house|building|edifice)\b")


def _corpus_text(pages: Sequence[Dict], combined_text: str = "") -> str:
    if combined_text:
        return combined_text
    return "\n\n".join(p.get("text", "") for p in (pages or [])
                       if isinstance(p, dict) and p.get("text"))


def detect_building_stop(
    venue_name: str,
    pages: Sequence[Dict] = (),
    combined_text: str = "",
    building_qid: str = "",
    building_name_hint: str = "",
) -> Optional[Dict]:
    """Return a single building stop dict, or None when the corpus gives no
    grounded building to describe.

    A building stop is produced when ANY of:
      * `building_qid` is set (the building has its own Wikidata item), OR
      * `building_name_hint` is a non-empty named building (from Wikidata P1435
        heritage designation / P84 architect, passed by the caller), OR
      * the corpus names a proper building (`_BUILDING_NAME_RE`) or describes the
        venue's architecture (`_BUILDING_SIGNALS`).
    The stop never invents architecture facts; it just marks the building as a
    stop and leaves narration to the sourced stop writer.
    """
    text = _corpus_text(pages, combined_text)
    ntext = _norm(text)

    name = (building_name_hint or "").strip()
    detail = ""
    if not name:
        m = _BUILDING_NAME_RE.search(text or "")
        if m:
            name = f"{m.group(1)} {m.group(2)}".strip()
            detail = "corpus_named_building"
    if not name:
        # No proper name, but architecture is described → a generic building stop.
        if building_qid or any(sig in ntext for sig in _BUILDING_SIGNALS):
            name = f"The {venue_name} building"
            detail = "architecture_described" if not building_qid else "building_wikidata_item"
    if not name:
        return None

    return {
        "name": name,
        "address": "",
        "verified": True,
        "_stop_kind": "building",
        "_fallback_source": detail or ("building_qid" if building_qid else "building_name_hint"),
        "_building_qid": building_qid or "",
    }


def detect_collection_area_stops(
    pages: Sequence[Dict] = (),
    combined_text: str = "",
    max_areas: int = 8,
) -> List[Dict]:
    """Return collection-area stops grounded in the corpus, in vocabulary order.

    Each area is included only when one of its keywords appears in the corpus, so
    "Champa sculpture" ships only if the corpus actually names Champa at this
    museum. Deterministic order; de-duplicated by canonical area label.
    """
    text = _corpus_text(pages, combined_text)
    ntext = _norm(text)
    out: List[Dict] = []
    seen = set()
    for label, keywords in _AREA_VOCAB:
        if label in seen:
            continue
        hit = next((kw for kw in keywords if _norm(kw) in ntext), "")
        if hit:
            seen.add(label)
            out.append({
                "name": f"{label} collection",
                "address": "",
                "verified": True,
                "_stop_kind": "collection_area",
                "_fallback_source": f"corpus_keyword:{hit}",
            })
            if len(out) >= max_areas:
                break
    return out


def build_fallback_stops(
    venue_name: str,
    pages: Sequence[Dict] = (),
    combined_text: str = "",
    *,
    needed: int = 0,
    building_qid: str = "",
    building_name_hint: str = "",
    exclude_names: Sequence[str] = (),
) -> List[Dict]:
    """Build up to `needed` fallback stops: the historic building first (one at
    most), then named collection areas, all grounded in the corpus and excluding
    anything already in the tour (`exclude_names`, matched case/accent-insensitively).

    Returns [] when `needed` <= 0 or the corpus grounds nothing — the caller then
    keeps the honest shortfall for what is truly left (LOCAL-632).
    """
    if needed <= 0:
        return []
    _excl = {_norm(n) for n in exclude_names}
    stops: List[Dict] = []

    bstop = detect_building_stop(venue_name, pages, combined_text,
                                 building_qid=building_qid,
                                 building_name_hint=building_name_hint)
    if bstop and _norm(bstop["name"]) not in _excl:
        stops.append(bstop)
        _excl.add(_norm(bstop["name"]))

    for area in detect_collection_area_stops(pages, combined_text):
        if len(stops) >= needed:
            break
        if _norm(area["name"]) in _excl:
            continue
        stops.append(area)
        _excl.add(_norm(area["name"]))

    return stops[:needed]
