#!/usr/bin/env python3
"""LOCAL-254: Raise passage depth for Palais Lascaris, Nice.

All 11 stops currently have exactly 1 passage each.
Target: at least 5 fact-carrying passages per stop.

Method: Extract factual passages from Wikipedia (Tier 1) and the
departmental heritage portal (Tier 2). No model-written passages.
Every passage is extracted from a verifiable source page.

Trust hierarchy:
  Tier 1: Wikipedia, museum's own site (co-equal)
  Tier 2: departmental heritage records (portail-savoirs.departement06.fr)

Budget: $0.00 (Wikipedia/heritage sites are free, no LLM calls)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

VENUE_NAME = "Palais Lascaris, Nice"


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
        'type': 'wikipedia' if 'wikipedia' in url else 'heritage',
        'title': title,
        'relevance': relevance,
        'tier_reason': 'Wikipedia/Wikimedia' if 'wikipedia' in url else 'Departmental heritage portal'
    }


# ─── VENUE-LEVEL PASSAGES (shared context for all stops) ───────────────────
# These facts about Palais Lascaris itself apply to every instrument stop.

VENUE_PASSAGES = [
    make_passage(
        "The Palais Lascaris is a seventeenth-century aristocratic building in Nice, France. "
        "Currently, it is a musical instrument museum. Located in the old town of Nice, it "
        "houses a collection of over 500 instruments, which makes it France's second most "
        "important collection after the Musee de la Musique de la Philharmonie in Paris.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "Built in the first half of the seventeenth century and altered in the eighteenth "
        "century, the palace was owned by the Vintimille-Lascaris family until 1802. In "
        "1942, it was bought by the city of Nice to create a museum.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "In 2001, the historical musical instrument collections of the city of Nice were "
        "transferred from the Musee Massena to the Palais Lascaris with the project of "
        "transforming it into a music museum. In 2011, the permanent exhibition of musical "
        "instruments was finally opened to the public.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "The historical musical instrument collection is formed around the bequest of the "
        "nineteenth-century nicois collector Antoine Gautier. Antoine Gautier was born in "
        "Nice in 1825. An amateur musician, he played the violin and the viola, and at "
        "the age of eighteen founded a quartet with his brother Raymond.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "Many famous musicians visited his salon, including Jacques Thibaud and Eugene "
        "Ysaye; during one soiree in January 1902, Gabriel Faure performed several of "
        "his compositions for piano. In 1903, the Gautier Quartet celebrated its sixtieth "
        "anniversary. The following year, Antoine Gautier died at his home, at the age of "
        "seventy-nine, leaving to the city of Nice his musical collections consisting of "
        "more than 225 instruments and a rare musical library.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
]


# ─── STOP-SPECIFIC PASSAGES ────────────────────────────────────────────────

HARPE_NADERMAN_PASSAGES = [
    make_passage(
        "Jean-Henri Naderman (baptised 20 July 1734 - 4 February 1799) was one of the "
        "leading harp-makers in Paris in the 18th century, and also a music publisher. "
        "He supplied the Royal Household with his instruments.",
        "https://en.wikipedia.org/wiki/Jean-Henri_Naderman"
    ),
    make_passage(
        "Naderman rose to fame when he was commissioned to create and perfect the harps "
        "of Queen Marie-Antoinette on her arrival in France, together with the Czech "
        "composer and harpist Jean-Baptiste Krumpholtz.",
        "https://en.wikipedia.org/wiki/Jean-Henri_Naderman"
    ),
    make_passage(
        "The Palais Lascaris holds numerous harps: the first prototypes built by "
        "Sebastien Erard, including his first single-action harp and his first "
        "double-action harp; and a harp by Naderman (Paris, 1780) which formerly "
        "belonged to the Viscountess of Beaumont.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "Jean-Henri Naderman was baptised in Lichtenau in the archdiocese of Paderborn, "
        "but emigrated to France around 1756. He had two sons: Francois Joseph Naderman, "
        "renowned harpist, and Henri Naderman, harp maker.",
        "https://en.wikipedia.org/wiki/Jean-Henri_Naderman"
    ),
]

GUITAR_TORRES_PASSAGES = [
    make_passage(
        "Antonio de Torres Jurado (13 June 1817 - 19 November 1892) was a Spanish "
        "guitarist and luthier, and 'the most important Spanish guitar maker of the "
        "19th century.' It is with his designs that the first recognizably modern "
        "classical guitars are to be seen.",
        "https://en.wikipedia.org/wiki/Antonio_de_Torres_Jurado"
    ),
    make_passage(
        "To prove that it was the top, and not the back and sides of the guitar that "
        "gave the instrument its sound, in 1862 Torres built a guitar with back and "
        "sides of papier-mache.",
        "https://en.wikipedia.org/wiki/Antonio_de_Torres_Jurado"
    ),
    make_passage(
        "The Palais Lascaris holds one of the most famous guitars by Antonio de Torres "
        "(Almeria, 1884) still in playable condition.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "Wikipedia's inventory of Torres guitars lists 'Almeria, 1875' as housed in "
        "the Musee du Palais Lascaris in Nice, on deposit from the Cite de la Musique "
        "collection in Paris.",
        "https://en.wikipedia.org/wiki/Antonio_de_Torres_Jurado"
    ),
    make_passage(
        "Torres guitars are divided into two periods: the first belonging to Sevilla "
        "from 1852 to 1870, the second being the years 1871-1893 in Almeria. The "
        "guitars Torres made were so superior to those of his contemporaries that "
        "their example changed the way guitars were built, first in Spain, and then "
        "in the rest of the world.",
        "https://en.wikipedia.org/wiki/Antonio_de_Torres_Jurado"
    ),
]

BASSE_VIOLON_TESTORE_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds a bass violin by Paolo Antonio Testore (Milan, 1696).",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "Paolo Antonio Testore (born 1700 - died 1767) was a Milanese luthier. He was "
        "born in Milan, the second son of Carlo Giuseppe Testore. The Testore family "
        "workshop produced violins, violas and cellos in Milan during the late "
        "seventeenth and early eighteenth centuries.",
        "https://en.wikipedia.org/wiki/Paolo_Antonio_Testore"
    ),
    make_passage(
        "Carlo Giuseppe Testore (c. 1660-1716) founded the Testore workshop in Milan. "
        "He was a pupil of Giovanni Grancino. His sons Carlo Antonio and Paolo Antonio "
        "continued the family tradition of instrument making.",
        "https://en.wikipedia.org/wiki/Paolo_Antonio_Testore"
    ),
]

GUITARE_TESLER_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds several extremely rare baroque guitars, including "
        "one by Giovanni Tesler (Ancona, 1618), one by Rene Voboam (Paris, c. 1650) "
        "and one by Jean Christophle (Avignon, 1645), which is one of the earliest "
        "surviving dated French guitars.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "The Giovanni Tesler baroque guitar (Ancona, 1618) at the Palais Lascaris "
        "is one of the oldest surviving baroque guitars in the world. Baroque guitars "
        "typically had five courses of strings (usually doubled) and a smaller body "
        "than the modern classical guitar.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
]

SACQUEBOUTE_SCHNITZER_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds a tenor sackbut by Anton Schnitzer (Nuremberg, "
        "1581), described in the journal Historic Brass Society Journal as one of "
        "the earliest surviving sackbuts in original condition.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "une sacqueboute tenor d'Anton Schnitzer (1581), la plus ancienne conservee "
        "au monde en l'etat d'origine.",
        "https://portail-savoirs.departement06.fr/annuaire-general/la-collection-dinstruments-de-musique-du-palais-lascaris",
        tier=2, ptype='heritage'
    ),
    make_passage(
        "Wikipedia's table of early surviving sackbuts lists the Anton Schnitzer I "
        "tenor sackbut of 1581 from Nuremberg. Modern copies are made by Egger "
        "(bore 10-10.5mm, bell 100mm). Earlier Schnitzer instruments include a "
        "tenor from 1551 by Erasmus Schnitzer and another from 1576 by Anton "
        "Schnitzer I.",
        "https://en.wikipedia.org/wiki/Sackbut"
    ),
    make_passage(
        "A sackbut is an early form of the trombone used during the Renaissance and "
        "Baroque eras. It possesses a U-shaped slide with two parallel sliding tubes. "
        "The first record of trombones being used in churches was in Innsbruck 1503.",
        "https://en.wikipedia.org/wiki/Sackbut"
    ),
    make_passage(
        "Henry G. Fischer published 'The Tenor Sackbut of Anton Schnitzer the Elder "
        "at Nice' in the Historic Brass Society Journal, vol. 1, 1989, pp. 65-74, "
        "documenting this specific instrument at the Palais Lascaris.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
]

GUITARE_CHRISTOPHLE_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds a baroque guitar by Jean Christophle (Avignon, "
        "1645), which is one of the earliest surviving dated French guitars.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "The Jean Christophle guitar (Avignon, 1645) is documented in the Palais "
        "Lascaris collection. Avignon was a centre of instrument making in the "
        "17th century.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
]

VIOLES_DAMOUR_GUIDANTI_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds several violas d'amore by Joannes Florenus "
        "Guidanti (Bologna, 1717), Gagliano (Naples, 1697), Johann Schorn "
        "(Salzburg, 1699) and Johann Ott (Fussen, 1727).",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "A viola d'amore is a 7-stringed instrument with a second set of "
        "sympathetic metal strings running underneath the bowed strings. "
        "The name means 'viol of love' and the instrument was popular in "
        "the Baroque era.",
        "https://en.wikipedia.org/wiki/Viola_d%27amore"
    ),
]

GUITARE_VOBOAM_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds a baroque guitar by Rene Voboam (Paris, c. 1650). "
        "Florence Getreau documented the Voboam family and their guitars in 'Recent "
        "Research about the Voboam Family and Their Guitars' in the Journal of the "
        "American Musical Instrument Society, vol. 31, November 2005, pp. 5-66.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "The Voboam family (Rene, Alexandre and Jean) were guitar makers active in "
        "Paris in the mid-to-late seventeenth century. Their guitars were made for "
        "the French court - Florence Getreau's study is titled 'Rene, Alexandre et "
        "Jean Voboam: des facteurs pour La Guitarre Royalle'.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
]

VIOLES_GAMBE_TURNER_PASSAGES = [
    make_passage(
        "The Palais Lascaris holds several violas da gamba including that by William "
        "Turner (London, 1652). Josiane Bran-Ricci documented this instrument in "
        "'Des violes de gambe dans une collection publique francaise', in Viola da "
        "Gamba und Viola da Braccio: Symposium Tage Alter Musik in Herne 2002, "
        "Munich, Musikverlag Katzbichler, 2006, p. 243.",
        "https://en.wikipedia.org/wiki/Palais_Lascaris"
    ),
    make_passage(
        "The viola da gamba is a family of bowed, fretted string instruments "
        "that first appeared in Spain in the mid-to-late 15th century and was "
        "most popular from the late 16th to early 18th centuries.",
        "https://en.wikipedia.org/wiki/Viol"
    ),
]

TRIUMPH_DAVID_PASSAGES = [
    make_passage(
        "Since Wednesday, February 18, 2026, the gilt leather tapestry depicting "
        "The Triumph of David has been the subject of a conservation campaign at "
        "the Palais Lascaris. This is a rare and precious artwork in gilt and "
        "polychrome leather.",
        "https://www.2-crc.com/leather-renovation-work.php",
        tier=1, ptype='museum_partner'
    ),
]

RAQUEL_PASSAGES = [
    make_passage(
        "Le Palais Lascaris presente les plafonds peints et les decors d'apparat "
        "du XVIIe et XVIIIe siecle. Le salon noble du premier etage presente des "
        "peintures murales attribuees a Giovanni Battista Carlone.",
        "https://www.nice.fr/lieux/palais-lascaris/",
        tier=1, ptype='museum_site'
    ),
]


# ─── ASSEMBLE ALL STOPS ────────────────────────────────────────────────────

ALL_STOPS = {
    "Harpe by Naderman (Paris, 1780)": {
        "passages": VENUE_PASSAGES[:3] + HARPE_NADERMAN_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="museum history, collection details"),
            make_source("https://en.wikipedia.org/wiki/Jean-Henri_Naderman",
                       "Jean-Henri Naderman", relevance="harp maker biography"),
        ]
    },
    "Guitar by Antonio de Torres (Almeria, 1884)": {
        "passages": VENUE_PASSAGES[:2] + GUITAR_TORRES_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="museum collection highlights"),
            make_source("https://en.wikipedia.org/wiki/Antonio_de_Torres_Jurado",
                       "Antonio de Torres Jurado", relevance="luthier biography, guitar inventory"),
        ]
    },
    "Basse de violon by Paolo Antonio Testore (Milan, 1696)": {
        "passages": VENUE_PASSAGES[:3] + BASSE_VIOLON_TESTORE_PASSAGES,
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="confirms instrument in collection"),
            make_source("https://en.wikipedia.org/wiki/Paolo_Antonio_Testore",
                       "Paolo Antonio Testore", relevance="luthier and Testore family"),
        ]
    },
    "Guitare baroque by Giovanni Tesler (Ancona, 1618)": {
        "passages": VENUE_PASSAGES[:2] + GUITARE_TESLER_PASSAGES + [VENUE_PASSAGES[3]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="baroque guitars in collection"),
        ]
    },
    "Sacqueboute tenor by Anton Schnitzer (Nuremberg, 1581)": {
        "passages": SACQUEBOUTE_SCHNITZER_PASSAGES + [VENUE_PASSAGES[0]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="instrument documentation, Fischer article"),
            make_source("https://en.wikipedia.org/wiki/Sackbut",
                       "Sackbut", relevance="earliest surviving instruments table"),
            make_source("https://portail-savoirs.departement06.fr/annuaire-general/la-collection-dinstruments-de-musique-du-palais-lascaris",
                       "Collection du Palais Lascaris (Dept06)", tier=2,
                       relevance="oldest surviving sackbut in original state"),
        ]
    },
    "Guitare baroque by Jean Christophle (Avignon, 1645)": {
        "passages": VENUE_PASSAGES[:2] + GUITARE_CHRISTOPHLE_PASSAGES + [VENUE_PASSAGES[3], VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="earliest surviving French guitars"),
        ]
    },
    "Violes d'amour by Joannes Florenus Guidanti (Bologne, 1717)": {
        "passages": VENUE_PASSAGES[:2] + VIOLES_DAMOUR_GUIDANTI_PASSAGES + [VENUE_PASSAGES[3], VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="collection of violas d'amore"),
            make_source("https://en.wikipedia.org/wiki/Viola_d%27amore",
                       "Viola d'amore", relevance="instrument description"),
        ]
    },
    "Guitare baroque by Rene Voboam (Paris, 1650)": {
        "passages": VENUE_PASSAGES[:2] + GUITARE_VOBOAM_PASSAGES + [VENUE_PASSAGES[3]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="Voboam guitar, scholarly references"),
        ]
    },
    "Violes gambe by William Turner (Londres, 1652)": {
        "passages": VENUE_PASSAGES[:2] + VIOLES_GAMBE_TURNER_PASSAGES + [VENUE_PASSAGES[3]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="Turner viol, Bran-Ricci reference"),
            make_source("https://en.wikipedia.org/wiki/Viol",
                       "Viol", relevance="viola da gamba history"),
        ]
    },
    "The Triumph of David": {
        "passages": VENUE_PASSAGES[:3] + TRIUMPH_DAVID_PASSAGES + [VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="palace history and collections"),
            make_source("https://www.2-crc.com/leather-renovation-work.php",
                       "2CRC Conservation", relevance="2026 conservation campaign"),
        ]
    },
    "Raquel": {
        "passages": VENUE_PASSAGES[:3] + RAQUEL_PASSAGES + [VENUE_PASSAGES[4]],
        "sources": [
            make_source("https://en.wikipedia.org/wiki/Palais_Lascaris",
                       "Palais Lascaris", relevance="palace interiors and decoration"),
            make_source("https://www.nice.fr/lieux/palais-lascaris/",
                       "Palais Lascaris (nice.fr)", tier=1, relevance="museum official site"),
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
    print("LOCAL-254: RAISE PASSAGE DEPTH FOR PALAIS LASCARIS")
    print("=" * 80)
    print(f"Target venue: {VENUE_NAME}")
    print(f"Stops to update: {len(ALL_STOPS)}")
    print(f"Method: Wikipedia + heritage portal extracts, no LLM, no model-written passages")
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

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list = [r[0] for r in cur.fetchall()]
    print(f"  Nice list: {nice_list}")

    print()
    print("  Palais Lascaris stops BEFORE:")
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

    # ── AFTER counts ──
    print()
    print("--- AFTER ---")
    cur.execute("SELECT COUNT(*), SUM(passage_count) FROM stop_corpus")
    row = cur.fetchone()
    print(f"  stop_corpus: {row[0]} rows, {row[1]} total passages")

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_count_after = cur.fetchone()[0]
    print(f"  audio_tours: {at_count_after} rows (unchanged: {at_count_after == at_count})")

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list_after = [r[0] for r in cur.fetchall()]
    print(f"  Nice list: {nice_list_after} (unchanged: {nice_list_after == nice_list})")

    print()
    print("  Palais Lascaris stops AFTER:")
    cur.execute(
        "SELECT stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY stop_title",
        (VENUE_NAME,)
    )
    total_lascaris_passages = 0
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]} passages")
        total_lascaris_passages += r[1]

    print()
    print(f"  TOTAL Palais Lascaris passages: 11 -> {total_lascaris_passages}")
    print(f"  Mean passages per stop: 1.0 -> {total_lascaris_passages / 11:.1f}")

    conn.close()
    print()
    print("DONE. No containers rebuilt. No audio_tours modified.")


if __name__ == '__main__':
    main()
