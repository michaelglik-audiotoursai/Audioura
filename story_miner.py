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


# --- Navigational / administrative label filter (LOCAL-9) ---

# Pattern-based keywords indicating a navigation/admin page label, NOT an artwork.
# Covers French and English administrative vocabulary found on museum websites.
# Deliberately broad patterns — an artwork title that accidentally contains one of
# these words would still be kept if it also has an artwork-like signal (date, medium,
# proper-noun structure suggesting a named work).
_NAV_LABEL_PATTERNS_FR = re.compile(
    r'\b(?:'
    r'infos?\s+pratiques?|informations?\s+pratiques?|'
    r'plan\s+d[eu\']?\s*(?:visite|acc[eè]s|salle)|'
    r'horaires?|tarifs?|billetterie|r[eé]servation|'
    r'acc[eè]s|comment\s+venir|nous\s+trouver|'
    r'mus[eé]e\s+en\s+vid[eé]o|vid[eé]os?\s+du\s+mus[eé]e|'
    r'actualit[eé]s?|agenda|[eé]v[eé]nements?|programmation|'
    r'newsletter|contactez(?:\s*[-–]\s*nous)?|nous\s+contacter|'
    r'mentions?\s+l[eé]gales?|politique\s+de\s+confidentialit[eé]|'
    r'plan\s+du\s+site|accessibilit[eé]|'
    r'groupes?\s+(?:et\s+)?scolaires?|m[eé]diation|'
    r'[eé]ditions?|publications?|boutique|librairie|'
    r'partenaires?|m[eé]c[eè]nat|soutenir|devenir\s+ami|'
    r'espace\s+(?:presse|enseignants?|pro)|'
    r'pr[eê]t\s+d[e\']?\s*[oœ]uvres?|'
    r'location\s+d[e\']?\s*(?:espaces?|salles?)'
    r')\b', re.IGNORECASE
)

_NAV_LABEL_PATTERNS_EN = re.compile(
    r'\b(?:'
    r'visit(?:or)?\s+info(?:rmation)?|plan\s+your\s+visit|'
    r'opening\s+hours?|admission|tickets?|book(?:ing)?|'
    r'getting\s+(?:here|there)|directions?|find\s+us|'
    r'museum\s+(?:on\s+video|shop|store|caf[eé])|'
    r'what\'?s?\s+on|current\s+exhibitions?|upcoming|'
    r'news(?:letter)?|press\s+(?:room|releases?)|'
    r'contact\s+us|privacy\s+policy|terms?\s+(?:of\s+use|and\s+conditions?)|'
    r'accessibility\s+(?:statement|guide|info(?:rmation)?)|site\s*map|'
    r'group\s+visits?|school\s+(?:visits?|programs?)|education|'
    r'support\s+us|become\s+a\s+(?:member|friend)|donate|'
    r'venue\s+hire|facility\s+rental'
    r')\b', re.IGNORECASE
)

# Artwork-like positive signals: if a candidate has any of these, it's likely a real
# title even if it superficially resembles a nav label.
_YEAR_PATTERN = re.compile(r'\b(?:1[5-9]\d{2}|20[0-2]\d)\b')  # 1500-2029
_MEDIUM_SIGNAL = re.compile(
    r'\b(?:'
    r'peinture|sculpture|gravure|lithographi|dessin|mosa[iï]que|vitrail|'
    r'tapisserie|c[eé]ramique|gouache|aquarelle|huile|encre|bronze|marbre|'
    r'painting|drawing|print|mosaic|stained\s+glass|tapestry|ceramic|'
    r'watercolor|oil\s+on|ink\s+on|acrylic|installation|fresco|bas[- ]relief'
    r')\b', re.IGNORECASE
)
# Artwork title structural signals: possessive/genitive ("de l'", "du", "of the"),
# named-entity patterns (multi-word starting uppercase), poetic constructions
_ARTWORK_TITLE_SIGNAL = re.compile(
    r'(?:'
    r'\b(?:portrait|autoportrait|vue|paysage|nature\s+morte|'
    r'sc[eè]ne|all[eé]gorie|hommage|composition|triptyque|'
    r'still\s+life|landscape|seascape|cityscape|self[- ]portrait)\b|'
    r'\b(?:Voyage|Geste|Exil|Message|Cantique|Paradis)\b|'
    r'[-–—]\s*(?:Prince|Roi|Reine|Duke|King|Queen)|'  # subtitle pattern
    r'\(\s*\d{4}\s*[-–]\s*\d{4}\s*\)'  # lifespan in parens
    r')', re.IGNORECASE
)


def _is_navigational_label(candidate: str) -> bool:
    """Return True if candidate looks like a website nav/admin label, not an artwork.
    
    Strategy: if the candidate matches a known navigational pattern AND lacks any
    artwork-like signal (date, medium keyword, artwork title structure), it's filtered.
    This is deliberately conservative — when in doubt, keep the candidate (false
    negatives are less harmful than dropping real exhibit titles).
    """
    # Check for navigational pattern match (FR or EN)
    has_nav_signal = bool(
        _NAV_LABEL_PATTERNS_FR.search(candidate) or
        _NAV_LABEL_PATTERNS_EN.search(candidate)
    )
    
    if not has_nav_signal:
        return False  # Not navigational — keep it
    
    # Has a nav signal — but does it also have artwork signals that override?
    has_artwork_signal = bool(
        _YEAR_PATTERN.search(candidate) or
        _MEDIUM_SIGNAL.search(candidate) or
        _ARTWORK_TITLE_SIGNAL.search(candidate)
    )
    
    if has_artwork_signal:
        return False  # Artwork signal overrides — keep it
    
    # Nav signal present, no artwork signal — filter it out
    return True


# --- Canonical title extraction (T0a) ---

def extract_canonical_titles(corpus: str, venue_name: str = "") -> Tuple[Set[str], Set[str], Set[str]]:
    """Extract canonical work titles, cycle names, and theme words from venue corpus.
    
    Returns: (canonical_titles, cycle_names, theme_words)
    
    Canonical titles are identified by patterns in the corpus text where
    they appear AS work titles (with dates, in lists, in image captions).
    Also extracts exhibit names from section headers and bold/quoted names
    for exhibit-type museums.
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

    # Pattern 2: Museum catalog format — "Medium  Title" (e.g. "Peinture  La Création de l'homme")
    # Common on museum collection pages where medium precedes the work title
    _MEDIUM_KEYWORDS = ('Peinture', 'Sculpture', 'Gravure', 'Lithographie', 'Dessin',
                        'Mosaïque', 'Vitrail', 'Tapisserie', 'Céramique', 'Gouache',
                        'Painting', 'Drawing', 'Print', 'Mosaic', 'Stained glass')
    for medium in _MEDIUM_KEYWORDS:
        _medium_pattern = re.compile(
            rf'{medium}\s{{2,}}([A-ZÀ-Ü][A-Za-z\u00C0-\u00FF\s\'\'\-\u2019]{{5,60}}?)(?:\s{{2,}}|$)',
            re.MULTILINE
        )
        for match in _medium_pattern.finditer(corpus):
            title = match.group(1).strip().rstrip(',. ')
            if len(title) >= 5 and len(title.split()) >= 2:
                canonical_titles.add(title)

    # Pattern 3: Exhibit-name extraction — for exhibit/experience museums
    # Wikipedia section headers (== Section Name == or === Section Name ===)
    _section_pattern = re.compile(r'^={2,4}\s*(.+?)\s*={2,4}\s*$', re.MULTILINE)
    _exhibit_from_sections = set()
    for match in _section_pattern.finditer(corpus):
        section_name = match.group(1).strip()
        # Filter out generic Wikipedia sections
        _GENERIC_SECTIONS = {
            'history', 'see also', 'references', 'external links', 'notes',
            'further reading', 'bibliography', 'gallery', 'location',
            'architecture', 'overview', 'mission', 'about', 'staff',
            'board of directors', 'governance', 'funding', 'hours',
            'admission', 'transit', 'getting there', 'accessibility',
            'education', 'programs', 'events', 'membership', 'impact',
            'criticism', 'controversy', 'awards', 'reception',
            # LOCAL-23: French generic sections (Wikipedia FR)
            'voir aussi', 'liens externes', 'articles connexes',
            'notes et références', 'notes et references', 'références',
            'bibliographie', 'histoire', 'localisation', 'architecture',
            'de nos jours', 'le musée', 'le musee', 'the museum',
            'initiative de création', 'initiative for creation',
            'origin of the museum\'s pieces', 'origine des pièces du musée',
            'the museum\'s collections', 'les collections du musée',
            'les collections', 'collections', 'description',
        }
        if (section_name.lower() not in _GENERIC_SECTIONS and
            len(section_name) >= 5 and len(section_name) <= 80 and
            not section_name.startswith('http') and
            not re.match(r'^\d+', section_name) and
            # LOCAL-23: Also filter very short generic headings (Le X, La X for single nouns)
            not (len(section_name.split()) <= 2 and
                 section_name.split()[0].lower() in ('le', 'la', 'les', 'l\'', 'the', 'a', 'an'))):
            _exhibit_from_sections.add(section_name)

    # Pattern 4: Quoted exhibit/installation names ("Name" or 'Name' or "Name")
    _quoted_pattern = re.compile(r'["\u201c]([A-Z][A-Za-z\u00C0-\u00FF\s\'\'\-\u2019:,]{4,60}?)["\u201d]')
    _exhibit_from_quoted = set()
    for match in _quoted_pattern.finditer(corpus):
        name = match.group(1).strip().rstrip(',. ')
        if len(name) >= 5 and len(name.split()) >= 2:
            _exhibit_from_quoted.add(name)

    # Pattern 5: Bold exhibit names (common in Wikipedia/HTML-derived text)
    # In plaintext Wikipedia extracts, bold appears as the title itself in first line
    # or as section-leading proper nouns. Detect named entities at line starts.
    _bold_pattern = re.compile(r"'''(.+?)'''")  # MediaWiki bold
    for match in _bold_pattern.finditer(corpus):
        name = match.group(1).strip()
        if len(name) >= 5 and len(name) <= 80 and name[0].isupper():
            _exhibit_from_quoted.add(name)

    # Pattern 6: List-item exhibit names (common on museum /exhibits pages)
    # "• Exhibit Name" or "- Exhibit Name" or "* Exhibit Name" at line start
    # LOCAL-9: Apply navigational-label filter here — this pattern is the primary
    # entry point for French museum-site nav labels rendered as bullet lists.
    _list_item_pattern = re.compile(r'^[\s]*[•\-\*]\s+([A-Z][A-Za-z\u00C0-\u00FF\s\'\'\-\u2019:,&]{4,60}?)(?:\s*[-–—:]|\s*$)', re.MULTILINE)
    for match in _list_item_pattern.finditer(corpus):
        name = match.group(1).strip().rstrip(',. ')
        if len(name) >= 5 and len(name.split()) >= 2:
            if not _is_navigational_label(name):
                _exhibit_from_quoted.add(name)
            else:
                print(f"  [T0a] Filtered nav label from list-items: '{name}'")

    # Combine exhibit names into canonical_titles
    _exhibit_names = _exhibit_from_sections | _exhibit_from_quoted
    if _exhibit_names:
        print(f"  [T0a] Exhibit-name extraction: {len(_exhibit_from_sections)} from sections, "
              f"{len(_exhibit_from_quoted)} from quoted/bold/list")
        canonical_titles |= _exhibit_names

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

    # LOCAL-9: Final-pass navigational-label filter on all combined candidates.
    # This catches any nav labels that entered via Pattern 4 (quoted) or Pattern 5
    # (bold), not just Pattern 6 which has its own inline check.
    _nav_filtered = {t for t in canonical_titles if _is_navigational_label(t)}
    if _nav_filtered:
        print(f"  [T0a] Final-pass nav filter removed {len(_nav_filtered)}: "
              f"{sorted(_nav_filtered)[:5]}")
        canonical_titles -= _nav_filtered

    print(f"  [T0a] Extracted {len(canonical_titles)} canonical titles, "
          f"{len(cycle_names)} cycle names")
    return canonical_titles, cycle_names, theme_words


# --- LOCAL-23: Joconde/POP (French national museum collections database) ---

def _fetch_joconde_titles(museo_code: str, venue_name: str = "", max_titles: int = 30) -> List[Dict]:
    """Fetch canonical work titles from Joconde/POP for a French public museum.
    
    Uses the POP individual notice pages which are server-rendered (the search
    interface is JS-only and inaccessible via simple HTTP).
    
    Strategy: query the POP search URL pattern and parse the SSR page for notice
    links and titles. Falls back to the data.gouv.fr Joconde data API.
    
    Args:
        museo_code: The Joconde museo code (e.g. 'M0946' for Asian Arts Nice)
        venue_name: Venue name for context logging
        max_titles: Maximum titles to retrieve
        
    Returns:
        List of {title, source_url, tier} dicts. Empty list if POP unreachable.
    """
    titles = []
    
    # Approach 1: Try known POP notice URL patterns
    # POP notice pages ARE server-rendered and contain the work title in the HTML
    # URL format: https://pop.culture.gouv.fr/notice/joconde/{REF}
    # We can discover refs from the Wikidata P347 (Joconde ID) property
    
    # Approach 2: Try direct search via the API (may work on some endpoints)
    _search_urls = [
        f'https://pop.culture.gouv.fr/recherche?base=%5B%22joconde%22%5D&museo=%5B%22{museo_code}%22%5D',
    ]
    
    # Approach 3: Fetch the museum's listing page on POP via a known sharing link format
    # The new POP site uses Next.js RSC; we try to get any HTML that includes notice refs
    try:
        resp = requests.get(
            f'https://pop.culture.gouv.fr/recherche',
            params={'base': '["joconde"]', 'museo': f'["{museo_code}"]'},
            headers={'User-Agent': 'Audioura/2.2'},
            timeout=10,
        )
        if resp.status_code == 200 and 'notice/joconde/' in resp.text:
            # Extract notice references from the HTML
            import re as _re_joc
            notice_refs = _re_joc.findall(r'/notice/joconde/([A-Z0-9]+)', resp.text)
            notice_refs = list(dict.fromkeys(notice_refs))[:max_titles]  # unique, preserve order
            
            for ref in notice_refs:
                notice_url = f'https://pop.culture.gouv.fr/notice/joconde/{ref}'
                try:
                    nr = requests.get(notice_url, headers={'User-Agent': 'Audioura/2.2'}, timeout=8)
                    if nr.status_code == 200:
                        # Extract title from the page (usually in <title> or <h1>)
                        _title_match = _re_joc.search(r'<title>([^<]+)</title>', nr.text)
                        if _title_match:
                            _raw_title = _title_match.group(1).strip()
                            # POP title format: "Work Title - POP" or "Work Title"
                            _clean = _re_joc.sub(r'\s*[-–—]\s*POP.*$', '', _raw_title).strip()
                            _clean = _re_joc.sub(r'\s*[-–—]\s*Plateforme.*$', '', _clean).strip()
                            if _clean and len(_clean) >= 3 and _clean.lower() != 'pop':
                                titles.append({
                                    'title': _clean,
                                    'source_url': notice_url,
                                    'tier': 2,
                                })
                except Exception:
                    continue
            
            if titles:
                print(f"  [story_miner] Joconde/POP: {len(titles)} titles from {len(notice_refs)} notices ({museo_code})")
                return titles
    except Exception as e:
        logger.info(f"story_miner: Joconde/POP search failed for {museo_code}: {e}")
    
    # If POP JS-rendered page didn't yield results, log and return empty
    # (the 1.1GB CSV download is not practical per-request)
    if not titles:
        print(f"  [story_miner] Joconde/POP: no results for {museo_code} (JS-rendered, expected)")
    
    return titles


def _lookup_museo_code(venue_qid: str) -> Optional[str]:
    """Look up Joconde museum code (P539) for a Wikidata entity.
    
    Returns the museo code (e.g. 'M0946') or None.
    """
    try:
        resp = requests.get(
            'https://query.wikidata.org/sparql',
            params={
                'query': f'SELECT ?code WHERE {{ wd:{venue_qid} wdt:P539 ?code. }}',
                'format': 'json',
            },
            headers={'User-Agent': 'Audioura/2.2', 'Accept': 'application/sparql-results+json'},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            bindings = data.get('results', {}).get('bindings', [])
            if bindings:
                code = bindings[0].get('code', {}).get('value', '')
                if code:
                    print(f"  [story_miner] Joconde museo code: {code} (from P539)")
                    return code
    except Exception as e:
        logger.info(f"story_miner: P539 lookup failed for {venue_qid}: {e}")
    return None


# --- Narrative page discovery + fetch (§1, T1) ---

def fetch_venue_narrative_corpus(
    venue_name: str,
    base_site_url: str = "",
    wikipedia_title: str = "",
    language: str = "en",
    venue_qid: str = "",
) -> Dict:
    """Fetch narrative-rich corpus for a museum venue.
    
    Extends D1's basic collection-page fetch with:
    - Museum site internal pages (history, about, creation story)
    - Wikipedia full article in EN + LOCAL language (from venue_resolver country→lang)
    - Wikipedia History section extraction
    - LOCAL-23: Joconde/POP for French public museums (tier 2)
    - LOCAL-23: Demand-driven page budget (15 pages, was 5)
    - LOCAL-23: Trust tier tracking per source
    
    Args:
        venue_name: The museum/venue name
        base_site_url: The museum's website URL (from Wikidata P856 or heuristic)
        wikipedia_title: Wikipedia article title for the venue
        language: The venue's local language code (from country→lang, e.g. "fr", "it")
        venue_qid: Wikidata QID for the venue (used for Joconde museo code lookup)
        
    Returns:
        dict with:
            pages: [{url, text, title}] — all fetched pages
            combined_text: str — all page texts concatenated
            canonical_titles: set — extracted work titles
            cycle_names: set — identified cycle/collection names  
            theme_words: set — theme words (not verifiers)
            source_urls: [str] — all URLs fetched
            per_work_contexts: {title: [sentences]} — per-work contextual sentences
            title_sources: {title: [{source_url, tier}]} — LOCAL-23: provenance per title
    """
    pages = []
    source_urls = []
    # LOCAL-23: Trust-tier tracking per source page
    # tier 1 = Wikipedia (venue language first) + official museum site
    # tier 2 = Joconde/POP, Wikidata SPARQL, other institutional sources
    _page_tiers = {}  # url → tier (1 or 2)

    # --- 1. Museum site: collection page + narrative pages ---
    # LOCAL-23: Demand-driven depth — page budget scales with site richness.
    # Collection/oeuvre pages are tier-1 priority; agenda/publications deprioritized.
    _PAGE_BUDGET = 15  # up from 5 — bounded but allows much richer corpus
    _pages_fetched_site = 0

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
            _page_tiers[base_site_url] = 1  # Official site = tier 1
            _pages_fetched_site += 1

        # LOCAL-23: Improved page-type prioritisation.
        # Priority 1 (highest): collection/oeuvre/works pages — these list actual artworks
        # Priority 2: exhibit/gallery pages — named installations
        # Priority 3: history/about/narrative — contextual richness
        # Priority 4 (lowest): agenda/publications/events — rarely useful for work titles
        _COLLECTION_KEYWORDS = ('oeuvre', 'œuvre', 'collection', 'works', 'permanent',
                                'galerie', 'gallery', 'highlight', 'masterpiece',
                                'chef-d-oeuvre', 'oeuvres-commentees', 'les-oeuvres')
        _EXHIBIT_KEYWORDS = ('exhibit', 'galleries', 'installations', 'experience',
                             'exposition-permanente', 'salle')
        _NARRATIVE_KEYWORDS_BASE = ('history', 'story', 'creation', 'about',
                                    'collection', 'works', 'permanent', 'exhibits',
                                    'galleries', 'interactive', 'experience', 'installations')
        _NARRATIVE_KEYWORDS_LOCALIZED = {
            'fr': ('histoire', 'parcours', 'exposition', 'evenement', 'oeuvres',
                   'collection', 'creation', 'oeuvres-commentees', 'les-oeuvres'),
            'it': ('storia', 'collezione', 'opere', 'mostra', 'esposizione', 'percorso'),
            'de': ('geschichte', 'sammlung', 'werke', 'ausstellung'),
            'es': ('historia', 'coleccion', 'obras', 'exposicion'),
        }
        _NARRATIVE_KEYWORDS = _NARRATIVE_KEYWORDS_BASE + _NARRATIVE_KEYWORDS_LOCALIZED.get(language, ())
        # LOCAL-23: Deprioritized page types (agenda, publications, press, tickets, visits info)
        _DEPRIORITIZED_KEYWORDS = ('agenda', 'actualite', 'newsletter', 'presse',
                                   'billetterie', 'tarif', 'horaire', 'contact',
                                   'publication', 'dossier-pedagogique', 'mentions-legales',
                                   'politique-confidentialite', 'accessibilite',
                                   'visite-guidee', 'visites-guidees', 'visites-scolaires',
                                   'reglement', 'handicap', 'acces-et-condition')
        # LOCAL-23: Skip binary/media URLs entirely
        _SKIP_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
                            '.mp4', '.mp3', '.wav', '.doc', '.docx', '.xls', '.xlsx')
        
        _base_domain = urlparse(base_site_url).netloc
        _collection_urls = []  # Priority 1: collection/oeuvre pages
        _exhibit_urls = []     # Priority 2: exhibit pages
        _narrative_urls = []   # Priority 3: narrative/history pages
        _other_urls = []       # Priority 4: agenda/publications (deprioritized)
        
        for link_text, href in _base_links:
            if not href or href.startswith('#') or href.startswith('mailto:'):
                continue
            full_url = urljoin(base_site_url, href)
            # LOCAL-23: Normalize URL — strip fragment identifiers
            full_url = full_url.split('#')[0]
            if not full_url or full_url in source_urls:
                continue
            # LOCAL-23: Skip binary/media files
            _url_path_lower = urlparse(full_url).path.lower()
            if any(_url_path_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue
            if urlparse(full_url).netloc != _base_domain:
                continue
            if full_url in source_urls:
                continue
            _href_lower = href.lower()
            _text_lower = link_text.lower()
            
            # Skip deprioritized pages entirely unless they also have collection keywords
            _is_deprioritized = any(dk in _href_lower for dk in _DEPRIORITIZED_KEYWORDS)
            _has_collection_signal = any(ck in _href_lower or ck in _text_lower
                                         for ck in _COLLECTION_KEYWORDS)
            
            if _is_deprioritized and not _has_collection_signal:
                _other_urls.append(full_url)
                continue
            
            # Classify by priority
            if _has_collection_signal:
                _collection_urls.append(full_url)
            elif any(ek in _href_lower or ek in _text_lower for ek in _EXHIBIT_KEYWORDS):
                _exhibit_urls.append(full_url)
            elif any(kw in _href_lower or kw in _text_lower for kw in _NARRATIVE_KEYWORDS):
                _narrative_urls.append(full_url)

        # Deduplicate while preserving priority order
        _seen_urls = set(source_urls)
        _ordered_urls = []
        for url in _collection_urls + _exhibit_urls + _narrative_urls + _other_urls:
            if url not in _seen_urls:
                _seen_urls.add(url)
                _ordered_urls.append(url)

        # LOCAL-23: Fetch up to PAGE_BUDGET pages (demand-driven, was hard-capped at 5)
        for url in _ordered_urls[:_PAGE_BUDGET]:
            _text, _links = _fetch_page_text(url)
            if _text and len(_text) > 300:
                pages.append({"url": url, "text": _text, "title": url.split('/')[-1]})
                source_urls.append(url)
                _page_tiers[url] = 1  # Official site = tier 1
                _pages_fetched_site += 1
                print(f"  [story_miner] Site page: {url} ({len(_text)} chars)")
                
                # LOCAL-23: Follow sub-links on collection pages (depth-2 crawl for oeuvres)
                _is_collection_page = any(ck in url.lower() for ck in _COLLECTION_KEYWORDS)
                _is_exhibit_page = any(ek in url.lower() for ek in ('exhibit', 'galleries'))
                
                if _is_collection_page or _is_exhibit_page:
                    _sub_link_budget = 5  # Cap depth-2 crawl per page
                    _sub_links_followed = 0
                    for _lt, _lhref in _links:
                        if not _lhref or _lhref.startswith('#') or _lhref.startswith('mailto:'):
                            continue
                        _full_link = urljoin(url, _lhref).split('#')[0]  # Strip fragments
                        if not _full_link:
                            continue
                        if urlparse(_full_link).netloc != _base_domain:
                            continue
                        if _full_link in _seen_urls:
                            continue
                        # Skip binary/media files
                        _sub_path = urlparse(_full_link).path.lower()
                        if any(_sub_path.endswith(ext) for ext in _SKIP_EXTENSIONS):
                            continue
                        # Only follow sub-pages of this collection/exhibit URL
                        if _full_link.startswith(url.rstrip('/') + '/') or \
                           any(ck in _full_link.lower() for ck in _COLLECTION_KEYWORDS):
                            if _pages_fetched_site < _PAGE_BUDGET and _sub_links_followed < _sub_link_budget:
                                _sub_text, _ = _fetch_page_text(_full_link)
                                if _sub_text and len(_sub_text) > 300:
                                    pages.append({"url": _full_link, "text": _sub_text,
                                                  "title": _full_link.split('/')[-1]})
                                    source_urls.append(_full_link)
                                    _page_tiers[_full_link] = 1
                                    _seen_urls.add(_full_link)
                                    _pages_fetched_site += 1
                                    _sub_links_followed += 1
                                    print(f"  [story_miner] Sub-page: {_full_link} ({len(_sub_text)} chars)")
                        elif _is_exhibit_page:
                            # Extract exhibit names from sub-page links
                            _slug = _full_link.rstrip('/').split('/')[-1]
                            _exhibit_title = _slug.replace('-', ' ').title()
                            if (len(_exhibit_title) >= 5 and
                                _exhibit_title.lower() not in ('learn more', 'read more', 'tickets', 'visit', 'about')):
                                _text += f"\n== {_exhibit_title} =="
                    # Re-store with enriched text
                    if _is_exhibit_page:
                        pages[-1]["text"] = _text
        
        print(f"  [story_miner] Site crawl: {_pages_fetched_site} pages fetched (budget: {_PAGE_BUDGET})")

    # --- 2. Wikipedia (English) full article — ALWAYS fetched regardless of language ---
    # LOCAL-23: Use Wikidata sitelinks to get EXACT Wikipedia titles (avoids variant guessing)
    _en_wiki_title_exact = ""
    _local_wiki_title_exact = ""
    if venue_qid:
        try:
            _sl_query = f"""SELECT ?sitelink WHERE {{
                ?sitelink schema:about wd:{venue_qid} .
                ?sitelink schema:isPartOf/wikibase:wikiGroup "wikipedia" .
            }}"""
            _sl_resp = requests.get(
                'https://query.wikidata.org/sparql',
                params={'query': _sl_query, 'format': 'json'},
                headers={'User-Agent': 'Audioura/2.2', 'Accept': 'application/sparql-results+json'},
                timeout=10,
            )
            if _sl_resp.status_code == 200:
                _sl_data = _sl_resp.json()
                for _sl_r in _sl_data.get('results', {}).get('bindings', []):
                    _sl_url = _sl_r.get('sitelink', {}).get('value', '')
                    if 'en.wikipedia.org' in _sl_url:
                        _en_wiki_title_exact = _sl_url.split('/wiki/')[-1].replace('_', ' ')
                        from urllib.parse import unquote
                        _en_wiki_title_exact = unquote(_en_wiki_title_exact)
                        print(f"  [story_miner] Sitelink EN: '{_en_wiki_title_exact}'")
                    elif f'{language}.wikipedia.org' in _sl_url and language != 'en':
                        _local_wiki_title_exact = _sl_url.split('/wiki/')[-1].replace('_', ' ')
                        from urllib.parse import unquote
                        _local_wiki_title_exact = unquote(_local_wiki_title_exact)
                        print(f"  [story_miner] Sitelink {language.upper()}: '{_local_wiki_title_exact}'")
        except Exception as e:
            logger.info(f"story_miner: Sitelink lookup failed for {venue_qid}: {e}")

    if wikipedia_title or _en_wiki_title_exact:
        from rag_retriever import fetch_wikipedia_summary
        # LOCAL-23: Use exact sitelink title first, then fall back to provided + variants
        _en_titles = []
        if _en_wiki_title_exact:
            _en_titles.append(_en_wiki_title_exact)
        if wikipedia_title:
            _en_titles.append(wikipedia_title)
        # Add variants: with/without accents, with city disambiguator
        _base_title = wikipedia_title or _en_wiki_title_exact
        _clean_title = _base_title.replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e').replace('à', 'a').replace('ô', 'o').replace('î', 'i').replace('ç', 'c').replace('ü', 'u').replace('ö', 'o').replace('ä', 'a')
        if _clean_title != _base_title:
            _en_titles.append(_clean_title)
        # Try "Musée X" → "X Museum" style conversion
        if _base_title.lower().startswith('mus'):
            _name_part = re.sub(r'(?i)^mus[ée]+e?\s*(national[e]?\s*)?', '', _base_title).strip()
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
        if venue_name and venue_name != _base_title:
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
                _en_wiki_url = f"https://en.wikipedia.org/wiki/{_en_title.replace(' ', '_')}"
                pages.append({"url": _en_wiki_url,
                             "text": en_article, "title": f"Wikipedia EN: {_en_title}"})
                source_urls.append(_en_wiki_url)
                _page_tiers[_en_wiki_url] = 1  # Wikipedia = tier 1
                print(f"  [story_miner] Wikipedia EN: {len(en_article)} chars (title: '{_en_title}')")
                break

    # --- 3. Local-language Wikipedia (country→lang, not hardcoded "fr") ---
    if language and language != "en" and (wikipedia_title or _local_wiki_title_exact):
        _local_titles = []
        # LOCAL-23: Use exact sitelink title first
        if _local_wiki_title_exact:
            _local_titles.append(_local_wiki_title_exact)
        if wikipedia_title:
            _local_titles.append(wikipedia_title)
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
                                _page_tiers[local_url] = 1  # Local Wikipedia = tier 1
                                print(f"  [story_miner] Wikipedia {language.upper()}: {len(extract)} chars")
                                break
            except Exception as e:
                logger.warning(f"story_miner: {language.upper()} Wikipedia error for '{local_title}': {e}")

    # --- LOCAL-23: Joconde/POP for French public museums (Tier 2) ---
    _joconde_titles = []
    if language == 'fr' and venue_qid:
        _museo_code = _lookup_museo_code(venue_qid)
        if _museo_code:
            _joconde_titles = _fetch_joconde_titles(_museo_code, venue_name)
            if _joconde_titles:
                # Add Joconde text as a pseudo-page for title extraction
                _joconde_text = "\n".join(f"== {t['title']} ==" for t in _joconde_titles)
                _joconde_url = f"https://pop.culture.gouv.fr/recherche?museo={_museo_code}"
                pages.append({"url": _joconde_url, "text": _joconde_text,
                              "title": f"Joconde/POP ({_museo_code})"})
                source_urls.append(_joconde_url)
                _page_tiers[_joconde_url] = 2

    # --- Combine and extract ---
    combined_text = "\n\n".join(p["text"] for p in pages)
    
    # Extract canonical titles from combined corpus
    canonical_titles, cycle_names, theme_words = extract_canonical_titles(combined_text, venue_name)

    # LOCAL-23: Add Joconde titles directly (they're already validated by the national database)
    for jt in _joconde_titles:
        if jt['title'] and len(jt['title']) >= 3:
            canonical_titles.add(jt['title'])

    # Extract per-work context sentences
    per_work_contexts = _extract_per_work_contexts(combined_text, canonical_titles)

    # LOCAL-23: Build title_sources provenance map
    # Maps each canonical title to the source(s) where it was found + trust tier
    title_sources = {}
    for title in canonical_titles:
        title_sources[title] = []
        _norm_t = _normalize(title).lower()
        # Check which pages contain this title
        for p in pages:
            if _norm_t in _normalize(p.get('text', '')).lower():
                _url = p.get('url', '')
                _tier = _page_tiers.get(_url, 1)  # default tier 1 for wiki/official site
                title_sources[title].append({'source_url': _url, 'tier': _tier})
        # Also check Joconde titles directly
        for jt in _joconde_titles:
            if _normalize(jt['title']).lower() == _norm_t:
                title_sources[title].append({'source_url': jt['source_url'], 'tier': 2})

    # LOCAL-23: Prominence ordering (sort canonical titles by number of sources mentioning them)
    # Proxies for prominence: multi-source mentions, presence in Wikipedia, museum highlights page
    _prominence_scores = {}
    for title in canonical_titles:
        score = 0
        sources = title_sources.get(title, [])
        score += len(sources)  # More sources = more prominent
        # Bonus for Wikipedia presence (tier 1)
        if any('wikipedia.org' in s.get('source_url', '') for s in sources):
            score += 3
        # Bonus for museum highlights/oeuvres page
        if any(any(k in s.get('source_url', '').lower() 
                   for k in ('oeuvre', 'highlight', 'collection', 'masterpiece'))
               for s in sources):
            score += 2
        _prominence_scores[title] = score
    
    # Sort canonical titles by prominence (descending) — most famous first
    _sorted_titles = sorted(canonical_titles, key=lambda t: _prominence_scores.get(t, 0), reverse=True)
    # Keep as set for backward compatibility, but store ordered list separately
    canonical_titles_ordered = _sorted_titles

    print(f"  [story_miner] Corpus: {len(pages)} pages, {len(canonical_titles)} titles, "
          f"{len(_joconde_titles)} from Joconde")

    return {
        "pages": pages,
        "combined_text": combined_text,
        "canonical_titles": canonical_titles,
        "canonical_titles_ordered": canonical_titles_ordered,  # LOCAL-23: prominence-ordered
        "cycle_names": cycle_names,
        "theme_words": theme_words,
        "source_urls": source_urls,
        "per_work_contexts": per_work_contexts,
        "title_sources": title_sources,  # LOCAL-23: provenance map
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


# EN↔local bilingual word map for cross-language title matching.
# SEED map: common art terms as fallback. The primary source is SPARQL label pairs
# built dynamically per venue (see build_bilingual_map_from_sparql).
_BILINGUAL_MAP_SEED = {
    'creation': 'creation', 'man': 'homme', 'homme': 'man',
    'sacrifice': 'sacrifice', 'isaac': 'isaac',
    'moses': 'moise', 'moise': 'moses',
    'burning': 'buisson', 'bush': 'ardent',
    'prophet': 'prophete', 'prophete': 'prophet',
    'elijah': 'elie', 'elie': 'elijah',
    'jacob': 'jacob', 'wrestling': 'lutte', 'lutte': 'wrestling',
    'angel': 'ange', 'ange': 'angel',
    'angels': 'anges', 'anges': 'angels',
    'dream': 'songe', 'songe': 'dream',
    'crossing': 'traversee', 'traversee': 'crossing',
    'rainbow': 'arc en ciel', 'noah': 'noe', 'noe': 'noah',
    'paradise': 'paradis', 'paradis': 'paradise',
    'resurrection': 'resurrection',
    'king': 'roi', 'roi': 'king',
    'david': 'david', 'abraham': 'abraham',
    'three': 'trois', 'trois': 'three',
    'red': 'rouge', 'sea': 'mer', 'mer': 'sea',
    'striking': 'frappement', 'rock': 'rocher',
    'circus': 'cirque', 'cirque': 'circus',
    'blue': 'bleu', 'bleu': 'blue',
    'song': 'cantique', 'songs': 'cantiques',
    'dance': 'danse', 'danse': 'dance',
    'wave': 'vague', 'vague': 'wave',
    'nude': 'nu', 'window': 'fenetre',
}

# Active bilingual map — built per-request from SPARQL + seed
_BILINGUAL_MAP: Dict[str, str] = dict(_BILINGUAL_MAP_SEED)


def build_bilingual_map_from_sparql(works: list) -> Dict[str, str]:
    """Build bilingual word pairs from SPARQL works that have both EN and local labels.
    
    Generic: works for any language pair (fr/it/de/es) — derived from actual data.
    Returns the updated map (seed + SPARQL-derived pairs).
    """
    global _BILINGUAL_MAP
    derived = dict(_BILINGUAL_MAP_SEED)
    
    for work in works:
        label_en = work.get('label_en', '').lower()
        label_local = work.get('label_local', '').lower()
        
        if not label_en or not label_local or label_en == label_local:
            continue
        
        # Normalize: strip accents for matching
        en_words = [w for w in _normalize(label_en).split() if len(w) >= 3]
        local_words = [w for w in _normalize(label_local).split() if len(w) >= 3]
        
        # Skip stop words
        _STOPS = {'the', 'les', 'des', 'une', 'del', 'della', 'dei', 'con', 'gli', 'per',
                  'der', 'die', 'das', 'und', 'ein', 'eine', 'mit', 'von', 'den', 'dem',
                  'los', 'las', 'por', 'and', 'for', 'with', 'from'}
        en_words = [w for w in en_words if w not in _STOPS]
        local_words = [w for w in local_words if w not in _STOPS]
        
        # Pair words by position (aligned titles often have corresponding words)
        for i, ew in enumerate(en_words):
            if i < len(local_words):
                lw = local_words[i]
                # Only add if they're different (same word = cognate, already matches)
                if ew != lw and len(ew) >= 3 and len(lw) >= 3:
                    derived[ew] = lw
                    derived[lw] = ew
    
    _BILINGUAL_MAP = derived
    return derived


def _expand_bilingual(words: List[str]) -> Set[str]:
    """Expand a word list with bilingual equivalents for cross-language matching."""
    expanded = set(words)
    for w in words:
        if w in _BILINGUAL_MAP:
            equiv = _BILINGUAL_MAP[w]
            # Some equivalents are multi-word
            expanded.update(equiv.split())
    return expanded


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

        # Calculate bidirectional word overlap (with bilingual expansion for EN↔FR)
        _expanded_candidate = _expand_bilingual(_candidate_words)
        _expanded_canon = _expand_bilingual(_canon_words)
        
        fwd_matches = sum(1 for w in _candidate_words if w in _expanded_canon)
        rev_matches = sum(1 for w in _canon_words if w in _expanded_candidate)
        
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


# --- LOCAL-11: Venue-identity mining (free path — uses already-fetched corpus) ---

def extract_venue_identity(combined_text: str, venue_name: str = "") -> Dict[str, List[str]]:
    """Mine already-fetched combined_text for venue-identity facts.
    
    Targets sections deliberately excluded from exhibit-title extraction
    (Architecture, Design, Mission, History, opening summary) for concrete,
    specific "why is this place special" facts:
      - Distinctive architecture / named architect
      - Unusual design philosophy (floor plan, spatial concept)
      - Signature recurring cultural program (tea ceremonies, concerts, workshops)
      - Notable curatorial approach or founding story
    
    Returns:
        dict with categorized facts:
            architecture: [str] — e.g. "designed by Kenzo Tange on a mandala plan"
            programs: [str] — e.g. "hosts authentic Japanese tea ceremonies (Chanoyu)"
            founding: [str] — e.g. "founded by Henri Matisse who donated..."
            design: [str] — e.g. "built around a sacred Tibetan mandala floor plan"
        Empty lists if nothing specific found. Never returns generic filler.
    
    Cost: ZERO additional API calls or fetches. Mines text already in memory.
    """
    results: Dict[str, List[str]] = {
        "architecture": [],
        "programs": [],
        "founding": [],
        "design": [],
    }
    
    if not combined_text or len(combined_text) < 200:
        return results
    
    # --- Extract relevant sections from the corpus ---
    # Wikipedia-style sections: == Section == or === Section ===
    _section_re = re.compile(r'^={2,4}\s*(.+?)\s*={2,4}\s*$', re.MULTILINE)
    
    # Identity-relevant section names (these are excluded from exhibit-title extraction)
    _IDENTITY_SECTIONS = {
        'architecture', 'building', 'design', 'the building',
        'history', 'histoire', 'founding', 'creation', 'origins',
        'mission', 'about', 'overview', 'description',
        'programmes', 'programs', 'activities', 'events',
        'collections', 'collection', 'la collection',
    }
    
    # Parse sections and their text content
    sections = []
    section_starts = list(_section_re.finditer(combined_text))
    for i, match in enumerate(section_starts):
        section_name = match.group(1).strip().lower()
        start_pos = match.end()
        end_pos = section_starts[i + 1].start() if i + 1 < len(section_starts) else len(combined_text)
        section_text = combined_text[start_pos:end_pos].strip()
        if section_name in _IDENTITY_SECTIONS:
            sections.append((section_name, section_text))
    
    # Also grab the opening text (before first section header) — usually the Wikipedia lead
    if section_starts:
        _opening = combined_text[:section_starts[0].start()].strip()
    else:
        _opening = combined_text[:3000].strip()  # No sections? Use first 3000 chars
    
    # Combine identity-relevant text (opening + identity sections)
    _identity_corpus = _opening + "\n\n" + "\n\n".join(
        text for _, text in sections
    )
    
    # --- Mine for architecture facts ---
    # Look for named architects (Pritzker-winners, notable names)
    _architect_patterns = [
        # "designed by <Name>" / "conçu par <Name>"
        re.compile(r'(?:designed|conceived|created|built|constructed|conçu|réalisé|construit)\s+by\s+([A-Z][A-Za-z\u00C0-\u00FF\s\-]{3,40}?)(?:\s*[,.(]|\s+in\s+|\s+and\s+|\s+who\b)', re.IGNORECASE),
        # "<Name>, architect" / "architect <Name>"
        re.compile(r'architect[e]?\s+([A-Z][A-Za-z\u00C0-\u00FF\s\-]{5,40}?)(?:\s*[,.(]|\s+designed|\s+who\b)', re.IGNORECASE),
        re.compile(r'([A-Z][A-Za-z\u00C0-\u00FF\s\-]{5,40}?),?\s+(?:the\s+)?architect', re.IGNORECASE),
        # "architectural design by"
        re.compile(r'(?:architectural\s+)?design(?:ed)?\s+by\s+([A-Z][A-Za-z\u00C0-\u00FF\s\-]{3,40}?)(?:\s*[,.(]|\s+in\s+)', re.IGNORECASE),
    ]
    
    _found_architects = set()
    for pat in _architect_patterns:
        for m in pat.finditer(_identity_corpus):
            architect_name = m.group(1).strip().rstrip(',.')
            # Filter out generic words that aren't architect names
            _GENERIC_WORDS = {'the', 'a', 'an', 'this', 'that', 'its', 'new', 'old', 'local'}
            if (len(architect_name) >= 5 and
                len(architect_name.split()) >= 2 and
                architect_name.split()[0].lower() not in _GENERIC_WORDS):
                _found_architects.add(architect_name)
    
    # For each architect, try to get context sentence
    for architect in _found_architects:
        # Find the sentence containing this architect name
        _sent = _extract_identity_sentence(_identity_corpus, architect)
        if _sent:
            results["architecture"].append(_sent)
    
    # --- Mine for design philosophy ---
    _design_patterns = [
        # Mandala, sacred geometry, floor plan descriptions
        re.compile(r'([^.]*(?:mandala|sacred\s+geometry|floor\s*plan|spatial\s+concept|circular\s+layout|octagonal|hexagonal|labyrinth)[^.]*\.)', re.IGNORECASE),
        # Specific architectural styles or concepts
        re.compile(r'([^.]*(?:inspired\s+by|modeled\s+(?:on|after)|based\s+on\s+(?:a|the)\s+)[^.]*(?:temple|monastery|palace|garden|pagoda|mosque|cathedral)[^.]*\.)', re.IGNORECASE),
        # Light/space/material philosophy
        re.compile(r'([^.]*(?:natural\s+light|deliberately|designed\s+to\s+(?:evoke|create|reflect)|architectural\s+philosophy)[^.]*\.)', re.IGNORECASE),
    ]
    
    for pat in _design_patterns:
        for m in pat.finditer(_identity_corpus):
            sentence = m.group(1).strip()
            if len(sentence) >= 30 and len(sentence) <= 300:
                # Skip if it's too generic
                if not _is_generic_filler(sentence):
                    results["design"].append(sentence)
    
    # --- Mine for signature programs ---
    _program_patterns = [
        # Tea ceremonies, concerts, workshops, performances
        re.compile(r'([^.]*(?:tea\s+ceremon|chanoyu|concert[s]?\s+(?:are|were|is)|hosts?\s+(?:regular|weekly|monthly|annual)|signature\s+program|flagship\s+event|recurring\s+(?:event|program|performance)|live\s+performance)[^.]*\.)', re.IGNORECASE),
        # "offers|presents|features <specific program>"
        re.compile(r'([^.]*(?:museum|venue|center|centre|gallery|palais|palazzo)\s+(?:also\s+)?(?:offers|presents|features|hosts|organizes|includes)\s+[^.]*(?:workshop|concert|ceremony|performance|demonstration|festival|residenc)[^.]*\.)', re.IGNORECASE),
    ]
    
    for pat in _program_patterns:
        for m in pat.finditer(_identity_corpus):
            sentence = m.group(1).strip()
            if len(sentence) >= 25 and len(sentence) <= 300:
                if not _is_generic_filler(sentence):
                    results["programs"].append(sentence)
    
    # --- Mine for founding story ---
    _founding_patterns = [
        # "founded by / established by / created by <person> in <year>"
        re.compile(r'([^.]*(?:founded|established|created|inaugurated|opened)\s+(?:by|in)\s+[^.]*\d{4}[^.]*\.)', re.IGNORECASE),
        # "donated (his/her/their) collection"
        re.compile(r'([^.]*(?:donat(?:ed|ion)|bequest(?:ed)?|gift(?:ed)?)\s+(?:his|her|their|the)\s+(?:entire\s+)?(?:collection|works|paintings)[^.]*\.)', re.IGNORECASE),
        # Specific founding intent phrases
        re.compile(r'([^.]*(?:wanted\s+to\s+create|vision\s+was|intended\s+(?:as|to)|purpose\s+was|conceived\s+as)[^.]*\.)', re.IGNORECASE),
    ]
    
    for pat in _founding_patterns:
        for m in pat.finditer(_identity_corpus):
            sentence = m.group(1).strip()
            if len(sentence) >= 30 and len(sentence) <= 300:
                if not _is_generic_filler(sentence):
                    results["founding"].append(sentence)
    
    # --- Deduplicate and cap ---
    for key in results:
        # Deduplicate near-identical sentences
        seen = set()
        unique = []
        for sent in results[key]:
            _norm_sent = re.sub(r'\s+', ' ', sent.lower().strip())
            if _norm_sent not in seen:
                seen.add(_norm_sent)
                unique.append(sent)
        results[key] = unique[:3]  # Cap at 3 facts per category
    
    # Report
    _total = sum(len(v) for v in results.values())
    if _total > 0:
        _summary = {k: len(v) for k, v in results.items() if v}
        print(f"  [LOCAL-11] Venue-identity mining: {_total} facts found {_summary}")
    else:
        print(f"  [LOCAL-11] Venue-identity mining: no specific facts found in corpus")
    
    return results


def _extract_identity_sentence(corpus: str, keyword: str) -> Optional[str]:
    """Extract the most informative sentence containing the keyword."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', corpus)
    for sent in sentences:
        if keyword.lower() in sent.lower() and len(sent) >= 30 and len(sent) <= 300:
            # Prefer sentences that also contain verbs of creation/design
            _design_verbs = ('design', 'built', 'creat', 'conceiv', 'construct',
                           'architect', 'commission', 'plan', 'inaugurat')
            if any(v in sent.lower() for v in _design_verbs):
                return sent.strip()
    # Fallback: any sentence with the keyword
    for sent in sentences:
        if keyword.lower() in sent.lower() and len(sent) >= 30 and len(sent) <= 300:
            return sent.strip()
    return None


def _is_generic_filler(sentence: str) -> bool:
    """Detect generic filler that adds no specific identity value."""
    _FILLER_PATTERNS = [
        r'wonderful\s+museum',
        r'many\s+treasures',
        r'rich\s+collection',
        r'wide\s+variety',
        r'something\s+for\s+everyone',
        r'world[\s-]class',
        r'must[\s-]see',
        r'not\s+to\s+be\s+missed',
        r'well\s+worth\s+a\s+visit',
        r'important\s+(?:museum|institution|cultural)',
        r'one\s+of\s+the\s+(?:most|finest|best)',
    ]
    _lower = sentence.lower()
    return any(re.search(p, _lower) for p in _FILLER_PATTERNS)


def format_venue_identity_for_prompt(identity_facts: Dict[str, List[str]], venue_name: str = "") -> str:
    """Format extracted venue-identity facts into a concise prompt injection.
    
    Returns a short paragraph suitable for injecting into the prolog prompt,
    or empty string if no usable facts were found.
    """
    all_facts = []
    
    # Prioritize: architecture > design > programs > founding
    for key in ("architecture", "design", "programs", "founding"):
        for fact in identity_facts.get(key, []):
            all_facts.append(fact)
    
    if not all_facts:
        return ""
    
    # Cap at 3 most interesting facts to avoid overwhelming the prompt
    _selected = all_facts[:3]
    
    _venue_label = venue_name.split(',')[0].strip() if venue_name else "This venue"
    
    return (
        f"Venue-specific identity facts about {_venue_label} (weave 1-2 of these "
        f"concretely into the introduction — do NOT use generic praise):\n"
        + "\n".join(f"- {fact}" for fact in _selected)
    )


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
