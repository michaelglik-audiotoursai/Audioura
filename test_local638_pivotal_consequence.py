#!/usr/bin/env python3
"""test_local638_pivotal_consequence.py — LOCAL-638 Note 3.

Michael listened to Frick tour 523 (D640):
    "It would have been 9 or 10 if it told the consequences of such a decision and
     how the painting reflects that."
(Thomas More refused to acknowledge Henry VIII as head of the Church. The
consequence — his execution in 1535 — is in any source.)

When a stop narrates a pivotal decision or event (a refusal, a theft, a war, an
exile, a death sentence), the narration contract (LOCAL-617, work_first_evidence)
and the story pass (LOCAL-490, story_pass) must ask for its CONSEQUENCE and the
link back to the work, grounded in the stop's sources. These tests assert both
prompts carry that instruction.

Run: python3 -m pytest test_local638_pivotal_consequence.py -q
"""
import unittest

import work_first_evidence as wf
from story_pass import build_story_prompt


_MATRIX = {
    'canonical_title': 'Sir Thomas More',
    'venue_name': 'The Frick Collection',
    'medium': 'oil on panel',
}
_MATERIAL = [
    'Hans Holbein painted Sir Thomas More in 1527.',
    'More refused to acknowledge Henry VIII as Supreme Head of the Church of England.',
    'More was executed in 1535 for that refusal.',
]


class TestNarrationContractAsksForConsequence(unittest.TestCase):
    def setUp(self):
        self.text = wf.narration_contract_instruction(
            work_title="Sir Thomas More", artist="Hans Holbein",
            has_reception_evidence=False)

    def test_contract_names_pivotal_events(self):
        low = self.text.lower()
        self.assertIn("pivotal", low)
        # A representative sample of the pivotal-event vocabulary.
        for word in ("refusal", "exile", "execution", "death sentence", "theft", "war"):
            self.assertIn(word, low, f"{word!r} missing from the contract")

    def test_contract_requires_consequence_and_link_to_work(self):
        low = self.text.lower()
        self.assertIn("consequence", low)
        self.assertRegex(low, r"link.*back to the work|reflects? or foreshadows")

    def test_contract_forbids_inventing_the_consequence(self):
        low = self.text.lower()
        self.assertIn("never invent", low)
        self.assertRegex(low, r"only from the reference material|from the reference material")


class TestStoryPassAsksForConsequence(unittest.TestCase):
    def setUp(self):
        self.prompt = build_story_prompt(_MATRIX, _MATERIAL)

    def test_prompt_has_pivotal_consequence_block(self):
        low = self.prompt.lower()
        self.assertIn("pivotal decision or event", low)
        self.assertIn("consequence", low)

    def test_prompt_names_the_pivotal_vocabulary(self):
        low = self.prompt.lower()
        for word in ("refusal", "exile", "execution", "death sentence", "theft"):
            self.assertIn(word, low, f"{word!r} missing from the story prompt")

    def test_prompt_requires_link_back_to_object(self):
        low = self.prompt.lower()
        self.assertIn("link it back to the object", low)

    def test_prompt_grounds_consequence_in_sources_only(self):
        low = self.prompt.lower()
        self.assertRegex(low, r"only from the source material|never invent the outcome")

    def test_prompt_still_only_the_story(self):
        # The existing contract (story-only, source-bounded) is intact.
        self.assertIn("Only the story", self.prompt)
        self.assertIn("You may not add facts from memory", self.prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
