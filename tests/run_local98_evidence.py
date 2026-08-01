#!/usr/bin/env python3
"""
LOCAL-98 acceptance evidence runner.

Generates N=8 Asian Arts Museum tours via the HTTP pipeline and measures
whether catalogue date+material survive into the prose for each stop.

The orchestrator updates the existing tour row (same tour_name+request_string),
so row count stays stable at 60.
"""
import os
import sys
import json
import time
import re
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:5002")

# Expected catalogue metadata per stop.
# stop 1: no structured catalogue date/material expected
# stop 7: genuinely no catalogue data (exempt)
EXPECTED = {
    1: {"name": "L'Armure d'Andô Naoyuki", "material": None, "period": None},
    2: {"name": "Statue de Bouddha", "material": "schiste", "period": None},
    3: {"name": "La danse cosmique de Ganesh", "material": "chlorite", "period": "Xe siècle"},
    4: {"name": "Kannon, le bodhisattva de la compassion", "material": None, "period": "XIIe siècle"},
    5: {"name": "Ulysses Grant au Japon", "material": None, "period": "1879"},
    6: {"name": "Robe de prêtre taoïste", "material": "soie", "period": "XVIIIe siècle"},
    7: {"name": "Kannon à mille bras", "material": None, "period": None},
    8: {"name": "Masque du vieillard kojô", "material": "bois", "period": "XVIe siècle"},
}


def generate_and_wait():
    """Generate a tour and wait for completion. Returns tour_content text."""
    resp = requests.post(f"{ORCHESTRATOR_URL}/generate-complete-tour", json={
        'location': 'Asian arts museum, nice, France',
        'tour_type': 'museum',
        'total_stops': 8,
        'user_id': 'test-mac-mini',
        'is_test': True,  # LOCAL-103: mark HTTP-generated test tours
    }, timeout=30)
    resp.raise_for_status()
    job_id = resp.json().get('job_id')
    print(f"  Job: {job_id}")

    for i in range(120):
        time.sleep(5)
        sr = requests.get(f"{ORCHESTRATOR_URL}/status/{job_id}", timeout=10)
        if sr.status_code != 200:
            continue
        sd = sr.json()
        if sd.get('status') == 'completed':
            tour_id = sd.get('final_tour_id')
            print(f"  Completed: tour_id={tour_id} ({(i+1)*5}s)")
            # Read tour_content from DB
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT tour_content FROM audio_tours WHERE id = %s", (tour_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return row[0] if row and row[0] else ""
        elif sd.get('status') in ('error', 'failed'):
            print(f"  FAILED: {sd.get('error')}")
            return None
    print("  TIMEOUT")
    return None


def check_period_present(desc_lower, period):
    """Check if period (date) is present in description. Returns True/False."""
    if not period:
        return True  # no requirement
    
    period_lower = period.lower()
    if period_lower in desc_lower:
        return True
    
    # Raw year
    if re.match(r'^\d{4}$', period.strip()):
        return period.strip() in desc_lower
    
    # Century format
    century_match = re.search(r'((?:X{0,3}(?:IX|IV|V?I{0,3})))e\s+si[eè]cle', period)
    if century_match:
        rom = century_match.group(1).upper()
        rom_map = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,
                   'IX':9,'X':10,'XI':11,'XII':12,'XIII':13,'XIV':14,'XV':15,
                   'XVI':16,'XVII':17,'XVIII':18,'XIX':19,'XX':20}
        arab = rom_map.get(rom, 0)
        if arab:
            sfx = 'th'
            if arab == 1: sfx = 'st'
            elif arab == 2: sfx = 'nd'
            elif arab == 3: sfx = 'rd'
            variants = [
                f"{arab}{sfx} century", f"{arab}{sfx}-century",
                f"half of the {arab}{sfx} century",
                f"early {arab}{sfx} century", f"late {arab}{sfx} century",
                period_lower,
            ]
            return any(v in desc_lower for v in variants)
    return False


def check_material_present(desc_lower, material):
    """Check if material is present in description."""
    if not material:
        return True
    # Check primary material (first in comma-separated list)
    primary = material.split(',')[0].strip().lower()
    return primary in desc_lower


def count_distinct_facts(tour_content):
    """
    Count distinct verifiable facts across all stops.
    A 'fact' is a specific claim that can be verified against an external source:
    dates, materials, dimensions, named people/events, techniques, origins.
    """
    facts = set()
    stops = re.split(r'(?=Stop \d+:)', tour_content)
    
    for stop_text in stops[1:]:
        text = stop_text.lower()
        # Dates/years
        for m in re.finditer(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text):
            facts.add(f"year:{m.group(1)}")
        for m in re.finditer(r'(\d{1,2})(?:st|nd|rd|th)[- ]century', text):
            facts.add(f"century:{m.group(1)}")
        # Materials
        materials = ['chlorite', 'schiste', 'schist', 'soie', 'silk', 'bois', 'wood',
                     'cypress', 'bronze', 'lacquer', 'laque', 'cuivre', 'acier',
                     'polychrome', 'papier', 'or ', 'gold', 'cuir', 'leather',
                     'porcelain', 'jade', 'ivory', 'bamboo', 'ceramic']
        for mat in materials:
            if mat in text:
                facts.add(f"material:{mat}")
        # Named people
        people = ['chikanobu', 'kenzo tange', 'trémois', 'tremois',
                  'andô naoyuki', 'ando naoyuki', 'ganesh', 'kannon', 'bouddha']
        for person in people:
            if person in text:
                facts.add(f"person:{person}")
        # Techniques
        techniques = ['xylogravure', 'woodblock', 'lost-wax', 'embroidery',
                      'lacquered', 'carved', 'cast', 'woven', 'painted']
        for tech in techniques:
            if tech in text:
                facts.add(f"technique:{tech}")
    
    return len(facts)


def run_single(run_num):
    """Run one tour generation and assess all 8 stops."""
    print(f"\n{'─'*60}\nRUN {run_num}\n{'─'*60}")
    
    content = generate_and_wait()
    if not content:
        return None
    
    stops = re.split(r'(?=Stop \d+:)', content)
    results = {}
    passes = 0
    
    for stop_num in range(1, 9):
        exp = EXPECTED[stop_num]
        # Get this stop's text
        stop_text = stops[stop_num] if stop_num < len(stops) else ""
        stop_lower = stop_text.lower()
        
        # Check requirements
        mat_req = exp['material']
        per_req = exp['period']
        
        if not mat_req and not per_req:
            results[stop_num] = {"exempt": True, "name": exp['name']}
            continue
        
        mat_ok = check_material_present(stop_lower, mat_req)
        per_ok = check_period_present(stop_lower, per_req)
        
        both = True
        if mat_req and not mat_ok:
            both = False
        if per_req and not per_ok:
            both = False
        
        if both:
            passes += 1
        
        results[stop_num] = {
            "name": exp['name'],
            "material": f"{'✓' if mat_ok else '✗'} ({mat_req})" if mat_req else "—",
            "period": f"{'✓' if per_ok else '✗'} ({per_req})" if per_req else "—",
            "passes": both,
        }
        
        status = "✓" if both else "✗"
        parts = []
        if mat_req: parts.append(f"mat={'✓' if mat_ok else '✗'}")
        if per_req: parts.append(f"date={'✓' if per_ok else '✗'}")
        print(f"  Stop {stop_num} ({exp['name'][:35]}): {status} [{', '.join(parts)}]")
        
        if not both:
            # Show relevant excerpt for debugging
            desc_start = stop_text.find('Description:')
            if desc_start < 0:
                desc_start = min(200, len(stop_text))
            excerpt = stop_text[desc_start:desc_start+200].replace('\n', ' | ')
            print(f"         → {excerpt[:150]}...")
    
    distinct = count_distinct_facts(content)
    print(f"\n  Result: {passes}/6 stops carry catalogue facts (target ≥6)")
    print(f"  Distinct facts: {distinct}")
    
    return {"passes": passes, "distinct_facts": distinct, "stops": results, "content": content}


def main():
    # Pre-check
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    rows_before = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"Row count before: {rows_before}")
    
    all_results = []
    for run_num in range(1, 4):
        result = run_single(run_num)
        if result:
            all_results.append(result)
            # Don't store the full content in JSON (too large)
            result_copy = {k: v for k, v in result.items() if k != 'content'}
            all_results[-1] = result_copy
    
    # Post-check
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    rows_after = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    # Summary table
    print(f"\n{'═'*60}")
    print("SUMMARY")
    print(f"{'═'*60}")
    print(f"\nRow count: before={rows_before}, after={rows_after}")
    print(f"\n| Run | Passes (of 6) | Distinct facts |")
    print(f"|-----|---------------|----------------|")
    for i, r in enumerate(all_results, 1):
        print(f"| {i}   | {r['passes']}/6          | {r['distinct_facts']}             |")
    
    # Verify tours-near
    print(f"\nVerifying tours-near/43.7009358/7.2683912?radius=50...")
    try:
        resp = requests.get("http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50", timeout=10)
        ids = sorted(resp.json()) if resp.status_code == 200 else []
        expected_ids = [1, 12, 14, 17, 21, 24, 27, 28, 29]
        if ids == expected_ids:
            print(f"  ✓ Returns {ids}")
        else:
            print(f"  ✗ Got {ids}, expected {expected_ids}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Save evidence
    output = os.path.join(os.path.dirname(__file__), '..', 'local98_evidence.json')
    with open(output, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nEvidence saved to: {output}")


if __name__ == "__main__":
    main()
