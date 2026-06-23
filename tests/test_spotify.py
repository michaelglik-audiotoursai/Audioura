import requests
import re
import html

# Test Spotify content extraction
url = 'https://open.spotify.com/episode/7k6m0uRJQohNyYp7omyYm7'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

r = requests.get(url, headers=headers)
content = r.text

print("=== TITLE EXTRACTION ===")
title_match = re.search(r'<title[^>]*>([^<]+)</title>', content)
if title_match:
    title = html.unescape(title_match.group(1))
    print(f"Raw title: {title}")
    clean_title = title.replace(' - Spotify', '').replace(' | Podcast on Spotify', '').strip()
    print(f"Clean title: {clean_title}")
else:
    print("No title found")

print("\n=== DESCRIPTION PATTERNS ===")
desc_patterns = [
    r'<meta property="og:description" content="([^"]+)"',
    r'<meta name="description" content="([^"]+)"',
    r'"description":"([^"]+)"'
]

for i, pattern in enumerate(desc_patterns):
    match = re.search(pattern, content)
    if match:
        desc = html.unescape(match.group(1))
        print(f"Pattern {i} found: {desc[:200]}...")
    else:
        print(f"Pattern {i}: Not found")

print(f"\n=== CONTENT LENGTH ===")
print(f"Total HTML length: {len(content)}")