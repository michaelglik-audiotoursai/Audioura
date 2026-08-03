#!/usr/bin/env python3
"""stop_anchor_detector_v2_with_stop_corpus.py — LOCAL-177

Round 4a: Let the v2 detector read stop_corpus.

WHAT CHANGES: Only the corpus lookup. When a stop has a row in stop_corpus,
its attributed passages are prepended to the anchor-building step. The
classification rules, sibling discrimination, navigation detection, and
thresholds are IDENTICAL to stop_anchor_detector_v2.py.

WHAT DOES NOT CHANGE:
- classify_paragraph() — untouched, imported from v2
- build_corpus_anchors() — untouched, imported from v2
- build_sibling_corpus_texts() — untouched, imported from v2
- is_navigation_paragraph() — untouched, imported from v2
- The 50% sibling threshold
- The NAVIGATION patterns
- The geographic self-reference exclusion

This script runs BOTH modes over the same 7 tours:
  Mode A: venue_corpus only (the 4.2% baseline — must reproduce exactly)
  Mode B: stop_corpus first, venue_corpus fallback

$0.00 API spend. Read-only against the database.
"""
import sys
import json
from typing import Dict, List, Optional

sys.path.insert(0, 'tests')
from db_connection import get_connection

# Import ALL detection logic from v2 — unchanged
from stop_anchor_detector_v2 import (
    analyze_tour,
    get_venue_corpus_for_tour,
    build_corpus_anchors,
    build_sibling_corpus_texts,
    classify_paragraph,
    is_navigation_paragraph,
    parse_tour_stops,
    extract_entities,
    _normalize_for_match,
)


# ─── NEW: stop_corpus lookup ────────────────────────────────────────────────

def get_stop_corpus_passages(venue_name: str, stop_title: str, conn) -> Optional[List[Dict]]:
    """Look up per-stop passages from stop_corpus table.
    
    Returns list of passage dicts [{text, method, ...}] or None if no row.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Exact match first
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
        (venue_name, stop_title)
    )
    row = cur.fetchone()
    if row:
        passages = row['passages_json']
        if isinstance(passages, str):
            passages = json.loads(passages)
        return passages if passages else None
    
    # Fuzzy: ILIKE on stop_title within same venue
    cur.execute(
        "SELECT passages_json, stop_title FROM stop_corpus WHERE venue_name = %s AND stop_title ILIKE %s",
        (venue_name, f'%{stop_title}%')
    )
    row = cur.fetchone()
    if row:
        passages = row['passages_json']
        if isinstance(passages, str):
            passages = json.loads(passages)
        return passages if passages else None
    
    # Reverse fuzzy: stop_corpus title contained in our title
    cur.execute(
        "SELECT passages_json, stop_title FROM stop_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    rows = cur.fetchall()
    stop_norm = _normalize_for_match(stop_title)
    for r in rows:
        corpus_title_norm = _normalize_for_match(r['stop_title'])
        # Check significant word overlap
        corpus_words = set(w for w in corpus_title_norm.split() if len(w) >= 4)
        stop_words = set(w for w in stop_norm.split() if len(w) >= 4)
        if corpus_words and stop_words:
            overlap = corpus_words & stop_words
            if len(overlap) >= max(1, min(len(corpus_words), len(stop_words)) * 0.5):
                passages = r['passages_json']
                if isinstance(passages, str):
                    passages = json.loads(passages)
                return passages if passages else None
    
    return None


def get_stop_corpus_venue_name(tour_name: str, conn) -> Optional[str]:
    """Find the venue_name used in stop_corpus for this tour.
    
    Conservative: only matches if a significant, distinctive word from the
    tour name appears in the stop_corpus venue_name. Generic location words
    (Nice, France, etc.) are excluded to prevent cross-venue pollution.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    venue_name = tour_name.split(' - ')[0].strip() if ' - ' in tour_name else tour_name
    
    # Exact-ish match first (full venue name substring)
    cur.execute("SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s", (f'%{venue_name}%',))
    row = cur.fetchone()
    if row:
        return row['venue_name']
    
    # Try significant words — strip punctuation, require length >= 5,
    # exclude generic location/type words
    import re as _re
    _stop_words = {'tour', 'france', 'museum', 'musee', 'musée', 'nice',
                   'walking', 'biking', 'cycling', 'historical', 'boston',
                   'common', 'park', 'street', 'avenue'}
    raw_words = _re.findall(r'[A-Za-zÀ-ÿ]+', venue_name)
    words = [w for w in raw_words if len(w) >= 5 and w.lower() not in _stop_words]
    
    for w in words:
        cur.execute("SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s", (f'%{w}%',))
        rows = cur.fetchall()
        if len(rows) == 1:
            # Unique match — safe
            return rows[0]['venue_name']
        # Multiple matches — too ambiguous, skip
    
    return None



def enrich_venue_corpus_with_stop_passages(venue_corpus: Optional[Dict],
                                            stop_title: str,
                                            passages: List[Dict]) -> Dict:
    """Enrich the venue_corpus dict with per-stop passage text.
    
    KEY DESIGN: This adds the stop_corpus passages as additional story_elements
    and extends the pages text. The classification rules in build_corpus_anchors
    remain UNCHANGED — they just see richer input for stops that have data.
    
    The sibling discrimination still applies: tokens common across siblings
    are excluded even if they come from stop_corpus.
    """
    if venue_corpus is None:
        venue_corpus = {
            'venue_name': '',
            'story_elements_json': [],
            'canonical_titles_json': [],
            'pages_json': [],
        }
    else:
        # Deep copy to avoid mutating shared data
        venue_corpus = dict(venue_corpus)
        venue_corpus['story_elements_json'] = list(venue_corpus.get('story_elements_json') or [])
        venue_corpus['pages_json'] = list(venue_corpus.get('pages_json') or [])
    
    # Extract people and dates from passages using the same NER as v2
    from stop_anchor_detector_v2 import extract_proper_nouns, extract_dates
    
    passage_texts = []
    for p in passages:
        text = p.get('text', '') if isinstance(p, dict) else str(p)
        if text:
            passage_texts.append(text)
    
    combined_passage_text = ' '.join(passage_texts)
    
    # Create story elements from passages — this feeds into build_corpus_anchors
    # which checks if the element's text matches the stop title
    people = extract_proper_nouns(combined_passage_text)
    dates = extract_dates(combined_passage_text)
    
    # Add as a story element tied to this stop
    # The stop_title words will match since this IS the stop's own material
    new_element = {
        'text': combined_passage_text[:2000],  # Reasonable limit
        'people': people[:20],
        'dates': dates[:20],
        'source': 'stop_corpus',
    }
    venue_corpus['story_elements_json'].append(new_element)
    
    # Also add passage text to pages so corpus_text_norm picks it up
    venue_corpus['pages_json'].append({
        'text': combined_passage_text,
        'source': 'stop_corpus',
    })
    
    return venue_corpus


def analyze_tour_with_stop_corpus(tour_id: int, conn) -> Dict:
    """Analyze a tour using stop_corpus data where available.
    
    IDENTICAL to analyze_tour() except:
    - Before calling build_corpus_anchors for a stop, checks if that stop
      has a stop_corpus row
    - If yes, enriches the venue_corpus with per-stop passages
    - The classification logic is completely unchanged
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row or not row['tour_content']:
        return {'tour_id': tour_id, 'error': 'no content'}

    tour_name = row['tour_name']
    tour_content = row['tour_content']

    venue_corpus = get_venue_corpus_for_tour(tour_id, tour_name, conn)
    stops = parse_tour_stops(tour_content)

    # Find the stop_corpus venue name for this tour
    sc_venue_name = get_stop_corpus_venue_name(tour_name, conn)

    # Track which stops got stop_corpus data
    stops_with_corpus = []
    stops_without_corpus = []

    # v2: Build sibling corpus texts — BUT with stop_corpus enrichment
    # We need to build sibling texts with enriched data too, so the
    # discrimination is fair (a token appearing in multiple stops' stop_corpus
    # is still sibling-common)
    all_stop_titles = [s['title'] for s in stops]
    
    # Build enriched venue_corpus per stop for sibling computation
    enriched_per_stop = {}
    for title in all_stop_titles:
        if sc_venue_name:
            passages = get_stop_corpus_passages(sc_venue_name, title, conn)
        else:
            passages = None
        
        if passages:
            enriched_per_stop[title] = enrich_venue_corpus_with_stop_passages(
                venue_corpus, title, passages
            )
            stops_with_corpus.append(title)
        else:
            enriched_per_stop[title] = venue_corpus
            stops_without_corpus.append(title)
    
    # Build sibling corpus texts using enriched data
    # Each stop's sibling text uses its own enriched corpus
    sibling_corpus_texts = {}
    for title in all_stop_titles:
        vc = enriched_per_stop[title]
        if vc:
            anchors = build_corpus_anchors(vc, title, tour_name)
            specific_text = ' '.join(anchors['facts'])
            for p in anchors['people']:
                specific_text += ' ' + p
            for d in anchors['dates']:
                specific_text += ' ' + d
            for t in anchors['titles']:
                specific_text += ' ' + t
            sibling_corpus_texts[title] = _normalize_for_match(specific_text)
        else:
            sibling_corpus_texts[title] = ''

    stop_analyses = []
    totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0,
              'NAVIGATION': 0, 'total_paragraphs': 0}

    for stop in stops:
        vc = enriched_per_stop.get(stop['title'], venue_corpus)
        
        corpus_anchors = build_corpus_anchors(
            vc, stop['title'], tour_name
        ) if vc else {
            'people': set(), 'dates': set(), 'titles': set(),
            'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
        }

        para_results = []
        for para in stop['paragraphs']:
            result = classify_paragraph(
                para, corpus_anchors, stop['title'], tour_name,
                sibling_corpus_texts=sibling_corpus_texts
            )
            result['text_preview'] = para[:150]
            para_results.append(result)
            totals[result['classification']] += 1
            totals['total_paragraphs'] += 1

        stop_analyses.append({
            'title': stop['title'],
            'paragraph_count': len(stop['paragraphs']),
            'paragraphs': para_results,
            'has_stop_corpus': stop['title'] in stops_with_corpus,
        })

    return {
        'tour_id': tour_id,
        'tour_name': tour_name,
        'has_corpus': venue_corpus is not None,
        'corpus_venue': venue_corpus.get('venue_name', '') if venue_corpus else '',
        'stop_count': len(stops),
        'stops': stop_analyses,
        'summary': totals,
        'stops_with_stop_corpus': stops_with_corpus,
        'stops_without_stop_corpus': stops_without_corpus,
    }



# ─── Report: side-by-side comparison ────────────────────────────────────────

def run_comparison_report(tour_ids: List[int]) -> str:
    """Run both modes over identical tours and report side by side."""
    conn = get_connection()
    
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── Coverage: how many stops have stop_corpus rows ──
    cur.execute("SELECT COUNT(*) as cnt FROM stop_corpus")
    total_sc_rows = cur.fetchone()['cnt']
    
    report = []
    report.append("=" * 80)
    report.append("LOCAL-177: STOP ANCHOR DETECTOR v2 — STOP_CORPUS COMPARISON")
    report.append("=" * 80)
    report.append("")
    report.append("DESIGN: Classification rules UNCHANGED. Only the corpus lookup differs.")
    report.append("  Mode A: venue_corpus only (the 4.2% baseline)")
    report.append("  Mode B: stop_corpus first, venue_corpus fallback")
    report.append("")
    report.append(f"stop_corpus table: {total_sc_rows} rows")
    report.append(f"Tours analyzed: {len(tour_ids)}")
    report.append(f"API spend: $0.00 (read-only, no LLM)")
    report.append("")
    
    # ── Sanity check: Michael's examples ──
    report.append("-" * 80)
    report.append("SANITY CHECK: Michael's examples (must be unchanged)")
    report.append("-" * 80)
    
    example1 = ("Cycling on the French Riviera, stop at Cap d'Antibes to experience "
                "the enduring power of nature, inspiring creativity and stimulating "
                "the imagination while admiring panoramic views and soaking up the "
                "atmosphere of this everyday paradise.")
    example2 = ("As you stand on Cap d'Antibes with Mediterranean sea stretching out "
                "before you Imagine the scene that once captivated Scott Fitzgerald "
                "inspiring the setting of his timeless novels.")
    wayfinding = ("As you enter the Palais Lascaris, make your way to the Grand Salon "
                  "on the first floor, where a masterpiece awaits.")

    cur.execute("SELECT * FROM venue_corpus WHERE venue_name ILIKE '%french riviera%'")
    riviera_corpus = cur.fetchone()
    riviera_corpus = dict(riviera_corpus) if riviera_corpus else None
    
    corpus_anchors = build_corpus_anchors(riviera_corpus, "Cap d'Antibes", "French Riviera Biking Tour")
    r1 = classify_paragraph(example1, corpus_anchors, "Cap d'Antibes", "French Riviera Biking Tour")
    r2 = classify_paragraph(example2, corpus_anchors, "Cap d'Antibes", "French Riviera Biking Tour")
    
    cur.execute("SELECT * FROM venue_corpus WHERE venue_name ILIKE '%Palais Lascaris%'")
    lascaris_corpus = cur.fetchone()
    lascaris_corpus = dict(lascaris_corpus) if lascaris_corpus else None
    lascaris_anchors = build_corpus_anchors(lascaris_corpus, "The Triumph of David", 
                                            "Palais Lascaris, Nice, France - museum Tour")
    r3 = classify_paragraph(wayfinding, lascaris_anchors, "The Triumph of David",
                           "Palais Lascaris, Nice, France - museum Tour")
    
    report.append(f"  Example 1 (generic): {r1['classification']:20s} {'PASS' if r1['classification'] == 'NO_ANCHOR' else 'FAIL'}")
    report.append(f"  Example 2 (Fitzgerald): {r2['classification']:16s} {'PASS' if r2['classification'] == 'UNLINKED_ENTITY' else 'FAIL'}")
    report.append(f"  Example 3 (wayfinding): {r3['classification']:16s} {'PASS' if r3['classification'] == 'NAVIGATION' else 'FAIL'}")
    report.append("")
    
    # ── Run Mode A (baseline) and Mode B (stop_corpus) ──
    report.append("=" * 80)
    report.append("SIDE-BY-SIDE RESULTS")
    report.append("=" * 80)
    
    mode_a_results = []
    mode_b_results = []
    
    for tid in tour_ids:
        a = analyze_tour(tid, conn)  # Mode A: venue_corpus only
        b = analyze_tour_with_stop_corpus(tid, conn)  # Mode B: stop_corpus first
        mode_a_results.append(a)
        mode_b_results.append(b)
    
    grand_a = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'NAVIGATION': 0, 'total': 0}
    grand_b = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'NAVIGATION': 0, 'total': 0}
    
    # Categorize tours
    museum_tours = []
    walking_tours = []
    
    for a, b in zip(mode_a_results, mode_b_results):
        if 'error' in a or 'error' in b:
            report.append(f"\n  Tour {a.get('tour_id', '?')}: ERROR")
            continue
        
        tid = a['tour_id']
        tname = a['tour_name']
        
        sa = a['summary']
        sb = b['summary']
        
        content_a = sa['total_paragraphs'] - sa['NAVIGATION']
        content_b = sb['total_paragraphs'] - sb['NAVIGATION']
        
        pct_a = 100 * sa['ANCHORED'] / content_a if content_a > 0 else 0
        pct_b = 100 * sb['ANCHORED'] / content_b if content_b > 0 else 0
        
        # Track which stops have stop_corpus
        sc_count = len(b.get('stops_with_stop_corpus', []))
        total_stops = b['stop_count']
        
        report.append(f"\n{'─' * 80}")
        report.append(f"Tour {tid}: {tname}")
        report.append(f"  Stops: {total_stops}, with stop_corpus: {sc_count}/{total_stops}")
        if b.get('stops_with_stop_corpus'):
            report.append(f"  Attributed stops: {b['stops_with_stop_corpus'][:5]}")
        report.append(f"  Content paragraphs: {content_a} (A) / {content_b} (B)")
        report.append(f"")
        report.append(f"  {'':25s} {'Mode A':>10s}  {'Mode B':>10s}  {'Delta':>8s}")
        report.append(f"  {'ANCHORED':25s} {pct_a:9.1f}%  {pct_b:9.1f}%  {pct_b-pct_a:+7.1f}%")
        
        na_a = 100 * sa['NO_ANCHOR'] / content_a if content_a > 0 else 0
        na_b = 100 * sb['NO_ANCHOR'] / content_b if content_b > 0 else 0
        report.append(f"  {'NO_ANCHOR':25s} {na_a:9.1f}%  {na_b:9.1f}%  {na_b-na_a:+7.1f}%")
        
        ul_a = 100 * sa['UNLINKED_ENTITY'] / content_a if content_a > 0 else 0
        ul_b = 100 * sb['UNLINKED_ENTITY'] / content_b if content_b > 0 else 0
        report.append(f"  {'UNLINKED_ENTITY':25s} {ul_a:9.1f}%  {ul_b:9.1f}%  {ul_b-ul_a:+7.1f}%")
        report.append(f"  {'NAVIGATION':25s} {sa['NAVIGATION']:>9d}   {sb['NAVIGATION']:>9d}")
        
        # Per-stop detail for Mode B where stop_corpus exists
        if sc_count > 0:
            report.append(f"")
            report.append(f"  Per-stop detail (stop_corpus stops only):")
            for sa_stop, sb_stop in zip(a['stops'], b['stops']):
                if sb_stop.get('has_stop_corpus'):
                    ca = [p['classification'] for p in sa_stop['paragraphs']]
                    cb = [p['classification'] for p in sb_stop['paragraphs']]
                    aa = ca.count('ANCHORED')
                    ab = cb.count('ANCHORED')
                    report.append(f"    {sb_stop['title'][:45]:45s} A:{aa}/{len(ca)} → B:{ab}/{len(cb)}")
        
        for k in ('ANCHORED', 'NO_ANCHOR', 'UNLINKED_ENTITY', 'NAVIGATION'):
            grand_a[k] += sa[k]
            grand_b[k] += sb[k]
        grand_a['total'] += sa['total_paragraphs']
        grand_b['total'] += sb['total_paragraphs']
        
        # Categorize
        is_museum = 'museum' in tname.lower() or 'musee' in tname.lower() or 'musée' in tname.lower() or 'chagall' in tname.lower()
        if is_museum:
            museum_tours.append((a, b))
        else:
            walking_tours.append((a, b))
    
    # ── Category breakdown ──
    report.append(f"\n{'=' * 80}")
    report.append("CATEGORY BREAKDOWN")
    report.append("=" * 80)
    
    for label, pairs in [("MUSEUMS (have attributable pages)", museum_tours),
                         ("WALKING/BIKING (no attributable pages)", walking_tours)]:
        report.append(f"\n  {label}:")
        cat_a = {'ANCHORED': 0, 'total': 0}
        cat_b = {'ANCHORED': 0, 'total': 0}
        for a, b in pairs:
            sa, sb = a['summary'], b['summary']
            ca = sa['total_paragraphs'] - sa['NAVIGATION']
            cb = sb['total_paragraphs'] - sb['NAVIGATION']
            cat_a['ANCHORED'] += sa['ANCHORED']
            cat_a['total'] += ca
            cat_b['ANCHORED'] += sb['ANCHORED']
            cat_b['total'] += cb
        
        pct_a = 100 * cat_a['ANCHORED'] / cat_a['total'] if cat_a['total'] > 0 else 0
        pct_b = 100 * cat_b['ANCHORED'] / cat_b['total'] if cat_b['total'] > 0 else 0
        report.append(f"    Mode A (venue-only):      {pct_a:.1f}% ANCHORED ({cat_a['ANCHORED']}/{cat_a['total']})")
        report.append(f"    Mode B (stop_corpus first): {pct_b:.1f}% ANCHORED ({cat_b['ANCHORED']}/{cat_b['total']})")
        report.append(f"    Delta: {pct_b - pct_a:+.1f}%")
    
    # ── Grand totals ──
    report.append(f"\n{'=' * 80}")
    report.append("GRAND TOTALS")
    report.append("=" * 80)
    
    content_a = grand_a['total'] - grand_a['NAVIGATION']
    content_b = grand_b['total'] - grand_b['NAVIGATION']
    
    pct_a = 100 * grand_a['ANCHORED'] / content_a if content_a > 0 else 0
    pct_b = 100 * grand_b['ANCHORED'] / content_b if content_b > 0 else 0
    
    report.append(f"  Total content paragraphs: {content_a} (A) / {content_b} (B)")
    report.append(f"")
    report.append(f"  {'':25s} {'Mode A':>10s}  {'Mode B':>10s}  {'Delta':>8s}")
    report.append(f"  {'ANCHORED':25s} {pct_a:9.1f}%  {pct_b:9.1f}%  {pct_b-pct_a:+7.1f}%")
    report.append(f"  {'NO_ANCHOR':25s} {100*grand_a['NO_ANCHOR']/content_a:9.1f}%  {100*grand_b['NO_ANCHOR']/content_b:9.1f}%")
    report.append(f"  {'UNLINKED_ENTITY':25s} {100*grand_a['UNLINKED_ENTITY']/content_a:9.1f}%  {100*grand_b['UNLINKED_ENTITY']/content_b:9.1f}%")
    
    # ── Coverage ──
    report.append(f"\n{'=' * 80}")
    report.append("COVERAGE")
    report.append("=" * 80)
    
    total_stops_all = 0
    stops_with_sc = 0
    for b in mode_b_results:
        if 'error' not in b:
            total_stops_all += b['stop_count']
            stops_with_sc += len(b.get('stops_with_stop_corpus', []))
    
    report.append(f"  Total stops across 7 tours: {total_stops_all}")
    report.append(f"  Stops with stop_corpus row: {stops_with_sc}")
    report.append(f"  Coverage: {100*stops_with_sc/total_stops_all:.1f}%" if total_stops_all > 0 else "  Coverage: N/A")
    report.append(f"  stop_corpus table total rows: {total_sc_rows}")
    
    # ── Noise floor ──
    report.append(f"\n{'=' * 80}")
    report.append("NOISE FLOOR — 3 runs, must be identical")
    report.append("=" * 80)
    
    run_results_a = []
    run_results_b = []
    for run_num in range(3):
        ra = {'ANCHORED': 0, 'NAV': 0, 'total': 0}
        rb = {'ANCHORED': 0, 'NAV': 0, 'total': 0}
        for tid in tour_ids:
            a = analyze_tour(tid, conn)
            b = analyze_tour_with_stop_corpus(tid, conn)
            if 'error' not in a:
                ra['ANCHORED'] += a['summary']['ANCHORED']
                ra['NAV'] += a['summary']['NAVIGATION']
                ra['total'] += a['summary']['total_paragraphs']
            if 'error' not in b:
                rb['ANCHORED'] += b['summary']['ANCHORED']
                rb['NAV'] += b['summary']['NAVIGATION']
                rb['total'] += b['summary']['total_paragraphs']
        run_results_a.append(ra)
        run_results_b.append(rb)
    
    for i, (ra, rb) in enumerate(zip(run_results_a, run_results_b), 1):
        ca = ra['total'] - ra['NAV']
        cb = rb['total'] - rb['NAV']
        pa = 100 * ra['ANCHORED'] / ca if ca > 0 else 0
        pb = 100 * rb['ANCHORED'] / cb if cb > 0 else 0
        report.append(f"  Run {i}: A={pa:.1f}%  B={pb:.1f}%")
    
    all_a_same = all(r == run_results_a[0] for r in run_results_a)
    all_b_same = all(r == run_results_b[0] for r in run_results_b)
    
    if all_a_same and all_b_same:
        report.append(f"  All runs IDENTICAL. Noise floor: ZERO.")
    else:
        report.append(f"  WARNING: Non-deterministic behavior!")
    
    # ── New anchors found via stop_corpus ──
    report.append(f"\n{'=' * 80}")
    report.append("NEWLY ANCHORED PARAGRAPHS (in Mode B but not Mode A)")
    report.append("=" * 80)
    
    new_anchors = []
    for a, b in zip(mode_a_results, mode_b_results):
        if 'error' in a or 'error' in b:
            continue
        for sa, sb in zip(a['stops'], b['stops']):
            for pa, pb in zip(sa['paragraphs'], sb['paragraphs']):
                if pa['classification'] != 'ANCHORED' and pb['classification'] == 'ANCHORED':
                    new_anchors.append({
                        'tour': a['tour_name'][:40],
                        'stop': sa['title'][:35],
                        'anchor': pb.get('anchor', ('?', '?')),
                        'all_anchors': pb.get('all_anchors', []),
                        'text': pb['text_preview'][:120],
                        'was': pa['classification'],
                    })
    
    if new_anchors:
        report.append(f"  Found {len(new_anchors)} newly anchored paragraphs:")
        for i, na in enumerate(new_anchors[:15], 1):
            report.append(f"")
            report.append(f"  [{i}] Tour: {na['tour']}")
            report.append(f"      Stop: {na['stop']}")
            report.append(f"      Was: {na['was']} → Now: ANCHORED via {na['anchor']}")
            if len(na['all_anchors']) > 1:
                report.append(f"      All anchors: {na['all_anchors'][:4]}")
            report.append(f"      Text: \"{na['text']}...\"")
    else:
        report.append(f"  No newly anchored paragraphs found.")
        report.append(f"  This means the stop_corpus passages did not provide tokens")
        report.append(f"  that distinguish stops from their siblings under the existing rule.")
    
    # ── Final summary ──
    report.append(f"\n{'=' * 80}")
    report.append("SUMMARY")
    report.append("=" * 80)
    report.append(f"  Mode A baseline (venue_corpus only): {pct_a:.1f}% ANCHORED")
    report.append(f"  Mode B (stop_corpus first):          {pct_b:.1f}% ANCHORED")
    report.append(f"  Delta: {pct_b - pct_a:+.1f}%")
    report.append(f"  API spend: $0.00")
    report.append(f"  Classification rules: UNCHANGED")
    report.append(f"  Database writes: NONE (read-only)")
    
    conn.close()
    return '\n'.join(report)


if __name__ == '__main__':
    TOUR_IDS = [1, 29, 12, 24, 14, 46, 44]
    report = run_comparison_report(TOUR_IDS)
    print(report)
