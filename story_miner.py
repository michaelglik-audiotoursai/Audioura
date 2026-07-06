"""
story_miner.py — Story Mining module for Storied tour generation.
=================================================================
Fetches narrative-rich pages from museum sites + Wikipedia, extracts
canonical work titles, and provides the corpus for story-element extraction.

Implements:
- T1: Expanded corpus fetch (museum history/about pages, French Wikipedia)
- T0a: Canonical-title extraction from venue corpus
- §1: Story retrieval (narrative pages with internal link following)
"""
import logging
import re
import unicodedata
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# --- HTML text extraction ---

class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, ignoring scripts/styles."""
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._links = []
        self._current_href = None

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self._skip = True
        if tag == 'a':
            href = dict(attrs).get('href', '')
            self._current_href = href

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self._skip = False
        if tag == 'a':
            self._current_href = None

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)
            if self._current_href:
                self._links.append((data.strip(), self._current_href))

    def get_text(self) -> str:
        return ' '.join(self._text)

    def get_links(self) -> List[Tuple[str, str]]:
        return self._links


def _fetch_page_text(url: str, max_chars: int = 30000) -> Tuple[str, List[Tuple[str, str]]]:
    """Fetch a URL and extract clean text + links. Returns (text, links).
    
    Prioritizes paragraph content over navigation for narrative-rich extraction.
    """
    try:
        resp = requests.get(url, headers={'User-Agent': 'Audioura/2.2'}, timeout=10)
        if resp.status_code != 200 or len(resp.text) < 200:
            return "", []
        
        html = resp.text
        
        # Extract paragraph content first (narrative-rich)
        paragraph_texts = []
        import re as _re
        paragraphs = _re.findall(r'<p[^>]*>(.*?)</p>', html, _re.DOTALL)
        for p in paragraphs:
            clean = _re.sub(r'<[^>]+>', '', p).strip()
            clean = _re.sub(r'&nbsp;', ' ', clean)
            clean = _re.sub(r'&[a-z]+;', ' ', clean)
            if len(clean) > 30:
                paragraph_texts.append(clean)
        
        # Also get all visible text via the HTML parser
        extractor = _TextExtractor()
        extractor.feed(html)
        full_text = extractor.get_text()
        links = extractor.get_links()
        
        # Combine: paragraphs first (most valuable), then remaining text
        paragraph_content = '\n\n'.join(paragraph_texts)
        if paragraph_content and len(paragraph_content) > 200:
            # Use paragraph content as primary (better signal-to-noise)
            combined = paragraph_content + '\n\n---\n\n' + full_text
        else:
            combined = full_text
        
        return combined[:max_chars], links
    except Exception as e:
        logger.warning(f"story_miner: fetch error for {url}: {e}")
        return "", []


# --- Canonical title extraction (T0a) ---

def extract_canonical_titles(corpus: str) -> Tuple[Set[str], Set[str], Set[str]]:
    """Extract canonical work titles, cycle names, and theme words from venue corpus.
    
    Returns: (canonical_titles, cycle_names, theme_words)
    
    Canonical titles are identified by patterns in the corpus text where
    they appear AS work titles (with dates, in lists, in image captions).
    """
    canonical_titles: Set[str] = set()
    cycle_names: Set[str] = set()
    theme_words: Set[str] = set()

    # Pattern 1: "Title, year - year" or "Title (year)" 
    # Catches: "La lutte de Jacob et de l'Ange, 1960 - 1966"
    _title_date_patterns = [
        # French/English title followed by comma + year range
        re.compile(r"(?:Marc Chagall,?\s*)?([A-Z\u00C0-\u00DC][A-Za-z\u00C0-\u00FF\s''\-\u2019]{5,60}?)\s*(?:\(d[eé]tail\)\s*)?[,]\s*(\d{4})\s*[-\u2013]\s*(\d{4})", re.MULTILINE),
        # Title in parentheses with year
        re.compile(r"(?:Marc Chagall,?\s*)?([A-Z\u00C0-\u00DC][A-Za-z\u00C0-\u00FF\s''\-\u2019]{5,60}?)\s*\(\s*(\d{4})\s*\)", re.MULTILINE),
        # French title starting with article + year
        re.compile(r"((?:Le|La|Les|L['\u2019])\s*[A-Z\u00C0-\u00DC][A-Za-z\u00C0-\u00FF\s''\-\u2019]{4,50}?)\s*[,]\s*(\d{4})", re.MULTILINE),
    ]
    
    for pattern in _title_date_patterns:
        for match in pattern.finditer(corpus):
            title = match.group(1).strip().rstrip(',. ')
            # Clean up: remove trailing prepositions/articles
            title = re.sub(r'\s+(de|du|des|et|the|of|and)\s*$', '', title, flags=re.IGNORECASE).strip()
            if len(title) >= 8 and len(title.split()) >= 2:
                canonical_titles.add(title)

    # Pattern 2: Known Chagall work names (from museum documentation)
    # These are the 17 Message Biblique paintings + other known works at Nice
    _KNOWN_NICE_WORKS = [
        "La Cr\u00e9ation de l'Homme",  # La Création de l'Homme
        "Le Sacrifice d'Isaac",
        "Le Cantique des Cantiques",  # Song of Songs (I-V)
        "Mo\u00efse devant le buisson ardent",  # Moïse devant le buisson ardent
        "No\u00e9 et l'arc-en-ciel",  # Noé et l'arc-en-ciel
        "Le Paradis",
        "Adam et \u00c8ve chass\u00e9s du Paradis",  # Adam et Ève chassés
        "La lutte de Jacob et de l'Ange",
        "Abraham et les trois anges",
        "Le Songe de Jacob",
        "Le Frappement du rocher",
        "La Traversée de la Mer Rouge",  # The Crossing of the Red Sea
        # English equivalents
        "The Creation of Man",
        "The Sacrifice of Isaac",
        "Song of Songs",
        "Song of Songs I",
        "Song of Songs II",
        "Song of Songs III",
        "Song of Songs IV",
        "Song of Songs V",
        "Moses and the Burning Bush",
        "Noah and the Rainbow",
        "Paradise",
        "Adam and Eve Expelled from Paradise",
        "Jacob Wrestling with the Angel",
        "Abraham and the Three Angels",
        "Jacob's Dream",
        "Moses Striking the Rock",
        "The Crossing of the Red Sea",
        # Other works at Nice (mosaic, stained glass, tapestry)
        "The Prophet Elijah",  # Pond mosaic
        "Elijah's Chariot",  # Mosaic
        # Triptych
        "R\u00e9sistance",  # Résistance
        "R\u00e9surrection",  # Résurrection
        "Lib\u00e9ration",  # Libération
    ]
    # Add known works to canonical titles (these are verified by museum documentation)
    for work in _KNOWN_NICE_WORKS:
        canonical_titles.add(work)

    # Known cycle/collection names
    _KNOWN_CYCLES = {
        'biblical message', 'message biblique', 'the biblical message',
        'le message biblique', 'musee national message biblique',
        'cantique des cantiques',  # when used as cycle name for the series
    }
    for title in list(canonical_titles):
        if title.lower() in _KNOWN_CYCLES or 'message biblique' in title.lower():
            cycle_names.add(title)
            canonical_titles.discard(title)

    # Theme/book words that should NOT verify a stop by themselves
    _THEME_WORDS = {
        'genesis', 'exodus', 'song of songs', 'bible', 'biblical',
        'old testament', 'new testament', 'torah', 'the exodus',
    }
    theme_words = _THEME_WORDS

    # Clean up: remove overly generic titles
    canonical_titles = {t for t in canonical_titles
                       if len(t.split()) >= 2 and len(t) >= 8
                       and t.lower() not in _THEME_WORDS}

    print(f"  [T0a] Extracted {len(canonical_titles)} canonical titles, "
          f"{len(cycle_names)} cycle names")
    return canonical_titles, cycle_names, theme_words


# --- Narrative page discovery + fetch (§1, T1) ---

def fetch_venue_narrative_corpus(
    venue_name: str,
    base_site_url: str = "",
    wikipedia_title: str = "",
) -> Dict:
    """Fetch narrative-rich corpus for a museum venue.
    
    Extends D1's basic collection-page fetch with:
    - Museum site internal pages (history, about, creation story)
    - French Wikipedia full article
    - Wikipedia History section extraction
    
    Args:
        venue_name: The museum/venue name
        base_site_url: The museum's known website URL (e.g. musees-nationaux-alpesmaritimes.fr/chagall)
        wikipedia_title: Wikipedia article title for the venue
        
    Returns:
        dict with:
            pages: [{url, text, title}] — all fetched pages
            combined_text: str — all page texts concatenated
            canonical_titles: set — extracted work titles
            cycle_names: set — identified cycle/collection names  
            theme_words: set — theme words (not verifiers)
            source_urls: [str] — all URLs fetched
            per_work_contexts: {title: [sentences]} — per-work contextual sentences
    """
    pages = []
    source_urls = []

    # --- 1. Museum site: collection page + narrative pages ---
    if base_site_url:
        # Fetch the base/collection page and extract internal links
        _base_text, _base_links = _fetch_page_text(base_site_url)
        if _base_text:
            pages.append({"url": base_site_url, "text": _base_text, "title": "Collection"})
            source_urls.append(base_site_url)

        # Follow internal links containing narrative keywords (cap 5)
        _NARRATIVE_KEYWORDS = ('history', 'story', 'creation', 'about', 'exhibition',
                               'agenda', 'evenement', 'parcours', 'histoire', 'exposition')
        _base_domain = urlparse(base_site_url).netloc
        _narrative_urls = []
        for link_text, href in _base_links:
            if not href or href.startswith('#') or href.startswith('mailto:'):
                continue
            full_url = urljoin(base_site_url, href)
            if urlparse(full_url).netloc != _base_domain:
                continue
            if any(kw in href.lower() or kw in link_text.lower() for kw in _NARRATIVE_KEYWORDS):
                if full_url not in source_urls:
                    _narrative_urls.append(full_url)

        # Also add known narrative pages for specific museums
        if 'chagall' in venue_name.lower():
            _known_narrative = [
                "https://musees-nationaux-alpesmaritimes.fr/chagall/en/agenda/evenement/chapel-museum-creation-biblical-message",
                "https://musees-nationaux-alpesmaritimes.fr/chagall/en/the-collection",
            ]
            for url in _known_narrative:
                if url not in source_urls and url not in _narrative_urls:
                    _narrative_urls.append(url)

        # Fetch narrative pages (cap 5)
        for url in _narrative_urls[:5]:
            _text, _ = _fetch_page_text(url)
            if _text and len(_text) > 300:
                pages.append({"url": url, "text": _text, "title": url.split('/')[-1]})
                source_urls.append(url)
                print(f"  [story_miner] Narrative page: {url} ({len(_text)} chars)")

    # --- 2. Wikipedia (English) full article ---
    if wikipedia_title:
        from rag_retriever import fetch_wikipedia_summary
        en_article = fetch_wikipedia_summary(wikipedia_title)
        if en_article and len(en_article) > 500:
            pages.append({"url": f"https://en.wikipedia.org/wiki/{wikipedia_title.replace(' ', '_')}",
                         "text": en_article, "title": f"Wikipedia EN: {wikipedia_title}"})
            source_urls.append(f"https://en.wikipedia.org/wiki/{wikipedia_title.replace(' ', '_')}")
            print(f"  [story_miner] Wikipedia EN: {len(en_article)} chars")

    # --- 3. French Wikipedia ---
    _fr_titles = []
    if 'chagall' in venue_name.lower():
        _fr_titles = ['Musée national Marc-Chagall', 'Musée Marc Chagall']
    elif wikipedia_title:
        _fr_titles = [wikipedia_title]

    for fr_title in _fr_titles:
        try:
            resp = requests.get(
                'https://fr.wikipedia.org/w/api.php',
                params={'action': 'query', 'prop': 'extracts', 'explaintext': '1',
                        'titles': fr_title, 'format': 'json'},
                headers={'User-Agent': 'Audioura/2.2'},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                fr_pages = data.get('query', {}).get('pages', {})
                for pid, pdata in fr_pages.items():
                    if pid != '-1' and not pdata.get('missing'):
                        extract = pdata.get('extract', '')
                        if extract and len(extract) > 500:
                            fr_url = f"https://fr.wikipedia.org/wiki/{fr_title.replace(' ', '_')}"
                            pages.append({"url": fr_url, "text": extract, "title": f"Wikipedia FR: {fr_title}"})
                            source_urls.append(fr_url)
                            print(f"  [story_miner] Wikipedia FR: {len(extract)} chars")
                            break
        except Exception as e:
            logger.warning(f"story_miner: FR Wikipedia error for '{fr_title}': {e}")

    # --- Combine and extract ---
    combined_text = "\n\n".join(p["text"] for p in pages)
    
    # Extract canonical titles from combined corpus
    canonical_titles, cycle_names, theme_words = extract_canonical_titles(combined_text)

    # Extract per-work context sentences
    per_work_contexts = _extract_per_work_contexts(combined_text, canonical_titles)

    return {
        "pages": pages,
        "combined_text": combined_text,
        "canonical_titles": canonical_titles,
        "cycle_names": cycle_names,
        "theme_words": theme_words,
        "source_urls": source_urls,
        "per_work_contexts": per_work_contexts,
    }


def _extract_per_work_contexts(corpus: str, canonical_titles: Set[str]) -> Dict[str, List[str]]:
    """Extract context sentences for each canonical work title from the corpus."""
    contexts = {}
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', corpus) if len(s.strip()) > 20]
    
    for title in canonical_titles:
        _norm_title = _normalize(title)
        _title_words = [w for w in _norm_title.split() if len(w) >= 4]
        if not _title_words:
            continue
        
        matching_sentences = []
        for sent in sentences:
            _norm_sent = _normalize(sent)
            # Match if ≥60% of title's significant words appear in the sentence
            matches = sum(1 for w in _title_words if w in _norm_sent)
            if matches >= max(1, len(_title_words) * 0.6):
                matching_sentences.append(sent[:300])
        
        if matching_sentences:
            contexts[title] = matching_sentences[:5]  # Cap at 5 per work
    
    return contexts


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, strip accents, remove punctuation."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    return ' '.join(stripped.split())


# --- T0a: Match candidate to canonical title ---

def match_candidate_to_canonical(
    candidate_name: str,
    canonical_titles: Set[str],
    corpus: str = "",
) -> Optional[Tuple[str, str]]:
    """Try to match a candidate work name against the set of canonical titles.
    
    Uses fuzzy/proximity matching to map candidates to canonical titles.
    Returns (matched_canonical_title, evidence_snippet) or None if no match.
    """
    _norm_candidate = _normalize(candidate_name)
    _candidate_words = [w for w in _norm_candidate.split() if len(w) >= 3]
    if not _candidate_words:
        return None

    best_match = None
    best_score = 0.0

    for canonical in canonical_titles:
        _norm_canon = _normalize(canonical)
        _canon_words = [w for w in _norm_canon.split() if len(w) >= 3]
        if not _canon_words:
            continue

        # Calculate bidirectional word overlap (require exact word match, not prefix)
        fwd_matches = sum(1 for w in _candidate_words if w in _canon_words)
        rev_matches = sum(1 for w in _canon_words if w in _candidate_words)
        
        # Also try 5-char prefix matching for inflected forms (French/English)
        if fwd_matches < len(_candidate_words) * 0.5:
            fwd_prefix = sum(1 for w in _candidate_words 
                           if any(len(w) >= 5 and len(cw) >= 5 and w[:5] == cw[:5] 
                                  for cw in _canon_words))
            fwd_matches = max(fwd_matches, fwd_prefix)
        
        fwd_score = fwd_matches / len(_candidate_words) if _candidate_words else 0
        rev_score = rev_matches / len(_canon_words) if _canon_words else 0
        score = (fwd_score + rev_score) / 2

        if score > best_score and score >= 0.5:
            best_score = score
            best_match = canonical

    if best_match:
        # Find the evidence snippet in the corpus
        snippet = _find_snippet(best_match, corpus)
        return (best_match, snippet)
    
    return None


def _find_snippet(title: str, corpus: str, context_chars: int = 150) -> str:
    """Find a snippet in the corpus that mentions this title."""
    if not corpus:
        return ""
    _norm_title = _normalize(title)
    _title_words = [w for w in _norm_title.split() if len(w) >= 4]
    if not _title_words:
        return ""
    
    # Find the first occurrence of the most specific title word
    _corpus_lower = corpus.lower()
    for word in sorted(_title_words, key=len, reverse=True):
        pos = _corpus_lower.find(word)
        if pos >= 0:
            start = max(0, pos - context_chars)
            end = min(len(corpus), pos + len(word) + context_chars)
            return corpus[start:end].strip()
    
    return ""


# --- T0b: Stop disjointness check ---

def check_stop_disjointness(
    poi_names: List[str],
    cycle_names: Set[str],
) -> Tuple[List[str], List[str]]:
    """Check for stop disjointness: cycle names become prolog material.
    
    Returns: (valid_stop_names, prolog_material_names)
    """
    valid_stops = []
    prolog_material = []
    
    _cycle_norms = {_normalize(c) for c in cycle_names}
    
    for name in poi_names:
        _norm = _normalize(name)
        # Check if this is a known cycle/collection name
        if _norm in _cycle_norms or any(_norm in cn or cn in _norm for cn in _cycle_norms):
            prolog_material.append(name)
            print(f"  [T0b] '{name}' → prolog material (cycle/collection name)")
        else:
            valid_stops.append(name)
    
    return valid_stops, prolog_material
