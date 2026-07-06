"""Test Wikipedia full article fetch for D1 verification."""
import requests

# Test: full article text via action API formatversion=2
titles_to_test = [
    ("en", "Musee Marc Chagall"),
    ("en", "Marc Chagall"),
    ("fr", "Musée national Marc-Chagall"),
]

for lang, title in titles_to_test:
    host = f"{lang}.wikipedia.org"
    r = requests.get(f"https://{host}/w/api.php", params={
        "action": "query", "prop": "extracts", "explaintext": "1",
        "formatversion": "2", "titles": title, "format": "json",
    }, headers={"User-Agent": "Audioura/2.2"}, timeout=10)
    
    data = r.json()
    pages = data.get("query", {}).get("pages", [])
    
    for p in pages:
        ext = p.get("extract", "")
        print(f"\n{lang}/{title}: {len(ext)} chars")
        if ext:
            lower = ext.lower()
            for term in ["song of songs", "sacrifice", "biblical", "creation", "exodus", "message biblique", "nice"]:
                if term in lower:
                    print(f"  ✓ contains '{term}'")
            # Show first 500 chars
            print(f"  First 300: {ext[:300]}")
