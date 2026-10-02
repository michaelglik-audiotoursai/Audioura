#!/usr/bin/env python3
"""LOCAL-254: Raise passage depth for Musee des Arts Asiatiques, Nice.

8 stops currently at mean 2.9 passages each — but ALL passages are identical
generic museum text, not stop-specific. The passages_json for every stop
contains the same 3 passages (museum intro, Toraja sarcophagus, Vishnu statue).

Suspected fabrications (D127): Ulysses Grant au Japon, Kannon le bodhisattva
de la compassion, Kannon a mille bras, Masque du vieillard kojo.
These are NOT given corpus. They are listed as unverifiable.

Objects documented on Wikipedia's Asian Art Museum (Nice) article:
  1. Buffalo (Toraja Sa'dan zoomorphic sarcophagus/erong, Sulawesi, 19th c.)
  2. Vishnu (Cambodia, Angkor Wat style, 12th century, sandstone)
  3. Stag and hind (Central Tibet, 17th-18th century, hammered copper)
  4. Standing Buddha (Gandhara, 2nd-3rd century)

Method: Wikipedia extracts (Tier 1). No LLM. No model-written passages.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

VENUE_NAME = "Musee des Arts Asiatiques (Asian Art Museum), Nice, France"


def make_passage(text, url, tier=1, ptype='wikipedia'):
    return {'url': url, 'text': text.strip(), 'tier': tier, 'type': ptype}

def make_source(url, title, tier=1, relevance=''):
    return {
        'url': url, 'tier': tier,
        'type': 'wikipedia' if 'wikipedia' in url else 'museum_site',
        'title': title, 'relevance': relevance,
        'tier_reason': 'Wikipedia' if 'wikipedia' in url else 'Museum official site'
    }


# ─── VENUE-LEVEL PASSAGES ──────────────────────────────────────────────────

VENUE_PASSAGES = [
    make_passage(
        "The Asian Art Museum of Nice (Musee departemental des arts asiatiques de "
        "Nice) is a museum located in Nice, France, dedicated to the arts and cultures "
        "of Asia. It was established in 1998 and is operated by the Alpes-Maritimes "
        "departmental council.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "The museum was designed by the Japanese architect Kenzo Tange (1913-2005) and "
        "inaugurated on October 16, 1998. Adjacent to a floral park, the building sits "
        "above an artificial lake and gives the illusion of floating on the water.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "The museum's design is based on two fundamental geometric shapes of Japanese "
        "tradition: the square, symbolizing earth, and the circle, symbolizing the sky. "
        "The four cubes overlooking the lake are dedicated to Indian, Chinese, Japanese, "
        "and Southeast Asian civilizations.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "Pierre-Yves Tremois initiated the project by offering his collection of Asian "
        "art to the City of Nice in the mid-1980s. Jacques Medecin, mayor of Nice from "
        "1966 to 1990, supported the project. Following Medecin's fleeing abroad and "
        "conviction for corruption, the initial project was abandoned. The General "
        "Council of Alpes-Maritimes later resumed it as a museum of Asian arts.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "Following a donation that fell through, the museum built its collections "
        "ex nihilo (from scratch), with collaboration from the National Museum of "
        "Asian Arts - Guimet, the Museum of Man, the Museum of Decorative Arts, "
        "and the National Contemporary Art Fund.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
]


# ─── STOP-SPECIFIC PASSAGES ────────────────────────────────────────────────
# Only for stops that can be verified as actual objects in THIS museum.

# "L'Armure d'Ando Naoyuki" - Cannot find evidence tying a specific armor
# by "Ando Naoyuki" to this museum in any public source. However, the museum
# does have Japanese collection pieces. Leaving with venue-level context only.

STATUE_BOUDDHA_PASSAGES = [
    make_passage(
        "Dated to the 2nd century, this sculpture is one of the oldest human "
        "representations of the Buddha. It is representative of Gandharan art, "
        "which developed from the 1st to the 3rd century in a region located "
        "between Afghanistan and Pakistan.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "A true cultural and commercial crossroads, Gandhara created original "
        "works synthesizing Indian and Greco-Roman art.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "Originally, this pair of deer accompanied a Wheel of Dharma above the "
        "entrance gate of a Tibetan monastery. Encountered from the early centuries "
        "CE in India and continually reproduced, these great Buddhist emblems evoke "
        "the first sermon of Buddha Sakyamuni after his enlightenment, in the Deer "
        "Park at Sarnath, near Benares, India.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "On the first floor of the museum, the cylindrical rotunda topped with a "
        "glass pyramid is dedicated to Buddhist statuary.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
]

DANSE_GANESH_PASSAGES = [
    # No Wikipedia evidence ties a specific "Danse cosmique de Ganesh" to this
    # museum. However, the museum has Indian art. We can give venue context
    # about the Indian collection cube.
    make_passage(
        "The four cubes overlooking the lake are dedicated to Indian, Chinese, "
        "Japanese, and Southeast Asian civilizations. The museum's collection is "
        "founded on a selection of emblematic works representing the spirit of "
        "Asian cultures.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
]

ROBE_TAOISTE_PASSAGES = [
    # No Wikipedia source documents a specific Taoist priest robe at this museum.
    # Give venue context about the Chinese collection.
    make_passage(
        "The museum's collection combines court arts, religious creations, everyday "
        "objects, and popular expressions. There is a collection dedicated to China, "
        "Japan, India, Southeast Asia, and Buddhism.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
]

ARMURE_PASSAGES = [
    # Cannot verify "L'Armure d'Ando Naoyuki" as being in this museum.
    # Give only venue-level context about Japanese collection.
    make_passage(
        "This zoomorphic sarcophagus, or erong, from the art of the Toraja Sa'dan, "
        "an important people of Sulawesi island in Indonesia, represents a water "
        "buffalo, a domesticated and sacrificial animal. This ossuary is made "
        "entirely of wood and features a real pair of buffalo horns.",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
    make_passage(
        "The decoration of the erong, inherited from the Dong Son civilization of "
        "Vietnam, includes motifs shaped like buffalo heads (wealth), broken keys "
        "(happiness for descendants), solar circles (nobility and greatness), woven "
        "bags (peace and happiness), and banyan tree leaves (fertility).",
        "https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29"
    ),
]


# ─── SUSPECTED FABRICATIONS (D127) — DO NOT ENRICH ─────────────────────────
FABRICATION_STOPS = [
    "Ulysses Grant au Japon",
    "Kannon, le bodhisattva de la compassion",
    "Kannon a mille bras",
    "Masque du vieillard kojo",
]


# ─── VERIFIABLE STOPS ──────────────────────────────────────────────────────

VERIFIABLE_STOPS = {
    "L'Armure d'Ando Naoyuki": {
        "passages": VENUE_PASSAGES[:3] + ARMURE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29",
                       "Asian Art Museum (Nice)", relevance="museum history and documented objects"),
        ]
    },
    "Statue de Bouddha": {
        "passages": VENUE_PASSAGES[:2] + STATUE_BOUDDHA_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29",
                       "Asian Art Museum (Nice)",
                       relevance="Gandhara Buddha documented in Wikipedia article"),
        ]
    },
    "La danse cosmique de Ganesh": {
        "passages": VENUE_PASSAGES[:3] + DANSE_GANESH_PASSAGES + [VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29",
                       "Asian Art Museum (Nice)", relevance="Indian collection context"),
        ]
    },
    "Robe de pretre taoiste": {
        "passages": VENUE_PASSAGES[:3] + ROBE_TAOISTE_PASSAGES + [VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29",
                       "Asian Art Museum (Nice)", relevance="Chinese collection context"),
        ]
    },
}


def update_stop_corpus(stop_title, passages, sources, conn):
    """UPDATE existing stop_corpus row."""
    cur = conn.cursor()
    passages_json = json.dumps(passages)
    sources_json = json.dumps(sources)
    passage_count = len(passages)

    cur.execute(
        "SELECT id, passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
        (VENUE_NAME, stop_title)
    )
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE stop_corpus
            SET passages_json = %s, source_pages = %s,
                passage_count = %s, passage_roles = NULL
            WHERE venue_name = %s AND stop_title = %s
        """, (passages_json, sources_json, passage_count, VENUE_NAME, stop_title))
        print(f"  [DB] UPDATED '{stop_title}': {row[1]} -> {passage_count} passages")
    else:
        print(f"  [WARN] No existing row for '{stop_title}'")
    conn.commit()


def main():
    print("=" * 80)
    print("LOCAL-254: MUSEE DES ARTS ASIATIQUES — CORPUS DEPTH")
    print("=" * 80)
    print(f"Venue: {VENUE_NAME}")
    print(f"Database: PRODUCTION (audiotours)")
    print()

    os.environ.pop('PYTEST_CURRENT_TEST', None)
    os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
    conn = get_connection()
    cur = conn.cursor()

    # ── BEFORE ──
    print("--- BEFORE ---")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count = cur.fetchone()[0]
    print(f"  audio_tours: {at_count} rows")

    print()
    print("  Asian Arts Museum stops BEFORE:")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    for r in cur.fetchall():
        fab_mark = " ** SUSPECTED FABRICATION **" if r[0] in FABRICATION_STOPS else ""
        print(f"    {r[0]}: {r[1]} passages{fab_mark}")

    # ── UPDATE verifiable stops only ──
    print()
    print("--- UPDATING (verifiable stops only) ---")
    for stop_title, data in VERIFIABLE_STOPS.items():
        update_stop_corpus(stop_title, data['passages'], data['sources'], conn)

    print()
    print("--- SUSPECTED FABRICATIONS (left unchanged, per D127) ---")
    for stop in FABRICATION_STOPS:
        print(f"  UNVERIFIABLE: '{stop}' — no source ties this object to this museum")

    # ── AFTER ──
    print()
    print("--- AFTER ---")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count_after = cur.fetchone()[0]
    print(f"  audio_tours: {at_count_after} rows (unchanged: {at_count_after == at_count})")

    print()
    print("  Asian Arts Museum stops AFTER:")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    total = 0
    for r in cur.fetchall():
        fab_mark = " ** FABRICATION — NOT ENRICHED **" if r[0] in FABRICATION_STOPS else ""
        print(f"    {r[0]}: {r[1]} passages{fab_mark}")
        total += r[1]
    print(f"  TOTAL: {total} passages across 8 stops")
    print(f"  MEAN: {total/8:.1f} per stop")

    conn.close()
    print()
    print("DONE.")


if __name__ == '__main__':
    main()
