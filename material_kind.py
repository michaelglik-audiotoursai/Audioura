#!/usr/bin/env python3
"""material_kind.py — D489 step (a): is the retrieved material the right KIND?

**The gap, stated by measurement.** Every instrument we have for "is there enough
material for this stop" counts things. `generate_tour_text.py:613` classifies a
stop rich/medium/thin on a COUNT of unique QIDs; `:9120` gates replenishment on a
character floor; LOCAL-487's retry fires on a word floor. So the pipeline asks
*"is there enough?"* and never *"is it the right kind?"*

On the 2026-08-19 01:15 tour all three stops cleared the volume test with
140/143/249 words of retrieved material, and the story detector still refused all
three — correctly: *"someone is described, but nothing is risked, refused or
lost."* **The material was sufficient and useless.** Replenishment could not fire,
because by its own instrument nothing was wrong.

**What this module measures instead.** Under D487, the unit a story needs is
Prince's middle event: **an ACTIVE change of state with an agent.** Not a person —
D487 settled that a volcano, a fire, a war or a restoration campaign all act. So
this asks of each snippet: *does anything happen in it?*

**It reports. It does not gate, and it does not spend.** Deterministic, no API
call. LEAD's claim is that the volume verdict and the kind verdict disagree
constantly; that claim is exactly the shape that was wrong in D423 (LOCAL-410's
false zero, which nearly got published). So this logs both verdicts side by side
and changes nothing, and the disagreement rate decides whether a re-query loop is
worth building. Same discipline that D474/D485 applied to the value index.

Reuses `story_opportunity_scan`'s vocabularies rather than defining its own —
two modules disagreeing about what an action is would be D483's defect class,
which this session has now hit twice.
"""
import re
from typing import Dict, List

from story_opportunity_scan import (_AGENCY_VERB, _STAKES, split_sentences)

__all__ = ['classify_material', 'summarise_stop', 'has_agentive_action',
           'KIND_RICH', 'KIND_INERT', 'KIND_EVENTFUL']

# An AGENTLESS PASSIVE is a state wearing an action's clothes. "The book was
# published in 1971" contains an agency verb and names nobody who did anything —
# Prince's middle event requires an AGENT, and the 2026-08-19 review of the 01:15
# tour named this exact construction as the top remaining defect: "the passive
# voice is eating the actors... every one of these had a named human in it
# upstream." ("was posthumously realized", "the generous gift", "was instrumental
# in bringing".)
#
# So this module shares the scanner's VOCABULARY (D483: two modules must not
# disagree about what an action is) and adds one test the scanner does not need.
# The scanner reads finished prose, where the subject is established across
# sentences; this reads isolated retrieved snippets, where an agentless passive
# is genuinely all there is.
#
# "was published BY Broder" keeps its agent and still counts.
_AGENTLESS_PASSIVE = re.compile(
    r'\b(?:was|were|is|are|been|being|got)\s+(?:\w+ly\s+)?'
    r'(?P<verb>\w+ed)\b(?!\s+by\b)', re.IGNORECASE)


# [D489a r2] THE ATTRIBUTIVE-PARTICIPLE TRAP, found by the first pilot run.
#
# LOCAL-497 added the making verbs (published, printed, illustrated, bound...)
# because the scanner could not see "Louis Broder published the book". Museum
# catalogue prose uses the same words as ADJECTIVES, and the pilot's very first
# stop reported its best sentence as:
#
#     "Illustrated book with forty lithographs (including wrapper front and cover)."
#
# That is the purest catalogue line in the tour and it scored as an action. So
# the instrument built to tell catalogue prose from stories was counting
# catalogue prose as a story — silently, and in the direction that hides the
# disagreement it exists to find.
#
# These verbs therefore require EXPLICIT AGENT EVIDENCE, which is also exactly
# what Prince's middle event demands: a capitalised name immediately before
# ("Broder published"), or "by" immediately after ("printed by Mourlot").
_MAKING_VERBS = frozenset({
    'published', 'printed', 'issued', 'engraved', 'etched', 'lithographed',
    'bound', 'illustrated', 'translated', 'edited', 'cast', 'carved', 'wove',
    'forged', 'assembled', 'designed', 'built', 'commissioned',
})

_AGENT_BEFORE = re.compile(
    r'\b([A-ZÀ-ÖØ-Þ][\wÀ-ÿ.\'’-]+(?:\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÿ.\'’-]+)*|he|she|they|who)\s+$')


def _making_verb_has_agent(sentence: str, match) -> bool:
    """Is this making-verb occurrence attached to an actor?"""
    before = sentence[:match.start()]
    after = sentence[match.end():]
    if re.match(r'\s+by\b', after):
        return True
    return bool(_AGENT_BEFORE.search(before))


def has_agentive_action(sentence: str) -> bool:
    """True when something happens AND someone or something does it."""
    if not sentence or not _AGENCY_VERB.search(sentence):
        return False
    passive = {m.group('verb').lower()
               for m in _AGENTLESS_PASSIVE.finditer(sentence)}
    for m in _AGENCY_VERB.finditer(sentence):
        verb = m.group(0).lower()
        if verb in passive:
            continue          # action with the actor removed
        if verb in _MAKING_VERBS and not _making_verb_has_agent(sentence, m):
            continue          # "Illustrated book" — an adjective, not an act
        return True
    return False

KIND_EVENTFUL = 'eventful'   # something happens AND something is at stake
KIND_RICH = 'active'         # something happens, nothing is at stake
KIND_INERT = 'inert'         # nothing happens: description only


def classify_material(snippets: List[str]) -> Dict:
    """Classify retrieved material by whether it contains a change of state.

    Returns counts, not a verdict — the caller decides what to do, and for now
    the caller only prints.
    """
    sentences: List[str] = []
    for snip in snippets or []:
        if snip and isinstance(snip, str):
            sentences.extend(split_sentences(snip))

    active = [s for s in sentences if has_agentive_action(s)]
    staked = [s for s in sentences if _STAKES.search(s)]
    both = [s for s in sentences
            if has_agentive_action(s) and _STAKES.search(s)]
    # Reported separately so a run can show how much of the material is action
    # with the actor removed — the defect the 01:15 review ranked first.
    passive_only = [s for s in sentences
                    if _AGENCY_VERB.search(s) and not has_agentive_action(s)]

    if both:
        kind = KIND_EVENTFUL
    elif active:
        kind = KIND_RICH
    else:
        kind = KIND_INERT

    return {
        'kind': kind,
        'sentences': len(sentences),
        'chars': sum(len(s) for s in sentences),
        'active_sentences': len(active),
        'staked_sentences': len(staked),
        'eventful_sentences': len(both),
        'agentless_passive_sentences': len(passive_only),
        # The one sentence most likely to become the story, for the log line —
        # so a human reading the run can see WHAT the instrument found, not just
        # that it found something. D423: an instrument that reports only a
        # number is an instrument nobody can check.
        'best_sentence': (both[0][:140] if both
                          else (active[0][:140] if active else '')),
    }


def summarise_stop(stop_name: str, snippets: List[str],
                   volume_verdict: str = '') -> str:
    """One log line per stop, both verdicts side by side.

    `volume_verdict` is whatever the existing count-based instrument said
    ('rich'/'medium'/'thin'), so the disagreement is visible in the log rather
    than needing to be reconstructed afterwards.
    """
    m = classify_material(snippets)
    # [D489a r2] The pilot printed volume=COVERED and this flag never fired.
    # `needs_replenishment` returns the COVERAGE vocabulary — EMPTY, VENUE_ONLY,
    # COVERED, UNKNOWN (`story_replenish.py:60`) — not the rich/medium/thin
    # of the QID classifier at generate_tour_text.py:613. Comparing against the
    # wrong vocabulary meant the instrument would have reported ZERO
    # disagreements on every run, i.e. "LEAD's claim is wrong", for a reason
    # that has nothing to do with the claim. Both vocabularies are accepted, and
    # anything unrecognised is treated as "not a satisfied volume verdict" so
    # the flag fails silent rather than false-positive.
    _volume_satisfied = str(volume_verdict).strip().lower() in (
        'covered', 'rich', 'medium')
    # A story needs a change of state with something at stake. Material that is
    # merely 'active' has actions and no consequence — the 01:15 failure exactly.
    disagrees = _volume_satisfied and m['kind'] in (KIND_INERT, KIND_RICH)
    line = (f"[D489] material kind: stop='{stop_name[:38]}' "
            f"kind={m['kind']} volume={volume_verdict or 'n/a'} "
            f"sentences={m['sentences']} active={m['active_sentences']} "
            f"staked={m['staked_sentences']} eventful={m['eventful_sentences']} "
            f"passive={m['agentless_passive_sentences']}")
    if disagrees:
        line += "  <-- DISAGREE: enough material, wrong kind"
    if m['best_sentence']:
        line += f"\n         best: \"{m['best_sentence']}\""
    return line
