#!/usr/bin/env python3
"""museum_claim_gate.py — LOCAL-864: museum claims that ship must be sourced,
stops must be about THIS venue's work, and the museum's catalog record wins.

Evidence: LOCAL-861 museum A/B (submission_artifacts/local861/).

1. UNSOURCED claims shipped.  The story verifier logged
   ``UNSOURCED: 'Louis Broder commissioned limited'`` and stripped only the ONE
   sentence containing the extracted span.  Everything else about the same
   invented agent survived ("Boris Fridman, who collected these editions ...",
   "He donated this statue ..."), later phases (credit-line loop, retries)
   rewrote stop text AFTER that strip ran, and nothing re-checked the delivered
   text.  This module is the last-word gate on the DELIVERED text: a sentence
   that asserts a named agent or a dated event that no retrieved source for that
   stop contains, or that names an entity the verifier flagged UNSOURCED, is
   dropped — unless it is DISCLOSED as unverified (D760: "It is sometimes
   said ...").  Pronoun sentences left dangling by a drop go with it.

2. Stop-identity bleed.  A work may be matched to a stop only when it belongs
   to THIS venue (accession number or a URL on the venue's domain, and not
   labelled as held elsewhere) AND its title matches beyond generic words
   (head, landscape, portrait, Buddha ...).  "Head of a Buddha" must not match
   Miro's "Head of a Catalan Peasant".

3. Object misidentification.  The museum's own catalog record wins over a search
   hit: date, culture and material come from the record.  A sentence that
   assigns the object a culture or century the record contradicts is dropped
   (and the "national treasure" story built on it goes with it), and the record's
   culture/date is stated when the narration omits it.

Pure: no network, no LLM, no DB.  Deterministic and idempotent.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

__all__ = [
    "GENERIC_TITLE_WORDS", "distinctive_tokens", "titles_match",
    "extract_accession", "host_matches_venue", "work_belongs_to_venue",
    "accept_stop_match", "reconcile_with_catalog", "sentence_contradicts_catalog",
    "is_disclosed", "unsourced_sentences", "filter_stop_body",
    "filter_tour_text_claims", "register_rejected_match", "rejected_matches_for",
    "clear_rejected_matches", "foreign_record_snippet", "parse_label_block",
    "catalog_urls_from_snippets", "catalog_urls_by_search", "lexicon_artists", "scrub_artists_tour", "filter_tour_text_claims_keep_tail", "record_names_stop", "makers_from_venue_works", "maker_bound_to_stop", "foreign_makers", "catalog_statement",
]

_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


# ═══ 2. STOP IDENTITY ════════════════════════════════════════════════════════

# Words that name a KIND of object or a subject, not a particular work.  A match
# resting on these alone is a different work with a similar-sounding title.
GENERIC_TITLE_WORDS = frozenset("""
head heads landscape landscapes portrait portraits figure figures study studies
buddha buddhas bodhisattva statue statuette sculpture bust relief panel painting
paintings scene scenes view views still life nude woman man girl boy lady
untitled composition vase bowl dish plate cup jar box bottle mask seated standing
reclining crowned image images work works print drawing sketch of the a an and
with in on at from for by de la le les du des el der die das
""".split())

_STOPWORDS = frozenset("the and for with from des les del della aux sur dans une que qui por con para nel dei".split())


def distinctive_tokens(title: str) -> set:
    """Tokens of a title that identify a particular work (accession numbers and
    parenthetical glosses removed; generic words removed)."""
    t = re.sub(r"\([^)]*\)", " ", title or "")
    t = re.sub(r"\b[A-Z]?\d+[A-Za-z0-9.+\-]*\b", " ", t)  # B60D49+, 1998.52, 338
    toks = re.findall(r"[a-z]{3,}", _fold(t))
    return {w for w in toks if w not in GENERIC_TITLE_WORDS and w not in _STOPWORDS}


def _norm_title(title: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", title or "")
    return " ".join(re.findall(r"[a-z0-9]+", _fold(t)))


def titles_match(stop_title: str, work_title: str) -> bool:
    """True only when the two titles name the same work, beyond generic words.

    If either title has no distinctive token ("Head of a Buddha"), only an exact
    normalised match counts.  Otherwise at least 75% of the smaller distinctive
    set must be shared, and at least one token must be.
    """
    a, b = _norm_title(stop_title), _norm_title(work_title)
    if not a or not b:
        return False
    if a == b:
        return True
    da, db = distinctive_tokens(stop_title), distinctive_tokens(work_title)
    if not da or not db:
        return False
    shared = da & db
    return bool(shared) and len(shared) / min(len(da), len(db)) >= 0.75


def extract_accession(*texts: str) -> str:
    for t in texts:
        m = re.search(r"\b[A-Z]{0,3}\d{1,4}[A-Z]\d{1,4}\+?(?=\W|$)", t or "")
        if m:
            return m.group(0)
        m = re.search(r"\b\d{1,4}\.\d{1,4}(?:\.\d{1,4})?[a-z]?\b", t or "")
        if m:
            return m.group(0)
    return ""


def _domain(url_or_host: str) -> str:
    h = (urlparse(url_or_host).netloc or url_or_host or "").lower().strip()
    h = h.split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _registrable(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def host_matches_venue(url: str, venue_url: str) -> bool:
    if not url or not venue_url:
        return False
    return _registrable(_domain(url)) == _registrable(_domain(venue_url))


def work_belongs_to_venue(work: Dict, venue_url: str = "", venue_name: str = "") -> Tuple[bool, str]:
    """A work belongs to this venue when it carries an accession number or a URL
    on the venue's domain, and nothing says another institution holds it."""
    if not work:
        return False, "no work"
    holder = _fold(str(work.get("holder") or work.get("collection") or work.get("venue") or ""))
    if holder and venue_name:
        vtoks = {t for t in re.findall(r"[a-z]{4,}", _fold(venue_name))
                 if t not in ("museum", "musee", "gallery", "national", "art", "arts")}
        if vtoks and not (vtoks & set(re.findall(r"[a-z]{4,}", holder))):
            return False, f"held by '{holder[:40]}', not this venue"
    url = str(work.get("url") or work.get("source_url") or work.get("record_url") or "")
    acc = str(work.get("accession_number") or work.get("accession") or "").strip()
    if url and venue_url and not host_matches_venue(url, venue_url):
        return False, f"record URL {url[:60]} is not on the venue's domain"
    if acc or (url and venue_url and host_matches_venue(url, venue_url)):
        return True, "accession" if acc else "venue url"
    return False, "no accession number and no museum URL"


def accept_stop_match(stop_title: str, work: Dict, venue_url: str = "",
                      venue_name: str = "") -> Tuple[bool, str]:
    """Gate for matching a work to a stop.  Both conditions must hold."""
    ok, why = work_belongs_to_venue(work, venue_url, venue_name)
    if not ok:
        return False, f"not this venue's work: {why}"
    if not titles_match(stop_title, str(work.get("title") or "")):
        return False, "title matches only on generic words"
    return True, "ok"


# Matches that were refused, per stop title: their artist/title are foreign to
# the stop and are used by the text filter to drop sentences that still narrate them.
_REJECTED: Dict[str, List[Dict]] = {}


def register_rejected_match(stop_title: str, work: Dict) -> None:
    _REJECTED.setdefault(_norm_title(stop_title), []).append(dict(work))


def rejected_matches_for(stop_title: str) -> List[Dict]:
    return list(_REJECTED.get(_norm_title(stop_title), []))


def clear_rejected_matches() -> None:
    _REJECTED.clear()


_RECORD_PATH_RE = re.compile(r"(?i)/(objects?|collection[s]?|oeuvres?|artworks?|works?|item|"
                             r"art|explore-the-collection|search/objects|catalog)/")
_VENUE_NOISE = frozenset("museum musee gallery national art arts of the de la san francisco "
                         "new york paris".split())


def _venue_host_tokens(venue_name: str) -> set:
    return {t for t in re.findall(r"[a-z]{4,}", _fold(venue_name)) if t not in _VENUE_NOISE}


def makers_from_venue_works(stop_title: str, works: Iterable[Dict]) -> List[str]:
    """The creator(s) this venue's own collection list (SPARQL venue works) gives
    for the stop's work, matched by title beyond generic words."""
    out: List[str] = []
    for w in works or []:
        if not isinstance(w, dict):
            continue
        t = str(w.get("title") or w.get("label") or "")
        if not t or not (titles_match(stop_title, t) or record_names_stop(stop_title, t)):
            continue
        for c in [w.get("creator")] + list(w.get("creators") or []):
            if c and c not in out:
                out.append(str(c))
    return out


def foreign_record_snippet(snippet: Dict, stop_title: str, venue_name: str = "",
                           venue_url: str = "") -> Optional[Dict]:
    """If a retrieved snippet is a collection RECORD of another museum whose title
    shares only generic words with the stop, return the work it describes
    ({'title','url','artist'}); else None.  Used to refuse the match and to keep
    that work's narration out of the stop (Head of a Buddha <- Miro)."""
    url = str(snippet.get("url") or snippet.get("link") or "")
    title = str(snippet.get("title") or "")
    if not url or not title:
        return None
    if not _RECORD_PATH_RE.search(url):
        return None
    host = _domain(url)
    if venue_url:
        if host_matches_venue(url, venue_url):
            return None
    else:
        vt = _venue_host_tokens(venue_name)
        if not vt or any(t in host for t in vt):
            return None
    clean = re.split(r"\s+[|\u2013\u2014\-]\s+", title)[0].strip()
    if titles_match(stop_title, clean):
        return None
    return {"title": clean, "url": url, "artist": ""}


# ── The museum's own object page: a LABEL BLOCK ─────────────────────────────
# Many collection sites that are not eMuseum print the wall label as a block of
# <br>-separated lines right after the bold title.  Asian Art Museum,
# collections.asianart.org/collection/seated-buddha-dated-338/:
#     <p><b>Buddha dated 338</b></p>
#     <p>China; Hebei province<br/>Later Zhao kingdom (319–351)<br/>
#        Bronze with gilding<br/><em>The Avery Brundage Collection</em>, B60B1034</p>
# and .../crowned-and-bejeweled-buddha-image-and-throne/:
#     Approx. 1860–1880 / Myanmar (Burma); Mandalay area /
#     Wood and iron, with lacquer, gilding, and mirrored glass / Gift ..., 2006.27.17
# Each line is classified by what it IS (date / place / material / credit), not by
# position, because sites order them differently.

_COUNTRY_TO_CULTURE = {
    "china": "Chinese", "myanmar": "Burmese", "burma": "Burmese", "vietnam": "Vietnamese",
    "thailand": "Thai", "japan": "Japanese", "korea": "Korean", "india": "Indian",
    "tibet": "Tibetan", "cambodia": "Cambodian", "nepal": "Nepalese", "indonesia": "Indonesian",
    "java": "Javanese", "sri lanka": "Sri Lankan", "laos": "Lao", "iran": "Persian",
    "mongolia": "Mongolian", "pakistan": "Pakistani", "afghanistan": "Afghan",
    "philippines": "Philippine", "bangladesh": "Bangladeshi",
    "france": "French", "italy": "Italian", "spain": "Spanish", "netherlands": "Dutch",
    "germany": "German", "england": "English", "egypt": "Egyptian",
}
_MATERIAL_WORDS = ("bronze", "gilding", "gilt", "stone", "sandstone", "limestone", "marble",
                   "schist", "wood", "lacquer", "iron", "silk", "paper", "ink", "clay",
                   "terracotta", "stucco", "porcelain", "stoneware", "jade", "ivory", "gold",
                   "silver", "copper", "brass", "glass", "oil on", "canvas", "earthenware",
                   "pigment", "color", "colors", "textile", "cotton", "bamboo", "lead")
_DATEY = re.compile(r"(?i)\b(\d{3,4}|\d{1,2}(?:st|nd|rd|th)\s+century|century|dynasty|kingdom|"
                    r"period|approx\.?|ca\.|circa|era|reign)\b")


def _content_tokens(title: str) -> set:
    t = re.sub(r"\([^)]*\)", " ", title or "")
    return {w for w in re.findall(r"[a-z0-9]+", _fold(t))
            if (len(w) >= 4 or w.isdigit()) and w not in _STOPWORDS and w not in ("with", "from")}


def record_names_stop(stop_title: str, record_title: str) -> bool:
    """Every content word of the stop title is in the record title (generic words
    included: here they narrow, they do not widen)."""
    a, b = _content_tokens(stop_title), _content_tokens(record_title)
    return bool(a) and a <= b


def parse_label_block(html: str, title: str = "") -> Dict[str, str]:
    """Parse a wall-label block ({'title','date','culture','origin','material',
    'credit_line','accession_number'}).  {} when no block is found."""
    if not html:
        return {}
    from html import unescape
    h = unescape(html)
    for m in re.finditer(r"<p>\s*<(?:b|strong)>(.*?)</(?:b|strong)>\s*</p>\s*<p>(.*?)</p>", h, re.S):
        ttl = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title and not record_names_stop(title, ttl):
            continue
        lines = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip(" ,;")
                 for x in re.split(r"<br\s*/?>", m.group(2))]
        lines = [x for x in lines if x]
        if len(lines) < 2:
            continue
        rec = {"title": ttl}
        for ln in lines:
            low = _fold(ln)
            acc = extract_accession(ln)
            if acc and ("gift" in low or "collection" in low or "purchase" in low or
                        "bequest" in low or re.search(r"\d+\.\d+", ln) or ln.endswith(acc)):
                rec.setdefault("accession_number", acc)
                rec.setdefault("credit_line", ln.replace(acc, "").strip(" ,;"))
                continue
            country = next((c for c in _COUNTRY_TO_CULTURE if re.search(r"\b" + c + r"\b", low)), None)
            if country and "culture" not in rec and not any(w in low for w in ("gift", "collection")):
                rec["culture"] = _COUNTRY_TO_CULTURE[country]
                rec["origin"] = ln
                continue
            if _DATEY.search(ln) and "date" not in rec:
                rec["date"] = ln
                continue
            if any(w in low for w in _MATERIAL_WORDS) and "material" not in rec:
                rec["material"] = ln
                continue
        _dm = re.search(r"\bdated\s+(\d{3,4})\b", ttl, re.I)
        if _dm and _dm.group(1) not in rec.get("date", ""):
            rec["date"] = _dm.group(1) + (f" ({rec['date']})" if rec.get("date") else "")
        if rec.get("culture") or rec.get("date"):
            return rec
    return {}


def catalog_urls_from_snippets(stop_title: str, snippets: Iterable[Dict], venue_url: str) -> List[str]:
    """URLs on the venue's own domain whose page title or slug names this stop's work."""
    out: List[str] = []
    for sn in snippets or []:
        if not isinstance(sn, dict):
            continue
        u = str(sn.get("url") or sn.get("link") or "")
        if not u or not host_matches_venue(u, venue_url) or not _RECORD_PATH_RE.search(u):
            continue
        ttl = re.split(r"\s+[|\u2013\u2014\-]\s+", str(sn.get("title") or ""))[0]
        slug = urlparse(u).path.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
        if (ttl and record_names_stop(stop_title, ttl)) or record_names_stop(stop_title, slug):
            if u not in out:
                out.append(u)
    return out


def _slugify(title: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", title or "")
    return "-".join(re.findall(r"[a-z0-9]+", _fold(t)))


def catalog_urls_by_search(stop_title: str, venue_url: str, fetch, serper=None,
                           max_urls: int = 3) -> Tuple[List[str], str]:
    """[LOCAL-864B] Find the venue's own record page for a stop when no retrieved
    snippet carried its URL (the live Asian Art path).  Tries, in order, the
    venue's collection-site search page (``?s=`` / ``/search/<q>``), the title
    slug under the usual record paths, and (when given) one Serper query
    restricted to the venue domain.  ``fetch(url) -> html``.  Returns
    (urls, why) -- ``why`` explains an empty result for the miss log."""
    dom = _domain(venue_url)
    if not dom or not stop_title:
        return [], "no venue url or title"
    bare = re.sub(r"\s*\([^)]*\)", "", stop_title).strip() or stop_title
    from urllib.parse import quote_plus
    hosts = [f"collections.{dom}", dom]
    out: List[str] = []
    tried = 0
    link_re = re.compile(r"""href=["'](https?://[^"'#?\s]+|/[^"'#?\s]+)["']""")
    for h in hosts:
        for tmpl in (f"https://{h}/?s={quote_plus(bare)}", f"https://{h}/search/{quote_plus(bare)}"):
            tried += 1
            html = fetch(tmpl) or ""
            for m in link_re.finditer(html):
                u = m.group(1)
                if u.startswith("/"):
                    u = f"https://{h}{u}"
                if not host_matches_venue(u, venue_url) or not _RECORD_PATH_RE.search(u):
                    continue
                slug = urlparse(u).path.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
                if record_names_stop(stop_title, slug) and u not in out:
                    out.append(u)
            if out:
                return out[:max_urls], ""
    slugs = [x for x in dict.fromkeys([_slugify(bare), _slugify(stop_title.replace("(", " ").replace(")", " "))]) if x]
    for slug in slugs:
        for h in hosts:
            for path in ("collection", "objects", "collections", "art"):
                u = f"https://{h}/{path}/{slug}/"
                tried += 1
                if (fetch(u) or ""):
                    return [u], ""
    if serper:
        try:
            res = serper(f'site:{hosts[0]} "{bare}"') or {}
            for it in res.get("organic", []) or []:
                u = str(it.get("link") or "")
                if u and host_matches_venue(u, venue_url) and _RECORD_PATH_RE.search(u):
                    ttl = re.split(r"\s+[|\u2013\u2014\-]\s+", str(it.get("title") or ""))[0]
                    if record_names_stop(stop_title, ttl) and u not in out:
                        out.append(u)
            if out:
                return out[:max_urls], ""
        except Exception as e:  # noqa: BLE001
            return [], f"serper failed: {e}"
    return [], f"no record page for '{bare}' on {dom} ({tried} lookups)"


# ═══ 3. CATALOG WINS ═════════════════════════════════════════════════════════

_CATALOG_FIELDS = ("date", "culture", "material", "medium", "period", "origin",
                   "accession_number", "credit_line")


def reconcile_with_catalog(search_hit: Dict, catalog: Dict) -> Tuple[Dict, List[str]]:
    """Merge a search hit with the museum's catalog record.  For date, culture,
    material (and the other record fields) the catalog value wins whenever the
    catalog has one.  Returns (merged, [fields where the hit was overridden])."""
    merged = dict(search_hit or {})
    overridden: List[str] = []
    for f in _CATALOG_FIELDS:
        cv = str((catalog or {}).get(f) or "").strip()
        if not cv:
            continue
        hv = str(merged.get(f) or "").strip()
        if hv and _fold(hv) != _fold(cv):
            overridden.append(f)
        merged[f] = cv
    return merged, overridden


_CULTURES = {
    "vietnamese": "vietnam", "chinese": "china", "burmese": "burma myanmar",
    "thai": "thailand", "japanese": "japan", "korean": "korea", "indian": "india",
    "tibetan": "tibet", "khmer": "cambodia", "cambodian": "cambodia",
    "nepalese": "nepal", "nepali": "nepal", "javanese": "java", "indonesian": "indonesia",
    "sri lankan": "sri lanka", "lao": "laos", "persian": "iran", "mongolian": "mongolia",
    "pakistani": "pakistan", "gandharan": "gandhara", "egyptian": "egypt",
    "greek": "greece", "roman": "rome", "italian": "italy", "french": "france",
    "dutch": "netherlands", "flemish": "flanders", "german": "germany",
    "spanish": "spain", "british": "britain england", "english": "england",
}
_DYNASTIES = ("ly", "tran", "le", "nguyen", "tang", "song", "ming", "qing", "yuan", "han",
              "wei", "jin", "sui", "liao", "pagan", "konbaung", "khmer", "gupta", "pala",
              "joseon", "goryeo", "heian", "kamakura", "edo", "ayutthaya", "sukhothai")
_DYN_RE = re.compile(r"\b(" + "|".join(_DYNASTIES) + r")\s+(?:dynasty|period)\b", re.I)
_CENTURY_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
                  "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
                  "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
                  "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
                  "twentieth": 20}
_CENTURY_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)[\s\-]+century\b|\b(" + "|".join(_CENTURY_WORDS) +
    r")[\s\-]+century\b", re.I)
_NATIONAL_TREASURE_RE = re.compile(r"national\s+treasure", re.I)
_STONE_CLAIM_RE = re.compile(
    r"\bblue stone\b|\b(?:solid|single|polished|grey|gray|green|white|dark|pale)\s+stone\b|"
    r"\b(?:carved|cut|hewn)\s+(?:in|from|out of)\s+(?:\w+\s+){0,2}stone\b")
_MEDIUM_STMT_RE = re.compile(
    r"\b(?:the )?(?:medium|material|materials)\s+(?:is|was|here is)\b|\bmade (?:of|from|with|entirely)\b|"
    r"\bcrafted (?:of|from|in|with)\b|\bfashioned (?:of|from|in)\b|\bconstructed (?:of|from)\b")
_MATERIAL_FAMILIES = {
    "stone": ("stone", "sandstone", "limestone", "marble", "schist", "granite", "basalt"),
    "metal": ("bronze", "gilt", "gilded", "gilding", "copper", "brass", "iron"),
    "wood": ("wood", "wooden", "lacquer", "lacquered", "teak"),
    "clay": ("terracotta", "clay", "stucco", "earthenware", "stoneware", "porcelain"),
    "canvas": ("canvas", "oil on canvas"),
}


def _centuries(text: str) -> set:
    out = set()
    for m in _CENTURY_RE.finditer(text or ""):
        out.add(int(m.group(1)) if m.group(1) else _CENTURY_WORDS[m.group(2).lower()])
    return out


def _years(text: str) -> List[int]:
    return [int(y) for y in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", text or "")]


def _catalog_blob(catalog: Dict) -> str:
    return " ".join(str(catalog.get(f) or "") for f in
                    ("date", "culture", "period", "origin", "material", "medium",
                     "snippet", "record_description", "title", "classification"))


def _catalog_centuries(catalog: Dict) -> set:
    cs = _centuries(_catalog_blob(catalog))
    for y in _years(str(catalog.get("date") or catalog.get("period") or "")):
        if y >= 1:
            cs.add((y - 1) // 100 + 1)
    return cs


_OBJECT_REF_RE = re.compile(
    r"(?i)\b(this|the)\s+(?:\w+\s+){0,3}(statue|sculpture|buddha|image|figure|bronze|work|"
    r"piece|object|bodhisattva|head|relief|painting|stele|gilt)\b")


def sentence_contradicts_catalog(sentence: str, catalog: Dict, stop_title: str = "") -> str:
    """Return a reason when the sentence assigns the stop's object a culture,
    dynasty, century or 'national treasure' status the catalog record does not
    support; '' otherwise.  Only applies when the catalog record has the field."""
    if not catalog or not sentence:
        return ""
    low = _fold(sentence)
    blob = _fold(_catalog_blob(catalog))
    cat_culture = _fold(str(catalog.get("culture") or catalog.get("origin") or ""))
    about_object = bool(_OBJECT_REF_RE.search(sentence)) or any(
        t in low for t in distinctive_tokens(stop_title)) or bool(
        re.search(r"\b(here|before you|in front of you|its|it)\b", low))
    if cat_culture or blob.strip():
        for adj, place in _CULTURES.items():
            if re.search(r"\b" + adj + r"\b", low) and adj not in blob and \
                    not any(p in blob for p in place.split()):
                # a culture the record does not mention; only when it is attached
                # to the object ("Vietnamese ... statue", "sculpture from Vietnam"),
                # not a passing art-historical reference ("Indian prototypes")
                attached = re.search(
                    r"\b" + adj + r"\b(?:\s+[a-z\-]+){0,3}\s+(?:statue|sculpture|buddha|image|"
                    r"figure|bronze|work|piece|object|bodhisattva|head|relief|painting|stele)\b",
                    low) or re.search(
                    r"\b(?:statue|sculpture|buddha|image|figure|work|piece)\b[^.]{0,40}\b"
                    r"(?:from|of|in|made in|carved in|cast in)\s+" + "(?:" +
                    "|".join(re.escape(p) for p in place.split()) + r")\b", low)
                if cat_culture and about_object and attached:
                    return f"culture '{adj}' contradicts catalog '{cat_culture[:40]}'"
        for m in _DYN_RE.finditer(sentence):
            if _fold(m.group(0)) not in blob and cat_culture and about_object:
                return f"'{m.group(0)}' not in catalog record"
    cat_c = _catalog_centuries(catalog)
    if cat_c and about_object:
        said = _centuries(sentence)
        if said and not (said & cat_c):
            return f"century {sorted(said)} contradicts catalog {sorted(cat_c)}"
    cat_mat = _fold(str(catalog.get("material") or catalog.get("medium") or ""))
    if cat_mat and _MEDIUM_STMT_RE.search(low):
        ctoks = {w for w in re.findall(r"[a-z]{4,}", cat_mat)} - {"with", "from", "and"}
        stoks = set(re.findall(r"[a-z]{4,}", low))
        # synonyms of a gilt/bronze record
        if ctoks and not (ctoks & stoks) and not (
                ("gilding" in ctoks or "gilt" in ctoks) and ({"gilt", "gilded", "gilding", "gold"} & stoks)):
            return f"material statement shares nothing with catalog '{cat_mat[:40]}'"
    if cat_mat and "stone" not in cat_mat and _STONE_CLAIM_RE.search(low):
        return f"material 'stone' contradicts catalog '{cat_mat[:40]}'"
    if re.search(r"\b(amitabha|amida)\b", low) and not re.search(r"\b(amitabha|amida)\b", blob + " " + _fold(stop_title)):
        return "names Amitabha/Amida; the catalog record does not"
    if cat_mat:
        for fam, words in _MATERIAL_FAMILIES.items():
            hit = next((w for w in words if re.search(r"\b" + w + r"\b", low)), None)
            if not hit:
                continue
            if any(re.search(r"\b" + w + r"\b", cat_mat) for w in words):
                continue
            # the object is said to be made of a material its record does not list
            if re.search(r"\b" + hit + r"(?:'s|’s)?\s+(?:\w+\s+){0,2}(?:sculpture|statue|statues|figure|"
                         r"surface|buddha|image|carving|relief|head|body|work|piece)\b", low) or \
                    re.search(r"\b(?:in|of|from|carved (?:in|from)|made of|choice of)\s+(?:\w+\s+){0,1}" +
                              hit + r"\b", low) and about_object:
                return f"material '{hit}' contradicts catalog '{cat_mat[:40]}'"
    if _NATIONAL_TREASURE_RE.search(sentence) and "national treasure" not in blob \
            and (cat_culture or cat_c):
        return "national-treasure status absent from the catalog record"
    return ""


def _states_catalog_facts(body: str, catalog: Dict) -> bool:
    low = _fold(body)
    cult = _fold(str(catalog.get("culture") or ""))
    date = str(catalog.get("date") or catalog.get("period") or "")
    origin = _fold(str(catalog.get("origin") or ""))
    place_words = set(re.findall(r"[a-z]{4,}", cult + " " + origin)) - {"area", "province", "region"}
    for adj, place in _CULTURES.items():
        if adj in cult:
            place_words |= set(place.split())
    has_c = (not cult) or any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in place_words)
    ys = _years(date)
    has_d = (not date) or any(str(y) in low for y in ys) or bool(_catalog_centuries(catalog) & _centuries(body))
    return has_c and has_d


def catalog_statement(catalog: Dict) -> str:
    cult = str(catalog.get("culture") or catalog.get("origin") or "").strip().rstrip(".")
    date = str(catalog.get("date") or catalog.get("period") or "").strip().rstrip(".")
    mat = str(catalog.get("material") or catalog.get("medium") or "").strip().rstrip(".")
    if not (cult or date):
        return ""
    date = re.sub(r"\s*\((.*)\)\s*$", r", \1", date) if date.count("(") > 1 else date
    bits = ["The museum's catalog records this as"]
    bits.append(f"a {cult} work" if cult else "a work")
    if date:
        _d = date[0].lower() + date[1:] if re.match(r"(?i)(approx|circa|ca\.)", date) else date
        bits.append("dated " + _d)
    s = " ".join(bits)
    if mat:
        s += f", in {mat[0].lower() + mat[1:]}"
    return s + "."


# ═══ 1. UNSOURCED CLAIMS ═════════════════════════════════════════════════════

_DISCLOSED_RE = re.compile(
    r"(?i)\b(it is sometimes (said|claimed|told|reported)|is sometimes said|sometimes said|"
    r"some (sources|accounts|say|claim|tellings)|according to (some|one|tradition|legend|"
    r"local|a tradition)|legend (has it|holds)|is said to|are said to|was said to|"
    r"reportedly|allegedly|unverified|one tradition|traditionally|though (this|it) "
    r"(is|cannot be|can't be)|not (documented|confirmed|verified))\b")


def is_disclosed(sentence: str) -> bool:
    return bool(_DISCLOSED_RE.search(sentence or ""))


_NAME_TOK = r"[A-ZÀ-ÖØ-Þ][a-zà-ÿ]+(?:-[A-ZÀ-ÖØ-Þ]?[a-zà-ÿ]+)*"
_NAME_RE = re.compile(r"\b(" + _NAME_TOK + r"(?:\s+(?:van|von|de|del|di|du|da|bin|ibn)\s+" + _NAME_TOK +
                      r"|(?:\s+" + _NAME_TOK + r"){1,2}))\b")
_SINGLE_NAME_RE = re.compile(r"\b(" + _NAME_TOK + r")\b")
# A named human agent doing something checkable.
_AGENT_CUE_RE = re.compile(
    r"(?i)\b(collector|donor|donat\w+|gave|gift|bequeath\w*|commission\w*|scholar|historian|"
    r"curator|official|dealer|publisher|printer|patron|sponsor\w*|advoca\w+|argued|highlight\w*|"
    r"oversaw|supervis\w+|recogni[sz]\w+|designat\w+|discover\w+|acquired|purchased|sold|"
    r"founded|chose|selected|insisted|credited|restored|authenticated|catalog(?:ed|ued))\b")
_EVENT_CUE_RE = re.compile(
    r"(?i)\b(recogni[sz]ed|designated|declared|discovered|unearthed|acquired|purchased|donated|"
    r"gifted|bequeathed|founded|commissioned|unveiled|named|awarded|registered|listed)\b")
_NOT_PERSON = frozenset("""
The This That These Those In On At Of For And But With Stop Museum Gallery Art Arts Asian
Buddha Buddhist Dynasty Period Century Chinese Vietnamese Burmese Indian Japanese Korean
Tibetan Thai Khmer Hindu Christian French English Dutch Italian German Spanish American
Parisian Greek Roman Gothic Baroque Impressionist Orsay Musee Paris San Francisco New York
Continue Next Previous Coordinates Orientation Address Notice Look Stand Imagine Here There
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday Seine Louvre Lotus Bodhi Ganges
Rue Avenue Boulevard Street Place Quai Pure Land Zen Heart Amitabha Amida Shakyamuni Sakyamuni
Guanyin Avalokiteshvara Maitreya Vairocana Bodhisattva Brahma Shiva Vishnu Krishna Christ Virgin
Mary Saint Holy God Directions Proceed Your Final
National Treasure Government State Ministry Vietnam China Burma Myanmar Japan Korea India
""".split())


# A creation/craft verb attributing a work to a named maker.
_MAKER_VERB = (r"(?:painted|created|made|produced|sculpted|drew|executed|rendered|designed|"
               r"carved|cast|conceived|composed|achieved|captured|painted|printed|etched|"
               r"engraved|worked|used|employed|applied|chose)")
_MAKER_RE = re.compile(
    r"\b(" + _NAME_TOK + r"(?:\s+" + _NAME_TOK + r"){0,2})(?:'s|’s)?\s+(?:" + _MAKER_VERB +
    r"|brushwork|brushstrokes?|brush|technique|palette|style|hand|touch|canvas|canvases|"
    r"paintings?|drawings?|sculptures?|work|works|vision|approach|genius|signature)\b"
    r"|\bby\s+(" + _NAME_TOK + r"(?:\s+" + _NAME_TOK + r"){0,2})\b")
# A different object located at a different named place.
_ELSEWHERE_RE = re.compile(
    r"\b(?:statue|sculpture|image|painting|figure|work|scroll|screen|stele)\s+"
    r"(?:\w+\s+){0,3}(?:at|in|of|from)\s+the\s+(" + _NAME_TOK + r"(?:[\s\-]+" + _NAME_TOK +
    r")*)\s+(?:temple|museum|monastery|shrine|cathedral|church|gallery|palace|collection)\b")


def _depossess(text: str) -> str:
    return re.sub(r"(\w)['’]s\b", r"\1", text or "")


def maker_bound_to_stop(maker: str, stop_title: str, snippets: Iterable[Dict]) -> bool:
    """True when some retrieved snippet ties this maker to THIS stop's work: the
    snippet mentions the maker AND its title is this work (beyond generic words),
    or its text names this work's full title.  A Tate page on Miro's "Head of a
    Catalan Peasant" mentions Miro but is not about "Head of a Buddha"."""
    sur = _fold(_depossess(maker)).split()[-1] if maker.split() else ""
    if len(sur) < 3:
        return True
    bare = _norm_title(re.sub(r"\([^)]*\)", " ", stop_title))
    gloss = re.search(r"\(([^)]{4,})\)", stop_title or "")
    gl = _norm_title(gloss.group(1)) if gloss and not extract_accession(gloss.group(1)) else ""
    for sn in snippets or []:
        if not isinstance(sn, dict):
            continue
        ttl = str(sn.get("title") or "")
        txt = _fold(f"{ttl} {sn.get('snippet') or sn.get('text') or ''}")
        if not re.search(r"\b" + re.escape(sur) + r"\b", txt):
            continue
        head = re.split(r"\s+[|\u2013\u2014\-]\s+", ttl)[0]
        if head and (titles_match(stop_title, head) or record_names_stop(stop_title, head)):
            return True
        ntxt = " ".join(re.findall(r"[a-z0-9]+", txt))
        if (bare and len(bare) >= 8 and bare in ntxt) or (gl and len(gl) >= 8 and gl in ntxt):
            return True
    return False


def foreign_makers(sentence: str, own: str, stop_artist: str = "") -> List[str]:
    """Named makers a sentence credits with a work, who are not this stop's maker
    and appear nowhere in this venue's own record/evidence for the stop."""
    out = []
    sa = _fold(stop_artist)
    sentence = _depossess(sentence)
    for m in _MAKER_RE.finditer(sentence):
        name = (m.group(1) or m.group(2) or "").strip()
        toks = [t for t in name.split() if t not in _NOT_PERSON]
        if not toks:
            continue
        name = " ".join(toks)
        sur = _fold(toks[-1])
        if len(sur) < 3 or (sa and sur in sa) or sur in own:
            continue
        out.append(name)
    return out


def _evidence_blob(evidence: Iterable[str]) -> str:
    return _fold(" \n ".join(e for e in evidence if e))


def _strip_poss(name: str) -> str:
    return re.sub(r"['’]s?$", "", name)


def _candidate_names(sentence: str) -> List[str]:
    """Person-like names in a sentence that is making an agent/event claim."""
    if not _AGENT_CUE_RE.search(sentence):
        return []
    sentence = re.sub(r"(\w)['’]s\b", r"\1", sentence)
    names: List[str] = []
    for m in _NAME_RE.finditer(sentence):
        toks = m.group(1).split()
        toks = [t for t in toks if t not in _NOT_PERSON]
        if len(toks) >= 2:
            names.append(" ".join(toks))
    # lone surname used as an official: "Nguyen, the cultural official ..."
    for m in re.finditer(r"\b(" + _NAME_TOK + r")\s*,\s+(?:the|a|an)\s+(?:\w+\s+){0,3}"
                         r"(?:official|scholar|historian|curator|collector|dealer|"
                         r"expert|archaeologist|director)\b", sentence):
        if m.group(1) not in _NOT_PERSON:
            names.append(m.group(1))
    for m in re.finditer(r"\b(official|scholar|historian|curator|collector|dealer|expert|"
                         r"archaeologist)\s+(" + _NAME_TOK + r")\b", sentence):
        if m.group(2) not in _NOT_PERSON:
            names.append(m.group(2))
    return names


def _name_sourced(name: str, blob: str, known: Iterable[str]) -> bool:
    n = _fold(name)
    if n in blob:
        return True
    for k in known:
        if k and n in _fold(k):
            return True
    return False


_PRONOUN_OPEN_RE = re.compile(
    r"(?i)^\s*(?:(?:he|she|his|her|they|their)\b|this (?:recognition|donation|gift|designation|"
    r"discovery|acquisition|decision|commission|episode)\b|these (?:editions|prints|donations)\b|"
    r"the (?:consequence|result|outcome) (?:was|of)\b|such a process\b|"
    r"this (?:angle|vantage(?: point)?|position|view|spot|pairing|juxtaposition|contrast)\b|"
    r"(?:the|both|these) two (?:statues|works|figures|sculptures|paintings|pieces)\b|"
    r"the (?:contrast|pairing|juxtaposition) (?:of|between)\b)")


# A capitalised multi-word title: "Head of a Catalan Peasant", "Bacchante in a Landscape".
_WORK_TITLE_RE = re.compile(
    r"\b[A-Z][a-z]+(?:\s+(?:of|in|a|an|the|on|with|and|de|du|la|le)\b|\s+[A-Z][a-z]+){2,8}")

# The work is said to be held by ANOTHER institution.
_INST = r"(?:Museum|Gallery|Galleria|Musée|Museo|Collection|Institute|Library|Rijksmuseum|Louvre|Hermitage|Prado|Uffizi)"
_HELD_ELSEWHERE_RE = re.compile(
    r"\b((?:The\s+)?(?:" + _NAME_TOK + r"\s+){0,4}" + _INST + r"(?:\s+of\s+(?:" + _NAME_TOK + r"\s*){1,3})?)"
    r"(?:\s+in\s+" + _NAME_TOK + r"(?:\s+" + _NAME_TOK + r")?)?\s+(?:now\s+|today\s+)?"
    r"(?:holds|owns|houses|acquired|bought|keeps|displays)\s+(?:this|the)\b"
    r"|\b(?:[Tt]his|[Tt]he)\s+(?:painting|work|piece|statue|sculpture|canvas)\s+(?:is|was)\s+(?:now\s+)?"
    r"(?:held|housed|kept|displayed|owned)\s+(?:at|in|by)\s+([Tt]he\s+(?:" + _NAME_TOK + r"\s+){0,4}" + _INST + r"[^,.;]*)")

# A back-reference to a just-removed comparison, anywhere in the sentence.
_BACKREF_ANY_RE = re.compile(r"(?i)\b(this pairing|this juxtaposition|both statues|the two statues|"
                             r"both works|the two works|the other statue|the other work)\b")

# "<Other Institution> ... integrated the piece into their collection"
_COLLECTION_OF_RE = re.compile(
    r"\b((?:The\s+)?(?:" + _NAME_TOK + r"\s+){1,5}" + _INST + r"(?:\s+of\s+(?:" + _NAME_TOK + r"\s*){1,3})?)"
    r"[^.;]{0,80}\b(?:the piece|this piece|the work|this work|the painting|this painting|it)\b"
    r"[^.;]{0,60}\b(?:their|its) (?:collection|holdings)\b")

_STRUCTURAL_RE = re.compile(r"(?i)^\s*(directions|continue to|coordinates|address|your final stop|"
                            r"next stop|proceed to)\b")


# ═══ 4. LOCAL-864B: ARTIST LEXICON, FUZZY FLAGGED SPANS, INSTITUTIONAL DATES ═══

# Surnames of artists that a model reaches for from its own memory (the Corot /
# Miro bleed).  A sentence naming one is kept only when the stop's own maker,
# catalog, venue pages or a snippet bound to THIS work sources the name.
ARTIST_LEXICON = frozenset("""
corot miro picasso monet manet degas renoir cezanne gogh gauguin matisse rembrandt
vermeer dali klee kandinsky mondrian rodin courbet millet seurat signac pissarro
sisley lautrec delacroix ingres turner constable goya velazquez titian raphael
leonardo michelangelo caravaggio rubens durer holbein cranach bruegel brueghel hals
whistler sargent hopper pollock warhol rothko cassatt morisot bonnard vuillard
daumier gericault chagall modigliani braque leger duchamp magritte ernst munch
klimt schiele hokusai hiroshige utamaro tintoretto veronese botticelli
giotto fragonard watteau boucher chardin poussin lorrain canaletto gainsborough
reynolds blake hockney lichtenstein basquiat kahlo rivera cranach vigee
""".split())
_LEX_RE = re.compile(r"\b([A-ZÀ-ÖØ-Þ][a-zà-ÿ]+(?:-[A-ZÀ-ÖØ-Þ]?[a-zà-ÿ]+)*)(?:['’]s)?\b")


def lexicon_artists(sentence: str) -> List[str]:
    """Famous-artist surnames named in a sentence (folded, de-duplicated)."""
    out: List[str] = []
    for m in _LEX_RE.finditer(sentence or ""):
        f = _fold(m.group(1))
        parts = [f] + (f.split("-") if "-" in f else [])
        for w in parts:
            if w in ARTIST_LEXICON and w not in out:
                out.append(w)
    return out


def artist_allowed(surname: str, stop_title: str, allow_blob: str,
                   stop_snippets: Optional[Sequence[Dict]]) -> bool:
    """True when the stop's own record sources this artist, or a snippet about
    THIS work names him."""
    if re.search(r"\b" + re.escape(surname) + r"\b", allow_blob):
        return True
    if stop_snippets and maker_bound_to_stop(surname.capitalize(), stop_title, stop_snippets):
        return True
    return False


_INSTITUTIONAL_DATE_RE = re.compile(
    r"(?i)\b(?:since|from|in|by)\s+(?:(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+)?(1[89]\d{2}|20[0-2]\d)\b")
_INSTITUTIONAL_CUE_RE = re.compile(
    r"(?i)\b(mission|expanded|expansion|renovat\w+|reopen\w*|rebrand\w*|"
    r"(?:museum|institution)['’]s (?:new|expanded|current)|launched|inaugurat\w+)\b")


# identities that leaked across stops in the live Asian Art runs (the Vietnamese
# Phat Tich Amitabha, the Byodo-in comparison)
_LEAK_RE = re.compile(r"\bbyodo[\s\-]?in\b|\bphat tich\b|\bly (?:court|dynasty|kings?|rulers?|emperors?|period)\b|\bvietnamese state\b")
_RECOGNITION_RE = re.compile(
    r"(?i)\b(?:state|government|ministry|nation)['’]?s?\s+(?:recogni|designat|declar)|"
    r"\brecogni[sz]\w*\s+(?:of|as)\b[^.]{0,40}\b(?:cultural|national|heritage|treasure)\b")


def _span_hit(span: str, sentence: str) -> bool:
    """A flagged claim span is (nearly) in the sentence: contained, or most of
    its content words are (the verifier quotes a paraphrase)."""
    sf, lf = _fold(span), _fold(sentence)
    if sf and sf in lf:
        return True
    toks = [w for w in re.findall(r"[a-z0-9]+", sf)
            if (len(w) >= 4 or w.isdigit()) and w not in _STOPWORDS]
    if len(toks) < 3:
        return False
    sw = set(re.findall(r"[a-z0-9]+", lf))
    return sum(1 for w in toks if w in sw) >= max(3, int(0.7 * len(toks) + 0.999))


def unsourced_sentences(sentences: Sequence[str], evidence: Iterable[str],
                        known: Iterable[str] = (), flagged: Iterable[str] = (),
                        catalog: Optional[Dict] = None, stop_title: str = "",
                        foreign: Iterable[str] = (), own_evidence: Iterable[str] = (),
                        stop_artist: str = "", venue_name: str = "",
                        stop_makers: Iterable[str] = (),
                        stop_snippets: Optional[Sequence[Dict]] = None) -> Dict[int, str]:
    """Return {sentence_index: reason} for sentences that must not ship.

    `stop_makers` are the maker(s) THIS venue's own collection record gives for
    the stop (SPARQL creator, catalog).  When known, a sentence crediting the work
    to anyone else is another work's narration, whatever a search hit says.

    `evidence` is everything retrieved for the stop; `own_evidence` is what THIS
    venue says about the work (its catalog record, its own pages).  A maker or a
    located-elsewhere object is checked against `own_evidence` + `known` only —
    a search hit about another museum's work does not make that work this stop's."""
    evid = list(evidence)
    blob = _evidence_blob(evid)
    # the museum's own record is a source too (its credit line names the donor)
    known = [k for k in known if k] + [str(v) for v in (catalog or {}).values() if v]
    drop: Dict[int, str] = {}

    # entities the upstream verifier flagged UNSOURCED -> every sentence naming them
    flagged_names: List[str] = []
    flagged_surnames: List[str] = []
    flagged_spans = [f for f in flagged if f and f.strip()]
    for f in flagged_spans:
        for m in _NAME_RE.finditer(f):
            toks = [t for t in m.group(1).split() if t not in _NOT_PERSON]
            if len(toks) >= 2 and not _name_sourced(" ".join(toks), blob, known):
                flagged_names.append(" ".join(toks))
                if len(_fold(toks[-1])) >= 3:
                    flagged_surnames.append(_fold(toks[-1]))
    foreign_l = [_fold(x) for x in foreign
                 if x and len(x) > 3 and distinctive_tokens(x)
                 and not (_venue_host_tokens(venue_name) and
                          distinctive_tokens(x) <= _venue_host_tokens(venue_name) | {"asian", "art"})]
    makers = [m for m in stop_makers if m and m.strip()]
    if makers:
        own = _fold(" ".join(makers + [stop_title, _catalog_blob(catalog or {})]))
    else:
        own = _fold(" ".join(list(own_evidence) + list(known) + [_catalog_blob(catalog or {})]))
    vtoks = _venue_host_tokens(venue_name)
    allow_blob = _fold(" ".join(
        [str(m) for m in makers] + [stop_title, stop_artist, _catalog_blob(catalog or {})]
        + [str(x) for x in own_evidence] + [str(k) for k in known]))

    for i, s in enumerate(sentences):
        if is_disclosed(s) or _STRUCTURAL_RE.match(s):
            continue
        low = _fold(s)
        fm = foreign_makers(s, own if (makers or stop_snippets is None) else "", stop_artist)
        if fm and not makers and stop_snippets is not None:
            # no venue record of the maker: keep a maker only if a snippet binds
            # him to THIS work; evidence that merely mentions him is not enough
            fm = [m for m in foreign_makers(s, "", stop_artist)
                  if not maker_bound_to_stop(m, stop_title, stop_snippets)]
        if fm:
            drop[i] = f"credits a work to '{fm[0]}', who is not in this venue's record for the stop"
            foreign_l.append(_fold(fm[0].split()[-1]))
            # the other work's own title goes with its maker ("Head of a Catalan Peasant")
            for tm in _WORK_TITLE_RE.finditer(_depossess(s)):
                dt = distinctive_tokens(tm.group(0)) - distinctive_tokens(stop_title) - \
                    {_fold(x) for x in fm[0].split()}
                if dt:
                    foreign_l.append(" ".join(sorted(dt, key=lambda w: _fold(tm.group(0)).find(w))))
                    foreign_l.extend(w for w in dt if len(w) >= 6)
            continue
        # identity of THIS object (dynasty, which Buddha): only this venue's own
        # record / the stop title may say it -- a search hit about another
        # museum's work (the Vietnamese Phat Tich Amitabha) does not.
        dm = _DYN_RE.search(s)
        if dm and _fold(dm.group(0)) not in own and _fold(dm.group(1) + " dynasty") not in own \
                and re.search(r"(?i)\b(this|the|its|statue|sculpture|image|buddha|work)\b", s):
            drop[i] = f"'{dm.group(0)}' is not in this venue's record for the stop"
            continue
        lk = _LEAK_RE.search(low)
        if lk and lk.group(0) not in own:
            drop[i] = f"'{lk.group(0)}' is another work's identity, not in this venue's record for the stop"
            continue
        if re.search(r"\b(amitabha|amida)\b", low) and not re.search(r"\b(amitabha|amida)\b", own):
            drop[i] = "names Amitabha/Amida; this venue's record for the stop does not"
            continue
        if "blue stone" in low and "blue stone" not in own:
            # the Vietnamese Phat Tich Amitabha leaking across stops: only this
            # venue's own record may say a work is blue stone
            drop[i] = "material 'blue stone' is not in this venue's record for the stop"
            continue
        lex_bad = [a for a in lexicon_artists(s)
                   if not artist_allowed(a, stop_title, allow_blob, stop_snippets)]
        if lex_bad:
            drop[i] = (f"names '{lex_bad[0].capitalize()}', an artist who is not in this "
                       f"venue's record for the stop (another museum's work)")
            foreign_l.append(lex_bad[0])
            continue
        hm = _HELD_ELSEWHERE_RE.search(s) or _COLLECTION_OF_RE.search(s)
        if hm:
            inst = hm.group(1) or hm.group(2) or ""
            itoks = set(re.findall(r"[a-z]{4,}", _fold(inst))) - _VENUE_NOISE - {"museum", "gallery", "collection"}
            if not (vtoks and itoks and itoks <= vtoks) and not (vtoks and vtoks <= set(re.findall(r"[a-z]{4,}", _fold(inst)))):
                drop[i] = f"says the work is held by '{inst.strip()[:50]}', not this venue"
                continue
        em = _ELSEWHERE_RE.search(s)
        if em and not (vtoks & set(re.findall(r"[a-z]{4,}", _fold(em.group(1))))):
            drop[i] = f"narrates a work at '{em.group(1)}', not this venue"
            continue
        if catalog:
            why = sentence_contradicts_catalog(s, catalog, stop_title)
            if why:
                drop[i] = "CATALOG: " + why
                continue
        if any(f and _span_hit(f, s) for f in flagged_spans):
            drop[i] = "flagged UNSOURCED by the verifier"
            continue
        hit = next((n for n in flagged_names if _fold(n) in low), None)
        if hit:
            drop[i] = f"names '{hit}', flagged UNSOURCED"
            continue
        hit = next((n for n in flagged_surnames if re.search(r"\b" + re.escape(n) + r"\b", low)), None)
        if hit:
            drop[i] = f"names '{hit}' (surname of a person flagged UNSOURCED)"
            continue
        if _RECOGNITION_RE.search(s) and not re.search(r"recogni|designat|treasure", blob):
            drop[i] = "official recognition claim appears in no source for this stop"
            continue
        hit = next((x for x in foreign_l if x in low), None)
        if hit:
            drop[i] = f"narrates '{hit}' from another museum's work"
            continue
        for n in _candidate_names(s):
            if not _name_sourced(n, blob, known):
                drop[i] = f"named agent '{n}' appears in no source for this stop"
                break
        else:
            if _EVENT_CUE_RE.search(s):
                miss = [y for y in re.findall(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", s)
                        if y not in blob and y not in " ".join(known)]
                if miss and (_NATIONAL_TREASURE_RE.search(s) or _AGENT_CUE_RE.search(s)):
                    drop[i] = f"dated event ({miss[0]}) appears in no source for this stop"
            if i not in drop and _INSTITUTIONAL_CUE_RE.search(s):
                dm = _INSTITUTIONAL_DATE_RE.search(s)
                if dm and dm.group(1) not in blob and dm.group(1) not in " ".join(known):
                    drop[i] = f"institutional dated claim ({dm.group(1)}) appears in no source for this stop"

    # a foreign maker found anywhere in the stop removes every mention of him
    foreign_l = [_fold(_depossess(x)) for x in foreign_l]
    for i, s in enumerate(sentences):
        if i in drop or is_disclosed(s) or _STRUCTURAL_RE.match(s):
            continue
        low = _fold(_depossess(s))
        hit = next((x for x in foreign_l if re.search(r"\b" + re.escape(x) + r"\b", low)), None)
        if hit:
            drop[i] = f"narrates '{hit}', another venue's work"

    # dangling references left by a drop go with it
    for i in sorted(list(drop)):
        j = i + 1
        while j < len(sentences) and j not in drop and not is_disclosed(sentences[j]) \
                and (_PRONOUN_OPEN_RE.match(sentences[j]) or _BACKREF_ANY_RE.search(sentences[j])):
            drop[j] = "refers back to a dropped unsourced sentence"
            j += 1
    return drop


def filter_stop_body(body: str, evidence: Iterable[str], known: Iterable[str] = (),
                     flagged: Iterable[str] = (), catalog: Optional[Dict] = None,
                     stop_title: str = "", foreign: Iterable[str] = (),
                     own_evidence: Iterable[str] = (), stop_artist: str = "",
                     venue_name: str = "", stop_makers: Iterable[str] = (),
                     stop_snippets: Optional[Sequence[Dict]] = None
                     ) -> Tuple[str, List[Tuple[str, str]], bool]:
    """Filter one stop body.  Returns (new_body, [(sentence, reason)], injected)."""
    removed: List[Tuple[str, str]] = []
    paras = re.split(r"(\n\s*\n)", body)
    flat: List[Tuple[int, str]] = []  # (para idx, sentence)
    for pi, seg in enumerate(paras):
        if seg.strip() and not re.fullmatch(r"\n\s*\n", seg):
            for s in _sentences(seg):
                flat.append((pi, s))
    drops = unsourced_sentences([s for _, s in flat], evidence, known, flagged,
                                catalog, stop_title, foreign, own_evidence,
                                stop_artist, venue_name, stop_makers, stop_snippets)
    # A stop whose narration was about ANOTHER venue's work: once that work is
    # removed, if nothing left names this stop's own object, what remains is the
    # other work described without its name (Corot's nude under "Landscape of the
    # four seasons").  Replace the narration with the catalog statement or an
    # honest line rather than ship it (D577: never an empty stop).
    _foreign_hit = any(("not in this venue's record" in r or "another venue" in r
                        or "not this venue" in r or "another museum" in r)
                       for r in drops.values())
    if _foreign_hit:
        _t_np = re.sub(r"\s*\([^)]*\)", "", stop_title)
        own_toks = distinctive_tokens(_t_np) | set(
            re.findall(r"[a-z]{5,}", _fold(_catalog_blob(catalog or {}))))
        own_toks -= {"museum", "collection", "work", "image", "asian"} | _venue_host_tokens(venue_name)
        # a generic-only title ("Head of a Buddha") is named by any of its words
        _all_generic = {w for w in _norm_title(stop_title).split()
                        if len(w) >= 4 and w not in _STOPWORDS} if not distinctive_tokens(stop_title) else set()
        narrative = [k for k, (_, s) in enumerate(flat)
                     if k not in drops and not _STRUCTURAL_RE.match(s)]
        _orient_paras = {pi for pi, s0 in flat if re.match(r"\s*Orientation\s*:", s0)}
        about = [k for k in narrative if flat[k][0] not in _orient_paras]
        def _names_own(sent: str) -> bool:
            toks = set(re.findall(r"[a-z0-9]{3,}", _fold(sent)))
            return bool(own_toks & toks) or bool(_all_generic & toks)
        if (own_toks or _all_generic) and stop_title.strip() and not any(
                _names_own(flat[k][1]) for k in about):
            for k in narrative:
                drops[k] = "describes the other venue's work after its name was removed"
            _bare = re.sub(r"\s*\([^)]*\)", "", stop_title).strip()
            fb = catalog_statement(catalog or {}) or (
                f"This is {_bare}"
                f"{', in the ' + venue_name + ' collection' if venue_name else ''}. "
                f"The sources this tour found describe a different work, so we say no more "
                f"about it than that.")
            slot = (about or narrative or [None])[0]
            if slot is not None:
                flat[slot] = (flat[slot][0], fb)
                drops.pop(slot, None)
    kept_by_para: Dict[int, List[str]] = {}
    _first_in_para: Dict[int, str] = {}
    for idx, (pi, s) in enumerate(flat):
        _first_in_para.setdefault(pi, s)
        if idx in drops:
            removed.append((s, drops[idx]))
        else:
            if pi not in kept_by_para:
                lab = re.match(r"\s*(Orientation|Directions)\s*:\s*", _first_in_para[pi])
                if lab and not re.match(r"\s*(Orientation|Directions)\s*:", s):
                    s = lab.group(0) + s
            kept_by_para.setdefault(pi, []).append(s)
    out = []
    for pi, seg in enumerate(paras):
        if pi in kept_by_para:
            out.append(" ".join(kept_by_para[pi]))
        elif seg.strip() and not re.fullmatch(r"\n\s*\n", seg):
            out.append("")  # whole paragraph dropped
        else:
            out.append(seg)
    new_body = re.sub(r"(\n\s*\n){2,}", "\n\n", "".join(out))
    # an Orientation that was wholly dropped is replaced by a minimal true one
    if re.search(r"(?m)^\s*Orientation\s*:", body) and new_body.strip() and \
            not re.search(r"(?m)^\s*Orientation\s*:", new_body) and stop_title.strip():
        _bare = re.sub(r"\s*\([^)]*\)", "", stop_title).strip()
        paras3 = re.split(r"(\n\s*\n)", new_body)
        for k, seg in enumerate(paras3):
            if seg.strip() and not re.match(r"\s*(Address|Coordinates|Type|Specific Examples)\s*:", seg):
                paras3[k] = f"Orientation: Look for {_bare}.\n\n" + seg.lstrip()
                break
        new_body = "".join(paras3)
    injected = False
    if catalog and (catalog.get("culture") or catalog.get("date") or catalog.get("period")) \
            and new_body.strip() and not _states_catalog_facts(new_body, catalog):
        st = catalog_statement(catalog)
        if st:
            paras2 = re.split(r"(\n\s*\n)", new_body)
            for k, seg in enumerate(paras2):
                if seg.strip() and not re.match(r"\s*(Orientation|Coordinates|Address)\s*:", seg):
                    paras2[k] = st + " " + seg.lstrip()
                    break
            else:
                paras2.insert(0, st + "\n\n")
            new_body = "".join(paras2)
            injected = True
    return new_body, removed, injected


def filter_tour_text_claims_keep_tail(tour_text: str, **kw) -> Tuple[str, Dict]:
    """Run the claim gate on everything BEFORE the trailing conclusion / sources
    and re-append the tail untouched (used after the conclusion is rebuilt)."""
    cut = _tail_cut(tour_text)
    head, tail = tour_text[:cut], tour_text[cut:]
    new_head, rep = filter_tour_text_claims(head, **kw)
    if not tail:
        return new_head, rep
    return new_head.rstrip("\n") + "\n\n" + tail.lstrip("\n"), rep


def filter_tour_text_claims(tour_text: str,
                            stop_evidence: Optional[Dict[int, List[str]]] = None,
                            stop_known: Optional[Dict[int, List[str]]] = None,
                            stop_flagged: Optional[Dict[int, List[str]]] = None,
                            stop_catalogs: Optional[Dict[int, Dict]] = None,
                            stop_titles: Optional[Dict[int, str]] = None,
                            stop_own_evidence: Optional[Dict[int, List[str]]] = None,
                            stop_artists: Optional[Dict[int, str]] = None,
                            venue_name: str = "",
                            stop_makers: Optional[Dict[int, List[str]]] = None,
                            stop_snippets: Optional[Dict[int, List[Dict]]] = None
                            ) -> Tuple[str, Dict]:
    """Apply the claim gate to every ``Stop N:`` body of a delivered tour."""
    report = {"stops": 0, "dropped": 0, "injected": 0, "changed": False, "removed": []}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report
    out = [parts[0]]
    i, n = 1, 0
    while i < len(parts):
        header, body = parts[i], (parts[i + 1] if i + 1 < len(parts) else "")
        n += 1
        report["stops"] += 1
        title = (stop_titles or {}).get(n) or re.sub(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*", "", header).strip()
        foreign = []
        for w in rejected_matches_for(title):
            foreign.extend([str(w.get("title") or ""), str(w.get("artist") or "")])
        # Evidence-free stops (no snippets at all) cannot be checked for names; the
        # catalog and foreign-work checks still run.
        evidence = (stop_evidence or {}).get(n, [])
        known = list((stop_known or {}).get(n, [])) + [title]
        new_body, removed, inj = filter_stop_body(
            body, evidence, known, (stop_flagged or {}).get(n, []),
            (stop_catalogs or {}).get(n), title, foreign,
            (stop_own_evidence or {}).get(n, []), (stop_artists or {}).get(n, ""), venue_name,
            (stop_makers or {}).get(n, []),
            (stop_snippets or {}).get(n))
        report["dropped"] += len(removed)
        report["injected"] += int(inj)
        for s, why in removed:
            report["removed"].append({"stop": n, "sentence": s, "reason": why})
        out.extend([header, new_body])
        i += 2
    report["changed"] = bool(report["dropped"] or report["injected"])
    return "".join(out), report


# ═══ 5. LOCAL-864B: EVERY-PATH ARTIST SCRUB (backstop) ═══════════════════════

def _tail_cut(tour_text: str) -> int:
    """Index where the trailing conclusion starts (len(text) when none)."""
    try:
        import tour_conclusion as _tc
        hdrs = list(_tc._STOP_HEADER.finditer(tour_text))
        frm = hdrs[-1].end() if hdrs else 0
        cut = len(tour_text)
        for rx in (_tc._THREAD_OPENER, _tc._COUNT_OPENER):
            m = rx.search(tour_text, frm)
            if m:
                cut = min(cut, m.start())
        m = _tc._SOURCES_LINE.search(tour_text)
        if m:
            cut = min(cut, m.start())
        return cut
    except Exception:
        return len(tour_text)


def _scrub_block(block: str, title: str, allow_blob: str, snippets, venue_name: str,
                 where: str, n: int) -> Tuple[str, List[Dict]]:
    removed: List[Dict] = []
    paras = re.split(r"(\n\s*\n)", block)
    out = []
    for seg in paras:
        if not seg.strip() or re.fullmatch(r"\n\s*\n", seg):
            out.append(seg)
            continue
        label = re.match(r"\s*(Orientation|Directions)\s*:\s*", seg)
        sents = _sentences(seg)
        kept = []
        for sn in sents:
            if _STRUCTURAL_RE.match(sn) or re.match(r"\s*(Coordinates|Address|Type|Specific Examples)\s*:", sn):
                kept.append(sn)
                continue
            bad = [a for a in lexicon_artists(sn) if not artist_allowed(a, title, allow_blob, snippets)]
            if bad:
                removed.append({"stop": n, "where": where, "artist": bad[0].capitalize(),
                                "sentence": sn})
                continue
            kept.append(sn)
        if len(kept) == len(sents):
            out.append(seg)
            continue
        if label and kept and not re.match(r"\s*(Orientation|Directions)\s*:", kept[0]):
            kept[0] = label.group(0) + kept[0]
        if not kept and label and label.group(1) == "Orientation" and title:
            kept = [f"Orientation: This is {re.sub(chr(92) + 's*[(][^)]*[)]', '', title).strip()}."]
        out.append(" ".join(kept))
    return re.sub(r"(\n\s*\n){2,}", "\n\n", "".join(out)), removed


def scrub_artists_tour(tour_text: str, stop_allow: Optional[Dict[int, str]] = None,
                       stop_snippets: Optional[Dict[int, List[Dict]]] = None,
                       stop_titles: Optional[Dict[int, str]] = None,
                       venue_name: str = "") -> Tuple[str, Dict]:
    """Last-word backstop over the WHOLE delivered text (intro, every stop, the
    conclusion): a sentence naming a well-known artist who is neither the stop's
    own maker/catalog nor a sourced comparison is dropped.  The intro and the
    conclusion may name only an artist that a delivered stop (title/body) names.
    ``stop_allow[n]`` is the folded-able text of what sources stop n (artist,
    makers, catalog, the venue's own pages)."""
    rep = {"dropped": 0, "removed": []}
    if not tour_text or not tour_text.strip():
        return tour_text, rep
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, rep
    cut_abs = _tail_cut(tour_text)
    stops = []          # [header, scrubbed main, raw tail]
    n = 0
    i = 1
    while i < len(parts):
        header, body = parts[i], (parts[i + 1] if i + 1 < len(parts) else "")
        n += 1
        title = (stop_titles or {}).get(n) or re.sub(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*", "", header).strip()
        allow = _fold(" ".join([(stop_allow or {}).get(n, ""), title]))
        main, tail = body, ""
        if i + 2 >= len(parts):          # last stop: the conclusion lives in its tail
            k = cut_abs - (len(tour_text) - len(body))
            if 0 <= k < len(body):
                main, tail = body[:k], body[k:]
        main2, r1 = _scrub_block(main, title, allow, (stop_snippets or {}).get(n),
                                 venue_name, "stop", n)
        rep["removed"].extend(r1)
        stops.append([header, main2, tail])
        i += 2
    # what the intro / conclusion may name: the delivered (scrubbed) stops
    deliv_blob = _fold(" ".join(h + " " + m for h, m, _ in stops))
    pre2, r0 = _scrub_block(parts[0], "", deliv_blob, None, venue_name, "intro", 0)
    rep["removed"].extend(r0)
    out = [pre2]
    for h, m, t in stops:
        if t:
            t, r2 = _scrub_block(t, "", deliv_blob, None, venue_name, "conclusion", len(stops))
            rep["removed"].extend(r2)
        out.extend([h, m + t])
    rep["dropped"] = len(rep["removed"])
    return "".join(out), rep
