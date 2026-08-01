"""
LOCAL-72 Evidence Runner — Measure distinct facts before and after LOCAL-48 changes.

Generates:
1. French Riviera biking tour (15 stops)
2. Musée des Arts Asiatiques, Nice (8 stops)

Reports per-stop: words, distinct facts, words-per-fact.
Also checks: Matisse stop 4 fabrication, Asian museum visitor info, cost.

Usage:
    OPENAI_API_KEY=sk-... python3 run_local72_evidence.py [--label BASELINE|LOCAL48]
"""
import sys
import os
import re
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STORIED_MODE"] = "true"

from generate_tour_text import generate_tour_text


def count_words(text: str) -> int:
    return len(text.split())


def extract_stops(tour_text: str) -> list:
    """Extract individual stop texts from a generated tour."""
    stops = []
    parts = re.split(r'\nStop\s+(\d+):\s*', tour_text)
    for i in range(1, len(parts) - 1, 2):
        stop_num = int(parts[i])
        stop_text = parts[i + 1].strip()
        first_line = stop_text.split('\n')[0]
        stops.append({
            'number': stop_num,
            'name': first_line.strip()[:80],
            'text': stop_text,
            'words': count_words(stop_text),
        })
    return stops


def count_distinct_facts(text: str) -> int:
    """Count distinct checkable facts in a stop's text.
    
    A fact = a sentence containing at least one of:
    - A year or century reference
    - A named person (capitalized multi-word)
    - A specific measurement
    - A specific event with a date
    - A named building/artwork with attribution
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    _year = re.compile(r'\b\d{3,4}\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b', re.IGNORECASE)
    _person = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[IVXLCDM]+)\b')
    _number = re.compile(r'\b\d+(?:\.\d+)?\s*(?:m|km|ft|metres?|meters?|miles?|hectares?|acres?|kg|tons?|tonnes?|years?|centuries?)\b', re.IGNORECASE)
    _event = re.compile(r'\b(?:built|founded|opened|established|designed|created|completed|commissioned|inaugurated|renovated|destroyed|constructed)\s+(?:in|by|during|around)\b', re.IGNORECASE)
    _artwork = re.compile(r'\"[^\"]+\"|"[^"]+"|«[^»]+»', re.IGNORECASE)
    
    facts = set()
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        # A sentence is a "fact" if it has checkable specifics
        has_year = bool(_year.search(sent))
        has_person = bool(_person.search(sent))
        has_number = bool(_number.search(sent))
        has_event = bool(_event.search(sent))
        has_artwork = bool(_artwork.search(sent))
        
        if has_year or has_person or has_number or has_event or has_artwork:
            # Normalize to avoid double-counting paraphrases
            facts.add(sent[:100])
    
    return len(facts)


def print_stop_table(stops, title):
    """Print a per-stop table and return totals."""
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"{'─'*70}")
    print(f"  {'Stop':<4} {'Name':<35} {'Words':>6} {'Facts':>6} {'W/F':>6}")
    print(f"  {'─'*4} {'─'*35} {'─'*6} {'─'*6} {'─'*6}")
    
    total_words = 0
    total_facts = 0
    violations = []
    
    for stop in stops:
        words = stop['words']
        facts = count_distinct_facts(stop['text'])
        wpf = f"{words/facts:.1f}" if facts > 0 else "∞"
        total_words += words
        total_facts += facts
        
        flag = ""
        if words > 250 and facts < 2:
            flag = " ⚠️ VIOLATION"
            violations.append(stop)
        
        print(f"  {stop['number']:<4} {stop['name'][:35]:<35} {words:>6} {facts:>6} {wpf:>6}{flag}")
    
    print(f"  {'─'*4} {'─'*35} {'─'*6} {'─'*6} {'─'*6}")
    wpf_total = f"{total_words/total_facts:.1f}" if total_facts > 0 else "∞"
    print(f"  {'TOTAL':<4} {'':<35} {total_words:>6} {total_facts:>6} {wpf_total:>6}")
    print()
    
    return total_words, total_facts, violations


def check_asian_visitor_info(tour_text: str) -> dict:
    """Check Asian museum specific requirements."""
    has_closed_tuesday = bool(re.search(r'closed\s+on\s+tuesday', tour_text, re.IGNORECASE))
    has_free_admission = bool(re.search(r'free\s+admission', tour_text, re.IGNORECASE))
    return {
        'closed_on_tuesday': has_closed_tuesday,
        'free_admission': has_free_admission,
    }


def check_matisse_stop4(tour_text: str) -> dict:
    """Check Musée Matisse stop 4 — should NOT describe exhibition as painting."""
    stops = extract_stops(tour_text)
    if len(stops) < 4:
        return {'stop4_exists': False}
    
    stop4 = stops[3]  # 0-indexed
    text = stop4['text'].lower()
    
    # Exhibition described as painting indicators
    painting_words = ['brushwork', 'brushstroke', 'canvas', 'palette', 'painted surface',
                      'colour palette', 'color palette', 'pigment', 'oil on canvas']
    exhibition_words = ['exhibition', 'exposition', 'hommage', 'programme', 'les années',
                        'marchand', 'galerie']
    
    has_painting_desc = any(w in text for w in painting_words)
    has_exhibition_context = any(w in text for w in exhibition_words)
    
    return {
        'stop4_name': stop4['name'],
        'describes_as_painting': has_painting_desc and not has_exhibition_context,
        'has_exhibition_context': has_exhibition_context,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='RUN', help='Label for this run (BASELINE or LOCAL48)')
    parser.add_argument('--output-dir', default='tours', help='Output directory for tour files')
    args = parser.parse_args()
    
    label = args.label
    os.makedirs(args.output_dir, exist_ok=True)
    
    results = {}
    
    # ──────────────────────────────────────────────────────────────────
    # Tour 1: French Riviera biking (15 stops)
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  [{label}] GENERATING: French Riviera biking tour, France (15 stops)")
    print(f"{'='*70}")
    
    t0 = time.time()
    riviera_output = os.path.join(args.output_dir, f"local72_{label.lower()}_riviera.txt")
    
    riviera_result = generate_tour_text(
        "French Riviera biking tour, France",
        "explore",
        output_file=riviera_output,
        total_stops=15,
    )
    
    riviera_time = time.time() - t0
    
    if isinstance(riviera_result, tuple):
        riviera_text = riviera_result[0] if riviera_result[0] else ""
    else:
        riviera_text = riviera_result or ""
    # Read cost from module-level tracker
    from generate_tour_text import _LAST_GENERATION_COST
    riviera_cost = _LAST_GENERATION_COST.get('total_cost', None) if _LAST_GENERATION_COST else None
    
    # Also try reading from file if text is empty
    if not riviera_text and os.path.exists(riviera_output):
        with open(riviera_output, 'r') as f:
            riviera_text = f.read()
    
    riviera_stops = extract_stops(riviera_text)
    riv_words, riv_facts, riv_violations = print_stop_table(riviera_stops, f"[{label}] French Riviera Biking Tour (15 stops)")
    
    results['riviera'] = {
        'stops': len(riviera_stops),
        'total_words': riv_words,
        'total_facts': riv_facts,
        'violations_250w_lt2f': len(riv_violations),
        'time_seconds': riviera_time,
        'cost': riviera_cost,
    }
    
    print(f"  Stops generated: {len(riviera_stops)}/15")
    print(f"  Total distinct facts: {riv_facts}")
    print(f"  250w+ with <2 facts: {len(riv_violations)}")
    print(f"  Time: {riviera_time:.1f}s")
    if riviera_cost is not None:
        print(f"  Cost: ${riviera_cost:.4f}")
    
    # ──────────────────────────────────────────────────────────────────
    # Tour 2: Asian Arts Museum (8 stops)
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  [{label}] GENERATING: Musée des Arts Asiatiques, Nice (8 stops)")
    print(f"{'='*70}")
    
    t0 = time.time()
    asian_output = os.path.join(args.output_dir, f"local72_{label.lower()}_asian.txt")
    
    asian_result = generate_tour_text(
        "Musée des Arts Asiatiques, Nice, France",
        "explore",
        output_file=asian_output,
        total_stops=8,
    )
    
    asian_time = time.time() - t0
    
    if isinstance(asian_result, tuple):
        asian_text = asian_result[0] if asian_result[0] else ""
    else:
        asian_text = asian_result or ""
    # Read cost from module-level tracker
    from generate_tour_text import _LAST_GENERATION_COST
    asian_cost = _LAST_GENERATION_COST.get('total_cost', None) if _LAST_GENERATION_COST else None
    
    if not asian_text and os.path.exists(asian_output):
        with open(asian_output, 'r') as f:
            asian_text = f.read()
    
    asian_stops = extract_stops(asian_text)
    asia_words, asia_facts, asia_violations = print_stop_table(asian_stops, f"[{label}] Asian Arts Museum (8 stops)")
    
    visitor_info = check_asian_visitor_info(asian_text)
    
    results['asian'] = {
        'stops': len(asian_stops),
        'total_words': asia_words,
        'total_facts': asia_facts,
        'violations_250w_lt2f': len(asia_violations),
        'time_seconds': asian_time,
        'cost': asian_cost,
        'closed_tuesday': visitor_info['closed_on_tuesday'],
        'free_admission': visitor_info['free_admission'],
    }
    
    print(f"  Stops generated: {len(asian_stops)}/8")
    print(f"  Total distinct facts: {asia_facts}")
    print(f"  'Closed on Tuesday': {'✓' if visitor_info['closed_on_tuesday'] else '✗'}")
    print(f"  'Free admission': {'✓' if visitor_info['free_admission'] else '✗'}")
    print(f"  Time: {asian_time:.1f}s")
    if asian_cost is not None:
        print(f"  Cost: ${asian_cost:.4f}")
    
    # ──────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────
    total_cost = 0
    if riviera_cost: total_cost += riviera_cost
    if asian_cost: total_cost += asian_cost
    
    print(f"\n{'='*70}")
    print(f"  [{label}] SUMMARY")
    print(f"{'='*70}")
    print(f"  Riviera: {riv_facts} distinct facts across {len(riviera_stops)} stops ({riv_words} words)")
    print(f"  Asian:   {asia_facts} distinct facts across {len(asian_stops)} stops ({asia_words} words)")
    if total_cost:
        print(f"  Total cost: ${total_cost:.4f} (ceiling: $1.30 per tour)")
    print()
    
    # Save JSON results
    json_path = os.path.join(args.output_dir, f"local72_{label.lower()}_results.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to: {json_path}")
    
    # Save full tour texts for reading
    if riviera_text:
        txt_path = os.path.join(args.output_dir, f"local72_{label.lower()}_riviera_full.txt")
        with open(txt_path, 'w') as f:
            f.write(riviera_text)
    if asian_text:
        txt_path = os.path.join(args.output_dir, f"local72_{label.lower()}_asian_full.txt")
        with open(txt_path, 'w') as f:
            f.write(asian_text)


if __name__ == '__main__':
    main()
