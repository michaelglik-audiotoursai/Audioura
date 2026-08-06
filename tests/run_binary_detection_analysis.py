#!/usr/bin/env python3
"""
Binary Detection Analysis for Guy Raz Content
Test each criteria individually to identify which one incorrectly flags clean content as binary
"""

def analyze_binary_detection_criteria(text):
    """Analyze Guy Raz content against each binary detection criteria"""
    
    print("=== BINARY DETECTION ANALYSIS ===")
    print(f"Content Length: {len(text)} characters")
    print(f"Content Preview: {text[:200]}...")
    print()
    
    # Test 1: Printable Character Ratio (80% threshold)
    print("1. PRINTABLE CHARACTER RATIO TEST")
    printable_chars = 0
    total_chars = len(text)
    
    for c in text:
        if c.isprintable() or c.isspace():
            printable_chars += 1
    
    printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
    print(f"   Printable chars: {printable_chars}/{total_chars}")
    print(f"   Printable ratio: {printable_ratio:.4f} ({printable_ratio*100:.2f}%)")
    print(f"   Threshold: 0.8000 (80%)")
    print(f"   RESULT: {'FAIL' if printable_ratio < 0.8 else 'PASS'} - {'Below' if printable_ratio < 0.8 else 'Above'} threshold")
    print()
    
    # Test 2: Control Character Detection (10% threshold)
    print("2. CONTROL CHARACTER DETECTION TEST")
    control_chars = 0
    
    for c in text:
        if ord(c) < 32 and c not in '\n\r\t':  # Control characters excluding newline, carriage return, tab
            control_chars += 1
    
    control_ratio = control_chars / total_chars if total_chars > 0 else 0
    print(f"   Control chars: {control_chars}/{total_chars}")
    print(f"   Control ratio: {control_ratio:.4f} ({control_ratio*100:.2f}%)")
    print(f"   Threshold: 0.1000 (10%)")
    print(f"   RESULT: {'FAIL' if control_ratio > 0.1 else 'PASS'} - {'Above' if control_ratio > 0.1 else 'Below'} threshold")
    print()
    
    # Test 3: Suspicious Character Sequence Detection (30% threshold)
    print("3. SUSPICIOUS CHARACTER SEQUENCE TEST")
    suspicious_count = 0
    
    for i in range(len(text) - 1):
        c1, c2 = text[i], text[i + 1]
        # Look for patterns like random chars followed by symbols
        if (not c1.isalnum() and not c1.isspace() and 
            not c2.isalnum() and not c2.isspace() and
            c1 != c2):  # Different non-alphanumeric chars in sequence
            suspicious_count += 1
    
    suspicious_ratio = suspicious_count / total_chars if total_chars > 0 else 0
    print(f"   Suspicious sequences: {suspicious_count}/{total_chars}")
    print(f"   Suspicious ratio: {suspicious_ratio:.4f} ({suspicious_ratio*100:.2f}%)")
    print(f"   Threshold: 0.3000 (30%)")
    print(f"   RESULT: {'FAIL' if suspicious_ratio > 0.3 else 'PASS'} - {'Above' if suspicious_ratio > 0.3 else 'Below'} threshold")
    print()
    
    # Test 4: Specific Binary Patterns
    print("4. SPECIFIC BINARY PATTERN TEST")
    binary_patterns = [
        ('\\ufffd', 'Unicode replacement character'),
        ('\\u0000', 'Null character'),
        ('\\u0001', 'Start of heading'),
        ('\\u0002', 'Start of text'),
        ('\\x00', 'Null byte')
    ]
    
    patterns_found = []
    for pattern, description in binary_patterns:
        if pattern in text:
            patterns_found.append((pattern, description))
    
    print(f"   Patterns checked: {len(binary_patterns)}")
    print(f"   Patterns found: {len(patterns_found)}")
    if patterns_found:
        for pattern, desc in patterns_found:
            print(f"     - {pattern}: {desc}")
    print(f"   RESULT: {'FAIL' if patterns_found else 'PASS'} - {'Found' if patterns_found else 'No'} binary patterns")
    print()
    
    # Test 5: UTF-8 Encoding Test
    print("5. UTF-8 ENCODING TEST")
    try:
        text.encode('utf-8')
        encoding_ok = True
        encoding_error = None
    except (UnicodeError, UnicodeEncodeError, UnicodeDecodeError) as e:
        encoding_ok = False
        encoding_error = str(e)
    
    print(f"   RESULT: {'PASS' if encoding_ok else 'FAIL'} - {'Can' if encoding_ok else 'Cannot'} encode as UTF-8")
    if not encoding_ok:
        print(f"   Error: {encoding_error}")
    print()
    
    # Overall Binary Detection Result
    print("=== OVERALL BINARY DETECTION RESULT ===")
    
    # Apply the original logic
    is_binary = False
    failing_criteria = []
    
    if printable_ratio < 0.8:
        is_binary = True
        failing_criteria.append("Printable ratio < 80%")
    
    if control_ratio > 0.1:
        is_binary = True
        failing_criteria.append("Control chars > 10%")
    
    if suspicious_ratio > 0.3:
        is_binary = True
        failing_criteria.append("Suspicious sequences > 30%")
    
    if patterns_found:
        is_binary = True
        failing_criteria.append("Binary patterns detected")
    
    if not encoding_ok:
        is_binary = True
        failing_criteria.append("UTF-8 encoding failed")
    
    print(f"Binary Detection: {'BINARY' if is_binary else 'CLEAN'}")
    if failing_criteria:
        print(f"Failing Criteria:")
        for i, criteria in enumerate(failing_criteria, 1):
            print(f"  {i}. {criteria}")
    else:
        print("All criteria passed - content is clean")
    
    return {
        'is_binary': is_binary,
        'printable_ratio': printable_ratio,
        'control_ratio': control_ratio,
        'suspicious_ratio': suspicious_ratio,
        'patterns_found': len(patterns_found),
        'encoding_ok': encoding_ok,
        'failing_criteria': failing_criteria
    }

def main():
    # Read the Guy Raz content from step 4 file
    try:
        with open('step_4_after_guy_raz_specific_cleaning.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract just the content part (skip the header)
        lines = content.split('\n')
        content_start = False
        actual_content = []
        
        for line in lines:
            if line.strip() == '=' * 60:
                content_start = True
                continue
            if content_start and line.strip():
                actual_content.append(line)
        
        guy_raz_text = '\n'.join(actual_content)
        
        # Analyze the content
        result = analyze_binary_detection_criteria(guy_raz_text)
        
        print("\n" + "="*60)
        print("SUMMARY:")
        print(f"The Guy Raz content is incorrectly flagged as binary due to:")
        for criteria in result['failing_criteria']:
            print(f"  - {criteria}")
        
        if not result['failing_criteria']:
            print("  • No criteria are failing - content should be detected as clean!")
        
    except FileNotFoundError:
        print("Error: step_4_after_guy_raz_specific_cleaning.txt not found")
        print("Please ensure the file exists in the current directory")
    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    main()