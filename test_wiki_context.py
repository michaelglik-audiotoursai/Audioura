"""Find work-in-venue context in the Marc Chagall article."""
import requests, re

r = requests.get("https://en.wikipedia.org/w/api.php", params={
    "action": "query", "prop": "extracts", "explaintext": "1",
    "formatversion": "2", "titles": "Marc Chagall", "format": "json",
}, headers={"User-Agent": "Audioura/2.2"}, timeout=10)

data = r.json()
pages = data.get("query", {}).get("pages", [])
text = pages[0].get("extract", "") if pages else ""
print(f"Article length: {len(text)} chars")

# Find paragraphs that mention both Nice/museum AND specific works
paragraphs = text.split("\n")
nice_paras = [p for p in paragraphs if "nice" in p.lower() or "chagall museum" in p.lower() or "message biblique" in p.lower()]
print(f"\nParagraphs mentioning Nice/museum/message biblique ({len(nice_paras)}):")
for p in nice_paras[:5]:
    print(f"\n  {p[:300]}")

# Check specific work names in Nice-context paragraphs
works = ["Song of Songs", "Sacrifice of Isaac", "Creation of Man", "Exodus", "Prophet Elijah", "Prophet Jeremiah"]
nice_text = " ".join(nice_paras).lower()
print(f"\n\nWorks found in Nice-context paragraphs:")
for w in works:
    found = w.lower() in nice_text
    print(f"  {w}: {found}")
