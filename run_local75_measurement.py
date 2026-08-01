#!/usr/bin/env python3
"""
LOCAL-75: Palais Lascaris measurement script.
Calls generate_tour_text directly in-process for full control.
Sets TOUR_TEST_MODE to prevent pollution.
"""
import os
import sys
import re
import json
import time

# Mark as test mode BEFORE any imports
os.environ['TOUR_TEST_MODE'] = 'true'
os.environ['STORIED_MODE'] = 'true'

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_tour_text import generate_tour_text

# Tour configs
PALAIS_LASCARIS = {
    "location": "Palais Lascaris, Nice",
    "tour_type": "art and musical instruments",
    "total_stops": 8,
}

ASIAN_ARTS = {
    "location": "Musée des Arts Asiatiques, Nice",
    "tour_type": "art and culture",
    "total_stops": 8,
}


def parse_stops(tour_text):
    """Parse tour text into stops."""
    stop_pattern = re.compile(r'^Stop\s+(\d+):\s*(.+?)$', re.MULTILINE)
    matches = list(stop_pattern.finditer(tour_text))
    
    stops = []
    for i, m in enumerate(matches):
        stop_num = int(m.group(1))
        stop_name = m.group(2).strip()
        start_pos = m.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(tour_text)
        stop_text = tour_text[start_pos:end_pos].strip()
        
        words = len(stop_text.split())
        facts = extract_distinct_facts(stop_text)
        
        stops.append({
            "num": stop_num,
            "name": stop_name,
            "words": words,
            "facts": len(facts),
            "wpf": round(words / max(len(facts), 1), 1),
            "fact_list": list(facts),
        })
    
    return stops


def extract_distinct_facts(text):
    """Extract distinct checkable facts from stop text."""
    facts = set()
    
    # Dates (4-digit years)
    for m in re.finditer(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text):
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 40)
        ctx = text[start:end].strip()
        facts.add(f"date:{m.group(0)}")
    
    # Named people (First Last pattern)
    for m in re.finditer(r'\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|di|van|von|le|la|du|del|da|den|der))?'
                         r'\s+[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)\b', text):
        name = m.group(1)
        if name not in ('Stop Number', 'Museum Information', 'The Museum', 'The Palais',
                       'The Palace', 'The Collection', 'The City', 'Nice France'):
            facts.add(f"person:{name}")
    
    # Materials/techniques
    materials = re.findall(
        r'\b(ivory|ebony|rosewood|marquetry|gilded|bronze|marble|fresco|'
        r'stucco|terracotta|lacquer|tortoiseshell|mother.of.pearl|'
        r'walnut|cedar|spruce|gut.strings?|inla(?:y|id)|porcelain|'
        r'cuir doré|panneau|bois|toile|silk|velvet|tapestry)\b',
        text, re.IGNORECASE
    )
    for mat in set(materials):
        facts.add(f"material:{mat.lower()}")
    
    # Measurements
    for m in re.finditer(r'\b\d+\s*(?:cm|mm|m|meters?|feet|inches?)\b', text, re.IGNORECASE):
        facts.add(f"measure:{m.group(0)}")
    
    # Instruments (for Palais Lascaris)
    instruments = re.findall(
        r'\b(guitar[es]*|violin[es]*|viola[es]*|harp[es]*|flute[s]*|'
        r'recorder[s]*|cello[s]*|harpsichord[s]*|clavecin[s]*|'
        r'lute[s]*|mandolin[es]*|oboe[s]*|clarinet[s]*|piano[s]*|'
        r'organ[s]*|virginal[s]*|spinet[s]*|theorbo[s]*)\b',
        text, re.IGNORECASE
    )
    for inst in set(instruments):
        facts.add(f"instrument:{inst.lower()}")
    
    # Attributions (Maker/City/Year patterns)
    for m in re.finditer(r'\(([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+)?),?\s*\d{4}\)', text):
        facts.add(f"attribution:{m.group(0)}")
    
    # Architectural/decorative specifics
    arch = re.findall(
        r'\b(trompe.l.oeil|bas.relief|ceiling|fresco|staircase|'
        r'balustrade|loggia|salon|chapel|pharmacy|facade|'
        r'Genoese|Baroque|Renaissance|Rococo)\b',
        text, re.IGNORECASE
    )
    for a in set(arch):
        facts.add(f"arch:{a.lower()}")
    
    return facts


def run_single(config, label):
    """Run one generation and return measurement."""
    print(f"\n{'='*60}")
    print(f"  {label}: {config['location']}")
    print(f"{'='*60}")
    
    start = time.time()
    tour_text, output_file, coords = generate_tour_text(
        location=config["location"],
        tour_type=config["tour_type"],
        total_stops=config["total_stops"],
        persona=None,
    )
    elapsed = time.time() - start
    
    if not tour_text:
        print(f"  FAILED: No tour text returned")
        return None
    
    stops = parse_stops(tour_text)
    total_words = sum(s['words'] for s in stops)
    total_facts = sum(s['facts'] for s in stops)
    
    # Read cost from module-level variable
    from generate_tour_text import _LAST_GENERATION_COST
    cost = _LAST_GENERATION_COST.get('total_cost', 0.0) if isinstance(_LAST_GENERATION_COST, dict) else 0.0
    
    result = {
        "label": label,
        "location": config["location"],
        "stop_count": len(stops),
        "total_words": total_words,
        "total_facts": total_facts,
        "cost": cost,
        "elapsed_s": round(elapsed, 1),
        "per_stop": stops,
        "full_text": tour_text,
    }
    
    # Print per-stop table
    print(f"\n  {'Stop':<4} {'Name':<45} {'Words':<6} {'Facts':<6} {'W/F':<6}")
    print(f"  {'-'*4} {'-'*45} {'-'*6} {'-'*6} {'-'*6}")
    for s in stops:
        print(f"  {s['num']:<4} {s['name'][:45]:<45} {s['words']:<6} {s['facts']:<6} {s['wpf']:<6}")
    print(f"  {'TOT':<4} {'':<45} {total_words:<6} {total_facts:<6} {round(total_words/max(total_facts,1),1):<6}")
    print(f"  Elapsed: {elapsed:.1f}s | Cost: ${cost:.4f}")
    
    return result


def main():
    arm = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    n_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    print(f"LOCAL-75 Measurement: arm={arm}, runs={n_runs}")
    print(f"{'='*60}")
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("FATAL: OPENAI_API_KEY not set.")
        sys.exit(1)
    
    # Run Palais Lascaris n times
    palais_results = []
    for i in range(n_runs):
        result = run_single(PALAIS_LASCARIS, f"Palais_{arm}_run{i+1}")
        if result:
            palais_results.append(result)
    
    # Run Asian Arts once
    asian_result = run_single(ASIAN_ARTS, f"Asian_{arm}")
    
    # Summary
    print(f"\n\n{'='*60}")
    print(f"  SUMMARY: {arm} ({len(palais_results)} Palais runs)")
    print(f"{'='*60}")
    
    if palais_results:
        facts_list = [r['total_facts'] for r in palais_results]
        words_list = [r['total_words'] for r in palais_results]
        costs_list = [r['cost'] for r in palais_results]
        stops_list = [r['stop_count'] for r in palais_results]
        
        mean_facts = sum(facts_list) / len(facts_list)
        mean_words = sum(words_list) / len(words_list)
        mean_cost = sum(costs_list) / len(costs_list)
        
        print(f"  Palais Lascaris:")
        print(f"    Stops:  {stops_list}")
        print(f"    Facts:  mean={mean_facts:.1f}, values={facts_list}, spread={max(facts_list)-min(facts_list)}")
        print(f"    Words:  mean={mean_words:.0f}, values={words_list}, spread={max(words_list)-min(words_list)}")
        print(f"    Cost:   mean=${mean_cost:.4f}, values=[${c:.4f} for c in costs_list]")
    
    if asian_result:
        has_closed_tuesday = bool(re.search(r'[Cc]losed\s+on\s+Tuesday', asian_result['full_text']))
        print(f"\n  Asian Arts Museum:")
        print(f"    Stops: {asian_result['stop_count']}/8")
        print(f"    'Closed on Tuesday': {has_closed_tuesday}")
        print(f"    Facts: {asian_result['total_facts']}")
    
    # Save results
    output = {
        "arm": arm,
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "palais": [{k: v for k, v in r.items() if k != 'full_text'} for r in palais_results],
        "palais_texts": [r['full_text'] for r in palais_results],
        "asian": {k: v for k, v in asian_result.items() if k != 'full_text'} if asian_result else None,
        "asian_text": asian_result['full_text'] if asian_result else None,
    }
    
    outfile = f"LOCAL75_{arm}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved to: {outfile}")


if __name__ == "__main__":
    main()
