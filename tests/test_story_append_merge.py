#!/usr/bin/env python3
"""D518 — the story must REPLACE the prose it overlaps.

Every fixture is verbatim from `TOUR_MFA_FINAL_20260823.md`, the tour Michael read
on 2026-08-24 when he said *"saying things twice is the worst for listeners"*. The
prose and the story are split at the seam `generate_tour_text.py` produced with
`description + ' ' + story`.

Run: python3 tests/test_story_append_merge.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_append_merge import (merge_story_into_description, sentences_of,
                                anchors_of)

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


# ─────────────────────────────────────────────────────────────────────────────
# Stop 3 — the case that is not a style bug. The prose says Freud argued Moses
# was an Egyptian PRIEST; the story says NOBILITY. The story is right. The append
# kept both, in one stop, six sentences apart.
# ─────────────────────────────────────────────────────────────────────────────
STOP3_PROSE = (
    'Salvador Dalí created illustrations for Sigmund Freud\'s book "Moses and '
    'Monotheism" in 1974. This marked a significant moment in Dalí\'s career, as he '
    'chose to interpret Freud\'s foundational text through his unique artistic lens. '
    'By doing so, Dalí visually explored Freud\'s psychoanalytic theories, bridging '
    'the realms of art and psychology. This endeavor by Dalí not only expanded his own '
    'artistic repertoire but also enriched the dialogue between visual art and literary '
    'analysis. Freud, the author of the original text, controversially suggested that '
    'Moses was not a Hebrew but an Egyptian priest, which stirred debates upon its '
    'publication by The Hogarth Press in 1939. Dalí’s illustrations brought a new '
    'dimension to Freud’s ideas, showing how artists can transform books into '
    'multi-faceted artworks. This work exemplifies the exhibition’s thesis: artists '
    'like Dalí revolutionized the book as an art form through such innovative '
    'collaborations.'
)
STOP3_STORY = (
    'In 1939, Sigmund Freud published his final work, *Moses and Monotheism*, '
    'proposing the controversial thesis that Moses was of Egyptian nobility rather '
    'than Hebrew origin. Decades later, Salvador Dalí engaged with Freud\'s '
    'psychoanalytic interpretation by etching original designs with a diamond stylus '
    'directly onto massive gold printing plates. Depending on the account, Dalí’s '
    'illustrations were then printed onto lambskin, or across a combination of '
    'sheepskin and silk. The loose-leaf folios were paired with a sculptural '
    'bas-relief cover based on Michelangelo’s *Moses*, described by some sources as '
    'silver-plated and by others as finished with a silver patina. Dalí signed and '
    'dated sets of this project in the mid-1970s, producing an edition that translated '
    'Freud\'s final historical hypothesis into print.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Stop 2 — the prose tells Gris's death, the eleven plates and the 1955 revival;
# the story tells all three again, with sources and a disagreement.
# ─────────────────────────────────────────────────────────────────────────────
STOP2_PROSE = (
    'In 1927, Juan Gris passed away in Boulogne-sur-Seine, leaving behind his '
    'incomplete project, "Au Soleil du Plafond," a collaboration with French poet '
    'Pierre Reverdy. Nearly three decades later, in 1955, the Louis Broder Tériade '
    'brought Gris\'s vision to life by releasing the work posthumously, transforming '
    'it from an unfinished endeavor into a celebrated artistic book. The work consists '
    'of 11 vivid lithographs, published by Éditions Verve and printed by Mourlot '
    'Frères, a renowned lithography workshop in Paris. Pierre Reverdy\'s poetic '
    'sensibilities seamlessly complemented Gris\'s distinct artistic style, resulting '
    'in a unified narrative that merges the visual and the textual. The gallery, named '
    'after its patron, Torf, displays works rarely seen publicly, usually housed in '
    'archives. "Au Soleil du Plafond" stands as a poignant reminder of Gris\'s lasting '
    'influence, showcasing the significance of cross-disciplinary partnerships in '
    'modern art\'s evolution. Gris\'s posthumously completed work alters the perception '
    'of books, blending elements to elevate the medium into an integrated whole.'
)
STOP2_STORY = (
    'Pierre Reverdy and Juan Gris began collaborating on *Au Soleil du Plafond* around '
    '1916, intending for Gris to create illustrations for each of Reverdy\'s twenty '
    'poems. The project halted when Gris died prematurely in 1927. Sources differ on '
    'how much he completed before his death, with some recording that he produced '
    'eleven finished lithographs and others stating he completed only half the '
    'intended set. Nearly thirty years later, publisher Tériade revived the abandoned '
    'work, and the volume was finally published in 1955 as a tribute to Gris\'s memory.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Stop 1 — the two sentences the story repeats are also the two LEAD flagged as
# unsourced biography. The vellum sentence and the Boris Fridman gift are the
# stop's own material and must survive.
# ─────────────────────────────────────────────────────────────────────────────
STOP1_PROSE = (
    'In 1956, Louis Broder, the publisher of this edition, began a partnership with '
    'Joan Miró and the renowned French lithographic studio, Atelier Mourlot. This work '
    'marked the last project between Miró and Broder, as their friendship endured '
    'until Broder\'s death, leaving behind a celebrated artistic legacy. The edition is '
    'bound in exquisite publisher’s vellum, where Miró\'s poetic verses, combined with '
    'his unique visual language, capture the essence of surrealism. The lithographs '
    'dance across the pages with whimsical forms and bold colors, each image injected '
    'with a sense of playfulness and depth. Boris Fridman, a generous patron of the '
    'arts, gifted this remarkable piece to the museum, allowing thousands of visitors '
    'annually to experience Miró\'s genius firsthand. "Le Lézard aux plumes d\'or" '
    'stands as a vibrant example of how visual art and poetry converge, coaxing out '
    'the surreal elements within us all.'
)
STOP1_STORY = (
    'In 1967, Joan Miró and publisher Louis Broder completed an initial edition of *Le '
    'Lézard aux plumes d’or*, an illustrated book pairing Miró\'s lithographs with his '
    'own handwritten poetic text [facebook.com, miromallorca.com, christies.com]. '
    'After printing, a defect came to light, but the original printing plates had '
    'already been erased [christies.com]. Because the first set of plates could no '
    'longer be used, Miró had to create an entirely new series from scratch '
    '[christies.com].'
)


def test_stop3_contradiction_removed():
    merged, report = merge_story_into_description(
        STOP3_PROSE, STOP3_STORY,
        work_titles=['Moses and Monotheism'])
    check('stop 3: the "Egyptian priest" prose is gone',
          'Egyptian priest' not in merged, merged[-400:])
    check('stop 3: the story\'s "Egyptian nobility" survives',
          'Egyptian nobility' in merged)
    check('stop 3: the stop is not gutted', len(report['kept']) >= 3,
          f"kept {len(report['kept'])} of {report['n_prose']}")
    check('stop 3: Dalí\'s diamond stylus (story-only material) survives',
          'diamond stylus' in merged)


def test_stop2_episode_duplication_removed():
    merged, report = merge_story_into_description(
        STOP2_PROSE, STOP2_STORY,
        work_titles=['Au Soleil du Plafond'])
    check('stop 2: the prose retelling of Gris\'s 1927 death is gone',
          'passed away in Boulogne-sur-Seine' not in merged)
    check('stop 2: the prose retelling of the 1955 revival is gone',
          'brought Gris\'s vision to life' not in merged)
    check('stop 2: Éditions Verve / Mourlot Frères survive — the story never says them',
          'Éditions Verve' in merged and 'Mourlot Frères' in merged)
    check('stop 2: the story survives intact',
          'Sources differ on how much he completed' in merged)
    check('stop 2: at least two sentences were dropped',
          report['n_dropped'] >= 2, str(report['n_dropped']))


def test_stop1_keeps_what_the_story_never_says():
    merged, report = merge_story_into_description(
        STOP1_PROSE, STOP1_STORY,
        work_titles=['Le Lézard aux plumes d’or',
                     'The Lizard with Golden Feathers'])
    check('stop 1: the Boris Fridman gift survives — the story never mentions it',
          'Boris Fridman' in merged)
    check('stop 1: the vellum binding survives — naming Miró is not duplication',
          'vellum' in merged)
    check('stop 1: the erased plates story survives',
          'plates had already been erased' in merged)
    check('stop 1: something was dropped', report['n_dropped'] >= 1,
          str(report['n_dropped']))


def test_title_exclusion_is_what_saves_descriptive_prose():
    """Without the title exclusion, a sentence is condemned for naming the work.

    This is the check that a passing merge is passing for the right reason: run the
    same sentence with the title NOT excluded and it must be judged covered.
    """
    sentence = ('"Le Lézard aux plumes d\'or" stands as a vibrant example of how '
                'visual art and poetry converge.')
    story_anchors_with_title = anchors_of(STOP1_STORY)
    from story_append_merge import _content, _overlap
    with_title = _overlap(sentence, story_anchors_with_title,
                          _content(STOP1_STORY), set())
    from story_append_merge import _title_tokens
    excluded = _title_tokens('Le Lézard aux plumes d’or')
    without_title = _overlap(sentence, anchors_of(STOP1_STORY, exclude=excluded),
                             _content(STOP1_STORY, exclude=excluded), excluded)
    check('title exclusion changes the verdict on a title-naming sentence',
          with_title['covered'] and not without_title['covered'],
          f"with={with_title['covered']} without={without_title['covered']}")


def test_story_opens_the_stop_when_it_replaced_the_opening():
    """Measured on the live run of 2026-08-24 — the defect this fix introduced.

    A stop's first prose sentence introduces its subject, so it is also the one
    most likely to duplicate a story mined from it. Dropping it left all three
    stops of that run opening on a reference to nobody: "Broder published this
    limited edition book", "The project, originally conceived by L. Rosenberg",
    "Published by The Hogarth Press, Freud's theory".
    """
    merged, report = merge_story_into_description(
        STOP3_PROSE, STOP3_STORY, work_titles=['Moses and Monotheism'])
    check('stop 3: the story opens the stop, because it replaced the opening',
          report['story_first'] and merged.startswith('In 1939, Sigmund Freud'),
          merged[:80])
    check('stop 3: "This marked…" now has an antecedent instead of being deleted',
          'This marked a significant moment' in merged)
    check('stop 3: nothing was deleted as an orphan — reordering did the work',
          report['orphans'] == [], str(report['orphans']))


def test_prose_still_opens_when_its_first_sentence_survived():
    merged, report = merge_story_into_description(
        STOP2_PROSE, STOP2_STORY, work_titles=['Au Soleil du Plafond'])
    check('stop 2: first prose sentence WAS dropped, so the story opens',
          report['story_first'] and merged.startswith('Pierre Reverdy and Juan Gris'),
          merged[:70])

    prose = ('The edition is bound in publisher’s vellum. Louis Broder published '
             'it in 1967 with Joan Miró.')
    story = ('In 1967 Joan Miró and Louis Broder completed an edition, then found '
             'a defect in the paper.')
    m2, r2 = merge_story_into_description(prose, story)
    check('when the opening survives, the story still comes last',
          not r2['story_first'] and m2.startswith('The edition is bound'), m2[:60])


def test_orphan_repair_when_the_prose_still_opens():
    """The pronoun repair still applies in the case it was written for."""
    prose = ('Juan Gris and Pierre Reverdy planned twenty poems in 1916. '
             'The vellum binding is unusual. It was later famous. '
             'The Torf Gallery holds it.')
    story = ('Juan Gris and Pierre Reverdy planned twenty poems around 1916, and '
             'Gris died in 1927.')
    merged, report = merge_story_into_description(prose, story)
    check('first sentence dropped here too, so the story opens',
          report['story_first'], str(report))
    check('the vellum sentence survives', 'vellum binding' in merged)


def test_orphan_repair_cannot_eat_a_stop():
    prose = ('Juan Gris died in 1927 leaving eleven lithographs. It was later '
             'finished. This became a famous book. That was that. Such is art.')
    story = 'Juan Gris died in 1927 leaving eleven lithographs, finished later.'
    merged, report = merge_story_into_description(prose, story)
    check('orphan drops stop at the budget', len(report['orphans']) <= 2,
          str(report['orphans']))
    check('at least one prose sentence survives', len(report['kept']) >= 1,
          str(report['kept']))


def test_only_the_first_story_may_claim_the_opening():
    """LOCAL-466 publishes more than one story per stop; order must survive.

    Found by fixture during review of LOCAL-466, before it was merged. The second
    story merges against text that already contains the first — and if that merge
    drops the opening sentence, D518b's "story becomes the opening" rule fires
    again and fronts the SECOND story: weaker story first, prose in the middle,
    best story last.
    """
    prose = ("In 1974, Salvador Dali illustrated Freud's book. The edition is "
             "bound in vellum. Boris Fridman gave the work to the museum.")
    first = ("In 1939 Sigmund Freud published Moses and Monotheism, arguing "
             "Moses was an Egyptian noble.")
    second = ("Dali etched the designs onto gold plates with a diamond stylus "
              "in 1974.")
    text, published = prose, []
    for s in (first, second):
        text, rep = merge_story_into_description(
            text, s, work_titles=['Moses and Monotheism'],
            allow_story_first=not published)
        published.append(s)
    check('the best story still precedes the second',
          text.index('Egyptian noble') < text.index('diamond stylus'), text[:90])
    check('both stories survive',
          'Egyptian noble' in text and 'diamond stylus' in text)

    # And the flag must not disturb the single-story case it was carved out of.
    solo, rep = merge_story_into_description(
        STOP3_PROSE, STOP3_STORY, work_titles=['Moses and Monotheism'])
    check('a single story still opens its stop when it replaced the opening',
          rep['story_first'] and solo.startswith('In 1939, Sigmund Freud'),
          solo[:60])


def test_no_story_still_gets_cleaned():
    """A stop that published no story can still read a domain out loud."""
    merged, report = merge_story_into_description(STOP1_PROSE, '')
    check('no story: no sentence dropped as a duplicate', report['n_dropped'] == 0)
    check('no story: the prose is otherwise untouched',
          'Boris Fridman' in merged and 'vellum' in merged)
    cited, _ = merge_story_into_description(
        'Freud published it in 1939 [jstor.org, dokumen.pub].', '')
    check('no story: bracketed citations are still stripped',
          cited == 'Freud published it in 1939.', repr(cited))


# ─────────────────────────────────────────────────────────────────────────────
# D521 — Michael, 2026-08-24, on the 10:36 tour.
# ─────────────────────────────────────────────────────────────────────────────

def test_bracketed_citations_never_reach_the_listener():
    """Verbatim from the 10:36 tour, which is the sentence he quoted."""
    from story_append_merge import strip_bracketed_citations as S
    got = S("Salvador Dalí later created a suite of artworks and illustrations "
            "to accompany a deluxe French edition of Freud's text "
            "[collections.museumofthebible.org, lockportstreetgallery.com].")
    check('the domain list is gone', '[' not in got and 'lockportstreet' not in got)
    check('and the full stop closed up, not left floating',
          got.endswith("Freud's text."), repr(got[-40:]))

    check('the [cite: …] form goes too',
          S("publisher Tériade revived the work [cite: abebooks.com, artsy.net].")
          == "publisher Tériade revived the work.")
    check('mid-sentence brackets go without eating the comma',
          S("In 1939, Freud published his final work [jstor.org], arguing a thesis.")
          == "In 1939, Freud published his final work, arguing a thesis.")
    check('bare reference numbers go', S("He noted the effect [12] on later work.")
          == "He noted the effect on later work.")

    kept = "The lithographs [which he redrew entirely] are unsigned."
    check('a bracketed ASIDE is not a citation and is left alone', S(kept) == kept)
    check('parentheses are never touched',
          S("The lithographs (printed in Paris) are unsigned.")
          == "The lithographs (printed in Paris) are unsigned.")


def test_a_sentence_may_not_say_the_same_thing_twice():
    """The sentence Michael pointed at: Fridman gives the work away twice."""
    from story_append_merge import dedupe_within_sentence as D
    got = D("Boris Fridman, the collector who gave this work to the museum, "
            "later donated this important work to the Museum of Fine Arts, "
            "Boston, enriching the museum's collection.")
    check('the repeated apposition is gone',
          'the collector who gave' not in got, got)
    check('the surviving clause is the one with the detail',
          'Museum of Fine Arts' in got and 'enriching' in got)
    check('no comma left stranded between subject and verb',
          got.startswith('Boris Fridman later donated'), got[:45])


def test_the_duplicate_may_be_the_LAST_clause():
    """Verbatim from the 12:23 tour, which the first version of the rule missed.

    The 10:36 sentence put the repeated clause in the middle; this one puts it at
    the end. A rule that stopped one segment short reported the tour clean, and
    the sentence Michael had already objected to went out again in a new shape.
    """
    from story_append_merge import dedupe_within_sentence as D
    got = D("This work is now part of the Museum of Fine Arts' collection, thanks "
            "to the generous gift of Boris Fridman, the collector who gave this "
            "work to the museum.")
    check('the trailing restatement is gone',
          'the collector who gave' not in got, got)
    check('the gift itself survives', 'generous gift of Boris Fridman' in got)
    check('the sentence still ends in a full stop', got.endswith('.'), repr(got[-30:]))

    # And the middle-clause form still works — one rule, both positions.
    mid = D("Boris Fridman, the collector who gave this work to the museum, later "
            "donated this important work to the Museum of Fine Arts, Boston.")
    check('the middle-clause form is still fixed',
          mid == 'Boris Fridman later donated this important work to the Museum '
                 'of Fine Arts, Boston.', mid)


def test_dedupe_leaves_appositions_that_add_something():
    """The controls. Each of these repeats nothing and must survive intact."""
    from story_append_merge import dedupe_within_sentence as D
    for s in [
        # different verb family — describing vs writing
        'Pierre Reverdy, the French poet linked to Surrealism, wrote twenty poems.',
        # the middle segment is not an apposition at all
        'The work consists of 11 lithographs, published by Éditions Verve and '
        'printed by Mourlot Frères, a renowned lithography workshop in Paris.',
        # same subject, different events
        'Juan Gris, who died in 1927, left the work unfinished.',
        # too short to be a restatement
        'Boris Fridman, a collector, donated the work.',
        # no shared verb family
        'The gallery, named after its patron Torf, displays works rarely seen.',
        # trailing participle at the very end — the position the rule now reaches
        'Boris Fridman donated the work to the museum, enriching the collection.',
        # a real trailing relative clause that adds information
        'The work is composed of 11 lithographs, printed by Mourlot Frères, '
        'a renowned Parisian house, which was known for its high-quality work.',
    ]:
        check(f'kept: "{s[:52]}…"', D(s) == s, D(s))


def test_the_whole_stop_is_cleaned_end_to_end():
    prose = ('Boris Fridman, the collector who gave this work to the museum, '
             'later donated this important work to the Museum of Fine Arts, '
             'Boston. The edition is bound in vellum.')
    story = ('In 1967 Joan Miró and Louis Broder completed an edition '
             '[christies.com, sothebys.com].')
    merged, report = merge_story_into_description(prose, story)
    check('end to end: no brackets survive', '[' not in merged, merged)
    check('end to end: no double giving', 'the collector who gave' not in merged)
    check('end to end: the intra-sentence fix was reported',
          len(report['intra']) == 1, str(report['intra']))
    check('end to end: real content survives',
          'vellum' in merged and 'Joan Miró' in merged)


def test_no_story_is_a_no_op():
    merged, report = merge_story_into_description(STOP1_PROSE, '')
    check('no story: nothing reported dropped', report['n_dropped'] == 0)


def test_never_strips_a_stop_bare():
    """A story that repeats everything must still leave most of the stop standing."""
    prose = ('Juan Gris died in 1927. Juan Gris died in 1927 leaving the work '
             'incomplete. Pierre Reverdy wrote the poems in 1927. The work has '
             'eleven lithographs from 1927. Tériade published it in 1955.')
    story = ('Juan Gris died in 1927 leaving the work incomplete, Pierre Reverdy '
             'having written eleven poems, and Tériade published it in 1955 with '
             'eleven lithographs.')
    merged, report = merge_story_into_description(prose, story)
    check('cap fired when the story subsumed everything', report['capped'])
    check('at most 60% of the prose was removed',
          report['n_dropped'] <= int(report['n_prose'] * 0.6),
          f"{report['n_dropped']} of {report['n_prose']}")
    check('the story is still there', 'Tériade published it in 1955 with' in merged)


def test_seam_has_no_missing_space():
    merged, _ = merge_story_into_description('A sentence about vellum binding.',
                                             'The story begins here.')
    check('seam joins with exactly one space',
          merged == 'A sentence about vellum binding. The story begins here.',
          repr(merged))


def test_sentence_splitter_keeps_everything():
    text = 'One. Two! Three? "Four." Five.'
    check('splitter loses no sentence', len(sentences_of(text)) == 5,
          repr(sentences_of(text)))


if __name__ == '__main__':
    print('D518 — story replaces the prose it overlaps\n')
    for fn in (test_stop3_contradiction_removed,
               test_stop2_episode_duplication_removed,
               test_stop1_keeps_what_the_story_never_says,
               test_title_exclusion_is_what_saves_descriptive_prose,
               test_story_opens_the_stop_when_it_replaced_the_opening,
               test_prose_still_opens_when_its_first_sentence_survived,
               test_orphan_repair_when_the_prose_still_opens,
               test_orphan_repair_cannot_eat_a_stop,
               test_only_the_first_story_may_claim_the_opening,
               test_no_story_still_gets_cleaned,
               test_bracketed_citations_never_reach_the_listener,
               test_a_sentence_may_not_say_the_same_thing_twice,
               test_the_duplicate_may_be_the_LAST_clause,
               test_dedupe_leaves_appositions_that_add_something,
               test_the_whole_stop_is_cleaned_end_to_end,
               test_never_strips_a_stop_bare,
               test_seam_has_no_missing_space,
               test_sentence_splitter_keeps_everything):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print('ALL TESTS PASSED')
