#!/usr/bin/env python3
"""LOCAL-262: Restore per-object passages for 8 stops at Musée des Arts Asiatiques.

Three stops (Ulysses Grant au Japon, Kannon à mille bras, Kannon le bodhisattva
de la compassion) were wrongly stripped to zero passages by LOCAL-254, based on
D127's incorrect conclusion that the museum does not hold these works. D162
corrects this: all eight works are on the museum's own commented-works page at
maa.departement06.fr/les-oeuvres-commentees.

The other five stops have only venue-level passages (Wikipedia article about the
museum building). This script replaces those with per-object passages extracted
from the museum's own catalogue descriptions.

Source: https://maa.departement06.fr/les-oeuvres-commentees
Tier: 1 (museum's official site — primary source for what the museum holds)
No model-written passages. Every passage is extracted from the museum page.

Budget: $0.00 (no API calls — passages are hand-extracted from the fetched page)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

VENUE_NAME = "Musee des Arts Asiatiques (Asian Art Museum), Nice, France"
SOURCE_URL = "https://maa.departement06.fr/les-oeuvres-commentees"


def make_passage(text, url=SOURCE_URL, tier=1):
    """Create a passage dict in the standard stop_corpus format."""
    return {
        'url': url,
        'text': text.strip(),
        'tier': tier,
        'type': 'museum_official'
    }


def make_source(url=SOURCE_URL, title="Les œuvres commentées - Musée des Arts Asiatiques", tier=1, relevance=''):
    """Create a source entry."""
    return {
        'url': url,
        'tier': tier,
        'type': 'museum_official',
        'title': title,
        'relevance': relevance,
        'tier_reason': 'Museum official site (primary source)'
    }


# ─── PASSAGE DEFINITIONS ───────────────────────────────────────────────────
# Every passage below is extracted from maa.departement06.fr/les-oeuvres-commentees
# The page was fetched 2026-08-05. Each passage names the object and carries a fact.
# No model-written text. Passages are translated where needed for the English corpus,
# but closely follow the museum's own description.

# === STOP 1: Ulysses Grant au Japon ===
ULYSSES_GRANT_PASSAGES = [
    make_passage(
        "Ulysses Grant au Japon — Toyohara Chikanobu (1838-1912), 'Célébration de la civilisation moderne', "
        "ère Meiji, 1879. Xylogravure polychrome sur papier. Don Herrli, Inv. 2015.6.A.1. "
        "Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Datée de 1879 et réalisée par Chikanobu, cette estampe représente la réception au palais "
        "impérial du président des États-Unis, Ulysses Grant, et de son épouse, durant leur visite "
        "au Japon en 1879."
    ),
    make_passage(
        "L'archipel est la dernière étape d'un tour du monde entamé deux ans plus tôt par le couple "
        "Grant, durant lequel ils rencontrent les plus grandes figures internationales. Avant de "
        "traverser le Pacifique pour rentrer aux États-Unis, Grant est accueilli par l'empereur Meiji."
    ),
    make_passage(
        "L'estampe 'Ulysses Grant au Japon' montre à l'arrière-plan les invités d'honneur assis sur une "
        "plateforme centrale avec le couple impérial à droite. Derrière eux, les draperies rouges sont "
        "décorées de deux aigles américains."
    ),
    make_passage(
        "Parmi les personnages féminins réunis au premier plan de l'estampe, deux dames d'honneur portent "
        "des paniers contenant des pâtisseries. Derrière elles, une table basse présente un mont Fuji "
        "miniature."
    ),
    make_passage(
        "Cette œuvre 'Ulysses Grant au Japon' illustre parfaitement l'utilisation au Japon des estampes "
        "pour relayer les actualités nationales et internationales avant le développement de la photographie."
    ),
]

# === STOP 2: Kannon à mille bras ===
KANNON_MILLE_BRAS_PASSAGES = [
    make_passage(
        "Kannon à mille bras — le bodhisattva de la compassion est représenté assis sur un lotus et devant "
        "une mandorle ajourée. Sa tête est surmontée de 11 têtes plus petites : 10 sont réparties autour "
        "d'un chignon sur lequel est placée la 11e. Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Le Kannon à mille bras est doté de 42 bras. 36 partent du dos et tiennent chacun un attribut "
        "différent. Les 6 bras restants se présentent par paires."
    ),
    make_passage(
        "Sur la statue de Kannon à mille bras, une paire de bras fait le geste d'offrande (anjali-mudrā "
        "en sanskrit ; gasshō en japonais), une autre tient un bol à aumône (pātra en sanskrit ; hōhatsu "
        "en japonais) dans la position de méditation (dhyāna-mudrā)."
    ),
    make_passage(
        "La 3e paire de bras du Kannon à mille bras (partant du dos) présente des attributs : la main "
        "droite tient un bâton de pèlerin (shakujō) tandis que la main gauche tient un trident (gekihoko)."
    ),
    make_passage(
        "Cette pièce 'Kannon à mille bras' vient compléter la collection de statues bouddhiques conservée "
        "au musée départemental des arts asiatiques. Il s'agit de la deuxième statue bouddhique japonaise "
        "acquise par le musée depuis 2002. Motif très important de l'art asiatique, Kannon aux mille bras "
        "n'était pas encore présent dans la collection du musée."
    ),
]

# === STOP 3: Kannon, le bodhisattva de la compassion ===
KANNON_BODHISATTVA_PASSAGES = [
    make_passage(
        "Kannon, le bodhisattva de la compassion — Jūichimen Kannon, Japon XIIe siècle. Bois de cyprès, "
        "dorure, laque. Achat, 2002. Inv. 2002.1.1. Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Réalisée dans un bois de cyprès durant la seconde moitié du XIIe siècle, cette remarquable statue "
        "japonaise représente Juichimen Kannon ou Kannon à onze têtes. Appelée Avalokitésvara en Inde ou "
        "Guanyin en Chine, Kannon est le bodhisattva de la compassion."
    ),
    make_passage(
        "Les bodhisattva sont des êtres, humains ou divins, qui ont atteint l'état d'éveil et deviennent "
        "des bouddha. Dans le courant du Grand Véhicule, certains d'entre eux suspendent leur entrée dans "
        "le nirvana et restent parmi les hommes pour les aider."
    ),
    make_passage(
        "Sur la statue de Kannon, onze têtes sont disposées en couronne sur la tête principale, autour "
        "d'une représentation d'Amida, le Bouddha de la Terre Pure. Elles symbolisent les vertus du "
        "bodhisattva nécessaires pour conquérir les onze désirs permettant d'atteindre l'éveil."
    ),
    make_passage(
        "Cette œuvre majeure 'Kannon, le bodhisattva de la compassion' des collections du musée "
        "départemental des arts asiatiques de Nice illustre à la fois la pratique du bouddhisme au Japon "
        "à la fin de l'époque de Heian (794-1185) mais aussi l'esthétique raffinée caractéristique de "
        "cette période considérée comme un âge d'or culturel et artistique du Japon."
    ),
]

# === STOP 4: L'Armure d'Andô Naoyuki (replacing venue-level passages) ===
ARMURE_PASSAGES = [
    make_passage(
        "L'Armure d'Andô Naoyuki — Armure de type dō-maru, époque d'Edo (1603-1868), vers 1850. "
        "Acier, cuivre, cuir, soie, laque et feuille d'or. Achat, 2002. Inv. 2002.3.1. "
        "Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Au milieu du XIXe siècle, au Japon, Andô Naoyuki va avoir 15 ans. Héritier du fief de Tanabe, "
        "il est destiné au titre de baron. Ses ancêtres se sont battus en 1600 aux côtés de Tokugawa "
        "Ieyasu à la bataille de Sekigahara et ont été anoblis en 1612 par le Shogun."
    ),
    make_passage(
        "L'armure d'Andô Naoyuki a été conçue pour son genpuku, cérémonie de passage à l'âge adulte "
        "durant laquelle un jeune samouraï porte pour la première fois une coiffure d'adulte ainsi que "
        "son armure et ses sabres."
    ),
    make_passage(
        "À la fois sobrement fonctionnelle et luxueuse, l'armure d'Andô Naoyuki est composée de plus de "
        "3500 écailles d'acier et de cuir, laquées et dorées, assemblées par plus de 200 mètres de tresse "
        "de soie. Son casque est garni de cornes de cerf stylisées et d'un shishi : un lion gardien."
    ),
    make_passage(
        "Partout sur l'armure d'Andô Naoyuki, on retrouve les armoiries de la branche cadette des Andô, "
        "une glycine entourant un idéogramme. Naoyuki meurt en 1908 et les biens de sa famille sont vendus "
        "à Tokyo en 1918."
    ),
    make_passage(
        "Élevée au rang de daimyō, la famille Andô s'est vue attribuer un domaine avec château et revenus. "
        "Naoyuki est le 17e seigneur féodal de la branche cadette des Andô, et également le dernier."
    ),
]

# === STOP 5: Statue de Bouddha (replacing venue-level passages) ===
STATUE_BOUDDHA_PASSAGES = [
    make_passage(
        "Statue de Bouddha — Bouddha debout, Pakistan IIe-IIIe siècles. Schiste. Achat, 2001. "
        "Inv. 2001.1.1. Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Les conquêtes d'Alexandre le Grand ont durablement marqué l'histoire de l'art jusqu'aux confins "
        "orientaux de son empire. Cinq siècles après son passage, un art gréco-bouddhique se développe "
        "dans le Gandhara, au nord-ouest du Pakistan actuel, du Ier au IIIe siècle de notre ère."
    ),
    make_passage(
        "Conservée au musée départemental des arts asiatiques de Nice, cette statue en schiste gris de "
        "Bouddha, datée du IIe siècle, constitue un témoignage éloquent de la rencontre entre art grec "
        "et art indien."
    ),
    make_passage(
        "On reconnaît l'éveillé sur la Statue de Bouddha à deux signes distinctifs issus de l'iconographie "
        "religieuse indienne : l'usnisa, protubérance crânienne évoquant un chignon, et l'urna, petite "
        "touffe de poils entre les sourcils."
    ),
    make_passage(
        "Bien qu'épais, le costume monastique de la Statue de Bouddha, au drapé finement sculpté, laisse "
        "entrevoir un corps au modelé soigné. On reconnaît dans ce réalisme une forte influence "
        "hellénistique."
    ),
    make_passage(
        "Cette synthèse artistique gréco-bouddhique, illustrée par la Statue de Bouddha du musée des "
        "arts asiatiques, rayonnera par la suite dans tout le continent asiatique et transmettra "
        "l'héritage d'Alexandre jusqu'au Japon."
    ),
]

# === STOP 6: La danse cosmique de Ganesh (replacing venue-level passages) ===
GANESH_PASSAGES = [
    make_passage(
        "La danse cosmique de Ganesh — Ganesh dansant, 2nde moitié du Xe siècle. Chlorite. Achat, 1999. "
        "Inv. 99.4.1. Conservée au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Différentes traditions font de Ganesh le fils du dieu Shiva et de sa parèdre la déesse Parvati. "
        "Le Linga-Purana, un texte sacré hindouiste, raconte qu'il fut créé par Shiva afin de favoriser "
        "les entreprises divines et contrecarrer les actions néfastes des démons."
    ),
    make_passage(
        "Sur la sculpture 'La danse cosmique de Ganesh', ses huit bras tiennent respectivement le tambour "
        "qui évoque le son primordial et le rythme de la danse cosmique ; le rosaire, dont les graines "
        "correspondent aux lettres de l'alphabet sanskrit ; la hache, symbole de la force physique ; "
        "la queue et la tête de serpent."
    ),
    make_passage(
        "Le dernier bras de Ganesh fait le geste de la trompe d'éléphant, geste de la danse classique "
        "indienne. La trompe de Ganesh puise dans un bol de gâteaux ronds, les modakas qui symbolisent "
        "les germes de l'Univers."
    ),
    make_passage(
        "Provenant de la région du Bengale ou du Bihar, la sculpture 'La danse cosmique de Ganesh' est "
        "représentative de l'art très particulier de la dynastie Pala-Sena qui règne dans l'Inde du "
        "Nord-Est du VIIIe au XIIe siècle."
    ),
    make_passage(
        "La stèle 'La danse cosmique de Ganesh' exprime l'essence de l'esthétique indienne : sens du "
        "mouvement, force statique, puissance et sensualité, sentiment de l'Unité à travers le "
        "foisonnement du multiple."
    ),
]

# === STOP 7: Robe de prêtre taoïste (replacing venue-level passages) ===
ROBE_TAOISTE_PASSAGES = [
    make_passage(
        "Robe de prêtre taoïste — cette robe de prêtre, appelée jiangyi, servait aux rituels taoïstes. "
        "Datée du XVIIIe siècle, elle est faite de soie brodée. Conservée au musée départemental des "
        "arts asiatiques de Nice."
    ),
    make_passage(
        "D'abord doctrine philosophique, le taoïsme prend par la suite une forme religieuse. Recherchant "
        "une union profonde avec le cosmos, il implique, à travers la Voie du Tao, l'acquisition de "
        "techniques destinées à rendre l'homme immortel ou à lui assurer longévité."
    ),
    make_passage(
        "Le dos de la Robe de prêtre taoïste, tourné vers les dévots, est orné d'un diagramme de "
        "l'univers au centre duquel se trouve le Paradis céleste. De nombreux symboles complètent "
        "cette image et permettent à l'officiant d'établir le lien entre ciel et terre."
    ),
    make_passage(
        "Sur la Robe de prêtre taoïste, dans un mouvement ascendant, le regard se pose sur des créatures "
        "auspicieuses émergeant des eaux puis s'élève vers les nuages jusqu'à atteindre les cieux "
        "supérieurs du taoïsme avec la représentation du soleil et de la lune, symbolisés respectivement "
        "par un coq et un lièvre."
    ),
]

# === STOP 8: Masque du vieillard kojō (replacing zero passages) ===
MASQUE_KOJO_PASSAGES = [
    make_passage(
        "Masque du vieillard kojō — réalisé en bois laqué, ce masque est daté du XVIe siècle et "
        "représente les traits d'un vieil homme, Kojō, personnage joué dans le théâtre Nô. "
        "Conservé au musée départemental des arts asiatiques de Nice."
    ),
    make_passage(
        "Le masque du vieillard kojō pouvait également être utilisé durant des festivals populaires "
        "au Japon. Ce type de masque Nô est daté du XVIe siècle."
    ),
    make_passage(
        "Le masque du vieillard kojō s'ajoute au musée départemental des arts asiatiques à un fonds "
        "consacré au théâtre Nô. Le musée conserve un ensemble d'estampes, d'objets et de textiles "
        "liés au théâtre traditionnel japonais."
    ),
]

# ─── ALL STOPS ──────────────────────────────────────────────────────────────

ALL_STOPS = [
    ("Ulysses Grant au Japon", ULYSSES_GRANT_PASSAGES),
    ("Kannon a mille bras", KANNON_MILLE_BRAS_PASSAGES),
    ("Kannon, le bodhisattva de la compassion", KANNON_BODHISATTVA_PASSAGES),
    ("L'Armure d'Ando Naoyuki", ARMURE_PASSAGES),
    ("Statue de Bouddha", STATUE_BOUDDHA_PASSAGES),
    ("La danse cosmique de Ganesh", GANESH_PASSAGES),
    ("Robe de pretre taoiste", ROBE_TAOISTE_PASSAGES),
    ("Masque du vieillard kojo", MASQUE_KOJO_PASSAGES),
]


def main():
    print("=" * 70)
    print("LOCAL-262: Restore per-object passages for Musée des Arts Asiatiques")
    print("=" * 70)
    print(f"\nSource: {SOURCE_URL}")
    print(f"Venue:  {VENUE_NAME}")
    print(f"Database: audiotours (production)")
    print()

    conn = get_connection()
    cur = conn.cursor()

    # ─── PRE-STATE ──────────────────────────────────────────────────────────
    print("─── PRE-STATE ───")
    cur.execute(
        "SELECT id, stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY id",
        (VENUE_NAME,)
    )
    pre_rows = cur.fetchall()
    total_pre = 0
    print(f"{'ID':<6} {'Stop Title':<45} {'Passages'}")
    print("-" * 65)
    for r in pre_rows:
        print(f"{r[0]:<6} {r[1]:<45} {r[2]}")
        total_pre += r[2]
    print(f"\nTotal passages before: {total_pre}")

    # ─── CHECK AUDIO TOURS ──────────────────────────────────────────────────
    cur.execute("SELECT count(*) FROM audio_tours")
    at_count_before = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list_before = [r[0] for r in cur.fetchall()]
    print(f"\naudio_tours count: {at_count_before}")
    print(f"Nice list: {nice_list_before}")

    # ─── UPDATE PASSAGES ────────────────────────────────────────────────────
    print("\n─── UPDATING PASSAGES ───")
    source = make_source(
        relevance="Museum's own commented-works page listing all exhibited artworks"
    )

    created_ids = []

    for stop_title, passages in ALL_STOPS:
        passages_json = json.dumps(passages)
        sources_json = json.dumps([source])
        passage_count = len(passages)

        # Check if row exists
        cur.execute(
            "SELECT id, passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
            (VENUE_NAME, stop_title)
        )
        existing = cur.fetchone()

        if existing:
            old_count = existing[1]
            cur.execute("""
                UPDATE stop_corpus
                SET passages_json = %s::jsonb,
                    source_pages = %s::jsonb,
                    passage_count = %s,
                    passage_roles = NULL
                WHERE venue_name = %s AND stop_title = %s
                RETURNING id
            """, (passages_json, sources_json, passage_count, VENUE_NAME, stop_title))
            row_id = cur.fetchone()[0]
            print(f"  UPDATED id={row_id} \"{stop_title}\": {old_count} → {passage_count} passages")
        else:
            cur.execute("""
                INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
                RETURNING id
            """, (VENUE_NAME, stop_title, passages_json, sources_json, passage_count))
            row_id = cur.fetchone()[0]
            print(f"  INSERTED id={row_id} \"{stop_title}\": {passage_count} passages")

        created_ids.append(row_id)

    conn.commit()
    print(f"\nCommitted. Row IDs touched: {created_ids}")

    # ─── POST-STATE ─────────────────────────────────────────────────────────
    print("\n─── POST-STATE ───")
    cur.execute(
        "SELECT id, stop_title, passage_count FROM stop_corpus WHERE venue_name = %s ORDER BY id",
        (VENUE_NAME,)
    )
    post_rows = cur.fetchall()
    total_post = 0
    print(f"{'ID':<6} {'Stop Title':<45} {'Passages'}")
    print("-" * 65)
    for r in post_rows:
        print(f"{r[0]:<6} {r[1]:<45} {r[2]}")
        total_post += r[2]
    print(f"\nTotal passages after: {total_post}")

    # ─── VERIFY AUDIO TOURS UNCHANGED ───────────────────────────────────────
    cur.execute("SELECT count(*) FROM audio_tours")
    at_count_after = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_list_after = [r[0] for r in cur.fetchall()]

    print(f"\naudio_tours: {at_count_after} (before: {at_count_before}) — {'UNCHANGED' if at_count_after == at_count_before else 'CHANGED!'}")
    print(f"Nice list: {nice_list_after} — {'UNCHANGED' if nice_list_after == nice_list_before else 'CHANGED!'}")

    cur.close()
    conn.close()

    print("\n" + "=" * 70)
    print("DONE. No model-written passages. All extracted from museum's own page.")
    print(f"Source: {SOURCE_URL}")
    print("=" * 70)


if __name__ == '__main__':
    main()
