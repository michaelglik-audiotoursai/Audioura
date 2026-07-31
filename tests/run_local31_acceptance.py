#!/usr/bin/env python3
"""
LOCAL-31 ACCEPTANCE TEST: Three consecutive 8-stop runs.

Procedure:
1. Delete tour_cache AND venue_corpus for Q3330160
2. Run 1: fresh (forces venue_corpus re-mining)
3. Run 2: cache hit (venue_corpus exists)
4. Run 3: cache hit (same)

For each stop in each run, prints catalogue value vs delivered value
for period and material.
"""
import os
import sys
import re
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Configuration
VENUE = "Musée des Arts asiatiques, Nice, France"
TOUR_TYPE = "museum"
TOTAL_STOPS = 8
NUM_RUNS = 3
QID = "Q3330160"

# Catalogue ground truth (from the museum's own site)
CATALOGUE_TRUTH = {
    'La danse cosmique de Ganesh': {'period': '2nde moitié du Xe siècle', 'material': 'chlorite'},
    'Kannon, le bodhisattva de la compassion': {'period': 'seconde moitié du XIIe siècle', 'material': 'bois'},
    'Statue de Bouddha': {'period': 'IIe siècle', 'material': 'schiste gris'},
    "L'Armure d'Andô Naoyuki": {'period': 'Époque d\'Edo', 'material': 'fer, laque, soie'},
    'Robe de prêtre taoïste': {'period': 'XIXe siècle', 'material': 'soie, broderie'},
    'Ulysses Grant au Japon': {'period': '1879', 'material': 'xylogravure'},
    'Kannon à mille bras': {'period': 'XIe siècle', 'material': 'bois'},
    'Masque du vieillard kojô': {'period': 'Époque Edo', 'material': 'bois'},
    'Armure du Clan Hotta': {'period': 'Époque d\'Edo', 'material': 'fer, laque'},
}

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')


def clear_caches():
    """Delete tour_cache and venue_corpus for Q3330160."""
    import psycopg2
    from db_connection import get_database_url
    conn = psycopg2.connect(get_database_url())
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tour_cache WHERE location ILIKE %s", ('%arts asiatiques%',))
        tc_deleted = cur.rowcount
        cur.execute("DELETE FROM venue_corpus WHERE qid = %s", (QID,))
        vc_deleted = cur.rowcount
        conn.commit()
    conn.close()
    print(f"  Cleared: {tc_deleted} tour_cache row(s), {vc_deleted} venue_corpus row(s)")


def run_single_generation(run_num):
    """Run one generation and return the text output."""
    from generate_tour_text import generate_tour_text
    
    output_file = f"tours/local31_acceptance_run{run_num}_{int(time.time())}.txt"
    os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
    os.environ['DATABASE_URL'] = DATABASE_URL
    os.environ['STORIED_MODE'] = 'true'
    
    try:
        result = generate_tour_text(
            location=VENUE,
            tour_type=TOUR_TYPE,
            output_file=output_file,
            total_stops=TOTAL_STOPS,
        )
        if result and len(result) >= 2:
            text = result[0] if isinstance(result[0], str) else str(result[0])
            return text, output_file
        elif result and isinstance(result, str):
            return result, output_file
        else:
            # Read from file
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    return f.read(), output_file
            return None, output_file
    except Exception as e:
        print(f"  ERROR in run {run_num}: {e}")
        import traceback
        traceback.print_exc()
        return None, output_file


def extract_stops(text):
    """Parse stops from the generated text."""
    if not text:
        return []
    # Match "Stop N: Title" or "## Stop N: Title"
    stop_pattern = re.compile(r'(?:^|\n)(?:#{1,3}\s*)?Stop\s+(\d+)[:\s]+(.+?)(?:\n|$)', re.IGNORECASE)
    stops = []
    matches = list(stop_pattern.finditer(text))
    for i, match in enumerate(matches):
        stop_num = int(match.group(1))
        title = match.group(2).strip()
        # Get the stop's body text (until next stop or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        stops.append({'num': stop_num, 'title': title, 'body': body})
    return stops


def check_period_in_text(text, expected_period):
    """Check if the expected period appears in the text."""
    text_lower = text.lower()
    period_lower = expected_period.lower()
    
    if period_lower in text_lower:
        return True, expected_period
    
    # Check Arabic equivalents
    century_match = re.search(r'((?:I{1,3}|IV|VI{0,3}|IX|X{0,3}I{0,3}V?)e)\s+si[eè]cle', expected_period)
    if century_match:
        expected_century = century_match.group(1).lower()
        roman_to_arabic = {
            'ie': '1', 'iie': '2', 'iiie': '3', 'ive': '4',
            've': '5', 'vie': '6', 'viie': '7', 'viiie': '8',
            'ixe': '9', 'xe': '10', 'xie': '11', 'xiie': '12',
            'xiiie': '13', 'xive': '14', 'xve': '15', 'xvie': '16',
        }
        arabic = roman_to_arabic.get(expected_century, '')
        if arabic:
            variants = [f"{arabic}th century", f"{arabic}th-century", f"{arabic}th cent"]
            if arabic == '1': variants.extend(['1st century', '1st-century'])
            elif arabic == '2': variants.extend(['2nd century', '2nd-century'])
            elif arabic == '3': variants.extend(['3rd century', '3rd-century'])
            for v in variants:
                if v in text_lower:
                    return True, v
    
    # Check year
    if re.match(r'^\d{4}$', expected_period):
        if expected_period in text:
            return True, expected_period
    
    # Check Edo
    if 'edo' in period_lower and 'edo' in text_lower:
        return True, 'Edo'
    
    return False, None


def check_material_in_text(text, expected_material):
    """Check if the expected material appears in the text."""
    text_lower = text.lower()
    # Split on comma to handle multi-material entries
    materials = [m.strip() for m in expected_material.split(',')]
    found = []
    missing = []
    for mat in materials:
        if mat.lower() in text_lower:
            found.append(mat)
        else:
            # Check English equivalents
            fr_to_en = {'bois': 'wood', 'fer': 'iron', 'soie': 'silk', 'laque': 'lacquer',
                       'broderie': 'embroidery', 'schiste gris': 'grey schist'}
            en = fr_to_en.get(mat.lower(), '')
            if en and en in text_lower:
                found.append(f"{mat} (as '{en}')")
            else:
                missing.append(mat)
    return found, missing


def check_fabrications(text):
    """Check for fabricated attributions."""
    patterns = [
        (r'Type/Specialty:\s*\S+', 'invented Type/Specialty'),
        (r'Specific Examples:\s*\S+', 'invented Specific Examples'),
        (r'Tang Dynasty', 'fabricated Tang Dynasty attribution'),
    ]
    found = []
    for pattern, label in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(label)
    return found


def main():
    print("=" * 70)
    print("LOCAL-31 ACCEPTANCE TEST: 3-run metadata binding verification")
    print("=" * 70)
    
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    
    # Step 1: Clear caches
    print("\n[Step 1] Clearing tour_cache AND venue_corpus for Q3330160...")
    clear_caches()
    
    results = []
    for run_num in range(1, NUM_RUNS + 1):
        print(f"\n{'='*70}")
        print(f"[Run {run_num}/{NUM_RUNS}]{'  (FRESH — venue_corpus deleted)' if run_num == 1 else '  (CACHE HIT)'}")
        print(f"{'='*70}")
        
        text, output_file = run_single_generation(run_num)
        
        if not text:
            print(f"  FAILED — no output generated")
            results.append(None)
            continue
        
        stops = extract_stops(text)
        print(f"  Generated {len(stops)} stops")
        
        # Check Museum Information
        has_museum_info = bool(re.search(r'Museum Information.*(?:Closed|Tuesday|Free|admission)', text, re.IGNORECASE | re.DOTALL))
        print(f"  Museum Information present: {has_museum_info}")
        
        # Check fabrications
        fabrications = check_fabrications(text)
        if fabrications:
            print(f"  ⚠️  FABRICATIONS FOUND: {fabrications}")
        else:
            print(f"  ✓ Zero fabrications")
        
        # Per-stop metadata comparison
        print(f"\n  {'Stop':<5} {'Title':<45} {'Period':<20} {'Material':<15}")
        print(f"  {'-'*5} {'-'*45} {'-'*20} {'-'*15}")
        
        run_result = {
            'stops': stops,
            'has_museum_info': has_museum_info,
            'fabrications': fabrications,
            'period_checks': [],
            'material_checks': [],
        }
        
        for stop in stops:
            title = stop['title'][:44]
            body = stop['body']
            
            # Find matching catalogue entry
            cat_entry = None
            for cat_title, cat_data in CATALOGUE_TRUTH.items():
                if cat_title.lower() in stop['title'].lower() or stop['title'].lower() in cat_title.lower():
                    cat_entry = (cat_title, cat_data)
                    break
                # Fuzzy: first 10 chars
                from story_miner import _normalize
                if _normalize(cat_title)[:10] in _normalize(stop['title']) or _normalize(stop['title'])[:10] in _normalize(cat_title):
                    cat_entry = (cat_title, cat_data)
                    break
            
            period_status = "—"
            material_status = "—"
            
            if cat_entry:
                cat_title, cat_data = cat_entry
                # Check period
                period_ok, found_as = check_period_in_text(body, cat_data['period'])
                if period_ok:
                    period_status = f"✓ {found_as}"
                else:
                    period_status = f"✗ expected: {cat_data['period']}"
                run_result['period_checks'].append((stop['title'], period_ok, cat_data['period']))
                
                # Check material
                found_mats, missing_mats = check_material_in_text(body, cat_data['material'])
                if not missing_mats:
                    material_status = f"✓ {','.join(found_mats)}"
                elif found_mats:
                    material_status = f"~ found:{','.join(found_mats)} miss:{','.join(missing_mats)}"
                else:
                    material_status = f"✗ expected: {cat_data['material']}"
                run_result['material_checks'].append((stop['title'], len(missing_mats) == 0, cat_data['material']))
            
            print(f"  {stop['num']:<5} {title:<45} {period_status:<20} {material_status:<15}")
        
        # Check for provenance over-assertions
        bengali_assertions = re.findall(r'(?:ancient\s+)?[Bb]engali\s+(?:culture|civilization|heritage|tradition|artwork|art)', text)
        if bengali_assertions:
            print(f"\n  ⚠️  PROVENANCE OVER-ASSERTION: {bengali_assertions}")
        else:
            print(f"\n  ✓ No provenance over-assertions")
        
        results.append(run_result)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    for run_num, result in enumerate(results, 1):
        if result is None:
            print(f"  Run {run_num}: FAILED (no output)")
            continue
        
        n_stops = len(result['stops'])
        n_period_ok = sum(1 for _, ok, _ in result['period_checks'] if ok)
        n_material_ok = sum(1 for _, ok, _ in result['material_checks'] if ok)
        n_period_total = len(result['period_checks'])
        n_material_total = len(result['material_checks'])
        
        print(f"  Run {run_num}: {n_stops} stops | "
              f"Period: {n_period_ok}/{n_period_total} | "
              f"Material: {n_material_ok}/{n_material_total} | "
              f"Museum Info: {'✓' if result['has_museum_info'] else '✗'} | "
              f"Fabrications: {len(result['fabrications'])}")


if __name__ == '__main__':
    main()
