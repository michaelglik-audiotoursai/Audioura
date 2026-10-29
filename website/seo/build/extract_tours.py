#!/usr/bin/env python3
"""extract_tours.py — LOCAL-812 / LOCAL-812B.

Reads the catalog manifest + the 10 tour ZIPs in ~/Audioura/catalog/export and
writes website/seo/build/tours_data.json: everything the static page generator
needs (titles, slugs, city, coords, per-stop title/type/coords/teaser-source).

The ZIPs are NOT committed; only the derived JSON is used to build the pages.
Teasers on the pages are REWRITTEN from this text by the generator — the full
narration is never published verbatim.

LOCAL-812B: the published "minutes" are now the REAL listening time, measured by
ffprobe over each tour's narration audio (audio_*.mp3 inside the ZIP), not an
invented round number. We sum the per-stop audio durations and round to the
nearest minute → `listen_min`. Walking distance stays a SEPARATE figure
(`distance_km`): listening time is not walking time. If ffprobe or the audio is
unavailable, `listen_min` is written as null and the generator omits the claim
rather than inventing one.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
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

# Per-tour overrides: natural H1 title, slug, city, place_query (for keyword
# research) and kind. `distance_km` is the walking distance between stops for
# walking tours (None for in-building museum tours). NOTE (LOCAL-812B): there is
# no hand-written duration here any more — the published listening time is
# measured from the real audio (see audio_listen_min).
TOUR_META = {
    844: {"city": "Paris", "slug": "montmartre-walking-tour",
          "h1": "Montmartre walking tour — 5 stops through artistic Paris",
          "place_query": "Montmartre Paris",
          "distance_km": 1.2, "kind": "walking"},
    845: {"city": "Paris", "slug": "louvre-museum-audio-tour",
          "h1": "Louvre Museum audio tour — 5 masterpieces, narrated",
          "place_query": "Louvre Museum Paris",
          "distance_km": None, "kind": "museum"},
    846: {"city": "Rome", "slug": "colosseum-roman-forum-walking-tour",
          "h1": "Colosseum & Roman Forum walking tour — 5 ancient landmarks",
          "place_query": "Colosseum Roman Forum Rome",
          "distance_km": 1.0, "kind": "walking"},
    848: {"city": "London", "slug": "british-museum-audio-tour",
          "h1": "British Museum audio tour — 5 world treasures",
          "place_query": "British Museum London",
          "distance_km": None, "kind": "museum"},
    850: {"city": "New York", "slug": "met-museum-audio-tour",
          "h1": "Metropolitan Museum of Art audio tour — 5 masterpieces",
          "place_query": "Metropolitan Museum of Art New York",
          "distance_km": None, "kind": "museum"},
    852: {"city": "Barcelona", "slug": "gothic-quarter-walking-tour",
          "h1": "Gothic Quarter walking tour — 5 medieval stops in Barcelona",
          "place_query": "Gothic Quarter Barcelona",
          "distance_km": 0.9, "kind": "walking"},
    853: {"city": "Barcelona", "slug": "gaudi-architecture-walking-tour",
          "h1": "Gaudí architecture walking tour — 5 Barcelona landmarks",
          "place_query": "Gaudi architecture Barcelona",
          "distance_km": 4.5, "kind": "walking"},
    856: {"city": "Istanbul", "slug": "sultanahmet-walking-tour",
          "h1": "Sultanahmet walking tour — 5 stops in old Istanbul",
          "place_query": "Sultanahmet Istanbul",
          "distance_km": 1.0, "kind": "walking"},
    858: {"city": "Prague", "slug": "old-town-charles-bridge-walking-tour",
          "h1": "Prague Old Town & Charles Bridge walking tour — 5 stops",
          "place_query": "Old Town Charles Bridge Prague",
          "distance_km": 1.3, "kind": "walking"},
    859: {"city": "Florence", "slug": "uffizi-gallery-audio-tour",
          "h1": "Uffizi Gallery audio tour — 5 Renaissance masterpieces",
          "place_query": "Uffizi Gallery Florence",
          "distance_km": None, "kind": "museum"},
}


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def _ffprobe_seconds(path):
    """Duration of one media file in seconds, via ffprobe. None on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def measure_listen_min(zip_path):
    """REAL listening time for a tour = sum of its narration audio
    (audio_*.mp3 inside the ZIP), rounded to the nearest minute.

    This is the honest figure published on the page (LOCAL-812B): no invented
    round numbers. Returns an int (minutes) or None if the audio/ffprobe is
    unavailable, in which case the generator omits the duration claim.
    """
    if shutil.which("ffprobe") is None:
        return None
    tmp = tempfile.mkdtemp(prefix="audioura-dur-")
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = sorted(n for n in z.namelist()
                           if re.fullmatch(r"audio_\d+\.mp3", n))
            if not names:
                return None
            total = 0.0
            for n in names:
                dest = z.extract(n, tmp)
                secs = _ffprobe_seconds(dest)
                if secs is None:
                    return None
                total += secs
        return max(1, round(total / 60.0))
    except (zipfile.BadZipFile, OSError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
        listen_min = measure_listen_min(zf)  # REAL audio length, not invented
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
            "listen_min": listen_min,       # minutes of narration (ffprobe)
            "distance_km": meta["distance_km"],
            "stops_count": t["stops_count"],
            "stops": stops,
            "zip_file": t["zip_file"],  # for audio extraction, not committed
        })
    json.dump(out, open(OUT, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("Wrote %s (%d tours)" % (OUT, len(out)))
    for t in out:
        lm = t["listen_min"]
        print("  %s / %s — %d stops, %s min listening%s"
              % (t["city_slug"], t["slug"], len(t["stops"]),
                 lm if lm is not None else "?",
                 (" · %.1f km walk" % t["distance_km"])
                 if t["distance_km"] else ""))


if __name__ == "__main__":
    main()
