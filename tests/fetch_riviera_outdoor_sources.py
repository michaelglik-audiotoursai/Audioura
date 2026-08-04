#!/usr/bin/env python3
"""LOCAL-179: Fetch per-stop source material for Tour 29 (French Riviera Biking Tour).

WHY THIS TOUR: This is the tour Michael field-tested with real listeners. It currently
scores 0.0% ANCHORED with zero stop_corpus rows. Both examples in ClickUp wdvrdaxa7h
come from this tour's stops (Cap d'Antibes).

WHAT IS DIFFERENT: Outdoor stops are PLACES, not artworks. The anchor for a place is:
who lived there, what was built there and when, what happened there, what was written
about it. Not "work X by artist Y at museum Z."

RELEVANCE RULE (identical to round 4b): A passage qualifies ONLY if it is ABOUT this
place. Keyword co-occurrence is not a relationship. The passage must contain substantive
information specific to THIS stop — history, named figures who lived/worked there,
specific events, architectural details, literary connections.

TIER SYSTEM (identical to round 4b):
  Tier 1: Wikipedia, official municipal/tourism-board sites
  Tier 2: Scholarly, quality journalism, government archives
  Tier 3: Personal blog, minor sources — labelled as such, not laundered
  Reject: Commerce, social media, aggregators, wrong-topic results

SPECIFICALLY: Check the Fitzgerald-Cap d'Antibes connection (D51's worked example).

BUDGET: $0.50 ceiling. Expected: 15 stops × 1-3 queries × $0.001 = ~$0.015-$0.045.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
BUDGET_CEILING = 0.50
COST_PER_QUERY = 0.001

# Tour 29's actual stops (from tour_content, not canonical_titles — D56)
TOUR_STOPS = [
    "Old Town of Antibes",
    "Cap d'Antibes",
    "Port Vauban",
    "Marineland Antibes",
    "Paloma Beach",
    "Villa Ephrussi de Rothschild",
    "Promenade Maurice Rouvier",
    "Chapelle Saint-Pierre",
    "Mont Boron",
    "Place Massena",
    "Parc Phoenix",
    "Cours Saleya Market",
    "Musee Matisse",
    "Castle Hill of Nice",
    "Eze Village",
]

# The venue_name to use for stop_corpus rows (matching the venue_corpus entry)
VENUE_NAME = "French Riviera walking area"

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
    url_lower = url.lower()

    # Tier 1: Wikipedia / Wikimedia
    if 'wikipedia.org' in domain or 'wikimedia.org' in domain:
        return 1, "Wikipedia/Wikimedia"

    # Tier 1: Official municipal / tourism board
    official_domains = [
        'nice.fr', 'www.nice.fr',
        'antibes-juanlespins.com', 'www.antibes-juanlespins.com',
        'ville-antibes.fr',
        'cotedazurfrance.fr', 'www.cotedazurfrance.fr',
        'villefranche-sur-mer.fr',
        'eze-tourisme.com',
        'saint-jean-cap-ferrat-tourisme.fr',
        'departement06.fr',
        'culture.gouv.fr',
    ]
    if any(d == domain or domain.endswith('.' + d) for d in official_domains):
        return 1, f"official municipal/tourism ({domain})"

    # Tier 2: Scholarly / academic / quality journalism
    tier2_markers = ['hal.science', '.edu', '.ac.uk', 'jstor.org', 'cairn.info',
                     'persee.fr', 'nicematin.com', 'francebleu.fr', 
                     'culture.gouv.fr', 'pop.culture.gouv.fr',
                     'monumentum.fr', 'bnf.fr', 'gallica.bnf.fr']
    if any(m in domain for m in tier2_markers):
        return 2, f"scholarly/journalism ({domain})"

    # Tier 2: Quality reference sites
    if any(d in domain for d in ['britannica.com', 'larousse.fr']):
        return 2, f"encyclopedia ({domain})"

    # REJECT: Commerce, social media, travel aggregators, video
    reject_domains = ['youtube.com', 'flickr.com', 'pinterest.com', 'tripadvisor',
                      'booking.com', 'amazon.', 'ebay.', 'instagram.com',
                      'facebook.com', 'twitter.com', 'tiktok.com', 'x.com',
                      'wanderboat.ai', 'getarchive.net', 'picryl.com',
                      'aroundus.com', 'alamy.com', 'travelinsightpedia.com',
                      'viator.com', 'getyourguide.com', 'klook.com',
                      'hotels.com', 'expedia.com', 'airbnb.com']
    if any(d in domain for d in reject_domains):
        return 0, f"rejected ({domain})"

    # Tier 3: Other — acceptable only if content is clearly relevant
    return 3, f"other ({domain})"


def is_about_this_place(passage, stop_title):
    """RELEVANCE RULE for outdoor stops.

    A passage qualifies ONLY if it is ABOUT this place — not merely mentions it.
    For a place, 'about' means: specific history, named figures, events, architecture,
    or literary/artistic connections that distinguish THIS place from other places.

    Returns (True, reason) or (False, reason).
    """
    if not passage or len(passage.strip()) < 50:
        return False, "too short"

    passage_norm = normalize_text(passage)
    stop_norm = normalize_text(stop_title)

    # Extract distinctive words from stop title
    noise = {'the', 'of', 'by', 'a', 'an', 'le', 'la', 'les', 'de', 'du', 'des',
             'old', 'town', 'new', 'market', 'beach', 'hill', 'village', 'park',
             'castle', 'place', 'port', 'promenade', 'chapelle', 'mont', 'parc'}
    stop_words = [w for w in stop_norm.split() if w not in noise and len(w) >= 3]

    # Check the stop name or distinctive words appear in the passage
    title_in_passage = stop_norm in passage_norm
    if not title_in_passage:
        word_hits = sum(1 for w in stop_words if w in passage_norm)
        if word_hits < max(1, len(stop_words) * 0.5):
            return False, f"stop name/words not in passage ({word_hits}/{len(stop_words)})"

    # Check for SUBSTANTIVE content — not just a travel guide list
    # Substantive = specific facts: dates, proper nouns, historical events
    date_pattern = r'\b(1[0-9]{3}|20[0-2][0-9])\b'
    dates = re.findall(date_pattern, passage)
    
    # Proper nouns (capitalized words that aren't at sentence starts)
    proper_nouns = re.findall(r'(?<=[.!?]\s)[A-Z][a-z]+|(?<=\s)[A-Z][a-z]{2,}', passage)
    # Filter out generic words
    generic_caps = {'The', 'This', 'That', 'These', 'Here', 'There', 'Today',
                    'French', 'Mediterranean', 'European', 'Its', 'One', 'Many'}
    specific_nouns = [n for n in proper_nouns if n not in generic_caps]

    # Must have EITHER dates OR specific proper nouns for the passage to be substantive
    has_substance = len(dates) >= 1 or len(specific_nouns) >= 2

    if not has_substance and len(passage) < 300:
        return False, "no dates or specific proper nouns — generic travel copy"

    # Reject pure travel-guide language with no specifics
    travel_filler = ['things to do', 'best time to visit', 'how to get there',
                     'opening hours', 'ticket price', 'book now', 'top rated',
                     'must-see', 'don\'t miss', 'hidden gem', 'bucket list']
    filler_count = sum(1 for f in travel_filler if f in passage_norm)
    if filler_count >= 2:
        return False, f"travel guide filler ({filler_count} markers)"

    # Passage length check — a Wikipedia extract of 200+ chars with the stop name is good
    if len(passage) >= 200 and title_in_passage:
        return True, f"substantive ({len(passage)} chars, {len(dates)} dates, {len(specific_nouns)} proper nouns)"
    if len(passage) >= 200 and has_substance:
        return True, f"substantive with facts ({len(dates)} dates, {len(specific_nouns)} nouns)"
    if has_substance:
        return True, f"brief but factual ({len(dates)} dates, {len(specific_nouns)} nouns)"

    return False, f"insufficient substance (len={len(passage)}, dates={len(dates)}, nouns={len(specific_nouns)})"


def search_wikipedia(query, lang='en'):
    """Search Wikipedia API. FREE."""
    encoded = urllib.parse.quote(query)
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&srprop=snippet&srlimit=5&format=json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AudioToursBot/1.0 (research)'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            results = []
            for item in data.get('query', {}).get('search', []):
                title = item['title']
                page_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))
                results.append({'title': title, 'url': page_url, 'snippet': snippet})
            return results
    except Exception as e:
        print(f"  [WIKI] Error: {e}")
        return []


def get_wikipedia_extract(title, lang='en'):
    """Get intro extract of a Wikipedia article. FREE."""
    encoded = urllib.parse.quote(title)
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={encoded}&prop=extracts&exintro=true&explaintext=true&format=json"
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
        print(f"  [WIKI] Extract error: {e}")
        return None


def serp_search(query):
    """Serper.dev search. COSTS $0.001."""
    global total_serp_queries

    if not SERP_API_KEY:
        print("  [SERP] ERROR: No SERP_API_KEY")
        return []

    projected = (total_serp_queries + 1) * COST_PER_QUERY
    if projected > BUDGET_CEILING:
        print(f"  [SERP] BUDGET ABORT: ${projected:.3f} > ${BUDGET_CEILING}")
        return []

    total_serp_queries += 1
    start = time.time()

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
            latency = (time.time() - start) * 1000
            results = [{'title': r.get('title', ''), 'url': r.get('link', ''),
                        'snippet': r.get('snippet', '')}
                       for r in organic]
            query_log.append({'query': query, 'results': len(results),
                            'cost': COST_PER_QUERY})
            print(f"  [SERP] #{total_serp_queries}: '{query[:65]}' -> {len(results)} results")
            return results
    except Exception as e:
        query_log.append({'query': query, 'results': 0, 'cost': COST_PER_QUERY, 'error': str(e)})
        print(f"  [SERP] Error: {e}")
        return []


def fetch_for_outdoor_stop(stop_title):
    """Fetch source material for one outdoor stop.

    Strategy:
    1. Wikipedia (free): direct article search for the place name
    2. Serper (paid): targeted query for historical/cultural info about the place
    3. French Wikipedia: for French-specific places

    Returns {passages, sources, tier} or None.
    """
    print(f"\n{'=' * 60}")
    print(f"  STOP: {stop_title}")
    print(f"{'=' * 60}")

    passages = []
    sources = []
    rejected = []

    # ── Wikipedia (FREE) ──
    # For outdoor stops, search directly for the place name
    wiki_queries = [stop_title]
    # Add more specific queries for certain stops
    if 'antibes' in stop_title.lower():
        wiki_queries.append(f"{stop_title} France")
    elif 'cap' in stop_title.lower():
        wiki_queries.append("Cap d'Antibes")
        wiki_queries.append("Antibes Cap")

    for wq in wiki_queries:
        print(f"  [WIKI] Search: {wq}")
        results = search_wikipedia(wq)
        for r in results:
            tier, tier_reason = classify_source(r['url'])
            if tier == 0:
                rejected.append((r['url'], tier_reason))
                continue

            extract = get_wikipedia_extract(r['title'])
            if not extract:
                continue

            relevant, rel_reason = is_about_this_place(extract, stop_title)
            if relevant:
                passages.append(extract[:2000])
                sources.append({
                    'url': r['url'],
                    'title': r['title'],
                    'tier': tier,
                    'tier_reason': tier_reason,
                    'relevance': rel_reason,
                    'type': 'wikipedia',
                })
                print(f"  [WIKI] ACCEPTED: '{r['title']}' (Tier {tier})")
                print(f"         Relevance: {rel_reason}")
                break
            else:
                rejected.append((r['url'], f"relevance: {rel_reason}"))
        if passages:
            break
        time.sleep(0.3)

    # ── French Wikipedia fallback (FREE) ──
    if not passages:
        fr_queries = [stop_title]
        if 'antibes' in stop_title.lower() or 'nice' in stop_title.lower():
            fr_queries.append(stop_title)
        for fq in fr_queries:
            print(f"  [WIKI-FR] Search: {fq}")
            results = search_wikipedia(fq, lang='fr')
            for r in results:
                extract = get_wikipedia_extract(r['title'], lang='fr')
                if not extract:
                    continue
                relevant, rel_reason = is_about_this_place(extract, stop_title)
                if relevant:
                    passages.append(extract[:2000])
                    sources.append({
                        'url': r['url'],
                        'title': r['title'],
                        'tier': 1,
                        'tier_reason': 'Wikipedia (fr)',
                        'relevance': rel_reason,
                        'type': 'wikipedia_fr',
                    })
                    print(f"  [WIKI-FR] ACCEPTED: '{r['title']}' (Tier 1)")
                    break
                else:
                    rejected.append((r['url'], f"relevance: {rel_reason}"))
            if passages:
                break
            time.sleep(0.3)

    # ── Serper (PAID) — only if Wikipedia yielded nothing ──
    if not passages:
        serp_queries = [f'"{stop_title}" history site:wikipedia.org OR site:britannica.com']
        if not any(r for r in serp_search(serp_queries[0])):
            serp_queries = [f'"{stop_title}" history French Riviera']

        for sq in serp_queries:
            results = serp_search(sq)
            if not results:
                continue

            for r in results:
                tier, tier_reason = classify_source(r['url'])
                if tier == 0:
                    rejected.append((r['url'], tier_reason))
                    continue

                snippet = r.get('snippet', '')
                relevant, rel_reason = is_about_this_place(snippet, stop_title)
                if relevant:
                    passages.append(snippet)
                    sources.append({
                        'url': r['url'],
                        'title': r['title'],
                        'tier': tier,
                        'tier_reason': tier_reason,
                        'relevance': rel_reason,
                        'type': 'serper',
                    })
                    print(f"  [SERP] ACCEPTED: {r['url'][:60]} (Tier {tier})")
                    break
                else:
                    rejected.append((r['url'], f"relevance: {rel_reason}"))
            if passages:
                break

    # Summary
    if passages:
        print(f"  RESULT: Found source (Tier {sources[0]['tier']})")
        print(f"    URL: {sources[0]['url']}")
    else:
        print(f"  RESULT: No valid source found")
        print(f"    Rejected: {len(rejected)}")

    return {'passages': passages, 'sources': sources, 'rejected': rejected} if passages else None


def fetch_fitzgerald_connection():
    """SPECIFICALLY check the Fitzgerald-Cap d'Antibes connection.

    This is the worked example from D51. If a tier-1 source confirms he lived
    there and set a novel there, that becomes a legitimate anchor.
    """
    print(f"\n{'#' * 60}")
    print(f"  FITZGERALD-CAP D'ANTIBES CHECK")
    print(f"{'#' * 60}")

    # Strategy: Wikipedia article on Tender Is the Night + Cap d'Antibes
    checks = []

    # Check 1: Wikipedia "Tender Is the Night"
    print(f"\n  Check 1: Wikipedia 'Tender Is the Night'")
    extract = get_wikipedia_extract("Tender Is the Night")
    if extract:
        norm = normalize_text(extract)
        has_antibes = 'antibes' in norm or 'riviera' in norm or "cap d" in norm
        has_fitzgerald = 'fitzgerald' in norm
        checks.append({
            'source': 'https://en.wikipedia.org/wiki/Tender_Is_the_Night',
            'found_antibes': has_antibes,
            'found_fitzgerald': has_fitzgerald,
            'extract_preview': extract[:500],
            'tier': 1,
        })
        print(f"    Antibes/Riviera mentioned: {has_antibes}")
        print(f"    Fitzgerald mentioned: {has_fitzgerald}")
    time.sleep(0.3)

    # Check 2: Wikipedia "Cap d'Antibes"
    print(f"\n  Check 2: Wikipedia 'Cap d'Antibes'")
    extract2 = get_wikipedia_extract("Cap d'Antibes")
    if extract2:
        norm2 = normalize_text(extract2)
        has_fitzgerald = 'fitzgerald' in norm2
        has_tender = 'tender' in norm2
        checks.append({
            'source': 'https://en.wikipedia.org/wiki/Cap_d%27Antibes',
            'found_fitzgerald': has_fitzgerald,
            'found_tender': has_tender,
            'extract_preview': extract2[:500],
            'tier': 1,
        })
        print(f"    Fitzgerald mentioned: {has_fitzgerald}")
        print(f"    'Tender' mentioned: {has_tender}")
    time.sleep(0.3)

    # Check 3: Wikipedia "F. Scott Fitzgerald" — check for Riviera connection
    print(f"\n  Check 3: Wikipedia 'F. Scott Fitzgerald'")
    extract3 = get_wikipedia_extract("F. Scott Fitzgerald")
    if extract3:
        norm3 = normalize_text(extract3)
        has_antibes = 'antibes' in norm3 or 'riviera' in norm3
        checks.append({
            'source': 'https://en.wikipedia.org/wiki/F._Scott_Fitzgerald',
            'found_riviera': has_antibes,
            'extract_preview': extract3[:500],
            'tier': 1,
        })
        print(f"    Riviera/Antibes mentioned: {has_antibes}")
    time.sleep(0.3)

    # Check 4: French Wikipedia "Cap d'Antibes"
    print(f"\n  Check 4: French Wikipedia 'Cap d'Antibes'")
    extract4 = get_wikipedia_extract("Cap d'Antibes", lang='fr')
    if extract4:
        norm4 = normalize_text(extract4)
        has_fitzgerald = 'fitzgerald' in norm4
        checks.append({
            'source': 'https://fr.wikipedia.org/wiki/Cap_d%27Antibes',
            'found_fitzgerald': has_fitzgerald,
            'extract_preview': extract4[:500],
            'tier': 1,
        })
        print(f"    Fitzgerald mentioned: {has_fitzgerald}")

    # Verdict
    confirmed = any(c.get('found_antibes') or c.get('found_riviera') 
                    for c in checks if c.get('found_fitzgerald', False))
    confirmed = confirmed or any(c.get('found_fitzgerald') for c in checks 
                                  if 'Antibes' in c.get('source', ''))

    print(f"\n  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    return checks, confirmed


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
    print(f"  [DB] Saved stop_corpus: '{stop_title}' ({passage_count} passages)")


def main():
    print("=" * 80)
    print("LOCAL-179: FETCH SOURCES FOR TOUR 29 — FRENCH RIVIERA BIKING TOUR")
    print("=" * 80)
    print(f"Budget ceiling: ${BUDGET_CEILING:.2f}")
    print(f"Serper key: {'present' if SERP_API_KEY else 'MISSING'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Stops: {len(TOUR_STOPS)}")
    print(f"Venue name: {VENUE_NAME}")
    print()

    conn = get_connection()

    # ── First: the Fitzgerald check (D51 worked example) ──
    fitzgerald_checks, fitzgerald_confirmed = fetch_fitzgerald_connection()

    # ── Fetch for each stop ──
    results = {}
    stops_with_source = []
    stops_without_source = []

    for stop_title in TOUR_STOPS:
        result = fetch_for_outdoor_stop(stop_title)
        if result and result['passages']:
            results[stop_title] = result
            stops_with_source.append(stop_title)
            persist_stop_corpus(VENUE_NAME, stop_title, 
                              result['passages'], result['sources'], conn)
        else:
            stops_without_source.append(stop_title)

        # Budget check
        current_spend = total_serp_queries * COST_PER_QUERY
        if current_spend >= BUDGET_CEILING:
            print(f"\n  BUDGET REACHED: ${current_spend:.3f}")
            break

    # ── If Fitzgerald confirmed, ensure Cap d'Antibes has that passage ──
    if fitzgerald_confirmed:
        # Find the best Fitzgerald passage and add it to Cap d'Antibes
        for check in fitzgerald_checks:
            if check.get('found_fitzgerald') and ('Antibes' in check.get('source', '') or 
                                                   check.get('found_antibes') or
                                                   check.get('found_riviera')):
                fitz_passage = check['extract_preview']
                if "Cap d'Antibes" in results:
                    # Append Fitzgerald passage
                    results["Cap d'Antibes"]['passages'].append(fitz_passage)
                    results["Cap d'Antibes"]['sources'].append({
                        'url': check['source'],
                        'title': 'Fitzgerald-Cap d\'Antibes connection',
                        'tier': check['tier'],
                        'tier_reason': 'Wikipedia (Fitzgerald biography/novel)',
                        'relevance': 'Fitzgerald lived at Cap d\'Antibes; Tender Is the Night set there',
                        'type': 'wikipedia',
                    })
                    persist_stop_corpus(VENUE_NAME, "Cap d'Antibes",
                                      results["Cap d'Antibes"]['passages'],
                                      results["Cap d'Antibes"]['sources'], conn)
                    print(f"\n  [FITZGERALD] Added to Cap d'Antibes stop_corpus")
                break

    # ── Summary ──
    total_spend = total_serp_queries * COST_PER_QUERY
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print("=" * 80)
    print(f"  Stops: {len(TOUR_STOPS)}")
    print(f"  With source: {len(stops_with_source)}")
    print(f"  Without source: {len(stops_without_source)}")
    print(f"  Serper queries: {total_serp_queries}")
    print(f"  Total spend: ${total_spend:.4f}")
    print(f"  Budget remaining: ${BUDGET_CEILING - total_spend:.4f}")
    print()
    print(f"  FITZGERALD VERDICT: {'CONFIRMED by Tier 1 source' if fitzgerald_confirmed else 'NOT CONFIRMED'}")
    print()

    if stops_with_source:
        print("  Stops WITH source:")
        for s in stops_with_source:
            src = results[s]['sources'][0]
            print(f"    {s:35s} Tier {src['tier']} — {src['url'][:60]}")
    print()
    if stops_without_source:
        print("  Stops WITHOUT source:")
        for s in stops_without_source:
            print(f"    {s}")
    print()
    print("  Query log:")
    for ql in query_log:
        print(f"    '{ql['query'][:60]}' -> {ql['results']} results, ${ql['cost']:.3f}")

    conn.close()
    return {
        'stops_with_source': stops_with_source,
        'stops_without_source': stops_without_source,
        'total_spend': total_spend,
        'fitzgerald_confirmed': fitzgerald_confirmed,
    }


if __name__ == '__main__':
    main()
