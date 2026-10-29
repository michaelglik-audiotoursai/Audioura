#!/usr/bin/env python3
"""extract_tours.py — LOCAL-812.

Reads the catalog manifest + the 10 tour ZIPs in ~/Audioura/catalog/export and
writes website/seo/build/tours_data.json: everything the static page generator
needs (titles, slugs, city, coords, per-stop title/type/coords/teaser-source).

The ZIPs are NOT committed; only the derived JSON is used to build the pages.
Teasers on the pages are REWRITTEN from this text by the generator — the full
narration is never published verbatim.
"""
import json
import os
import re
import unicodedata
import zipfile

EXPORT_DIR = os.path.expanduser("~/Audioura/catalog/export")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tours_data.json")

# City metadata: display name, slug, country, lat/lng (city centre), blurb.
CITY = {
    "Paris": {"slug": "paris", "country": "France", "lat": 48.8566, "lng": 2.3522},
    "Rome": {"slug": "rome", "country": "Italy", "lat": 41.9028, "lng": 12.4964},
    "London": {"slug": "london", "country": "United Kingdom", "lat": 51.5074, "lng": -0.1278},
    "New York": {"slug": "new-york", "country": "United States", "lat": 40.7128, "lng": -74.0060},
    "Barcelona": {"slug": "barcelona", "country": "Spain", "lat": 41.3874, "lng": 2.1686},
    "Istanbul": {"slug": "istanbul", "country": "Türkiye", "lat": 41.0082, "lng": 28.9784},
    "Prague": {"slug": "prague", "country": "Czech Republic", "lat": 50.0755, "lng": 14.4378},
    "Florence": {"slug": "florence", "country": "Italy", "lat": 43.7696, "lng": 11.2558},
}

# Per-tour overrides: natural H1 title, slug, city, duration (min), place_query
# (for keyword research), short city-hub label.
TOUR_META = {
    844: {"city": "Paris", "slug": "montmartre-walking-tour",
          "h1": "Montmartre walking tour — 5 stops through artistic Paris",
          "place_query": "Montmartre Paris", "duration_min": 60,
          "distance_km": 1.2, "kind": "walking"},
    845: {"city": "Paris", "slug": "louvre-museum-audio-tour",
          "h1": "Louvre Museum audio tour — 5 masterpieces in 60 minutes",
          "place_query": "Louvre Museum Paris", "duration_min": 60,
          "distance_km": None, "kind": "museum"},
    846: {"city": "Rome", "slug": "colosseum-roman-forum-walking-tour",
          "h1": "Colosseum & Roman Forum walking tour — 5 ancient landmarks",
          "place_query": "Colosseum Roman Forum Rome", "duration_min": 75,
          "distance_km": 1.0, "kind": "walking"},
    848: {"city": "London", "slug": "british-museum-audio-tour",
          "h1": "British Museum audio tour — 5 world treasures in an hour",
          "place_query": "British Museum London", "duration_min": 60,
          "distance_km": None, "kind": "museum"},
    850: {"city": "New York", "slug": "met-museum-audio-tour",
          "h1": "Metropolitan Museum of Art audio tour — 5 masterpieces",
          "place_query": "Metropolitan Museum of Art New York", "duration_min": 60,
          "distance_km": None, "kind": "museum"},
    852: {"city": "Barcelona", "slug": "gothic-quarter-walking-tour",
          "h1": "Gothic Quarter walking tour — 5 medieval stops in Barcelona",
          "place_query": "Gothic Quarter Barcelona", "duration_min": 60,
          "distance_km": 0.9, "kind": "walking"},
    853: {"city": "Barcelona", "slug": "gaudi-architecture-walking-tour",
          "h1": "Gaudí architecture walking tour — 5 Barcelona landmarks",
          "place_query": "Gaudi architecture Barcelona", "duration_min": 90,
          "distance_km": 4.5, "kind": "walking"},
    856: {"city": "Istanbul", "slug": "sultanahmet-walking-tour",
          "h1": "Sultanahmet walking tour — 5 stops in old Istanbul",
          "place_query": "Sultanahmet Istanbul", "duration_min": 75,
          "distance_km": 1.0, "kind": "walking"},
    858: {"city": "Prague", "slug": "old-town-charles-bridge-walking-tour",
          "h1": "Prague Old Town & Charles Bridge walking tour — 5 stops",
          "place_query": "Old Town Charles Bridge Prague", "duration_min": 75,
          "distance_km": 1.3, "kind": "walking"},
    859: {"city": "Florence", "slug": "uffizi-gallery-audio-tour",
          "h1": "Uffizi Gallery audio tour — 5 Renaissance masterpieces",
          "place_query": "Uffizi Gallery Florence", "duration_min": 60,
          "distance_km": None, "kind": "museum"},
}


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def clean(text):
    """Collapse whitespace; strip the manifest's escape artefacts."""
    return re.sub(r"\s+", " ", text).strip()


def parse_stops(content):
    """Parse 'Stop N:' blocks from tour_content.txt into structured stops.
    Returns list of dicts with num, title, address, lat, lng, type, and the
    first 2 substantive 'story' paragraphs (teaser source — NOT published raw).
    """
    parts = re.split(r"\nStop (\d+):\s*", "\n" + content)
    stops = []
    for i in range(1, len(parts), 2):
        num = int(parts[i])
        body = parts[i + 1]
        lines = body.split("\n")
        title = lines[0].strip()
        addr = re.search(r"Address:\s*(.+)", body)
        coords = re.search(r"Coordinates:\s*([-\d.]+),\s*([-\d.]+)", body)
        typ = re.search(r"Type/Specialty:\s*(.+)", body)
        # The narrative sits after 'Orientation:' and before 'Directions:'.
        story = ""
        mo = re.search(r"Orientation:\s*(.+?)(?:\nDirections:|\Z)", body, re.S)
        if mo:
            story = clean(mo.group(1))
        stops.append({
            "num": num,
            "title": clean(title),
            "address": clean(addr.group(1)) if addr else None,
            "lat": float(coords.group(1)) if coords else None,
            "lng": float(coords.group(2)) if coords else None,
            "type": clean(typ.group(1)) if typ else None,
            "story_source": story,
        })
    return stops


def main():
    manifest = json.load(open(os.path.join(EXPORT_DIR, "manifest.json")))
    out = []
    for t in manifest["tours"]:
        sid = t["source_id"]
        meta = TOUR_META[sid]
        zf = os.path.join(EXPORT_DIR, t["zip_file"])
        with zipfile.ZipFile(zf) as z:
            content = z.read("tour_content.txt").decode("utf-8", "replace")
        stops = parse_stops(content)
        # fall back to the manifest centre when a stop has no coords
        for s in stops:
            if s["lat"] is None:
                s["lat"], s["lng"] = t["lat"], t["lng"]
        city = meta["city"]
        out.append({
            "source_id": sid,
            "slug": meta["slug"],
            "h1": meta["h1"],
            "short_title": t["short_title"],
            "city": city,
            "city_slug": CITY[city]["slug"],
            "country": CITY[city]["country"],
            "place_query": meta["place_query"],
            "kind": meta["kind"],
            "lat": t["lat"],
            "lng": t["lng"],
            "duration_min": meta["duration_min"],
            "distance_km": meta["distance_km"],
            "stops_count": t["stops_count"],
            "stops": stops,
            "zip_file": t["zip_file"],  # for audio extraction, not committed
        })
    json.dump(out, open(OUT, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("Wrote %s (%d tours)" % (OUT, len(out)))
    for t in out:
        print("  %s / %s — %d stops" % (t["city_slug"], t["slug"], len(t["stops"])))


if __name__ == "__main__":
    main()
