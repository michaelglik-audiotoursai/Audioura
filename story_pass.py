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
           'NO_STORY', 'sentences_in']

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
                       forbidden: str = '') -> str:
    """The prompt for the story and nothing else.

    Deliberately NOT a copy of the LOCAL-421 reinforcement block. That block had
    to shout ("read this LAST — it overrides everything above") because it was
    competing with five other jobs in the same prompt. With the story alone in
    its own call there is nothing to override, so the instruction can simply
    describe the task — which is what the lab prompt does, and the lab scores 64.
    """
    def f(key, default=''):
        return (matrix.get(key) or default).strip()

    facts = []
    for label, key in (('Work', 'canonical_title'), ('English title', 'english_title'),
                       ('Artist', 'artist'), ('Publisher', 'publisher'),
                       ('Printed by', 'printed_by'), ('Medium', 'medium'),
                       ('Credit line', 'credit_line'), ('Venue', 'venue_name')):
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

  A FACT connects the STOP to the EXHIBITION, the museum, the city or the country,
  THROUGH A PERSON WHO DID SOMETHING.

Build it around ONE NAMED PERSON and STAY WITH THEM. This matters and is the
commonest way these come out wrong: a sentence each about the publisher, the
printer and the donor is a list of credits, not a story, and it reads as one.

  Sentences 1–3: the SAME person. What they did, why they did it or what it cost
    them, and what followed. You may refer to them as "he" or "she" after the
    first naming — that reads better aloud than repeating the name.
  Then, and only then: connect outward to a second person, to this exhibition,
    or to this museum.

"X was a Catalan artist who worked in Paris" is not a story — it is a label.
"Broder published the book and had Mourlot pull every sheet by hand, so the
artist and the printer worked in the same room" is one: someone did something,
and something followed.

Aim for that shape. Where the material is plainer than the example, write the
plainer version — a real, small, sourced action beats an invented dramatic one.

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
  - No evaluation: not "stands as a testament to", not "showcasing a unique
    fusion", not "the transformative power of". Say what happened.
  - Plain prose for a voice to read aloud. No markdown, no headings, no bullets.
  - Reply with exactly {NO_STORY} and nothing else ONLY if the material names no
    person at all, or records nothing any person did. That is a narrow test: if
    there is a named publisher, printer, donor or collaborator and any action
    attributable to them, write the story. Do not answer {NO_STORY} because the
    material is less dramatic than the example — write the undramatic version.
    An invented story is the one unacceptable outcome, because it would enter
    upstream of every fact-check in the pipeline.

Write the story now."""
    return prompt


def generate_story_for_stop(matrix: Dict, material: List[str],
                            caller=None, model: str = None,
                            max_sentences: int = MAX_SENTENCES,
                            forbidden: str = '') -> Dict:
    """Run the story pass for one stop.

    `caller` is injectable — `caller(prompt, model) -> (text, cost)` — so the
    whole pass is testable with no key and no network, which is what D421 says
    an inline gate can never be.

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
                               forbidden=forbidden)
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
