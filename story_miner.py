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
    
    Follows redirects, uses 15s timeout, one retry on timeout.
    Prioritizes paragraph content over navigation for narrative-rich extraction.
    """
    for attempt in range(2):  # One retry
        try:
            resp = requests.get(url, headers={'User-Agent': 'Audioura/2.2'},
                              timeout=15, allow_redirects=True)
            if resp.status_code != 200 or len(resp.text) < 200:
                if attempt == 0:
                    continue  # Retry once
                return "", []
            break
        except requests.exceptions.Timeout:
            if attempt == 0:
                logger.info(f"story_miner: timeout on {url}, retrying...")
                continue
            logger.warning(f"story_miner: timeout on {url} after retry")
            return "", []
        except Exception as e:
            logger.warning(f"story_miner: fetch error for {url}: {e}")
            return "", []
    else:
        return "", []
    
    html = resp.text
    
    try:
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

def extract_canonical_titles(corpus: str, venue_name: str = "") -> Tuple[Set[str], Set[str], Set[str]]:
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

    # Known cycle/collection names
    _KNOWN_CYCLES = {
        'biblical message', 'message biblique', 'the biblical message',
        'le message biblique', 'musee national message biblique',
        'cantique des cantiques',  # when used as cycle name for the series
        'song of songs',  # The 5-canvas cycle — members I-V are canonical stops
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
    language: str = "en",
) -> Dict:
    """Fetch narrative-rich corpus for a museum venue.
    
    Extends D1's basic collection-page fetch with:
    - Museum site internal pages (history, about, creation story)
    - Wikipedia full article in EN + LOCAL language (from venue_resolver country→lang)
    - Wikipedia History section extraction
    
    Args:
        venue_name: The museum/venue name
        base_site_url: The museum's website URL (from Wikidata P856 or heuristic)
        wikipedia_title: Wikipedia article title for the venue
        language: The venue's local language code (from country→lang, e.g. "fr", "it")
        
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
        
        # R1(a) fallback: if P856 URL times out, try HTTPS or known alternative domains
        if not _base_text and base_site_url.startswith('http://'):
            _https_url = base_site_url.replace('http://', 'https://')
            _base_text, _base_links = _fetch_page_text(_https_url)
            if _base_text:
                base_site_url = _https_url
                print(f"  [story_miner] P856 timeout → HTTPS fallback worked: {_https_url}")
        
        if _base_text:
            pages.append({"url": base_site_url, "text": _base_text, "title": "Collection"})
            source_urls.append(base_site_url)

        # Follow internal links containing narrative keywords (cap 5)
        # Localized keywords based on venue language
        _NARRATIVE_KEYWORDS_BASE = ('history', 'story', 'creation', 'about', 'exhibition',
                                    'collection', 'works', 'permanent')
        _NARRATIVE_KEYWORDS_LOCALIZED = {
            'fr': ('histoire', 'parcours', 'exposition', 'evenement', 'oeuvres', 'collection', 'creation'),
            'it': ('storia', 'collezione', 'opere', 'mostra', 'esposizione', 'percorso'),
            'de': ('geschichte', 'sammlung', 'werke', 'ausstellung'),
            'es': ('historia', 'coleccion', 'obras', 'exposicion'),
        }
        _NARRATIVE_KEYWORDS = _NARRATIVE_KEYWORDS_BASE + _NARRATIVE_KEYWORDS_LOCALIZED.get(language, ())
        
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

        # Fetch narrative pages (cap 5)
        for url in _narrative_urls[:5]:
            _text, _ = _fetch_page_text(url)
            if _text and len(_text) > 300:
                pages.append({"url": url, "text": _text, "title": url.split('/')[-1]})
                source_urls.append(url)
                print(f"  [story_miner] Narrative page: {url} ({len(_text)} chars)")

    # --- 2. Wikipedia (English) full article — ALWAYS fetched regardless of language ---
    if wikipedia_title:
        from rag_retriever import fetch_wikipedia_summary
        # Try the provided title and common variants
        _en_titles = [wikipedia_title]
        # Add variants: with/without accents, with city disambiguator
        _clean_title = wikipedia_title.replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e').replace('à', 'a').replace('ô', 'o').replace('î', 'i').replace('ç', 'c').replace('ü', 'u').replace('ö', 'o').replace('ä', 'a')
        if _clean_title != wikipedia_title:
            _en_titles.append(_clean_title)
        # Try "Musée X" → "X Museum" style conversion
        if wikipedia_title.lower().startswith('mus'):
            _name_part = re.sub(r'(?i)^mus[ée]+e?\s*(national[e]?\s*)?', '', wikipedia_title).strip()
            _name_part = _name_part.replace('-', ' ')  # "Marc-Chagall" → "Marc Chagall"
            if _name_part:
                _en_titles.append(f"{_name_part} Museum")
                _en_titles.append(f"Musée {_name_part}")
                # Also try with city disambiguator to avoid wrong museum (e.g. Belarus vs Nice)
                if venue_name and ',' in venue_name:
                    _city_part = venue_name.split(',')[1].strip() if len(venue_name.split(',')) > 1 else ""
                    if _city_part:
                        _en_titles.append(f"{_name_part} Museum {_city_part}")
                        _en_titles.append(f"Musée national {_name_part}")
        # Also try with venue_name directly
        if venue_name and venue_name != wikipedia_title:
            _en_titles.append(venue_name)
        
        en_article = ""
        for _en_title in _en_titles:
            _candidate = fetch_wikipedia_summary(_en_title)
            if _candidate and len(_candidate) > 500:
                # Validate: article should mention the venue's city (avoid wrong-city museum)
                _city_from_name = ""
                if venue_name and ',' in venue_name:
                    parts = venue_name.split(',')
                    _city_from_name = parts[1].strip().lower() if len(parts) > 1 else ""
                
                if _city_from_name and _city_from_name not in _candidate.lower()[:2000]:
                    # Wrong museum (e.g. Belarus Chagall museum vs Nice)
                    print(f"  [story_miner] Wikipedia EN: '{_en_title}' rejected (doesn't mention '{_city_from_name}')")
                    continue
                
                en_article = _candidate
                pages.append({"url": f"https://en.wikipedia.org/wiki/{_en_title.replace(' ', '_')}",
                             "text": en_article, "title": f"Wikipedia EN: {_en_title}"})
                source_urls.append(f"https://en.wikipedia.org/wiki/{_en_title.replace(' ', '_')}")
                print(f"  [story_miner] Wikipedia EN: {len(en_article)} chars (title: '{_en_title}')")
                break

    # --- 3. Local-language Wikipedia (country→lang, not hardcoded "fr") ---
    if language and language != "en" and wikipedia_title:
        _local_titles = [wikipedia_title]
        # Try with city disambiguator for common ambiguous venue names
        if "nice" in venue_name.lower() or "nice" in (wikipedia_title or "").lower():
            _local_titles.append(f"{wikipedia_title} (Nice)")
        
        for local_title in _local_titles:
            try:
                resp = requests.get(
                    f'https://{language}.wikipedia.org/w/api.php',
                    params={'action': 'query', 'prop': 'extracts', 'explaintext': '1',
                            'titles': local_title, 'format': 'json'},
                    headers={'User-Agent': 'Audioura/2.2'},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    local_pages = data.get('query', {}).get('pages', {})
                    for pid, pdata in local_pages.items():
                        if pid != '-1' and not pdata.get('missing'):
                            extract = pdata.get('extract', '')
                            if extract and len(extract) > 500:
                                local_url = f"https://{language}.wikipedia.org/wiki/{local_title.replace(' ', '_')}"
                                pages.append({"url": local_url, "text": extract, "title": f"Wikipedia {language.upper()}: {local_title}"})
                                source_urls.append(local_url)
                                print(f"  [story_miner] Wikipedia {language.upper()}: {len(extract)} chars")
                                break
            except Exception as e:
                logger.warning(f"story_miner: {language.upper()} Wikipedia error for '{local_title}': {e}")

    # --- Combine and extract ---
    combined_text = "\n\n".join(p["text"] for p in pages)
    
    # Extract canonical titles from combined corpus
    canonical_titles, cycle_names, theme_words = extract_canonical_titles(combined_text, venue_name)

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


# --- W4: Canonical alias map (variants → single canonical entry) ---
# Built dynamically from Wikidata SPARQL labels at runtime.
# Empty by default — populated per-request by venue_resolver.build_dynamic_aliases()
CANONICAL_ALIASES: Dict[str, str] = {}

# Roman numerals that should NEVER be dropped during matching
_ROMAN_NUMERALS = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}


# --- T0a: Match candidate to canonical title ---

def match_candidate_to_canonical(
    candidate_name: str,
    canonical_titles: Set[str],
    corpus: str = "",
) -> Optional[Tuple[str, str]]:
    """Try to match a candidate work name against the set of canonical titles.
    
    Resolution order:
    1. Exact alias lookup (normalized) — deterministic, no ties
    2. Fuzzy content-word matching — with numeral-awareness
    
    Returns (matched_canonical_title, evidence_snippet) or None if no match.
    """
    _norm_candidate = _normalize(candidate_name)
    
    # Step 1: Exact alias lookup (deterministic, no hash-order ties)
    if _norm_candidate in CANONICAL_ALIASES:
        _resolved = CANONICAL_ALIASES[_norm_candidate]
        if _resolved in canonical_titles:
            snippet = _find_snippet(_resolved, corpus)
            return (_resolved, snippet)
    
    # Also try exact match against canonical titles (normalized)
    _canon_norm_map = {_normalize(c): c for c in canonical_titles}
    if _norm_candidate in _canon_norm_map:
        _exact = _canon_norm_map[_norm_candidate]
        snippet = _find_snippet(_exact, corpus)
        return (_exact, snippet)
    
    # Step 2: Fuzzy matching with numeral awareness
    _STOP_WORDS = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'his',
        'her', 'its', 'who', 'which', 'their', 'not', 'but', 'all', 'can', 'will',
        'les', 'des', 'une', 'dans', 'sur', 'par', 'pour', 'avec', 'son', 'ses',
        'est', 'sont', 'qui', 'que', 'aux',
        'der', 'die', 'das', 'und', 'ein', 'eine', 'mit', 'von', 'den', 'dem',
        'del', 'della', 'dei', 'con', 'gli', 'per', 'una',
        'los', 'las', 'con', 'por',
    }
    
    def _content_words(text_norm):
        """Extract content words, preserving roman numerals as distinguishing tokens."""
        words = text_norm.split()
        result = []
        for w in words:
            if w in _ROMAN_NUMERALS:
                result.append(w)  # Always keep numerals
            elif len(w) >= 3 and w not in _STOP_WORDS:
                result.append(w)
        return result
    
    _candidate_words = _content_words(_norm_candidate)
    if not _candidate_words:
        return None
    
    # Extract candidate's numeral (if any)
    _cand_numeral = None
    for w in _candidate_words:
        if w in _ROMAN_NUMERALS:
            _cand_numeral = w
            break

    best_match = None
    best_score = 0.0

    for canonical in canonical_titles:
        _norm_canon = _normalize(canonical)
        _canon_words = _content_words(_norm_canon)
        if not _canon_words:
            continue
        
        # [W4] Numeral mismatch check: if candidate has a numeral, canonical must have same one
        _canon_numeral = None
        for w in _canon_words:
            if w in _ROMAN_NUMERALS:
                _canon_numeral = w
                break
        if _cand_numeral and _canon_numeral and _cand_numeral != _canon_numeral:
            continue  # Different numerals = different works
        if _cand_numeral and not _canon_numeral:
            continue  # Candidate has numeral, canonical doesn't = candidate is more specific
        if not _cand_numeral and _canon_numeral:
            continue  # [W4] Canonical has numeral, candidate doesn't = candidate is less specific (cycle vs member)

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
            # [M3 fix] Short titles (≤2 content words) require ALL content words to match
            if len(_candidate_words) <= 2:
                if fwd_matches < len(_candidate_words):
                    continue  # Not all candidate words matched — skip
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
