#!/usr/bin/env python3
"""wayback_wikipedia_probe.py — LOCAL-447 Part 1: Measure Wayback as a Wikipedia substitute.

Draws 30 real titles from stop_corpus (including French titles), accent-folds them
per D243, and measures:
  1. Coverage — fraction with any Wayback snapshot, for /wiki/X and REST URL, separately.
  2. Freshness — median snapshot age in days (reuses _parse_wayback_timestamp logic).
  3. Latency — median and p90 for Wayback fetch vs healthy Wikipedia for same titles.
  4. Content equivalence — archived lead section vs live REST extract (same/degraded/wrong).

Rate-limiting: spaces requests to avoid triggering dead_host_breaker or Wayback 429s.
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

# ─── DB connection (reuse project pattern) ───────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection


# ─── Accent folding (D243 pattern, same as dining_corpus_harvester.py) ───────

def _strip_accents(text: str) -> str:
    """Remove accents for matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_for_wiki(title: str) -> str:
    """Normalise a title for use as a Wikipedia article name.
    
    - Strip accents for the lookup attempt
    - Replace spaces with underscores (Wikipedia convention)
    - URL-encode
    """
    return title.strip().replace(' ', '_')


def _shorten_title(title: str) -> str:
    """Shorten a composite French museum/place name for retry.
    
    E.g. "Musée Océanographique de Monaco" → "Musée Océanographique"
    Drops trailing "de/d'/du/des + city" or "(qualifier)" suffixes.
    """
    # Remove parenthetical qualifiers
    shortened = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()
    # Remove trailing "de/d'/du/des/à + word(s)" (French location suffixes)
    shortened = re.sub(r'\s+(?:de|d\'|du|des|à)\s+\S+(?:\s+\S+)?$', '', shortened, flags=re.IGNORECASE).strip()
    if shortened and shortened != title and len(shortened) > 3:
        return shortened
    return ''


# ─── Wayback timestamp parser (reused from exhibition_checklist.py) ──────────

def _parse_wayback_timestamp(url_or_ts: str) -> Optional[datetime]:
    """Parse a Wayback Machine timestamp (YYYYMMDDHHmmss) from a URL or raw string."""
    m = re.search(r'/web/(\d{14})/', url_or_ts)
    if not m:
        m = re.match(r'^(\d{14})$', url_or_ts.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ─── HTTP helpers ────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': 'Audioura/2.2 (LOCAL-447 probe; contact: support@audioura.com)',
}

WAYBACK_HEADERS = {
    'User-Agent': 'Audioura/2.2 LOCAL-447 WaybackProbe',
}


def fetch_wikipedia_rest(title: str, timeout: float = 8.0) -> Tuple[Optional[str], float]:
    """Fetch Wikipedia REST summary. Returns (extract_or_None, latency_seconds)."""
    encoded = quote(title.strip().replace(' ', '_'), safe='')
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    t0 = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        latency = time.time() - t0
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get('extract', '')
            return (extract if extract else None), latency
        return None, latency
    except Exception:
        return None, time.time() - t0


def check_wayback_snapshot(url: str, timeout: float = 15.0) -> Tuple[bool, Optional[datetime], float]:
    """Check if Wayback has a snapshot. Uses the availability API (fast, no full fetch).
    
    Returns (has_snapshot, snapshot_datetime_or_None, latency_seconds).
    """
    api_url = f"https://archive.org/wayback/available?url={quote(url, safe='')}"
    t0 = time.time()
    try:
        resp = requests.get(api_url, headers=WAYBACK_HEADERS, timeout=timeout)
        latency = time.time() - t0
        if resp.status_code == 200:
            data = resp.json()
            closest = data.get('archived_snapshots', {}).get('closest')
            if closest and closest.get('available'):
                ts_str = closest.get('timestamp', '')
                ts_dt = _parse_wayback_timestamp(ts_str) if ts_str else None
                return True, ts_dt, latency
        return False, None, latency
    except Exception:
        return False, None, time.time() - t0


def fetch_wayback_page(wiki_title: str, timeout: float = 20.0) -> Tuple[Optional[str], float, Optional[datetime]]:
    """Fetch the archived Wikipedia article page (/wiki/X) and extract the lead section.
    
    Returns (lead_text_or_None, latency_seconds, snapshot_datetime_or_None).
    """
    encoded = quote(wiki_title.strip().replace(' ', '_'), safe='')
    article_url = f"https://en.wikipedia.org/wiki/{encoded}"
    wayback_url = f"https://web.archive.org/web/2/{article_url}"
    
    t0 = time.time()
    try:
        resp = requests.get(wayback_url, headers=WAYBACK_HEADERS, timeout=timeout, allow_redirects=True)
        latency = time.time() - t0
        if resp.status_code != 200:
            return None, latency, None
        
        # Parse snapshot timestamp from final URL
        final_url = resp.url if isinstance(resp.url, str) else str(resp.url)
        snapshot_dt = _parse_wayback_timestamp(final_url)
        
        html = resp.text
        if not html or len(html) < 500:
            return None, latency, snapshot_dt
        
        # Extract lead section: paragraphs before the first <h2> (table of contents start)
        # Wikipedia articles have the lead before the first section heading
        lead_html = re.split(r'<h2', html, maxsplit=1)[0]
        
        # Extract text from paragraphs in the lead
        paragraphs = []
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', lead_html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            # Remove citation brackets [1], [2], etc.
            clean = re.sub(r'\[\d+\]', '', clean).strip()
            if clean and len(clean) > 30:
                paragraphs.append(clean)
        
        lead_text = '\n'.join(paragraphs)
        return (lead_text if lead_text else None), latency, snapshot_dt
    except Exception:
        return None, time.time() - t0, None


def fetch_wayback_rest(wiki_title: str, timeout: float = 15.0) -> Tuple[bool, float]:
    """Check if the REST API URL has a Wayback snapshot (availability only).
    
    Returns (has_snapshot, latency_seconds).
    """
    encoded = quote(wiki_title.strip().replace(' ', '_'), safe='')
    rest_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    has, _, latency = check_wayback_snapshot(rest_url, timeout)
    return has, latency


# ─── Content comparison ──────────────────────────────────────────────────────

def compare_extracts(live_extract: str, wayback_lead: str) -> str:
    """Compare live REST extract with archived lead section.
    
    Returns: 'same', 'degraded', or 'wrong'.
    - same: core facts match (names, dates, key descriptors)
    - degraded: archived version has less info but nothing incorrect
    - wrong: archived version contains contradictory facts
    """
    if not live_extract or not wayback_lead:
        return 'degraded'
    
    live_lower = _strip_accents(live_extract).lower()
    wb_lower = _strip_accents(wayback_lead).lower()
    
    # Extract key facts from live extract: years, proper nouns, numbers
    live_years = set(re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', live_extract))
    wb_years = set(re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', wayback_lead))
    
    # Check if the first sentence core matches
    live_first = live_lower.split('.')[0] if '.' in live_lower else live_lower[:200]
    
    # Key words from live (significant words > 4 chars)
    live_words = set(w for w in re.findall(r'\b\w{5,}\b', live_lower))
    wb_words = set(w for w in re.findall(r'\b\w{5,}\b', wb_lower))
    
    if not wb_words:
        return 'degraded'
    
    overlap = len(live_words & wb_words) / max(len(live_words), 1)
    
    # Check for year contradictions (a year in live NOT in wayback is fine;
    # a year in wayback that contradicts live is 'wrong')
    # Actually, different years are common due to updates — only flag if
    # the wayback text directly contradicts a clear factual claim
    
    if overlap >= 0.5:
        return 'same'
    elif overlap >= 0.2:
        return 'degraded'
    else:
        # Very low overlap — could be wrong page or major rewrite
        # Check if at least the subject name appears
        # Use first significant word from live_first as subject indicator
        subject_words = [w for w in live_first.split() if len(w) > 3][:3]
        subject_in_wb = sum(1 for w in subject_words if w in wb_lower)
        if subject_in_wb >= 2:
            return 'degraded'
        return 'wrong'


# ─── Main probe ──────────────────────────────────────────────────────────────

def draw_titles_from_corpus(n: int = 30) -> List[Dict]:
    """Draw n titles from stop_corpus, including French titles.
    
    Returns list of dicts with 'stop_title', 'venue_name'.
    Ensures a mix: at least 10 French-looking titles, at least 5 English titles.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all distinct titles with their venue
    cur.execute("""
        SELECT DISTINCT ON (stop_title) stop_title, venue_name 
        FROM stop_corpus 
        WHERE stop_title IS NOT NULL AND length(stop_title) > 2
        ORDER BY stop_title, venue_name
    """)
    all_rows = [{'stop_title': r[0], 'venue_name': r[1]} for r in cur.fetchall()]
    conn.close()
    
    # Separate French-looking vs English titles
    french_indicators = re.compile(r'[éèêëàâùûôîïç]|(?:^|\s)(?:le|la|les|du|des|un|une)\s', re.IGNORECASE)
    french = [r for r in all_rows if french_indicators.search(r['stop_title'])]
    english = [r for r in all_rows if r not in french]
    
    # Aim for a representative mix
    import random
    random.seed(447)  # Reproducible
    
    selected = []
    # Take up to 15 French titles
    selected.extend(random.sample(french, min(15, len(french))))
    # Fill remaining from English
    remaining = n - len(selected)
    selected.extend(random.sample(english, min(remaining, len(english))))
    
    # If still short, fill from whichever has more
    if len(selected) < n:
        pool = [r for r in all_rows if r not in selected]
        selected.extend(random.sample(pool, min(n - len(selected), len(pool))))
    
    return selected[:n]


def resolve_wikipedia_title(stop_title: str, venue_name: str = '') -> List[str]:
    """Generate candidate Wikipedia titles for a stop_corpus entry.
    
    Returns a list of titles to try, in order:
      1. Original title
      2. Accent-folded title  
      3. Shortened form (drop location qualifiers)
    """
    candidates = [stop_title]
    
    # Accent-folded version
    folded = _strip_accents(stop_title)
    if folded != stop_title:
        candidates.append(folded)
    
    # Shortened form
    short = _shorten_title(stop_title)
    if short:
        candidates.append(short)
        short_folded = _strip_accents(short)
        if short_folded != short:
            candidates.append(short_folded)
    
    return candidates


def run_probe():
    """Run the full measurement probe."""
    print("=" * 70)
    print("LOCAL-447 Part 1: Wayback Machine as Wikipedia Substitute — Probe")
    print("=" * 70)
    print()
    
    # Draw 30 titles
    print("[1/5] Drawing 30 titles from stop_corpus...")
    titles = draw_titles_from_corpus(30)
    print(f"  Drawn {len(titles)} titles ({sum(1 for t in titles if re.search(r'[éèêëàâùûôîïç]', t['stop_title']))} with accents)")
    print()
    
    # Results storage
    results = []
    
    # ─── Measure each title ──────────────────────────────────────────────────
    print("[2/5] Measuring coverage, latency, and content for each title...")
    print("  (Spacing requests to avoid rate limits)")
    print()
    
    for i, entry in enumerate(titles):
        title = entry['stop_title']
        venue = entry['venue_name']
        print(f"  [{i+1:2d}/30] {title}")
        
        result = {
            'stop_title': title,
            'venue_name': venue,
            'candidates_tried': [],
            'wikipedia_found': False,
            'wikipedia_extract': None,
            'wikipedia_latency': None,
            'wayback_wiki_has_snapshot': False,
            'wayback_wiki_snapshot_age_days': None,
            'wayback_wiki_latency': None,
            'wayback_wiki_lead': None,
            'wayback_rest_has_snapshot': False,
            'content_verdict': None,
        }
        
        # Step 1: Try Wikipedia REST API with candidate titles
        candidates = resolve_wikipedia_title(title, venue)
        result['candidates_tried'] = candidates
        
        wiki_extract = None
        wiki_latency = None
        wiki_title_used = None
        
        for candidate in candidates:
            extract, latency = fetch_wikipedia_rest(candidate)
            if extract:
                wiki_extract = extract
                wiki_latency = latency
                wiki_title_used = candidate
                break
            time.sleep(0.5)  # Space requests
        
        if wiki_extract:
            result['wikipedia_found'] = True
            result['wikipedia_extract'] = wiki_extract[:2000]  # Cap for storage
            result['wikipedia_latency'] = wiki_latency
            print(f"         Wikipedia: ✓ found ({len(wiki_extract)} chars, {wiki_latency:.2f}s) via '{wiki_title_used}'")
        else:
            print(f"         Wikipedia: ✗ not found (tried {len(candidates)} variants)")
        
        time.sleep(1.0)  # Rate limit spacing
        
        # Step 2: Check Wayback for the article page URL (/wiki/X)
        # Use the title that worked for Wikipedia, or the original
        check_title = wiki_title_used or title
        
        wb_lead, wb_latency, wb_snapshot_dt = fetch_wayback_page(check_title)
        
        if wb_lead:
            result['wayback_wiki_has_snapshot'] = True
            result['wayback_wiki_lead'] = wb_lead[:2000]
            result['wayback_wiki_latency'] = wb_latency
            if wb_snapshot_dt:
                age = (datetime.now(timezone.utc) - wb_snapshot_dt).days
                result['wayback_wiki_snapshot_age_days'] = age
                print(f"         Wayback /wiki/: ✓ snapshot ({len(wb_lead)} chars, age {age}d, {wb_latency:.2f}s)")
            else:
                print(f"         Wayback /wiki/: ✓ snapshot ({len(wb_lead)} chars, {wb_latency:.2f}s)")
        else:
            result['wayback_wiki_has_snapshot'] = False
            result['wayback_wiki_latency'] = wb_latency
            print(f"         Wayback /wiki/: ✗ no usable snapshot ({wb_latency:.2f}s)")
        
        time.sleep(1.5)  # Wayback rate limit is tighter
        
        # Step 3: Check if Wayback has the REST API URL (availability check only)
        rest_has, rest_latency = fetch_wayback_rest(check_title)
        result['wayback_rest_has_snapshot'] = rest_has
        print(f"         Wayback REST: {'✓' if rest_has else '✗'} ({rest_latency:.2f}s)")
        
        time.sleep(1.5)
        
        # Step 4: Content comparison (if both succeeded)
        if wiki_extract and wb_lead:
            verdict = compare_extracts(wiki_extract, wb_lead)
            result['content_verdict'] = verdict
            print(f"         Content: {verdict}")
        
        results.append(result)
        print()
    
    # ─── Aggregate and report ────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    
    # Coverage
    wiki_found = sum(1 for r in results if r['wikipedia_found'])
    wb_wiki_found = sum(1 for r in results if r['wayback_wiki_has_snapshot'])
    wb_rest_found = sum(1 for r in results if r['wayback_rest_has_snapshot'])
    
    print(f"[COVERAGE] (n={len(results)} titles)")
    print(f"  Wikipedia REST (live):        {wiki_found}/{len(results)} ({wiki_found/len(results)*100:.0f}%)")
    print(f"  Wayback /wiki/ page:          {wb_wiki_found}/{len(results)} ({wb_wiki_found/len(results)*100:.0f}%)")
    print(f"  Wayback REST API URL:         {wb_rest_found}/{len(results)} ({wb_rest_found/len(results)*100:.0f}%)")
    print()
    
    # Coverage conditional: of titles Wikipedia found, how many does Wayback also have?
    wiki_found_set = [r for r in results if r['wikipedia_found']]
    if wiki_found_set:
        wb_of_wiki = sum(1 for r in wiki_found_set if r['wayback_wiki_has_snapshot'])
        print(f"  Wayback /wiki/ GIVEN wiki exists: {wb_of_wiki}/{len(wiki_found_set)} ({wb_of_wiki/len(wiki_found_set)*100:.0f}%)")
    
    # Coverage for titles Wikipedia did NOT find
    wiki_miss_set = [r for r in results if not r['wikipedia_found']]
    if wiki_miss_set:
        wb_of_miss = sum(1 for r in wiki_miss_set if r['wayback_wiki_has_snapshot'])
        print(f"  Wayback /wiki/ GIVEN wiki 404:    {wb_of_miss}/{len(wiki_miss_set)} ({wb_of_miss/len(wiki_miss_set)*100:.0f}%)")
    print()
    
    # Freshness
    ages = [r['wayback_wiki_snapshot_age_days'] for r in results if r['wayback_wiki_snapshot_age_days'] is not None]
    if ages:
        print(f"[FRESHNESS] (n={len(ages)} snapshots with parseable timestamps)")
        print(f"  Median snapshot age: {median(ages):.0f} days")
        print(f"  Min: {min(ages)} days, Max: {max(ages)} days")
        print(f"  Snapshots < 90 days old: {sum(1 for a in ages if a < 90)}/{len(ages)}")
        print(f"  Snapshots < 365 days old: {sum(1 for a in ages if a < 365)}/{len(ages)}")
    else:
        print("[FRESHNESS] No parseable snapshot timestamps found.")
    print()
    
    # Latency
    wiki_latencies = [r['wikipedia_latency'] for r in results if r['wikipedia_latency'] is not None]
    wb_latencies = [r['wayback_wiki_latency'] for r in results if r['wayback_wiki_has_snapshot'] and r['wayback_wiki_latency'] is not None]
    
    print(f"[LATENCY]")
    if wiki_latencies:
        wiki_latencies_sorted = sorted(wiki_latencies)
        p90_idx = int(len(wiki_latencies_sorted) * 0.9)
        print(f"  Wikipedia REST (n={len(wiki_latencies)}):  median={median(wiki_latencies):.2f}s  p90={wiki_latencies_sorted[min(p90_idx, len(wiki_latencies_sorted)-1)]:.2f}s")
    if wb_latencies:
        wb_latencies_sorted = sorted(wb_latencies)
        p90_idx = int(len(wb_latencies_sorted) * 0.9)
        print(f"  Wayback /wiki/ (n={len(wb_latencies)}):   median={median(wb_latencies):.2f}s  p90={wb_latencies_sorted[min(p90_idx, len(wb_latencies_sorted)-1)]:.2f}s")
    
    if wiki_latencies and wb_latencies:
        ratio = median(wb_latencies) / median(wiki_latencies) if median(wiki_latencies) > 0 else float('inf')
        print(f"  Wayback/Wikipedia ratio: {ratio:.1f}x")
        # The rag_retriever uses a 5s timeout for REST, 10s for action API
        over_5s = sum(1 for l in wb_latencies if l > 5.0)
        print(f"  Wayback fetches exceeding 5s timeout budget: {over_5s}/{len(wb_latencies)}")
    print()
    
    # Content equivalence
    verdicts = [r['content_verdict'] for r in results if r['content_verdict'] is not None]
    if verdicts:
        same_count = verdicts.count('same')
        degraded_count = verdicts.count('degraded')
        wrong_count = verdicts.count('wrong')
        print(f"[CONTENT EQUIVALENCE] (n={len(verdicts)} titles where both sources succeeded)")
        print(f"  Same:     {same_count} ({same_count/len(verdicts)*100:.0f}%)")
        print(f"  Degraded: {degraded_count} ({degraded_count/len(verdicts)*100:.0f}%)")
        print(f"  Wrong:    {wrong_count} ({wrong_count/len(verdicts)*100:.0f}%)")
        print()
        
        # Show 3 side-by-side examples
        print("[SIDE-BY-SIDE EXAMPLES] (first 3 titles where both succeeded)")
        print("-" * 70)
        examples = [r for r in results if r['content_verdict'] is not None][:3]
        for ex in examples:
            print(f"  Title: {ex['stop_title']}")
            print(f"  Verdict: {ex['content_verdict']}")
            print(f"  --- Live Wikipedia extract (first 300 chars) ---")
            print(f"  {(ex.get('wikipedia_extract') or '')[:300]}")
            print(f"  --- Wayback lead section (first 300 chars) ---")
            print(f"  {(ex.get('wayback_wiki_lead') or '')[:300]}")
            print(f"  {'-' * 70}")
    else:
        print("[CONTENT EQUIVALENCE] No titles with both sources succeeding.")
    print()
    
    # ─── Verdict ─────────────────────────────────────────────────────────────
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    # Decision logic
    viable = True
    reasons = []
    
    if wb_wiki_found / len(results) < 0.5:
        viable = False
        reasons.append(f"Coverage too low: only {wb_wiki_found}/{len(results)} titles have Wayback snapshots")
    
    if wb_latencies and median(wb_latencies) > 5.0:
        viable = False
        reasons.append(f"Latency too high: median {median(wb_latencies):.1f}s exceeds 5s timeout budget")
    
    if verdicts and wrong_count / len(verdicts) > 0.2:
        viable = False
        reasons.append(f"Content quality: {wrong_count}/{len(verdicts)} 'wrong' exceeds 20% threshold")
    
    if viable:
        print("  Wayback IS a viable substitute for failed Wikipedia fetches.")
        print("  Proceed to Part 2 (wiring).")
    else:
        print("  Wayback is NOT a viable substitute for Wikipedia.")
        for reason in reasons:
            print(f"    • {reason}")
        print()
        print("  However, the DB-first path (Part 2a) is justified regardless —")
        print("  stop_corpus already holds fetched Wikipedia content.")
    
    print()
    
    # ─── Save raw data ───────────────────────────────────────────────────────
    output_path = Path(__file__).parent / 'tests' / 'fixtures' / 'wayback_probe_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Serialise (strip large text for the fixture, keep in results table)
    fixture_data = {
        'probe_timestamp': datetime.now(timezone.utc).isoformat(),
        'n_titles': len(results),
        'summary': {
            'wikipedia_coverage': f"{wiki_found}/{len(results)}",
            'wayback_wiki_coverage': f"{wb_wiki_found}/{len(results)}",
            'wayback_rest_coverage': f"{wb_rest_found}/{len(results)}",
            'median_snapshot_age_days': median(ages) if ages else None,
            'median_wiki_latency_s': median(wiki_latencies) if wiki_latencies else None,
            'median_wayback_latency_s': median(wb_latencies) if wb_latencies else None,
            'content_same': same_count if verdicts else 0,
            'content_degraded': degraded_count if verdicts else 0,
            'content_wrong': wrong_count if verdicts else 0,
            'viable': viable,
            'reasons': reasons,
        },
        'per_title': results,
    }
    
    with open(output_path, 'w') as f:
        json.dump(fixture_data, f, indent=2, default=str)
    
    print(f"[RAW DATA] Saved to {output_path}")
    print()
    
    return fixture_data


if __name__ == '__main__':
    run_probe()
