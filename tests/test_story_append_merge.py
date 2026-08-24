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


def test_orphaned_opener_is_repaired():
    """Dropping the first sentence must not leave the next one pointing at it.

    Stop 3 measured this: the duplicate opener went, and the stop began "This
    marked a significant moment in Dalí's career" — marked what?
    """
    merged, report = merge_story_into_description(
        STOP3_PROSE, STOP3_STORY, work_titles=['Moses and Monotheism'])
    check('stop 3: the dangling "This marked" opener went with it',
          not merged.startswith('This marked'), merged[:80])
    check('stop 3: it was recorded as an orphan, not as a duplicate',
          any(s.startswith('This marked') for s in report['orphans']),
          str(report['orphans']))
    check('stop 3: a pronoun carrying its own noun is NOT treated as orphaned',
          'This work exemplifies' in merged)


def test_orphan_repair_cannot_eat_a_stop():
    prose = ('Juan Gris died in 1927 leaving eleven lithographs. It was later '
             'finished. This became a famous book. That was that. Such is art.')
    story = 'Juan Gris died in 1927 leaving eleven lithographs, finished later.'
    merged, report = merge_story_into_description(prose, story)
    check('orphan drops stop at the budget', len(report['orphans']) <= 2,
          str(report['orphans']))
    check('at least one prose sentence survives', len(report['kept']) >= 1,
          str(report['kept']))


def test_no_story_is_a_no_op():
    merged, report = merge_story_into_description(STOP1_PROSE, '')
    check('no story: description returned byte-identical', merged == STOP1_PROSE)
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
               test_orphaned_opener_is_repaired,
               test_orphan_repair_cannot_eat_a_stop,
               test_no_story_is_a_no_op,
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
