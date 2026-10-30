#!/usr/bin/env python3
"""test_local842_scan_stakes_precision.py — the scanner must RECOGNISE a stake.

LEAD ruling D752: the D511 bar is UNCHANGED (one subject, an action, a stake, 3+
consecutive sentences). What changed is only the scanner's STAKES VOCABULARY: a
grounded human story of violence, loss, judgement or death — the stories the
LOCAL-840 per-work research now feeds the museum story pass — must no longer score
`stakes=0` and be reported as exposition.

The evidence this closes (LOCAL-840 submission): the delivered Night Watch stop
carries a complete human story —

    "On 14 September 1975, Wilhelmus de Rijk … attacked The Night Watch with a
     bread knife, slashing several large zig-zagged cuts … the painting was left
     permanently scarred. De Rijk died by suicide in April 1976 …"

— an action, a consequence and a stake, and the scanner scored it
`agency=1 stakes=0 → NO STORY` because `_STAKES` knew destroyed/lost/refused/
survived/bequeathed but not slashed/attacked/scarred/suicide.

TWO HALVES, asserted as a class (the shape of D483's audit):

  [1] WIDENING — the harm/loss/conflict/judgement vocabulary is recognised, and
      D512's "widening never narrows" property holds: every marker the scanner
      matched before still matches.

  [2] PRECISION — a stake word counts only in a sentence about a REAL event, never
      in a description of what the picture DEPICTS. "The painting shows a dying
      soldier", "a stolen kiss in the foreground", "depicts the burning of Troy"
      carry a stake word and NO story.

RED-CHECK notes on each class: the control sets (FALSE / precision) are what prove
the scanner did not simply become permissive.
"""
import unittest

import story_opportunity_scan as s


def scan(text):
    m = s.measure(text)
    return m, s.verdict(m)


def is_story(text):
    _, v = scan(text)
    return not v['needs_additional_story']


# ═══════════════════════════════════════════════════════════════════════════════
# THE DELIVERED STORIES — grounded verbatim in each work's Wikipedia article by
# the LOCAL-840 research, written by the museum story pass, reaching delivered text.
# ═══════════════════════════════════════════════════════════════════════════════

# The exact delivered Night Watch paragraph (LOCAL-840 submission, §"Why").
NIGHT_WATCH = (
    "On 14 September 1975, Wilhelmus de Rijk, an unemployed school teacher, "
    "attacked The Night Watch with a bread knife, slashing several large "
    "zig-zagged cuts up to 30 centimetres long into the canvas. "
    "The painting was left permanently scarred. "
    "De Rijk died by suicide in April 1976, before he could be charged.")

# Manet's Déjeuner — the 1863 Salon refusal, grounded in the work's Wikipedia
# ("Rejected by the Salon jury of 1863, Manet seized the opportunity … where the
# painting sparked public notoriety and controversy").
MANET = (
    "Édouard Manet was rejected by the official Salon jury in 1863. "
    "He seized the opportunity to exhibit the painting at the Salon des Refusés "
    "that same year. "
    "There he was mocked by the crowds, and the work sparked public notoriety "
    "and controversy.")

# Lacan and L'Origine du monde — grounded in the work's Wikipedia History
# ("Its new owner was the psychoanalyst Jacques Lacan … Lacan asked André Masson …
# to build a double bottom frame and draw another picture thereon").
LACAN = (
    "In 1955 the painting was sold at auction to the psychoanalyst Jacques Lacan. "
    "Lacan hid the canvas in his country house behind a double-bottomed frame. "
    "He asked his stepbrother André Masson to paint another picture to conceal it.")


class TestWidening_GroundedStoriesAreRecognised(unittest.TestCase):
    """RED-CHECK: revert the LOCAL-842 alternation in `_STAKES`. All three go red —
    each scores stakes=0 and is reported as exposition, exactly as in 840."""

    def test_delivered_night_watch_is_a_story(self):
        self.assertTrue(is_story(NIGHT_WATCH),
                        "the delivered Night Watch attack is still NO STORY")

    def test_night_watch_run_carries_the_stake(self):
        m, _ = scan(NIGHT_WATCH)
        lr = m['longest_run']
        self.assertEqual(lr['handle'], 'Wilhelmus de Rijk')
        self.assertGreaterEqual(lr['run'], 3)
        self.assertGreaterEqual(lr['agency'], 1)
        self.assertGreaterEqual(lr['stakes'], 1)

    def test_manet_salon_refusal_is_a_story(self):
        self.assertTrue(is_story(MANET))

    def test_lacan_hiding_is_a_story(self):
        self.assertTrue(is_story(LACAN))

    def test_the_harm_loss_judgement_vocabulary_is_seen(self):
        # Each listed in the ticket's Do-item 1 — a stake word in a real-event
        # sentence (no depiction cue), which must now register.
        for sent in (
            "The jury rejected the work.",
            "The mob attacked the statue.",
            "Vandals slashed the canvas.",
            "The painting was stolen from the gallery.",
            "The censors banned the book.",
            "The crowd mocked the artist.",
            "The work caused a scandal.",
            "Manet faced rejection from the Salon.",
            "The debut sparked controversy and notoriety.",
            "The painter was sued by his patron.",
            "He was arrested and imprisoned.",
            "The artist died by suicide the following year.",
            "He fled the country to escape his debts.",
            "The dealer went bankrupt and sold the lot to pay his debts.",
        ):
            self.assertTrue(s._sentence_has_stakes(sent),
                            f'stake not recognised: {sent!r}')

    def test_widening_never_narrows(self):
        # THE D512 SAFETY PROPERTY. Everything the pre-842 `_STAKES` matched must
        # still match: the alternation can only make the scanner see MORE stakes.
        for sent in (
            "Miró decided to destroy the lithographs.",          # destroyed/destroy
            "The edition was never finished.",                   # never / unfinished
            "Only the first proof survives.",                    # only / the first
            "Van Gogh left it to the Orsay after his death.",    # left … to / after his death
            "Caillebotte bequeathed it to the state.",           # bequeathed
            "He broke with the static group portrait.",          # broke with
            "The guardsmen complained that faces were hidden.",  # complained / hidden
        ):
            self.assertTrue(s._STAKES.search(sent),
                            f'widening lost a pre-842 marker: {sent!r}')
            self.assertTrue(s._sentence_has_stakes(sent),
                            f'widening lost a pre-842 marker: {sent!r}')

    def test_inflected_forms_match(self):
        for root, forms in {
            'attack': ['attacked', 'attacks', 'attacking'],
            'slash': ['slashed', 'slashes', 'slashing'],
            'steal': ['stole', 'stolen', 'stealing'],
            'reject': ['rejected', 'rejects', 'rejecting', 'rejection'],
            'mock': ['mocked', 'mocks', 'mocking'],
            'die': ['died', 'dies', 'dying'],
            'ban': ['banned', 'bans', 'banning'],
        }.items():
            for f in forms:
                self.assertTrue(s._STAKES.search(f"The jury {f} the work."),
                                f'{f!r} ({root}) not matched')


class TestPrecision_DepictionIsNotAStake(unittest.TestCase):
    """RED-CHECK: make `_sentence_has_stakes` return `bool(_STAKES.search(...))`
    (i.e. drop the depiction guard). `test_ten_depiction_sentences_are_not_a_story`
    goes red — the burning/stolen/dying content starts counting as real stakes."""

    DEPICTION = (
        "The painting shows a dying soldier at the center. "
        "In the foreground, a stolen kiss unfolds between two lovers. "
        "The canvas depicts the burning of Troy. "
        "A slain warrior lies in the background. "
        "The scene portrays a city under attack. "
        "To the left, a child is being abducted. "
        "The mural depicts martyrs being executed. "
        "In the background, a ship is wrecked on the rocks. "
        "The fresco shows a king condemned to death. "
        "A woman mourns her murdered husband in the foreground.")

    def test_ten_depiction_sentences_are_not_a_story(self):
        self.assertFalse(is_story(self.DEPICTION))

    def test_no_depiction_sentence_spends_its_stake_word(self):
        m, _ = scan(self.DEPICTION)
        self.assertEqual(m['total_stakes'], 0,
                         'a depiction sentence counted as a real stake')

    def test_individual_depiction_cues_suppress_the_stake(self):
        for sent in (
            "The painting shows a dying soldier.",
            "The canvas depicts the burning of Troy.",
            "In the foreground, a stolen kiss unfolds.",
            "In the background, a ship is burning.",
            "The scene portrays a king condemned to death.",
            "At the centre, a martyr is executed.",
            "To the left, a child is being murdered.",
            "The composition shows a murdered husband.",
        ):
            self.assertTrue(s._STAKES.search(sent),
                            f'fixture: {sent!r} must contain a stake word')
            self.assertFalse(s._sentence_has_stakes(sent),
                             f'depiction counted as a stake: {sent!r}')

    def test_a_real_event_is_not_suppressed_by_a_stray_depiction_word(self):
        # The guard keys on the sentence being ABOUT the image. A real event that
        # contains none of the depiction cues must still count.
        for sent in (
            "De Rijk attacked the painting with a bread knife.",
            "The Salon jury rejected the work in 1863.",
            "Thieves stole the canvas from the gallery.",
            "Lacan hid the painting behind a panel for decades.",
        ):
            self.assertTrue(s._sentence_has_stakes(sent),
                            f'real event wrongly suppressed: {sent!r}')


class TestControls_StillRefusesNonStories(unittest.TestCase):
    """The scanner must not have simply become permissive."""

    def test_exposition_is_still_refused(self):
        exposition = ("Joan Miró was a Catalan artist who worked in Paris. "
                      "He was known for his surrealist imagery. "
                      "His work is celebrated worldwide for its vibrant colour.")
        self.assertFalse(is_story(exposition))

    def test_a_catalogue_is_still_refused(self):
        catalogue = ("The gallery holds forty lithographs. "
                     "The gallery is named for the Linde Family. "
                     "The collection is displayed in rotation.")
        self.assertFalse(is_story(catalogue))

    def test_a_pure_depiction_passage_is_still_refused(self):
        # Even when the same figure is "held" across three sentences, a depiction
        # is not a story: the stake words are suppressed, so there is no load.
        depict_run = ("The painting shows a dying soldier. "
                      "The soldier is being stabbed in the chest. "
                      "Behind the dying soldier, a city burns.")
        self.assertFalse(is_story(depict_run))


if __name__ == '__main__':
    unittest.main(verbosity=2)
