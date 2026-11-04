"""palace_museum_stops.py — LOCAL-865.

Palais Lascaris (Nice) delivered 1 of 6 stops ("27 R4 candidates failed canonical
match", LOCAL-861 A/B, cloud tour 528). Traced root causes (all measured, see
SUBMISSION_LOCAL-865.md):

1. The venue canon is NOT empty and NOT the wrong Lascaris: Wikidata Q34653010 gives
   1 work ("Raquel") and the nice.fr + fr/en Wikipedia pages add 9 musical
   instruments ("Harpe by Naderman (Paris, 1780)", ...). The R4 replenishment prompt,
   however, asks the model for "INDIVIDUAL ARTWORKS ... (painting, mosaic, sculpture,
   stained glass)", so it proposes paintings the palace does not hold; none shares a
   word with the 10 instrument titles -> every candidate "failed canonical match".
2. The tier is 'exhibit_museum' (10 site/wiki titles > 1 SPARQL), and the thin-source
   verification and the building/area fallback were gated on tier == 'thin', so the
   venue's real ROOMS and FEATURES were never offered as stops.
3. The tour-level lat/lng is Stop 1's model-produced coordinate; the "venue pin"
   used by [D4] only knew two hard-coded Nice museums, so any other venue kept an
   offset point (43.7073, 7.3054 — 2.5 km east of the 43.6977, 7.2773 pin).

This module supplies the data-side fix for a PALACE-MUSEUM whose collection is thin
on Wikidata: the venue's documented ROOMS and FEATURES (grand staircase, frescoed
ceilings, apothecary, chapel, salons, ... and the signature instrument collection)
become stops.

HONESTY CONTRACT (D756): a feature is a stop ONLY when the VENUE'S OWN corpus pages
(its official site + its own Wikipedia articles, already fetched for the resolved
venue) name it. Nothing is invented, and no other venue's works are ever borrowed:
every stop carries the page/sentence that grounds it.

Pure / deterministic given the corpus; unit-tested in
tests/test_local865_palace_museum.py.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

Coord = Tuple[Optional[float], Optional[float]]


def _norm(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return " ".join(stripped.split())


# ── is this a palace / historic-house museum? ────────────────────────────────

_PALACE_WORDS = (
    "palais", "palace", "palazzo", "chateau", "schloss", "villa", "mansion",
    "hotel particulier", "manor", "hall", "castle", "residence", "historic house",
    "maison", "casa", "pazo",
)
_PALACE_CORPUS_SIGNALS = (
    "palace", "palais", "baroque", "mansion", "chateau", "stately", "aristocratic",
    "noble family", "hotel particulier", "piano nobile", "etage noble", "historic house",
)


def is_palace_museum(venue_name: str, combined_text: str = "") -> bool:
    """True when the venue is a palace / mansion / historic-house museum.

    Name evidence alone is enough ("Palais Lascaris"); otherwise the corpus must
    describe the venue itself as such (>= 2 distinct signals, to avoid a museum that
    merely mentions a palace once).
    """
    nv = _norm(venue_name)
    if any(re.search(rf"\b{re.escape(w)}\b", nv) for w in _PALACE_WORDS):
        return True
    nt = _norm(combined_text)
    return sum(1 for s in _PALACE_CORPUS_SIGNALS if s in nt) >= 2


# ── feature vocabulary (EN + FR) ─────────────────────────────────────────────
# (stop name, feature id, accent-stripped keywords that GROUND it in the corpus).
# The vocabulary is only the lens: a feature ships only if a keyword is in the
# venue's own pages.
_FEATURES: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("The Musical Instrument Collection", "instruments",
     ("musical instruments", "instruments de musique", "collection of instruments",
      "collection d instruments", "instruments")),
    ("The Frescoed and Painted Ceilings", "ceilings",
     ("frescoed ceiling", "frescoed ceilings", "frescoes", "fresco", "painted ceiling",
      "painted ceilings", "plafonds peints", "plafond peint", "fresques", "fresque",
      "plafonds")),
    ("The Grand Staircase", "staircase",
     ("grand staircase", "monumental staircase", "grand escalier", "escalier monumental",
      "escalier d honneur", "staircase", "escalier")),
    ("The 17th-Century Apothecary", "apothecary",
     ("apothecary", "apothicairerie", "apothicaire", "pharmacie ancienne",
      "ancienne pharmacie", "old pharmacy")),
    ("The Palace Chapel", "chapel",
     ("chapel", "chapelle", "oratory", "oratoire")),
    ("The Noble Floor and State Rooms", "state_rooms",
     ("piano nobile", "etage noble", "salons", "state rooms", "salle", "drawing room",
      "reception rooms", "salons d apparat")),
    ("The Baroque Facade and Entrance", "facade",
     ("facade", "façade", "portal", "portail", "entrance hall", "vestibule", "porche")),
    ("The Tapestries and Period Furnishings", "furnishings",
     ("tapestries", "tapisseries", "period furniture", "mobilier", "furnishings",
      "flemish tapestries")),
]

# Feature ids that, when the corpus names them, should lead (the signature items
# first, so a 6-stop tour opens on what the museum is known for).
_FEATURE_ORDER = ("instruments", "ceilings", "staircase", "apothecary",
                  "chapel", "state_rooms", "facade", "furnishings")


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p and len(p.strip()) >= 40]


def _venue_tokens(venue_name: str) -> List[str]:
    """Distinctive tokens of the venue name ('Palais Lascaris, Nice' -> ['lascaris'])."""
    head = (venue_name or "").split(",")[0]
    toks = [t for t in _norm(head).split() if len(t) >= 4 and t not in _PALACE_WORDS]
    return toks


def _page_is_venue_own(page: Dict, venue_tokens: Sequence[str]) -> bool:
    """A page grounds a feature only if it is ABOUT this venue (names it)."""
    if not venue_tokens:
        return True
    hay = _norm((page.get("url", "") or "") + " " + (page.get("title", "") or "")
                + " " + (page.get("text", "") or "")[:4000])
    return any(t in hay for t in venue_tokens)


def _origin(url: str) -> str:
    u = (url or "").lower()
    if "wikipedia.org" in u:
        m = re.search(r"//([a-z]+)\.wikipedia", u)
        return f"wikipedia_{m.group(1)}" if m else "wikipedia"
    return "venue_site"


def detect_feature_stops(
    venue_name: str,
    pages: Sequence[Dict] = (),
    combined_text: str = "",
    *,
    needed: int = 0,
    exclude_names: Sequence[str] = (),
) -> List[Dict]:
    """Return up to ``needed`` ROOM / FEATURE stops grounded in the venue's own pages.

    Each stop is a dict compatible with the LOCAL-667 fallback stops
    (``_stop_kind='collection_area'`` so every downstream gate treats it as a
    contained interior stop of THIS venue) plus:
      * ``_feature_id``       — which feature;
      * ``_feature_sources``  — [{origin, url, sentence}] (>= 1 sentence from a page
        about this venue that names the feature) — the D756 grounding record;
      * ``_feature_facts``    — the grounding sentences, used as the ONLY facts the
        narration may state.
    Returns [] when ``needed`` <= 0, the venue is not a palace-museum, or the corpus
    grounds nothing.
    """
    if needed <= 0:
        return []
    page_list = [p for p in (pages or []) if isinstance(p, dict) and p.get("text")]
    if not page_list and combined_text:
        page_list = [{"url": "", "text": combined_text}]
    if not is_palace_museum(venue_name, combined_text or
                            " ".join(p.get("text", "") for p in page_list)):
        return []

    vtoks = _venue_tokens(venue_name)
    own_pages = [p for p in page_list if _page_is_venue_own(p, vtoks)]
    excl = {_norm(n) for n in exclude_names}

    by_id = {fid: (name, kws) for name, fid, kws in _FEATURES}
    out: List[Dict] = []
    for fid in _FEATURE_ORDER:
        if len(out) >= needed:
            break
        name, kws = by_id[fid]
        if _norm(name) in excl:
            continue
        sources: List[Dict] = []
        for page in own_pages:
            for sent in _sentences(page.get("text", "")):
                ns = _norm(sent)
                # whole-word / phrase match (so 'hall' never fires inside 'marshall')
                if any(re.search(rf"\b{re.escape(_norm(k))}\b", ns) for k in kws):
                    sources.append({"origin": _origin(page.get("url", "")),
                                    "url": page.get("url", ""),
                                    "sentence": sent[:400]})
                    if len([s for s in sources if s["url"] == page.get("url", "")]) >= 2:
                        break
        if not sources:
            continue
        # Keep the strongest 4 sentences, preferring ones that name a distinctive
        # keyword over the bare one-word fallbacks.
        sources = sources[:4]
        out.append({
            "name": name,
            "address": "",
            "verified": True,
            "_stop_kind": "collection_area",
            "_feature_id": fid,
            "_fallback_source": f"palace_feature:{fid}",
            "_feature_sources": sources,
            "_feature_facts": [s["sentence"] for s in sources],
        })
        excl.add(_norm(name))
    return out


def feature_narration_instruction(poi: Dict) -> str:
    """Prompt addendum for a feature stop: narrate ONLY the sourced facts."""
    facts = poi.get("_feature_facts") or []
    if not facts:
        return ""
    lines = "\n".join(f"  - {f}" for f in facts)
    return (
        f"\nSOURCED FACTS FOR THIS STOP (LOCAL-865) — this stop is a documented ROOM or "
        f"FEATURE of the venue, not an artwork. Describe it ONLY from these facts from the "
        f"venue's own pages; do NOT invent an artist, year, medium, dimensions or any "
        f"object not named here, and NEVER mention a work from another museum:\n{lines}\n"
    )


# ── venue pin (tour-level lat/lng) ───────────────────────────────────────────

def _valid(c: Optional[Coord]) -> bool:
    try:
        return (c is not None and c[0] is not None and c[1] is not None
                and not (float(c[0]) == 0.0 and float(c[1]) == 0.0)
                and -90 <= float(c[0]) <= 90 and -180 <= float(c[1]) <= 180)
    except (TypeError, ValueError):
        return False


def pick_venue_pin(
    known: Optional[Coord] = None,
    resolver: Optional[Coord] = None,
    corpus: Optional[Coord] = None,
    first_stop: Optional[Coord] = None,
) -> Tuple[Coord, str]:
    """Choose the single venue pin used for the tour and every interior stop.

    Priority: curated table -> the resolved venue's own Wikidata P625 -> a corpus
    coordinate -> Stop 1's (model) coordinate. The resolver pin MUST outrank the
    corpus regex and Stop 1: the Lascaris tour carried Stop 1's 43.7073,7.3054
    (2.5 km east of the 43.6977,7.2773 P625 pin).
    """
    for coord, src in ((known, "known"), (resolver, "resolver_p625"),
                       (corpus, "corpus"), (first_stop, "model_first_stop")):
        if _valid(coord):
            return ((float(coord[0]), float(coord[1])), src)
    return ((None, None), "none")
