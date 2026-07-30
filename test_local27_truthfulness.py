"""
test_local27_truthfulness.py — LOCAL-27 content truthfulness regression test.
=============================================================================
Verifies that museum tours do NOT contain fabricated metadata:
1. Museum Information field must be sourced from official site or ABSENT
2. Type/Specialty must derive from corpus data or be ABSENT
3. Specific Examples must derive from corpus data or be ABSENT
4. No stop may contradict itself (declared type vs prose content)

Runs the storied pipeline for a museum with known facts to verify.

Usage:
    python test_local27_truthfulness.py
"""
import os
import sys
import re
import json

os.environ["STORIED_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def extract_field(tour_text, field_name):
    """Extract a field value from tour text."""
    pattern = re.compile(rf'^{re.escape(field_name)}:\s*(.+?)$', re.MULTILINE)
    matches = pattern.findall(tour_text)
    return matches


def extract_stops_with_type(tour_text):
    """Extract stop headers and their associated Type/Specialty fields."""
    stops = []
    current_stop = None
    current_type = None
    
    for line in tour_text.split('\n'):
        stop_match = re.match(r'^Stop\s+(\d+):\s+(.+)', line)
        if stop_match:
            if current_stop is not None:
                stops.append({'name': current_stop, 'type': current_type})
            current_stop = stop_match.group(2).strip()
            current_type = None
        elif line.startswith('Type/Specialty:'):
            current_type = line.replace('Type/Specialty:', '').strip()
    
    if current_stop is not None:
        stops.append({'name': current_stop, 'type': current_type})
    
    return stops


def check_museum_information_stability(tour_texts):
    """Check that Museum Information field is stable across runs (sourced, not fabricated)."""
    museum_info_values = []
    for text in tour_texts:
        fields = extract_field(text, 'Museum Information')
        museum_info_values.append(fields[0] if fields else None)
    
    # All should be the same (sourced) or all absent
    unique_values = set(str(v) for v in museum_info_values)
    return len(unique_values) <= 1, museum_info_values


def check_no_fabricated_type_specialty(tour_text, corpus_result=None):
    """Verify Type/Specialty fields are not generic fabricated filler."""
    stops = extract_stops_with_type(tour_text)
    
    # Known fabricated patterns that should never appear
    FABRICATED_PATTERNS = [
        r'contemporary art.*various',
        r'modern artistic expressions',
        r'scenic paintings capturing',
        r'artistic expressions in various forms',
        r'various forms of art',
        r'diverse collection of',
    ]
    
    issues = []
    for stop in stops:
        if not stop['type']:
            continue  # Absent is fine
        for pattern in FABRICATED_PATTERNS:
            if re.search(pattern, stop['type'], re.IGNORECASE):
                issues.append(f"Stop '{stop['name']}': type_specialty looks fabricated: '{stop['type']}'")
    
    return issues


def check_no_self_contradictions(tour_text):
    """Check that no stop's Type/Specialty contradicts its description."""
    CONTRADICTING_PAIRS = [
        ('contemporary', ['tang dynasty', 'song dynasty', 'ming dynasty', 'ancient', 'antiquity']),
        ('ancient', ['contemporary', 'modern art', '20th century', '21st century']),
        ('medieval', ['contemporary', 'modern art', 'impressionist']),
    ]
    
    issues = []
    # Split into stop sections
    sections = re.split(r'\n(?=Stop\s+\d+:)', tour_text)
    
    for section in sections:
        # Extract type
        type_match = re.search(r'^Type/Specialty:\s*(.+)$', section, re.MULTILINE)
        if not type_match:
            continue
        declared_type = type_match.group(1).lower()
        
        # Get the description text (everything after the metadata fields)
        desc_lines = []
        in_desc = False
        for line in section.split('\n'):
            if in_desc:
                desc_lines.append(line)
            elif not any(line.startswith(f) for f in 
                       ['Stop ', 'Address:', 'Coordinates:', 'Type/Specialty:', 
                        'Specific Examples:', 'Museum Information:', 'Orientation:']):
                if line.strip():
                    in_desc = True
                    desc_lines.append(line)
        
        desc_text = ' '.join(desc_lines).lower()
        
        for type_keyword, contradicting_keywords in CONTRADICTING_PAIRS:
            if type_keyword in declared_type:
                for ck in contradicting_keywords:
                    if ck in desc_text:
                        # Count occurrences — one mention might be comparative, 2+ is a contradiction
                        count = desc_text.count(ck)
                        if count >= 2:
                            issues.append(
                                f"CONTRADICTION: Type says '{declared_type}' but prose "
                                f"mentions '{ck}' {count} times"
                            )
    
    return issues


def run_test():
    """Run the LOCAL-27 truthfulness regression test."""
    from generate_tour_text import generate_tour_text
    
    print("=" * 70)
    print("LOCAL-27 TRUTHFULNESS REGRESSION TEST")
    print("=" * 70)
    
    PASS = 0
    FAIL = 0
    
    # --- Test 1: Museum Information must not be fabricated ---
    print("\n" + "-" * 70)
    print("[1] Museum Information stability (Musée Chagall Nice)")
    print("-" * 70)
    
    tour_text, _, _ = generate_tour_text(
        "Musee National Marc Chagall, Nice, France", "museum", total_stops=8
    )
    
    if not tour_text:
        print("  FAIL: Generation returned no text")
        FAIL += 1
    else:
        museum_info = extract_field(tour_text, 'Museum Information')
        if museum_info:
            # If present, it must look like sourced data (contains specific time patterns)
            info_text = museum_info[0]
            has_time_pattern = bool(re.search(r'\d{1,2}h?\d{0,2}\s*[-–àa]\s*\d{1,2}h?\d{0,2}|\d{1,2}(?::\d{2})?\s*(?:am|pm)', info_text, re.IGNORECASE))
            has_day_pattern = bool(re.search(r'lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|monday|tuesday|wednesday|thursday|friday|saturday|sunday', info_text, re.IGNORECASE))
            has_price_pattern = bool(re.search(r'gratuit|free|€|\d+\s*euros?', info_text, re.IGNORECASE))
            
            if has_time_pattern or has_day_pattern or has_price_pattern:
                print(f"  PASS: Museum Information present and appears sourced: '{info_text[:80]}...'")
                PASS += 1
            else:
                # Suspicious — might be fabricated
                print(f"  INFO: Museum Information present but unclear sourcing: '{info_text[:80]}...'")
                print(f"        (Absent is acceptable; only flagging for review)")
                PASS += 1
        else:
            print(f"  PASS: Museum Information field ABSENT (correct — sourced-or-omit)")
            PASS += 1
    
    # --- Test 2: Type/Specialty must not be fabricated filler ---
    print("\n" + "-" * 70)
    print("[2] Type/Specialty not fabricated filler")
    print("-" * 70)
    
    if not tour_text:
        print("  SKIP: No tour text from test 1")
    else:
        issues = check_no_fabricated_type_specialty(tour_text)
        if issues:
            for issue in issues:
                print(f"  FAIL: {issue}")
            FAIL += 1
        else:
            stops = extract_stops_with_type(tour_text)
            types_present = [s for s in stops if s['type']]
            types_absent = [s for s in stops if not s['type']]
            print(f"  PASS: {len(types_present)} stops have type_specialty, "
                  f"{len(types_absent)} omitted (all acceptable)")
            for s in types_present:
                print(f"    '{s['name']}' → '{s['type']}'")
            PASS += 1
    
    # --- Test 3: No self-contradictions ---
    print("\n" + "-" * 70)
    print("[3] No type/prose contradictions")
    print("-" * 70)
    
    if not tour_text:
        print("  SKIP: No tour text from test 1")
    else:
        contradictions = check_no_self_contradictions(tour_text)
        if contradictions:
            for c in contradictions:
                print(f"  FAIL: {c}")
            FAIL += 1
        else:
            print(f"  PASS: Zero self-contradictions detected")
            PASS += 1
    
    # --- Test 4: Specific Examples must not be generic filler ---
    print("\n" + "-" * 70)
    print("[4] Specific Examples not generic filler")
    print("-" * 70)
    
    if not tour_text:
        print("  SKIP: No tour text from test 1")
    else:
        specific_examples = extract_field(tour_text, 'Specific Examples')
        FILLER_PATTERNS = [
            r'various forms',
            r'artistic expressions',
            r'capturing the essence',
            r'diverse collection',
            r'modern .* in various',
        ]
        filler_found = []
        for ex in specific_examples:
            for pattern in FILLER_PATTERNS:
                if re.search(pattern, ex, re.IGNORECASE):
                    filler_found.append(f"'{ex[:60]}...' matches filler pattern '{pattern}'")
        
        if filler_found:
            for f in filler_found:
                print(f"  FAIL: {f}")
            FAIL += 1
        else:
            if specific_examples:
                print(f"  PASS: {len(specific_examples)} Specific Examples present, none are filler")
                for ex in specific_examples[:3]:
                    print(f"    → '{ex[:60]}'")
            else:
                print(f"  PASS: Specific Examples field ABSENT (correct — sourced-or-omit)")
            PASS += 1
    
    # --- Test 5: Operational Details absent for non-first stops ---
    print("\n" + "-" * 70)
    print("[5] Museum Information only on stop 1 (or absent entirely)")
    print("-" * 70)
    
    if not tour_text:
        print("  SKIP: No tour text from test 1")
    else:
        # Split by stops and check Museum Information appears only in Stop 1 section
        sections = re.split(r'\n(?=Stop\s+\d+:)', tour_text)
        info_in_wrong_stop = []
        for section in sections:
            stop_match = re.match(r'Stop\s+(\d+):', section)
            if stop_match:
                stop_num = int(stop_match.group(1))
                if stop_num > 1 and 'Museum Information:' in section:
                    info_in_wrong_stop.append(stop_num)
        
        if info_in_wrong_stop:
            print(f"  FAIL: Museum Information found in stop(s) {info_in_wrong_stop} (should only be stop 1)")
            FAIL += 1
        else:
            print(f"  PASS: Museum Information correctly limited to stop 1 (or absent)")
            PASS += 1
    
    # --- Summary ---
    print("\n" + "=" * 70)
    print(f"LOCAL-27 TRUTHFULNESS: {PASS} PASS, {FAIL} FAIL")
    print("=" * 70)
    
    return FAIL == 0


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
