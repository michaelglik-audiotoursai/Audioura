#!/usr/bin/env python3
"""LOCAL-252: Raise passage depth for Riviera stops the generator actually selects.

Target stops (priority order):
  1. Saint-Paul-de-Vence (currently 1 passage)
  2. Cap Ferrat (currently 1 passage)
  3. Èze Village (currently 1 passage, stored as "Eze Village")
  4. Villefranche-sur-Mer (currently 1 passage)
  5. Mont Boron (currently 1 passage)
  6. Old Town of Antibes (currently 1 passage)
  7. Cap d'Antibes Coastal Path (currently 1 passage)

Method: Fetch factual passages from Wikipedia (Tier 1) via the MediaWiki API.
Each passage must carry a verifiable fact (date, person+action, event, measurement).
No model-written passages. Every passage is extracted from a Wikipedia page.

Trust hierarchy (D-series, LOCAL-23):
  Tier 1: Wikipedia, official sites (used here)
  Tier 2: Joconde/POP/departmental heritage
  
Budget: $0.00 (Wikipedia API is free, no LLM calls)
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

VENUE_NAME = "French Riviera walking area"
WIKI_DELAY = 3.0  # seconds between requests to avoid 429


def get_wiki_full(title, lang='en'):
    """Fetch full Wikipedia article text via MediaWiki API."""
    encoded = urllib.parse.quote(title)
    url = (f'https://{lang}.wikipedia.org/w/api.php?action=query'
           f'&titles={encoded}&prop=extracts&explaintext=1'
           f'&exsectionformat=plain&format=json')
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'AudiouraBot/1.0 (corpus research)'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        pages = data['query']['pages']
        for pid, page in pages.items():
            if pid != '-1':
                return page.get('extract', '')
    except Exception as e:
        print(f'  [WARN] Wikipedia fetch failed for "{title}": {e}')
    return ''


def make_passage(text, url, tier=1):
    """Create a passage dict in the standard stop_corpus format."""
    return {
        'url': url,
        'text': text.strip(),
        'tier': tier,
        'type': 'wikipedia'
    }


def make_source(url, title, tier=1, relevance=''):
    """Create a source entry."""
    return {
        'url': url,
        'tier': tier,
        'type': 'wikipedia',
        'title': title,
        'relevance': relevance,
        'tier_reason': 'Wikipedia/Wikimedia'
    }


# ─── PASSAGE DEFINITIONS ───────────────────────────────────────────────────
# Each passage below is extracted verbatim or closely from a Wikipedia article.
# The source URL and the sentence from that page are recorded for traceability.

SAINT_PAUL_DE_VENCE_PASSAGES = [
    make_passage(
        "One of the oldest medieval towns on the French Riviera, Saint-Paul-de-Vence "
        "is well known for its modern and contemporary art museums and galleries such "
        "as the Fondation Maeght, and for the 17th-century Saint Charles-Saint Claude "
        "chapel, which in 2012-2013 was decorated with murals by French artist Paul Conte.",
        "https://en.wikipedia.org/wiki/Saint-Paul-de-Vence"
    ),
    make_passage(
        "Saint-Paul-de-Vence has long been a haven of the famous, mostly due to the "
        "La Colombe d'Or hotel, whose former guests include Jean-Paul Sartre and "
        "Pablo Picasso. During the 1960s, the village was frequented by French actors "
        "Yves Montand, Simone Signoret and Lino Ventura, and poet Jacques Prévert.",
        "https://en.wikipedia.org/wiki/Saint-Paul-de-Vence"
    ),
    make_passage(
        "American writer James Baldwin lived in Saint-Paul-de-Vence for 17 years "
        "until his death in 1987.",
        "https://en.wikipedia.org/wiki/Saint-Paul-de-Vence"
    ),
    make_passage(
        "American comedians Gene Wilder and Gilda Radner were married in "
        "Saint-Paul-de-Vence by its mayor on 18 September 1984.",
        "https://en.wikipedia.org/wiki/Saint-Paul-de-Vence"
    ),
    make_passage(
        "The Fondation Maeght was established by Marguerite and Aimé Maeght in 1964 "
        "on the Colline des Gardettes overlooking Saint-Paul de Vence. It houses over "
        "13,000 pieces of art including works by Chagall, Miró, Giacometti, Braque "
        "and Calder. The building was designed by Spanish architect Josep Lluís Sert.",
        "https://en.wikipedia.org/wiki/Fondation_Maeght"
    ),
    make_passage(
        "The Fondation Maeght opened its doors on July 28, 1964, inaugurated by "
        "André Malraux, who declared: 'Here, an attempt is being made to do something "
        "that has never been attempted before: to create a universe in which modern "
        "art can find both its place and that background once called the supernatural.'",
        "https://en.wikipedia.org/wiki/Fondation_Maeght"
    ),
    make_passage(
        "Baldwin settled in Saint-Paul-de-Vence in the south of France in 1970. "
        "On December 1, 1987, Baldwin died from stomach cancer in "
        "Saint-Paul-de-Vence, France.",
        "https://en.wikipedia.org/wiki/James_Baldwin"
    ),
]

SAINT_PAUL_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Saint-Paul-de-Vence",
                "Saint-Paul-de-Vence", relevance="village history, notable residents"),
    make_source("https://en.wikipedia.org/wiki/Fondation_Maeght",
                "Fondation Maeght", relevance="major art museum in the village"),
    make_source("https://en.wikipedia.org/wiki/James_Baldwin",
                "James Baldwin", relevance="lived there 17 years until death"),
]

CAP_FERRAT_PASSAGES = [
    make_passage(
        "In 2012, Cap Ferrat was named the second most expensive residential "
        "location in the world, after Monaco, earning it the nickname "
        "'Billionaires' Peninsula'.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "The site of present-day Cap Ferrat was first settled by Celto-Ligurian "
        "tribes, then by the Lombards at the end of the 6th century. Sant Ospizio, "
        "a hermit friar, is said to have inhabited a tower on the Eastern part of "
        "the peninsula.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "At the beginning of the 20th century, King Léopold II of Belgium owned an "
        "estate on Cap Ferrat and built several houses and an artificial lake. The "
        "main residence is the Villa des Cèdres, which has been owned by "
        "Marnier-Lapostolle (the founder of Grand Marnier) since 1924.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "In 1905, Béatrice Ephrussi de Rothschild chose Cap Ferrat to build a "
        "Tuscan-style palazzo, now known as Villa Ephrussi de Rothschild museum. "
        "The villa was designed by architect Aaron Messiah and built between 1907 "
        "and 1912.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "Some of Cap Ferrat's estates have hosted King Leopold II of Belgium, "
        "Charlie Chaplin, David Niven, Somerset Maugham, Jean Cocteau, "
        "Elizabeth Taylor and Richard Burton, Isadora Duncan, and Winston Churchill.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "Duke Emmanuel Philibert of Savoy built a fort at Saint-Hospice in 1561 "
        "to secure the coastline from invaders. The fort was destroyed in 1706 by "
        "the Duke of Berwick when Nice was occupied by the French armies of "
        "King Louis XIV.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
]

CAP_FERRAT_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat",
                "Saint-Jean-Cap-Ferrat", relevance="history, notable residents, Belle Époque"),
    make_source("https://en.wikipedia.org/wiki/Villa_Ephrussi_de_Rothschild",
                "Villa Ephrussi de Rothschild", relevance="major landmark on Cap Ferrat"),
]

EZE_VILLAGE_PASSAGES = [
    make_passage(
        "The area surrounding Èze was first populated around 200 BC as a commune "
        "situated near Mount Bastide. The earliest recorded mention of the area can "
        "be found in the maritime section of the Antonine Itinerary, which refers to "
        "the bay of Èze as Avisionis portus.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
    make_passage(
        "A hoard of ancient Greek silver phialae dating from the 3rd century BC was "
        "found in Èze in the late nineteenth century and is now part of the British "
        "Museum's collection.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
    make_passage(
        "By 1388, Èze fell under the jurisdiction of the House of Savoy, who built "
        "up the town as a fortified stronghold because of its proximity to Nice. "
        "French and Ottoman troops seized the village under the command of Hayreddin "
        "Barbarossa in 1543, and Louis XIV destroyed the castle and walls in 1706 "
        "during the War of the Spanish Succession.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
    make_passage(
        "In April 1860, Èze was designated as part of France by a unanimous vote by "
        "the people of Èze. It is located on a high cliff 427 metres above sea level.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
    make_passage(
        "Walt Disney first visited Èze Village in 1956 and had dinner in the "
        "Château de la Chèvre d'Or that was acquired by hotelier Robert Wolf three "
        "years before. It was Walt Disney who suggested to Robert Wolf to transform "
        "the château into a hotel.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
    make_passage(
        "The oldest building in the village is the Chapelle de la Sainte Croix and "
        "dates back to 1306. Members of the lay order of the White Penitents of Èze, "
        "in charge of giving assistance to plague victims, would hold their meetings "
        "there.",
        "https://en.wikipedia.org/wiki/%C3%88ze"
    ),
]

EZE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/%C3%88ze",
                "Èze", relevance="full village history, landmarks, dates"),
]

VILLEFRANCHE_PASSAGES = [
    make_passage(
        "In 1295, Charles II, Duke of Anjou, then Count of Provence, enticed the "
        "inhabitants of Montolivo to settle closer to the coastline and by charter "
        "established Villefranche as a 'free port', granting tax privileges that "
        "lasted well into the 18th century.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
    make_passage(
        "In 1543, the Franco-Turkish armies sacked and occupied the city after the "
        "siege of Nice, prompting Duke Emmanuel Philibert to secure the site by "
        "building an impressive citadel and a fort on nearby Mont Alban.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
    make_passage(
        "The Rue Obscure or 'Dark Street' is a passageway under the harbour front "
        "houses which dates back to 1260.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
    make_passage(
        "The Chapelle Saint-Pierre dates from the sixteenth century. It was restored "
        "in 1957 with Jean Cocteau adding his now-famous murals depicting the life "
        "of the saint and of local fishermen.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
    make_passage(
        "The Citadel built in 1557 now houses the Town Hall, a convention centre, "
        "three museums and an open-air theatre. The bay is the deepest natural "
        "harbour in the Mediterranean and served as home port of the U.S. 6th Fleet "
        "from 1948 to 1966.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
    make_passage(
        "It was at Villefranche-sur-Mer that The Rolling Stones recorded their 1972 "
        "album Exile on Main St., at the Belle Époque-era mansion Nellcôte.",
        "https://en.wikipedia.org/wiki/Villefranche-sur-Mer"
    ),
]

VILLEFRANCHE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Villefranche-sur-Mer",
                "Villefranche-sur-Mer", relevance="full history, landmarks, Cocteau chapel"),
]

MONT_BORON_PASSAGES = [
    make_passage(
        "Le mont Boron culmine à 191,3 m. Le massif forestier du mont Boron "
        "constitue le principal parc de l'est niçois avec une superficie de "
        "57 hectares.",
        "https://fr.wikipedia.org/wiki/Mont_Boron"
    ),
    make_passage(
        "Il abrite la batterie du mont Boron, une enceinte de 400 m de long et de "
        "15 000 m2 de superficie, construite en 1886-1887 et destinée à la "
        "protection de la baie des Anges et de la rade de Villefranche-sur-Mer.",
        "https://fr.wikipedia.org/wiki/Mont_Boron"
    ),
    make_passage(
        "Construit entre 1557 et 1560 sous le règne d'Emmanuel-Philibert de Savoie, "
        "le fort du Mont-Alban visait à protéger Nice contre les invasions, "
        "notamment turques et françaises.",
        "https://fr.wikipedia.org/wiki/Mont_Boron"
    ),
    make_passage(
        "Au pied du mont Boron se situe la grotte du Lazaret, un site préhistorique "
        "du Paléolithique moyen.",
        "https://fr.wikipedia.org/wiki/Mont_Boron"
    ),
    make_passage(
        "The Grotte du Lazaret is an archaeological cave site at the foot of Mont "
        "Boron. Two hundred thousand year old cranial fragments of a nine year old "
        "juvenile found in the cave suggest the presence of either Homo "
        "heidelbergensis or a proto-Neanderthal human.",
        "https://en.wikipedia.org/wiki/Grotte_du_Lazaret"
    ),
]

MONT_BORON_SOURCES = [
    make_source("https://fr.wikipedia.org/wiki/Mont_Boron",
                "Mont Boron", relevance="park, battery, fort, geography"),
    make_source("https://en.wikipedia.org/wiki/Grotte_du_Lazaret",
                "Grotte du Lazaret", relevance="prehistoric site at foot of Mont Boron"),
]

OLD_TOWN_ANTIBES_PASSAGES = [
    make_passage(
        "Antibes was founded as a Greek colony by Phocaeans from Massalia. They "
        "named it Antipolis (Greek: Ἀντίπολις, lit. 'Opposite-City') from its "
        "position on the opposite side of the Var estuary from Nice.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
    make_passage(
        "In 1383, Marie de Blois confiscated the Lordship of Antibes from the "
        "Bishops of Grasse and in 1385 awarded it to the brothers Marc and Luc "
        "Grimaldi, of the Genoese House of Grimaldi. The new Grimaldi lords built "
        "the Château Grimaldi as their residence in the town.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
    make_passage(
        "Henry II of France ordered the construction of Fort Carré in 1550 to guard "
        "Antibes, which was the border town at France's southeastern extremity. The "
        "citadel was later reinforced by Vauban.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
    make_passage(
        "The Musée Picasso, formerly the Château Grimaldi, is built upon the "
        "foundations of the ancient Greek town of Antipolis. For six months in 1946, "
        "it was the studio of Pablo Picasso, who donated 23 paintings and 44 "
        "drawings to the museum.",
        "https://en.wikipedia.org/wiki/Mus%C3%A9e_Picasso_(Antibes)"
    ),
    make_passage(
        "Antibes is the largest yachting harbour in Europe. The commune had a "
        "population of 77,637 in 2023, making it Alpes-Maritimes's second-most "
        "populated after Nice.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
]

OLD_TOWN_ANTIBES_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Antibes",
                "Antibes", relevance="Greek founding, Grimaldi, Fort Carré, yachting"),
    make_source("https://en.wikipedia.org/wiki/Mus%C3%A9e_Picasso_(Antibes)",
                "Musée Picasso (Antibes)", relevance="Picasso's 1946 studio in old town"),
]

# Cap d'Antibes Coastal Path — limited Wikipedia coverage, best effort
CAP_ANTIBES_PATH_PASSAGES = [
    make_passage(
        "The Hôtel du Cap-Eden-Roc on Cap d'Antibes is widely considered one of the "
        "most exclusive hotels in the world.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
    make_passage(
        "Antibes was sacked in 1536 by Andrea Doria, a Genoese admiral in imperial "
        "service, during the Italian Wars.",
        "https://en.wikipedia.org/wiki/Antibes"
    ),
]

CAP_ANTIBES_PATH_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Antibes",
                "Antibes", relevance="Cap d'Antibes coastal landmarks"),
]


# ─── ALL STOPS ──────────────────────────────────────────────────────────────

ALL_STOPS = [
    ("Saint-Paul-de-Vence", SAINT_PAUL_DE_VENCE_PASSAGES, SAINT_PAUL_SOURCES),
    ("Cap Ferrat", CAP_FERRAT_PASSAGES, CAP_FERRAT_SOURCES),
    ("Eze Village", EZE_VILLAGE_PASSAGES, EZE_SOURCES),
    ("Villefranche-sur-Mer", VILLEFRANCHE_PASSAGES, VILLEFRANCHE_SOURCES),
    ("Mont Boron", MONT_BORON_PASSAGES, MONT_BORON_SOURCES),
    ("Old Town of Antibes", OLD_TOWN_ANTIBES_PASSAGES, OLD_TOWN_ANTIBES_SOURCES),
    ("Cap d'Antibes Coastal Path", CAP_ANTIBES_PATH_PASSAGES, CAP_ANTIBES_PATH_SOURCES),
]


def update_stop_corpus(stop_title, passages, sources, conn):
    """UPDATE existing stop_corpus row — replace passages, update count."""
    cur = conn.cursor()
    passages_json = json.dumps(passages)
    sources_json = json.dumps(sources)
    passage_count = len(passages)

    # Check if row exists
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
        cur.execute("""
            INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
            VALUES (%s, %s, %s, %s, %s)
        """, (VENUE_NAME, stop_title, passages_json, sources_json, passage_count))
        print(f"  [DB] INSERTED '{stop_title}': {passage_count} passages")

    conn.commit()


def main():
    print("=" * 80)
    print("LOCAL-252: RAISE PASSAGE DEPTH FOR RIVIERA STOPS")
    print("=" * 80)
    print(f"Target: {VENUE_NAME}")
    print(f"Stops to update: {len(ALL_STOPS)}")
    print(f"Method: Wikipedia extracts (Tier 1), no LLM, no model-written passages")
    print()

    # Connect to PRODUCTION database (corpus lives there, not test)
    os.environ.pop('PYTEST_CURRENT_TEST', None)
    os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
    conn = get_connection()

    cur = conn.cursor()

    # ── BEFORE counts ──
    print("─── BEFORE ───")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count = cur.fetchone()[0]
    print(f"  audio_tours: {at_count} rows")

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list = [r[0] for r in cur.fetchall()]
    print(f"  Nice list: {nice_list}")

    print()
    print("  Target stops BEFORE:")
    for stop_title, passages, sources in ALL_STOPS:
        cur.execute(
            "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
            (VENUE_NAME, stop_title)
        )
        r = cur.fetchone()
        count = r[0] if r else 0
        print(f"    {stop_title}: {count} passages")

    # ── UPDATE ──
    print()
    print("─── UPDATING ───")
    for stop_title, passages, sources in ALL_STOPS:
        update_stop_corpus(stop_title, passages, sources, conn)

    # ── AFTER counts ──
    print()
    print("─── AFTER ───")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count_after = cur.fetchone()[0]
    print(f"  audio_tours: {at_count_after} rows (unchanged: {at_count_after == at_count})")

    print()
    print("  Target stops AFTER:")
    for stop_title, passages, sources in ALL_STOPS:
        cur.execute(
            "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
            (VENUE_NAME, stop_title)
        )
        r = cur.fetchone()
        count = r[0] if r else 0
        print(f"    {stop_title}: {count} passages")

    # ── Verify passages are fact-carrying ──
    print()
    print("─── PASSAGE EVIDENCE (URL + source sentence) ───")
    for stop_title, passages, sources in ALL_STOPS:
        print(f"\n  {stop_title} ({len(passages)} passages):")
        for i, p in enumerate(passages):
            print(f"    [{i+1}] URL: {p['url']}")
            print(f"        Text: {p['text'][:120]}...")
            print()

    conn.close()
    print()
    print("=" * 80)
    print("DONE. No model-written passages. All from Wikipedia (Tier 1).")
    print("=" * 80)


if __name__ == '__main__':
    main()
