#!/usr/bin/env python3
"""LOCAL-178: Fetch source material for Palais Lascaris stops that have no stop_corpus row.

Trust hierarchy (SQ-S3):
  1. Wikipedia (free API, Tier 1) — query by work title + venue
  2. Serper.dev (paid, ~$0.001/query) — only if Wikipedia yields nothing

Budget ceiling: $0.50. Estimated: 10 works × 1-2 queries × $0.001 = $0.01-$0.02.

Constraints:
  - Every persisted passage must carry a source URL
  - No fabrication: if nothing found, record that explicitly
  - Additive only: no DELETE FROM, no modification of existing data
  - Do not modify detector classification logic
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

# ─── Setup ───────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
VENUE_NAME = "Palais Lascaris, Nice"

# Cost tracking
TOTAL_SERP_QUERIES = 0
COST_PER_QUERY = 0.001  # USD per Serper query
BUDGET_CEILING = 0.50
query_log = []


def normalize_text(text):
    """Lowercase, strip diacritics, collapse whitespace."""
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', ascii_text.lower()).strip()


# ─── Wikipedia API (FREE — no cost) ─────────────────────────────────────────
def search_wikipedia(query, lang='en'):
    """Search Wikipedia API for articles matching query. Returns list of {title, url, snippet}. FREE."""
    encoded = urllib.parse.quote(query)
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&srinfo=totalhits&srprop=snippet&srlimit=5&format=json"
    
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
        print(f"  [WIKI] Search failed: {e}")
        return []


def get_wikipedia_extract(title, lang='en'):
    """Get the introductory extract of a Wikipedia article. FREE."""
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
        print(f"  [WIKI] Extract failed: {e}")
        return None


# ─── Serper API (PAID — $0.001/query) ───────────────────────────────────────
def serp_search(query):
    """Execute a Serper.dev search. COSTS $0.001."""
    global TOTAL_SERP_QUERIES
    
    if not SERP_API_KEY:
        print("  [SERP] ERROR: No SERP_API_KEY set")
        return []
    
    # Budget check
    projected_cost = (TOTAL_SERP_QUERIES + 1) * COST_PER_QUERY
    if projected_cost > BUDGET_CEILING:
        print(f"  [SERP] BUDGET ABORT: projected ${projected_cost:.3f} > ceiling ${BUDGET_CEILING:.2f}")
        return []
    
    TOTAL_SERP_QUERIES += 1
    start = time.time()
    
    try:
        data = json.dumps({"q": query, "num": 8}).encode()
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
            results = [{'title': r.get('title', ''), 'url': r.get('link', ''), 'snippet': r.get('snippet', '')}
                      for r in organic]
            query_log.append({'query': query, 'results': len(results), 'latency_ms': round(latency, 1), 'cost': COST_PER_QUERY})
            print(f"  [SERP] Query #{TOTAL_SERP_QUERIES}: '{query[:60]}' → {len(results)} results ({latency:.0f}ms)")
            return results
    except Exception as e:
        latency = (time.time() - start) * 1000
        query_log.append({'query': query, 'results': 0, 'latency_ms': round(latency, 1), 'cost': COST_PER_QUERY, 'error': str(e)})
        print(f"  [SERP] Query failed: {e}")
        return []


# ─── Source evaluation ───────────────────────────────────────────────────────
def is_useful_snippet(snippet, work_title):
    """Check if a snippet/extract actually mentions the work or provides useful context."""
    if not snippet or len(snippet) < 30:
        return False
    # Must have SOME connection to the work or instrument type
    title_lower = normalize_text(work_title)
    snippet_lower = normalize_text(snippet)
    
    # Extract key terms from the title
    # e.g. "Harpe by Naderman (Paris, 1780)" → ["harpe", "naderman", "paris", "1780"]
    terms = re.findall(r'[a-z]+', title_lower)
    # Remove very common words
    stopwords = {'by', 'the', 'de', 'du', 'le', 'la', 'les', 'des', 'in', 'et', 'a', 'par'}
    terms = [t for t in terms if t not in stopwords and len(t) > 2]
    
    # At least 2 distinctive terms from the title must appear
    matches = sum(1 for t in terms if t in snippet_lower)
    return matches >= 2


def extract_maker_and_instrument(title):
    """Parse 'Instrument by Maker (City, Year)' format."""
    # Pattern: "Instrument by Maker (City, Year)"
    match = re.match(r'^(.+?)\s+by\s+(.+?)(?:\s*\((.+?)\))?$', title, re.IGNORECASE)
    if match:
        return {
            'instrument': match.group(1).strip(),
            'maker': match.group(2).strip(),
            'details': match.group(3).strip() if match.group(3) else ''
        }
    # Bare title (like "Raquel")
    return {'instrument': title, 'maker': '', 'details': ''}


# ─── Main fetch logic ────────────────────────────────────────────────────────
def fetch_source_for_work(work_title):
    """Try to find source material for a single work. Returns {passages, sources} or None."""
    print(f"\n{'─' * 60}")
    print(f"  WORK: {work_title}")
    print(f"{'─' * 60}")
    
    parsed = extract_maker_and_instrument(work_title)
    passages = []
    sources = []
    
    # ── Step 1: Wikipedia (FREE) ──
    # Try maker name + instrument type
    wiki_queries = []
    if parsed['maker']:
        wiki_queries.append(f"{parsed['maker']} luthier")
        wiki_queries.append(f"{parsed['maker']} instrument maker")
    if parsed['instrument']:
        # For French instrument names, try both languages
        wiki_queries.append(f"{parsed['instrument']} musical instrument")
    
    for wq in wiki_queries:
        results = search_wikipedia(wq)
        for r in results:
            # Check if the Wikipedia article is actually relevant
            extract = get_wikipedia_extract(r['title'])
            if extract and is_useful_snippet(extract, work_title):
                # Trim to relevant portion (first 1500 chars)
                passage_text = extract[:1500]
                passages.append(passage_text)
                sources.append({'url': r['url'], 'title': r['title'], 'type': 'wikipedia'})
                print(f"  [WIKI] ✓ Found: '{r['title']}' ({len(extract)} chars)")
                break  # One good Wikipedia source is enough per query
        if passages:
            break  # Got something from Wikipedia
        time.sleep(0.3)  # Be polite to Wikipedia
    
    # Also try French Wikipedia for French instruments
    if not passages and parsed['maker']:
        results_fr = search_wikipedia(f"{parsed['maker']}", lang='fr')
        for r in results_fr:
            extract = get_wikipedia_extract(r['title'], lang='fr')
            if extract and is_useful_snippet(extract, work_title):
                passage_text = extract[:1500]
                passages.append(passage_text)
                sources.append({'url': r['url'], 'title': r['title'], 'type': 'wikipedia_fr'})
                print(f"  [WIKI-FR] ✓ Found: '{r['title']}' ({len(extract)} chars)")
                break
        time.sleep(0.3)
    
    # ── Step 2: Serper (PAID) — only if Wikipedia yielded nothing ──
    if not passages:
        # Construct targeted query
        serp_query = f'"{parsed["maker"]}" {parsed["instrument"]} Palais Lascaris'
        if not parsed['maker']:
            serp_query = f'"{work_title}" Palais Lascaris'
        
        results = serp_search(serp_query)
        for r in results:
            if is_useful_snippet(r.get('snippet', ''), work_title):
                passages.append(r['snippet'])
                sources.append({'url': r['url'], 'title': r['title'], 'type': 'serper'})
                print(f"  [SERP] ✓ Snippet from: {r['url'][:80]}")
                break
        
        # If first query didn't work, try a broader one
        if not passages and parsed['maker']:
            serp_query2 = f'"{parsed["maker"]}" instrument maker {parsed.get("details", "")}'
            results2 = serp_search(serp_query2)
            for r in results2:
                if is_useful_snippet(r.get('snippet', ''), work_title):
                    passages.append(r['snippet'])
                    sources.append({'url': r['url'], 'title': r['title'], 'type': 'serper'})
                    print(f"  [SERP] ✓ Snippet from: {r['url'][:80]}")
                    break
    
    if passages:
        return {'passages': passages, 'sources': sources}
    else:
        print(f"  [RESULT] ✗ No usable source found for: {work_title}")
        return None


# ─── Persistence ─────────────────────────────────────────────────────────────
def persist_to_stop_corpus(venue_name, stop_title, passages, sources, conn):
    """Insert into stop_corpus. Additive only — uses ON CONFLICT DO NOTHING."""
    cur = conn.cursor()
    
    passages_json = json.dumps(passages)
    source_pages_json = json.dumps(sources)
    passage_count = len(passages)
    
    cur.execute("""
        INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (venue_name, stop_title) DO UPDATE SET
            passages_json = EXCLUDED.passages_json,
            source_pages = EXCLUDED.source_pages,
            passage_count = EXCLUDED.passage_count
    """, (venue_name, stop_title, passages_json, source_pages_json, passage_count))
    
    conn.commit()
    print(f"  [DB] ✓ Persisted {passage_count} passage(s) for '{stop_title}'")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("LOCAL-178: Fetch source material for Palais Lascaris stops")
    print(f"Budget ceiling: ${BUDGET_CEILING:.2f}")
    print(f"Serper key: {'present' if SERP_API_KEY else 'MISSING'} ({len(SERP_API_KEY)} chars)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get canonical titles for Palais Lascaris
    cur.execute("""
        SELECT canonical_titles_json FROM venue_corpus
        WHERE venue_name = %s
    """, (VENUE_NAME,))
    row = cur.fetchone()
    if not row:
        print(f"ERROR: No venue_corpus row for '{VENUE_NAME}'")
        sys.exit(1)
    
    titles = row[0] if isinstance(row[0], list) else json.loads(row[0])
    print(f"\nCanonical titles ({len(titles)}):")
    for t in titles:
        print(f"  - {t}")
    
    # Check existing stop_corpus rows
    cur.execute("""
        SELECT stop_title FROM stop_corpus WHERE venue_name = %s
    """, (VENUE_NAME,))
    existing = {r[0] for r in cur.fetchall()}
    print(f"\nExisting stop_corpus rows: {len(existing)}")
    
    # Determine which titles need fetching
    titles_to_fetch = [t for t in titles if t not in existing]
    print(f"Titles needing source material: {len(titles_to_fetch)}")
    
    if not titles_to_fetch:
        print("All titles already have stop_corpus rows. Nothing to fetch.")
        return
    
    # ── Fetch sources for each work ──
    results = {}
    works_with_source = []
    works_without_source = []
    
    for title in titles_to_fetch:
        result = fetch_source_for_work(title)
        if result:
            results[title] = result
            works_with_source.append(title)
            # Persist immediately
            persist_to_stop_corpus(VENUE_NAME, title, result['passages'], result['sources'], conn)
        else:
            works_without_source.append(title)
        
        # Budget check after each work
        current_spend = TOTAL_SERP_QUERIES * COST_PER_QUERY
        if current_spend >= BUDGET_CEILING:
            print(f"\n⚠️  BUDGET REACHED: ${current_spend:.3f} — stopping")
            break
    
    # ── Summary ──
    total_spend = TOTAL_SERP_QUERIES * COST_PER_QUERY
    print(f"\n{'=' * 80}")
    print("FETCH SUMMARY")
    print("=" * 80)
    print(f"  Works fetched: {len(titles_to_fetch)}")
    print(f"  Works with usable material: {len(works_with_source)}")
    print(f"  Works with nothing found: {len(works_without_source)}")
    print(f"  Total Serper queries: {TOTAL_SERP_QUERIES}")
    print(f"  Total spend: ${total_spend:.4f}")
    print(f"  Budget remaining: ${BUDGET_CEILING - total_spend:.4f}")
    
    if works_with_source:
        print(f"\n  ✓ Works with source material:")
        for w in works_with_source:
            src = results[w]['sources'][0]
            print(f"    - {w}")
            print(f"      Source: {src['url']}")
    
    if works_without_source:
        print(f"\n  ✗ Works with NO source found:")
        for w in works_without_source:
            print(f"    - {w}")
    
    print(f"\n  Query log:")
    for ql in query_log:
        err = f" ERROR: {ql['error']}" if 'error' in ql else ""
        print(f"    '{ql['query'][:50]}...' → {ql['results']} results, {ql['latency_ms']}ms, ${ql['cost']:.4f}{err}")
    
    conn.close()
    return {
        'works_fetched': len(titles_to_fetch),
        'works_with_source': len(works_with_source),
        'works_without_source': len(works_without_source),
        'total_serper_queries': TOTAL_SERP_QUERIES,
        'total_spend': total_spend,
        'works_with_source_list': works_with_source,
        'works_without_source_list': works_without_source,
    }


if __name__ == '__main__':
    main()
