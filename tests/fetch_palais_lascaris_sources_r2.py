#!/usr/bin/env python3
"""LOCAL-178 Round 2: Re-fetch source material for Palais Lascaris actual tour stops.

BOUNCE FINDINGS (Round 1):
- "The Annunciation" source (mamac-nice.org PDF) is FALSE — it's about a 2020
  contemporary work by the Leisgens, not the historic Annunciation at Palais Lascaris.
  Keyword co-occurrence ≠ relationship.
- "The Triumph of David" source (2-crc.com) is VALID but low-authority — a leather
  restorer who actually worked on that tapestry.
- Fetching was driven by canonical_titles (10 instruments) rather than actual tour
  stops (3 frescoes).

ROUND 2 CHANGES:
1. Drive from ACTUAL TOUR STOPS: "The Triumph of David", "The Annunciation", "Raquel"
2. Apply trust hierarchy with correct-institution check:
   - Tier 1: Wikipedia, the venue's own site (palais-lascaris* or nice.fr/lieux/palais-lascaris)
   - Tier 2: Joconde/POP (French national catalogue), departement06
   - Tier 3: Other sources — only if clearly about THIS work AT THIS venue
3. RELEVANCE RULE: A passage qualifies only if:
   - It is ABOUT this work at this venue (not merely co-occurrence)
   - The work's distinctive terms appear in substantive context (not a list mention,
     not a different work that shares a word)
   - For institutional sites: must be THIS institution, not another museum

BUDGET: $0.50 ceiling. Expected: 3 stops × 2-3 queries = ~$0.006.
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
ACTUAL_TOUR_STOPS = ["The Triumph of David", "The Annunciation", "Raquel"]

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


# ─── RELEVANCE RULE ──────────────────────────────────────────────────────────
#
# A passage qualifies ONLY if it is ABOUT this work at this venue.
# NOT merely a page where both strings happen to appear.
#
# Rule: The passage must contain the work's distinctive terms in a SUBSTANTIVE
# context — i.e., the passage is discussing this work, not merely listing it
# alongside other items or mentioning a homonym.
#
# Specific checks:
# 1. The work title (or its distinctive words) must appear in the passage
# 2. The passage must be about Palais Lascaris (not another venue)
# 3. The passage must be ABOUT the work — not just a catalogue list entry
#    where the title appears as one item among many
# 4. For "The Annunciation" specifically: must be about an HISTORIC work at
#    Palais Lascaris, not a contemporary artwork that happens to reference
#    the Annunciation theme

def is_about_this_work_at_this_venue(passage, work_title, venue="Palais Lascaris"):
    """Check if a passage is genuinely ABOUT this work at this venue.

    RULE: The passage must discuss this specific artwork at this specific venue.
    Keyword co-occurrence on a page ≠ a relationship. Both the work and the
    venue must be related WITHIN the passage, not just appearing on the same page.

    Returns (True, reason) or (False, reason).
    """
    if not passage or len(passage) < 30:
        return False, "too short"

    passage_norm = normalize_text(passage)
    work_norm = normalize_text(work_title)
    venue_norm = normalize_text(venue)

    # Extract distinctive words from work title (skip articles/prepositions)
    noise = {'the', 'of', 'by', 'a', 'an', 'le', 'la', 'les', 'de', 'du', 'des'}
    work_words = [w for w in work_norm.split() if w not in noise and len(w) >= 3]

    if not work_words:
        return False, "no distinctive words in title"

    # Check 1: work title terms present in passage
    title_matches = sum(1 for w in work_words if w in passage_norm)
    if title_matches < max(1, len(work_words) * 0.5):
        return False, f"work title terms not present ({title_matches}/{len(work_words)})"

    # Check 2: venue context present
    venue_terms = ['palais lascaris', 'lascaris']
    has_venue = any(t in passage_norm for t in venue_terms)
    if not has_venue:
        # For Wikipedia articles specifically ABOUT the work, venue isn't always
        # in the intro. But for search snippets, we require venue context.
        # Be lenient only for full Wikipedia extracts (>500 chars)
        if len(passage) < 500:
            return False, "no venue context in short passage"

    # Check 3: NOT just a list/catalogue mention
    # If the work name appears only in a comma-separated list among many items,
    # the passage is not ABOUT this work
    sentences = re.split(r'[.;]\s+', passage)
    relevant_sentences = []
    for i, sent in enumerate(sentences):
        sent_norm = normalize_text(sent)
        if any(w in sent_norm for w in work_words):
            relevant_sentences.append(sent)
            # Also include the next sentence as context (the description
            # often follows the name mention)
            if i + 1 < len(sentences):
                relevant_sentences.append(sentences[i + 1])

    if not relevant_sentences:
        return False, "work terms not in any sentence"

    # Consider the combined relevant context, not just the single sentence
    combined_relevant = ' '.join(relevant_sentences)
    longest_relevant = len(combined_relevant)
    if longest_relevant < 40:
        return False, f"mention too brief ({longest_relevant} chars) — likely a list entry"

    # Check 4: Distinguish paintings/artworks from churches and orders
    if "annunciation" in work_norm or "annonciation" in work_norm:
        # REJECT if about the Church of the Annunciation (not the painting)
        church_markers = ['church of', 'eglise de', 'église de', 'solo-friendly',
                          'things to do', 'nearby', 'km of']
        if any(m in passage_norm for m in church_markers):
            return False, "about the Church of the Annunciation, not the painting"

        # REJECT if about the Order of the Most Holy Annunciation (a medal)
        order_markers = ['order of', 'collar of', 'ordre de']
        if any(m in passage_norm for m in order_markers):
            return False, "about the Order of the Annunciation, not the painting"

        # REJECT if about musical instruments (trombone, etc.) — a page about
        # instruments at Palais Lascaris that merely shows a trombone player in
        # an Annunciation scene is NOT about the painting "The Annunciation"
        instrument_markers = ['trombone', 'instrument', 'sacqueboute', 'sackbut',
                              'extant examples', 'illustrations']
        instrument_hits = sum(1 for m in instrument_markers if m in passage_norm)
        if instrument_hits >= 2:
            return False, f"about musical instruments, not the painting ({instrument_hits} markers)"

        # REJECT contemporary works that reference the Annunciation theme
        contemporary_markers = ['2020', '2021', '2022', '2023', '2024', '2025',
                                'leisgen', 'contemporary', 'installation',
                                'shadow', 'reflection', 'echo']
        contemporary_hits = sum(1 for m in contemporary_markers if m in passage_norm)
        if contemporary_hits >= 2:
            return False, f"about a contemporary work ({contemporary_hits} markers)"

        # MUST reference Palais Lascaris, not MAMAC or another museum
        wrong_venues = ['mamac', 'musee art moderne', 'museum of modern']
        if any(v in passage_norm for v in wrong_venues):
            if not has_venue:
                return False, "references wrong museum, not Palais Lascaris"

        # The passage must have PAINTING-related context to confirm it's about the artwork
        painting_context = ['painting', 'peinture', 'fresque', 'fresco', 'tableau',
                           'artwork', 'oeuvre', 'toile', 'canvas', 'baroque',
                           'angel gabriel', 'virgin mary', 'vierge', 'ange']
        has_painting = any(c in passage_norm for c in painting_context)
        if not has_painting and not has_venue:
            return False, "no painting/artwork context for The Annunciation"

    # Check 5: For "Raquel" — must be about the gilt leather painting, not a person
    if "raquel" in work_norm:
        # The work is a gilt leather painting of the biblical figure Raquel
        # Accept if it mentions: cuir doré, gilt leather, biblical, painting/peinture,
        # or is clearly in the context of Palais Lascaris artworks
        raquel_context = ['cuir dore', 'gilt leather', 'biblical', 'peinture',
                          'painting', 'panel', 'panneau', 'testament',
                          'lascaris', 'personnage']
        has_art_context = any(c in passage_norm for c in raquel_context)
        if not has_art_context:
            return False, "mentions 'Raquel' without art/Lascaris context"

    return True, f"relevant ({title_matches}/{len(work_words)} terms, venue={'yes' if has_venue else 'no'}, longest sent {longest_relevant} chars)"


# ─── TRUST HIERARCHY ─────────────────────────────────────────────────────────
#
# Tier 1: Wikipedia, venue's own site
# Tier 2: Joconde/POP, departement06, scholarly
# Tier 3: Other (only if clearly relevant)
# Reject: Wrong museum, commerce, aggregator

def classify_source(url, snippet=""):
    """Classify a search result by trust tier.

    Returns (tier, reason) where tier is 1, 2, 3, or 0 (reject).

    CRITICAL: Tier 1 "venue's own site" means ONLY domains that the
    institution itself controls. A travel aggregator whose URL happens
    to contain 'palais-lascaris' is NOT the venue's own site.
    """
    url_lower = url.lower()
    domain = urllib.parse.urlparse(url).netloc.lower()

    # Tier 1: Wikipedia / Wikimedia
    if 'wikipedia.org' in domain or 'wikimedia.org' in domain:
        return 1, "Wikipedia/Wikimedia"

    # Tier 1: Palais Lascaris own site — ONLY official Nice municipal domain
    # The venue is managed by the city of Nice; its official page is on nice.fr
    if domain in ('www.nice.fr', 'nice.fr') and 'lascaris' in url_lower:
        return 1, "Nice municipal (venue's own page)"

    # Tier 2: French national catalogues and archives
    if 'pop.culture.gouv.fr' in domain or 'joconde' in domain:
        return 2, "Joconde/POP (national catalogue)"
    if 'portail-savoirs.departement06.fr' in domain:
        return 2, "Département 06 (regional archives)"

    # Tier 2: Scholarly/academic sources
    if any(d in domain for d in ['hal.science', '.edu', '.ac.uk', 'jstor.org',
                                  'cairn.info', 'agorha.inha.fr', 'persee.fr']):
        return 2, f"scholarly/academic ({domain})"

    # Tier 2: Quality French journalism about heritage
    if domain in ('www.nicematin.com', 'nicematin.com'):
        return 2, "regional journalism (Nice-Matin)"

    # REJECT: Wrong museum's site
    if 'mamac-nice.org' in domain:
        return 0, "WRONG MUSEUM (MAMAC ≠ Palais Lascaris)"
    if any(d in domain for d in ['musee-matisse', 'musee-chagall']):
        return 0, "wrong museum"

    # REJECT: Commerce, video, social media, travel aggregators
    if any(d in domain for d in ['youtube.com', 'flickr.com', 'pinterest.com',
                                  'tripadvisor', 'booking.com', 'amazon.',
                                  'ebay.', 'etsy.', 'instagram.com',
                                  'facebook.com', 'twitter.com', 'tiktok.com',
                                  'traveltowith.com', 'wanderboat.ai',
                                  'getarchive.net', 'picryl.com',
                                  'aroundus.com', 'alamy.com',
                                  'travelinsightpedia.com']):
        return 0, f"rejected ({domain})"

    # Tier 3: Other — acceptable only if content is clearly relevant
    return 3, f"other ({domain})"


# ─── Wikipedia API (FREE) ────────────────────────────────────────────────────
def search_wikipedia(query, lang='en'):
    """Search Wikipedia. Returns list of {title, url, snippet}. FREE."""
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
    """Get introductory extract of a Wikipedia article. FREE."""
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


# ─── Serper API (PAID — $0.001/query) ────────────────────────────────────────
def serp_search(query):
    """Execute a Serper.dev search. COSTS $0.001."""
    global TOTAL_SERP_QUERIES

    if not SERP_API_KEY:
        print("  [SERP] ERROR: No SERP_API_KEY set")
        return []

    projected_cost = (TOTAL_SERP_QUERIES + 1) * COST_PER_QUERY
    if projected_cost > BUDGET_CEILING:
        print(f"  [SERP] BUDGET ABORT: ${projected_cost:.3f} > ${BUDGET_CEILING:.2f}")
        return []

    TOTAL_SERP_QUERIES += 1
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
                            'latency_ms': round(latency, 1), 'cost': COST_PER_QUERY})
            print(f"  [SERP] Query #{TOTAL_SERP_QUERIES}: '{query[:60]}' → {len(results)} results ({latency:.0f}ms)")
            return results
    except Exception as e:
        latency = (time.time() - start) * 1000
        query_log.append({'query': query, 'results': 0, 'latency_ms': round(latency, 1),
                         'cost': COST_PER_QUERY, 'error': str(e)})
        print(f"  [SERP] Query failed: {e}")
        return []


# ─── Fetch logic per actual tour stop ────────────────────────────────────────

def fetch_for_stop(stop_title):
    """Fetch source material for one actual tour stop.

    Strategy per stop:
    1. Wikipedia (free): search for the work + Palais Lascaris
    2. Serper (paid): targeted query with trust hierarchy + relevance check
    3. French Wikipedia as fallback

    Returns {passages: [...], sources: [...]} or None if nothing valid found.
    """
    print(f"\n{'═' * 70}")
    print(f"  STOP: {stop_title}")
    print(f"{'═' * 70}")

    passages = []
    sources = []
    rejected = []

    # ── Step 1: Wikipedia (FREE) ──
    # Search for the work specifically at/in Palais Lascaris
    wiki_queries = [
        f'"{stop_title}" Palais Lascaris',
        f'Palais Lascaris {stop_title}',
    ]
    # For The Triumph of David, also try the tapestry/gilt leather angle
    if 'triumph' in stop_title.lower() and 'david' in stop_title.lower():
        wiki_queries.append("Triumph of David gilt leather tapestry")
        wiki_queries.append("Palais Lascaris tapestry")
    if 'annunciation' in stop_title.lower():
        wiki_queries.append("Palais Lascaris painting fresco")
    if 'raquel' in stop_title.lower():
        wiki_queries.append("Palais Lascaris Raquel painting")

    for wq in wiki_queries:
        print(f"  [WIKI] Searching: {wq}")
        results = search_wikipedia(wq)
        for r in results:
            # Check trust tier
            tier, tier_reason = classify_source(r['url'])
            if tier == 0:
                rejected.append((r['url'], tier_reason))
                continue

            # Get full extract
            extract = get_wikipedia_extract(r['title'])
            if not extract:
                continue

            # Apply relevance rule
            relevant, rel_reason = is_about_this_work_at_this_venue(extract, stop_title)
            if relevant:
                passage_text = extract[:1500]
                passages.append(passage_text)
                sources.append({
                    'url': r['url'],
                    'title': r['title'],
                    'type': 'wikipedia',
                    'tier': tier,
                    'relevance': rel_reason,
                })
                print(f"  [WIKI] ✓ ACCEPTED: '{r['title']}' (Tier {tier}: {tier_reason})")
                print(f"         Relevance: {rel_reason}")
                break
            else:
                rejected.append((r['url'], f"relevance check failed: {rel_reason}"))
                print(f"  [WIKI] ✗ Rejected: '{r['title']}' — {rel_reason}")

        if passages:
            break
        time.sleep(0.3)

    # Also try French Wikipedia
    if not passages:
        fr_queries = [f'Palais Lascaris {stop_title}', f'Palais Lascaris Nice']
        for fq in fr_queries:
            results_fr = search_wikipedia(fq, lang='fr')
            for r in results_fr:
                extract = get_wikipedia_extract(r['title'], lang='fr')
                if not extract:
                    continue
                relevant, rel_reason = is_about_this_work_at_this_venue(extract, stop_title)
                if relevant:
                    passages.append(extract[:1500])
                    sources.append({
                        'url': r['url'],
                        'title': r['title'],
                        'type': 'wikipedia_fr',
                        'tier': 1,
                        'relevance': rel_reason,
                    })
                    print(f"  [WIKI-FR] ✓ ACCEPTED: '{r['title']}'")
                    break
                else:
                    rejected.append((r['url'], f"relevance: {rel_reason}"))
            if passages:
                break
            time.sleep(0.3)

    # ── Step 2: Serper (PAID) — only if Wikipedia yielded nothing ──
    if not passages:
        # Query shape: work title + venue name, quoted for precision
        serp_queries = [
            f'"{stop_title}" "Palais Lascaris"',
        ]
        # Stop-specific additional queries
        if 'triumph' in stop_title.lower() and 'david' in stop_title.lower():
            serp_queries.append('"Triumph of David" "Palais Lascaris" tapestry leather')
            serp_queries.append('"Triomphe de David" "Palais Lascaris"')
        elif 'annunciation' in stop_title.lower():
            serp_queries.append('"Annonciation" "Palais Lascaris" peinture fresque')
            serp_queries.append('"Annunciation" "Palais Lascaris" painting fresco')
            serp_queries.append('"Annonciation" "Palais Lascaris" baroque')
        elif 'raquel' in stop_title.lower():
            serp_queries.append('"Raquel" "Palais Lascaris" "gilt leather" OR "cuir doré" OR "biblical"')
            serp_queries.append('"Raquel" "Palais Lascaris" "cuir doré"')

        for sq in serp_queries:
            results = serp_search(sq)
            if not results:
                continue

            # Rank results by trust tier, skip rejected
            ranked = []
            for r in results:
                tier, tier_reason = classify_source(r['url'], r.get('snippet', ''))
                if tier == 0:
                    rejected.append((r['url'], tier_reason))
                    print(f"  [SERP] ✗ Tier 0 REJECTED: {r['url'][:60]} — {tier_reason}")
                    continue
                ranked.append((tier, r, tier_reason))

            # Sort by tier (lower = better)
            ranked.sort(key=lambda x: x[0])

            for tier, r, tier_reason in ranked:
                snippet = r.get('snippet', '')
                # Apply relevance rule to snippet
                relevant, rel_reason = is_about_this_work_at_this_venue(
                    snippet, stop_title)
                if relevant:
                    passages.append(snippet)
                    sources.append({
                        'url': r['url'],
                        'title': r['title'],
                        'type': 'serper',
                        'tier': tier,
                        'tier_reason': tier_reason,
                        'relevance': rel_reason,
                    })
                    print(f"  [SERP] ✓ ACCEPTED: {r['url'][:70]}")
                    print(f"         Tier {tier} ({tier_reason}), Relevance: {rel_reason}")
                    break
                else:
                    rejected.append((r['url'], f"relevance: {rel_reason}"))
                    print(f"  [SERP] ✗ Rejected: {r['url'][:60]} — {rel_reason}")

            if passages:
                break

    # ── Summary for this stop ──
    print(f"\n  {'─' * 50}")
    if passages:
        print(f"  RESULT: ✓ Found {len(passages)} valid passage(s)")
        print(f"  Source: {sources[0]['url']}")
        print(f"  Passage preview: {passages[0][:100]}...")
    else:
        print(f"  RESULT: ✗ No valid source found for '{stop_title}'")
        print(f"  Rejected {len(rejected)} candidate(s):")
        for url, reason in rejected[:5]:
            print(f"    - {url[:60]} — {reason}")

    return {
        'passages': passages,
        'sources': sources,
        'rejected': rejected,
    } if passages else None


# ─── Persistence ─────────────────────────────────────────────────────────────

def update_stop_corpus(venue_name, stop_title, passages, sources, conn):
    """UPDATE existing stop_corpus row (replace false data) or INSERT new.

    Uses ON CONFLICT DO UPDATE — not DELETE.
    """
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
    print(f"  [DB] ✓ Updated stop_corpus for '{stop_title}' ({passage_count} passage(s))")


def clear_false_stop_corpus(venue_name, stop_title, conn):
    """Replace a false stop_corpus entry with empty data (not DELETE).

    Sets passages to empty, source_pages to empty, passage_count to 0.
    This neutralizes the false data without violating 'no DELETE' constraint.
    """
    cur = conn.cursor()
    cur.execute("""
        UPDATE stop_corpus
        SET passages_json = '[]'::jsonb,
            source_pages = '[]'::jsonb,
            passage_count = 0
        WHERE venue_name = %s AND stop_title = %s
    """, (venue_name, stop_title))
    if cur.rowcount > 0:
        conn.commit()
        print(f"  [DB] ✓ Cleared false data for '{stop_title}' (row preserved, content zeroed)")
    else:
        conn.commit()
        print(f"  [DB] No existing row to clear for '{stop_title}'")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("LOCAL-178 ROUND 2: Re-fetch for Palais Lascaris actual tour stops")
    print("=" * 80)
    print(f"Budget ceiling: ${BUDGET_CEILING:.2f}")
    print(f"Serper key: {'present' if SERP_API_KEY else 'MISSING'} ({len(SERP_API_KEY)} chars)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Actual tour stops: {ACTUAL_TOUR_STOPS}")
    print()
    print("RELEVANCE RULE:")
    print("  A passage qualifies only if it is ABOUT this work AT this venue.")
    print("  Keyword co-occurrence on a page ≠ a relationship.")
    print("  The work's distinctive terms must appear in substantive context.")
    print()
    print("TRUST HIERARCHY:")
    print("  Tier 1: Wikipedia, venue's own site (palais-lascaris/nice.fr)")
    print("  Tier 2: Joconde/POP, departement06, scholarly")
    print("  Tier 3: Other credible sources")
    print("  Reject: Wrong museum, commerce, social media")
    print("=" * 80)

    conn = get_connection()

    # ── First: clear the known false entry ──
    print("\n─── CLEARING KNOWN FALSE ENTRIES ───")
    # The Annunciation had a mamac-nice.org source about a DIFFERENT work
    clear_false_stop_corpus(VENUE_NAME, "The Annunciation", conn)

    # ── Fetch for each actual tour stop ──
    results = {}
    works_with_source = []
    works_without_source = []

    for stop_title in ACTUAL_TOUR_STOPS:
        result = fetch_for_stop(stop_title)
        if result:
            results[stop_title] = result
            works_with_source.append(stop_title)
            update_stop_corpus(VENUE_NAME, stop_title,
                             result['passages'], result['sources'], conn)
        else:
            works_without_source.append(stop_title)
            # Clear any existing false data for this stop
            clear_false_stop_corpus(VENUE_NAME, stop_title, conn)

        # Budget check
        current_spend = TOTAL_SERP_QUERIES * COST_PER_QUERY
        if current_spend >= BUDGET_CEILING:
            print(f"\n⚠️  BUDGET REACHED: ${current_spend:.3f} — stopping")
            break

    # ── Summary ──
    total_spend = TOTAL_SERP_QUERIES * COST_PER_QUERY
    print(f"\n{'=' * 80}")
    print("ROUND 2 FETCH SUMMARY")
    print("=" * 80)
    print(f"  Stops processed: {len(ACTUAL_TOUR_STOPS)}")
    print(f"  Stops with valid source: {len(works_with_source)}")
    print(f"  Stops with NO valid source: {len(works_without_source)}")
    print(f"  Total Serper queries: {TOTAL_SERP_QUERIES}")
    print(f"  Total spend: ${total_spend:.4f}")
    print(f"  Budget remaining: ${BUDGET_CEILING - total_spend:.4f}")

    if works_with_source:
        print(f"\n  ✓ Stops with valid source material:")
        for w in works_with_source:
            src = results[w]['sources'][0]
            print(f"    - {w}")
            print(f"      Tier {src.get('tier', '?')}: {src['url']}")
            print(f"      Relevance: {src.get('relevance', '?')}")

    if works_without_source:
        print(f"\n  ✗ Stops with NO valid source (honestly recorded):")
        for w in works_without_source:
            print(f"    - {w}")

    print(f"\n  Query log:")
    for ql in query_log:
        err = f" ERROR: {ql['error']}" if 'error' in ql else ""
        print(f"    '{ql['query'][:60]}' → {ql['results']} results, ${ql['cost']:.4f}{err}")

    conn.close()
    return {
        'works_with_source': works_with_source,
        'works_without_source': works_without_source,
        'total_serper_queries': TOTAL_SERP_QUERIES,
        'total_spend': total_spend,
    }


if __name__ == '__main__':
    main()
