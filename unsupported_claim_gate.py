#!/usr/bin/env python3
"""unsupported_claim_gate.py — LOCAL-263: One gate for unsupported claims.

Michael's rule (D166): a sentence is bad unsupported and good supported.
The entire difference is what comes next. This gate classifies what a sentence
asserts (PROMISE, SENSORY, FEELING, QUALITY) and checks whether something
adjacent substantiates it with a concrete payload on the same subject.

Four claim types, one shared substantiation test:
  PROMISE — "holds stories that deepen the allure" (previously R10)
  SENSORY — "the waves crash against the rocky shore" (previously R7, partially)
  FEELING — "invites contemplation and serenity" (previously R4, partially)
  QUALITY — "holds a significant place in the region's landscape" (previously nothing)

Substantiation = a nearby sentence supplies a date, a named person and what they
did, a documented event, or a measurement — on the same subject.

Navigation is exempt (D107). D164: a navigation sentence may carry an appended
instruction — "Start cycling southeast on the main road, enjoy the sea breeze"
survives.

Escalation: when deterministic stage cannot decide, an LLM call adjudicates
using only the stop's corpus passages. One call per stop max.

Deterministic. $0.00 unless escalation fires. Read-only against the database.
"""
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from style_validator_detector import (
    _is_style_navigation_sentence,
    _split_sentences,
    _sentence_has_concrete_payload,
    _extract_content_words,
    _delivery_matches_promise,
    _DANGLING_CONNECTIVE_COMPILED,
    _R10_STOPWORDS,
    _R10_ABSTRACT_FILLERS,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIM TYPE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

# PROMISE: sentence promises a story/tale/history/legacy without delivering it
# (Reuses R10's existing promise patterns)
_PROMISE_PATTERNS = [
    r'\bhold(?:s|ing)?\s+(?:a\s+)?(?:stor(?:y|ies)|tale[s]?|secret[s]?|chapter[s]?)\b',
    r'\b(?:multitude|wealth|treasure)\s+of\s+(?:tales?|stories?|secrets?|legends?)\b',
    r'\brich\s+tapestry\s+of\s+(?:history|culture|stories?|heritage)\b',
    r'\ba\s+testament\s+to\s+(?:the\s+)?(?:enduring\s+)?(?:allure|legacy|spirit|charm|beauty|power)\b',
    r'\bbridge\s+between\s+(?:ancient|past|old)\b',
    r'\bsymphony\s+of\s+(?:past\s+and\s+present|old\s+and\s+new)\b',
    r'\bwitness\s+to\s+(?:centuries|generations|ages|history|time)\b',
    r'\b(?:delving|diving|exploring|dipping)\s+into\s+(?:a\s+)?(?:rich\s+)?(?:tapestry|world|realm)\b',
    r'\bwhisper[s]?\s+(?:tales?|stories?|of\s+(?:a\s+)?bygone)\b',
    r'\btales?\s+(?:from|of)\s+(?:a\s+)?bygone\b',
    r'\bsteeped\s+in\s+(?:history|tradition|heritage|legend|lore)\b',
    r'\bechoes?\s+of\s+(?:a\s+)?(?:bygone|the\s+past|history|time)\b',
    r'\ba\s+chapter\s+in\s+(?:the|its|a)\b',
    r'\benduring\s+(?:legacy|spirit|allure|charm|beauty|appeal)\b',
    r'\bcenturies\s+of\s+(?:history|tradition|heritage|culture|stories?)\b',
    r'\bsense\s+of\s+(?:antiquity|history|heritage|the\s+past|time)\b',
    r'\b(?:thread|fabric)\s+(?:weaving|of\s+time|through\s+time)\b',
    r'\bconnection\s+between\s+(?:past\s+and\s+present|old\s+and\s+new|then\s+and\s+now)\b',
    r'\b(?:transport|take|carry)\s+(?:visitors?|you|us)\s+back\s+(?:through|in|to)\b',
    r'\btimeless\s+(?:allure|appeal)\s+(?:of|resides)\b',
]
_PROMISE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PROMISE_PATTERNS]

# SENSORY: sentence asserts a sensory experience (sound, sight, smell, touch)
# that is atmospheric rather than factual
_SENSORY_PATTERNS = [
    # Waves, sea sounds, wind
    r'\b(?:the\s+)?(?:waves?\s+(?:crash|lap|break|pound|roll|splash))',
    r'\b(?:the\s+)?(?:sound|roar|thunder|crash|splash)\s+of\s+(?:waves?|the\s+sea|the\s+ocean|water)',
    r'\b(?:the\s+)?(?:gentle|soft|rhythmic|crashing)\s+(?:lapping|crashing|splashing|breaking)\s+of\s+(?:waves?|water)',
    # Breeze, wind
    r'\b(?:the\s+)?(?:gentle|salty|warm|cool|fresh|sea|soft)\s+(?:\w+\s+)?(?:breeze|wind)\s+(?:carries|brings|whispers|caresses|rustles)',
    r'\b(?:the\s+)?(?:breeze|wind)\s+(?:carries|brings|whispers|caresses|rustles)',
    # Calls of birds
    r'\b(?:calls?|cries?|songs?)\s+of\s+(?:seagulls?|birds?|gulls?)\b',
    r'\bseagulls?\s+(?:soaring|circling|calling|crying)\b',
    # Sun, warmth on skin
    r'\b(?:the\s+)?(?:warmth|heat|glow)\s+of\s+the\s+sun\s+on\s+(?:your|the)\b',
    r'\bsun\s+(?:warms?|bathes?|kisses?|caresses?)\b',
    # Scent/smell claims
    r'\b(?:the\s+)?(?:salty|sweet|fresh|fragrant)\s+(?:scent|smell|aroma|fragrance)\s+(?:of|fills)\b',
    r'\b(?:scent|smell|aroma|fragrance)\s+of\s+the\s+(?:sea|ocean|Mediterranean|flowers?|pine)',
    # Fabricated soundscape
    r'\b(?:the\s+)?(?:distant|faint|gentle|soft)\s+(?:chime|tolling|ringing|peal)\s+of\s+(?:church\s+)?bells?\b',
    r'\b(?:the\s+)?(?:rustling|whisper|murmur|babble)\s+of\s+(?:leaves|trees|wind|water|the\s+breeze)',
    # Stretching endlessly / Mediterranean imagery
    r'\b(?:Mediterranean|sea|ocean|water)\s+(?:stretching|spreading|extending)\s+(?:out\s+)?(?:endlessly|infinitely|before)',
    # "filled with the scent/smell/aroma of" — atmospheric scent claim
    r'\bfilled\s+with\s+(?:the\s+)?(?:scent|smell|aroma|fragrance)\s+of\b',
    # "creating a [unique/special/coastal] aroma/atmosphere"
    r'\bcreating\s+(?:a\s+)?(?:unique|special|coastal|salty|fresh|tropical)\s+(?:aroma|atmosphere|ambiance|ambience)\b',
    # "[waters/waves] [gently/softly] lap/crash against"
    r'\b(?:waters?|waves?)\s+(?:gently|softly|rhythmically)?\s*(?:lap|crash|break|splash|pound)\s+(?:against|on|upon)\b',
    # "gently/softly [verb] against" (adverb before sensory verb)
    r'\b(?:gently|softly|rhythmically)\s+(?:lap|crash|break|splash|pound|lapping|crashing)\s+(?:against|on|upon)\b',
    # "the scent of [X] and [Y]" — multi-sensory fabrication
    r'\b(?:scent|smell|aroma|fragrance)\s+of\s+\w+\s+and\s+\w+\s*(?:trees?|flowers?|herbs?)?\b.*\b(?:creating|producing|offering|filling)\b',
    # "sound of waves/water [verb]" pattern
    r'\b(?:the\s+)?(?:rhythmic|gentle|soft|distant|crashing)?\s*(?:sound|roar|crash|splash)\s+of\s+(?:waves?|water|the\s+sea|the\s+ocean)\s+(?:crash|echo|resound|fill|accompan)',
]
_SENSORY_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSORY_PATTERNS]

# FEELING: sentence prescribes or asserts an emotional/contemplative state
_FEELING_PATTERNS = [
    r'\binvites?\s+(?:contemplation|serenity|reflection|meditation|wonder|awe|introspection)\b',
    r'\b(?:contemplation|serenity|tranquility|tranquillity|peace|calm)\b.*\b(?:washes?|settles?|descends?|fills?|envelops?)\b',
    r'\byou\s+(?:feel|sense|experience|are\s+(?:overcome|struck|overwhelmed|moved|transported|enveloped|surrounded))\b',
    r'\b(?:sense|feeling|atmosphere|aura)\s+of\s+(?:serenity|peace|calm|tranquility|contemplation|wonder|awe|reverence)\b',
    r'\b(?:serene|tranquil|peaceful|contemplative|meditative)\s+(?:atmosphere|ambiance|ambience|setting|mood)\b',
    r'\byou\s+(?:can|could|will|would|may|might)\s+(?:feel|sense|experience)\b',
    r'\bimmerse\s+yourself\b',
    r'\byou\s+find\s+yourself\b',
    # "creates a serene atmosphere" — fabricated ambiance
    r'\b(?:creates?|produces?|evokes?|conjures?)\s+(?:a\s+)?(?:sense|feeling|atmosphere|aura|mood)\s+of\s+(?:serenity|peace|calm|tranquility|contemplation)',
    # "inviting you to ponder/reflect/contemplate"
    r'\binviting\s+(?:you\s+)?(?:to\s+)?(?:ponder|reflect|contemplate|consider|meditate|marvel)\b',
    # "you are surrounded by history and natural beauty"
    r'\byou\s+are\s+surrounded\s+by\b',
]
_FEELING_COMPILED = [re.compile(p, re.IGNORECASE) for p in _FEELING_PATTERNS]

# QUALITY: sentence asserts significance/importance/special status without evidence
_QUALITY_PATTERNS = [
    # "holds a [significant/special/important] place in [the region's X]"
    r'\bholds?\s+(?:a\s+)?(?:significant|special|important|prominent|unique|notable|vital|central)\s+(?:place|position|role|status)\b',
    # "forms [distinctive/significant] [feature/landmark]"
    r'\bforms?\s+(?:a\s+)?(?:distinctive|significant|notable|prominent|important)\s+(?:feature|landmark|part|element)\b',
    # "is a [significant/important/major] [noun] in/of the [region]"
    r'\bis\s+(?:a\s+)?(?:significant|important|major|key|notable|prominent)\s+(?:feature|landmark|destination|attraction|part|element|hub)\b',
    # "holds stories/place" without following detail
    r'\bholds?\s+(?:a\s+)?(?:special|significant|important)\s+place\s+in\s+(?:the\s+)?(?:region|area|coast|city|town)\'?s?\s+(?:history|culture|landscape|heritage)\b',
    # "plays a [vital/crucial] role"
    r'\bplays?\s+(?:a\s+)?(?:vital|crucial|key|important|significant|central)\s+(?:role|part)\b',
    # "is renowned/famous/known for its [X]" without saying what X is
    r'\bis\s+(?:renowned|famous|known|celebrated|noted)\s+for\s+its\s+(?:beauty|charm|elegance|history|heritage|culture|architecture|landscape|scenery)\b',
]
_QUALITY_COMPILED = [re.compile(p, re.IGNORECASE) for p in _QUALITY_PATTERNS]

# EXHORTATION (LOCAL-271): sentence urges the listener toward a vague experience
# without naming WHAT lies ahead. "Just ahead, journey back through the centuries."
# — tells the listener to do something but doesn't say what's there.
# Must NOT match sentences that name a concrete target: "Just ahead, the Chapelle..."
_EXHORTATION_PATTERNS = [
    # "Journey back through the centuries/ages/time"
    r'\bjourney\s+back\s+(?:through|across|into)\s+(?:the\s+)?(?:centuries|ages|time|history|past)\b',
    # "Step into a world where..." — vague invitation
    r'\bstep\s+into\s+(?:a\s+)?(?:world|realm|era|time|place)\s+(?:where|of|in which)\b',
    # "Prepare to be transported/taken/carried to/into..."
    r'\bprepare\s+to\s+be\s+(?:transported|taken|carried|swept|whisked)\b',
    # "Transport yourself to another era/time/world"
    r'\btransport\s+yourself\s+(?:to|into)\s+(?:a(?:nother)?|the)\s+(?:era|time|world|age|period|past)\b',
    # "Let history come alive" / "Watch history unfold"
    r'\b(?:let|watch|see|feel)\s+(?:the\s+)?history\s+(?:come alive|unfold|surround|envelop)\b',
    # "Prepare to discover/explore/uncover" (without naming what)
    r'\bprepare\s+to\s+(?:discover|explore|uncover|experience|witness)\b',
    # "Get ready to" (without naming what)
    r'\bget\s+ready\s+to\s+(?:discover|explore|experience|witness|uncover|be\s+(?:amazed|transported|swept))\b',
    # "Just ahead, [verb imperative]" where the verb is vague (journey/step/prepare/discover)
    r'\bjust\s+ahead[,.]?\s*(?:you\s+(?:can|will)\s+)?(?:journey|step|discover|explore|experience|uncover|find)\s+(?:back|into|through)\b',
    # "Step back in time" / "Travel back in time"
    r'\b(?:step|travel|go|venture)\s+back\s+in\s+time\b',
    # "Enter a world of" + abstract noun
    r'\b(?:enter|step\s+into)\s+(?:a\s+)?world\s+of\s+(?:wonder|mystery|enchantment|beauty|history|art|culture)\b',
    # "Discover what lies ahead/beyond/within" (vague — doesn't name it)
    r'\bdiscover\s+what\s+(?:lies|awaits|lurks)\s+(?:ahead|beyond|within|beneath)\b',
    # "Be transported to another era/time"
    r'\bbe\s+transported\s+to\s+(?:a(?:nother)?|the)\s+(?:era|time|world|age|period|past)\b',
]
_EXHORTATION_COMPILED = [re.compile(p, re.IGNORECASE) for p in _EXHORTATION_PATTERNS]


def classify_claim(sentence: str) -> Optional[str]:
    """Classify what type of claim a sentence makes.

    Returns one of: 'PROMISE', 'SENSORY', 'FEELING', 'QUALITY', 'EXHORTATION', or None.
    A sentence with none of these is not a claim and is left alone.
    Navigation is exempt (checked by caller).
    """
    stripped = sentence.strip()
    if not stripped or len(stripped) < 15:
        return None

    # Check in priority order: PROMISE > SENSORY > FEELING > QUALITY > EXHORTATION
    for pat in _PROMISE_COMPILED:
        if pat.search(stripped):
            return 'PROMISE'

    for pat in _SENSORY_COMPILED:
        if pat.search(stripped):
            return 'SENSORY'

    for pat in _FEELING_COMPILED:
        if pat.search(stripped):
            return 'FEELING'

    for pat in _QUALITY_COMPILED:
        if pat.search(stripped):
            return 'QUALITY'

    # LOCAL-271: Empty exhortation — urges listener toward vague experience
    for pat in _EXHORTATION_COMPILED:
        if pat.search(stripped):
            return 'EXHORTATION'

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SUBSTANTIATION TEST — shared for all four types
# ═══════════════════════════════════════════════════════════════════════════════

# Look-ahead/look-back window
_LOOKAHEAD = 2
_LOOKBACK = 1


def _extract_place_names(sentence: str) -> set:
    """Extract place-related proper nouns from a sentence.

    Returns lowercased place name fragments for geographic co-reference.
    Includes: multi-word capitalized sequences, known geographic words.
    """
    places = set()
    # Find capitalized word sequences (potential place names)
    words = sentence.split()
    i = 0
    while i < len(words):
        word = words[i]
        clean = re.sub(r'[^a-zA-Z\u00C0-\u024F\'-]', '', word)
        if clean and len(clean) > 1 and clean[0].isupper():
            # Collect consecutive capitalized words
            name_parts = [clean.lower()]
            j = i + 1
            while j < len(words):
                next_clean = re.sub(r'[^a-zA-Z\u00C0-\u024F\'-]', '', words[j])
                # Allow particles (d', de, du) and capitalized words
                if next_clean and next_clean[0].isupper() and len(next_clean) > 1:
                    name_parts.append(next_clean.lower())
                    j += 1
                elif next_clean.lower() in ("d'", "de", "du", "la", "le", "les",
                                            "des", "di", "del", "van", "von"):
                    name_parts.append(next_clean.lower())
                    j += 1
                elif "'" in next_clean:
                    # Handle d'Antibes as one token
                    name_parts.append(next_clean.lower())
                    j += 1
                else:
                    break
            # Add individual parts and the full name
            for part in name_parts:
                if len(part) > 2 and part not in ('the', 'this', 'that', 'and', 'for'):
                    places.add(part)
            if len(name_parts) > 1:
                places.add(' '.join(name_parts))
            i = j
        else:
            i += 1
    return places


def _geographic_co_reference(claim_sent: str, delivery_sent: str) -> bool:
    """Check if two sentences refer to the same geographic area.

    Michael's rule: a quality claim about "this cape" / "the region" is
    substantiated by a fact about Antibes/Alpes-Maritimes/Nice because they
    are the SAME geographic context. Lexical overlap is too strict.

    Strategy: if both sentences contain place names from the same area, or
    if the delivery sentence has a concrete fact (date/number) and refers to
    a place that is plausibly the same as the claim's referent, they co-refer.
    """
    claim_places = _extract_place_names(claim_sent)
    delivery_places = _extract_place_names(delivery_sent)

    # Direct overlap: shared place name
    if claim_places & delivery_places:
        return True

    # Geographic context words in the claim that signal "this area"
    _area_refs = {'region', 'area', 'coast', 'coastline', 'peninsula', 'cape',
                  'landscape', 'shore', 'shoreline', 'riviera', 'village',
                  'town', 'city'}
    claim_lower = claim_sent.lower()
    has_area_ref = any(w in claim_lower for w in _area_refs)

    # If the claim refers to "the region/area/coast" and the delivery has
    # a concrete fact with a place name, assume co-reference within the same
    # stop context (they're adjacent sentences about the same stop)
    if has_area_ref and delivery_places:
        return True

    # Deictic references: "this cape", "this iconic cape", "the region's"
    _deictics = ['this', 'the', 'its', "region's", "area's"]
    has_deictic = any(d in claim_lower.split() for d in _deictics)
    if has_deictic and delivery_places:
        return True

    return False


def _is_substantiated(sentences: List[str], index: int) -> bool:
    """Check if the claim at sentences[index] is substantiated by neighbours.

    Substantiation = a nearby sentence (forward _LOOKAHEAD, back _LOOKBACK)
    supplies a concrete payload ON THE SAME SUBJECT:
      - a date/year
      - a named person and what they did
      - a documented event
      - a measurement

    Uses TWO matching strategies:
    1. Lexical: shared content words (R10's _delivery_matches_promise)
    2. Geographic: both sentences refer to the same place/area

    Michael's rule (D166): "is good because it immediately followed by [the
    fact] that supports it" — geographic co-reference counts.
    """
    sentence = sentences[index]

    # Does THIS sentence self-deliver? (claim + evidence in same sentence)
    if _sentence_has_concrete_payload(sentence):
        return True

    def _matches(claim, delivery):
        """Check if delivery substantiates claim (lexical OR geographic)."""
        if _delivery_matches_promise(claim, delivery):
            return True
        if _geographic_co_reference(claim, delivery):
            return True
        return False

    # Look forward
    for offset in range(1, _LOOKAHEAD + 1):
        next_idx = index + offset
        if next_idx >= len(sentences):
            break
        next_sent = sentences[next_idx].strip()
        if not next_sent:
            continue
        if _sentence_has_concrete_payload(next_sent):
            if _matches(sentence, next_sent):
                return True

    # Look backward
    for offset in range(1, _LOOKBACK + 1):
        prev_idx = index - offset
        if prev_idx < 0:
            break
        prev_sent = sentences[prev_idx].strip()
        if not prev_sent:
            continue
        if _sentence_has_concrete_payload(prev_sent):
            if _matches(sentence, prev_sent):
                return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# ESCALATION — LLM adjudication for uncertain cases
# ═══════════════════════════════════════════════════════════════════════════════

def _escalate_batch(sentences_with_indices: List[Tuple[int, str]],
                    corpus_passages: List[str],
                    api_key: str,
                    model: str = None) -> Tuple[Dict[int, str], int, float]:
    """Escalate uncertain claims to an LLM for adjudication.

    The model's job is narrow:
    1. Verify whether a corpus passage actually substantiates the claim.
    2. If it does, rewrite the claim and its support as a coherent sentence set.
    3. If it cannot ground the claim, return "delete".

    Args:
        sentences_with_indices: list of (original_index, sentence_text)
        corpus_passages: the stop's corpus passages
        api_key: OpenAI API key
        model: model name (defaults to gpt-4o-mini for cost)

    Returns:
        (results_dict, tokens_used, cost)
        results_dict maps original_index → rewritten text or None (delete)
    """
    import requests as _req
    import json

    if not model:
        model = os.environ.get('ESCALATION_MODEL', 'gpt-4o-mini')

    if not sentences_with_indices or not corpus_passages:
        return {}, 0, 0.0

    # Build the corpus context (limit to avoid token explosion)
    corpus_text = "\n\n".join(corpus_passages[:5])
    if len(corpus_text) > 3000:
        corpus_text = corpus_text[:3000] + "..."

    # Build the claims list
    claims_block = "\n".join(
        f"{i+1}. \"{sent}\"" for i, (_, sent) in enumerate(sentences_with_indices)
    )

    prompt = f"""You are adjudicating tour narration claims against source material.

CORPUS (the only facts you may use):
---
{corpus_text}
---

CLAIMS to adjudicate:
{claims_block}

For EACH claim, do exactly one of:
A) If the corpus passage substantiates the claim, output: KEEP: [claim number]
B) If you can ground the claim by combining it with a corpus fact into a coherent sentence, output: REWRITE [claim number]: [rewritten sentence using only corpus facts]
C) If the corpus does not support the claim at all, output: DELETE: [claim number]

RULES:
- You may ONLY use facts from the corpus above. Do NOT add any fact.
- A "rewrite" must contain only information present in the corpus.
- If uncertain, prefer DELETE over inventing support.
- Output one line per claim, numbered to match.
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You adjudicate claims against source material. Be strict: only corpus facts count."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30,
        )
        if resp.status_code != 200:
            # API error — default to delete (safe fallback)
            return {idx: None for idx, _ in sentences_with_indices}, 0, 0.0

        result = resp.json()
        text = result["choices"][0]["message"]["content"].strip()
        tokens_used = result.get("usage", {}).get("total_tokens", 0)

        # Cost calculation for gpt-4o-mini: ~$0.15/1M input, ~$0.60/1M output
        # Approximate: $0.0003 per 1K tokens
        cost = tokens_used * 0.0003 / 1000

        # Parse response
        results = {}
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            # Match "KEEP: N" or "DELETE: N" or "REWRITE N: text"
            keep_match = re.match(r'(?:KEEP|keep)\s*:?\s*(\d+)', line)
            delete_match = re.match(r'(?:DELETE|delete)\s*:?\s*(\d+)', line)
            rewrite_match = re.match(r'(?:REWRITE|rewrite)\s*(\d+)\s*:\s*(.+)', line)

            if keep_match:
                claim_num = int(keep_match.group(1)) - 1
                if 0 <= claim_num < len(sentences_with_indices):
                    orig_idx = sentences_with_indices[claim_num][0]
                    results[orig_idx] = sentences_with_indices[claim_num][1]  # Keep original
            elif rewrite_match:
                claim_num = int(rewrite_match.group(1)) - 1
                rewritten = rewrite_match.group(2).strip()
                if 0 <= claim_num < len(sentences_with_indices):
                    orig_idx = sentences_with_indices[claim_num][0]
                    results[orig_idx] = rewritten
            elif delete_match:
                claim_num = int(delete_match.group(1)) - 1
                if 0 <= claim_num < len(sentences_with_indices):
                    orig_idx = sentences_with_indices[claim_num][0]
                    results[orig_idx] = None  # Delete

        # Any claims not addressed — default to delete
        for idx, _ in sentences_with_indices:
            if idx not in results:
                results[idx] = None

        return results, tokens_used, cost

    except Exception:
        # Network/parse error — default to delete
        return {idx: None for idx, _ in sentences_with_indices}, 0, 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GATE — apply to a stop description
# ═══════════════════════════════════════════════════════════════════════════════

def apply_unsupported_claim_gate(
    description: str,
    corpus_passages: List[str] = None,
    api_key: str = None,
    model: str = None,
) -> Tuple[str, Dict]:
    """Apply the unsupported-claim gate to a stop description.

    Two stages:
    1. Classify each sentence's claim type (PROMISE/SENSORY/FEELING/QUALITY/None)
    2. For claims: check substantiation. Unsubstantiated → remove.

    Escalation: if deterministic stage cannot decide AND corpus holds a
    plausibly relevant passage, escalate to LLM. One call per stop max.

    Args:
        description: the stop's description text
        corpus_passages: the stop's corpus passages (for escalation)
        api_key: OpenAI API key (for escalation; None = deterministic only)
        model: LLM model for escalation

    Returns:
        (new_description, stats_dict)
        stats_dict has keys: sentences_removed, claim_types_removed,
        escalation_tokens, escalation_cost, escalation_fired
    """
    stats = {
        'sentences_removed': 0,
        'claim_types_removed': {'PROMISE': 0, 'SENSORY': 0, 'FEELING': 0, 'QUALITY': 0, 'EXHORTATION': 0},
        'sentences_kept_substantiated': 0,
        'escalation_tokens': 0,
        'escalation_cost': 0.0,
        'escalation_fired': False,
    }

    if not description or not description.strip():
        return description, stats

    paragraphs = [p for p in description.split('\n\n') if p.strip()]
    if not paragraphs:
        return description, stats

    new_paragraphs = []

    for para in paragraphs:
        para = para.strip()
        if len(para) <= 30:
            new_paragraphs.append(para)
            continue

        sentences = _split_sentences(para)
        if not sentences:
            new_paragraphs.append(para)
            continue

        # Classify each sentence
        classifications = []  # (index, sentence, claim_type_or_None)
        for i, sent in enumerate(sentences):
            if len(sent) < 15:
                classifications.append((i, sent, None))
                continue
            # LOCAL-271: Check exhortation BEFORE navigation exemption.
            # "Step into a world where time stands still" looks navigational
            # (verb "step" + "into") but is actually a vague exhortation.
            # If it classifies as EXHORTATION, treat it as such regardless
            # of navigation detection.
            claim_type = classify_claim(sent)
            if claim_type == 'EXHORTATION':
                classifications.append((i, sent, 'EXHORTATION'))
                continue
            if _is_style_navigation_sentence(sent):
                classifications.append((i, sent, None))  # Exempt
                continue
            classifications.append((i, sent, claim_type))

        # For each claim, check substantiation
        kept = []
        uncertain = []  # For potential escalation

        for i, sent, claim_type in classifications:
            if claim_type is None:
                # Not a claim — keep
                kept.append((i, sent))
                continue

            # Check substantiation using full paragraph context
            all_sents = [s for _, s, _ in classifications]
            if _is_substantiated(all_sents, i):
                # Substantiated — keep
                kept.append((i, sent))
                stats['sentences_kept_substantiated'] += 1
            else:
                # Unsubstantiated — check if we should escalate or delete
                # Escalate only if corpus has a passage plausibly related
                if api_key and corpus_passages:
                    # Check if any corpus passage shares content words with the claim
                    claim_words = _extract_content_words(sent)
                    has_relevant_passage = False
                    for passage in corpus_passages[:5]:
                        passage_words = _extract_content_words(passage)
                        if claim_words & passage_words:
                            has_relevant_passage = True
                            break

                    if has_relevant_passage:
                        uncertain.append((i, sent, claim_type))
                        continue

                # No escalation possible/needed — delete
                stats['sentences_removed'] += 1
                stats['claim_types_removed'][claim_type] += 1

        # Handle escalation batch (one call per stop max)
        if uncertain and api_key and corpus_passages:
            escalation_input = [(i, sent) for i, sent, _ in uncertain]
            escalation_results, tokens, cost = _escalate_batch(
                escalation_input, corpus_passages, api_key, model
            )
            stats['escalation_tokens'] = tokens
            stats['escalation_cost'] = cost
            stats['escalation_fired'] = True

            for i, sent, claim_type in uncertain:
                result = escalation_results.get(i)
                if result is None:
                    # LLM says delete
                    stats['sentences_removed'] += 1
                    stats['claim_types_removed'][claim_type] += 1
                else:
                    # LLM says keep or rewrite
                    kept.append((i, result))
                    stats['sentences_kept_substantiated'] += 1
        elif uncertain:
            # No API key — delete all uncertain (safe fallback)
            for i, sent, claim_type in uncertain:
                stats['sentences_removed'] += 1
                stats['claim_types_removed'][claim_type] += 1

        # Reassemble paragraph from kept sentences (in original order)
        kept.sort(key=lambda x: x[0])
        kept_texts = [sent for _, sent in kept]

        if not kept_texts:
            # All sentences removed — drop paragraph
            continue

        result_text = ' '.join(kept_texts)

        # Fix dangling connective on new first sentence
        for pat in _DANGLING_CONNECTIVE_COMPILED:
            new_text = pat.sub('', result_text, count=1)
            if new_text != result_text:
                new_text = new_text.strip()
                if new_text and new_text[0].islower():
                    new_text = new_text[0].upper() + new_text[1:]
                result_text = new_text
                break

        new_paragraphs.append(result_text.strip())

    new_description = '\n\n'.join(new_paragraphs)
    return new_description, stats


def apply_gate_to_stop_descriptions(
    poi_list: List[Dict],
    stop_corpus_data: Dict = None,
    api_key: str = None,
    model: str = None,
) -> Dict:
    """Apply the unsupported-claim gate to all stops in a tour.

    Args:
        poi_list: list of POI dicts with 'description' and 'name' keys
        stop_corpus_data: dict mapping stop_name → {passages: [...]}
        api_key: OpenAI API key for escalation
        model: LLM model for escalation

    Returns:
        Summary dict with per-stop and total stats.
    """
    total_stats = {
        'total_removed': 0,
        'total_kept_substantiated': 0,
        'claim_types_removed': {'PROMISE': 0, 'SENSORY': 0, 'FEELING': 0, 'QUALITY': 0, 'EXHORTATION': 0},
        'escalation_tokens': 0,
        'escalation_cost': 0.0,
        'escalation_calls': 0,
        'stops_affected': 0,
        'per_stop': [],
    }

    for si, poi in enumerate(poi_list):
        desc = poi.get('description', '')
        if not desc or desc.startswith('['):
            continue

        stop_name = poi.get('name', f'Stop {si + 1}')

        # Get corpus passages for this stop
        passages = []
        if stop_corpus_data and stop_name in stop_corpus_data:
            sc_entry = stop_corpus_data[stop_name]
            if sc_entry and sc_entry.get('passages'):
                passages = sc_entry['passages']

        new_desc, stats = apply_unsupported_claim_gate(
            desc, corpus_passages=passages, api_key=api_key, model=model
        )

        if stats['sentences_removed'] > 0:
            poi_list[si]['description'] = new_desc
            total_stats['stops_affected'] += 1

        total_stats['total_removed'] += stats['sentences_removed']
        total_stats['total_kept_substantiated'] += stats['sentences_kept_substantiated']
        for ct in ('PROMISE', 'SENSORY', 'FEELING', 'QUALITY', 'EXHORTATION'):
            total_stats['claim_types_removed'][ct] += stats['claim_types_removed'][ct]
        total_stats['escalation_tokens'] += stats['escalation_tokens']
        total_stats['escalation_cost'] += stats['escalation_cost']
        if stats['escalation_fired']:
            total_stats['escalation_calls'] += 1

        total_stats['per_stop'].append({
            'stop_name': stop_name,
            'removed': stats['sentences_removed'],
            'kept_substantiated': stats['sentences_kept_substantiated'],
            'claim_types': stats['claim_types_removed'],
            'escalation_fired': stats['escalation_fired'],
        })

    return total_stats
