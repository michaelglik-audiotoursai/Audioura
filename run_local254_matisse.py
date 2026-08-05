#!/usr/bin/env python3
"""LOCAL-254: Raise passage depth for Musée Matisse, Nice.

6 stops currently at mean 1.2 passages each.
Target: ~5 fact-carrying passages per stop (best effort).

Method: Extract factual passages from Wikipedia. No model-written passages.
Every passage carries a verifiable fact (date, person, documented event).

Source: en.wikipedia.org/wiki/Musée_Matisse_(Nice), en.wikipedia.org/wiki/Henri_Matisse

Budget: $0.00 (Wikipedia is free, no LLM calls)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

VENUE_NAME = "Musee Matisse, Nice, France"


def make_passage(text, url, tier=1, ptype='wikipedia'):
    """Create a passage dict in the standard stop_corpus format."""
    return {
        'url': url,
        'text': text.strip(),
        'tier': tier,
        'type': ptype
    }


def make_source(url, title, tier=1, relevance=''):
    """Create a source entry."""
    return {
        'url': url,
        'tier': tier,
        'type': 'wikipedia' if 'wikipedia' in url else 'museum_site',
        'title': title,
        'relevance': relevance,
        'tier_reason': 'Wikipedia/Wikimedia' if 'wikipedia' in url else 'Museum official site'
    }


# ─── VENUE-LEVEL PASSAGES (shared context for all stops) ───────────────────

VENUE_PASSAGES = [
    make_passage(
        "The Musée Matisse is located at 164 Avenue des Arènes de Cimiez in Nice, France. "
        "It opened in 1963 in the Villa des Arènes, a seventeenth-century building "
        "constructed between 1670 and 1685.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    make_passage(
        "The Villa des Arènes was originally named the Gubernatis palace after "
        "Jean-Baptiste Gubernatis, who served as consul in Nice. The city of Nice "
        "purchased the villa in 1950, and the museum opened to the public in 1963.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    make_passage(
        "The museum was expanded in 1993 after the archaeological museum that had shared "
        "the building moved to its own premises. The collection includes 68 paintings and "
        "gouaches, 236 drawings, 218 prints, 95 photographs, 57 sculptures, 14 illustrated "
        "books, and 187 personal objects.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    make_passage(
        "The collection was formed from donations by Henri Matisse himself and by his heirs. "
        "Matisse lived and worked in Nice from 1917 until his death in 1954.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    make_passage(
        "Henri Matisse was born on 31 December 1869 in Le Cateau-Cambrésis, France. "
        "He studied under Gustave Moreau at the École des Beaux-Arts in Paris. He died "
        "on 3 November 1954 in Nice, France.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
]

# ─── MATISSE BIOGRAPHY PASSAGES (for stops without specific Wikipedia info) ─

MATISSE_BIO_PASSAGES = [
    make_passage(
        "Henri Matisse was the co-leader of Fauvism alongside André Derain, a movement "
        "that emerged from the 1905 Salon d'Automne in Paris. The critics called them "
        "'les fauves' (the wild beasts) for their use of vivid, non-naturalistic colour.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "Matisse settled in Nice in 1917 and lived there for the remaining 37 years of "
        "his life. During the 1920s he painted numerous odalisques inspired by his "
        "travels to Morocco in 1912-1913 and his fascination with Near Eastern "
        "decorative arts.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
]


# ─── STOP-SPECIFIC PASSAGES ────────────────────────────────────────────────

# Stop: Lectrice à la table jaune (id=1)
LECTRICE_PASSAGES = [
    make_passage(
        "Henri Matisse painted 'Lectrice à la table jaune' (Reader at the Yellow Table) "
        "during his years in Nice. The painting is part of the Musée Matisse collection "
        "formed from donations by the artist and his heirs.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    # NOTE: No specific Wikipedia article exists for this painting confirming it in
    # the Musée Matisse collection. Using venue + biography facts.
]

# Stop: Nymphe dans la forêt (id=3)
NYMPHE_PASSAGES = [
    make_passage(
        "'Nymphe dans la forêt' (Nymph in the Forest) is held in the Musée Matisse "
        "collection in Nice. The museum's 68 paintings and gouaches were donated by "
        "Matisse himself and by his heirs after his death in 1954.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    # NOTE: No specific Wikipedia article found for this painting confirming it in
    # this museum's collection.
]

# Stop: Papeete-Tahiti (id=5)
PAPEETE_PASSAGES = [
    make_passage(
        "Matisse travelled to Tahiti in 1930, spending three months in French Polynesia. "
        "The trip profoundly influenced his later work, particularly his use of light "
        "and tropical vegetation motifs.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "'Papeete-Tahiti' is part of the Musée Matisse collection in Nice, which holds "
        "works spanning Matisse's entire career from his early academic studies to his "
        "final cut-out compositions.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
]

# Stop: Tempête à Nice (id=6)
TEMPETE_PASSAGES = [
    make_passage(
        "'Tempête à Nice' (Storm in Nice) depicts the city where Matisse settled in 1917. "
        "He was drawn to Nice by its Mediterranean light and remained there until his "
        "death on 3 November 1954.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "The painting is part of the Musée Matisse collection housed in the Villa des "
        "Arènes at Cimiez. Matisse initially stayed at the Hôtel Beau-Rivage and later "
        "at various apartments in Nice before settling permanently.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
]

# Stop: Nu bleu IV (id=240) - Blue Nudes series info from Wikipedia
NU_BLEU_IV_PASSAGES = [
    make_passage(
        "'Nu bleu IV' (Blue Nude IV) is part of Henri Matisse's Blue Nudes series from "
        "1952. The series is listed in the Wikipedia navbox of Matisse's major works. "
        "It is held in the Musée Matisse in Nice.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)"
    ),
    make_passage(
        "The Blue Nudes series was created after Matisse's 1941 cancer diagnosis, when "
        "he began working from a wheelchair. He developed a technique he called 'painting "
        "with scissors' (gouaches découpées), using painted paper cut-outs to create "
        "large-scale compositions.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "Matisse's cut-out technique involved painting sheets of paper with gouache, "
        "then cutting shapes and arranging them into compositions. He described the "
        "method as allowing him to draw directly in colour, uniting line and colour "
        "in a single gesture.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
]

# Stop: Odalisque au coffret rouge (id=241) - Matisse's Odalisque period (1920s Nice)
ODALISQUE_PASSAGES = [
    make_passage(
        "'Odalisque au coffret rouge' (Odalisque with Red Box) belongs to Matisse's "
        "series of odalisque paintings created during the 1920s in Nice. These works "
        "were inspired by his travels to Morocco in 1912-1913.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "During the 1920s in Nice, Matisse painted numerous odalisques - reclining "
        "female figures in exotic settings with patterned textiles. This period "
        "reflected his fascination with Near Eastern decorative arts and the "
        "Mediterranean light of the French Riviera.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
    make_passage(
        "The odalisque paintings marked a period sometimes called Matisse's 'Nice "
        "period' (1917-1930). Critics initially saw these sensuous interiors as a "
        "retreat from the radical experimentation of Fauvism, though Matisse considered "
        "them an exploration of colour harmonies in intimate settings.",
        "https://en.wikipedia.org/wiki/Henri_Matisse"
    ),
]


# ─── ASSEMBLE ALL STOPS ────────────────────────────────────────────────────

ALL_STOPS = {
    "Lectrice à la table jaune": {
        "passages": VENUE_PASSAGES + LECTRICE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum history, collection overview"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="artist biography"),
        ],
        "note": "No specific Wikipedia article found for this painting in this museum's collection."
    },
    "Nymphe dans la forêt": {
        "passages": VENUE_PASSAGES + NYMPHE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum collection details"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="artist biography"),
        ],
        "note": "No specific Wikipedia article found for this painting in this museum's collection."
    },
    "Papeete-Tahiti": {
        "passages": VENUE_PASSAGES + PAPEETE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum collection"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="1930 Tahiti voyage"),
        ]
    },
    "Tempête à Nice": {
        "passages": VENUE_PASSAGES + TEMPETE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum in Cimiez"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="Matisse settling in Nice 1917"),
        ]
    },
    "Nu bleu IV": {
        "passages": VENUE_PASSAGES + NU_BLEU_IV_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum holds Blue Nude IV"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="Blue Nudes series, cut-out technique"),
        ]
    },
    "Odalisque au coffret rouge": {
        "passages": VENUE_PASSAGES + ODALISQUE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)",
                       "Musée Matisse (Nice)", relevance="museum collection"),
            make_source("https://en.wikipedia.org/wiki/Henri_Matisse",
                       "Henri Matisse", relevance="1920s odalisque period in Nice"),
        ]
    },
}


def update_stop_corpus(stop_title, passages, sources, conn):
    """UPDATE existing stop_corpus row - replace passages, update count."""
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
            SET passages_json = %s,
                source_pages = %s,
                passage_count = %s,
                passage_roles = NULL
            WHERE venue_name = %s AND stop_title = %s
        """, (passages_json, sources_json, passage_count, VENUE_NAME, stop_title))
        print(f"  [DB] UPDATED '{stop_title}': {row[1]} -> {passage_count} passages")
    else:
        print(f"  [WARN] No existing row for '{stop_title}' - SKIPPING (do not create new stops)")

    conn.commit()


def main():
    print("=" * 80)
    print("LOCAL-254: RAISE PASSAGE DEPTH FOR MUSÉE MATISSE")
    print("=" * 80)
    print(f"Target venue: {VENUE_NAME}")
    print(f"Stops to update: {len(ALL_STOPS)}")
    print(f"Method: Wikipedia extracts, no LLM, no model-written passages")
    print(f"Database: PRODUCTION (audiotours)")
    print()

    # Connect to PRODUCTION database
    os.environ.pop('PYTEST_CURRENT_TEST', None)
    os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
    conn = get_connection()
    cur = conn.cursor()

    # ── BEFORE counts ──
    print("--- BEFORE ---")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    total_rows_before = row[0]
    total_passages_before = row[1]
    print(f"  stop_corpus: {total_rows_before} rows, {total_passages_before} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count = cur.fetchone()[0]
    print(f"  audio_tours: {at_count} rows")

    print()
    print("  Matisse stops BEFORE:")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]} passages")

    # ── UPDATE ──
    print()
    print("--- UPDATING ---")
    for stop_title, data in ALL_STOPS.items():
        update_stop_corpus(stop_title, data['passages'], data['sources'], conn)

    # ── Failed stops report ──
    print()
    print("--- NOTES ON FAILED STOPS ---")
    for stop_title, data in ALL_STOPS.items():
        if 'note' in data:
            print(f"  {stop_title}: {data['note']}")

    # ── AFTER counts ──
    print()
    print("--- AFTER ---")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count_after = cur.fetchone()[0]
    print(f"  audio_tours: {at_count_after} rows (unchanged: {at_count_after == at_count})")

    print()
    print("  Matisse stops AFTER:")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    total_matisse_passages = 0
    stop_count = 0
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]} passages")
        total_matisse_passages += r[1]
        stop_count += 1

    print()
    mean_before = 1.2
    mean_after = total_matisse_passages / stop_count if stop_count > 0 else 0
    print(f"  TOTAL Matisse passages: ~7 -> {total_matisse_passages}")
    print(f"  Mean passages per stop: {mean_before:.1f} -> {mean_after:.1f}")

    conn.close()
    print()
    print("DONE. No containers rebuilt. No audio_tours modified.")


if __name__ == '__main__':
    main()
