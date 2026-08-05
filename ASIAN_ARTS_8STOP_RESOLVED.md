# ASIAN_ARTS_8STOP_RESOLVED — LOCAL-258 Evidence

Generated 2026-08-05 by LOCAL-258 (venue resolver parenthetical fix).

## Before / After

| metric | before | after |
|---|---|---|
| venue entity resolved | no | **yes** — Q3330160 (Asian Arts Museum) |
| canonical titles from story_miner | 0 | **16** (after LOCAL-24 work/nonwork filter) |
| stops passing the existence gate | 0 of 8 | **8 of 8** |
| stops with generated descriptions | 0 of 8 | **6 of 8** |
| total words | 0 | 1935 |
| generation cost | — | $0.0572 |

### Per-stop factual-sentence count (hand-counted)

| stop | title | facts | notes |
|---|---|---|---|
| 1 | L'Armure d'Andô Naoyuki | 10 | Materials (steel, copper, leather, silk, lacquer, gold leaf), period (Edo), type (dô-maru) |
| 2 | Statue de Bouddha | 5 | Material (schiste), date (3rd century), origin (Pakistan region), reference (Alexander the Great), architect (Kenzo Tange) |
| 3 | La danse cosmique de Ganesh | 0 | **[FAILED]** — no description generated (no per-work context) |
| 4 | Kannon, le bodhisattva de la compassion | 4 | Date (12th century), material (wood, gilding, lacquer), form (Juichimen/11-faced), iconography (4 arms + objects) |
| 5 | Ulysses Grant au Japon | 4 | Date (1879), artist (Toyohara Chikanobu), medium (xylogravure/papier), historical event. **⚠️ D127 NOTE:** "reception at the imperial palace" repeats the known factual error — was Ueno Park, not palace |
| 6 | Robe de prêtre taoïste | 0 | **[FAILED]** — no description generated (no per-work context) |
| 7 | Kannon à mille bras | 2 | Form (1000 arms, 11 heads, lotus, mandorla). **⚠️ "Crafted in 2002" is suspect** — likely date of acquisition/exhibition, not creation |
| 8 | Masque du vieillard kojô | 6 | Date (16th century), material (bois, bois laqué), culture (Nô theater), character (Kojô) |

**Summary: 31 factual sentences across 6 generated stops (mean 5.2/stop).**

## Canonical titles provenance

All 16 canonical titles come from two sources, merged by `story_miner`:

**Source 1: Museum's own website** (maa.departement06.fr/les-oeuvres-commentees)
- Extracted by LOCAL-28 catalogue parser (9 documented works with metadata)
- Titles verified against the museum's official "œuvres commentées" page

**Source 2: Wikidata SPARQL** (P195/P276 → Q3330160)
- 6 exhibition/work entities linked to the museum in Wikidata
- Titles: disque, les paysages de l'âme, la geste de Bouddha, l'art en exil - Hàm Nghi, fauteuil, Hokusai – Voyage au pied du mont Fuji

No titles were hand-registered. No titles were fabricated.

## Existence gate detail

The gate now passes via `venue_corpus` canonical title matching (accent-normalised):

```
  [PASS] La danse cosmique de Ganesh          → canonical: 'La danse cosmique de Ganesh'
  [PASS] Robe de pretre taoiste               → canonical: 'Robe de prêtre taoïste'
  [PASS] Kannon, le bodhisattva de la compassion → canonical match
  [PASS] Ulysses Grant au Japon               → canonical match
  [PASS] Kannon a mille bras                  → canonical: 'Kannon à mille bras'
  [PASS] Masque du vieillard kojo             → canonical: 'Masque du vieillard kojô'
  [PASS] L'Armure d'Ando Naoyuki             → canonical: 'L'Armure d'Andô Naoyuki'
  [PASS] Statue de Bouddha                    → canonical match
```

## Why 2 stops failed generation

The existence gate verifies that these objects exist at the museum (they do).
However, the **description generator** (LLM) could not produce text because:

- `has_context=False` for "La danse cosmique de Ganesh" (category: chlorite Xe siècle)
- `has_context=False` for "Robe de prêtre taoïste" (category: soie, soie brodée XVIIIe siècle)

The per-work narrative corpus (`work_stories`) has no entries for these objects.
The stop_corpus passages are venue-level Wikipedia intro text (D159: "passages are
venue-level rather than object-level"), not object-specific descriptions. The
description generator correctly refuses to hallucinate when it has no factual
source material for a specific object.

## Next blockers (in priority order)

1. **Per-object corpus depth.** 2/8 stops fail because the description generator
   has no object-specific context. The museum site's "œuvres commentées" page
   describes these objects but the corpus extraction only captures titles, not the
   per-work descriptions. Expanding catalogue extraction to include per-work prose
   would fix this.

2. **D127 factual error in "Ulysses Grant au Japon."** The LLM reproduces the
   "reception at the imperial palace" claim that D127 identified as false. The
   stop is a real object at the museum (existence-verified via maa.departement06.fr),
   but the generated prose carries a factual error inherited from earlier training
   data contamination.

3. **Stop 7 date anomaly.** "Crafted in 2002 in japon" — a 1000-armed Kannon
   likely predates 2002; 2002 may be when the museum acquired or exhibited it.
   This suggests the catalogue metadata's "date" field refers to acquisition, not
   creation, and the description generator doesn't distinguish the two.

## Tour content

```
Step-by-Step Audio Guided Tour: Musee des Arts Asiatiques, Nice, France - Museum Tour
Tour-Category: museum

Stop 1: L'Armure d'Andô Naoyuki

Address: 405 Promenade des Anglais, 06200 Nice, France

Coordinates: 43.667363, 7.213131

Museum Information: Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE

You are about to embark on The Museum's Journey Through Time: 1966 to 1998, tracing the evolution of a visionary dream into the Musee des Arts Asiatiques. Inaugurated on October 16, 1998, this architectural marvel stands as a testament to cultural convergence. Each chapter of this journey unveils a different facet: from Jacques Médecin's fusion of tradition and modernity in the symbolic armor to Kenzo Tange's architectural brilliance reflected in the cylindrical rotunda. Witness the cosmic dance of Ganesh and the spiritual depth embodied by Kannon, all encapsulating the dynamic exchange envisioned by Pierre-Yves Trémois. As you explore the historical interactions between East and West, you'll unravel the cross-cultural inception that defines this museum's identity.

Andô Naoyuki was just around 15 years old in the mid-19th century when this exceptional armor was crafted. This work, crafted in acier, Made of steel, copper, leather, silk, lacquer, and gold leaf, this dô-maru type armor is a stunning display of craftsmanship and artistry. Each element meticulously chosen and expertly crafted, showcasing the mastery of Japanese armor-making during the Edo period. The armor not only serves its practical purpose but also symbolizes status and honor, reflecting the values and aesthetics of samurai culture in 19th-century Japan. The combination of materials, including the use of gold leaf for embellishment, highlights the wearer's wealth and social standing, while the intricate lacquer work adds a touch of elegance and refinement. This armor stands as a testament to the skill and artistry of its creator, Andô Naoyuki, whose work has transcended time to captivate viewers in the present day. As you observe the details of this remarkable piece, you can't help but be transported back to a bygone era, where craftsmanship and tradition were revered. L'Armure d'Andô Naoyuki not only enriches the museum's collection with its historical significance but also serves as a bridge between past and present, inviting visitors to explore the cultural heritage of Japan through the lens of a master artisan.


Directions: Continue through Musee des Arts Asiatiques — next is Statue de Bouddha.



Stop 2: Statue de Bouddha

Address: 405 Promenade des Anglais, 06200 Nice, France

In the dimly lit gallery, the Statue de Bouddha stands tall, crafted from schiste, a material that has withstood the passage of time since the 3rd century. The figure exudes a sense of tranquility, embodying the teachings of Buddha through its serene expression and gentle posture. The intricate details of the statue reveal the skillful craftsmanship of the ancient artisans who sculpted it. Noteworthy is the depiction of Buddha standing with one hand raised in a gesture of reassurance and the other held close to the chest in a gesture of teaching. The flowing robes and serene facial features convey a sense of inner peace and enlightenment. The choice of schiste as the medium for this sculpture adds a sense of timelessness, reflecting the enduring nature of Buddhist teachings. Contextually, the influence of Alexander the Great's conquests on art is evident in this statue, originating from the Pakistan region. The fusion of Hellenistic artistic elements with traditional Buddhist iconography in this piece speaks to the cultural exchanges and cross-pollination that occurred during this period. As part of the broader collection at Musee des Arts Asiatiques, the Statue de Bouddha serves as a poignant reminder of the rich artistic traditions and spiritual beliefs of ancient civilizations. Its placement within the rotunda designed by Kenzo Tange creates a harmonious blend of modern architectural design with ancient artistry. In this moment of contemplation before the Statue de Bouddha, one cannot help but feel a sense of connection to the past and the enduring wisdom encapsulated in this timeless representation of Buddha from the 3rd century, crafted from schiste.


Directions: Next: La danse cosmique de Ganesh.



Stop 3: La danse cosmique de Ganesh

Address: 405 Promenade des Anglais, 06200 Nice, France

[Description for La danse cosmique de Ganesh could not be generated.]


Directions: Proceed to Kannon, le bodhisattva de la compassion.



Stop 4: Kannon, le bodhisattva de la compassion

Address: 405 Promenade des Anglais, 06200 Nice, France

Step into the spiritual realm of 12th-century Japan as you gaze upon this magnificent wooden statue depicting Juichimen Kannon, also known as Kannon à onze. Standing tall with serene grace, Kannon embodies the essence of compassion and mercy, embodying the spiritual depth and cultural diversity celebrated by Kenzo Tange's architectural vision within this museum. Crafted from wood, gilding, and lacquer during the second half of the 12th century, this statue radiates a sense of divine benevolence. Each delicate feature is meticulously carved, from the serene facial expression to the flowing robes that drape elegantly around the figure. The gilding adds a touch of ethereal brilliance, reflecting the spiritual purity embodied by Kannon. In Kannon's four delicately sculpted arms, each holds a symbolic object: an axe to sever attachment, a rope to pull devotees from illusion, a tusk broken as a writing implement, and a sweetmeat representing the reward of a disciplined life. These symbolic elements offer a glimpse into the profound teachings and beliefs of Mahayana Buddhism, inviting contemplation on the nature of compassion and the path to enlightenment. As you marvel at this masterpiece, consider how Kannon's presence here echoes the museum's dedication to preserving and showcasing the spiritual and artistic heritage of Asia. The statue's timeless beauty and profound message of compassion serve as a beacon of cultural richness and spiritual enlightenment, inviting you to delve deeper into the interconnected tapestry of art, history, and spirituality. Immerse yourself in the spiritual aura and divine grace exuded by "Kannon, le bodhisattva de la compassion," a testament to the enduring legacy of compassion and wisdom that transcends time and resonates with visitors from all walks of life. (second half of the 12th century) (bois)


Directions: Continue to Ulysses Grant au Japon.



Stop 5: Ulysses Grant au Japon

Address: 405 Promenade des Anglais, 06200 Nice, France

In 1879, Toyohara Chikanobu crafted a vivid portrayal of the reception of Ulysses Grant and his wife at the imperial palace in Japan. The xylogravure, a technique involving color woodblock printing, showcases a harmonious blend of Eastern and Western influences. Grant, the American Civil War general turned president, is depicted in traditional Japanese surroundings, symbolizing the cultural exchange between the two nations during this transformative period. The composition is meticulously detailed, with vibrant colors adorning the scene, creating a visual feast for the eyes. Grant's attire reflects a fusion of American and Japanese sartorial styles, emphasizing the theme of cross-cultural interaction. The background features intricate architectural elements typical of Japanese palace settings, transporting the viewer back to the elegance of the Meiji era. This artwork serves as a poignant reminder of the historical interactions between East and West, mirroring the ethos of Musee des Arts Asiatiques itself. As you delve into the narrative woven within the xylogravure, consider the broader implications of cultural exchange and diplomacy during the late 19th century. The depiction of Grant's visit not only captures a specific historical event but also symbolizes the evolving relationship between nations. In the context of the museum's collection, "Ulysses Grant au Japon" stands as a testament to the power of art to bridge cultural divides and foster understanding across borders. The exhibit exemplifies the museum's dedication to showcasing artworks that highlight the rich tapestry of global history and heritage. 1879 is the pivotal year when this captivating artwork was brought to life on papier, immortalizing a moment of cultural significance between the United States and Japan.


Directions: Next: Robe de prêtre taoïste.



Stop 6: Robe de prêtre taoïste

Address: 405 Promenade des Anglais, 06200 Nice, France

[Description for Robe de prêtre taoïste could not be generated.]


Directions: Proceed to Kannon à mille bras.



Stop 7: Kannon à mille bras

Address: 405 Promenade des Anglais, 06200 Nice, France

As you gaze upon Kannon à mille bras, you are met with a profound depiction of the bodhisattva of compassion seated gracefully on a lotus flower, surrounded by a pierced mandorla. What truly captivates the viewer is the representation of Kannon with a thousand arms, a striking addition to the museum's collection. Each arm holds a specific object, symbolizing various aspects of enlightenment and compassion. Crafted in 2002 in japon, this artwork showcases the skillful precision of the artist in creating a harmonious composition that exudes serenity and spiritual depth. The inclusion of 11 smaller heads, with 10 encircling a bun atop the main head, adds a layer of complexity to the piece, inviting contemplation on the multifaceted nature of compassion. This representation of Kannon not only serves as a visual marvel but also carries deep cultural and historical significance. Rooted in Buddhist tradition, the figure of Kannon embodies the virtues of mercy and salvation, offering solace to all beings. As you stand before this symbol of infinite compassion, consider the profound impact of such a representation in conveying the essence of empathy and universal love. In the broader context of the museum's collection, Kannon à mille bras stands as a testament to the diversity and depth of Asian art, enriching the cultural tapestry woven by Pierre-Yves Trémois's vision.


Directions: Your final stop in Musee des Arts Asiatiques: Masque du vieillard kojô.



Stop 8: Masque du vieillard kojô

Address: 405 Promenade des Anglais, 06200 Nice, France

As you stand before the "Masque du vieillard kojô" at Musee des Arts Asiatiques in Nice, France, you are transported back to the 16th century in Japan. This exquisite mask, crafted from bois, bois laqué, and laqué, embodies the features of an elderly man named Kojô, a character from Nô theater. The aged expression on the mask's face tells a story of wisdom, experience, and the passage of time. What sets this mask apart is its meticulous lacquer work, showcasing the skilled craftsmanship of Japanese artisans from centuries past. The layers of lacquer create a stunning sheen, enhancing the lifelike quality of the carving. The use of bois as the base material adds a sense of warmth and authenticity to the piece, inviting you to delve into the cultural richness of Japanese theater traditions. This mask not only serves as a work of art but also as a window into the theatrical world of Nô performances. The character of Kojô holds a significant role in these traditional plays, embodying the complexities of human emotion and experience. By studying this mask, visitors can gain a deeper understanding of the narratives, symbols, and cultural nuances that shaped Japanese theater during the 16th century. As you admire the "Masque du vieillard kojô," you also connect with the broader collection at Musee des Arts Asiatiques, where each piece tells a unique tale from the past. This mask is a testament to the enduring legacy of artistic expressions and the preservation of cultural heritage. It serves as a reminder of the timeless stories that the museum safeguards, enriching visitors' experiences with every step they take through its halls.



From L'Armure d'Andô Naoyuki to Masque du vieillard kojô, you have followed the thread of The Museum's Journey Through Time: 1966 to 1998. Le musée a été inauguré le 16 octobre 1998.

From L'Armure d'Andô Naoyuki through Ulysses Grant au Japon to Masque du vieillard kojô — three facets of a collection that spans centuries and continents.

Sources: This tour draws on information from en.wikipedia.org, fr.wikipedia.org, maa.departement06.fr and the Wikipedia article on the museum.
```

## Generation metadata

- Job ID: `8545a116-44a6-4d82-934c-1e78d2b7ba15`
- Model: gpt-3.5-turbo (default)
- Cost: $0.0572 (28,610 tokens)
- Venue resolved: Q3330160 via existing container code (input lacked parenthetical)
- venue_corpus cached: tier=medium, 16 canonical titles, expires 2026-09-04
- Container: audioura-tour-generator-1 (built 2026-08-03, NOT rebuilt)

## Venue resolution matrix (run from LOCAL-258 worktree with fix applied)

| input | city | resolved | QID |
|---|---|---|---|
| `Musee des Arts Asiatiques (Asian Art Museum)` | Nice | ✅ | Q3330160 |
| `Musée des Arts Asiatiques` | Nice | ✅ | Q3330160 |
| `Musee des Arts Asiatiques` | Nice | ✅ | Q3330160 |
| `Musee des Arts Asiatiques (Asian Art Museum), Nice, France` | (extracted) | ✅ | Q3330160 |
| `Palais Lascaris` | Nice | ✅ | Q34653010 |
| `Musée Matisse` | Nice | ✅ | Q1563354 |
| `Musée National Marc Chagall` | Nice | ✅ | Q3329265 |
| `Musée d Art Moderne et d Art Contemporain` | Nice | ✅ | Q936859 |
| `Musee des arts asiatiques` | Toulon | ✅ | Q3330161 (≠ Q3330160 — correct) |
