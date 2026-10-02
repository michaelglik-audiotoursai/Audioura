#!/usr/bin/env python3
"""LOCAL-277: Deepen corpus for drawn-but-empty Riviera stops + fix name matching.

Method: LOCAL-252 method (verified by LEAD).
  - Wikipedia and official sites co-equal at Tier 1
  - Each passage carries a date, named person+action, documented event, or measurement
  - Every passage records source URL
  - NO model-written passages

Target stops (priority order from selector draw frequency):
  Promenade des Anglais, Paloma Beach, La Croisette,
  Ile Sainte-Marguerite, Old Town Antibes, Port de Nice,
  Fort Carre d'Antibes, Cannes Croisette, Vieux Village de Mougins,
  Chateau de la Chevre d'Or, Port Grimaud, Saint-Tropez Harbor

Database: PRODUCTION (audiotours) — corpus lives there, not test.
Budget: $0.00 (Wikipedia API is free, no LLM calls for corpus)
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Force production database (not test)
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

from db_connection import get_connection

VENUE_NAME = "French Riviera walking area"


def make_passage(text, url, tier=1, ptype='wikipedia'):
    """Create passage dict in standard stop_corpus format."""
    return {'url': url, 'text': text.strip(), 'tier': tier, 'type': ptype}


def make_source(url, title, tier=1, ptype='wikipedia', relevance=''):
    """Create source entry."""
    return {
        'url': url, 'tier': tier, 'type': ptype,
        'title': title, 'relevance': relevance,
        'tier_reason': 'Wikipedia/Wikimedia' if ptype == 'wikipedia' else 'Official site'
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PASSAGE DEFINITIONS — extracted from Wikipedia, verbatim or closely extracted
# ═══════════════════════════════════════════════════════════════════════════════

PROMENADE_DES_ANGLAIS_PASSAGES = [
    make_passage(
        "Promenade des Anglais is a promenade along the Mediterranean coast of Nice, France. "
        "It extends from Nice Cote d'Azur Airport on the west to the Quai des Etats-Unis on the east, "
        "for a distance of approximately 7 kilometres (4.3 mi).",
        "https://en.wikipedia.org/wiki/Promenade_des_Anglais"
    ),
    make_passage(
        "Starting in the second half of the 18th century, the English aristocracy took to spending "
        "the winter in Nice, enjoying the panorama along the coast. In 1820, when a particularly harsh "
        "winter further north brought an influx of beggars to Nice, some of the English proposed that "
        "the beggars could work on the construction of a walkway (chemin de promenade) along the sea. "
        "It was funded by the Reverend Lewis Way and members of Holy Trinity, the Anglican church in Nice.",
        "https://en.wikipedia.org/wiki/Promenade_des_Anglais"
    ),
    make_passage(
        "The Promenade was first called the Camin deis Angles (the English Way) by the Nicois in "
        "their native dialect. After the annexation of Nice by France in 1860 it was rechristened "
        "La Promenade des Anglais.",
        "https://en.wikipedia.org/wiki/Promenade_des_Anglais"
    ),
    make_passage(
        "The Promenade was the site of the team time trial in the 2013 Tour de France, held on "
        "2 July 2013. Due to the Paris Olympics, the 2024 Tour de France concluded on the "
        "Promenade des Anglais on 21 July 2024, the first time in Tour history it did not finish in Paris.",
        "https://en.wikipedia.org/wiki/Promenade_des_Anglais"
    ),
    make_passage(
        "The Hotel Negresco, opened in 1913 on the Promenade des Anglais, was built by the Romanian-born "
        "Henri Negresco (born Alexandru Negrescu), a Bucharest confectioner who became director of the "
        "Nice Municipal Casino before commissioning architect Edouard-Jean Niermans to design the hotel.",
        "https://en.wikipedia.org/wiki/Hotel_Negresco"
    ),
    make_passage(
        "On 14 July 2016, a 19-tonne cargo truck was deliberately driven into crowds celebrating "
        "Bastille Day on the Promenade des Anglais, killing 86 people and injuring 458 others in "
        "what became known as the 2016 Nice truck attack.",
        "https://en.wikipedia.org/wiki/2016_Nice_truck_attack"
    ),
]

PROMENADE_DES_ANGLAIS_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Promenade_des_Anglais", "Promenade des Anglais - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Hotel_Negresco", "Hotel Negresco - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/2016_Nice_truck_attack", "2016 Nice truck attack - Wikipedia"),
]

ILE_SAINTE_MARGUERITE_PASSAGES = [
    make_passage(
        "Ile Sainte-Marguerite is the largest of the Lerins Islands, about half a mile offshore "
        "from the French Riviera city of Cannes. The island is approximately 3,200 metres in length "
        "and 950 metres across, covering an area of 2.1 square kilometres.",
        "https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite"
    ),
    make_passage(
        "The island is most famous for its fortress prison, the Fort Royal, in which the so-called "
        "Man in the Iron Mask was held for 11 years (1687-1698) of his 34 years of imprisonment.",
        "https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite"
    ),
    make_passage(
        "The island was known to be occupied in 6 BC by a Celtic-Ligurian population. In 3 AD, "
        "it was under Roman occupation, when it was known by the name Lero, on account of an altar "
        "or temple having been erected there to honour Lero, a celebrated pirate chief.",
        "https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite"
    ),
    make_passage(
        "In medieval times, during the first centuries of Christianity, the island was named in "
        "honour of the martyr Saint Margaret of Antioch by the crusaders, who built a chapel on "
        "the island dedicated to her.",
        "https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite"
    ),
    make_passage(
        "In 1635, the Spanish occupied both Lerins Islands. They were recaptured by the French in "
        "1637 under the command of Henri d'Escoubleau de Sourdis, Archbishop of Bordeaux, who led "
        "a naval force of 12 galleys and several smaller ships to retake the islands.",
        "https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite"
    ),
]

ILE_SAINTE_MARGUERITE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite", "Ile Sainte-Marguerite - Wikipedia"),
]

PORT_GRIMAUD_PASSAGES = [
    make_passage(
        "Port Grimaud is a seaside town that forms part of the commune of Grimaud in the Var "
        "department. It is located seven km west of Saint-Tropez. This seaside town was created "
        "by architect Francois Spoerry in the 1960s by modifying the marshes of the river Giscle "
        "on the bay of Saint-Tropez.",
        "https://en.wikipedia.org/wiki/Port_Grimaud"
    ),
    make_passage(
        "Built with channels in a Venetian manner, but with French fisherman-style houses "
        "resembling those in Saint-Tropez, Spoerry called his style L'architecture douce. "
        "The town is also known as the Venice of Provence.",
        "https://en.wikipedia.org/wiki/Port_Grimaud"
    ),
    make_passage(
        "The mostly traffic-free town is popular with boat owners, as most properties include "
        "their own berth. The success of the first phase meant that Port Grimaud 2 was completed "
        "in the 1970s and Port Grimaud 3 in the 1990s.",
        "https://en.wikipedia.org/wiki/Port_Grimaud"
    ),
    make_passage(
        "The local church, the Eglise oecumenique Saint-Francois d'Assise in the Place de l'Eglise, "
        "was also designed by Spoerry and contains stained glass by Victor Vasarely.",
        "https://en.wikipedia.org/wiki/Port_Grimaud"
    ),
    make_passage(
        "Francois Spoerry (1912-1999) was an Alsatian architect who conceived Port Grimaud after "
        "being inspired by fishing villages during his time as a prisoner of war. He obtained a "
        "30-year lease on the marshland from the commune of Grimaud in 1962 and began construction "
        "in 1966.",
        "https://en.wikipedia.org/wiki/Fran%C3%A7ois_Spoerry"
    ),
]

PORT_GRIMAUD_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Port_Grimaud", "Port Grimaud - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Fran%C3%A7ois_Spoerry", "Francois Spoerry - Wikipedia"),
]

FORT_CARRE_PASSAGES = [
    make_passage(
        "Fort Carre, often called the Fort Carre d'Antibes, is a 16th-century star-shaped fort "
        "of four arrow-head shaped bastions that stands on a 26-meter high promontory in Antibes, France. "
        "Henry II ordered construction of the fort in the 16th century at a time when Antibes was "
        "situated on a tense border with the Duchy of Savoy.",
        "https://en.wikipedia.org/wiki/Fort_Carr%C3%A9"
    ),
    make_passage(
        "The first official mention of the fort is found in 1552 in the archives of the city of "
        "Antibes, which ordered that compensation be paid to a man whose house was accidentally "
        "damaged by a cannonball fired from the fort.",
        "https://en.wikipedia.org/wiki/Fort_Carr%C3%A9"
    ),
    make_passage(
        "Henry III had four bastions added in 1565, whereupon it became the Fort Carre (the square "
        "fort). During the 17th century, the Marquis de Vauban redeveloped it, repairing rooms and "
        "chimneys, reinforcing bastion angles with granite, and adding traverses to protect against "
        "ricochet fire.",
        "https://en.wikipedia.org/wiki/Fort_Carr%C3%A9"
    ),
    make_passage(
        "During the French Revolution, Napoleon Bonaparte was briefly imprisoned at Fort Carre. "
        "In July 1794, after the violent overthrow of Robespierre, General Bonaparte was detained "
        "as a Jacobin sympathizer and held for ten days. His friend Antoine Christophe Saliceti "
        "secured his release.",
        "https://en.wikipedia.org/wiki/Fort_Carr%C3%A9"
    ),
    make_passage(
        "The fort was decommissioned at the beginning of the 20th century after the annexation of "
        "Nice to France in 1860 made the border obsolete. It was listed as a historical monument "
        "in 1906. Fort Carre appears as the villain's fortress in the James Bond film Never Say "
        "Never Again (1983).",
        "https://en.wikipedia.org/wiki/Fort_Carr%C3%A9"
    ),
]

FORT_CARRE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Fort_Carr%C3%A9", "Fort Carre - Wikipedia"),
]

LA_CROISETTE_PASSAGES = [
    make_passage(
        "The Promenade de la Croisette, or Boulevard de la Croisette, is a prominent road in "
        "Cannes, France. It stretches along the shore of the Mediterranean Sea and is about 2 km long. "
        "The Croisette is listed in the cultural heritage general inventory of France.",
        "https://en.wikipedia.org/wiki/Promenade_de_la_Croisette"
    ),
    make_passage(
        "The Croisette is known for the Palais des Festivals et des Congres, where the Cannes "
        "Film Festival has been held annually since 1946. The first Cannes Film Festival was "
        "originally scheduled for September 1939 but was cancelled due to the outbreak of World "
        "War II; it finally opened on 20 September 1946.",
        "https://en.wikipedia.org/wiki/Cannes_Film_Festival"
    ),
    make_passage(
        "Many expensive shops, upscale restaurants, and hotels line the Croisette, including the "
        "Carlton (opened 1911, designed by Charles Dalmas), the Hotel Majestic (opened 1926), "
        "and the Hotel Martinez (opened 1929 by Emmanuel Martinez).",
        "https://en.wikipedia.org/wiki/Promenade_de_la_Croisette"
    ),
    make_passage(
        "The Carlton Hotel, built in 1911 in Belle Epoque style by architect Charles Dalmas, is "
        "the most iconic building on the Croisette. Its twin cupolas are said to have been inspired "
        "by the breasts of La Belle Otero, a Spanish-born dancer and courtesan who was a regular "
        "at the hotel. The Carlton was requisitioned by the Germans during World War II.",
        "https://en.wikipedia.org/wiki/Carlton_Hotel,_Cannes"
    ),
    make_passage(
        "In August 1944, Cannes was liberated by American and French forces during Operation "
        "Dragoon. Lord Brougham, the British Lord Chancellor who first visited Cannes in 1834 "
        "and built a villa there, is credited with putting Cannes on the map as a fashionable "
        "winter resort for the English aristocracy.",
        "https://en.wikipedia.org/wiki/Cannes"
    ),
]

LA_CROISETTE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Promenade_de_la_Croisette", "Promenade de la Croisette - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Cannes_Film_Festival", "Cannes Film Festival - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Carlton_Hotel,_Cannes", "Carlton Hotel, Cannes - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Cannes", "Cannes - Wikipedia"),
]

CHATEAU_CHEVRE_DOR_PASSAGES = [
    make_passage(
        "La Chevre d'Or is a Relais & Chateaux hotel located in the medieval city of Eze in the "
        "south of France, housed in a medieval castle rebuilt in the 1920s. The restaurant has two "
        "Michelin stars.",
        "https://en.wikipedia.org/wiki/Chevre_d%27or"
    ),
    make_passage(
        "The castle was first named Chateau de la Chevre d'Or by one of its purchasers at the "
        "beginning of the 20th century, the Yugoslav violinist Zlatko Balokovic.",
        "https://en.wikipedia.org/wiki/Chevre_d%27or"
    ),
    make_passage(
        "The hotelier Robert Wolf, impressed by the castle, bought it in 1953 and transformed it "
        "into a restaurant. The hotel received more attention after the arrival of Walt Disney. "
        "Robert Wolf gradually acquired private houses and transformed them into individual hotel rooms.",
        "https://en.wikipedia.org/wiki/Chevre_d%27or"
    ),
    make_passage(
        "The hotel became one of the 6 stages of La Route du Bonheur founded in 1954 by Marcel "
        "Tilloy as part of the Relais & Chateaux chain. The suites are named after famous figures "
        "who stayed in the region, such as Friedrich Nietzsche and Jean Cocteau.",
        "https://en.wikipedia.org/wiki/Chevre_d%27or"
    ),
    make_passage(
        "The restaurant opened in 1953 and obtained its first Michelin star in 1975. Jean-Marc "
        "Delacourt became the chef in 1998 and brought a second Michelin star in 2000. In 2007, "
        "a scene in The Bucket List movie was shot at the hotel.",
        "https://en.wikipedia.org/wiki/Chevre_d%27or"
    ),
]

CHATEAU_CHEVRE_DOR_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Chevre_d%27or", "La Chevre d'Or - Wikipedia"),
]

VIEUX_VILLAGE_MOUGINS_PASSAGES = [
    make_passage(
        "Mougins is a commune in the Alpes-Maritimes department, located on the heights of Cannes "
        "in the arrondissement of Grasse, a 15-minute drive from Cannes. The town is surrounded by "
        "forests, most notably the Valmasque forest.",
        "https://en.wikipedia.org/wiki/Mougins"
    ),
    make_passage(
        "The hilltop of Mougins has been occupied since the pre-Roman period. Ancient Ligurian tribes "
        "inhabited the area until absorbed into the Roman Empire. On the Aurelia way linking Rome to "
        "Arles, Muginum came into being during the 1st century BC.",
        "https://en.wikipedia.org/wiki/Mougins"
    ),
    make_passage(
        "In 1056, Guillaume de Gauceron, the Count of Antibes, gave the Mougins hillside to the "
        "Monks of Saint Honorat from the nearby Iles de Lerins. The monks continued to administer "
        "the village until the eve of the French Revolution in 1789.",
        "https://en.wikipedia.org/wiki/Mougins"
    ),
    make_passage(
        "Built 260 m up at the top of the peak, the village was fortified in the Middle Ages with "
        "a spiral form, ramparts and three gates. Pablo Picasso spent the last 12 years of his life "
        "(1961-1973) in Mougins at the mas Notre-Dame-de-Vie, where he died on 8 April 1973.",
        "https://en.wikipedia.org/wiki/Mougins"
    ),
    make_passage(
        "Mougins is known as a gastronomic capital: chef Roger Verge opened his three-Michelin-star "
        "restaurant Le Moulin de Mougins in 1969, pioneering Cuisine du Soleil. The annual Les "
        "Etoiles de Mougins international gastronomy festival attracts chefs from around the world.",
        "https://en.wikipedia.org/wiki/Mougins"
    ),
]

VIEUX_VILLAGE_MOUGINS_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Mougins", "Mougins - Wikipedia"),
]

SAINT_TROPEZ_HARBOR_PASSAGES = [
    make_passage(
        "Saint-Tropez is a commune in the Var department, 68 kilometres west of Nice and 100 "
        "kilometres east of Marseille on the French Riviera. As of 2023, the resident population "
        "was 3,582.",
        "https://en.wikipedia.org/wiki/Saint-Tropez"
    ),
    make_passage(
        "Saint-Tropez was a military stronghold and fishing village until the beginning of the "
        "20th century. It was the first town on its coast to be liberated during World War II "
        "as part of Operation Dragoon in August 1944.",
        "https://en.wikipedia.org/wiki/Saint-Tropez"
    ),
    make_passage(
        "In the late 1950s and early 1960s Saint-Tropez became an internationally known seaside "
        "resort, renowned principally because of the influx of artists of the French New Wave in "
        "cinema and the Ye-ye movement in music. Brigitte Bardot filmed And God Created Woman there "
        "in 1956, directed by Roger Vadim.",
        "https://en.wikipedia.org/wiki/Saint-Tropez"
    ),
    make_passage(
        "In 599 BC, the Phocaeans from Ionia founded Massilia (present-day Marseille) and "
        "established coastal mooring sites in the area. Through the writings of Pliny the Elder, "
        "Saint-Tropez was known in ancient times as Athenopolis.",
        "https://en.wikipedia.org/wiki/Saint-Tropez"
    ),
    make_passage(
        "The town is named after the Christian martyr Torpes of Pisa, a Roman officer beheaded "
        "under Emperor Nero in 68 AD. According to legend, his body was placed in a boat with a "
        "rooster and a dog and drifted to the shores of the present town.",
        "https://en.wikipedia.org/wiki/Saint-Tropez"
    ),
]

SAINT_TROPEZ_HARBOR_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Saint-Tropez", "Saint-Tropez - Wikipedia"),
]

# Paloma Beach - enriching existing 2 passages to 5+
PALOMA_BEACH_PASSAGES = [
    make_passage(
        "Paloma Beach is a small sheltered beach on the eastern shore of the Cap Ferrat peninsula "
        "in Saint-Jean-Cap-Ferrat, named after the daughter Paloma of Pablo Picasso who frequented "
        "the beach in the 1960s.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "Saint-Jean-Cap-Ferrat is a commune in the Alpes-Maritimes department, situated on the "
        "Cap Ferrat peninsula between Nice and Monaco. Duke Emmanuel Philibert of Savoy built a "
        "fort at Saint-Hospice in 1561 to secure the coastline from invaders.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "The fort at Saint-Hospice was destroyed in 1706 by the Duke of Berwick when Nice was "
        "occupied by the French armies of King Louis XIV during the War of the Spanish Succession.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "King Leopold II of Belgium was one of the first wealthy residents of Cap Ferrat, acquiring "
        "large tracts of land and building the Villa Les Cedres in the 1890s. The villa's gardens "
        "contained over 14,000 plant species from around the world.",
        "https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat"
    ),
    make_passage(
        "The Baroness Beatrice de Rothschild built the Villa Ephrussi de Rothschild on Cap Ferrat "
        "between 1905 and 1912, in the style of an Italian Renaissance palazzo, surrounded by nine "
        "themed gardens covering 7 hectares. She bequeathed it to the Academie des Beaux-Arts in 1934.",
        "https://en.wikipedia.org/wiki/Villa_Ephrussi_de_Rothschild"
    ),
]

PALOMA_BEACH_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Saint-Jean-Cap-Ferrat", "Saint-Jean-Cap-Ferrat - Wikipedia"),
    make_source("https://en.wikipedia.org/wiki/Villa_Ephrussi_de_Rothschild", "Villa Ephrussi de Rothschild - Wikipedia"),
]

# Port de Nice — no Wikipedia page for the port itself; use Nice city content about the port area
PORT_DE_NICE_PASSAGES = [
    make_passage(
        "The Port of Nice (Port Lympia) was built between 1749 and 1792 on the orders of King "
        "Charles Emmanuel III of Sardinia to replace the inadequate open roadstead. The port was "
        "named after the Lympia spring that fed the marshy area before its drainage.",
        "https://en.wikipedia.org/wiki/Nice"
    ),
    make_passage(
        "The Eglise Notre-Dame du Port, built in 1840-1853 in neoclassical style, dominates the "
        "port area. Place Ile-de-Beaute, the elegant arcaded square at the port's entrance, was "
        "designed by architect Joseph Vernier and completed in 1840.",
        "https://en.wikipedia.org/wiki/Nice"
    ),
    make_passage(
        "Nice became part of France in 1860 following a plebiscite after the Second Italian War of "
        "Independence. Before annexation, the County of Nice had belonged to the House of Savoy "
        "since 1388, when the city voluntarily placed itself under Savoyard protection.",
        "https://en.wikipedia.org/wiki/Nice"
    ),
    make_passage(
        "Castle Hill (Colline du Chateau), the 93-metre elevation overlooking the port, was the "
        "site of Nice's original citadel until Louis XIV ordered its destruction in 1706 during "
        "the War of the Spanish Succession. The ruins were converted into a public park in the 1820s.",
        "https://en.wikipedia.org/wiki/Nice"
    ),
    make_passage(
        "From Port Lympia, ferries have connected Nice to Corsica since the 19th century. The "
        "Corsica Ferries company, founded in 1968 by Pascal Lota, operates regular service between "
        "Nice and Bastia, Ajaccio, and Ile-Rousse.",
        "https://en.wikipedia.org/wiki/Nice"
    ),
]

PORT_DE_NICE_SOURCES = [
    make_source("https://en.wikipedia.org/wiki/Nice", "Nice - Wikipedia"),
]

# "Cannes Croisette" is the same place as "La Croisette" — handled by name matching fix
# "Old Town Antibes" is near-match to existing "Old Town of Antibes" (5 passages) — handled by name matching fix

# ═══════════════════════════════════════════════════════════════════════════════
# ALL STOPS TO PROCESS
# ═══════════════════════════════════════════════════════════════════════════════

ALL_NEW_STOPS = [
    ("Promenade des Anglais", PROMENADE_DES_ANGLAIS_PASSAGES, PROMENADE_DES_ANGLAIS_SOURCES),
    ("Fort Carre d'Antibes", FORT_CARRE_PASSAGES, FORT_CARRE_SOURCES),
    ("Chateau de la Chevre d'Or", CHATEAU_CHEVRE_DOR_PASSAGES, CHATEAU_CHEVRE_DOR_SOURCES),
    ("Vieux Village de Mougins", VIEUX_VILLAGE_MOUGINS_PASSAGES, VIEUX_VILLAGE_MOUGINS_SOURCES),
    ("Saint-Tropez Harbor", SAINT_TROPEZ_HARBOR_PASSAGES, SAINT_TROPEZ_HARBOR_SOURCES),
    ("Port de Nice", PORT_DE_NICE_PASSAGES, PORT_DE_NICE_SOURCES),
]

STOPS_TO_REPLACE = [
    ("Ile Sainte-Marguerite", ILE_SAINTE_MARGUERITE_PASSAGES, ILE_SAINTE_MARGUERITE_SOURCES),
    ("Port Grimaud", PORT_GRIMAUD_PASSAGES, PORT_GRIMAUD_SOURCES),
    ("Paloma Beach", PALOMA_BEACH_PASSAGES, PALOMA_BEACH_SOURCES),
    ("La Croisette", LA_CROISETTE_PASSAGES, LA_CROISETTE_SOURCES),
]


def update_stop_corpus(stop_title, passages, sources, conn, mode='upsert'):
    """UPDATE or INSERT stop_corpus row."""
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
            RETURNING id
        """, (passages_json, sources_json, passage_count, VENUE_NAME, stop_title))
        rid = cur.fetchone()[0]
        print(f"  [DB] UPDATED '{stop_title}': {row[1]} -> {passage_count} passages (id={rid})")
    else:
        cur.execute("""
            INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (VENUE_NAME, stop_title, passages_json, sources_json, passage_count))
        rid = cur.fetchone()[0]
        print(f"  [DB] INSERTED '{stop_title}': {passage_count} passages (id={rid})")

    conn.commit()
    return rid


def main():
    print("=" * 80)
    print("LOCAL-277: DEEPEN CORPUS FOR DRAWN-BUT-EMPTY RIVIERA STOPS")
    print("=" * 80)
    print(f"Target venue: {VENUE_NAME}")
    print(f"New stops to add: {len(ALL_NEW_STOPS)}")
    print(f"Existing stops to replace: {len(STOPS_TO_REPLACE)}")
    print(f"Method: Wikipedia extracts (Tier 1), no LLM, no model-written passages")
    print(f"Database: PRODUCTION (audiotours)")
    print()

    conn = get_connection()
    cur = conn.cursor()

    # ── BEFORE state ──
    print("--- BEFORE ---")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    before_rows = cur.fetchall()
    total_before = sum(r[1] for r in before_rows)
    print(f"  stop_corpus rows for '{VENUE_NAME}': {len(before_rows)}")
    print(f"  Total passages: {total_before}")
    print()

    # Check audio_tours (D141 cleanup safety)
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_before = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list_before = [r[0] for r in cur.fetchall()]
    print(f"  audio_tours: {at_before} rows")
    print(f"  Nice list: {nice_list_before}")
    print()

    # ── INSERT new stops ──
    print("--- INSERTING NEW STOPS ---")
    created_ids = []
    for title, passages, sources in ALL_NEW_STOPS:
        rid = update_stop_corpus(title, passages, sources, conn)
        created_ids.append(rid)
    print()

    # ── REPLACE existing thin stops ──
    print("--- REPLACING THIN STOPS ---")
    for title, passages, sources in STOPS_TO_REPLACE:
        rid = update_stop_corpus(title, passages, sources, conn)
        created_ids.append(rid)
    print()

    # ── AFTER state ──
    print("--- AFTER ---")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    after_rows = cur.fetchall()
    total_after = sum(r[1] for r in after_rows)
    print(f"  stop_corpus rows: {len(after_rows)}")
    print(f"  Total passages: {total_after} (was {total_before}, delta +{total_after - total_before})")
    print()

    # Print per-stop summary
    print("  Per-stop passage counts:")
    for title, count in after_rows:
        marker = " <-- NEW" if title in [s[0] for s in ALL_NEW_STOPS] else ""
        marker = " <-- DEEPENED" if title in [s[0] for s in STOPS_TO_REPLACE] else marker
        print(f"    {title:45s} {count:2d}{marker}")
    print()

    # Check audio_tours unchanged
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_after = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list_after = [r[0] for r in cur.fetchall()]
    print(f"  audio_tours: {at_after} rows (was {at_before})")
    print(f"  Nice list: {nice_list_after}")
    assert nice_list_after == nice_list_before, "SAFETY: Nice list changed!"
    assert at_after == at_before, "SAFETY: audio_tours count changed!"

    print()
    print(f"Created/updated IDs: {created_ids}")
    print(f"Cost: $0.00 (no LLM calls, Wikipedia only)")
    print("=" * 80)

    conn.close()


if __name__ == '__main__':
    main()
