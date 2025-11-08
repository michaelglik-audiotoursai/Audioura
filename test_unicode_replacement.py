#!/usr/bin/env python3
"""
Test Unicode character replacement for TTS-friendly text
"""

def test_unicode_replacement():
    """Test replacing Unicode characters with ASCII equivalents"""
    
    sample_text = "If you've ever wandered into a big-box baby store and felt your heart rate spike, you'll recognize the origin story of Babylist. Natalie Gordon wasn't trying to build a billion—dollar brand."
    
    print("=== UNICODE REPLACEMENT TEST ===")
    print(f"Original: {sample_text}")
    print(f"Length: {len(sample_text)}")
    
    # Replace Unicode characters with ASCII equivalents
    cleaned = sample_text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('\u2014', '-').replace('\u2013', '-')
    
    print(f"After replacement: {cleaned}")
    print(f"Length after: {len(cleaned)}")
    
    # Show what changed
    if sample_text != cleaned:
        print("Changes made:")
        for i, (orig, new) in enumerate(zip(sample_text, cleaned)):
            if orig != new:
                print(f"  Position {i}: '{orig}' (U+{ord(orig):04X}) → '{new}' (U+{ord(new):04X})")

if __name__ == "__main__":
    test_unicode_replacement()