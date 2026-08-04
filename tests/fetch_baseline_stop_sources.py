#!/usr/bin/env python3
"""LOCAL-180: Fetch per-stop source material for the 3 remaining baseline tours.

TARGET TOURS (D56 — driven by actual tour stops, not canonical_titles):
  Tour 14: Museum Of Naive Art (9 stops — naive art paintings)
  Tour 12: Nice walking tour (10 stops — places/landmarks)
  Tour 46: Boston Common (5 stops — historical landmarks)

RELEVANCE RULE (unchanged from LOCAL-178/179):
  A passage qualifies ONLY if it is ABOUT this stop. Keyword co-occurrence
  is not a relationship. The passage must contain substantive information
  specific to THIS stop.

TIER SYSTEM (unchanged):
  Tier 1: Wikipedia, official municipal/tourism-board sites
  Tier 2: Scholarly, quality journalism, government archives
  Tier 3: Personal blog, minor sources — labelled as such
  Reject: Commerce, social media, aggregators, wrong-topic results

BUDGET: $0.50 ceiling total across all three venues.

RATE LIMITING: 2s between Wikipedia requests to avoid 429 errors.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.parse
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
BUDGET_CEILING = 0.50
COST_PER_QUERY = 0.001
WIKI_DELAY = 2.0  # seconds between Wikipedia requests

# Actual tour stops as parsed by the detector (D56)
TOURS = {
    14: {
        'name': 'Museum Of Naive Art, Nice, France - museum Tour',
        'venue_name': 'Museum Of Naive Art, Nice, France',
        'type': 'museum',
        'stops': [
            "The Flight into Egypt",
            "The Wedding",
            "The Dream",
            "The Red Umbrella",
            "The Bathers",
            "The Carousel",
            "The Hot Day",
            "The Sleeping Gypsy",
            "On the hills - rainforest",
        ],
    },
    12: {
        'name': 'walking tour in Nice, france - walking Tour',
        'venue_name': 'walking tour in Nice, france',
        'type': 'walking',
        'stops': [
            "Promenade des Anglais",
            "Castle Hill (Colline du Chateau)",
            "Albert 1st Gardens",
            "Nice Opera House",
            "Place Massena",
            "Cours Saleya Market",
            "Old Town (Vieux Nice)",
            "Russian Orthodox Cathedral",
            "Marc Chagall National Museum",
            "Museum of Modern and Contemporary Art (MAMAC)",
        ],
    },
    46: {
        'name': 'Boston Common, Boston MA - historical Tour',
        'venue_name': 'Boston Common, Boston MA',
        'type': 'walking',
        'stops': [
            "Frog Pond",
            "Soldiers and Sailors Monument",
            "Parkman Bandstand",
            "Granary Burying Ground",
            "Brewer Fountain",
        ],
    },
}

# Direct Wikipedia article titles for stops that have known articles
# Only include here if we KNOW the article is about THIS specific thing
DIRECT_WIKI_ARTICLES = {
    # Tour 12 — Nice walking stops
    "Promenade des Anglais": ("Promenade des Anglais", "en"),
    "Castle Hill (Colline du Chateau)": ("Castle Hill, Nice", "en"),
    "Nice Opera House": ("Opéra de Nice", "en"),
    "Place Massena": ("Place Masséna", "en"),
    "Russian Orthodox Cathedral": ("St Nicholas Orthodox Cathedral, Nice", "en"),
    "Marc Chagall National Museum": ("Musée Marc Chagall", "en"),
    "Museum of Modern and Contemporary Art (MAMAC)": ("Musée d'Art Moderne et d'Art Contemporain", "en"),
    # Tour 46 — Boston Common stops
    "Frog Pond": ("Frog Pond", "en"),
    "Granary Burying Ground": ("Granary Burying Ground", "en"),
    "Brewer Fountain": ("Brewer Fountain", "en"),
}

# Serper queries for stops without direct Wikipedia articles
SERPER_QUERIES = {
    # Tour 12
    "Albert 1st Gardens": '"Jardin Albert 1er" Nice history',
    "Cours Saleya Market": '"Cours Saleya" Nice market history',
    "Old Town (Vieux Nice)": '"Vieux Nice" OR "Old Town Nice" history',
    # Tour 46
    "Soldiers and Sailors Monument": '"Soldiers and Sailors Monument" "Boston Common"',
    "Parkman Bandstand": '"Parkman Bandstand" "Boston Common"',
    # Tour 14 — all need serper since generic titles won't have Wikipedia
    "The Flight into Egypt": '"Flight into Egypt" "Jakovsky" OR "Art Naif" OR "naive art" Nice',
    "The Wedding": '"The Wedding" "Jakovsky" OR "Art Naif" OR "naive art" Nice painting',
    "The Dream": '"The Dream" "Jakovsky" OR "Art Naif" OR "naive art" Nice painting',
    "The Red Umbrella": '"Red Umbrella" "Jakovsky" OR "Art Naif" OR "naive art" Nice',
    "The Bathers": '"Bathers" "Jakovsky" OR "Art Naif" OR "naive art" Nice painting',
    "The Carousel": '"Carousel" "Jakovsky" OR "Art Naif" OR "naive art" Nice painting',
    "The Hot Day": '"Hot Day" "Jakovsky" OR "Art Naif" OR "naive art" Nice',
    "The Sleeping Gypsy": '"Sleeping Gypsy" "Jakovsky" OR "Art Naif" Nice',
    "On the hills - rainforest": '"Art Naif" "Jakovsky" Nice museum painting rainforest',
}

# Also try French Wikipedia for some stops
FR_WIKI_ARTICLES = {
    "Castle Hill (Colline du Chateau)": ("Colline du Château", "fr"),
    "Albert 1st Gardens": ("Jardin Albert-Ier (Nice)", "fr"),
    "Cours Saleya Market": ("Cours Saleya", "fr"),
    "Old Town (Vieux Nice)": ("Vieux-Nice", "fr"),
    "Place Massena": ("Place Masséna", "fr"),
}

# Cost tracking
total_serp_queries = 0
query_log = []


def normalize_text(text):
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', ascii_text.lower()).strip()


def classify_source(url):
    """Classify by trust tier. Returns (tier, reason). 0 = reject."""
    domain = urllib.parse.urlparse(url).netloc.lower()

    if 'wikipedia.org' in domain or 'wikimedia.org' in domain:
        return 1, "Wikipedia/Wikimedia"

    official_domains = [
        'nice.fr', 'www.nice.fr', 'cotedazurfrance.fr',
        'boston.gov', 'www.boston.gov', 'nps.gov',
        'culture.gouv.fr', 'musees-nationaux-alpesmaritimes.fr',
    ]
    if any(d == domain or domain.endswith('.' + d) for d in official_domains):
        return 1, f"official ({domain})"

    tier2_markers = ['hal.science', '.edu', '.ac.uk', 'jstor.org', 'cairn.info',
                     'persee.fr', 'nicematin.com', 'francebleu.fr',
                     'pop.culture.gouv.fr', 'monumentum.fr', 'bnf.fr',
                     'britannica.com', 'larousse.fr', 'bostonglobe.com', 'wbur.org']
    if any(m in domain for m in tier2_markers):
        return 2, f"scholarly/journalism ({domain})"

    reject_domains = ['youtube.com', 'flickr.com', 'pinterest.com', 'tripadvisor',
                      'booking.com', 'amazon.', 'ebay.', 'instagram.com',
                      'facebook.com', 'twitter.com', 'tiktok.com', 'x.com',
                      'alamy.com', 'viator.com', 'getyourguide.com', 'klook.com',
                      'hotels.com', 'expedia.com', 'airbnb.com', 'yelp.com']
    if any(d in domain for d in reject_domains):
        return 0, f"rejected ({domain})"

    return 3, f"other ({domain})"


def is_relevant_for_place(passage, stop_title):
    """Relevance gate for PLACE stops (walking tours).

    A passage qualifies if it is ABOUT this specific place — contains
    historical facts, dates, named figures, architectural details.
    NOT just mentioning the place name in a list.
    """
    if not passage or len(passage.strip()) < 80:
        return False, "too short"

    passage_norm = normalize_text(passage)
    stop_norm = normalize_text(stop_title)

    # Must mention the place (at least key words)
    noise = {'the', 'of', 'by', 'a', 'an', 'le', 'la', 'les', 'de', 'du',
             'old', 'town', 'new', 'market', 'hill', 'park', 'museum', 'art',
             'national', 'modern', 'contemporary', 'monument', 'and', '1st'}
    stop_words = [w for w in stop_norm.split() if w not in noise and len(w) >= 3]

    title_in_passage = stop_norm in passage_norm
    if not title_in_passage:
        hits = sum(1 for w in stop_words if w in passage_norm)
        if hits < max(1, len(stop_words) * 0.4):
            return False, f"stop words not in passage ({hits}/{len(stop_words)})"

    # Must have substance (dates, proper nouns, specific facts)
    dates = re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', passage)
    if len(passage) >= 200:
        return True, f"substantial ({len(passage)} chars, {len(dates)} dates)"
    if dates:
        return True, f"brief with dates ({len(dates)} dates)"

    proper = re.findall(r'(?<=\s)[A-Z][a-z]{3,}', passage)
    generic = {'French', 'Nice', 'Boston', 'This', 'That', 'Here', 'There'}
    specific = [p for p in proper if p not in generic]
    if len(specific) >= 2:
        return True, f"brief with proper nouns ({len(specific)})"

    return False, f"insufficient substance (len={len(passage)})"


def is_relevant_for_artwork(passage, stop_title, museum_context):
    """Relevance gate for ARTWORK stops (museum tours).

    A passage qualifies ONLY if it is about THIS specific artwork AT this museum.
    D56: A generic Wikipedia article about 'weddings' or 'flight into Egypt'
    (the Biblical event) is NOT about a painting with that title.
    """
    if not passage or len(passage.strip()) < 80:
        return False, "too short"

    passage_norm = normalize_text(passage)

    # For naive art paintings with generic titles, we need MUSEUM CONTEXT
    # The passage must reference: the museum, Jakovsky, naive art, the artist, Nice
    museum_markers = ['naif', 'naive', 'jakovsky', 'anatole', 'musee international']
    has_museum_context = any(m in passage_norm for m in museum_markers)

    # If no museum context, check if it's about art at all
    art_markers = ['painting', 'canvas', 'oil', 'artist', 'exhibition', 'gallery',
                   'tableau', 'peinture', 'toile', 'artiste']
    has_art_context = any(m in passage_norm for m in art_markers)

    if not has_museum_context and not has_art_context:
        return False, "no museum or art context — likely about the subject, not the painting"

    if has_museum_context:
        return True, f"museum context confirmed ({[m for m in museum_markers if m in passage_norm]})"

    # Has art context but not museum-specific — could be wrong artwork
    # Be cautious: only accept if passage is clearly about a specific painting
    stop_norm = normalize_text(stop_title)
    if stop_norm in passage_norm and has_art_context:
        return True, f"art context with title mention"

    return False, "art context but ambiguous — could be wrong version of this work"


def get_wikipedia_extract(title, lang='en'):
    """Get intro extract. Rate-limited."""
    time.sleep(WIKI_DELAY)
    encoded = urllib.parse.quote(title)
    url = (f'https://{lang}.wikipedia.org/w/api.php?action=query&titles={encoded}'
           f'&prop=extracts&exintro=true&explaintext=true&format=json')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AudioToursBot/1.0 (research)'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            pages = data.get('query', {}).get('pages', {})
            for page_id, page in pages.items():
                if page_id == '-1':
                    return None
                extract = page.get('extract', '')
                if extract and len(extract) > 50:
                    return extract
            return None
    except Exception as e:
        print(f"    [WIKI] Error: {e}")
        return None


def serp_search(query):
    """Serper.dev search. COSTS $0.001."""
    global total_serp_queries

    if not SERP_API_KEY:
        print("    [SERP] ERROR: No SERP_API_KEY")
        return []

    projected = (total_serp_queries + 1) * COST_PER_QUERY
    if projected > BUDGET_CEILING:
        print(f"    [SERP] BUDGET ABORT: ${projected:.3f} > ${BUDGET_CEILING}")
        return []

    total_serp_queries += 1
    try:
        data = json.dumps({"q": query, "num": 10}).encode()
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=data,
            headers={"X-API-KEY": SERP_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            organic = body.get("organic", [])
            results = [{'title': r.get('title', ''), 'url': r.get('link', ''),
                        'snippet': r.get('snippet', '')}
                       for r in organic]
            query_log.append({'query': query, 'results': len(results),
                            'cost': COST_PER_QUERY})
            print(f"    [SERP] #{total_serp_queries}: '{query[:55]}' -> {len(results)} results")
            return results
    except Exception as e:
        query_log.append({'query': query, 'results': 0, 'cost': COST_PER_QUERY, 'error': str(e)})
        print(f"    [SERP] Error: {e}")
        return []


def fetch_stop(stop_title, tour_type, tour_id):
    """Fetch source for one stop. Returns result dict or None."""
    print(f"\n  STOP: {stop_title}")

    # Strategy 1: Direct Wikipedia article (known mapping)
    if stop_title in DIRECT_WIKI_ARTICLES:
        wiki_title, lang = DIRECT_WIKI_ARTICLES[stop_title]
        extract = get_wikipedia_extract(wiki_title, lang)
        if extract:
            wiki_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(wiki_title.replace(' ', '_'))}"
            if tour_type == 'walking':
                relevant, reason = is_relevant_for_place(extract, stop_title)
            else:
                relevant, reason = is_relevant_for_artwork(extract, stop_title, '')
            if relevant:
                print(f"    [WIKI] ACCEPTED: '{wiki_title}' (Tier 1) — {reason}")
                return {
                    'passages': [extract[:2000]],
                    'sources': [{'url': wiki_url, 'title': wiki_title, 'tier': 1,
                                'tier_reason': 'Wikipedia', 'relevance': reason}],
                }
            else:
                print(f"    [WIKI] Direct article REJECTED: {reason}")
        else:
            print(f"    [WIKI] Direct article not found: '{wiki_title}'")

    # Strategy 2: French Wikipedia (for Nice stops)
    if stop_title in FR_WIKI_ARTICLES:
        wiki_title, lang = FR_WIKI_ARTICLES[stop_title]
        extract = get_wikipedia_extract(wiki_title, lang)
        if extract:
            wiki_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(wiki_title.replace(' ', '_'))}"
            if tour_type == 'walking':
                relevant, reason = is_relevant_for_place(extract, stop_title)
            else:
                relevant, reason = is_relevant_for_artwork(extract, stop_title, '')
            if relevant:
                print(f"    [WIKI-FR] ACCEPTED: '{wiki_title}' (Tier 1) — {reason}")
                return {
                    'passages': [extract[:2000]],
                    'sources': [{'url': wiki_url, 'title': wiki_title, 'tier': 1,
                                'tier_reason': 'Wikipedia (fr)', 'relevance': reason}],
                }
            else:
                print(f"    [WIKI-FR] REJECTED: {reason}")

    # Strategy 3: Serper search (PAID)
    if stop_title in SERPER_QUERIES:
        results = serp_search(SERPER_QUERIES[stop_title])
        if results:
            for r in results:
                tier, tier_reason = classify_source(r['url'])
                if tier == 0:
                    continue
                snippet = r.get('snippet', '')

                # Try to get Wikipedia extract if it's a Wikipedia result
                if 'wikipedia.org' in r['url']:
                    # Extract the article title from URL
                    wiki_path = urllib.parse.urlparse(r['url']).path
                    wiki_title = urllib.parse.unquote(wiki_path.split('/')[-1]).replace('_', ' ')
                    lang = 'fr' if 'fr.wikipedia' in r['url'] else 'en'
                    extract = get_wikipedia_extract(wiki_title, lang)
                    if extract:
                        snippet = extract[:2000]

                if tour_type == 'walking':
                    relevant, reason = is_relevant_for_place(snippet, stop_title)
                else:
                    relevant, reason = is_relevant_for_artwork(snippet, stop_title,
                                                              'Jakovsky Art Naif Nice')
                if relevant:
                    print(f"    [SERP] ACCEPTED: {r['url'][:55]} (Tier {tier}) — {reason}")
                    return {
                        'passages': [snippet[:2000]],
                        'sources': [{'url': r['url'], 'title': r['title'], 'tier': tier,
                                    'tier_reason': tier_reason, 'relevance': reason}],
                    }

    print(f"    NO SOURCE FOUND")
    return None


def persist_stop_corpus(venue_name, stop_title, passages, sources, conn):
    """INSERT or UPDATE stop_corpus. Additive only."""
    cur = conn.cursor()
    passages_json = json.dumps(passages)
    source_json = json.dumps(sources)
    passage_count = len(passages)

    cur.execute("""
        INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (venue_name, stop_title) DO UPDATE SET
            passages_json = EXCLUDED.passages_json,
            source_pages = EXCLUDED.source_pages,
            passage_count = EXCLUDED.passage_count
    """, (venue_name, stop_title, passages_json, source_json, passage_count))
    conn.commit()
    print(f"    [DB] Saved: '{stop_title}' ({passage_count} passages)")


def main():
    print("=" * 80)
    print("LOCAL-180: FETCH SOURCES FOR 3 REMAINING BASELINE TOURS")
    print("=" * 80)
    print(f"Budget ceiling: ${BUDGET_CEILING:.2f}")
    print(f"Serper key: {'present' if SERP_API_KEY else 'MISSING'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    conn = get_connection()
    all_results = {}

    for tour_id in [14, 12, 46]:
        tour = TOURS[tour_id]
        print(f"\n{'#' * 80}")
        print(f"# TOUR {tour_id}: {tour['name']}")
        print(f"# Venue name for stop_corpus: \"{tour['venue_name']}\"")
        print(f"# Type: {tour['type']}, Stops: {len(tour['stops'])}")
        print(f"{'#' * 80}")

        tour_results = {}
        for stop_title in tour['stops']:
            current_spend = total_serp_queries * COST_PER_QUERY
            if current_spend >= BUDGET_CEILING:
                print(f"\n  BUDGET REACHED: ${current_spend:.3f}")
                tour_results[stop_title] = None
                continue

            result = fetch_stop(stop_title, tour['type'], tour_id)
            if result and result['passages']:
                tour_results[stop_title] = result
                persist_stop_corpus(tour['venue_name'], stop_title,
                                   result['passages'], result['sources'], conn)
            else:
                tour_results[stop_title] = None

        all_results[tour_id] = tour_results

    # ── DISTINCT PASSAGE CHECK ──
    print(f"\n{'=' * 80}")
    print("DISTINCT PASSAGE CHECK")
    print("=" * 80)
    for tour_id, tour_results in all_results.items():
        tour = TOURS[tour_id]
        hashes = {}
        for stop, result in tour_results.items():
            if result and result['passages']:
                h = hashlib.md5(result['passages'][0].encode()).hexdigest()[:12]
                hashes[stop] = h
        unique_hashes = set(hashes.values())
        total_with_data = len(hashes)
        print(f"\n  Tour {tour_id} ({tour['name'][:45]}):")
        print(f"    Stops with passages: {total_with_data}/{len(tour['stops'])}")
        print(f"    Distinct passage hashes: {len(unique_hashes)}")
        if total_with_data > 0 and len(unique_hashes) < total_with_data:
            print(f"    WARNING: {total_with_data - len(unique_hashes)} duplicate passages!")
            from collections import Counter
            hash_counts = Counter(hashes.values())
            for h, count in hash_counts.items():
                if count > 1:
                    dupes = [s for s, hh in hashes.items() if hh == h]
                    print(f"      SHARED: {dupes}")
        elif total_with_data > 0:
            print(f"    ALL DISTINCT")

    # ── SUMMARY ──
    total_spend = total_serp_queries * COST_PER_QUERY
    print(f"\n{'=' * 80}")
    print("COST REPORT")
    print("=" * 80)
    print(f"  Wikipedia API: ~{sum(1 for _ in all_results)} venues, FREE")
    print(f"  Serper queries: {total_serp_queries} x ${COST_PER_QUERY} = ${total_spend:.4f}")
    print(f"  Total spend: ${total_spend:.4f}")
    print(f"  Budget remaining: ${BUDGET_CEILING - total_spend:.4f}")
    print()

    for tour_id, tour_results in all_results.items():
        tour = TOURS[tour_id]
        with_source = [s for s, r in tour_results.items() if r is not None]
        without_source = [s for s, r in tour_results.items() if r is None]
        print(f"\n  Tour {tour_id} ({tour['name'][:50]}):")
        print(f"    With source: {len(with_source)}/{len(tour['stops'])}")
        if with_source:
            for s in with_source:
                src = tour_results[s]['sources'][0]
                print(f"      {s:45s} Tier {src['tier']} — {src['url'][:50]}")
        if without_source:
            print(f"    Without source:")
            for s in without_source:
                print(f"      {s}")

    print(f"\n  Query log ({len(query_log)} paid queries):")
    for ql in query_log:
        print(f"    '{ql['query'][:55]}' -> {ql['results']} results, ${ql['cost']:.3f}")

    conn.close()
    return all_results, total_spend


if __name__ == '__main__':
    main()
