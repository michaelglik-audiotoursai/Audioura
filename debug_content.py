#!/usr/bin/env python3
import requests

url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

response = requests.get(url, headers=headers, timeout=10)
print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)}")
print(f"Apple mentions: {response.text.count('podcasts.apple.com')}")

# Check if content is different
if 'podcasts.apple.com' in response.text:
    index = response.text.find('podcasts.apple.com')
    print(f"First mention: {response.text[index-50:index+200]}")
else:
    # Check for any podcast mentions
    if 'podcast' in response.text.lower():
        print("Found 'podcast' mentions but not Apple Podcasts")
    else:
        print("No podcast content found - might be dynamic loading")
        
    # Check first 1000 chars of content
    print(f"Content preview: {response.text[:1000]}")