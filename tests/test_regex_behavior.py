#!/usr/bin/env python3
"""
Test the actual behavior of the Guy Raz regex
"""
import re

def test_regex_behavior():
    """Test what the regex is actually doing"""
    
    # Sample text with smart quotes (like Guy Raz content)
    sample_text = "If you've ever wandered into a big-box baby store and felt your heart rate spike, you'll recognize the origin story of Babylist. Natalie Gordon wasn't trying to build a billion-dollar brand."
    
    print("=== REGEX BEHAVIOR TEST ===")
    print(f"Original text: {sample_text}")
    print(f"Original length: {len(sample_text)} chars")
    print()
    
    # Test the actual regex from the code
    regex_pattern = r'[^\\x20-\\x7E\\n\\r\\t]+'
    print(f"Regex pattern: {regex_pattern}")
    
    # Apply the regex
    cleaned = re.sub(regex_pattern, ' ', sample_text)
    print(f"After regex: {cleaned}")
    print(f"After length: {len(cleaned)} chars")
    print()
    
    # Check what characters are being matched
    matches = re.findall(regex_pattern, sample_text)
    print(f"Characters matched by regex: {matches}")
    print(f"Number of matches: {len(matches)}")
    
    # Test each character individually
    print("\nCharacter analysis:")
    for i, char in enumerate(sample_text[:50]):  # First 50 chars
        ascii_val = ord(char)
        in_range = 0x20 <= ascii_val <= 0x7E
        print(f"{i:2d}. '{char}' = {ascii_val:3d} (0x{ascii_val:02X}) - {'KEEP' if in_range or char in '\\n\\r\\t' else 'REMOVE'}")

def test_correct_regex():
    """Test what the regex should be"""
    
    sample_text = "If you've ever wandered into a big-box baby store and felt your heart rate spike, you'll recognize the origin story of Babylist."
    
    print("\n=== CORRECT REGEX TEST ===")
    print(f"Original: {sample_text}")
    print(f"Length: {len(sample_text)}")
    
    # Correct regex - single backslash
    correct_pattern = r'[^\x20-\x7E\n\r\t]+'
    cleaned_correct = re.sub(correct_pattern, ' ', sample_text)
    print(f"Correct regex result: {cleaned_correct}")
    print(f"Correct length: {len(cleaned_correct)}")
    
    # Show what gets removed
    matches = re.findall(correct_pattern, sample_text)
    print(f"Removed characters: {matches}")

if __name__ == "__main__":
    test_regex_behavior()
    test_correct_regex()