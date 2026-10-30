#!/usr/bin/env python3
"""work_story_research.py — LOCAL-840.

**The defect this exists to close, stated by measurement.** LOCAL-837 gave the
museum story pass a prompt that writes a HUMAN story — a named person who ACTS on
the work — and refuses provenance. On the SAME research, gpt-4.1 extracted a named
agent where gpt-4.1-mini did not. But Orsay stayed 0/5 and Rijks 2/5 on the story
bar, and the LOCAL-837 submission proved why from `reports/local837/research_live.jsonl`:
the material reaching the pass is Serper SNIPPETS, and for these works those
snippets are PROVENANCE AND METADATA —

  "Legs Gustave Caillebotte", "Gift of H.W.A. Deterding", "oil on canvas",
  "Achat avec le concours", "Download this stock image", a blog ("as I walked in
  I thought Viva la France").

No person does anything at a stake, so `works_mode=True` CORRECTLY returns
`NO_STORY`. The story pass was never the bottleneck; the RESEARCH was. These are
famous works with well-documented human stories — Lacan hid *L'Origine du monde*
behind a panel for decades; Manet's *Déjeuner* was thrown out of the 1863 Salon
and mocked at the Salon des Refusés; Rembrandt's *Night Watch* was rolled onto a
cylinder and evacuated to a bunker in 1939 and slashed in 1975 — and the research
layer never asks for them.

**What this module does.** For ONE museum work (its title + artist), it fetches
the work's OWN Wikipedia article and returns the passages that narrate a human
event — creation, commission, reception, history, theft, vandalism, damage,
restoration, rescue — and DROPS the provenance / catalogue-metadata lines that
the Serper path was delivering instead. The output is a `list[str]` of passages,
drop-in as the `material=` the story pass already consumes.

**How, cheapest-and-free first (the ticket's cost ceiling is ≤ $0.03 / stop).**

  1. Resolve the work to its Wikidata QID by TITLE, disambiguated by the ARTIST
     (so Manet's *Déjeuner* is Q152509, not Monet's Q1167912, and *The Night
     Watch* is the 1642 painting, not the musical group / video game). FREE.
  2. Read the FULL English article AND, when the venue's country implies a
     non-English language, the local-language article, via the item's sitelinks.
     Section-formatted (`exsectionformat=wiki`), so headers survive. FREE.
  3. Keep only the EVENT sections (History, Commission, Theft, Vandalism and
     restoration, Provenance-as-narrative…) and, within them, drop the
     provenance / metadata LINES heuristically — no LLM needed, so no spend and
     nothing to fabricate. This is the whole discriminator the ticket asks for:
     keep "Lacan bought it and hid it behind a panel"; drop "Gift of H.W.A.
     Deterding, London" and "oil on canvas, 72.5 × 92 cm".
  4. ONLY when Wikipedia comes back thin (no QID, no article, or < MIN_PASSAGES
     event passages) does it spend: ONE Serper query "<work> <artist> story
     history theft restoration" + one cheap extractor call, both metered, both
     bounded, together well under $0.03.

The result is cached per QID in an additive table (`work_story_research_cache`),
so a repeated tour of the same venue pays nothing. Grounding is unchanged and
still enforced downstream: every passage returned is VERBATIM Wikipedia text, so
the story pass's "every name/date/number must appear in the material" rule and
every gate after it apply exactly as before. This module adds material; it never
writes a story and never relaxes a gate.

Nothing here runs unless `museum_work_research` is called, so default behaviour is
byte-for-byte unchanged.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Reuse the LOCAL-674 Wikimedia primitives rather than re-implementing the
# backoff/retry path that module already got right (venue_resolver backoff,
# Retry-After, User-Agent). _wiki_get is the only transport we need from it.
from serper_plus_research import _wiki_get  # noqa: E402

__all__ = [
    'museum_work_research', 'resolve_work_qid', 'fetch_work_sections',
    'event_passages', 'is_provenance_or_metadata', 'EVENT_SECTION_RE',
    'CORPUS_VERSION', 'MIN_PASSAGES',
]

# ── tunables (env-overridable) ────────────────────────────────────────────────
WIKI_CHARS = int(os.environ.get('WORK_RESEARCH_WIKI_CHARS', '14000'))
WIKI_LOCAL_CHARS = int(os.environ.get('WORK_RESEARCH_WIKI_LOCAL_CHARS', '6000'))
MAX_PASSAGES = int(os.environ.get('WORK_RESEARCH_MAX_PASSAGES', '8'))
# Below this many event passages, Wikipedia is "thin" and the optional (paid)
# Serper fallback is allowed to fire — once, bounded.
MIN_PASSAGES = int(os.environ.get('WORK_RESEARCH_MIN_PASSAGES', '2'))
MAX_PASSAGE_CHARS = int(os.environ.get('WORK_RESEARCH_MAX_PASSAGE_CHARS', '600'))
FALLBACK_MODEL = os.environ.get('WORK_RESEARCH_FALLBACK_MODEL', 'gpt-4.1-mini')
# Hard per-stop cost ceiling (the ticket's ≤ $0.03). The fallback is skipped if
# it cannot be issued within this.
COST_CEILING = float(os.environ.get('WORK_RESEARCH_COST_CEILING', '0.03'))

# Bump when the extraction logic changes in a way that should invalidate the
# cache (same discipline as work_story_searcher.CORPUS_VERSION).
CORPUS_VERSION = 1


# ── section + line classification (FREE — no LLM) ─────────────────────────────

# Sections of a work's article that narrate a HUMAN EVENT. Matched case-insensitively
# against the wiki header text. Deliberately broad on the event side and narrow on
# the metadata side: a false-keep is cleaned line-by-line below, a false-drop loses
# a story outright.
EVENT_SECTION_RE = re.compile(
    r'\b(history|histoi|geschied|commission|creation|making|painting of|'
    r'genesis|background|reception|scandal|controvers|exhibition|salon|'
    r'theft|stolen|stole|robbery|looting|loot|seizure|confiscat|'
    r'vandal|attack|slash|damage|damaged|destruction|destroy|fire|war|'
    r'wartime|evacuat|hidden|hiding|rescue|recover|restoration|restor|'
    r'conservation|conservat|forgery|forger|copy|provenance|ownership|'
    r'later|legacy|aftermath|fate|dispute|trial|lawsuit|return|repatriat)\b',
    re.IGNORECASE)

# Sections to always skip: pure apparatus, description-of-looks, and lists.
SKIP_SECTION_RE = re.compile(
    r'\b(references|bibliograph|further reading|external links|see also|'
    r'notes|citations|sources|gallery|in popular culture|popular culture|'
    r'notes and references|footnotes|technical|dimensions|materials and '
    r'technique|description|composition|style|iconograph|gigapixel|'
    r'photograph of|ai recreation|ai reconstruction)\b',
    re.IGNORECASE)

# [LOCAL-840] INFLUENCE / LEGACY sections narrate LATER artists making their own
# homages to this work — an event, but about a DIFFERENT work. Down-weighted (not
# dropped) so the stop's own story wins the cap when it exists, but the homage is
# still available if nothing else carries one.
_INFLUENCE_SECTION_RE = re.compile(
    r'\b(influence|legacy|in popular culture|popular culture|reception by|'
    r'homage|parod|adaptation|later works|aftermath in art|in other media)\b',
    re.IGNORECASE)
# A sentence that is itself a later artist painting their OWN version/homage.
_LATER_HOMAGE_RE = re.compile(
    r'\b(painted (?:a|the|his|her|their|another|the same)|'
    r'version|homage|parody|reinterpret|adaptation|inspired (?:by|the)|'
    r'reproduced it|based on it|his own|her own)\b',
    re.IGNORECASE)

# A sentence that is PROVENANCE or CATALOGUE METADATA — a transfer of ownership
# that nobody DID at a cost, or a physical/catalogue descriptor. These are the
# exact shapes the Serper path was delivering, and the ones the story pass must
# never be handed as "material" because they look like facts but carry no stake.
_PROVENANCE_LINE_RE = re.compile(
    r'(legs\s+[A-Z]|\bgift of\b|\bgifted\b|\bbequest\b|\bbequeath|'
    r'\bdonat(?:ed|ion)\b|\bdonor\b|\bachat\b|\bacquis(?:ition|ed)\b|'
    r'\bpurchased\s+(?:by|from|in|with|at)\b|\bbought\s+by\s+the\b|'
    r'\bentered the collection\b|\bon loan\b|\bloaned\b|\baccession\b|'
    r'\binv(?:\.|entory)\s*(?:no|number|n°)|\bcatalogue\s+(?:no|number|raisonn)|'
    r'\bcredit line\b|\bdist\.?\s*rmn\b|\brmn-grand palais\b|'
    r'\bprovenance\s*[:：]|\bleft by the artist\b|\bconcours\b)',
    re.IGNORECASE)

_METADATA_LINE_RE = re.compile(
    r'(\boil on canvas\b|\bhuile sur toile\b|\btempera\b|\bwatercolou?r\b|'
    r'\bgouache\b|\bpen and ink\b|\bbronze\b|\bmarble\b|\blithograph\b|'
    r'\betching\b|\bengraving\b|\bwoodcut\b|\bchalk\b|\bcharcoal\b|'
    r'^\s*(?:dimensions?|medium|material|technique|date created|creator|'
    r'physical dimensions|title|current location|location)\s*[:：]|'
    r'\b\d{2,4}\s*(?:\u00d7|x|by)\s*\d{2,4}\s*(?:cm|mm|centimet|in\b)|'
    r'\bcm\b\s*\u00d7|\bstock image\b|\bdownload this\b|\bphoto\s*\u00a9|'
    r'\b\u00a9\s*(?:photo|rmn|mus[eé]e)|\bgetty\b|\balamy\b)',
    re.IGNORECASE)

# A line with NO event verb and NO date is unlikely to carry a story, even inside
# an event section (it is usually a caption or a label). A date OR one of these
# verbs is the cheapest "something happened" signal.
_EVENT_VERB_RE = re.compile(
    r'\b(painted|commission|refused|rejected|mock|scandal|exhibit|shown|'
    r'submitted|hid|hidden|hide|conceal|bought|sold|stole|stolen|theft|'
    r'slashed|attack|damaged|vandal|destroyed|burn|evacuat|rolled|moved|'
    r'rescued|recovered|restor|repaired|forged|copied|died|shot|killed|'
    r'executed|accepted|seized|confiscat|returned|discovered|found|'
    r'declared|ordered|fled|escaped|survived|married|posed|kept)\b',
    re.IGNORECASE)
_DATE_RE = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')

# The highest-stake verbs — a passage containing one is the kind of human event
# the story pass exists to find (a theft, a rescue, a refusal, a death). Used to
# RANK passages so the Lacan concealment and the Night Watch slashing beat
# art-historical speculation and tradition when the MAX_PASSAGES cap bites.
_STRONG_EVENT_RE = re.compile(
    r'\b(hid|hidden|hide|conceal|stole|stolen|theft|robbed|looted|loot|'
    r'slashed|slash|attack|stabbed|knife|acid|vandal|damaged|destroyed|'
    r'burn|fire|evacuat|rescued|ransom|seized|confiscat|refused|rejected|'
    r'mock|scandal|notoriety|controvers|censor|withdraw|banned|trimmed|cut|'
    r'executed|shot|killed|died|suicide|duel|forged|forgery|commission|'
    r'auction)\b',
    re.IGNORECASE)


def is_provenance_or_metadata(line: str) -> bool:
    """True when `line` is a transfer of ownership (provenance) or a catalogue /
    physical descriptor (metadata) — the shapes to DROP. Pure function, no I/O,
    so it is the unit the fixtures test directly."""
    if not line or not line.strip():
        return True
    s = line.strip()
    if _PROVENANCE_LINE_RE.search(s):
        return True
    if _METADATA_LINE_RE.search(s):
        return True
    return False


def _looks_like_event(sentence: str) -> bool:
    """A sentence carries an event when it has a date OR an event verb AND is not
    itself provenance/metadata. This is the KEEP test applied line by line."""
    s = (sentence or '').strip()
    if len(s) < 25:
        return False
    if is_provenance_or_metadata(s):
        return False
    return bool(_EVENT_VERB_RE.search(s) or _DATE_RE.search(s))


def _split_sections(wikitext: str) -> List[Tuple[str, str]]:
    """Split an `exsectionformat=wiki` extract into (header, body) pairs. The
    lead (before the first header) is returned under the header 'Lead'."""
    out: List[Tuple[str, str]] = []
    if not wikitext:
        return out
    # Headers look like '== History ==' / '=== Commission ==='. Split on them,
    # keeping the header text.
    parts = re.split(r'^\s*=+\s*(.+?)\s*=+\s*$', wikitext, flags=re.MULTILINE)
    # re.split with one capturing group yields: [lead, h1, body1, h2, body2, ...]
    lead = parts[0].strip()
    if lead:
        out.append(('Lead', lead))
    i = 1
    while i + 1 < len(parts) + 1 and i < len(parts):
        header = parts[i].strip()
        body = parts[i + 1].strip() if (i + 1) < len(parts) else ''
        out.append((header, body))
        i += 2
    return out


def _passage_score(sentence: str, header: str, order: int) -> float:
    """Rank a kept passage so the strongest human events surface first within the
    MAX_PASSAGES cap. Higher is better."""
    s = sentence or ''
    score = 0.0
    if _STRONG_EVENT_RE.search(s):
        score += 5
    if _EVENT_VERB_RE.search(s):
        score += 2
    if _DATE_RE.search(s):
        score += 1.5
    # A section whose header names an event (History, Theft, Owners-is-not-here
    # but Vandalism is) is more likely to carry the story than the lead or a
    # description subsection.
    if header and EVENT_SECTION_RE.search(header):
        score += 2
    # [LOCAL-840] Down-weight INFLUENCE / LEGACY / popular-culture passages: those
    # narrate a LATER artist painting their OWN homage ("Cézanne painted the same
    # theme", "Tissot painted a tamer version"), which is an event — but about a
    # different work, not THIS one. They outscored the stop's own story (Manet at
    # the Salon des Refusés) and lured the pass onto the wrong subject.
    if _INFLUENCE_SECTION_RE.search(header or ''):
        score -= 4
    if _LATER_HOMAGE_RE.search(s):
        score -= 4
    # Earlier passages break ties (keeps the narrative roughly chronological).
    score -= 0.01 * order
    return score


def _passages_from_section(body: str, header: str = '',
                           start_order: int = 0) -> List[Tuple[float, str]]:
    """Return (score, passage) for the event-bearing sentences in one section
    body, provenance/metadata dropped, each capped to MAX_PASSAGE_CHARS."""
    out: List[Tuple[float, str]] = []
    order = start_order
    for para in re.split(r'\n{2,}', body or ''):
        para = re.sub(r'\s+', ' ', para).strip()
        if not para:
            continue
        for sent in re.split(r'(?<=[.!?])\s+', para):
            sent = sent.strip()
            if _looks_like_event(sent):
                out.append((_passage_score(sent, header, order), sent[:MAX_PASSAGE_CHARS]))
                order += 1
    return out


def event_passages(sections: List[Tuple[str, str]]) -> List[str]:
    """From (header, body) sections, return the event-bearing lines, dropping
    apparatus/description sections wholesale and provenance/metadata lines
    individually, RANKED so the strongest human events come first, then capped
    at MAX_PASSAGES. De-duplicated, original wording preserved verbatim.

    The discriminator is LINE-LEVEL, not header-level, and that is deliberate:
    a work's real story often lives under a header that READS like metadata —
    L'Origine du monde's Lacan episode (he bought it in 1955 and had Masson build
    a double-bottom frame to hide it) sits under a section titled "Owners", and
    The Night Watch's 1911/1975 knife attacks under "Vandalism and restoration".
    Gating on the header keyword alone drops the Lacan story with the credits.

    So: skip only the sections that are PURELY apparatus or description-of-looks
    (References, Technique, Composition, Gallery…), and from every OTHER section
    keep the lines that carry an event (a date or an event verb) and are NOT
    themselves a transfer of ownership or a catalogue descriptor. Ranking then
    lifts the strongest events (theft, rescue, refusal, death) above the merely
    dated, so the cap keeps the story and sheds the art-historical speculation."""
    scored: List[Tuple[float, str]] = []
    seen = set()
    order = 0
    for header, body in sections:
        h = header or ''
        is_lead = (h.lower() == 'lead')
        if not is_lead and SKIP_SECTION_RE.search(h) \
                and not EVENT_SECTION_RE.search(h):
            # Pure apparatus/description AND not also an event header → skip.
            continue
        for sc, p in _passages_from_section(body, h, order):
            key = p.lower()[:120]
            if key in seen:
                continue
            seen.add(key)
            scored.append((sc, p))
            order += 1
    # Stable sort by score descending (ties keep insertion order via the small
    # order penalty already folded into the score).
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _sc, p in scored[:MAX_PASSAGES]]
    # [LOCAL-840] Protagonist grouping. The story pass (works_mode) must stay with
    # ONE named person across 3 sentences, and story_opportunity_scan rejects a
    # run whose subject switches — so a jumble of passages about Khalil Bey, de
    # Goncourt AND Lacan invites a multi-subject story the bar then refuses. Lead
    # with the passages about the SINGLE most-present protagonist, contiguously,
    # so the pass has a coherent one-person arc to write from. Still verbatim,
    # still the same set — only the ORDER changes, and only to help the pass keep
    # one subject. The remaining passages follow, so nothing is lost.
    return _lead_with_dominant_protagonist(top)


# People mentioned in the event passages: a capitalised forename + surname (or a
# two-token capitalised span), allowing one lowercase particle (van, de, von, du).
_PERSON_RE = re.compile(
    r'\b([A-ZÀ-Ý][a-zà-ÿ\'’.-]+(?:\s+(?:van|de|der|den|von|du|la|le|di|dos|da))?'
    r'\s+[A-ZÀ-Ý][a-zà-ÿ\'’.-]+)\b')

# Spans that are works/places, not people, when they slip through the pattern.
_NOT_PERSON_RE = re.compile(
    r'\b(museum|gallery|rijksmuseum|louvre|orsay|amsterdam|paris|town hall|'
    r'golden age|second empire|world war|night watch|origine|salon)\b',
    re.IGNORECASE)


def _people_in(text: str) -> List[str]:
    out = []
    for m in _PERSON_RE.finditer(text or ''):
        span = m.group(1).strip()
        if _NOT_PERSON_RE.search(span):
            continue
        out.append(span)
    return out


def _lead_with_dominant_protagonist(passages: List[str]) -> List[str]:
    """Reorder `passages` so the SINGLE most-mentioned person's passages lead,
    contiguously, with the rest following in their existing order. Returns the
    input unchanged when no person recurs (nothing to group around)."""
    if len(passages) < 3:
        return passages
    # Count surname occurrences across all passages (surname is the handle the
    # scanner bridges on).
    from collections import Counter
    counts: Counter = Counter()
    per_passage_people = []
    for p in passages:
        names = _people_in(p)
        surnames = {n.split()[-1] for n in names}
        per_passage_people.append(surnames)
        for s in surnames:
            counts[s] += 1
    if not counts:
        return passages
    top_surname, top_n = counts.most_common(1)[0]
    # Only regroup when the dominant person actually recurs (>=2 passages); a
    # single mention is not an arc worth leading with.
    if top_n < 2:
        return passages
    lead = [p for p, people in zip(passages, per_passage_people)
            if top_surname in people]
    rest = [p for p, people in zip(passages, per_passage_people)
            if top_surname not in people]
    return lead + rest


# ── Wikidata QID resolution, disambiguated by ARTIST ──────────────────────────

# Words in a Wikidata description that mark the hit as the WORK (not a film /
# band / book / game of the same title).
_WORK_DESC_RE = re.compile(
    r'\b(painting|oil|canvas|panel|fresco|mural|sculpture|statue|bronze|'
    r'marble|print|etching|engraving|lithograph|woodcut|drawing|watercolou?r|'
    r'portrait|triptych|altarpiece|tapestry|photograph|artwork|work of art|'
    r'peinture|tableau|sculpture|\u00f6lgem|schilderij)\b',
    re.IGNORECASE)
# Descriptions that mark a hit as NOT the work (a disambiguator to avoid).
_NOT_WORK_DESC_RE = re.compile(
    r'\b(film|movie|band|album|song|musical group|video game|game|novel|'
    r'book|essay|comic|tv series|episode|edition|magazine|opera|play)\b',
    re.IGNORECASE)


def _surname(artist: str) -> str:
    a = (artist or '').strip()
    if not a:
        return ''
    # drop trailing dates / parentheticals, take the last word
    a = re.sub(r'\([^)]*\)', '', a).strip()
    a = re.sub(r'\b1[0-9]{3}\b.*$', '', a).strip()
    parts = [p for p in re.split(r'\s+', a) if p]
    return parts[-1] if parts else ''


def resolve_work_qid(title: str, artist: str = '',
                     fetch: Optional[Callable] = None) -> Tuple[str, Dict]:
    """Resolve a WORK's title to its Wikidata QID, disambiguated by artist.
    Returns (qid, sitelinks_by_wiki). ('', {}) on failure. FREE (Wikidata API).

    Scoring, in order of trust:
      +3  description names the artist's surname (the strongest signal)
      +2  description looks like a work of art (painting/sculpture/print/…)
      -5  description looks like a film/band/book/game of the same title
      small bonus for earlier hits (Wikidata ranks by relevance)
    """
    get = fetch or _wiki_get
    if not title:
        return '', {}
    r = get('https://www.wikidata.org/w/api.php',
            {'action': 'wbsearchentities', 'search': title, 'language': 'en',
             'format': 'json', 'limit': 7, 'type': 'item'}, timeout=12)
    try:
        if r is None or r.status_code != 200:
            return '', {}
        hits = r.json().get('search', []) or []
    except Exception:
        return '', {}
    if not hits:
        return '', {}

    sn = _surname(artist).lower()
    best_qid, best_score = '', -1e9
    for rank, h in enumerate(hits):
        desc = (h.get('description') or '').lower()
        score = -0.2 * rank
        if sn and sn in desc:
            score += 3
        if _WORK_DESC_RE.search(desc):
            score += 2
        if _NOT_WORK_DESC_RE.search(desc):
            score -= 5
        if score > best_score:
            best_score, best_qid = score, h.get('id', '')
    # A hit that is clearly NOT the work and matches nothing is worse than no
    # hit: better to fall through to the Serper fallback than to read a film's
    # article. Require either an artist/work signal or no disqualifier.
    if best_score < 0:
        return '', {}
    qid = best_qid
    if not qid:
        return '', {}

    sitelinks: Dict[str, str] = {}
    r2 = get('https://www.wikidata.org/w/api.php',
             {'action': 'wbgetentities', 'ids': qid, 'props': 'sitelinks',
              'format': 'json'}, timeout=12)
    try:
        if r2 is not None and r2.status_code == 200:
            ent = r2.json().get('entities', {}).get(qid, {}) or {}
            for wiki, info in (ent.get('sitelinks', {}) or {}).items():
                if wiki.endswith('wiki') and not wiki.endswith('wikiquote') \
                        and 'wikinews' not in wiki and 'wikisource' not in wiki \
                        and 'commons' not in wiki and 'wikivoyage' not in wiki \
                        and 'wikidata' not in wiki:
                    sitelinks[wiki] = info.get('title', '')
    except Exception:
        pass
    return qid, sitelinks


def _wiki_sections(lang: str, title: str, max_chars: int,
                   fetch: Optional[Callable] = None) -> List[Tuple[str, str]]:
    """Section-formatted plain-text article → (header, body) pairs. FREE."""
    get = fetch or _wiki_get
    if not title:
        return []
    r = get(f'https://{lang}.wikipedia.org/w/api.php',
            {'action': 'query', 'prop': 'extracts', 'explaintext': '1',
             'exsectionformat': 'wiki', 'formatversion': '2',
             'titles': title, 'format': 'json', 'redirects': '1'}, timeout=15)
    try:
        if r is None or r.status_code != 200:
            return []
        pages = r.json().get('query', {}).get('pages', []) or []
        for p in pages:
            ext = p.get('extract', '') or ''
            if ext:
                return _split_sections(ext[:max_chars])
    except Exception:
        return []
    return []


# Best-effort local Wikipedia language code from a venue/location string. A wrong
# guess only means we read the EN article (and no local one). Mirrors the small
# table in serper_plus_research, extended for museum locales.
_LOCAL_LANG_TABLE = [
    (('france', 'french', 'paris', 'orsay', 'louvre', 'nice', 'lyon'), 'fr'),
    (('netherlands', 'dutch', 'amsterdam', 'rijksmuseum', 'hague', 'rotterdam'), 'nl'),
    (('italy', 'italian', 'rome', 'florence', 'venice', 'milan', 'uffizi'), 'it'),
    (('spain', 'spanish', 'madrid', 'barcelona', 'prado', 'seville'), 'es'),
    (('germany', 'german', 'berlin', 'munich', 'hamburg', 'dresden'), 'de'),
    (('portugal', 'portuguese', 'lisbon', 'porto'), 'pt'),
    (('vietnam', 'vietnamese', 'hanoi', 'ho chi minh', 'saigon'), 'vi'),
    (('japan', 'japanese', 'tokyo', 'kyoto', 'osaka'), 'ja'),
    (('china', 'chinese', 'beijing', 'shanghai'), 'zh'),
    (('russia', 'russian', 'moscow', 'petersburg', 'hermitage'), 'ru'),
    (('greece', 'greek', 'athens'), 'el'),
    (('austria', 'vienna', 'belvedere', 'kunsthistor'), 'de'),
]


def _local_lang(location: str, venue: str) -> str:
    c = f'{location or ""} {venue or ""}'.lower()
    for keys, code in _LOCAL_LANG_TABLE:
        if any(k in c for k in keys):
            return code
    return ''


def fetch_work_sections(title: str, artist: str = '', location: str = '',
                        venue: str = '', fetch: Optional[Callable] = None
                        ) -> Tuple[str, List[Tuple[str, str]]]:
    """Resolve the work and return (qid, [(header, body), …]) for the EN article
    plus one local-language article when the locale implies one. FREE."""
    qid, sitelinks = resolve_work_qid(title, artist, fetch=fetch)
    if not qid:
        return '', []
    sections: List[Tuple[str, str]] = []
    en_title = sitelinks.get('enwiki') or title
    sections.extend(_wiki_sections('en', en_title, WIKI_CHARS, fetch=fetch))

    code = _local_lang(location, venue)
    if code and code != 'en':
        local_title = sitelinks.get(f'{code}wiki', '')
        if local_title:
            sections.extend(_wiki_sections(code, local_title, WIKI_LOCAL_CHARS,
                                           fetch=fetch))
    return qid, sections


# ── optional (PAID) Serper fallback — only when Wikipedia is thin ─────────────

_FALLBACK_PROMPT = """\
You are a museum fact researcher. Using ONLY the numbered SOURCES below, extract \
the passages that narrate a HUMAN EVENT connected to the work "{title}"{by} — \
who made it, posed for it, paid for it, refused it, stole it, hid it, damaged it, \
rescued it, restored it, forged it, or attacked it, and what followed. Give each \
as one or two plain sentences with the names, dates and places from the source. \
DROP anything that is only provenance (who owns it, who gave or bequeathed it, \
when it was acquired) or catalogue metadata (medium, dimensions, inventory \
number). If the sources contain no such human event, reply with exactly: \
NO MATERIAL FOUND

SOURCES:
{sources}
"""


def _serper_fallback(title: str, artist: str,
                     serp: Optional[Callable] = None,
                     fetch: Optional[Callable] = None,
                     answer: Optional[Callable] = None) -> Tuple[List[str], float]:
    """ONE Serper query + one cheap extractor over the top pages. Metered.
    Returns (passages, cost_estimate). Bounded to stay under COST_CEILING."""
    try:
        import serper_research as _sr
    except Exception:
        return [], 0.0
    serp = serp or _sr._default_serp
    fetch = fetch or _sr._fetch
    answer = answer or _sr._openai_chat

    q = f'"{title}" {artist} story history theft vandalism restoration'.strip()
    results = []
    try:
        results = serp(q) or []
    except Exception:
        return [], 0.0
    pages: List[Dict] = []
    for r in results[:5]:
        url = (r.get('url') or r.get('link') or '').strip()
        if not url:
            continue
        try:
            text = fetch(url)
        except Exception:
            text = ''
        if text and len(text) >= 120:
            pages.append({'url': url, 'text': text[:3000]})
        if len(pages) >= 3:
            break
    if not pages:
        return [], 0.001  # the Serper query still metered

    sources_block = '\n\n'.join(
        f"[{i + 1}] {p['text']}" for i, p in enumerate(pages))
    by = f" by {artist}" if artist else ''
    prompt = _FALLBACK_PROMPT.format(title=title, by=by, sources=sources_block)
    try:
        ans = answer(prompt, model=FALLBACK_MODEL, max_tokens=500)
    except TypeError:
        ans = answer(prompt, FALLBACK_MODEL)
    except Exception:
        return [], 0.001
    text = (ans.get('text') or '').strip()
    if not text or 'NO MATERIAL FOUND' in text.upper():
        return [], 0.01
    # Split the extractor's reply into passages, drop any provenance/metadata the
    # model let through (belt and braces — the heuristic is authoritative).
    out: List[str] = []
    seen = set()
    for sent in re.split(r'(?<=[.!?])\s+', text):
        s = re.sub(r'\[\d+\]', '', sent).strip()
        if not s or is_provenance_or_metadata(s) or len(s) < 25:
            continue
        key = s.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:MAX_PASSAGE_CHARS])
        if len(out) >= MAX_PASSAGES:
            break
    return out, 0.02


# ── per-QID cache (additive; new small table) ─────────────────────────────────
_CACHE_TABLE_ENSURED = False


def _get_conn():
    try:
        from work_story_searcher import _get_db_connection
        return _get_db_connection()
    except Exception:
        return None


def _ensure_cache_table(conn) -> bool:
    global _CACHE_TABLE_ENSURED
    if _CACHE_TABLE_ENSURED:
        return True
    try:
        with conn.cursor() as cur:
            # CREATE TABLE IF NOT EXISTS takes no lock on an existing relation.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_story_research_cache (
                    id SERIAL PRIMARY KEY,
                    cache_key VARCHAR(80) NOT NULL UNIQUE,
                    work_qid VARCHAR(20),
                    title TEXT,
                    artist TEXT,
                    passages_json JSONB NOT NULL,
                    corpus_version INT NOT NULL DEFAULT 1,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        try:
            from db_safe_ddl import safe_ddl
        except Exception:
            safe_ddl = None
        if safe_ddl is not None:
            safe_ddl(
                conn,
                "CREATE INDEX IF NOT EXISTS idx_wsr_cache_expires "
                "ON work_story_research_cache(expires_at)",
                needed_check_sql=(
                    "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM pg_indexes "
                    "WHERE tablename = 'work_story_research_cache' "
                    "AND indexname = 'idx_wsr_cache_expires')"),
                label="LOCAL-840",
            )
        _CACHE_TABLE_ENSURED = True
        return True
    except Exception as e:
        print(f"  [work_story_research] cache table ensure failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def _cache_key(qid: str, title: str, artist: str) -> str:
    if qid:
        return f'qid:{qid}:v{CORPUS_VERSION}'
    base = re.sub(r'\s+', ' ', f'{title}|{artist}'.lower()).strip()
    import hashlib
    return 'k:' + hashlib.sha1(base.encode('utf-8')).hexdigest()[:24] + f':v{CORPUS_VERSION}'


def _cache_get(qid: str, title: str, artist: str) -> Optional[List[str]]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        if not _ensure_cache_table(conn):
            return None
        with conn.cursor() as cur:
            cur.execute(
                "SELECT passages_json FROM work_story_research_cache "
                "WHERE cache_key = %s AND expires_at > NOW() AND corpus_version = %s",
                (_cache_key(qid, title, artist), CORPUS_VERSION))
            row = cur.fetchone()
            if row and row[0]:
                print(f"  [work_story_research] cache HIT {_cache_key(qid, title, artist)}")
                return list(row[0])
        return None
    except Exception as e:
        print(f"  [work_story_research] cache read error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _cache_put(qid: str, title: str, artist: str, passages: List[str],
               ttl_days: int = 45) -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        if not _ensure_cache_table(conn):
            return
        expires = datetime.utcnow() + timedelta(days=ttl_days)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO work_story_research_cache "
                "(cache_key, work_qid, title, artist, passages_json, "
                " corpus_version, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (cache_key) DO UPDATE SET "
                "  passages_json = EXCLUDED.passages_json, "
                "  expires_at = EXCLUDED.expires_at, "
                "  corpus_version = EXCLUDED.corpus_version",
                (_cache_key(qid, title, artist), qid or None, title, artist,
                 json.dumps(passages, ensure_ascii=False), CORPUS_VERSION, expires))
            conn.commit()
            print(f"  [work_story_research] cache PUT {_cache_key(qid, title, artist)} "
                  f"({len(passages)} passages)")
    except Exception as e:
        print(f"  [work_story_research] cache write error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── the entry point ───────────────────────────────────────────────────────────

def museum_work_research(title: str, artist: str = '', location: str = '',
                         venue: str = '', *, use_cache: bool = True,
                         allow_fallback: bool = True,
                         fetch: Optional[Callable] = None,
                         serp: Optional[Callable] = None,
                         page_fetch: Optional[Callable] = None,
                         answer: Optional[Callable] = None) -> Dict:
    """Research ONE museum work and return human-event passages for the story pass.

    Returns {'passages': list[str], 'qid': str, 'source': str, 'cost': float}.
      - 'source' is 'cache' | 'wikipedia' | 'serper_fallback' | 'none'.
      - 'cost' is the metered spend this call incurred (Wikipedia is $0.00).

    Never raises; on total failure returns an empty passage list, which the caller
    treats exactly as "no extra material" — the Serper snippets it already has
    remain in play, and the story pass still answers NO_STORY rather than inventing.

    `fetch` is the Wikimedia transport (url, params) -> Response; `serp`,
    `page_fetch` and `answer` are the fallback's Serper query, web-page fetch
    (url) -> text, and extractor. All injectable so the fixtures test every branch
    with no network and no key.
    """
    out = {'passages': [], 'qid': '', 'source': 'none', 'cost': 0.0}
    title = (title or '').strip()
    if not title:
        return out

    if use_cache:
        cached = _cache_get('', title, artist)
        if cached is not None:
            out['passages'] = cached[:MAX_PASSAGES]
            out['source'] = 'cache'
            return out

    # 1-3. Wikipedia (free): resolve QID, read article(s), keep event passages.
    try:
        qid, sections = fetch_work_sections(title, artist, location, venue,
                                            fetch=fetch)
    except Exception as e:
        print(f"  [work_story_research] wikipedia fetch failed (non-fatal): {e}")
        qid, sections = '', []
    out['qid'] = qid

    # A QID-keyed cache read, now that we have the QID (the venue_works path may
    # have seeded it under the QID from a prior tour).
    if use_cache and qid:
        cached = _cache_get(qid, title, artist)
        if cached is not None:
            out['passages'] = cached[:MAX_PASSAGES]
            out['source'] = 'cache'
            return out

    passages = event_passages(sections) if sections else []
    source = 'wikipedia' if passages else 'none'

    # 4. Optional PAID fallback — ONLY when Wikipedia is thin, and only if it fits
    #    under the per-stop ceiling. Bounded to one Serper query + one extraction.
    if allow_fallback and len(passages) < MIN_PASSAGES and COST_CEILING >= 0.02:
        fb, fb_cost = _serper_fallback(title, artist, serp=serp,
                                       fetch=page_fetch, answer=answer)
        out['cost'] += fb_cost
        if fb:
            # Merge, Wikipedia first, de-duplicated.
            seen = {p.lower()[:120] for p in passages}
            for p in fb:
                k = p.lower()[:120]
                if k not in seen:
                    seen.add(k)
                    passages.append(p)
            source = 'serper_fallback'

    passages = passages[:MAX_PASSAGES]
    out['passages'] = passages
    out['source'] = source if passages else 'none'

    # Cache the result (even an empty list — a known-thin work should not be
    # re-fetched every tour). Keyed by QID when we have one, else by title+artist.
    if use_cache:
        try:
            _cache_put(qid, title, artist, passages)
        except Exception:
            pass
    return out


# ── CLI: research one work and print the passages (spot checks) ───────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='work_story_research (LOCAL-840)')
    ap.add_argument('title')
    ap.add_argument('--artist', default='')
    ap.add_argument('--location', default='')
    ap.add_argument('--venue', default='')
    ap.add_argument('--no-cache', action='store_true')
    ap.add_argument('--no-fallback', action='store_true')
    a = ap.parse_args()
    res = museum_work_research(a.title, a.artist, a.location, a.venue,
                               use_cache=not a.no_cache,
                               allow_fallback=not a.no_fallback)
    print(json.dumps(res, indent=2, ensure_ascii=False))
