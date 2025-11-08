#!/usr/bin/env python3
"""
Test to identify where binary contamination is introduced in Guy Raz content
"""

def analyze_character_corruption(text):
    """Analyze where binary characters appear in the text"""
    
    print("=== BINARY CHARACTER ANALYSIS ===")
    print(f"Text length: {len(text)} characters")
    print()
    
    # Find all non-ASCII characters
    non_ascii_chars = []
    for i, char in enumerate(text):
        if ord(char) > 127:  # Non-ASCII
            non_ascii_chars.append((i, char, ord(char), hex(ord(char))))
    
    print(f"Non-ASCII characters found: {len(non_ascii_chars)}")
    
    if non_ascii_chars:
        print("\nFirst 10 non-ASCII characters:")
        for i, (pos, char, code, hex_code) in enumerate(non_ascii_chars[:10]):
            # Get context around the character
            start = max(0, pos - 20)
            end = min(len(text), pos + 20)
            context = text[start:end]
            
            print(f"{i+1:2d}. Position {pos:4d}: '{char}' (U+{hex_code[2:].upper().zfill(4)}) = {code}")
            print(f"    Context: ...{context}...")
            print()
    
    # Check for specific corrupted patterns
    corrupted_patterns = [
        ("'", "致"),  # Apostrophe corrupted to 致
        ("'", "値"),  # Apostrophe corrupted to 値  
        ("'", "稚"),  # Apostrophe corrupted to 稚
        ("—", "?"),   # Em dash corrupted
        (""", "?"),   # Smart quote corrupted
        (""", "?"),   # Smart quote corrupted
    ]
    
    print("=== CORRUPTION PATTERN ANALYSIS ===")
    for original, corrupted in corrupted_patterns:
        count = text.count(corrupted)
        if count > 0:
            print(f"Found {count} instances of '{corrupted}' (likely corrupted '{original}')")
            # Find first few instances
            pos = 0
            for i in range(min(3, count)):
                pos = text.find(corrupted, pos)
                if pos >= 0:
                    start = max(0, pos - 15)
                    end = min(len(text), pos + 15)
                    context = text[start:end]
                    print(f"  Position {pos}: ...{context}...")
                    pos += 1
    
    return non_ascii_chars

def test_original_vs_corrupted():
    """Compare original clean content with corrupted content"""
    
    # Read the original clean content
    try:
        with open('extracted_content_guy_raz_substack.txt', 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Extract just the content part
        lines = original_content.split('\n')
        content_start = False
        original_text = []
        
        for line in lines:
            if line.strip() == '=' * 60:
                content_start = True
                continue
            if content_start and line.strip():
                original_text.append(line)
        
        original_clean = '\n'.join(original_text)
        
        print("=== ORIGINAL CLEAN CONTENT ===")
        print(f"Length: {len(original_clean)} chars")
        original_non_ascii = analyze_character_corruption(original_clean)
        
    except FileNotFoundError:
        print("Original file not found")
        return
    
    # Read the corrupted step 3 content
    try:
        with open('step_3_after_is_binary_content_validation.txt', 'r', encoding='utf-8') as f:
            step3_content = f.read()
        
        # Extract just the content part
        lines = step3_content.split('\n')
        content_start = False
        step3_text = []
        
        for line in lines:
            if line.strip() == '=' * 60:
                content_start = True
                continue
            if content_start and line.strip():
                step3_text.append(line)
        
        step3_corrupted = '\n'.join(step3_text)
        
        print("\n" + "="*60)
        print("=== STEP 3 CORRUPTED CONTENT ===")
        print(f"Length: {len(step3_corrupted)} chars")
        step3_non_ascii = analyze_character_corruption(step3_corrupted)
        
        # Compare the two
        print("\n" + "="*60)
        print("=== COMPARISON ===")
        print(f"Original non-ASCII chars: {len(original_non_ascii)}")
        print(f"Step 3 non-ASCII chars: {len(step3_non_ascii)}")
        
        if len(step3_non_ascii) > len(original_non_ascii):
            print(f"❌ CORRUPTION DETECTED: {len(step3_non_ascii) - len(original_non_ascii)} new corrupted characters introduced")
        else:
            print("✅ No new corruption detected")
        
        # Find where corruption happens
        if len(original_clean) > 100 and len(step3_corrupted) > 100:
            print("\nFirst 200 chars comparison:")
            print(f"Original: {original_clean[:200]}")
            print(f"Step 3:   {step3_corrupted[:200]}")
            
            # Find first difference
            for i in range(min(len(original_clean), len(step3_corrupted))):
                if original_clean[i] != step3_corrupted[i]:
                    print(f"\nFirst difference at position {i}:")
                    print(f"Original: '{original_clean[i]}' (U+{ord(original_clean[i]):04X})")
                    print(f"Step 3:   '{step3_corrupted[i]}' (U+{ord(step3_corrupted[i]):04X})")
                    break
        
    except FileNotFoundError:
        print("Step 3 file not found")

if __name__ == "__main__":
    test_original_vs_corrupted()