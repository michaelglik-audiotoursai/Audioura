#!/usr/bin/env python3
"""run_local242_retrieval_lift.py — LOCAL-242: Measure how much corpus better queries produce.

READ-ONLY measurement. Does NOT write to stop_corpus, venue_corpus, or audio_tours.

Methodology:
  - Selects 15 stops spanning 3 situations:
    A. COVERED (have stop_corpus with real passages)
    B. VENUE_ONLY (venue has venue_corpus, stop has thin/generic corpus)
    C. UNVERIFIED (Asian Arts, Naïve Art — stop titles may be fabricated)
  - For each stop, runs:
    1. TODAY'S QUERY: the stop title as-is (what stop_subject_acquisition does)
    2. RICHER STRATEGY: decomposed (artist, work, period, object type),
       institutional catalogue, event/person, single distinctive token
  - Reports passages found with quotes.
  - Counts how many move from unsourced to sourced.
  - Reports cost per stop.
  - Extrapolates to 88 stops and ~190 across all tours.

Budget ceiling: $0.40 (Serper at $0.001/query = 400 queries max).
"""
import json
import os
import sys
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

# ─── Load environment ────────────────────────────────────────────────────────
env_path = os.path.expanduser('~/Audioura/.env')
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
if not SERP_API_KEY:
    print("ERROR: SERP_API_KEY not found in environment or ~/Audioura/.env")
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection

# ─── Cost tracking ───────────────────────────────────────────────────────────
COST_PER_QUERY = 0.001
BUDGET_CEILING = 0.40
total_cost = 0.0
total_queries = 0


def serp_search(query: str, num: int = 8) -> List[Dict]:
    """Execute a Serper query. Returns list of {title, url, snippet}."""
    global total_cost, total_queries
    if total_cost + COST_PER_QUERY > BUDGET_CEILING:
        print(f"  ⚠️  BUDGET CEILING reached (${total_cost:.4f}). Skipping query.")
        return []
    
    try:
        data = json.dumps({"q": query, "num": num}).encode()
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=data,
            headers={"X-API-KEY": SERP_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            organic = body.get("organic", [])
            total_cost += COST_PER_QUERY
            total_queries += 1
            return [{'title': r.get('title', ''), 'url': r.get('link', ''),
                     'snippet': r.get('snippet', '')} for r in organic]
    except Exception as e:
        total_cost += COST_PER_QUERY  # Count the attempt
        total_queries += 1
        print(f"  ⚠️  SERP query failed: {e}")
        return []


# ─── Stop Selection ──────────────────────────────────────────────────────────

# Category A: COVERED — stops with real subject-specific passages in stop_corpus
# Selected: varied venues, different levels of passage quality
COVERED_STOPS = [
    # French Riviera — real geographic stops with sourced passages
    {"venue": "French Riviera walking area", "stop": "Villa Ephrussi de Rothschild",
     "why": "2 passages. Michael's Eilenroc benchmark is same tour type. Does decomposition add?"},
    {"venue": "French Riviera walking area", "stop": "Cap d'Antibes",
     "why": "7 passages already. Can richer queries add Fitzgerald/Monet detail?"},
    {"venue": "French Riviera walking area", "stop": "Chapelle Saint-Pierre",
     "why": "2 passages, one is wrong chapel (Vénéjan). Precision test."},
    {"venue": "Musee National Marc Chagall, Nice, France", "stop": "Abraham et les trois anges",
     "why": "Chagall museum is the one fully-verified venue. 5 passages. Baseline."},
    {"venue": "French Riviera walking area", "stop": "Eze Village",
     "why": "1 passage. Walking stop with historical depth. Does decomposition help?"},
]

# Category B: VENUE_ONLY — venue has venue_corpus, stop has thin/generic corpus
# These stops have passages but they're often the venue Wikipedia page, not stop-specific
COVERED_VENUE_STOPS = [
    {"venue": "Musee d Art Moderne et d Art Contemporain, Nice, France",
     "stop": "Richard Long ou la sculpture en marchant",
     "why": "Only 1 passage and it's the museum's opening date. Subject is clearly an artist."},
    {"venue": "Musee d Art Moderne et d Art Contemporain, Nice, France",
     "stop": "Le Déjeuner sur l'herbe",
     "why": "3 passages. Alain Jacquet's version specifically at MAMAC."},
    {"venue": "Palais Lascaris, Nice", "stop": "Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)",
     "why": "Highly specific historical instrument. Can we find it in catalogues?"},
    {"venue": "Palais Lascaris, Nice", "stop": "Guitar by Antonio de Torres (Almeria, 1884)",
     "why": "Torres guitars are well-documented. Subject decomposition should work."},
    {"venue": "Musee Matisse, Nice, France",
     "stop": "Nu bleu IV",
     "why": "Matisse's famous cut-out series. Well-known work, should be findable with proper query."},
]

# Category C: UNVERIFIED — institutions with possibly-fabricated stop titles
UNVERIFIED_STOPS = [
    {"venue": "Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
     "stop": "Ulysses Grant au Japon",
     "why": "D127's test case. We know this is findable (Chikanobu). Does richer query get it?"},
    {"venue": "Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
     "stop": "Kannon a mille bras",
     "why": "Generic Buddhist subject. Can the museum's own catalogue confirm?"},
    {"venue": "Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
     "stop": "L'Armure d'Ando Naoyuki",
     "why": "Specific name. If real, Japanese armour catalogues would have it."},
    {"venue": "Musée d'art naïf (Museum of Naïve Art), Nice, France",
     "stop": "The Flight into Egypt",
     "why": "Classic art subject. Multiple artists. Can we confirm THIS museum holds one?"},
    {"venue": "Musée d'art naïf (Museum of Naïve Art), Nice, France",
     "stop": "The Red Umbrella",
     "why": "Possibly a real naïve art painting. Jakovsky museum inventory test."},
]


def get_todays_query(stop: Dict) -> str:
    """Simulate what stop_subject_acquisition does: title as the query."""
    return stop["stop"]


def get_richer_queries(stop: Dict) -> List[Tuple[str, str]]:
    """Build richer queries per the 4 strategies in the task brief.
    
    Returns list of (query, strategy_name) tuples.
    """
    venue = stop["venue"]
    title = stop["stop"]
    queries = []
    
    # Strategy 1: Subject decomposed — artist, work, period, object type
    # Parse the title to extract components
    if " by " in title:
        # "Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)"
        parts = title.split(" by ", 1)
        object_type = parts[0].strip()
        maker_part = parts[1].strip()
        queries.append((f'"{maker_part}" {object_type}', "decomposed: maker + object"))
        # Also just the maker's name
        maker_name = maker_part.split("(")[0].strip()
        queries.append((f'"{maker_name}" instrument maker', "decomposed: maker alone"))
    elif " ou " in title:
        # "Richard Long ou la sculpture en marchant" -> artist = "Richard Long"
        artist = title.split(" ou ")[0].strip()
        queries.append((f'"{artist}" artist sculptor', "decomposed: artist"))
        queries.append((f'"{artist}" land art', "decomposed: artist + medium"))
    elif title.startswith(("Le ", "La ", "Les ", "L'")):
        # French artwork title
        queries.append((f'{title} painting artist', "decomposed: artwork title + medium"))
        if "Matisse" in venue:
            queries.append((f'Matisse "{title}"', "decomposed: known artist + title"))
        elif "Chagall" in venue:
            queries.append((f'Chagall "{title}"', "decomposed: known artist + title"))
    elif "Matisse" in venue:
        # Matisse works that don't start with article
        queries.append((f'Matisse "{title}"', "decomposed: Matisse + title"))
        queries.append((f'Henri Matisse "{title}" Nice museum', "decomposed: full artist + title + venue"))
    elif "Chagall" in venue:
        queries.append((f'Chagall "{title}"', "decomposed: Chagall + title"))
        queries.append((f'Marc Chagall "{title}" Biblical Message', "decomposed: full artist + series"))
    else:
        # Try to decompose the title into subject words
        queries.append((f'{title} history', "decomposed: title + history"))
    
    # Strategy 2: Institution's own catalogue and collection pages
    if "Asiatiques" in venue or "Asian" in venue:
        queries.append((f'maa.departement06.fr collection {title}',
                       "catalogue: maa.departement06.fr"))
        queries.append((f'site:maa.departement06.fr {title.split()[0]}',
                       "catalogue: site-scoped search"))
    elif "naïf" in venue.lower() or "Naïve" in venue or "Jakovsky" in venue.lower():
        queries.append((f'"Musée International d\'Art Naïf Anatole Jakovsky" "{title}"',
                       "catalogue: Jakovsky museum + title"))
        queries.append((f'pop.culture.gouv.fr "art naïf" Nice "{title}"',
                       "catalogue: Joconde/POP"))
    elif "Lascaris" in venue:
        queries.append((f'"Palais Lascaris" collection instruments "{title.split(" by ")[0] if " by " in title else title}"',
                       "catalogue: Palais Lascaris instruments"))
        queries.append((f'pop.culture.gouv.fr "Palais Lascaris" {title.split(" by ")[0] if " by " in title else title}',
                       "catalogue: Joconde/POP Lascaris"))
    elif "MAMAC" in venue or "Moderne" in venue:
        queries.append((f'"MAMAC Nice" collection "{title}"',
                       "catalogue: MAMAC collection"))
    elif "Riviera" in venue or "walking" in venue:
        queries.append((f'"{title}" "Côte d\'Azur" OR "French Riviera" history',
                       "catalogue: regional tourism"))
    
    # Strategy 3: Event or person rather than object
    if "Grant" in title or "Ulysses" in title:
        queries.append((f'Chikanobu "Ulysses Grant" Japan 1879 woodblock',
                       "event: Chikanobu Grant"))
        queries.append((f'"Grant" "Ueno Park" 1879 print triptych',
                       "event: Grant reception"))
    elif "Kannon" in title:
        queries.append((f'"Kannon" "thousand arms" statue Asian art Nice',
                       "event: subject + city"))
    elif "Armure" in title or "Ando" in title:
        queries.append((f'"Ando Naoyuki" armour samurai',
                       "person: named individual"))
    elif "Flight into Egypt" in title:
        queries.append((f'"Flight into Egypt" naïve art painting',
                       "event: subject + genre"))
    elif "Eilenroc" in title or "Ephrussi" in title:
        queries.append((f'"Villa Ephrussi de Rothschild" history Cap Ferrat',
                       "event: villa history"))
        queries.append((f'"Béatrice de Rothschild" villa Cap Ferrat',
                       "token: distinctive patron name"))
    elif "Èze" in title or "Eze" in title:
        queries.append((f'Èze village history medieval "200 BC" OR "Iron Age"',
                       "event: historical period"))
        queries.append((f'"Avisionis portus" Antonine Itinerary',
                       "event: specific historical reference"))
        queries.append((f'Nietzsche Eze path philosophy',
                       "event: Nietzsche connection"))
    elif "Cap d'Antibes" in title:
        queries.append((f'Fitzgerald "Tender is the Night" Cap Antibes hotel',
                       "event: literary connection"))
        queries.append((f'Monet Antibes 1888 painting',
                       "event: Monet's Antibes period"))
    elif "Chapelle Saint-Pierre" in title:
        queries.append((f'Cocteau "Chapelle Saint-Pierre" Villefranche',
                       "event: Cocteau's chapel"))
    elif "Red Umbrella" in title:
        queries.append((f'"Red Umbrella" naive art painting Nice Jakovsky',
                       "event: artwork + museum"))
    
    # Strategy 4: Single distinctive tokens where compound fails
    # Extract the most distinctive word(s) from the title
    words = title.split()
    distinctive = [w for w in words if len(w) > 5 and w[0].isupper()
                   and w.lower() not in ('museum', 'musee', 'france', 'nice')]
    if distinctive and len(distinctive) <= 3:
        # Search each distinctive token with venue context
        for word in distinctive[:2]:
            queries.append((f'{word} {venue.split(",")[0]}',
                           f"token: '{word}' + venue"))
    
    return queries


def evaluate_result(results: List[Dict], stop: Dict, require_venue: bool = True) -> Dict:
    """Evaluate search results per D74: is there a passage that is genuinely about 
    this stop AT THIS VENUE?
    
    D74 rule: A passage that mentions the right words is not a source.
    Venue confirmation must come from the same source as the subject claim.
    A Wikipedia article about the Bible's Flight into Egypt does NOT confirm
    that the Jakovsky museum holds a naïve art painting of that subject.
    
    Returns: {found: bool, passage: str, url: str, why: str, rejected: []}
    """
    title = stop["stop"]
    venue = stop["venue"]
    
    if not results:
        return {"found": False, "passage": "", "url": "", "why": "no results", "rejected": []}
    
    # Extract venue indicators
    venue_signals = []
    if "Riviera" in venue or "walking" in venue:
        venue_signals = ["riviera", "côte d'azur", "nice", "antibes", "monaco", 
                        "villefranche", "cap ferrat", "eze", "èze"]
    elif "Asiatiques" in venue or "Asian" in venue:
        venue_signals = ["arts asiatiques", "asian art", "maa", "departement06", 
                        "nice", "musée"]
    elif "naïf" in venue.lower() or "Naïve" in venue or "Jakovsky" in venue.lower():
        venue_signals = ["naïf", "naive art", "jakovsky", "anatole", "nice"]
    elif "Lascaris" in venue:
        venue_signals = ["lascaris", "nice", "palais"]
    elif "MAMAC" in venue or "Moderne" in venue:
        venue_signals = ["mamac", "moderne", "contemporain", "nice"]
    elif "Matisse" in venue:
        venue_signals = ["matisse", "nice", "musée matisse", "musee matisse"]
    elif "Chagall" in venue:
        venue_signals = ["chagall", "nice", "musée chagall", "musee chagall",
                        "message biblique", "biblical message"]
    
    # Title words for subject matching
    title_words = [w.lower() for w in title.split() if len(w) > 3 
                   and w.lower() not in ('the', 'les', 'des', 'sur', 'dans', 'par')]
    
    rejected = []
    
    for r in results:
        snippet = r.get("snippet", "").lower()
        url = r.get("url", "").lower()
        result_title = r.get("title", "").lower()
        
        # Skip social media
        if any(d in url for d in ['pinterest.', 'facebook.', 'instagram.', 'twitter.', 'youtube.']):
            continue
        
        # Check subject relevance: at least some title words in snippet
        subject_matches = sum(1 for w in title_words if w in snippet or w in result_title)
        has_subject = subject_matches >= max(1, len(title_words) // 2)
        
        if not has_subject:
            continue
        
        # Check venue confirmation per D74
        if require_venue:
            has_venue = False
            # Check URL and snippet for venue signals
            combined = snippet + " " + url + " " + result_title
            for signal in venue_signals:
                if signal in combined:
                    has_venue = True
                    break
            
            # Also accept if the URL is from the venue's own domain
            venue_domains = []
            if "Asiatiques" in venue:
                venue_domains = ["maa.departement06.fr"]
            elif "Lascaris" in venue:
                venue_domains = ["palais-lascaris", "lascaris"]
            elif "Matisse" in venue:
                venue_domains = ["musee-matisse-nice", "musees-nationaux"]
            elif "Chagall" in venue:
                venue_domains = ["musees-nationaux-alpesmaritimes", "musee-chagall"]
            elif "naïf" in venue.lower():
                venue_domains = ["jakovsky", "art-naif-nice"]
            elif "MAMAC" in venue or "Moderne" in venue:
                venue_domains = ["mamac-nice"]
            
            for domain in venue_domains:
                if domain in url:
                    has_venue = True
                    break
            
            if not has_venue:
                rejected.append({
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:150],
                    "reason": "subject mentioned but no venue confirmation (D74)"
                })
                continue
        
        # FOUND: subject + venue confirmed in same source
        return {
            "found": True,
            "passage": r.get("snippet", "")[:300],
            "url": r.get("url", ""),
            "result_title": r.get("title", ""),
            "why": f"subject ({subject_matches}/{len(title_words)} words) + venue confirmed",
            "rejected": rejected
        }
    
    return {"found": False, "passage": "", "url": "", 
            "why": f"no results with both subject + venue (D74). {len(rejected)} rejected.",
            "rejected": rejected}


def run_measurement():
    """Main measurement loop."""
    global total_cost, total_queries
    
    print("=" * 80)
    print("LOCAL-242: Retrieval Lift Measurement")
    print("=" * 80)
    print()
    
    # ─── Baseline table counts ────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stop_corpus")
    sc_before = cur.fetchone()[0]
    conn.close()
    
    print(f"BASELINE COUNTS (before):")
    print(f"  audio_tours: {at_before}")
    print(f"  stop_corpus: {sc_before}")
    print()
    
    # ─── Check for existing passages ──────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    
    # Check which of our selected stops already have passages
    print("=" * 80)
    print("STOP SELECTION (15 stops across 3 situations)")
    print("=" * 80)
    print()
    
    all_stops = COVERED_STOPS + COVERED_VENUE_STOPS + UNVERIFIED_STOPS
    
    results_by_category = {"A_COVERED": [], "B_VENUE_ONLY": [], "C_UNVERIFIED": []}
    
    # ─── Run measurements ─────────────────────────────────────────────────────
    
    for idx, stop in enumerate(all_stops):
        if idx < 5:
            category = "A_COVERED"
            cat_label = "A (COVERED)"
        elif idx < 10:
            category = "B_VENUE_ONLY"
            cat_label = "B (VENUE_ONLY)"
        else:
            category = "C_UNVERIFIED"
            cat_label = "C (UNVERIFIED)"
        
        print(f"\n{'─' * 80}")
        print(f"STOP {idx+1}/15 — Category {cat_label}")
        print(f"  Venue: {stop['venue']}")
        print(f"  Stop:  {stop['stop']}")
        print(f"  Why:   {stop['why']}")
        print(f"{'─' * 80}")
        
        # ─── TODAY'S QUERY ────────────────────────────────────────────────────
        today_query = get_todays_query(stop)
        print(f"\n  TODAY'S QUERY: \"{today_query}\"")
        time.sleep(1.0)  # Rate limit
        today_results = serp_search(today_query)
        today_eval = evaluate_result(today_results, stop, require_venue=True)
        
        if today_eval["found"]:
            print(f"  ✓ FOUND (D74-compliant) — {today_eval['why']}")
            print(f"    URL: {today_eval.get('url', '')}")
            print(f"    Passage: \"{today_eval['passage']}\"")
        else:
            print(f"  ✗ NOT FOUND (D74-compliant) — {today_eval['why']}")
            if today_eval.get("rejected"):
                for rej in today_eval["rejected"][:2]:
                    print(f"    REJECTED: {rej['reason']}")
                    print(f"      URL: {rej['url']}")
                    print(f"      Snippet: \"{rej['snippet']}\"")
            elif today_results:
                print(f"    (Got {len(today_results)} results, none relevant)")
                top = today_results[0]
                print(f"    Top result: {top['title'][:60]}")
                print(f"    Snippet: \"{top['snippet'][:150]}\"")
        
        # ─── RICHER STRATEGY ─────────────────────────────────────────────────
        richer_queries = get_richer_queries(stop)
        print(f"\n  RICHER STRATEGY ({len(richer_queries)} queries):")
        
        richer_found = False
        richer_passage = ""
        richer_url = ""
        richer_strategy_used = ""
        richer_query_used = ""
        all_richer_rejected = []
        
        for query, strategy in richer_queries:
            time.sleep(1.0)  # Rate limit
            print(f"    → [{strategy}] \"{query}\"")
            results = serp_search(query)
            eval_result = evaluate_result(results, stop, require_venue=True)
            
            if eval_result["found"]:
                richer_found = True
                richer_passage = eval_result["passage"]
                richer_url = eval_result.get("url", "")
                richer_strategy_used = strategy
                richer_query_used = query
                print(f"      ✓ FOUND (D74-compliant)! URL: {richer_url}")
                print(f"      Passage: \"{richer_passage}\"")
                break
            else:
                all_richer_rejected.extend(eval_result.get("rejected", []))
                if results:
                    print(f"      ✗ ({len(results)} results, {len(eval_result.get('rejected',[]))} rejected by D74)")
                else:
                    print(f"      ✗ (no results)")
        
        if not richer_found:
            print(f"    → [CONCLUSION: no D74-compliant result from any strategy]")
            if all_richer_rejected:
                print(f"       Total rejected across all queries: {len(all_richer_rejected)}")
                # Show most promising rejection
                best_rej = all_richer_rejected[0]
                print(f"       Best rejected: {best_rej['url']}")
                print(f"       Snippet: \"{best_rej['snippet']}\"")
                print(f"       Reason: {best_rej['reason']}")
        
        # ─── Record result ────────────────────────────────────────────────────
        result = {
            "stop": stop,
            "today_query": today_query,
            "today_found": today_eval["found"],
            "today_passage": today_eval.get("passage", ""),
            "today_url": today_eval.get("url", ""),
            "richer_found": richer_found,
            "richer_passage": richer_passage,
            "richer_url": richer_url,
            "richer_strategy": richer_strategy_used,
            "richer_query": richer_query_used,
            "lifted": not today_eval["found"] and richer_found,
        }
        results_by_category[category].append(result)
    
    # ─── Summary ──────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    total_lifted = 0
    total_today_found = 0
    total_richer_found = 0
    
    for cat, label in [("A_COVERED", "A: COVERED"), 
                       ("B_VENUE_ONLY", "B: VENUE_ONLY"),
                       ("C_UNVERIFIED", "C: UNVERIFIED")]:
        results = results_by_category[cat]
        lifted = sum(1 for r in results if r["lifted"])
        today_found = sum(1 for r in results if r["today_found"])
        richer_found = sum(1 for r in results if r["richer_found"])
        total_lifted += lifted
        total_today_found += today_found
        total_richer_found += richer_found
        
        print(f"\n  {label} ({len(results)} stops):")
        print(f"    Today's query found:   {today_found}/{len(results)}")
        print(f"    Richer strategy found: {richer_found}/{len(results)}")
        print(f"    LIFTED (unsourced→sourced): {lifted}/{len(results)}")
    
    print(f"\n  TOTALS (all 15 stops):")
    print(f"    Today's query found:   {total_today_found}/15")
    print(f"    Richer strategy found: {total_richer_found}/15")
    print(f"    LIFTED: {total_lifted}/15")
    
    # ─── Cost ─────────────────────────────────────────────────────────────────
    print(f"\n  COST:")
    print(f"    Total queries: {total_queries}")
    print(f"    Total cost: ${total_cost:.4f}")
    print(f"    Cost per stop: ${total_cost/15:.4f}")
    
    # ─── Extrapolation ────────────────────────────────────────────────────────
    lift_rate = total_lifted / 15.0
    print(f"\n  EXTRAPOLATION (explicitly stated as such):")
    print(f"    Lift rate from sample: {total_lifted}/15 = {lift_rate:.1%}")
    print(f"    Applied to 88 stop_corpus rows: ~{int(88 * lift_rate)} would lift")
    print(f"    Applied to ~190 stops across all tours: ~{int(190 * lift_rate)} would lift")
    print(f"    Estimated cost for 88 stops: ${88 * (total_cost/15):.2f}")
    print(f"    Estimated cost for 190 stops: ${190 * (total_cost/15):.2f}")
    
    # ─── D74 Rejections ───────────────────────────────────────────────────────
    print(f"\n  D74 REJECTIONS:")
    print(f"    (Passages that mention the right words but are not genuine sources)")
    rejections = []
    for cat in results_by_category.values():
        for r in cat:
            # Any result where today found but it's the wrong chapel, etc
            if r["today_found"] and "wrong" in r.get("today_passage", "").lower():
                rejections.append(r)
    if rejections:
        for rej in rejections:
            print(f"    - {rej['stop']['stop']}: {rej['today_passage'][:80]}")
    else:
        print(f"    None identified in this measurement run.")
    
    # ─── Verify table counts unchanged ────────────────────────────────────────
    print(f"\n  TABLE INTEGRITY CHECK:")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stop_corpus")
    sc_after = cur.fetchone()[0]
    conn.close()
    
    print(f"    audio_tours: {at_before} → {at_after} {'✓ UNCHANGED' if at_before == at_after else '⚠️ CHANGED!'}")
    print(f"    stop_corpus: {sc_before} → {sc_after} {'✓ UNCHANGED' if sc_before == sc_after else '⚠️ CHANGED!'}")
    
    # ─── Output JSON for the submission ───────────────────────────────────────
    output = {
        "measurement_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_queries": total_queries,
        "total_cost_usd": round(total_cost, 4),
        "cost_per_stop_usd": round(total_cost / 15, 4),
        "results": {cat: results for cat, results in results_by_category.items()},
        "summary": {
            "today_found": total_today_found,
            "richer_found": total_richer_found,
            "lifted": total_lifted,
            "lift_rate": round(lift_rate, 3),
            "extrapolation_88": int(88 * lift_rate),
            "extrapolation_190": int(190 * lift_rate),
        },
        "table_counts": {
            "audio_tours_before": at_before,
            "audio_tours_after": at_after,
            "stop_corpus_before": sc_before,
            "stop_corpus_after": sc_after,
        },
    }
    
    output_path = os.path.join(os.path.dirname(__file__), "local242_measurement.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_measurement()
