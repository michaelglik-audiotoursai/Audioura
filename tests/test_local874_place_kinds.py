"""LOCAL-874 / D767: place-kind taxonomy."""
import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import place_kinds as pk
import user_stop_enrichment as use


def _gs(name, **kw):
    r = pk.classify(name, **kw)
    return r["group"], r["subtype"]


MICHAEL = [
    # religious
    ("Notre-Dame Cathedral Basilica of Saigon", "religious", "church"),
    ("St Mary's Church", "religious", "church"), ("Chùa Một Cột", "religious", "temple"),
    ("Chua Mot Cot", "religious", "temple"), ("Đền Ngọc Sơn", "religious", "temple"),
    ("Nhà thờ Đức Bà", "religious", "church"), ("Thánh đường Hồi giáo Jamia", "religious", "mosque"),
    ("Senso-ji Temple", "religious", "temple"), ("Fushimi Inari Shrine", "religious", "temple"),
    ("Shwedagon Pagoda", "religious", "temple"), ("Blue Mosque", "religious", "mosque"),
    ("Cathédrale Notre-Dame", "religious", "church"), ("Église Saint-Eustache", "religious", "church"),
    ("Catedral de Sevilla", "religious", "church"), ("Mezquita de Córdoba", "religious", "mosque"),
    ("Duomo di Milano", "religious", "church"), ("Kölner Dom", "religious", "church"),
    ("Казанский собор", "religious", "church"), ("Голубая мечеть", "religious", "mosque"),
    # royal
    ("Independence Palace", "royal", "palace"), ("Dinh Độc Lập", "royal", "palace"),
    ("Château de Chambord", "royal", "palace"), ("Palacio Real", "royal", "palace"),
    ("Schloss Neuschwanstein", "royal", "palace"), ("Зимний дворец", "royal", "palace"),
    ("Edinburgh Castle", "royal", "castle"), ("Hue Citadel", "royal", "castle"),
    ("Castello Sforzesco", "royal", "castle"), ("Burg Eltz", "royal", "castle"),
    ("Cartagena Fortress", "royal", "castle"),
    # performance
    ("Saigon Opera House", "performance", "opera_house"), ("Sydney Concert Hall", "performance", "opera_house"),
    ("Nhà hát Lớn Hà Nội", "performance", "opera_house"), ("Globe Theatre", "performance", "theater"),
    ("Roman Amphitheatre", "performance", "theater"), ("Teatro Colón", "performance", "theater"),
    # maritime / engineering
    ("Bạch Đằng Pier", "maritime", "pier"), ("Santa Monica Pier", "maritime", "pier"),
    ("Fisherman's Wharf", "maritime", "pier"), ("Atlantic City Boardwalk", "maritime", "pier"),
    ("Golden Gate Bridge", "maritime", "bridge"), ("Cầu Rồng", "maritime", "bridge"),
    ("Millau Viaduct", "maritime", "bridge"), ("Pont Neuf", "maritime", "bridge"),
    ("Puente de Triana", "maritime", "bridge"), ("Hải đăng Vũng Tàu", "maritime", "lighthouse"),
    ("Cape Hatteras Lighthouse", "maritime", "lighthouse"), ("Phare d'Eckmühl", "maritime", "lighthouse"),
    ("Leuchtturm Roter Sand", "maritime", "lighthouse"), ("Quai de la Tournelle", "maritime", "pier"),
    # civic
    ("Arc de Triomphe", "civic", "arch"), ("Triumphal Arch of Orange", "civic", "arch"),
    ("Tháp Rùa", "civic", "tower"), ("Eiffel Tower", "civic", "tower"),
    ("Washington Monument", "civic", "monument"), ("Luxor Obelisk", "civic", "tower"),
    ("Lăng Chủ tịch Hồ Chí Minh", "civic", "mausoleum"), ("Taj Mahal Mausoleum", "civic", "mausoleum"),
    ("Tomb of Tu Duc", "civic", "mausoleum"),
    # landscape
    ("Mount Fuji", "peaks", "mountain"), ("Núi Bà Đen", "peaks", "mountain"),
    ("Mount Vesuvius Volcano", "peaks", "mountain"), ("Cliffs of Moher", "peaks", "cliff"),
    ("Devils Tower Monolith", "peaks", "cliff"), ("Grand Canyon", "depression", "canyon"),
    ("Antelope Gorge", "depression", "canyon"), ("Son Doong Cave", "depression", "cave"),
    ("Hang Sơn Đoòng", "depression", "cave"), ("Carlsbad Caverns", "depression", "cave"),
    ("Cueva de los Cristales", "depression", "cave"), ("Hạ Long Bay", "water", "bay"),
    ("Vịnh Hạ Long", "water", "bay"), ("Sognefjord", "water", "bay"),
    ("Niagara Waterfall", "water", "waterfall"), ("Thác Bản Giốc", "water", "waterfall"),
    ("Great Barrier Reef", "water", "reef"), ("Bikini Atoll", "water", "reef"),
    ("Hồ Gươm", "water", "lake"), ("Phu Quoc Island", "water", "island"),
    ("Đảo Phú Quốc", "water", "island"),
]


@pytest.mark.parametrize("name,group,sub", MICHAEL)
def test_michael_examples(name, group, sub):
    assert _gs(name) == (group, sub), name


def test_unknown_is_landmark_unknown_never_business():
    r = pk.classify("Zzxq")
    assert r["group"] == "landmark_unknown"
    assert pk.classify("")["group"] == "landmark_unknown"
    assert use.classify_stop_kind("Zzxq") == "landmark"


def test_wikidata_p31_and_category_order():
    assert pk.classify("Foo", wikidata_instance_of="Q39715")["group"] == "maritime"
    assert pk.classify("Foo", wikidata_instance_of="lighthouse, tourist attraction")["subtype"] == "lighthouse"
    assert pk.classify("Foo", places_category="Buddhist temple")["group"] == "religious"
    assert pk.classify("Foo", places_category="Cocktail bar")["group"] == "business"
    assert pk.classify("Foo", type_label="Pier")["group"] == "maritime"


def test_business_word_in_name_wins():
    for n in ("Palace Bar", "Temple Bar", "Cathedral Cafe", "Pier Restaurant", "Lighthouse Coffee"):
        assert pk.classify(n)["group"] == "business", n
    assert pk.classify("Palace Bar", wikidata_instance_of="Q16560")["group"] == "business"


BIZ_NAMES = {
    "bar": "Thi Bar", "pub": "The Red Pub", "club": "Lux Club", "lounge": "Sky Lounge",
    "restaurant": "Anan Restaurant", "cafe": "Cong Cafe", "café": "Le Café", "coffee": "Highlands Coffee",
    "bistro": "Le Bistro", "diner": "Joe Diner", "eatery": "Corner Eatery", "grill": "Hanoi Grill",
    "karaoke": "Vui Karaoke", "nightclub": "Apocalypse Nightclub", "brewery": "Heart of Darkness Brewery",
    "taproom": "East West Taproom", "spa": "An Spa", "salon": "Linh Salon", "massage": "Hoa Massage",
    "wellness": "Lotus Wellness", "studio": "Zen Studio", "gym": "California Gym", "shop": "Silk Shop",
    "store": "Book Store", "boutique": "Mai Boutique", "bakery": "Tous Bakery", "patisserie": "Paris Patisserie",
    "teahouse": "Jade Teahouse", "izakaya": "Ken Izakaya", "tavern": "Old Tavern",
    "speakeasy": "Hidden Speakeasy", "hotel": "Rex Hotel", "hostel": "Backpacker Hostel",
    "cocktail": "Layla Cocktail", "food": "Saigon Food",
}


def test_every_current_business_word_is_covered():
    assert set(BIZ_NAMES) == set(pk.BUSINESS_WORDS)


@pytest.mark.parametrize("word", sorted(BIZ_NAMES))
def test_every_business_word_classifies_business_and_takes_business_path(word):
    name = BIZ_NAMES[word]
    assert pk.classify(name)["group"] == "business", name
    assert use.classify_stop_kind(name) == "business", name
    assert use.classify_stop_kind(name, word) == "business"


@pytest.mark.parametrize("name", ["Quán Cà Phê Muối", "Nhà hàng Ngon", "Khách sạn Continental", "Nhà nghỉ Hoa",
                                  "Quán bar Chill", "Quán nhậu Tư Béo", "Tiệm bánh Mì", "Cà phê Trung Nguyên"])
def test_vietnamese_business(name):
    assert pk.classify(name)["group"] == "business", name


def test_street_area():
    for n, t in (("The Crazy street", "Walking street"), ("Book Street", ""), ("Nguyễn Huệ Walking Street", ""),
                 ("Bùi Viện", "Walking street"), ("Bui Vien", "Street with vibrant nightlife"),
                 ("Phố Tây", ""), ("Đường sách", ""), ("Hẻm 22", ""), ("Lam Son Square", ""),
                 ("Old Quarter", ""), ("Rue Montorgueil", ""), ("Calle Mayor", "")):
        assert pk.classify(n, t)["group"] == "street_area", n
        assert use.classify_stop_kind(n, t) == "street_area"
    # walking/nightlife/street are no longer business words
    assert not ({"street", "walking", "nightlife", "market", "gallery", "venue", "music", "live"}
                & set(pk.BUSINESS_WORDS))


def test_market_gallery_both_or_business():
    assert pk.classify("Ben Thanh Market")["group"] == "both"
    assert use.classify_stop_kind("Ben Thanh Market") == "both"
    assert pk.classify("Joe's Local Market")["group"] == "business"
    assert pk.classify("Corner Gallery")["group"] == "business"


def test_activity_words_ignored():
    assert pk.classify("Saigon Opera House", "Live music venue")["group"] == "performance"
    assert use.classify_stop_kind("Saigon Opera House", "Performing arts venue") == "landmark"
    assert pk.classify("Zzxq", "Live music venue")["group"] == "landmark_unknown"


def test_research_angles_per_group():
    for g in ("religious", "royal", "performance", "maritime", "civic", "peaks", "depression", "water",
              "street_area"):
        assert pk.research_angles(g) and pk.query_hints(g), g
    assert any("legend" in a and "D760" in a for a in pk.research_angles("water"))
    assert any("SOURCED" in a for a in pk.research_angles("performance"))
    assert any("ALONG" in a for a in pk.research_angles("street_area"))


def test_legacy_expectations_still_hold():
    k = use.classify_stop_kind
    assert k("Longan", "Bar") == "business"
    assert k("A Star is Born", "Karaoke Bar") == "business"
    assert k("Tao Dan Park", "Park") == "landmark"
    assert k("Independence Palace", "Historical Site") == "landmark"
    assert k("War Remnants", "Historical museum") == "landmark"
    assert k("Bạch Đằng Pier") == "landmark"
