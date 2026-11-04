"""LOCAL-864 — built from the exact LOCAL-861 cases (submission_artifacts/local861)."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import museum_claim_gate as g

BLIND = os.path.join(os.path.dirname(__file__), '..', 'submission_artifacts', 'local861', 'blind')


def _blind(n):
    return open(os.path.join(BLIND, n + '.txt'), encoding='utf-8').read()


# ── 1. UNSOURCED claims ─────────────────────────────────────────────────────
ASIAN_EVIDENCE = ["Buddha dated 338. Gilt bronze, China. Earliest dated Chinese Buddha image. "
                  "Avery Brundage Collection, B60S593."]


def test_asian_art_fridman_broder_freeman_nguyen_dropped_with_dependents():
    t = _blind('t4425')
    body = t[t.index('Stop 2:'):t.index('Stop 3:')]
    new, rep = g.filter_tour_text_claims(
        body, {1: ASIAN_EVIDENCE}, stop_titles={1: 'Buddha dated 338'})
    for name in ('Fridman', 'Broder', 'Freeman', 'Nguyen', 'national treasure'):
        assert name.lower() not in new.lower(), (name, new)
    assert rep['dropped'] >= 3
    assert not re.search(r'(?m)^(He|His) donated', new)


def test_orsay_broder_print_editions_dropped():
    t = _blind('t9872')
    para = [p for p in t.split('\n\n') if 'Louis Broder' in p][0]
    new, removed, _ = g.filter_stop_body(
        para, ["Manet, Dejeuner sur l'herbe, 1863, oil on canvas, Salon des Refuses"],
        known=["Le Déjeuner sur l'herbe", "Édouard Manet"])
    assert 'Broder' not in new
    assert any('Broder' in s for s, _ in removed)


def test_sourced_name_is_kept():
    s = "Boris Fridman, a collector, donated this book to the museum."
    new, removed, _ = g.filter_stop_body(s, ["Gift of Boris Fridman, 2021."])
    assert new.strip() == s and not removed


def test_disclosed_unsourced_claim_may_stay():
    s = "It is sometimes said that Louis Broder commissioned editions of this print."
    new, removed, _ = g.filter_stop_body(s, ["nothing relevant"])
    assert 'Broder' in new and not removed


def test_verifier_flagged_span_drops_every_sentence_naming_the_entity():
    body = ("Louis Broder commissioned limited editions of prints. "
            "Later, Louis Broder sold the plates to a dealer. The canvas is oil.")
    new, removed, _ = g.filter_stop_body(body, ["The canvas is oil."],
                                         flagged=["Louis Broder commissioned limited"])
    assert 'Broder' not in new and 'canvas' in new and len(removed) == 2


# ── 2. stop identity ────────────────────────────────────────────────────────
VENUE = "https://asianart.org"


def test_head_of_buddha_does_not_match_miro_head():
    miro = {"title": "Head of a Catalan Peasant", "artist": "Joan Miró",
            "url": "https://collections.mfa.org/objects/1"}
    ok, why = g.accept_stop_match("Head of a Buddha", miro, VENUE, "Asian Art Museum")
    assert not ok
    # even with a (wrong) venue record, generic-word overlap alone is refused
    miro2 = dict(miro, url="https://asianart.org/collection/1", accession_number="X1")
    ok, why = g.accept_stop_match("Head of a Buddha", miro2, VENUE, "Asian Art Museum")
    assert not ok and 'generic' in why


def test_landscape_four_seasons_does_not_match_corot_nude():
    corot = {"title": "Landscape with a Nude Woman", "artist": "Corot",
             "accession_number": "RF 1234", "holder": "Musée d'Orsay"}
    assert not g.accept_stop_match("Landscape of the four seasons (B60D49+)", corot,
                                   VENUE, "Asian Art Museum")[0]
    assert g.distinctive_tokens("Landscape of the four seasons (B60D49+)") == {"four", "seasons"}


def test_own_work_with_accession_matches():
    w = {"title": "Landscape of the Four Seasons", "accession_number": "B60D49+"}
    assert g.accept_stop_match("Landscape of the four seasons (B60D49+)", w, VENUE,
                               "Asian Art Museum")[0]
    assert g.accept_stop_match("Head of a Buddha",
                               {"title": "Head of a Buddha", "url": "https://asianart.org/c/9"},
                               VENUE, "Asian Art Museum")[0]


def test_work_without_accession_or_museum_url_refused():
    assert not g.work_belongs_to_venue({"title": "Head of a Buddha"}, VENUE)[0]
    assert not g.work_belongs_to_venue(
        {"title": "x", "url": "https://example.com/x", "accession_number": "1"}, VENUE)[0]


def test_foreign_work_narration_dropped_when_match_rejected():
    g.clear_rejected_matches()
    g.register_rejected_match("Head of a Buddha", {"title": "Head of a Catalan Peasant",
                                                   "artist": "Joan Miró"})
    body = ("This head shows a calm face. Joan Miró made Head of a Catalan Peasant in 1925. "
            "The ears are elongated.")
    out, rep = g.filter_tour_text_claims("Stop 1: Head of a Buddha\n\n" + body,
                                         {1: ["Head of a Buddha, gilt bronze"]})
    assert 'Miró' not in out and 'calm face' in out and rep['dropped'] == 1
    g.clear_rejected_matches()


# ── 3. catalog wins ─────────────────────────────────────────────────────────
CROWNED = {"title": "Crowned and bejeweled Buddha image", "culture": "Burmese",
           "date": "19th century", "material": "Wood, lacquer, gilding"}
B338 = {"title": "Buddha dated 338", "culture": "Chinese", "date": "338",
        "material": "Gilt bronze"}


def test_reconcile_catalog_overrides_search_hit():
    hit = {"title": "Crowned and bejeweled Buddha image", "culture": "Vietnamese",
           "date": "11th century", "material": "stone"}
    m, over = g.reconcile_with_catalog(hit, CROWNED)
    assert (m['culture'], m['date'], m['material']) == ("Burmese", "19th century",
                                                        "Wood, lacquer, gilding")
    assert set(over) == {"culture", "date", "material"}


def test_ly_dynasty_vietnam_sentences_dropped_for_both_buddhas():
    s_ly = "The artist worked within the Ly Dynasty's milieu in eleventh-century Vietnam."
    for cat, title in ((CROWNED, "Crowned and bejeweled Buddha image"),
                       (B338, "Buddha dated 338")):
        assert g.sentence_contradicts_catalog(
            "This Buddha is an 11th-century Vietnamese Ly Dynasty sculpture.", cat, title)
        assert g.sentence_contradicts_catalog(
            "In 2013, the Vietnamese State recognized this statue as a national treasure.",
            cat, title)
    assert not g.sentence_contradicts_catalog(
        "This Burmese Buddha, from the 19th century, wears a crown.", CROWNED,
        "Crowned and bejeweled Buddha image")


def test_text_filter_removes_ly_story_and_states_catalog_facts():
    t = _blind('t6291')
    start = t.index('Stop ')
    body = t[start:]
    stops = re.split(r'(?m)^(?=Stop \d+:)', body)
    crowned = [s for s in stops if 'Crowned' in s.split('\n')[0]]
    assert crowned, "fixture should hold the crowned Buddha stop"
    new, rep = g.filter_tour_text_claims(crowned[0], {1: ["19th century Burmese"]},
                                         stop_catalogs={1: CROWNED},
                                         stop_titles={1: "Crowned and bejeweled Buddha image"})
    assert 'Ly Dynasty' not in new and 'national treasure' not in new.lower()
    assert 'Burmese' in new and '19th' in new


def test_b338_stop_carries_chinese_and_338():
    body = "Stop 1: Buddha dated 338\n\nThis Buddha has a square protrusion behind the head."
    new, rep = g.filter_tour_text_claims(body, {1: ["Buddha dated 338"]},
                                         stop_catalogs={1: B338},
                                         stop_titles={1: "Buddha dated 338"})
    assert 'Chinese' in new and '338' in new and rep['injected'] == 1
    again, rep2 = g.filter_tour_text_claims(new, {1: ["Buddha dated 338"]},
                                            stop_catalogs={1: B338},
                                            stop_titles={1: "Buddha dated 338"})
    assert again == new and rep2['injected'] == 0   # idempotent


# ── catalog record (label block) — real markup excerpts, collections.asianart.org ──
B338_HTML = ('<div class="wysiwyg"><p><b>Buddha dated 338</b></p>\n<p><span style="font-weight: 400;">'
             'China; Hebei province<br /></span><span style="font-weight: 400;">Later Zhao kingdom '
             '(319&ndash;351)<br /></span><span style="font-weight: 400;">Bronze with gilding<br />'
             '</span><em><span style="font-weight: 400;">The Avery Brundage Collection</span></em>'
             '<span style="font-weight: 400;">, B60B1034</span></p>')
CROWNED_HTML = ('<p><b>Crowned and bejeweled Buddha image and throne</b></p>\n<p><span>Approx. '
                '1860&ndash;1880<br /></span><span>Myanmar (Burma); Mandalay area<br /></span><span>'
                'Wood and iron, with lacquer, gilding, and mirrored glass<br /></span><em><span>Gift '
                'from Doris Duke Charitable Foundation&#8217;s Southeast Asian Art Collection,</span>'
                '</em><span> 2006.27.17 and 2006.27.1.a-.t</span></p>')


def test_label_block_b338():
    r = g.parse_label_block(B338_HTML, 'Buddha dated 338')
    assert r['culture'] == 'Chinese' and r['date'].startswith('338')
    assert 'Bronze' in r['material'] and r['accession_number'] == 'B60B1034'


def test_label_block_crowned_is_19th_c_burmese():
    r = g.parse_label_block(CROWNED_HTML, 'Crowned and bejeweled Buddha image')
    assert r['culture'] == 'Burmese' and '1860' in r['date']
    assert g._catalog_centuries(r) == {19}
    # a different object must not take this record
    assert g.parse_label_block(CROWNED_HTML, 'Seated crowned and bejeweled Buddha') == {}


def test_catalog_url_found_on_venue_domain_only():
    sn = [{'url': 'https://collections.asianart.org/collection/seated-buddha-dated-338/', 'title': ''},
          {'url': 'https://www.slam.org/collection/objects/33270/', 'title': 'Buddha dated 338'}]
    assert g.catalog_urls_from_snippets('Buddha dated 338', sn, 'http://www.asianart.org') == [
        'https://collections.asianart.org/collection/seated-buddha-dated-338/']


def test_stone_buddha_contradicts_gilt_bronze_record():
    cat = g.parse_label_block(B338_HTML, 'Buddha dated 338')
    assert g.sentence_contradicts_catalog(
        'The Buddha dated 338 before you is a blue stone sculpture of Buddha Amitabha.', cat,
        'Buddha dated 338')
    assert not g.sentence_contradicts_catalog('The gilt bronze still shines.', cat, 'Buddha dated 338')


# ── LOCAL-864 live run asian_A (pre-fix delivered text, quoted) ────────────────
MIRO_STOP = ("Stop 3: Head of a Buddha\n\nHead of a Buddha is a fragmentary sculpture, presenting only "
             "the Buddha's head. Turning now to a related piece nearby—the Head of a Catalan Peasant by "
             "Joan Miró—you find an intriguing parallel. Miró created this emblematic sequence of oil "
             "paintings and pencil drawings between 1924 and 1925. Such a process ensured the work's "
             "integrity and intimacy. Miró's ongoing interest in Catalonian themes echoes the Head of a "
             "Buddha's focus on essential identity.\n\nContinue to Landscape of the four seasons.\n")
COROT_STOP = ("Stop 4: Landscape of the four seasons, one of a pair (Asian Art Museum B60D49+)\n\n"
              "Orientation: Standing directly before it, notice the silvery tones that Corot achieved on "
              "the canvas. This angle allows the figure and surrounding landscape to emerge fully.\n\n"
              "Silvery, muted tones and soft brushwork allow the figure to blend into the environment. "
              "This work captures a moment of tranquility.\n\nDirections: Continue to Seated crowned "
              "and bejeweled Buddha.\n")


def test_miro_narration_removed_from_head_of_a_buddha():
    out, rep = g.filter_tour_text_claims(MIRO_STOP, {1: ["Head of a Buddha Joan Miró Head of a "
                                                         "Catalan Peasant 1924 1925 Tate"]},
                                         venue_name='Asian Art Museum')
    assert 'Miró' not in out and 'Catalan' not in out and 'integrity' not in out
    assert 'fragmentary sculpture' in out and 'Continue to' in out


def test_corot_stop_hollowed_to_honest_line_not_left_describing_the_nude():
    out, rep = g.filter_tour_text_claims(COROT_STOP, {1: ["Corot Bacchante in a Landscape"]},
                                         venue_name='Asian Art Museum')
    assert 'Corot' not in out and 'figure' not in out
    assert 'different work' in out and 'Directions: Continue' in out


def test_corot_stop_with_catalog_gets_catalog_statement():
    cat = {'culture': 'Japanese', 'date': 'approx. 1550', 'material': 'ink and colors on paper'}
    out, _ = g.filter_tour_text_claims(COROT_STOP, {1: []}, stop_catalogs={1: cat},
                                       venue_name='Asian Art Museum')
    assert "catalog records this as a Japanese work" in out and 'Corot' not in out


def test_work_at_another_temple_dropped():
    s = ("The Amida Buddha statue at the Byodo-in temple, built in the 11th century, is covered "
         "in gold leaf. The lotus base symbolizes purity.")
    new, removed, _ = g.filter_stop_body(s, ["Byodo-in Amida"], venue_name='Asian Art Museum')
    assert 'Byodo' not in new and 'lotus' in new


def test_structural_lines_never_dropped():
    s = "Directions: Proceed to Landscape of the four seasons, one of a pair (Asian Art Museum B60D49+)."
    g.clear_rejected_matches()
    g.register_rejected_match("Head of a Buddha", {"title": "Asian Art"})  # generic: ignored
    out, rep = g.filter_tour_text_claims("Stop 1: Head of a Buddha\n\n" + s + "\n", {1: []},
                                         venue_name='Asian Art Museum')
    assert s in out and rep['dropped'] == 0
    g.clear_rejected_matches()


# ── root cause of the Broder/Fridman bleed: few-shot examples named them ─────
def test_story_prompts_carry_no_real_example_names():
    here = os.path.join(os.path.dirname(__file__), '..')
    src = open(os.path.join(here, 'generate_tour_text.py'), encoding='utf-8').read()
    a = src.index('STORY INSTRUCTION (LOCAL-407/412/419)')
    b = src.index('# [LOCAL-402] Direct snippet injection')
    block = src[a:b]
    c = src.index('━━━ FINAL STORY SHAPE')
    d = src.index('━━━ END FINAL STORY SHAPE')
    final = src[c:d]
    for name in ('Broder', 'Fridman', 'Mourlot', 'Chabrol', 'Tériade', 'Miró', 'Freud'):
        assert name not in block, name
        assert name not in final, name
    sp = open(os.path.join(here, 'story_pass.py'), encoding='utf-8').read()
    assert 'Broder published' not in sp and 'Mourlot pull' not in sp


# ── LOCAL-864 live run 2 (asian_A): survivors that the venue's maker record catches ──
RUN2_STOP4 = ("Stop 4: Landscape of the four seasons, one of a pair (Asian Art Museum B60D49+)\n\n"
              "Measuring 12 1/8 by 24 1/4 inches, this painting's elongated horizontal format draws the eye "
              "along a serene natural expanse where a nude figure, the Bacchante, integrates seamlessly into "
              "the surrounding environment. Corot created this work at a turning point in his career.\n\n"
              "Directions: Continue to Seated crowned and bejeweled Buddha.\n")


def test_venue_maker_record_beats_evidence_mentioning_corot():
    # the search corpus mentions Corot, so evidence alone would let him through;
    # this venue's own record says the maker is Shikibu Terutada.
    works = [{"title": "Landscape of the four seasons, one of a pair", "creator": "Shikibu Terutada"}]
    makers = g.makers_from_venue_works("Landscape of the four seasons, one of a pair (Asian Art Museum B60D49+)", works)
    assert makers == ["Shikibu Terutada"]
    out, rep = g.filter_tour_text_claims(
        RUN2_STOP4, {1: ["Corot Bacchante in a Landscape 12 1/8 by 24 1/4"]},
        stop_own_evidence={1: ["Corot"]}, stop_makers={1: makers}, venue_name="Asian Art Museum")
    assert "Corot" not in out and "Bacchante" not in out and "Directions: Continue" in out


def test_orsay_manet_kept_when_venue_record_names_manet():
    body = ("Stop 1: Le Déjeuner sur l'herbe (Luncheon on the Grass)\n\nÉdouard Manet painted Le Déjeuner "
            "sur l'herbe in 1863. Manet's technique flattened the figures.\n")
    works = [{"title": "Le Déjeuner sur l'herbe", "creator": "Édouard Manet"}]
    m = g.makers_from_venue_works("Le Déjeuner sur l'herbe (Luncheon on the Grass)", works)
    out, rep = g.filter_tour_text_claims(body, {1: ["Manet Déjeuner sur l'herbe 1863"]},
                                         stop_makers={1: m}, venue_name="Musée d'Orsay")
    assert rep["dropped"] == 0 and "Manet" in out


def test_hyphenated_and_possessive_maker_names():
    assert g.foreign_makers("This painting was made by Jean-Baptiste Camille Corot.", "", "") == [
        "Jean-Baptiste Camille Corot"]
    assert g.foreign_makers("Corot’s technique blurs edges.", "", "") == ["Corot"]


# ── maker binding: evidence must tie the maker to THIS work, not just mention him ──
def test_corot_in_evidence_but_not_bound_to_four_seasons():
    snips = [{"title": "Bacchante in a Landscape | The Met", "snippet": "Camille Corot, 1865-70, oil on canvas"},
             {"title": "Landscape of the four seasons, one of a pair - Asian Art Museum",
              "snippet": "Pair of six-panel folding screens; ink and colors on paper"}]
    out, rep = g.filter_tour_text_claims(RUN2_STOP4, {1: [s["title"] + " " + s["snippet"] for s in snips]},
                                         stop_own_evidence={1: ["Corot"]}, stop_snippets={1: snips},
                                         venue_name="Asian Art Museum")
    assert "Corot" not in out and "Bacchante" not in out


def test_miro_in_evidence_but_not_bound_to_head_of_buddha():
    snips = [{"title": "Head of a Catalan Peasant | Tate", "snippet": "Joan Miró 1925 oil on canvas"}]
    out, _ = g.filter_tour_text_claims(MIRO_STOP, {1: ["Joan Miró Head of a Catalan Peasant"]},
                                       stop_snippets={1: snips}, venue_name="Asian Art Museum")
    assert "Miró" not in out and "fragmentary sculpture" in out


def test_manet_bound_by_snippet_without_venue_record():
    snips = [{"title": "Le Déjeuner sur l'herbe - Wikipedia",
              "snippet": "Le Déjeuner sur l'herbe is a large oil on canvas by Édouard Manet, 1863."}]
    body = ("Stop 1: Le Déjeuner sur l'herbe (Luncheon on the Grass)\n\nÉdouard Manet painted Le Déjeuner "
            "sur l'herbe in 1863. Manet's technique flattened the figures.\n")
    out, rep = g.filter_tour_text_claims(body, {1: [snips[0]["title"] + " " + snips[0]["snippet"]]},
                                         stop_snippets={1: snips}, venue_name="Musée d'Orsay")
    assert rep["dropped"] == 0 and "Manet" in out


def test_catalog_credit_line_sources_the_donor():
    cat = g.parse_label_block(B338_HTML, 'Buddha dated 338')
    s = "The donor Avery Brundage gave this work to the museum."
    new, removed, _ = g.filter_stop_body(s, [], catalog=cat, stop_title='Buddha dated 338')
    assert 'Brundage' in new and not removed
