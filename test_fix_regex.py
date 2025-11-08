#!/usr/bin/env python3
"""
Test the correct regex pattern
"""
import re

def test_correct_regex():
    """Test what the correct regex should be"""
    
    sample_text = "If you've ever wandered into a big-box baby store and felt your heart rate spike, you'll recognize the origin story of Babylist."
    
    print("=== TESTING CORRECT REGEX ===")
    print(f"Original: {sample_text}")
    print(f"Length: {len(sample_text)}")
    
    # CORRECT regex pattern (single backslashes)
    correct_pattern = r'[^\x20-\x7E\n\r\t]+'
    print(f"Correct pattern: {correct_pattern}")
    
    cleaned = re.sub(correct_pattern, ' ', sample_text)
    print(f"After correct regex: {cleaned}")
    print(f"Length after: {len(cleaned)}")
    
    # Show what gets removed
    matches = re.findall(correct_pattern, sample_text)
    print(f"Removed characters: {matches}")
    
    # Test with Guy Raz content
    guy_raz_sample = "If you've ever wandered into a big-box baby store and felt your heart rate spike, you'll recognize the origin story of Babylist. Natalie Gordon wasn't trying to build a billion-dollar brand."
    
    print(f"\nGuy Raz sample: {guy_raz_sample}")
    print(f"Length: {len(guy_raz_sample)}")
    
    cleaned_guy_raz = re.sub(correct_pattern, ' ', guy_raz_sample)
    print(f"After cleaning: {cleaned_guy_raz}")
    print(f"Length after: {len(cleaned_guy_raz)}")

if __name__ == "__main__":
    test_correct_regex()