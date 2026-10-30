#!/usr/bin/env python3
"""story_pass.py — D474: the story, as its own pass over its own object.

**The problem this exists to solve, stated by measurement.** The lab scores 64
doing one job. Production scores 42.8 ± 2.1 (D484) doing six in a single prompt:
orientation, directions, transitions, category voice, physical description, and —
appended last, as a block of shape instructions — the story.

That prompt does not have a story in it. It has an *instruction to produce* one,
competing with five other instructions, and nothing downstream can point at "the
story for this stop" because no such object exists. Steps 5 and 7 of Michael's
seven both need to reason about one:

  * step 5 assigns a value index TO a story;
  * step 7 picks the most valuable story, sizes it to 3–5 sentences, and rotates
    to the next fact when there is no valid one.

Both were being applied to a whole stop description instead, because that is the
only object there was.

**What this module does.** One focused call, one job: given the matrix and the
retrieved material, write the story. 3–5 sentences (Michael's step 7, which is
also why `STOP_WORD_BUDGET`'s 450-word packing was never the right shape). The
description prompt then RECEIVES a finished story rather than being asked to
invent one while doing five other things.

**Michael's constraint, and how it is honoured.** He ruled that this change must
land alone, with nothing else in it, or a regression is unattributable (D474).
He then asked for it overnight on 2026-08-18. It is therefore behind
`STORY_PASS_ENABLED`, defaulting ON but switchable, so the A/B is a flag flip
rather than a revert — which is a better version of the same protection.

**It never invents.** The pass is given only material already retrieved and paid
for, and is told to return NO_STORY rather than fabricate. An empty story is a
recoverable outcome; a fabricated one is the failure this whole gate chain exists
to prevent, and it would arrive upstream of every gate.
"""
import json
import os
import re
from typing import Dict, List, Optional

__all__ = ['generate_story_for_stop', 'build_story_prompt', 'STORY_PASS_ENABLED_ENV',
           'NO_STORY', 'sentences_in', 'MATRIX_SLOTS', 'MATRIX_KEYS']

# [D498] Step 3a — ONE slot vocabulary, shared by the producer and the consumer.
#
# `build_story_prompt` reads these keys; `generate_tour_text` used to build the
# same dict inline from a hand-copied list. They happened to match, and nothing
# enforced it — a renamed key would have silently emptied a slot rather than
# raising, because `f()` below falls back to ''.
#
# NOT routed through `interrogation_matrix.build_matrix`, deliberately. That
# module derives the matrix by PARSING STOP PROSE, which is the lab's input.
# Production already holds these facts structurally, off the exhibition
# checklist (LOCAL-419 enrichment). Re-deriving them from prose would throw away
# the better source to satisfy a diagram. `interrogation_matrix` keeps its own
# vocabulary (it calls the venue slot `venue`, this one calls it `venue_name`)
# because it answers a different question from a different input.
MATRIX_SLOTS = (
    ('Work', 'canonical_title'),
    ('English title', 'english_title'),
    ('Artist', 'artist'),
    ('Publisher', 'publisher'),
    ('Printed by', 'printed_by'),
    ('Medium', 'medium'),
    ('Credit line', 'credit_line'),
    ('Venue', 'venue_name'),
)
# The rotating focus fact (step 7b) is a slot but not a labelled fact line — it
# is rendered separately below — so it is listed apart from MATRIX_SLOTS.
MATRIX_KEYS = tuple(k for _, k in MATRIX_SLOTS) + ('focus_fact',)

STORY_PASS_ENABLED_ENV = 'STORY_PASS_ENABLED'
NO_STORY = 'NO_STORY'

# Michael's step 7: "make it to 3-5 sentences, in most valuable we can take a
# larger size". The upper bound is lifted for the stop that scores highest.
MIN_SENTENCES = 3
MAX_SENTENCES = 5
MAX_SENTENCES_TOP = 7


def is_enabled() -> bool:
    return (os.environ.get(STORY_PASS_ENABLED_ENV, '1') or '1').strip() != '0'


def sentences_in(text: str) -> int:
    if not text:
        return 0
    return len([s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()])


def build_story_prompt(matrix: Dict, material: List[str],
                       max_sentences: int = MAX_SENTENCES,
                       forbidden: str = '', works_mode: bool = False) -> str:
    """The prompt for the story and nothing else.

    Deliberately NOT a copy of the LOCAL-421 reinforcement block. That block had
    to shout ("read this LAST — it overrides everything above") because it was
    competing with five other jobs in the same prompt. With the story alone in
    its own call there is nothing to override, so the instruction can simply
    describe the task — which is what the lab prompt does, and the lab scores 64.

    `works_mode` — [LOCAL-837] the MUSEUM-WORKS path. The default prompt (Pompeii,
    LOCAL-493) correctly says a story need not be about a person: a place, a site
    or an event can carry one, because `story_opportunity_scan.can_carry` accepts
    `kind in ('proper noun', 'event')`. But the stop at a MUSEUM is a discrete
    artwork — a painting, a sculpture, a book — and that enters the scanner as a
    quoted `title`, which `can_carry` refuses BY DESIGN (a title names a thing,
    and things do not act). So on the museum-works path the only subject that can
    clear the bar is a PERSON connected to the work: the painter, the sitter, the
    patron, the thief, the restorer, the curator who hid it. Measured on the cheap
    arm (LOCAL-832B): the default prompt there wrote PROVENANCE ("the museum
    acquired it", "X gifted it" — no stake) or made the ARTWORK itself the subject
    ("The Night Watch was evacuated… hidden in a bunker" — `can_carry` refuses
    kind=='title'); 0/5 stops cleared the bar. `works_mode` tells the writer to
    build the story around the human who ACTED on the work, and to answer NO_STORY
    when the research records no human event — rather than falling back to
    provenance. It does NOT touch `can_carry` and does NOT game the scanner; it
    writes the one shape the scanner was always going to accept here. The default
    path is byte-for-byte unchanged (works_mode=False).
    """
    def f(key, default=''):
        return (matrix.get(key) or default).strip()

    facts = []
    for label, key in MATRIX_SLOTS:  # [D498] one vocabulary, defined once
        value = f(key)
        if value:
            facts.append(f"  {label}: {value}")
    # Michael's rotating focus fact (step 7). Its own slot, deliberately NOT
    # credit_line — LOCAL-406 regex-parses donor and printer out of that field,
    # so a fact written there is read as a person's name.
    focus = f('focus_fact')
    matrix_block = '\n'.join(facts) if facts else '  (no matrix fields available)'

    material_block = '\n'.join(f"  - {m.strip()}" for m in material if m and m.strip())
    if not material_block:
        material_block = '  (no source material retrieved)'

    prompt = f"""Write the STORY for one stop on a museum audio tour. Only the story.
Not an introduction, not directions, not a description of what the object looks
like — those are written elsewhere.

A STORY here has a specific meaning, and it is the only thing being asked for:

  SOMETHING CHANGED, SOMETHING CAUSED THE CHANGE, AND IT MATTERED.

Three parts, and all three must be there:

  1. How things stood.
  2. AN ACTION that changed it — this is the part that is usually missing.
  3. How things stood afterwards, which must differ from 1.

  "Pompeii was a living city. Vesuvius erupted in 79 AD. Pompeii was buried, and
  stayed buried for sixteen centuries." — that is the whole shape.

"""
    if works_mode:
        # [LOCAL-837] MUSEUM-WORKS PATH. The stop is a single artwork, which the
        # downstream scanner reads as a `title` and refuses to let carry a story
        # (titles name a thing; things do not act). So the subject here must be a
        # PERSON who did something to or around the work.
        prompt += """BUILD IT AROUND ONE NAMED PERSON AND STAY WITH THEM.

The stop is a single work of art — a painting, a sculpture, a print, a book. The
work itself CANNOT be the subject of this story: "The Night Watch was moved to a
bunker" is about the painting, and that is not a story here. Find the PERSON in
the research and make the story theirs:

  the painter who made it, the sitter who posed for it, the patron who paid for
  it, the dealer who sold it, the thief who stole it, the soldier or curator who
  hid it, the restorer who repaired it, the forger who copied it, the rival who
  attacked it.

Name that person and stay with them for all three sentences. Then "he" or "she"
after the first naming — that reads better aloud than repeating the name.

  Sentence 1: how things stood for that person, or what they faced.
  Sentence 2: THE ACTION they took — the decision, the theft, the refusal, the
    rescue, the move to the bunker. This is the sentence the work exists to tell.
  Sentence 3: what followed BECAUSE of it — the fate, the year, the outcome — and
    only then, if there is room, how the work in front of the listener carries it.

"The curator Arie van Schendel had The Night Watch rolled onto a cylinder and
moved to a bunker in Maastricht in 1939, because he feared German bombing would
destroy it; it stayed hidden underground until 1945." — ONE person, an action,
and a consequence. That is the shape, and the work is the OBJECT of the action,
never its subject.

PROVENANCE IS NOT A STORY. "The museum acquired it in 1897", "X bequeathed it",
"it was gifted by a collector", "it entered the collection" — these name a
transfer with nobody doing anything that cost or risked or changed anything. A
line of credits is the failure this path exists to prevent, because it is exactly
what gets written when no human event is found. If the only human fact in the
research is who owned it or who gave it, that is NOT a story — answer """ + NO_STORY + """.

"""
    else:
        prompt += """BUILD IT AROUND ONE NAMED SUBJECT AND STAY WITH THEM.

The subject may be A PERSON, but it does not have to be. A place, an institution,
a workshop, an eruption, a war, a fire, a restoration campaign, or the object
itself can all carry a story, provided they DO something in part 2. Do not refuse
to write a story because no person is named — write it about whatever acted.

"""
    prompt += f"""Staying with one subject is what matters, and abandoning it is the commonest way
these come out wrong: a sentence each about the publisher, the printer and the
donor is a list of credits, not a story, and it reads as one. When the subject is
a person you may say "he" or "she" after first naming them — that reads better
aloud than repeating the name.

  Sentences 1-3: the SAME subject throughout.
  Then, and only then: connect outward — to a second person, to this exhibition,
    to this museum, to the city. Say WHY that connection holds.

USE "BECAUSE", NOT "AND THEN". This is the difference between a story and a list.

  "The king died, and then the queen died" is a sequence.
  "The king died, and then the queen died OF GRIEF" is a story.

Same two events; the causal link is the whole difference. Every stop already has
a sequence of facts. Your job is the link between them.

"X was a Catalan artist who worked in Paris" is not a story — it is a label.
"Broder published the book and had Mourlot pull every sheet by hand, SO the
artist and the printer worked in the same room" is one: something was done, and
something followed BECAUSE of it.

IS IT WORTH TELLING? Before you write, check the change you have found:

  - Did it have consequences, for the subject or for what survives?
  - Was it unexpected, rather than what anyone would assume?
  - Did it stick — is it irreversible, or was it undone?
  - Did it happen ONCE? "The press published many editions" is a routine, not an
    event. "The 1967 edition was destroyed" is an event.

The test to apply when you finish: a listener who has just heard this should want
to say "IT DID?" or "HE DID?" — not "how interesting", and above all not
"so what?". If the only honest response is "so what?", you have written a label.

IF THE ACTION IS A PIVOTAL DECISION OR EVENT, GIVE ITS CONSEQUENCE. When part 2
is a refusal, a stand on principle, a betrayal, a theft, a battle or war, an
exile, a trial, an execution or death sentence, a martyrdom, a flight, a
conversion, a coronation or abdication, part 3 is not optional and is not vague:
state WHAT FOLLOWED from the act — the named outcome, the fate, the year — and
link it back to the object in front of the listener (how the work reflects,
commemorates or foreshadows that consequence). "He refused" is half a story; "he
refused, and was executed in 1535 for it, which is why this calm portrait reads
the way it does" is the whole one. Take the consequence ONLY from the source
material; if the material records the event but not its consequence, tell what it
does record and stop — never invent the outcome.

Where the material is plainer than the examples, write the plainer version — a
real, small, sourced action beats an invented dramatic one. Numbers earn this:
how many were destroyed, how long it lasted, how much was paid, what remains.

THE MATRIX FOR THIS STOP
{matrix_block}
"""
    if focus:
        prompt += f"""
FOCUS THIS STORY ON THIS FACT. Earlier attempts for this stop used other facts
and produced nothing valid, so this one is the subject now:
  {focus}
"""
    prompt += f"""
SOURCE MATERIAL — everything you may use. You may not add facts from memory.
{material_block}
"""
    if forbidden:
        prompt += forbidden
    prompt += f"""
RULES
  - Between {MIN_SENTENCES} and {max_sentences} sentences. No more.
  - Every name, date, place and number must appear in the source material above.
  - SHOW THE POINT, DO NOT ANNOUNCE IT. The story must make clear why it was
    worth telling — but through what was done, chosen, refused, lost or paid for.
    Never by commentary from outside: not "stands as a testament to", not
    "showcasing a unique fusion", not "the transformative power of", not
    "transformative", "vibrant", "profound" or "revolutionary". Test: delete
    every proper noun and every number from your sentence. If something is left
    that still sounds like praise, it is commentary — cut it and say what
    happened instead.
  - Plain prose for a voice to read aloud. No markdown, no headings, no bullets.
"""
    if works_mode:
        prompt += f"""  - Reply with exactly {NO_STORY} and nothing else when the material records no
    HUMAN EVENT connected to this work — when all it has is who owns it, who gave
    it, when it was acquired, bequeathed or exhibited, or a description of the
    work itself. Provenance and transfers of ownership are NOT human events here:
    a gift, a bequest, an acquisition and a loan are not actions anyone can be
    said to have DONE at a cost. Write the story ONLY when a named person did
    something to or around the work — made it, posed for it, paid for it, stole
    it, hid it, restored it, forged it, attacked it, or refused to part with it —
    and that act had a consequence. If the research has no such human event, say
    {NO_STORY} rather than dressing provenance up as a story; a storyless stop is
    a recoverable outcome, a provenance-list dressed as a story is not.
    An invented story is the one unacceptable outcome, because it would enter
    upstream of every fact-check in the pipeline.
"""
    else:
        prompt += f"""  - Reply with exactly {NO_STORY} and nothing else ONLY if the material records
    NOTHING THAT HAPPENED — no action, no change, by anyone or anything. That is
    a narrow test, and it is deliberately NOT a test for people. If there is a
    named publisher, printer, donor or collaborator and any action attributable
    to them, write the story. If there is no person at all but something still
    occurred — an eruption, a fire, a war, a demolition, a rebuilding, a
    rediscovery, a move from one collection to another — write THAT story, with
    the event as the subject. Do not answer {NO_STORY} because the material is
    less dramatic than the examples — write the undramatic version.
    An invented story is the one unacceptable outcome, because it would enter
    upstream of every fact-check in the pipeline.
"""
    prompt += """
Write the story now."""
    return prompt


def generate_story_for_stop(matrix: Dict, material: List[str],
                            caller=None, model: str = None,
                            max_sentences: int = MAX_SENTENCES,
                            forbidden: str = '', works_mode: bool = False) -> Dict:
    """Run the story pass for one stop.

    `caller` is injectable — `caller(prompt, model) -> (text, cost)` — so the
    whole pass is testable with no key and no network, which is what D421 says
    an inline gate can never be.

    `works_mode` — [LOCAL-837] forwarded to build_story_prompt. On the museum-
    works path the subject must be a PERSON connected to the work and provenance
    alone is NO_STORY; off it, the default (LOCAL-493) prompt is used unchanged.

    Returns {'story', 'sentences', 'ok', 'reason', 'cost', 'prompt'}.
    """
    result = {'story': '', 'sentences': 0, 'ok': False, 'reason': '',
              'cost': 0.0, 'prompt': ''}

    if not is_enabled():
        result['reason'] = 'story pass disabled'
        return result

    usable = [m for m in (material or []) if m and m.strip()]
    if not usable:
        # Running the pass with nothing to write from is how fabrication starts.
        result['reason'] = 'no source material — pass skipped rather than invited to invent'
        return result

    prompt = build_story_prompt(matrix, usable, max_sentences=max_sentences,
                               forbidden=forbidden, works_mode=works_mode)
    result['prompt'] = prompt

    if caller is None:
        caller = _default_caller

    try:
        text, cost = caller(prompt, model)
    except Exception as err:
        result['reason'] = f'story pass call failed: {type(err).__name__}: {err}'
        return result

    result['cost'] = cost or 0.0
    text = (text or '').strip()
    # Strip markdown the voice would stumble over, same as LOCAL-477 does
    # downstream — better to never emit it than to clean it up later.
    text = re.sub(r'\*{1,3}', '', text)
    text = re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.MULTILINE).strip()

    if not text or text.upper().startswith(NO_STORY):
        result['reason'] = 'model returned NO_STORY — material did not support one'
        return result

    count = sentences_in(text)
    result['story'] = text
    result['sentences'] = count
    if count < MIN_SENTENCES:
        result['reason'] = f'only {count} sentence(s); the bar is {MIN_SENTENCES}'
        return result
    result['ok'] = True
    result['reason'] = f'{count} sentences'
    return result


def _default_caller(prompt: str, model: str = None):
    """Real OpenAI call. Kept tiny and at the bottom so the logic above is pure."""
    import requests
    key = os.environ.get('OPENAI_API_KEY', '')
    model = model or os.environ.get('STORY_PASS_MODEL', 'gpt-4o')
    resp = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        data=json.dumps({
            'model': model,
            'messages': [
                {'role': 'system',
                 'content': 'You write factual, grounded narrative for museum audio tours. '
                            'You never state a fact that is not in the material you are given.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.6,
            'max_tokens': 400,
        }),
        timeout=90,
    )
    resp.raise_for_status()
    body = resp.json()
    text = body['choices'][0]['message']['content']
    usage = body.get('usage') or {}
    try:
        # `cost_rates`, not `cost_tracker` — the latter does not exist, and the
        # try/except was reporting every story-pass call as $0.0000 rather than
        # failing. A silent zero in a cost meter is worse than no meter.
        from cost_rates import llm_cost
        cost = llm_cost(model=model,
                        input_tokens=usage.get('prompt_tokens', 0),
                        output_tokens=usage.get('completion_tokens', 0))
    except Exception as err:
        print(f"  [LOCAL-490] cost unavailable for the story pass: {err}")
        cost = 0.0
    return text, cost
