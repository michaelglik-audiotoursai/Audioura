"""place_kinds.py — LOCAL-874 / D767: the single source of truth for a stop's KIND.

``classify(name, type_label, places_category, wikidata_instance_of, language)``
returns ``{"group", "subtype", "confidence"}`` using Michael's typology:

  religious    Religious & Sacred Sites          church/cathedral/basilica, temple/shrine/pagoda, mosque
  royal        Royal & Governmental Seats        palace/chateau, castle/fortress/citadel
  performance  Performance & Cultural Arts       opera house/concert hall, theater/amphitheater
  maritime     Engineering & Maritime Structures pier/wharf/boardwalk, bridge/viaduct, lighthouse
  civic        Civic & Memorial Monuments        arch, tower/obelisk, mausoleum/tomb, monument
  peaks        Landscape: Elevations & Structural Peaks   mountain/volcano/ridge, cliff/butte/monolith
  depression   Landscape: Erosional & Subterranean        canyon/gorge/rift, cave/cavern
  water        Landscape: Aqueous & Hydrological          waterfall, bay/fjord/sound, reef/atoll, lake, island
  other_documented  park, garden, museum, library, ruins ... (documented, not in Michael's list)
  both         a FAMOUS market/gallery: landmark story AND business details
  business     bar/cafe/spa/hotel/... and an ordinary market/gallery
  street_area  street, walking street, alley, square, neighbourhood, district, quarter
  landmark_unknown   nothing matched: NEVER defaulted to business

Order of evidence: (a) Wikidata P31, (b) Places category, (c) name words,
(d) type label.  A name with a business word ("Palace Bar") stays a business.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

__all__ = ["classify", "kind_for_path", "research_angles", "query_hints",
           "BUSINESS_WORDS", "BUSINESS_WORDS_VI", "GROUPS", "ANGLES"]

# The CURRENT business list (user_stop_enrichment._BUSINESS_KINDS) minus the
# words moved out: street/walking/nightlife -> street_area, market/gallery ->
# both-or-business, venue/music/live -> activity words, ignored.
BUSINESS_WORDS = [
    "bar", "pub", "club", "lounge", "restaurant", "cafe", "café", "coffee",
    "bistro", "diner", "eatery", "grill", "karaoke", "nightclub", "brewery",
    "taproom", "spa", "salon", "massage", "wellness", "studio", "gym", "shop",
    "store", "boutique", "bakery", "patisserie", "teahouse", "izakaya",
    "tavern", "speakeasy", "hotel", "hostel", "cocktail", "food",
]
# Vietnamese equivalents (noun-first: "Quán X", "Nhà hàng X").
BUSINESS_WORDS_VI = [
    "quán", "quán bar", "quán nhậu", "quán cà phê", "nhà hàng", "cà phê",
    "tiệm", "khách sạn", "nhà nghỉ", "tiệm bánh", "quán ăn", "trà sữa",
]
_BUSINESS_OTHER = [
    "restaurante", "ristorante", "trattoria", "pizzeria", "brasserie",
    "boulangerie", "bodega", "cerveceria", "ресторан", "кафе", "бар", "отель",
    "гостиница", "kneipe", "gasthaus",
]
_MARKET_EN = {"market", "bazaar", "gallery", "marche", "mercado", "mercato",
              "markt", "galerie", "galeria", "galleria", "рынок", "базар", "галерея"}
_MARKET_HEAD = [("cho",), ("phong", "tranh")]
# Describe the ACTIVITY, not the kind: ignored for the decision.
_IGNORED_WORDS = {"venue", "music", "live"}

# (group, subtype, {lang: [words]}).  Modes: en = anywhere (last match wins);
# vi/fr/es/it = head (first word after articles); de = suffix; ru = stem.
_T = [
    ("religious", "church", {
        "en": ["church", "cathedral", "basilica", "chapel", "abbey", "monastery", "synagogue"],
        "vi": ["nhà thờ", "thánh đường", "giáo đường", "tu viện"],
        "fr": ["église", "cathédrale", "basilique", "chapelle", "abbaye"],
        "es": ["iglesia", "catedral", "basílica", "capilla", "abadía", "monasterio"],
        "it": ["chiesa", "cattedrale", "duomo", "abbazia"],
        "de": ["kirche", "dom", "münster", "kapelle", "kathedrale", "kloster"],
        "ru": ["церковь", "церкви", "собор", "костел", "монастыр", "часовн"]}),
    ("religious", "temple", {
        "en": ["temple", "shrine", "pagoda", "stupa", "joss house"],
        "vi": ["chùa", "đền", "miếu", "điện", "thiền viện", "văn miếu"],
        "fr": ["temple", "pagode", "sanctuaire"],
        "es": ["templo", "santuario"],
        "it": ["tempio", "santuario"],
        "de": ["tempel", "pagode", "schrein"],
        "ru": ["храм", "пагод", "святилищ"]}),
    ("religious", "mosque", {
        "en": ["mosque", "masjid"],
        "vi": ["thánh đường hồi giáo", "nhà thờ hồi giáo"],
        "fr": ["mosquée"], "es": ["mezquita"], "it": ["moschea"],
        "de": ["moschee"], "ru": ["мечет"]}),
    ("royal", "palace", {
        "en": ["palace", "chateau", "château"],
        "vi": ["dinh", "cung điện", "hoàng cung", "đại nội", "hoàng thành", "lâu đài"],
        "fr": ["palais", "château"], "es": ["palacio"], "it": ["palazzo", "reggia"],
        "de": ["palast", "schloss", "residenz"], "ru": ["дворец", "дворц"]}),
    ("royal", "castle", {
        "en": ["castle", "fortress", "citadel", "fort", "kremlin", "stronghold"],
        "vi": ["thành", "pháo đài", "thành cổ", "cổ thành"],
        "fr": ["forteresse", "citadelle", "fort"],
        "es": ["castillo", "fortaleza", "ciudadela", "alcázar"],
        "it": ["castello", "fortezza", "cittadella", "rocca"],
        "de": ["burg", "festung", "zitadelle"],
        "ru": ["замок", "замк", "крепост", "кремль", "цитадел"]}),
    ("performance", "opera_house", {
        "en": ["opera house", "opera", "concert hall", "philharmonic", "symphony hall", "playhouse"],
        "vi": ["nhà hát lớn", "nhà hát opera", "nhà hát giao hưởng"],
        "fr": ["opéra", "salle de concert", "philharmonie"],
        "es": ["ópera", "teatro de la ópera", "sala de conciertos"],
        "it": ["teatro dell'opera", "teatro alla scala", "sala concerti"],
        "de": ["oper", "opernhaus", "konzerthaus", "philharmonie"],
        "ru": ["опер", "филармони"]}),
    ("performance", "theater", {
        "en": ["theater", "theatre", "amphitheater", "amphitheatre", "colosseum", "coliseum"],
        "vi": ["nhà hát", "đấu trường", "rạp"],
        "fr": ["théâtre", "amphithéâtre"], "es": ["teatro", "anfiteatro", "coliseo"],
        "it": ["teatro", "anfiteatro", "colosseo"],
        "de": ["theater", "amphitheater"], "ru": ["театр", "амфитеатр", "колизей"]}),
    ("maritime", "pier", {
        "en": ["pier", "wharf", "quay", "boardwalk", "jetty", "harbour", "harbor", "dock", "esplanade"],
        "vi": ["bến tàu", "bến", "cầu cảng", "bến cảng", "cảng"],
        "fr": ["quai", "jetée", "embarcadère"],
        "es": ["muelle", "malecón", "embarcadero"],
        "it": ["molo", "banchina", "pontile", "lungomare"],
        "de": ["pier", "kai", "steg", "hafen", "seebrücke"],
        "ru": ["пирс", "причал", "пристан", "порт"]}),
    ("maritime", "bridge", {
        "en": ["bridge", "viaduct", "aqueduct", "overpass"],
        "vi": ["cầu"],
        "fr": ["pont", "viaduc", "aqueduc"], "es": ["puente", "viaducto", "acueducto"],
        "it": ["ponte", "viadotto", "acquedotto"],
        "de": ["brücke", "viadukt", "aquädukt"], "ru": ["мост", "виадук", "акведук"]}),
    ("maritime", "lighthouse", {
        "en": ["lighthouse", "light house", "beacon"],
        "vi": ["hải đăng", "ngọn hải đăng"],
        "fr": ["phare"], "es": ["faro"], "it": ["faro"],
        "de": ["leuchtturm"], "ru": ["маяк"]}),
    ("civic", "arch", {
        "en": ["triumphal arch", "arch", "arc de triomphe", "city gate"],
        "vi": ["khải hoàn môn", "cổng chào"],
        "fr": ["arc de triomphe", "arc"], "es": ["arco de triunfo", "arco"],
        "it": ["arco di trionfo", "arco"], "de": ["triumphbogen", "torbogen"],
        "ru": ["триумфальн", "арка"]}),
    ("civic", "tower", {
        "en": ["tower", "obelisk", "belfry", "clock tower", "campanile"],
        "vi": ["tháp", "cột cờ", "bảo tháp"],
        "fr": ["tour", "obélisque"], "es": ["torre", "obelisco"],
        "it": ["torre", "obelisco", "campanile"],
        "de": ["turm", "obelisk", "fernsehturm"], "ru": ["башн", "обелиск", "колокольн"]}),
    ("civic", "mausoleum", {
        "en": ["mausoleum", "tomb", "tombs", "crypt", "sepulchre", "sarcophagus"],
        "vi": ["lăng", "mộ", "lăng mộ"],
        "fr": ["mausolée", "tombeau", "crypte"], "es": ["mausoleo", "tumba", "cripta"],
        "it": ["mausoleo", "tomba", "cripta"],
        "de": ["mausoleum", "grab", "gruft", "grabmal"],
        "ru": ["мавзолей", "гробниц", "усыпальниц", "склеп"]}),
    ("civic", "monument", {
        "en": ["monument", "memorial", "statue", "cenotaph", "war memorial"],
        "vi": ["tượng đài", "đài tưởng niệm", "tượng"],
        "fr": ["monument", "mémorial", "statue"], "es": ["monumento", "memorial", "estatua"],
        "it": ["monumento", "memoriale", "statua"],
        "de": ["denkmal", "mahnmal", "gedenkstätte"],
        "ru": ["памятник", "мемориал", "монумент"]}),
    ("peaks", "mountain", {
        "en": ["mountain", "mountains", "volcano", "ridge", "peak", "hill", "summit", "massif"],
        "vi": ["núi", "đỉnh", "núi lửa", "dãy núi", "đồi", "đèo"],
        "fr": ["montagne", "mont", "volcan", "crête", "pic", "colline"],
        "es": ["montaña", "monte", "volcán", "cordillera", "sierra", "cerro"],
        "it": ["montagna", "monte", "vulcano", "cresta", "colle"],
        "de": ["berg", "gebirge", "vulkan", "grat", "gipfel"],
        "ru": ["гора", "вулкан", "хребет", "пик", "сопка"]}),
    ("peaks", "cliff", {
        "en": ["cliff", "cliffs", "butte", "monolith", "bluff", "escarpment", "mesa"],
        "vi": ["vách đá", "mỏm đá"],
        "fr": ["falaise", "falaises", "butte", "monolithe", "rocher"],
        "es": ["acantilado", "acantilados", "monolito", "peñón"],
        "it": ["scogliera", "falesia", "monolito", "rupe"],
        "de": ["klippe", "felsen", "monolith"],
        "ru": ["утес", "скала", "скалы", "монолит", "обрыв"]}),
    ("depression", "canyon", {
        "en": ["canyon", "gorge", "rift", "ravine", "chasm", "valley"],
        "vi": ["hẻm núi", "hẻm vực", "thung lũng", "vực"],
        "fr": ["canyon", "gorge", "gorges", "ravin", "vallée"],
        "es": ["cañón", "garganta", "barranco", "desfiladero", "valle"],
        "it": ["canyon", "gola", "forra", "burrone", "valle"],
        "de": ["schlucht", "klamm", "canyon"],
        "ru": ["каньон", "ущелье", "ущель", "расселина", "долина"]}),
    ("depression", "cave", {
        "en": ["cave", "caves", "cavern", "caverns", "grotto", "sinkhole"],
        "vi": ["hang", "động", "hang động", "thạch động"],
        "fr": ["grotte", "grottes", "caverne", "gouffre"],
        "es": ["cueva", "cuevas", "caverna", "gruta"],
        "it": ["grotta", "grotte", "caverna"],
        "de": ["höhle", "grotte"], "ru": ["пещер", "грот"]}),
    ("water", "waterfall", {
        "en": ["waterfall", "waterfalls", "falls", "cascade", "cascades"],
        "vi": ["thác", "thác nước"],
        "fr": ["chute", "chutes", "cascade", "cascades"],
        "es": ["cascada", "catarata", "cataratas", "salto"],
        "it": ["cascata", "cascate", "cataratta"],
        "de": ["wasserfall", "wasserfälle"], "ru": ["водопад", "каскад"]}),
    ("water", "bay", {
        "en": ["bay", "fjord", "fiord", "sound", "cove", "gulf", "lagoon", "strait", "inlet"],
        "vi": ["vịnh", "vũng", "vụng", "đầm phá", "eo biển"],
        "fr": ["baie", "fjord", "golfe", "anse", "lagon", "détroit", "calanque"],
        "es": ["bahía", "fiordo", "golfo", "ensenada", "laguna", "estrecho", "cala"],
        "it": ["baia", "fiordo", "golfo", "insenatura", "laguna", "stretto"],
        "de": ["bucht", "fjord", "golf", "lagune", "meerenge", "sund"],
        "ru": ["залив", "бухт", "фьорд", "лагун", "пролив"]}),
    ("water", "reef", {
        "en": ["reef", "atoll", "coral reef"],
        "vi": ["rạn san hô", "rạn", "đảo san hô"],
        "fr": ["récif", "atoll", "barrière de corail"], "es": ["arrecife", "atolón"],
        "it": ["barriera corallina", "atollo"],
        "de": ["riff", "atoll", "korallenriff"], "ru": ["риф", "атолл"]}),
    ("water", "lake", {
        "en": ["lake", "pond", "river", "spring", "hot spring"],
        "vi": ["hồ", "sông", "suối", "giếng"],
        "fr": ["lac", "étang", "rivière", "fleuve", "source"],
        "es": ["lago", "río", "estanque", "manantial"],
        "it": ["lago", "stagno", "fiume", "sorgente"],
        "de": ["see", "teich", "fluss", "quelle"],
        "ru": ["озеро", "озер", "пруд", "река", "реки", "родник"]}),
    ("water", "island", {
        "en": ["island", "islands", "islet", "isle", "archipelago", "cay"],
        "vi": ["đảo", "quần đảo", "hòn", "cù lao"],
        "fr": ["île", "îles", "îlot", "archipel"], "es": ["isla", "islas", "islote", "archipiélago"],
        "it": ["isola", "isole", "isolotto", "arcipelago"],
        "de": ["insel", "inseln", "archipel"], "ru": ["остров", "архипелаг"]}),
    ("other_documented", "museum", {
        "en": ["museum", "art museum", "exhibition hall"],
        "vi": ["bảo tàng", "nhà truyền thống", "nhà lưu niệm", "di tích"],
        "fr": ["musée"], "es": ["museo"], "it": ["museo"], "de": ["museum"], "ru": ["музей"]}),
    ("other_documented", "park", {
        "en": ["park", "garden", "gardens", "botanical garden", "zoo", "national park", "reserve", "beach"],
        "vi": ["công viên", "vườn", "thảo cầm viên", "vườn quốc gia", "bãi biển"],
        "fr": ["parc", "jardin", "jardins", "plage"], "es": ["parque", "jardín", "jardines", "playa"],
        "it": ["parco", "giardino", "giardini", "spiaggia"], "de": ["park", "garten", "strand"],
        "ru": ["парк", "сад", "зоопарк", "пляж"]}),
    ("other_documented", "historic", {
        "en": ["library", "university", "observatory", "ruins", "ruin", "cemetery", "heritage",
               "historic", "historical", "landmark", "archaeological", "city hall", "town hall",
               "post office", "railway station", "train station"],
        "vi": ["thư viện", "đại học", "tàn tích", "phế tích", "nhà cổ", "ủy ban nhân dân", "bưu điện", "nhà ga"],
        "fr": ["bibliothèque", "université", "ruines", "cimetière", "hôtel de ville", "gare"],
        "es": ["biblioteca", "universidad", "ruinas", "cementerio", "ayuntamiento", "estación"],
        "it": ["biblioteca", "università", "rovine", "cimitero", "municipio", "stazione"],
        "de": ["bibliothek", "universität", "ruine", "friedhof", "rathaus", "bahnhof"],
        "ru": ["библиотек", "университет", "руины", "кладбищ", "ратуша", "вокзал"]}),
    ("street_area", "street", {
        "en": ["street", "walking street", "pedestrian street", "road", "avenue", "alley", "alleyway",
               "lane", "boulevard", "square", "plaza", "neighbourhood", "neighborhood", "district",
               "quarter", "old quarter", "old town", "nightlife", "walking", "promenade", "ward"],
        "vi": ["phố đi bộ", "phố", "đường", "ngõ", "ngách", "hẻm", "khu", "phường", "quảng trường",
               "khu phố", "đường sách", "phố cổ", "xóm"],
        "fr": ["rue", "ruelle", "avenue", "boulevard", "place", "quartier", "passage", "impasse"],
        "es": ["calle", "callejón", "avenida", "plaza", "barrio", "paseo", "rambla", "distrito"],
        "it": ["via", "vicolo", "viale", "piazza", "quartiere", "corso", "rione"],
        "de": ["straße", "strasse", "gasse", "allee", "platz", "viertel", "bezirk"],
        "ru": ["улица", "улиц", "переулок", "проспект", "площадь", "площад", "квартал", "район", "бульвар"]}),
]

GROUPS = sorted({g for g, _, _ in _T} | {"business", "both", "landmark_unknown"})

# P31 QIDs of the resolved entity (only ones I am certain of).
_QID: Dict[str, Tuple[str, str]] = {
    "Q16970": ("religious", "church"), "Q2977": ("religious", "church"),
    "Q108325": ("religious", "church"), "Q44539": ("religious", "temple"),
    "Q5393308": ("religious", "temple"), "Q32815": ("religious", "mosque"),
    "Q16560": ("royal", "palace"), "Q23413": ("royal", "castle"),
    "Q57821": ("royal", "castle"), "Q153562": ("performance", "opera_house"),
    "Q24354": ("performance", "theater"), "Q12280": ("maritime", "bridge"),
    "Q863454": ("maritime", "pier"), "Q39715": ("maritime", "lighthouse"),
    "Q12518": ("civic", "tower"), "Q4989906": ("civic", "monument"),
    "Q8502": ("peaks", "mountain"), "Q8072": ("peaks", "mountain"),
    "Q35509": ("depression", "cave"), "Q34038": ("water", "waterfall"),
    "Q39594": ("water", "bay"), "Q131681": ("water", "reef"),
    "Q23397": ("water", "lake"), "Q23442": ("water", "island"),
    "Q33506": ("other_documented", "museum"), "Q22698": ("other_documented", "park"),
}

_ARTICLES = {"the", "a", "an", "le", "la", "les", "el", "los", "las", "il", "lo", "l",
             "der", "die", "das"}
_CONF = {"wikidata": 0.95, "category": 0.85, "name": 0.75, "type": 0.6, "unknown": 0.2}


def _fold(text) -> str:
    raw = str(text or "").lower().replace("đ", "d").replace("ß", "ss")
    nfkd = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _toks(text) -> List[str]:
    return _fold(text).replace("ho chi minh", "hcm").split()


def _build():
    tbl = {"en": [], "head": [], "de": [], "ru": []}
    for g, sub, langs in _T:
        for lang, words in langs.items():
            mode = lang if lang in ("en", "de", "ru") else "head"
            for w in words:
                tk = tuple(_toks(w))
                if tk:
                    tbl[mode].append((tk, g, sub))
    return tbl


_TABLE = _build()
_BIZ_EN = {_fold(w) for w in BUSINESS_WORDS} | {_fold(w) for w in _BUSINESS_OTHER}
_BIZ_VI = [tuple(_toks(w)) for w in BUSINESS_WORDS_VI]


def _head(toks: List[str]) -> int:
    i = 0
    while i < len(toks) - 1 and toks[i] in _ARTICLES:
        i += 1
    return i


def _find(toks, tk, start=0) -> int:
    n = len(tk)
    for i in range(start, len(toks) - n + 1):
        if tuple(toks[i:i + n]) == tk:
            return i
    return -1


def _is_business(toks: List[str]) -> bool:
    if not toks:
        return False
    if any(t in _BIZ_EN for t in toks):
        return True
    h = _head(toks)
    return any(_find(toks, p) == h for p in _BIZ_VI)


def _is_market(toks: List[str]) -> bool:
    if any(t in _MARKET_EN for t in toks):
        return True
    h = _head(toks)
    return any(_find(toks, p) == h for p in _MARKET_HEAD)


def _match(toks: List[str]) -> Optional[Tuple[str, str]]:
    """Head word (noun-first Vietnamese/Romance) beats an English word anywhere;
    among English words the LAST wins ('Cathedral Square' is a square) within the
    part before ' of ' ('Temple of Literature' is a temple)."""
    if not toks:
        return None
    h = _head(toks)
    best = None
    for tk, g, sub in _TABLE["head"]:
        if _find(toks, tk) == h and (best is None or len(tk) > best[0]):
            best = (len(tk), g, sub)
    if best:
        return best[1], best[2]
    if toks[h] in ("mount", "mt", "mont", "monte") and len(toks) > h + 1:
        return "peaks", "mountain"
    cut = toks.index("of") if "of" in toks[1:] else len(toks)
    for scope in (toks[:cut], toks):
        found = None
        for tk, g, sub in _TABLE["en"]:
            last, j = -1, _find(scope, tk)
            while j >= 0:
                last, j = j, _find(scope, tk, j + 1)
            if last >= 0 and (found is None or (last, len(tk)) > (found[0], found[1])):
                found = (last, len(tk), g, sub)
        if found:
            return found[2], found[3]
    for t in toks:
        for tk, g, sub in _TABLE["de"]:
            s = tk[0] if len(tk) == 1 else ""
            if s and (t == s or (len(s) >= 5 and t.endswith(s))):
                return g, sub
    for t in toks:
        if t.isascii():
            continue
        for tk, g, sub in _TABLE["ru"]:
            if len(tk) == 1 and len(tk[0]) >= 3 and t.startswith(tk[0]):
                return g, sub
    return None


def _res(g, sub, how) -> Dict:
    return {"group": g, "subtype": sub, "confidence": _CONF[how]}


_FAMOUS_MARKETS = ("ben thanh", "dong xuan", "binh tay", "borough market", "la boqueria",
                   "pike place", "grand bazaar", "tsukiji", "chatuchak", "central market",
                   "mercado de san miguel", "marche aux puces", "naschmarkt", "campo de fiori")


def _famous(name: str) -> bool:
    f = _fold(name)
    if any(m in f for m in _FAMOUS_MARKETS):
        return True
    try:
        from landmark_reference import lookup
        return bool(lookup(name))
    except Exception:
        return False


def _from_wikidata(p31):
    if not p31:
        return None
    if isinstance(p31, (list, tuple, set)):
        p31 = ",".join(str(x) for x in p31)
    parts = [p.strip() for p in re.split(r"[,;|]", str(p31)) if p.strip()]
    for p in parts:
        q = re.search(r"Q\d+", p)
        if q and q.group(0) in _QID:
            return _QID[q.group(0)]
    for p in parts:
        toks = _toks(p)
        if toks and not _is_business(toks):
            m = _match(toks)
            if m:
                return m
    return None


def classify(name: str, type_label: str = "", places_category: str = "",
             wikidata_instance_of: str = "", language: str = "") -> Dict:
    """-> {group, subtype, confidence}.  Unknown -> landmark_unknown, never business."""
    ntoks = _toks(name)
    nb = _is_business(ntoks)
    # (a) Wikidata P31 of the resolved entity (a business-word name still wins)
    wd = _from_wikidata(wikidata_instance_of)
    if wd and not nb:
        return _res(wd[0], wd[1], "wikidata")
    # (b) Places category
    ctoks = [t for t in _toks(places_category) if t not in _IGNORED_WORDS]
    if ctoks:
        if _is_business(ctoks):
            return _res("business", "business", "category")
        m = _match(ctoks)
        if m and not nb:
            return _res(m[0], m[1], "category")
    # (c) name words
    if nb:
        return _res("business", next((t for t in ntoks if t in _BIZ_EN), "business"), "name")
    if _is_market(ntoks):
        return _res("both" if _famous(name) else "business", "market", "name")
    ttoks = [t for t in _toks(type_label) if t not in _IGNORED_WORDS]
    tb = _is_business(ttoks)
    m = _match(ntoks)
    if m:
        # a hard-business TYPE beats a landmark word in the name unless the
        # landmark table knows the place (a restaurant called "Pagoda")
        if tb and m[0] != "street_area" and not _famous(name):
            return _res("business", "business", "type")
        return _res(m[0], m[1], "name")
    # (d) type label
    if tb:
        return _res("business", "business", "type") if not _famous(name) else \
            _res("landmark_unknown", "landmark", "name")
    if _is_market(ttoks):
        return _res("both" if _famous(name) else "business", "market", "type")
    m = _match(ttoks)
    if m:
        return _res(m[0], m[1], "type")
    if _famous(name):
        return _res("landmark_unknown", "landmark", "name")
    return _res("landmark_unknown", "unknown", "unknown")


def kind_for_path(info_or_name, *args, **kw) -> str:
    """Coarse path: 'business' | 'landmark' | 'street_area' | 'both'."""
    info = info_or_name if isinstance(info_or_name, dict) else classify(info_or_name, *args, **kw)
    g = info["group"]
    return g if g in ("business", "street_area", "both") else "landmark"


ANGLES: Dict[str, Dict] = {
    "religious": {"angles": ["founding and who founded it", "faith / denomination / tradition",
                             "architecture and notable features", "rituals, festivals and visiting etiquette"],
                  "query": ["history founded", "architecture", "festival ritual"]},
    "royal": {"angles": ["who built it and why", "the power it held and who ruled or lived there",
                         "events that happened there", "architecture and later use"],
              "query": ["history built by", "architecture", "events"]},
    "performance": {"angles": ["architect and style", "opening", "famous performances (SOURCED only, per LOCAL-872)",
                               "what it hosts today"],
                    "query": ["architect opened", "history performances"]},
    "maritime": {"angles": ["purpose of the structure", "trade / transport history", "engineering and materials",
                            "what it is used for now"],
                 "query": ["history built purpose", "engineering", "trade history"]},
    "civic": {"angles": ["what it commemorates", "whom it commemorates", "who built it and when",
                         "symbolism and ceremonies held there"],
              "query": ["commemorates history", "built by", "symbolism"]},
    "peaks": {"angles": ["formation and geology", "ecology", "human history and use",
                         "legends (disclosed per D760)"],
              "query": ["geology formation", "ecology", "legend history"]},
    "depression": {"angles": ["formation and geology", "ecology and wildlife", "human history and exploration",
                              "legends (disclosed per D760)"],
                   "query": ["geology formation", "exploration history", "legend"]},
    "water": {"angles": ["formation and geology", "ecology", "human history and use",
                         "legends (disclosed per D760)"],
              "query": ["geology formation", "ecology", "legend history"]},
    "street_area": {"angles": ["where the name comes from (if a person: who they were, sourced)",
                               "history of the street or area", "what it is known for now",
                               "2-4 notable places ALONG it (sourced; no separate pin)", "the best time to go"],
                    "query": ["name origin history", "known for", "best time to visit"]},
    "other_documented": {"angles": ["history and founding", "what it holds or offers", "why it matters"],
                         "query": ["history"]},
    "landmark_unknown": {"angles": ["history and founding", "what it is known for", "why it matters"],
                         "query": ["history"]},
    "both": {"angles": ["the market/gallery's history and fame", "hours, what is sold or shown, reviews"],
             "query": ["history", "opening hours"]},
}


def research_angles(info_or_group) -> List[str]:
    g = info_or_group["group"] if isinstance(info_or_group, dict) else info_or_group
    return list((ANGLES.get(g) or {}).get("angles", []))


def query_hints(info_or_group) -> List[str]:
    """Short suffixes for search queries ('<name> <city> <hint>')."""
    g = info_or_group["group"] if isinstance(info_or_group, dict) else info_or_group
    return list((ANGLES.get(g) or {}).get("query", []))
