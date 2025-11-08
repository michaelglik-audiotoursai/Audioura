#!/usr/bin/env python3
"""Debug Spotify content to see actual output"""
import sys
import os
sys.path.append('/app')

from spotify_processor import process_spotify_url

# Test the problematic URL
result = process_spotify_url('https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3')

print("=== SPOTIFY CONTENT DEBUG ===")
print(f"Success: {result.get('success')}")
print(f"Content Length: {len(result.get('content', ''))}")
print(f"Description Length: {len(result.get('description', ''))}")

content = result.get('content', '')
print(f"\n=== FULL CONTENT ===")
print(content)

print(f"\n=== TRUNCATION CHECK ===")
truncation_indicators = ["... Show more", "Show more", "... Read more", "Read more"]
found_truncation = False
for indicator in truncation_indicators:
    if indicator in content:
        print(f"❌ FOUND TRUNCATION: '{indicator}'")
        found_truncation = True

if not found_truncation:
    print("✅ NO TRUNCATION INDICATORS FOUND")

# Save to file for analysis
with open('/app/debug_spotify_full_content.txt', 'w') as f:
    f.write(f"URL: https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3\n")
    f.write(f"Success: {result.get('success')}\n")
    f.write(f"Content Length: {len(content)}\n")
    f.write(f"Description Length: {len(result.get('description', ''))}\n")
    f.write(f"\n=== FULL CONTENT ===\n")
    f.write(content)

print(f"\n✅ Content saved to /app/debug_spotify_full_content.txt")