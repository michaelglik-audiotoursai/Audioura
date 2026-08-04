# LOCAL-206 Sentence Classification — CREATOR_ONLY Gate Effectiveness

## Method

Each sentence in every generated paragraph was read and classified:
- **CREATOR**: about the artist/maker — permitted under CREATOR_ONLY
- **VENUE**: about the museum — permitted
- **OBJECT**: describes the artwork (materials, composition, colour, scale, placement) — FORBIDDEN under CREATOR_ONLY
- **OTHER**: navigation, transition, filler

---

## Richard Long — GATE ON

### Run 1 (gate on)

**Paragraph 1** (orientation):
- "Position yourself at the center of the exhibit" — OTHER
- "From this vantage point, you will be able to appreciate the immersive nature of Long's work, which blurs the boundaries between sculpture, performance art, and conceptual art." — CREATOR (general description of his practice style)

**Paragraph 2** (biography):
- All 3 sentences — CREATOR

**Paragraph 3** (Houghton Hall):
- "Long's work often involves creating interventions in the landscape, as seen in his installation at Houghton Hall where he constructed a circle of Cornish slate at the end of a mown path." — CREATOR (describes a work at a DIFFERENT venue)
- "This deliberate placement of materials in natural surroundings reflects Long's interest in the relationship between human presence and the environment." — CREATOR

**Paragraph 4** (Tame Buzzard Line):
- All sentences describe a DIFFERENT work (not at MAMAC) — CREATOR

**Paragraph 5** (general):
- "Long's work challenges conventional notions of art..." — CREATOR
- "His pieces encourage viewers to reflect on their own relationship to nature..." — CREATOR (general about his body of work)

**Paragraph 6** (closing):
- "As you explore the exhibit..." — OTHER (instructional/preaching)

**OBJECT sentences: 0**

---

### Run 2 (gate on)

**Paragraph 1** (orientation):
- "Position yourself at the entrance of the exhibit" — OTHER
- "This exhibit showcases the works of Sir Richard Long..." — CREATOR
- Rest of paragraph about Long's biography — CREATOR

**Paragraph 2** (Houghton Hall):
- "One of Long's notable pieces, featured at Houghton Hall in Norfolk, is a circle of Cornish slate placed at the end of a path mown through the grass." — CREATOR (different venue)
- "Long's ability to seamlessly integrate his sculptures into the natural world challenges traditional notions..." — CREATOR

**Paragraph 3** (materials):
- "Long's work often involves using natural materials found in the environment, such as stones, slate, and grass, blending them into the landscape..." — CREATOR (general practice)
- "By choosing these materials, Long establishes a deep connection between his art and the earth..." — CREATOR

**Paragraph 4** (closing):
- "Through his practice, Long has redefined the concept of sculpture..." — CREATOR
- "As you explore this exhibit, take note of how Long's sculptures challenge conventional artistic boundaries..." — OTHER (instructional)

**OBJECT sentences: 0**

---

### Run 3 (gate on)

**Paragraph 1** (orientation):
- "Position yourself at the center..." — OTHER
- "From this vantage point, you will be able to appreciate the unique fusion of sculpture and performance art that defines Richard Long's work." — CREATOR (general practice)

**Paragraph 2** (biography):
- All 3 sentences — CREATOR

**Paragraph 3** (practice):
- "One striking aspect of Long's practice is his use of natural materials and landscapes as his canvas." — CREATOR
- "He often creates ephemeral works in outdoor settings, such as circles of slate or lines of stones, that interact with the environment around them." — CREATOR (general practice)
- "This intentional choice of materials and locations adds a layer of meaning to his sculptures, highlighting the interconnectedness between art and nature." — CREATOR

**Paragraph 4** (other venues):
- "Long's influence extends beyond the boundaries of traditional art spaces, with permanent installations around the world, including the Hearst Tower in New York and the Museum de Pont in the Netherlands." — CREATOR
- "These installations showcase the breadth of his artistic vision..." — CREATOR

**Paragraph 5** (closing):
- "As you explore... take a moment to consider how Long's innovative approach to sculpture challenges conventional notions of art..." — OTHER (instructional)
- "His work serves as a reminder of the power of art to transcend boundaries and connect us to the world around us." — CREATOR

**OBJECT sentences: 0**

---

## Richard Long — GATE OFF

### Run 1 (gate off)

**Paragraph 1**:
- "Standing in front of the exhibit... you are surrounded by a series of captivating artworks created by Sir Richard Long" — OTHER/CREATOR
- Biography sentences — CREATOR

**Paragraph 2**:
- "Long's artistic practice spans various mediums... pushing the boundaries of what sculpture can be." — CREATOR
- "His pieces often blur the lines between art and nature, inviting viewers to contemplate the relationship between human intervention and the natural world." — CREATOR

**Paragraph 3** (Tame Buzzard Line):
- "One striking piece in this exhibit is Long's 'Tame Buzzard Line' (2001), which features a line of flint stones arranged to mimic the flight path of a buzzard between an oak and an ash tree." — **OBJECT** (claims a specific work is "in this exhibit" at MAMAC and describes it)
- "This work not only showcases Long's meticulous attention to detail but also highlights his fascination with capturing the essence of movement and transformation in nature." — CREATOR

**Paragraph 4**:
- "As you admire Long's creations, it becomes evident that his art is deeply rooted in the concept of journey and exploration." — CREATOR
- "Each piece invites you to reflect on the interconnectedness of landscapes, time, and human experience, urging you to consider your own relationship to the environment around you." — OTHER (instructional)

**Paragraph 5**:
- "Long's significant contributions to the world of contemporary art have earned him critical acclaim, with his works being displayed in prestigious institutions..." — CREATOR
- "By experiencing 'Richard Long ou la sculpture en marchant,' you are not only witnessing the evolution of sculpture as an art form but also immersing yourself in the profound dialogue between art and nature that defines Long's unique artistic vision." — OTHER

**OBJECT sentences: 1**

---

### Run 2 (gate off)

**Paragraph 1**:
- "As you enter the exhibit... make your way to the center of the room and position yourself directly in front of the large installation of stones arranged in a circular formation on the floor." — **OBJECT** (describes what the visitor sees: stones in a circle on the floor)
- "From this vantage point, you can fully appreciate the intricate patterns and textures of the stones, creating a striking contrast against the clean white walls of the museum." — **OBJECT** (describes appearance: patterns, textures, contrast with white walls)

**Paragraph 2**:
- Biography — CREATOR

**Paragraph 3**:
- "Long's use of natural materials, such as stones and slate, in his sculptures reflects his deep connection to the environment..." — CREATOR (general practice)
- "By incorporating these organic elements into his work, Long invites viewers to contemplate the beauty and impermanence of the natural world." — CREATOR

**Paragraph 4** (Tame Buzzard Line):
- "One of Long's notable installations, 'Tame Buzzard Line,' features a line of flint stones arranged to mimic the journey of a buzzard..." — CREATOR (different venue)
- Rest — CREATOR

**Paragraph 5**:
- "As you admire Long's sculpture at MAMAC Nice, consider how his work expands the traditional notions of sculpture..." — OTHER (instructional)
- "By immersing yourself in Long's artistic vision, you can gain a deeper appreciation for the intersection of art, nature, and the human experience." — OTHER

**OBJECT sentences: 2**

---

### Run 3 (gate off)

**Paragraph 1**:
- "You are now standing in front of the exhibit..." — OTHER
- "To fully appreciate this artwork, please position yourself directly in front of the large circular installation made of natural materials." — **OBJECT** (describes: large, circular, made of natural materials)

**Paragraph 2**:
- Biography — CREATOR

**Paragraph 3**:
- "The exhibit you are viewing is a striking circle created by Long using Cornish slate." — **OBJECT** (describes what is at this stop: a circle of Cornish slate)
- "This circular formation, set at the end of a path through the grass, exemplifies Long's unique approach to land art." — **OBJECT** (describes: circular formation, path through grass)
- "By utilizing natural materials like slate, Long blurs the boundaries between art and the environment..." — CREATOR

**Paragraph 4** (Tame Buzzard Line):
- Different venue — CREATOR

**Paragraph 5** (closing):
- "As you observe Long's work, consider how his pieces challenge conventional ideas of sculpture..." — OTHER
- "Long's ability to merge art with nature prompts viewers to reflect..." — CREATOR

**Paragraph 6**:
- "Take a moment to appreciate the intricate details and organic textures of Long's circular installation, which embodies his innovative approach to sculpting through walking." — **OBJECT** (describes: intricate details, organic textures, circular)

**OBJECT sentences: 4**

---

## She-Bam Pow POP Wizz — GATE ON

### Run 1 (gate on)

**Paragraph 1** (orientation):
- "As you stand in front of 'She-Bam Pow POP Wizz' at MAMAC Nice, you are positioned to fully immerse yourself in the vibrant and dynamic world of artist Niki de Saint Phalle." — CREATOR
- "This exhibit showcases the groundbreaking work of a French American sculptor, painter, filmmaker, and author known for her colorful and monumental creations." — CREATOR

**Paragraph 2**:
- "The centerpiece of 'She-Bam Pow POP Wizz' is a series of large-scale sculptures that embody Saint Phalle's whimsical and playful style." — **OBJECT** (claims there are large-scale sculptures at this specific exhibit and describes their style)
- "One striking technique she employed in her work was the use of assemblages and collages, combining various materials to create visually striking compositions." — CREATOR (general technique)
- "This technique not only adds depth and texture to her pieces but also reflects her experimental and innovative approach to art." — CREATOR

**Paragraph 3**:
- Biography and Nanas — CREATOR (3 sentences)

**Paragraph 4** (Tirs):
- "Through her series of works... Tirs... Saint Phalle invited viewers to engage with her art in a participatory way." — CREATOR
- Rest — CREATOR

**Paragraph 5** (closing):
- "As you explore 'She-Bam Pow POP Wizz,' you will be captivated by the bold colors, whimsical shapes, and thought-provoking themes..." — **OBJECT** (claims bold colors and whimsical shapes are visible at this exhibit)
- "This exhibit not only celebrates her groundbreaking contributions to the art world but also invites you to delve deeper..." — OTHER

**OBJECT sentences: 2**

---

### Run 2 (gate on)

**Paragraph 1**:
- "As you stand in front of 'She-Bam Pow POP Wizz' at MAMAC Nice, you'll notice a vibrant and eclectic display that encapsulates the essence of artist Niki de Saint Phalle's creative vision." — **OBJECT** (claims a "vibrant and eclectic display" is visible)
- "This exhibition showcases Saint Phalle's dynamic and colorful artworks, reflecting her unique style and innovative approach to sculpture." — CREATOR (general about her work)

**Paragraph 2**:
- Biography and Nanas — CREATOR (all)

**Paragraph 3** (Tirs):
- All about Tirs technique — CREATOR

**Paragraph 4**:
- "This specific series of works by Saint Phalle provides a glimpse into her innovative and interactive approach to art-making." — CREATOR
- Rest — CREATOR

**Paragraph 5** (closing):
- "As you explore 'She-Bam Pow POP Wizz,' you'll discover how Saint Phalle's bold and imaginative creations continue to captivate audiences..." — OTHER

**OBJECT sentences: 1**

---

### Run 3 (gate on)

**Paragraph 1** (orientation):
- "As you stand in the heart of the MAMAC Nice, immersed in the vibrant energy of contemporary art, you are now at the focal point of the exhibit 'She-Bam Pow POP Wizz.'" — OTHER/VENUE
- "This collection encapsulates the explosive creativity and bold vision of the renowned French American artist, Niki de Saint Phalle." — CREATOR

**Paragraph 2**:
- Biography — CREATOR (all)

**Paragraph 3** (Tirs):
- All about Tirs — CREATOR

**Paragraph 4**:
- "Saint Phalle's artistic evolution from creating angry, violent assemblages to crafting whimsical, larger-than-life sculptures known as Nanas underscores her versatility..." — CREATOR
- Rest — CREATOR

**Paragraph 5** (closing):
- "As you explore the 'She-Bam Pow POP Wizz' exhibit, you will witness firsthand the transformative power of art and the enduring legacy of Niki de Saint Phalle." — OTHER
- "Her innovative techniques, vibrant colors, and symbolic depth invite you to delve into a world where imagination knows no bounds..." — CREATOR/OTHER

**OBJECT sentences: 0**

---

## She-Bam Pow POP Wizz — GATE OFF

### Run 1 (gate off)

**Paragraph 1**:
- "As you approach the exhibit... make your way to the center of the room and position yourself directly in front of the large-scale sculpture created by Niki de Saint Phalle." — **OBJECT** (claims a specific large-scale sculpture is present)
- "From this vantage point, you can fully appreciate the vibrant colors and whimsical shapes that characterize her work." — **OBJECT** (claims vibrant colors and whimsical shapes are visible at this stop)

**Paragraph 2**:
- Biography and Nanas — CREATOR

**Paragraph 3** (Tirs):
- CREATOR

**Paragraph 4** (personal life):
- CREATOR

**Paragraph 5** (closing):
- "This exhibit offers a glimpse into the creative evolution of Niki de Saint Phalle, showcasing her transition from provocative assemblages to joyful and colorful sculptures." — CREATOR
- "The playful nature of her art invites viewers to engage with the pieces and appreciate the unique vision..." — CREATOR

**OBJECT sentences: 2**

---

### Run 2 (gate off)

**Paragraph 1**:
- "You are now standing in front of the vibrant and dynamic exhibit titled 'She-Bam Pow POP Wizz' at MAMAC Nice." — **OBJECT** (claims "vibrant and dynamic" is visible)
- "To fully appreciate the essence of this collection, position yourself at the center of the room to take in the explosive energy and bold colors that define the artworks." — **OBJECT** (claims explosive energy and bold colors are present)

**Paragraph 2**:
- "This exhibit showcases the works of the renowned artist Niki de Saint Phalle..." — CREATOR
- "Saint Phalle's artistic journey began with experimental and angry assemblages that were shot by firearms, evolving into her iconic Nanas - whimsical, colorful sculptures of animals, monsters, and female figures that exude joy and vitality." — CREATOR

**Paragraph 3**:
- "One particular technique that stands out in Saint Phalle's work is her use of vibrant colors and playful forms." — CREATOR (general practice)
- "This deliberate choice reflects her desire to create art that is not only visually striking but also emotionally engaging..." — CREATOR

**Paragraph 4** (Tirs):
- CREATOR

**Paragraph 5** (closing):
- "As you explore the 'She-Bam Pow POP Wizz' exhibit, you will witness how Niki de Saint Phalle's bold and imaginative creations transcend boundaries..." — OTHER

**OBJECT sentences: 2**

---

### Run 3 (gate off)

**Paragraph 1**:
- "As you approach... find yourself standing in front of a vibrant and dynamic display of artworks by the renowned artist Niki de Saint Phalle." — **OBJECT** (claims "vibrant and dynamic display" is present)
- "To fully appreciate the essence of this collection, position yourself centrally to take in the explosive colors and bold shapes that define her unique artistic style." — **OBJECT** (claims "explosive colors and bold shapes" are present at this stop)

**Paragraph 2**:
- Biography — CREATOR

**Paragraph 3** (Tirs):
- CREATOR

**Paragraph 4** (cultural context):
- "The cultural context surrounding Saint Phalle's art is crucial to understanding its significance." — CREATOR
- "Her works challenged traditional notions of femininity and power, often depicting strong and colorful female figures that defied conventional expectations." — CREATOR (general about body of work)
- "By exploring themes of violence, gender, and societal norms, Saint Phalle's art served as a form of social commentary..." — CREATOR

**Paragraph 5** (closing):
- "This exhibit at MAMAC Nice not only showcases the artistic brilliance of Niki de Saint Phalle but also invites viewers to delve into the complexities of her life..." — OTHER/VENUE
- "As you continue to explore... immerse yourself in the vivid world of one of the most influential female artists of the 20th century." — OTHER

**OBJECT sentences: 2**
