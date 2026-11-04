"""LOCAL-864B: catalog binding without a snippet URL, artist scrub, conclusion grounding."""
import os, sys
sys.path[:0] = [os.path.join(os.path.dirname(__file__), ".."), os.path.dirname(__file__)]
import museum_claim_gate as g
from test_local864_museum_claim_gate import B338_HTML, CROWNED_HTML

VENUE = "http://www.asianart.org"
PAGES = {
    "https://collections.asianart.org/?s=Buddha+dated+338":
        '<a href="https://collections.asianart.org/collection/seated-buddha-dated-338/">x</a>'
        '<a href="/collection/other-thing/">y</a>',
    "https://collections.asianart.org/collection/seated-buddha-dated-338/": B338_HTML,
    "https://collections.asianart.org/collection/crowned-and-bejeweled-buddha-image-and-throne/": CROWNED_HTML,
}


def fetch(u):
    return PAGES.get(u, "")


def test_catalog_found_by_site_search_when_no_snippet_has_url():
    urls, why = g.catalog_urls_by_search("Buddha dated 338", VENUE, fetch)
    assert urls == ["https://collections.asianart.org/collection/seated-buddha-dated-338/"], (urls, why)
    rec = g.parse_label_block(fetch(urls[0]), "Buddha dated 338")
    assert rec["culture"] == "Chinese" and "338" in rec["date"]


def test_catalog_found_by_slug_guess():
    urls, _ = g.catalog_urls_by_search("Crowned and bejeweled Buddha image (and throne)", VENUE, fetch)
    assert urls and "crowned-and-bejeweled" in urls[0]


def test_catalog_miss_explains_why():
    urls, why = g.catalog_urls_by_search("Landscape of the four seasons", VENUE, fetch)
    assert urls == [] and "no record page" in why


def test_blue_stone_contradicting_bronze_record_dropped_in_orientation():
    rec = g.parse_label_block(B338_HTML, "Buddha dated 338")
    body = ("Orientation: Standing before the solid blue stone, look at the face. "
            "The hands rest in the lap.")
    new, rem, inj = g.filter_stop_body(body, [], [], [], rec, "Buddha dated 338",
                                       venue_name="Asian Art Museum", stop_snippets=[])
    assert "blue stone" not in new and "Chinese" in new


def test_corot_dropped_and_other_work_replaced():
    body = ("The painting dissolves the figure of a nude. "
            "Corot's restless brushstrokes animate the foliage.")
    new, rem, _ = g.filter_stop_body(body, [], ["Landscape of the four seasons"], [], None,
                                     "Landscape of the four seasons", venue_name="Asian Art Museum",
                                     stop_snippets=[])
    assert "Corot" not in new and "nude" not in new and new.strip()


def test_sourced_comparison_kept():
    body = "Hokusai's wave is the model for this print."
    new, rem, _ = g.filter_stop_body(body, ["Hokusai wave"], [], [], None, "Print",
                                     own_evidence=["Hokusai inspired this print"], venue_name="X")
    assert "Hokusai" in new


def test_artist_scrub_whole_tour_intro_stop_conclusion():
    t = ("Intro mentions Miro briefly.\n\nStop 1: Head of a Buddha\n\nOrientation: Look up. Miro's shift mattered.\n\n"
         "A calm face.\n\nThat's 1 stops in all. You encountered the Head of a Buddha, which marked Miró's shift.\n")
    new, rep = g.scrub_artists_tour(t, stop_allow={1: ""}, stop_titles={1: "Head of a Buddha"})
    assert "Mir" not in new.replace("Miro", "Miro") or "Miro" not in new
    assert "Miró" not in new and "Miro" not in new
    assert "Orientation:" in new and "A calm face." in new


def test_conclusion_never_names_absent_artist():
    import tour_conclusion as tc
    tour = ("Step-by-Step Audio Guided Tour: X\n\nStop 1: Head of a Buddha\n\nOrientation: Look.\n\nA calm face of bronze.\n\n"
            "Stop 2: Seated Buddha\n\nOrientation: Look.\n\nGilded wood.\n")
    llm = lambda prompt, key: "Across these Buddhas you encountered the Head of a Buddha, which marked Miró's shift to abstract visual language."
    out = tc.build_conclusion(tour, venue_name="Asian Art Museum", use_llm=True, llm_fn=llm, api_key="x")
    assert "Mir" not in out


def test_flagged_person_surname_and_recognition_and_medium_dropped():
    rec = g.parse_label_block(CROWNED_HTML, "Crowned and bejeweled Buddha image (and throne)")
    body = ("The medium is a combination of painted panel and embedded ornamental elements. "
            "The State’s recognition of the statue’s cultural value underscores its importance. "
            "The museum secured it thanks to Lee’s donation. "
            "The crown is heavy with jewels.")
    new, rem, _ = g.filter_stop_body(body, [], [], ["Moon Lee commissioned the"], rec,
                                     "Crowned and bejeweled Buddha image (and throne)",
                                     venue_name="Asian Art Museum", stop_snippets=[])
    assert "medium" not in new and "State" not in new and "Lee" not in new
    assert "crown is heavy" in new


def test_flagged_span_paraphrase_matches():
    assert g._span_hit("expanded mission since October 2011 Asian American artist",
                       "The Asian American artist programs reflect the museum's expanded mission, which since October 2011 has grown.")


def test_dropped_orientation_replaced_and_leak_identities_dropped():
    body = ("Address: 200 Larkin St\n\nOrientation: Stand beside the blue stone Amitabha.\n\n"
            "The crown echoes the Amida Buddha of the Byodo-in temple. The Ly court promoted Buddhism. "
            "A donor gave it in the 1990s.")
    new, rem, _ = g.filter_stop_body(body, [], ["Seated crowned and bejeweled Buddha"], [], None,
                                     "Seated crowned and bejeweled Buddha", venue_name="Asian Art Museum",
                                     stop_snippets=[])
    assert "Orientation:" in new
    for bad in ("blue stone", "Amida", "Byodo", "Ly court"):
        assert bad not in new
